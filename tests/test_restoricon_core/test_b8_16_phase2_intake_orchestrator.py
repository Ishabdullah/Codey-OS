"""
Unit tests for B8.16 Phase 2 (work-order intake pipeline service-layer
orchestrator, Ish-driven 2026-09-26/27; see CODEY_MASTER_PLAN.md's B8.16
entry for full phase history). Covers:

  - CRMService.submit_work_order_intake: customer find-or-create with the
    conjunctive, false-merge-safe dedup (exact email OR normalized-phone-
    AND-last-name, never phone-alone; ambiguity always creates new);
    Customer.assigned_user_id set explicitly from salesperson_user_id, not
    inherited from the actor; project find-or-create keyed on
    customer_id + property_address using the real ProjectStage.INTAKE
    enum value; work order + invoice creation under a scoped system
    actor so ROLE_TECHNICIAN/ROLE_SUBCONTRACTOR (neither of which holds
    PERM_WRITE_CUSTOMERS/PERM_WRITE_PROJECTS/PERM_WRITE_FINANCIALS) can
    still call the orchestrator end-to-end; the outer audit entry
    attributed to the real submitting actor, not the system actor.
  - The commission trigger widening in record_payment: fires on a paid
    invoice_type='project' invoice now, not just 'assessment'; unchanged
    for 'assessment'; still does not fire for 'subscription'/'other'.
"""

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_READ_AUDIT_LOG,
    ROLE_ADMIN,
    ROLE_SALES,
    ROLE_SUBCONTRACTOR,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Invoice, ProjectStage
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.commission_service import CommissionService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.operations_service import OperationsService

# Same fixture shape as test_invoice_line_items.py's real water-heater job
# (verified to sum to 790.00 exactly, including a negative Service Call
# Fee adjustment and a zero-value Tax line).
_LINE_ITEMS = [
    {"description": "Labor Charge", "quantity": 4.0, "unit_cost": 55.0, "total_cost": 220.0},
    {"description": "rheem XE30S06ST45U1", "quantity": 1.0, "unit_cost": 530.0, "total_cost": 530.0},
    {"description": "water supply line hoses", "quantity": 1.0, "unit_cost": 70.0, "total_cost": 70.0},
    {"description": "3/4\" copper", "quantity": 1.0, "unit_cost": 25.0, "total_cost": 25.0},
    {"description": "pex pipe 10' 1/2\"", "quantity": 1.0, "unit_cost": 10.0, "total_cost": 10.0},
    {"description": "pex 90 elbow 1/2\"", "quantity": 1.0, "unit_cost": 2.0, "total_cost": 2.0},
    {"description": "male 3/4\" to 1/2\" pex connector", "quantity": 1.0, "unit_cost": 8.0, "total_cost": 8.0},
    {"description": "Service Call Fee (SCF)", "quantity": 1.0, "unit_cost": -75.0, "total_cost": -75.0},
    {"description": "Tax", "quantity": 1.0, "unit_cost": 0.0, "total_cost": 0.0},
]


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    commission = CommissionService(db, audit)
    ops = OperationsService(db, audit)
    crm = CRMService(db, audit, operations_service=ops, commission_service=commission)
    # Admin created FIRST so it lands users.id == 1, matching
    # intake_system_actor/commission_system_actor's hardcoded user_id=1
    # (same known FK-fragility as the existing commission_system_actor/
    # pdf_system_actor precedents -- NEW-602).
    admin_user = auth.create_user(
        username="admin", plain_password="Password123", full_name="Admin", email="admin@test.com", role=ROLE_ADMIN,
    )
    admin = AuthContext(user_id=admin_user.id, username="admin", role=ROLE_ADMIN, actor_type="human")
    return {
        "db": db,
        "auth": auth,
        "audit": audit,
        "commission": commission,
        "ops": ops,
        "crm": crm,
        "admin": admin,
    }


