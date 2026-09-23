"""
Unit tests for B8.8b-2 (sales_rep_portal.md §4/§8): the financing_records
AR-offset wiring into FinanceService.get_ar_aging/get_financial_summary/
get_project_pnl (Ish decision 2026-09-23). Rule-4 money-computation round,
deliberately isolated from B8.8b-1's table + CRUD (already shipped,
tested in test_b8_8b1_financing_records.py). Written with the two
NEW-614 double-count shapes specifically in mind -- see (e) below.
"""

import pytest

from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, FinancingRecord, Invoice, Project
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.finance_service import FinanceService
from restoricon_core.services.financing_service import FinancingService


def _make_actor(auth_service, username, role, email=None):
    user = auth_service.create_user(
        username=username,
        plain_password="Password123",
        full_name=username.title(),
        email=email or f"{username}@test.com",
        role=role,
    )
    return AuthContext(user_id=user.id, username=username, role=role, actor_type="human")


@pytest.fixture
def setup_services():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)
    finance_service = FinanceService(db, audit_service)
    financing_service = FinancingService(db, audit_service)
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    return {
        "db": db,
        "auth": auth_service,
        "audit": audit_service,
        "crm": crm_service,
        "finance": finance_service,
        "financing": financing_service,
        "admin": admin,
    }


def _make_project(crm_service, admin, email="fin_customer@test.com"):
    cust = crm_service.create_customer(
        Customer(first_name="Fin", last_name="Ancing", email=email), admin
    )
    project = crm_service.create_project(
        Project(customer_id=cust.id, title="Financed Restoration", contract_amount=10000.0),
        admin,
    )
    return cust, project


def _make_invoice(crm_service, admin, cust, project, balance_due, status="sent", due_date="2099-01-01T00:00:00Z"):
    return crm_service.create_invoice(
        Invoice(
            customer_id=cust.id,
            project_id=project.id,
            amount=balance_due,
            balance_due=balance_due,
            due_date=due_date,
            status=status,
        ),
        admin,
    )


# ==========================================
# get_ar_aging offset wiring
# ==========================================


def test_ar_aging_nets_eligible_financing_against_invoice_balance(setup_services):
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    inv = _make_invoice(crm, admin, cust, project, balance_due=5000.0)

    financing.create_financing_record(
        FinancingRecord(
            project_id=project.id, invoice_id=inv.id,
            application_status="approved", amount_financed=2000.0,
        ),
        admin,
    )

    aging = finance.get_ar_aging(admin)
    row = next(d for d in aging["details"] if d["invoice_id"] == inv.id)
    assert row["balance_due"] == 5000.0
    assert row["financed_offset"] == 2000.0
    assert row["net_balance_due"] == 3000.0
    assert aging["total_ar_gross"] == 5000.0
    assert aging["total_financed_offset"] == 2000.0
    assert aging["total_ar"] == 3000.0
    assert aging["buckets"]["current"] == 3000.0


def test_ar_aging_over_financed_invoice_clamps_at_zero_not_negative(setup_services):
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    inv = _make_invoice(crm, admin, cust, project, balance_due=1000.0)

    financing.create_financing_record(
        FinancingRecord(
            project_id=project.id, invoice_id=inv.id,
            application_status="funded", amount_financed=5000.0,
        ),
        admin,
    )

    aging = finance.get_ar_aging(admin)
    row = next(d for d in aging["details"] if d["invoice_id"] == inv.id)
    assert row["net_balance_due"] == 0.0
    assert row["financed_offset"] == 1000.0  # clipped to balance_due, not the raw 5000
    assert aging["total_ar_gross"] == 1000.0
    assert aging["total_financed_offset"] == 1000.0
    assert aging["total_ar"] == 0.0
    assert aging["buckets"]["current"] == 0.0
    # reconciliation identity holds even in the clamp case
    assert round(aging["total_ar_gross"] - aging["total_financed_offset"], 2) == aging["total_ar"]


def test_ar_aging_customer_contribution_never_enters_offset(setup_services):
    """(c) customer_contribution must never reduce AR -- only amount_financed."""
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    inv = _make_invoice(crm, admin, cust, project, balance_due=5000.0)

    financing.create_financing_record(
        FinancingRecord(
            project_id=project.id, invoice_id=inv.id,
            application_status="approved", amount_financed=500.0,
            customer_contribution=4000.0,
        ),
        admin,
    )

    aging = finance.get_ar_aging(admin)
    row = next(d for d in aging["details"] if d["invoice_id"] == inv.id)
    assert row["financed_offset"] == 500.0
    assert row["net_balance_due"] == 4500.0


