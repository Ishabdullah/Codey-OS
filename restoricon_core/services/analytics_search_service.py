"""
Global Search & Executive Reporting Analytics Service for Restoricon Core (Track B Phase B5a).
Provides:
- Multi-domain fuzzy/tokenized global search across all 12 system entities with strict customer data isolation.
- Cross-domain executive KPI analytics dashboard spanning Sales, Operations, Finance, Marketing, and Compliance.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from ..auth import (
    AuthContext,
    PERM_GLOBAL_SEARCH,
    PERM_VIEW_REPORTS,
    ROLE_CUSTOMER,
)
from ..database import DatabaseManager


class AnalyticsSearchService:
    """Provides unified cross-domain search and executive KPI aggregation."""

    def __init__(self, db: DatabaseManager):
        self.db = db

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
        l_rows = conn.execute(
            """
            SELECT id, customer_id, source, status, property_type, urgency_level, score
            FROM leads
            WHERE property_type LIKE ? OR notes LIKE ? OR source LIKE ?
            LIMIT ?;
            """,
            (like_pattern, like_pattern, like_pattern, limit_per_category),
        ).fetchall()
        results["leads"] = [dict(r) for r in l_rows]
        total_count += len(results["leads"])

        # 3. Opportunities
        opp_rows = conn.execute(
            """
            SELECT id, customer_id, title, pipeline_stage, estimated_value, insurance_carrier
            FROM opportunities
            WHERE title LIKE ? OR insurance_carrier LIKE ? OR notes LIKE ?
            LIMIT ?;
            """,
            (like_pattern, like_pattern, like_pattern, limit_per_category),
        ).fetchall()
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
        if not actor.has_permission(PERM_VIEW_REPORTS):
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

        ar_stat = conn.execute(
            "SELECT COALESCE(SUM(balance_due), 0.0) as total_ar FROM invoices WHERE balance_due > 0;"
        ).fetchone()
        total_ar = float(ar_stat["total_ar"]) if ar_stat else 0.0

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
