"""
Unit and integration tests for Global Search & Executive Reporting Analytics (Track B Phase B5a).
Tests multi-domain tokenized search, customer data isolation during search, and executive KPI aggregation.
"""

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_SALES,
    ROLE_SALES_MANAGER,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    Customer,
    FinancialTransaction,
    Lead,
    MarketingCampaign,
    Opportunity,
    Project,
    Vendor,
)
from restoricon_core.services.analytics_search_service import AnalyticsSearchService
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.business_ops_service import BusinessOpsService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.finance_service import FinanceService
from restoricon_core.services.operations_service import OperationsService


@pytest.fixture
def analytics_setup():
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    auth = AuthService(db)
    crm = CRMService(db, audit)
    ops = BusinessOpsService(db, audit)
    operations = OperationsService(db, audit)
    finance = FinanceService(db, audit)
    analytics = AnalyticsSearchService(db)

    admin_user = auth.create_user("admin_srch", "AdminPass123!", "Admin Srch", "admin_srch@test.com", ROLE_ADMIN)
    admin_ctx = AuthContext(user_id=admin_user.id, username=admin_user.username, role=ROLE_ADMIN, actor_type="human")

    sales_user = auth.create_user("sales_srch", "SalesPass123!", "Sales Srch", "sales_srch@test.com", ROLE_SALES)
    sales_ctx = AuthContext(user_id=sales_user.id, username=sales_user.username, role=ROLE_SALES, actor_type="human")

    # Customer 1 (Alice)
    cust1 = crm.create_customer(Customer(first_name="Alice", last_name="Johnson", email="alice@test.com", service_address="123 Maple Street"), admin_ctx)
    cust1_user = auth.create_user("cust_alice", "AlicePass123!", "Alice Johnson", "alice@test.com", ROLE_CUSTOMER, customer_id=cust1.id)
    cust1_ctx = AuthContext(user_id=cust1_user.id, username=cust1_user.username, role=ROLE_CUSTOMER, customer_id=cust1.id, actor_type="human")

    # Customer 2 (David)
    cust2 = crm.create_customer(Customer(first_name="David", last_name="Miller", email="david@test.com", service_address="456 Oak Avenue"), admin_ctx)
    cust2_user = auth.create_user("cust_david", "DavidPass123!", "David Miller", "david@test.com", ROLE_CUSTOMER, customer_id=cust2.id)
    cust2_ctx = AuthContext(user_id=cust2_user.id, username=cust2_user.username, role=ROLE_CUSTOMER, customer_id=cust2.id, actor_type="human")

    # Project for Alice
    proj1 = crm.create_project(
        Project(
            customer_id=cust1.id,
            title="Maple Street Flood Drying",
            property_address="123 Maple Street",
            contract_amount=12000.0,
            insurance_carrier="State Farm",
            stage="in_progress",
        ),
        admin_ctx,
    )

    # Project for David
    proj2 = crm.create_project(
        Project(
            customer_id=cust2.id,
            title="Oak Avenue Mold Remediation",
            property_address="456 Oak Avenue",
            contract_amount=8000.0,
            insurance_carrier="Allstate",
            stage="in_progress",
        ),
        admin_ctx,
    )

    # Vendor
    ops.create_vendor(Vendor(company_name="Maple Wood Restoration Supply"), admin_ctx)

    return {
        "db": db,
        "audit": audit,
        "auth": auth,
        "crm": crm,
        "ops": ops,
        "finance": finance,
        "analytics": analytics,
        "admin_ctx": admin_ctx,
        "sales_ctx": sales_ctx,
        "cust1_ctx": cust1_ctx,
        "cust2_ctx": cust2_ctx,
        "cust1": cust1,
        "cust2": cust2,
        "proj1": proj1,
        "proj2": proj2,
    }


