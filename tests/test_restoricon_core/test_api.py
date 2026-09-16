"""
Integration tests for Restoricon Core HTTP REST API server.
Tests live HTTP request-response roundtrips, token authentication, role-based scoping,
and audit log generation.
"""

import json
import socket
import time
import urllib.request
import urllib.error
import pytest
from restoricon_core.api.server import RestoriconAPIServer
from restoricon_core.auth import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_AI_AGENT, ROLE_TECHNICIAN
from core.resource_gate import ContextBudgetDecision


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_request(url: str, method: str = "GET", data: dict = None, headers: dict = None):
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

    # Create seed users
    admin_user = server.auth_service.create_user(
        username="admin",
        plain_password="AdminSecretPassword123",
        full_name="Admin Boss",
        email="admin@restoricon.com",
        role=ROLE_ADMIN,
    )

    agent_user = server.auth_service.create_user(
        username="aigentik",
        plain_password="AgentSecretPassword123",
        full_name="Aigentik Bot",
        email="aigentik@restoricon.com",
        role=ROLE_AI_AGENT,
    )

    yield server, base_url, admin_user, agent_user
    server.stop()


def test_api_health_and_unauthenticated_access(api_server):
    _, base_url, _, _ = api_server
    
    # Health check
    status, body = make_request(f"{base_url}/api/v1/health")
    assert status == 200
    assert body["status"] == "ok"
    assert body["service"] == "restoricon_core"

    # Protected endpoint without auth returns 401
    status, body = make_request(f"{base_url}/api/v1/customers")
    assert status == 401
    assert "error" in body


def test_api_login_and_authenticated_crud(api_server):
    server, base_url, _, _ = api_server

    # 1. Login as Admin
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    admin_token = body["token"]
    assert len(admin_token) > 20

    auth_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Check /api/v1/auth/me
    status, body = make_request(f"{base_url}/api/v1/auth/me", headers=auth_headers)
    assert status == 200
    assert body["user"]["username"] == "admin"
    assert body["user"]["role"] == "admin"

    # 3. Create a Customer via API
    status, body = make_request(
        f"{base_url}/api/v1/customers",
        method="POST",
        headers=auth_headers,
        data={
            "first_name": "Alice",
            "last_name": "Smith",
            "company_name": "Smith Corp",
            "email": "alice@smithcorp.com",
            "service_address": "100 Main St, Hartford, CT",
            "customer_type": "commercial",
            "status": "active",
        },
    )
    assert status == 201
    cust_id = body["customer"]["id"]
    assert cust_id is not None

    # 4. Create a Customer user for Alice
    alice_user = server.auth_service.create_user(
        username="alice",
        plain_password="AlicePassword123",
        full_name="Alice Smith",
        email="alice@smithcorp.com",
        role=ROLE_CUSTOMER,
        customer_id=cust_id,
    )

    # 5. Create a project for Alice
    status, body = make_request(
        f"{base_url}/api/v1/projects",
        method="POST",
        headers=auth_headers,
        data={
            "customer_id": cust_id,
            "title": "Smith Corp Office Renovation",
            "property_address": "100 Main St, Hartford, CT",
            "project_type": "commercial_remodel",
            "contract_amount": 75000.0,
        },
    )
    assert status == 201
    proj_id = body["project"]["id"]

    # 6. Login as Alice (Customer)
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "alice", "password": "AlicePassword123"},
    )
    assert status == 200
    alice_token = body["token"]
    alice_headers = {"Authorization": f"Bearer {alice_token}"}

    # 7. Alice fetches projects (should see her own project)
    status, body = make_request(f"{base_url}/api/v1/projects", headers=alice_headers)
    assert status == 200
    assert len(body["projects"]) == 1
    assert body["projects"][0]["id"] == proj_id

    # 8. Alice attempts to view Audit Log (should be denied 403)
    status, body = make_request(f"{base_url}/api/v1/audit-log", headers=alice_headers)
    assert status == 403

    # 9. Admin views Audit Log (should see all actions recorded)
    status, body = make_request(f"{base_url}/api/v1/audit-log", headers=auth_headers)
    assert status == 200
    logs = body["audit_logs"]
    # Check that audit trail contains auth_login, create customer, create project
    assert len(logs) >= 3


def _agent_headers(base_url):
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "aigentik", "password": "AgentSecretPassword123"},
    )
    assert status == 200
    return {"Authorization": f"Bearer {body['token']}"}


def _mock_admitted_budget_decision(effective_n_ctx=4096, reservation_id="test-reservation-id"):
    """Deterministic stand-in for `wait_and_reserve_context_budget()`'s
    real return value, used by the T3 telemetry tests in this file to
    avoid depending on real, live device RAM headroom: in isolation this
    device has enough free RAM for the real admission gate to admit every
    request, but deep into the full 1300+-test suite run -- with many
    other tests' real subprocesses/servers still using RAM -- the real
    gate can genuinely and correctly refuse admission (429), which is a
    live-RAM-state dependency these telemetry tests must not have."""
    return ContextBudgetDecision(
        admitted=True,
        reservation_id=reservation_id,
        reserved_tokens=100,
        effective_n_ctx=effective_n_ctx,
        ceiling_tokens=4000,
        slots_occupied_tokens=0,
        other_reserved_tokens=0,
        estimate_source="heuristic",
        reason="test-mocked admission",
        timed_out=False,
    )


