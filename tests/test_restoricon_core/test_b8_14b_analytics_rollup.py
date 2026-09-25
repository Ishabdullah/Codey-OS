"""
Unit tests for B8.14b: GET /api/v1/sales/analytics-rollup and
AnalyticsSearchService.get_sales_analytics_rollup (sales_rep_portal.md's
B8.14 exit criterion -- "three permission-gated views of the same
underlying aggregation query").

Covers:
- rep-tier: a plain sales rep's response excludes any other rep's
  pipeline/commission figures, same as get_pipeline_summary/
  get_team_commission_summary already enforce today.
- executive-tier gating: a `sales`-role actor without
  PERM_READ_TEAM_SALES_DATA cannot reach the executive tier (reuses
  B8.14a/NEW-550's now-fixed AND-composed gate on get_executive_dashboard).
- manager-tier: an actor holding PERM_READ_TEAM_SALES_DATA and/or
  PERM_READ_TEAM_COMMISSIONS (but not PERM_VIEW_REPORTS, so NOT executive)
  gets team-wide pipeline/commission data.
- executive-tier: an actor holding both PERM_VIEW_REPORTS and
  PERM_READ_TEAM_SALES_DATA gets the executive dashboard shape, WITHOUT
  a "financial" block (NEW-613: no AR/revenue figure in this rollup).
- every CRM-permissioned actor (holds PERM_READ_OPPORTUNITIES or
  PERM_READ_CRM) gets some tier and the method itself never raises for
  them. An actor holding NEITHER (ROLE_TECHNICIAN, ROLE_CUSTOMER) DOES
  hit get_pipeline_summary's own PermissionError on the rep/manager
  branch -- this is the correct "no new data exposure" outcome (they
  can't see pipeline data via get_pipeline_summary directly either), and
  the route maps it to a controlled 403, not a raw 500 or leaked data.
"""

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_READ_TEAM_COMMISSIONS,
    PERM_READ_TEAM_SALES_DATA,
    PERM_VIEW_REPORTS,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_SALES,
    ROLE_SALES_MANAGER,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import CommissionLedgerEntry, Customer, Opportunity
from restoricon_core.services.analytics_search_service import AnalyticsSearchService
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.commission_service import CommissionService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.scheduling_service import SchedulingService


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    comm = CommunicationService(db)
    crm = CRMService(db, audit)
    sched = SchedulingService(db, audit)
    auto = AutomationService(db, audit)
    commissions = CommissionService(db, audit)
    analytics = AnalyticsSearchService(db, crm_service=crm, commission_service=commissions)
    router = APIRouter(
        auth, crm, comm, audit, sched, auto,
        commission_service=commissions,
        analytics_search_service=analytics,
    )

    admin_user = auth.create_user("admin_user", "Pass123!", "Admin User", "admin@test.com", ROLE_ADMIN)
    admin_actor = AuthContext(admin_user.id, "admin_user", ROLE_ADMIN, "human")

    rep_a_user = auth.create_user("rep_a", "Pass123!", "Rep A", "repa@test.com", ROLE_SALES)
    rep_a_actor = AuthContext(rep_a_user.id, "rep_a", ROLE_SALES, "human")

    rep_b_user = auth.create_user("rep_b", "Pass123!", "Rep B", "repb@test.com", ROLE_SALES)
    rep_b_actor = AuthContext(rep_b_user.id, "rep_b", ROLE_SALES, "human")

    mgr_user = auth.create_user("sales_mgr", "Pass123!", "Sales Mgr", "mgr@test.com", ROLE_SALES_MANAGER)
    mgr_actor = AuthContext(mgr_user.id, "sales_mgr", ROLE_SALES_MANAGER, "human")

    # Split-grant actor (NEW-533/NEW-637 precedent): PERM_READ_TEAM_SALES_DATA
    # WITHOUT PERM_VIEW_REPORTS -- every built-in role pairs these, so only
    # a custom_permissions grant produces this split. Confirms manager tier
    # is reachable independently of the executive tier's AND-gate.
    manager_only_custom_perms = {PERM_READ_TEAM_SALES_DATA: True, PERM_VIEW_REPORTS: False}
    manager_only_user = auth.create_user(
        "manager_only_rep", "Pass123!", "Manager Only Rep", "mgronly@test.com", ROLE_SALES,
        custom_permissions=manager_only_custom_perms,
    )
    manager_only_actor = AuthContext(
        manager_only_user.id, "manager_only_rep", ROLE_SALES, "human",
        custom_permissions=manager_only_custom_perms,
    )

    # Neither PERM_READ_OPPORTUNITIES nor PERM_READ_CRM -- confirms the
    # rep/manager branch's delegation to get_pipeline_summary correctly
    # 403s these roles rather than silently widening their visibility.
    tech_user = auth.create_user("tech_a", "Pass123!", "Tech A", "techa@test.com", ROLE_TECHNICIAN)
    tech_actor = AuthContext(tech_user.id, "tech_a", ROLE_TECHNICIAN, "human")

    cust = crm.create_customer(Customer(first_name="Test", last_name="Cust", email="cust@test.com"), admin_actor)
    cust_user = auth.create_user(
        "cust_a", "Pass123!", "Cust A", "custa@test.com", ROLE_CUSTOMER, customer_id=cust.id,
    )
    cust_actor = AuthContext(cust_user.id, "cust_a", ROLE_CUSTOMER, "human", customer_id=cust.id)

    opp_a = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Opp A", estimated_value=1000.0, probability=0.5, assigned_user_id=rep_a_user.id),
        admin_actor,
    )
    opp_b = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Opp B", estimated_value=2000.0, probability=0.5, assigned_user_id=rep_b_user.id),
        admin_actor,
    )

    commissions.record_commission(
        CommissionLedgerEntry(rep_user_id=rep_a_user.id, source_type="assessment", commission_amount=100.0, status="earned"),
        admin_actor,
    )
    commissions.record_commission(
        CommissionLedgerEntry(rep_user_id=rep_b_user.id, source_type="assessment", commission_amount=250.0, status="earned"),
        admin_actor,
    )

    return {
        "db": db,
        "router": router,
        "auth": auth,
        "analytics": analytics,
        "admin_actor": admin_actor,
        "admin_user": admin_user,
        "rep_a_actor": rep_a_actor,
        "rep_a_user": rep_a_user,
        "rep_b_actor": rep_b_actor,
        "rep_b_user": rep_b_user,
        "mgr_actor": mgr_actor,
        "mgr_user": mgr_user,
        "manager_only_actor": manager_only_actor,
        "manager_only_user": manager_only_user,
        "tech_actor": tech_actor,
        "tech_user": tech_user,
        "cust_actor": cust_actor,
        "cust_user": cust_user,
    }


