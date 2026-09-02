"""
Finance & Bookkeeping Domain Engine for Restoricon Core (Track B Phase B5a).
Provides financial transaction ledger, project P&L job costing, AR aging breakdown,
and financial summaries with strict RBAC audit logging.
"""

from datetime import datetime, timezone
import json
import secrets
from typing import Any, Dict, List, Optional

from ..auth import (
    AuthContext,
    PERM_READ_FINANCE,
    PERM_WRITE_FINANCE,
    ROLE_CUSTOMER,
)
from ..database import DatabaseManager
from ..models import FinancialTransaction
from .audit_service import AuditService, build_audit_details


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FinanceService:
    """Manages transaction ledger, job costing, project P&L, and AR aging."""

    def __init__(self, db: DatabaseManager, audit: AuditService):
        self.db = db
        self.audit = audit

    def _generate_txn_number(self) -> str:
        date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
        rand_part = secrets.token_hex(2).upper()
        return f"TXN-{date_part}-{rand_part}"

    @staticmethod
    def _row_to_txn(row: Any) -> FinancialTransaction:
        return FinancialTransaction(
            id=row["id"],
            transaction_number=row["transaction_number"],
            transaction_type=row["transaction_type"],
            amount=float(row["amount"]),
            category=row["category"],
            payment_method=row["payment_method"],
            reference_number=row["reference_number"],
            customer_id=row["customer_id"],
            project_id=row["project_id"],
            invoice_id=row["invoice_id"],
            vendor_id=row["vendor_id"],
            recorded_by_id=row["recorded_by_id"],
            transaction_date=row["transaction_date"],
            notes=row["notes"],
            created_at=row["created_at"],
        )

    def record_transaction(
        self,
        txn: FinancialTransaction,
        actor: AuthContext,
    ) -> FinancialTransaction:
        """Record a financial transaction in the ledger."""
        if not actor.has_permission(PERM_WRITE_FINANCE):
            raise PermissionError("Actor lacks permission to record financial transactions")

        if txn.amount <= 0:
            raise ValueError("Transaction amount must be positive")

        valid_types = {
            "payment_received",
            "vendor_expense",
            "payroll",
            "material_cost",
            "equipment_rental",
            "refund",
            "other",
        }
        if txn.transaction_type not in valid_types:
            raise ValueError(f"Invalid transaction type: {txn.transaction_type}")

        if not txn.transaction_number:
            txn.transaction_number = self._generate_txn_number()

        now = utc_now_iso()
        if not txn.transaction_date:
            txn.transaction_date = now
        txn.created_at = now
        txn.recorded_by_id = actor.user_id

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO financial_transactions (
                    transaction_number, transaction_type, amount, category,
                    payment_method, reference_number, customer_id, project_id,
                    invoice_id, vendor_id, recorded_by_id, transaction_date,
                    notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    txn.transaction_number,
                    txn.transaction_type,
                    txn.amount,
                    txn.category,
                    txn.payment_method,
                    txn.reference_number,
                    txn.customer_id,
                    txn.project_id,
                    txn.invoice_id,
                    txn.vendor_id,
                    txn.recorded_by_id,
                    txn.transaction_date,
                    txn.notes,
                    txn.created_at,
                ),
            )
            txn.id = cursor.lastrowid

            # If this is a project cost/expense, update project's actual_cost
            cost_applied = False
            if txn.project_id and txn.transaction_type in ("vendor_expense", "payroll", "material_cost", "equipment_rental"):
                conn.execute(
                    """
                    UPDATE projects
                    SET actual_cost = actual_cost + ?,
                        updated_at = ?
                    WHERE id = ?;
                    """,
                    (txn.amount, now, txn.project_id),
                )
                cost_applied = True

        self.audit.log(
            action="create",
            entity_type="financial_transaction",
            entity_id=txn.id,
            change_summary=f"Recorded {txn.transaction_type} of ${txn.amount:.2f} (#{txn.transaction_number})",
            actor=actor,
            details=build_audit_details(
                after=txn.to_dict(),
                side_effects=(
                    {"project_actual_cost_delta": {"project_id": txn.project_id, "amount": txn.amount}}
                    if cost_applied
                    else None
                ),
            ),
        )
        return txn

    def get_transaction(self, txn_id: int, actor: AuthContext) -> Optional[FinancialTransaction]:
        """Retrieve a transaction by ID."""
        if not actor.has_permission(PERM_READ_FINANCE):
            raise PermissionError("Actor lacks permission to view financial transactions")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM financial_transactions WHERE id = ?;", (txn_id,)).fetchone()
        if not row:
            return None
        return self._row_to_txn(row)

    def list_transactions(
        self,
        actor: AuthContext,
        project_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        transaction_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[FinancialTransaction]:
        """List financial transactions with optional filters."""
        if not actor.has_permission(PERM_READ_FINANCE):
            raise PermissionError("Actor lacks permission to view financial transactions")

        clauses = []
        params: List[Any] = []

        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        if customer_id is not None:
            clauses.append("customer_id = ?")
            params.append(customer_id)
        if transaction_type is not None:
            clauses.append("transaction_type = ?")
            params.append(transaction_type)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"SELECT * FROM financial_transactions {where} ORDER BY id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_txn(r) for r in rows]

    def get_project_pnl(self, project_id: int, actor: AuthContext) -> Dict[str, Any]:
        """Compute project-level Profit & Loss and Job Costing breakdown."""
        if not actor.has_permission(PERM_READ_FINANCE):
            raise PermissionError("Actor lacks permission to view financial P&L")

        conn = self.db.get_connection()
        proj_row = conn.execute("SELECT * FROM projects WHERE id = ?;", (project_id,)).fetchone()
        if not proj_row:
            raise ValueError(f"Project {project_id} not found")

        contract_amount = float(proj_row["contract_amount"] or 0.0)
        estimated_cost = float(proj_row["estimated_cost"] or 0.0)

        # Revenue collected from payments
        rev_row = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0.0) as total_rev
            FROM financial_transactions
            WHERE project_id = ? AND transaction_type = 'payment_received';
            """,
            (project_id,),
        ).fetchone()
        total_revenue = float(rev_row["total_rev"]) if rev_row else 0.0

        # Expenses breakdown
        exp_rows = conn.execute(
            """
            SELECT transaction_type, category, COALESCE(SUM(amount), 0.0) as total
            FROM financial_transactions
            WHERE project_id = ? AND transaction_type IN ('vendor_expense', 'payroll', 'material_cost', 'equipment_rental', 'other')
            GROUP BY transaction_type, category;
            """,
            (project_id,),
        ).fetchall()

        materials_cost = 0.0
        labor_cost = 0.0
        subcontractor_cost = 0.0
        equipment_cost = 0.0
        other_cost = 0.0

        for r in exp_rows:
            tt = r["transaction_type"]
            amt = float(r["total"])
            if tt == "material_cost":
                materials_cost += amt
            elif tt == "payroll":
                labor_cost += amt
            elif tt == "vendor_expense":
                subcontractor_cost += amt
            elif tt == "equipment_rental":
                equipment_cost += amt
            else:
                other_cost += amt

        # Also pull labor from approved timesheets if not already in ledger
        ts_row = conn.execute(
            """
            SELECT COALESCE(SUM(total_cost), 0.0) as ts_labor
            FROM timesheets
            WHERE project_id = ? AND status = 'approved';
            """,
            (project_id,),
        ).fetchone()
        timesheet_labor = float(ts_row["ts_labor"]) if ts_row else 0.0

        # Effective labor is the higher of ledger or approved timesheets
        effective_labor = max(labor_cost, timesheet_labor)
        total_costs = materials_cost + effective_labor + subcontractor_cost + equipment_cost + other_cost

        # Invoiced amounts
        inv_row = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0.0) as total_invoiced,
                   COALESCE(SUM(balance_due), 0.0) as total_balance_due
            FROM invoices
            WHERE project_id = ? AND status != 'void';
            """,
            (project_id,),
        ).fetchone()
        total_invoiced = float(inv_row["total_invoiced"]) if inv_row else 0.0
        total_outstanding = float(inv_row["total_balance_due"]) if inv_row else 0.0

        # Benchmark against contract or total revenue
        basis_revenue = contract_amount if contract_amount > 0 else total_revenue
        gross_profit = basis_revenue - total_costs
        gross_margin_pct = (gross_profit / basis_revenue * 100.0) if basis_revenue > 0 else 0.0

        return {
            "project_id": project_id,
            "project_number": f"PRJ-{project_id:04d}",
            "project_title": proj_row["title"],
            "contract_amount": contract_amount,
            "estimated_cost": estimated_cost,
            "total_invoiced": total_invoiced,
            "total_collected": total_revenue,
            "total_outstanding": total_outstanding,
            "total_expenses": total_costs,
            "expenses_breakdown": {
                "materials": materials_cost,
                "labor": effective_labor,
                "subcontractors": subcontractor_cost,
                "equipment": equipment_cost,
                "other": other_cost,
            },
            "gross_profit": gross_profit,
            "gross_margin_percent": round(gross_margin_pct, 2),
        }

    def get_ar_aging(self, actor: AuthContext) -> Dict[str, Any]:
        """Compute Accounts Receivable aging buckets."""
        if not actor.has_permission(PERM_READ_FINANCE):
            raise PermissionError("Actor lacks permission to view AR aging")

        conn = self.db.get_connection()
        rows = conn.execute(
            """
            SELECT id, invoice_number, customer_id, project_id, balance_due, due_date, status
            FROM invoices
            WHERE status IN ('sent', 'partially_paid', 'overdue') AND balance_due > 0;
            """
        ).fetchall()

        now_dt = datetime.now(timezone.utc)
        buckets = {
            "current": 0.0,
            "1_30_days": 0.0,
            "31_60_days": 0.0,
            "61_90_days": 0.0,
            "over_90_days": 0.0,
        }
        total_ar = 0.0
        details = []

        for r in rows:
            bal = float(r["balance_due"])
            total_ar += bal
            due_str = r["due_date"]
            days_overdue = 0
            if due_str:
                try:
                    due_dt = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
                    diff = (now_dt - due_dt).days
                    days_overdue = max(0, diff)
                except Exception:
                    days_overdue = 0

            if days_overdue <= 0:
                buckets["current"] += bal
                bucket_name = "current"
            elif days_overdue <= 30:
                buckets["1_30_days"] += bal
                bucket_name = "1_30_days"
            elif days_overdue <= 60:
                buckets["31_60_days"] += bal
                bucket_name = "31_60_days"
            elif days_overdue <= 90:
                buckets["61_90_days"] += bal
                bucket_name = "61_90_days"
            else:
                buckets["over_90_days"] += bal
                bucket_name = "over_90_days"

            details.append({
                "invoice_id": r["id"],
                "invoice_number": r["invoice_number"],
                "customer_id": r["customer_id"],
                "balance_due": bal,
                "due_date": due_str,
                "days_overdue": days_overdue,
                "bucket": bucket_name,
            })

        return {
            "total_ar": round(total_ar, 2),
            "buckets": {k: round(v, 2) for k, v in buckets.items()},
            "invoices_count": len(rows),
            "details": details,
        }

    def get_financial_summary(self, actor: AuthContext) -> Dict[str, Any]:
        """Aggregate high-level financial health summary."""
        if not actor.has_permission(PERM_READ_FINANCE):
            raise PermissionError("Actor lacks permission to view financial summary")

        conn = self.db.get_connection()
        rev_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0.0) as rev FROM financial_transactions WHERE transaction_type = 'payment_received';"
        ).fetchone()
        exp_row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0.0) as exp FROM financial_transactions WHERE transaction_type != 'payment_received' AND transaction_type != 'refund';"
        ).fetchone()

        total_rev = float(rev_row["rev"]) if rev_row else 0.0
        total_exp = float(exp_row["exp"]) if exp_row else 0.0
        net_profit = total_rev - total_exp
        margin = (net_profit / total_rev * 100.0) if total_rev > 0 else 0.0

        ar_data = self.get_ar_aging(actor)

        return {
            "total_revenue": round(total_rev, 2),
            "total_expenses": round(total_exp, 2),
            "net_profit": round(net_profit, 2),
            "net_margin_percent": round(margin, 2),
            "total_ar_outstanding": ar_data["total_ar"],
            "ar_buckets": ar_data["buckets"],
        }
