"""
Tests for Phase B9.4 -- public share-link delivery
(restoricon_core/services/estimate_service.py's resolve_share_link()/
record_share_link_view()/_deliver_share_link(), and routes.py's new
unauthenticated `/api/v1/public/estimate/{raw_token}/...` route family).

Split into two fixture styles, matching this test suite's existing
convention (test_b9_2_estimate_service.py for service-layer-only cases,
test_b9_3_estimate_routes.py for full router/HTTP-shape cases):
  - `env`: EstimateService directly, for resolve_share_link()/
    record_share_link_view()/_deliver_share_link() unit coverage
    (including a stub NotificationService, so no live HTTP call is ever
    made here or anywhere else in this file).
  - `api_setup`: the full APIRouter, for the public route family's actual
    HTTP-shape behavior (404 uniformity, no-store headers, customer-view
    allow-list, decision recording, terminal-state 409).
"""

import hashlib

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN, ROLE_MANAGER, ROLE_SALES
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer
from restoricon_core.services.analytics_search_service import AnalyticsSearchService
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.business_ops_service import BusinessOpsService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.estimate_service import EstimateService
from restoricon_core.services.finance_service import FinanceService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService


class _StubNotificationService:
    """Records calls instead of making any real HTTP request -- this
    project's own sandbox-proxy trap (ambient HTTP_PROXY breaking loopback
    urllib calls) is exactly why the test suite must never let a real
    NotificationService.send_email() fire during a unit test."""

    def __init__(self, succeed: bool = True):
        self.succeed = succeed
        self.calls = []

    def send_email(self, to_email, subject, body, html=None, timeout=2.0):
        self.calls.append({"to_email": to_email, "subject": subject, "body": body, "timeout": timeout})
        return self.succeed


def _material_line(**overrides):
    line = {
        "line_type": "material",
        "description": "Drywall sheets",
        "customer_description": "Drywall",
        "quantity": 10,
        "unit": "SF",
        "unit_cost_cents": 1000,
        "package_qty": 1,
    }
    line.update(overrides)
    return line


# ------------------------------------------------------------------
# Service-layer fixture
# ------------------------------------------------------------------

@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    crm = CRMService(db, audit)
    notifications = _StubNotificationService()
    svc = EstimateService(db, audit, notifications)

    admin_user = auth.create_user("admin1", "Pass123!", "Admin One", "admin1@restoricon.com", role=ROLE_ADMIN)
    admin = AuthContext(admin_user.id, admin_user.username, ROLE_ADMIN, "human")

    sales_user = auth.create_user("sales1", "Pass123!", "Sales One", "sales1@restoricon.com", role=ROLE_SALES)
    sales = AuthContext(sales_user.id, sales_user.username, ROLE_SALES, "human")

    customer = crm.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@example.com"), admin
    )

    return {
        "db": db, "svc": svc, "admin": admin, "sales": sales, "customer_id": customer.id,
        "notifications": notifications,
    }


def _send(env, header):
    env["svc"].add_line(header.id, _material_line(), env["sales"])
    share_link_out = {}
    sent = env["svc"].transition(header.id, "SENT", env["sales"], share_link_out=share_link_out)
    return sent, share_link_out


# ------------------------------------------------------------------
# Service-layer coverage
# ------------------------------------------------------------------

def test_transition_send_returns_raw_token_via_out_param_never_in_header(env):
    header = env["svc"].create(customer_id=env["customer_id"], actor=env["sales"])
    sent, share_link_out = _send(env, header)

    assert share_link_out["raw_token"]
    assert len(share_link_out["raw_token"]) > 20
    # Never on the returned EstimateHeader/its to_dict() -- transition()'s
    # own return type is unchanged, and the raw token must never be
    # attachable to anything that flows into build_audit_details().
    assert "raw_token" not in sent.to_dict()
    for value in sent.to_dict().values():
        assert value != share_link_out["raw_token"]