def test_rep_tier_excludes_other_reps_data(env):
    """A plain sales rep's rollup must not leak another rep's pipeline or
    commission figures -- same narrowing get_pipeline_summary/
    get_team_commission_summary already enforce independently."""
    analytics = env["analytics"]
    rep_a_actor = env["rep_a_actor"]
    rep_a_user = env["rep_a_user"]

    result = analytics.get_sales_analytics_rollup(rep_a_actor)
    assert result["tier"] == "rep"

    # Pipeline: rep A's own opportunity only (Opp A, $1000), not Opp B's $2000.
    pl = result["pipeline"]
    assert pl["total_deals"] == 1
    assert pl["active_pipeline_value"] == 1000.0

    # Commissions: rep A's own $100 entry only, not rep B's $250.
    commission_rows = result["commissions"]
    assert len(commission_rows) == 1
    assert commission_rows[0]["rep_user_id"] == rep_a_user.id
    assert commission_rows[0]["total_earned"] == 100.0

    assert "note" in result
    assert "executive" not in result


def test_executive_tier_gated_sales_role_without_team_perm_denied(env):
    """A plain `sales`-role actor (holds PERM_VIEW_REPORTS by default, but
    NOT PERM_READ_TEAM_SALES_DATA) must NOT reach the executive tier --
    reuses B8.14a/NEW-550's fix on get_executive_dashboard. It should land
    in the rep tier instead, not raise, and not receive team-wide data."""
    analytics = env["analytics"]
    rep_a_actor = env["rep_a_actor"]
    assert rep_a_actor.has_permission(PERM_VIEW_REPORTS)
    assert not rep_a_actor.has_permission(PERM_READ_TEAM_SALES_DATA)

    result = analytics.get_sales_analytics_rollup(rep_a_actor)
    assert result["tier"] != "executive"
    assert result["tier"] == "rep"
    assert "executive" not in result


def test_manager_tier_split_grant_without_view_reports(env):
    """PERM_READ_TEAM_SALES_DATA without PERM_VIEW_REPORTS lands in the
    manager tier (team-wide pipeline/commissions), not executive."""
    analytics = env["analytics"]
    manager_only_actor = env["manager_only_actor"]
    assert manager_only_actor.has_permission(PERM_READ_TEAM_SALES_DATA)
    assert not manager_only_actor.has_permission(PERM_VIEW_REPORTS)

    result = analytics.get_sales_analytics_rollup(manager_only_actor)
    assert result["tier"] == "manager"
    assert "executive" not in result

    # Team-wide: both opportunities visible.
    pl = result["pipeline"]
    assert pl["total_deals"] == 2
    assert pl["active_pipeline_value"] == 3000.0

    # Manager tier only widens the pipeline axis here (PERM_READ_TEAM_
    # COMMISSIONS not granted) -- commissions stay narrowed to this
    # actor's own user_id, which has no ledger entries of its own.
    assert result["commissions"] == []


