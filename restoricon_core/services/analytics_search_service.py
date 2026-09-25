"""
Global Search & Executive Reporting Analytics Service for Restoricon Core (Track B Phase B5a).
Provides:
- Multi-domain fuzzy/tokenized global search across all 12 system entities with strict customer data isolation.
- Cross-domain executive KPI analytics dashboard spanning Sales, Operations, Finance, Marketing, and Compliance.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..auth import (
    AuthContext,
    PERM_GLOBAL_SEARCH,
    PERM_READ_TEAM_COMMISSIONS,
    PERM_READ_TEAM_SALES_DATA,
    PERM_VIEW_REPORTS,
    ROLE_CUSTOMER,
)
from ..database import DatabaseManager
from .audit_service import AuditService
from .commission_service import CommissionService
from .crm_service import CRMService
from .finance_service import FinanceService

# B8.14: documents the known cross-tier reconciliation quirk in
# get_sales_analytics_rollup's rep/manager-tier response so a future
# reader doesn't mistake the divergence for a bug (see that method's
# docstring for the full explanation).
_ROLLUP_RECONCILIATION_NOTE = (
    "Pipeline figures include unclaimed-pool leniency (an actor without "
    "PERM_READ_TEAM_SALES_DATA sees rows with assigned_user_id = them OR "
    "NULL -- CRMService._scoped_assignee_filter, NEW-608, open, fail-open "
    "by design) while commission figures use a strict fail-closed filter "
    "(CommissionService._scoped_rep_filter). The pipeline and commission "
    "sections of this response will NOT arithmetically reconcile row-for-"
    "row against each other for that reason -- this is a known, accepted "
    "divergence between the two underlying scoping rules, not a bug in "
    "this rollup."
)


class AnalyticsSearchService:
    """Provides unified cross-domain search and executive KPI aggregation."""

    def __init__(
        self,
        db: DatabaseManager,
        crm_service: Optional[CRMService] = None,
        commission_service: Optional[CommissionService] = None,
        finance_service: Optional[FinanceService] = None,
    ):
        self.db = db
        # B8.14: lazily default-constructed only when not supplied, mirroring
        # CRMService's own `commission_service or CommissionService(self.db,
        # audit_service)` pattern (crm_service.py:206) -- callers that wire
        # real app services (api/server.py) should pass the actual shared
        # instances rather than letting this service default-construct its
        # own separate ones. These are used by get_sales_analytics_rollup
        # below (read-only calls) and, as of NEW-613, also by
        # get_executive_dashboard's total_ar figure
        # (self._finance_service.get_ar_net_totals(), also read-only, never
        # writes/audits), so a fresh, never-written-to AuditService is safe
        # for every lazy-default path here.
        self._crm_service = crm_service or CRMService(db, AuditService(db))
        self._commission_service = commission_service or CommissionService(db, AuditService(db))
        # NEW-613: FinanceService.get_ar_net_totals() is an internal,
        # no-actor helper (see its own docstring for the RBAC contract) --
        # only called from get_executive_dashboard below, itself already
        # gated on PERM_VIEW_REPORTS + PERM_READ_TEAM_SALES_DATA.
        self._finance_service = finance_service or FinanceService(db, AuditService(db))

    def global_search(
        self,
        query: str,
        actor: AuthContext,
        limit_per_category: int = 10,
    ) -> Dict[str, Any]:
        """
        Execute unified global search across all business entities.
        Enforces strict customer data isolation for customer actors.
        """
        if not actor.has_permission(PERM_GLOBAL_SEARCH):
            raise PermissionError("Actor lacks permission for global search")

        q_clean = query.strip()
        if not q_clean:
            return {"query": "", "total_matches": 0, "results": {}}

        like_pattern = f"%{q_clean}%"
        conn = self.db.get_connection()
        results: Dict[str, List[Dict[str, Any]]] = {}
        total_count = 0

        # Customer role can ONLY view their own records (projects, estimates, contracts, invoices)
        if actor.role == ROLE_CUSTOMER:
            cust_id = actor.customer_id
            if not cust_id:
                return {"query": q_clean, "total_matches": 0, "results": {}}

            # Projects
            proj_rows = conn.execute(
                """
                SELECT id, title, stage, status, property_address, created_at
                FROM projects
                WHERE customer_id = ? AND (title LIKE ? OR property_address LIKE ?)
                LIMIT ?;
                """,
                (cust_id, like_pattern, like_pattern, limit_per_category),
            ).fetchall()
            results["projects"] = [dict(r) for r in proj_rows]
            total_count += len(results["projects"])

            # Estimates
            est_rows = conn.execute(
                """
                SELECT id, estimate_number, project_id, status, total_amount, created_at
                FROM estimates
                WHERE customer_id = ? AND (estimate_number LIKE ? OR notes LIKE ?)
                LIMIT ?;
                """,
                (cust_id, like_pattern, like_pattern, limit_per_category),
            ).fetchall()
            results["estimates"] = [dict(r) for r in est_rows]
            total_count += len(results["estimates"])

            # Contracts
            con_rows = conn.execute(
                """
                SELECT id, contract_number, project_id, title, status, created_at
                FROM contracts
                WHERE customer_id = ? AND (contract_number LIKE ? OR title LIKE ?)
                LIMIT ?;
                """,
                (cust_id, like_pattern, like_pattern, limit_per_category),
            ).fetchall()
            results["contracts"] = [dict(r) for r in con_rows]
            total_count += len(results["contracts"])

            # Invoices
            inv_rows = conn.execute(
                """
                SELECT id, invoice_number, project_id, status, amount, balance_due, due_date
                FROM invoices
                WHERE customer_id = ? AND (invoice_number LIKE ? OR notes LIKE ?)
                LIMIT ?;
                """,
                (cust_id, like_pattern, like_pattern, limit_per_category),
            ).fetchall()
            results["invoices"] = [dict(r) for r in inv_rows]
            total_count += len(results["invoices"])

            return {
                "query": q_clean,
                "total_matches": total_count,
                "results": {k: v for k, v in results.items() if v},
            }

        # Internal roles: search across all business entities
        # 1. Customers
        c_rows = conn.execute(
            """
            SELECT id, first_name, last_name, email, phone, service_address, customer_source, status
            FROM customers
            WHERE first_name LIKE ? OR last_name LIKE ? OR email LIKE ? OR phone LIKE ? OR service_address LIKE ?
            LIMIT ?;
            """,
            (like_pattern, like_pattern, like_pattern, like_pattern, like_pattern, limit_per_category),
        ).fetchall()
        results["customers"] = [dict(r) for r in c_rows]
        total_count += len(results["customers"])

        # 2. Leads
        # NEW-549: leads/opportunities need the same rep-ownership narrowing
        # CRMService.list_leads/list_opportunities already apply (see
        # CRMService._scoped_assignee_filter) -- an actor without
        # PERM_READ_TEAM_SALES_DATA must only see their own assigned rows
        # (plus unclaimed/NULL rows, same unclaimed-pool visibility rule),
        # not every rep's records. Holders of PERM_READ_TEAM_SALES_DATA keep
        # today's unscoped, company-wide search behavior.
        l_query = """
            SELECT id, customer_id, assigned_user_id, source, status, property_type, urgency_level, score
            FROM leads
            WHERE (property_type LIKE ? OR notes LIKE ? OR source LIKE ?)
        """
        l_params: List[Any] = [like_pattern, like_pattern, like_pattern]
        if not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            l_query += " AND (assigned_user_id = ? OR assigned_user_id IS NULL)"
            l_params.append(actor.user_id)
        l_query += " LIMIT ?;"
        l_params.append(limit_per_category)
        l_rows = conn.execute(l_query, l_params).fetchall()
        results["leads"] = [dict(r) for r in l_rows]
        total_count += len(results["leads"])

        # 3. Opportunities
        opp_query = """
            SELECT id, customer_id, assigned_user_id, title, pipeline_stage, estimated_value, insurance_carrier
            FROM opportunities
            WHERE (title LIKE ? OR insurance_carrier LIKE ? OR notes LIKE ?)
        """
        opp_params: List[Any] = [like_pattern, like_pattern, like_pattern]
        if not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            opp_query += " AND (assigned_user_id = ? OR assigned_user_id IS NULL)"
            opp_params.append(actor.user_id)
        opp_query += " LIMIT ?;"
        opp_params.append(limit_per_category)
        opp_rows = conn.execute(opp_query, opp_params).fetchall()
        results["opportunities"] = [dict(r) for r in opp_rows]
        total_count += len(results["opportunities"])

        # 4. Projects
        p_rows = conn.execute(
            """
            SELECT id, customer_id, title, stage, status, property_address, insurance_carrier
            FROM projects
            WHERE title LIKE ? OR property_address LIKE ? OR insurance_carrier LIKE ?
            LIMIT ?;
            """,
            (like_pattern, like_pattern, like_pattern, limit_per_category),
        ).fetchall()
        results["projects"] = [dict(r) for r in p_rows]
        total_count += len(results["projects"])

        # 5. Estimates
        e_rows = conn.execute(
            """
            SELECT id, estimate_number, customer_id, project_id, status, total_amount
            FROM estimates
            WHERE estimate_number LIKE ? OR notes LIKE ?
            LIMIT ?;
            """,
            (like_pattern, like_pattern, limit_per_category),
        ).fetchall()
        results["estimates"] = [dict(r) for r in e_rows]
        total_count += len(results["estimates"])

        # 6. Contracts
        ctr_rows = conn.execute(
            """
            SELECT id, contract_number, customer_id, project_id, title, status
            FROM contracts
            WHERE contract_number LIKE ? OR title LIKE ?
            LIMIT ?;
            """,
            (like_pattern, like_pattern, limit_per_category),
        ).fetchall()
        results["contracts"] = [dict(r) for r in ctr_rows]
        total_count += len(results["contracts"])

        # 7. Invoices
        i_rows = conn.execute(
            """
            SELECT id, invoice_number, customer_id, project_id, status, amount, balance_due, due_date
            FROM invoices
            WHERE invoice_number LIKE ? OR notes LIKE ?
            LIMIT ?;
            """,
            (like_pattern, like_pattern, limit_per_category),
        ).fetchall()
        results["invoices"] = [dict(r) for r in i_rows]
        total_count += len(results["invoices"])

        # 8. Work Orders
        wo_rows = conn.execute(
            """
            SELECT id, work_order_number, project_id, trade, status, title, assigned_crew_lead
            FROM work_orders
            WHERE work_order_number LIKE ? OR title LIKE ? OR instructions LIKE ? OR trade LIKE ?
            LIMIT ?;
            """,
            (like_pattern, like_pattern, like_pattern, like_pattern, limit_per_category),
        ).fetchall()
        results["work_orders"] = [dict(r) for r in wo_rows]
        total_count += len(results["work_orders"])

        # 9. Subcontractors
        sub_rows = conn.execute(
            """
            SELECT id, company_name, contact_name, primary_trade, phone, email
            FROM subcontractors
            WHERE company_name LIKE ? OR contact_name LIKE ? OR primary_trade LIKE ? OR email LIKE ? OR phone LIKE ?
            LIMIT ?;
            """,
            (like_pattern, like_pattern, like_pattern, like_pattern, like_pattern, limit_per_category),
        ).fetchall()
        results["subcontractors"] = [dict(r) for r in sub_rows]
        total_count += len(results["subcontractors"])

        # 10. Vendors
        v_rows = conn.execute(
            """
            SELECT id, company_name, contact_name, category, phone, email
            FROM vendors
            WHERE company_name LIKE ? OR contact_name LIKE ? OR category LIKE ? OR email LIKE ?
            LIMIT ?;
            """,
            (like_pattern, like_pattern, like_pattern, like_pattern, limit_per_category),
        ).fetchall()
        results["vendors"] = [dict(r) for r in v_rows]
        total_count += len(results["vendors"])

        # 11. Employees
        emp_rows = conn.execute(
            """
            SELECT id, first_name, last_name, role_title, department, phone, email, status
            FROM employees
            WHERE first_name LIKE ? OR last_name LIKE ? OR role_title LIKE ? OR email LIKE ? OR phone LIKE ?
            LIMIT ?;
            """,
            (like_pattern, like_pattern, like_pattern, like_pattern, like_pattern, limit_per_category),
        ).fetchall()
        results["employees"] = [dict(r) for r in emp_rows]
        total_count += len(results["employees"])

        # 12. Compliance Items
        comp_rows = conn.execute(
            """
            SELECT id, title, category, entity_type, license_number, expiration_date, status
            FROM compliance_items
            WHERE title LIKE ? OR category LIKE ? OR license_number LIKE ? OR issuer LIKE ?
            LIMIT ?;
            """,
            (like_pattern, like_pattern, like_pattern, like_pattern, limit_per_category),
        ).fetchall()
        results["compliance"] = [dict(r) for r in comp_rows]
        total_count += len(results["compliance"])

        return {
            "query": q_clean,
            "total_matches": total_count,
            "results": {k: v for k, v in results.items() if v},
        }

    def get_executive_dashboard(self, actor: AuthContext) -> Dict[str, Any]:
        """Compute aggregated executive analytics dashboard across all domains."""
        # NEW-550: this method has no per-rep scoping mode -- every query
        # below is inherently company-wide, unlike the assignee-filtered
        # queries elsewhere in this file (see PERM_READ_TEAM_SALES_DATA
        # narrowing above). Gating on PERM_VIEW_REPORTS alone let any
        # ROLE_SALES actor (which holds PERM_VIEW_REPORTS by default) pull
        # every rep's company-wide pipeline/lead/win-rate aggregates via
        # /api/v1/reports/summary and /api/v1/reports/executive, which call
        # this method directly with no route-level gate of their own.
        # AND-composing with PERM_READ_TEAM_SALES_DATA closes that: a caller
        # now needs both permissions, same as /api/v1/sales/dashboard's
        # "team" block already required independently (routes.py ~3362).
        if not actor.has_permission(PERM_VIEW_REPORTS) or not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            raise PermissionError("Actor lacks permission to view executive reports")

        conn = self.db.get_connection()

        # 1. CRM & Sales KPIs
        leads_stat = conn.execute(
            """
            SELECT COUNT(*) as total_leads,
                   SUM(CASE WHEN score >= 80 THEN 1 ELSE 0 END) as hot_leads,
                   SUM(CASE WHEN status = 'new' THEN 1 ELSE 0 END) as new_leads
            FROM leads;
            """
        ).fetchone()

        opps_stat = conn.execute(
            """
            SELECT COUNT(*) as total_opps,
                   COALESCE(SUM(estimated_value), 0.0) as total_pipeline_val,
                   COALESCE(SUM(estimated_value * probability), 0.0) as weighted_val,
                   SUM(CASE WHEN pipeline_stage = 'won' THEN 1 ELSE 0 END) as won_count,
                   SUM(CASE WHEN pipeline_stage = 'lost' THEN 1 ELSE 0 END) as lost_count
            FROM opportunities;
            """
        ).fetchone()

        won_c = opps_stat["won_count"] or 0
        lost_c = opps_stat["lost_count"] or 0
        closed_total = won_c + lost_c
        win_rate = (won_c / closed_total * 100.0) if closed_total > 0 else 0.0

        # 2. Operations KPIs
        proj_stat = conn.execute(
            """
            SELECT COUNT(*) as total_projects,
                   SUM(CASE WHEN stage NOT IN ('closed', 'cancelled') THEN 1 ELSE 0 END) as active_projects,
                   SUM(CASE WHEN stage = 'in_progress' THEN 1 ELSE 0 END) as in_progress_projects,
                   SUM(CASE WHEN stage = 'closed' THEN 1 ELSE 0 END) as completed_projects
            FROM projects;
            """
        ).fetchone()

        wo_stat = conn.execute(
            """
            SELECT COUNT(*) as total_wo,
                   SUM(CASE WHEN status IN ('dispatched', 'accepted', 'in_progress') THEN 1 ELSE 0 END) as active_wo,
                   SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_wo
            FROM work_orders;
            """
        ).fetchone()

        eq_stat = conn.execute(
            """
            SELECT COUNT(*) as total_equipment,
                   SUM(CASE WHEN status = 'deployed' THEN 1 ELSE 0 END) as deployed_equipment,
                   SUM(CASE WHEN status = 'maintenance' THEN 1 ELSE 0 END) as maintenance_equipment
            FROM equipment;
            """
        ).fetchone()

        # 3. Financial KPIs
        fin_stat = conn.execute(
            """
            SELECT COALESCE(SUM(CASE WHEN transaction_type = 'payment_received' THEN amount ELSE 0 END), 0.0) as total_rev,
                   COALESCE(SUM(CASE WHEN transaction_type != 'payment_received' AND transaction_type != 'refund' THEN amount ELSE 0 END), 0.0) as total_exp
            FROM financial_transactions;
            """
        ).fetchone()
        tot_rev = float(fin_stat["total_rev"])
        tot_exp = float(fin_stat["total_exp"])
        net_profit = tot_rev - tot_exp
        gross_margin = (net_profit / tot_rev * 100.0) if tot_rev > 0 else 0.0

        # NEW-613: was a raw, unoffset SUM(balance_due) that disagreed with
        # FinanceService.get_ar_aging's own total_ar on the same underlying
        # data. Now sourced from the same shared, no-actor
        # get_ar_net_totals() helper get_ar_aging itself calls, so this
        # figure reconciles to get_ar_aging()["total_ar"] by construction.
        # Behavior change: get_ar_net_totals' invoice SELECT is
        # status IN ('sent','partially_paid','overdue') AND balance_due>0,
        # narrower than the old query's bare "balance_due > 0" (every
        # status). Verified inert except for the 'draft' exclusion --
        # nothing in this codebase ever sets status='void' on an invoice
        # (repo-wide grep), and 'paid' invoices already have
        # balance_due≈0 by construction (CRMService's
        # _recalculate_invoice_balance), so those two status differences
        # are no-ops; only draft invoices with a nonzero balance_due stop
        # counting toward this KPI, which is the intended effect of this
        # fix (see finance_service.py's module docstring for the fuller
        # NEW-613 writeup).
        total_ar = self._finance_service.get_ar_net_totals()["total_ar"]

        # 4. Marketing KPIs
        mkt_stat = conn.execute(
            """
            SELECT COUNT(*) as total_campaigns,
                   COALESCE(SUM(actual_spend), 0.0) as total_spend,
                   COALESCE(SUM(leads_generated), 0) as leads_from_mkt
            FROM marketing_campaigns;
            """
        ).fetchone()

        rev_stat = conn.execute(
            "SELECT COUNT(*) as review_count, AVG(rating) as avg_rating FROM review_requests WHERE rating IS NOT NULL;"
        ).fetchone()
        avg_rating = float(rev_stat["avg_rating"]) if rev_stat and rev_stat["avg_rating"] is not None else 5.0

        # 5. Compliance KPIs
        comp_stat = conn.execute(
            """
            SELECT COUNT(*) as total_items,
                   SUM(CASE WHEN status = 'expiring_soon' THEN 1 ELSE 0 END) as expiring_soon,
                   SUM(CASE WHEN status = 'expired' THEN 1 ELSE 0 END) as expired
            FROM compliance_items;
            """
        ).fetchone()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sales": {
                "total_leads": leads_stat["total_leads"] or 0,
                "hot_leads": leads_stat["hot_leads"] or 0,
                "new_leads": leads_stat["new_leads"] or 0,
                "pipeline_opportunities": opps_stat["total_opps"] or 0,
                "pipeline_value": round(float(opps_stat["total_pipeline_val"]), 2),
                "weighted_pipeline_value": round(float(opps_stat["weighted_val"]), 2),
                "win_rate_percent": round(win_rate, 2),
            },
            "operations": {
                "total_projects": proj_stat["total_projects"] or 0,
                "active_projects": proj_stat["active_projects"] or 0,
                "in_progress_projects": proj_stat["in_progress_projects"] or 0,
                "completed_projects": proj_stat["completed_projects"] or 0,
                "active_work_orders": wo_stat["active_wo"] or 0,
                "total_equipment": eq_stat["total_equipment"] or 0,
                "deployed_equipment": eq_stat["deployed_equipment"] or 0,
            },
            "financial": {
                "total_revenue": round(tot_rev, 2),
                "total_expenses": round(tot_exp, 2),
                "net_profit": round(net_profit, 2),
                "gross_margin_percent": round(gross_margin, 2),
                "total_ar_outstanding": round(total_ar, 2),
            },
            "marketing": {
                "active_campaigns": mkt_stat["total_campaigns"] or 0,
                "total_marketing_spend": round(float(mkt_stat["total_spend"]), 2),
                "leads_generated": int(mkt_stat["leads_from_mkt"]),
                "reviews_count": rev_stat["review_count"] or 0,
                "average_customer_rating": round(avg_rating, 2),
            },
            "compliance": {
                "total_compliance_items": comp_stat["total_items"] or 0,
                "expiring_soon_items": comp_stat["expiring_soon"] or 0,
                "expired_items": comp_stat["expired"] or 0,
            },
        }

    def get_sales_analytics_rollup(self, actor: AuthContext) -> Dict[str, Any]:
        """B8.14: one tiered sales analytics rollup with three permission-
        gated views (rep/manager/executive) of the SAME underlying
        aggregation calls -- not three separately maintained queries.
        sales_rep_portal.md's B8.14 exit criterion.

        Tiering is keyed on the actor's permission set (never actor.role),
        same convention as CRMService._scoped_assignee_filter/
        CommissionService._scoped_rep_filter -- so a custom_permissions
        grant (NEW-637's precedent) lands in the correct tier exactly like
        a built-in role would:

        - "executive": actor holds BOTH PERM_VIEW_REPORTS and
          PERM_READ_TEAM_SALES_DATA (post-B8.14a/NEW-550 gate) -> calls
          get_executive_dashboard(actor) unmodified.
        - "manager": actor holds PERM_READ_TEAM_SALES_DATA and/or
          PERM_READ_TEAM_COMMISSIONS (but not both executive-tier perms
          together) -> calls CRMService.get_pipeline_summary(actor) and
          CommissionService.get_team_commission_summary(actor), which are
          already unfiltered/team-wide for a holder of either permission.
        - "rep": everyone else -> the SAME two calls, which self-scope to
          the caller's own rows via each service's existing narrowing
          helper (_scoped_assignee_filter / _scoped_rep_filter). This is
          exactly what get_pipeline_summary/get_team_commission_summary
          already return that actor elsewhere in the system -- this
          method widens no actor's visibility beyond that.

        Deliberately excludes AR/revenue figures from EVERY tier, including
        executive -- the task spec is explicit ("Do not surface any
        AR/revenue figure in this rollup") because get_executive_dashboard's
        own "financial" block (total_revenue/total_expenses/net_profit/
        gross_margin_percent/total_ar_outstanding) is all AR/revenue-derived.
        This exclusion is an unrelated, explicit scope decision for THIS
        rollup response, not a workaround for NEW-613's reconciliation bug
        (now fixed -- as of NEW-613, get_executive_dashboard's own
        total_ar_outstanding DOES carry the same financing offset as
        FinanceService.get_ar_aging, sourced from the same shared
        get_ar_net_totals() helper, so the two no longer diverge). A future
        reader should not conflate the two: even with NEW-613 fixed, this
        rollup would still omit "financial" from every tier, by the task
        spec's own explicit requirement. The executive tier below calls
        get_executive_dashboard(actor) UNMODIFIED (per this method's own
        "reuse get_executive_dashboard" requirement) and then projects the
        "financial" key back out of the copy returned here -- the
        underlying method/route (get_executive_dashboard itself,
        /api/v1/reports/summary, /api/v1/reports/executive,
        /api/v1/sales/dashboard's "team" block) are untouched and still
        expose it as before; only this new rollup's response omits it.
        Also excludes territory-dimension and handoff-completion-rate
        breakdowns (out of B8.14's scope) and any auto-refresh wiring --
        this is a load-on-demand / explicit-refresh surface only, per
        NEW-554's existing ~7-aggregate-query-per-tick cost concern on the
        dashboard's polling timer.

        See _ROLLUP_RECONCILIATION_NOTE (also returned as this response's
        own "note" field for rep/manager tiers) for the pipeline-vs-
        commission reconciliation quirk this response does NOT hide.
        """
        is_executive = actor.has_permission(PERM_VIEW_REPORTS) and actor.has_permission(
            PERM_READ_TEAM_SALES_DATA
        )
        if is_executive:
            executive_data = dict(self.get_executive_dashboard(actor))
            executive_data.pop("financial", None)  # NEW-613: no AR/revenue in this rollup
            return {
                "tier": "executive",
                "executive": executive_data,
            }

        is_manager = actor.has_permission(PERM_READ_TEAM_SALES_DATA) or actor.has_permission(
            PERM_READ_TEAM_COMMISSIONS
        )
        return {
            "tier": "manager" if is_manager else "rep",
            "pipeline": self._crm_service.get_pipeline_summary(actor),
            "commissions": self._commission_service.get_team_commission_summary(actor),
            "note": _ROLLUP_RECONCILIATION_NOTE,
        }