def test_api_customer_and_project_get_by_id(api_server):
    """No prior test exercised GET /customers/{id} or /projects/{id}
    directly; added alongside the NEW-222/NEW-237 by-id route match
    tightening since that change touched these two branches too."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    status, body = make_request(
        f"{base_url}/api/v1/customers",
        method="POST",
        headers=headers,
        data={
            "first_name": "Bob",
            "last_name": "Jones",
            "email": "bob@example.com",
            "service_address": "1 Elm St",
            "customer_type": "residential",
            "status": "active",
        },
    )
    assert status == 201
    cust_id = body["customer"]["id"]

    status, body = make_request(f"{base_url}/api/v1/customers/{cust_id}", headers=headers)
    assert status == 200
    assert body["customer"]["first_name"] == "Bob"

    status, body = make_request(f"{base_url}/api/v1/customers/999999", headers=headers)
    assert status == 404

    status, body = make_request(
        f"{base_url}/api/v1/projects",
        method="POST",
        headers=headers,
        data={
            "customer_id": cust_id,
            "title": "Kitchen remodel",
            "property_address": "1 Elm St",
            "project_type": "residential_remodel",
            "contract_amount": 5000.0,
        },
    )
    assert status == 201
    proj_id = body["project"]["id"]

    status, body = make_request(f"{base_url}/api/v1/projects/{proj_id}", headers=headers)
    assert status == 200
    assert body["project"]["title"] == "Kitchen remodel"

    status, body = make_request(f"{base_url}/api/v1/projects/999999", headers=headers)
    assert status == 404


def test_api_subcontractors_crud(api_server):
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/subcontractors",
        method="POST",
        headers=headers,
        data={"company_name": "Acme Roofing", "primary_trade": "roofing"},
    )
    assert status == 201
    sub_id = body["subcontractor"]["id"]
    assert body["subcontractor"]["qualification_status"] == "QUALIFICATION_IN_PROGRESS"

    status, body = make_request(f"{base_url}/api/v1/subcontractors/{sub_id}", headers=headers)
    assert status == 200
    assert body["subcontractor"]["company_name"] == "Acme Roofing"

    status, body = make_request(f"{base_url}/api/v1/subcontractors", headers=headers)
    assert status == 200
    assert len(body["subcontractors"]) == 1

    status, body = make_request(
        f"{base_url}/api/v1/subcontractors/{sub_id}/qualification",
        method="POST",
        headers=headers,
        data={"qualification_status": "QUALIFIED", "recruitment_step": "onboarded"},
    )
    assert status == 200
    assert body["subcontractor"]["qualification_status"] == "QUALIFIED"

    # Non-existent id -> 404 for both GET and the qualification update
    status, body = make_request(f"{base_url}/api/v1/subcontractors/999999", headers=headers)
    assert status == 404
    status, body = make_request(
        f"{base_url}/api/v1/subcontractors/999999/qualification",
        method="POST",
        headers=headers,
        data={"qualification_status": "QUALIFIED"},
    )
    assert status == 404


def test_api_subcontractors_update(api_server):
    server, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    server.auth_service.create_user(
        username="tech",
        plain_password="TechPassword123",
        full_name="Tech Guy",
        email="tech@restoricon.com",
        role=ROLE_TECHNICIAN,
    )
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "tech", "password": "TechPassword123"},
    )
    assert status == 200
    tech_headers = {"Authorization": f"Bearer {body['token']}"}

    status, body = make_request(
        f"{base_url}/api/v1/subcontractors",
        method="POST",
        headers=headers,
        data={
            "company_name": "  Acme Roofing  ",
            "primary_trade": "roofing",
            "email": "Acme@Example.com",
            "qualification_data": {"years_licensed": 5, "notes": "solid"},
            "secondary_trades": ["gutters"],
        },
    )
    assert status == 201
    sub_id = body["subcontractor"]["id"]

    # PermissionError (actor lacks PERM_WRITE_SUBCONTRACTORS) -> 403
    status, body = make_request(
        f"{base_url}/api/v1/subcontractors/{sub_id}/update",
        method="POST",
        headers=tech_headers,
        data={"phone": "555-1234"},
    )
    assert status == 403

    # Unknown key -> 400
    status, body = make_request(
        f"{base_url}/api/v1/subcontractors/{sub_id}/update",
        method="POST",
        headers=headers,
        data={"not_a_real_field": "x"},
    )
    assert status == 400

    # None-valued key -> 400
    status, body = make_request(
        f"{base_url}/api/v1/subcontractors/{sub_id}/update",
        method="POST",
        headers=headers,
        data={"phone": None},
    )
    assert status == 400

    # qualification_status/recruitment_step rejected as unknown keys
    status, body = make_request(
        f"{base_url}/api/v1/subcontractors/{sub_id}/update",
        method="POST",
        headers=headers,
        data={"qualification_status": "QUALIFIED"},
    )
    assert status == 400
    status, body = make_request(
        f"{base_url}/api/v1/subcontractors/{sub_id}/update",
        method="POST",
        headers=headers,
        data={"recruitment_step": "onboarded"},
    )
    assert status == 400

    # qualification_data merge preserves pre-existing keys; secondary_trades replaces;
    # email/company_name normalized
    status, body = make_request(
        f"{base_url}/api/v1/subcontractors/{sub_id}/update",
        method="POST",
        headers=headers,
        data={
            "qualification_data": {"notes": "updated note"},
            "secondary_trades": ["siding"],
            "email": " New@Example.COM ",
            "company_name": "  New Name  ",
        },
    )
    assert status == 200
    updated = body["subcontractor"]
    assert updated["qualification_data"] == {"years_licensed": 5, "notes": "updated note"}
    assert updated["secondary_trades"] == ["siding"]
    assert updated["email"] == "new@example.com"
    assert updated["company_name"] == "New Name"

    # Empty {} updates dict is a no-op
    status, body = make_request(
        f"{base_url}/api/v1/subcontractors/{sub_id}/update",
        method="POST",
        headers=headers,
        data={},
    )
    assert status == 200
    assert body["subcontractor"] == updated

    # 404 on nonexistent id
    status, body = make_request(
        f"{base_url}/api/v1/subcontractors/999999/update",
        method="POST",
        headers=headers,
        data={"phone": "555-1234"},
    )
    assert status == 404


def test_api_subcontractors_find_query_param(api_server):
    """GET /api/v1/subcontractors?q=... -- B2 task 4, third module
    continuation, 2026-08-27, CODEY_MASTER_PLAN.md Sec6.4."""
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/subcontractors",
        method="POST",
        headers=headers,
        data={"company_name": "Acme Roofing", "email": "acme@example.com", "phone": "860-555-0101"},
    )
    assert status == 201
    sub_id = body["subcontractor"]["id"]

    # q matches -> 200 with the found record, taking priority over any
    # co-present list-style params
    status, body = make_request(
        f"{base_url}/api/v1/subcontractors?q=acme&qualification_status=QUALIFICATION_IN_PROGRESS&limit=1",
        headers=headers,
    )
    assert status == 200
    assert body["subcontractor"]["id"] == sub_id

    # q with no match -> 404, not an exception
    status, body = make_request(f"{base_url}/api/v1/subcontractors?q=nonexistentxyz", headers=headers)
    assert status == 404
    assert body["error"] == "Subcontractor not found"

    # q= (blank) falls through to list_subcontractors, not find_subcontractor
    status, body = make_request(f"{base_url}/api/v1/subcontractors?q=", headers=headers)
    assert status == 200
    assert "subcontractors" in body
    assert len(body["subcontractors"]) == 1

    # q=%20 (whitespace-only) also falls through to list
    status, body = make_request(f"{base_url}/api/v1/subcontractors?q=%20", headers=headers)
    assert status == 200
    assert "subcontractors" in body
    assert len(body["subcontractors"]) == 1


def test_api_by_id_get_routes_404_not_400_on_action_suffix(api_server):
    """NEW-222/NEW-237: GET .../{id}/qualification, .../{id}/update, and
    .../{id}/status (all POST-only action suffixes) must fall through to
    the router's final 404 catch-all, not into the generic by-id GET
    handler where the suffix segment gets fed to int() and raises a
    ValueError that handle_request turns into a 400."""
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/subcontractors",
        method="POST",
        headers=headers,
        data={"company_name": "Acme Roofing", "primary_trade": "roofing"},
    )
    assert status == 201
    sub_id = body["subcontractor"]["id"]

    status, body = make_request(f"{base_url}/api/v1/subcontractors/{sub_id}/qualification", headers=headers)
    assert status == 404

    status, body = make_request(f"{base_url}/api/v1/subcontractors/{sub_id}/update", headers=headers)
    assert status == 404

    status, body = make_request(
        f"{base_url}/api/v1/appointments",
        method="POST",
        headers=headers,
        data={"title": "Site walkthrough", "start_time": "2026-09-01T10:00:00"},
    )
    assert status == 201
    appt_id = body["appointment"]["id"]

    status, body = make_request(f"{base_url}/api/v1/appointments/{appt_id}/status", headers=headers)
    assert status == 404

    # And the generic by-id GET routes must still behave normally for the
    # plain numeric-id case (no regression from the tightened match).
    status, body = make_request(f"{base_url}/api/v1/subcontractors/{sub_id}", headers=headers)
    assert status == 200
    status, body = make_request(f"{base_url}/api/v1/appointments/{appt_id}", headers=headers)
    assert status == 200


def test_api_appointments_crud(api_server):
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/appointments",
        method="POST",
        headers=headers,
        data={"title": "Site walkthrough", "start_time": "2026-09-01T10:00:00"},
    )
    assert status == 201
    appt_id = body["appointment"]["id"]

    status, body = make_request(f"{base_url}/api/v1/appointments/{appt_id}", headers=headers)
    assert status == 200
    assert body["appointment"]["title"] == "Site walkthrough"

    status, body = make_request(f"{base_url}/api/v1/appointments", headers=headers)
    assert status == 200
    assert len(body["appointments"]) == 1

    status, body = make_request(
        f"{base_url}/api/v1/appointments/{appt_id}/status",
        method="POST",
        headers=headers,
        data={"status": "confirmed"},
    )
    assert status == 200
    assert body["appointment"]["status"] == "confirmed"

    # Invalid status -> 400 (ValueError from the service)
    status, body = make_request(
        f"{base_url}/api/v1/appointments/{appt_id}/status",
        method="POST",
        headers=headers,
        data={"status": "not_a_real_status"},
    )
    assert status == 400

    status, body = make_request(f"{base_url}/api/v1/appointments/999999", headers=headers)
    assert status == 404
    status, body = make_request(
        f"{base_url}/api/v1/appointments/999999/status",
        method="POST",
        headers=headers,
        data={"status": "confirmed"},
    )
    assert status == 404


def test_api_automation_rules_crud(api_server):
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/automation-rules",
        method="POST",
        headers=headers,
        data={
            "channel": "email",
            "condition_type": "contains",
            "condition_value": "invoice",
            "action": "forward",
        },
    )
    assert status == 201
    rule_id = body["automation_rule"]["id"]
    assert body["automation_rule"]["match_count"] == 0

    status, body = make_request(f"{base_url}/api/v1/automation-rules", headers=headers)
    assert status == 200
    assert len(body["automation_rules"]) == 1

    status, body = make_request(
        f"{base_url}/api/v1/automation-rules/{rule_id}/match",
        method="POST",
        headers=headers,
    )
    assert status == 200
    assert body["automation_rule"]["match_count"] == 1

    # NEW-219: no get-rule-by-id route exists, so an unknown id still
    # returns 404 for /match but there is no GET /{id} to also check.
    status, body = make_request(
        f"{base_url}/api/v1/automation-rules/999999/match",
        method="POST",
        headers=headers,
    )
    assert status == 404


def test_api_automation_rules_delete(api_server):
    """NEW-230: POST /api/v1/automation-rules/{id}/delete -- always-200
    bare-bool shape (matching /do-not-contact/remove), not a 404 for a
    delete of an already-gone id."""
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/automation-rules",
        method="POST",
        headers=headers,
        data={
            "channel": "sms",
            "condition_type": "from_number",
            "condition_value": "5551234567",
            "action": "spam",
        },
    )
    assert status == 201
    rule_id = body["automation_rule"]["id"]

    status, body = make_request(
        f"{base_url}/api/v1/automation-rules/{rule_id}/delete",
        method="POST",
        headers=headers,
    )
    assert status == 200
    assert body["deleted"] is True

    status, body = make_request(f"{base_url}/api/v1/automation-rules", headers=headers)
    assert status == 200
    assert len(body["automation_rules"]) == 0

    # Deleting an already-gone id -> still 200, bare False, never 404.
    status, body = make_request(
        f"{base_url}/api/v1/automation-rules/{rule_id}/delete",
        method="POST",
        headers=headers,
    )
    assert status == 200
    assert body["deleted"] is False


def test_api_business_profile_singleton(api_server):
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    # Not configured yet -> 404
    status, body = make_request(f"{base_url}/api/v1/business-profile", headers=headers)
    assert status == 404

    status, body = make_request(
        f"{base_url}/api/v1/business-profile",
        method="POST",
        headers=headers,
        data={"business_name": "Restoricon LLC", "owner_name": "Ish"},
    )
    assert status == 200
    assert body["business_profile"]["business_name"] == "Restoricon LLC"
    assert body["business_profile"]["id"] == 1

    status, body = make_request(f"{base_url}/api/v1/business-profile", headers=headers)
    assert status == 200
    assert body["business_profile"]["owner_name"] == "Ish"

    # Upsert again -> still id 1, still 200 not 201
    status, body = make_request(
        f"{base_url}/api/v1/business-profile",
        method="POST",
        headers=headers,
        data={"business_name": "Restoricon LLC Updated"},
    )
    assert status == 200
    assert body["business_profile"]["id"] == 1
    assert body["business_profile"]["business_name"] == "Restoricon LLC Updated"


def test_api_do_not_contact(api_server):
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/do-not-contact",
        method="POST",
        headers=headers,
        data={"identifier": "spammer@example.com", "reason": "requested removal"},
    )
    assert status == 201
    assert body["do_not_contact"]["type"] == "email"

    status, body = make_request(f"{base_url}/api/v1/do-not-contact", headers=headers)
    assert status == 200
    assert len(body["do_not_contact"]) == 1

    status, body = make_request(
        f"{base_url}/api/v1/do-not-contact/check?identifier=spammer@example.com", headers=headers
    )
    assert status == 200
    assert body["blocked"] is True

    status, body = make_request(
        f"{base_url}/api/v1/do-not-contact/check?identifier=someone-else@example.com", headers=headers
    )
    assert status == 200
    assert body["blocked"] is False

    # NEW-220: a malformed identifier is indistinguishable from "not
    # blocked" at this route today -- documented, not fixed here.
    status, body = make_request(
        f"{base_url}/api/v1/do-not-contact/check?identifier=not-an-email-or-phone", headers=headers
    )
    assert status == 200
    assert body["blocked"] is False

    status, body = make_request(
        f"{base_url}/api/v1/do-not-contact/remove",
        method="POST",
        headers=headers,
        data={"identifier": "spammer@example.com"},
    )
    assert status == 200
    assert body["removed"] is True

    # Removing again -> still 200, bare False, never 404
    status, body = make_request(
        f"{base_url}/api/v1/do-not-contact/remove",
        method="POST",
        headers=headers,
        data={"identifier": "spammer@example.com"},
    )
    assert status == 200
    assert body["removed"] is False

    # Malformed identifier on add -> 400, not 404 (per the spec's
    # falsy/error-return table: None means classify_identifier() rejected
    # the input, not "not found")
    status, body = make_request(
        f"{base_url}/api/v1/do-not-contact",
        method="POST",
        headers=headers,
        data={"identifier": "not-an-email-or-phone"},
    )
    assert status == 400


def test_api_new_resources_permission_denied_for_technician(api_server):
    server, base_url, _, _ = api_server

    server.auth_service.create_user(
        username="tech",
        plain_password="TechSecretPassword123",
        full_name="Tech Nician",
        email="tech@restoricon.com",
        role=ROLE_TECHNICIAN,
    )
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "tech", "password": "TechSecretPassword123"},
    )
    assert status == 200
    tech_headers = {"Authorization": f"Bearer {body['token']}"}

    # ROLE_TECHNICIAN holds none of the ten new permissions (auth.py's
    # ROLE_PERMISSIONS matrix) -- every one of these five resources must
    # reject a read attempt with 403.
    status, _ = make_request(f"{base_url}/api/v1/subcontractors", headers=tech_headers)
    assert status == 403

    status, _ = make_request(f"{base_url}/api/v1/appointments", headers=tech_headers)
    assert status == 403

    status, _ = make_request(f"{base_url}/api/v1/automation-rules", headers=tech_headers)
    assert status == 403

    status, _ = make_request(
        f"{base_url}/api/v1/automation-rules/1/delete", method="POST", headers=tech_headers
    )
    assert status == 403

    status, _ = make_request(f"{base_url}/api/v1/business-profile", headers=tech_headers)
    assert status == 403

    status, _ = make_request(f"{base_url}/api/v1/do-not-contact", headers=tech_headers)
    assert status == 403


def test_api_communications_provider_message_id_dedup_and_email_resolution(api_server):
    """NEW-233: exercises the POST /api/v1/communications write-through
    route end to end over real HTTP -- customer_id resolution from
    from_email, provider_message_id dedup on a retried/reprocessed call,
    and the technician fail-open path (a role with PERM_LOG_COMMUNICATION
    but not PERM_READ_ALL_CUSTOMERS must still succeed, just without
    resolution) -- none of which the service-layer unit tests reach,
    since the resolution logic itself lives in routes.py."""
    server, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/customers",
        method="POST",
        headers=headers,
        data={"first_name": "Carol", "last_name": "Customer", "email": "carol@example.com"},
    )
    assert status == 201
    cust_id = body["customer"]["id"]

    # from_email resolves to the existing customer's id
    status, body = make_request(
        f"{base_url}/api/v1/communications",
        method="POST",
        headers=headers,
        data={
            "channel": "email",
            "direction": "inbound",
            "content": "Original inbound message",
            "from_email": "carol@example.com",
            "provider_message_id": "<msg-1@mail.gmail.com>",
        },
    )
    assert status == 201
    assert body["communication"]["customer_id"] == cust_id
    comm_id = body["communication"]["id"]

    # Same provider_message_id reprocessed with different content (the
    # \Seen-flag race) -- must return the SAME row, not a duplicate.
    status, body = make_request(
        f"{base_url}/api/v1/communications",
        method="POST",
        headers=headers,
        data={
            "channel": "email",
            "direction": "inbound",
            "content": "Reprocessed different content",
            "from_email": "carol@example.com",
            "provider_message_id": "<msg-1@mail.gmail.com>",
        },
    )
    assert status == 201
    assert body["communication"]["id"] == comm_id
    assert body["communication"]["content"] == "Original inbound message"

    status, body = make_request(f"{base_url}/api/v1/communications", headers=headers)
    assert status == 200
    assert len(body["communications"]) == 1

    # Technician holds PERM_LOG_COMMUNICATION but not PERM_READ_ALL_CUSTOMERS
    # -- the write must still succeed (fail open on resolution), just with
    # customer_id left unresolved rather than the whole call 403ing.
    server.auth_service.create_user(
        username="tech2",
        plain_password="TechSecretPassword123",
        full_name="Tech Nician",
        email="tech2@restoricon.com",
        role=ROLE_TECHNICIAN,
    )
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "tech2", "password": "TechSecretPassword123"},
    )
    assert status == 200
    tech_headers = {"Authorization": f"Bearer {body['token']}"}

    status, body = make_request(
        f"{base_url}/api/v1/communications",
        method="POST",
        headers=tech_headers,
        data={
            "channel": "phone",
            "direction": "inbound",
            "content": "Technician logged a call",
            "from_email": "carol@example.com",
        },
    )
    assert status == 201
    assert body["communication"]["customer_id"] is None


def test_api_communications_non_string_provider_message_id_returns_400(api_server):
    """Code-reviewer non-blocking finding on NEW-233/257: a JSON number
    (or list/dict) in provider_message_id previously flowed unvalidated
    into CommunicationService.record_communication()'s .strip() call and
    raised an uncaught AttributeError, surfacing as a 500 instead of a
    400. routes.py now validates the type before that call."""
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/communications",
        method="POST",
        headers=headers,
        data={
            "channel": "phone",
            "direction": "inbound",
            "content": "Call with a malformed message id",
            "provider_message_id": 12345,
        },
    )
    assert status == 400
    assert "error" in body


def test_api_ai_chat_auth_and_validation(api_server, monkeypatch):
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    # 1. Unauthenticated -> 401
    status, body = make_request(
        f"{base_url}/api/v1/ai/chat",
        method="POST",
        data={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert status == 401

    # 2. Missing messages -> 400
    status, body = make_request(
        f"{base_url}/api/v1/ai/chat",
        method="POST",
        headers=headers,
        data={},
    )
    assert status == 400
    assert "Missing messages" in body.get("error", "")

    # Admission gate: mocked so this test is deterministic regardless of
    # real device model-server state at test time -- see
    # _mock_admitted_budget_decision()'s own docstring, and the identical
    # pattern already used by the T3 telemetry tests in this file (NEW-433).
    monkeypatch.setattr(
        "core.resource_gate.wait_and_reserve_context_budget",
        lambda *a, **k: _mock_admitted_budget_decision(),
    )
    monkeypatch.setattr("core.resource_gate.release_context_budget", _strict_release_spy())

    # 3. Successful proxy with mocked urlopen
    class MockHTTPResponse:
        def __init__(self, data, status=200):
            self.data = json.dumps(data).encode("utf-8")
            self.status = status

        def read(self):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    mock_resp_payload = {
        "choices": [{"message": {"role": "assistant", "content": "Hello there!"}}]
    }

    real_urlopen = urllib.request.urlopen

    def mock_urlopen(req, timeout=180.0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/v1/chat/completions" in url:
            return MockHTTPResponse(mock_resp_payload)
        return real_urlopen(req, timeout=timeout)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    status, body = make_request(
        f"{base_url}/api/v1/ai/chat",
        method="POST",
        headers=headers,
        data={
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 100,
            "temperature": 0.2,
        },
    )
    assert status == 200
    assert body["choices"][0]["message"]["content"] == "Hello there!"


class _MockHTTPResponse:
    def __init__(self, data, status=200):
        self.data = json.dumps(data).encode("utf-8")
        self.status = status

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _ReleaseContractViolation(BaseException):
    """Raised by `_strict_release_spy()` on a wrong-shape
    `release_context_budget` call. Derives from `BaseException`, NOT
    `Exception`, on purpose: the /api/v1/ai/chat route wraps its
    `release_context_budget(reservation_id)` call in a bare
    `except Exception` (routes.py finally-block). A plain `Exception`
    here would be caught, logged at WARNING, and the request would still
    return 200 -- i.e. the contract violation would be swallowed exactly
    the way `lambda *a, **k: True` swallowed it (NEW-443). BaseException
    escapes that handler so a regression fails the test loudly."""


def _strict_release_spy():
    """A `release_context_budget` stand-in enforcing the call contract
    NEW-442 broke: exactly one positional `reservation_id` (a str), or
    the `reservation_id=` kwarg -- never `release_context_budget(port,
    reservation_id)`. Raises on the arg-swapped shape so a future
    regression fails loudly instead of being swallowed."""

    def _spy(*args, **kwargs):
        if len(args) > 1:
            raise _ReleaseContractViolation(
                f"release_context_budget called with {len(args)} positionals: {args!r}"
            )
        if args:
            if not isinstance(args[0], str):
                raise _ReleaseContractViolation(
                    f"release_context_budget positional is {type(args[0]).__name__}, "
                    f"expected str reservation_id: {args[0]!r}"
                )
        elif "reservation_id" not in kwargs or not isinstance(
            kwargs["reservation_id"], str
        ):
            raise _ReleaseContractViolation(
                f"release_context_budget called without a str reservation_id: "
                f"args={args!r} kwargs={kwargs!r}"
            )
        return True

    return _spy


def _ai_chat_success_env(monkeypatch, base_url, release_spy):
    """Wire up the mocks shared by the NEW-442 regression tests: mocked
    admission gate, the given `release_context_budget` spy, and a
    path-scoped `urlopen` mock that only fakes the server-side
    llama-server proxy call. Returns the agent auth headers."""
    monkeypatch.setattr(
        "core.resource_gate.wait_and_reserve_context_budget",
        lambda *a, **k: _mock_admitted_budget_decision(),
    )
    monkeypatch.setattr("core.resource_gate.release_context_budget", release_spy)

    mock_resp_payload = {
        "choices": [{"message": {"role": "assistant", "content": "Hello there!"}}]
    }
    real_urlopen = urllib.request.urlopen

    def mock_urlopen(req, timeout=180.0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/v1/chat/completions" in url:
            return _MockHTTPResponse(mock_resp_payload)
        return real_urlopen(req, timeout=timeout)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    return _agent_headers(base_url)


def test_api_ai_chat_releases_reservation_with_correct_signature(api_server, monkeypatch):
    """NEW-442: the /api/v1/ai/chat `finally` block must call
    `release_context_budget(reservation_id)` -- a single positional (or
    the `reservation_id` kwarg), never `release_context_budget(port,
    reservation_id)`. The old arg-swapped call passed an int port as
    `reservation_id` and the hex id as `state_dir`, silently leaking the
    real lease (and creating a spurious CWD dir). The 5 pre-existing
    mock sites used `lambda *a, **k: True`, which swallowed the bug."""
    _, base_url, _, _ = api_server

    calls = []

    def release_spy(*args, **kwargs):
        calls.append((args, kwargs))
        return True

    headers = _ai_chat_success_env(monkeypatch, base_url, release_spy)

    status, body = make_request(
        f"{base_url}/api/v1/ai/chat",
        method="POST",
        headers=headers,
        data={
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 100,
            "temperature": 0.2,
        },
    )
    assert status == 200
    assert body["choices"][0]["message"]["content"] == "Hello there!"

    assert len(calls) == 1, f"expected exactly one release call, got {calls!r}"
    args, kwargs = calls[0]
    reservation_id = _mock_admitted_budget_decision().reservation_id
    assert args == (reservation_id,) or (
        not args and kwargs == {"reservation_id": reservation_id}
    ), f"release called with {args!r} {kwargs!r}"
    # Belt-and-braces: the arg-swapped NEW-442 bug passed the int port first.
    assert not any(isinstance(a, int) for a in args), f"int (port) arg leaked: {args!r}"


def test_api_ai_chat_warns_when_release_returns_false(api_server, monkeypatch, caplog):
    """NEW-442 / NEW-430: a `False` return from `release_context_budget()`
    means the reservation was already reaped/expired; the handler logs a
    WARNING on `restoricon_core.api` and the HTTP response is unaffected
    (still 200 with the normal body). Zero coverage before this test."""
    _, base_url, _, _ = api_server

    headers = _ai_chat_success_env(monkeypatch, base_url, lambda *a, **k: False)

    caplog.set_level("WARNING", logger="restoricon_core.api")

    status, body = make_request(
        f"{base_url}/api/v1/ai/chat",
        method="POST",
        headers=headers,
        data={
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 100,
            "temperature": 0.2,
        },
    )
    assert status == 200
    assert body["choices"][0]["message"]["content"] == "Hello there!"

    reservation_id = _mock_admitted_budget_decision().reservation_id
    warnings = [
        r.getMessage()
        for r in caplog.records
        if r.levelname == "WARNING" and r.name == "restoricon_core.api"
    ]
    assert any(
        (reservation_id in m or "NEW-430" in m) for m in warnings
    ), f"expected a release-failure warning, got {warnings!r}"


def test_api_ai_chat_emits_category_a_telemetry_on_success(api_server, monkeypatch, tmp_path, caplog):
    """T3 (docs/telemetry_layer_design.md §7): /api/v1/ai/chat emits a
    category-A `inference`/`completion` record from real llama-server
    `timings`/`usage` fields after resp_data is parsed, without changing
    the response returned to the caller. tests/conftest.py's autouse
    isolation fixture defaults TELEMETRY_ENABLED False and METRICS_DIR to
    a throwaway dir for every test -- this test explicitly opts back in
    (same pattern as tests/test_telemetry_t2_run_start.py).

    `mock_urlopen` below only fakes the *server-side* proxy call to
    llama-server (matched by the `/v1/chat/completions` path) and passes
    every other URL through to the real `urlopen` -- unlike the existing
    "3. Successful proxy with mocked urlopen" case in
    `test_api_ai_chat_auth_and_validation` above, which patches
    `urllib.request.urlopen` unconditionally. Because `make_request()`
    (this file's own HTTP test client) also calls `urllib.request.urlopen`
    to reach the local test server, an unconditional patch intercepts the
    *client's* request too and never actually exercises the server code
    at all -- it happens to still pass there only because the canned
    response coincidentally satisfies that test's own assertions. Flagged
    to the coordinator as a pre-existing test gap (out of T3's scope), not
    fixed here beyond not repeating it in this new test."""
    from telemetry import envelope, schema, store

    caplog.set_level("WARNING")
    envelope.reset_seq()
    store.reset_for_tests()
    monkeypatch.setattr(store, "TELEMETRY_ENABLED", True)
    monkeypatch.setattr(store, "METRICS_DIR", tmp_path)
    # Admission gate: mocked so this test is deterministic regardless of
    # real device RAM state at test time -- see _mock_admitted_budget_decision()'s
    # own docstring.
    monkeypatch.setattr(
        "core.resource_gate.wait_and_reserve_context_budget",
        lambda *a, **k: _mock_admitted_budget_decision(),
    )
    monkeypatch.setattr("core.resource_gate.release_context_budget", _strict_release_spy())

    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    class MockHTTPResponse:
        def __init__(self, data, status=200):
            self.data = json.dumps(data).encode("utf-8")
            self.status = status

        def read(self):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    mock_resp_payload = {
        "id": "chatcmpl-abc123",
        "system_fingerprint": "b1234-abcdef0",
        "choices": [
            {"message": {"role": "assistant", "content": "Hello there!"}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5},
        "timings": {
            "cache_n": 4,
            "prompt_n": 12,
            "prompt_ms": 50.0,
            "prompt_per_token_ms": 4.16,
            "prompt_per_second": 240.0,
            "predicted_n": 5,
            "predicted_ms": 100.0,
            "predicted_per_token_ms": 20.0,
            "predicted_per_second": 50.0,
        },
    }

    real_urlopen = urllib.request.urlopen

    def mock_urlopen(req, timeout=180.0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/v1/chat/completions" in url:
            return MockHTTPResponse(mock_resp_payload)
        return real_urlopen(req, timeout=timeout)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    try:
        status, body = make_request(
            f"{base_url}/api/v1/ai/chat",
            method="POST",
            headers=headers,
            data={
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": 100,
                "temperature": 0.2,
            },
        )
        assert status == 200
        assert body["choices"][0]["message"]["content"] == "Hello there!"

        deadline = time.monotonic() + 5.0
        records = []
        while time.monotonic() < deadline and not records:
            for path in tmp_path.rglob("inference.*.jsonl"):
                lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln]
                records.extend(json.loads(ln) for ln in lines)
            if not records:
                time.sleep(0.1)

        assert records, f"expected at least one category-A inference record to be written; log={caplog.text!r}"
        record = records[0]
        assert record["category"] == "inference"
        assert record["event_type"] == "completion"
        assert record["emitter"] == "codey-os.core-api"
        body_fields = record["body"]
        assert body_fields["backend"] == "local"
        assert body_fields["stream"] is False
        assert body_fields["prompt_tokens"] == 12
        assert body_fields["completion_tokens"] == 5
        assert body_fields["cached_prompt_tokens"] == 4
        assert body_fields["prefix_cache_hit"] is True
        assert body_fields["prefill_tps"] == 240.0
        assert body_fields["generation_tps"] == 50.0
        assert body_fields["finish_reason"] == "stop"
        assert body_fields["server_request_id"] == "chatcmpl-abc123"
        assert body_fields["server_fingerprint"] == "b1234-abcdef0"
        assert record["nulls"]["body.role"] == "call_site_not_yet_tagged"
        assert record["nulls"]["body.model_sha256"] == "model_sha256_not_computed"
        assert record["nulls"]["body.ttft_ms"] == "server_timings_absent"

        violations = schema.validate(record)
        assert violations == [], violations
    finally:
        store.reset_for_tests()


def _read_inference_records(tmp_path, timeout=5.0):
    deadline = time.monotonic() + timeout
    records = []
    while time.monotonic() < deadline and not records:
        for path in tmp_path.rglob("inference.*.jsonl"):
            lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln]
            records.extend(json.loads(ln) for ln in lines)
        if not records:
            time.sleep(0.1)
    return records


def test_api_ai_chat_telemetry_falls_back_to_usage_when_timings_absent(api_server, monkeypatch, tmp_path):
    """T3 / design constraint 2: when llama-server's `timings` block is
    absent, prefill/generation throughput fields must be honest nulls
    with reason `server_timings_absent` -- never back-computed from
    `wall_ms` -- while `prompt_tokens`/`completion_tokens` still fall
    back to `usage` when it's present. This is the branch
    `test_api_ai_chat_emits_category_a_telemetry_on_success` above does
    NOT exercise (that mock includes a full `timings` block)."""
    from telemetry import envelope, schema, store

    envelope.reset_seq()
    store.reset_for_tests()
    monkeypatch.setattr(store, "TELEMETRY_ENABLED", True)
    monkeypatch.setattr(store, "METRICS_DIR", tmp_path)
    # Admission gate: mocked so this test is deterministic regardless of
    # real device RAM state at test time -- see _mock_admitted_budget_decision()'s
    # own docstring.
    monkeypatch.setattr(
        "core.resource_gate.wait_and_reserve_context_budget",
        lambda *a, **k: _mock_admitted_budget_decision(),
    )
    monkeypatch.setattr("core.resource_gate.release_context_budget", _strict_release_spy())

    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    class MockHTTPResponse:
        def __init__(self, data, status=200):
            self.data = json.dumps(data).encode("utf-8")
            self.status = status

        def read(self):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    # No "timings" key at all -- only "usage" -- matching a server
    # response shape where the timings block genuinely never arrived.
    mock_resp_payload = {
        "choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 8},
    }

    real_urlopen = urllib.request.urlopen

    def mock_urlopen(req, timeout=180.0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/v1/chat/completions" in url:
            return MockHTTPResponse(mock_resp_payload)
        return real_urlopen(req, timeout=timeout)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    try:
        status, body = make_request(
            f"{base_url}/api/v1/ai/chat",
            method="POST",
            headers=headers,
            data={"messages": [{"role": "user", "content": "hello"}], "max_tokens": 50},
        )
        assert status == 200

        records = _read_inference_records(tmp_path)
        assert records, "expected a category-A inference record"
        record = records[0]
        body_fields = record["body"]
        nulls = record["nulls"]

        assert body_fields["prompt_tokens"] == 20
        assert body_fields["completion_tokens"] == 8
        for field in (
            "prefill_tps", "generation_tps", "prefill_ms", "generation_ms",
            "prompt_per_token_ms", "predicted_per_token_ms", "cached_prompt_tokens",
            "prefix_cache_hit",
        ):
            assert body_fields[field] is None, f"{field} should be null, got {body_fields.get(field)!r}"
            assert nulls[f"body.{field}"] == "server_timings_absent"

        violations = schema.validate(record)
        assert violations == [], violations
    finally:
        store.reset_for_tests()


def test_api_ai_chat_telemetry_honest_null_when_timings_and_usage_both_absent(api_server, monkeypatch, tmp_path):
    """T3 / design constraint 2, worst case: neither `timings` nor
    `usage` present -- prompt_tokens/completion_tokens must be honest
    nulls with reason `server_usage_absent`, never guessed."""
    from telemetry import envelope, schema, store

    envelope.reset_seq()
    store.reset_for_tests()
    monkeypatch.setattr(store, "TELEMETRY_ENABLED", True)
    monkeypatch.setattr(store, "METRICS_DIR", tmp_path)
    # Admission gate: mocked so this test is deterministic regardless of
    # real device RAM state at test time -- see _mock_admitted_budget_decision()'s
    # own docstring.
    monkeypatch.setattr(
        "core.resource_gate.wait_and_reserve_context_budget",
        lambda *a, **k: _mock_admitted_budget_decision(),
    )
    monkeypatch.setattr("core.resource_gate.release_context_budget", _strict_release_spy())

    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    class MockHTTPResponse:
        def __init__(self, data, status=200):
            self.data = json.dumps(data).encode("utf-8")
            self.status = status

        def read(self):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    mock_resp_payload = {
        "choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
    }

    real_urlopen = urllib.request.urlopen

    def mock_urlopen(req, timeout=180.0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/v1/chat/completions" in url:
            return MockHTTPResponse(mock_resp_payload)
        return real_urlopen(req, timeout=timeout)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    try:
        status, body = make_request(
            f"{base_url}/api/v1/ai/chat",
            method="POST",
            headers=headers,
            data={"messages": [{"role": "user", "content": "hello"}], "max_tokens": 50},
        )
        assert status == 200

        records = _read_inference_records(tmp_path)
        assert records, "expected a category-A inference record"
        record = records[0]
        body_fields = record["body"]
        nulls = record["nulls"]

        assert body_fields["prompt_tokens"] is None
        assert body_fields["completion_tokens"] is None
        assert nulls["body.prompt_tokens"] == "server_usage_absent"
        assert nulls["body.completion_tokens"] == "server_usage_absent"

        violations = schema.validate(record)
        assert violations == [], violations
    finally:
        store.reset_for_tests()


def test_api_staff_schedule_patch_reaches_router(api_server):
    """Live-verifier-caught bug: RestoriconRequestHandler (server.py) never
    defined do_PATCH, so every real HTTP PATCH -- including the Calendar
    UI's edit-schedule-entry form (web_surfaces.py:3737, `method = id ?
    'PATCH' : 'POST'`) hitting PATCH /api/v1/staff-schedules/{id} -- got a
    bare stdlib 501 "Unsupported method" before ever reaching routes.py.
    Unit tests that call APIRouter.handle_request() directly cannot catch
    this since they bypass the real BaseHTTPRequestHandler/socket layer
    entirely -- this test goes over a real socket via the api_server
    fixture's live RestoriconAPIServer to exercise the actual HTTP verb
    dispatch."""
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/staff-schedules",
        method="POST",
        headers=headers,
        data={
            "user_id": 1,
            "title": "On-site inspection",
            "start_time": "2026-09-15T09:00:00",
            "end_time": "2026-09-15T10:00:00",
            "status": "scheduled",
            "notes": "initial",
        },
    )
    assert status == 201
    sched_id = body["schedule"]["id"]

    status, body = make_request(
        f"{base_url}/api/v1/staff-schedules/{sched_id}",
        method="PATCH",
        headers=headers,
        data={"notes": "rescheduled by Calendar UI edit form"},
    )
    assert status != 501, f"PATCH still unreachable (bare stdlib 501): {body!r}"
    assert status == 200
    assert body["schedule"]["notes"] == "rescheduled by Calendar UI edit form"


def test_api_ai_chat_no_telemetry_written_when_disabled(api_server, monkeypatch, tmp_path):
    """Kill-switch check (design §5.3): with TELEMETRY_ENABLED left False
    (the default -- tests/conftest.py's autouse isolation fixture), no
    category-A record is written for a successful completion, and the
    response to the caller is unaffected."""
    from telemetry import store

    store.reset_for_tests()
    monkeypatch.setattr(store, "METRICS_DIR", tmp_path)
    assert store.TELEMETRY_ENABLED is False
    # Admission gate: mocked so this test is deterministic regardless of
    # real device RAM state at test time -- see _mock_admitted_budget_decision()'s
    # own docstring.
    monkeypatch.setattr(
        "core.resource_gate.wait_and_reserve_context_budget",
        lambda *a, **k: _mock_admitted_budget_decision(),
    )
    monkeypatch.setattr("core.resource_gate.release_context_budget", _strict_release_spy())

    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    class MockHTTPResponse:
        def __init__(self, data, status=200):
            self.data = json.dumps(data).encode("utf-8")
            self.status = status

        def read(self):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    mock_resp_payload = {
        "choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    real_urlopen = urllib.request.urlopen

    def mock_urlopen(req, timeout=180.0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/v1/chat/completions" in url:
            return MockHTTPResponse(mock_resp_payload)
        return real_urlopen(req, timeout=timeout)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    try:
        status, body = make_request(
            f"{base_url}/api/v1/ai/chat",
            method="POST",
            headers=headers,
            data={"messages": [{"role": "user", "content": "hello"}], "max_tokens": 50},
        )
        assert status == 200
        assert body["choices"][0]["message"]["content"] == "hi"

        time.sleep(0.5)
        assert list(tmp_path.rglob("inference.*.jsonl")) == []
    finally:
        store.reset_for_tests()



def test_api_staff_schedule_patch_and_delete_missing_id_are_404(api_server):
    """NEW-491 (cloud review 2026-09-15): PATCH on a nonexistent staff
    schedule 500'd (`'NoneType' object has no attribute 'to_dict'`) and
    DELETE reported `{"deleted": true}` for a row that never existed.
    Both must be a clean 404 -- exercised over a real socket since PATCH
    only became reachable once server.py gained do_PATCH."""
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/staff-schedules/999999",
        method="PATCH", headers=headers, data={"notes": "ghost"},
    )
    assert status == 404, body
    assert body == {"error": "Staff schedule not found"}

    status, body = make_request(
        f"{base_url}/api/v1/staff-schedules/999999", method="DELETE", headers=headers,
    )
    assert status == 404, body
    assert body == {"error": "Staff schedule not found"}

    # Sanity: a real row still deletes exactly once, then 404s on retry.
    status, body = make_request(
        f"{base_url}/api/v1/staff-schedules", method="POST", headers=headers,
        data={"user_id": 1, "title": "One-off", "start_time": "2026-09-16T09:00:00",
              "end_time": "2026-09-16T10:00:00", "status": "scheduled", "notes": None},
    )
    assert status == 201, body
    sched_id = body["schedule"]["id"]
    status, body = make_request(f"{base_url}/api/v1/staff-schedules/{sched_id}", method="DELETE", headers=headers)
    assert (status, body) == (200, {"deleted": True})
    status, body = make_request(f"{base_url}/api/v1/staff-schedules/{sched_id}", method="DELETE", headers=headers)
    assert status == 404, body


def test_api_staff_schedule_patch_unknown_user_id_is_400(api_server):
    """F4: the Calendar edit modal sends user_id on PATCH; an unknown id is
    a 400 with the service's message, not an IntegrityError 500."""
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)
    status, body = make_request(
        f"{base_url}/api/v1/staff-schedules", method="POST", headers=headers,
        data={"user_id": 1, "title": "Reassign me", "start_time": "2026-09-17T09:00:00",
              "end_time": "2026-09-17T10:00:00", "status": "scheduled", "notes": None},
    )
    assert status == 201, body
    sched_id = body["schedule"]["id"]
    status, body = make_request(
        f"{base_url}/api/v1/staff-schedules/{sched_id}",
        method="PATCH", headers=headers, data={"user_id": 424242},
    )
    assert status == 400, body
    assert body["error"] == "Unknown user_id: 424242"


def test_api_staff_schedule_get_by_id(api_server):
    """NEW-492: `GET /api/v1/staff-schedules/{id}` for a real row returns
    200 with the schedule dict; a nonexistent id returns a clean 404."""
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/staff-schedules", method="POST", headers=headers,
        data={"user_id": 1, "title": "Fetch me by id", "start_time": "2026-09-18T09:00:00",
              "end_time": "2026-09-18T10:00:00", "status": "scheduled", "notes": "n/a"},
    )
    assert status == 201, body
    sched_id = body["schedule"]["id"]

    status, body = make_request(
        f"{base_url}/api/v1/staff-schedules/{sched_id}", headers=headers,
    )
    assert status == 200, body
    assert body["schedule"]["id"] == sched_id
    assert body["schedule"]["title"] == "Fetch me by id"

    status, body = make_request(
        f"{base_url}/api/v1/staff-schedules/999999", headers=headers,
    )
    assert status == 404, body
    assert body == {"error": "Staff schedule not found"}


def test_api_staff_schedule_get_by_id_permission_denied_for_technician(api_server):
    """NEW-492 RBAC: ROLE_TECHNICIAN holds no PERM_READ_STAFF_SCHEDULES,
    same as the existing list/PATCH/DELETE routes on this resource."""
    server, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/staff-schedules", method="POST", headers=headers,
        data={"user_id": 1, "title": "Restricted", "start_time": "2026-09-19T09:00:00",
              "end_time": "2026-09-19T10:00:00", "status": "scheduled", "notes": None},
    )
    assert status == 201, body
    sched_id = body["schedule"]["id"]

    server.auth_service.create_user(
        username="tech2",
        plain_password="TechSecretPassword123",
        full_name="Tech Nician Two",
        email="tech2@restoricon.com",
        role=ROLE_TECHNICIAN,
    )
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "tech2", "password": "TechSecretPassword123"},
    )
    assert status == 200
    tech_headers = {"Authorization": f"Bearer {body['token']}"}

    status, _ = make_request(
        f"{base_url}/api/v1/staff-schedules/{sched_id}", headers=tech_headers
    )
    assert status == 403


def test_api_staff_schedule_non_integer_id_is_400_without_raw_pyexc_text(api_server):
    """NEW-520: `GET`/`PATCH`/`DELETE /api/v1/staff-schedules/{id}` parse
    the id via the shared `_parse_int_path_segment` helper, which raises a
    clean ValueError instead of letting Python's raw `int()` exception
    text ('invalid literal for int() with base 10') reach the client."""
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    status, body = make_request(f"{base_url}/api/v1/staff-schedules/abc", headers=headers)
    assert status == 400, body
    assert body == {"error": "Invalid 'schedule_id' path segment: 'abc'"}

    status, body = make_request(
        f"{base_url}/api/v1/staff-schedules/abc",
        method="PATCH", headers=headers, data={"notes": "ghost"},
    )
    assert status == 400, body
    assert body == {"error": "Invalid 'schedule_id' path segment: 'abc'"}

    status, body = make_request(
        f"{base_url}/api/v1/staff-schedules/abc", method="DELETE", headers=headers,
    )
    assert status == 400, body
    assert body == {"error": "Invalid 'schedule_id' path segment: 'abc'"}


def test_api_staff_schedule_patch_malformed_extra_segment_is_generic_404(api_server):
    """NEW-520: a malformed path with a trailing extra segment past the id
    (e.g. a client bug appending something after the id) must fall through
    to the router's generic 'Endpoint not found' 404, not be misread as a
    bad schedule_id -- the PATCH/DELETE block's route-matching guard now
    matches the sibling GET block's single-path-segment check."""
    _, base_url, _, _ = api_server
    headers = _agent_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/staff-schedules/1/foo",
        method="PATCH", headers=headers, data={"notes": "ghost"},
    )
    assert status == 404, body
    assert body == {"error": "Endpoint not found: PATCH /api/v1/staff-schedules/1/foo"}


def test_api_customers_limit_non_integer_is_400_without_raw_pyexc_text(api_server):
    """NEW-505: `?limit=` is parsed via the shared `_parse_int_query_param`
    helper, which raises a clean ValueError instead of letting Python's
    raw `int()` exception text ('invalid literal for int() with base 10')
    reach the client."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    status, body = make_request(f"{base_url}/api/v1/customers?limit=abc", headers=headers)
    assert status == 400, body
    assert "error" in body
    assert "base 10" not in body["error"]


def test_api_customers_limit_is_clamped_to_maximum(api_server):
    """NEW-505: an oversized `?limit=` is clamped to 1000, not passed
    through unbounded to the DB layer."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    status, body = make_request(
        f"{base_url}/api/v1/customers?limit=99999999", headers=headers
    )
    assert status == 200, body
    assert len(body["customers"]) <= 1000


# NEW-522/NEW-523 batch 1: (method, url_path, var_name) for every leak-fix
# site that got a bare `int(...)` -> `_parse_int_path_segment`/
# `_parse_int_query_param` wrap in this round. Each is hit with a
# non-numeric value and must return a clean 400, not Python's raw
# `int()` exception text.
_NEW522_523_BATCH1_SITES = [
    ("POST", "/api/v1/users/{}/password", "user_id"),
    ("POST", "/api/v1/users/{}/suspend", "user_id"),
    ("POST", "/api/v1/users/{}/activate", "user_id"),
    ("GET", "/api/v1/users/{}/permissions", "user_id"),
    ("GET", "/api/v1/users/{}/active-references", "user_id"),
    ("GET", "/api/v1/crm/tasks/{}", "task_id"),
    ("GET", "/api/v1/projects/{}", "proj_id"),
    ("GET", "/api/v1/estimates/{}", "est_id"),
    ("GET", "/api/v1/contracts/{}", "contract_id"),
    ("GET", "/api/v1/invoices/{}", "inv_id"),
    ("GET", "/api/v1/documents/{}", "doc_id"),
    ("GET", "/api/v1/portal/projects/{}", "proj_id"),
    ("GET", "/api/v1/subcontractors/{}", "sub_id"),
    ("GET", "/api/v1/appointments/{}", "appt_id"),
    ("POST", "/api/v1/operations/projects/{}/stage", "proj_id"),
    ("GET", "/api/v1/operations/projects/{}/summary", "proj_id"),
    ("GET", "/api/v1/operations/projects/{}/milestones", "proj_id"),
    ("GET", "/api/v1/operations/projects/{}/equipment", "proj_id"),
    ("POST", "/api/v1/operations/work-orders/{}/dispatch", "wo_id"),
    ("POST", "/api/v1/operations/work-orders/{}/accept", "wo_id"),
    ("POST", "/api/v1/operations/work-orders/{}/complete", "wo_id"),
    ("POST", "/api/v1/operations/work-orders/{}/verify", "wo_id"),
    ("POST", "/api/v1/operations/work-orders/{}/status", "wo_id"),
    ("GET", "/api/v1/operations/milestones/{}", "mid"),
    ("POST", "/api/v1/operations/milestones/{}/status", "mid"),
]


def test_api_new522_batch1_non_integer_path_segments_are_400_without_raw_pyexc_text(api_server):
    """NEW-522 batch 1: every bare `int(path.split(...))`-style path-segment
    parse in this batch now goes through the shared `_parse_int_path_segment`
    helper, which raises a clean ValueError instead of letting Python's raw
    `int()` exception text ('invalid literal for int() with base 10') reach
    the client as a leaked 400 body."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    for method, url_template, var_name in _NEW522_523_BATCH1_SITES:
        url = f"{base_url}{url_template.format('abc')}"
        status, body = make_request(url, method=method, headers=headers, data={} if method == "POST" else None)
        assert status == 400, f"{method} {url_template}: expected 400, got {status} ({body})"
        assert body == {"error": f"Invalid '{var_name}' path segment: 'abc'"}, f"{method} {url_template}: {body}"


def test_api_new523_staff_schedules_user_id_non_integer_is_400_without_raw_pyexc_text(api_server):
    """NEW-523: `GET /api/v1/staff-schedules?user_id=` is parsed via the
    shared `_parse_int_query_param` helper, which raises a clean ValueError
    instead of letting Python's raw `int()` exception text reach the client.
    Also confirms absent/empty `user_id` still means "no filter" (None),
    not a validation error."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    status, body = make_request(f"{base_url}/api/v1/staff-schedules?user_id=abc", headers=headers)
    assert status == 400, body
    assert body == {"error": "Invalid 'user_id' query parameter: 'abc'"}

    # Absent user_id still means "no filter" (None), unaffected by the fix.
    status, body = make_request(f"{base_url}/api/v1/staff-schedules", headers=headers)
    assert status == 200, body
    assert "schedules" in body


def test_api_new522_batch1_valid_integer_path_segments_still_work(api_server):
    """NEW-522 batch 1 spot-check: a valid numeric id on a representative
    site from each distinct index-expression shape in the batch (front-
    anchored `[4]`, front-anchored `[5]`, `[-1]`, and the two special-shape
    milestone/work-order sites) still resolves normally after the
    `_parse_int_path_segment` wrap -- the fix only rejects non-numeric
    input, it doesn't change behavior for valid input."""
    server, base_url, admin_user, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    # Front-anchored [4]: /api/v1/users/{id}/active-references
    status, body = make_request(
        f"{base_url}/api/v1/users/{admin_user.id}/active-references", headers=headers
    )
    assert status == 200, body

    # Front-anchored [5]: /api/v1/operations/projects/{id}/milestones (empty
    # list for a nonexistent-but-valid-format project id, not a 400/500)
    status, body = make_request(
        f"{base_url}/api/v1/operations/projects/999999/milestones", headers=headers
    )
    assert status == 200, body
    assert body["milestones"] == []

    # [-1] form: /api/v1/projects/{id} (404 "not found" for a
    # nonexistent-but-valid-format id, not a 400/500)
    status, body = make_request(f"{base_url}/api/v1/projects/999999", headers=headers)
    assert status == 404, body

    # Special shape: /api/v1/operations/milestones/{id} (bare int(sub_path))
    status, body = make_request(f"{base_url}/api/v1/operations/milestones/999999", headers=headers)
    assert status == 404, body

    # Special shape: /api/v1/operations/work-orders/{id} (int(path[len(prefix):]))
    status, body = make_request(f"{base_url}/api/v1/operations/work-orders/999999", headers=headers)
    assert status == 404, body


# NEW-526 (NEW-522 batch 2): (method, url_template, var_name) for every
# relative-`[-2]`-indexed sub-action route that got a segment-count guard
# added AND its id-parsing switched to the shared `_parse_int_path_segment`
# helper. `{}` is the single id slot between the route's prefix and its
# trailing verb suffix.
_NEW526_BATCH2_SITES = [
    ("POST", "/api/v1/customers/{}/update", "cust_id"),
    ("POST", "/api/v1/crm/tasks/{}/complete", "task_id"),
    ("POST", "/api/v1/crm/tasks/{}/update", "task_id"),
    ("POST", "/api/v1/leads/{}/update", "lead_id"),
    ("POST", "/api/v1/opportunities/{}/transition", "opp_id"),
    ("POST", "/api/v1/opportunities/{}/update", "opp_id"),
    ("POST", "/api/v1/projects/{}/update", "proj_id"),
    ("POST", "/api/v1/contracts/{}/sign", "contract_id"),
    ("POST", "/api/v1/invoices/{}/pay", "inv_id"),
    ("GET", "/api/v1/documents/{}/download", "doc_id"),
    ("GET", "/api/v1/portal/projects/{}/milestones", "proj_id"),
    ("POST", "/api/v1/portal/contracts/{}/sign", "contract_id"),
    ("POST", "/api/v1/subcontractors/{}/qualification", "sub_id"),
    ("POST", "/api/v1/subcontractors/{}/update", "sub_id"),
    ("GET", "/api/v1/subcontractors/{}/active-references", "sub_id"),
    ("POST", "/api/v1/subcontractors/{}/delete", "sub_id"),
    ("POST", "/api/v1/appointments/{}/status", "appt_id"),
    ("POST", "/api/v1/appointments/{}/update", "appt_id"),
    ("POST", "/api/v1/appointment-types/{}/update", "type_id"),
    ("GET", "/api/v1/appointment-types/{}/active-references", "type_id"),
    ("POST", "/api/v1/appointment-types/{}/delete", "type_id"),
    ("POST", "/api/v1/automation-rules/{}/match", "rule_id"),
    ("POST", "/api/v1/automation-rules/{}/delete", "rule_id"),
    ("GET", "/api/v1/finance/projects/{}/pnl", "proj_id"),
    ("POST", "/api/v1/marketing/reviews/{}/submit", "req_id"),
    ("POST", "/api/v1/hr/timesheets/{}/approve", "ts_id"),
    ("POST", "/api/v1/procurement/purchase-orders/{}/receive", "po_id"),
]


def test_api_new526_batch2_non_integer_path_segments_are_400_without_raw_pyexc_text(api_server):
    """NEW-526 (NEW-522 batch 2): all 27 sub-action routes that used to
    parse their id via a bare `int(path.split("/")[-2])` now go through the
    shared `_parse_int_path_segment` helper, which raises a clean
    ValueError instead of letting Python's raw `int()` exception text
    ('invalid literal for int() with base 10') reach the client. A
    non-numeric value in the single-segment position between the route's
    prefix and its trailing verb suffix must still be recognized as that
    route (the new segment-count guard only rejects paths with more than
    one segment there, not non-numeric single segments) and return the
    clean 400 shape."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    for method, url_template, var_name in _NEW526_BATCH2_SITES:
        url = f"{base_url}{url_template.format('abc')}"
        status, body = make_request(url, method=method, headers=headers, data={} if method == "POST" else None)
        assert status == 400, f"{method} {url_template}: expected 400, got {status} ({body})"
        assert body == {"error": f"Invalid '{var_name}' path segment: 'abc'"}, f"{method} {url_template}: {body}"


def test_api_new526_batch2_malformed_extra_segment_is_404_and_no_write_happens(api_server):
    """NEW-526: a malformed path with an extra numeric segment inserted
    before the trailing verb (e.g. `POST /api/v1/customers/5/99/update`)
    used to silently parse the LAST segment (99) as the id via
    `path.split("/")[-2]`, acting on the wrong record with no error and no
    404. The new segment-count guard now makes these routes NOT match at
    all on such a path, falling through to the router's generic 404 --
    and, critically, the record actually named earlier in the URL (and
    every other record) must be left completely unmodified, not just get
    a 404 response. Covers a representative subset of the 27 sites: two
    POST writes, two POST deletes, and one GET (read-only) route, seeding
    two distinct records per case so a wrong-id write would be observable."""
    server, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    def create_customer(company_name):
        status, body = make_request(
            f"{base_url}/api/v1/customers",
            method="POST",
            headers=headers,
            data={
                "first_name": "First",
                "last_name": "Last",
                "company_name": company_name,
                "email": f"{company_name.lower().replace(' ', '')}@example.com",
                "service_address": "1 Main St",
                "customer_type": "commercial",
                "status": "active",
            },
        )
        assert status == 201, body
        return body["customer"]["id"]

    def get_customer(cust_id):
        status, body = make_request(f"{base_url}/api/v1/customers/{cust_id}", headers=headers)
        assert status == 200, body
        return body["customer"]

    # --- Case 1: POST .../customers/{id}/update (plain write) ---
    cust_a = create_customer("Alpha Corp")
    cust_b = create_customer("Beta Corp")

    status, body = make_request(
        f"{base_url}/api/v1/customers/{cust_a}/{cust_b}/update",
        method="POST",
        headers=headers,
        data={"company_name": "HACKED"},
    )
    assert status == 404, body

    assert get_customer(cust_a)["company_name"] == "Alpha Corp"
    assert get_customer(cust_b)["company_name"] == "Beta Corp"

    # --- Case 2: POST .../subcontractors/{id}/delete (destructive) ---
    def create_subcontractor(company_name):
        status, body = make_request(
            f"{base_url}/api/v1/subcontractors",
            method="POST",
            headers=headers,
            data={"company_name": company_name, "primary_trade": "roofing"},
        )
        assert status == 201, body
        return body["subcontractor"]["id"]

    sub_a = create_subcontractor("Sub Alpha")
    sub_b = create_subcontractor("Sub Beta")

    status, body = make_request(
        f"{base_url}/api/v1/subcontractors/{sub_a}/{sub_b}/delete",
        method="POST",
        headers=headers,
    )
    assert status == 404, body

    status, body = make_request(f"{base_url}/api/v1/subcontractors/{sub_a}", headers=headers)
    assert status == 200, body
    assert body["subcontractor"]["company_name"] == "Sub Alpha"
    status, body = make_request(f"{base_url}/api/v1/subcontractors/{sub_b}", headers=headers)
    assert status == 200, body
    assert body["subcontractor"]["company_name"] == "Sub Beta"

    # --- Case 3: POST .../appointment-types/{id}/delete (destructive) ---
    def create_appointment_type(name):
        status, body = make_request(
            f"{base_url}/api/v1/appointment-types",
            method="POST",
            headers=headers,
            data={"name": name},
        )
        assert status == 201, body
        return body["appointment_type"]["id"]

    type_a = create_appointment_type("Roof Inspection")
    type_b = create_appointment_type("Water Mitigation")

    status, body = make_request(
        f"{base_url}/api/v1/appointment-types/{type_a}/{type_b}/delete",
        method="POST",
        headers=headers,
    )
    assert status == 404, body

    status, body = make_request(f"{base_url}/api/v1/appointment-types", headers=headers)
    assert status == 200, body
    remaining_names = {t["name"] for t in body["appointment_types"]}
    assert {"Roof Inspection", "Water Mitigation"} <= remaining_names

    # --- Case 4: POST .../opportunities/{id}/transition (stage write) ---
    def create_opportunity(title, customer_id):
        status, body = make_request(
            f"{base_url}/api/v1/opportunities",
            method="POST",
            headers=headers,
            data={"customer_id": customer_id, "title": title},
        )
        assert status == 201, body
        return body["opportunity"]["id"]

    def get_opportunity(opp_id):
        status, body = make_request(f"{base_url}/api/v1/opportunities/{opp_id}", headers=headers)
        assert status == 200, body
        return body["opportunity"]

    opp_a = create_opportunity("Alpha Deal", cust_a)
    opp_b = create_opportunity("Beta Deal", cust_b)
    stage_a_before = get_opportunity(opp_a)["pipeline_stage"]
    stage_b_before = get_opportunity(opp_b)["pipeline_stage"]

    status, body = make_request(
        f"{base_url}/api/v1/opportunities/{opp_a}/{opp_b}/transition",
        method="POST",
        headers=headers,
        data={"stage": "contacted"},
    )
    assert status == 404, body

    assert get_opportunity(opp_a)["pipeline_stage"] == stage_a_before
    assert get_opportunity(opp_b)["pipeline_stage"] == stage_b_before

    # --- Case 5: GET .../finance/projects/{id}/pnl (read-only) ---
    def create_project(title, customer_id):
        status, body = make_request(
            f"{base_url}/api/v1/projects",
            method="POST",
            headers=headers,
            data={
                "customer_id": customer_id,
                "title": title,
                "property_address": "1 Main St",
                "project_type": "commercial_remodel",
                "contract_amount": 10000.0,
            },
        )
        assert status == 201, body
        return body["project"]["id"]

    proj_a = create_project("Alpha Project", cust_a)
    proj_b = create_project("Beta Project", cust_b)

    status, body = make_request(
        f"{base_url}/api/v1/finance/projects/{proj_a}/{proj_b}/pnl",
        headers=headers,
    )
    assert status == 404, body

    # The route still resolves correctly for each project individually
    # via its own single-segment path -- the guard only rejects the
    # malformed multi-segment shape, not legitimate requests.
    status, body = make_request(f"{base_url}/api/v1/finance/projects/{proj_a}/pnl", headers=headers)
    assert status == 200, body
    status, body = make_request(f"{base_url}/api/v1/finance/projects/{proj_b}/pnl", headers=headers)
    assert status == 200, body


# NEW-525: (method, url) pairs for every verb-suffix route in this round's
# batch whose id path segment can be omitted entirely, causing the old
# `path.split("/")[N]`-style parse to instead mis-parse the trailing verb
# word as the id (or, for the compound stage/transition route, hit the
# ValueError path with a nonsensical id). The new guard requires a
# non-empty, slash-free segment between the route's prefix and its verb
# suffix, so an omitted id now falls through to the router's generic 404
# instead of ever reaching `_parse_int_path_segment`. Includes NEW-525's
# Part 3 stray sibling site, /api/v1/leads/{id}/score (GET and POST, no
# method restriction on that route).
#
# The 5 work-orders verb routes (dispatch/accept/complete/verify/status)
# are deliberately NOT in this table -- see
# test_api_new530_work_orders_omitted_id_now_404s_not_400s below. Prior to
# NEW-530 an omitted id on those routes observably landed on a 400, not a
# 404 (the work-orders catch-all lacked the isdigit() pre-guard); NEW-530
# added that guard, so they now agree with this table's 404 contract but
# are still covered by their own dedicated test rather than folded in
# here.
_NEW525_OMITTED_ID_404_SITES = [
    ("POST", "/api/v1/users/password"),
    ("POST", "/api/v1/users/suspend"),
    ("POST", "/api/v1/users/activate"),
    ("GET", "/api/v1/users/permissions"),
    ("GET", "/api/v1/users/active-references"),
    ("POST", "/api/v1/operations/projects/stage"),
    ("GET", "/api/v1/operations/projects/summary"),
    ("GET", "/api/v1/operations/projects/milestones"),
    ("GET", "/api/v1/operations/projects/equipment"),
    ("GET", "/api/v1/leads/score"),
    ("POST", "/api/v1/leads/score"),
]


def test_api_new525_omitted_id_path_segments_are_generic_404(api_server):
    """NEW-525: omitting the id path segment on any of these verb-suffix
    routes (e.g. `POST /api/v1/users/password` instead of
    `POST /api/v1/users/{id}/password`) must fall through to the router's
    generic 'Endpoint not found' 404 -- not have the trailing verb word
    (e.g. 'password') mis-parsed as the id."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    for method, url in _NEW525_OMITTED_ID_404_SITES:
        status, body = make_request(
            f"{base_url}{url}", method=method, headers=headers, data={} if method == "POST" else None
        )
        assert status == 404, f"{method} {url}: expected 404, got {status} ({body})"
        assert body == {"error": f"Endpoint not found: {method} {url}"}, f"{method} {url}: {body}"


# The 5 work-orders verb-suffix sites from Part 1 site list #10-14.
# /api/v1/operations/work-orders/ has a generic single-segment catch-all
# route (`.../work-orders/{id}`, no method restriction) that still matches
# when the id is omitted and the trailing verb word lands in the single
# segment slot, e.g. `POST /api/v1/operations/work-orders/dispatch` has
# sub_path "dispatch". NEW-530 added an isdigit() pre-guard to this
# catch-all, matching the analogous users and equipment catch-alls, so a
# non-numeric single segment (including this omitted-id case) now falls
# through to the router's generic 404 instead of reaching
# `_parse_int_path_segment` for a 400. What the earlier NEW-525 guard
# fixed on these 5 routes is the separate *multi-segment* misrouting shape
# covered below.
_NEW525_WORK_ORDER_VERB_SUFFIXES = ["dispatch", "accept", "complete", "verify", "status"]


def test_api_new530_work_orders_omitted_id_now_404s_not_400s(api_server):
    """NEW-530: with the work-orders catch-all's isdigit() guard added,
    an omitted id on any of the 5 work-orders verb routes (the verb word
    itself landing in the catch-all's single-segment slot) now falls
    through to the router's generic 404, matching the /api/v1/users/{id}
    and /api/v1/operations/equipment/{id} catch-alls' contract."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    for verb in _NEW525_WORK_ORDER_VERB_SUFFIXES:
        url = f"/api/v1/operations/work-orders/{verb}"
        status, body = make_request(f"{base_url}{url}", method="POST", headers=headers, data={})
        assert status == 404, f"POST {url}: expected 404, got {status} ({body})"
        assert body == {"error": f"Endpoint not found: POST {url}"}, f"POST {url}: {body}"


def test_api_new530_work_orders_catchall_non_numeric_id_is_404_not_400(api_server):
    """NEW-530: GET/POST on /api/v1/operations/work-orders/{non-numeric}
    now falls through to the router's generic 404 instead of reaching
    _parse_int_path_segment for a 400 -- the isdigit() guard now matches
    the analogous users/equipment catch-alls' contract exactly.

    The trailing-slash (empty-segment) case described in this task's
    original brief is NOT exercised here: `handle_request` does
    `path.rstrip("/")` on every incoming path before any route matching
    (routes.py ~line 339), so `GET /api/v1/operations/work-orders/`
    is normalized to `/api/v1/operations/work-orders` before it ever
    reaches this catch-all -- it exactly matches the list-endpoint route
    instead (200, `{"work_orders": []}`), both before and after this
    fix. Verified live; the isdigit()-guard's empty-string branch is
    correct but unreachable in practice for this reason."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login", method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    for method, url in [
        ("GET", "/api/v1/operations/work-orders/abc"),
        ("POST", "/api/v1/operations/work-orders/abc"),
    ]:
        status, body = make_request(
            f"{base_url}{url}", method=method, headers=headers, data={} if method == "POST" else None
        )
        assert status == 404, f"{method} {url}: expected 404, got {status} ({body})"
        assert body == {"error": f"Endpoint not found: {method} {url}"}, f"{method} {url}: {body}"


def test_api_new525_work_orders_multi_segment_id_is_generic_404_not_misrouted(api_server):
    """The actual bug this round's guard fixes on the 5 work-orders verb
    routes: pre-fix, `path.split("/")[5]` on a malformed multi-segment
    path like `/api/v1/operations/work-orders/1/2/dispatch` would have
    silently taken index [5] = '1' as the id and dispatched work order 1
    -- the NEW-526 misrouting class, acting on the wrong record with no
    error. The new segment-count guard now makes these routes NOT match a
    multi-segment path at all, falling through (the work-orders catch-all
    also requires a single segment, so it doesn't match multi-segment
    paths either) to the router's generic 404."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    for verb in _NEW525_WORK_ORDER_VERB_SUFFIXES:
        url = f"/api/v1/operations/work-orders/1/2/{verb}"
        status, body = make_request(f"{base_url}{url}", method="POST", headers=headers, data={})
        assert status == 404, f"POST {url}: expected 404, got {status} ({body})"
        assert body == {"error": f"Endpoint not found: POST {url}"}, f"POST {url}: {body}"


def test_api_new522_batch1_non_integer_path_segments_still_pass_with_new525_guard(api_server):
    """Confirms NEW-525's added guard didn't regress the NEW-522 batch 1
    behavior it sits alongside: a single non-numeric segment in the id
    position (as opposed to an omitted one) must still be recognized as
    that route and reach `_parse_int_path_segment` for a clean 400, not
    fall through to a 404."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    status, body = make_request(
        f"{base_url}/api/v1/users/abc/password", method="POST", headers=headers, data={}
    )
    assert status == 400, body
    assert body == {"error": "Invalid 'user_id' path segment: 'abc'"}


_NEW531_MULTI_SEGMENT_404_SITES = [
    ("POST", "/api/v1/users/1/2/password"),
    ("POST", "/api/v1/users/1/2/suspend"),
    ("POST", "/api/v1/users/1/2/activate"),
    ("GET", "/api/v1/users/1/2/permissions"),
    ("GET", "/api/v1/users/1/2/active-references"),
    ("POST", "/api/v1/operations/projects/1/2/stage"),
    ("POST", "/api/v1/operations/projects/1/2/transition"),
    ("GET", "/api/v1/operations/projects/1/2/summary"),
    ("GET", "/api/v1/operations/projects/1/2/milestones"),
    ("GET", "/api/v1/operations/projects/1/2/equipment"),
]


def test_api_new531_other_new525_sites_multi_segment_id_is_generic_404_not_misrouted(api_server):
    """NEW-531: extends NEW-525's multi-segment-misrouting regression
    coverage (previously only the 5 work-orders verb sites) to the other
    9 NEW-525 sites sharing the identical vulnerable shape -- a malformed
    path with an extra segment between the id and the verb suffix (e.g.
    /api/v1/users/1/2/password) must fall through to the router's generic
    404, not get silently misrouted onto the wrong record (the NEW-526
    misrouting class). Covers the users-family (5 verb suffixes) and the
    projects-family (4 distinct guards; both arms of the compound
    stage/transition route are exercised here since the existing
    omitted-id table only exercises /stage)."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login", method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    for method, url in _NEW531_MULTI_SEGMENT_404_SITES:
        status, body = make_request(
            f"{base_url}{url}", method=method, headers=headers, data={} if method == "POST" else None
        )
        assert status == 404, f"{method} {url}: expected 404, got {status} ({body})"
        assert body == {"error": f"Endpoint not found: {method} {url}"}, f"{method} {url}: {body}"


def test_api_new532_active_query_param_negative_value_is_not_clamped(api_server):
    """NEW-532: `active` is a real 0/1-valued filter, not an id -- unlike
    the other 33 NEW-527 sites, clamping a negative value to 0 here would
    silently change the query's meaning (returns all inactive users
    instead of the correct empty result for a nonsensical filter value).
    Creates a genuinely inactive user first so the assertion can't
    accidentally pass just because no inactive users exist in the
    fixture."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login", method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    # Create and suspend a user so a real active=0 row exists.
    create_status, create_body = make_request(
        f"{base_url}/api/v1/users", method="POST", headers=headers,
        data={"username": "inactive_test_user", "password": "TestPassword123",
              "full_name": "Inactive Test User", "email": "inactive@restoricon.com",
              "role": "technician"},
    )
    assert create_status == 201, create_body
    target_id = create_body["user"]["id"]
    suspend_status, suspend_body = make_request(
        f"{base_url}/api/v1/users/{target_id}/suspend", method="POST", headers=headers, data={}
    )
    assert suspend_status == 200, suspend_body

    # Positive control: active=0 finds the genuinely inactive user.
    status, body = make_request(f"{base_url}/api/v1/users?active=0", headers=headers)
    assert status == 200, body
    assert any(u["id"] == target_id for u in body["users"]), body

    # The actual fix: active=-1 must NOT be clamped to 0 -- it's a
    # nonsensical filter value (active is always 0 or 1), so it must
    # match nothing, even though a real active=0 user now exists.
    status, body = make_request(f"{base_url}/api/v1/users?active=-1", headers=headers)
    assert status == 200, body
    assert body["users"] == [], body
    assert body["total"] == 0, body


# NEW-527: (method, url, param_name) for every optional query-param filter
# in this round's batch whose bare `int(...)` got wrapped in the shared
# `_parse_int_query_param` helper, preserving each site's exact existing
# absent-value semantics (the raw-string guard var or the `"key" in
# query_params` presence check, whichever the site already used).
_NEW527_QUERY_PARAM_SITES = [
    ("GET", "/api/v1/users?active=abc", "active"),
    ("GET", "/api/v1/crm/tasks?customer_id=abc", "customer_id"),
    ("GET", "/api/v1/crm/tasks?opportunity_id=abc", "opportunity_id"),
    ("GET", "/api/v1/crm/tasks?lead_id=abc", "lead_id"),
    ("GET", "/api/v1/crm/tasks?assigned_user_id=abc", "assigned_user_id"),
    ("GET", "/api/v1/opportunities?customer_id=abc", "customer_id"),
    ("GET", "/api/v1/opportunities?assigned_user_id=abc", "assigned_user_id"),
    ("GET", "/api/v1/projects?customer_id=abc", "customer_id"),
    ("GET", "/api/v1/estimates?customer_id=abc", "customer_id"),
    ("GET", "/api/v1/estimates?project_id=abc", "project_id"),
    ("GET", "/api/v1/contracts?customer_id=abc", "customer_id"),
    ("GET", "/api/v1/contracts?project_id=abc", "project_id"),
    ("GET", "/api/v1/invoices?customer_id=abc", "customer_id"),
    ("GET", "/api/v1/invoices?project_id=abc", "project_id"),
    ("GET", "/api/v1/documents?customer_id=abc", "customer_id"),
    ("GET", "/api/v1/documents?project_id=abc", "project_id"),
    ("GET", "/api/v1/portal/estimates?project_id=abc", "project_id"),
    ("GET", "/api/v1/portal/contracts?project_id=abc", "project_id"),
    ("GET", "/api/v1/portal/invoices?project_id=abc", "project_id"),
    ("GET", "/api/v1/portal/documents?project_id=abc", "project_id"),
    ("GET", "/api/v1/communications?customer_id=abc", "customer_id"),
    ("GET", "/api/v1/communications?project_id=abc", "project_id"),
    ("GET", "/api/v1/audit-log?entity_id=abc", "entity_id"),
    ("GET", "/api/v1/audit-log?actor_id=abc", "actor_id"),
    ("GET", "/api/v1/appointments?customer_id=abc", "customer_id"),
    ("GET", "/api/v1/operations/work-orders?project_id=abc", "project_id"),
    ("GET", "/api/v1/operations/work-orders?subcontractor_id=abc", "subcontractor_id"),
    ("GET", "/api/v1/operations/equipment?project_id=abc", "project_id"),
    ("GET", "/api/v1/finance/transactions?project_id=abc", "project_id"),
    ("GET", "/api/v1/finance/transactions?customer_id=abc", "customer_id"),
    ("GET", "/api/v1/hr/timesheets?employee_id=abc", "employee_id"),
    ("GET", "/api/v1/hr/timesheets?project_id=abc", "project_id"),
    ("GET", "/api/v1/procurement/purchase-orders?vendor_id=abc", "vendor_id"),
    ("GET", "/api/v1/procurement/purchase-orders?project_id=abc", "project_id"),
]


def test_api_new527_non_integer_query_params_are_400_without_raw_pyexc_text(api_server):
    """NEW-527: every bare `int(...)` wrap on an optional query-param
    filter in this batch now goes through the shared
    `_parse_int_query_param` helper, which raises a clean ValueError
    instead of letting Python's raw `int()` exception text ('invalid
    literal for int() with base 10') reach the client."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    for method, url, param_name in _NEW527_QUERY_PARAM_SITES:
        status, body = make_request(f"{base_url}{url}", method=method, headers=headers)
        assert status == 400, f"{method} {url}: expected 400, got {status} ({body})"
        assert body == {"error": f"Invalid '{param_name}' query parameter: 'abc'"}, f"{method} {url}: {body}"


def test_api_new527_valid_integer_query_params_still_filter_correctly(api_server):
    """NEW-527 spot-check (one site per absent-value-semantics shape): a
    valid numeric query value still resolves and filters normally after
    the `_parse_int_query_param` wrap -- the fix only rejects non-numeric
    input, it doesn't change behavior for valid input."""
    server, base_url, admin_user, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    status, body = make_request(
        f"{base_url}/api/v1/customers",
        method="POST",
        headers=headers,
        data={
            "first_name": "Carla",
            "last_name": "Nguyen",
            "company_name": "Nguyen LLC",
            "email": "carla@nguyenllc.com",
            "service_address": "5 Elm St, Hartford, CT",
            "customer_type": "residential",
            "status": "active",
        },
    )
    assert status == 201, body
    cust_id = body["customer"]["id"]

    status, body = make_request(
        f"{base_url}/api/v1/opportunities",
        method="POST",
        headers=headers,
        data={"customer_id": cust_id, "title": "Nguyen Deal"},
    )
    assert status == 201, body

    # Shape A: guard is `if <raw_var> else None` -- /api/v1/opportunities?customer_id=
    status, body = make_request(
        f"{base_url}/api/v1/opportunities?customer_id={cust_id}", headers=headers
    )
    assert status == 200, body
    assert len(body["opportunities"]) == 1
    assert body["opportunities"][0]["customer_id"] == cust_id

    # Shape B: guard is `if "<key>" in query_params else None` --
    # /api/v1/finance/transactions?customer_id= (no matching transactions
    # for a fresh customer, but the filter must apply without error).
    status, body = make_request(
        f"{base_url}/api/v1/finance/transactions?customer_id={cust_id}", headers=headers
    )
    assert status == 200, body
    assert body["transactions"] == []


# NEW-528: 11 sites where a bare `int(json_body.get(...))` on a POST body
# field had NO pre-existing truthy guard, so a `null` value crashed with a
# raw TypeError-turned-500 (not just a leaky ValueError-turned-400). Each
# tuple is (method, url, base_body, field_name), where base_body is the
# minimal set of *other* fields needed so the request reaches the
# `_parse_int_body_field` call for `field_name` rather than 400ing earlier
# on some other missing required field. None of these routes need real
# rows to exist first -- in every site, the int-parse of `field_name`
# happens before any DB lookup or write, so the parse failure fires first
# regardless of whether the other referenced ids are real.
_NEW528_UNGUARDED_SITES = [
    ("POST", "/api/v1/ai/chat", {"messages": [{"role": "user", "content": "hi"}]}, "max_tokens"),
    ("POST", "/api/v1/operations/work-orders/1/dispatch", {}, "subcontractor_id"),
    ("POST", "/api/v1/operations/equipment/deploy", {}, "equipment_id"),
    ("POST", "/api/v1/operations/equipment/deploy", {"equipment_id": 1}, "project_id"),
    ("POST", "/api/v1/operations/equipment/return", {}, "deployment_id"),
    ("POST", "/api/v1/marketing/campaigns", {}, "leads_generated"),
    ("POST", "/api/v1/marketing/reviews/request", {}, "customer_id"),
    ("POST", "/api/v1/marketing/reviews/1/submit", {}, "rating"),
    ("POST", "/api/v1/compliance/scan", {}, "threshold_days"),
    ("POST", "/api/v1/hr/timesheets", {}, "employee_id"),
    ("POST", "/api/v1/procurement/purchase-orders", {}, "vendor_id"),
]

# NEW-528: 3 sites that already had a truthy guard (`if json_body.get(...)
# else None` or an explicit `if not x: return 400`) excluding falsy values
# -- including `None` -- from ever reaching the bare `int(...)` call. These
# were never vulnerable to the null-value 500; only the non-numeric-string
# case is new coverage here.
_NEW528_GUARDED_SITES = [
    (
        "POST",
        "/api/v1/operations/equipment/deploy",
        {"equipment_id": 1, "project_id": 1, "work_order_id": "abc"},
        "work_order_id",
    ),
    ("POST", "/api/v1/crm/generate-cadence-tasks", {"opportunity_id": "abc"}, "opportunity_id"),
    ("POST", "/api/v1/portal/messages", {"message": "hi", "project_id": "abc"}, "project_id"),
]


def test_api_new528_body_field_null_is_400_not_500(api_server):
    """NEW-528: 11 POST-body int-parse sites had no guard excluding JSON
    `null`, so `int(None)` raised a bare TypeError that fell through
    handle_request's `except ValueError` and reached the generic `except
    Exception` handler as a raw, un-messaged 500. After the
    `_parse_int_body_field` fix, the same request must be a clean 400 with
    a non-leaking message -- the 500-to-400 status flip is the load-bearing
    assertion here, not just the message text."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    for method, url, base_body, field in _NEW528_UNGUARDED_SITES:
        payload = dict(base_body)
        payload[field] = None
        status, body = make_request(f"{base_url}{url}", method=method, headers=headers, data=payload)
        assert status == 400, f"{method} {url} field={field}: expected 400, got {status} ({body})"
        assert body == {"error": f"Invalid '{field}' body field: None"}, f"{method} {url}: {body}"


def test_api_new528_body_field_non_numeric_string_is_400_without_raw_pyexc_text(api_server):
    """NEW-528: the same 11 unguarded sites plus 3 already-guarded sites
    (whose truthy guard only ever excluded falsy values, not non-numeric
    strings) all now go through `_parse_int_body_field`, which raises a
    clean ValueError instead of letting Python's raw `int()` exception
    text reach the client."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    for method, url, base_body, field in _NEW528_UNGUARDED_SITES + _NEW528_GUARDED_SITES:
        payload = dict(base_body)
        payload[field] = "abc"
        status, body = make_request(f"{base_url}{url}", method=method, headers=headers, data=payload)
        assert status == 400, f"{method} {url} field={field}: expected 400, got {status} ({body})"
        assert body == {"error": f"Invalid '{field}' body field: 'abc'"}, f"{method} {url}: {body}"


def test_api_new528_valid_integer_body_fields_still_work(api_server):
    """NEW-528 spot-check (mirroring NEW-527's valid-input spot check): a
    valid numeric value in the body field still parses and takes effect
    normally after the `_parse_int_body_field` wrap -- the fix only rejects
    `null`/non-numeric input, it doesn't change behavior for valid input.
    Covers two of the 14 changed sites that had no pre-existing valid-input
    coverage elsewhere in this file (`/api/v1/ai/chat`'s `max_tokens` and
    `/api/v1/operations/work-orders/{}/dispatch`'s `subcontractor_id` do
    already have coverage via other tests in this file)."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    status, body = make_request(
        f"{base_url}/api/v1/compliance/scan",
        method="POST",
        headers=headers,
        data={"threshold_days": 45},
    )
    assert status == 200, body
    assert body["status"] == "scanned"

    status, body = make_request(
        f"{base_url}/api/v1/marketing/campaigns",
        method="POST",
        headers=headers,
        data={"name": "Spring Promo", "leads_generated": 12},
    )
    assert status == 201, body
    assert body["campaign"]["leads_generated"] == 12


def test_api_new529_contacts_malformed_extra_segment_is_404_and_no_write_happens(api_server):
    """NEW-529: `/api/v1/contacts/{id}/update` and the `/delete`+`DELETE`
    pair shared NEW-526's missing-segment-guard bug -- `path.split("/")[-2]`
    with no segment-count check, so a malformed path with an extra segment
    (e.g. `POST /api/v1/contacts/5/99/update`) used to silently parse the
    LAST segment (99) as the id, acting on the wrong contact with no error.
    The new guard makes these routes NOT match at all on such a path,
    falling through to the router's generic 404 -- and both named contacts
    must be left completely unmodified, not just get a 404 response."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    def create_contact(name, external_id=None):
        payload = {"name": name}
        if external_id:
            payload["external_id"] = external_id
        status, body = make_request(f"{base_url}/api/v1/contacts", method="POST", headers=headers, data=payload)
        assert status == 201, body
        return body["contact"]["id"]

    def get_contact(cid):
        status, body = make_request(f"{base_url}/api/v1/contacts/{cid}", headers=headers)
        assert status == 200, body
        return body["contact"]

    contact_a = create_contact("Contact A")
    contact_b = create_contact("Contact B", external_id="aigentik-ext-999")

    # --- update: malformed extra-segment path must not silently rename B ---
    status, body = make_request(
        f"{base_url}/api/v1/contacts/{contact_a}/{contact_b}/update",
        method="POST",
        headers=headers,
        data={"name": "HACKED"},
    )
    assert status == 404, body
    assert get_contact(contact_a)["name"] == "Contact A"
    assert get_contact(contact_b)["name"] == "Contact B"

    # --- delete (POST .../delete): malformed extra-segment path must not
    # silently delete B ---
    status, body = make_request(
        f"{base_url}/api/v1/contacts/{contact_a}/{contact_b}/delete",
        method="POST",
        headers=headers,
    )
    assert status == 404, body
    assert get_contact(contact_a)["name"] == "Contact A"
    assert get_contact(contact_b)["name"] == "Contact B"


def test_api_new529_contacts_external_id_update_still_works_after_guard(api_server):
    """NEW-529 regression-protection test: the whole reason this fix needed
    a different shape than NEW-526's bare `_parse_int_path_segment` swap is
    that contacts intentionally support a non-numeric `external_id` in the
    id slot. This confirms the added segment-count guard doesn't break that
    -- a single non-numeric segment must still match the route and resolve
    via `get_contact_by_external_id`, for both update and delete."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    status, body = make_request(
        f"{base_url}/api/v1/contacts",
        method="POST",
        headers=headers,
        data={"name": "External Update Contact", "external_id": "aigentik-abc-123"},
    )
    assert status == 201, body

    status, body = make_request(
        f"{base_url}/api/v1/contacts/aigentik-abc-123/update",
        method="POST",
        headers=headers,
        data={"name": "Renamed"},
    )
    assert status == 200, body
    assert body["contact"]["name"] == "Renamed"

    status, body = make_request(
        f"{base_url}/api/v1/contacts",
        method="POST",
        headers=headers,
        data={"name": "External Delete Contact", "external_id": "aigentik-def-456"},
    )
    assert status == 201, body

    status, body = make_request(
        f"{base_url}/api/v1/contacts/aigentik-def-456/delete",
        method="POST",
        headers=headers,
    )
    assert status == 200, body
    assert body == {"deleted": True}

    status, body = make_request(f"{base_url}/api/v1/contacts/aigentik-def-456", headers=headers)
    assert status == 404, body


def test_api_new529_contacts_bare_delete_multi_segment_is_404_and_no_write_happens(api_server):
    """NEW-529 regression/defense-in-depth coverage for the bare `DELETE
    /api/v1/contacts/{id}` arm -- scoping confirmed this arm never actually
    misrouted (its id_str derivation is `path[len(PREFIX):]`, which already
    included the full multi-segment remainder rather than just the last
    segment, so `isdigit()` would already have failed and fallen through to
    the external_id branch pre-fix). This is not bug-closure coverage, just
    confirms the added guard doesn't change well-formed-vs-malformed
    behavior for this specific arm."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    status, body = make_request(
        f"{base_url}/api/v1/contacts", method="POST", headers=headers, data={"name": "Bare Delete Contact"}
    )
    assert status == 201, body
    cid = body["contact"]["id"]

    status, body = make_request(
        f"{base_url}/api/v1/contacts/{cid}/99", method="DELETE", headers=headers
    )
    assert status == 404, body

    status, body = make_request(f"{base_url}/api/v1/contacts/{cid}", headers=headers)
    assert status == 200, body
    assert body["contact"]["name"] == "Bare Delete Contact"


def test_api_new529_bare_delete_on_path_ending_in_literal_delete_now_404s(api_server):
    """NEW-529 disclosed, intentional behavior change: pre-fix, the original
    one-liner match condition was `path.endswith("/delete") and method ==
    "POST" or method == "DELETE"`, which -- due to Python operator
    precedence (`and` binds tighter than `or`) -- parsed as `(endswith AND
    POST) OR (method == DELETE)`. A bare DELETE request satisfied the
    second disjunct regardless of the path's suffix, so `DELETE
    /api/v1/contacts/{id}/delete` (a path that happens to literally end in
    "/delete") took the delete-arm's `id_str = path.split("/")[-2]`
    derivation and deleted the contact -- silently ignoring the trailing
    "/delete" segment as if it were the plain single-id DELETE route. The
    new segment-count guard on the `/delete`-suffix disjunct now requires
    method == POST for that arm, and the plain bare-DELETE disjunct now
    requires no "/" in the remainder -- "{id}/delete" contains one, so
    neither disjunct matches and the route now correctly 404s instead of
    deleting the contact. No legitimate caller relies on DELETEing a path
    with a literal trailing "/delete" segment (the documented API contract
    is POST-only for that path shape); this is a hardening side effect of
    the misrouting fix, not a caller-visible regression."""
    _, base_url, _, _ = api_server
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    headers = {"Authorization": f"Bearer {body['token']}"}

    status, body = make_request(
        f"{base_url}/api/v1/contacts", method="POST", headers=headers, data={"name": "Literal Delete Suffix Contact"}
    )
    assert status == 201, body
    cid = body["contact"]["id"]

    status, body = make_request(
        f"{base_url}/api/v1/contacts/{cid}/delete", method="DELETE", headers=headers
    )
    assert status == 404, body

    status, body = make_request(f"{base_url}/api/v1/contacts/{cid}", headers=headers)
    assert status == 200, body
    assert body["contact"]["name"] == "Literal Delete Suffix Contact"
