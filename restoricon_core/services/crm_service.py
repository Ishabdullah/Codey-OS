"""
CRM and Operations Business Services for Restoricon Core.
Orchestrates domain entities (Customers, Leads, Opportunities, Projects, Estimates,
Contracts, Invoices, Documents) with RBAC enforcement and automatic audit logging.
"""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
from typing import Any, Dict, List, Optional

from ..auth import (
    AuthContext,
    PERM_READ_ALL_CUSTOMERS,
    PERM_WRITE_CUSTOMERS,
    PERM_READ_LEADS,
    PERM_WRITE_LEADS,
    PERM_READ_OPPORTUNITIES,
    PERM_WRITE_OPPORTUNITIES,
    PERM_READ_CRM,
    PERM_WRITE_CRM,
    PERM_MANAGE_PIPELINE,
    PERM_SCORE_LEADS,
    PERM_READ_ALL_PROJECTS,
    PERM_READ_ASSIGNED_PROJECTS,
    PERM_READ_OWN_PROJECTS,
    PERM_WRITE_PROJECTS,
    PERM_READ_ESTIMATES,
    PERM_WRITE_ESTIMATES,
    PERM_READ_OWN_ESTIMATES,
    PERM_READ_CONTRACTS,
    PERM_WRITE_CONTRACTS,
    PERM_READ_OWN_CONTRACTS,
    PERM_SIGN_CONTRACTS,
    PERM_READ_DOCUMENTS,
    PERM_WRITE_DOCUMENTS,
    PERM_READ_OWN_DOCUMENTS,
    PERM_READ_FINANCIALS,
    PERM_WRITE_FINANCIALS,
    PERM_READ_OWN_FINANCIALS,
    PERM_READ_SUBCONTRACTORS,
    PERM_WRITE_SUBCONTRACTORS,
    PERM_READ_CONTACTS,
    PERM_WRITE_CONTACTS,
    ROLE_CUSTOMER,
    ROLE_TECHNICIAN,
    ROLE_ADMIN,
    _actor_may_reassign_project_staff,
)
from ..database import DatabaseManager
from ..models import (
    CommunicationRecord,
    Contact,
    Contract,
    Customer,
    Document,
    Estimate,
    Invoice,
    Lead,
    Opportunity,
    PipelineStage,
    Project,
    ProjectStage,
    STAGE_DEFAULT_PROBABILITIES,
    Subcontractor,
    Task,
    utc_now_iso,
)
from .audit_service import AuditService, build_audit_details, _AUDITABLE_CONTRACT_FIELDS, _AUDITABLE_INVOICE_FIELDS, _AUDITABLE_SUBCONTRACTOR_FIELDS, _AUDITABLE_PROJECT_FIELDS, _AUDITABLE_CONTACT_FIELDS
from .notification_service import NotificationService