def test_deliver_share_link_sends_email_and_persists_delivery_metadata(env):
    header = env["svc"].create(customer_id=env["customer_id"], actor=env["sales"])
    sent, share_link_out = _send(env, header)

    assert share_link_out["delivery_channel"] == "email"
    assert share_link_out["delivered_to"] == "jane@example.com"
    assert len(env["notifications"].calls) == 1
    call = env["notifications"].calls[0]
    assert call["to_email"] == "jane@example.com"
    assert share_link_out["raw_token"] in call["body"]
    assert call["timeout"] == 15.0

    link_row = env["db"].get_connection().execute(
        "SELECT delivery_channel, delivered_to FROM estimate_share_links WHERE id = ?;",
        (share_link_out["share_link_id"],),
    ).fetchone()
    assert link_row["delivery_channel"] == "email"
    assert link_row["delivered_to"] == "jane@example.com"


def test_deliver_share_link_no_notification_service_is_disclosed_gap_not_error(env):
    """NEW-712's original fallback, still true when this service was
    constructed WITHOUT a notification_service (e.g. some lazy-default
    construction paths) -- the send transition still succeeds and the raw
    token is still returned, just never emailed."""
    svc_no_notify = EstimateService(env["db"], AuditService(env["db"]))
    header = svc_no_notify.create(customer_id=env["customer_id"], actor=env["sales"])
    svc_no_notify.add_line(header.id, _material_line(), env["sales"])
    share_link_out = {}
    sent = svc_no_notify.transition(header.id, "SENT", env["sales"], share_link_out=share_link_out)

    assert sent.workflow_status == "SENT"
    assert share_link_out["raw_token"]
    assert share_link_out["delivery_channel"] is None
    assert share_link_out["delivered_to"] is None


def test_deliver_share_link_failed_send_does_not_fail_transition(env):
    env["notifications"].succeed = False
    header = env["svc"].create(customer_id=env["customer_id"], actor=env["sales"])
    sent, share_link_out = _send(env, header)

    assert sent.workflow_status == "SENT"
    assert share_link_out["raw_token"]
    assert share_link_out["delivery_channel"] is None
    assert share_link_out["delivered_to"] is None


def test_deliver_share_link_customer_with_no_email_is_disclosed_gap(env):
    admin = env["admin"]
    crm = CRMService(env["db"], AuditService(env["db"]))
    no_email_customer = crm.create_customer(Customer(first_name="No", last_name="Email"), admin)
    header = env["svc"].create(customer_id=no_email_customer.id, actor=env["sales"])
    sent, share_link_out = _send(env, header)

    assert sent.workflow_status == "SENT"
    assert share_link_out["delivery_channel"] is None
    assert len(env["notifications"].calls) == 0


def test_resolve_share_link_unknown_token_returns_none(env):
    assert env["svc"].resolve_share_link("not-a-real-token") is None


def test_resolve_share_link_valid_token_round_trips(env):
    header = env["svc"].create(customer_id=env["customer_id"], actor=env["sales"])
    _, share_link_out = _send(env, header)

    link = env["svc"].resolve_share_link(share_link_out["raw_token"])
    assert link is not None
    assert link.id == share_link_out["share_link_id"]
    assert link.estimate_id == header.id
    # The hash must match a fresh SHA-256 of the same raw token -- proves
    # resolve_share_link() actually hashes, rather than e.g. doing a raw
    # substring/prefix match.
    assert link.token_hash == hashlib.sha256(share_link_out["raw_token"].encode()).hexdigest()


def test_record_share_link_view_first_view_transitions_sent_to_viewed(env):
    header = env["svc"].create(customer_id=env["customer_id"], actor=env["sales"])
    _, share_link_out = _send(env, header)
    link = env["svc"].resolve_share_link(share_link_out["raw_token"])

    env["svc"].record_share_link_view(link)

    updated = env["svc"].get(header.id, env["admin"])
    assert updated.workflow_status == "VIEWED"

    link_row = env["db"].get_connection().execute(
        "SELECT first_viewed_at, last_viewed_at, view_count FROM estimate_share_links WHERE id = ?;",
        (link.id,),
    ).fetchone()
    assert link_row["first_viewed_at"] is not None
    assert link_row["view_count"] == 1