def _make_actor(env, username, role, email=None):
    user = env["auth"].create_user(
        username=username,
        plain_password="Password123",
        full_name=username.title(),
        email=email or f"{username}@test.com",
        role=role,
    )
    return AuthContext(user_id=user.id, username=username, role=role, actor_type="human")


def _line_items():
    return [dict(item) for item in _LINE_ITEMS]


def _customer_data(**overrides):
    data = {
        "first_name": "Joy",
        "last_name": "Clark",
        "phone": "(555) 123-4567",
        "email": "joy.clark@test.com",
    }
    data.update(overrides)
    return data


# ==========================================
# Customer dedup
# ==========================================


def test_no_match_creates_new_customer(env):
    crm = env["crm"]
    tech = _make_actor(env, "tech1", ROLE_TECHNICIAN)
    sales = _make_actor(env, "sales1", ROLE_SALES)

    result = crm.submit_work_order_intake(
        actor=tech,
        salesperson_user_id=sales.user_id,
        customer_data=_customer_data(),
        property_address="123 Main St",
        work_order_data={"trade": "plumbing"},
        line_items=_line_items(),
    )
    assert result["customer_created"] is True

    cust = crm.get_customer(result["customer_id"], env["admin"])
    assert cust.first_name == "Joy"
    assert cust.last_name == "Clark"


def test_exact_email_match_reuses_customer(env):
    crm = env["crm"]
    tech = _make_actor(env, "tech1", ROLE_TECHNICIAN)
    sales = _make_actor(env, "sales1", ROLE_SALES)

    existing = crm.create_customer(
        Customer(first_name="Joy", last_name="Clark", email="Joy.Clark@Test.com", phone="999-999-9999"),
        env["admin"],
    )

    result = crm.submit_work_order_intake(
        actor=tech,
        salesperson_user_id=sales.user_id,
        # Different phone/case-different email -- email match alone must win.
        customer_data=_customer_data(email="joy.clark@test.com", phone="000-000-0000"),
        property_address="123 Main St",
        work_order_data={"trade": "plumbing"},
        line_items=_line_items(),
    )
    assert result["customer_created"] is False
    assert result["customer_id"] == existing.id


def test_phone_and_lastname_match_reuses_customer_when_no_email_match(env):
    crm = env["crm"]
    tech = _make_actor(env, "tech1", ROLE_TECHNICIAN)
    sales = _make_actor(env, "sales1", ROLE_SALES)

    existing = crm.create_customer(
        Customer(first_name="Joy", last_name="Clark", email="unrelated@test.com", phone="555-123-4567"),
        env["admin"],
    )

    result = crm.submit_work_order_intake(
        actor=tech,
        salesperson_user_id=sales.user_id,
        # No email supplied at all -- must fall through to phone+lastname.
        customer_data={"first_name": "Joy", "last_name": "Clark", "phone": "(555) 123-4567"},
        property_address="123 Main St",
        work_order_data={"trade": "plumbing"},
        line_items=_line_items(),
    )
    assert result["customer_created"] is False
    assert result["customer_id"] == existing.id


def test_ambiguous_email_match_falls_through_to_phone_lastname(env):
    crm = env["crm"]
    tech = _make_actor(env, "tech1", ROLE_TECHNICIAN)
    sales = _make_actor(env, "sales1", ROLE_SALES)

    # Two customers share the same email (household inbox) -- ambiguous.
    crm.create_customer(Customer(first_name="Joy", last_name="Clark", email="shared@test.com", phone="111-111-1111"), env["admin"])
    target = crm.create_customer(Customer(first_name="Tom", last_name="Clark", email="shared@test.com", phone="555-123-4567"), env["admin"])

    result = crm.submit_work_order_intake(
        actor=tech,
        salesperson_user_id=sales.user_id,
        customer_data={"first_name": "Tom", "last_name": "Clark", "phone": "(555) 123-4567", "email": "shared@test.com"},
        property_address="123 Main St",
        work_order_data={"trade": "plumbing"},
        line_items=_line_items(),
    )
    # Email was ambiguous (2 matches), but phone+lastname resolves to
    # exactly one (Tom Clark) -- reused, not a new customer.
    assert result["customer_created"] is False
    assert result["customer_id"] == target.id


