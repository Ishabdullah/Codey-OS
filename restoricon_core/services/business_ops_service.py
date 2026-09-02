"""
Business Operations Domain Engine for Restoricon Core (Track B Phase B5a).
Encompasses:
- Marketing Campaigns & Online Review Tracking
- Compliance Licenses, Certifications, and Expiration Alerts
- HR Employees & Job-Costing Timesheets
- Procurement Vendors & Purchase Orders
"""

from datetime import datetime, timezone, timedelta
import json
import secrets
from typing import Any, Dict, List, Optional

from ..auth import (
    AuthContext,
    ROLE_CUSTOMER,
    PERM_READ_MARKETING,
    PERM_WRITE_MARKETING,
    PERM_READ_COMPLIANCE,
    PERM_WRITE_COMPLIANCE,
    PERM_READ_HR,
    PERM_WRITE_HR,
    PERM_READ_PROCUREMENT,
    PERM_WRITE_PROCUREMENT,
)
from ..database import DatabaseManager
from ..models import (
    MarketingCampaign,
    ReviewRequest,
    ComplianceItem,
    Employee,
    Timesheet,
    Vendor,
    PurchaseOrder,
)
from .audit_service import AuditService


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BusinessOpsService:
    """Manages marketing, compliance, HR, and procurement operations."""

    def __init__(self, db: DatabaseManager, audit: AuditService):
        self.db = db
        self.audit = audit

    # ==========================================
    # MARKETING & REVIEWS
    # ==========================================

    @staticmethod
    def _row_to_campaign(row: Any) -> MarketingCampaign:
        return MarketingCampaign(
            id=row["id"],
            name=row["name"],
            channel=row["channel"],
            status=row["status"],
            budget=float(row["budget"]),
            actual_spend=float(row["actual_spend"]),
            leads_generated=int(row["leads_generated"]),
            revenue_attributed=float(row["revenue_attributed"]),
            start_date=row["start_date"],
            end_date=row["end_date"],
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_campaign(self, camp: MarketingCampaign, actor: AuthContext) -> MarketingCampaign:
        """Create a marketing campaign."""
        if not actor.has_permission(PERM_WRITE_MARKETING):
            raise PermissionError("Actor lacks permission to create marketing campaigns")

        if not camp.name:
            raise ValueError("Campaign name is required")

        now = utc_now_iso()
        camp.created_at = now
        camp.updated_at = now

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO marketing_campaigns (
                    name, channel, status, budget, actual_spend,
                    leads_generated, revenue_attributed, start_date, end_date,
                    notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    camp.name,
                    camp.channel,
                    camp.status,
                    camp.budget,
                    camp.actual_spend,
                    camp.leads_generated,
                    camp.revenue_attributed,
                    camp.start_date,
                    camp.end_date,
                    camp.notes,
                    now,
                    now,
                ),
            )
            camp.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="marketing_campaign",
            entity_id=camp.id,
            change_summary=f"Created marketing campaign '{camp.name}' ({camp.channel})",
            actor=actor,
            details=camp.to_dict(),
        )
        return camp

    def list_campaigns(self, actor: AuthContext) -> List[MarketingCampaign]:
        """List all marketing campaigns."""
        if not actor.has_permission(PERM_READ_MARKETING):
            raise PermissionError("Actor lacks permission to view marketing campaigns")

        conn = self.db.get_connection()
        rows = conn.execute("SELECT * FROM marketing_campaigns ORDER BY id DESC;").fetchall()
        return [self._row_to_campaign(r) for r in rows]

    def create_review_request(self, req: ReviewRequest, actor: AuthContext) -> ReviewRequest:
        """Create and dispatch an automated customer review request."""
        if not actor.has_permission(PERM_WRITE_MARKETING):
            raise PermissionError("Actor lacks permission to manage review requests")

        now = utc_now_iso()
        req.created_at = now
        req.sent_at = now
        req.status = "sent"

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO review_requests (
                    customer_id, project_id, platform, rating, feedback,
                    status, sent_at, completed_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    req.customer_id,
                    req.project_id,
                    req.platform,
                    req.rating,
                    req.feedback,
                    req.status,
                    req.sent_at,
                    req.completed_at,
                    now,
                ),
            )
            req.id = cursor.lastrowid

        return req

    def submit_review(self, request_id: int, rating: int, feedback: str, actor: AuthContext) -> ReviewRequest:
        """Submit review feedback from a customer.

        Unlike the other marketing methods this endpoint is deliberately
        reachable by ROLE_CUSTOMER -- the customer the review request was
        sent to is its intended caller. Staff may also submit on a
        customer's behalf, which requires PERM_WRITE_MARKETING.
        """
        if not (1 <= rating <= 5):
            raise ValueError("Rating must be between 1 and 5")

        now = utc_now_iso()
        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM review_requests WHERE id = ?;", (request_id,)).fetchone()
        if not row:
            raise ValueError(f"Review request {request_id} not found")

        is_own_request = (
            actor.role == ROLE_CUSTOMER
            and actor.customer_id is not None
            and actor.customer_id == row["customer_id"]
        )
        if not (actor.has_permission(PERM_WRITE_MARKETING) or is_own_request):
            raise PermissionError("Actor lacks permission to submit this review")

        with conn:
            conn.execute(
                """
                UPDATE review_requests
                SET rating = ?, feedback = ?, status = 'completed', completed_at = ?
                WHERE id = ?;
                """,
                (rating, feedback, now, request_id),
            )

        self.audit.log(
            action="submit_review",
            entity_type="review_request",
            entity_id=request_id,
            change_summary=f"Submitted review for request {request_id} (rating {rating})",
            actor=actor,
            details={
                "customer_id": row["customer_id"],
                "old_rating": row["rating"],
                "new_rating": rating,
                "old_feedback": row["feedback"],
                "new_feedback": feedback,
                "old_status": row["status"],
                "new_status": "completed",
            },
        )

        return ReviewRequest(
            id=row["id"],
            customer_id=row["customer_id"],
            project_id=row["project_id"],
            platform=row["platform"],
            rating=rating,
            feedback=feedback,
            status="completed",
            sent_at=row["sent_at"],
            completed_at=now,
            created_at=row["created_at"],
        )

    def list_reviews(self, actor: AuthContext) -> List[ReviewRequest]:
        """List all review requests and ratings."""
        if not actor.has_permission(PERM_READ_MARKETING):
            raise PermissionError("Actor lacks permission to view review requests")

        conn = self.db.get_connection()
        rows = conn.execute("SELECT * FROM review_requests ORDER BY id DESC;").fetchall()
        return [
            ReviewRequest(
                id=r["id"],
                customer_id=r["customer_id"],
                project_id=r["project_id"],
                platform=r["platform"],
                rating=r["rating"],
                feedback=r["feedback"],
                status=r["status"],
                sent_at=r["sent_at"],
                completed_at=r["completed_at"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ==========================================
    # COMPLIANCE ENGINE
    # ==========================================

    @staticmethod
    def _row_to_compliance(row: Any) -> ComplianceItem:
        return ComplianceItem(
            id=row["id"],
            title=row["title"],
            category=row["category"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            license_number=row["license_number"],
            issuer=row["issuer"],
            issue_date=row["issue_date"],
            expiration_date=row["expiration_date"],
            status=row["status"],
            document_id=row["document_id"],
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_compliance_item(self, item: ComplianceItem, actor: AuthContext) -> ComplianceItem:
        """Register a license, certification, or insurance policy."""
        if not actor.has_permission(PERM_WRITE_COMPLIANCE):
            raise PermissionError("Actor lacks permission to create compliance items")

        if not item.title or not item.expiration_date:
            raise ValueError("Title and expiration date are required")

        now = utc_now_iso()
        item.created_at = now
        item.updated_at = now

        # Determine initial status based on expiration date
        try:
            exp_dt = datetime.fromisoformat(item.expiration_date.replace("Z", "+00:00"))
            now_dt = datetime.now(timezone.utc)
            if exp_dt < now_dt:
                item.status = "expired"
            elif (exp_dt - now_dt).days <= 30:
                item.status = "expiring_soon"
            else:
                item.status = "active"
        except Exception:
            item.status = "active"

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO compliance_items (
                    title, category, entity_type, entity_id, license_number,
                    issuer, issue_date, expiration_date, status, document_id,
                    notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    item.title,
                    item.category,
                    item.entity_type,
                    item.entity_id,
                    item.license_number,
                    item.issuer,
                    item.issue_date,
                    item.expiration_date,
                    item.status,
                    item.document_id,
                    item.notes,
                    now,
                    now,
                ),
            )
            item.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="compliance_item",
            entity_id=item.id,
            change_summary=f"Registered compliance item '{item.title}' (Exp: {item.expiration_date})",
            actor=actor,
            details=item.to_dict(),
        )
        return item

    def list_compliance_items(
        self,
        actor: AuthContext,
        entity_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[ComplianceItem]:
        """List compliance items with optional filters."""
        if not actor.has_permission(PERM_READ_COMPLIANCE):
            raise PermissionError("Actor lacks permission to view compliance items")

        clauses = []
        params: List[Any] = []
        if entity_type:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        if status:
            clauses.append("status = ?")
            params.append(status)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"SELECT * FROM compliance_items {where} ORDER BY expiration_date ASC;"

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_compliance(r) for r in rows]

    def scan_compliance_expirations(self, actor: AuthContext, threshold_days: int = 30) -> Dict[str, Any]:
        """Scan compliance items and update expiring/expired status flags."""
        if not actor.has_permission(PERM_READ_COMPLIANCE):
            raise PermissionError("Actor lacks permission to scan compliance expirations")

        conn = self.db.get_connection()
        rows = conn.execute("SELECT * FROM compliance_items WHERE status != 'renewed';").fetchall()

        now_dt = datetime.now(timezone.utc)
        now_str = utc_now_iso()
        expired_count = 0
        expiring_soon_count = 0
        active_count = 0

        with conn:
            for r in rows:
                exp_str = r["expiration_date"]
                new_status = r["status"]
                try:
                    exp_dt = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
                    diff_days = (exp_dt - now_dt).days
                    if diff_days < 0:
                        new_status = "expired"
                        expired_count += 1
                    elif diff_days <= threshold_days:
                        new_status = "expiring_soon"
                        expiring_soon_count += 1
                    else:
                        new_status = "active"
                        active_count += 1
                except Exception:
                    pass

                if new_status != r["status"]:
                    conn.execute(
                        "UPDATE compliance_items SET status = ?, updated_at = ? WHERE id = ?;",
                        (new_status, now_str, r["id"]),
                    )

        return {
            "total_scanned": len(rows),
            "expired_count": expired_count,
            "expiring_soon_count": expiring_soon_count,
            "active_count": active_count,
            "threshold_days": threshold_days,
        }

    # ==========================================
    # HR & TIMESHEETS
    # ==========================================

    @staticmethod
    def _row_to_employee(row: Any) -> Employee:
        return Employee(
            id=row["id"],
            user_id=row["user_id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            role_title=row["role_title"],
            department=row["department"],
            phone=row["phone"],
            email=row["email"],
            hourly_rate=float(row["hourly_rate"]),
            hire_date=row["hire_date"],
            status=row["status"],
            emergency_contact=row["emergency_contact"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_employee(self, emp: Employee, actor: AuthContext) -> Employee:
        """Create a new employee record."""
        if not actor.has_permission(PERM_WRITE_HR):
            raise PermissionError("Actor lacks permission to create employees")

        if not emp.first_name or not emp.last_name or not emp.role_title:
            raise ValueError("Employee name and role title are required")

        now = utc_now_iso()
        emp.created_at = now
        emp.updated_at = now

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO employees (
                    user_id, first_name, last_name, role_title, department,
                    phone, email, hourly_rate, hire_date, status, emergency_contact,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    emp.user_id,
                    emp.first_name,
                    emp.last_name,
                    emp.role_title,
                    emp.department,
                    emp.phone,
                    emp.email,
                    emp.hourly_rate,
                    emp.hire_date,
                    emp.status,
                    emp.emergency_contact,
                    now,
                    now,
                ),
            )
            emp.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="employee",
            entity_id=emp.id,
            change_summary=f"Added employee {emp.first_name} {emp.last_name} ({emp.role_title})",
            actor=actor,
            details=emp.to_dict(),
        )
        return emp

    def list_employees(
        self,
        actor: AuthContext,
        department: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Employee]:
        """List employees with optional department/status filter."""
        if not actor.has_permission(PERM_READ_HR):
            raise PermissionError("Actor lacks permission to view employees")

        clauses = []
        params: List[Any] = []
        if department:
            clauses.append("department = ?")
            params.append(department)
        if status:
            clauses.append("status = ?")
            params.append(status)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"SELECT * FROM employees {where} ORDER BY last_name ASC, first_name ASC;"

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_employee(r) for r in rows]

    def submit_timesheet(self, ts: Timesheet, actor: AuthContext) -> Timesheet:
        """Submit a timesheet entry for labor hours and job costing."""
        if not actor.has_permission(PERM_WRITE_HR):
            raise PermissionError("Actor lacks permission to log timesheets")

        if ts.hours_worked <= 0:
            raise ValueError("Hours worked must be greater than zero")

        conn = self.db.get_connection()
        # Look up employee hourly rate if not explicitly supplied
        emp_row = conn.execute("SELECT * FROM employees WHERE id = ?;", (ts.employee_id,)).fetchone()
        if not emp_row:
            raise ValueError(f"Employee {ts.employee_id} not found")

        if ts.hourly_rate <= 0:
            ts.hourly_rate = float(emp_row["hourly_rate"])

        ts.total_cost = round(ts.hours_worked * ts.hourly_rate, 2)
        now = utc_now_iso()
        ts.created_at = now
        if not ts.work_date:
            ts.work_date = now[:10]

        with conn:
            cursor = conn.execute(
                """
                INSERT INTO timesheets (
                    employee_id, project_id, work_order_id, work_date,
                    hours_worked, work_type, hourly_rate, total_cost,
                    notes, approved_by_id, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    ts.employee_id,
                    ts.project_id,
                    ts.work_order_id,
                    ts.work_date,
                    ts.hours_worked,
                    ts.work_type,
                    ts.hourly_rate,
                    ts.total_cost,
                    ts.notes,
                    ts.approved_by_id,
                    ts.status,
                    now,
                ),
            )
            ts.id = cursor.lastrowid

        return ts

    def approve_timesheet(self, ts_id: int, actor: AuthContext) -> Timesheet:
        """Approve a submitted timesheet."""
        if not actor.has_permission(PERM_WRITE_HR):
            raise PermissionError("Actor lacks permission to approve timesheets")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM timesheets WHERE id = ?;", (ts_id,)).fetchone()
        if not row:
            raise ValueError(f"Timesheet {ts_id} not found")

        with conn:
            conn.execute(
                "UPDATE timesheets SET status = 'approved', approved_by_id = ? WHERE id = ?;",
                (actor.user_id, ts_id),
            )

        return Timesheet(
            id=row["id"],
            employee_id=row["employee_id"],
            project_id=row["project_id"],
            work_order_id=row["work_order_id"],
            work_date=row["work_date"],
            hours_worked=float(row["hours_worked"]),
            work_type=row["work_type"],
            hourly_rate=float(row["hourly_rate"]),
            total_cost=float(row["total_cost"]),
            notes=row["notes"],
            approved_by_id=actor.user_id,
            status="approved",
            created_at=row["created_at"],
        )

    def list_timesheets(
        self,
        actor: AuthContext,
        employee_id: Optional[int] = None,
        project_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[Timesheet]:
        """List timesheets with optional filters."""
        if not actor.has_permission(PERM_READ_HR):
            raise PermissionError("Actor lacks permission to view timesheets")

        clauses = []
        params: List[Any] = []
        if employee_id is not None:
            clauses.append("employee_id = ?")
            params.append(employee_id)
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        if status:
            clauses.append("status = ?")
            params.append(status)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"SELECT * FROM timesheets {where} ORDER BY work_date DESC, id DESC;"

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [
            Timesheet(
                id=r["id"],
                employee_id=r["employee_id"],
                project_id=r["project_id"],
                work_order_id=r["work_order_id"],
                work_date=r["work_date"],
                hours_worked=float(r["hours_worked"]),
                work_type=r["work_type"],
                hourly_rate=float(r["hourly_rate"]),
                total_cost=float(r["total_cost"]),
                notes=r["notes"],
                approved_by_id=r["approved_by_id"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]

    # ==========================================
    # PROCUREMENT & PURCHASE ORDERS
    # ==========================================

    @staticmethod
    def _row_to_vendor(row: Any) -> Vendor:
        return Vendor(
            id=row["id"],
            company_name=row["company_name"],
            contact_name=row["contact_name"],
            phone=row["phone"],
            email=row["email"],
            address=row["address"],
            category=row["category"],
            payment_terms=row["payment_terms"],
            rating=float(row["rating"]) if row["rating"] is not None else None,
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_vendor(self, vendor: Vendor, actor: AuthContext) -> Vendor:
        """Create a supplier / vendor profile."""
        if not actor.has_permission(PERM_WRITE_PROCUREMENT):
            raise PermissionError("Actor lacks permission to create vendors")

        if not vendor.company_name:
            raise ValueError("Company name is required")

        now = utc_now_iso()
        vendor.created_at = now
        vendor.updated_at = now

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO vendors (
                    company_name, contact_name, phone, email, address,
                    category, payment_terms, rating, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    vendor.company_name,
                    vendor.contact_name,
                    vendor.phone,
                    vendor.email,
                    vendor.address,
                    vendor.category,
                    vendor.payment_terms,
                    vendor.rating,
                    vendor.notes,
                    now,
                    now,
                ),
            )
            vendor.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="vendor",
            entity_id=vendor.id,
            change_summary=f"Added vendor '{vendor.company_name}' ({vendor.category})",
            actor=actor,
            details=vendor.to_dict(),
        )
        return vendor

    def list_vendors(self, actor: AuthContext, category: Optional[str] = None) -> List[Vendor]:
        """List procurement vendors."""
        if not actor.has_permission(PERM_READ_PROCUREMENT):
            raise PermissionError("Actor lacks permission to view vendors")

        conn = self.db.get_connection()
        if category:
            rows = conn.execute("SELECT * FROM vendors WHERE category = ? ORDER BY company_name ASC;", (category,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM vendors ORDER BY company_name ASC;").fetchall()
        return [self._row_to_vendor(r) for r in rows]

    def _generate_po_number(self) -> str:
        date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
        rand_part = secrets.token_hex(2).upper()
        return f"PO-{date_part}-{rand_part}"

    @staticmethod
    def _row_to_po(row: Any) -> PurchaseOrder:
        items = json.loads(row["items_json"]) if row["items_json"] else []
        return PurchaseOrder(
            id=row["id"],
            po_number=row["po_number"],
            vendor_id=row["vendor_id"],
            project_id=row["project_id"],
            status=row["status"],
            items=items,
            subtotal=float(row["subtotal"]),
            tax_amount=float(row["tax_amount"]),
            total_amount=float(row["total_amount"]),
            ordered_date=row["ordered_date"],
            expected_date=row["expected_date"],
            received_date=row["received_date"],
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_purchase_order(self, po: PurchaseOrder, actor: AuthContext) -> PurchaseOrder:
        """Create a purchase order for materials/equipment."""
        if not actor.has_permission(PERM_WRITE_PROCUREMENT):
            raise PermissionError("Actor lacks permission to create purchase orders")

        if not po.po_number:
            po.po_number = self._generate_po_number()

        # Compute total if items given
        if po.items and po.total_amount <= 0:
            subtot = sum(float(it.get("quantity", 1)) * float(it.get("unit_cost", 0.0)) for it in po.items)
            po.subtotal = subtot
            po.total_amount = round(subtot + po.tax_amount, 2)

        now = utc_now_iso()
        po.created_at = now
        po.updated_at = now
        if not po.ordered_date:
            po.ordered_date = now

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO purchase_orders (
                    po_number, vendor_id, project_id, status, items_json,
                    subtotal, tax_amount, total_amount, ordered_date,
                    expected_date, received_date, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    po.po_number,
                    po.vendor_id,
                    po.project_id,
                    po.status,
                    json.dumps(po.items),
                    po.subtotal,
                    po.tax_amount,
                    po.total_amount,
                    po.ordered_date,
                    po.expected_date,
                    po.received_date,
                    po.notes,
                    now,
                    now,
                ),
            )
            po.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="purchase_order",
            entity_id=po.id,
            change_summary=f"Created PO #{po.po_number} (${po.total_amount:.2f})",
            actor=actor,
            details=po.to_dict(),
        )
        return po

    def receive_purchase_order(self, po_id: int, actor: AuthContext) -> PurchaseOrder:
        """Mark purchase order materials/supplies as received."""
        if not actor.has_permission(PERM_WRITE_PROCUREMENT):
            raise PermissionError("Actor lacks permission to receive purchase orders")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM purchase_orders WHERE id = ?;", (po_id,)).fetchone()
        if not row:
            raise ValueError(f"Purchase order {po_id} not found")

        now = utc_now_iso()
        with conn:
            conn.execute(
                """
                UPDATE purchase_orders
                SET status = 'received', received_date = ?, updated_at = ?
                WHERE id = ?;
                """,
                (now, now, po_id),
            )

        self.audit.log(
            action="update",
            entity_type="purchase_order",
            entity_id=po_id,
            change_summary=f"Received PO #{row['po_number']}",
            actor=actor,
        )
        return self._row_to_po({**dict(row), "status": "received", "received_date": now, "updated_at": now})

    def list_purchase_orders(
        self,
        actor: AuthContext,
        vendor_id: Optional[int] = None,
        project_id: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[PurchaseOrder]:
        """List purchase orders with optional filters."""
        if not actor.has_permission(PERM_READ_PROCUREMENT):
            raise PermissionError("Actor lacks permission to view purchase orders")

        clauses = []
        params: List[Any] = []
        if vendor_id is not None:
            clauses.append("vendor_id = ?")
            params.append(vendor_id)
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        if status:
            clauses.append("status = ?")
            params.append(status)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"SELECT * FROM purchase_orders {where} ORDER BY id DESC;"

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_po(r) for r in rows]