def test_ar_aging_denied_financing_record_does_not_offset(setup_services):
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    inv = _make_invoice(crm, admin, cust, project, balance_due=5000.0)

    financing.create_financing_record(
        FinancingRecord(
            project_id=project.id, invoice_id=inv.id,
            application_status="denied", amount_financed=2000.0,
        ),
        admin,
    )

    aging = finance.get_ar_aging(admin)
    row = next(d for d in aging["details"] if d["invoice_id"] == inv.id)
    assert row["financed_offset"] == 0.0
    assert row["net_balance_due"] == 5000.0


def test_ar_aging_live_reevaluates_when_status_changes_no_stale_cache(setup_services):
    """(b) A denied/cancelled/voided financing record's offset disappears
    on the very next read with no stale figure -- live re-evaluation."""
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    inv = _make_invoice(crm, admin, cust, project, balance_due=5000.0)

    record = financing.create_financing_record(
        FinancingRecord(
            project_id=project.id, invoice_id=inv.id,
            application_status="approved", amount_financed=2000.0,
        ),
        admin,
    )

    aging_before = finance.get_ar_aging(admin)
    row_before = next(d for d in aging_before["details"] if d["invoice_id"] == inv.id)
    assert row_before["net_balance_due"] == 3000.0

    financing.update_financing_record(record.id, {"status": "voided"}, admin)

    aging_after = finance.get_ar_aging(admin)
    row_after = next(d for d in aging_after["details"] if d["invoice_id"] == inv.id)
    assert row_after["financed_offset"] == 0.0
    assert row_after["net_balance_due"] == 5000.0
    assert aging_after["total_ar"] == 5000.0


def test_ar_aging_voided_approved_record_excluded_new_614_shape(setup_services):
    """(e) NEW-614 shape 2: a voided row can still carry
    application_status='approved' (voiding never clears it) -- must be
    excluded from the offset via status='active', not application_status
    alone. Write this test explicitly, don't just trust the WHERE clause."""
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    inv = _make_invoice(crm, admin, cust, project, balance_due=5000.0)

    record = financing.create_financing_record(
        FinancingRecord(
            project_id=project.id, invoice_id=inv.id,
            application_status="approved", amount_financed=2000.0,
        ),
        admin,
    )
    financing.update_financing_record(record.id, {"status": "voided"}, admin)

    refetched = financing.get_financing_record(record.id, admin)
    assert refetched.status == "voided"
    assert refetched.application_status == "approved"  # NOT cleared by voiding

    aging = finance.get_ar_aging(admin)
    row = next(d for d in aging["details"] if d["invoice_id"] == inv.id)
    assert row["financed_offset"] == 0.0
    assert row["net_balance_due"] == 5000.0


def test_ar_aging_null_invoice_id_financing_excluded_new_614_shape(setup_services):
    """(e) NEW-614 shape 1: a NULL-invoice_id eligible record has nothing
    to net against in get_ar_aging's invoice-scoped view -- excluded here
    (picked up instead by get_project_pnl's project-scoped offset)."""
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    inv = _make_invoice(crm, admin, cust, project, balance_due=5000.0)

    financing.create_financing_record(
        FinancingRecord(
            project_id=project.id, invoice_id=None,
            application_status="funded", amount_financed=2000.0,
        ),
        admin,
    )

    aging = finance.get_ar_aging(admin)
    row = next(d for d in aging["details"] if d["invoice_id"] == inv.id)
    assert row["financed_offset"] == 0.0
    assert row["net_balance_due"] == 5000.0


def test_ar_aging_partial_cash_payment_plus_financing_does_not_exceed_invoice_total(setup_services):
    """(a) A customer partially pays an invoice in cash (via the real
    CRMService.record_payment flow, which mutates balance_due exactly the
    way a live payment would) AND the remainder is financed -- the offset
    plus the cash payment together must not exceed the invoice's real
    total."""
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    total_invoice = 5000.0
    cash_paid = 2000.0
    inv = crm.create_invoice(
        Invoice(
            customer_id=cust.id, project_id=project.id,
            amount=total_invoice, balance_due=total_invoice,
            due_date="2099-01-01T00:00:00Z", status="sent",
        ),
        admin,
    )

    paid_inv = crm.record_payment(inv.id, cash_paid, "check", "CHK-1001", admin)
    assert paid_inv.balance_due == total_invoice - cash_paid  # 3000.0
    assert paid_inv.status == "partially_paid"

    financing.create_financing_record(
        FinancingRecord(
            project_id=project.id, invoice_id=inv.id,
            application_status="approved", amount_financed=paid_inv.balance_due,
        ),
        admin,
    )

    aging = finance.get_ar_aging(admin)
    row = next(d for d in aging["details"] if d["invoice_id"] == inv.id)
    assert row["balance_due"] == paid_inv.balance_due  # 3000.0, matches the real DB row
    assert row["net_balance_due"] == 0.0
    # cash_paid (already reflected outside balance_due, since record_payment
    # already reduced it) + financed offset together equal the invoice
    # total, never exceeding it
    assert cash_paid + row["financed_offset"] == total_invoice


