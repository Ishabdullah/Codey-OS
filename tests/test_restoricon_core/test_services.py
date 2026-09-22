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
    PERM_READ_TEAM_SALES_DATA,
    PERM_WRITE_CONTRACTS,
    ROLE_ADMIN,
    ROLE_AI_AGENT,
    ROLE_CUSTOMER,
    ROLE_MANAGER,
    ROLE_PROJECT_MANAGER,
    ROLE_SALES,
    ROLE_SALES_MANAGER,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    Contract,
    Customer,
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
    # B8.6d-a: sign_contract now also generates and persists a contract PDF
    # as a Document row (create_document's own audit entry), one more log
    # than before -- 10, not 9.
    assert len(logs) == 10


def test_sign_contract_new192_role_matrix(setup_services):
    # NEW-192: PERM_SIGN_CONTRACTS is granted to admin/manager/sales/
    # project_manager/customer, deliberately withheld from technician and
    # ai_agent. Confirms the grant is real (positive cases) and that the
    # withholding is enforced (negative cases), not just present in the
    # permission table.
    #
    # B8.6a / NEW-573 (2026-09-17): sign_contract now (a) rejects re-signing
    # an already-signed contract (idempotency guard, see
    # test_sign_contract_idempotency_guard below) and (b) requires either
    # PERM_READ_TEAM_SALES_DATA or contract ownership (assigned_user_id ==
    # actor.user_id) from non-customer actors. Each positive case below
    # therefore uses its own freshly-created contract (idempotency), and a
    # non-team-tier actor signs a contract it created itself so it owns it
    # (ownership), rather than repeatedly re-signing one shared,
    # admin-owned contract as this test did pre-B8.6a.
    #
    # NEW-575 (2026-09-22): B8.6a's ownership narrowing above accidentally
    # broke the NEW-192 grant for ROLE_PROJECT_MANAGER, which holds
    # PERM_SIGN_CONTRACTS but neither PERM_READ_TEAM_SALES_DATA nor
    # PERM_WRITE_CONTRACTS -- it could sign nothing (no team-tier bypass,
    # can never own a contract since it can't create one). Fixed by
    # exempting actors that lack PERM_WRITE_CONTRACTS from the ownership
    # check in sign_contract: such an actor can never be an owner anyway,
    # so narrowing by ownership can only ever reject it, not usefully scope
    # it. ROLE_SALES (which holds PERM_WRITE_CONTRACTS) is unaffected --
    # see test_sign_contract_rejects_non_owning_narrowed_actor. The case
    # below now documents the restored (accepted) behavior, not a gap.
    db, auth_service, audit_service, _, crm_service = setup_services

    admin_user = auth_service.create_user(
        username="admin", plain_password="Password123", full_name="Admin", email="admin@test.com", role=ROLE_ADMIN
    )
    actor_admin = AuthContext(user_id=admin_user.id, username="admin", role=ROLE_ADMIN, actor_type="human")

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@example.com"),
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

    def make_contract(number, creating_actor):
        return crm_service.create_contract(
            Contract(contract_number=number, customer_id=cust.id, title="Test Agreement", content="Terms..."),
            creating_actor,
        )

    # Team-tier bypass: manager can sign a contract it doesn't own.
    actor_manager = make_actor(ROLE_MANAGER)
    contract_for_manager = make_contract("CTR-NEW192-MGR", actor_admin)
    signed = crm_service.sign_contract(contract_for_manager.id, "sig-manager", actor_manager)
    assert signed.status == "signed"

    # Ownership path: sales rep signs a contract it created (and thus owns).
    actor_sales = make_actor(ROLE_SALES)
    contract_for_sales = make_contract("CTR-NEW192-SALES", actor_sales)
    signed = crm_service.sign_contract(contract_for_sales.id, "sig-sales", actor_sales)
    assert signed.status == "signed"

    # Admin (team-tier) signing its own contract still succeeds.
    contract_for_admin = make_contract("CTR-NEW192-ADMIN", actor_admin)
    signed = crm_service.sign_contract(contract_for_admin.id, "sig-admin-2", actor_admin)
    assert signed.status == "signed"

    # Customer signing their own contract must also succeed.
    contract_for_customer = make_contract("CTR-NEW192-CUST", actor_admin)
    actor_customer = make_actor(ROLE_CUSTOMER, customer_id=cust.id)
    signed = crm_service.sign_contract(contract_for_customer.id, "sig-customer", actor_customer)
    assert signed.status == "signed"

    # NEW-575: project_manager holds PERM_SIGN_CONTRACTS and, lacking
    # PERM_WRITE_CONTRACTS, is exempt from the ownership narrowing -- it can
    # sign a contract it doesn't own (and never could own).
    actor_pm = make_actor(ROLE_PROJECT_MANAGER)
    contract_for_pm = make_contract("CTR-NEW192-PM", actor_admin)
    signed = crm_service.sign_contract(contract_for_pm.id, "sig-pm", actor_pm)
    assert signed.status == "signed"

    # Negative: technician and ai_agent must still be rejected outright
    # (permission check fires before ownership is even considered).
    contract_for_neg = make_contract("CTR-NEW192-NEG", actor_admin)
    for role in (ROLE_TECHNICIAN, ROLE_AI_AGENT):
        with pytest.raises(PermissionError):
            crm_service.sign_contract(contract_for_neg.id, f"sig-{role}", make_actor(role))


