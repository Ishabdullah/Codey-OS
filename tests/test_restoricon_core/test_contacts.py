"""
Unit tests for Restoricon Core contacts module (Track B Phase B2 cutover).
Verifies Contact schema, models, RBAC permissions, CRMService methods,
batch sync from external/Android sources, and HTTP REST API endpoints.
"""

import json
import pytest
from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_READ_CONTACTS,
    PERM_WRITE_CONTACTS,
    ROLE_ADMIN,
    ROLE_AI_AGENT,
    ROLE_CUSTOMER,
    ROLE_MANAGER,
    ROLE_PROJECT_MANAGER,
    ROLE_SALES,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Contact
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.scheduling_service import SchedulingService


@pytest.fixture
def setup_core():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    comm_service = CommunicationService(db)
    crm_service = CRMService(db, audit_service)
    sched_service = SchedulingService(db, audit_service)
    auto_service = AutomationService(db, audit_service)
    router = APIRouter(
        auth_service=auth_service,
        crm_service=crm_service,
        comm_service=comm_service,
        audit_service=audit_service,
        scheduling_service=sched_service,
        automation_service=auto_service,
    )
    user = auth_service.create_user(
        username="admin",
        plain_password="SecretPassword123!",
        full_name="Admin User",
        email="admin@restoricon.com",
        role=ROLE_ADMIN,
    )
    agent = auth_service.create_user(
        username="aigentik",
        plain_password="SecretPassword123!",
        full_name="AI Agent",
        email="agent@restoricon.com",
        role=ROLE_AI_AGENT,
    )
    actor_admin = AuthContext(user_id=user.id, username="admin", role=ROLE_ADMIN, actor_type="human")
    actor_agent = AuthContext(user_id=agent.id, username="aigentik", role=ROLE_AI_AGENT, actor_type="agent")
    return db, auth_service, crm_service, router, actor_admin, actor_agent


def test_contact_rbac_permissions():
    """Verify RBAC permissions for all roles."""
    for role in [ROLE_ADMIN, ROLE_MANAGER, ROLE_SALES, ROLE_PROJECT_MANAGER, ROLE_AI_AGENT]:
        ctx = AuthContext(user_id=1, username="test", role=role, actor_type="agent")
        assert ctx.has_permission(PERM_READ_CONTACTS) is True
        assert ctx.has_permission(PERM_WRITE_CONTACTS) is True

    for role in [ROLE_TECHNICIAN, ROLE_CUSTOMER]:
        ctx = AuthContext(user_id=2, username="test", role=role, actor_type="human")
        assert ctx.has_permission(PERM_READ_CONTACTS) is False
        assert ctx.has_permission(PERM_WRITE_CONTACTS) is False


def test_contact_crud_lifecycle(setup_core):
    db, auth_service, crm_service, _, _, actor = setup_core

    contact = Contact(
        external_id="contact_0001",
        name="John Doe",
        aliases=["johnd"],
        phones=["(860) 555-1234", "860-555-5678"],
        emails=["john.doe@example.com"],
        address="123 Main St, Hartford, CT",
        relationship="client",
        type="person",
        notes="Important contact",
        instructions="Always answer promptly",
        reply_behavior="always",
        roles=["CUSTOMER"],
        active_role="CUSTOMER",
        source="manual",
    )

    created = crm_service.create_contact(contact, actor)
    assert created.id is not None
    assert created.external_id == "contact_0001"
    assert created.name == "John Doe"
    assert len(created.phones) == 2
    assert created.reply_behavior == "always"

    # Get by integer ID
    fetched = crm_service.get_contact(created.id, actor)
    assert fetched is not None
    assert fetched.name == "John Doe"
    assert fetched.aliases == ["johnd"]
    assert fetched.phones == ["(860) 555-1234", "860-555-5678"]
    assert fetched.emails == ["john.doe@example.com"]

    # Get by external_id
    by_ext = crm_service.get_contact_by_external_id("contact_0001", actor)
    assert by_ext is not None
    assert by_ext.id == created.id

    # Update contact
    updated = crm_service.update_contact(
        created.id,
        {
            "notes": "Updated notes",
            "phones": ["860-555-9999"],
            "trade": "plumbing",
            "licensed": 1,
            "license_number": "LIC-9876",
        },
        actor,
    )
    assert updated is not None
    assert updated.notes == "Updated notes"
    assert updated.phones == ["860-555-9999"]
    assert updated.trade == "plumbing"
    assert updated.licensed == 1
    assert updated.license_number == "LIC-9876"

    # Delete contact
    deleted = crm_service.delete_contact(created.id, actor)
    assert deleted is True
    assert crm_service.get_contact(created.id, actor) is None


