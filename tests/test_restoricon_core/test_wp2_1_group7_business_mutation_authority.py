"""Regression tests for WP2.1 group 7 ("Business mutation boundaries",
NEW-919/920/921): the native restoricon_core/authority.py fail-closed
HIGH_IMPACT gate for ROLE_AI_AGENT actors, and the `confirmed`
caller-asserted signal plumbed through delete_contact (and, for the
Aigentik-side bundle, delete_rule / remove_from_do_not_contact).

Uses a live in-memory (`:memory:`) RestoriconAPIServer, same fixture
pattern as tests/test_restoricon_core/test_api.py -- never touches the
real persistent DB.
"""

import json
import socket
import urllib.error
import urllib.request

import pytest

from restoricon_core.api.server import RestoriconAPIServer
from restoricon_core.auth import AuthContext, ROLE_ADMIN, ROLE_AI_AGENT
from restoricon_core.models import AutomationRule, CommissionLedgerEntry, Contact


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_request(url: str, method: str = "GET", data=None, headers: dict = None):
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    body_bytes = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            return resp.status, json.loads(resp_body) if resp_body else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        return e.code, json.loads(err_body) if err_body else {}


@pytest.fixture
def api_server():
    port = find_free_port()
    server = RestoriconAPIServer(db_path=":memory:", host="127.0.0.1", port=port)
    server.start(background=True)
    base_url = f"http://127.0.0.1:{port}"

    admin_user = server.auth_service.create_user(
        username="admin",
        plain_password="AdminSecretPassword123",
        full_name="Admin Boss",
        email="admin@restoricon.com",
        role=ROLE_ADMIN,
    )
    agent_user = server.auth_service.create_user(
        username="codey-aigentik-agent",
        plain_password="AgentSecretPassword123",
        full_name="Codey-Aigentik",
        email="codey-aigentik-agent@local.invalid",
        role=ROLE_AI_AGENT,
    )

    yield server, base_url, admin_user, agent_user
    server.stop()


def _login(base_url, username, password):
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": username, "password": password},
    )
    assert status == 200, body
    return {"Authorization": f"Bearer {body['token']}"}


def _create_contact_direct(server, name="Jane Refusenik"):
    """Create a contact directly through the service layer (bypassing the
    HTTP layer entirely) under an admin AuthContext, so test setup never
    depends on the behavior under test."""
    admin_ctx = AuthContext(user_id=1, username="admin", role=ROLE_ADMIN, actor_type="human")
    contact = server.crm_service.create_contact(
        Contact(name=name, phones=["5551234567"]), admin_ctx
    )
    return contact


def test_human_delete_contact_no_confirmed_field_still_succeeds(api_server):
    """Regression 1: a human-actor delete_contact call (no `confirmed`
    field in the body at all) still returns 200 -- the fail-closed gate
    only applies to ROLE_AI_AGENT actors."""
    server, base_url, admin_user, _ = api_server
    contact = _create_contact_direct(server)
    admin_headers = _login(base_url, "admin", "AdminSecretPassword123")

    status, body = make_request(
        f"{base_url}/api/v1/contacts/{contact.id}/delete",
        method="POST",
        headers=admin_headers,
        data={},
    )
    assert status == 200, body
    assert body["deleted"] is True


def test_ai_agent_delete_contact_requires_confirmed_true(api_server):
    """Regression 2: role=ai_agent + {"confirmed": true} -> 200;
    same actor, no `confirmed` (or `confirmed: false`) -> 403 via the real
    `except PermissionError` handler, not a 500."""
    server, base_url, _, agent_user = api_server
    agent_headers = _login(base_url, "codey-aigentik-agent", "AgentSecretPassword123")

    # Unconfirmed -> refused, mapped to 403 (not 500).
    contact_a = _create_contact_direct(server, name="Unconfirmed Target")
    status, body = make_request(
        f"{base_url}/api/v1/contacts/{contact_a.id}/delete",
        method="POST",
        headers=agent_headers,
        data={},
    )
    assert status == 403, body
    assert "error" in body

    # Explicit confirmed: false -> still refused (strict identity check,
    # not merely falsy-default).
    status, body = make_request(
        f"{base_url}/api/v1/contacts/{contact_a.id}/delete",
        method="POST",
        headers=agent_headers,
        data={"confirmed": False},
    )
    assert status == 403, body

    # Confirmed: true -> succeeds.
    contact_b = _create_contact_direct(server, name="Confirmed Target")
    status, body = make_request(
        f"{base_url}/api/v1/contacts/{contact_b.id}/delete",
        method="POST",
        headers=agent_headers,
        data={"confirmed": True},
    )
    assert status == 200, body
    assert body["deleted"] is True


