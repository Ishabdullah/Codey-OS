"""
Unit tests for the B8.15 findings-backlog sweep's void-invoice guard and
negative-payment rejection (NEW-633/NEW-651), fixed in the same round in
record_payment per this project's "fix related findings together"
convention.

NEW-633: record_payment never checked the invoice's current status
before recording a payment -- a payment against a 'void' invoice would
silently resurrect it to 'paid'/'partially_paid'. No service method can
actually produce status='void' today (confirmed by a repo-wide grep), so
these tests write it directly via the DB connection, mirroring how a
future void-invoice feature (or a manual DB fixup) would leave the row.

NEW-651: record_payment accepted a negative payment_amount with no
validation -- confirmed consequence (flagged during the NEW-613/633
credit-ledger review): a negative payment silently skips creating a new
credit row (the overage-delta guard is `> 0.001`) without clawing back
any previously-issued customer_credits row, since no payment-correction/
reversal mechanism exists in this codebase. $0.00 remains a legitimate,
explicitly documented use case (an operator's reconciliation note, see
record_payment's own idempotency comment) and must still be accepted.
"""

import pytest

from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN
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


def test_record_payment_rejects_payment_against_voided_invoice(setup_services):
    db, auth_service, audit_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin
    )
    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=1000.0), admin
    )

    # No service method can produce status='void' -- write it directly,
    # as a future void-invoice feature or manual DB fixup would.
    conn = db.get_connection()
    with conn:
        conn.execute("UPDATE invoices SET status = 'void' WHERE id = ?;", (invoice.id,))

    logs_before = audit_service.query_logs(admin)
    credits_before = conn.execute(
        "SELECT COUNT(*) FROM customer_credits WHERE source_invoice_id = ?;", (invoice.id,)
    ).fetchone()[0]

    with pytest.raises(ValueError):
        crm_service.record_payment(invoice.id, 500.0, "check", "TXN-1", admin)

    row = conn.execute("SELECT * FROM invoices WHERE id = ?;", (invoice.id,)).fetchone()
    assert row["status"] == "void"
    assert row["payments_json"] in (None, "[]")

    logs_after = audit_service.query_logs(admin)
    assert len(logs_after) == len(logs_before)

    credits_after = conn.execute(
        "SELECT COUNT(*) FROM customer_credits WHERE source_invoice_id = ?;", (invoice.id,)
    ).fetchone()[0]
    assert credits_after == credits_before


def test_record_payment_rejects_negative_payment_amount(setup_services):
    db, auth_service, audit_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin
    )
    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=1000.0), admin
    )

    logs_before = audit_service.query_logs(admin)

    with pytest.raises(ValueError):
        crm_service.record_payment(invoice.id, -50.0, "check", "TXN-1", admin)

    conn = db.get_connection()
    row = conn.execute("SELECT * FROM invoices WHERE id = ?;", (invoice.id,)).fetchone()
    assert row["status"] == "draft"
    assert row["payments_json"] in (None, "[]")

    logs_after = audit_service.query_logs(admin)
    assert len(logs_after) == len(logs_before)


def test_negative_payment_does_not_claw_back_an_existing_credit_row(setup_services):
    """The actual consequence NEW-651 was filed on: a negative payment
    doesn't create a new credit row (the overage-delta guard is
    `> 0.001`), but there's no reversal mechanism to claw back a
    PREVIOUSLY-issued customer_credits row either -- so an accepted
    negative payment would leave the credit ledger stuck at its
    high-water mark while balance_due silently moved. The fix's job is
    to reject the negative payment outright before any of that can
    happen."""
    db, auth_service, audit_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin
    )
    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=1000.0), admin
    )

    # First, a genuine overpayment that logs a $500 credit row.
    first = crm_service.record_payment(invoice.id, 1500.0, "check", "TXN-1", admin)
    assert first.status == "paid"
    assert crm_service.get_customer_credit_balance(cust.id, admin) == 500.0

    logs_before = audit_service.query_logs(admin)

    with pytest.raises(ValueError):
        crm_service.record_payment(invoice.id, -200.0, "check", "TXN-2", admin)

    # Credit ledger untouched -- still exactly the one $500 row.
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT amount FROM customer_credits WHERE source_invoice_id = ?;", (invoice.id,)
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["amount"] == 500.0
    assert crm_service.get_customer_credit_balance(cust.id, admin) == 500.0

    # payments_json and audit trail also unchanged by the rejected call.
    row = conn.execute("SELECT * FROM invoices WHERE id = ?;", (invoice.id,)).fetchone()
    payments = row["payments_json"]
    assert payments.count('"reference"') == 1  # only TXN-1's payment recorded

    logs_after = audit_service.query_logs(admin)
    assert len(logs_after) == len(logs_before)


def test_record_payment_still_allows_zero_amount_reconciliation_note(setup_services):
    """$0.00 is an explicitly documented legitimate use case (an
    operator's reconciliation note) and must not be rejected by the
    NEW-651 negative-amount guard."""
    db, auth_service, audit_service, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin
    )
    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=1000.0), admin
    )

    updated = crm_service.record_payment(invoice.id, 0.0, "check", "TXN-1", admin)
    # A $0.00 payment doesn't pay anything off, so balance/status still
    # reflect the invoice as owed -- what NEW-651 guarantees is that the
    # call succeeds at all (no ValueError) and the note is recorded.
    assert updated.status == "partially_paid"
    assert updated.balance_due == 1000.0
    assert len(updated.payments) == 1
    assert updated.payments[0]["amount"] == 0.0