def test_find_contact(setup_core):
    db, auth_service, crm_service, _, actor, _ = setup_core

    c1 = Contact(
        external_id="contact_0001",
        name="Alice Smith",
        aliases=["asmith", "ally"],
        phones=["860-111-2222"],
        emails=["alice@smith.org"],
        relationship="engineer",
        address="100 Maple Ave, Hartford, CT",
        business_name="Smith Consulting",
    )
    c2 = Contact(
        external_id="contact_0002",
        name="Bob Builder",
        aliases=["bobby"],
        phones=["860-333-4444"],
        emails=["bob@builder.com"],
        type="subcontractor",
        trade="carpentry",
        business_name="Builder LLC",
    )
    crm_service.create_contact(c1, actor)
    crm_service.create_contact(c2, actor)

    # Match by external_id
    assert crm_service.find_contact("contact_0001", actor).name == "Alice Smith"
    # Match by phone digits
    assert crm_service.find_contact("8601112222", actor).name == "Alice Smith"
    assert crm_service.find_contact("(860) 333-4444", actor).name == "Bob Builder"
    # Match by email
    assert crm_service.find_contact("alice@smith.org", actor).name == "Alice Smith"
    # Match by name
    assert crm_service.find_contact("Bob", actor).name == "Bob Builder"
    # Match by alias
    assert crm_service.find_contact("ally", actor).name == "Alice Smith"
    # Match by relationship
    assert crm_service.find_contact("engineer", actor).name == "Alice Smith"
    # Match by business name
    assert crm_service.find_contact("Builder LLC", actor).name == "Bob Builder"
    # Match by address
    assert crm_service.find_contact("Maple Ave", actor).name == "Alice Smith"
    # Empty query
    assert crm_service.find_contact("", actor) is None
    assert crm_service.find_contact("   ", actor) is None
    # No match
    assert crm_service.find_contact("NonExistent", actor) is None


def test_upsert_contact(setup_core):
    db, auth_service, crm_service, _, _, actor = setup_core

    # Insert on initial upsert
    contact = Contact(
        external_id="contact_0050",
        name="Charlie Brown",
        phones=["860-777-8888"],
        emails=["charlie@peanuts.com"],
    )
    upserted = crm_service.upsert_contact(contact, actor)
    assert upserted.id is not None
    assert upserted.name == "Charlie Brown"

    # Update on second upsert
    contact_v2 = Contact(
        external_id="contact_0050",
        name="Charles Brown",
        notes="Updated through upsert",
    )
    upserted_v2 = crm_service.upsert_contact(contact_v2, actor)
    assert upserted_v2.id == upserted.id
    assert upserted_v2.name == "Charles Brown"
    assert upserted_v2.notes == "Updated through upsert"


