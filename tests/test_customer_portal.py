"""
Unit and integration tests for Phase B4 Customer Portal endpoints and data isolation:
- Customer profile, project tracking, and milestone visibility
- Financial masking: internal costs & markups masked for customer role
- Digital contract e-signature verification
- Invoices & payment balance tracking
- Document and photo access isolation
- Direct customer portal messaging to communication history
"""

import json
import pytest
from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthService,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    Contract,
    Customer,
    Document,
    Estimate,
    Invoice,
    MilestoneStatus,
    Project,
    ProjectMilestone,
    ProjectStage,
)
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService


@pytest.fixture
def portal_setup():
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    auth = AuthService(db)
    crm = CRMService(db, audit)
    comm = CommunicationService(db)
    scheduling = SchedulingService(db, audit)
    automation = AutomationService(db, audit)
    operations = OperationsService(db, audit)

    # Setup Admin
    admin_u = auth.create_user("admin", "adminpass", "Admin User", "admin@restoricon.com", ROLE_ADMIN)
    admin_token = auth.create_token(admin_u)
    admin_actor = auth.authenticate_token(admin_token)

    # Create Customer 1 (Alice)
    cust1 = crm.create_customer(
        Customer(first_name="Alice", last_name="Vance", email="alice@example.com", phone="555-1111", service_address="101 Pine St"),
        admin_actor,
    )
    alice_u = auth.create_user("alice", "alicepass", "Alice Vance", "alice@example.com", ROLE_CUSTOMER, customer_id=cust1.id)
    alice_token = auth.create_token(alice_u)

    # Create Customer 2 (Bob)
    cust2 = crm.create_customer(
        Customer(first_name="Bob", last_name="Dylan", email="bob@example.com", phone="555-2222", service_address="202 Oak St"),
        admin_actor,
    )
    bob_u = auth.create_user("bob", "bobpass", "Bob Dylan", "bob@example.com", ROLE_CUSTOMER, customer_id=cust2.id)
    bob_token = auth.create_token(bob_u)

    # Create Projects for Alice
    proj1 = crm.create_project(
        Project(
            customer_id=cust1.id,
            title="Alice Kitchen Restoration",
            property_address="101 Pine St",
            project_type="remodel",
            status="in_progress",
            contract_amount=15000.0,
            estimated_cost=8000.0,
            profit=7000.0,
            notes="Internal project manager notes: VIP client",
        ),
        admin_actor,
    )

    # Create Milestone for Alice's Project
    operations.create_milestone(
        ProjectMilestone(
            project_id=proj1.id,
            name="Drywall & Flooring Complete",
            stage=ProjectStage.IN_PROGRESS,
            status=MilestoneStatus.IN_PROGRESS,
            target_date="2026-09-15",
        ),
        admin_actor,
    )

    # Create Estimate for Alice
    est1 = crm.create_estimate(
        Estimate(
            estimate_number="EST-ALICE-001",
            customer_id=cust1.id,
            project_id=proj1.id,
            subtotal=12000.0,
            materials_cost=4000.0,
            labor_cost=3000.0,
            subcontractor_cost=1000.0,
            markup_percent=50.0,
            tax_amount=1000.0,
            total_amount=13000.0,
            notes="Internal supplier discounts apply",
        ),
        admin_actor,
    )

    # Create Contract for Alice
    contract1 = crm.create_contract(
        Contract(
            contract_number="CTR-ALICE-001",
            customer_id=cust1.id,
            project_id=proj1.id,
            estimate_id=est1.id,
            title="Kitchen Remodel Master Agreement",
            content="Standard terms and conditions for kitchen restoration...",
            status="sent",
        ),
        admin_actor,
    )

    # Create Invoice for Alice
    inv1 = crm.create_invoice(
        Invoice(
            invoice_number="INV-ALICE-001",
            customer_id=cust1.id,
            project_id=proj1.id,
            amount=5000.0,
            deposit_amount=1000.0,
            balance_due=4000.0,
            status="partially_paid",
        ),
        admin_actor,
    )

    # Create Document for Alice
    doc1 = crm.create_document(
        Document(
            customer_id=cust1.id,
            project_id=proj1.id,
            document_type="contract",
            title="Signed Kitchen Agreement PDF",
            file_path="/var/docs/alice_agreement.pdf",
        ),
        admin_actor,
    )

    router = APIRouter(
        auth_service=auth,
        crm_service=crm,
        comm_service=comm,
        audit_service=audit,
        scheduling_service=scheduling,
        automation_service=automation,
        operations_service=operations,
    )

    return {
        "router": router,
        "admin_token": admin_token,
        "admin_actor": admin_actor,
        "alice_token": alice_token,
        "bob_token": bob_token,
        "cust1": cust1,
        "cust2": cust2,
        "proj1": proj1,
        "est1": est1,
        "contract1": contract1,
        "inv1": inv1,
        "doc1": doc1,
        "crm": crm,
        "comm": comm,
    }