def test_global_search_internal_admin(analytics_setup):
    search = analytics_setup["analytics"]
    admin_ctx = analytics_setup["admin_ctx"]

    # Search query "Maple" -> should match Customer (Alice on Maple St), Project (Maple St Flood Drying), and Vendor (Maple Wood Restoration Supply)
    res = search.global_search("Maple", admin_ctx)
    assert res["total_matches"] >= 3
    assert "customers" in res["results"]
    assert "projects" in res["results"]
    assert "vendors" in res["results"]
    assert res["results"]["customers"][0]["first_name"] == "Alice"
    assert res["results"]["projects"][0]["title"] == "Maple Street Flood Drying"
    assert res["results"]["vendors"][0]["company_name"] == "Maple Wood Restoration Supply"


def test_global_search_customer_isolation(analytics_setup):
    search = analytics_setup["analytics"]
    cust1_ctx = analytics_setup["cust1_ctx"]
    cust2_ctx = analytics_setup["cust2_ctx"]

    # Alice searches "Maple" -> should find HER project only, NOT vendor or internal entities
    res_alice = search.global_search("Maple", cust1_ctx)
    assert "projects" in res_alice["results"]
    assert len(res_alice["results"]["projects"]) == 1
    assert "vendors" not in res_alice["results"]
    assert "customers" not in res_alice["results"]

    # David searches "Maple" -> should find 0 results (since Maple belongs to Alice)
    res_david = search.global_search("Maple", cust2_ctx)
    assert res_david["total_matches"] == 0
    assert len(res_david["results"]) == 0


def test_executive_dashboard_kpis(analytics_setup):
    search = analytics_setup["analytics"]
    admin_ctx = analytics_setup["admin_ctx"]
    crm = analytics_setup["crm"]
    finance = analytics_setup["finance"]
    ops = analytics_setup["ops"]
    cust1 = analytics_setup["cust1"]

    # Add lead & opportunity
    crm.create_lead(Lead(customer_id=cust1.id, property_type="Residential", score=85), admin_ctx)
    crm.create_opportunity(Opportunity(customer_id=cust1.id, title="Basement Drying", estimated_value=5000.0, pipeline_stage="won"), admin_ctx)

    # Add transaction
    finance.record_transaction(FinancialTransaction(transaction_type="payment_received", amount=12000.0), admin_ctx)
    finance.record_transaction(FinancialTransaction(transaction_type="material_cost", amount=4000.0), admin_ctx)

    # Add campaign
    ops.create_campaign(MarketingCampaign(name="Local SEO", actual_spend=500.0, leads_generated=4), admin_ctx)

    dash = search.get_executive_dashboard(admin_ctx)
    assert dash["sales"]["hot_leads"] == 1
    assert dash["sales"]["win_rate_percent"] == 100.0
    assert dash["financial"]["total_revenue"] == 12000.0
    assert dash["financial"]["total_expenses"] == 4000.0
    assert dash["financial"]["net_profit"] == 8000.0
    assert dash["marketing"]["active_campaigns"] == 1
    assert dash["marketing"]["total_marketing_spend"] == 500.0


