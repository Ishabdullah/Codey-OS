"""
Unit tests for Phase 0-slim: invoice line-item schema and read/write
support (crm_service.create_invoice / _row_to_invoice). Mirrors
OperationsService.create_work_order's line-item cost computation --
each item's total_cost is recomputed server-side from
quantity * unit_cost and summed into Invoice.amount, never trusting a
client-supplied amount when line_items is non-empty.
"""

import pytest

from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Invoice
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService

# Real line items from a live water-heater job, verified to sum to
# 790.00 exactly (including a negative Service Call Fee adjustment and a
# zero-value Tax line).
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
def setup_services():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)
    return db, auth_service, crm_service


def _make_actor(auth_service, username, role, email=None):
    user = auth_service.create_user(
        username=username,
        plain_password="Password123",
        full_name=username.title(),
        email=email or f"{username}@test.com",
        role=role,
    )
    return AuthContext(user_id=user.id, username=username, role=role, actor_type="human")


def _make_customer(crm_service, admin):
    return crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"),
        admin,
    )


def test_create_invoice_computes_amount_from_line_items(setup_services):
    _, auth_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust = _make_customer(crm_service, admin)

    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, line_items=[dict(item) for item in _LINE_ITEMS]),
        admin,
    )

    assert invoice.amount == 790.00
    # balance_due must be computed from the corrected amount, not from
    # whatever amount the client (didn't) supply -- ordering regression
    # guard.
    assert invoice.balance_due == 790.00
    assert len(invoice.line_items) == len(_LINE_ITEMS)
    assert invoice.line_items[0]["total_cost"] == 220.0

    fetched = crm_service.get_invoice(invoice.id, admin)
    assert fetched.amount == 790.00
    assert fetched.balance_due == 790.00
    assert len(fetched.line_items) == len(_LINE_ITEMS)
    assert fetched.line_items[-1]["description"] == "Tax"


def test_create_invoice_line_items_override_bogus_client_amount(setup_services):
    """The rule this phase exists for: a client-supplied amount must never
    be trusted when line_items is non-empty."""
    _, auth_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust = _make_customer(crm_service, admin)

    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=1.0, line_items=[dict(item) for item in _LINE_ITEMS]),
        admin,
    )

    assert invoice.amount == 790.00
    assert invoice.balance_due == 790.00


def test_line_item_total_cost_is_recomputed_not_trusted(setup_services):
    """Distinguishes 'recompute total_cost from quantity*unit_cost' from
    'sum the client-supplied total_cost field' -- the real line-item
    fixture above happens to agree on both readings, so this uses a
    client total_cost that's a deliberate lie (999.0) to prove the
    server recomputes rather than trusting it, mirroring
    OperationsService.create_work_order exactly."""
    _, auth_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust = _make_customer(crm_service, admin)

    invoice = crm_service.create_invoice(
        Invoice(
            customer_id=cust.id,
            line_items=[{"description": "X", "quantity": 2.0, "unit_cost": 10.0, "total_cost": 999.0}],
        ),
        admin,
    )

    assert invoice.amount == 20.0
    assert invoice.line_items[0]["total_cost"] == 20.0


def test_record_payment_returns_invoice_with_line_items(setup_services):
    """Reviewer-flagged bug: record_payment hand-builds its returned
    Invoice from the row instead of calling _row_to_invoice, so it never
    populated line_items -- the dataclass default ([]) silently won
    even when the invoice has real line items. This is what
    POST /api/v1/invoices/{id}/pay returns directly (routes.py,
    updated_inv.to_dict()), so the bug was visible to that one API
    response even though the DB and get_invoice were always correct."""
    _, auth_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust = _make_customer(crm_service, admin)

    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, line_items=[dict(item) for item in _LINE_ITEMS]),
        admin,
    )
    assert invoice.line_items  # sanity: fixture actually has line items

    updated = crm_service.record_payment(
        invoice_id=invoice.id,
        payment_amount=100.0,
        payment_method="check",
        transaction_reference="TEST-REF-1",
        actor=admin,
    )

    assert updated.line_items == invoice.line_items
    assert len(updated.line_items) == len(_LINE_ITEMS)


def test_create_invoice_without_line_items_is_unchanged(setup_services):
    """Backward compat: existing callers that only pass amount (no
    line_items) must not break."""
    _, auth_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust = _make_customer(crm_service, admin)

    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=299.0),
        admin,
    )

    assert invoice.amount == 299.0
    assert invoice.balance_due == 299.0
    assert invoice.line_items == []

    fetched = crm_service.get_invoice(invoice.id, admin)
    assert fetched.amount == 299.0
    assert fetched.line_items == []
