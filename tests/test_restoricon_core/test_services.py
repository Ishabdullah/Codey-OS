"""
Unit tests for CRM, Audit Log, and Communication History services.
Verifies append-only invariants, entity lifecycles, and audit logging by humans & agents.
"""

import pytest
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_LOG_COMMUNICATION,
    PERM_READ_COMMUNICATIONS,
    ROLE_ADMIN,
    ROLE_AI_AGENT,
    ROLE_CUSTOMER,
    ROLE_MANAGER,
    ROLE_PROJECT_MANAGER,
    ROLE_SALES,
    ROLE_TECHNICIAN,
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


def test_communication_provider_message_id_dedup(setup_services):
    """NEW-233: a reprocessed or retried write-through call carrying the
    same provider_message_id must not create a duplicate row -- this is
    the mechanism that makes the comms log safe against
    email-provider.js's documented \\Seen-flag reprocessing race."""
    db, auth_service, _, comm_service, crm_service = setup_services

    agent_user = auth_service.create_user(
        username="aigentik", plain_password="Password123", full_name="Aigentik", email="agent@test.com", role=ROLE_AI_AGENT
    )
    actor_agent = AuthContext(user_id=agent_user.id, username="aigentik", role=ROLE_AI_AGENT, actor_type="agent")

    first = comm_service.record_communication(
        channel="email",
        direction="inbound",
        content="Original message body",
        actor=actor_agent,
        provider_message_id="<abc123@mail.gmail.com>",
    )
    # Same provider_message_id, reprocessed with (deliberately) different
    # content -- simulates a reprocess race, not just a byte-identical retry.
    duplicate = comm_service.record_communication(
        channel="email",
        direction="inbound",
        content="Reprocessed duplicate body",
        actor=actor_agent,
        provider_message_id="<abc123@mail.gmail.com>",
    )
    assert duplicate.id == first.id
    assert duplicate.content == "Original message body"  # unchanged, not overwritten

    all_comms = comm_service.query_communications(actor_agent)
    assert len(all_comms) == 1


def test_customer_role_cannot_use_provider_message_id_to_read_another_customers_row(setup_services):
    """A customer-role caller must never be able to supply a
    provider_message_id that collides with an existing row belonging to
    a DIFFERENT customer and have that row's content returned to them --
    message ids are observable by anyone who received the mail, so this
    isn't purely theoretical. provider_message_id is dropped entirely
    for ROLE_CUSTOMER before the insert/conflict logic runs."""
    db, auth_service, _, comm_service, crm_service = setup_services

    agent_user = auth_service.create_user(
        username="aigentik", plain_password="Password123", full_name="Aigentik", email="agent@test.com", role=ROLE_AI_AGENT
    )
    actor_agent = AuthContext(user_id=agent_user.id, username="aigentik", role=ROLE_AI_AGENT, actor_type="agent")

    cust_a = crm_service.create_customer(
        Customer(first_name="Alice", last_name="Adams", email="alice@test.com"), actor_agent
    )
    cust_b = crm_service.create_customer(
        Customer(first_name="Bob", last_name="Brown", email="bob@test.com"), actor_agent
    )
    user_b = auth_service.create_user(
        username="bob", plain_password="Password123", full_name="Bob Brown", email="bob@test.com",
        role=ROLE_CUSTOMER, customer_id=cust_b.id,
    )
    actor_b = AuthContext(user_id=user_b.id, username="bob", role=ROLE_CUSTOMER, actor_type="human", customer_id=cust_b.id)

    # Agent logs a real row for customer A with a real provider_message_id
    private_row = comm_service.record_communication(
        channel="email",
        direction="inbound",
        content="Alice's private message content",
        actor=actor_agent,
        customer_id=cust_a.id,
        provider_message_id="<shared-observable-id@mail.gmail.com>",
    )

    # Customer B (a different customer) tries to log their own communication
    # while supplying the SAME provider_message_id -- must not return
    # Alice's row or her content.
    result = comm_service.record_communication(
        channel="web_chat",
        direction="inbound",
        content="Bob's own message",
        actor=actor_b,
        provider_message_id="<shared-observable-id@mail.gmail.com>",
    )
    assert result.id != private_row.id
    assert result.content == "Bob's own message"
    assert result.customer_id == cust_b.id
    assert result.provider_message_id is None