def test_record_share_link_view_second_view_does_not_error_or_double_transition(env):
    header = env["svc"].create(customer_id=env["customer_id"], actor=env["sales"])
    _, share_link_out = _send(env, header)
    link = env["svc"].resolve_share_link(share_link_out["raw_token"])

    env["svc"].record_share_link_view(link)
    first_viewed_row = env["db"].get_connection().execute(
        "SELECT first_viewed_at FROM estimate_share_links WHERE id = ?;", (link.id,)
    ).fetchone()
    first_viewed_at = first_viewed_row["first_viewed_at"]

    # Second view -- must not raise, must not change workflow_status again,
    # must not overwrite first_viewed_at, but view_count still climbs.
    env["svc"].record_share_link_view(link)

    updated = env["svc"].get(header.id, env["admin"])
    assert updated.workflow_status == "VIEWED"

    link_row = env["db"].get_connection().execute(
        "SELECT first_viewed_at, view_count FROM estimate_share_links WHERE id = ?;", (link.id,)
    ).fetchone()
    assert link_row["first_viewed_at"] == first_viewed_at
    assert link_row["view_count"] == 2


def test_record_decision_terminal_state_guard_blocks_second_accept(env):
    header = env["svc"].create(customer_id=env["customer_id"], actor=env["sales"])
    _, share_link_out = _send(env, header)
    link = env["svc"].resolve_share_link(share_link_out["raw_token"])

    env["svc"].record_decision(
        estimate_version_id=header.current_version_id,
        decision="accepted", ip="127.0.0.1", user_agent="pytest",
        signer_name="Jane Doe", share_link_id=link.id,
    )

    from restoricon_core.services.crm_service import ClaimConflictError
    with pytest.raises(ClaimConflictError):
        env["svc"].record_decision(
            estimate_version_id=header.current_version_id,
            decision="accepted", ip="127.0.0.1", user_agent="pytest",
            signer_name="Jane Doe", share_link_id=link.id,
        )


def test_record_decision_changes_requested_does_not_block_a_further_decision(env):
    """Pin the exact reason _DECISION_BLOCKED_STATUSES excludes
    CHANGES_REQUESTED -- test_record_decision_declined_and_changes_requested_do_not_lock
    (B9.2) already relies on this; this is the same invariant exercised
    through the share-link-scoped call shape B9.4 adds."""
    header = env["svc"].create(customer_id=env["customer_id"], actor=env["sales"])
    _, share_link_out = _send(env, header)
    link = env["svc"].resolve_share_link(share_link_out["raw_token"])

    env["svc"].record_decision(
        estimate_version_id=header.current_version_id,
        decision="changes_requested", ip="127.0.0.1", user_agent="pytest",
        share_link_id=link.id,
    )
    # Must NOT raise.
    result = env["svc"].record_decision(
        estimate_version_id=header.current_version_id,
        decision="declined", ip="127.0.0.1", user_agent="pytest",
        share_link_id=link.id,
    )
    assert result.decision == "declined"


def test_record_decision_via_share_link_persists_null_customer_user_id(env):
    header = env["svc"].create(customer_id=env["customer_id"], actor=env["sales"])
    _, share_link_out = _send(env, header)
    link = env["svc"].resolve_share_link(share_link_out["raw_token"])

    result = env["svc"].record_decision(
        estimate_version_id=header.current_version_id,
        decision="accepted", ip="127.0.0.1", user_agent="pytest",
        signer_name="Jane Doe", share_link_id=link.id,
    )
    assert result.share_link_id == link.id
    assert result.customer_user_id is None


# ------------------------------------------------------------------
# Route-layer fixture (full APIRouter, real HTTP-shape assertions)
# ------------------------------------------------------------------

@pytest.fixture
def api_setup():
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    auth = AuthService(db)
    crm = CRMService(db, audit)
    comm = CommunicationService(db)
    sched = SchedulingService(db, audit)
    auto = AutomationService(db, audit)
    ops = OperationsService(db, audit)
    fin = FinanceService(db, audit)
    bops = BusinessOpsService(db, audit)
    search = AnalyticsSearchService(db)
    estimates = EstimateService(db, audit)  # notification_service intentionally None: no live HTTP in route tests

    router = APIRouter(
        auth_service=auth,
        crm_service=crm,
        comm_service=comm,
        audit_service=audit,
        scheduling_service=sched,
        automation_service=auto,
        operations_service=ops,
        finance_service=fin,
        business_ops_service=bops,
        analytics_search_service=search,
        estimate_service=estimates,
    )

    mgr_u = auth.create_user("mgr_pub", "MgrPass123!", "Manager Pub", "mgr_pub@test.com", ROLE_MANAGER)
    mgr_tok = auth.create_token(mgr_u)
    admin_ctx = AuthContext(mgr_u.id, mgr_u.username, ROLE_MANAGER, "human")
    cust = crm.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane_pub@test.com"), admin_ctx
    )

    return {"router": router, "estimates": estimates, "db": db, "mgr_tok": mgr_tok, "cust": cust}


