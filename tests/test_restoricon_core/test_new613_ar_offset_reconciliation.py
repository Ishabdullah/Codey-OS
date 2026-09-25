"""
Unit tests for NEW-613 (fixed): the two AR aggregates that used to
disagree with FinanceService's own get_ar_aging/get_project_pnl on the
same underlying data --
AnalyticsSearchService.get_executive_dashboard's org-wide total_ar and
OperationsService.transition_project_stage's CLOSED-stage unpaid-balance
gate. Both are now wired through FinanceService's two internal,
no-actor helpers (get_ar_net_totals / get_project_ar_net) so each
reconciles to the corresponding FinanceService figure by construction.

Rule-6 correction: NEW-613's own ledger text originally named
get_project_pnl itself as a third missing site -- that was wrong,
get_project_pnl already had the full B8.8b-2 offset from the original
round. Only the two sites above were ever actually missing it.

Does NOT modify test_b8_8b2_financing_ar_offset.py, test_finance_service.py,
or any other pre-existing get_ar_aging/get_financial_summary/
get_project_pnl test file -- those are run UNMODIFIED as the pure-refactor
safety net proving the get_ar_net_totals/get_project_ar_net extraction
changed zero arithmetic.
"""

import pytest

from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, FinancingRecord, Invoice, Project, ProjectStage
from restoricon_core.services.analytics_search_service import AnalyticsSearchService
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.finance_service import FinanceService
from restoricon_core.services.financing_service import FinancingService
from restoricon_core.services.operations_service import OperationsService


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
    ops_service = OperationsService(db, audit_service, finance_service=finance_service)
    analytics_service = AnalyticsSearchService(db, crm_service=crm_service, finance_service=finance_service)
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    return {
        "db": db,
        "auth": auth_service,
        "audit": audit_service,
        "crm": crm_service,
        "finance": finance_service,
        "financing": financing_service,
        "ops": ops_service,
        "analytics": analytics_service,
        "admin": admin,
    }