class CRMService:
    """Core domain logic and data management for Restoricon Core."""

    def __init__(self, db_manager: DatabaseManager, audit_service: AuditService, notification_service: Optional[NotificationService] = None):
        self.db = db_manager
        self.audit = audit_service
        self.notification_service = notification_service

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
            details=build_audit_details(after=customer.to_dict()),
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
            results.append(self._row_to_customer(row))
        return results

    @staticmethod
    def _row_to_customer(row) -> Customer:
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
            notes=row["notes"],
            custom_fields=custom_fields,
            created_at=row["created_at"],
            last_contact_at=row["last_contact_at"],
            next_followup_at=row["next_followup_at"],
        )

    ALLOWED_CUSTOMER_UPDATE_FIELDS = {
        "first_name",
        "last_name",
        "company_name",
        "phone",
        "email",
        "mailing_address",
        "service_address",
        "customer_type",
        "customer_source",
        "assigned_user_id",
        "status",
        "tags",
        "notes",
        "custom_fields",
        "last_contact_at",
        "next_followup_at",
    }

    def update_customer(
        self, customer_id: int, updates: Dict[str, Any], actor: AuthContext
    ) -> Optional[Customer]:
        """Partial update for customer records with allow-list enforcement,
        None-value guard, custom_fields shallow merge, and audit logging."""
        if not actor.has_permission(PERM_WRITE_CUSTOMERS):
            raise PermissionError("Actor lacks permission to update customers")

        unknown = set(updates) - self.ALLOWED_CUSTOMER_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unknown field(s) for customer update: {sorted(unknown)}")

        for key, value in updates.items():
            if value is None:
                raise ValueError(
                    f"Field '{key}' cannot be set to None via update_customer; omit the key instead"
                )

        if not updates:
            return self.get_customer(customer_id, actor)

        updates = dict(updates)
        if "email" in updates and isinstance(updates["email"], str):
            updates["email"] = updates["email"].strip().lower()
        if "first_name" in updates and isinstance(updates["first_name"], str):
            updates["first_name"] = updates["first_name"].strip()
        if "last_name" in updates and isinstance(updates["last_name"], str):
            updates["last_name"] = updates["last_name"].strip()

        conn = self.db.get_connection()
        with conn:
            row = conn.execute(
                "SELECT * FROM customers WHERE id = ?;",
                (customer_id,),
            ).fetchone()
            if not row:
                return None

            # Pre-image scoped to the submitted keys only. No _row_to_customer
            # pre-image is used here: the after-image builder (get_customer ->
            # _row_to_customer) is a straight column pass-through for every
            # allowed scalar field, so reading row[k] directly is equivalent.
            _before = {}
            for k in updates:
                if k == "custom_fields":
                    _before[k] = json.loads(row["custom_fields_json"]) if row["custom_fields_json"] else {}
                elif k == "tags":
                    _before[k] = json.loads(row["tags_json"]) if row["tags_json"] else []
                else:
                    _before[k] = row[k]

            set_clauses = []
            params: List[Any] = []
            for key, value in updates.items():
                if key == "custom_fields":
                    existing = json.loads(row["custom_fields_json"]) if row["custom_fields_json"] else {}
                    merged = {**existing, **value}
                    set_clauses.append("custom_fields_json = ?")
                    params.append(json.dumps(merged))
                elif key == "tags":
                    set_clauses.append("tags_json = ?")
                    params.append(json.dumps(value))
                else:
                    set_clauses.append(f"{key} = ?")
                    params.append(value)

            params.append(customer_id)
            cursor = conn.execute(
                f"UPDATE customers SET {', '.join(set_clauses)} WHERE id = ?;",
                params,
            )
            if cursor.rowcount == 0:
                return None

        updated_cust = self.get_customer(customer_id, actor)
        # fields=sorted(updates) here is a diff-domain scope, not a security
        # filter -- Customer.to_dict() carries nothing sensitive, so there is
        # no _AUDITABLE_CUSTOMER_FIELDS constant. It bounds changed_fields to
        # the keys actually submitted.
        details = build_audit_details(
            before=_before,
            after=updated_cust.to_dict() if updated_cust else None,
            fields=sorted(updates),
        )
        self.audit.log(
            action="update",
            entity_type="customer",
            entity_id=customer_id,
            change_summary=f"Customer {customer_id} updated ({', '.join(sorted(updates.keys()))})",
            actor=actor,
            details=details,
        )
        return updated_cust

    def upsert_customer(self, customer: Customer, actor: AuthContext) -> Customer:
        """Create or update customer by external_id with write-through semantics."""
        if not actor.has_permission(PERM_WRITE_CUSTOMERS):
            raise PermissionError("Actor lacks permission to create or update customers")

        if not customer.external_id or not customer.external_id.strip():
            raise ValueError("upsert_customer requires a non-empty external_id")

        existing = self.get_customer_by_external_id(customer.external_id, actor)
        if existing is None:
            return self.create_customer(customer, actor)

        immutable = {"external_id", "created_at", "id"}
        raw = customer.to_dict()
        updates = {
            k: v
            for k, v in raw.items()
            if k not in immutable and v is not None and k in self.ALLOWED_CUSTOMER_UPDATE_FIELDS
        }
        if not updates:
            return existing

        updated = self.update_customer(existing.id, updates, actor)
        return updated or existing

    def find_customer(self, query: str, actor: AuthContext) -> Optional[Customer]:
        """Fuzzy phone/email/name/address lookup mirroring findCustomer() in JS.
        Checks external_id exact match -> phone digit substring match (len >= 7) ->
        email exact match -> name substring match -> address substring match.
        Returns first matching customer in ascending id order."""
        if not actor.has_permission(PERM_READ_ALL_CUSTOMERS):
            raise PermissionError("Actor lacks permission to search customers")

        if not query or not query.strip():
            return None

        q = query.strip().lower()
        clean_digits = re.sub(r"\D", "", q)
        phone_match_eligible = len(clean_digits) >= 7

        conn = self.db.get_connection()
        rows = conn.execute("SELECT * FROM customers ORDER BY id ASC;").fetchall()
        for row in rows:
            external_id = row["external_id"]
            if external_id and external_id.lower() == q:
                return self._row_to_customer(row)

            if phone_match_eligible:
                p_digits = re.sub(r"\D", "", row["phone"] or "")
                if p_digits and (clean_digits in p_digits or p_digits in clean_digits):
                    return self._row_to_customer(row)

            email = row["email"]
            if email and email.lower() == q:
                return self._row_to_customer(row)

            first_name = row["first_name"] or ""
            last_name = row["last_name"] or ""
            full_name = f"{first_name} {last_name}".strip().lower()
            company_name = (row["company_name"] or "").lower()

            if (first_name and q in first_name.lower()) or (last_name and q in last_name.lower()) or (full_name and q in full_name):
                return self._row_to_customer(row)
            if company_name and q in company_name:
                return self._row_to_customer(row)

            mailing_address = (row["mailing_address"] or "").lower()
            service_address = (row["service_address"] or "").lower()
            if (mailing_address and q in mailing_address) or (service_address and q in service_address):
                return self._row_to_customer(row)

        return None

    # ==========================================
    # LEADS
    # ==========================================

    @staticmethod
    def _row_to_lead(row: Any) -> Lead:
        keys = row.keys() if hasattr(row, "keys") else []
        score_factors: Dict[str, Any] = {}
        if "score_factors_json" in keys and row["score_factors_json"]:
            try:
                score_factors = json.loads(row["score_factors_json"])
            except Exception:
                score_factors = {}
        return Lead(
            id=row["id"],
            external_id=row["external_id"] if "external_id" in keys else None,
            customer_id=row["customer_id"] if "customer_id" in keys else None,
            source=row["source"],
            status=row["status"],
            score=row["score"],
            score_factors=score_factors,
            property_type=row["property_type"] if "property_type" in keys else None,
            project_scope=row["project_scope"] if "project_scope" in keys else None,
            urgency_level=row["urgency_level"] if "urgency_level" in keys else None,
            insurance_status=row["insurance_status"] if "insurance_status" in keys else None,
            estimated_value=row["estimated_value"],
            assigned_user_id=row["assigned_user_id"] if "assigned_user_id" in keys else None,
            first_contact_at=row["first_contact_at"] if "first_contact_at" in keys else None,
            last_contact_at=row["last_contact_at"] if "last_contact_at" in keys else None,
            next_followup_at=row["next_followup_at"] if "next_followup_at" in keys else None,
            notes=row["notes"] if "notes" in keys else None,
            lost_reason=row["lost_reason"] if "lost_reason" in keys else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_lead(self, lead: Lead, actor: AuthContext) -> Lead:
        if not (actor.has_permission(PERM_WRITE_LEADS) or actor.has_permission(PERM_WRITE_CRM)):
            raise PermissionError("Actor lacks permission to create leads")

        now = utc_now_iso()
        lead.created_at = now
        lead.updated_at = now
        factors_json = json.dumps(lead.score_factors) if lead.score_factors else "{}"

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO leads (
                    external_id, customer_id, source, status, score, score_factors_json,
                    property_type, project_scope, urgency_level, insurance_status,
                    estimated_value, assigned_user_id, first_contact_at, last_contact_at,
                    next_followup_at, notes, lost_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    lead.external_id,
                    lead.customer_id,
                    lead.source,
                    lead.status,
                    lead.score,
                    factors_json,
                    lead.property_type,
                    lead.project_scope,
                    lead.urgency_level,
                    lead.insurance_status,
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
            details=build_audit_details(after=lead.to_dict()),
        )
        return lead

    def get_lead(self, lead_id: int, actor: AuthContext) -> Optional[Lead]:
        if not (actor.has_permission(PERM_READ_LEADS) or actor.has_permission(PERM_READ_CRM)):
            raise PermissionError("Actor lacks permission to view leads")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM leads WHERE id = ?;", (lead_id,)).fetchone()
        if not row:
            return None
        return self._row_to_lead(row)

    def list_leads(self, actor: AuthContext, status: Optional[str] = None) -> List[Lead]:
        if not (actor.has_permission(PERM_READ_LEADS) or actor.has_permission(PERM_READ_CRM)):
            raise PermissionError("Actor lacks permission to view leads")

        query = "SELECT * FROM leads WHERE 1=1"
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY id DESC;"

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_lead(r) for r in rows]

    def get_lead_by_external_id(self, external_id: str, actor: AuthContext) -> Optional[Lead]:
        """Look up by an external system's own string ID (NEW-212/NEW-232,
        2026-08-27), matching the subcontractors/appointments/
        automation_rules by_external_id lookup pattern."""
        if not (actor.has_permission(PERM_READ_LEADS) or actor.has_permission(PERM_READ_CRM)):
            raise PermissionError("Actor lacks permission to look up leads by external ID")

        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM leads WHERE external_id = ?;", (external_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_lead(row)

    def update_lead(self, lead_id: int, updates: Dict[str, Any], actor: AuthContext) -> Optional[Lead]:
        if not (actor.has_permission(PERM_WRITE_LEADS) or actor.has_permission(PERM_WRITE_CRM)):
            raise PermissionError("Actor lacks permission to update leads")

        lead = self.get_lead(lead_id, actor)
        if not lead:
            return None

        _before = lead.to_dict()

        allowed_fields = {
            "customer_id", "source", "status", "score", "score_factors",
            "property_type", "project_scope", "urgency_level", "insurance_status",
            "estimated_value", "assigned_user_id", "first_contact_at",
            "last_contact_at", "next_followup_at", "notes", "lost_reason"
        }
        for k, v in updates.items():
            if k in allowed_fields:
                setattr(lead, k, v)

        now = utc_now_iso()
        lead.updated_at = now
        factors_json = json.dumps(lead.score_factors) if lead.score_factors else "{}"

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                UPDATE leads SET
                    customer_id = ?, source = ?, status = ?, score = ?, score_factors_json = ?,
                    property_type = ?, project_scope = ?, urgency_level = ?, insurance_status = ?,
                    estimated_value = ?, assigned_user_id = ?, first_contact_at = ?,
                    last_contact_at = ?, next_followup_at = ?, notes = ?, lost_reason = ?,
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    lead.customer_id, lead.source, lead.status, lead.score, factors_json,
                    lead.property_type, lead.project_scope, lead.urgency_level, lead.insurance_status,
                    lead.estimated_value, lead.assigned_user_id, lead.first_contact_at,
                    lead.last_contact_at, lead.next_followup_at, lead.notes, lead.lost_reason,
                    now, lead_id,
                ),
            )

        _after = self.get_lead(lead_id, actor)
        self.audit.log(
            action="update",
            entity_type="lead",
            entity_id=lead_id,
            change_summary=f"Updated lead {lead_id}",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_after.to_dict() if _after else None,
            ),
        )
        return lead

    def score_lead(
        self,
        lead_id_or_obj: int | Lead | Dict[str, Any],
        actor: AuthContext,
        factors: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Deterministic 5-dimension lead qualification scoring (0-100 pts):
        1. Project scope (25 pts)
        2. Property type (15 pts)
        3. Urgency level (25 pts)
        4. Insurance claim status (20 pts)
        5. Responsiveness / engagement (15 pts)
        """
        if not (
            actor.has_permission(PERM_SCORE_LEADS)
            or actor.has_permission(PERM_WRITE_LEADS)
            or actor.has_permission(PERM_READ_LEADS)
            or actor.has_permission(PERM_READ_CRM)
        ):
            raise PermissionError("Actor lacks permission to score leads")

        lead_id: Optional[int] = None
        db_lead: Optional[Lead] = None

        if isinstance(lead_id_or_obj, int):
            lead_id = lead_id_or_obj
            db_lead = self.get_lead(lead_id, actor)
            if not db_lead:
                raise ValueError(f"Lead {lead_id} not found")
            input_dict = db_lead.to_dict()
        elif isinstance(lead_id_or_obj, Lead):
            db_lead = lead_id_or_obj
            lead_id = db_lead.id
            input_dict = db_lead.to_dict()
        elif isinstance(lead_id_or_obj, dict):
            input_dict = dict(lead_id_or_obj)
            lead_id = input_dict.get("id")
            if lead_id and not db_lead:
                db_lead = self.get_lead(int(lead_id), actor)
        else:
            input_dict = {}

        if factors:
            input_dict.update(factors)

        scope = str(input_dict.get("project_scope", "") or "").lower().strip()
        prop = str(input_dict.get("property_type", "") or "").lower().strip()
        urgency = str(input_dict.get("urgency_level", "") or "").lower().strip()
        insurance = str(input_dict.get("insurance_status", "") or "").lower().strip()
        responsiveness = str(input_dict.get("responsiveness", "") or "").lower().strip()

        # Dimension 1: Scope (max 25 pts)
        if any(w in scope for w in ["full_restoration", "reconstruction", "rebuild", "commercial", "large", "multi_room"]):
            scope_pts = 25
        elif any(w in scope for w in ["water_mitigation", "mold_remediation", "fire_damage", "smoke", "medium", "storm"]):
            scope_pts = 20
        elif any(w in scope for w in ["roofing", "repairs", "small", "leak_repair", "patch"]):
            scope_pts = 12
        elif any(w in scope for w in ["inspection", "consultation", "minor", "assessment"]):
            scope_pts = 5
        elif scope:
            scope_pts = 10
        else:
            scope_pts = 0

        # Dimension 2: Property (max 15 pts)
        if any(w in prop for w in ["commercial", "multi_family", "industrial", "enterprise"]):
            prop_pts = 15
        elif any(w in prop for w in ["residential", "single_family", "home"]):
            prop_pts = 12
        elif any(w in prop for w in ["condo", "townhouse", "apartment", "other"]):
            prop_pts = 8
        elif prop:
            prop_pts = 5
        else:
            prop_pts = 0

        # Dimension 3: Urgency (max 25 pts)
        if any(w in urgency for w in ["emergency", "immediate", "urgent", "active_leak", "standing_water", "within_24h", "24h"]):
            urgency_pts = 25
        elif any(w in urgency for w in ["high", "this_week", "1_3_days", "soon", "48h"]):
            urgency_pts = 20
        elif any(w in urgency for w in ["medium", "standard", "within_month", "2_weeks"]):
            urgency_pts = 12
        elif any(w in urgency for w in ["low", "flexible", "planning", "future"]):
            urgency_pts = 5
        elif urgency:
            urgency_pts = 5
        else:
            urgency_pts = 0

        # Dimension 4: Insurance (max 20 pts)
        if any(w in insurance for w in ["claim_filed", "approved", "active_claim", "adjuster_assigned", "carrier_approved"]):
            ins_pts = 20
        elif any(w in insurance for w in ["filing_claim", "in_process", "insurance_covered", "filing"]):
            ins_pts = 15
        elif any(w in insurance for w in ["self_pay", "out_of_pocket", "private_pay", "cash"]):
            ins_pts = 12
        elif any(w in insurance for w in ["uninsured", "denied", "unknown"]):
            ins_pts = 5
        elif insurance:
            ins_pts = 5
        else:
            ins_pts = 0

        # Dimension 5: Responsiveness (max 15 pts)
        if any(w in responsiveness for w in ["high", "immediate_response", "has_appointment", "instant"]):
            resp_pts = 15
        elif any(w in responsiveness for w in ["medium", "contacted", "responsive", "normal"]):
            resp_pts = 10
        elif any(w in responsiveness for w in ["low", "unresponsive", "first_contact", "slow"]):
            resp_pts = 5
        elif responsiveness:
            resp_pts = 5
        else:
            resp_pts = 10

        total_score = min(100, max(0, scope_pts + prop_pts + urgency_pts + ins_pts + resp_pts))

        if total_score >= 80:
            grade = "Hot"
        elif total_score >= 60:
            grade = "Warm"
        elif total_score >= 40:
            grade = "Cold"
        else:
            grade = "Unqualified"

        breakdown = {
            "project_scope": {"value": scope or None, "points": scope_pts, "max": 25},
            "property_type": {"value": prop or None, "points": prop_pts, "max": 15},
            "urgency_level": {"value": urgency or None, "points": urgency_pts, "max": 25},
            "insurance_status": {"value": insurance or None, "points": ins_pts, "max": 20},
            "responsiveness": {"value": responsiveness or None, "points": resp_pts, "max": 15},
            "total_score": total_score,
            "grade": grade,
        }

        # If lead exists in DB, update lead record
        if lead_id and db_lead:
            db_updates: Dict[str, Any] = {
                "score": total_score,
                "score_factors": breakdown,
            }
            if scope:
                db_updates["project_scope"] = scope
            if prop:
                db_updates["property_type"] = prop
            if urgency:
                db_updates["urgency_level"] = urgency
            if insurance:
                db_updates["insurance_status"] = insurance
            self.update_lead(lead_id, db_updates, actor)

        return {
            "lead_id": lead_id,
            "score": total_score,
            "grade": grade,
            "score_factors": breakdown,
        }

    # ==========================================
    # OPPORTUNITIES / SALES PIPELINE
    # ==========================================

    @staticmethod
    def _row_to_opportunity(row: Any) -> Opportunity:
        keys = row.keys() if hasattr(row, "keys") else []
        return Opportunity(
            id=row["id"],
            customer_id=row["customer_id"],
            project_id=row["project_id"] if "project_id" in keys else None,
            title=row["title"],
            estimated_value=row["estimated_value"],
            probability=row["probability"],
            pipeline_stage=PipelineStage.normalize(row["pipeline_stage"]),
            expected_close_date=row["expected_close_date"] if "expected_close_date" in keys else None,
            assigned_user_id=row["assigned_user_id"] if "assigned_user_id" in keys else None,
            competitor_info=row["competitor_info"] if "competitor_info" in keys else None,
            notes=row["notes"] if "notes" in keys else None,
            lost_reason=row["lost_reason"] if "lost_reason" in keys else None,
            insurance_carrier=row["insurance_carrier"] if "insurance_carrier" in keys else None,
            claim_number=row["claim_number"] if "claim_number" in keys else None,
            adjuster_name=row["adjuster_name"] if "adjuster_name" in keys else None,
            adjuster_phone=row["adjuster_phone"] if "adjuster_phone" in keys else None,
            adjuster_email=row["adjuster_email"] if "adjuster_email" in keys else None,
            deductible=row["deductible"] if "deductible" in keys else None,
            insurance_claim_status=row["insurance_claim_status"] if "insurance_claim_status" in keys else None,
            stage_entered_at=row["stage_entered_at"] if "stage_entered_at" in keys else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_opportunity(self, opp: Opportunity, actor: AuthContext) -> Opportunity:
        if not (actor.has_permission(PERM_WRITE_OPPORTUNITIES) or actor.has_permission(PERM_WRITE_CRM)):
            raise PermissionError("Actor lacks permission to create opportunities")

        now = utc_now_iso()
        opp.created_at = now
        opp.updated_at = now
        opp.pipeline_stage = PipelineStage.normalize(opp.pipeline_stage)
        if not opp.stage_entered_at:
            opp.stage_entered_at = now
        if opp.probability == 0.0 and opp.pipeline_stage in PipelineStage.STAGE_DEFAULT_PROBABILITIES:
            opp.probability = PipelineStage.STAGE_DEFAULT_PROBABILITIES[opp.pipeline_stage]

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO opportunities (
                    customer_id, project_id, title, estimated_value, probability,
                    pipeline_stage, expected_close_date, assigned_user_id,
                    competitor_info, notes, lost_reason, insurance_carrier,
                    claim_number, adjuster_name, adjuster_phone, adjuster_email,
                    deductible, insurance_claim_status, stage_entered_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                    opp.lost_reason,
                    opp.insurance_carrier,
                    opp.claim_number,
                    opp.adjuster_name,
                    opp.adjuster_phone,
                    opp.adjuster_email,
                    opp.deductible,
                    opp.insurance_claim_status,
                    opp.stage_entered_at,
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
            details=build_audit_details(after=opp.to_dict()),
        )
        return opp

    def get_opportunity(self, opp_id: int, actor: AuthContext) -> Optional[Opportunity]:
        if not (actor.has_permission(PERM_READ_OPPORTUNITIES) or actor.has_permission(PERM_READ_CRM)):
            raise PermissionError("Actor lacks permission to view opportunities")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM opportunities WHERE id = ?;", (opp_id,)).fetchone()
        if not row:
            return None
        return self._row_to_opportunity(row)

    def list_opportunities(
        self,
        actor: AuthContext,
        pipeline_stage: Optional[str] = None,
        customer_id: Optional[int] = None,
        assigned_user_id: Optional[int] = None,
    ) -> List[Opportunity]:
        if not (actor.has_permission(PERM_READ_OPPORTUNITIES) or actor.has_permission(PERM_READ_CRM)):
            raise PermissionError("Actor lacks permission to view opportunities")

        query = "SELECT * FROM opportunities WHERE 1=1"
        params: List[Any] = []
        if pipeline_stage:
            norm_stage = PipelineStage.normalize(pipeline_stage)
            query += " AND pipeline_stage = ?"
            params.append(norm_stage)
        if customer_id is not None:
            query += " AND customer_id = ?"
            params.append(customer_id)
        if assigned_user_id is not None:
            query += " AND assigned_user_id = ?"
            params.append(assigned_user_id)
        query += " ORDER BY id DESC;"

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_opportunity(r) for r in rows]

    def update_opportunity(
        self, opp_id: int, updates: Dict[str, Any], actor: AuthContext
    ) -> Optional[Opportunity]:
        if not (actor.has_permission(PERM_WRITE_OPPORTUNITIES) or actor.has_permission(PERM_WRITE_CRM)):
            raise PermissionError("Actor lacks permission to update opportunities")

        opp = self.get_opportunity(opp_id, actor)
        if not opp:
            return None

        _before = opp.to_dict()

        if "pipeline_stage" in updates and PipelineStage.normalize(updates["pipeline_stage"]) != opp.pipeline_stage:
            return self.transition_opportunity_stage(
                opp_id,
                updates["pipeline_stage"],
                actor,
                lost_reason=updates.get("lost_reason"),
                notes=updates.get("notes"),
            )

        allowed_fields = {
            "customer_id", "project_id", "title", "estimated_value", "probability",
            "expected_close_date", "assigned_user_id", "competitor_info", "notes",
            "lost_reason", "insurance_carrier", "claim_number", "adjuster_name",
            "adjuster_phone", "adjuster_email", "deductible", "insurance_claim_status",
            "stage_entered_at",
        }
        for k, v in updates.items():
            if k in allowed_fields:
                setattr(opp, k, v)

        now = utc_now_iso()
        opp.updated_at = now

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                UPDATE opportunities SET
                    customer_id = ?, project_id = ?, title = ?, estimated_value = ?,
                    probability = ?, pipeline_stage = ?, expected_close_date = ?,
                    assigned_user_id = ?, competitor_info = ?, notes = ?, lost_reason = ?,
                    insurance_carrier = ?, claim_number = ?, adjuster_name = ?,
                    adjuster_phone = ?, adjuster_email = ?, deductible = ?,
                    insurance_claim_status = ?, stage_entered_at = ?, updated_at = ?
                WHERE id = ?;
                """,
                (
                    opp.customer_id, opp.project_id, opp.title, opp.estimated_value,
                    opp.probability, opp.pipeline_stage, opp.expected_close_date,
                    opp.assigned_user_id, opp.competitor_info, opp.notes, opp.lost_reason,
                    opp.insurance_carrier, opp.claim_number, opp.adjuster_name,
                    opp.adjuster_phone, opp.adjuster_email, opp.deductible,
                    opp.insurance_claim_status, opp.stage_entered_at, now, opp_id,
                ),
            )

        _after = self.get_opportunity(opp_id, actor)
        self.audit.log(
            action="update",
            entity_type="opportunity",
            entity_id=opp_id,
            change_summary=f"Updated opportunity {opp_id}",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_after.to_dict() if _after else None,
            ),
        )
        return opp

    def transition_opportunity_stage(
        self,
        opp_id: int,
        new_stage: str,
        actor: AuthContext,
        lost_reason: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Opportunity:
        """
        Transition an opportunity to a new pipeline stage with validation:
        - Validates that new_stage is one of the 9 canonical stages.
        - Enforces lost_reason requirement when transitioning to LOST.
        - Updates stage_entered_at, probability, and logs audit.
        - Generates automated cadence tasks for the target stage.
        """
        if not (
            actor.has_permission(PERM_MANAGE_PIPELINE)
            or actor.has_permission(PERM_WRITE_OPPORTUNITIES)
            or actor.has_permission(PERM_WRITE_CRM)
        ):
            raise PermissionError("Actor lacks permission to manage sales pipeline stages")

        opp = self.get_opportunity(opp_id, actor)
        if not opp:
            raise ValueError(f"Opportunity {opp_id} not found")

        _before = opp.to_dict()

        canonical_stage = PipelineStage.normalize(new_stage)
        if not PipelineStage.is_valid(canonical_stage):
            raise ValueError(f"Invalid pipeline stage: '{new_stage}'")

        if canonical_stage == PipelineStage.LOST:
            if not lost_reason or not str(lost_reason).strip():
                raise ValueError("A lost_reason is required when transitioning an opportunity to LOST")
            opp.lost_reason = str(lost_reason).strip()
            opp.probability = 0.0
        elif canonical_stage == PipelineStage.WON:
            opp.probability = 1.0
        else:
            opp.probability = PipelineStage.STAGE_DEFAULT_PROBABILITIES.get(canonical_stage, opp.probability)

        old_stage = opp.pipeline_stage
        opp.pipeline_stage = canonical_stage
        now = utc_now_iso()
        opp.stage_entered_at = now
        opp.updated_at = now
        if notes:
            opp.notes = f"{opp.notes}\n{notes}".strip() if opp.notes else str(notes).strip()

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                UPDATE opportunities SET
                    pipeline_stage = ?, probability = ?, lost_reason = ?,
                    stage_entered_at = ?, notes = ?, updated_at = ?
                WHERE id = ?;
                """,
                (
                    opp.pipeline_stage,
                    opp.probability,
                    opp.lost_reason,
                    opp.stage_entered_at,
                    opp.notes,
                    now,
                    opp_id,
                ),
            )

        _after = self.get_opportunity(opp_id, actor)

        # Generate cadence follow-up tasks for the new stage.
        # Initialized before the try so the except path can't NameError.
        _cadence_tasks = []
        try:
            _cadence_tasks = self.generate_cadence_tasks(opp, actor)
        except Exception:
            pass

        # generate_cadence_tasks creates 0 or 1 Task via self.create_task,
        # which writes its OWN create audit row. Recording the id here is a
        # cross-reference pointer, not a double-log.
        _side_effects = {}
        if _cadence_tasks:
            t = _cadence_tasks[0]
            _side_effects["cadence_task_created"] = {
                "id": t.id, "rule_name": t.rule_name, "title": t.title,
            }
        if notes:
            _side_effects["notes_appended"] = notes

        self.audit.log(
            action="stage_transition",
            entity_type="opportunity",
            entity_id=opp_id,
            change_summary=f"Transitioned opportunity '{opp.title}' ({opp_id}) from '{old_stage}' to '{canonical_stage}'",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_after.to_dict() if _after else None,
                side_effects=_side_effects or None,
            ),
        )
        return opp

    def get_pipeline_summary(self, actor: AuthContext) -> Dict[str, Any]:
        """
        Aggregate deal count, total value, and weighted value grouped by stage.
        """
        if not (actor.has_permission(PERM_READ_OPPORTUNITIES) or actor.has_permission(PERM_READ_CRM)):
            raise PermissionError("Actor lacks permission to view sales pipeline summary")

        all_opps = self.list_opportunities(actor)
        stage_metrics: Dict[str, Dict[str, Any]] = {}

        for stage in PipelineStage.STAGE_ORDER:
            stage_metrics[stage] = {
                "stage": stage,
                "count": 0,
                "total_value": 0.0,
                "weighted_value": 0.0,
                "avg_value": 0.0,
            }

        total_pipeline_value = 0.0
        total_weighted_value = 0.0
        won_count = 0
        won_value = 0.0
        lost_count = 0
        lost_value = 0.0

        for o in all_opps:
            st = PipelineStage.normalize(o.pipeline_stage)
            if st not in stage_metrics:
                stage_metrics[st] = {
                    "stage": st,
                    "count": 0,
                    "total_value": 0.0,
                    "weighted_value": 0.0,
                    "avg_value": 0.0,
                }
            val = float(o.estimated_value or 0.0)
            prob = float(o.probability or 0.0)
            weighted = val * prob

            stage_metrics[st]["count"] += 1
            stage_metrics[st]["total_value"] += val
            stage_metrics[st]["weighted_value"] += weighted

            if st == PipelineStage.WON:
                won_count += 1
                won_value += val
            elif st == PipelineStage.LOST:
                lost_count += 1
                lost_value += val
            else:
                total_pipeline_value += val
                total_weighted_value += weighted

        for st, data in stage_metrics.items():
            if data["count"] > 0:
                data["avg_value"] = round(data["total_value"] / data["count"], 2)
            data["total_value"] = round(data["total_value"], 2)
            data["weighted_value"] = round(data["weighted_value"], 2)

        closed_total = won_count + lost_count
        win_rate = round(won_count / closed_total, 4) if closed_total > 0 else 0.0

        return {
            "stages": stage_metrics,
            "stage_order": PipelineStage.STAGE_ORDER,
            "total_deals": len(all_opps),
            "active_pipeline_value": round(total_pipeline_value, 2),
            "active_weighted_value": round(total_weighted_value, 2),
            "won_deals": won_count,
            "won_value": round(won_value, 2),
            "lost_deals": lost_count,
            "lost_value": round(lost_value, 2),
            "win_rate": win_rate,
        }

    # ==========================================
    # TASKS & FOLLOW-UP CADENCE
    # ==========================================

    @staticmethod
    def _row_to_task(row: Any) -> Task:
        keys = row.keys() if hasattr(row, "keys") else []
        return Task(
            id=row["id"],
            external_id=row["external_id"] if "external_id" in keys else None,
            title=row["title"],
            description=row["description"] if "description" in keys else None,
            task_type=row["task_type"],
            status=row["status"],
            priority=row["priority"],
            due_date=row["due_date"] if "due_date" in keys else None,
            completed_at=row["completed_at"] if "completed_at" in keys else None,
            customer_id=row["customer_id"] if "customer_id" in keys else None,
            opportunity_id=row["opportunity_id"] if "opportunity_id" in keys else None,
            lead_id=row["lead_id"] if "lead_id" in keys else None,
            assigned_user_id=row["assigned_user_id"] if "assigned_user_id" in keys else None,
            trigger_source=row["trigger_source"] if "trigger_source" in keys else None,
            rule_name=row["rule_name"] if "rule_name" in keys else None,
            notes=row["notes"] if "notes" in keys else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_task(self, task: Task, actor: AuthContext) -> Task:
        if not (
            actor.has_permission(PERM_WRITE_CRM)
            or actor.has_permission(PERM_WRITE_OPPORTUNITIES)
            or actor.has_permission(PERM_WRITE_LEADS)
        ):
            raise PermissionError("Actor lacks permission to create tasks")

        now = utc_now_iso()
        task.created_at = now
        task.updated_at = now

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO tasks (
                    external_id, title, description, task_type, status,
                    priority, due_date, completed_at, customer_id,
                    opportunity_id, lead_id, assigned_user_id, trigger_source,
                    rule_name, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    task.external_id,
                    task.title.strip(),
                    task.description,
                    task.task_type,
                    task.status,
                    task.priority,
                    task.due_date,
                    task.completed_at,
                    task.customer_id,
                    task.opportunity_id,
                    task.lead_id,
                    task.assigned_user_id,
                    task.trigger_source,
                    task.rule_name,
                    task.notes,
                    now,
                    now,
                ),
            )
            task.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="task",
            entity_id=task.id,
            change_summary=f"Created task '{task.title}'",
            actor=actor,
            details=build_audit_details(after=task.to_dict()),
        )
        return task

    def get_task(self, task_id: int, actor: AuthContext) -> Optional[Task]:
        if not (
            actor.has_permission(PERM_READ_CRM)
            or actor.has_permission(PERM_READ_OPPORTUNITIES)
            or actor.has_permission(PERM_READ_LEADS)
        ):
            raise PermissionError("Actor lacks permission to view tasks")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?;", (task_id,)).fetchone()
        if not row:
            return None
        return self._row_to_task(row)

    def list_tasks(
        self,
        actor: AuthContext,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
        opportunity_id: Optional[int] = None,
        lead_id: Optional[int] = None,
        assigned_user_id: Optional[int] = None,
    ) -> List[Task]:
        if not (
            actor.has_permission(PERM_READ_CRM)
            or actor.has_permission(PERM_READ_OPPORTUNITIES)
            or actor.has_permission(PERM_READ_LEADS)
        ):
            raise PermissionError("Actor lacks permission to view tasks")

        query = "SELECT * FROM tasks WHERE 1=1"
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if customer_id is not None:
            query += " AND customer_id = ?"
            params.append(customer_id)
        if opportunity_id is not None:
            query += " AND opportunity_id = ?"
            params.append(opportunity_id)
        if lead_id is not None:
            query += " AND lead_id = ?"
            params.append(lead_id)
        if assigned_user_id is not None:
            query += " AND assigned_user_id = ?"
            params.append(assigned_user_id)
        query += " ORDER BY id DESC;"

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_task(r) for r in rows]

    def update_task(self, task_id: int, updates: Dict[str, Any], actor: AuthContext) -> Optional[Task]:
        if not (
            actor.has_permission(PERM_WRITE_CRM)
            or actor.has_permission(PERM_WRITE_OPPORTUNITIES)
            or actor.has_permission(PERM_WRITE_LEADS)
        ):
            raise PermissionError("Actor lacks permission to update tasks")

        task = self.get_task(task_id, actor)
        if not task:
            return None

        _before = task.to_dict()

        allowed_fields = {
            "title", "description", "task_type", "status", "priority",
            "due_date", "completed_at", "customer_id", "opportunity_id",
            "lead_id", "assigned_user_id", "trigger_source", "rule_name", "notes"
        }
        for k, v in updates.items():
            if k in allowed_fields:
                setattr(task, k, v)

        now = utc_now_iso()
        task.updated_at = now

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                UPDATE tasks SET
                    title = ?, description = ?, task_type = ?, status = ?,
                    priority = ?, due_date = ?, completed_at = ?, customer_id = ?,
                    opportunity_id = ?, lead_id = ?, assigned_user_id = ?,
                    trigger_source = ?, rule_name = ?, notes = ?, updated_at = ?
                WHERE id = ?;
                """,
                (
                    task.title, task.description, task.task_type, task.status,
                    task.priority, task.due_date, task.completed_at, task.customer_id,
                    task.opportunity_id, task.lead_id, task.assigned_user_id,
                    task.trigger_source, task.rule_name, task.notes, now, task_id,
                ),
            )

        _after = self.get_task(task_id, actor)
        self.audit.log(
            action="update",
            entity_type="task",
            entity_id=task_id,
            change_summary=f"Updated task {task_id}",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_after.to_dict() if _after else None,
            ),
        )
        return task

    def complete_task(self, task_id: int, actor: AuthContext, notes: Optional[str] = None) -> Task:
        if not (
            actor.has_permission(PERM_WRITE_CRM)
            or actor.has_permission(PERM_WRITE_OPPORTUNITIES)
            or actor.has_permission(PERM_WRITE_LEADS)
        ):
            raise PermissionError("Actor lacks permission to complete tasks")

        task = self.get_task(task_id, actor)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        _before = task.to_dict()

        now = utc_now_iso()
        task.status = "completed"
        task.completed_at = now
        task.updated_at = now
        if notes:
            task.notes = f"{task.notes}\n{notes}".strip() if task.notes else str(notes).strip()

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                "UPDATE tasks SET status = 'completed', completed_at = ?, notes = ?, updated_at = ? WHERE id = ?;",
                (now, task.notes, now, task_id),
            )

        _after = self.get_task(task_id, actor)
        self.audit.log(
            action="complete",
            entity_type="task",
            entity_id=task_id,
            change_summary=f"Completed task '{task.title}'",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_after.to_dict() if _after else None,
                side_effects=({"notes_appended": notes} if notes else None),
            ),
        )
        return task

    def generate_cadence_tasks(
        self, opportunity_or_id: int | Opportunity, actor: AuthContext
    ) -> List[Task]:
        """
        Generate automated follow-up cadence tasks triggered by opportunity stage progression.
        """
        if isinstance(opportunity_or_id, int):
            opp = self.get_opportunity(opportunity_or_id, actor)
            if not opp:
                raise ValueError(f"Opportunity {opportunity_or_id} not found")
        else:
            opp = opportunity_or_id

        stage = PipelineStage.normalize(opp.pipeline_stage)
        cadence_templates: Dict[str, Dict[str, Any]] = {
            PipelineStage.NEW_LEAD: {
                "title": "Initial Outreach / Contact Lead",
                "description": f"Perform first contact outreach for opportunity '{opp.title}'.",
                "task_type": "phone_call",
                "priority": "high",
                "rule_name": "cadence_new_lead",
            },
            PipelineStage.CONTACTED: {
                "title": "Schedule Site Inspection / Assessment",
                "description": f"Follow up with customer to schedule property inspection for '{opp.title}'.",
                "task_type": "follow_up",
                "priority": "medium",
                "rule_name": "cadence_contacted",
            },
            PipelineStage.APPOINTMENT_SET: {
                "title": "Prepare Inspection Scope & Measurements",
                "description": f"Gather property details and prepare moisture/damage checklist for '{opp.title}'.",
                "task_type": "inspection",
                "priority": "medium",
                "rule_name": "cadence_appointment_set",
            },
            PipelineStage.ESTIMATE_SCHEDULED: {
                "title": "Conduct Property Inspection & Take Measurements",
                "description": f"Execute on-site inspection and document damage for '{opp.title}'.",
                "task_type": "inspection",
                "priority": "high",
                "rule_name": "cadence_estimate_scheduled",
            },
            PipelineStage.ESTIMATE_SENT: {
                "title": "Follow up on Estimate with Customer & Adjuster",
                "description": f"Verify receipt of estimate and follow up with adjuster for '{opp.title}'.",
                "task_type": "estimate_follow_up",
                "priority": "high",
                "rule_name": "cadence_estimate_sent",
            },
            PipelineStage.PROPOSAL_SENT: {
                "title": "Proposal Review & Contract Closing Follow-up",
                "description": f"Follow up on sent proposal and review contract terms for '{opp.title}'.",
                "task_type": "follow_up",
                "priority": "high",
                "rule_name": "cadence_proposal_sent",
            },
            PipelineStage.NEGOTIATION: {
                "title": "Address Scope Adjustments & Finalize Contract Terms",
                "description": f"Resolve pending questions, adjust line items if needed, and secure signature for '{opp.title}'.",
                "task_type": "negotiation",
                "priority": "urgent",
                "rule_name": "cadence_negotiation",
            },
            PipelineStage.WON: {
                "title": "Hand-off to Production / Schedule Job Kickoff",
                "description": f"Transition won deal '{opp.title}' to project management and schedule kickoff.",
                "task_type": "production_handoff",
                "priority": "high",
                "rule_name": "cadence_won",
            },
            PipelineStage.LOST: {
                "title": "Log Lost Reason & Archive Opportunity",
                "description": f"Document lost analysis: '{opp.lost_reason or 'No reason specified'}' for '{opp.title}'.",
                "task_type": "lost_review",
                "priority": "low",
                "rule_name": "cadence_lost",
            },
        }

        tpl = cadence_templates.get(stage)
        if not tpl:
            return []

        # Check for existing pending task with the same rule_name for this opportunity
        conn = self.db.get_connection()
        existing = conn.execute(
            """
            SELECT id FROM tasks
            WHERE opportunity_id = ? AND rule_name = ? AND status IN ('pending', 'in_progress');
            """,
            (opp.id, tpl["rule_name"]),
        ).fetchone()

        if existing:
            return []

        new_task = Task(
            title=tpl["title"],
            description=tpl["description"],
            task_type=tpl["task_type"],
            status="pending",
            priority=tpl["priority"],
            customer_id=opp.customer_id,
            opportunity_id=opp.id,
            assigned_user_id=opp.assigned_user_id,
            trigger_source="pipeline_stage_transition",
            rule_name=tpl["rule_name"],
        )
        created = self.create_task(new_task, actor)
        return [created]

    # ==========================================
    # PROJECTS / JOBS
    # ==========================================

    @staticmethod
    def _row_to_project(row: Any, actor_role: str = "") -> Project:
        keys = row.keys() if hasattr(row, "keys") else []
        assigned_employees = json.loads(row["assigned_employees_json"]) if "assigned_employees_json" in keys and row["assigned_employees_json"] else []
        subcontractors = json.loads(row["subcontractors_json"]) if "subcontractors_json" in keys and row["subcontractors_json"] else []
        is_customer = actor_role == ROLE_CUSTOMER

        return Project(
            id=row["id"],
            customer_id=row["customer_id"],
            title=row["title"],
            property_address=row["property_address"],
            project_type=row["project_type"],
            status=row["status"],
            stage=ProjectStage.normalize(row["stage"]) if "stage" in keys and row["stage"] else ProjectStage.INTAKE,
            start_date=row["start_date"] if "start_date" in keys else None,
            expected_completion=row["expected_completion"] if "expected_completion" in keys else None,
            actual_completion=row["actual_completion"] if "actual_completion" in keys else None,
            project_manager_id=row["project_manager_id"] if "project_manager_id" in keys else None,
            assigned_employees=assigned_employees,
            subcontractors=subcontractors if not is_customer else [],
            scope_of_work=row["scope_of_work"] if "scope_of_work" in keys else None,
            estimated_cost=row["estimated_cost"] if "estimated_cost" in keys and not is_customer else 0.0,
            contract_amount=row["contract_amount"] if "contract_amount" in keys else 0.0,
            actual_cost=row["actual_cost"] if "actual_cost" in keys and not is_customer else 0.0,
            profit=row["profit"] if "profit" in keys and not is_customer else 0.0,
            notes=row["notes"] if "notes" in keys and not is_customer else None,
            warranty_info=row["warranty_info"] if "warranty_info" in keys else None,
            stage_entered_at=row["stage_entered_at"] if "stage_entered_at" in keys else None,
            insurance_claim_number=row["insurance_claim_number"] if "insurance_claim_number" in keys else None,
            insurance_carrier=row["insurance_carrier"] if "insurance_carrier" in keys else None,
            adjuster_name=row["adjuster_name"] if "adjuster_name" in keys else None,
            adjuster_phone=row["adjuster_phone"] if "adjuster_phone" in keys else None,
            adjuster_email=row["adjuster_email"] if "adjuster_email" in keys else None,
            deductible=row["deductible"] if "deductible" in keys else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_project(self, project: Project, actor: AuthContext) -> Project:
        """Create a project. Does NO referential validation of
        ``project_manager_id`` / ``assigned_employees`` / ``subcontractors``
        beyond the DB foreign key on ``project_manager_id`` -- element ids in
        the two JSON lists are not checked against any table. ``update_project``
        matches this intentionally."""
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
                    stage, start_date, expected_completion, actual_completion,
                    project_manager_id, assigned_employees_json, subcontractors_json,
                    scope_of_work, estimated_cost, contract_amount, actual_cost,
                    profit, notes, warranty_info, stage_entered_at,
                    insurance_claim_number, insurance_carrier, adjuster_name,
                    adjuster_phone, adjuster_email, deductible, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    project.customer_id,
                    project.title.strip(),
                    project.property_address.strip(),
                    project.project_type,
                    project.status,
                    ProjectStage.normalize(project.stage),
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
                    project.stage_entered_at or now,
                    project.insurance_claim_number,
                    project.insurance_carrier,
                    project.adjuster_name,
                    project.adjuster_phone,
                    project.adjuster_email,
                    project.deductible,
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
            details=build_audit_details(after=project.to_dict()),
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

        # Technician assigned check
        if actor.role == ROLE_TECHNICIAN and actor.user_id not in assigned_employees:
            raise PermissionError("Technician can only view assigned projects")

        return self._row_to_project(row, actor.role)

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

            results.append(self._row_to_project(r, actor.role))
        return results

    ALLOWED_PROJECT_UPDATE_FIELDS = {
        "title", "property_address", "project_type",
        "start_date", "expected_completion", "actual_completion",
        "project_manager_id", "assigned_employees", "subcontractors",
        "scope_of_work", "estimated_cost", "contract_amount", "actual_cost",
        "profit", "notes", "warranty_info",
        "insurance_claim_number", "insurance_carrier", "adjuster_name",
        "adjuster_phone", "adjuster_email", "deductible",
    }

    # The three fields whose modification is a "staff reassignment" and needs
    # the reassignment permission rather than plain PERM_WRITE_PROJECTS.
    _PROJECT_REASSIGNMENT_FIELDS = {"project_manager_id", "assigned_employees", "subcontractors"}

    def update_project(
        self, project_id: int, updates: Dict[str, Any], actor: AuthContext
    ) -> Optional[Project]:
        """Partial update for a project, allow-list enforced (see
        ``ALLOWED_PROJECT_UPDATE_FIELDS``). The three assignment fields
        (``project_manager_id``, ``assigned_employees``, ``subcontractors``)
        additionally require the reassignment permission -- unrestricted for
        admin/manager, scoped-to-owned for ``project_manager`` (only projects
        where they are the pre-update ``project_manager_id``); every other
        field needs only ``PERM_WRITE_PROJECTS``. The reassignment check runs
        against the pre-update row, so a PM may hand a project off to someone
        else but may not grab one they do not manage. ``stage``/``status`` are
        rejected with a pointer to the stage-transition endpoint;
        ``customer_id`` is simply not in the allow-list. ``project_manager_id``
        cannot be nulled (None-value guard) -- omit the key instead. Like
        ``create_project`` this does NO referential validation beyond the DB
        foreign key on ``project_manager_id``; element ids in the two JSON
        lists are not checked. Read-then-write is not atomic, matching the
        rest of this service layer. When every submitted value already equals
        the stored value, ``updated_at`` still bumps but no audit row is
        written."""
        if not actor.has_permission(PERM_WRITE_PROJECTS):
            raise PermissionError("Actor lacks permission to update projects")

        _transition_only = {"stage", "status"} & set(updates)
        if _transition_only:
            raise ValueError(
                f"Field(s) {sorted(_transition_only)} cannot be changed via update_project; "
                "use the project stage-transition endpoint"
            )

        unknown = set(updates) - self.ALLOWED_PROJECT_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unknown field(s) for project update: {sorted(unknown)}")

        for key, value in updates.items():
            if value is None:
                raise ValueError(
                    f"Field '{key}' cannot be set to None via update_project; omit the key instead"
                )

        if not updates:
            return self.get_project(project_id, actor)

        for key in ("assigned_employees", "subcontractors"):
            if key in updates and not isinstance(updates[key], list):
                # Must be a JSON array. A dict here would be silently json.dumps'd
                # and later json.loads'd back into a dict, corrupting the
                # `actor.user_id not in assigned` technician-visibility filter
                # in list_projects()/get_project() (a dict membership test hits
                # keys, not values).
                raise ValueError(f"Field '{key}' must be a list")

        conn = self.db.get_connection()
        # RAW row read -- never self.get_project(), which zeroes financial
        # fields for the customer role and raises for an unassigned technician.
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?;", (project_id,)
        ).fetchone()
        if row is None:
            return None

        _before = self._row_to_project(row, actor.role).to_dict()

        if self._PROJECT_REASSIGNMENT_FIELDS & set(updates):
            if not _actor_may_reassign_project_staff(actor, row):
                raise PermissionError("Actor may not reassign staff on this project")

        set_clauses: List[str] = []
        params: List[Any] = []
        for key, value in updates.items():
            if key == "assigned_employees":
                set_clauses.append("assigned_employees_json = ?")
                params.append(json.dumps(value))
            elif key == "subcontractors":
                set_clauses.append("subcontractors_json = ?")
                params.append(json.dumps(value))
            else:
                set_clauses.append(f"{key} = ?")
                params.append(value)
        set_clauses.append("updated_at = ?")
        params.append(utc_now_iso())
        params.append(project_id)

        try:
            with conn:
                # NEW-307: the pre-UPDATE `_actor_may_reassign_project_staff`
                # check above reads a row fetched before this SELECT/UPDATE
                # sequence started, so a concurrent reassignment between
                # that read and this UPDATE could let a PM slip past the
                # ownership check (TOCTOU). Re-check inside the `with conn:`
                # block, immediately before the UPDATE, against a re-fetch
                # of the row. The earlier check stays as a legitimate
                # fail-fast; this recheck is the actual fix and narrows,
                # rather than eliminates, the race per the logged NEW-311
                # decision (no BEGIN IMMEDIATE change).
                if self._PROJECT_REASSIGNMENT_FIELDS & set(updates):
                    _tx_row = conn.execute(
                        "SELECT project_manager_id FROM projects WHERE id = ?;",
                        (project_id,),
                    ).fetchone()
                    if _tx_row is None:
                        # Row was deleted concurrently -- match this
                        # method's existing missing-row contract (line
                        # ~1799-1800 above returns None for the same case).
                        return None
                    if not _actor_may_reassign_project_staff(actor, _tx_row):
                        raise PermissionError("Actor may not reassign staff on this project")
                conn.execute(
                    f"UPDATE projects SET {', '.join(set_clauses)} WHERE id = ?;",
                    params,
                )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Update violates a data constraint: {e}") from e

        # NEW-312: build the audit after-image from a raw row read + the same
        # _row_to_project builder used for _before, and emit audit.log BEFORE
        # the final get_project() -- get_project raises for a
        # read-restricted actor (technician not on the project, customer on
        # another's project), and the audit trail must not depend on that
        # read-permission raise firing after the UPDATE has already committed.
        _after_row = conn.execute(
            "SELECT * FROM projects WHERE id = ?;", (project_id,)
        ).fetchone()
        _after = self._row_to_project(_after_row, actor.role).to_dict() if _after_row else None
        _details = build_audit_details(
            before=_before,
            after=_after,
            fields=_AUDITABLE_PROJECT_FIELDS,
        )
        _changed = _details.get("changed_fields", {})
        # updated_at bumps on every call, so it can't participate in the
        # "did anything change" decision -- see this method's docstring.
        _meaningful = sorted(set(_changed) - {"updated_at"})
        if _meaningful:
            self.audit.log(
                action="update",
                entity_type="project",
                entity_id=project_id,
                change_summary=f"Project {project_id} updated ({', '.join(_meaningful)})",
                actor=actor,
                details=_details,
            )

            if "project_manager_id" in _meaningful and _after and _after.get("project_manager_id"):
                new_pm_id = _after["project_manager_id"]
                pm_row = conn.execute(
                    "SELECT email, full_name FROM users WHERE id = ?;", 
                    (new_pm_id,)
                ).fetchone()
                
                if pm_row and pm_row["email"] and self.notification_service:
                    try:
                        self.notification_service.send_email(
                            to_email=pm_row["email"],
                            subject=f"Project Assignment: Project {project_id}",
                            body=f"Hi {pm_row['full_name'] or 'Staff'},\n\nYou have been assigned as the Project Manager for Project {project_id}."
                        )
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning(f"Failed to send assignment notification: {e}")

        return self.get_project(project_id, actor)

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
            details=build_audit_details(after=estimate.to_dict()),
        )
        return estimate

    @staticmethod
    def _row_to_estimate(row: Any, actor_role: str = "") -> Estimate:
        keys = row.keys() if hasattr(row, "keys") else []
        line_items = json.loads(row["line_items_json"]) if "line_items_json" in keys and row["line_items_json"] else []
        is_customer = actor_role in (ROLE_CUSTOMER, ROLE_TECHNICIAN)

        return Estimate(
            id=row["id"],
            estimate_number=row["estimate_number"],
            customer_id=row["customer_id"],
            project_id=row["project_id"] if "project_id" in keys else None,
            line_items=line_items,
            subtotal=row["subtotal"] if "subtotal" in keys else 0.0,
            materials_cost=row["materials_cost"] if "materials_cost" in keys and not is_customer else 0.0,
            labor_cost=row["labor_cost"] if "labor_cost" in keys and not is_customer else 0.0,
            subcontractor_cost=row["subcontractor_cost"] if "subcontractor_cost" in keys and not is_customer else 0.0,
            markup_percent=row["markup_percent"] if "markup_percent" in keys and not is_customer else 0.0,
            tax_amount=row["tax_amount"] if "tax_amount" in keys else 0.0,
            discount_amount=row["discount_amount"] if "discount_amount" in keys else 0.0,
            total_amount=row["total_amount"] if "total_amount" in keys else 0.0,
            status=row["status"] if "status" in keys else "draft",
            expiration_date=row["expiration_date"] if "expiration_date" in keys else None,
            version=row["version"] if "version" in keys else 1,
            notes=row["notes"] if "notes" in keys and not is_customer else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_estimate(self, estimate_id: int, actor: AuthContext) -> Optional[Estimate]:
        if not (actor.has_permission(PERM_READ_ESTIMATES) or actor.has_permission(PERM_READ_OWN_ESTIMATES)):
            raise PermissionError("Actor lacks permission to read estimates")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        if not row:
            return None

        if actor.role == ROLE_CUSTOMER and (not actor.customer_id or actor.customer_id != row["customer_id"]):
            raise PermissionError("Customer cannot access another customer's estimate")

        return self._row_to_estimate(row, actor.role)

    def list_estimates(
        self,
        actor: AuthContext,
        customer_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> List[Estimate]:
        if not (actor.has_permission(PERM_READ_ESTIMATES) or actor.has_permission(PERM_READ_OWN_ESTIMATES)):
            raise PermissionError("Actor lacks permission to read estimates")

        if actor.role == ROLE_CUSTOMER:
            customer_id = actor.customer_id

        conn = self.db.get_connection()
        query = "SELECT * FROM estimates WHERE 1=1"
        params: List[Any] = []

        if customer_id is not None:
            query += " AND customer_id = ?"
            params.append(customer_id)
        if project_id is not None:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY id DESC;"
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_estimate(r, actor.role) for r in rows]

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
            details=build_audit_details(after=contract.to_dict(), fields=_AUDITABLE_CONTRACT_FIELDS),
        )
        return contract

    @staticmethod
    def _row_to_contract(row: Any) -> Contract:
        keys = row.keys() if hasattr(row, "keys") else []
        return Contract(
            id=row["id"],
            contract_number=row["contract_number"],
            customer_id=row["customer_id"],
            project_id=row["project_id"] if "project_id" in keys else None,
            estimate_id=row["estimate_id"] if "estimate_id" in keys else None,
            title=row["title"],
            template_name=row["template_name"] if "template_name" in keys else None,
            content=row["content"] if "content" in keys else "",
            status=row["status"] if "status" in keys else "draft",
            customer_signed_at=row["customer_signed_at"] if "customer_signed_at" in keys else None,
            customer_signature_data=row["customer_signature_data"] if "customer_signature_data" in keys else None,
            version=row["version"] if "version" in keys else 1,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_contract(self, contract_id: int, actor: AuthContext) -> Optional[Contract]:
        if not (actor.has_permission(PERM_READ_CONTRACTS) or actor.has_permission(PERM_READ_OWN_CONTRACTS)):
            raise PermissionError("Actor lacks permission to read contracts")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM contracts WHERE id = ?;", (contract_id,)).fetchone()
        if not row:
            return None

        if actor.role == ROLE_CUSTOMER and (not actor.customer_id or actor.customer_id != row["customer_id"]):
            raise PermissionError("Customer cannot access another customer's contract")

        return self._row_to_contract(row)

    def list_contracts(
        self,
        actor: AuthContext,
        customer_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> List[Contract]:
        if not (actor.has_permission(PERM_READ_CONTRACTS) or actor.has_permission(PERM_READ_OWN_CONTRACTS)):
            raise PermissionError("Actor lacks permission to read contracts")

        if actor.role == ROLE_CUSTOMER:
            customer_id = actor.customer_id

        conn = self.db.get_connection()
        query = "SELECT * FROM contracts WHERE 1=1"
        params: List[Any] = []

        if customer_id is not None:
            query += " AND customer_id = ?"
            params.append(customer_id)
        if project_id is not None:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY id DESC;"
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_contract(r) for r in rows]

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

        _before = self._row_to_contract(row).to_dict()

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

        _signed = Contract(
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

        self.audit.log(
            action="sign",
            entity_type="contract",
            entity_id=contract_id,
            change_summary=f"Signed contract #{row['contract_number']}",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_signed.to_dict(),
                fields=_AUDITABLE_CONTRACT_FIELDS,
                # Never surface the signature blob in the audit payload.
                side_effects={"signature_captured": True},
            ),
        )

        return _signed

    # ==========================================
    # INVOICES & PAYMENTS
    # ==========================================

    @staticmethod
    def _row_to_invoice(row: Any) -> Invoice:
        keys = row.keys() if hasattr(row, "keys") else []
        payments = json.loads(row["payments_json"]) if "payments_json" in keys and row["payments_json"] else []
        return Invoice(
            id=row["id"],
            invoice_number=row["invoice_number"],
            customer_id=row["customer_id"],
            project_id=row["project_id"] if "project_id" in keys else None,
            status=row["status"] if "status" in keys else "draft",
            amount=row["amount"] if "amount" in keys else 0.0,
            deposit_amount=row["deposit_amount"] if "deposit_amount" in keys else 0.0,
            balance_due=row["balance_due"] if "balance_due" in keys else 0.0,
            due_date=row["due_date"] if "due_date" in keys else None,
            payments=payments,
            notes=row["notes"] if "notes" in keys else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_invoice(self, invoice_id: int, actor: AuthContext) -> Optional[Invoice]:
        if not (actor.has_permission(PERM_READ_FINANCIALS) or actor.has_permission(PERM_READ_OWN_FINANCIALS)):
            raise PermissionError("Actor lacks permission to read invoices")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM invoices WHERE id = ?;", (invoice_id,)).fetchone()
        if not row:
            return None

        if actor.role == ROLE_CUSTOMER and (not actor.customer_id or actor.customer_id != row["customer_id"]):
            raise PermissionError("Customer cannot access another customer's invoice")

        return self._row_to_invoice(row)

    def list_invoices(
        self,
        actor: AuthContext,
        customer_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> List[Invoice]:
        if not (actor.has_permission(PERM_READ_FINANCIALS) or actor.has_permission(PERM_READ_OWN_FINANCIALS)):
            raise PermissionError("Actor lacks permission to read invoices")

        if actor.role == ROLE_CUSTOMER:
            customer_id = actor.customer_id

        conn = self.db.get_connection()
        query = "SELECT * FROM invoices WHERE 1=1"
        params: List[Any] = []

        if customer_id is not None:
            query += " AND customer_id = ?"
            params.append(customer_id)
        if project_id is not None:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY id DESC;"
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_invoice(r) for r in rows]

    def create_invoice(self, invoice: Invoice, actor: AuthContext) -> Invoice:
        if not actor.has_permission(PERM_WRITE_FINANCIALS):
            raise PermissionError("Actor lacks permission to create invoices")

        now = utc_now_iso()
        if not invoice.invoice_number:
            invoice.invoice_number = f"INV-{now[:10].replace('-', '')}-{secrets.token_hex(2).upper()}"
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
            details=build_audit_details(after=invoice.to_dict(), fields=_AUDITABLE_INVOICE_FIELDS),
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

        _before = self._row_to_invoice(row).to_dict()

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

        _updated = Invoice(
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

        self.audit.log(
            action="pay",
            entity_type="invoice",
            entity_id=invoice_id,
            change_summary=f"Recorded payment ${payment_amount:.2f} on invoice #{row['invoice_number']} via {payment_method}",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_updated.to_dict(),
                fields=_AUDITABLE_INVOICE_FIELDS,
                side_effects={"payment_recorded": {
                    "amount": payment_amount,
                    "method": payment_method,
                    "reference": transaction_reference,
                    "new_balance": new_balance,
                    "new_status": new_status,
                }},
            ),
        )

        return _updated

    # ==========================================
    # DOCUMENTS
    # ==========================================

    @staticmethod
    def _row_to_document(row: Any) -> Document:
        keys = row.keys() if hasattr(row, "keys") else []
        tags = json.loads(row["tags_json"]) if "tags_json" in keys and row["tags_json"] else []
        perms = json.loads(row["permissions_json"]) if "permissions_json" in keys and row["permissions_json"] else []
        return Document(
            id=row["id"],
            customer_id=row["customer_id"] if "customer_id" in keys else None,
            project_id=row["project_id"] if "project_id" in keys else None,
            document_type=row["document_type"],
            title=row["title"],
            file_path=row["file_path"],
            file_size_bytes=row["file_size_bytes"] if "file_size_bytes" in keys else 0,
            mime_type=row["mime_type"] if "mime_type" in keys else "application/octet-stream",
            tags=tags,
            permissions=perms,
            expiration_date=row["expiration_date"] if "expiration_date" in keys else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_document(self, document_id: int, actor: AuthContext) -> Optional[Document]:
        if not (actor.has_permission(PERM_READ_DOCUMENTS) or actor.has_permission(PERM_READ_OWN_DOCUMENTS)):
            raise PermissionError("Actor lacks permission to read documents")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM documents WHERE id = ?;", (document_id,)).fetchone()
        if not row:
            return None

        if actor.role == ROLE_CUSTOMER and (not actor.customer_id or actor.customer_id != row["customer_id"]):
            raise PermissionError("Customer cannot access another customer's document")

        return self._row_to_document(row)

    def list_documents(
        self,
        actor: AuthContext,
        customer_id: Optional[int] = None,
        project_id: Optional[int] = None,
        document_type: Optional[str] = None,
    ) -> List[Document]:
        if not (actor.has_permission(PERM_READ_DOCUMENTS) or actor.has_permission(PERM_READ_OWN_DOCUMENTS)):
            raise PermissionError("Actor lacks permission to read documents")

        if actor.role == ROLE_CUSTOMER:
            customer_id = actor.customer_id

        conn = self.db.get_connection()
        query = "SELECT * FROM documents WHERE 1=1"
        params: List[Any] = []

        if customer_id is not None:
            query += " AND customer_id = ?"
            params.append(customer_id)
        if project_id is not None:
            query += " AND project_id = ?"
            params.append(project_id)
        if document_type:
            query += " AND document_type = ?"
            params.append(document_type)

        query += " ORDER BY id DESC;"
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_document(r) for r in rows]

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
            details=build_audit_details(after=doc.to_dict()),
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
            details=build_audit_details(after=sub.to_dict(), fields=_AUDITABLE_SUBCONTRACTOR_FIELDS),
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

    # ------------------------------------------------------------------
    # CORE_TO_JS_SUBCONTRACTOR_MAP — resolves NEW-245.
    # Maps Core Subcontractor field names to the JS-side field names used
    # by subcontractor-recruiter.js functions (formatSubcontractorSummary,
    # formatFollowupList, createOrUpdateSubcontractorLead, syncWithContacts).
    #
    # IMPORTANT: Must stay in sync with mapCoreToJS() in
    # subcontractor-recruiter.js (lines 62-76).  The JS function maps:
    #   external_id → subcontractor_id   (not id)
    #   last_contact_at → last_contact
    #   bool-coerced: w9_received, msa_signed, coi_received, msa_sent,
    #                 workers_comp, license_required, general_liability
    # The `id` field is kept as-is by JS (jsObj.id = coreObj.id).
    # ------------------------------------------------------------------
    CORE_TO_JS_SUBCONTRACTOR_MAP: Dict[str, str] = {
        "external_id": "subcontractor_id",   # JS: jsObj.subcontractor_id = coreObj.external_id
        "last_contact_at": "last_contact",   # JS: jsObj.last_contact = coreObj.last_contact_at
        "next_followup_at": "next_followup",
        "contact_attempts": "contact_count",
        "dnc_status": "do_not_contact",
        "residential_experience": "residential",
        "commercial_experience": "commercial",
        "emergency_availability": "emergency_available",
        # The following are bool-coerced but keep the same key name in JS:
        "w9_received": "w9_received",
        "msa_signed": "msa_signed",
        "coi_received": "coi_received",
        "msa_sent": "msa_sent",
        "workers_comp": "workers_comp",
        "license_required": "license_required",
        "general_liability": "general_liability",
    }

    # Fields stored as integers in SQLite that must be converted to bool
    # before handing off to JS callers.  Must match the `boolFields` array
    # in subcontractor-recruiter.js mapCoreToJS (lines 69-74).
    _BOOL_FIELDS: frozenset = frozenset({
        "w9_received", "msa_signed", "coi_received", "msa_sent",
        "workers_comp", "license_required", "general_liability",
        # Additional bool fields not in JS mapCoreToJS but used by JS formatters:
        "residential_experience", "commercial_experience", "emergency_availability",
    })

    @classmethod
    def format_subcontractor_for_js(cls, sub: "Subcontractor") -> Dict:
        """Convert a Core Subcontractor object to a JS-compatible dict.

        Resolves NEW-245: renames Core field names to the JS-side names
        expected by subcontractor-recruiter.js (formatSubcontractorSummary,
        formatFollowupList, createOrUpdateSubcontractorLead, etc.) and
        coerces integer-boolean SQLite columns to Python bools.  Fields
        not present in CORE_TO_JS_SUBCONTRACTOR_MAP are passed through
        unchanged.  Callers should never assume Core field names after
        this function — use the returned dict keys only.
        """
        raw = sub.to_dict()
        out: Dict = {}
        for core_key, value in raw.items():
            # Coerce int booleans before renaming
            if core_key in cls._BOOL_FIELDS and isinstance(value, int):
                value = bool(value)
            js_key = cls.CORE_TO_JS_SUBCONTRACTOR_MAP.get(core_key, core_key)
            out[js_key] = value
        return out

    def upsert_subcontractor(
        self, sub: "Subcontractor", actor: AuthContext
    ) -> "Subcontractor":
        """Create-or-update a subcontractor row keyed on external_id.

        Resolves NEW-242: subcontractor-recruiter.js's
        createOrUpdateSubcontractorLead() performs a lookup then either
        merges or inserts, but the Core layer previously exposed only pure
        create_subcontractor and update_subcontractor primitives with no
        dedup/upsert logic.  This method bridges that gap using a
        two-step find-then-create/update pattern so there is no raw SQL
        duplication and both paths go through the same audit trail.

        Requires PERM_WRITE_SUBCONTRACTORS.  If external_id is None or
        empty a ValueError is raised — callers must supply a stable
        external_id so the lookup is deterministic.

        Returns the final Subcontractor row (newly created or updated).
        """
        if not actor.has_permission(PERM_WRITE_SUBCONTRACTORS):
            raise PermissionError("Actor lacks permission to upsert subcontractors")

        if not sub.external_id or not sub.external_id.strip():
            raise ValueError("upsert_subcontractor requires a non-empty external_id")

        existing = self.get_subcontractor_by_external_id(sub.external_id, actor)
        if existing is None:
            # INSERT path — delegate entirely to create_subcontractor so
            # audit, timestamps, and permission checks are consistent.
            return self.create_subcontractor(sub, actor)

        # UPDATE path — build an updates dict from all non-None fields on
        # the incoming sub, excluding immutable columns (external_id,
        # created_at, id) AND restricting to ALLOWED_UPDATE_FIELDS so we
        # don't accidentally push qualification_status, dnc_status, or
        # other fields that must go through dedicated update methods.
        immutable = {"external_id", "created_at", "id"}
        raw = sub.to_dict()
        updates = {
            k: v
            for k, v in raw.items()
            if k not in immutable and v is not None
            and k in self.ALLOWED_UPDATE_FIELDS
        }
        if not updates:
            # Nothing allowed to change; return the existing row.
            return existing

        return self.update_subcontractor(existing.id, updates, actor)

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

            updated_row = conn.execute(
                "SELECT * FROM subcontractors WHERE id = ?;", (subcontractor_id,)
            ).fetchone()

        self.audit.log(
            action="status_change",
            entity_type="subcontractor",
            entity_id=subcontractor_id,
            change_summary=f"Subcontractor {subcontractor_id} qualification set to '{qualification_status}'",
            actor=actor,
            details=build_audit_details(snapshot={
                # NEW-311: no pre-image read in this method; NEW-315: snapshot
                # can't be filtered. This method mutates only these two columns,
                # so a scoped snapshot is a complete change record -- not a
                # manufactured diff.
                "qualification_status": qualification_status,
                "recruitment_step": recruitment_step,
            }),
        )
        # NEW-240: build the return from the write-scoped row rather than
        # the READ-gated get_subcontractor() -- this method is authorized
        # on PERM_WRITE_SUBCONTRACTORS, not PERM_READ_SUBCONTRACTORS.
        return self._row_to_subcontractor(updated_row) if updated_row else None

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
                "SELECT * FROM subcontractors WHERE id = ?;",
                (subcontractor_id,),
            ).fetchone()
            if not row:
                return None

            _before = self._row_to_subcontractor(row).to_dict()

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

            updated_row = conn.execute(
                "SELECT * FROM subcontractors WHERE id = ?;",
                (subcontractor_id,),
            ).fetchone()
            # NEW-240: build the return from the write-scoped row rather
            # than the READ-gated get_subcontractor() -- this method is
            # authorized on PERM_WRITE_SUBCONTRACTORS, not
            # PERM_READ_SUBCONTRACTORS.
            updated_sub = self._row_to_subcontractor(updated_row) if updated_row else None

        self.audit.log(
            action="update",
            entity_type="subcontractor",
            entity_id=subcontractor_id,
            change_summary=f"Subcontractor {subcontractor_id} updated ({', '.join(sorted(updates.keys()))})",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=updated_sub.to_dict() if updated_sub else None,
                fields=_AUDITABLE_SUBCONTRACTOR_FIELDS,
            ),
        )
        return updated_sub

    # ==========================================
    # CONTACTS (Aigentik Memory System)
    # ==========================================

    @staticmethod
    def _row_to_contact(row) -> Contact:
        aliases = json.loads(row["aliases_json"]) if row["aliases_json"] else []
        phones = json.loads(row["phones_json"]) if row["phones_json"] else []
        emails = json.loads(row["emails_json"]) if row["emails_json"] else []
        roles = json.loads(row["roles_json"]) if row["roles_json"] else []
        references = json.loads(row["references_json"]) if row["references_json"] else []
        history = json.loads(row["history_json"]) if row["history_json"] else []
        return Contact(
            id=row["id"],
            external_id=row["external_id"],
            name=row["name"],
            aliases=aliases,
            phones=phones,
            emails=emails,
            address=row["address"],
            relationship=row["relationship"],
            type=row["type"],
            notes=row["notes"],
            instructions=row["instructions"],
            reply_behavior=row["reply_behavior"],
            roles=roles,
            active_role=row["active_role"],
            business_name=row["business_name"],
            trade=row["trade"],
            trade_raw=row["trade_raw"],
            licensed=row["licensed"],
            license_number=row["license_number"],
            gl_insurance=row["gl_insurance"],
            wc_insurance=row["wc_insurance"],
            has_tools=row["has_tools"],
            crew_size=row["crew_size"],
            weekly_capacity=row["weekly_capacity"],
            references=references,
            source=row["source"],
            first_seen=row["first_seen"],
            last_contact=row["last_contact"],
            contact_count=row["contact_count"],
            history=history,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_contact(self, contact: Contact, actor: AuthContext) -> Contact:
        if not actor.has_permission(PERM_WRITE_CONTACTS):
            raise PermissionError("Actor lacks permission to create contacts")

        now = utc_now_iso()
        contact.created_at = contact.created_at or now
        contact.updated_at = now
        if not contact.first_seen:
            contact.first_seen = now

        aliases_json = json.dumps(contact.aliases)
        phones_json = json.dumps(contact.phones)
        emails_json = json.dumps(contact.emails)
        roles_json = json.dumps(contact.roles)
        references_json = json.dumps(contact.references)
        history_json = json.dumps(contact.history)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO contacts (
                    external_id, name, aliases_json, phones_json, emails_json,
                    address, relationship, type, notes, instructions,
                    reply_behavior, roles_json, active_role, business_name,
                    trade, trade_raw, licensed, license_number, gl_insurance,
                    wc_insurance, has_tools, crew_size, weekly_capacity,
                    references_json, source, first_seen, last_contact,
                    contact_count, history_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    contact.external_id,
                    contact.name.strip() if contact.name else None,
                    aliases_json,
                    phones_json,
                    emails_json,
                    contact.address,
                    contact.relationship,
                    contact.type,
                    contact.notes,
                    contact.instructions,
                    contact.reply_behavior,
                    roles_json,
                    contact.active_role,
                    contact.business_name,
                    contact.trade,
                    contact.trade_raw,
                    contact.licensed,
                    contact.license_number,
                    contact.gl_insurance,
                    contact.wc_insurance,
                    contact.has_tools,
                    contact.crew_size,
                    contact.weekly_capacity,
                    references_json,
                    contact.source,
                    contact.first_seen,
                    contact.last_contact,
                    contact.contact_count,
                    history_json,
                    contact.created_at,
                    now,
                ),
            )
            contact.id = cursor.lastrowid

            # Auto-assign a string external_id when the caller didn't supply
            # one. The Android-sync path (sync_contacts_batch) already does
            # this as "contact_NNNN"; direct creates (inbound SMS/email leads
            # via POST /api/v1/contacts) previously left external_id NULL,
            # and Core resolves a non-numeric contact id ONLY by exact
            # external_id match -- so GET/POST /api/v1/contacts/{a string id}
            # 404s for those rows and any follow-up update by string id is a
            # silent no-op. Same "contact_NNNN" shape as the sync path.
            # The create response returns this id (routes.py -> to_dict()),
            # which is what the caller should address the contact by
            # afterwards. The loop only avoids a UNIQUE-index IntegrityError
            # if the row-id-derived string is already taken by an
            # out-of-step sync-assigned id; when it fires, a caller that
            # instead derives the id purely from the numeric row id would
            # still miss -- see NEW-262.
            if not contact.external_id or not str(contact.external_id).strip():
                candidate_num = contact.id
                new_external_id = f"contact_{candidate_num:04d}"
                while conn.execute(
                    "SELECT 1 FROM contacts WHERE external_id = ? AND id != ?;",
                    (new_external_id, contact.id),
                ).fetchone():
                    candidate_num += 1
                    new_external_id = f"contact_{candidate_num:04d}"
                conn.execute(
                    "UPDATE contacts SET external_id = ? WHERE id = ?;",
                    (new_external_id, contact.id),
                )
                contact.external_id = new_external_id

        self.audit.log(
            action="create",
            entity_type="contact",
            entity_id=contact.id,
            change_summary=f"Created contact {contact.name or contact.external_id or contact.id}",
            actor=actor,
            details=build_audit_details(after=contact.to_dict()),
        )
        return contact

    def get_contact(self, contact_id: int, actor: AuthContext) -> Optional[Contact]:
        if not actor.has_permission(PERM_READ_CONTACTS):
            raise PermissionError("Actor lacks permission to view contacts")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM contacts WHERE id = ?;", (contact_id,)).fetchone()
        if not row:
            return None
        return self._row_to_contact(row)

    def get_contact_by_external_id(self, external_id: str, actor: AuthContext) -> Optional[Contact]:
        if not actor.has_permission(PERM_READ_CONTACTS):
            raise PermissionError("Actor lacks permission to view contacts")

        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM contacts WHERE external_id = ?;", (external_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_contact(row)

    def find_contact(self, query: str, actor: AuthContext) -> Optional[Contact]:
        """Fuzzy lookup for contacts matching findContact() in JS.
        Checks: external_id exact match -> phones normalized digit substring match (>=7 digits) ->
        emails exact lowercase match -> name exact/substring match -> aliases exact/substring match ->
        relationship exact lowercase match -> business_name substring match -> address substring match.
        Returns first matching contact ordered by id ASC."""
        if not actor.has_permission(PERM_READ_CONTACTS):
            raise PermissionError("Actor lacks permission to search contacts")

        if not query or not query.strip():
            return None

        q = query.strip().lower()
        clean_digits = re.sub(r"\D", "", q)
        norm_phone = clean_digits[-10:] if len(clean_digits) >= 7 else None

        conn = self.db.get_connection()
        rows = conn.execute("SELECT * FROM contacts ORDER BY id ASC;").fetchall()
        for row in rows:
            # 1. external_id exact match
            external_id = row["external_id"]
            if external_id and external_id.lower() == q:
                return self._row_to_contact(row)

            # 2. phones match
            phones = json.loads(row["phones_json"]) if row["phones_json"] else []
            if norm_phone:
                for p in phones:
                    p_digits = re.sub(r"\D", "", str(p))
                    p_norm = p_digits[-10:] if len(p_digits) >= 7 else None
                    if p_norm and (norm_phone == p_norm or norm_phone in p_digits or p_digits in clean_digits):
                        return self._row_to_contact(row)

            # 3. emails match
            emails = json.loads(row["emails_json"]) if row["emails_json"] else []
            if any(e.lower().strip() == q for e in emails if isinstance(e, str)):
                return self._row_to_contact(row)

            # 4. name exact or substring match
            name = (row["name"] or "").lower()
            if name and (name == q or q in name):
                return self._row_to_contact(row)

            # 5. aliases match
            aliases = json.loads(row["aliases_json"]) if row["aliases_json"] else []
            if any((a.lower() == q or q in a.lower()) for a in aliases if isinstance(a, str)):
                return self._row_to_contact(row)

            # 6. relationship match
            rel = (row["relationship"] or "").lower()
            if rel and rel == q:
                return self._row_to_contact(row)

            # 7. business_name substring match
            biz = (row["business_name"] or "").lower()
            if biz and q in biz:
                return self._row_to_contact(row)

            # 8. address substring match
            addr = (row["address"] or "").lower()
            if addr and q in addr:
                return self._row_to_contact(row)

        return None

    def list_contacts(
        self,
        actor: AuthContext,
        type: Optional[str] = None,
        active_role: Optional[str] = None,
        trade: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Contact]:
        if not actor.has_permission(PERM_READ_CONTACTS):
            raise PermissionError("Actor lacks permission to list contacts")

        query = "SELECT * FROM contacts WHERE 1=1"
        params: List[Any] = []

        if type:
            query += " AND type = ?"
            params.append(type)

        if active_role:
            query += " AND active_role = ?"
            params.append(active_role)

        if trade:
            query += " AND (trade = ? OR trade_raw LIKE ?)"
            params.extend([trade, f"%{trade}%"])

        query += " ORDER BY id ASC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_contact(r) for r in rows]

    ALLOWED_CONTACT_UPDATE_FIELDS = {
        "name", "aliases", "phones", "emails", "address", "relationship",
        "type", "notes", "instructions", "reply_behavior", "roles",
        "active_role", "business_name", "trade", "trade_raw", "licensed",
        "license_number", "gl_insurance", "wc_insurance", "has_tools",
        "crew_size", "weekly_capacity", "references", "source", "first_seen",
        "last_contact", "contact_count", "history",
    }

    def update_contact(
        self, contact_id: int, updates: Dict[str, Any], actor: AuthContext
    ) -> Optional[Contact]:
        if not actor.has_permission(PERM_WRITE_CONTACTS):
            raise PermissionError("Actor lacks permission to update contacts")

        unknown = set(updates) - self.ALLOWED_CONTACT_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unknown field(s) for contact update: {sorted(unknown)}")

        for key, value in updates.items():
            if value is None and key not in {
                "name", "address", "relationship", "notes", "instructions",
                "business_name", "trade", "trade_raw", "license_number",
                "weekly_capacity", "licensed", "gl_insurance", "wc_insurance",
                "has_tools", "crew_size", "last_contact"
            }:
                raise ValueError(
                    f"Field '{key}' cannot be set to None via update_contact; omit the key instead"
                )

        if not updates:
            return self.get_contact(contact_id, actor)

        updates = dict(updates)
        if "name" in updates and isinstance(updates["name"], str):
            updates["name"] = updates["name"].strip()

        now = utc_now_iso()
        conn = self.db.get_connection()
        with conn:
            row = conn.execute("SELECT * FROM contacts WHERE id = ?;", (contact_id,)).fetchone()
            if not row:
                return None

            # Audit pre-image: both sides via the same _row_to_contact builder
            # so JSON-column normalization can't produce a phantom diff.
            _before = self._row_to_contact(row).to_dict()

            set_clauses = []
            params: List[Any] = []

            for key, value in updates.items():
                if key in {"aliases", "phones", "emails", "roles", "references", "history"}:
                    set_clauses.append(f"{key}_json = ?")
                    params.append(json.dumps(value if isinstance(value, list) else [value]))
                else:
                    set_clauses.append(f"{key} = ?")
                    params.append(value)

            set_clauses.append("updated_at = ?")
            params.append(now)
            params.append(contact_id)

            cursor = conn.execute(
                f"UPDATE contacts SET {', '.join(set_clauses)} WHERE id = ?;",
                params,
            )
            if cursor.rowcount == 0:
                return None

        _after_row = conn.execute(
            "SELECT * FROM contacts WHERE id = ?;", (contact_id,)
        ).fetchone()
        _after = self._row_to_contact(_after_row).to_dict() if _after_row else None

        self.audit.log(
            action="update",
            entity_type="contact",
            entity_id=contact_id,
            change_summary=f"Contact {contact_id} updated ({', '.join(sorted(updates.keys()))})",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_after,
                fields=_AUDITABLE_CONTACT_FIELDS,
            ),
        )
        return self.get_contact(contact_id, actor)

    def upsert_contact(self, contact: Contact, actor: AuthContext) -> Contact:
        if not actor.has_permission(PERM_WRITE_CONTACTS):
            raise PermissionError("Actor lacks permission to create or update contacts")

        if not contact.external_id or not contact.external_id.strip():
            raise ValueError("upsert_contact requires a non-empty external_id")

        existing = self.get_contact_by_external_id(contact.external_id, actor)
        if existing is None:
            return self.create_contact(contact, actor)

        immutable = {"external_id", "created_at", "id"}
        raw = contact.to_dict()
        updates = {
            k: v
            for k, v in raw.items()
            if k not in immutable and v is not None and k in self.ALLOWED_CONTACT_UPDATE_FIELDS
        }
        if not updates:
            return existing

        updated = self.update_contact(existing.id, updates, actor)
        return updated or existing

    def delete_contact(self, contact_id: int, actor: AuthContext) -> bool:
        if not actor.has_permission(PERM_WRITE_CONTACTS):
            raise PermissionError("Actor lacks permission to delete contacts")

        contact = self.get_contact(contact_id, actor)
        if not contact:
            return False

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute("DELETE FROM contacts WHERE id = ?;", (contact_id,))
            if cursor.rowcount == 0:
                return False

        self.audit.log(
            action="delete",
            entity_type="contact",
            entity_id=contact_id,
            change_summary=f"Deleted contact {contact.name or contact.external_id or contact_id}",
            actor=actor,
            details=build_audit_details(snapshot=contact.to_dict()),
        )
        return True

    def sync_contacts_batch(self, contacts: List[Contact], actor: AuthContext) -> Dict[str, Any]:
        """Batch sync endpoint for external/Android contact lists."""
        if not actor.has_permission(PERM_WRITE_CONTACTS):
            raise PermissionError("Actor lacks permission to sync contacts")

        added = 0
        updated = 0

        conn = self.db.get_connection()
        with conn:
            existing_rows = conn.execute("SELECT * FROM contacts ORDER BY id ASC;").fetchall()
            existing_contacts = [self._row_to_contact(r) for r in existing_rows]

            max_id = 0
            for c in existing_contacts:
                if c.external_id and c.external_id.startswith("contact_"):
                    try:
                        num = int(c.external_id.replace("contact_", ""))
                        if num > max_id:
                            max_id = num
                    except ValueError:
                        pass

            for incoming in contacts:
                matched: Optional[Contact] = None
                if incoming.external_id:
                    matched = next((c for c in existing_contacts if c.external_id == incoming.external_id), None)

                if not matched and incoming.phones:
                    for in_p in incoming.phones:
                        in_digits = re.sub(r"\D", "", str(in_p))[-10:]
                        if not in_digits:
                            continue
                        for ec in existing_contacts:
                            if any(re.sub(r"\D", "", str(p))[-10:] == in_digits for p in ec.phones if re.sub(r"\D", "", str(p))):
                                matched = ec
                                break
                        if matched:
                            break

                if not matched:
                    max_id += 1
                    ext_id = incoming.external_id or f"contact_{str(max_id).zfill(4)}"
                    incoming.external_id = ext_id
                    now = utc_now_iso()
                    incoming.created_at = incoming.created_at or now
                    incoming.updated_at = now
                    if not incoming.first_seen:
                        incoming.first_seen = now

                    cursor = conn.execute(
                        """
                        INSERT INTO contacts (
                            external_id, name, aliases_json, phones_json, emails_json,
                            address, relationship, type, notes, instructions,
                            reply_behavior, roles_json, active_role, business_name,
                            trade, trade_raw, licensed, license_number, gl_insurance,
                            wc_insurance, has_tools, crew_size, weekly_capacity,
                            references_json, source, first_seen, last_contact,
                            contact_count, history_json, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            incoming.external_id,
                            incoming.name.strip() if incoming.name else None,
                            json.dumps(incoming.aliases),
                            json.dumps(incoming.phones),
                            json.dumps(incoming.emails),
                            incoming.address,
                            incoming.relationship,
                            incoming.type,
                            incoming.notes,
                            incoming.instructions,
                            incoming.reply_behavior,
                            json.dumps(incoming.roles),
                            incoming.active_role,
                            incoming.business_name,
                            incoming.trade,
                            incoming.trade_raw,
                            incoming.licensed,
                            incoming.license_number,
                            incoming.gl_insurance,
                            incoming.wc_insurance,
                            incoming.has_tools,
                            incoming.crew_size,
                            incoming.weekly_capacity,
                            json.dumps(incoming.references),
                            incoming.source,
                            incoming.first_seen,
                            incoming.last_contact,
                            incoming.contact_count,
                            json.dumps(incoming.history),
                            incoming.created_at,
                            now,
                        ),
                    )
                    incoming.id = cursor.lastrowid
                    existing_contacts.append(incoming)
                    added += 1
                else:
                    needs_update = False
                    up_name = matched.name
                    if not matched.name and incoming.name:
                        up_name = incoming.name
                        needs_update = True

                    up_aliases = list(matched.aliases)
                    if incoming.name:
                        name_lower = incoming.name.lower()
                        if name_lower not in up_aliases:
                            up_aliases.append(name_lower)
                            needs_update = True

                    up_source = matched.source
                    if matched.source in ("auto", "sms") and incoming.source:
                        up_source = incoming.source
                        needs_update = True

                    if needs_update:
                        now = utc_now_iso()
                        conn.execute(
                            """
                            UPDATE contacts SET name = ?, aliases_json = ?, source = ?, updated_at = ?
                            WHERE id = ?;
                            """,
                            (up_name, json.dumps(up_aliases), up_source, now, matched.id),
                        )
                        matched.name = up_name
                        matched.aliases = up_aliases
                        matched.source = up_source
                        matched.updated_at = now
                        updated += 1

            total_count = conn.execute("SELECT COUNT(*) as cnt FROM contacts;").fetchone()["cnt"]

        self.audit.log(
            action="update",
            entity_type="contact",
            entity_id=None,
            change_summary=f"Synced batch of {len(contacts)} contacts (added: {added}, updated: {updated})",
            actor=actor,
            # Bulk op: entity_id=None, aggregate counts only (no per-row
            # before/after -- the batch touches many rows).
            details=build_audit_details(side_effects={
                "android": len(contacts),
                "added": added,
                "updated": updated,
                "total": total_count,
            }),
        )
        return {"android": len(contacts), "added": added, "updated": updated, "total": total_count}

    # ==========================================
    # PUBLIC INTAKE / WEB FORM SUBMISSIONS
    # ==========================================

    def submit_public_lead(self, data: Dict[str, Any], client_ip: str = "") -> Dict[str, Any]:
        """Process public lead form submission from restoricon.com with spam mitigation,
        deduplication, lead qualification scoring, and opportunity creation."""
        # 1. Honeypot / Bot check
        if data.get("website_hp") or data.get("honeypot") or data.get("bot_check"):
            return {"success": True, "lead_id": 0, "status": "received"}

        # 2. Extract & Sanitize fields
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("Name is required for lead submission")

        phone = str(data.get("phone", "")).strip()
        email = str(data.get("email", "")).strip()
        address = str(data.get("property_address", data.get("address", ""))).strip()
        project_type = str(data.get("project_type", "remodel")).strip()
        description = str(data.get("description", data.get("message", ""))).strip()
        urgency = str(data.get("urgency", "medium")).strip().lower()
        has_insurance = bool(data.get("insurance", data.get("has_insurance", False)))
        insurance_carrier = data.get("insurance_carrier")

        system_actor = AuthContext(
            user_id=1,
            username="system_web_intake",
            role=ROLE_ADMIN,
            actor_type="agent",
        )

        # 3. Customer Deduplication & Upsert
        customer: Optional[Customer] = None
        if email:
            customer = self.get_customer_by_email(email, system_actor)
        if not customer and phone:
            customer = self.find_customer(phone, system_actor)

        parts = name.split(maxsplit=1)
        first_name = parts[0] if parts else ""
        last_name = parts[1] if len(parts) > 1 else ""

        if not customer:
            new_cust = Customer(
                first_name=first_name,
                last_name=last_name,
                email=email if email else None,
                phone=phone if phone else None,
                service_address=address if address else None,
                customer_source="website",
                notes=f"Created via website intake from {client_ip}" if client_ip else "Created via website intake",
            )
            customer = self.create_customer(new_cust, system_actor)
        else:
            # Update customer address if newly supplied
            if address and not customer.service_address:
                self.update_customer(customer.id, {"service_address": address}, system_actor)

        # 4. Create Lead Record
        lead = Lead(
            customer_id=customer.id,
            source="website",
            status="new",
            property_type=project_type,
            project_scope=description,
            urgency_level=urgency,
            insurance_status="insured" if has_insurance else "none",
            notes=f"Carrier: {insurance_carrier}" if insurance_carrier else None,
        )
        created_lead = self.create_lead(lead, system_actor)

        # 5. Score Lead using Deterministic Scoring Engine
        score_res = self.score_lead(created_lead.id, system_actor)

        # 6. Create Opportunity in NEW_LEAD Pipeline Stage
        est_val = float(data.get("estimated_value", 0.0))
        opp = Opportunity(
            customer_id=customer.id,
            title=f"Website Lead: {name} - {project_type.capitalize()}",
            estimated_value=est_val,
            pipeline_stage=PipelineStage.NEW_LEAD,
            probability=STAGE_DEFAULT_PROBABILITIES[PipelineStage.NEW_LEAD],
            notes=description if description else None,
            insurance_carrier=insurance_carrier,
        )
        created_opp = self.create_opportunity(opp, system_actor)

        # 7. Create Follow-up Task for Sales Team
        task_priority = "urgent" if urgency in ("emergency", "urgent") else "high"
        task = Task(
            title=f"Follow up with website lead: {name}",
            description=f"Inquiry for {project_type} ({urgency} priority): {description}",
            task_type="follow_up",
            priority=task_priority,
            customer_id=customer.id,
            opportunity_id=created_opp.id,
            lead_id=created_lead.id,
            trigger_source="website_form",
            rule_name="inbound_web_lead",
        )
        self.create_task(task, system_actor)

        # 8. Record Inbound Communication Entry
        now = utc_now_iso()
        comm = CommunicationRecord(
            timestamp=now,
            channel="web_chat",
            direction="inbound",
            subject=f"Website Lead: {project_type}",
            content=description if description else f"New lead submission from {name} ({phone}, {email})",
            actor_role="customer",
            actor_type="human",
            customer_id=customer.id,
            opportunity_id=created_opp.id,
            metadata={"ip": client_ip, "form": "website_contact", "urgency": urgency},
        )
        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO communication_history (
                    timestamp, channel, direction, subject, content,
                    actor_id, actor_role, actor_type, customer_id,
                    project_id, opportunity_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    comm.timestamp,
                    comm.channel,
                    comm.direction,
                    comm.subject,
                    comm.content,
                    None,
                    comm.actor_role,
                    comm.actor_type,
                    comm.customer_id,
                    comm.project_id,
                    comm.opportunity_id,
                    json.dumps(comm.metadata),
                ),
            )

        self.audit.log(
            action="submit",
            entity_type="lead",
            entity_id=created_lead.id,
            change_summary=f"Inbound website lead from {name} (Score: {score_res.get('score', 0)})",
            actor=system_actor,
            # Compound create: after-image of the lead itself; ids + the
            # (JSON-serializable) score result as cross-entity side effects.
            details=build_audit_details(
                after=created_lead.to_dict(),
                side_effects={
                    "customer_id": customer.id,
                    "opportunity_id": created_opp.id,
                    "score": score_res,
                },
            ),
        )

        return {
            "success": True,
            "lead_id": created_lead.id,
            "customer_id": customer.id,
            "opportunity_id": created_opp.id,
            "score": score_res.get("score"),
            "grade": score_res.get("grade"),
            "status": "received",
        }

    def submit_public_booking(self, data: Dict[str, Any], client_ip: str = "") -> Dict[str, Any]:
        """Process public appointment booking request from restoricon.com."""
        if data.get("website_hp") or data.get("honeypot") or data.get("bot_check"):
            return {"success": True, "appointment_id": 0, "status": "received"}

        name = str(data.get("name", data.get("customer_name", ""))).strip()
        if not name:
            raise ValueError("Name is required for booking request")

        phone = str(data.get("phone", "")).strip()
        email = str(data.get("email", "")).strip()
        address = str(data.get("address", data.get("property_address", ""))).strip()
        service_type = str(data.get("service_type", "estimate")).strip()
        preferred_date = str(data.get("preferred_date", "")).strip()
        preferred_time_slot = str(data.get("preferred_time_slot", "morning")).strip()
        notes = str(data.get("notes", data.get("description", ""))).strip()

        system_actor = AuthContext(
            user_id=1,
            username="system_web_intake",
            role=ROLE_ADMIN,
            actor_type="agent",
        )

        customer: Optional[Customer] = None
        if email:
            customer = self.get_customer_by_email(email, system_actor)
        if not customer and phone:
            customer = self.find_customer(phone, system_actor)

        parts = name.split(maxsplit=1)
        first_name = parts[0] if parts else ""
        last_name = parts[1] if len(parts) > 1 else ""

        if not customer:
            new_cust = Customer(
                first_name=first_name,
                last_name=last_name,
                email=email if email else None,
                phone=phone if phone else None,
                service_address=address if address else None,
                customer_source="website_booking",
            )
            customer = self.create_customer(new_cust, system_actor)

        now = utc_now_iso()
        start_time = f"{preferred_date}T{preferred_time_slot}" if preferred_date else None
        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO appointments (
                    title, start_time, end_time, customer_id,
                    attendee_name, attendee_email, appointment_type, status,
                    offered_slots_json, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    f"Consultation: {name} ({service_type})",
                    start_time,
                    None,
                    customer.id,
                    name,
                    email if email else None,
                    "in_person",
                    "negotiating",
                    json.dumps([{"date": preferred_date, "slot": preferred_time_slot}]) if preferred_date else "[]",
                    f"Service: {service_type}. Notes: {notes}" if notes else f"Service: {service_type}",
                    now,
                    now,
                ),
            )
            appt_id = cursor.lastrowid

        # Follow-up task
        task = Task(
            title=f"Confirm booking request from {name}",
            description=f"Requested {service_type} on {preferred_date} ({preferred_time_slot}): {notes}",
            task_type="follow_up",
            priority="high",
            customer_id=customer.id,
            trigger_source="website_booking",
        )
        self.create_task(task, system_actor)

        self.audit.log(
            action="submit",
            entity_type="appointment",
            entity_id=appt_id,
            change_summary=f"Inbound booking request from {name} for {preferred_date}",
            actor=system_actor,
            # after-image omitted: the method holds no Appointment model and a
            # re-read would be a new SELECT under NEW-311. ids only.
            details=build_audit_details(side_effects={
                "appointment_id": appt_id,
                "customer_id": customer.id,
            }),
        )

        return {
            "success": True,
            "appointment_id": appt_id,
            "customer_id": customer.id,
            "status": "pending_confirmation",
        }

