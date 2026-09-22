"""
Unit tests for B8.7a (D4, sales_rep_portal.md §4, Ish-approved 2026-09-16;
NEW-598/600/601 context): the commission_plan_config singleton, Invoice's
new assigned_user_id/invoice_type columns, and record_payment's automatic
Phase-1 flat-commission trigger fired exactly on the not-paid -> paid
transition edge for invoice_type == 'assessment'.
"""

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_READ_TEAM_COMMISSIONS,
    ROLE_ADMIN,
    ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Invoice
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.commission_service import CommissionService
from restoricon_core.services.crm_service import CRMService


@pytest.fixture
def setup_services():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    commission_service = CommissionService(db, audit_service)
    crm_service = CRMService(db, audit_service, commission_service=commission_service)
    return db, auth_service, audit_service, crm_service, commission_service


def _make_actor(auth_service, username, role, email=None):
    user = auth_service.create_user(
        username=username,
        plain_password="Password123",
        full_name=username.title(),
        email=email or f"{username}@test.com",
        role=role,
    )
    return AuthContext(user_id=user.id, username=username, role=role, actor_type="human")


def _set_flat_commission(db, amount):
    """Directly mutates the seeded commission_plan_config row -- no
    update method exists this round (not required by B8.7a's scope), so
    this simulates a future dashboard edit to prove the trigger reads
    the config row rather than a hardcoded value."""
    conn = db.get_connection()
    with conn:
        conn.execute(
            "UPDATE commission_plan_config SET assessment_flat_commission = ? WHERE id = 1;",
            (amount,),
        )


def test_commission_plan_config_seeded_with_d4_numbers(setup_services):
    """The singleton row exists and is readable without any manual setup
    step, seeded with D4's real numbers (not Python constants)."""
    _, auth_service, _, _, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    config = commission_service.get_commission_plan_config(admin)
    assert config.id == 1
    assert config.assessment_price == 299.0
    assert config.assessment_flat_commission == 100.0
    assert config.homecare_basic_monthly_fee == 179.0
    assert config.homecare_plus_monthly_fee == 399.0
    assert config.homecare_complete_monthly_fee == 599.0
    assert config.homecare_estate_monthly_fee == 999.0


def test_assessment_invoice_paid_in_full_creates_one_commission_entry_reading_config(setup_services):
    """The core exit criterion: an assessment invoice transitioning to
    paid produces exactly one commission_ledger_entries row, attributed
    to the customer's assigned rep, for whatever amount is currently
    seeded in commission_plan_config -- mutated here to a non-default
    value so the test would catch a wiring bug (e.g. a hardcoded $100)
    rather than passing by coincidence against the seed."""
    db, auth_service, _, crm_service, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    rep = _make_actor(auth_service, "rep1", ROLE_SALES)

    _set_flat_commission(db, 137.50)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com", assigned_user_id=rep.user_id),
        admin,
    )

    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=299.0, invoice_type="assessment"),
        admin,
    )
    # Inherited from the customer's own assigned_user_id at creation time,
    # not explicitly supplied.
    assert invoice.assigned_user_id == rep.user_id

    updated = crm_service.record_payment(invoice.id, 299.0, "credit_card", "TXN-1", admin)
    assert updated.status == "paid"

    entries = commission_service.list_commissions(admin, rep_user_id=rep.user_id)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.source_type == "assessment"
    assert entry.source_id == invoice.id
    assert entry.rep_user_id == rep.user_id
    assert entry.commission_amount == 137.50
    assert entry.status == "earned"


def test_record_payment_called_again_on_already_paid_invoice_produces_no_additional_commission(setup_services):
    """Idempotency: record_payment can be called more than once against
    an already-paid invoice (e.g. a retried request) -- the trigger must
    only fire on the actual not-paid -> paid transition edge, not on
    every call."""
    db, auth_service, _, crm_service, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    rep = _make_actor(auth_service, "rep1", ROLE_SALES)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com", assigned_user_id=rep.user_id),
        admin,
    )
    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=299.0, invoice_type="assessment"),
        admin,
    )

    first = crm_service.record_payment(invoice.id, 299.0, "credit_card", "TXN-1", admin)
    assert first.status == "paid"

    # Second call against the same already-paid invoice (a retried
    # request, or an operator recording a $0 reconciliation note) --
    # must not fire the trigger again.
    second = crm_service.record_payment(invoice.id, 0.0, "credit_card", "TXN-2", admin)
    assert second.status == "paid"

    entries = commission_service.list_commissions(admin, rep_user_id=rep.user_id)
    assert len(entries) == 1


def test_double_fire_past_the_python_guard_is_caught_by_the_db_index(setup_services):
    """Second layer of defense: even if the in-Python not-paid -> paid
    guard were somehow bypassed, the DB-level partial unique index on
    commission_ledger_entries(source_type, source_id) rejects a second
    row for the same invoice as an IntegrityError -- which record_payment
    must catch and turn into a no-op audit entry, not a crash and not a
    false failure on the (already-committed) payment.

    This exercises record_payment's actual `except sqlite3.IntegrityError`
    branch for real, at the real not-paid -> paid transition edge --
    not just the index in isolation -- by pre-seeding a commission row
    for this invoice's id *before* paying it, so the trigger's own
    record_commission call is the one that collides."""
    db, auth_service, audit_service, crm_service, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    rep = _make_actor(auth_service, "rep1", ROLE_SALES)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com", assigned_user_id=rep.user_id),
        admin,
    )
    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=299.0, invoice_type="assessment"),
        admin,
    )

    # Pre-seed a commission row against this invoice's id while it's
    # still unpaid -- simulates a prior trigger fire (e.g. a race between
    # two concurrent record_payment calls) that the DB index is meant to
    # catch on the *next* attempt.
    conn = db.get_connection()
    with conn:
        conn.execute(
            "INSERT INTO commission_ledger_entries (rep_user_id, source_type, source_id, commission_amount, status, created_at) "
            "VALUES (?, 'assessment', ?, 100.0, 'earned', datetime('now'));",
            (rep.user_id, invoice.id),
        )

    # The real transition-edge fire: must not raise, despite the trigger's
    # own record_commission call colliding with the pre-seeded row above.
    updated = crm_service.record_payment(invoice.id, 299.0, "credit_card", "TXN-1", admin)
    assert updated.status == "paid"

    entries = commission_service.list_commissions(admin, rep_user_id=rep.user_id)
    assert len(entries) == 1  # only the pre-seeded row -- no second write

    logs = audit_service.query_logs(admin, entity_type="invoice", entity_id=invoice.id, action="commission_duplicate_skipped")
    assert len(logs) == 1