def test_technician_cannot_use_provider_message_id_to_read_another_customers_row(setup_services):
    """NEW-257 regression: ROLE_TECHNICIAN holds PERM_LOG_COMMUNICATION
    (can write) but NOT PERM_READ_COMMUNICATIONS (cannot read) -- the
    original fix only stripped provider_message_id for ROLE_CUSTOMER, so
    a technician POSTing a communication with a guessed/observed
    provider_message_id could hit the dedup-conflict path and get back
    another customer's full private communication content, subject, and
    customer_id, despite lacking any read permission at all. The strip
    must be gated on the PERM_READ_COMMUNICATIONS permission itself, not
    on which role happened to prompt the original fix."""
    db, auth_service, _, comm_service, crm_service = setup_services

    agent_user = auth_service.create_user(
        username="aigentik2", plain_password="Password123", full_name="Aigentik", email="agent2@test.com", role=ROLE_AI_AGENT
    )
    actor_agent = AuthContext(user_id=agent_user.id, username="aigentik2", role=ROLE_AI_AGENT, actor_type="agent")

    cust_a = crm_service.create_customer(
        Customer(first_name="Carol", last_name="Cross", email="carol@test.com"), actor_agent
    )

    tech_user = auth_service.create_user(
        username="tim", plain_password="Password123", full_name="Tim Tech", email="tim@test.com", role=ROLE_TECHNICIAN
    )
    actor_tech = AuthContext(user_id=tech_user.id, username="tim", role=ROLE_TECHNICIAN, actor_type="human")

    assert actor_tech.has_permission(PERM_LOG_COMMUNICATION)
    assert not actor_tech.has_permission(PERM_READ_COMMUNICATIONS)

    # Agent logs a real, private row for customer A with a real
    # provider_message_id -- content/subject a technician has no
    # business ever seeing.
    private_row = comm_service.record_communication(
        channel="email",
        direction="inbound",
        content="Carol's private message content",
        actor=actor_agent,
        subject="Carol's private subject",
        customer_id=cust_a.id,
        provider_message_id="<tech-guessable-id@mail.gmail.com>",
    )

    # Technician logs their own communication while supplying the SAME
    # provider_message_id -- must not return Carol's row, content,
    # subject, or customer_id.
    result = comm_service.record_communication(
        channel="phone",
        direction="outbound",
        content="Technician's own call note",
        actor=actor_tech,
        provider_message_id="<tech-guessable-id@mail.gmail.com>",
    )
    assert result.id != private_row.id
    assert result.content == "Technician's own call note"
    assert result.subject != "Carol's private subject"
    assert result.customer_id != cust_a.id
    assert result.provider_message_id is None


def test_communication_provider_message_id_blank_never_dedups(setup_services):
    """A blank/whitespace-only provider_message_id must be normalized to
    NULL, not treated as a real duplicate-eligible value -- SQLite's
    partial unique index only excludes NULL, not empty string, so this
    normalization is the only thing standing between a headerless
    message and every subsequent headerless message being silently
    swallowed as a 'duplicate' of the first."""
    db, auth_service, _, comm_service, crm_service = setup_services

    agent_user = auth_service.create_user(
        username="aigentik", plain_password="Password123", full_name="Aigentik", email="agent@test.com", role=ROLE_AI_AGENT
    )
    actor_agent = AuthContext(user_id=agent_user.id, username="aigentik", role=ROLE_AI_AGENT, actor_type="agent")

    for provider_id in ("", "   ", None):
        comm_service.record_communication(
            channel="email",
            direction="inbound",
            content=f"Message with provider_message_id={provider_id!r}",
            actor=actor_agent,
            provider_message_id=provider_id,
        )

    all_comms = comm_service.query_communications(actor_agent)
    assert len(all_comms) == 3
    assert all(c.provider_message_id is None for c in all_comms)


def test_get_customer_by_email_resolution(setup_services):
    """NEW-233: resolving an inbound message's sender address to a
    customer_id must return None on zero OR 2+ matches, not guess --
    customers.email has no UNIQUE constraint, so ambiguity is a real
    possibility with migrated production data."""
    db, auth_service, _, comm_service, crm_service = setup_services

    agent_user = auth_service.create_user(
        username="aigentik", plain_password="Password123", full_name="Aigentik", email="agent@test.com", role=ROLE_AI_AGENT
    )
    actor_agent = AuthContext(user_id=agent_user.id, username="aigentik", role=ROLE_AI_AGENT, actor_type="agent")

    cust = crm_service.create_customer(
        Customer(first_name="Mary", last_name="Johnson", email="mary@test.com"),
        actor_agent,
    )

    # Unique match
    resolved = crm_service.get_customer_by_email("mary@test.com", actor_agent)
    assert resolved is not None
    assert resolved.id == cust.id

    # Case-insensitive match (customers.email is COLLATE NOCASE)
    resolved_ci = crm_service.get_customer_by_email("MARY@TEST.COM", actor_agent)
    assert resolved_ci is not None
    assert resolved_ci.id == cust.id

    # No match
    assert crm_service.get_customer_by_email("nobody@test.com", actor_agent) is None

    # Ambiguous match (2+ customers share an email) resolves to None
    crm_service.create_customer(
        Customer(first_name="Mary", last_name="Smith", email="mary@test.com"),
        actor_agent,
    )
    assert crm_service.get_customer_by_email("mary@test.com", actor_agent) is None


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