def test_ambiguous_matches_on_both_paths_creates_new_customer(env):
    crm = env["crm"]
    tech = _make_actor(env, "tech1", ROLE_TECHNICIAN)
    sales = _make_actor(env, "sales1", ROLE_SALES)

    crm.create_customer(Customer(first_name="A", last_name="Clark", email="shared@test.com", phone="555-123-4567"), env["admin"])
    crm.create_customer(Customer(first_name="B", last_name="Clark", email="shared@test.com", phone="555-123-4567"), env["admin"])

    result = crm.submit_work_order_intake(
        actor=tech,
        salesperson_user_id=sales.user_id,
        customer_data={"first_name": "C", "last_name": "Clark", "phone": "(555) 123-4567", "email": "shared@test.com"},
        property_address="123 Main St",
        work_order_data={"trade": "plumbing"},
        line_items=_line_items(),
    )
    # Both paths ambiguous (2 matches each) -- never guess, create new.
    assert result["customer_created"] is True


def test_assigned_user_id_set_from_salesperson_param_not_actor(env):
    crm = env["crm"]
    tech = _make_actor(env, "tech1", ROLE_TECHNICIAN)
    sales = _make_actor(env, "sales1", ROLE_SALES)

    result = crm.submit_work_order_intake(
        actor=tech,
        salesperson_user_id=sales.user_id,
        customer_data=_customer_data(),
        property_address="123 Main St",
        work_order_data={"trade": "plumbing"},
        line_items=_line_items(),
    )

    cust = crm.get_customer(result["customer_id"], env["admin"])
    assert cust.assigned_user_id == sales.user_id
    assert cust.assigned_user_id != tech.user_id

    invoice = crm.get_invoice(result["invoice_id"], env["admin"])
    assert invoice.assigned_user_id == sales.user_id


def test_reuse_unclaimed_customer_still_attributes_invoice_to_intake_salesperson(env):
    """NEW-673-adjacent bug fix (2026-09-27): on the customer-REUSE branch
    (matched via dedup), the existing customer's own assigned_user_id must
    NOT be silently reassigned to the intake's salesperson -- but the new
    Invoice this method creates must still be explicitly attributed to
    that salesperson, not left to inherit whatever (possibly None)
    assigned_user_id the reused customer carries."""
    crm = env["crm"]
    tech = _make_actor(env, "tech1", ROLE_TECHNICIAN)
    sales = _make_actor(env, "sales1", ROLE_SALES)

    existing = crm.create_customer(
        Customer(
            first_name="Joy",
            last_name="Clark",
            email="joy.clark@test.com",
            phone="999-999-9999",
            assigned_user_id=None,
        ),
        env["admin"],
    )

    result = crm.submit_work_order_intake(
        actor=tech,
        salesperson_user_id=sales.user_id,
        customer_data=_customer_data(email="joy.clark@test.com"),
        property_address="123 Main St",
        work_order_data={"trade": "plumbing"},
        line_items=_line_items(),
    )
    assert result["customer_created"] is False
    assert result["customer_id"] == existing.id

    cust = crm.get_customer(result["customer_id"], env["admin"])
    assert cust.assigned_user_id is None  # ownership not silently reassigned

    invoice = crm.get_invoice(result["invoice_id"], env["admin"])
    assert invoice.assigned_user_id == sales.user_id