def test_executive_tier_requires_both_perms(env):
    """Both PERM_VIEW_REPORTS and PERM_READ_TEAM_SALES_DATA (sales_manager
    role) reach the executive tier and get get_executive_dashboard's shape,
    MINUS its "financial" block (NEW-613: no AR/revenue figure in this
    rollup) -- confirms this projection, not the raw unmodified dashboard."""
    analytics = env["analytics"]
    mgr_actor = env["mgr_actor"]
    assert mgr_actor.has_permission(PERM_VIEW_REPORTS)
    assert mgr_actor.has_permission(PERM_READ_TEAM_SALES_DATA)

    result = analytics.get_sales_analytics_rollup(mgr_actor)
    assert result["tier"] == "executive"
    assert "sales" in result["executive"]
    assert "operations" in result["executive"]
    assert "financial" not in result["executive"]
    assert "pipeline" not in result
    assert "commissions" not in result

    # The underlying get_executive_dashboard call itself is untouched --
    # only this rollup's own response projects "financial" out.
    raw_dashboard = analytics.get_executive_dashboard(mgr_actor)
    assert "financial" in raw_dashboard


def test_admin_reaches_executive_tier(env):
    analytics = env["analytics"]
    admin_actor = env["admin_actor"]
    result = analytics.get_sales_analytics_rollup(admin_actor)
    assert result["tier"] == "executive"


def test_route_gets_rep_tier_for_plain_rep(env):
    """GET /api/v1/sales/analytics-rollup end-to-end for a plain rep."""
    router = env["router"]
    auth = env["auth"]
    token = auth.create_token(env["rep_a_user"])
    status, headers, body = router.handle_request(
        "GET", "/api/v1/sales/analytics-rollup", {"Authorization": f"Bearer {token}"}, b""
    )
    assert status == 200
    assert body["tier"] == "rep"
    assert body["pipeline"]["total_deals"] == 1


def test_route_gets_executive_tier_for_admin(env):
    router = env["router"]
    auth = env["auth"]
    token = auth.create_token(env["admin_user"])
    status, headers, body = router.handle_request(
        "GET", "/api/v1/sales/analytics-rollup", {"Authorization": f"Bearer {token}"}, b""
    )
    assert status == 200
    assert body["tier"] == "executive"
    assert "executive" in body


def test_route_never_403s_for_a_crm_permissioned_actor(env):
    """Every actor who holds PERM_READ_OPPORTUNITIES or PERM_READ_CRM
    (i.e. can call get_pipeline_summary at all) gets SOME tier from this
    route, never a 403."""
    router = env["router"]
    auth = env["auth"]
    users = [
        env["rep_a_user"], env["rep_b_user"], env["mgr_user"],
        env["manager_only_user"], env["admin_user"],
    ]
    for user in users:
        token = auth.create_token(user)
        status, headers, body = router.handle_request(
            "GET", "/api/v1/sales/analytics-rollup", {"Authorization": f"Bearer {token}"}, b""
        )
        assert status == 200, f"{user.username} got {status}: {body}"
        assert body["tier"] in ("rep", "manager", "executive")


def test_route_403s_for_technician_not_500_or_leaked_data(env):
    """ROLE_TECHNICIAN holds neither PERM_READ_OPPORTUNITIES nor
    PERM_READ_CRM, so the rep-tier branch's delegation to
    CRMService.get_pipeline_summary raises PermissionError -- the route's
    existing `except PermissionError` handler must turn that into a
    controlled 403, not a raw 500, and no pipeline/commission data must
    leak through beforehand."""
    router = env["router"]
    auth = env["auth"]
    token = auth.create_token(env["tech_user"])
    status, headers, body = router.handle_request(
        "GET", "/api/v1/sales/analytics-rollup", {"Authorization": f"Bearer {token}"}, b""
    )
    assert status == 403
    assert "pipeline" not in body
    assert "commissions" not in body


def test_route_403s_for_customer_not_500_or_leaked_data(env):
    """Same as the technician case, for ROLE_CUSTOMER."""
    router = env["router"]
    auth = env["auth"]
    token = auth.create_token(env["cust_user"])
    status, headers, body = router.handle_request(
        "GET", "/api/v1/sales/analytics-rollup", {"Authorization": f"Bearer {token}"}, b""
    )
    assert status == 403
    assert "pipeline" not in body
    assert "commissions" not in body


def test_service_raises_permission_error_for_technician(env):
    """Direct-call confirmation (not just the route-level 403) that the
    method itself raises for a non-CRM-permissioned actor, matching
    get_pipeline_summary's own documented behavior."""
    analytics = env["analytics"]
    tech_actor = env["tech_actor"]
    with pytest.raises(PermissionError):
        analytics.get_sales_analytics_rollup(tech_actor)
