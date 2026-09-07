"""
Unit and integration tests for public website API intake endpoints:
- POST /api/v1/public/leads
- POST /api/v1/public/booking
- Rate limiting, honeypot mitigation, CRM pipeline ingestion
"""

import json
import pytest
from restoricon_core.api.routes import APIRouter
from restoricon_core.api.rate_limiter import RateLimiter
from restoricon_core.auth import AuthService, ROLE_ADMIN
from restoricon_core.database import DatabaseManager
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService


@pytest.fixture
def setup_api():
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    auth = AuthService(db)
    crm = CRMService(db, audit)
    comm = CommunicationService(db)
    scheduling = SchedulingService(db, audit)
    automation = AutomationService(db, audit)
    operations = OperationsService(db, audit)
    rate_limiter = RateLimiter(max_requests=5, window_seconds=60)

    # Initialize admin user
    user = auth.create_user("admin", "adminpass123", "Admin User", "admin@restoricon.com", ROLE_ADMIN)
    token = auth.create_token(user)

    router = APIRouter(
        auth_service=auth,
        crm_service=crm,
        comm_service=comm,
        audit_service=audit,
        scheduling_service=scheduling,
        automation_service=automation,
        operations_service=operations,
        rate_limiter=rate_limiter,
    )
    return router, db, crm, auth, token


def test_public_lead_submission(setup_api):
    router, db, crm, auth, admin_token = setup_api

    payload = {
        "name": "Jane Doe",
        "phone": "555-0199",
        "email": "jane.doe@example.com",
        "address": "456 Oak Avenue, Denver, CO",
        "project_type": "water_damage",
        "description": "Basement flooded from broken pipe",
        "urgency": "urgent",
        "insurance": True,
        "insurance_carrier": "State Farm",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = {"cf-connecting-ip": "203.0.113.195"}

    code, resp_headers, data = router.handle_request("POST", "/api/v1/public/leads", headers, body_bytes)
    assert code == 201
    assert data["success"] is True
    assert data["status"] == "received"
    assert data["lead_id"] > 0
    assert data["customer_id"] > 0
    assert data["opportunity_id"] > 0
    assert "score" in data
    assert "X-RateLimit-Remaining" in resp_headers

    # Verify CRM database state
    admin_actor = auth.authenticate_token(admin_token)

    cust = crm.get_customer(data["customer_id"], admin_actor)
    assert cust is not None
    assert cust.first_name == "Jane"
    assert cust.last_name == "Doe"
    assert cust.email == "jane.doe@example.com"

    lead = crm.get_lead(data["lead_id"], admin_actor)
    assert lead is not None
    assert lead.property_type == "water_damage"
    assert lead.urgency_level == "urgent"
    assert lead.insurance_status == "insured"

    opp = crm.get_opportunity(data["opportunity_id"], admin_actor)
    assert opp is not None
    assert "Jane Doe" in opp.title

    # Verify task created
    tasks = crm.list_tasks(admin_actor, customer_id=cust.id)
    assert len(tasks) >= 1
    assert any("Jane Doe" in t.title for t in tasks)


def test_public_lead_honeypot_spam_trap(setup_api):
    router, db, crm, auth, admin_token = setup_api

    payload = {
        "name": "Spam Bot",
        "email": "bot@spammer.org",
        "website_hp": "http://spamlink.xyz",  # Honeypot filled by bot
        "description": "Buy cheap viagra online",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = {"cf-connecting-ip": "198.51.100.1"}

    code, resp_headers, data = router.handle_request("POST", "/api/v1/public/leads", headers, body_bytes)
    assert code == 201
    assert data["success"] is True
    assert data["lead_id"] == 0

    # Ensure no customer or lead created in db
    admin_actor = auth.authenticate_token(admin_token)
    assert crm.get_customer_by_email("bot@spammer.org", admin_actor) is None


def test_public_lead_rate_limiting(setup_api):
    router, db, crm, auth, admin_token = setup_api
    headers = {"cf-connecting-ip": "198.51.100.42"}

    payload = {"name": "Test User", "phone": "555-1234"}
    body_bytes = json.dumps(payload).encode("utf-8")

    # Max requests is 5
    for _ in range(5):
        code, _, _ = router.handle_request("POST", "/api/v1/public/leads", headers, body_bytes)
        assert code == 201

    # 6th request must trigger 429
    code, resp_headers, data = router.handle_request("POST", "/api/v1/public/leads", headers, body_bytes)
    assert code == 429
    assert "error" in data
    assert resp_headers["X-RateLimit-Remaining"] == "0"


def test_public_booking_submission(setup_api):
    router, db, crm, auth, admin_token = setup_api

    payload = {
        "name": "Bob Smith",
        "phone": "555-9876",
        "email": "bob.smith@example.com",
        "service_type": "mold_remediation",
        "preferred_date": "2026-09-10",
        "preferred_time_slot": "afternoon",
        "notes": "Musty odor in master bedroom closet",
    }
    body_bytes = json.dumps(payload).encode("utf-8")
    headers = {"cf-connecting-ip": "203.0.113.88"}

    code, resp_headers, data = router.handle_request("POST", "/api/v1/public/booking", headers, body_bytes)
    assert code == 201
    assert data["success"] is True
    assert data["appointment_id"] > 0
    assert data["customer_id"] > 0
    assert data["status"] == "pending_confirmation"

    admin_actor = auth.authenticate_token(admin_token)

    cust = crm.get_customer(data["customer_id"], admin_actor)
    assert cust is not None
    assert cust.first_name == "Bob"
    assert cust.last_name == "Smith"