def test_reuse_claimed_customer_by_different_rep_still_attributes_invoice_to_intake_salesperson(env):
    """Same as above, but the reused customer already has a DIFFERENT
    owning rep -- confirms the invoice still gets the intake's named
    salesperson, and the customer's existing (different) assigned_user_id
    is left completely untouched."""
    crm = env["crm"]
    tech = _make_actor(env, "tech1", ROLE_TECHNICIAN)
    sales = _make_actor(env, "sales1", ROLE_SALES)
    prior_rep = _make_actor(env, "priorrep1", ROLE_SALES)

    existing = crm.create_customer(
        Customer(
            first_name="Joy",
            last_name="Clark",
            email="joy.clark@test.com",
            phone="999-999-9999",
            assigned_user_id=prior_rep.user_id,
        ),
        env["admin"],
    )

    result = crm.submit_work_order_intake(
        actor=tech,
        salesperson_user_id=sales.user_id,
        customer_data=_customer_data(email="joy.clark@test.com"),
        property_address="123 Main St",
        work_order_data={"trade": "plumbing"},
        line_items=_line_items(),
    )
    assert result["customer_created"] is False
    assert result["customer_id"] == existing.id

    cust = crm.get_customer(result["customer_id"], env["admin"])
    assert cust.assigned_user_id == prior_rep.user_id  # untouched, not reassigned

    invoice = crm.get_invoice(result["invoice_id"], env["admin"])
    assert invoice.assigned_user_id == sales.user_id
    assert invoice.assigned_user_id != prior_rep.user_id


# ==========================================
# End-to-end, both eligible roles
# ==========================================


def test_technician_actor_can_submit_intake_end_to_end(env):
    crm = env["crm"]
    tech = _make_actor(env, "tech1", ROLE_TECHNICIAN)
    sales = _make_actor(env, "sales1", ROLE_SALES)

    result = crm.submit_work_order_intake(
        actor=tech,
        salesperson_user_id=sales.user_id,
        customer_data=_customer_data(),
        property_address="123 Main St",
        work_order_data={"trade": "plumbing", "instructions": "No hot water"},
        line_items=_line_items(),
        reported_technician_name="Tech One",
    )
    assert result["customer_id"] is not None
    assert result["project_id"] is not None
    assert result["work_order_id"] is not None
    assert result["invoice_id"] is not None

    wo = env["ops"].get_work_order(result["work_order_id"], env["admin"])
    assert wo.project_id == result["project_id"]
    assert wo.trade == "plumbing"
    assert "Tech One" in (wo.notes or "")
    assert wo.status == "draft"


def test_diagnostic_appliance_fields_are_not_silently_dropped(env):
    """WorkOrder has no dedicated columns for diagnostic/appliance-report
    fields -- any work_order_data key that isn't one of the structured
    WorkOrder fields must survive into notes, not vanish."""
    crm = env["crm"]
    tech = _make_actor(env, "tech1", ROLE_TECHNICIAN)
    sales = _make_actor(env, "sales1", ROLE_SALES)

    result = crm.submit_work_order_intake(
        actor=tech,
        salesperson_user_id=sales.user_id,
        customer_data=_customer_data(),
        property_address="123 Main St",
        work_order_data={
            "trade": "plumbing",
            "notes": "Customer reports no hot water",
            "appliance_model": "Rheem XE30S06ST45U1",
            "serial_number": "SN12345",
            "diagnosis": "Failed heating element",
        },
        line_items=_line_items(),
        reported_technician_name="Tech One",
    )

    wo = env["ops"].get_work_order(result["work_order_id"], env["admin"])
    assert "Customer reports no hot water" in wo.notes
    assert "Tech One" in wo.notes
    assert "appliance_model: Rheem XE30S06ST45U1" in wo.notes
    assert "serial_number: SN12345" in wo.notes
    assert "diagnosis: Failed heating element" in wo.notes


