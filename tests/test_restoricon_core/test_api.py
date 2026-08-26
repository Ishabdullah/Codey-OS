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
from restoricon_core.auth import ROLE_ADMIN, ROLE_CUSTOMER, ROLE_AI_AGENT
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