def test_ar_aging_two_distinct_eligible_records_on_different_invoices_both_sum_correctly(setup_services):
    """(d) Confirm the offset query correctly sums whatever legitimately
    distinct eligible rows exist -- doesn't miss or double-sum a single
    valid row. (The DB-level unique index already blocks two eligible
    rows on the SAME invoice; this checks the query handles the
    multi-invoice, single-eligible-row-each case correctly.)"""
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    inv1 = _make_invoice(crm, admin, cust, project, balance_due=3000.0)
    inv2 = _make_invoice(crm, admin, cust, project, balance_due=4000.0)

    financing.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=inv1.id, application_status="approved", amount_financed=1000.0),
        admin,
    )
    financing.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=inv2.id, application_status="funded", amount_financed=1500.0),
        admin,
    )

    aging = finance.get_ar_aging(admin)
    row1 = next(d for d in aging["details"] if d["invoice_id"] == inv1.id)
    row2 = next(d for d in aging["details"] if d["invoice_id"] == inv2.id)
    assert row1["financed_offset"] == 1000.0
    assert row2["financed_offset"] == 1500.0
    assert aging["total_financed_offset"] == 2500.0
    assert aging["total_ar"] == 4500.0  # (3000-1000) + (4000-1500)


def test_ar_aging_zero_financing_scenarios_unaffected_additive_only(setup_services):
    """(f) Confirm the new offset logic is additive, not disruptive, for
    invoices with zero financing records."""
    s = setup_services
    admin, crm, finance = s["admin"], s["crm"], s["finance"]
    cust, project = _make_project(crm, admin)
    _make_invoice(crm, admin, cust, project, balance_due=5000.0)

    aging = finance.get_ar_aging(admin)
    assert aging["total_ar"] == 5000.0
    assert aging["total_ar_gross"] == 5000.0
    assert aging["total_financed_offset"] == 0.0


# ==========================================
# get_financial_summary offset wiring
# ==========================================


def test_financial_summary_carries_financing_offset_through(setup_services):
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    inv = _make_invoice(crm, admin, cust, project, balance_due=5000.0)

    financing.create_financing_record(
        FinancingRecord(
            project_id=project.id, invoice_id=inv.id,
            application_status="approved", amount_financed=2000.0,
        ),
        admin,
    )

    summary = finance.get_financial_summary(admin)
    assert summary["total_ar_outstanding"] == 3000.0
    assert summary["total_financing_offset"] == 2000.0
    assert summary["ar_buckets"]["current"] == 3000.0


# ==========================================
# get_project_pnl offset wiring (project-scoped, includes NULL invoice_id)
# ==========================================


def test_project_pnl_nets_financing_offset_project_scoped(setup_services):
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    _make_invoice(crm, admin, cust, project, balance_due=5000.0)

    financing.create_financing_record(
        FinancingRecord(
            project_id=project.id, invoice_id=None,
            application_status="funded", amount_financed=1500.0,
        ),
        admin,
    )

    pnl = finance.get_project_pnl(project.id, admin)
    assert pnl["total_outstanding_gross"] == 5000.0
    assert pnl["total_financing_offset"] == 1500.0
    assert pnl["total_outstanding"] == 3500.0


def test_project_pnl_sums_multiple_null_invoice_id_records_correctly(setup_services):
    """Multiple distinct NULL-invoice_id eligible rows for the same
    project are legitimate multi-lender financing -- summing them is
    correct, not the NEW-614 bug (which is about the DB not blocking
    duplicates, not about summing legitimately being wrong)."""
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    _make_invoice(crm, admin, cust, project, balance_due=10000.0)

    financing.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=None, application_status="approved", amount_financed=1000.0),
        admin,
    )
    financing.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=None, application_status="funded", amount_financed=2000.0),
        admin,
    )

    pnl = finance.get_project_pnl(project.id, admin)
    assert pnl["total_financing_offset"] == 3000.0
    assert pnl["total_outstanding"] == 7000.0