def test_portal_profile(portal_setup):
    router = portal_setup["router"]
    alice_token = portal_setup["alice_token"]

    headers = {"Authorization": f"Bearer {alice_token}"}
    code, _, data = router.handle_request("GET", "/api/v1/portal/profile", headers, b"")
    assert code == 200
    assert data["profile"]["first_name"] == "Alice"
    assert data["profile"]["last_name"] == "Vance"
    assert data["profile"]["email"] == "alice@example.com"


def test_portal_projects_and_financial_masking(portal_setup):
    router = portal_setup["router"]
    alice_token = portal_setup["alice_token"]
    admin_token = portal_setup["admin_token"]
    proj_id = portal_setup["proj1"].id

    # Alice views her projects
    headers_alice = {"Authorization": f"Bearer {alice_token}"}
    code, _, data = router.handle_request("GET", "/api/v1/portal/projects", headers_alice, b"")
    assert code == 200
    assert len(data["projects"]) == 1
    p = data["projects"][0]
    assert p["title"] == "Alice Kitchen Restoration"
    # Verify financial masking: profit, estimated_cost, actual_cost, and internal notes are masked (0.0 / None)
    assert p["estimated_cost"] == 0.0
    assert p["actual_cost"] == 0.0
    assert p["profit"] == 0.0
    assert p["notes"] is None
    assert p["contract_amount"] == 15000.0  # Public customer-facing contract amount remains visible

    # Admin views project directly: full financial transparency
    headers_admin = {"Authorization": f"Bearer {admin_token}"}
    code, _, admin_data = router.handle_request("GET", f"/api/v1/projects/{proj_id}", headers_admin, b"")
    assert code == 200
    assert admin_data["project"]["estimated_cost"] == 8000.0
    assert admin_data["project"]["profit"] == 7000.0


def test_portal_customer_data_isolation(portal_setup):
    router = portal_setup["router"]
    bob_token = portal_setup["bob_token"]
    proj_id = portal_setup["proj1"].id
    contract_id = portal_setup["contract1"].id

    headers_bob = {"Authorization": f"Bearer {bob_token}"}

    # Bob asks for his projects: should see empty list (none for Bob)
    code, _, data = router.handle_request("GET", "/api/v1/portal/projects", headers_bob, b"")
    assert code == 200
    assert len(data["projects"]) == 0

    # Bob tries to access Alice's project directly: must be forbidden
    code, _, _ = router.handle_request("GET", f"/api/v1/portal/projects/{proj_id}", headers_bob, b"")
    assert code == 403

    # Bob tries to sign Alice's contract: must be forbidden
    body = json.dumps({"signature_data": "Bob Signature"}).encode("utf-8")
    code, _, _ = router.handle_request("POST", f"/api/v1/portal/contracts/{contract_id}/sign", headers_bob, body)
    assert code == 403