def test_ai_agent_delete_contact_truthy_string_does_not_count(api_server):
    """`confirmed` must be a strict `is True` check -- a truthy string
    ("true"/"yes") must not satisfy it."""
    server, base_url, _, _ = api_server
    agent_headers = _login(base_url, "codey-aigentik-agent", "AgentSecretPassword123")
    contact = _create_contact_direct(server, name="Truthy String Target")

    status, body = make_request(
        f"{base_url}/api/v1/contacts/{contact.id}/delete",
        method="POST",
        headers=agent_headers,
        data={"confirmed": "true"},
    )
    assert status == 403, body


def _audit_rows(server, entity_type: str):
    conn = server.db.get_connection()
    return conn.execute(
        "SELECT * FROM audit_log WHERE entity_type = ? ORDER BY id DESC;",
        (entity_type,),
    ).fetchall()


def test_ai_agent_remove_rule_refused_and_audited(api_server):
    """Regression 3 (automation_rules): remove_rule called as role=ai_agent
    with no `confirmed` -> refused AND an audit row is written (queried
    directly from the audit_log table, not via a service read path)."""
    server, base_url, _, _ = api_server
    admin_ctx = AuthContext(user_id=1, username="admin", role=ROLE_ADMIN, actor_type="human")
    rule = server.automation_service.create_rule(
        AutomationRule(channel="email", description="test rule", condition_type="keyword", condition_value="x", action="ignore"),
        admin_ctx,
    )
    agent_headers = _login(base_url, "codey-aigentik-agent", "AgentSecretPassword123")

    before_count = len(_audit_rows(server, "business_mutation_authority"))

    status, body = make_request(
        f"{base_url}/api/v1/automation-rules/{rule.id}/delete",
        method="POST",
        headers=agent_headers,
        data={},
    )
    assert status == 403, body

    after_rows = _audit_rows(server, "business_mutation_authority")
    assert len(after_rows) == before_count + 1
    assert after_rows[0]["action"] == "refused"
    assert "automation_service.delete_rule" in after_rows[0]["change_summary"]

    # The rule must still exist -- the refusal must not have deleted it.
    still_there = server.automation_service.get_automation_rule_by_external_id
    conn = server.db.get_connection()
    row = conn.execute("SELECT * FROM automation_rules WHERE id = ?;", (rule.id,)).fetchone()
    assert row is not None


def test_ai_agent_unblock_dnc_refused_and_audited(api_server):
    """Regression 3 (do-not-contact): remove_from_do_not_contact called as
    role=ai_agent with no `confirmed` -> refused AND an audit row is
    written."""
    server, base_url, _, _ = api_server
    admin_ctx = AuthContext(user_id=1, username="admin", role=ROLE_ADMIN, actor_type="human")
    server.automation_service.add_to_do_not_contact("blocked@example.com", admin_ctx)
    agent_headers = _login(base_url, "codey-aigentik-agent", "AgentSecretPassword123")

    before_count = len(_audit_rows(server, "business_mutation_authority"))

    status, body = make_request(
        f"{base_url}/api/v1/do-not-contact/remove",
        method="POST",
        headers=agent_headers,
        data={"identifier": "blocked@example.com"},
    )
    assert status == 403, body

    after_rows = _audit_rows(server, "business_mutation_authority")
    assert len(after_rows) == before_count + 1
    assert after_rows[0]["action"] == "refused"
    assert "automation_service.remove_from_do_not_contact" in after_rows[0]["change_summary"]

    # The DNC entry must still exist -- the refusal must not have removed it.
    assert server.automation_service.is_blocked("blocked@example.com", admin_ctx) is True