def test_sign_contract_new192_role_matrix(setup_services):
    # NEW-192: PERM_SIGN_CONTRACTS is granted to admin/manager/sales/
    # project_manager/customer, deliberately withheld from technician and
    # ai_agent. Confirms the grant is real (positive cases) and that the
    # withholding is enforced (negative cases), not just present in the
    # permission table.
    db, auth_service, audit_service, _, crm_service = setup_services

    admin_user = auth_service.create_user(
        username="admin", plain_password="Password123", full_name="Admin", email="admin@test.com", role=ROLE_ADMIN
    )
    actor_admin = AuthContext(user_id=admin_user.id, username="admin", role=ROLE_ADMIN, actor_type="human")

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@example.com"),
        actor_admin,
    )
    contract = crm_service.create_contract(
        Contract(
            contract_number="CTR-NEW192-001",
            customer_id=cust.id,
            title="Test Agreement",
            content="Terms...",
        ),
        actor_admin,
    )

    def make_actor(role, **kwargs):
        user = auth_service.create_user(
            username=f"user_{role}",
            plain_password="Password123",
            full_name=f"Test {role}",
            email=f"{role}@test.com",
            role=role,
            **kwargs,
        )
        return AuthContext(user_id=user.id, username=f"user_{role}", role=role, actor_type="human", **kwargs)

    # Positive: each of these roles must be able to sign.
    for role in (ROLE_MANAGER, ROLE_SALES, ROLE_PROJECT_MANAGER):
        signed = crm_service.sign_contract(contract.id, f"sig-{role}", make_actor(role))
        assert signed.status == "signed"
    signed = crm_service.sign_contract(contract.id, "sig-admin-2", actor_admin)
    assert signed.status == "signed"

    # Customer signing their own contract must also succeed.
    signed = crm_service.sign_contract(
        contract.id, "sig-customer", make_actor(ROLE_CUSTOMER, customer_id=cust.id)
    )
    assert signed.status == "signed"

    # Negative: technician and ai_agent must still be rejected.
    for role in (ROLE_TECHNICIAN, ROLE_AI_AGENT):
        with pytest.raises(PermissionError):
            crm_service.sign_contract(contract.id, f"sig-{role}", make_actor(role))


# ==========================================
# CUSTOMER/LEAD external_id (NEW-212/NEW-232, 2026-08-27)
# ==========================================


def test_get_customer_by_external_id(setup_services):
    db, auth_service, audit_service, _, crm_service = setup_services
    admin_user = auth_service.create_user(
        username="admin", plain_password="Password123", full_name="Admin", email="admin@test.com", role=ROLE_ADMIN
    )
    actor_admin = AuthContext(user_id=admin_user.id, username="admin", role=ROLE_ADMIN, actor_type="human")

    created = crm_service.create_customer(
        Customer(external_id="contact_0197", first_name="Jane", last_name="Doe"), actor_admin
    )
    assert created.external_id == "contact_0197"

    fetched = crm_service.get_customer_by_external_id("contact_0197", actor_admin)
    assert fetched is not None
    assert fetched.id == created.id

    assert crm_service.get_customer_by_external_id("does_not_exist", actor_admin) is None

    # Uniqueness is enforced at the DB layer -- inserting a second customer
    # with the same external_id must fail.
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        crm_service.create_customer(
            Customer(external_id="contact_0197", first_name="Other", last_name="Person"), actor_admin
        )


def test_get_customer_by_external_id_rejects_zero_permission_actor(setup_services):
    _, _, _, _, crm_service = setup_services

    class ZeroPermissionActor:
        role = "nobody"

        def has_permission(self, permission: str) -> bool:
            return False

    with pytest.raises(PermissionError):
        crm_service.get_customer_by_external_id("contact_0197", ZeroPermissionActor())


def test_get_lead_by_external_id(setup_services):
    db, auth_service, audit_service, _, crm_service = setup_services
    admin_user = auth_service.create_user(
        username="admin", plain_password="Password123", full_name="Admin", email="admin@test.com", role=ROLE_ADMIN
    )
    actor_admin = AuthContext(user_id=admin_user.id, username="admin", role=ROLE_ADMIN, actor_type="human")

    created = crm_service.create_lead(
        Lead(external_id="lead_0042", source="referral"), actor_admin
    )
    assert created.external_id == "lead_0042"

    fetched = crm_service.get_lead_by_external_id("lead_0042", actor_admin)
    assert fetched is not None
    assert fetched.id == created.id

    assert crm_service.get_lead_by_external_id("does_not_exist", actor_admin) is None


def test_get_lead_by_external_id_rejects_zero_permission_actor(setup_services):
    _, _, _, _, crm_service = setup_services

    class ZeroPermissionActor:
        role = "nobody"

        def has_permission(self, permission: str) -> bool:
            return False

    with pytest.raises(PermissionError):
        crm_service.get_lead_by_external_id("lead_0042", ZeroPermissionActor())
