"""
Integration tests for CODEY_MASTER_PLAN.md 12.x -- CCOS read-only CRM
query capability.

Spins up a real RestoriconAPIServer (same pattern as
tests/test_restoricon_core/test_api.py's `api_server` fixture) and
exercises the nine `crm.*` capabilities registered by
ccos/plugins/crm/core_query/ via `pm.call_capability()`, the same
mechanism core/agent.py's new `crm_query` tool uses.

Uses a real `tmp_path`-backed file DB (never ":memory:") for every test
that provisions a token via tools.provision_ai_agent_auth.provision() and
then authenticates against a *separate* RestoriconAPIServer/DatabaseManager
instance pointed at the same db_path -- each ":memory:" DatabaseManager
gets its own isolated in-memory DB (see
tests/test_provision_ai_agent_auth.py's own comment on this exact trap),
so a shared on-disk file is required for the token to actually mean
anything across those two objects.
"""

import socket
import time

import pytest
import requests

from ccos.core.plugin_manager import PluginManager
from ccos.plugins.crm.core_query.client import CoreQueryClient, LIST_CAP
from restoricon_core.api.server import RestoriconAPIServer
from restoricon_core.auth import ROLE_ADMIN
from restoricon_core.models import Customer, Lead, Opportunity, Task
from tools.provision_ai_agent_auth import CRM_READER_DENY_PERMISSIONS, CRM_READER_USERNAME, provision


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def crm_server_and_token(tmp_path, monkeypatch):
    """A live RestoriconAPIServer on a real tmp_path file DB, seeded with
    two reps' worth of leads/opportunities/customers/tasks, plus a real
    provisioned codey-ccos-crm-reader token pointed (via the token file
    the client reads) at that same server."""
    db_path = str(tmp_path / "core.db")
    port = _find_free_port()
    server = RestoriconAPIServer(db_path=db_path, host="127.0.0.1", port=port)
    server.start(background=True)
    time.sleep(0.1)  # let the ThreadingHTTPServer's background thread bind

    admin = server.auth_service.create_user(
        username="admin", plain_password="AdminPass123!", full_name="Admin",
        email="admin@test.restoricon", role=ROLE_ADMIN,
    )
    admin_ctx = server.auth_service.authenticate_token(server.auth_service.create_token(admin))

    rep_a = server.auth_service.create_user(
        username="rep_a", plain_password="RepAPass123!", full_name="Rep A",
        email="rep_a@test.restoricon", role="sales",
    )
    rep_b = server.auth_service.create_user(
        username="rep_b", plain_password="RepBPass123!", full_name="Rep B",
        email="rep_b@test.restoricon", role="sales",
    )

    cust1 = server.crm_service.create_customer(
        Customer(first_name="Alice", last_name="Smith", phone="+15551234567"), admin_ctx
    )

    # 3 open leads for rep_a, so list_leads/count_open_leads has >0 but
    # <LIST_CAP rows by default, and a dedicated bulk batch for the
    # context-cap test.
    for i in range(3):
        server.crm_service.create_lead(
            Lead(customer_id=cust1.id, assigned_user_id=rep_a.id, status="new", project_scope="roofing"),
            admin_ctx,
        )
    # One lead for rep_b, used by the cross-rep scoping test.
    lead_b = server.crm_service.create_lead(
        Lead(customer_id=cust1.id, assigned_user_id=rep_b.id, status="new", project_scope="roofing"),
        admin_ctx,
    )
    # One closed (converted) lead for rep_a -- must NOT count as "open".
    server.crm_service.create_lead(
        Lead(customer_id=cust1.id, assigned_user_id=rep_a.id, status="converted", project_scope="roofing"),
        admin_ctx,
    )

    opp = server.crm_service.create_opportunity(
        Opportunity(customer_id=cust1.id, assigned_user_id=rep_a.id, title="Roof replacement", pipeline_stage="qualifying"),
        admin_ctx,
    )
    server.crm_service.create_task(
        Task(title="Follow up", customer_id=cust1.id, assigned_user_id=rep_a.id), admin_ctx
    )

    # The CLI (`python -m tools.provision_ai_agent_auth --username
    # codey-ccos-crm-reader`) applies CRM_READER_DENY_PERMISSIONS
    # automatically based on the username (see provision_ai_agent_auth's
    # main()); calling provision() directly here must pass it explicitly
    # to reproduce that same real-world invocation.
    token = provision(username=CRM_READER_USERNAME, db_path=db_path, custom_permissions=CRM_READER_DENY_PERMISSIONS)
    token_path = tmp_path / "ccos_crm_read_token"
    token_path.write_text(token)
    monkeypatch.setattr("ccos.plugins.crm.core_query.client.CRM_READ_TOKEN_FILE", token_path)
    monkeypatch.setenv("RESTORICON_API_HOST", "127.0.0.1")
    monkeypatch.setenv("RESTORICON_API_PORT", str(port))
    # Loopback calls in this test process must never be routed through an
    # ambient HTTP_PROXY/http_proxy (documented footgun on this project's
    # own dev machine, MEMORY.md "Sandbox proxy test artifact") -- the
    # client itself already sets trust_env=False, this belt-and-suspenders
    # covers any other requests call in-process during the test.
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")

    # Reset the module-level default client singleton so each test gets a
    # fresh CoreQueryClient bound to this test's host/port/token-file.
    import ccos.plugins.crm.core_query.client as client_mod
    client_mod._default_client = None

    yield {
        "server": server, "base_url": f"http://127.0.0.1:{port}", "db_path": db_path,
        "token": token, "rep_a": rep_a, "rep_b": rep_b, "lead_b": lead_b,
        "opportunity": opp, "customer": cust1, "admin_ctx": admin_ctx,
    }

    client_mod._default_client = None
    server.stop()