def test_global_search_leads_opportunities_rep_scoped(analytics_setup):
    """NEW-549: a plain sales rep's global_search must not leak other reps'
    leads/opportunities. Mirrors the rep-ownership narrowing
    CRMService.list_leads/list_opportunities already enforce."""
    search = analytics_setup["analytics"]
    auth = analytics_setup["auth"]
    crm = analytics_setup["crm"]
    admin_ctx = analytics_setup["admin_ctx"]
    sales_ctx = analytics_setup["sales_ctx"]
    cust1 = analytics_setup["cust1"]
    cust2 = analytics_setup["cust2"]

    rep_b_user = auth.create_user("sales_rep_b", "SalesPassB123!", "Sales Rep B", "sales_repb@test.com", ROLE_SALES)
    rep_b_ctx = AuthContext(user_id=rep_b_user.id, username=rep_b_user.username, role=ROLE_SALES, actor_type="human")

    # Rep A (sales_ctx) owns one lead/opportunity, Rep B owns another --
    # both mention "Restoration" so a single search term matches both.
    crm.create_lead(
        Lead(customer_id=cust1.id, property_type="Restoration", source="referral", assigned_user_id=sales_ctx.user_id),
        admin_ctx,
    )
    crm.create_lead(
        Lead(customer_id=cust2.id, property_type="Restoration", source="referral", assigned_user_id=rep_b_ctx.user_id),
        admin_ctx,
    )
    crm.create_opportunity(
        Opportunity(customer_id=cust1.id, title="Restoration Job A", estimated_value=1000.0, assigned_user_id=sales_ctx.user_id),
        admin_ctx,
    )
    crm.create_opportunity(
        Opportunity(customer_id=cust2.id, title="Restoration Job B", estimated_value=2000.0, assigned_user_id=rep_b_ctx.user_id),
        admin_ctx,
    )

    # Rep A searching "Restoration" sees only their own lead/opportunity.
    res_a = search.global_search("Restoration", sales_ctx)
    assert len(res_a["results"]["leads"]) == 1
    assert res_a["results"]["leads"][0]["assigned_user_id"] == sales_ctx.user_id
    assert len(res_a["results"]["opportunities"]) == 1
    assert res_a["results"]["opportunities"][0]["assigned_user_id"] == sales_ctx.user_id

    # Rep B searching "Restoration" sees only their own lead/opportunity.
    res_b = search.global_search("Restoration", rep_b_ctx)
    assert len(res_b["results"]["leads"]) == 1
    assert res_b["results"]["leads"][0]["assigned_user_id"] == rep_b_ctx.user_id
    assert len(res_b["results"]["opportunities"]) == 1
    assert res_b["results"]["opportunities"][0]["assigned_user_id"] == rep_b_ctx.user_id


def test_global_search_leads_opportunities_team_visibility_unscoped(analytics_setup):
    """An actor holding PERM_READ_TEAM_SALES_DATA (e.g. a sales manager)
    must still see all reps' leads/opportunities -- confirms this fix
    doesn't regress the existing team-visibility behavior."""
    search = analytics_setup["analytics"]
    auth = analytics_setup["auth"]
    crm = analytics_setup["crm"]
    admin_ctx = analytics_setup["admin_ctx"]
    sales_ctx = analytics_setup["sales_ctx"]
    cust1 = analytics_setup["cust1"]
    cust2 = analytics_setup["cust2"]

    rep_b_user = auth.create_user("sales_rep_b2", "SalesPassB123!", "Sales Rep B2", "sales_repb2@test.com", ROLE_SALES)
    rep_b_ctx = AuthContext(user_id=rep_b_user.id, username=rep_b_user.username, role=ROLE_SALES, actor_type="human")

    manager_user = auth.create_user("sales_mgr", "MgrPass123!", "Sales Manager", "sales_mgr@test.com", ROLE_SALES_MANAGER)
    manager_ctx = AuthContext(user_id=manager_user.id, username=manager_user.username, role=ROLE_SALES_MANAGER, actor_type="human")

    crm.create_lead(
        Lead(customer_id=cust1.id, property_type="Mitigation", source="referral", assigned_user_id=sales_ctx.user_id),
        admin_ctx,
    )
    crm.create_lead(
        Lead(customer_id=cust2.id, property_type="Mitigation", source="referral", assigned_user_id=rep_b_ctx.user_id),
        admin_ctx,
    )
    crm.create_opportunity(
        Opportunity(customer_id=cust1.id, title="Mitigation Job A", estimated_value=1000.0, assigned_user_id=sales_ctx.user_id),
        admin_ctx,
    )
    crm.create_opportunity(
        Opportunity(customer_id=cust2.id, title="Mitigation Job B", estimated_value=2000.0, assigned_user_id=rep_b_ctx.user_id),
        admin_ctx,
    )

    # Admin (unscoped by role/permissions elsewhere) still sees both.
    res_admin = search.global_search("Mitigation", admin_ctx)
    assert len(res_admin["results"]["leads"]) == 2
    assert len(res_admin["results"]["opportunities"]) == 2

    # Sales manager (holds PERM_READ_TEAM_SALES_DATA) sees both reps' records.
    res_mgr = search.global_search("Mitigation", manager_ctx)
    assert len(res_mgr["results"]["leads"]) == 2
    assert len(res_mgr["results"]["opportunities"]) == 2
