"""
Integration tests for Restoricon Core HTTP REST API server.
Tests live HTTP request-response roundtrips, token authentication, role-based scoping,
and audit log generation.
"""

import json
import socket
import urllib.request
import urllib.error
import pytest
from restoricon_core.api.server import RestoriconAPIServer
from restoricon_core.auth import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_AI_AGENT, ROLE_TECHNICIAN
from restoricon_core.models import Customer


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