@pytest.fixture
def pm():
    """A fresh PluginManager with crm_core_query loaded and its
    capabilities registered on the real, process-global capability
    registry (mirroring main.py's own
    `pm = get_plugin_manager(); if "crm_core_query" not in pm._modules: pm.load(...)`
    pattern)."""
    manager = PluginManager()
    loaded = manager.load("crm_core_query")
    assert loaded, "crm_core_query plugin failed to load"
    yield manager
    # Unregister so repeat test runs in the same process don't collide on
    # "capability already registered" in the shared global registry.
    manager.unload("crm_core_query")


# ── Part E.2: each capability via pm.call_capability() ──────────────────

def test_count_open_leads(crm_server_and_token, pm):
    result = pm.call_capability("crm.count_open_leads")
    assert result["count"] == 4  # 3 new (rep_a) + 1 new (rep_b), excludes the 1 converted


def test_count_open_leads_scoped_to_rep(crm_server_and_token, pm):
    rep_a_id = crm_server_and_token["rep_a"].id
    result = pm.call_capability("crm.count_open_leads", assigned_user_id=rep_a_id)
    assert result["count"] == 3


def test_list_leads(crm_server_and_token, pm):
    result = pm.call_capability("crm.list_leads")
    assert result["truncated"] is False
    assert len(result["leads"]) == 5  # all 5 leads created, including the converted one (no status filter)


def test_get_lead(crm_server_and_token, pm):
    lead_b = crm_server_and_token["lead_b"]
    result = pm.call_capability("crm.get_lead", lead_id=lead_b.id)
    assert result["lead"]["id"] == lead_b.id