def test_sync_contacts_batch(setup_core):
    db, auth_service, crm_service, _, _, actor = setup_core

    # Batch 1: Initial sync of 2 contacts
    batch_1 = [
        Contact(
            name="Diana Prince",
            phones=["860-999-0001"],
            source="android_contacts",
        ),
        Contact(
            name="Clark Kent",
            phones=["860-999-0002"],
            source="android_contacts",
        ),
    ]
    stats_1 = crm_service.sync_contacts_batch(batch_1, actor)
    assert stats_1["android"] == 2
    assert stats_1["added"] == 2
    assert stats_1["updated"] == 0
    assert stats_1["total"] == 2

    # Batch 2: Re-syncing Clark Kent with new alias + new contact Bruce Wayne
    batch_2 = [
        Contact(
            name="Clark Kent",
            phones=["(860) 999-0002"],
            source="android_contacts",
        ),
        Contact(
            name="Bruce Wayne",
            phones=["860-999-0003"],
            source="android_contacts",
        ),
    ]
    stats_2 = crm_service.sync_contacts_batch(batch_2, actor)
    assert stats_2["android"] == 2
    assert stats_2["added"] == 1
    assert stats_2["updated"] == 1
    assert stats_2["total"] == 3


def test_contacts_api_endpoints(setup_core):
    db, auth_service, crm_service, router, actor_admin, _ = setup_core

    admin_user = auth_service.get_user_by_id(actor_admin.user_id)
    token = auth_service.create_token(admin_user)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. POST /api/v1/contacts
    contact_body = {
        "external_id": "contact_0100",
        "name": "Bruce Banner",
        "phones": ["860-123-4567"],
        "emails": ["banner@avengers.org"],
        "type": "person",
    }
    status, _, res = router.handle_request(
        "POST", "/api/v1/contacts", headers, json.dumps(contact_body).encode("utf-8")
    )
    assert status == 201
    assert res["contact"]["name"] == "Bruce Banner"
    cid = res["contact"]["id"]

    # 2. GET /api/v1/contacts
    status, _, res = router.handle_request("GET", "/api/v1/contacts", headers, b"")
    assert status == 200
    assert len(res["contacts"]) >= 1

    # 3. GET /api/v1/contacts/find?q=banner
    status, _, res = router.handle_request("GET", "/api/v1/contacts/find?q=banner", headers, b"")
    assert status == 200
    assert res["contact"]["external_id"] == "contact_0100"

    # 4. POST /api/v1/contacts/upsert
    upsert_body = {
        "external_id": "contact_0100",
        "name": "Dr. Bruce Banner",
        "notes": "Scientist",
    }
    status, _, res = router.handle_request(
        "POST", "/api/v1/contacts/upsert", headers, json.dumps(upsert_body).encode("utf-8")
    )
    assert status == 200
    assert res["contact"]["name"] == "Dr. Bruce Banner"

    # 5. GET /api/v1/contacts/{id} (by integer id and external_id)
    status, _, res = router.handle_request("GET", f"/api/v1/contacts/{cid}", headers, b"")
    assert status == 200
    assert res["contact"]["name"] == "Dr. Bruce Banner"

    status, _, res = router.handle_request("GET", "/api/v1/contacts/contact_0100", headers, b"")
    assert status == 200
    assert res["contact"]["id"] == cid

    # 6. POST /api/v1/contacts/{id}/update
    status, _, res = router.handle_request(
        "POST",
        f"/api/v1/contacts/{cid}/update",
        headers,
        json.dumps({"notes": "Avenger"}).encode("utf-8"),
    )
    assert status == 200
    assert res["contact"]["notes"] == "Avenger"

    # 7. POST /api/v1/contacts/sync
    sync_body = {
        "contacts": [
            {"name": "Tony Stark", "phones": ["860-000-1111"], "emails": ["tony@stark.com"]}
        ]
    }
    status, _, res = router.handle_request(
        "POST", "/api/v1/contacts/sync", headers, json.dumps(sync_body).encode("utf-8")
    )
    assert status == 200
    assert res["status"] == "ok"
    assert res["stats"]["added"] == 1

    # 8. POST /api/v1/contacts/{id}/delete
    status, _, res = router.handle_request(
        "POST", f"/api/v1/contacts/{cid}/delete", headers, b""
    )
    assert status == 200
    assert res["deleted"] is True
