"""
Unit tests for CRM, Audit Log, and Communication History services.
Verifies append-only invariants, entity lifecycles, and audit logging by humans & agents.
"""

import pytest
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_AI_AGENT,
    ROLE_CUSTOMER,
    ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    Contract,
    Customer,
    Document,
    Estimate,
    Invoice,
    Lead,
    Opportunity,
    Project,
)
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService


@pytest.fixture
def setup_services():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    comm_service = CommunicationService(db)
    crm_service = CRMService(db, audit_service)
    return db, auth_service, audit_service, comm_service, crm_service


def test_append_only_audit_log(setup_services):
    db, auth_service, audit_service, _, _ = setup_services

    # Create real users for foreign key integrity
    human_user = auth_service.create_user(
        username="admin", plain_password="Password123", full_name="Admin", email="admin@test.com", role=ROLE_ADMIN
    )
    agent_user = auth_service.create_user(
        username="aigentik", plain_password="Password123", full_name="Aigentik", email="agent@test.com", role=ROLE_AI_AGENT
    )

    actor_human = AuthContext(user_id=human_user.id, username="admin", role=ROLE_ADMIN, actor_type="human")
    actor_agent = AuthContext(user_id=agent_user.id, username="aigentik", role=ROLE_AI_AGENT, actor_type="agent")

    # Log action by human
    rec1 = audit_service.log(
        action="create",
        entity_type="customer",
        entity_id=10,
        change_summary="Admin created customer 10",
        actor=actor_human,
        details={"source": "direct"},
    )
    assert rec1.id is not None
    assert rec1.actor_type == "human"

    # Log action by AI agent
    rec2 = audit_service.log(
        action="update",
        entity_type="opportunity",
        entity_id=5,
        change_summary="Aigentik moved opportunity 5 to Proposal Sent",
        actor=actor_agent,
        details={"pipeline_stage": "Proposal Sent"},
    )
    assert rec2.id is not None
    assert rec2.actor_type == "agent"

    # Query audit logs
    logs = audit_service.query_logs(actor_human)
    assert len(logs) == 2
    assert logs[0].id == rec2.id  # Most recent first
    assert logs[1].id == rec1.id


def test_append_only_communication_history(setup_services):
    db, auth_service, _, comm_service, crm_service = setup_services

    agent_user = auth_service.create_user(
        username="aigentik", plain_password="Password123", full_name="Aigentik", email="agent@test.com", role=ROLE_AI_AGENT
    )
    actor_agent = AuthContext(user_id=agent_user.id, username="aigentik", role=ROLE_AI_AGENT, actor_type="agent")

    # Create customer record first
    cust = crm_service.create_customer(
        Customer(first_name="Mary", last_name="Johnson", email="mary@test.com"),
        actor_agent,
    )
    cust_user = auth_service.create_user(
        username="mary", plain_password="Password123", full_name="Mary Johnson", email="mary@test.com", role=ROLE_CUSTOMER, customer_id=cust.id
    )
    actor_cust = AuthContext(user_id=cust_user.id, username="mary", role=ROLE_CUSTOMER, actor_type="human", customer_id=cust.id)

    # Agent records automated email
    comm1 = comm_service.record_communication(
        channel="email",
        direction="outbound",
        content="Hello Mary, here is your project status update.",
        actor=actor_agent,
        subject="Project Update",
        customer_id=cust.id,
    )
    assert comm1.id is not None
    assert comm1.actor_type == "agent"

    # Customer records web chat message
    comm2 = comm_service.record_communication(
        channel="web_chat",
        direction="inbound",
        content="Thank you! When will the framing start?",
        actor=actor_cust,
        customer_id=cust.id,
    )
    assert comm2.id is not None
    assert comm2.actor_type == "human"

    # Customer queries communications (should only see own)
    cust_comms = comm_service.query_communications(actor_cust)
    assert len(cust_comms) == 2

    # Verify customer cannot record internal notes
    with pytest.raises(PermissionError):
        comm_service.record_communication(
            channel="internal_note",
            direction="internal",
            content="Internal note attempt",
            actor=actor_cust,
            customer_id=cust.id,
        )