def test_project_pnl_clamps_at_zero_not_negative(setup_services):
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    _make_invoice(crm, admin, cust, project, balance_due=1000.0)

    financing.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=None, application_status="funded", amount_financed=5000.0),
        admin,
    )

    pnl = finance.get_project_pnl(project.id, admin)
    assert pnl["total_outstanding"] == 0.0
    assert pnl["total_outstanding_gross"] == 1000.0


def test_project_pnl_voided_approved_record_excluded(setup_services):
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    _make_invoice(crm, admin, cust, project, balance_due=5000.0)

    record = financing.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=None, application_status="approved", amount_financed=2000.0),
        admin,
    )
    financing.update_financing_record(record.id, {"status": "voided"}, admin)

    pnl = finance.get_project_pnl(project.id, admin)
    assert pnl["total_financing_offset"] == 0.0
    assert pnl["total_outstanding"] == 5000.0


def test_project_pnl_linked_financing_does_not_spill_onto_other_invoices_in_project(setup_services):
    """Misattribution guard: a financing record linked to invoice A must
    never offset invoice B's balance in the same project, even though the
    project-scoped offset sums across the whole project. Invoice A is
    already fully paid off in cash (balance_due=0, status='paid') but a
    stale 'approved' financing record is still linked to it -- that
    financing must be capped at A's own (zero) balance, not spill onto
    B's real outstanding balance."""
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    inv_a = crm.create_invoice(
        Invoice(
            customer_id=cust.id, project_id=project.id,
            amount=3000.0, balance_due=3000.0, status="sent",
            due_date="2099-01-01T00:00:00Z",
        ),
        admin,
    )
    # Pay inv_a off in full via the real payment flow -- create_invoice
    # itself recomputes balance_due = amount - deposit_amount, so a paid-off
    # invoice must be produced through record_payment, not constructed
    # directly with balance_due=0.
    inv_a = crm.record_payment(inv_a.id, 3000.0, "check", "CHK-2001", admin)
    assert inv_a.balance_due == 0.0
    assert inv_a.status == "paid"
    inv_b = _make_invoice(crm, admin, cust, project, balance_due=5000.0)

    financing.create_financing_record(
        FinancingRecord(
            project_id=project.id, invoice_id=inv_a.id,
            application_status="approved", amount_financed=3000.0,
        ),
        admin,
    )

    pnl = finance.get_project_pnl(project.id, admin)
    assert pnl["total_outstanding_gross"] == 5000.0  # inv_a=0 + inv_b=5000
    # linked_offset for inv_a is clamped to inv_a's own balance_due (0.0),
    # so it must NOT reduce inv_b's outstanding balance
    assert pnl["total_financing_offset"] == 0.0
    assert pnl["total_outstanding"] == 5000.0


def test_project_pnl_linked_offset_clamped_per_invoice_not_pooled(setup_services):
    """A financing record linked to a specific invoice can only offset
    THAT invoice's balance, even when pooled at project scope -- excess
    financing beyond one invoice's balance does not spill onto a sibling
    invoice in the same project."""
    s = setup_services
    admin, crm, finance, financing = s["admin"], s["crm"], s["finance"], s["financing"]
    cust, project = _make_project(crm, admin)
    inv_a = _make_invoice(crm, admin, cust, project, balance_due=1000.0)
    inv_b = _make_invoice(crm, admin, cust, project, balance_due=5000.0)

    # Over-financed against inv_a specifically (5000 financed, but inv_a's
    # own balance is only 1000)
    financing.create_financing_record(
        FinancingRecord(
            project_id=project.id, invoice_id=inv_a.id,
            application_status="funded", amount_financed=5000.0,
        ),
        admin,
    )

    pnl = finance.get_project_pnl(project.id, admin)
    assert pnl["total_outstanding_gross"] == 6000.0
    # capped at inv_a's own balance (1000), not the raw 5000 financed
    assert pnl["total_financing_offset"] == 1000.0
    assert pnl["total_outstanding"] == 5000.0  # inv_b's balance untouched


def test_project_pnl_zero_financing_unaffected_additive_only(setup_services):
    s = setup_services
    admin, crm, finance = s["admin"], s["crm"], s["finance"]
    cust, project = _make_project(crm, admin)
    _make_invoice(crm, admin, cust, project, balance_due=5000.0)

    pnl = finance.get_project_pnl(project.id, admin)
    assert pnl["total_outstanding"] == 5000.0
    assert pnl["total_outstanding_gross"] == 5000.0
    assert pnl["total_financing_offset"] == 0.0
