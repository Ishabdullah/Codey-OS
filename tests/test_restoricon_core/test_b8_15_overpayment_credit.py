"""
Unit tests for B8.15's overpayment-credit tracking (NEW-613/NEW-633
cluster, Ish-approved 2026-09-25: "overpayments should be logged as
credit" -- manual-only, no auto-apply to future invoices, and
deliberately kept separate from AR reporting).

Invoices in these tests deliberately use the default invoice_type
('other'), NOT 'assessment' -- an assessment invoice would route through
record_payment's Phase-1 commission block and the Phase-3
portfolio-override block (which fires on every call), which would muddy
what these tests are actually proving about the credit ledger.
"""

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Invoice
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService


@pytest.fixture
def setup_services():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)
    return db, auth_service, audit_service, crm_service


def _make_actor(auth_service, username, role, email=None, customer_id=None):
    user = auth_service.create_user(
        username=username,
        plain_password="Password123",
        full_name=username.title(),
        email=email or f"{username}@test.com",
        role=role,
        customer_id=customer_id,
    )
    return AuthContext(
        user_id=user.id, username=username, role=role, actor_type="human", customer_id=customer_id
    )


def test_overpayment_logs_a_customer_credit_row(setup_services):
    db, auth_service, audit_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin
    )
    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=1000.0), admin
    )

    updated = crm_service.record_payment(invoice.id, 1500.0, "check", "TXN-1", admin)
    assert updated.status == "paid"
    assert updated.balance_due == 0.0

    balance = crm_service.get_customer_credit_balance(cust.id, admin)
    assert balance == 500.0

    conn = db.get_connection()
    rows = conn.execute(
        "SELECT customer_id, source_invoice_id, amount, reason FROM customer_credits WHERE source_invoice_id = ?;",
        (invoice.id,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["customer_id"] == cust.id
    assert rows[0]["amount"] == 500.0
    assert rows[0]["reason"] == "overpayment"


def test_no_credit_logged_when_payment_does_not_overpay(setup_services):
    db, auth_service, audit_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin
    )
    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=1000.0), admin
    )

    updated = crm_service.record_payment(invoice.id, 400.0, "check", "TXN-1", admin)
    assert updated.status == "partially_paid"

    balance = crm_service.get_customer_credit_balance(cust.id, admin)
    assert balance == 0.0


def test_retried_call_on_already_overpaid_invoice_does_not_double_log_credit(setup_services):
    """Idempotency: two back-to-back record_payment calls where the
    second is a retry with no new money (payment_amount=0.0, mirroring
    B8.7a's own idempotency-guard test shape) must not create a second
    credit row -- overage is unchanged across the retry."""
    db, auth_service, audit_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin
    )
    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=1000.0), admin
    )

    first = crm_service.record_payment(invoice.id, 1500.0, "check", "TXN-1", admin)
    assert first.status == "paid"

    second = crm_service.record_payment(invoice.id, 0.0, "check", "TXN-2", admin)
    assert second.status == "paid"

    conn = db.get_connection()
    rows = conn.execute(
        "SELECT amount FROM customer_credits WHERE source_invoice_id = ?;", (invoice.id,)
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["amount"] == 500.0

    balance = crm_service.get_customer_credit_balance(cust.id, admin)
    assert balance == 500.0


def test_genuine_further_overpayment_logs_only_the_incremental_delta(setup_services):
    """Third case, distinct from a no-op retry: a genuine SECOND
    overpayment on top of an already-credited invoice must log only the
    new increment, not the full new overage total (which would double-
    count the first $500)."""
    db, auth_service, audit_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin
    )
    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=1000.0), admin
    )

    first = crm_service.record_payment(invoice.id, 1500.0, "check", "TXN-1", admin)
    assert first.status == "paid"

    # A further, genuinely new $200 misdirected payment against the same
    # already-paid/overpaid invoice.
    second = crm_service.record_payment(invoice.id, 200.0, "check", "TXN-2", admin)
    assert second.status == "paid"

    conn = db.get_connection()
    rows = conn.execute(
        "SELECT amount FROM customer_credits WHERE source_invoice_id = ? ORDER BY id;",
        (invoice.id,),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["amount"] == 500.0
    assert rows[1]["amount"] == 200.0

    balance = crm_service.get_customer_credit_balance(cust.id, admin)
    assert balance == 700.0


def test_get_customer_credit_balance_rejects_actor_without_financial_read(setup_services):
    db, auth_service, audit_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin
    )

    class ZeroPermissionActor:
        role = "nobody"
        customer_id = None

        def has_permission(self, permission: str) -> bool:
            return False

    with pytest.raises(PermissionError):
        crm_service.get_customer_credit_balance(cust.id, ZeroPermissionActor())


def test_customer_role_cannot_read_another_customers_credit_balance(setup_services):
    """Mirrors test_services.py's
    test_customer_role_cannot_use_provider_message_id_to_read_another_customers_row
    convention: a ROLE_CUSTOMER actor holding PERM_READ_OWN_FINANCIALS
    must not be able to pass an arbitrary customer_id and read a
    different customer's credit balance."""
    db, auth_service, audit_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust_a = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin
    )
    cust_b = crm_service.create_customer(
        Customer(first_name="John", last_name="Smith", email="john@test.com"), admin
    )
    invoice_a = crm_service.create_invoice(Invoice(customer_id=cust_a.id, amount=1000.0), admin)
    crm_service.record_payment(invoice_a.id, 1500.0, "check", "TXN-1", admin)

    actor_cust_b = _make_actor(
        auth_service, "john_smith", ROLE_CUSTOMER, customer_id=cust_b.id
    )

    # Actor is customer B, but tries to read customer A's credit balance.
    with pytest.raises(PermissionError):
        crm_service.get_customer_credit_balance(cust_a.id, actor_cust_b)

    # Reading their own balance (zero, no overpayment) is fine.
    assert crm_service.get_customer_credit_balance(cust_b.id, actor_cust_b) == 0.0


def test_credit_recorded_folded_into_existing_pay_audit_entry_not_a_new_one(setup_services):
    """Confirms the credit side effect is folded into the existing 'pay'
    audit.log call rather than a separate audit entry -- test_services.py's
    test_crm_entity_lifecycle_with_audit_trail hard-asserts an exact log
    count elsewhere in this suite, so a new audit.log call per overpayment
    would be a regression risk there."""
    db, auth_service, audit_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin
    )
    invoice = crm_service.create_invoice(Invoice(customer_id=cust.id, amount=1000.0), admin)

    crm_service.record_payment(invoice.id, 1500.0, "check", "TXN-1", admin)
    logs_after = audit_service.query_logs(admin)

    # Exactly one "pay" audit entry, and it carries the credit side
    # effect -- no separate audit.log call was added for the credit.
    pay_entries = [entry for entry in logs_after if entry.action == "pay"]
    assert len(pay_entries) == 1
    assert pay_entries[0].details["side_effects"]["credit_recorded"]["amount"] == 500.0