def test_crm_entity_lifecycle_with_audit_trail(setup_services):
    db, auth_service, audit_service, _, crm_service = setup_services

    sales_user = auth_service.create_user(
        username="sales_rep", plain_password="Password123", full_name="Sales Guy", email="sales@test.com", role=ROLE_SALES
    )
    admin_user = auth_service.create_user(
        username="admin", plain_password="Password123", full_name="Admin Boss", email="admin@test.com", role=ROLE_ADMIN
    )

    actor_sales = AuthContext(user_id=sales_user.id, username="sales_rep", role=ROLE_SALES, actor_type="human")
    actor_admin = AuthContext(user_id=admin_user.id, username="admin", role=ROLE_ADMIN, actor_type="human")

    # 1. Create Customer
    customer = Customer(
        first_name="Jane",
        last_name="Doe",
        company_name="Doe Enterprises",
        phone="860-555-0199",
        email="jane.doe@example.com",
        service_address="45 Farmington Ave, Hartford, CT",
    )
    created_cust = crm_service.create_customer(customer, actor_sales)
    assert created_cust.id is not None

    # 2. Create Lead
    lead = Lead(
        customer_id=created_cust.id,
        source="Google Ads",
        status="new",
        estimated_value=25000.0,
    )
    created_lead = crm_service.create_lead(lead, actor_sales)
    assert created_lead.id is not None

    # 3. Create Opportunity
    opp = Opportunity(
        customer_id=created_cust.id,
        title="Kitchen & Living Room Remodel",
        estimated_value=25000.0,
        pipeline_stage="New Lead",
    )
    created_opp = crm_service.create_opportunity(opp, actor_sales)
    assert created_opp.id is not None

    # 4. Create Project (Admin or Project Manager creates projects)
    proj = Project(
        customer_id=created_cust.id,
        title="Doe Residence Kitchen Remodel",
        property_address="45 Farmington Ave, Hartford, CT",
        project_type="remodel",
        contract_amount=25000.0,
    )
    created_proj = crm_service.create_project(proj, actor_admin)
    assert created_proj.id is not None

    # 5. Create Estimate
    est = Estimate(
        estimate_number="EST-2026-001",
        customer_id=created_cust.id,
        project_id=created_proj.id,
        total_amount=25000.0,
        line_items=[{"desc": "Cabinetry & Countertops", "cost": 15000.0}, {"desc": "Labor", "cost": 10000.0}],
    )
    created_est = crm_service.create_estimate(est, actor_sales)
    assert created_est.id is not None

    # 6. Create & Sign Contract
    contract = Contract(
        contract_number="CTR-2026-001",
        customer_id=created_cust.id,
        project_id=created_proj.id,
        estimate_id=created_est.id,
        title="Restoricon Remodeling Agreement",
        content="Full remodeling agreement terms...",
    )
    created_contract = crm_service.create_contract(contract, actor_sales)
    assert created_contract.id is not None

    # Customer user created and signs contract
    cust_user = auth_service.create_user(
        username="jane_doe",
        plain_password="Password123",
        full_name="Jane Doe",
        email="jane.doe@example.com",
        role=ROLE_CUSTOMER,
        customer_id=created_cust.id,
    )
    actor_cust = AuthContext(
        user_id=cust_user.id, username="jane_doe", role=ROLE_CUSTOMER, actor_type="human", customer_id=created_cust.id
    )
    signed_contract = crm_service.sign_contract(created_contract.id, "JaneDoeSignatureDataHash", actor_cust)
    assert signed_contract.status == "signed"
    assert signed_contract.customer_signature_data == "JaneDoeSignatureDataHash"

    # 7. Create Invoice & Record Payment
    inv = Invoice(
        invoice_number="INV-2026-001",
        customer_id=created_cust.id,
        project_id=created_proj.id,
        amount=25000.0,
        deposit_amount=5000.0,
    )
    created_inv = crm_service.create_invoice(inv, actor_admin)
    assert created_inv.balance_due == 20000.0

    # Record partial payment
    updated_inv = crm_service.record_payment(
        invoice_id=created_inv.id,
        payment_amount=10000.0,
        payment_method="check",
        transaction_reference="CHK-9812",
        actor=actor_admin,
    )
    assert updated_inv.status == "partially_paid"
    assert updated_inv.balance_due == 10000.0

    # 8. Verify comprehensive audit trail
    logs = audit_service.query_logs(actor_admin)
    # We should have audit logs for: create customer, create lead, create opp, create proj, create est, create contract, sign contract, create invoice, pay invoice
    assert len(logs) == 9