def test_subcontractor_actor_can_submit_intake_end_to_end(env):
    crm = env["crm"]
    sub = _make_actor(env, "sub1", ROLE_SUBCONTRACTOR)
    sales = _make_actor(env, "sales1", ROLE_SALES)

    result = crm.submit_work_order_intake(
        actor=sub,
        salesperson_user_id=sales.user_id,
        customer_data=_customer_data(),
        property_address="123 Main St",
        work_order_data={"trade": "plumbing"},
        line_items=_line_items(),
    )
    assert result["customer_id"] is not None
    assert result["project_id"] is not None
    assert result["work_order_id"] is not None
    assert result["invoice_id"] is not None


def test_actor_without_write_operations_cannot_submit_intake(env):
    crm = env["crm"]
    sales = _make_actor(env, "sales1", ROLE_SALES)

    with pytest.raises(PermissionError):
        crm.submit_work_order_intake(
            actor=sales,
            salesperson_user_id=sales.user_id,
            customer_data=_customer_data(),
            property_address="123 Main St",
            work_order_data={"trade": "plumbing"},
            line_items=_line_items(),
        )


# ==========================================
# Invoice / project shape
# ==========================================


def test_invoice_is_typed_project_with_computed_amount_and_matching_line_items(env):
    crm = env["crm"]
    tech = _make_actor(env, "tech1", ROLE_TECHNICIAN)
    sales = _make_actor(env, "sales1", ROLE_SALES)

    result = crm.submit_work_order_intake(
        actor=tech,
        salesperson_user_id=sales.user_id,
        customer_data=_customer_data(),
        property_address="123 Main St",
        work_order_data={"trade": "plumbing"},
        line_items=_line_items(),
    )

    invoice = crm.get_invoice(result["invoice_id"], env["admin"])
    assert invoice.invoice_type == "project"
    assert invoice.status == "draft"
    assert invoice.amount == 790.00
    assert invoice.balance_due == 790.00
    assert len(invoice.line_items) == len(_LINE_ITEMS)
    assert invoice.line_items[0]["total_cost"] == 220.0


def test_project_stage_is_real_intake_enum_value(env):
    crm = env["crm"]
    tech = _make_actor(env, "tech1", ROLE_TECHNICIAN)
    sales = _make_actor(env, "sales1", ROLE_SALES)

    result = crm.submit_work_order_intake(
        actor=tech,
        salesperson_user_id=sales.user_id,
        customer_data=_customer_data(),
        property_address="123 Main St",
        work_order_data={"trade": "plumbing"},
        line_items=_line_items(),
    )

    project = crm.get_project(result["project_id"], env["admin"])
    assert project.stage == ProjectStage.INTAKE
    assert project.stage == "intake"
    assert project.stage != "Lead"


def test_project_find_or_create_reuses_existing_project_same_customer_and_address(env):
    crm = env["crm"]
    tech = _make_actor(env, "tech1", ROLE_TECHNICIAN)
    sales = _make_actor(env, "sales1", ROLE_SALES)

    first = crm.submit_work_order_intake(
        actor=tech,
        salesperson_user_id=sales.user_id,
        customer_data=_customer_data(),
        property_address="123 Main St",
        work_order_data={"trade": "plumbing"},
        line_items=_line_items(),
    )
    second = crm.submit_work_order_intake(
        actor=tech,
        salesperson_user_id=sales.user_id,
        # Same email -> reuses customer; same address -> reuses project.
        customer_data=_customer_data(),
        property_address="123 Main St",
        work_order_data={"trade": "electrical"},
        line_items=_line_items(),
    )
    assert second["customer_created"] is False
    assert second["customer_id"] == first["customer_id"]
    assert second["project_created"] is False
    assert second["project_id"] == first["project_id"]
    # A second, independent work order + invoice is still created each call.
    assert second["work_order_id"] != first["work_order_id"]
    assert second["invoice_id"] != first["invoice_id"]


# ==========================================
# Audit trail
# ==========================================


