"""
CRM and Operations Business Services for Restoricon Core.
Orchestrates domain entities (Customers, Leads, Opportunities, Projects, Estimates,
Contracts, Invoices, Documents) with RBAC enforcement and automatic audit logging.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..auth import (
    AuthContext,
    PERM_READ_ALL_CUSTOMERS,
    PERM_WRITE_CUSTOMERS,
    PERM_READ_LEADS,
    PERM_WRITE_LEADS,
    PERM_READ_OPPORTUNITIES,
    PERM_WRITE_OPPORTUNITIES,
    PERM_READ_ALL_PROJECTS,
    PERM_READ_ASSIGNED_PROJECTS,
    PERM_READ_OWN_PROJECTS,
    PERM_WRITE_PROJECTS,
    PERM_READ_ESTIMATES,
    PERM_WRITE_ESTIMATES,
    PERM_READ_CONTRACTS,
    PERM_WRITE_CONTRACTS,
    PERM_SIGN_CONTRACTS,
    PERM_READ_DOCUMENTS,
    PERM_WRITE_DOCUMENTS,
    PERM_READ_FINANCIALS,
    PERM_WRITE_FINANCIALS,
    PERM_READ_SUBCONTRACTORS,
    PERM_WRITE_SUBCONTRACTORS,
    ROLE_CUSTOMER,
    ROLE_TECHNICIAN,
)
from ..database import DatabaseManager
from ..models import (
    Contract,
    Customer,
    Document,
    Estimate,
    Invoice,
    Lead,
    Opportunity,
    Project,
    Subcontractor,
    utc_now_iso,
)
from .audit_service import AuditService


class CRMService:
    """Core domain logic and data management for Restoricon Core."""

    def __init__(self, db_manager: DatabaseManager, audit_service: AuditService):
        self.db = db_manager
        self.audit = audit_service

    # ==========================================
    # CUSTOMERS
    # ==========================================

    def create_customer(self, customer: Customer, actor: AuthContext) -> Customer:
        if not actor.has_permission(PERM_WRITE_CUSTOMERS):
            raise PermissionError("Actor lacks permission to create customers")

        now = utc_now_iso()
        customer.created_at = now
        tags_json = json.dumps(customer.tags)
        custom_fields_json = json.dumps(customer.custom_fields)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO customers (
                    external_id, first_name, last_name, company_name, phone, email,
                    mailing_address, service_address, customer_type,
                    customer_source, assigned_user_id, status, tags_json,
                    notes, custom_fields_json, created_at, last_contact_at, next_followup_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    customer.external_id,
                    customer.first_name.strip(),
                    customer.last_name.strip(),
                    customer.company_name,
                    customer.phone,
                    customer.email.strip().lower() if customer.email else None,
                    customer.mailing_address,
                    customer.service_address,
                    customer.customer_type,
                    customer.customer_source,
                    customer.assigned_user_id,
                    customer.status,
                    tags_json,
                    customer.notes,
                    custom_fields_json,
                    now,
                    customer.last_contact_at,
                    customer.next_followup_at,
                ),
            )
            customer.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="customer",
            entity_id=customer.id,
            change_summary=f"Created customer {customer.first_name} {customer.last_name}",
            actor=actor,
            details=customer.to_dict(),
        )
        return customer

    def get_customer(self, customer_id: int, actor: AuthContext) -> Optional[Customer]:
        if not actor.can_access_customer(customer_id):
            raise PermissionError("Actor lacks permission to access this customer record")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM customers WHERE id = ?;", (customer_id,)).fetchone()
        if not row:
            return None

        tags = json.loads(row["tags_json"]) if row["tags_json"] else []
        custom_fields = json.loads(row["custom_fields_json"]) if row["custom_fields_json"] else {}

        return Customer(
            id=row["id"],
            external_id=row["external_id"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            company_name=row["company_name"],
            phone=row["phone"],
            email=row["email"],
            mailing_address=row["mailing_address"],
            service_address=row["service_address"],
            customer_type=row["customer_type"],
            customer_source=row["customer_source"],
            assigned_user_id=row["assigned_user_id"],
            status=row["status"],
            tags=tags,
            notes=row["notes"] if actor.role != ROLE_CUSTOMER else None,  # Hide internal notes from customer
            custom_fields=custom_fields,
            created_at=row["created_at"],
            last_contact_at=row["last_contact_at"],
            next_followup_at=row["next_followup_at"],
        )

    def get_customer_by_external_id(self, external_id: str, actor: AuthContext) -> Optional[Customer]:
        """Look up by an external system's own string ID (NEW-212/NEW-232,
        2026-08-27), matching the subcontractors/appointments/
        automation_rules by_external_id lookup pattern -- lets a migration
        or write-through check for an existing row before INSERT and skip
        re-migrating it, instead of hitting the unique-index constraint as
        an IntegrityError."""
        if not actor.has_permission(PERM_READ_ALL_CUSTOMERS):
            raise PermissionError("Actor lacks permission to look up customers by external ID")

        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM customers WHERE external_id = ?;", (external_id,)
        ).fetchone()
        if not row:
            return None
        return self.get_customer(row["id"], actor)

    def get_customer_by_email(self, email: str, actor: AuthContext) -> Optional[Customer]:
        """Best-effort lookup for resolving an inbound message's sender
        address to an existing customer (NEW-233). `customers.email` has
        no UNIQUE constraint -- only `idx_customers_email` (COLLATE
        NOCASE) -- so more than one customer row can share an address in
        real data (e.g. shared household inboxes, or two records created
        independently before dedup). Returns None on zero matches AND on
        2+ matches: attaching a communication to the wrong customer is
        worse than leaving customer_id NULL, so ambiguity is treated the
        same as "unknown" rather than guessed at."""
        if not actor.has_permission(PERM_READ_ALL_CUSTOMERS):
            raise PermissionError("Actor lacks permission to look up customers by email")

        conn = self.db.get_connection()
        rows = conn.execute(
            "SELECT id FROM customers WHERE email = ?;", (email,)
        ).fetchall()
        if len(rows) != 1:
            return None
        return self.get_customer(rows[0]["id"], actor)

    def list_customers(
        self,
        actor: AuthContext,
        status: Optional[str] = None,
        search_term: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Customer]:
        if actor.role == ROLE_CUSTOMER:
            if not actor.customer_id:
                return []
            cust = self.get_customer(actor.customer_id, actor)
            return [cust] if cust else []

        if not actor.has_permission(PERM_READ_ALL_CUSTOMERS):
            raise PermissionError("Actor lacks permission to list all customers")

        query = "SELECT * FROM customers WHERE 1=1"
        params: List[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status)

        if search_term:
            term = f"%{search_term.strip()}%"
            query += " AND (first_name LIKE ? OR last_name LIKE ? OR company_name LIKE ? OR phone LIKE ? OR email LIKE ?)"
            params.extend([term, term, term, term, term])

        query += " ORDER BY id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()

        results = []
        for row in rows:
            tags = json.loads(row["tags_json"]) if row["tags_json"] else []
            custom_fields = json.loads(row["custom_fields_json"]) if row["custom_fields_json"] else {}
            results.append(
                Customer(
                    id=row["id"],
                    external_id=row["external_id"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    company_name=row["company_name"],
                    phone=row["phone"],
                    email=row["email"],
                    mailing_address=row["mailing_address"],
                    service_address=row["service_address"],
                    customer_type=row["customer_type"],
                    customer_source=row["customer_source"],
                    assigned_user_id=row["assigned_user_id"],
                    status=row["status"],
                    tags=tags,
                    notes=row["notes"],
                    custom_fields=custom_fields,
                    created_at=row["created_at"],
                    last_contact_at=row["last_contact_at"],
                    next_followup_at=row["next_followup_at"],
                )
            )
        return results

    # ==========================================
    # LEADS
    # ==========================================

    def create_lead(self, lead: Lead, actor: AuthContext) -> Lead:
        if not actor.has_permission(PERM_WRITE_LEADS):
            raise PermissionError("Actor lacks permission to create leads")

        now = utc_now_iso()
        lead.created_at = now
        lead.updated_at = now

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO leads (
                    external_id, customer_id, source, status, score, estimated_value,
                    assigned_user_id, first_contact_at, last_contact_at,
                    next_followup_at, notes, lost_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    lead.external_id,
                    lead.customer_id,
                    lead.source,
                    lead.status,
                    lead.score,
                    lead.estimated_value,
                    lead.assigned_user_id,
                    lead.first_contact_at,
                    lead.last_contact_at,
                    lead.next_followup_at,
                    lead.notes,
                    lead.lost_reason,
                    now,
                    now,
                ),
            )
            lead.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="lead",
            entity_id=lead.id,
            change_summary=f"Created lead from source '{lead.source}' (est. ${lead.estimated_value:.2f})",
            actor=actor,
            details=lead.to_dict(),
        )
        return lead

    def list_leads(self, actor: AuthContext, status: Optional[str] = None) -> List[Lead]:
        if not actor.has_permission(PERM_READ_LEADS):
            raise PermissionError("Actor lacks permission to view leads")

        query = "SELECT * FROM leads WHERE 1=1"
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY id DESC;"

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()

        return [
            Lead(
                id=r["id"],
                external_id=r["external_id"],
                customer_id=r["customer_id"],
                source=r["source"],
                status=r["status"],
                score=r["score"],
                estimated_value=r["estimated_value"],
                assigned_user_id=r["assigned_user_id"],
                first_contact_at=r["first_contact_at"],
                last_contact_at=r["last_contact_at"],
                next_followup_at=r["next_followup_at"],
                notes=r["notes"],
                lost_reason=r["lost_reason"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    def get_lead_by_external_id(self, external_id: str, actor: AuthContext) -> Optional[Lead]:
        """Look up by an external system's own string ID (NEW-212/NEW-232,
        2026-08-27), matching the subcontractors/appointments/
        automation_rules by_external_id lookup pattern."""
        if not actor.has_permission(PERM_READ_LEADS):
            raise PermissionError("Actor lacks permission to look up leads by external ID")

        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM leads WHERE external_id = ?;", (external_id,)
        ).fetchone()
        if not row:
            return None
        return Lead(
            id=row["id"],
            external_id=row["external_id"],
            customer_id=row["customer_id"],
            source=row["source"],
            status=row["status"],
            score=row["score"],
            estimated_value=row["estimated_value"],
            assigned_user_id=row["assigned_user_id"],
            first_contact_at=row["first_contact_at"],
            last_contact_at=row["last_contact_at"],
            next_followup_at=row["next_followup_at"],
            notes=row["notes"],
            lost_reason=row["lost_reason"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ==========================================
    # OPPORTUNITIES / SALES PIPELINE
    # ==========================================

    def create_opportunity(self, opp: Opportunity, actor: AuthContext) -> Opportunity:
        if not actor.has_permission(PERM_WRITE_OPPORTUNITIES):
            raise PermissionError("Actor lacks permission to create opportunities")

        now = utc_now_iso()
        opp.created_at = now
        opp.updated_at = now

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO opportunities (
                    customer_id, project_id, title, estimated_value, probability,
                    pipeline_stage, expected_close_date, assigned_user_id,
                    competitor_info, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    opp.customer_id,
                    opp.project_id,
                    opp.title.strip(),
                    opp.estimated_value,
                    opp.probability,
                    opp.pipeline_stage,
                    opp.expected_close_date,
                    opp.assigned_user_id,
                    opp.competitor_info,
                    opp.notes,
                    now,
                    now,
                ),
            )
            opp.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="opportunity",
            entity_id=opp.id,
            change_summary=f"Created opportunity '{opp.title}' at stage '{opp.pipeline_stage}'",
            actor=actor,
            details=opp.to_dict(),
        )
        return opp

    def list_opportunities(self, actor: AuthContext, pipeline_stage: Optional[str] = None) -> List[Opportunity]:
        if not actor.has_permission(PERM_READ_OPPORTUNITIES):
            raise PermissionError("Actor lacks permission to view opportunities")

        query = "SELECT * FROM opportunities WHERE 1=1"
        params: List[Any] = []
        if pipeline_stage:
            query += " AND pipeline_stage = ?"
            params.append(pipeline_stage)
        query += " ORDER BY id DESC;"

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()

        return [
            Opportunity(
                id=r["id"],
                customer_id=r["customer_id"],
                project_id=r["project_id"],
                title=r["title"],
                estimated_value=r["estimated_value"],
                probability=r["probability"],
                pipeline_stage=r["pipeline_stage"],
                expected_close_date=r["expected_close_date"],
                assigned_user_id=r["assigned_user_id"],
                competitor_info=r["competitor_info"],
                notes=r["notes"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]

    # ==========================================
    # PROJECTS / JOBS
    # ==========================================

    def create_project(self, project: Project, actor: AuthContext) -> Project:
        if not actor.has_permission(PERM_WRITE_PROJECTS):
            raise PermissionError("Actor lacks permission to create projects")

        now = utc_now_iso()
        project.created_at = now
        project.updated_at = now
        assigned_json = json.dumps(project.assigned_employees)
        subcontractors_json = json.dumps(project.subcontractors)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO projects (
                    customer_id, title, property_address, project_type, status,
                    start_date, expected_completion, actual_completion,
                    project_manager_id, assigned_employees_json, subcontractors_json,
                    scope_of_work, estimated_cost, contract_amount, actual_cost,
                    profit, notes, warranty_info, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    project.customer_id,
                    project.title.strip(),
                    project.property_address.strip(),
                    project.project_type,
                    project.status,
                    project.start_date,
                    project.expected_completion,
                    project.actual_completion,
                    project.project_manager_id,
                    assigned_json,
                    subcontractors_json,
                    project.scope_of_work,
                    project.estimated_cost,
                    project.contract_amount,
                    project.actual_cost,
                    project.profit,
                    project.notes,
                    project.warranty_info,
                    now,
                    now,
                ),
            )
            project.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="project",
            entity_id=project.id,
            change_summary=f"Created project '{project.title}' for customer ID {project.customer_id}",
            actor=actor,
            details=project.to_dict(),
        )
        return project

    def get_project(self, project_id: int, actor: AuthContext) -> Optional[Project]:
        if not (
            actor.has_permission(PERM_READ_ALL_PROJECTS)
            or actor.has_permission(PERM_READ_ASSIGNED_PROJECTS)
            or actor.has_permission(PERM_READ_OWN_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to view projects")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM projects WHERE id = ?;", (project_id,)).fetchone()
        if not row:
            return None

        # Customer isolation
        if actor.role == ROLE_CUSTOMER:
            if not actor.customer_id or actor.customer_id != row["customer_id"]:
                raise PermissionError("Customer cannot view other customers' projects")

        assigned_employees = json.loads(row["assigned_employees_json"]) if row["assigned_employees_json"] else []
        subcontractors = json.loads(row["subcontractors_json"]) if row["subcontractors_json"] else []

        # Technician assigned check
        if actor.role == ROLE_TECHNICIAN and actor.user_id not in assigned_employees:
            raise PermissionError("Technician can only view assigned projects")

        return Project(
            id=row["id"],
            customer_id=row["customer_id"],
            title=row["title"],
            property_address=row["property_address"],
            project_type=row["project_type"],
            status=row["status"],
            start_date=row["start_date"],
            expected_completion=row["expected_completion"],
            actual_completion=row["actual_completion"],
            project_manager_id=row["project_manager_id"],
            assigned_employees=assigned_employees,
            subcontractors=subcontractors if actor.role != ROLE_CUSTOMER else [],
            scope_of_work=row["scope_of_work"],
            estimated_cost=row["estimated_cost"] if actor.role != ROLE_CUSTOMER else 0.0,
            contract_amount=row["contract_amount"],
            actual_cost=row["actual_cost"] if actor.role != ROLE_CUSTOMER else 0.0,
            profit=row["profit"] if actor.role != ROLE_CUSTOMER else 0.0,
            notes=row["notes"] if actor.role != ROLE_CUSTOMER else None,
            warranty_info=row["warranty_info"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_projects(self, actor: AuthContext, customer_id: Optional[int] = None) -> List[Project]:
        if not (
            actor.has_permission(PERM_READ_ALL_PROJECTS)
            or actor.has_permission(PERM_READ_ASSIGNED_PROJECTS)
            or actor.has_permission(PERM_READ_OWN_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to list projects")

        query = "SELECT * FROM projects WHERE 1=1"
        params: List[Any] = []

        if actor.role == ROLE_CUSTOMER:
            if not actor.customer_id:
                return []
            query += " AND customer_id = ?"
            params.append(actor.customer_id)
        else:
            if customer_id is not None:
                query += " AND customer_id = ?"
                params.append(customer_id)

        query += " ORDER BY id DESC;"

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()

        results = []
        for r in rows:
            assigned = json.loads(r["assigned_employees_json"]) if r["assigned_employees_json"] else []
            if actor.role == ROLE_TECHNICIAN and actor.user_id not in assigned:
                continue

            results.append(
                Project(
                    id=r["id"],
                    customer_id=r["customer_id"],
                    title=r["title"],
                    property_address=r["property_address"],
                    project_type=r["project_type"],
                    status=r["status"],
                    start_date=r["start_date"],
                    expected_completion=r["expected_completion"],
                    actual_completion=r["actual_completion"],
                    project_manager_id=r["project_manager_id"],
                    assigned_employees=assigned,
                    subcontractors=json.loads(r["subcontractors_json"]) if actor.role != ROLE_CUSTOMER and r["subcontractors_json"] else [],
                    scope_of_work=r["scope_of_work"],
                    estimated_cost=r["estimated_cost"] if actor.role != ROLE_CUSTOMER else 0.0,
                    contract_amount=r["contract_amount"],
                    actual_cost=r["actual_cost"] if actor.role != ROLE_CUSTOMER else 0.0,
                    profit=r["profit"] if actor.role != ROLE_CUSTOMER else 0.0,
                    notes=r["notes"] if actor.role != ROLE_CUSTOMER else None,
                    warranty_info=r["warranty_info"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
            )
        return results

    # ==========================================
    # ESTIMATES
    # ==========================================

    def create_estimate(self, estimate: Estimate, actor: AuthContext) -> Estimate:
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to create estimates")

        now = utc_now_iso()
        estimate.created_at = now
        estimate.updated_at = now
        line_items_json = json.dumps(estimate.line_items)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO estimates (
                    estimate_number, customer_id, project_id, line_items_json,
                    subtotal, materials_cost, labor_cost, subcontractor_cost,
                    markup_percent, tax_amount, discount_amount, total_amount,
                    status, expiration_date, version, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    estimate.estimate_number,
                    estimate.customer_id,
                    estimate.project_id,
                    line_items_json,
                    estimate.subtotal,
                    estimate.materials_cost,
                    estimate.labor_cost,
                    estimate.subcontractor_cost,
                    estimate.markup_percent,
                    estimate.tax_amount,
                    estimate.discount_amount,
                    estimate.total_amount,
                    estimate.status,
                    estimate.expiration_date,
                    estimate.version,
                    estimate.notes,
                    now,
                    now,
                ),
            )
            estimate.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="estimate",
            entity_id=estimate.id,
            change_summary=f"Created estimate #{estimate.estimate_number} (${estimate.total_amount:.2f})",
            actor=actor,
            details=estimate.to_dict(),
        )
        return estimate

    # ==========================================
    # CONTRACTS / PROPOSALS
    # ==========================================

    def create_contract(self, contract: Contract, actor: AuthContext) -> Contract:
        if not actor.has_permission(PERM_WRITE_CONTRACTS):
            raise PermissionError("Actor lacks permission to create contracts")

        now = utc_now_iso()
        contract.created_at = now
        contract.updated_at = now

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO contracts (
                    contract_number, customer_id, project_id, estimate_id,
                    title, template_name, content, status, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    contract.contract_number,
                    contract.customer_id,
                    contract.project_id,
                    contract.estimate_id,
                    contract.title,
                    contract.template_name,
                    contract.content,
                    contract.status,
                    contract.version,
                    now,
                    now,
                ),
            )
            contract.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="contract",
            entity_id=contract.id,
            change_summary=f"Created contract #{contract.contract_number} '{contract.title}'",
            actor=actor,
            details=contract.to_dict(),
        )
        return contract

    def sign_contract(
        self,
        contract_id: int,
        signature_data: str,
        actor: AuthContext,
    ) -> Contract:
        """Sign a contract (customer digital signature or admin/manager approval)."""
        if not actor.has_permission(PERM_SIGN_CONTRACTS):
            raise PermissionError("Actor lacks permission to sign contracts")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM contracts WHERE id = ?;", (contract_id,)).fetchone()
        if not row:
            raise ValueError(f"Contract {contract_id} not found")

        # Customer isolation
        if actor.role == ROLE_CUSTOMER:
            if not actor.customer_id or actor.customer_id != row["customer_id"]:
                raise PermissionError("Customer cannot sign another customer's contract")

        now = utc_now_iso()
        with conn:
            conn.execute(
                """
                UPDATE contracts
                SET status = 'signed',
                    customer_signed_at = ?,
                    customer_signature_data = ?,
                    updated_at = ?
                WHERE id = ?;
                """,
                (now, signature_data, now, contract_id),
            )

        self.audit.log(
            action="sign",
            entity_type="contract",
            entity_id=contract_id,
            change_summary=f"Signed contract #{row['contract_number']}",
            actor=actor,
            details={"signed_at": now},
        )

        return Contract(
            id=row["id"],
            contract_number=row["contract_number"],
            customer_id=row["customer_id"],
            project_id=row["project_id"],
            estimate_id=row["estimate_id"],
            title=row["title"],
            template_name=row["template_name"],
            content=row["content"],
            status="signed",
            customer_signed_at=now,
            customer_signature_data=signature_data,
            version=row["version"],
            created_at=row["created_at"],
            updated_at=now,
        )

    # ==========================================
    # INVOICES & PAYMENTS
    # ==========================================

    def create_invoice(self, invoice: Invoice, actor: AuthContext) -> Invoice:
        if not actor.has_permission(PERM_WRITE_FINANCIALS):
            raise PermissionError("Actor lacks permission to create invoices")

        now = utc_now_iso()
        invoice.created_at = now
        invoice.updated_at = now
        invoice.balance_due = invoice.amount - invoice.deposit_amount
        payments_json = json.dumps(invoice.payments)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO invoices (
                    invoice_number, customer_id, project_id, status,
                    amount, deposit_amount, balance_due, due_date,
                    payments_json, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    invoice.invoice_number,
                    invoice.customer_id,
                    invoice.project_id,
                    invoice.status,
                    invoice.amount,
                    invoice.deposit_amount,
                    invoice.balance_due,
                    invoice.due_date,
                    payments_json,
                    invoice.notes,
                    now,
                    now,
                ),
            )
            invoice.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="invoice",
            entity_id=invoice.id,
            change_summary=f"Created invoice #{invoice.invoice_number} for ${invoice.amount:.2f}",
            actor=actor,
            details=invoice.to_dict(),
        )
        return invoice

    def record_payment(
        self,
        invoice_id: int,
        payment_amount: float,
        payment_method: str,
        transaction_reference: str,
        actor: AuthContext,
    ) -> Invoice:
        """Record a customer payment against an invoice."""
        if not actor.has_permission(PERM_WRITE_FINANCIALS):
            raise PermissionError("Actor lacks permission to record payments")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM invoices WHERE id = ?;", (invoice_id,)).fetchone()
        if not row:
            raise ValueError(f"Invoice {invoice_id} not found")

        now = utc_now_iso()
        payments = json.loads(row["payments_json"]) if row["payments_json"] else []
        payments.append({
            "timestamp": now,
            "amount": payment_amount,
            "method": payment_method,
            "reference": transaction_reference,
            "recorded_by_user_id": actor.user_id,
        })

        total_paid = row["deposit_amount"] + sum(p["amount"] for p in payments)
        new_balance = max(0.0, row["amount"] - total_paid)
        new_status = "paid" if new_balance <= 0.001 else "partially_paid"

        with conn:
            conn.execute(
                """
                UPDATE invoices
                SET status = ?,
                    balance_due = ?,
                    payments_json = ?,
                    updated_at = ?
                WHERE id = ?;
                """,
                (new_status, new_balance, json.dumps(payments), now, invoice_id),
            )

        self.audit.log(
            action="pay",
            entity_type="invoice",
            entity_id=invoice_id,
            change_summary=f"Recorded payment ${payment_amount:.2f} on invoice #{row['invoice_number']} via {payment_method}",
            actor=actor,
            details={"payment_amount": payment_amount, "new_balance": new_balance, "status": new_status},
        )

        return Invoice(
            id=row["id"],
            invoice_number=row["invoice_number"],
            customer_id=row["customer_id"],
            project_id=row["project_id"],
            status=new_status,
            amount=row["amount"],
            deposit_amount=row["deposit_amount"],
            balance_due=new_balance,
            due_date=row["due_date"],
            payments=payments,
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=now,
        )

    # ==========================================
    # DOCUMENTS
    # ==========================================

    def create_document(self, doc: Document, actor: AuthContext) -> Document:
        if not actor.has_permission(PERM_WRITE_DOCUMENTS):
            raise PermissionError("Actor lacks permission to register documents")

        now = utc_now_iso()
        doc.created_at = now
        doc.updated_at = now
        tags_json = json.dumps(doc.tags)
        permissions_json = json.dumps(doc.permissions)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO documents (
                    customer_id, project_id, document_type, title, file_path,
                    file_size_bytes, mime_type, tags_json, permissions_json,
                    expiration_date, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    doc.customer_id,
                    doc.project_id,
                    doc.document_type,
                    doc.title.strip(),
                    doc.file_path,
                    doc.file_size_bytes,
                    doc.mime_type,
                    tags_json,
                    permissions_json,
                    doc.expiration_date,
                    now,
                    now,
                ),
            )
            doc.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="document",
            entity_id=doc.id,
            change_summary=f"Added document '{doc.title}' ({doc.document_type})",
            actor=actor,
            details=doc.to_dict(),
        )
        return doc

    # ==========================================
    # SUBCONTRACTORS (B2/NEW-209 schema expansion, 2026-08-27)
    # ==========================================

    @staticmethod
    def _row_to_subcontractor(row) -> Subcontractor:
        return Subcontractor(
            id=row["id"],
            external_id=row["external_id"],
            contact_external_id=row["contact_external_id"],
            company_name=row["company_name"],
            legal_name=row["legal_name"],
            dba=row["dba"],
            contact_name=row["contact_name"],
            title=row["title"],
            phone=row["phone"],
            email=row["email"],
            website=row["website"],
            primary_trade=row["primary_trade"],
            secondary_trades=json.loads(row["secondary_trades_json"]) if row["secondary_trades_json"] else [],
            service_area=row["service_area"],
            years_in_business=row["years_in_business"],
            crew_size=row["crew_size"],
            residential_experience=row["residential_experience"],
            commercial_experience=row["commercial_experience"],
            typical_project_size=row["typical_project_size"],
            availability=row["availability"],
            emergency_availability=row["emergency_availability"],
            license_required=row["license_required"],
            license_type=row["license_type"],
            license_number=row["license_number"],
            license_expiration=row["license_expiration"],
            license_status=row["license_status"],
            general_liability=row["general_liability"],
            workers_comp=row["workers_comp"],
            coi_received=row["coi_received"],
            coi_expiration=row["coi_expiration"],
            additional_insured_status=row["additional_insured_status"],
            insurance_status=row["insurance_status"],
            w9_received=row["w9_received"],
            msa_sent=row["msa_sent"],
            msa_signed=row["msa_signed"],
            references=json.loads(row["references_json"]) if row["references_json"] else [],
            portfolio_url=row["portfolio_url"],
            qualification_status=row["qualification_status"],
            recruitment_step=row["recruitment_step"],
            lead_source=row["lead_source"],
            last_contact_at=row["last_contact_at"],
            next_followup_at=row["next_followup_at"],
            contact_attempts=row["contact_attempts"],
            dnc_status=row["dnc_status"],
            notes=row["notes"],
            qualification_data=json.loads(row["qualification_data_json"]) if row["qualification_data_json"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_subcontractor(self, sub: Subcontractor, actor: AuthContext) -> Subcontractor:
        if not actor.has_permission(PERM_WRITE_SUBCONTRACTORS):
            raise PermissionError("Actor lacks permission to create subcontractors")

        now = utc_now_iso()
        sub.created_at = now
        sub.updated_at = now
        secondary_trades_json = json.dumps(sub.secondary_trades)
        references_json = json.dumps(sub.references)
        qualification_data_json = json.dumps(sub.qualification_data)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO subcontractors (
                    external_id, contact_external_id, company_name, legal_name, dba,
                    contact_name, title, phone, email, website, primary_trade,
                    secondary_trades_json, service_area, years_in_business, crew_size,
                    residential_experience, commercial_experience, typical_project_size,
                    availability, emergency_availability, license_required, license_type,
                    license_number, license_expiration, license_status, general_liability,
                    workers_comp, coi_received, coi_expiration, additional_insured_status,
                    insurance_status, w9_received, msa_sent, msa_signed, references_json,
                    portfolio_url, qualification_status, recruitment_step, lead_source,
                    last_contact_at, next_followup_at, contact_attempts, dnc_status,
                    notes, qualification_data_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    sub.external_id,
                    sub.contact_external_id,
                    sub.company_name.strip(),
                    sub.legal_name,
                    sub.dba,
                    sub.contact_name,
                    sub.title,
                    sub.phone,
                    sub.email.strip().lower() if sub.email else None,
                    sub.website,
                    sub.primary_trade,
                    secondary_trades_json,
                    sub.service_area,
                    sub.years_in_business,
                    sub.crew_size,
                    sub.residential_experience,
                    sub.commercial_experience,
                    sub.typical_project_size,
                    sub.availability,
                    sub.emergency_availability,
                    sub.license_required,
                    sub.license_type,
                    sub.license_number,
                    sub.license_expiration,
                    sub.license_status,
                    sub.general_liability,
                    sub.workers_comp,
                    sub.coi_received,
                    sub.coi_expiration,
                    sub.additional_insured_status,
                    sub.insurance_status,
                    sub.w9_received,
                    sub.msa_sent,
                    sub.msa_signed,
                    references_json,
                    sub.portfolio_url,
                    sub.qualification_status,
                    sub.recruitment_step,
                    sub.lead_source,
                    sub.last_contact_at,
                    sub.next_followup_at,
                    sub.contact_attempts,
                    sub.dnc_status,
                    sub.notes,
                    qualification_data_json,
                    now,
                    now,
                ),
            )
            sub.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="subcontractor",
            entity_id=sub.id,
            change_summary=f"Added subcontractor '{sub.company_name}'",
            actor=actor,
            details=sub.to_dict(),
        )
        return sub

    def get_subcontractor(self, subcontractor_id: int, actor: AuthContext) -> Optional[Subcontractor]:
        if not actor.has_permission(PERM_READ_SUBCONTRACTORS):
            raise PermissionError("Actor lacks permission to view subcontractors")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM subcontractors WHERE id = ?;", (subcontractor_id,)).fetchone()
        if not row:
            return None
        return self._row_to_subcontractor(row)

    def get_subcontractor_by_external_id(self, external_id: str, actor: AuthContext) -> Optional[Subcontractor]:
        """Look up by Aigentik-CLI's own string ID (e.g. 'sub_0001').
        NEW-217: added so migrate_aigentik.py can check for an existing
        row before INSERT and skip re-migrating it, instead of hitting
        the `UNIQUE(external_id)` constraint as an IntegrityError."""
        if not actor.has_permission(PERM_READ_SUBCONTRACTORS):
            raise PermissionError("Actor lacks permission to view subcontractors")

        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM subcontractors WHERE external_id = ?;", (external_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_subcontractor(row)

    def find_subcontractor(
        self, query: str, actor: AuthContext
    ) -> Optional[Subcontractor]:
        """Fuzzy phone/email/name lookup mirroring
        ~/Codey-Aigentik/subcontractor-recruiter.js's findSubcontractor()
        (B2 task 4, third module continuation, 2026-08-27, see
        CODEY_MASTER_PLAN.md Sec6.4). Read-only lookup used as a
        prerequisite for a future JS cutover -- NOT yet wired to any JS
        call site.

        Per-record predicate order (must match the JS exactly, not just
        the overall result set): external_id exact match (case-
        insensitive) -> email exact match (case-insensitive) ->
        company_name substring -> legal_name substring -> dba substring
        -> contact_name substring -> bidirectional phone digit-substring
        match (only attempted when the query's stripped-digit count is
        >= 7). Returns the first row (ascending id, the closest analog
        to the JS array's insertion order) for which any check matches.
        """
        if not actor.has_permission(PERM_READ_SUBCONTRACTORS):
            raise PermissionError("Actor lacks permission to view subcontractors")

        # Empty/blank query must return None before anything else --
        # mirrors subcontractor-recruiter.js:201's `if (!identifier)
        # return null`. Without this guard an empty-string query would
        # substring-match every non-null company_name and silently
        # return the first row in the table instead of no match.
        if not query or not query.strip():
            return None

        q = query.strip().lower()
        clean_digits = re.sub(r"\D", "", q)
        phone_match_eligible = len(clean_digits) >= 7

        conn = self.db.get_connection()
        rows = conn.execute("SELECT * FROM subcontractors ORDER BY id ASC;").fetchall()
        for row in rows:
            external_id = row["external_id"]
            if external_id and external_id.lower() == q:
                return self._row_to_subcontractor(row)
            email = row["email"]
            if email and email.lower() == q:
                return self._row_to_subcontractor(row)
            company_name = row["company_name"]
            if company_name and q in company_name.lower():
                return self._row_to_subcontractor(row)
            legal_name = row["legal_name"]
            if legal_name and q in legal_name.lower():
                return self._row_to_subcontractor(row)
            dba = row["dba"]
            if dba and q in dba.lower():
                return self._row_to_subcontractor(row)
            contact_name = row["contact_name"]
            if contact_name and q in contact_name.lower():
                return self._row_to_subcontractor(row)
            if phone_match_eligible:
                p_digits = re.sub(r"\D", "", row["phone"] or "")
                # Deliberately mirrors subcontractor-recruiter.js:213-216
                # exactly, including its bug: `cleanDigits.includes(pDigits)`
                # is always true when pDigits is '' (empty string is a
                # substring of every string), so a NULL/empty-phone row
                # matches any query with >=7 stripped digits. Because this
                # is the last predicate checked per row and rows are
                # scanned in ascending id order, a phoneless row earlier
                # in the table can shadow the real phone-number owner
                # later in the table -- returning the wrong subcontractor's
                # record for what looks like an exact phone lookup. This
                # is a pre-existing JS bug (logged as NEW-246, not fixed
                # here), mirrored on purpose for drop-in cutover parity
                # per CODEY_MASTER_PLAN.md Sec6.4 -- do not "fix" this
                # without also fixing subcontractor-recruiter.js, or the
                # two lookups will silently diverge.
                if clean_digits in p_digits or p_digits in clean_digits:
                    return self._row_to_subcontractor(row)

        return None

    def list_subcontractors(
        self,
        actor: AuthContext,
        qualification_status: Optional[str] = None,
        primary_trade: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Subcontractor]:
        if not actor.has_permission(PERM_READ_SUBCONTRACTORS):
            raise PermissionError("Actor lacks permission to list subcontractors")

        query = "SELECT * FROM subcontractors WHERE 1=1"
        params: List[Any] = []

        if qualification_status:
            query += " AND qualification_status = ?"
            params.append(qualification_status)

        if primary_trade:
            query += " AND primary_trade = ?"
            params.append(primary_trade)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_subcontractor(row) for row in rows]

    def update_subcontractor_qualification(
        self,
        subcontractor_id: int,
        qualification_status: str,
        actor: AuthContext,
        recruitment_step: Optional[str] = None,
    ) -> Optional[Subcontractor]:
        """Move a subcontractor through the recruitment/qualification pipeline."""
        if not actor.has_permission(PERM_WRITE_SUBCONTRACTORS):
            raise PermissionError("Actor lacks permission to update subcontractors")

        now = utc_now_iso()
        conn = self.db.get_connection()
        with conn:
            if recruitment_step is not None:
                cursor = conn.execute(
                    """
                    UPDATE subcontractors SET qualification_status = ?, recruitment_step = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (qualification_status, recruitment_step, now, subcontractor_id),
                )
            else:
                cursor = conn.execute(
                    "UPDATE subcontractors SET qualification_status = ?, updated_at = ? WHERE id = ?;",
                    (qualification_status, now, subcontractor_id),
                )
            if cursor.rowcount == 0:
                return None

        self.audit.log(
            action="status_change",
            entity_type="subcontractor",
            entity_id=subcontractor_id,
            change_summary=f"Subcontractor {subcontractor_id} qualification set to '{qualification_status}'",
            actor=actor,
            details={"qualification_status": qualification_status, "recruitment_step": recruitment_step},
        )
        return self.get_subcontractor(subcontractor_id, actor)

    # Allow-listed fields for update_subcontractor (B2 task 4, third
    # module, 2026-08-27) -- matches only what index.js's call sites
    # actually merge, per CODEY_MASTER_PLAN.md Sec6.4. qualification_status
    # and recruitment_step are deliberately excluded (single-writer via
    # update_subcontractor_qualification()); id/external_id/timestamps/
    # audit-only fields are excluded as not caller-settable.
    ALLOWED_UPDATE_FIELDS = {
        "company_name", "legal_name", "dba", "contact_name", "title",
        "phone", "email", "website", "primary_trade", "secondary_trades",
        "service_area", "years_in_business", "crew_size",
        "typical_project_size", "availability", "emergency_availability",
        "license_number", "license_type", "license_required",
        "general_liability", "workers_comp", "qualification_data",
    }

    def update_subcontractor(
        self, subcontractor_id: int, updates: Dict[str, Any], actor: AuthContext
    ) -> Optional[Subcontractor]:
        """General partial-update method for subcontractors (B2 task 4,
        third module). Deliberately excludes qualification_status/
        recruitment_step -- see update_subcontractor_qualification()."""
        if not actor.has_permission(PERM_WRITE_SUBCONTRACTORS):
            raise PermissionError("Actor lacks permission to update subcontractors")

        unknown = set(updates) - self.ALLOWED_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unknown field(s) for subcontractor update: {sorted(unknown)}")

        for key, value in updates.items():
            if value is None:
                raise ValueError(
                    f"Field '{key}' cannot be set to None via update_subcontractor; omit the key instead"
                )

        if not updates:
            return self.get_subcontractor(subcontractor_id, actor)

        updates = dict(updates)
        if "email" in updates:
            updates["email"] = updates["email"].strip().lower()
        if "company_name" in updates:
            updates["company_name"] = updates["company_name"].strip()

        now = utc_now_iso()
        conn = self.db.get_connection()
        with conn:
            row = conn.execute(
                "SELECT qualification_data_json FROM subcontractors WHERE id = ?;",
                (subcontractor_id,),
            ).fetchone()
            if not row:
                return None

            set_clauses = []
            params: List[Any] = []
            for key, value in updates.items():
                if key == "qualification_data":
                    existing = json.loads(row["qualification_data_json"]) if row["qualification_data_json"] else {}
                    merged = {**existing, **value}
                    set_clauses.append("qualification_data_json = ?")
                    params.append(json.dumps(merged))
                elif key == "secondary_trades":
                    set_clauses.append("secondary_trades_json = ?")
                    params.append(json.dumps(value))
                else:
                    set_clauses.append(f"{key} = ?")
                    params.append(value)

            set_clauses.append("updated_at = ?")
            params.append(now)
            set_clauses.append("last_contact_at = ?")
            params.append(now)
            params.append(subcontractor_id)

            cursor = conn.execute(
                f"UPDATE subcontractors SET {', '.join(set_clauses)} WHERE id = ?;",
                params,
            )
            if cursor.rowcount == 0:
                return None

        updated_sub = self.get_subcontractor(subcontractor_id, actor)
        self.audit.log(
            action="update",
            entity_type="subcontractor",
            entity_id=subcontractor_id,
            change_summary=f"Subcontractor {subcontractor_id} updated ({', '.join(sorted(updates.keys()))})",
            actor=actor,
            details=updated_sub.to_dict(),
        )
        return updated_sub