def test_commission_fk_violation_does_not_fail_the_already_committed_payment(setup_services):
    """An IntegrityError NOT matching the expected duplicate-trigger shape
    (e.g. a bogus rep_user_id violating commission_ledger_entries' real
    FK to users) must not propagate past the payment, which has already
    committed by the time the commission side effect runs -- mirrors
    sign_contract's PDF-generation best-effort contract. Forces this via
    a client-supplied assigned_user_id on invoice creation that doesn't
    correspond to any real user row (create_invoice only validates
    invoice_type, not that assigned_user_id references a real user)."""
    db, auth_service, audit_service, crm_service, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin
    )
    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=299.0, invoice_type="assessment", assigned_user_id=999999),
        admin,
    )

    updated = crm_service.record_payment(invoice.id, 299.0, "credit_card", "TXN-1", admin)
    assert updated.status == "paid"  # payment succeeds despite the doomed commission write

    entries = commission_service.list_commissions(admin)
    assert entries == []  # the FK violation rolled back only the commission INSERT

    logs = audit_service.query_logs(admin, entity_type="invoice", entity_id=invoice.id, action="commission_recording_failed")
    assert len(logs) == 1


def test_assessment_invoice_with_no_assigned_rep_skips_commission_without_crashing(setup_services):
    """Explicit product decision (Ish): a rep-less record must not
    silently pay nobody's commission, and must not crash the payment
    either -- zero commission rows, but the skip is logged/auditable."""
    db, auth_service, audit_service, crm_service, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust = crm_service.create_customer(
        Customer(first_name="Unclaimed", last_name="Customer", email="unclaimed@test.com"),
        admin,
    )
    assert cust.assigned_user_id is None

    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=299.0, invoice_type="assessment"),
        admin,
    )
    assert invoice.assigned_user_id is None

    updated = crm_service.record_payment(invoice.id, 299.0, "credit_card", "TXN-1", admin)
    assert updated.status == "paid"

    entries = commission_service.list_commissions(admin)
    assert entries == []

    logs = audit_service.query_logs(admin, entity_type="invoice", entity_id=invoice.id, action="commission_skipped_no_rep")
    assert len(logs) == 1


def test_non_assessment_invoice_paid_in_full_produces_no_commission(setup_services):
    """A non-assessment invoice (default invoice_type) paid in full must
    not trigger any commission write -- B8.7a only acts on invoice_type
    == 'assessment'."""
    _, auth_service, _, crm_service, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    rep = _make_actor(auth_service, "rep1", ROLE_SALES)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com", assigned_user_id=rep.user_id),
        admin,
    )
    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=15000.0, invoice_type="project"),
        admin,
    )

    updated = crm_service.record_payment(invoice.id, 15000.0, "check", "TXN-1", admin)
    assert updated.status == "paid"

    entries = commission_service.list_commissions(admin, rep_user_id=rep.user_id)
    assert entries == []


def test_get_commission_plan_config_raising_does_not_fail_the_already_committed_payment(setup_services, monkeypatch):
    """Regression for a real code-review-caught bug: get_commission_plan_config
    used to be called OUTSIDE (before) the best-effort try/except block, so a
    failure there propagated straight past record_payment despite the payment
    itself having already committed -- a false 500 on an already-successful
    payment. Must be covered by the same best-effort contract as every other
    failure mode in this block: no raise, payment status is 'paid', no
    commission row written, and the failure is audit-logged."""
    db, auth_service, audit_service, crm_service, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    rep = _make_actor(auth_service, "rep1", ROLE_SALES)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com", assigned_user_id=rep.user_id),
        admin,
    )
    invoice = crm_service.create_invoice(
        Invoice(customer_id=cust.id, amount=299.0, invoice_type="assessment"),
        admin,
    )

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated get_commission_plan_config failure")

    monkeypatch.setattr(CommissionService, "get_commission_plan_config", _raise)

    updated = crm_service.record_payment(invoice.id, 299.0, "credit_card", "TXN-1", admin)
    assert updated.status == "paid"

    entries = commission_service.list_commissions(admin, rep_user_id=rep.user_id)
    assert entries == []

    logs = audit_service.query_logs(admin, entity_type="invoice", entity_id=invoice.id, action="commission_recording_failed")
    assert len(logs) == 1
    assert "simulated get_commission_plan_config failure" in logs[0].change_summary


def test_create_invoice_rejects_invalid_invoice_type(setup_services):
    _, auth_service, _, crm_service, _ = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin
    )
    with pytest.raises(ValueError):
        crm_service.create_invoice(
            Invoice(customer_id=cust.id, amount=100.0, invoice_type="bogus"), admin
        )