def test_portal_contract_e_signature(portal_setup):
    router = portal_setup["router"]
    alice_token = portal_setup["alice_token"]
    contract_id = portal_setup["contract1"].id

    headers = {"Authorization": f"Bearer {alice_token}"}
    body = json.dumps({"signature_data": "data:image/png;base64,iVBORw0KGgo..."}).encode("utf-8")

    code, _, data = router.handle_request("POST", f"/api/v1/portal/contracts/{contract_id}/sign", headers, body)
    assert code == 200
    assert data["contract"]["status"] == "signed"
    assert data["contract"]["customer_signed_at"] is not None


def test_portal_invoices_and_documents(portal_setup):
    router = portal_setup["router"]
    alice_token = portal_setup["alice_token"]
    headers = {"Authorization": f"Bearer {alice_token}"}

    # Invoices
    code, _, data = router.handle_request("GET", "/api/v1/portal/invoices", headers, b"")
    assert code == 200
    assert len(data["invoices"]) == 1
    assert data["invoices"][0]["invoice_number"] == "INV-ALICE-001"
    assert data["invoices"][0]["balance_due"] == 4000.0

    # Documents
    code, _, data = router.handle_request("GET", "/api/v1/portal/documents", headers, b"")
    assert code == 200
    assert len(data["documents"]) == 1
    assert data["documents"][0]["title"] == "Signed Kitchen Agreement PDF"


def test_portal_messaging(portal_setup):
    router = portal_setup["router"]
    alice_token = portal_setup["alice_token"]
    proj_id = portal_setup["proj1"].id

    headers = {"Authorization": f"Bearer {alice_token}"}
    body = json.dumps({
        "subject": "Tile Selection Question",
        "message": "Can we switch to the subway tile for the backsplash?",
        "project_id": proj_id,
    }).encode("utf-8")

    code, _, data = router.handle_request("POST", "/api/v1/portal/messages", headers, body)
    assert code == 201
    assert data["message"]["content"] == "Can we switch to the subway tile for the backsplash?"
    assert data["message"]["channel"] == "web_chat"


def test_portal_messages_no_channel_leak(portal_setup):
    """Regression: non-web_chat records logged by admin/Aigentik must NOT appear
    in GET /api/v1/portal/messages for the customer.

    Before the fix, query_communications() was called with no channel filter,
    so email logs, phone records, SMS, voicemails, and ai_conversation records
    (written by the Aigentik orchestrator) all surfaced in the customer-facing
    'Project Manager Direct Thread' chat widget.
    """
    router = portal_setup["router"]
    comm = portal_setup["comm"]
    admin_actor = portal_setup["admin_actor"]
    alice_token = portal_setup["alice_token"]
    cust1 = portal_setup["cust1"]
    proj_id = portal_setup["proj1"].id

    # Admin (simulating Aigentik or staff) logs several non-web_chat records
    # for Alice that should NEVER appear in her portal thread.
    leaked_channels = ["email", "phone", "sms", "voicemail", "ai_conversation"]
    for ch in leaked_channels:
        comm.record_communication(
            channel=ch,
            direction="inbound",
            content=f"SHOULD NOT LEAK: {ch} record for Alice",
            actor=admin_actor,
            customer_id=cust1.id,
            project_id=proj_id,
        )

    # Alice posts one legitimate web_chat message.
    alice_headers = {"Authorization": f"Bearer {alice_token}"}
    body = json.dumps({"message": "Hello, any update?"}).encode("utf-8")
    code, _, _ = router.handle_request("POST", "/api/v1/portal/messages", alice_headers, body)
    assert code == 201

    # Alice GETs the portal message feed.
    code, _, data = router.handle_request("GET", "/api/v1/portal/messages", alice_headers, b"")
    assert code == 200

    messages = data["messages"]
    # Only Alice's own web_chat message should be present.
    assert len(messages) == 1, (
        f"Expected 1 web_chat message, got {len(messages)}: "
        + str([m.get("channel") for m in messages])
    )
    assert messages[0]["channel"] == "web_chat"
    assert messages[0]["content"] == "Hello, any update?"

    # None of the non-web_chat channels should appear.
    returned_channels = {m["channel"] for m in messages}
    for ch in leaked_channels:
        assert ch not in returned_channels, f"Leaked channel '{ch}' appeared in portal messages"