def test_audit_trail_records_real_submitting_actor_not_system_actor(env):
    crm = env["crm"]
    audit = env["audit"]
    admin = env["admin"]
    tech = _make_actor(env, "tech1", ROLE_TECHNICIAN)
    sales = _make_actor(env, "sales1", ROLE_SALES)

    result = crm.submit_work_order_intake(
        actor=tech,
        salesperson_user_id=sales.user_id,
        customer_data=_customer_data(),
        property_address="123 Main St",
        work_order_data={"trade": "plumbing"},
        line_items=_line_items(),
    )

    logs = audit.query_logs(admin, action="intake_submitted", entity_type="work_order", entity_id=result["work_order_id"])
    assert len(logs) == 1
    assert logs[0].actor_id == tech.user_id
    assert logs[0].actor_role == ROLE_TECHNICIAN

    # The internal create_customer step, by contrast, is attributed to the
    # system actor, not the real submitting technician.
    customer_create_logs = audit.query_logs(admin, action="create", entity_type="customer", entity_id=result["customer_id"])
    assert len(customer_create_logs) == 1
    assert customer_create_logs[0].actor_id == 1
    assert customer_create_logs[0].actor_role == ROLE_ADMIN
    assert customer_create_logs[0].actor_id != tech.user_id


# ==========================================
# Commission trigger widening (record_payment)
# ==========================================


def test_paid_project_invoice_now_fires_commission(env):
    crm = env["crm"]
    commission = env["commission"]
    admin = env["admin"]
    rep = _make_actor(env, "rep1", ROLE_SALES)

    cust = crm.create_customer(
        Customer(first_name="Joy", last_name="Clark", email="joy2@test.com", assigned_user_id=rep.user_id),
        admin,
    )
    invoice = crm.create_invoice(
        Invoice(customer_id=cust.id, invoice_type="project", line_items=_line_items()),
        admin,
    )
    assert invoice.amount == 790.00

    updated = crm.record_payment(invoice.id, invoice.amount, "credit_card", "TXN-PROJ-1", admin)
    assert updated.status == "paid"

    entries = commission.list_commissions(admin, rep_user_id=rep.user_id)
    assert len(entries) == 1
    assert entries[0].source_type == "assessment"
    assert entries[0].source_id == invoice.id
    assert entries[0].status == "earned"


def test_paid_assessment_invoice_commission_unchanged(env):
    """Regression guard: the pre-existing assessment-invoice commission
    behavior must be completely unaffected by the widened condition."""
    crm = env["crm"]
    commission = env["commission"]
    admin = env["admin"]
    rep = _make_actor(env, "rep1", ROLE_SALES)

    cust = crm.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane3@test.com", assigned_user_id=rep.user_id),
        admin,
    )
    invoice = crm.create_invoice(
        Invoice(customer_id=cust.id, amount=299.0, invoice_type="assessment"),
        admin,
    )
    updated = crm.record_payment(invoice.id, 299.0, "credit_card", "TXN-ASSESS-1", admin)
    assert updated.status == "paid"

    entries = commission.list_commissions(admin, rep_user_id=rep.user_id)
    assert len(entries) == 1
    assert entries[0].source_type == "assessment"
    assert entries[0].source_id == invoice.id


@pytest.mark.parametrize("invoice_type", ["subscription", "other"])
def test_paid_invoice_other_types_still_do_not_fire_commission(env, invoice_type):
    crm = env["crm"]
    commission = env["commission"]
    admin = env["admin"]
    rep = _make_actor(env, "rep1", ROLE_SALES)

    cust = crm.create_customer(
        Customer(first_name="No", last_name="Commission", email=f"no-commission-{invoice_type}@test.com", assigned_user_id=rep.user_id),
        admin,
    )
    invoice = crm.create_invoice(
        Invoice(customer_id=cust.id, amount=100.0, invoice_type=invoice_type),
        admin,
    )
    updated = crm.record_payment(invoice.id, 100.0, "credit_card", f"TXN-{invoice_type}", admin)
    assert updated.status == "paid"

    entries = commission.list_commissions(admin, rep_user_id=rep.user_id)
    assert len(entries) == 0
