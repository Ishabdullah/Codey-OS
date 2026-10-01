"""
Integration/unit tests for CODEY_MASTER_PLAN.md B8.11 "AI Sales Copilot"
(Part A shared budget-gated completion helper, Part B
/api/v1/sales/copilot-summary, Part C /api/v1/sales/appointment-prep).

Spins up a real RestoriconAPIServer (same pattern as
tests/test_ccos_crm_read.py's `crm_server_and_token` fixture) and hits the
two new routes over real HTTP, with `ccos.core.plugin_manager.get_plugin_manager`
and `restoricon_core.api.routes._call_budget_gated_completion` monkeypatched
-- the actual prose-generation completion call itself is explicitly out of
scope this round (requires a live model load, CLAUDE.md rule 2), so these
tests verify everything up to and including the one completion call site,
never the real llama-server call.
"""

import socket
import time

import pytest
import requests

import restoricon_core.api.routes as routes_mod
from restoricon_core.api.server import RestoriconAPIServer
from restoricon_core.auth import (
    PERM_READ_LEADS,
    PERM_READ_OPPORTUNITIES,
    ROLE_ADMIN,
    ROLE_SALES,
    ROLE_TECHNICIAN,
    AuthContext,
)
from restoricon_core.models import Appointment, Customer


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _FakePluginManager:
    """Records every call_capability() invocation's name + kwargs, so
    tests can assert on exactly what Core passed through -- the
    actor-scoping derivation is the thing under test here, not the real
    crm_core_query plugin's own behavior (already covered by
    tests/test_ccos_crm_read.py)."""

    _modules = {"crm_core_query": object()}  # pre-populated -> no load() needed

    def __init__(self):
        self.calls = []

    def call_capability(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if name == "crm.list_properties":
            return {"properties": [], "returned": 0, "truncated": False}
        if name == "crm.list_estimates":
            return {"estimates": [], "returned": 0, "truncated": False}
        if name == "crm.list_communications":
            return {"communications": [], "returned": 0, "truncated": False}
        if name == "crm.get_pipeline_summary":
            return {"pipeline_summary": {}}
        return {"leads": [], "opportunities": [], "tasks": [], "customers": [], "returned": 0, "truncated": False}


@pytest.fixture
def copilot_fixture(tmp_path, monkeypatch):
    db_path = str(tmp_path / "core.db")
    port = _find_free_port()
    server = RestoriconAPIServer(db_path=db_path, host="127.0.0.1", port=port)
    server.start(background=True)
    time.sleep(0.1)

    admin = server.auth_service.create_user(
        username="admin", plain_password="AdminPass123!", full_name="Admin",
        email="admin@test.restoricon", role=ROLE_ADMIN,
    )
    admin_ctx = server.auth_service.authenticate_token(server.auth_service.create_token(admin))
    admin_token = server.auth_service.create_token(admin)

    # ROLE_SALES lacks PERM_READ_TEAM_SALES_DATA by default (auth.py) --
    # a realistic narrowed actor, not a hand-built custom_permissions dict.
    rep_a = server.auth_service.create_user(
        username="rep_a", plain_password="RepAPass123!", full_name="Rep A",
        email="rep_a@test.restoricon", role=ROLE_SALES,
    )
    rep_a_token = server.auth_service.create_token(rep_a)
    rep_b = server.auth_service.create_user(
        username="rep_b", plain_password="RepBPass123!", full_name="Rep B",
        email="rep_b@test.restoricon", role=ROLE_SALES,
    )
    rep_b_token = server.auth_service.create_token(rep_b)

    cust1 = server.crm_service.create_customer(
        Customer(first_name="Alice", last_name="Smith", phone="+15551234567"), admin_ctx
    )
    appt_rep_a = server.scheduling_service.create_appointment(
        Appointment(customer_id=cust1.id, assigned_user_id=rep_a.id, title="Inspection"), admin_ctx
    )
    appt_unassigned = server.scheduling_service.create_appointment(
        Appointment(customer_id=cust1.id, title="Unassigned appt"), admin_ctx
    )
    appt_no_customer = server.scheduling_service.create_appointment(
        Appointment(title="No customer appt"), admin_ctx
    )

    # NEW-546-class guard test fixture: a sentinel bearer token that
    # resolves to a real, valid AuthContext with user_id=None -- mirrors
    # migrate_aigentik.py's own ai_agent-only construction path (per
    # routes.py's own comment on this precondition being otherwise
    # unreachable via a real login). authenticate_token() is monkeypatched
    # only for this one sentinel token value; every other token still goes
    # through the real DB-backed path unchanged.
    _real_authenticate_token = server.auth_service.authenticate_token
    _NO_USER_ID_TOKEN = "sentinel-no-user-id-token"

    # CHANGES-REQUESTED Critical finding fix (code-reviewer round 1,
    # b8_11_ai_sales_copilot_approved): a ROLE_TECHNICIAN actor holds none
    # of PERM_READ_LEADS/PERM_READ_OPPORTUNITIES/PERM_READ_CRM/
    # PERM_READ_TEAM_SALES_DATA (verified directly against
    # ROLE_PERMISSIONS[ROLE_TECHNICIAN] in auth.py) -- this is the
    # reviewer's own live repro actor, reproduced here as a sentinel token
    # the same way the no-user-id guard above is, rather than going through
    # real signup (no CRM permission to grant it through normal role
    # assignment).
    _TECHNICIAN_TOKEN = "sentinel-technician-token"
    _technician_ctx = AuthContext(
        user_id=99901, username="tech", role=ROLE_TECHNICIAN, actor_type="human"
    )

    # No real role holds PERM_READ_LEADS without also holding
    # PERM_READ_OPPORTUNITIES or vice versa (confirmed by reading every
    # ROLE_PERMISSIONS entry in auth.py directly) -- building a
    # leads-only actor via AuthContext.custom_permissions (the same
    # mechanism auth.py's own NEW-533 custom_permissions_json override
    # uses) is the only way to prove the gate is genuinely per-panel/
    # permission-specific, not just "any permission passes".
    _LEADS_ONLY_TOKEN = "sentinel-leads-only-token"
    _leads_only_ctx = AuthContext(
        user_id=99902,
        username="leads_only",
        role=ROLE_TECHNICIAN,
        actor_type="human",
        custom_permissions={PERM_READ_LEADS: True},
    )

    def _patched_authenticate_token(token):
        if token == _NO_USER_ID_TOKEN:
            return AuthContext(user_id=None, username="agent", role="ai_agent", actor_type="agent")
        if token == _TECHNICIAN_TOKEN:
            return _technician_ctx
        if token == _LEADS_ONLY_TOKEN:
            return _leads_only_ctx
        return _real_authenticate_token(token)

    monkeypatch.setattr(server.auth_service, "authenticate_token", _patched_authenticate_token)

    fake_pm = _FakePluginManager()
    monkeypatch.setattr("ccos.core.plugin_manager.get_plugin_manager", lambda: fake_pm)
    monkeypatch.setattr(
        routes_mod, "_call_budget_gated_completion",
        lambda **kw: (200, {"Content-Type": "application/json"}, {"choices": [{"message": {"content": "ok"}}]}),
    )
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")

    yield {
        "server": server, "base_url": f"http://127.0.0.1:{port}",
        "admin_token": admin_token, "no_user_id_token": _NO_USER_ID_TOKEN,
        "rep_a": rep_a, "rep_a_token": rep_a_token,
        "rep_b": rep_b, "rep_b_token": rep_b_token,
        "customer": cust1, "fake_pm": fake_pm,
        "appointment_rep_a": appt_rep_a,
        "appointment_unassigned": appt_unassigned,
        "appointment_no_customer": appt_no_customer,
        "technician_token": _TECHNICIAN_TOKEN,
        "leads_only_token": _LEADS_ONLY_TOKEN,
    }
    server.stop()


# ── Part B: /api/v1/sales/copilot-summary ────────────────────────────────

def test_copilot_summary_403_when_actor_has_no_user_id(copilot_fixture):
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/copilot-summary",
        json={"panel": "leads"},
        headers={"Authorization": f"Bearer {copilot_fixture['no_user_id_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 403


def test_copilot_summary_scopes_to_rep_when_actor_lacks_team_permission(copilot_fixture):
    """Spec test 1: a narrowed actor (no PERM_READ_TEAM_SALES_DATA)
    produces assigned_user_id=actor.user_id in the capability call kwargs."""
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/copilot-summary",
        json={"panel": "leads", "prompt": "which leads haven't been touched recently?"},
        headers={"Authorization": f"Bearer {copilot_fixture['rep_a_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 200, resp.text
    calls = copilot_fixture["fake_pm"].calls
    assert calls == [("crm.list_leads", {"assigned_user_id": copilot_fixture["rep_a"].id})]


def test_copilot_summary_scopes_to_team_when_actor_has_team_permission(copilot_fixture):
    """Spec test 1: a team-scoped actor (holds PERM_READ_TEAM_SALES_DATA,
    ROLE_ADMIN here) produces assigned_user_id=None in the capability call
    kwargs."""
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/copilot-summary",
        json={"panel": "opportunities"},
        headers={"Authorization": f"Bearer {copilot_fixture['admin_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 200, resp.text
    calls = copilot_fixture["fake_pm"].calls
    assert calls == [("crm.list_opportunities", {"assigned_user_id": None})]


def test_copilot_summary_pipeline_panel_never_calls_unscoped_capability_for_narrowed_actor(copilot_fixture):
    """crm.get_pipeline_summary has no assigned_user_id knob at all (it
    always aggregates whatever the calling actor's own list_opportunities
    sees, and the CCOS token's actor always holds
    PERM_READ_TEAM_SALES_DATA) -- calling it unscoped for a narrowed rep
    would leak the whole team's pipeline. Confirms the route instead
    retrieves crm.list_opportunities(assigned_user_id=...) for this case."""
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/copilot-summary",
        json={"panel": "pipeline"},
        headers={"Authorization": f"Bearer {copilot_fixture['rep_a_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 200, resp.text
    calls = copilot_fixture["fake_pm"].calls
    assert calls == [("crm.list_opportunities", {"assigned_user_id": copilot_fixture["rep_a"].id})]
    assert all(name != "crm.get_pipeline_summary" for name, _ in calls)


def test_copilot_summary_pipeline_panel_uses_real_capability_for_team_scope(copilot_fixture):
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/copilot-summary",
        json={"panel": "pipeline"},
        headers={"Authorization": f"Bearer {copilot_fixture['admin_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 200, resp.text
    calls = copilot_fixture["fake_pm"].calls
    assert calls == [("crm.get_pipeline_summary", {})]


def test_copilot_summary_rejects_customers_panel_because_it_is_unscopable(copilot_fixture):
    """crm.list_customers has no assigned_user_id scope knob at all (not
    the client, not /api/v1/customers' own GET branch) -- a narrowed rep
    could never be safely scoped for it, same shape as the pipeline case
    above but with no scoped fallback available. Deliberately excluded
    from the supported panel set rather than shipped unscoped."""
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/copilot-summary",
        json={"panel": "customers"},
        headers={"Authorization": f"Bearer {copilot_fixture['rep_a_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 400
    assert copilot_fixture["fake_pm"].calls == []


def test_copilot_summary_denies_actor_with_zero_crm_permission(copilot_fixture):
    """Code-reviewer Critical finding, round 1 (b8_11_ai_sales_copilot_approved):
    live-reproduced as a ROLE_TECHNICIAN actor (holds none of
    PERM_READ_LEADS/PERM_READ_OPPORTUNITIES/PERM_READ_CRM/
    PERM_READ_TEAM_SALES_DATA) POSTing {"panel": "tasks"} and getting a
    real 200 with real CRM data, with the capability call having actually
    fired. Must now be a 403 with the capability call never made at all."""
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/copilot-summary",
        json={"panel": "tasks"},
        headers={"Authorization": f"Bearer {copilot_fixture['technician_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 403, resp.text
    assert copilot_fixture["fake_pm"].calls == []


def test_copilot_summary_gate_is_permission_specific_not_any_permission(copilot_fixture):
    """Proves the gate is genuinely per-panel/permission-specific, not
    "holding any one CRM permission unlocks every panel": an actor
    holding ONLY PERM_READ_LEADS (via custom_permissions, since no real
    role in this codebase holds PERM_READ_LEADS without also holding
    PERM_READ_OPPORTUNITIES or vice versa) is allowed on the 'leads'
    panel but denied on 'opportunities', which requires a permission this
    actor does not hold."""
    allowed = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/copilot-summary",
        json={"panel": "leads"},
        headers={"Authorization": f"Bearer {copilot_fixture['leads_only_token']}"},
        timeout=10.0,
    )
    assert allowed.status_code == 200, allowed.text
    assert copilot_fixture["fake_pm"].calls == [("crm.list_leads", {"assigned_user_id": 99902})]

    denied = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/copilot-summary",
        json={"panel": "opportunities"},
        headers={"Authorization": f"Bearer {copilot_fixture['leads_only_token']}"},
        timeout=10.0,
    )
    assert denied.status_code == 403, denied.text
    # No new capability call beyond the one recorded by the allowed
    # request above -- the denied request must not have reached CCOS.
    assert copilot_fixture["fake_pm"].calls == [("crm.list_leads", {"assigned_user_id": 99902})]


def test_copilot_summary_rejects_unknown_panel(copilot_fixture):
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/copilot-summary",
        json={"panel": "not_a_real_panel"},
        headers={"Authorization": f"Bearer {copilot_fixture['rep_a_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 400


# ── Part C: /api/v1/sales/appointment-prep ───────────────────────────────

def test_appointment_prep_403_when_actor_has_no_user_id(copilot_fixture):
    appt_id = copilot_fixture["appointment_rep_a"].id
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/appointment-prep",
        json={"appointment_id": appt_id},
        headers={"Authorization": f"Bearer {copilot_fixture['no_user_id_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 403


def test_appointment_prep_owning_rep_can_prep_own_appointment(copilot_fixture):
    appt = copilot_fixture["appointment_rep_a"]
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/appointment-prep",
        json={"appointment_id": appt.id},
        headers={"Authorization": f"Bearer {copilot_fixture['rep_a_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 200, resp.text
    calls = copilot_fixture["fake_pm"].calls
    cust_id = copilot_fixture["customer"].id
    assert ("crm.list_properties", {"customer_id": cust_id}) in calls
    assert ("crm.list_estimates", {"customer_id": cust_id}) in calls
    assert ("crm.list_communications", {"customer_id": cust_id}) in calls


def test_appointment_prep_other_rep_denied_without_team_permission(copilot_fixture):
    """Mirrors routes.py's /api/v1/sales/dashboard appointments filter
    (`appt.assigned_user_id == actor.user_id` for a narrowed actor): rep_b
    (ROLE_SALES, no PERM_READ_TEAM_SALES_DATA) may not prep an appointment
    assigned to rep_a."""
    appt = copilot_fixture["appointment_rep_a"]
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/appointment-prep",
        json={"appointment_id": appt.id},
        headers={"Authorization": f"Bearer {copilot_fixture['rep_b_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 403


def test_appointment_prep_unassigned_appointment_denied_for_narrowed_actor(copilot_fixture):
    """NEW-551's own divergence, applied here rather than inventing a new
    unclaimed-pool rule for prep: an unassigned appointment's
    assigned_user_id is None, which never equals a narrowed actor's real
    user_id, so it is a 403 here too -- consistent with the dashboard's
    own strict filter, not a gap introduced by this route."""
    appt = copilot_fixture["appointment_unassigned"]
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/appointment-prep",
        json={"appointment_id": appt.id},
        headers={"Authorization": f"Bearer {copilot_fixture['rep_a_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 403


def test_appointment_prep_team_scoped_actor_can_prep_any_appointment(copilot_fixture):
    appt = copilot_fixture["appointment_rep_a"]
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/appointment-prep",
        json={"appointment_id": appt.id},
        headers={"Authorization": f"Bearer {copilot_fixture['admin_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 200, resp.text


def test_appointment_prep_404_for_nonexistent_appointment(copilot_fixture):
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/appointment-prep",
        json={"appointment_id": 999999},
        headers={"Authorization": f"Bearer {copilot_fixture['admin_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 404


def test_appointment_prep_400_when_appointment_has_no_customer(copilot_fixture):
    appt = copilot_fixture["appointment_no_customer"]
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/appointment-prep",
        json={"appointment_id": appt.id},
        headers={"Authorization": f"Bearer {copilot_fixture['admin_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 400


def test_appointment_prep_400_when_appointment_id_missing(copilot_fixture):
    resp = requests.post(
        f"{copilot_fixture['base_url']}/api/v1/sales/appointment-prep",
        json={},
        headers={"Authorization": f"Bearer {copilot_fixture['admin_token']}"},
        timeout=10.0,
    )
    assert resp.status_code == 400
