"""
Unit tests for B8.10c: POST /api/v1/customers/<id>/compose-email -- the only
B8.10 sub-phase with a real external side effect (a genuine email sent via
NotificationService.send_email -> Aigentik's /send-email -> real Gmail SMTP).

Covers:
- NEW-620's mandatory send-then-log ordering: a successful send (mocked
  urllib.request.urlopen returning 200) produces exactly one
  CommunicationRecord with correct fields; a failed send (mocked to raise/
  return non-200) produces ZERO CommunicationRecord entries.
- RBAC: an actor lacking PERM_LOG_COMMUNICATION is denied with zero outbound
  HTTP calls attempted (not just a 403 after the fact).
- Ownership narrowing: a rep composing to a customer they are not assigned
  to (and who isn't unclaimed) is denied, reusing get_customer's existing
  NEW-568 narrowing -- same as every other customer-scoped route.
- Recipient locking: the outbound `to` address is always the customer's own
  address from the database, never an attacker-supplied field from the
  request body, even when the body explicitly includes one.
- The rep's display name appears in the sent body (signature).
- notification_service=None (a legitimately constructible CRMService state)
  is handled with a clean error, not an AttributeError.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.notification_service import NotificationService
from restoricon_core.services.scheduling_service import SchedulingService


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    comm = CommunicationService(db)
    notif = NotificationService()
    crm = CRMService(db, audit, notif)
    sched = SchedulingService(db, audit)
    auto = AutomationService(db, audit)
    router = APIRouter(auth, crm, comm, audit, sched, auto)

    admin_user = auth.create_user("admin_user", "Pass123!", "Admin User", "admin@test.com", ROLE_ADMIN)
    admin_actor = AuthContext(admin_user.id, "admin_user", ROLE_ADMIN, "human")

    rep_a_user = auth.create_user("rep_a", "Pass123!", "Rep Alpha", "repa@test.com", ROLE_SALES)
    rep_b_user = auth.create_user("rep_b", "Pass123!", "Rep Beta", "repb@test.com", ROLE_SALES)

    tokens = {
        "admin": auth.create_token(admin_user),
        "rep_a": auth.create_token(rep_a_user),
        "rep_b": auth.create_token(rep_b_user),
    }

    cust_a = crm.create_customer(
        Customer(first_name="Cust", last_name="A", email="custa@example.com", assigned_user_id=rep_a_user.id),
        admin_actor,
    )
    cust_no_email = crm.create_customer(
        Customer(first_name="Cust", last_name="NoEmail", email=None, assigned_user_id=rep_a_user.id),
        admin_actor,
    )

    return {
        "db": db, "auth": auth, "crm": crm, "comm": comm, "router": router,
        "notif": notif,
        "tokens": tokens,
        "rep_a_user": rep_a_user, "rep_b_user": rep_b_user,
        "cust_a": cust_a, "cust_no_email": cust_no_email,
    }


def _compose(router, token, customer_id, subject="Hello", body="This is a test message."):
    return router.handle_request(
        "POST", f"/api/v1/customers/{customer_id}/compose-email",
        {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json.dumps({"subject": subject, "body": body}).encode("utf-8"),
    )


def _fake_200_response():
    fake_response = MagicMock()
    fake_response.getcode.return_value = 200
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False
    return fake_response


# ---------------------------------------------------------------------
# NEW-620: send-then-log ordering -- the single most important test.
# ---------------------------------------------------------------------

def test_successful_send_produces_exactly_one_communication_record(env):
    router = env["router"]
    with patch("urllib.request.urlopen", return_value=_fake_200_response()) as mock_urlopen:
        status, _, data = _compose(
            router, env["tokens"]["rep_a"], env["cust_a"].id,
            subject="Project Update", body="Here is your update.",
        )

    assert status == 201
    assert mock_urlopen.call_count == 1
    comm_id = data["communication"]["id"]

    records = env["comm"].query_communications(
        AuthContext(env["rep_a_user"].id, "rep_a", ROLE_SALES, "human"),
        customer_id=env["cust_a"].id,
    )
    matching = [r for r in records if r.id == comm_id]
    assert len(matching) == 1
    rec = matching[0]
    assert rec.channel == "email"
    assert rec.direction == "outbound"
    assert rec.customer_id == env["cust_a"].id
    assert rec.subject == "Project Update"
    assert rec.content == "Here is your update."
    assert rec.actor_id == env["rep_a_user"].id


def test_failed_send_produces_zero_communication_records(env):
    """The load-bearing NEW-620 regression test: a failed send (urlopen
    raising, exactly like a real connection failure or timeout) must not
    create a CommunicationRecord -- send-then-log, not log-then-send."""
    router = env["router"]
    import urllib.error

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        status, _, data = _compose(router, env["tokens"]["rep_a"], env["cust_a"].id)

    assert status == 502
    assert "error" in data

    records = env["comm"].query_communications(
        AuthContext(env["rep_a_user"].id, "rep_a", ROLE_SALES, "human"),
        customer_id=env["cust_a"].id,
    )
    assert records == []


def test_failed_send_via_timeout_produces_zero_communication_records(env):
    """NEW-623-shaped failure: a socket timeout (TimeoutError, NOT a
    URLError subclass) lands in _post_request's bare except branch and
    returns False -- must still result in zero phantom records."""
    router = env["router"]

    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        status, _, data = _compose(router, env["tokens"]["rep_a"], env["cust_a"].id)

    assert status == 502
    records = env["comm"].query_communications(
        AuthContext(env["rep_a_user"].id, "rep_a", ROLE_SALES, "human"),
        customer_id=env["cust_a"].id,
    )
    assert records == []


def test_non_200_response_produces_zero_communication_records(env):
    router = env["router"]
    fake_response = MagicMock()
    fake_response.getcode.return_value = 500
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False

    with patch("urllib.request.urlopen", return_value=fake_response):
        status, _, data = _compose(router, env["tokens"]["rep_a"], env["cust_a"].id)

    assert status == 502
    records = env["comm"].query_communications(
        AuthContext(env["rep_a_user"].id, "rep_a", ROLE_SALES, "human"),
        customer_id=env["cust_a"].id,
    )
    assert records == []


# ---------------------------------------------------------------------
# RBAC: PERM_LOG_COMMUNICATION denial must happen BEFORE any send attempt.
# ---------------------------------------------------------------------

def test_actor_lacking_permission_is_denied_with_zero_outbound_calls(env):
    """ROLE_CUSTOMER holds PERM_LOG_COMMUNICATION in general (for portal
    messages) but this route explicitly excludes ROLE_CUSTOMER entirely
    (out of scope -- staff/sales-portal only). Use a role/permission
    combination that genuinely lacks PERM_LOG_COMMUNICATION instead:
    a plain ROLE_SALES actor always holds it, so directly strip it via
    custom_permissions to exercise the denial path."""
    router = env["router"]
    auth = env["auth"]
    from restoricon_core.auth import PERM_LOG_COMMUNICATION

    no_perm_user = auth.create_user(
        "no_perm_rep", "Pass123!", "No Perm Rep", "noperm@test.com", ROLE_SALES,
        custom_permissions={PERM_LOG_COMMUNICATION: False},
    )
    token = auth.create_token(no_perm_user)

    with patch("urllib.request.urlopen") as mock_urlopen:
        status, _, data = _compose(router, token, env["cust_a"].id)

    assert status == 403
    assert mock_urlopen.call_count == 0

    records = env["comm"].query_communications(
        AuthContext(env["rep_a_user"].id, "rep_a", ROLE_SALES, "human"),
        customer_id=env["cust_a"].id,
    )
    assert records == []


def test_customer_role_is_denied(env):
    """This is a staff/sales-portal compose action; ROLE_CUSTOMER (which
    otherwise holds PERM_LOG_COMMUNICATION for portal_messages) must not
    be able to reach it at all."""
    from restoricon_core.auth import ROLE_CUSTOMER

    router = env["router"]
    auth = env["auth"]
    cust_user = auth.create_user(
        "cust_login", "Pass123!", "Cust Login", "custlogin@test.com", ROLE_CUSTOMER,
        customer_id=env["cust_a"].id,
    )
    token = auth.create_token(cust_user)

    with patch("urllib.request.urlopen") as mock_urlopen:
        status, _, _ = _compose(router, token, env["cust_a"].id)

    assert status == 403
    assert mock_urlopen.call_count == 0


# ---------------------------------------------------------------------
# Ownership narrowing: reuses get_customer's existing NEW-568 pattern.
# ---------------------------------------------------------------------

def test_rep_cannot_compose_to_unowned_customer(env):
    router = env["router"]

    with patch("urllib.request.urlopen") as mock_urlopen:
        status, _, data = _compose(router, env["tokens"]["rep_b"], env["cust_a"].id)

    assert status == 404
    assert mock_urlopen.call_count == 0


def test_admin_can_compose_to_any_customer(env):
    router = env["router"]
    with patch("urllib.request.urlopen", return_value=_fake_200_response()):
        status, _, data = _compose(router, env["tokens"]["admin"], env["cust_a"].id)
    assert status == 201


# ---------------------------------------------------------------------
# Recipient locking: the request body cannot redirect the send.
# ---------------------------------------------------------------------

def test_recipient_is_locked_to_customer_email_not_request_body(env):
    router = env["router"]
    with patch("urllib.request.urlopen", return_value=_fake_200_response()) as mock_urlopen:
        status, _, data = router.handle_request(
            "POST", f"/api/v1/customers/{env['cust_a'].id}/compose-email",
            {"Authorization": f"Bearer {env['tokens']['rep_a']}", "Content-Type": "application/json"},
            json.dumps({
                "subject": "Hi",
                "body": "Test",
                "to": "attacker@evil.com",
                "to_email": "attacker@evil.com",
            }).encode("utf-8"),
        )

    assert status == 201
    req = mock_urlopen.call_args.args[0]
    sent_payload = json.loads(req.data.decode("utf-8"))
    assert sent_payload["to"] == env["cust_a"].email
    assert sent_payload["to"] != "attacker@evil.com"


def test_customer_with_no_email_is_rejected(env):
    router = env["router"]
    with patch("urllib.request.urlopen") as mock_urlopen:
        status, _, data = _compose(router, env["tokens"]["rep_a"], env["cust_no_email"].id)
    assert status == 400
    assert mock_urlopen.call_count == 0


# ---------------------------------------------------------------------
# Rep name appears in the sent body (signature).
# ---------------------------------------------------------------------

def test_rep_display_name_appears_in_sent_body(env):
    router = env["router"]
    with patch("urllib.request.urlopen", return_value=_fake_200_response()) as mock_urlopen:
        _compose(router, env["tokens"]["rep_a"], env["cust_a"].id, body="Thanks for your patience.")

    req = mock_urlopen.call_args.args[0]
    sent_payload = json.loads(req.data.decode("utf-8"))
    assert "Rep Alpha" in sent_payload["text"]
    assert "Thanks for your patience." in sent_payload["text"]


# ---------------------------------------------------------------------
# notification_service=None -- a legitimately constructible CRMService
# state (see its own __init__ comment) -- must not raise AttributeError.
# ---------------------------------------------------------------------

def test_missing_notification_service_returns_clean_error(env):
    db = env["db"]
    auth = env["auth"]
    audit = AuditService(db)
    comm = env["comm"]
    crm_no_notif = CRMService(db, audit, notification_service=None)
    sched = SchedulingService(db, audit)
    auto = AutomationService(db, audit)
    router_no_notif = APIRouter(auth, crm_no_notif, comm, audit, sched, auto)

    with patch("urllib.request.urlopen") as mock_urlopen:
        status, _, data = _compose(router_no_notif, env["tokens"]["rep_a"], env["cust_a"].id)

    assert status == 503
    assert mock_urlopen.call_count == 0


def test_missing_body_is_rejected(env):
    router = env["router"]
    with patch("urllib.request.urlopen") as mock_urlopen:
        status, _, data = router.handle_request(
            "POST", f"/api/v1/customers/{env['cust_a'].id}/compose-email",
            {"Authorization": f"Bearer {env['tokens']['rep_a']}", "Content-Type": "application/json"},
            json.dumps({"subject": "Hi", "body": "   "}).encode("utf-8"),
        )
    assert status == 400
    assert mock_urlopen.call_count == 0


def test_route_requires_valid_token(env):
    status, _, _ = env["router"].handle_request(
        "POST", f"/api/v1/customers/{env['cust_a'].id}/compose-email",
        {"Authorization": "Bearer not-a-real-token"},
        json.dumps({"subject": "Hi", "body": "Test"}).encode("utf-8"),
    )
    assert status == 401


# ---------------------------------------------------------------------
# Rendered-surface test: catches a UI-wiring regression (e.g. a template
# string that no longer matches, or a renamed handler) that a purely
# backend test suite would never see. NEW-259's lesson (a diff that
# passed every test but shipped a permanent no-op) is why this exists,
# not just the backend route tests above.
# ---------------------------------------------------------------------

def test_sales_portal_renders_compose_ui():
    from restoricon_core.api.web_surfaces import render_sales_surface

    html = render_sales_surface()
    assert 'id="composeEmailModal"' in html
    assert "function openComposeEmailModal()" in html
    assert "function sendComposeEmail()" in html
    assert "/compose-email" in html
    assert "onclick=\"openComposeEmailModal()\"" in html