def test_sign_contract_idempotency_guard(setup_services):
    # NEW-573: signing an already-signed contract must be rejected cleanly
    # (ValueError -- mapped to 400 by routes.py's handle_request), not
    # silently re-applied (which would let a contract be re-signed
    # indefinitely and let B8.7's future commission hook double-fire).
    db, auth_service, audit_service, _, crm_service = setup_services
    admin_user = auth_service.create_user(
        username="admin_idem", plain_password="Password123", full_name="Admin", email="admin_idem@test.com", role=ROLE_ADMIN
    )
    actor_admin = AuthContext(user_id=admin_user.id, username="admin_idem", role=ROLE_ADMIN, actor_type="human")
    cust = crm_service.create_customer(
        Customer(first_name="John", last_name="Roe", email="john.roe@example.com"), actor_admin
    )
    contract = crm_service.create_contract(
        Contract(contract_number="CTR-IDEMPOTENT-001", customer_id=cust.id, title="Test", content="Terms..."),
        actor_admin,
    )
    signed = crm_service.sign_contract(contract.id, "sig-1", actor_admin)
    assert signed.status == "signed"

    with pytest.raises(ValueError):
        crm_service.sign_contract(contract.id, "sig-2", actor_admin)


# ==========================================
# B8.6a: Estimates/Contracts RBAC narrowing (NEW-548, NEW-573)
# ==========================================


def _make_scoped_actors(auth_service, crm_service, suffix):
    """Shared setup for the B8.6a scoping tests: a customer plus a rep_a /
    rep_b pair (both ROLE_SALES, so neither holds PERM_READ_TEAM_SALES_DATA)
    and one full-tier actor (ROLE_MANAGER, holds PERM_READ_TEAM_SALES_DATA)."""
    admin_user = auth_service.create_user(
        username=f"admin_{suffix}", plain_password="Password123", full_name="Admin",
        email=f"admin_{suffix}@test.com", role=ROLE_ADMIN,
    )
    actor_admin = AuthContext(user_id=admin_user.id, username=f"admin_{suffix}", role=ROLE_ADMIN, actor_type="human")

    rep_a_user = auth_service.create_user(
        username=f"rep_a_{suffix}", plain_password="Password123", full_name="Rep A",
        email=f"rep_a_{suffix}@test.com", role=ROLE_SALES,
    )
    actor_rep_a = AuthContext(user_id=rep_a_user.id, username=f"rep_a_{suffix}", role=ROLE_SALES, actor_type="human")

    rep_b_user = auth_service.create_user(
        username=f"rep_b_{suffix}", plain_password="Password123", full_name="Rep B",
        email=f"rep_b_{suffix}@test.com", role=ROLE_SALES,
    )
    actor_rep_b = AuthContext(user_id=rep_b_user.id, username=f"rep_b_{suffix}", role=ROLE_SALES, actor_type="human")

    manager_user = auth_service.create_user(
        username=f"manager_{suffix}", plain_password="Password123", full_name="Manager",
        email=f"manager_{suffix}@test.com", role=ROLE_MANAGER,
    )
    actor_manager = AuthContext(user_id=manager_user.id, username=f"manager_{suffix}", role=ROLE_MANAGER, actor_type="human")

    cust = crm_service.create_customer(
        Customer(first_name="Scoped", last_name=suffix, email=f"cust_{suffix}@test.com"), actor_admin
    )
    return actor_admin, actor_rep_a, actor_rep_b, actor_manager, cust