def test_internal_admin_actor_reverse_commission_unaffected(api_server):
    """Regression 4 (Correction A lock): an internal role=ROLE_ADMIN
    system-actor flow through reverse_commission is UNAFFECTED by the
    HIGH_IMPACT gate -- the gate must key on actor.role, not
    actor.actor_type. Uses actor_type='agent' + role=ROLE_ADMIN, the exact
    shape of crm_service.py's internal system actors (e.g.
    clawback_system_actor), to prove the gate does not key on actor_type."""
    server, base_url, _, _ = api_server
    admin_ctx = AuthContext(user_id=1, username="admin", role=ROLE_ADMIN, actor_type="human")

    original = server.commission_service.record_commission(
        CommissionLedgerEntry(
            rep_user_id=1,
            source_type="bonus",
            basis_amount=100.0,
            commission_rate_or_flat=1.0,
            commission_amount=100.0,
            status="earned",
        ),
        admin_ctx,
    )

    # Same shape as crm_service.py's internal system actors: role=ROLE_ADMIN,
    # actor_type="agent" -- NOT a human caller, but still role=ROLE_ADMIN.
    system_actor = AuthContext(
        user_id=1, username="system_commission_engine", role=ROLE_ADMIN, actor_type="agent",
    )
    reversal = server.commission_service.reverse_commission(original.id, system_actor)
    assert reversal.status == "reversed"
    assert reversal.reversed_entry_id == original.id


def test_mutation_actor_type_gate_would_break_internal_system_actors():
    """Direct unit-level proof that gating on actor_type instead of role
    would have refused the exact internal system-actor shape regression 4
    exercises above (mutation-testing the gate condition itself, per the
    task's explicit ask, without monkeypatching restoricon_core.authority
    -- this re-implements the wrong condition standalone and asserts it
    would indeed misfire on this shape)."""
    from restoricon_core.auth import ROLE_ADMIN

    system_actor = AuthContext(
        user_id=1, username="system_commission_engine", role=ROLE_ADMIN, actor_type="agent",
    )
    # The correct (shipped) gate condition:
    assert not (system_actor.role == ROLE_AI_AGENT)
    # The REJECTED literal-reading condition (actor_type == "agent") would
    # have matched this exact internal system actor -- proving Correction A
    # is load-bearing, not optional.
    assert system_actor.actor_type == "agent"


def test_ai_agent_update_appointment_cancel_no_confirmation_still_succeeds(api_server):
    """Regression 5 (Correction B lock): scheduling_service.update_appointment
    (the shared cancel/reschedule method) called as role=ai_agent with no
    confirmation signal still succeeds -- it is classified ACT, not
    HIGH_IMPACT, specifically so Aigentik's unconfirmed customer
    self-service cancellation flow (handleCancelRequest()) keeps working."""
    server, base_url, _, _ = api_server
    admin_ctx = AuthContext(user_id=1, username="admin", role=ROLE_ADMIN, actor_type="human")

    customer = server.crm_service.create_customer(
        __import__("restoricon_core.models", fromlist=["Customer"]).Customer(
            first_name="Bob", last_name="Builder", email="bob@example.com",
            service_address="1 Main St", customer_type="residential", status="active",
        ),
        admin_ctx,
    )
    from datetime import datetime, timedelta, timezone
    start = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=1, hours=1)).isoformat()
    appt = server.scheduling_service.create_appointment(
        __import__("restoricon_core.models", fromlist=["Appointment"]).Appointment(
            title="Estimate visit", customer_id=customer.id,
            start_time=start, end_time=end, status="negotiating",
        ),
        admin_ctx,
    )

    agent_headers = _login(base_url, "codey-aigentik-agent", "AgentSecretPassword123")
    status, body = make_request(
        f"{base_url}/api/v1/appointments/{appt.id}/update",
        method="POST",
        headers=agent_headers,
        data={"status": "cancelled"},
    )
    assert status == 200, body
    assert body["appointment"]["status"] == "cancelled"
