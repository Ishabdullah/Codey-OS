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

    def mock_urlopen(req, timeout=180.0):
        return MockHTTPResponse(mock_resp_payload)

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
    monkeypatch.setattr("core.resource_gate.release_context_budget", lambda *a, **k: True)

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
    monkeypatch.setattr("core.resource_gate.release_context_budget", lambda *a, **k: True)

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
    monkeypatch.setattr("core.resource_gate.release_context_budget", lambda *a, **k: True)

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
    monkeypatch.setattr("core.resource_gate.release_context_budget", lambda *a, **k: True)

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