def _req(router, method, path, token=None, body=None):
    headers = {"authorization": f"Bearer {token}"} if token else {}
    body_bytes = json_dumps(body) if body is not None else b""
    status, res_headers, res_json = router.handle_request(method, path, headers, body_bytes)
    return status, res_headers, res_json


def json_dumps(body):
    import json
    return json.dumps(body).encode("utf-8")


def _create_and_send(router, mgr_tok, cust_id):
    status, _, res = _req(
        router, "POST", "/api/v1/estimator/estimates", mgr_tok,
        {"customer_id": cust_id, "title": "Kitchen remodel"},
    )
    assert status == 201, res
    est_id = res["estimate"]["id"]
    _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/lines", mgr_tok,
        {
            "line_type": "material", "description": "Drywall", "customer_description": "Drywall",
            "quantity": 10, "unit": "SF", "unit_cost_cents": 1000, "package_qty": 1,
        },
    )
    status, _, res = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/transition", mgr_tok, {"new_status": "SENT"}
    )
    assert status == 200, res
    return est_id, res["share_link"]["raw_token"]


def test_public_get_valid_token_returns_customer_view_no_cost_fields(api_setup):
    router = api_setup["router"]
    est_id, raw_token = _create_and_send(router, api_setup["mgr_tok"], api_setup["cust"].id)

    status, headers, res = _req(router, "GET", f"/api/v1/public/estimate/{raw_token}")
    assert status == 200, res
    assert headers["Cache-Control"] == "no-store"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["X-Robots-Tag"] == "noindex"
    assert "total_cents" in res
    # to_customer_view()'s allow-list must never leak internal cost fields.
    assert "cost_total_cents" not in res
    assert "gross_profit_cents" not in res
    assert "gross_margin_bp" not in res


def test_public_get_invalid_token_returns_uniform_404(api_setup):
    router = api_setup["router"]
    status, headers, res = _req(router, "GET", "/api/v1/public/estimate/totally-bogus-token")
    assert status == 404
    assert res == {"error": "Not found"}


def test_public_get_expired_token_returns_uniform_404(api_setup):
    router = api_setup["router"]
    est_id, raw_token = _create_and_send(router, api_setup["mgr_tok"], api_setup["cust"].id)

    db = api_setup["db"]
    db.get_connection().execute(
        "UPDATE estimate_share_links SET expires_at = '2000-01-01T00:00:00+00:00' "
        "WHERE token_hash = ?;",
        (hashlib.sha256(raw_token.encode()).hexdigest(),),
    )
    db.get_connection().commit()

    status, headers, res = _req(router, "GET", f"/api/v1/public/estimate/{raw_token}")
    assert status == 404
    assert res == {"error": "Not found"}


def test_public_get_revoked_token_returns_uniform_404(api_setup):
    router = api_setup["router"]
    est_id, raw_token = _create_and_send(router, api_setup["mgr_tok"], api_setup["cust"].id)

    db = api_setup["db"]
    db.get_connection().execute(
        "UPDATE estimate_share_links SET revoked_at = '2026-01-01T00:00:00+00:00' "
        "WHERE token_hash = ?;",
        (hashlib.sha256(raw_token.encode()).hexdigest(),),
    )
    db.get_connection().commit()

    status, headers, res = _req(router, "GET", f"/api/v1/public/estimate/{raw_token}")
    assert status == 404
    assert res == {"error": "Not found"}


def test_public_get_first_view_transitions_to_viewed_second_view_does_not_error(api_setup):
    router = api_setup["router"]
    est_id, raw_token = _create_and_send(router, api_setup["mgr_tok"], api_setup["cust"].id)

    status, _, res = _req(router, "GET", f"/api/v1/public/estimate/{raw_token}")
    assert status == 200, res
    updated = api_setup["estimates"].get(est_id, api_setup_actor(api_setup))
    assert updated.workflow_status == "VIEWED"

    # Second view -- must still succeed, not double-error.
    status, _, res = _req(router, "GET", f"/api/v1/public/estimate/{raw_token}")
    assert status == 200, res