def test_list_and_get_estimates_scoped_by_assigned_user_id(setup_services):
    """A narrowed ROLE_SALES actor's list_estimates/get_estimate only sees
    its own records; PERM_READ_TEAM_SALES_DATA holders see everything."""
    db, auth_service, audit_service, _, crm_service = setup_services
    actor_admin, actor_rep_a, actor_rep_b, actor_manager, cust = _make_scoped_actors(
        auth_service, crm_service, "est"
    )

    est_a = crm_service.create_estimate(
        Estimate(estimate_number="EST-SCOPE-A", customer_id=cust.id, total_amount=1000.0), actor_rep_a
    )
    est_b = crm_service.create_estimate(
        Estimate(estimate_number="EST-SCOPE-B", customer_id=cust.id, total_amount=2000.0), actor_rep_b
    )

    # Narrowed actor sees only its own.
    rep_a_list = crm_service.list_estimates(actor_rep_a)
    assert {e.id for e in rep_a_list} == {est_a.id}

    rep_b_list = crm_service.list_estimates(actor_rep_b)
    assert {e.id for e in rep_b_list} == {est_b.id}

    # Full-tier actor sees both.
    manager_list = crm_service.list_estimates(actor_manager)
    assert {e.id for e in manager_list} == {est_a.id, est_b.id}

    # get_estimate: narrowed actor gets None for the other rep's record, not
    # a PermissionError and not the row -- matches get_lead's not-found shape.
    assert crm_service.get_estimate(est_b.id, actor_rep_a) is None
    assert crm_service.get_estimate(est_a.id, actor_rep_a).id == est_a.id

    # Full-tier actor can get either.
    assert crm_service.get_estimate(est_a.id, actor_manager).id == est_a.id
    assert crm_service.get_estimate(est_b.id, actor_manager).id == est_b.id


def test_list_and_get_contracts_scoped_by_assigned_user_id(setup_services):
    """Same scoping as estimates, for contracts."""
    db, auth_service, audit_service, _, crm_service = setup_services
    actor_admin, actor_rep_a, actor_rep_b, actor_manager, cust = _make_scoped_actors(
        auth_service, crm_service, "contract"
    )

    contract_a = crm_service.create_contract(
        Contract(contract_number="CTR-SCOPE-A", customer_id=cust.id, title="A", content="Terms A"), actor_rep_a
    )
    contract_b = crm_service.create_contract(
        Contract(contract_number="CTR-SCOPE-B", customer_id=cust.id, title="B", content="Terms B"), actor_rep_b
    )

    rep_a_list = crm_service.list_contracts(actor_rep_a)
    assert {c.id for c in rep_a_list} == {contract_a.id}

    rep_b_list = crm_service.list_contracts(actor_rep_b)
    assert {c.id for c in rep_b_list} == {contract_b.id}

    manager_list = crm_service.list_contracts(actor_manager)
    assert {c.id for c in manager_list} == {contract_a.id, contract_b.id}

    assert crm_service.get_contract(contract_b.id, actor_rep_a) is None
    assert crm_service.get_contract(contract_a.id, actor_rep_a).id == contract_a.id

    assert crm_service.get_contract(contract_a.id, actor_manager).id == contract_a.id
    assert crm_service.get_contract(contract_b.id, actor_manager).id == contract_b.id


def test_create_estimate_and_contract_ignore_client_supplied_assigned_user_id(setup_services):
    """A client-supplied assigned_user_id in the create payload must be
    ignored/overwritten -- the created record's assigned_user_id is always
    the real actor's id, never an attacker-supplied one (same fail-open
    shape NEW-546 was closed for)."""
    db, auth_service, audit_service, _, crm_service = setup_services
    actor_admin, actor_rep_a, actor_rep_b, _actor_manager, cust = _make_scoped_actors(
        auth_service, crm_service, "splat"
    )

    # actor_rep_a attempts to create an estimate/contract pre-assigned to
    # actor_rep_b -- this is exactly what routes.py's `Estimate(**json_body)`
    # / `Contract(**json_body)` would do with a malicious client body.
    est = crm_service.create_estimate(
        Estimate(
            estimate_number="EST-SPLAT",
            customer_id=cust.id,
            total_amount=500.0,
            assigned_user_id=actor_rep_b.user_id,
        ),
        actor_rep_a,
    )
    assert est.assigned_user_id == actor_rep_a.user_id
    assert est.assigned_user_id != actor_rep_b.user_id

    contract = crm_service.create_contract(
        Contract(
            contract_number="CTR-SPLAT",
            customer_id=cust.id,
            title="Splat",
            content="Terms",
            assigned_user_id=actor_rep_b.user_id,
        ),
        actor_rep_a,
    )
    assert contract.assigned_user_id == actor_rep_a.user_id
    assert contract.assigned_user_id != actor_rep_b.user_id