def _make_project(crm_service, admin, email="new613_customer@test.com"):
    cust = crm_service.create_customer(
        Customer(first_name="Six", last_name="Thirteen", email=email), admin
    )
    project = crm_service.create_project(
        Project(customer_id=cust.id, title="NEW-613 Project", contract_amount=10000.0),
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
# (1) Reconciliation equality: executive dashboard vs get_ar_aging
# ==========================================


def test_executive_dashboard_total_ar_reconciles_with_ar_aging(setup_services):
    s = setup_services
    admin, crm, finance, financing, analytics = (
        s["admin"], s["crm"], s["finance"], s["financing"], s["analytics"]
    )
    cust, project = _make_project(crm, admin)
    inv = _make_invoice(crm, admin, cust, project, balance_due=5000.0)

    financing.create_financing_record(
        FinancingRecord(
            project_id=project.id, invoice_id=inv.id,
            application_status="approved", amount_financed=2000.0,
        ),
        admin,
    )

    dashboard = analytics.get_executive_dashboard(admin)
    aging = finance.get_ar_aging(admin)

    assert dashboard["financial"]["total_ar_outstanding"] == aging["total_ar"]
    assert dashboard["financial"]["total_ar_outstanding"] == 3000.0
    # Only total_ar_outstanding is replaced -- no new gross/offset keys
    # widening disclosure beyond PERM_READ_FINANCE holders.
    assert "total_ar_gross" not in dashboard["financial"]
    assert "total_financing_offset" not in dashboard["financial"]


def test_executive_dashboard_total_ar_zero_financing_unaffected(setup_services):
    s = setup_services
    admin, crm, finance, analytics = s["admin"], s["crm"], s["finance"], s["analytics"]
    cust, project = _make_project(crm, admin)
    _make_invoice(crm, admin, cust, project, balance_due=5000.0)

    dashboard = analytics.get_executive_dashboard(admin)
    aging = finance.get_ar_aging(admin)
    assert dashboard["financial"]["total_ar_outstanding"] == aging["total_ar"] == 5000.0


# ==========================================
# (2) CLOSED-gate behavior, both directions
# ==========================================


def _make_billed_project_with_invoice(crm, admin, db, balance_due=5000.0):
    cust, project = _make_project(crm, admin, email=f"closed_{balance_due}@test.com")
    inv = _make_invoice(crm, admin, cust, project, balance_due=balance_due)
    # Fast-forward the project straight to 'billed' -- can_transition only
    # allows billed -> closed, and walking the full lifecycle would drag
    # in unrelated gates (work orders, milestones) that have nothing to do
    # with this money-only test.
    conn = db.get_connection()
    with conn:
        conn.execute(
            "UPDATE projects SET stage = ?, status = 'completed' WHERE id = ?;",
            (ProjectStage.BILLED, project.id),
        )
    return cust, project, inv


def test_closed_gate_financing_fully_covers_balance_no_reason_needed(setup_services):
    s = setup_services
    admin, crm, financing, ops, db = s["admin"], s["crm"], s["financing"], s["ops"], s["db"]
    cust, project, inv = _make_billed_project_with_invoice(crm, admin, db, balance_due=3000.0)

    financing.create_financing_record(
        FinancingRecord(
            project_id=project.id, invoice_id=inv.id,
            application_status="approved", amount_financed=3000.0,
        ),
        admin,
    )

    # No reason passed -- must NOT raise, since financing fully covers the
    # outstanding balance (this is the intended behavior change: previously
    # this always required an override reason regardless of financing).
    closed = ops.transition_project_stage(project.id, ProjectStage.CLOSED, admin)
    assert closed.stage == ProjectStage.CLOSED


def test_closed_gate_financing_partially_covers_balance_still_requires_reason(setup_services):
    s = setup_services
    admin, crm, financing, ops, db = s["admin"], s["crm"], s["financing"], s["ops"], s["db"]
    cust, project, inv = _make_billed_project_with_invoice(crm, admin, db, balance_due=3000.0)

    financing.create_financing_record(
        FinancingRecord(
            project_id=project.id, invoice_id=inv.id,
            application_status="approved", amount_financed=1000.0,
        ),
        admin,
    )

    with pytest.raises(ValueError, match=r"outstanding balance of \$2000\.00"):
        ops.transition_project_stage(project.id, ProjectStage.CLOSED, admin)

    # With an override reason, it succeeds despite the remaining balance.
    closed = ops.transition_project_stage(
        project.id, ProjectStage.CLOSED, admin, reason="Manager override"
    )
    assert closed.stage == ProjectStage.CLOSED


def test_closed_gate_no_financing_still_requires_reason_unchanged(setup_services):
    """Regression: zero financing scenario is unaffected -- the gate
    behaves exactly as before NEW-613 when there is no financing at all."""
    s = setup_services
    admin, crm, ops, db = s["admin"], s["crm"], s["ops"], s["db"]
    cust, project, inv = _make_billed_project_with_invoice(crm, admin, db, balance_due=1500.0)

    with pytest.raises(ValueError, match=r"outstanding balance of \$1500\.00"):
        ops.transition_project_stage(project.id, ProjectStage.CLOSED, admin)

    closed = ops.transition_project_stage(
        project.id, ProjectStage.CLOSED, admin, reason="Write-off"
    )
    assert closed.stage == ProjectStage.CLOSED


# ==========================================
# (3) Ineligibility respected at both new sites
# ==========================================


def test_denied_financing_record_produces_zero_offset_at_both_sites(setup_services):
    s = setup_services
    admin, crm, financing, ops, analytics, db = (
        s["admin"], s["crm"], s["financing"], s["ops"], s["analytics"], s["db"]
    )

    # Site 1: executive dashboard -- exact equality, not just ">=", so a
    # wrongly-applied nonzero offset would actually fail this (a lenient
    # ">=" bound wouldn't catch it).
    cust1, project1 = _make_project(crm, admin, email="denied_dash@test.com")
    inv1 = _make_invoice(crm, admin, cust1, project1, balance_due=4000.0)
    financing.create_financing_record(
        FinancingRecord(
            project_id=project1.id, invoice_id=inv1.id,
            application_status="denied", amount_financed=2000.0,
        ),
        admin,
    )
    dashboard = analytics.get_executive_dashboard(admin)
    aging = s["finance"].get_ar_aging(admin)
    assert aging["total_financed_offset"] == 0.0
    assert dashboard["financial"]["total_ar_outstanding"] == aging["total_ar"] == 4000.0

    # Site 2: CLOSED gate
    cust2, project2, inv2 = _make_billed_project_with_invoice(crm, admin, db, balance_due=4000.0)
    financing.create_financing_record(
        FinancingRecord(
            project_id=project2.id, invoice_id=inv2.id,
            application_status="denied", amount_financed=2000.0,
        ),
        admin,
    )
    with pytest.raises(ValueError, match=r"outstanding balance of \$4000\.00"):
        ops.transition_project_stage(project2.id, ProjectStage.CLOSED, admin)


def test_voided_but_still_approved_financing_record_produces_zero_offset_at_both_sites(setup_services):
    """NEW-614 shape: voiding a financing_records row never clears its
    application_status, so eligibility must be status='active' AND
    application_status IN (...) TOGETHER, not application_status alone."""
    s = setup_services
    admin, crm, financing, ops, analytics, db = (
        s["admin"], s["crm"], s["financing"], s["ops"], s["analytics"], s["db"]
    )

    # Site 1: executive dashboard
    cust1, project1 = _make_project(crm, admin, email="voided_dash@test.com")
    inv1 = _make_invoice(crm, admin, cust1, project1, balance_due=4000.0)
    record1 = financing.create_financing_record(
        FinancingRecord(
            project_id=project1.id, invoice_id=inv1.id,
            application_status="approved", amount_financed=2000.0,
        ),
        admin,
    )
    financing.update_financing_record(record1.id, {"status": "voided"}, admin)
    refetched1 = financing.get_financing_record(record1.id, admin)
    assert refetched1.status == "voided"
    assert refetched1.application_status == "approved"  # NOT cleared by voiding

    dashboard = analytics.get_executive_dashboard(admin)
    aging = s["finance"].get_ar_aging(admin)
    assert aging["total_financed_offset"] == 0.0
    assert dashboard["financial"]["total_ar_outstanding"] == aging["total_ar"] == 4000.0

    # Site 2: CLOSED gate
    cust2, project2, inv2 = _make_billed_project_with_invoice(crm, admin, db, balance_due=4000.0)
    record2 = financing.create_financing_record(
        FinancingRecord(
            project_id=project2.id, invoice_id=inv2.id,
            application_status="approved", amount_financed=2000.0,
        ),
        admin,
    )
    financing.update_financing_record(record2.id, {"status": "voided"}, admin)

    with pytest.raises(ValueError, match=r"outstanding balance of \$4000\.00"):
        ops.transition_project_stage(project2.id, ProjectStage.CLOSED, admin)


# ==========================================
# (4) get_project_ar_net / get_ar_net_totals RBAC contract sanity
# ==========================================


def test_internal_helpers_are_not_actor_gated_by_design(setup_services):
    """Documents the deliberate RBAC exception these two helpers are --
    no actor param, callable only from already-authorized service-layer
    code (see each helper's own docstring for the full call-site list)."""
    s = setup_services
    finance = s["finance"]
    cust, project = _make_project(s["crm"], s["admin"], email="rbac_contract@test.com")

    # No actor arg accepted/required -- these are internal, not routable.
    totals = finance.get_ar_net_totals()
    assert "total_ar" in totals

    project_net = finance.get_project_ar_net(project.id)
    assert "total_outstanding" in project_net