def api_setup_actor(api_setup):
    auth = api_setup["router"].auth
    return auth.authenticate_token(api_setup["mgr_tok"])


def test_public_decision_accept_creates_contract_and_declines_create_no_contract(api_setup):
    router = api_setup["router"]
    est_id, raw_token = _create_and_send(router, api_setup["mgr_tok"], api_setup["cust"].id)

    status, _, res = _req(
        router, "POST", f"/api/v1/public/estimate/{raw_token}/decision", None,
        {"decision": "accepted", "signer_name": "Jane Doe"},
    )
    assert status == 201, res

    updated = api_setup["estimates"].get(est_id, api_setup_actor(api_setup))
    assert updated.workflow_status == "ACCEPTED"
    assert updated.contract_id is not None


def test_public_decision_decline_creates_no_contract(api_setup):
    router = api_setup["router"]
    est_id, raw_token = _create_and_send(router, api_setup["mgr_tok"], api_setup["cust"].id)

    status, _, res = _req(
        router, "POST", f"/api/v1/public/estimate/{raw_token}/decision", None,
        {"decision": "declined"},
    )
    assert status == 201, res

    updated = api_setup["estimates"].get(est_id, api_setup_actor(api_setup))
    assert updated.workflow_status == "DECLINED"
    assert updated.contract_id is None


def test_public_decision_on_already_decided_estimate_returns_409(api_setup):
    router = api_setup["router"]
    est_id, raw_token = _create_and_send(router, api_setup["mgr_tok"], api_setup["cust"].id)

    status, _, res = _req(
        router, "POST", f"/api/v1/public/estimate/{raw_token}/decision", None,
        {"decision": "declined"},
    )
    assert status == 201, res

    status, _, res = _req(
        router, "POST", f"/api/v1/public/estimate/{raw_token}/decision", None,
        {"decision": "accepted", "signer_name": "Jane Doe"},
    )
    assert status == 409, res


def test_public_decision_ignores_client_supplied_customer_user_id(api_setup):
    """§4.1/NEW-719: customer_user_id must never be trusted from this
    request's body -- persisted row must show share_link_id set and
    customer_user_id NULL, matching record_decision()'s own XOR
    invariant, regardless of what the (attacker-controlled) body claims."""
    router = api_setup["router"]
    est_id, raw_token = _create_and_send(router, api_setup["mgr_tok"], api_setup["cust"].id)

    status, _, res = _req(
        router, "POST", f"/api/v1/public/estimate/{raw_token}/decision", None,
        {"decision": "accepted", "signer_name": "Jane Doe", "customer_user_id": 999999},
    )
    assert status == 201, res

    db = api_setup["db"]
    row = db.get_connection().execute(
        "SELECT customer_user_id, share_link_id FROM estimate_decisions WHERE id = ?;",
        (res["decision"]["id"],),
    ).fetchone()
    assert row["customer_user_id"] is None
    assert row["share_link_id"] is not None
    assert row["share_link_id"] != 999999


def test_public_decision_invalid_token_returns_uniform_404(api_setup):
    router = api_setup["router"]
    status, headers, res = _req(
        router, "POST", "/api/v1/public/estimate/bogus/decision", None, {"decision": "declined"}
    )
    assert status == 404
    assert res == {"error": "Not found"}


def test_public_route_extra_path_segments_return_uniform_404(api_setup):
    router = api_setup["router"]
    est_id, raw_token = _create_and_send(router, api_setup["mgr_tok"], api_setup["cust"].id)
    status, headers, res = _req(router, "GET", f"/api/v1/public/estimate/{raw_token}/something-else")
    assert status == 404
    assert res == {"error": "Not found"}


def test_public_get_superseded_link_returns_superseded_marker(api_setup):
    """§4.2: a link is scoped to exactly one estimate_version_id -- once
    revise() moves the estimate on to a new current_version_id, the OLD
    link must not silently serve the new version's numbers."""
    router = api_setup["router"]
    est_id, raw_token = _create_and_send(router, api_setup["mgr_tok"], api_setup["cust"].id)

    status, _, res = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/revise", api_setup["mgr_tok"]
    )
    assert status == 200, res

    status, _, res = _req(router, "GET", f"/api/v1/public/estimate/{raw_token}")
    assert status == 200, res
    assert res == {"superseded": True}