def test_sign_contract_rejects_non_owning_narrowed_actor(setup_services):
    """NEW-573: a narrowed actor (no PERM_READ_TEAM_SALES_DATA) who doesn't
    own the contract must be rejected, not able to sign it just by knowing
    its id."""
    db, auth_service, audit_service, _, crm_service = setup_services
    actor_admin, actor_rep_a, actor_rep_b, actor_manager, cust = _make_scoped_actors(
        auth_service, crm_service, "signown"
    )

    contract_a = crm_service.create_contract(
        Contract(contract_number="CTR-SIGNOWN-A", customer_id=cust.id, title="A", content="Terms A"), actor_rep_a
    )

    # rep_b doesn't own contract_a and lacks PERM_READ_TEAM_SALES_DATA.
    with pytest.raises(PermissionError):
        crm_service.sign_contract(contract_a.id, "sig-rep-b", actor_rep_b)

    # rep_a (the owner) can sign it.
    signed = crm_service.sign_contract(contract_a.id, "sig-rep-a", actor_rep_a)
    assert signed.status == "signed"

    # A full-tier actor (PERM_READ_TEAM_SALES_DATA) can sign someone else's
    # contract -- but not this one twice (idempotency guard), so use a fresh
    # one owned by rep_b.
    contract_b = crm_service.create_contract(
        Contract(contract_number="CTR-SIGNOWN-B", customer_id=cust.id, title="B", content="Terms B"), actor_rep_b
    )
    signed_by_manager = crm_service.sign_contract(contract_b.id, "sig-manager", actor_manager)
    assert signed_by_manager.status == "signed"


def test_sign_contract_pm_ownership_bypass_local_to_signing(setup_services):
    """NEW-575: the ownership-narrowing bypass added to sign_contract for
    actors lacking PERM_WRITE_CONTRACTS (e.g. ROLE_PROJECT_MANAGER) is local
    to sign_contract only -- it must NOT also widen get_contract/
    list_contracts visibility. A PM must still be unable to see a contract
    it doesn't own via those two read paths, confirming the fix didn't leak
    into general contract visibility."""
    db, auth_service, audit_service, _, crm_service = setup_services
    actor_admin, actor_rep_a, actor_rep_b, actor_manager, cust = _make_scoped_actors(
        auth_service, crm_service, "pmvis"
    )

    pm_user = auth_service.create_user(
        username="pm_pmvis", plain_password="Password123", full_name="PM",
        email="pm_pmvis@test.com", role=ROLE_PROJECT_MANAGER,
    )
    actor_pm = AuthContext(user_id=pm_user.id, username="pm_pmvis", role=ROLE_PROJECT_MANAGER, actor_type="human")
    assert not actor_pm.has_permission(PERM_READ_TEAM_SALES_DATA)
    assert not actor_pm.has_permission(PERM_WRITE_CONTRACTS)

    contract_a = crm_service.create_contract(
        Contract(contract_number="CTR-PMVIS-A", customer_id=cust.id, title="A", content="Terms A"), actor_rep_a
    )

    # get_contract: not owned by the PM -> not-found (same narrowing shape
    # as get_estimate/get_lead), unchanged by the sign_contract fix.
    assert crm_service.get_contract(contract_a.id, actor_pm) is None

    # list_contracts: contract_a must not appear for the PM.
    contract_ids = {c.id for c in crm_service.list_contracts(actor_pm)}
    assert contract_a.id not in contract_ids

    # But sign_contract itself is exempted (NEW-575) -- the PM can still
    # sign it despite not owning/seeing it via the read paths.
    signed = crm_service.sign_contract(contract_a.id, "sig-pm-vis", actor_pm)
    assert signed.status == "signed"