def test_score_lead_route_is_write_gated_despite_being_a_get(crm_server_and_token):
    """Pins this round's headline finding (NEW_ISSUES.md): there is no
    crm.score_lead capability in this plugin because
    GET /api/v1/leads/{id}/score is not actually read-only --
    crm_service.py's score_lead() persists the computed score via
    update_lead() for any existing lead_id regardless of HTTP method, so
    it requires write:leads/write:crm, both denied for this token. This
    test proves that 403 is real Core behavior, not an assumption, so it
    fails loudly if Core is ever changed to make the GET path genuinely
    non-persisting without this test (and this round's scope decision)
    being revisited."""
    base_url = crm_server_and_token["base_url"]
    token = crm_server_and_token["token"]
    lead_b = crm_server_and_token["lead_b"]
    resp = requests.get(
        f"{base_url}/api/v1/leads/{lead_b.id}/score",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    assert resp.status_code == 403


def test_list_opportunities(crm_server_and_token, pm):
    result = pm.call_capability("crm.list_opportunities")
    assert result["truncated"] is False
    assert len(result["opportunities"]) == 1


def test_get_opportunity(crm_server_and_token, pm):
    opp = crm_server_and_token["opportunity"]
    result = pm.call_capability("crm.get_opportunity", opportunity_id=opp.id)
    assert result["opportunity"]["id"] == opp.id


def test_get_pipeline_summary(crm_server_and_token, pm):
    result = pm.call_capability("crm.get_pipeline_summary")
    assert "pipeline" in result


def test_list_customers(crm_server_and_token, pm):
    result = pm.call_capability("crm.list_customers")
    assert len(result["customers"]) == 1


def test_get_customer(crm_server_and_token, pm):
    cust = crm_server_and_token["customer"]
    result = pm.call_capability("crm.get_customer", customer_id=cust.id)
    assert result["customer"]["id"] == cust.id


def test_list_tasks(crm_server_and_token, pm):
    result = pm.call_capability("crm.list_tasks")
    assert result["truncated"] is False
    assert len(result["tasks"]) == 1


# ── Part E.3: the real provisioned token rejects a WRITE route ──────────

def test_provisioned_token_rejects_write_route(crm_server_and_token):
    base_url = crm_server_and_token["base_url"]
    token = crm_server_and_token["token"]
    resp = requests.post(
        f"{base_url}/api/v1/leads",
        json={"customer_id": crm_server_and_token["customer"].id, "status": "new"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    assert resp.status_code in (401, 403)


# ── Part E.4: the deny-list did NOT silently break cross-rep scoping ────

def test_cross_rep_query_returns_real_data_not_silently_empty(crm_server_and_token, pm):
    """Proves PERM_READ_TEAM_SALES_DATA was correctly retained (not denied):
    querying a DIFFERENT rep's assigned_user_id than the token's own
    identity must return that rep's real, non-empty data."""
    rep_b_id = crm_server_and_token["rep_b"].id
    result = pm.call_capability("crm.list_leads", assigned_user_id=rep_b_id)
    assert result["leads"], "expected rep_b's lead to be visible to the crm-reader token"
    assert all(l["assigned_user_id"] == rep_b_id for l in result["leads"])


def test_denying_read_team_sales_data_would_have_hidden_this(crm_server_and_token, tmp_path):
    """Mirror/control for the test above: a second token that DOES deny
    read:team_sales_data gets silently scoped to its own user_id and sees
    NOTHING for rep_b's query -- the exact trap 12.x Part B's spec warns
    about. This is what would have happened had PERM_READ_TEAM_SALES_DATA
    been denied for the real crm-reader token; it demonstrates the trap
    exists, not just that this round avoided it."""
    narrowed_deny = dict(CRM_READER_DENY_PERMISSIONS)
    narrowed_deny["read:team_sales_data"] = False
    db_path = crm_server_and_token["db_path"]
    narrowed_token = provision(
        username="codey-ccos-crm-reader-narrowed-test-only",
        email="codey-ccos-crm-reader-narrowed-test-only@local.invalid",
        db_path=db_path,
        custom_permissions=narrowed_deny,
    )

    client = CoreQueryClient(host="127.0.0.1", port=int(crm_server_and_token["base_url"].rsplit(":", 1)[1]), token=narrowed_token)
    rep_b_id = crm_server_and_token["rep_b"].id
    result = client.list_leads(assigned_user_id=rep_b_id)
    assert result["leads"] == []


# ── Part E.5: context-cap truncation, one per list-shaped capability ────

def _bulk_create_leads(server, admin_ctx, customer_id, n):
    for _ in range(n):
        server.crm_service.create_lead(Lead(customer_id=customer_id, status="new", project_scope="roofing"), admin_ctx)


def test_list_leads_truncation_marker(crm_server_and_token, pm):
    server = crm_server_and_token["server"]
    admin_ctx = crm_server_and_token["admin_ctx"]
    cust_id = crm_server_and_token["customer"].id
    _bulk_create_leads(server, admin_ctx, cust_id, LIST_CAP + 10)

    result = pm.call_capability("crm.list_leads")
    assert result["truncated"] is True
    assert result["returned"] == LIST_CAP
    assert "more not shown, narrow your query" in result["note"]


def test_list_opportunities_truncation_marker(crm_server_and_token, pm):
    server = crm_server_and_token["server"]
    admin_ctx = crm_server_and_token["admin_ctx"]
    cust_id = crm_server_and_token["customer"].id
    for _ in range(LIST_CAP + 5):
        server.crm_service.create_opportunity(
            Opportunity(customer_id=cust_id, title="Bulk opp", pipeline_stage="qualifying"), admin_ctx
        )

    result = pm.call_capability("crm.list_opportunities")
    assert result["truncated"] is True
    assert result["returned"] == LIST_CAP
    assert "more not shown, narrow your query" in result["note"]


def test_list_tasks_truncation_marker(crm_server_and_token, pm):
    server = crm_server_and_token["server"]
    admin_ctx = crm_server_and_token["admin_ctx"]
    cust_id = crm_server_and_token["customer"].id
    for _ in range(LIST_CAP + 5):
        server.crm_service.create_task(Task(title="Bulk task", customer_id=cust_id), admin_ctx)

    result = pm.call_capability("crm.list_tasks")
    assert result["truncated"] is True
    assert result["returned"] == LIST_CAP
    assert "more not shown, narrow your query" in result["note"]