def test_estimates_contracts_full_tier_actors_see_everything(setup_services):
    """Regression: ROLE_ADMIN/ROLE_MANAGER/ROLE_SALES_MANAGER/ROLE_AI_AGENT
    (the roles that actually hold PERM_READ_TEAM_SALES_DATA by default in
    auth.py's ROLE_PERMISSIONS matrix) see every rep's estimates/contracts
    unscoped -- this round did not accidentally narrow the full-tier path.

    NOTE: the B8.6a task description named ROLE_PROJECT_MANAGER as a
    full-tier role for this regression check. Verified directly against
    auth.py's ROLE_PERMISSIONS (not assumed from the task description, per
    project rule 12): ROLE_PROJECT_MANAGER does NOT hold
    PERM_READ_TEAM_SALES_DATA in this codebase (only ROLE_ADMIN,
    ROLE_MANAGER, ROLE_AI_AGENT, and the derived ROLE_SALES_MANAGER do), so
    it is deliberately excluded from this regression list rather than
    asserted incorrectly. Note this is about general contract
    visibility (get_contract/list_contracts), which is unaffected by
    NEW-575: that fix only restored PROJECT_MANAGER's ability to sign a
    contract it doesn't own, not team-wide visibility -- see
    test_sign_contract_pm_ownership_bypass_local_to_signing.
    """
    db, auth_service, audit_service, _, crm_service = setup_services
    actor_admin, actor_rep_a, actor_rep_b, actor_manager, cust = _make_scoped_actors(
        auth_service, crm_service, "fulltier"
    )

    sales_mgr_user = auth_service.create_user(
        username="sales_mgr_fulltier", plain_password="Password123", full_name="Sales Manager",
        email="sales_mgr_fulltier@test.com", role=ROLE_SALES_MANAGER,
    )
    actor_sales_mgr = AuthContext(
        user_id=sales_mgr_user.id, username="sales_mgr_fulltier", role=ROLE_SALES_MANAGER, actor_type="human"
    )
    agent_user = auth_service.create_user(
        username="agent_fulltier", plain_password="Password123", full_name="Agent",
        email="agent_fulltier@test.com", role=ROLE_AI_AGENT,
    )
    actor_agent = AuthContext(user_id=agent_user.id, username="agent_fulltier", role=ROLE_AI_AGENT, actor_type="agent")

    for actor in (actor_admin, actor_manager, actor_sales_mgr, actor_agent):
        assert actor.has_permission(PERM_READ_TEAM_SALES_DATA)

    est_a = crm_service.create_estimate(
        Estimate(estimate_number="EST-FULLTIER-A", customer_id=cust.id, total_amount=100.0), actor_rep_a
    )
    est_b = crm_service.create_estimate(
        Estimate(estimate_number="EST-FULLTIER-B", customer_id=cust.id, total_amount=200.0), actor_rep_b
    )
    contract_a = crm_service.create_contract(
        Contract(contract_number="CTR-FULLTIER-A", customer_id=cust.id, title="A", content="Terms A"), actor_rep_a
    )
    contract_b = crm_service.create_contract(
        Contract(contract_number="CTR-FULLTIER-B", customer_id=cust.id, title="B", content="Terms B"), actor_rep_b
    )

    for actor in (actor_admin, actor_manager, actor_sales_mgr, actor_agent):
        est_ids = {e.id for e in crm_service.list_estimates(actor)}
        assert est_ids == {est_a.id, est_b.id}, f"{actor.role} did not see all estimates"
        contract_ids = {c.id for c in crm_service.list_contracts(actor)}
        assert contract_ids == {contract_a.id, contract_b.id}, f"{actor.role} did not see all contracts"
        assert crm_service.get_estimate(est_a.id, actor) is not None
        assert crm_service.get_estimate(est_b.id, actor) is not None
        assert crm_service.get_contract(contract_a.id, actor) is not None
        assert crm_service.get_contract(contract_b.id, actor) is not None


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


def test_get_customer_by_external_id_rejects_mismatched_customer_actor(setup_services):
    """NEW-248: the redundant top-level PERM_READ_ALL_CUSTOMERS gate was
    removed -- get_customer_by_external_id now delegates authorization
    entirely to get_customer()'s row-scoped `can_access_customer` check,
    matching get_customer's own pattern. A customer-role actor whose
    customer_id doesn't match the resolved row is still rejected; the
    internal ID-resolution SELECT itself is ungated (it discloses nothing
    beyond a boolean "does this external_id exist")."""
    db, auth_service, audit_service, _, crm_service = setup_services
    admin_user = auth_service.create_user(
        username="admin", plain_password="Password123", full_name="Admin", email="admin@test.com", role=ROLE_ADMIN
    )
    actor_admin = AuthContext(user_id=admin_user.id, username="admin", role=ROLE_ADMIN, actor_type="human")

    created = crm_service.create_customer(
        Customer(external_id="contact_0197", first_name="Jane", last_name="Doe"), actor_admin
    )

    # A customer-role actor tied to a DIFFERENT customer_id must be denied
    # access to this row, exactly like get_customer() already enforces.
    mismatched_customer_actor = AuthContext(
        user_id=999, username="other_customer", role=ROLE_CUSTOMER,
        actor_type="human", customer_id=created.id + 1,
    )
    with pytest.raises(PermissionError):
        crm_service.get_customer_by_external_id("contact_0197", mismatched_customer_actor)

    # A nonexistent external_id resolves to no row before any permission
    # check runs -- returns None, not a PermissionError.
    assert crm_service.get_customer_by_external_id("does_not_exist", mismatched_customer_actor) is None


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
