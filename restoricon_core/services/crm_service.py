"""
CRM and Operations Business Services for Restoricon Core.
Orchestrates domain entities (Customers, Leads, Opportunities, Projects, Estimates,
Contracts, Invoices, Documents) with RBAC enforcement and automatic audit logging.
"""

from __future__ import annotations

import calendar
import json
import os
import re
import secrets
import sqlite3
import time
from collections import namedtuple
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

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
    PERM_READ_TEAM_SALES_DATA,
    PERM_READ_ALL_PROJECTS,
    PERM_READ_OWN_SOLD_PROJECTS,
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
    ROLE_MANAGER,
    ROLE_SALES,
    ROLE_SALES_MANAGER,
    ROLE_PROJECT_MANAGER,
    _actor_may_reassign_project_staff,
)
from ..database import DatabaseManager
from ..models import (
    CommissionLedgerEntry,
    CommunicationRecord,
    Contact,
    Contract,
    ContractSigner,
    Customer,
    Document,
    Estimate,
    HomecareSubscription,
    HOMECARE_TIER_FEE_FIELDS,
    Invoice,
    Lead,
    Opportunity,
    CONTRACT_TEMPLATE_NAMES,
    PackageOption,
    PipelineStage,
    ProductionHandoffChecklist,
    PRODUCTION_HANDOFF_CHECKLIST_ITEMS,
    PRODUCTION_HANDOFF_ITEM_STATUSES,
    Project,
    ProjectStage,
    Property,
    STAGE_DEFAULT_PROBABILITIES,
    Subcontractor,
    Task,
    utc_now_iso,
)
from .audit_service import AuditService, build_audit_details, _AUDITABLE_CONTRACT_FIELDS, _AUDITABLE_INVOICE_FIELDS, _AUDITABLE_SUBCONTRACTOR_FIELDS, _AUDITABLE_PROJECT_FIELDS, _AUDITABLE_CONTACT_FIELDS, _AUDITABLE_HANDOFF_CHECKLIST_FIELDS
from .commission_service import CommissionService
from .notification_service import NotificationService
from .operations_service import OperationsService
from .scheduling_service import SchedulingService
from . import pdf_service


# B8.7a: Invoice.invoice_type's valid values -- must stay byte-for-byte in
# sync with models.py's Invoice.invoice_type docstring/comment (no CHECK
# constraint at the DB level, same reasoning as ContractSigner.party_role
# and CommissionService._VALID_SOURCE_TYPES -- a real DB's CHECK
# constraint can't be widened later without a full table rebuild).
_VALID_INVOICE_TYPES = {"assessment", "subscription", "project", "other"}

# B8.12b, sales_rep_portal.md §B8.12: explicit deposit-tagging mechanism
# (Ish, 2026-09-24) -- deliberately NOT a sum-of-payments deposit
# inference. A payment recorded via record_payment can be tagged
# payment_type='deposit' (vs the 'installment' default) so
# complete_handoff_checklist's guard can check for a specific tagged
# payment >= Invoice.deposit_amount, rather than guessing intent from
# amounts. Stored as a new key inside each payments_json list entry, not
# a schema/column change -- payments are already an opaque JSON list, no
# separate payments table exists to migrate. No CHECK constraint, same
# reasoning as _VALID_INVOICE_TYPES above.
_VALID_PAYMENT_TYPES = {"installment", "deposit"}

# B8.7c: the result of CRMService._resolve_portfolio_override_eligibility.
# rep_user_id is only meaningful when eligible is True. skip_reason is only
# populated for the ONE skip shape record_payment must audit-log
# (contract_link_missing, the disclosed fail-closed gap) -- every other
# ineligible outcome (outside the window, HomeCare cancelled, signed after
# termination, not a GC invoice, no HomeCare origination at all) is a
# normal business outcome, not logged.
_PortfolioOverrideEligibility = namedtuple(
    "_PortfolioOverrideEligibility", ["eligible", "rep_user_id", "skip_reason"]
)


def _add_months(dt: datetime, months: int) -> datetime:
    """Add a whole number of calendar months to `dt`, clamping the day of
    month to the target month's real length (stdlib only -- no dateutil
    dependency exists in this project, confirmed against requirements.txt).
    Used by the B8.7c 12-month portfolio-override window check."""
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _parse_aware_iso(value: str) -> datetime:
    """Parse a stored ISO timestamp as timezone-aware, coercing a naive
    string to UTC. utc_now_iso() always produces an aware string, but this
    project has no schema-versioning/backfill guarantee that every
    historical row in the DB was written that way -- see
    cancel_homecare_subscription's own datetime.fromisoformat use, which
    this mirrors, extended defensively since B8.7c compares against
    payment timestamps at a real money boundary."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class ClaimConflictError(Exception):
    """Raised by claim_lead/claim_opportunity/claim_task when the atomic
    conditional UPDATE's WHERE assigned_user_id IS NULL guard matched zero
    rows because the record is already claimed (a lost race or a stale
    "Unclaimed" view). Deliberately NOT a ValueError subclass: routes.py's
    handle_request has no 409 anywhere in its global except-chain
    (PermissionError->403, ValueError->400, Exception->500) -- if this
    subclassed ValueError, a route that forgot a local `except
    ClaimConflictError` would silently turn a real conflict into a
    misleading 400 instead of failing loudly. Each claim_* route handler
    must catch this locally and return 409 (NEW-534)."""


class CRMService:
    """Core domain logic and data management for Restoricon Core."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        audit_service: AuditService,
        notification_service: Optional[NotificationService] = None,
        scheduling_service: Optional["SchedulingService"] = None,
        operations_service: Optional["OperationsService"] = None,
        commission_service: Optional["CommissionService"] = None,
    ):
        self.db = db_manager
        self.audit = audit_service
        self.notification_service = notification_service
        # Lazily default-constructed (NEW-510) so delete_subcontractor()'s
        # active-reference guard is available to ANY caller, not just the
        # HTTP route -- and so existing 2-/3-arg call sites (server.py
        # constructs CRMService before SchedulingService/OperationsService
        # exist yet; most tests too) keep working unchanged. Each fallback
        # instance is built with notification_service=None: harmless for
        # the read-only reference queries this guard makes, but a future
        # write call made through self.scheduling/self.operations directly
        # (not through the real SchedulingService/OperationsService
        # instances server.py wires up) would silently skip notifications
        # -- documented here so that isn't re-discovered the hard way.
        self.scheduling = scheduling_service or SchedulingService(self.db, audit_service)
        self.operations = operations_service or OperationsService(self.db, audit_service)
        # B8.7a: same lazy-default-construction rationale as scheduling/
        # operations above -- server.py wires the real shared instance
        # (also used directly by routes.py for the commission-ledger
        # endpoints); a fallback instance here only matters for callers
        # that construct CRMService with fewer args (existing tests,
        # migrate_aigentik.py), and is harmless since CommissionService is
        # stateless beyond the shared db/audit it's given.
        self.commission = commission_service or CommissionService(self.db, audit_service)

    # ==========================================
    # CUSTOMERS
    # ==========================================

    def create_customer(self, customer: Customer, actor: AuthContext) -> Customer:
        if not actor.has_permission(PERM_WRITE_CUSTOMERS):
            raise PermissionError("Actor lacks permission to create customers")

        # NEW-598: force server-side ownership for actors who don't hold
        # PERM_READ_TEAM_SALES_DATA -- routes.py builds `Customer(**json_body)`
        # directly from client input (same shape NEW-548/create_contract was
        # closed for), so a plain rep-tier actor's client-supplied
        # assigned_user_id can't be trusted, and without this a customer
        # created through the guided flow lands unclaimed rather than owned
        # by the creating rep. Unlike create_contract's unconditional
        # override, this is gated: actors who hold PERM_READ_TEAM_SALES_DATA
        # (admin/sales-manager/system-intake tiers -- the same tier
        # update_customer's NEW-568 gate already trusts to reassign
        # ownership on someone else's behalf) keep today's behavior of
        # respecting whatever assigned_user_id was supplied, including None
        # (the unclaimed pool default relied on by web-intake customers and
        # by admin-created customers awaiting manual assignment).
        if not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            customer.assigned_user_id = actor.user_id

        now = utc_now_iso()
        customer.created_at = now
        tags_json = json.dumps(customer.tags)
        custom_fields_json = json.dumps(customer.custom_fields)

        conn = self.db.get_connection()
        with conn:
            # B8.6d-c: customer_number is generated as part of THIS single
            # INSERT statement (INSERT ... SELECT ... FROM customers, not a
            # separate `SELECT MAX(...)` followed by an INSERT) -- a bare
            # SELECT does not start sqlite3's implicit transaction (that
            # only begins at the first DML statement), so splitting the
            # read and the write across two statements would let two
            # concurrent create_customer calls both read the same MAX and
            # both insert the same customer_number, with no DB-level
            # UNIQUE constraint to catch it (SQLite's ALTER TABLE ADD
            # COLUMN can't attach one -- see the customers table's
            # external_id comment for the same limit). A single
            # self-referencing INSERT...SELECT is one atomic write
            # statement: SQLite takes the write lock before evaluating the
            # subquery, so no other writer can interleave between the MAX
            # read and this row's insert.
            cursor = conn.execute(
                """
                INSERT INTO customers (
                    customer_number, external_id, first_name, last_name, company_name, phone, email,
                    mailing_address, service_address, customer_type,
                    customer_source, assigned_user_id, territory_id, status, tags_json,
                    notes, custom_fields_json, created_at, last_contact_at, next_followup_at
                )
                SELECT COALESCE(MAX(customer_number), 0) + 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                FROM customers;
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
                    customer.territory_id,
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
            # Read back the number the INSERT...SELECT above just computed
            # -- a read-after-write on the same connection/transaction that
            # produced it, so it's unaffected by any other writer (no other
            # write could have interleaved with the atomic statement above,
            # and this connection always sees its own not-yet-committed
            # write).
            customer.customer_number = conn.execute(
                "SELECT customer_number FROM customers WHERE id = ?;", (customer.id,)
            ).fetchone()["customer_number"]

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

        # NEW-568 rep-ownership narrowing, mirroring get_lead's pattern
        # (crm_service.py:809 area): a non-customer actor without
        # PERM_READ_TEAM_SALES_DATA only sees customers assigned to them or
        # left unclaimed (assigned_user_id IS NULL) -- everything else is
        # treated as not-found, same as get_lead, rather than a 403 that
        # would leak the record's existence.
        if actor.role != ROLE_CUSTOMER and not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            if row["assigned_user_id"] is not None and row["assigned_user_id"] != actor.user_id:
                return None

        cust = self._row_to_customer(row)
        if actor.role == ROLE_CUSTOMER:
            cust.notes = None  # Hide internal notes from customer
        return cust

    def _get_customer_display_name(self, customer_id: int) -> Optional[str]:
        """Resolve a customer id to a display name, with NO
        actor/permission check at all -- mirrors AuthService.get_user_by_id's
        established pattern (auth.py) for "resolve a display name for an id
        the caller already independently holds from a row they're already
        permitted to see" (e.g. a lead/opportunity's customer_id). This is
        deliberately NOT get_customer(): get_customer enforces the NEW-568
        per-row ownership narrowing, and a lead's assigned_user_id can
        legitimately diverge from its linked customer's assigned_user_id --
        using get_customer here would silently hide the very rows this is
        meant to name. Discloses only a name, not the full customer record,
        for an id the caller doesn't get to choose (it comes from an
        already-authorized row), so no new permission constant is needed.
        Returns None for a nonexistent id, never raises."""
        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT first_name, last_name, company_name FROM customers WHERE id = ?;",
            (customer_id,),
        ).fetchone()
        if not row:
            return None
        full_name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
        return full_name or row["company_name"] or None

    def _get_project_display_name(self, project_id: int) -> Optional[str]:
        """Resolve a project id to a display name (its title), with NO
        actor/permission check at all -- same rationale as
        `_get_customer_display_name` above: the caller already
        independently holds this id from a row (e.g. a document) it is
        already authorized to see, so disclosing only a name for that id
        needs no new permission constant. Returns None for a nonexistent
        id, never raises."""
        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT title FROM projects WHERE id = ?;",
            (project_id,),
        ).fetchone()
        if not row:
            return None
        return row["title"] or None

    def _get_customer_unscoped(self, customer_id: int) -> Optional[Customer]:
        """NEW-587 fix: fetch a customer with NO ownership/narrowing check
        at all -- not even the NEW-568 rep-ownership narrowing that
        get_customer applies. Only for callers that have already
        established the caller's authorization to view this customer
        through a *different*, already-narrowed record (e.g. the proposal
        route below, which only reaches here after get_estimate's own
        rep-ownership narrowing already confirmed the actor may see this
        estimate, and therefore the customer info needed to render it).

        Do NOT call this from a route or service method that hasn't
        already independently authorized access to this specific
        customer_id -- it has no access control of its own. `notes` is
        always cleared (hardcoded, not actor-conditioned) since this
        helper takes no actor and has no basis to decide who's allowed to
        see internal notes; callers needing notes must use get_customer."""
        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM customers WHERE id = ?;", (customer_id,)).fetchone()
        if not row:
            return None
        cust = self._row_to_customer(row)
        cust.notes = None
        return cust

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
        territory_id: Optional[int] = None,
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

        # B8.9a: territory_id filter, same 1=1-appended shape as status
        # above.
        if territory_id is not None:
            query += " AND territory_id = ?"
            params.append(territory_id)

        if search_term:
            term = f"%{search_term.strip()}%"
            query += " AND (first_name LIKE ? OR last_name LIKE ? OR company_name LIKE ? OR phone LIKE ? OR email LIKE ?)"
            params.extend([term, term, term, term, term])

        # NEW-568 rep-ownership narrowing, matching list_leads's convention
        # (crm_service.py:844 area): a plain sales actor (no
        # PERM_READ_TEAM_SALES_DATA) only sees customers assigned to them or
        # still unclaimed. Full-tier actors (admin/manager/ai_agent/
        # sales_manager) are unaffected -- no extra clause is added for them,
        # same as today.
        if not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            query += " AND (assigned_user_id = ? OR assigned_user_id IS NULL)"
            params.append(actor.user_id)

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
            # customer_number (B8.6d-c): unguarded direct access, matching
            # this method's existing style for every other column -- safe
            # because _migrate_schema()'s ALTER always runs inside
            # DatabaseManager.__init__ before any row can be read, so the
            # column is guaranteed to exist on every reachable connection.
            customer_number=row["customer_number"],
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
            # territory_id (B8.9a): unguarded direct access, same
            # justification as customer_number above -- _migrate_schema()'s
            # ALTER always runs before any row can be read.
            territory_id=row["territory_id"],
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
        "territory_id",
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

        # NEW-568: assigned_user_id is part of ALLOWED_CUSTOMER_UPDATE_FIELDS
        # (pre-existing), but reassigning ownership is the admin/sales-manager
        # action Part 2 of NEW-568 asks for -- gating it on the general
        # PERM_WRITE_CUSTOMERS alone would let any plain ROLE_SALES actor
        # (who already holds that permission) reassign any customer to
        # anyone, defeating the narrowing this same change adds to
        # list_customers/get_customer. Reuse PERM_READ_TEAM_SALES_DATA (the
        # same permission that ungates full-tier visibility) rather than
        # inventing a new permission -- it is exactly the tier the task
        # calls "admin/sales manager".
        if "assigned_user_id" in updates and not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            raise PermissionError("Actor lacks permission to reassign customer ownership")

        for key, value in updates.items():
            if value is None and key not in ("assigned_user_id", "territory_id"):
                raise ValueError(
                    f"Field '{key}' cannot be set to None via update_customer; omit the key instead"
                )
            # assigned_user_id may be explicitly None -- that's how a
            # customer is returned to the unclaimed pool (NEW-568 Part 2).
            # territory_id (B8.9a) may also be explicitly None -- how a
            # customer is returned to "no territory", same nullable-
            # cross-entity-reference shape as assigned_user_id.

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

            # NEW-306: build the after-image from a raw post-write row read
            # rather than self.get_customer(), which re-runs the read-gate
            # (can_access_customer) that a write-capable-but-read-refused
            # actor may not pass. _row_to_customer is a plain staticmethod
            # with no role parameter and does not redact `notes` the way
            # get_customer() does for ROLE_CUSTOMER. custom_permissions can
            # grant a ROLE_CUSTOMER actor PERM_WRITE_CUSTOMERS (has_permission
            # checks custom_permissions before the static ROLE_PERMISSIONS
            # table), so that actor CAN reach this write path -- apply the
            # same notes redaction get_customer() applies, inline, without
            # re-invoking the read-permission gate (calling get_customer()
            # here would reintroduce NEW-306's original 403-on-legitimate-
            # write bug).
            updated_row = conn.execute(
                "SELECT * FROM customers WHERE id = ?;", (customer_id,)
            ).fetchone()
            updated_cust = self._row_to_customer(updated_row) if updated_row else None
            if updated_cust is not None and actor.role == ROLE_CUSTOMER:
                updated_cust.notes = None
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
        """Create or update customer by external_id with write-through semantics.

        NOTE (NEW-568 follow-up, not fixed this round): get_customer_by_external_id
        below delegates its authorization entirely to get_customer() (NEW-248,
        deliberate), which now also applies rep-ownership narrowing. A narrowed
        actor (no PERM_READ_TEAM_SALES_DATA) calling upsert on an external_id
        that already exists but is assigned to a *different* rep will see
        `existing is None` (treated as not-found by narrowing) and fall through
        to create_customer with the same external_id, raising sqlite3.IntegrityError
        instead of a clean 403/404. Pre-existing sharp edge, made reachable by
        this round's narrowing; flagged for NEW_ISSUES.md rather than fixed here."""
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
        # NOTE (NEW-568 follow-up, not fixed this round): this lookup is
        # gated below on PERM_READ_ALL_CUSTOMERS only, same as
        # get_customer_by_email -- neither applies the new rep-ownership
        # narrowing added to get_customer/list_customers. Flagged for
        # NEW_ISSUES.md rather than fixed here (out of this round's scope).
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
    # PROPERTIES (B8.1, D4, sales_rep_portal.md §4, Ish-approved 2026-09-16)
    # ==========================================
    # Gated on PERM_READ_ALL_CUSTOMERS / PERM_WRITE_CUSTOMERS, the same
    # permissions that already gate Customer CRUD above, rather than a new
    # PERM_READ_PROPERTIES/PERM_WRITE_PROPERTIES pair -- properties.customer_id
    # is a direct FK to customers and a property record carries no more
    # sensitivity than a customer's mailing/service address already does.
    # No PERM_READ_TEAM_SALES_DATA-style ownership narrowing here: unlike
    # leads/opportunities/tasks, properties have no assigned_user_id to
    # narrow on.

    def create_property(self, prop: Property, actor: AuthContext) -> Property:
        if not actor.has_permission(PERM_WRITE_CUSTOMERS):
            raise PermissionError("Actor lacks permission to create properties")

        now = utc_now_iso()
        prop.created_at = now
        existing_systems_json = json.dumps(prop.existing_systems)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO properties (
                    external_id, customer_id, address, parcel_number, property_type,
                    year_built, square_footage, stories, roof_type, exterior_type,
                    existing_systems_json, insurance_carrier, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    prop.external_id,
                    prop.customer_id,
                    prop.address,
                    prop.parcel_number,
                    prop.property_type,
                    prop.year_built,
                    prop.square_footage,
                    prop.stories,
                    prop.roof_type,
                    prop.exterior_type,
                    existing_systems_json,
                    prop.insurance_carrier,
                    prop.notes,
                    now,
                ),
            )
            prop.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="property",
            entity_id=prop.id,
            change_summary=f"Created property {prop.address}",
            actor=actor,
            details=build_audit_details(after=prop.to_dict()),
        )
        return prop

    @staticmethod
    def _row_to_property(row: Any) -> Property:
        existing_systems = json.loads(row["existing_systems_json"]) if row["existing_systems_json"] else {}
        return Property(
            id=row["id"],
            external_id=row["external_id"],
            customer_id=row["customer_id"],
            address=row["address"],
            parcel_number=row["parcel_number"],
            property_type=row["property_type"],
            year_built=row["year_built"],
            square_footage=row["square_footage"],
            stories=row["stories"],
            roof_type=row["roof_type"],
            exterior_type=row["exterior_type"],
            existing_systems=existing_systems,
            insurance_carrier=row["insurance_carrier"],
            notes=row["notes"],
            created_at=row["created_at"],
        )

    def get_property(self, property_id: int, actor: AuthContext) -> Optional[Property]:
        if not actor.has_permission(PERM_READ_ALL_CUSTOMERS):
            raise PermissionError("Actor lacks permission to view properties")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM properties WHERE id = ?;", (property_id,)).fetchone()
        if not row:
            return None
        return self._row_to_property(row)

    def list_properties(
        self, actor: AuthContext, customer_id: Optional[int] = None
    ) -> List[Property]:
        if not actor.has_permission(PERM_READ_ALL_CUSTOMERS):
            raise PermissionError("Actor lacks permission to list properties")

        query = "SELECT * FROM properties WHERE 1=1"
        params: List[Any] = []
        if customer_id is not None:
            query += " AND customer_id = ?"
            params.append(customer_id)
        query += " ORDER BY id DESC;"

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_property(r) for r in rows]

    ALLOWED_PROPERTY_UPDATE_FIELDS = {
        "customer_id",
        "address",
        "parcel_number",
        "property_type",
        "year_built",
        "square_footage",
        "stories",
        "roof_type",
        "exterior_type",
        "existing_systems",
        "insurance_carrier",
        "notes",
    }

    def update_property(
        self, property_id: int, updates: Dict[str, Any], actor: AuthContext
    ) -> Optional[Property]:
        """Partial update for property records with allow-list enforcement,
        None-value guard, and existing_systems shallow merge -- mirrors
        update_customer's shape above."""
        if not actor.has_permission(PERM_WRITE_CUSTOMERS):
            raise PermissionError("Actor lacks permission to update properties")

        unknown = set(updates) - self.ALLOWED_PROPERTY_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unknown field(s) for property update: {sorted(unknown)}")

        for key, value in updates.items():
            if value is None:
                raise ValueError(
                    f"Field '{key}' cannot be set to None via update_property; omit the key instead"
                )

        if not updates:
            return self.get_property(property_id, actor)

        conn = self.db.get_connection()
        with conn:
            row = conn.execute(
                "SELECT * FROM properties WHERE id = ?;", (property_id,)
            ).fetchone()
            if not row:
                return None

            _before = {}
            for k in updates:
                if k == "existing_systems":
                    _before[k] = json.loads(row["existing_systems_json"]) if row["existing_systems_json"] else {}
                else:
                    _before[k] = row[k]

            set_clauses = []
            params: List[Any] = []
            for key, value in updates.items():
                if key == "existing_systems":
                    existing = json.loads(row["existing_systems_json"]) if row["existing_systems_json"] else {}
                    merged = {**existing, **value}
                    set_clauses.append("existing_systems_json = ?")
                    params.append(json.dumps(merged))
                else:
                    set_clauses.append(f"{key} = ?")
                    params.append(value)

            params.append(property_id)
            cursor = conn.execute(
                f"UPDATE properties SET {', '.join(set_clauses)} WHERE id = ?;",
                params,
            )
            if cursor.rowcount == 0:
                return None

            updated_row = conn.execute(
                "SELECT * FROM properties WHERE id = ?;", (property_id,)
            ).fetchone()
            updated_prop = self._row_to_property(updated_row) if updated_row else None

        details = build_audit_details(
            before=_before,
            after=updated_prop.to_dict() if updated_prop else None,
            fields=sorted(updates),
        )
        self.audit.log(
            action="update",
            entity_type="property",
            entity_id=property_id,
            change_summary=f"Property {property_id} updated ({', '.join(sorted(updates.keys()))})",
            actor=actor,
            details=details,
        )
        return updated_prop

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
            territory_id=row["territory_id"] if "territory_id" in keys else None,
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
                    estimated_value, assigned_user_id, territory_id, first_contact_at, last_contact_at,
                    next_followup_at, notes, lost_reason, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                    lead.territory_id,
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
        lead = self._row_to_lead(row)
        if not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            if lead.assigned_user_id is not None and lead.assigned_user_id != actor.user_id:
                return None  # treat as not-found. update_lead/update_opportunity/update_task
                # already treat a None get_* result as not-found -> 404. score_lead,
                # transition_opportunity_stage, complete_task, and generate_cadence_tasks
                # instead raise ValueError("... not found") on a None get_* result, which
                # handle_request's except-chain maps to 400, not 404 -- still a controlled,
                # non-leaking not-found signal, just a different status code per caller.
        return lead

    def _scoped_assignee_filter(self, actor: AuthContext, requested_assigned_user_id: Optional[int]) -> Optional[int]:
        """
        Resolves the effective assigned_user_id filter for a read.
        Holders of PERM_READ_TEAM_SALES_DATA pass their own requested filter
        through unchanged (None = whole team, a specific id = drill into one
        rep). Everyone else is forced to their own user_id regardless of what
        they requested -- narrowing is keyed on permission, never actor.role,
        per the PERM_REASSIGN_PROJECT_STAFF/PERM_REASSIGN_ANY_PROJECT_STAFF
        precedent, so ai_agent's unrestricted CRM access (Aigentik's
        integration identity) is preserved via the permission grant, not a
        role special-case.
        """
        if actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            return requested_assigned_user_id
        return actor.user_id

    def list_leads(
        self,
        actor: AuthContext,
        status: Optional[str] = None,
        assigned_user_id: Optional[int] = None,
        territory_id: Optional[int] = None,
    ) -> List[Lead]:
        if not (actor.has_permission(PERM_READ_LEADS) or actor.has_permission(PERM_READ_CRM)):
            raise PermissionError("Actor lacks permission to view leads")

        query = "SELECT * FROM leads WHERE 1=1"
        params: List[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)

        # B8.9a: territory_id filter, composes with the assigned_user_id/
        # unclaimed-pool narrowing below rather than replacing it -- both
        # clauses are simply AND-ed onto the same query.
        if territory_id is not None:
            query += " AND territory_id = ?"
            params.append(territory_id)

        effective_uid = self._scoped_assignee_filter(actor, assigned_user_id)
        if effective_uid is not None:
            if actor.has_permission(PERM_READ_TEAM_SALES_DATA):
                query += " AND assigned_user_id = ?"
                params.append(effective_uid)
            else:
                # unclaimed-pool visibility: nothing in this codebase auto-assigns
                # a lead/opportunity/task at creation, so a narrowed actor must
                # still see unclaimed rows or the portal goes empty. Once claimed
                # by someone else, the row disappears from the narrowed actor's
                # view. See NEW-534 for the follow-up gap this leaves (no claim
                # workflow / race protection) -- logged, not fixed here.
                query += " AND (assigned_user_id = ? OR assigned_user_id IS NULL)"
                params.append(effective_uid)

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
            "estimated_value", "assigned_user_id", "territory_id", "first_contact_at",
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
                    estimated_value = ?, assigned_user_id = ?, territory_id = ?, first_contact_at = ?,
                    last_contact_at = ?, next_followup_at = ?, notes = ?, lost_reason = ?,
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    lead.customer_id, lead.source, lead.status, lead.score, factors_json,
                    lead.property_type, lead.project_scope, lead.urgency_level, lead.insurance_status,
                    lead.estimated_value, lead.assigned_user_id, lead.territory_id, lead.first_contact_at,
                    lead.last_contact_at, lead.next_followup_at, lead.notes, lead.lost_reason,
                    now, lead_id,
                ),
            )

        # NEW-533: after-image is built from the already-updated in-memory
        # `lead` object, NOT a re-read via self.get_lead(lead_id, actor).
        # `lead` already reflects every column written above (identical
        # values). A re-read would re-run get_lead's PERM_READ_TEAM_SALES_DATA
        # narrowing gate, which a narrowed actor reassigning assigned_user_id
        # AWAY from themselves would fail -- silently recording after=None
        # for the exact reassignment event. Same NEW-306 class of bug
        # (re-invoking a read gate for an audit after-image breaks it for a
        # write-capable-but-now-read-refused actor), applied here to the
        # narrowing this round adds instead of NEW-306's original mismatch.
        self.audit.log(
            action="update",
            entity_type="lead",
            entity_id=lead_id,
            change_summary=f"Updated lead {lead_id}",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=lead.to_dict(),
            ),
        )
        return lead

    def claim_lead(self, lead_id: int, actor: AuthContext) -> Optional[Lead]:
        """NEW-534: atomic self-claim of an unclaimed lead. Hardcodes
        assigned_user_id = actor.user_id -- never accepts a caller-supplied
        assignee, unlike the generic update_lead path (which already lets
        any write-permitted actor assign to anyone and is left unchanged).
        Returns None (-> 404, matching update_lead's not-found convention;
        NOT a ValueError, since routes.py's global except-chain maps
        ValueError to 400) if the id genuinely doesn't exist. Raises
        ClaimConflictError (-> 409, mapped locally by the route) if it's
        already claimed by someone else or lost a race against a concurrent
        claim."""
        if not (actor.has_permission(PERM_WRITE_LEADS) or actor.has_permission(PERM_WRITE_CRM)):
            raise PermissionError("Actor lacks permission to update leads")

        conn = self.db.get_connection()
        # Raw, unguarded pre-read to build the in-memory Lead object this
        # claim will mutate -- deliberately NOT self.get_lead(lead_id,
        # actor): that applies the PERM_READ_TEAM_SALES_DATA narrowing
        # gate, which for a row already claimed by someone else returns
        # None identically to a genuinely nonexistent id (the exact
        # ambiguity the post-write disambiguation query below exists to
        # avoid). A narrowed actor may attempt a claim on any row id;
        # whether it succeeds is governed solely by the atomic UPDATE's
        # WHERE clause, not by this pre-read.
        row = conn.execute("SELECT * FROM leads WHERE id = ?;", (lead_id,)).fetchone()
        if row is None:
            return None
        lead = self._row_to_lead(row)
        _before = lead.to_dict()

        now = utc_now_iso()
        with conn:
            cursor = conn.execute(
                "UPDATE leads SET assigned_user_id = ?, updated_at = ? "
                "WHERE id = ? AND assigned_user_id IS NULL;",
                (actor.user_id, now, lead_id),
            )

        if cursor.rowcount == 0:
            # Second, unguarded disambiguation query (raw SQL, not
            # get_lead): distinguishes a lost race / already-claimed row
            # (row present, assigned_user_id not null) from the row having
            # been deleted between the pre-read above and this UPDATE (row
            # absent). Using get_lead here would misreport a genuine 409
            # conflict as a 404 for a narrowed actor, since get_lead
            # returns None for both cases.
            conflict_row = conn.execute(
                "SELECT id, assigned_user_id FROM leads WHERE id = ?;", (lead_id,)
            ).fetchone()
            if conflict_row is None:
                return None
            raise ClaimConflictError(f"Lead {lead_id} already claimed")

        # rowcount == 1: build the after-image from the already-known
        # in-memory `lead` object mutated with exactly the values just
        # written -- NOT a re-read via self.get_lead(lead_id, actor).
        # Matches the NEW-533 pattern update_lead already established:
        # never route an audit after-image / return value through a
        # permission-gated getter.
        lead.assigned_user_id = actor.user_id
        lead.updated_at = now

        self.audit.log(
            action="claim",
            entity_type="lead",
            entity_id=lead_id,
            change_summary=f"Lead {lead_id} claimed by user {actor.user_id}",
            actor=actor,
            details=build_audit_details(before=_before, after=lead.to_dict()),
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

        # NEW-557: Opportunity.customer_id's dataclass default is 0 (an
        # `int` field, not Optional), which is not a real customers.id --
        # the `opportunities.customer_id` FK has no ON DELETE behavior that
        # tolerates it and every real caller/fixture in this codebase always
        # supplies a real id (verified via a full-repo grep of `Opportunity(`
        # before adding this guard). Reject the default/invalid case here
        # rather than let it reach the FK constraint as an opaque IntegrityError.
        if not opp.customer_id or opp.customer_id <= 0:
            raise ValueError("Opportunity.customer_id must be a positive, existing customer id")

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

    # Identity/contact fields a caller may supply to fill in a missing
    # Customer when converting a lead (NEW-556). Deliberately a small,
    # explicit subset of Customer's real field names -- Lead itself carries
    # no name/phone/email/address fields at all (verified directly against
    # models.py), so this data can only come from the caller, never be
    # derived from the Lead record.
    _CONVERT_CUSTOMER_FIELDS = {
        "first_name", "last_name", "company_name", "phone", "email",
        "mailing_address", "service_address", "customer_type",
        "customer_source", "notes",
    }

    def convert_lead_to_opportunity(
        self,
        lead_id: int,
        actor: AuthContext,
        opportunity_title: Optional[str] = None,
        customer_fields: Optional[Dict[str, Any]] = None,
    ) -> Opportunity:
        """NEW-556: the missing lead->opportunity conversion path. One
        service-layer call, not client-side orchestration of two separate
        API requests -- though NOT one DB transaction: create_customer/
        create_opportunity/update_lead each own their own `with conn:`
        block on this project's single sqlite3 connection, so nesting them
        here commits at each inner block's exit already. "Atomic" in this
        method's contract means "one service call, one audited unit of
        work", not a single SQL transaction.

        NEW-311's accepted scope covers *concurrent* read-then-write races
        (two actors racing against the same row) -- that's what ruled out a
        BEGIN IMMEDIATE change for this class of multi-write service call,
        and it's what this method is safe against by the same reasoning.
        It does NOT cover *sequential partial failure inside one call*:
        e.g. create_customer commits but create_opportunity then fails
        (different required permissions -- PERM_WRITE_CUSTOMERS vs.
        PERM_WRITE_OPPORTUNITIES/PERM_WRITE_CRM -- so this is reachable,
        not hypothetical), or create_opportunity commits but the final
        update_lead fails. A caller retry after such a failure can
        re-create a duplicate Customer and/or duplicate Opportunity. The
        customer_id writeback onto the Lead below narrows this for the
        "only the final update_lead failed" case (a retry finds
        lead.customer_id already set and skips re-creating the Customer),
        but does not eliminate the duplication risk for the other failure
        points. See NEW-561 (logged, not fixed this round -- would need
        either a real multi-statement transaction or an idempotency key).

        Field mapping is deliberately conservative: only `estimated_value`
        and `notes` have a verified real overlap between Lead and
        Opportunity (read directly off both dataclasses in models.py).
        Lead.property_type/project_scope/urgency_level/insurance_status
        have no corresponding Opportunity column -- they are folded into
        the derived title/notes instead of guessed onto a same-named-looking
        but differently-vocabularied column (e.g. Opportunity.
        insurance_claim_status uses a different value vocabulary than
        Lead.insurance_status, per score_lead's own insurance keyword list).
        """
        lead = self.get_lead(lead_id, actor)
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")

        if lead.status == "converted":
            raise ValueError(f"Lead {lead_id} has already been converted")

        customer_id = lead.customer_id
        if not customer_id:
            if not customer_fields:
                raise ValueError(
                    f"Lead {lead_id} has no linked customer; supply customer_fields "
                    "(e.g. first_name/last_name/phone/email) to convert"
                )
            unknown = set(customer_fields) - self._CONVERT_CUSTOMER_FIELDS
            if unknown:
                raise ValueError(f"Unknown field(s) for customer_fields: {sorted(unknown)}")
            new_customer = Customer(
                first_name=str(customer_fields.get("first_name", "")).strip(),
                last_name=str(customer_fields.get("last_name", "")).strip(),
                company_name=customer_fields.get("company_name"),
                phone=customer_fields.get("phone"),
                email=customer_fields.get("email"),
                mailing_address=customer_fields.get("mailing_address"),
                service_address=customer_fields.get("service_address"),
                customer_type=customer_fields.get("customer_type", "residential"),
                customer_source=customer_fields.get("customer_source", lead.source),
                notes=customer_fields.get("notes"),
            )
            if not new_customer.first_name and not new_customer.last_name and not new_customer.company_name:
                raise ValueError(
                    "customer_fields must include at least a first_name, last_name, or company_name"
                )
            created_customer = self.create_customer(new_customer, actor)
            customer_id = created_customer.id

        title = opportunity_title or f"{(lead.property_type or 'Project').capitalize()} - Lead #{lead.id} ({lead.source})"

        opp = Opportunity(
            customer_id=customer_id,
            title=title,
            estimated_value=lead.estimated_value or 0.0,
            pipeline_stage=PipelineStage.NEW_LEAD,
            # Carry the lead's assignment over: create_opportunity/
            # list_opportunities apply no auto-assignment of their own, so a
            # rep converting their own claimed lead would otherwise land on
            # an unclaimed opportunity and immediately hit Part C's own
            # "Claim first" gate on a deal they just created.
            assigned_user_id=lead.assigned_user_id,
            notes=lead.notes,
        )
        created_opp = self.create_opportunity(opp, actor)

        # Mark the lead converted so Convert can't be fired twice into two
        # separate opportunities off one lead. update_lead already
        # audit-logs this write; a genuine re-conversion attempt after this
        # point is rejected by the status == "converted" guard above.
        self.update_lead(
            lead_id, {"status": "converted", "customer_id": customer_id}, actor
        )

        return created_opp

    def get_opportunity(self, opp_id: int, actor: AuthContext) -> Optional[Opportunity]:
        if not (actor.has_permission(PERM_READ_OPPORTUNITIES) or actor.has_permission(PERM_READ_CRM)):
            raise PermissionError("Actor lacks permission to view opportunities")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM opportunities WHERE id = ?;", (opp_id,)).fetchone()
        if not row:
            return None
        opp = self._row_to_opportunity(row)
        if not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            if opp.assigned_user_id is not None and opp.assigned_user_id != actor.user_id:
                return None  # treat as not-found. update_lead/update_opportunity/update_task
                # already treat a None get_* result as not-found -> 404. score_lead,
                # transition_opportunity_stage, complete_task, and generate_cadence_tasks
                # instead raise ValueError("... not found") on a None get_* result, which
                # handle_request's except-chain maps to 400, not 404 -- still a controlled,
                # non-leaking not-found signal, just a different status code per caller.
        return opp

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

        effective_uid = self._scoped_assignee_filter(actor, assigned_user_id)
        if effective_uid is not None:
            if actor.has_permission(PERM_READ_TEAM_SALES_DATA):
                query += " AND assigned_user_id = ?"
                params.append(effective_uid)
            else:
                # unclaimed-pool visibility: nothing in this codebase auto-assigns
                # a lead/opportunity/task at creation, so a narrowed actor must
                # still see unclaimed rows or the portal goes empty. Once claimed
                # by someone else, the row disappears from the narrowed actor's
                # view. See NEW-534 for the follow-up gap this leaves (no claim
                # workflow / race protection) -- logged, not fixed here.
                query += " AND (assigned_user_id = ? OR assigned_user_id IS NULL)"
                params.append(effective_uid)

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

        # NEW-533: after-image built from the already-updated in-memory `opp`
        # object rather than a re-read via self.get_opportunity(opp_id, actor)
        # -- see the matching comment in update_lead for why a re-read would
        # break the audit trail specifically for an actor reassigning
        # assigned_user_id away from themselves.
        self.audit.log(
            action="update",
            entity_type="opportunity",
            entity_id=opp_id,
            change_summary=f"Updated opportunity {opp_id}",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=opp.to_dict(),
            ),
        )
        return opp

    def claim_opportunity(self, opp_id: int, actor: AuthContext) -> Optional[Opportunity]:
        """NEW-534: atomic self-claim of an unclaimed opportunity. Mirrors
        claim_lead exactly -- see its docstring/comments for the full
        rationale (hardcoded self-claim, raw unguarded pre-/post-read,
        None on not-found matching update_opportunity's convention,
        ClaimConflictError on conflict)."""
        if not (actor.has_permission(PERM_WRITE_OPPORTUNITIES) or actor.has_permission(PERM_WRITE_CRM)):
            raise PermissionError("Actor lacks permission to update opportunities")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM opportunities WHERE id = ?;", (opp_id,)).fetchone()
        if row is None:
            return None
        opp = self._row_to_opportunity(row)
        _before = opp.to_dict()

        now = utc_now_iso()
        with conn:
            cursor = conn.execute(
                "UPDATE opportunities SET assigned_user_id = ?, updated_at = ? "
                "WHERE id = ? AND assigned_user_id IS NULL;",
                (actor.user_id, now, opp_id),
            )

        if cursor.rowcount == 0:
            conflict_row = conn.execute(
                "SELECT id, assigned_user_id FROM opportunities WHERE id = ?;", (opp_id,)
            ).fetchone()
            if conflict_row is None:
                return None
            raise ClaimConflictError(f"Opportunity {opp_id} already claimed")

        opp.assigned_user_id = actor.user_id
        opp.updated_at = now

        self.audit.log(
            action="claim",
            entity_type="opportunity",
            entity_id=opp_id,
            change_summary=f"Opportunity {opp_id} claimed by user {actor.user_id}",
            actor=actor,
            details=build_audit_details(before=_before, after=opp.to_dict()),
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

        # NEW-559/NEW-533: after-image built from the already-updated
        # in-memory `opp` object rather than a re-read via
        # self.get_opportunity(opp_id, actor) -- aligns with the
        # NEW-533-corrected pattern in update_lead/update_opportunity, so
        # a permission-gated re-read can never silently substitute `None`
        # into the audit after-image here either.
        _after = opp

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

    def get_stage_duration_analytics(self, actor: AuthContext) -> Dict[str, Any]:
        """B8.3 Part D: rep-facing "where are MY leads stuck" analytics.

        Deliberately built here, not in AnalyticsSearchService per
        sales_rep_portal.md's literal wording -- that service's
        get_executive_dashboard does unscoped company-wide SQL gated only
        behind PERM_VIEW_REPORTS, the wrong permission model for a
        rep-facing panel. Gated the same way get_pipeline_summary already
        is, scoped via list_opportunities(actor)'s existing narrowing.

        Reads audit_log directly for 'create'/'stage_transition' rows on
        each visible opportunity. build_audit_details (audit_service.py)
        does NOT store raw before/after dicts -- it diffs them into
        {"changed_fields": {field: {"old":..., "new":...}}}. The create
        row's build_audit_details(after=opp.to_dict()) call (before=None)
        still emits changed_fields (every key comes out as {"old": None,
        "new": <value>} because the before-diff against the empty {} b
        dict is unconditional in that branch), so
        changed_fields.pipeline_stage.new is present on create rows too --
        verified directly against build_audit_details's source before
        relying on it here.
        """
        if not (actor.has_permission(PERM_READ_OPPORTUNITIES) or actor.has_permission(PERM_READ_CRM)):
            raise PermissionError("Actor lacks permission to view sales pipeline stage analytics")

        visible_opps = self.list_opportunities(actor)
        opp_by_id: Dict[int, Opportunity] = {o.id: o for o in visible_opps if o.id is not None}
        ids = list(opp_by_id.keys())

        conn = self.db.get_connection()
        rows_by_id: Dict[int, List[Any]] = {}
        # Chunked to respect SQLite's bound-variable limit (default 999) --
        # each opportunity id appears in exactly one chunk's query, so its
        # audit rows (already ORDER BY entity_id, timestamp ASC within that
        # single query) never need re-merging across chunks.
        _CHUNK = 400
        for start in range(0, len(ids), _CHUNK):
            batch = ids[start:start + _CHUNK]
            if not batch:
                continue
            placeholders = ",".join("?" for _ in batch)
            query = (
                "SELECT entity_id, action, timestamp, details_json FROM audit_log "
                "WHERE entity_type = 'opportunity' AND action IN ('create', 'stage_transition') "
                f"AND entity_id IN ({placeholders}) ORDER BY entity_id, timestamp ASC;"
            )
            for row in conn.execute(query, batch).fetchall():
                rows_by_id.setdefault(row["entity_id"], []).append(row)

        def _parse_iso(ts: str) -> datetime:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))

        def _safe_details(row: Any) -> Dict[str, Any]:
            # A malformed details_json would be a pre-existing data
            # integrity issue in an already-committed audit row (this
            # method only reads audit_log, it never writes it) -- treating
            # it as "no usable diff for this row" and falling through to
            # this opportunity's fallback/broken-chain bucket is safe: it
            # can only ever make this analytics report more conservative
            # (fewer full-chain averages), never mask a live mutation.
            try:
                return json.loads(row["details_json"]) if row["details_json"] else {}
            except (TypeError, ValueError):
                return {}

        stage_hours: Dict[str, List[float]] = {}
        full_chain_count = 0
        fallback_count = 0
        chain_broken_count = 0
        currently_stuck: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        terminal_stages = (PipelineStage.WON, PipelineStage.LOST)

        for opp_id, opp in opp_by_id.items():
            rows = rows_by_id.get(opp_id, [])
            create_row = next((r for r in rows if r["action"] == "create"), None)

            prev_stage: Optional[str] = None
            prev_ts: Optional[datetime] = None
            has_usable_chain = False
            chain_broken = False

            # Entries accumulated for THIS opportunity's walk only -- held
            # back from stage_hours until the whole chain is confirmed
            # unbroken, so a mid-walk break retracts any hours already
            # computed for this opportunity rather than letting them
            # silently feed avg_hours_per_stage from a partial/untrusted
            # chain (see the "also" fix in the NEW-561 review round).
            pending_stage_hours: List[Any] = []

            if create_row is not None:
                start_stage = (
                    _safe_details(create_row).get("changed_fields", {}).get("pipeline_stage", {}).get("new")
                )
                if start_stage:
                    try:
                        prev_stage = start_stage
                        prev_ts = _parse_iso(create_row["timestamp"])
                        has_usable_chain = True
                    except (TypeError, ValueError):
                        # A malformed timestamp on the create row is corrupt
                        # audit data, not absent audit data -- put it in the
                        # same bucket/handling as the changed_fields.
                        # pipeline_stage.new is None broken-chain case below
                        # (chain_broken_count), not lumped in with
                        # legitimately no-audit-history migrated records
                        # (fallback_count).
                        chain_broken = True

            if has_usable_chain:
                for row in rows:
                    if row["action"] != "stage_transition":
                        continue
                    changed = _safe_details(row).get("changed_fields", {}).get("pipeline_stage", {})
                    new_stage = changed.get("new")
                    if new_stage is None:
                        # NEW-559 (logged, not fixed here): a broken link in
                        # this chain. Exclude this row from duration math and
                        # stop walking further -- continuity past this point
                        # can't be trusted -- and count the opportunity in
                        # the chain-broken bucket instead of silently
                        # skipping it or crashing.
                        chain_broken = True
                        break
                    try:
                        row_ts = _parse_iso(row["timestamp"])
                    except (TypeError, ValueError):
                        # Same reasoning as the create-row parse above and
                        # the stage_entered_at/created_at fallback parse
                        # below: a malformed stored timestamp is
                        # pre-existing data, not something this read-only
                        # report should raise on. Treat as a broken chain
                        # from this point rather than crashing the endpoint.
                        chain_broken = True
                        break
                    if prev_stage is not None and prev_ts is not None:
                        hours = (row_ts - prev_ts).total_seconds() / 3600.0
                        if hours >= 0:
                            pending_stage_hours.append((prev_stage, hours))
                    prev_stage = new_stage
                    prev_ts = row_ts

            if has_usable_chain and not chain_broken:
                for stage, hours in pending_stage_hours:
                    stage_hours.setdefault(stage, []).append(hours)
                full_chain_count += 1
                if opp.pipeline_stage not in terminal_stages and prev_ts is not None:
                    hours_in_stage = (now - prev_ts).total_seconds() / 3600.0
                    currently_stuck.append({
                        "opportunity_id": opp_id,
                        "stage": opp.pipeline_stage,
                        "hours_in_stage": round(max(hours_in_stage, 0.0), 2),
                    })
            else:
                if chain_broken:
                    chain_broken_count += 1
                else:
                    fallback_count += 1
                # No usable chain (e.g. migrate_aigentik.py-imported
                # opportunities with no audit history at all) or a broken
                # one: fall back to stage_entered_at/created_at for a
                # "currently stuck" figure only, never a historical average.
                fallback_ts_raw = opp.stage_entered_at or opp.created_at
                if opp.pipeline_stage not in terminal_stages and fallback_ts_raw:
                    try:
                        fallback_ts = _parse_iso(fallback_ts_raw)
                    except (TypeError, ValueError):
                        # Same reasoning as _safe_details above: an
                        # unparseable stored timestamp is a pre-existing
                        # data issue, not something this read-only report
                        # can or should repair -- just omit this
                        # opportunity from currently_stuck rather than
                        # raising out of an analytics endpoint.
                        fallback_ts = None
                    if fallback_ts is not None:
                        hours_in_stage = (now - fallback_ts).total_seconds() / 3600.0
                        currently_stuck.append({
                            "opportunity_id": opp_id,
                            "stage": opp.pipeline_stage,
                            "hours_in_stage": round(max(hours_in_stage, 0.0), 2),
                        })

        avg_hours_per_stage = {
            stage: round(sum(vals) / len(vals), 2) for stage, vals in stage_hours.items() if vals
        }

        return {
            "avg_hours_per_stage": avg_hours_per_stage,
            "opportunities_with_full_chain": full_chain_count,
            "opportunities_using_fallback": fallback_count + chain_broken_count,
            "opportunities_chain_broken": chain_broken_count,
            "currently_stuck": sorted(currently_stuck, key=lambda x: x["hours_in_stage"], reverse=True),
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
        task = self._row_to_task(row)
        if not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            if task.assigned_user_id is not None and task.assigned_user_id != actor.user_id:
                return None  # treat as not-found. update_lead/update_opportunity/update_task
                # already treat a None get_* result as not-found -> 404. score_lead,
                # transition_opportunity_stage, complete_task, and generate_cadence_tasks
                # instead raise ValueError("... not found") on a None get_* result, which
                # handle_request's except-chain maps to 400, not 404 -- still a controlled,
                # non-leaking not-found signal, just a different status code per caller.
        return task

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

        effective_uid = self._scoped_assignee_filter(actor, assigned_user_id)
        if effective_uid is not None:
            if actor.has_permission(PERM_READ_TEAM_SALES_DATA):
                query += " AND assigned_user_id = ?"
                params.append(effective_uid)
            else:
                # unclaimed-pool visibility: nothing in this codebase auto-assigns
                # a lead/opportunity/task at creation, so a narrowed actor must
                # still see unclaimed rows or the portal goes empty. Once claimed
                # by someone else, the row disappears from the narrowed actor's
                # view. See NEW-534 for the follow-up gap this leaves (no claim
                # workflow / race protection) -- logged, not fixed here.
                query += " AND (assigned_user_id = ? OR assigned_user_id IS NULL)"
                params.append(effective_uid)

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

        # NEW-533: after-image built from the already-updated in-memory `task`
        # object rather than a re-read via self.get_task(task_id, actor) --
        # see the matching comment in update_lead for why a re-read would
        # break the audit trail specifically for an actor reassigning
        # assigned_user_id away from themselves.
        self.audit.log(
            action="update",
            entity_type="task",
            entity_id=task_id,
            change_summary=f"Updated task {task_id}",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=task.to_dict(),
            ),
        )
        return task

    def claim_task(self, task_id: int, actor: AuthContext) -> Optional[Task]:
        """NEW-534: atomic self-claim of an unclaimed task. Mirrors
        claim_lead exactly -- see its docstring/comments for the full
        rationale (hardcoded self-claim, raw unguarded pre-/post-read,
        None on not-found matching update_task's convention,
        ClaimConflictError on conflict)."""
        if not (
            actor.has_permission(PERM_WRITE_CRM)
            or actor.has_permission(PERM_WRITE_OPPORTUNITIES)
            or actor.has_permission(PERM_WRITE_LEADS)
        ):
            raise PermissionError("Actor lacks permission to update tasks")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?;", (task_id,)).fetchone()
        if row is None:
            return None
        task = self._row_to_task(row)
        _before = task.to_dict()

        now = utc_now_iso()
        with conn:
            cursor = conn.execute(
                "UPDATE tasks SET assigned_user_id = ?, updated_at = ? "
                "WHERE id = ? AND assigned_user_id IS NULL;",
                (actor.user_id, now, task_id),
            )

        if cursor.rowcount == 0:
            conflict_row = conn.execute(
                "SELECT id, assigned_user_id FROM tasks WHERE id = ?;", (task_id,)
            ).fetchone()
            if conflict_row is None:
                return None
            raise ClaimConflictError(f"Task {task_id} already claimed")

        task.assigned_user_id = actor.user_id
        task.updated_at = now

        self.audit.log(
            action="claim",
            entity_type="task",
            entity_id=task_id,
            change_summary=f"Task {task_id} claimed by user {actor.user_id}",
            actor=actor,
            details=build_audit_details(before=_before, after=task.to_dict()),
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
            coverage_amount=row["coverage_amount"] if "coverage_amount" in keys else None,
            supplement_amount=row["supplement_amount"] if "supplement_amount" in keys else None,
            property_id=row["property_id"] if "property_id" in keys else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_project(self, project: Project, actor: AuthContext) -> Project:
        """Create a project. Validates ``project_manager_id``,
        ``property_id`` (B8.4b, NEW-566), and ``assigned_employees`` against
        their referent tables up front (NEW-303) so a bad id raises a clean
        ValueError instead of leaking an uncaught IntegrityError as a 500.
        ``subcontractors`` (List[str]) is NOT validated -- its referent
        table is undecided (NEW-304, open)."""
        if not actor.has_permission(PERM_WRITE_PROJECTS):
            raise PermissionError("Actor lacks permission to create projects")

        conn = self.db.get_connection()
        if project.project_manager_id is not None:
            row = conn.execute("SELECT 1 FROM users WHERE id = ?;", (project.project_manager_id,)).fetchone()
            if not row:
                raise ValueError(f"project_manager_id {project.project_manager_id} does not exist")
        if project.property_id is not None:
            row = conn.execute("SELECT 1 FROM properties WHERE id = ?;", (project.property_id,)).fetchone()
            if not row:
                raise ValueError(f"property_id {project.property_id} does not exist")
        if project.assigned_employees:
            # Type-check BEFORE the existence check's SQL/set() below -- a
            # non-int element (e.g. a dict) would otherwise reach the IN-clause
            # binding or the set() difference and raise a raw sqlite3 error
            # instead of a clean ValueError (same ordering fix as
            # update_project's NEW-308 check).
            if not all(isinstance(x, int) for x in project.assigned_employees):
                raise ValueError("Field 'assigned_employees' elements must be ints")
            placeholders = ",".join("?" * len(project.assigned_employees))
            found = {r["id"] for r in conn.execute(
                f"SELECT id FROM users WHERE id IN ({placeholders});", project.assigned_employees
            ).fetchall()}
            missing = sorted(set(project.assigned_employees) - found)
            if missing:
                raise ValueError(f"assigned_employees contains unknown user id(s): {missing}")

        now = utc_now_iso()
        project.created_at = now
        project.updated_at = now
        assigned_json = json.dumps(project.assigned_employees)
        subcontractors_json = json.dumps(project.subcontractors)

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
                    adjuster_phone, adjuster_email, deductible, coverage_amount,
                    supplement_amount, property_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                    project.coverage_amount,
                    project.supplement_amount,
                    project.property_id,
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

    def _actor_lacks_sold_project_ownership(self, project_id: int, actor: AuthContext) -> bool:
        """True iff `actor` reaches project reads only via
        PERM_READ_OWN_SOLD_PROJECTS (B8.12a) and does NOT own a Contract
        row for `project_id`. Keyed on permission, never `actor.role`
        (`_scoped_assignee_filter`'s documented convention) so a
        custom_permissions_json grant of PERM_READ_OWN_SOLD_PROJECTS to any
        other role is narrowed identically, and so PERM_READ_ALL_PROJECTS/
        PERM_READ_TEAM_SALES_DATA both bypass the filter (the latter is how
        ROLE_SALES_MANAGER keeps full visibility with zero extra grant).
        A Contract row with assigned_user_id IS NULL (unclaimed) does NOT
        match -- fail-closed, deliberately NOT the leads/opportunities
        unclaimed-pool leniency (see PERM_READ_OWN_SOLD_PROJECTS in auth.py).

        Also exempts PERM_READ_ASSIGNED_PROJECTS/PERM_READ_OWN_PROJECTS --
        both are independent entitlements in get_project's own outer gate
        (code-reviewer finding, B8.12a round 1: the first draft only
        exempted PERM_READ_ALL_PROJECTS/PERM_READ_TEAM_SALES_DATA, so a
        hypothetical actor holding PERM_READ_OWN_SOLD_PROJECTS plus one of
        these -- not reachable via any built-in role today, only a future
        custom_permissions_json grant -- would have been narrowed BELOW
        what the weaker permission alone already grants, contradicting
        this method's own "narrowed identically" claim). This mirrors
        operations_service.py's symmetric _actor_reaches_only_via_sold_projects,
        which never had this asymmetry.
        """
        if not actor.has_permission(PERM_READ_OWN_SOLD_PROJECTS):
            return False
        if (
            actor.has_permission(PERM_READ_ALL_PROJECTS)
            or actor.has_permission(PERM_READ_TEAM_SALES_DATA)
            or actor.has_permission(PERM_READ_ASSIGNED_PROJECTS)
            or actor.has_permission(PERM_READ_OWN_PROJECTS)
        ):
            return False
        conn = self.db.get_connection()
        owned = conn.execute(
            "SELECT 1 FROM contracts WHERE project_id = ? AND assigned_user_id = ? LIMIT 1;",
            (project_id, actor.user_id),
        ).fetchone()
        return owned is None

    def get_project(self, project_id: int, actor: AuthContext) -> Optional[Project]:
        if not (
            actor.has_permission(PERM_READ_ALL_PROJECTS)
            or actor.has_permission(PERM_READ_OWN_SOLD_PROJECTS)
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

        # B8.12a: rep-ownership narrowing via Contract.assigned_user_id.
        # Same PermissionError shape as the customer/technician branches
        # above (not get_contract's return-None shape) -- this method's own
        # existing convention for a denied single-record read.
        if self._actor_lacks_sold_project_ownership(project_id, actor):
            raise PermissionError("Actor cannot view a project they did not sell")

        return self._row_to_project(row, actor.role)

    def list_projects(
        self, actor: AuthContext, customer_id: Optional[int] = None, property_id: Optional[int] = None
    ) -> List[Project]:
        if not (
            actor.has_permission(PERM_READ_ALL_PROJECTS)
            or actor.has_permission(PERM_READ_OWN_SOLD_PROJECTS)
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

        if property_id is not None:
            query += " AND property_id = ?"
            params.append(property_id)

        # B8.12a: rep-ownership narrowing, mirrors get_project's single-row
        # check as a subquery so list_projects stays one query instead of
        # N+1. A rep who lacks PERM_READ_ALL_PROJECTS/PERM_READ_TEAM_SALES_DATA
        # but holds PERM_READ_OWN_SOLD_PROJECTS only sees projects with a
        # matching, actually-assigned Contract row -- an unclaimed contract
        # (assigned_user_id IS NULL) can never match this subquery, so it's
        # fail-closed for free, no special-case needed.
        if actor.has_permission(PERM_READ_OWN_SOLD_PROJECTS) and not (
            actor.has_permission(PERM_READ_ALL_PROJECTS) or actor.has_permission(PERM_READ_TEAM_SALES_DATA)
        ):
            query += " AND id IN (SELECT project_id FROM contracts WHERE assigned_user_id = ?)"
            params.append(actor.user_id)

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
        "adjuster_phone", "adjuster_email", "deductible", "coverage_amount",
        "supplement_amount", "property_id",
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
        cannot be nulled (None-value guard) -- omit the key instead. The same
        blanket None-guard applies to every allow-listed field including
        ``property_id`` (B8.4b, NEW-566) -- a project cannot be unlinked from
        its property via this method once linked; omit the key to leave it
        unchanged, there is no supported way to null it here.
        ``assigned_employees`` ids are validated against ``users.id``
        (NEW-303); ``subcontractors`` (List[str]) is not, its referent table
        is undecided (NEW-304, open). Submitted values are also type-checked
        (NEW-308) -- no date-format validation. Read-then-write is not atomic, matching the
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

        # NEW-308 (value-type half only): type-check submitted values BEFORE
        # the NEW-303 existence check below -- this must run first, or a
        # non-int assigned_employees element (e.g. a string or dict) would
        # reach the existence check's SQL IN-clause / set() call and raise a
        # raw sqlite3.InterfaceError/TypeError instead of a clean ValueError,
        # which is exactly the shape NEW-239/NEW-308 exist to eliminate.
        # Date-format validation is deliberately out of scope -- see this
        # method's docstring update.
        _PROJECT_STRING_FIELDS = {
            "title", "property_address", "project_type", "start_date",
            "expected_completion", "actual_completion", "scope_of_work", "notes",
            "warranty_info", "insurance_claim_number", "insurance_carrier",
            "adjuster_name", "adjuster_phone", "adjuster_email",
        }
        _PROJECT_NUMERIC_FIELDS = {
            "estimated_cost", "contract_amount", "actual_cost", "profit",
            "deductible", "coverage_amount", "supplement_amount",
        }

        for key in _PROJECT_STRING_FIELDS & set(updates):
            if not isinstance(updates[key], str):
                raise ValueError(f"Field '{key}' must be a string")
        for key in _PROJECT_NUMERIC_FIELDS & set(updates):
            v = updates[key]
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"Field '{key}' must be a number")
        if "project_manager_id" in updates and not isinstance(updates["project_manager_id"], int):
            raise ValueError("Field 'project_manager_id' must be an int")
        if "property_id" in updates and (
            isinstance(updates["property_id"], bool) or not isinstance(updates["property_id"], int)
        ):
            raise ValueError("Field 'property_id' must be an int")
        if "assigned_employees" in updates and not all(isinstance(x, int) for x in updates["assigned_employees"]):
            raise ValueError("Field 'assigned_employees' elements must be ints")
        if "subcontractors" in updates and not all(isinstance(x, str) for x in updates["subcontractors"]):
            raise ValueError("Field 'subcontractors' elements must be strings")

        # NEW-303: existence checks against users.id. subcontractors (List[str])
        # is out of scope -- its referent table is undecided (NEW-304, open).
        if "assigned_employees" in updates and updates["assigned_employees"]:
            placeholders = ",".join("?" * len(updates["assigned_employees"]))
            found = {r["id"] for r in conn.execute(
                f"SELECT id FROM users WHERE id IN ({placeholders});", updates["assigned_employees"]
            ).fetchall()}
            missing = sorted(set(updates["assigned_employees"]) - found)
            if missing:
                raise ValueError(f"assigned_employees contains unknown user id(s): {missing}")

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
        _after_project = self._row_to_project(_after_row, actor.role) if _after_row else None
        _after = _after_project.to_dict() if _after_project else None
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

        # NEW-306: return the already-fetched/converted post-write row
        # directly instead of a redundant self.get_project() call --
        # _row_to_project(row, actor.role) above already applies the same
        # role-conditional field redaction (e.g. zeroing financial fields
        # for the customer role) that get_project() would, so a
        # write-capable-but-read-refused actor now gets the updated row
        # back instead of a PermissionError from get_project()'s read-gate.
        return _after_project

    # ==========================================
    # ESTIMATES
    # ==========================================

    # Line item bucket categories -- must stay in sync with whatever
    # dispatcher/UI eventually authors line_items. Mirrors
    # OperationsService.create_work_order's `quantity` * `unit_cost` = item
    # total convention (operations_service.py) so both cost-computation
    # paths in this codebase agree on the same line-item shape. An item
    # with no recognized `category` (or none at all) still counts toward
    # `subtotal` but not toward any of the three cost buckets -- e.g. a
    # generic "other" cost line.
    _ESTIMATE_COST_BUCKETS = {
        "materials": "materials_cost",
        "labor": "labor_cost",
        "subcontractor": "subcontractor_cost",
    }

    @classmethod
    def _compute_line_item_costs(cls, line_items: List[Dict[str, Any]]) -> Dict[str, float]:
        """Server-side cost computation from line_items -- NEW-574. Never
        trusts a client-supplied subtotal/materials_cost/labor_cost/
        subcontractor_cost; always derives them from quantity * unit_cost
        per item, bucketed by `category`."""
        totals = {"materials_cost": 0.0, "labor_cost": 0.0, "subcontractor_cost": 0.0, "subtotal": 0.0}
        for item in line_items or []:
            try:
                qty = float(item.get("quantity", 1.0))
                unit_cost = float(item.get("unit_cost", 0.0))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid line_item quantity/unit_cost: {item!r}") from exc
            item_total = round(qty * unit_cost, 2)
            totals["subtotal"] += item_total
            bucket = cls._ESTIMATE_COST_BUCKETS.get(item.get("category"))
            if bucket:
                totals[bucket] += item_total
        totals["subtotal"] = round(totals["subtotal"], 2)
        totals["materials_cost"] = round(totals["materials_cost"], 2)
        totals["labor_cost"] = round(totals["labor_cost"], 2)
        totals["subcontractor_cost"] = round(totals["subcontractor_cost"], 2)
        return totals

    @staticmethod
    def _compute_estimate_total(
        subtotal: float, markup_percent: float, discount_amount: float, tax_amount: float
    ) -> float:
        """total_amount = subtotal + markup (applied to subtotal) -
        discount + tax. markup_percent/discount_amount/tax_amount remain
        client-settable inputs (not derived from line_items); only the
        cost buckets and this resulting total are computed here."""
        markup = subtotal * (float(markup_percent) / 100.0)
        total = subtotal + markup - float(discount_amount or 0.0) + float(tax_amount or 0.0)
        return round(total, 2)

    def _apply_estimate_pricing(self, estimate: Estimate) -> None:
        """Overwrites estimate's computed cost/total fields in place from
        its own line_items/markup_percent/discount_amount/tax_amount --
        the only trusted source. Called by both create_estimate and
        update_estimate so the two paths can never drift."""
        costs = self._compute_line_item_costs(estimate.line_items)
        estimate.subtotal = costs["subtotal"]
        estimate.materials_cost = costs["materials_cost"]
        estimate.labor_cost = costs["labor_cost"]
        estimate.subcontractor_cost = costs["subcontractor_cost"]
        estimate.total_amount = self._compute_estimate_total(
            estimate.subtotal, estimate.markup_percent, estimate.discount_amount, estimate.tax_amount
        )

    def create_estimate(self, estimate: Estimate, actor: AuthContext) -> Estimate:
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to create estimates")

        now = utc_now_iso()
        estimate.created_at = now
        estimate.updated_at = now
        # B8.6a / NEW-548: force server-side ownership, ignoring/overwriting
        # any assigned_user_id a client JSON body set -- routes.py builds
        # `Estimate(**json_body)` directly from client input, so this is the
        # only place that can be trusted. Same fail-open shape NEW-546 was
        # closed for.
        estimate.assigned_user_id = actor.user_id
        # NEW-574: force server-side cost/total computation, ignoring/
        # overwriting any subtotal/materials_cost/labor_cost/
        # subcontractor_cost/total_amount a client JSON body set -- same
        # fail-open shape as the assigned_user_id fix above.
        self._apply_estimate_pricing(estimate)
        line_items_json = json.dumps(estimate.line_items)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO estimates (
                    estimate_number, customer_id, project_id, line_items_json,
                    subtotal, materials_cost, labor_cost, subcontractor_cost,
                    markup_percent, tax_amount, discount_amount, total_amount,
                    status, expiration_date, version, notes, assigned_user_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                    estimate.assigned_user_id,
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
            assigned_user_id=row["assigned_user_id"] if "assigned_user_id" in keys else None,
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

        estimate = self._row_to_estimate(row, actor.role)
        if actor.role != ROLE_CUSTOMER and not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            # B8.6a / NEW-548: rep-ownership narrowing, same not-found (not
            # PermissionError) shape as get_lead/get_opportunity. Deliberately
            # no unclaimed-pool (assigned_user_id IS NULL) carve-out here,
            # unlike leads/opportunities/tasks -- an estimate always has an
            # author at creation (create_estimate forces assigned_user_id
            # server-side), so there's no "unclaimed estimate" concept to
            # preserve visibility for. A pre-B8.6a migrated row (NULL
            # assigned_user_id) is therefore correctly invisible to a
            # narrowed actor, not a gap to "fix" with an IS NULL clause.
            if estimate.assigned_user_id != actor.user_id:
                return None
        return estimate

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

        # B8.6a / NEW-548: rep-ownership narrowing via PERM_READ_TEAM_SALES_DATA
        # (same mechanism as list_leads/list_opportunities/list_tasks), not
        # PERM_READ_OWN_ESTIMATES -- that permission is ROLE_CUSTOMER-only
        # "own record" access and is a different thing, already handled by
        # the customer_id scoping above. Deliberately NO unclaimed-pool
        # (assigned_user_id IS NULL) clause -- see get_estimate's comment.
        if actor.role != ROLE_CUSTOMER:
            effective_uid = self._scoped_assignee_filter(actor, None)
            if effective_uid is not None:
                query += " AND assigned_user_id = ?"
                params.append(effective_uid)

        query += " ORDER BY id DESC;"
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_estimate(r, actor.role) for r in rows]

    # Fields updatable via update_estimate. Deliberately excludes
    # customer_id/project_id/assigned_user_id/status/version (status has
    # its own transition method below; the other three are out of this
    # round's scope) and every server-computed cost field (subtotal,
    # materials_cost, labor_cost, subcontractor_cost, total_amount --
    # NEW-574, see _apply_estimate_pricing).
    ALLOWED_ESTIMATE_UPDATE_FIELDS = {
        "line_items", "markup_percent", "tax_amount", "discount_amount",
        "expiration_date", "notes",
    }

    # Any change to one of these fields forces a server-side pricing
    # recompute (see _apply_estimate_pricing) -- they're the only inputs
    # that feed the computed cost/total fields.
    _ESTIMATE_PRICING_INPUT_FIELDS = {"line_items", "markup_percent", "tax_amount", "discount_amount"}

    def update_estimate(
        self, estimate_id: int, updates: Dict[str, Any], actor: AuthContext
    ) -> Optional[Estimate]:
        """Partial update for an estimate, allow-list enforced (see
        ALLOWED_ESTIMATE_UPDATE_FIELDS). NEW-574: any client-supplied
        subtotal/materials_cost/labor_cost/subcontractor_cost/
        total_amount is rejected outright (not silently overwritten --
        those keys aren't in the allow-list at all) and the real computed
        values are always re-derived server-side from line_items/
        markup_percent/discount_amount/tax_amount whenever any of those
        four inputs changes."""
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to update estimates")

        unknown = set(updates) - self.ALLOWED_ESTIMATE_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unknown field(s) for estimate update: {sorted(unknown)}")

        for key, value in updates.items():
            if value is None:
                raise ValueError(
                    f"Field '{key}' cannot be set to None via update_estimate; omit the key instead"
                )

        if not updates:
            return self.get_estimate(estimate_id, actor)

        conn = self.db.get_connection()
        # RAW row read -- never self._row_to_estimate(row, actor.role),
        # which zeroes cost fields for the customer role (mirrors
        # update_project's identical rationale, crm_service.py NEW-306).
        row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        if not row:
            return None

        # Customer-isolation gate -- same shape as get_estimate. A
        # ROLE_CUSTOMER actor granted write:estimates via custom_permissions
        # (the catalog check in _validate_custom_permissions doesn't enforce
        # role-compatibility) must still be confined to their own customer_id;
        # without this, only the rep-ownership branch below ran, and that
        # branch is skipped entirely for ROLE_CUSTOMER.
        if actor.role == ROLE_CUSTOMER and (not actor.customer_id or actor.customer_id != row["customer_id"]):
            raise PermissionError("Customer cannot access another customer's estimate")

        # B8.6a / NEW-548: same rep-ownership narrowing as get_estimate --
        # a narrowed actor (no PERM_READ_TEAM_SALES_DATA) may only update
        # their own estimate.
        if actor.role != ROLE_CUSTOMER and not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            if row["assigned_user_id"] != actor.user_id:
                return None

        estimate = self._row_to_estimate(row)
        _before = estimate.to_dict()

        for key, value in updates.items():
            setattr(estimate, key, value)

        if self._ESTIMATE_PRICING_INPUT_FIELDS & set(updates):
            self._apply_estimate_pricing(estimate)

        now = utc_now_iso()
        estimate.updated_at = now
        line_items_json = json.dumps(estimate.line_items)

        with conn:
            conn.execute(
                """
                UPDATE estimates SET
                    line_items_json = ?, subtotal = ?, materials_cost = ?,
                    labor_cost = ?, subcontractor_cost = ?, markup_percent = ?,
                    tax_amount = ?, discount_amount = ?, total_amount = ?,
                    expiration_date = ?, notes = ?, updated_at = ?
                WHERE id = ?;
                """,
                (
                    line_items_json,
                    estimate.subtotal,
                    estimate.materials_cost,
                    estimate.labor_cost,
                    estimate.subcontractor_cost,
                    estimate.markup_percent,
                    estimate.tax_amount,
                    estimate.discount_amount,
                    estimate.total_amount,
                    estimate.expiration_date,
                    estimate.notes,
                    now,
                    estimate_id,
                ),
            )

        self.audit.log(
            action="update",
            entity_type="estimate",
            entity_id=estimate_id,
            change_summary=f"Updated estimate #{estimate.estimate_number} (${estimate.total_amount:.2f})",
            actor=actor,
            details=build_audit_details(before=_before, after=estimate.to_dict()),
        )
        # Redact cost fields for the response per actor.role (get_estimate's
        # redaction shape) -- re-read post-update so both the empty-updates
        # early-return path above and this path return the same masked
        # shape for ROLE_CUSTOMER/ROLE_TECHNICIAN.
        updated_row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        return self._row_to_estimate(updated_row, actor.role)

    def send_estimate(self, estimate_id: int, actor: AuthContext) -> Optional[Estimate]:
        """Transition an estimate from draft to sent (NEW-574 / B8.6b).
        Mirrors transition_opportunity_stage's audit-logging shape.
        Deliberately minimal: only draft -> sent is wired this round --
        approved/rejected/expired are legal CHECK values but have no
        transition method yet (left for B8.6c per the scoping brief).
        Idempotent-refusal, not a silent no-op: re-sending an
        already-sent (or approved/rejected/expired) estimate raises
        ValueError rather than silently succeeding, so a caller can't
        mistake a rejected retry for a real state change."""
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to send estimates")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        if not row:
            return None

        # Customer-isolation gate -- see update_estimate for the same
        # rationale (a ROLE_CUSTOMER actor granted write:estimates via
        # custom_permissions must still be confined to their own customer_id).
        if actor.role == ROLE_CUSTOMER and (not actor.customer_id or actor.customer_id != row["customer_id"]):
            raise PermissionError("Customer cannot access another customer's estimate")

        if actor.role != ROLE_CUSTOMER and not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            if row["assigned_user_id"] != actor.user_id:
                return None

        estimate = self._row_to_estimate(row)
        if estimate.status != "draft":
            raise ValueError(
                f"Cannot send estimate {estimate_id}: status is '{estimate.status}', not 'draft'"
            )

        _before = estimate.to_dict()
        old_status = estimate.status
        estimate.status = "sent"
        now = utc_now_iso()
        estimate.updated_at = now

        with conn:
            conn.execute(
                "UPDATE estimates SET status = ?, updated_at = ? WHERE id = ?;",
                (estimate.status, now, estimate_id),
            )

        self.audit.log(
            action="stage_transition",
            entity_type="estimate",
            entity_id=estimate_id,
            change_summary=f"Transitioned estimate #{estimate.estimate_number} ({estimate_id}) from '{old_status}' to '{estimate.status}'",
            actor=actor,
            details=build_audit_details(before=_before, after=estimate.to_dict()),
        )
        # Redact cost fields for the response per actor.role -- see
        # update_estimate's identical re-read-and-mask rationale.
        updated_row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        return self._row_to_estimate(updated_row, actor.role)

    # ==========================================
    # PACKAGE OPTIONS
    # ==========================================

    @staticmethod
    def _row_to_package_option(row: Any, actor_role: str = "") -> PackageOption:
        """actor_role redaction mirrors _row_to_estimate: ROLE_CUSTOMER/
        ROLE_TECHNICIAN never see internal margin/gross_profit -- price
        (the customer-facing sell number) is always shown."""
        keys = row.keys() if hasattr(row, "keys") else []
        included_items = json.loads(row["included_items_json"]) if "included_items_json" in keys and row["included_items_json"] else []
        is_customer = actor_role in (ROLE_CUSTOMER, ROLE_TECHNICIAN)
        return PackageOption(
            id=row["id"],
            estimate_id=row["estimate_id"] if "estimate_id" in keys else None,
            tier=row["tier"],
            price=float(row["price"]),
            gross_profit=float(row["gross_profit"]) if row["gross_profit"] is not None and not is_customer else None,
            margin=float(row["margin"]) if row["margin"] is not None and not is_customer else None,
            included_items=included_items if not is_customer else [],
            created_at=row["created_at"],
        )

    def create_package_option(self, package_option: PackageOption, actor: AuthContext) -> PackageOption:
        """A package option is scoped to its estimate -- inherits
        estimate's write access model (PERM_WRITE_ESTIMATES), not a new
        permission. price/gross_profit/margin are always computed here
        from included_items, reusing the exact same quantity * unit_cost
        item-total convention as _compute_line_item_costs, plus the same
        gross_profit/margin formula FinanceService.get_project_pnl already
        established (gross_profit = revenue - cost, margin = gross_profit
        / revenue * 100) -- never trusted from the client. included_items
        entries additionally carry `unit_price` (the sell price per unit,
        as opposed to `unit_cost`); price is qty * unit_price summed,
        cost is qty * unit_cost summed."""
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to create package options")

        if package_option.tier not in ("good", "better", "best"):
            raise ValueError(f"Invalid package tier: '{package_option.tier}'")

        # A package option is always estimate-scoped -- a NULL estimate_id
        # would skip the ownership check below AND be invisible to
        # list_package_options' unfiltered (INNER JOIN) path, i.e. an
        # orphan row with no access control. Reject it outright.
        if package_option.estimate_id is None:
            raise ValueError("Package option must reference an estimate_id")
        estimate = self.get_estimate(package_option.estimate_id, actor)
        if not estimate:
            raise ValueError(f"Estimate {package_option.estimate_id} not found")

        cost_total = 0.0
        price_total = 0.0
        for item in package_option.included_items or []:
            try:
                qty = float(item.get("quantity", 1.0))
                unit_cost = float(item.get("unit_cost", 0.0))
                unit_price = float(item.get("unit_price", 0.0))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid included_item quantity/unit_cost/unit_price: {item!r}") from exc
            cost_total += round(qty * unit_cost, 2)
            price_total += round(qty * unit_price, 2)
        price_total = round(price_total, 2)
        cost_total = round(cost_total, 2)
        gross_profit = round(price_total - cost_total, 2)
        margin = round((gross_profit / price_total * 100.0), 2) if price_total > 0 else 0.0

        package_option.price = price_total
        package_option.gross_profit = gross_profit
        package_option.margin = margin
        package_option.created_at = utc_now_iso()
        included_items_json = json.dumps(package_option.included_items)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO package_options (
                    estimate_id, tier, price, gross_profit, margin,
                    included_items_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    package_option.estimate_id,
                    package_option.tier,
                    package_option.price,
                    package_option.gross_profit,
                    package_option.margin,
                    included_items_json,
                    package_option.created_at,
                ),
            )
            package_option.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="package_option",
            entity_id=package_option.id,
            change_summary=f"Created '{package_option.tier}' package option for estimate {package_option.estimate_id} (${package_option.price:.2f})",
            actor=actor,
            details=build_audit_details(after=package_option.to_dict()),
        )
        return package_option

    def list_package_options(
        self, actor: AuthContext, estimate_id: Optional[int] = None
    ) -> List[PackageOption]:
        if not (actor.has_permission(PERM_READ_ESTIMATES) or actor.has_permission(PERM_READ_OWN_ESTIMATES)):
            raise PermissionError("Actor lacks permission to read package options")

        # A package option inherits its estimate's access model -- if the
        # caller can't see the estimate (rep-ownership narrowing / customer
        # scoping / not-found), they can't see its package options either.
        if estimate_id is not None:
            estimate = self.get_estimate(estimate_id, actor)
            if not estimate:
                return []

        conn = self.db.get_connection()
        if estimate_id is not None:
            rows = conn.execute(
                "SELECT * FROM package_options WHERE estimate_id = ? ORDER BY id DESC;",
                (estimate_id,),
            ).fetchall()
            return [self._row_to_package_option(r, actor.role) for r in rows]

        # No estimate_id filter: same rep-ownership narrowing as
        # list_estimates (join to estimates so an unfiltered call can't
        # leak another rep's package options).
        query = "SELECT po.* FROM package_options po JOIN estimates e ON po.estimate_id = e.id WHERE 1=1"
        params: List[Any] = []
        if actor.role == ROLE_CUSTOMER:
            query += " AND e.customer_id = ?"
            params.append(actor.customer_id)
        elif not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            effective_uid = self._scoped_assignee_filter(actor, None)
            if effective_uid is not None:
                query += " AND e.assigned_user_id = ?"
                params.append(effective_uid)
        query += " ORDER BY po.id DESC;"
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_package_option(r, actor.role) for r in rows]

    # ==========================================
    # CONTRACTS / PROPOSALS
    # ==========================================

    def create_contract(self, contract: Contract, actor: AuthContext) -> Contract:
        if not actor.has_permission(PERM_WRITE_CONTRACTS):
            raise PermissionError("Actor lacks permission to create contracts")

        # B8.6d-c: template_name, when given, must be one of the fixed
        # legal values (CONTRACT_TEMPLATE_NAMES in models.py) -- None is
        # still allowed (unset/legacy contracts).
        if contract.template_name is not None and contract.template_name not in CONTRACT_TEMPLATE_NAMES:
            raise ValueError(
                f"Unknown contract template_name '{contract.template_name}'; "
                f"must be one of {CONTRACT_TEMPLATE_NAMES} or omitted"
            )

        now = utc_now_iso()
        contract.created_at = now
        contract.updated_at = now
        # B8.6a / NEW-548: force server-side ownership, ignoring/overwriting
        # any assigned_user_id a client JSON body set -- routes.py builds
        # `Contract(**json_body)` directly from client input, so this is the
        # only place that can be trusted. Same fail-open shape NEW-546 was
        # closed for.
        contract.assigned_user_id = actor.user_id

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO contracts (
                    contract_number, customer_id, project_id, estimate_id,
                    title, template_name, content, status, version,
                    assigned_user_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                    contract.assigned_user_id,
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
            assigned_user_id=row["assigned_user_id"] if "assigned_user_id" in keys else None,
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

        contract = self._row_to_contract(row)
        if actor.role != ROLE_CUSTOMER and not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            # B8.6a / NEW-548: rep-ownership narrowing, same not-found (not
            # PermissionError) shape as get_lead/get_opportunity. See
            # get_estimate's comment for why there's deliberately no
            # unclaimed-pool (assigned_user_id IS NULL) carve-out.
            if contract.assigned_user_id != actor.user_id:
                return None
        return contract

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

        # B8.6a / NEW-548: rep-ownership narrowing via PERM_READ_TEAM_SALES_DATA
        # (same mechanism as list_leads/list_opportunities/list_tasks), not
        # PERM_READ_OWN_CONTRACTS -- that permission is ROLE_CUSTOMER-only
        # "own record" access and is a different thing, already handled by
        # the customer_id scoping above. Deliberately NO unclaimed-pool
        # (assigned_user_id IS NULL) clause -- see get_contract's comment.
        if actor.role != ROLE_CUSTOMER:
            effective_uid = self._scoped_assignee_filter(actor, None)
            if effective_uid is not None:
                query += " AND assigned_user_id = ?"
                params.append(effective_uid)

        query += " ORDER BY id DESC;"
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_contract(r) for r in rows]

    # Fields updatable via update_contract. Deliberately excludes
    # customer_id/project_id/estimate_id/assigned_user_id/status (status
    # has its own transition methods -- send_contract below, sign_contract
    # further down) and the signature fields customer_signed_at/
    # customer_signature_data (only sign_contract may set those). Mirrors
    # ALLOWED_ESTIMATE_UPDATE_FIELDS' exclusion logic (B8.6b).
    ALLOWED_CONTRACT_UPDATE_FIELDS = {"title", "template_name", "content"}

    def update_contract(
        self, contract_id: int, updates: Dict[str, Any], actor: AuthContext
    ) -> Optional[Contract]:
        """Partial update for a contract, allow-list enforced (see
        ALLOWED_CONTRACT_UPDATE_FIELDS). Mirrors update_estimate's shape
        exactly (B8.6c)."""
        if not actor.has_permission(PERM_WRITE_CONTRACTS):
            raise PermissionError("Actor lacks permission to update contracts")

        unknown = set(updates) - self.ALLOWED_CONTRACT_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unknown field(s) for contract update: {sorted(unknown)}")

        for key, value in updates.items():
            if value is None:
                raise ValueError(
                    f"Field '{key}' cannot be set to None via update_contract; omit the key instead"
                )

        # B8.6d-c: same fixed-legal-value check as create_contract.
        if "template_name" in updates and updates["template_name"] not in CONTRACT_TEMPLATE_NAMES:
            raise ValueError(
                f"Unknown contract template_name '{updates['template_name']}'; "
                f"must be one of {CONTRACT_TEMPLATE_NAMES}"
            )

        if not updates:
            return self.get_contract(contract_id, actor)

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM contracts WHERE id = ?;", (contract_id,)).fetchone()
        if not row:
            return None

        # Customer-isolation gate -- same shape as update_estimate/
        # get_contract. A ROLE_CUSTOMER actor granted write:contracts via
        # custom_permissions must still be confined to their own
        # customer_id; without this, only the rep-ownership branch below
        # ran, and that branch is skipped entirely for ROLE_CUSTOMER.
        if actor.role == ROLE_CUSTOMER and (not actor.customer_id or actor.customer_id != row["customer_id"]):
            raise PermissionError("Customer cannot access another customer's contract")

        # B8.6a / NEW-548: same rep-ownership narrowing as get_contract --
        # a narrowed actor (no PERM_READ_TEAM_SALES_DATA) may only update
        # their own contract.
        if actor.role != ROLE_CUSTOMER and not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            if row["assigned_user_id"] != actor.user_id:
                return None

        contract = self._row_to_contract(row)
        _before = contract.to_dict()

        for key, value in updates.items():
            setattr(contract, key, value)

        now = utc_now_iso()
        contract.updated_at = now

        with conn:
            conn.execute(
                """
                UPDATE contracts SET
                    title = ?, template_name = ?, content = ?, updated_at = ?
                WHERE id = ?;
                """,
                (
                    contract.title,
                    contract.template_name,
                    contract.content,
                    now,
                    contract_id,
                ),
            )

        self.audit.log(
            action="update",
            entity_type="contract",
            entity_id=contract_id,
            change_summary=f"Updated contract #{contract.contract_number} '{contract.title}'",
            actor=actor,
            details=build_audit_details(before=_before, after=contract.to_dict(), fields=_AUDITABLE_CONTRACT_FIELDS),
        )
        updated_row = conn.execute("SELECT * FROM contracts WHERE id = ?;", (contract_id,)).fetchone()
        return self._row_to_contract(updated_row)

    def send_contract(self, contract_id: int, actor: AuthContext) -> Optional[Contract]:
        """Transition a contract from draft to sent (B8.6c). Mirrors
        send_estimate's shape exactly, including its idempotent-refusal
        design (rejecting a re-send with ValueError rather than silently
        no-opping) and its audit-logging shape."""
        if not actor.has_permission(PERM_WRITE_CONTRACTS):
            raise PermissionError("Actor lacks permission to send contracts")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM contracts WHERE id = ?;", (contract_id,)).fetchone()
        if not row:
            return None

        # Customer-isolation gate -- see update_contract for the same
        # rationale (a ROLE_CUSTOMER actor granted write:contracts via
        # custom_permissions must still be confined to their own customer_id).
        if actor.role == ROLE_CUSTOMER and (not actor.customer_id or actor.customer_id != row["customer_id"]):
            raise PermissionError("Customer cannot access another customer's contract")

        if actor.role != ROLE_CUSTOMER and not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            if row["assigned_user_id"] != actor.user_id:
                return None

        contract = self._row_to_contract(row)
        if contract.status != "draft":
            raise ValueError(
                f"Cannot send contract {contract_id}: status is '{contract.status}', not 'draft'"
            )

        _before = contract.to_dict()
        old_status = contract.status
        contract.status = "sent"
        now = utc_now_iso()
        contract.updated_at = now

        with conn:
            conn.execute(
                "UPDATE contracts SET status = ?, updated_at = ? WHERE id = ?;",
                (contract.status, now, contract_id),
            )

        self.audit.log(
            action="stage_transition",
            entity_type="contract",
            entity_id=contract_id,
            change_summary=f"Transitioned contract #{contract.contract_number} ({contract_id}) from '{old_status}' to '{contract.status}'",
            actor=actor,
            details=build_audit_details(before=_before, after=contract.to_dict(), fields=_AUDITABLE_CONTRACT_FIELDS),
        )
        updated_row = conn.execute("SELECT * FROM contracts WHERE id = ?;", (contract_id,)).fetchone()
        return self._row_to_contract(updated_row)

    # B8.6d-b: actor.role -> ContractSigner.party_role, used only to derive
    # which row a caller is signing when sign_contract's `party_role` kwarg
    # is omitted on a multi-party contract (see sign_contract below).
    # Deliberately narrow/explicit rather than a fallback default -- an
    # unmapped role (or a role mapped to more than one unsigned row) must
    # force the caller to pass party_role explicitly, not silently guess.
    _ROLE_TO_PARTY_ROLE = {
        ROLE_CUSTOMER: "customer",
        ROLE_SALES: "rep",
        ROLE_SALES_MANAGER: "rep",
        ROLE_PROJECT_MANAGER: "project_manager",
        ROLE_ADMIN: "admin",
        ROLE_MANAGER: "admin",
    }

    def add_contract_signers(
        self,
        contract_id: int,
        signers: List[Dict[str, Any]],
        actor: AuthContext,
    ) -> List[ContractSigner]:
        """Opt a contract into multi-party signing (B8.6d-b) by creating one
        unsigned ContractSigner row per entry in `signers` (each a dict with
        at least `party_role`, optionally `signer_name`/`anchor_label`).

        A contract with zero ContractSigner rows uses sign_contract's
        original single-signer path (Contract.customer_signed_at/
        customer_signature_data) unchanged -- this method is what a caller
        uses to opt in to the multi-party path instead. Same
        PERM_WRITE_CONTRACTS + rep-ownership gate as create_contract/
        update_contract, since this is contract configuration, not signing
        itself (that stays gated by PERM_SIGN_CONTRACTS in sign_contract).

        NEW-597 (B8.6d-c): calling this twice with the same party_role for
        one contract used to create a second unsigned row, permanently
        breaking role-derived signing for that party. Each INSERT below is
        a single INSERT...SELECT...WHERE NOT EXISTS statement -- same
        atomicity reasoning as create_customer's customer_number generation
        -- rather than a separate existence check followed by a plain
        INSERT, so two concurrent calls (or two duplicate entries within
        one `signers` list) can't both pass a pre-check and both insert. A
        skipped duplicate is silent (no row created, not returned in
        `created`) rather than an error -- this method is meant to be
        safely re-callable to converge a contract's signer set, not to
        reject a caller who re-sends a spec it already applied. This is
        the load-bearing guard (see the contract_signers table's UNIQUE
        comment in database.py for why the DB-level constraint alone isn't
        enough for a DB file created before it existed).
        """
        if not actor.has_permission(PERM_WRITE_CONTRACTS):
            raise PermissionError("Actor lacks permission to configure contract signers")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM contracts WHERE id = ?;", (contract_id,)).fetchone()
        if not row:
            raise ValueError(f"Contract {contract_id} not found")

        if not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            # Same NEW-573/575 ownership narrowing sign_contract applies:
            # a rep without team-wide visibility may only configure signers
            # on a contract they own.
            contract_owner = row["assigned_user_id"] if "assigned_user_id" in row.keys() else None
            if contract_owner != actor.user_id:
                raise PermissionError("Actor cannot configure signers on a contract assigned to another user")

        if row["status"] == "signed":
            raise ValueError(f"Contract {contract_id} is already signed")

        now = utc_now_iso()
        created: List[ContractSigner] = []
        with conn:
            for spec in signers:
                party_role = spec.get("party_role")
                if not party_role:
                    raise ValueError("Each signer must have a party_role")
                cursor = conn.execute(
                    """
                    INSERT INTO contract_signers (
                        contract_id, party_role, signer_name, anchor_label,
                        signature_data, signed_at, created_at
                    )
                    SELECT ?, ?, ?, ?, NULL, NULL, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM contract_signers
                        WHERE contract_id = ? AND party_role = ?
                    );
                    """,
                    (
                        contract_id,
                        party_role,
                        spec.get("signer_name"),
                        spec.get("anchor_label"),
                        now,
                        contract_id,
                        party_role,
                    ),
                )
                if cursor.rowcount == 0:
                    # NEW-597: party_role already configured for this
                    # contract (either from an earlier call or an earlier
                    # entry in this same `signers` list) -- skip rather
                    # than create a second unsigned row for it.
                    continue
                created.append(
                    ContractSigner(
                        id=cursor.lastrowid,
                        contract_id=contract_id,
                        party_role=party_role,
                        signer_name=spec.get("signer_name"),
                        anchor_label=spec.get("anchor_label"),
                        signature_data=None,
                        signed_at=None,
                        created_at=now,
                    )
                )

        self.audit.log(
            action="update",
            entity_type="contract",
            entity_id=contract_id,
            change_summary=f"Configured {len(created)} required signer(s) for contract #{row['contract_number']}",
            actor=actor,
            details=build_audit_details(after={"required_signers": [c.party_role for c in created]}),
        )
        return created

    def _resolve_contract_signer_row(
        self,
        signer_rows: List[Any],
        actor: AuthContext,
        party_role: Optional[str],
    ) -> Any:
        """Pick the single ContractSigner row `actor` is signing on a
        multi-party contract. Never silently guesses across an ambiguous
        match -- either the caller says which party_role they're signing
        as, or exactly one unsigned row must derive unambiguously from
        actor.role (_ROLE_TO_PARTY_ROLE above)."""
        if party_role:
            matches = [r for r in signer_rows if r["party_role"] == party_role]
            if not matches:
                raise ValueError(f"No signer of role '{party_role}' found on this contract")
            unsigned_matches = [r for r in matches if not r["signed_at"]]
            # Prefer an unsigned row for this role so signing proceeds
            # normally; if none is unsigned, return the first match so the
            # idempotency check above raises "already signed" rather than
            # this method silently picking among already-signed rows.
            return unsigned_matches[0] if unsigned_matches else matches[0]

        derived_role = self._ROLE_TO_PARTY_ROLE.get(actor.role)
        candidates = [r for r in signer_rows if r["party_role"] == derived_role] if derived_role else []
        unsigned_candidates = [r for r in candidates if not r["signed_at"]]
        if len(unsigned_candidates) == 1:
            return unsigned_candidates[0]
        if len(candidates) == 1:
            # Exactly one row for this role, already signed -- return it so
            # the caller gets the "already signed" ValueError below rather
            # than this ambiguity error.
            return candidates[0]
        raise ValueError(
            "Cannot determine which signer role this actor is signing as; "
            "pass party_role explicitly"
        )

    def sign_contract(
        self,
        contract_id: int,
        signature_data: str,
        actor: AuthContext,
        party_role: Optional[str] = None,
    ) -> Contract:
        """Sign a contract (customer digital signature or admin/manager approval).

        `party_role` (B8.6d-b) is only meaningful for a contract that has
        been opted into multi-party signing via add_contract_signers; it is
        ignored (and may be omitted, as every existing caller does) for the
        common single-signer contract, which signs exactly as before this
        round -- see the `contract_signers` row-count branch below.
        """
        if not actor.has_permission(PERM_SIGN_CONTRACTS):
            raise PermissionError("Actor lacks permission to sign contracts")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM contracts WHERE id = ?;", (contract_id,)).fetchone()
        if not row:
            raise ValueError(f"Contract {contract_id} not found")

        _before = self._row_to_contract(row).to_dict()

        # Authorization (customer isolation / rep-ownership narrowing) is
        # checked BEFORE the idempotency guard below, deliberately: an actor
        # who isn't allowed to touch this contract at all must get the same
        # PermissionError/not-found signal regardless of the contract's
        # current status, not a 400 "already signed" that leaks the
        # contract's state to someone unauthorized to act on it (e.g. a
        # different customer re-attempting a sign on an already-signed
        # contract must still see a permission/not-found failure, not an
        # idempotency one -- see test_customer_portal_isolation_and_masking).
        #
        # Customer isolation
        if actor.role == ROLE_CUSTOMER:
            if not actor.customer_id or actor.customer_id != row["customer_id"]:
                raise PermissionError("Customer cannot sign another customer's contract")
        elif not (
            actor.has_permission(PERM_READ_TEAM_SALES_DATA)
            or not actor.has_permission(PERM_WRITE_CONTRACTS)
        ):
            # NEW-573: rep-ownership narrowing, same gate as get_contract --
            # a rep without team-wide visibility must not be able to sign a
            # contract assigned to a different rep just by knowing its id,
            # bypassing whatever narrowing get_contract applies.
            #
            # NEW-575: an actor that lacks PERM_WRITE_CONTRACTS (and so can
            # never be the assigned owner of a contract in the first place,
            # e.g. ROLE_PROJECT_MANAGER) is exempted from this ownership
            # narrowing entirely -- otherwise it could never sign any
            # contract at all, silently breaking the PERM_SIGN_CONTRACTS
            # grant from NEW-192. Actors that DO hold PERM_WRITE_CONTRACTS
            # (e.g. ROLE_SALES) are unaffected: this only widens who is
            # exempt, it does not narrow ROLE_SALES's existing ownership
            # check.
            contract_owner = row["assigned_user_id"] if "assigned_user_id" in row.keys() else None
            if contract_owner != actor.user_id:
                raise PermissionError("Actor cannot sign a contract assigned to another user")

        # NEW-573: idempotency guard. Reject signing a contract that's
        # already signed instead of silently overwriting
        # customer_signed_at/customer_signature_data on every call -- an
        # unconditional re-sign here would let this fire indefinitely, and
        # B8.7 (commission engine, future work) needs one clean
        # CONTRACT_SIGNED transition to hook off of, not a re-signable one
        # that could double-fire or misfire it.
        if row["status"] == "signed":
            raise ValueError(f"Contract {contract_id} is already signed")

        # B8.6d-b: multi-party branch. A contract with zero contract_signers
        # rows takes the exact original single-signer path below (the
        # `if not signer_rows` branch), byte-for-byte unchanged from
        # B8.6d-a/NEW-573/575 -- every existing caller (routes.py staff +
        # portal sign endpoints, all pre-B8.6d-b tests) hits this path and
        # must see identical behavior. This lookup runs AFTER the status
        # idempotency guard above on purpose: once a multi-party contract's
        # last required signer completes, status flips to 'signed' and any
        # further sign_contract call (any party) hits that guard first,
        # same "already signed" signal a single-signer contract gives.
        signer_rows = conn.execute(
            "SELECT * FROM contract_signers WHERE contract_id = ? ORDER BY id;",
            (contract_id,),
        ).fetchall()

        now = utc_now_iso()
        multi_party_status_note = ""
        signed_contract_signers: Optional[List[ContractSigner]] = None
        # NEW-595: populated only on the multi-party branch below, so the
        # audit entry for a partial (1-of-N) sign can record specifically
        # WHICH party signed, not just that "a signature happened."
        signed_party_details: Optional[Dict[str, Any]] = None

        if not signer_rows:
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
                assigned_user_id=row["assigned_user_id"] if "assigned_user_id" in row.keys() else None,
                created_at=row["created_at"],
                updated_at=now,
            )
        else:
            # NEW-573/575 idempotency for THIS specific party: "already
            # signed" for the resolved signer row is the same ValueError
            # shape as the single-signer guard above, not a silent no-op.
            # NEW-593 (B8.6d-c): when a caller supplies party_role
            # explicitly, verify the actor's role can plausibly claim that
            # party -- reusing _ROLE_TO_PARTY_ROLE (above) as the single
            # source of truth for valid role->party_role pairs, not a
            # second mapping. Only enforced when party_role is given: the
            # omitted-party_role path (every pre-B8.6d-c caller) already
            # fails closed via _resolve_contract_signer_row's own
            # ambiguous-match handling, so this doesn't change that
            # behavior. An unmapped actor.role (.get() returns None) can
            # never equal a real party_role string, so it's rejected here
            # too -- fail-closed, not a silent pass-through.
            if party_role is not None and self._ROLE_TO_PARTY_ROLE.get(actor.role) != party_role:
                raise PermissionError(
                    f"Actor role '{actor.role}' may not sign contract {contract_id} as party_role '{party_role}'"
                )

            target = self._resolve_contract_signer_row(signer_rows, actor, party_role)
            if target["signed_at"]:
                raise ValueError(
                    f"{target['party_role']} has already signed contract {contract_id}"
                )

            # NEW-593 (code-reviewer, B8.6d-b round 1): the signer-row
            # UPDATE and the conditional contracts.status UPDATE must
            # commit atomically as one transaction when this signature is
            # the last one required -- otherwise a process death between
            # two separate `with conn:` commits can leave every
            # contract_signers row signed while contracts.status is stuck
            # at its pre-signing value forever, with no recovery path
            # through sign_contract (idempotency guard) or
            # update_contract (status is not in its allow-list). Order
            # matters here: update first, then COUNT inside the same
            # block -- sqlite3's deferred transaction takes the write
            # lock at the first UPDATE, so the COUNT below is protected
            # from a concurrent signer's UPDATE interleaving between a
            # pre-update count and this one (which a "count remaining
            # BEFORE updating, excluding this row" restructuring would
            # not be: two parties signing concurrently could each read
            # "one other still pending" and neither would flip status).
            with conn:
                conn.execute(
                    "UPDATE contract_signers SET signature_data = ?, signed_at = ? WHERE id = ?;",
                    (signature_data, now, target["id"]),
                )
                remaining = conn.execute(
                    "SELECT COUNT(*) AS c FROM contract_signers WHERE contract_id = ? AND signed_at IS NULL;",
                    (contract_id,),
                ).fetchone()["c"]
                all_signed = remaining == 0
                if all_signed:
                    conn.execute(
                        "UPDATE contracts SET status = 'signed', updated_at = ? WHERE id = ?;",
                        (now, contract_id),
                    )

            new_status = row["status"]
            if all_signed:
                new_status = "signed"
                multi_party_status_note = "; all required signers complete"
            else:
                multi_party_status_note = f"; {remaining} signer(s) still pending"

            _signed = Contract(
                id=row["id"],
                contract_number=row["contract_number"],
                customer_id=row["customer_id"],
                project_id=row["project_id"],
                estimate_id=row["estimate_id"],
                title=row["title"],
                template_name=row["template_name"],
                content=row["content"],
                status=new_status,
                customer_signed_at=row["customer_signed_at"] if "customer_signed_at" in row.keys() else None,
                customer_signature_data=row["customer_signature_data"] if "customer_signature_data" in row.keys() else None,
                version=row["version"],
                assigned_user_id=row["assigned_user_id"] if "assigned_user_id" in row.keys() else None,
                created_at=row["created_at"],
                updated_at=now if all_signed else row["updated_at"],
            )

            signed_contract_signers = [
                ContractSigner(
                    id=r["id"],
                    contract_id=r["contract_id"],
                    party_role=r["party_role"],
                    signer_name=r["signer_name"],
                    anchor_label=r["anchor_label"],
                    signature_data=r["signature_data"] if r["id"] != target["id"] else signature_data,
                    signed_at=r["signed_at"] if r["id"] != target["id"] else now,
                    created_at=r["created_at"],
                )
                for r in signer_rows
            ]

            # NEW-595: the specific party/signer identity for this
            # signature, so a partial sign's audit entry answers "who
            # specifically signed" rather than only "a signature
            # happened." `target` is the contract_signers row this call
            # just updated.
            signed_party_details = {
                "party_role": target["party_role"],
                "signer_name": target["signer_name"],
            }

        side_effects: Dict[str, Any] = {"signature_captured": True}
        if signed_party_details is not None:
            side_effects.update(signed_party_details)

        self.audit.log(
            action="sign",
            entity_type="contract",
            entity_id=contract_id,
            change_summary=f"Signed contract #{row['contract_number']}{multi_party_status_note}",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_signed.to_dict(),
                fields=_AUDITABLE_CONTRACT_FIELDS,
                # Never surface the signature blob in the audit payload.
                side_effects=side_effects,
            ),
        )

        # B8.6d-a: server-generated contract PDF, persisted as a Document
        # row, as a best-effort side effect of a successful sign. This does
        # NOT touch sign_contract's authorization/ownership/idempotency gate
        # above (NEW-573/575) -- it only runs after that gate has already
        # let the sign through and the status/signature UPDATE has
        # committed.
        #
        # Uses a system actor (not the real signer `actor`) for
        # create_document: ROLE_CUSTOMER -- the common self-signer -- holds
        # PERM_SIGN_CONTRACTS + PERM_READ_OWN_DOCUMENTS but not
        # PERM_WRITE_DOCUMENTS (auth.py ROLE_PERMISSIONS), so a customer
        # signing their own contract would otherwise get a PermissionError
        # from this internal side effect. The `sign` audit entry above
        # already records the real actor; only the Document row's own
        # audit entry (inside create_document) is attributed to the system
        # actor. Same system_actor shape as the web-intake path elsewhere
        # in this file (see create_lead_from_web_form).
        try:
            from utils.config import get_restoricon_doc_store_path

            # B8.6d-b: a multi-party contract (signed_contract_signers is
            # not None) renders one anchor per ContractSigner row, each
            # with its own signature/pending state -- regenerated on every
            # completed signature (not only once all parties are done), so
            # the stored PDF always reflects the contract's current
            # signing progress rather than only its final state.
            if signed_contract_signers is not None:
                pdf_bytes = pdf_service.render_contract_pdf_multi(_signed, signed_contract_signers)
            else:
                signer_label = f"Signed by {actor.username} on {now}"
                pdf_bytes = pdf_service.render_contract_pdf(_signed, signer_label)

            base_dir = get_restoricon_doc_store_path()
            target_dir = os.path.join(base_dir, "contracts", "customers", str(_signed.customer_id))
            os.makedirs(target_dir, exist_ok=True)
            safe_filename = os.path.basename(
                f"{contract_id}_{int(time.time())}_{_signed.contract_number or 'contract'}.pdf"
            )
            file_path = os.path.join(target_dir, safe_filename)
            with open(file_path, "wb") as fh:
                fh.write(pdf_bytes)

            pdf_system_actor = AuthContext(
                user_id=1,
                username="system_contract_pdf",
                role=ROLE_ADMIN,
                actor_type="agent",
            )
            self.create_document(
                Document(
                    customer_id=_signed.customer_id,
                    project_id=_signed.project_id,
                    document_type="contract",
                    title=f"Signed Contract {_signed.contract_number or contract_id}",
                    file_path=file_path,
                    file_size_bytes=len(pdf_bytes),
                    mime_type="application/pdf",
                ),
                pdf_system_actor,
            )
        except Exception as pdf_exc:
            # Best-effort by design: the sign transaction above is already
            # committed and authoritative, and must not fail or appear to
            # roll back because PDF rendering/persistence failed (disk
            # full, unwritable doc-store path, etc). Not silently
            # swallowed, though -- audit-logged so an operator reviewing
            # the log can see a contract signed with no PDF and
            # investigate, rather than the failure vanishing with no trace.
            self.audit.log(
                action="pdf_generation_failed",
                entity_type="contract",
                entity_id=contract_id,
                change_summary=f"PDF generation failed for signed contract #{row['contract_number']}: {pdf_exc}",
                actor=actor,
                details=build_audit_details(after={"error": str(pdf_exc)}),
            )

        # B8.7b: automatic HomeCare enrollment + Phase 2 bonus -- a
        # second, independent best-effort side effect of a successful
        # sign, deliberately in its own try/except block rather than
        # nested inside the PDF block above: a PDF failure must not skip
        # enrollment, and an enrollment failure must not be misattributed
        # to the "pdf_generation_failed" audit action. Only fires when
        # this sign_contract call actually reached the fully-signed
        # status (_signed.status == "signed") -- for the multi-party
        # branch above, that's only true once every required signer has
        # completed (all_signed), not on the first signature; for the
        # single-signer branch it's always true, matching B8.7a's
        # single-transition-edge precedent. template_name is checked
        # against HOMECARE_TIER_FEE_FIELDS (the four real 'homecare_*'
        # values), not against CONTRACT_TEMPLATE_NAMES directly, so a
        # 'general_remodeling' contract (or a legacy contract with no
        # template_name at all) is never touched by this trigger.
        if _signed.status == "signed" and row["template_name"] in HOMECARE_TIER_FEE_FIELDS:
            subscription_id: Optional[int] = None
            try:
                # System actor, same shape/rationale as pdf_system_actor
                # above and record_payment's commission_system_actor:
                # PERM_READ_TEAM_COMMISSIONS/PERM_WRITE_TEAM_COMMISSIONS
                # are required to read the plan config and record a
                # commission, which the real signer `actor` (often
                # ROLE_CUSTOMER) may not hold. This is an automatic side
                # effect of the sign, not an action the signer is
                # personally authoring.
                homecare_system_actor = AuthContext(
                    user_id=1,
                    username="system_homecare_engine",
                    role=ROLE_ADMIN,
                    actor_type="agent",
                )

                # code-reviewer round-1 bug in B8.7a (NEW context: the
                # plan-config read sat OUTSIDE its own try/except) must
                # not be repeated here -- this read is the first thing
                # inside this try block, not before it.
                plan = self.commission.get_commission_plan_config(homecare_system_actor)
                monthly_fee = getattr(plan, HOMECARE_TIER_FEE_FIELDS[row["template_name"]])

                # property_id: Contract has no direct property column,
                # only project_id -- and a contract's own project's
                # property_id is itself nullable (B8.1). Best-effort
                # resolution, not a guarantee (see database.py's
                # homecare_subscriptions comment).
                property_id = None
                if _signed.project_id:
                    proj_row = conn.execute(
                        "SELECT property_id FROM projects WHERE id = ?;",
                        (_signed.project_id,),
                    ).fetchone()
                    if proj_row:
                        property_id = proj_row["property_id"]

                # Attribution comes from Contract.assigned_user_id --
                # the established pattern this session has used
                # everywhere (create_contract force-sets it server-side
                # to the creating actor). None is handled below exactly
                # like B8.7a's no-rep case: the subscription row is
                # still created, only the commission is skipped.
                rep_user_id = _signed.assigned_user_id

                with conn:
                    cursor = conn.execute(
                        """
                        INSERT INTO homecare_subscriptions (
                            customer_id, property_id, contract_id, tier,
                            monthly_fee, originating_rep_user_id, status,
                            enrolled_at, cancelled_at
                        ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, NULL);
                        """,
                        (
                            _signed.customer_id,
                            property_id,
                            contract_id,
                            row["template_name"],
                            monthly_fee,
                            rep_user_id,
                            now,
                        ),
                    )
                    subscription_id = cursor.lastrowid

                subscription = HomecareSubscription(
                    id=subscription_id,
                    customer_id=_signed.customer_id,
                    property_id=property_id,
                    contract_id=contract_id,
                    tier=row["template_name"],
                    monthly_fee=monthly_fee,
                    originating_rep_user_id=rep_user_id,
                    status="active",
                    enrolled_at=now,
                    cancelled_at=None,
                )

                self.audit.log(
                    action="create",
                    entity_type="homecare_subscription",
                    entity_id=subscription_id,
                    change_summary=(
                        f"Enrolled HomeCare subscription ({row['template_name']}) "
                        f"for contract #{row['contract_number']}"
                    ),
                    actor=actor,
                    details=build_audit_details(after=subscription.to_dict()),
                )

                if rep_user_id is None:
                    # Explicit mirror of B8.7a's no-rep case (Ish, B8.7a
                    # scoping): the subscription still enrolls, but a
                    # rep-less record must not silently pay nobody's
                    # bonus, and must not crash the sign either.
                    self.audit.log(
                        action="commission_skipped_no_rep",
                        entity_type="homecare_subscription",
                        entity_id=subscription_id,
                        change_summary=(
                            f"HomeCare subscription {subscription_id} enrolled but "
                            f"contract #{row['contract_number']} has no assigned rep "
                            f"-- Phase 2 bonus skipped, not paid to anyone"
                        ),
                        actor=actor,
                        details=build_audit_details(
                            after={"subscription_id": subscription_id, "contract_id": contract_id}
                        ),
                    )
                else:
                    # D4 (sales_rep_portal.md §4): Phase 2 bonus = the
                    # tier's first month's fee minus the $100 already
                    # paid in Phase 1 (assessment_flat_commission). Not
                    # clamped at zero -- a future plan-config edit that
                    # drops a tier fee below the flat commission would
                    # produce a negative, non-reversal ledger row; that's
                    # a known edge case, not handled here (see handoff).
                    bonus = monthly_fee - plan.assessment_flat_commission
                    self.commission.record_commission(
                        CommissionLedgerEntry(
                            rep_user_id=rep_user_id,
                            source_type="subscription_upsell",
                            source_id=subscription_id,
                            basis_amount=monthly_fee,
                            commission_rate_or_flat=bonus,
                            commission_amount=bonus,
                            status="earned",
                            earned_at=now,
                            notes=(
                                f"Auto-recorded: HomeCare enrollment for contract "
                                f"#{row['contract_number']} (tier {row['template_name']})"
                            ),
                        ),
                        homecare_system_actor,
                    )
            except sqlite3.IntegrityError as exc:
                # Mirrors record_payment's narrow IntegrityError handling
                # (B8.7a) -- distinguishes the two EXPECTED double-fire
                # shapes (this contract already has a subscription row;
                # this subscription already has a Phase 2 bonus row) from
                # any OTHER integrity violation (e.g. a bogus
                # rep_user_id violating a real FK). All three are
                # audit-logged and none re-raise: this code runs after
                # the sign transaction has already committed, so
                # re-raising here would surface as a false error on an
                # already-successful sign.
                exc_text = str(exc)
                if "homecare_subscriptions.contract_id" in exc_text:
                    self.audit.log(
                        action="homecare_enrollment_duplicate_skipped",
                        entity_type="contract",
                        entity_id=contract_id,
                        change_summary=(
                            f"HomeCare subscription already exists for contract "
                            f"#{row['contract_number']} -- duplicate enrollment "
                            f"trigger skipped"
                        ),
                        actor=actor,
                        details=build_audit_details(after={"contract_id": contract_id}),
                    )
                elif "commission_ledger_entries.source_type, commission_ledger_entries.source_id" in exc_text:
                    self.audit.log(
                        action="commission_duplicate_skipped",
                        entity_type="homecare_subscription",
                        entity_id=subscription_id,
                        change_summary=(
                            f"Phase 2 bonus already recorded for HomeCare "
                            f"subscription {subscription_id} -- duplicate trigger "
                            f"skipped"
                        ),
                        actor=actor,
                        details=build_audit_details(after={"subscription_id": subscription_id}),
                    )
                else:
                    self.audit.log(
                        action="homecare_enrollment_failed",
                        entity_type="contract",
                        entity_id=contract_id,
                        change_summary=(
                            f"HomeCare enrollment/commission failed for contract "
                            f"#{row['contract_number']}: {exc}"
                        ),
                        actor=actor,
                        details=build_audit_details(
                            after={
                                "contract_id": contract_id,
                                "subscription_id": subscription_id,
                                "error": exc_text,
                            }
                        ),
                    )
            except Exception as exc:
                # Any other failure -- including get_commission_plan_config
                # raising (covered: it's the first call inside this try
                # block) as well as record_commission itself raising
                # something other than sqlite3.IntegrityError. Same
                # best-effort contract as above.
                self.audit.log(
                    action="homecare_enrollment_failed",
                    entity_type="contract",
                    entity_id=contract_id,
                    change_summary=(
                        f"HomeCare enrollment/commission failed for contract "
                        f"#{row['contract_number']}: {exc}"
                    ),
                    actor=actor,
                    details=build_audit_details(
                        after={
                            "contract_id": contract_id,
                            "subscription_id": subscription_id,
                            "error": str(exc),
                        }
                    ),
                )

        return _signed

    def cancel_homecare_subscription(
        self, subscription_id: int, actor: AuthContext
    ) -> HomecareSubscription:
        """Cancel a HomeCare subscription and lazily evaluate the 90-day
        Phase 2 clawback (B8.7b, D4, sales_rep_portal.md §4). No
        scheduler exists in Core (confirmed during B8.7 scoping) -- the
        clawback is not a background day-90 job, it is evaluated exactly
        once, right here, at the moment status flips to 'cancelled'. If
        the gap between enrolled_at and cancelled_at is <= 90 days, the
        original Phase 2 bonus is reversed in full via the EXISTING
        CommissionService.reverse_commission mechanism (not duplicated
        here) -- that reversal row carries
        source_type='subscription_upsell', status='reversed',
        commission_amount=-bonus, reversed_entry_id pointing at the
        original bonus row -- NOT a source_type='chargeback' row.
        CommissionService has no such write path: reverse_commission
        always mirrors the original entry's own source_type by design
        (see its docstring), and hand-rolling a separate chargeback
        INSERT here would duplicate its logic and bypass
        idx_commission_ledger_reversed_entry_id_unique's double-reversal
        guard. Cancelling after 90 days performs the status update only,
        no reversal.

        Gated on PERM_WRITE_CONTRACTS -- the closest existing write
        permission to this HomeCare-subscription-adjacent action; no
        dedicated commission/subscription write permission exists yet
        (flagged in this round's report for a NEW_ISSUES entry, not
        built here -- out of B8.7b's scope). Ownership narrowing is the
        SAME TWO CHECKS update_contract applies (customer isolation for
        ROLE_CUSTOMER; rep-ownership narrowing against
        originating_rep_user_id for an actor without
        PERM_READ_TEAM_SALES_DATA) but DEVIATES on the narrowing
        failure's shape: update_contract returns None (the get_lead/
        get_contract not-found precedent, NEW-548) for an out-of-scope
        row, whereas this method raises PermissionError. Deliberate, not
        an oversight -- there is no route exposed for this method yet
        (see this round's report), so there is no HTTP-layer reason to
        prefer a not-found signal over a clear permission error for a
        direct/internal caller.
        """
        if not actor.has_permission(PERM_WRITE_CONTRACTS):
            raise PermissionError("Actor lacks permission to cancel a HomeCare subscription")

        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM homecare_subscriptions WHERE id = ?;", (subscription_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"HomeCare subscription {subscription_id} not found")

        if actor.role == ROLE_CUSTOMER:
            if not actor.customer_id or actor.customer_id != row["customer_id"]:
                raise PermissionError("Customer cannot cancel another customer's HomeCare subscription")
        elif not actor.has_permission(PERM_READ_TEAM_SALES_DATA):
            if row["originating_rep_user_id"] != actor.user_id:
                raise PermissionError("Actor cannot cancel a HomeCare subscription assigned to another rep")

        # Idempotency guard, same shape as sign_contract's -- reject
        # cancelling an already-cancelled subscription instead of
        # silently re-evaluating (and potentially re-reversing, though
        # reverse_commission's own unique index would catch that too) the
        # clawback on every call.
        if row["status"] == "cancelled":
            raise ValueError(f"HomeCare subscription {subscription_id} is already cancelled")

        now = utc_now_iso()
        with conn:
            conn.execute(
                "UPDATE homecare_subscriptions SET status = 'cancelled', cancelled_at = ? WHERE id = ?;",
                (now, subscription_id),
            )

        cancelled = HomecareSubscription(
            id=row["id"],
            customer_id=row["customer_id"],
            property_id=row["property_id"],
            contract_id=row["contract_id"],
            tier=row["tier"],
            monthly_fee=float(row["monthly_fee"]),
            originating_rep_user_id=row["originating_rep_user_id"],
            status="cancelled",
            enrolled_at=row["enrolled_at"],
            cancelled_at=now,
        )

        self.audit.log(
            action="cancel",
            entity_type="homecare_subscription",
            entity_id=subscription_id,
            change_summary=f"Cancelled HomeCare subscription {subscription_id} ({row['tier']})",
            actor=actor,
            details=build_audit_details(
                before={"status": row["status"]},
                after=cancelled.to_dict(),
            ),
        )

        # 90-day clawback, lazy-evaluated right here -- best-effort: the
        # cancellation UPDATE above has already committed, so a clawback
        # failure must not fail or appear to roll back the cancellation
        # itself. Not silently swallowed though -- audit-logged so an
        # operator can investigate/manually correct.
        try:
            enrolled_dt = datetime.fromisoformat(row["enrolled_at"])
            cancelled_dt = datetime.fromisoformat(now)
            within_90_days = (cancelled_dt - enrolled_dt).total_seconds() <= 90 * 86400

            if within_90_days:
                original = conn.execute(
                    "SELECT id FROM commission_ledger_entries "
                    "WHERE source_type = 'subscription_upsell' AND source_id = ? "
                    "AND reversed_entry_id IS NULL;",
                    (subscription_id,),
                ).fetchone()
                # No un-reversed Phase 2 bonus row exists for this
                # subscription (e.g. it was rep-less at enrollment, so no
                # bonus was ever recorded) -- nothing to claw back, not an
                # error.
                if original:
                    clawback_system_actor = AuthContext(
                        user_id=1,
                        username="system_homecare_engine",
                        role=ROLE_ADMIN,
                        actor_type="agent",
                    )
                    self.commission.reverse_commission(
                        original["id"],
                        clawback_system_actor,
                        notes=(
                            f"90-day clawback: HomeCare subscription "
                            f"{subscription_id} cancelled within 90 days of "
                            f"enrollment"
                        ),
                    )
        except Exception as exc:
            self.audit.log(
                action="clawback_failed",
                entity_type="homecare_subscription",
                entity_id=subscription_id,
                change_summary=f"90-day clawback check failed for subscription {subscription_id}: {exc}",
                actor=actor,
                details=build_audit_details(
                    after={"subscription_id": subscription_id, "error": str(exc)}
                ),
            )

        return cancelled

    # ==========================================
    # INVOICES & PAYMENTS
    # ==========================================

    @staticmethod
    def _row_to_invoice(row: Any) -> Invoice:
        keys = row.keys() if hasattr(row, "keys") else []
        payments = json.loads(row["payments_json"]) if "payments_json" in keys and row["payments_json"] else []
        line_items = json.loads(row["line_items_json"]) if "line_items_json" in keys and row["line_items_json"] else []
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
            assigned_user_id=row["assigned_user_id"] if "assigned_user_id" in keys else None,
            invoice_type=row["invoice_type"] if "invoice_type" in keys and row["invoice_type"] else "other",
            line_items=line_items,
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

    def get_customer_credit_balance(self, customer_id: int, actor: AuthContext) -> float:
        """B8.15 (NEW-613/633): sum of every customer_credits row logged
        for this customer -- read-only, no application/spend mechanism
        exists yet (manual-only per Ish's decision). Gated identically to
        get_invoice/list_invoices (PERM_READ_FINANCIALS or PERM_READ_OWN_
        FINANCIALS), with the same ROLE_CUSTOMER narrowing get_invoice
        applies -- customer_id is a caller-supplied parameter here, so
        without this check a ROLE_CUSTOMER actor holding PERM_READ_OWN_
        FINANCIALS could pass an arbitrary customer_id and read someone
        else's credit balance.

        Deliberately excluded from get_ar_aging/get_financial_summary/
        get_project_pnl/AnalyticsSearchService.total_ar per Ish's
        decision that credits stay separate from AR reporting.
        """
        if not (actor.has_permission(PERM_READ_FINANCIALS) or actor.has_permission(PERM_READ_OWN_FINANCIALS)):
            raise PermissionError("Actor lacks permission to read customer credits")

        if actor.role == ROLE_CUSTOMER and (not actor.customer_id or actor.customer_id != customer_id):
            raise PermissionError("Customer cannot access another customer's credit balance")

        conn = self.db.get_connection()
        total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0.0) FROM customer_credits WHERE customer_id = ?;",
            (customer_id,),
        ).fetchone()[0]
        return round(total, 2)

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

    @staticmethod
    def _recalculate_invoice_balance(
        amount: float, payments: List[Dict[str, Any]]
    ) -> Tuple[float, str]:
        """NEW-631 fix: the single, shared balance/status formula for an
        invoice -- `deposit_amount` deliberately does NOT appear here at
        all. Per Ish's 2026-09-25 Design B decision, `deposit_amount` is
        purely a TARGET/expected figure (still stored on the Invoice row,
        still what the handoff-completion guard's deposit condition
        checks against) and never feeds balance/status math again -- no
        special-casing, no conditional logic based on payment_type
        tagging. `balance_due` is always `amount` minus the sum of every
        REAL payment recorded in `payments` (a payment tagged
        payment_type='deposit' is just a real payment like any other
        here; tagging only matters to the handoff guard's own separate
        check).

        Called by create_invoice with payments=[] (so balance_due starts
        at the full amount -- a freshly created invoice owes its full
        amount until a real payment lands, deposit or not) and by
        record_payment with the real, already-updated payments list
        (which includes the just-recorded payment).

        Deliberately uses p["amount"] (hard key, not .get), unlike the
        deposit-guard's own p.get("amount", 0.0) below -- a malformed
        payment dict reaching THIS calculation should fail loud rather
        than silently be treated as $0.0, which would understate
        total_paid and overstate balance_due (money the customer already
        paid would appear still owed). Every real caller (record_payment)
        constructs this dict itself with "amount" always present; the
        only way to reach this without it is a directly-manipulated DB
        row, which is exactly the case that should surface as an error,
        not a wrong number.
        """
        total_paid = sum(p["amount"] for p in payments)
        balance_due = max(0.0, amount - total_paid)
        status = "paid" if balance_due <= 0.001 else "partially_paid"
        return balance_due, status

    def create_invoice(self, invoice: Invoice, actor: AuthContext) -> Invoice:
        if not actor.has_permission(PERM_WRITE_FINANCIALS):
            raise PermissionError("Actor lacks permission to create invoices")

        if invoice.invoice_type not in _VALID_INVOICE_TYPES:
            raise ValueError(f"Invalid invoice_type: {invoice.invoice_type}")

        # B8.7a: default assigned_user_id from the linked Customer's own
        # assigned_user_id when the caller didn't supply one explicitly.
        # create_invoice is PERM_WRITE_FINANCIALS-gated (admin/manager
        # tier -- ROLE_SALES does not hold this permission, confirmed
        # directly against auth.py), so unconditionally stamping the
        # *creating actor* here (create_contract's pattern) would
        # attribute every commission to whichever admin typed the
        # invoice, not the rep who owns the account -- wrong. Invoice has
        # no reliable Contract/Opportunity link to trace a rep through
        # (verified directly), so Customer.assigned_user_id is the only
        # real ownership signal to inherit from. This can still be None
        # (an unclaimed customer -- see NEW-600) -- record_payment's
        # trigger logs and skips rather than crashing or misattributing
        # when that happens. An explicit client-supplied assigned_user_id
        # is respected unchanged (this route is only reachable by a
        # trusted admin/manager-tier actor, unlike create_customer's
        # untrusted-client-input exposure that NEW-598 had to gate).
        if invoice.assigned_user_id is None:
            _customer = self._get_customer_unscoped(invoice.customer_id)
            if _customer is not None:
                invoice.assigned_user_id = _customer.assigned_user_id

        # Phase 0-slim: when line_items are supplied, compute amount
        # server-side as the sum of each item's total -- never trust a
        # client-supplied amount in that case. Mirrors
        # OperationsService.create_work_order's line-item cost computation
        # exactly: each item's total_cost is recomputed from
        # quantity * unit_cost (overwriting whatever the client sent),
        # then summed.
        if invoice.line_items:
            total = 0.0
            for item in invoice.line_items:
                qty = float(item.get("quantity", 1.0))
                unit_cost = float(item.get("unit_cost", 0.0))
                item_total = round(qty * unit_cost, 2)
                item["total_cost"] = item_total
                total += item_total
            invoice.amount = round(total, 2)

        now = utc_now_iso()
        if not invoice.invoice_number:
            invoice.invoice_number = f"INV-{now[:10].replace('-', '')}-{secrets.token_hex(2).upper()}"
        invoice.created_at = now
        invoice.updated_at = now
        # NEW-631 fix: balance_due at creation is always the FULL amount --
        # a freshly created invoice owes its full amount until a real
        # payment lands, deposit or not. deposit_amount is a target figure
        # only (see _recalculate_invoice_balance), never subtracted here.
        # Deliberately called with payments=[], NOT invoice.payments --
        # a caller-supplied payments list at creation time (an unusual
        # shape, but Invoice's own dataclass allows it) must not be fed
        # into the balance formula here; only record_payment's own real,
        # recorded payments ever count toward balance_due.
        invoice.balance_due, _ = self._recalculate_invoice_balance(invoice.amount, [])
        payments_json = json.dumps(invoice.payments)
        line_items_json = json.dumps(invoice.line_items)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO invoices (
                    invoice_number, customer_id, project_id, status,
                    amount, deposit_amount, balance_due, due_date,
                    payments_json, notes, assigned_user_id, invoice_type,
                    line_items_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                    invoice.assigned_user_id,
                    invoice.invoice_type,
                    line_items_json,
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

    @staticmethod
    def _resolve_signed_at_value(
        customer_signed_at: Optional[str],
        multi_party_signed_at: Optional[str],
        signer_row_count: int,
    ) -> Optional[str]:
        """Pure resolution rule, shared by _resolve_portfolio_override_
        eligibility's gate 1b/5 (below) and resolve_contract_signed_at
        (NEW-617): a contract with one or more contract_signers rows
        (opted into multi-party signing via add_contract_signers,
        B8.6d-b) resolves to MAX(contract_signers.signed_at) --
        Contract.customer_signed_at is never written for such a
        contract, since the last required signer to complete may not be
        the customer (see add_contract_signers's docstring). A contract
        with zero contract_signers rows (the legacy single-signer path)
        resolves to Contract.customer_signed_at unchanged. Extracted as
        its own pure function (rather than duplicated logic) so both
        callers can never diverge on this rule.
        """
        if signer_row_count and signer_row_count > 0:
            return multi_party_signed_at
        return customer_signed_at

    def resolve_contract_signed_at(self, contract_id: int) -> Optional[str]:
        """NEW-617: standalone, DB-backed resolution of a single
        contract's real "signed at" timestamp, for display sites (the
        /api/v1/contracts list/get responses) that need this outside
        _resolve_portfolio_override_eligibility's own query shape.
        Delegates to _resolve_signed_at_value so the resolution rule
        itself lives in exactly one place. Returns None if the contract
        doesn't exist."""
        conn = self.db.get_connection()
        row = conn.execute(
            """
            SELECT c.customer_signed_at,
                   (SELECT MAX(cs.signed_at) FROM contract_signers cs
                    WHERE cs.contract_id = c.id) AS multi_party_signed_at,
                   (SELECT COUNT(*) FROM contract_signers cs
                    WHERE cs.contract_id = c.id) AS signer_row_count
            FROM contracts c WHERE c.id = ?;
            """,
            (contract_id,),
        ).fetchone()
        if row is None:
            return None
        return self._resolve_signed_at_value(
            row["customer_signed_at"], row["multi_party_signed_at"], row["signer_row_count"]
        )

    def _resolve_portfolio_override_eligibility(
        self,
        invoice_id: int,
        project_id: Optional[int],
        invoice_type: str,
        payment_timestamp: str,
        window_months: int,
    ) -> _PortfolioOverrideEligibility:
        """B8.7c, D6, sales_rep_portal.md §4 Phase 3 -- isolated, independently
        testable eligibility resolution for the portfolio-override commission
        (a 5% residual on gross collected revenue from major GC projects, for
        `window_months` from a customer's initial HomeCare enrollment).
        Called by record_payment on EVERY call against an eligible invoice
        (not a status-transition edge -- "collected" is any amount received).

        Every gate below is independent; ALL must pass for `eligible=True`:

        1. Invoice classification: invoice_type not in ('assessment',
           'subscription') AND the linked Contract's template_name ==
           'general_remodeling'. Invoice has no direct contract_id -- resolved
           via Invoice.project_id -> Contract WHERE project_id = ? AND
           status = 'signed' (both links are nullable; a missing link is the
           ONE fail-closed skip this method flags via skip_reason, since it
           is a genuine data-integrity gap rather than a normal business
           outcome).
        2. HomeCare origination (customer-level, deliberately NOT
           property-level -- homecare_subscriptions.property_id is
           documented best-effort/not-guaranteed): the customer's INITIAL
           enrollment (MIN(enrolled_at)) supplies both the enrollment date
           for gate 3 and the attributed rep (originating_rep_user_id) --
           attribution is locked to this, NEVER the GC contract's own
           assigned_user_id.
        3. 12-month window: payment_timestamp <= initial enrolled_at +
           window_months. Live-evaluated on every call, no caching.
        4. Live HomeCare-active check: the customer's most-relevant (latest
           by enrolled_at) subscription row must have status == 'active' --
           if their HomeCare account has since been cancelled, no override on
           subsequent payments.
        5. Termination gate, independent of gate 3: the GC contract's
           resolved signed timestamp (customer_signed_at for a
           single-signer contract, or MAX(contract_signers.signed_at) for
           one opted into multi-party signing via add_contract_signers --
           see gate 1b) must be <= the originating rep's terminated_at, OR
           the rep was never terminated (terminated_at IS NULL). This is
           the counter-intuitive rule from the real signed contract text:
           a contract signed BEFORE the rep's departure still pays the
           override on payments collected even AFTER the rep left --
           there is deliberately no "is the rep currently active" check
           anywhere in this method.

        Returns eligible=False with skip_reason=None for every normal
        ineligible outcome (not logged by the caller) and
        skip_reason='contract_link_missing' only for the disclosed
        fail-closed gap (Invoice.project_id or the resolved Contract's own
        project_id is missing) -- record_payment audit-logs only that one
        case, mirroring commission_skipped_no_rep's shape.
        """
        no_override = _PortfolioOverrideEligibility(False, None, None)

        # Gate 1a: invoice classification (cheap check first).
        if invoice_type in ("assessment", "subscription"):
            return no_override

        if project_id is None:
            return _PortfolioOverrideEligibility(False, None, "contract_link_missing")

        conn = self.db.get_connection()

        # Gate 1b: resolve the project's own signed contract(s). If more
        # than one signed contract somehow exists for this project, pick
        # the one matching template_name == 'general_remodeling', most
        # recently signed first.
        #
        # NEW (round 2, code-reviewer Critical): a contract's real "signed"
        # moment is NOT always Contract.customer_signed_at -- a contract
        # opted into multi-party signing via add_contract_signers
        # (B8.6d-b) flips contracts.status to 'signed' when its LAST
        # required signer completes, without ever writing
        # customer_signed_at (that column specifically means "the
        # customer signed", and on a multi-party contract the last signer
        # may be the admin/PM, not the customer -- see sign_contract's
        # `all_signed` branch, crm_service.py ~4236-4239, and
        # add_contract_signers's docstring, ~3924-3927). Left unresolved,
        # every multi-party-signed GC contract has customer_signed_at
        # NULL forever, which (a) made gate 5 below always fall through
        # to eligible=True (the contract-signed-before-termination check
        # never ran), and (b) made this ORDER BY systematically
        # deprioritize a multi-party contract under SQLite's NULLS-last
        # DESC ordering when a project has more than one signed contract.
        #
        # Fix: resolve each candidate contract's real signed timestamp as
        # MAX(contract_signers.signed_at) when contract_signers rows
        # exist for it (the multi-party analogue of "done when the last
        # required signer finishes"), falling back to
        # Contract.customer_signed_at when there are no contract_signers
        # rows (the legacy single-signer path, unchanged). Applied in
        # Python after fetching candidates rather than in the ORDER BY
        # itself, then re-sorted here -- keeps this query readable and
        # keeps the resolution logic in one place gate 5 can reuse below.
        contract_rows = conn.execute(
            """
            SELECT c.id, c.template_name, c.customer_signed_at,
                   (SELECT MAX(cs.signed_at) FROM contract_signers cs
                    WHERE cs.contract_id = c.id) AS multi_party_signed_at,
                   (SELECT COUNT(*) FROM contract_signers cs
                    WHERE cs.contract_id = c.id) AS signer_row_count
            FROM contracts c
            WHERE c.project_id = ? AND c.status = 'signed';
            """,
            (project_id,),
        ).fetchall()
        if not contract_rows:
            # No signed contract at all links back to this project -- the
            # disclosed fail-closed gap, not a normal ineligible outcome.
            return _PortfolioOverrideEligibility(False, None, "contract_link_missing")

        def _resolved_signed_at(row: Any) -> Optional[str]:
            return self._resolve_signed_at_value(
                row["customer_signed_at"], row["multi_party_signed_at"], row["signer_row_count"]
            )

        contract_rows = sorted(
            contract_rows,
            key=lambda r: (_resolved_signed_at(r) or "", r["id"]),
            reverse=True,
        )

        gc_contract = next(
            (r for r in contract_rows if r["template_name"] == "general_remodeling"), None
        )
        if gc_contract is None:
            # Real signed contract(s) exist for this project, just none of
            # them are the GC template -- a normal ineligible outcome (e.g.
            # a HomeCare-only project), not a link gap.
            return no_override

        project_row = conn.execute(
            "SELECT customer_id FROM projects WHERE id = ?;", (project_id,)
        ).fetchone()
        if project_row is None:
            # invoices.project_id carries ON DELETE SET NULL, so this is
            # only reachable via a race with a concurrent project delete --
            # treat the same as a missing link.
            return _PortfolioOverrideEligibility(False, None, "contract_link_missing")

        # Gate 2: HomeCare origination, customer-level. The initial
        # (earliest) enrollment supplies both the window's anchor date and
        # the attributed rep.
        initial_enrollment = conn.execute(
            "SELECT enrolled_at, originating_rep_user_id FROM homecare_subscriptions "
            "WHERE customer_id = ? ORDER BY enrolled_at ASC, id ASC LIMIT 1;",
            (project_row["customer_id"],),
        ).fetchone()
        if initial_enrollment is None:
            # This customer never had a HomeCare enrollment -- a normal
            # ineligible outcome for a GC-only customer.
            return no_override

        rep_user_id = initial_enrollment["originating_rep_user_id"]
        if rep_user_id is None:
            # The originating rep's user row was deleted (originating_rep_
            # user_id is ON DELETE SET NULL) -- no rep to attribute this
            # override to. Distinct from contract_link_missing: this is a
            # rep-attribution gap, not a data-integrity link gap, so it is
            # deliberately NOT flagged via skip_reason here (record_payment
            # gives it its own dedicated skip/audit action, separate from
            # both commission_skipped_no_rep and commission_skipped_no_
            # contract_link, so it is never confused with either in the
            # audit log).
            return no_override

        # Gate 4: live HomeCare-active check, the customer's most-relevant
        # (latest by enrolled_at) subscription row.
        latest_subscription = conn.execute(
            "SELECT status FROM homecare_subscriptions "
            "WHERE customer_id = ? ORDER BY enrolled_at DESC, id DESC LIMIT 1;",
            (project_row["customer_id"],),
        ).fetchone()
        if latest_subscription is None or latest_subscription["status"] != "active":
            return no_override

        # Gate 3: 12-month window, live-evaluated.
        initial_enrolled_at = _parse_aware_iso(initial_enrollment["enrolled_at"])
        window_end = _add_months(initial_enrolled_at, window_months)
        payment_dt = _parse_aware_iso(payment_timestamp)
        if payment_dt > window_end:
            return no_override

        # Gate 5: termination gate, INDEPENDENT of gate 3. A contract
        # signed before (or on) the rep's departure still pays the
        # override on payments collected after the rep left -- no "is the
        # rep currently active" check. Uses _resolved_signed_at (gate 1b
        # above), not the raw customer_signed_at column -- a multi-party
        # contract's real completion moment is
        # MAX(contract_signers.signed_at), which customer_signed_at never
        # captures (see gate 1b's comment for why).
        #
        # gc_contract was already filtered to status = 'signed' by gate
        # 1b's query, and status only ever becomes 'signed' via
        # sign_contract's two branches -- the single-signer branch always
        # writes customer_signed_at in the SAME UPDATE that sets status,
        # and the multi-party branch only sets status when every
        # contract_signers row already has signed_at populated
        # (sign_contract's `all_signed` check) -- so _resolved_signed_at
        # cannot actually be None for a row that reaches this line today.
        # Still fails CLOSED, not open, if it ever is: this is the exact
        # mechanism the round-1 Critical exploited (an unresolved signed
        # timestamp silently falling through to eligible=True), so rather
        # than repeat that shape for a hypothetical future third path to
        # status='signed', a rep with a non-NULL terminated_at and an
        # unresolvable signed_at is treated as failing the termination
        # check (no override) rather than passing it by default. A rep
        # who was never terminated (terminated_at IS NULL) is unaffected
        # either way, since there is nothing to compare signed_at against.
        signed_at = _resolved_signed_at(gc_contract)
        rep_row = conn.execute(
            "SELECT terminated_at FROM users WHERE id = ?;", (rep_user_id,)
        ).fetchone()
        terminated_at = rep_row["terminated_at"] if rep_row is not None else None
        if terminated_at is not None:
            if signed_at is None or _parse_aware_iso(signed_at) > _parse_aware_iso(terminated_at):
                return no_override

        return _PortfolioOverrideEligibility(True, rep_user_id, None)

    def record_payment(
        self,
        invoice_id: int,
        payment_amount: float,
        payment_method: str,
        transaction_reference: str,
        actor: AuthContext,
        payment_type: str = "installment",
    ) -> Invoice:
        """Record a customer payment against an invoice.

        `payment_type` (B8.12b, default 'installment') is the explicit
        deposit-tagging mechanism -- see _VALID_PAYMENT_TYPES' module-level
        comment. Passing 'deposit' is how a caller marks this specific
        payment as the one complete_handoff_checklist's guard looks for.
        """
        if not actor.has_permission(PERM_WRITE_FINANCIALS):
            raise PermissionError("Actor lacks permission to record payments")

        if payment_type not in _VALID_PAYMENT_TYPES:
            raise ValueError(
                f"Invalid payment_type '{payment_type}'; must be one of {sorted(_VALID_PAYMENT_TYPES)}"
            )

        # NEW-651: negative payments would silently skip the overpayment-
        # credit insert below (its guard is `> 0.001`) while leaving any
        # previously-issued customer_credits row unreversed -- there's no
        # payment-correction/reversal mechanism in this codebase, so the
        # fix is simply to reject negative amounts outright. $0.00 stays
        # allowed -- it's a documented legitimate use case (an operator's
        # reconciliation note, see the idempotency comment below).
        if payment_amount < 0:
            raise ValueError(
                f"payment_amount must be >= 0, got {payment_amount}"
            )

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM invoices WHERE id = ?;", (invoice_id,)).fetchone()
        if not row:
            raise ValueError(f"Invoice {invoice_id} not found")

        # NEW-633: a payment against a voided invoice must not silently
        # resurrect it to paid/partially_paid. finance_service.py already
        # treats status='void' as excluded/terminal on the read side (its
        # AR-balance queries filter `status != 'void'`); this matches that
        # on the write side. Checked before any side effect
        # (before _before is even captured) so a rejected call leaves no
        # audit entry, matching this method's other early-raise sites.
        if row["status"] == "void":
            raise ValueError(f"Cannot record a payment against voided invoice {invoice_id}")

        _before = self._row_to_invoice(row).to_dict()

        now = utc_now_iso()
        payments = json.loads(row["payments_json"]) if row["payments_json"] else []
        payments.append({
            "timestamp": now,
            "amount": payment_amount,
            "method": payment_method,
            "reference": transaction_reference,
            "recorded_by_user_id": actor.user_id,
            "payment_type": payment_type,
        })

        # NEW-631 fix: deposit_amount does NOT feed this calculation --
        # `payments` (already includes the just-recorded payment above) is
        # the sole source of truth for what's actually been paid. See
        # _recalculate_invoice_balance's docstring for the full rationale.
        new_balance, new_status = self._recalculate_invoice_balance(row["amount"], payments)

        # B8.15 (NEW-613/633, Ish-approved 2026-09-25): "overpayments
        # should be logged as credit" -- manual-only, no auto-apply, and
        # deliberately kept out of AR reporting (see customer_credits'
        # own DDL comment in database.py for the full rationale). total
        # overage is total_paid (every real payment on this invoice,
        # including the one just appended above) minus the invoice's
        # full amount -- the SAME total_paid _recalculate_invoice_balance
        # just computed internally, recomputed here since that helper
        # only returns balance_due/status, not the raw total.
        #
        # Idempotency: record_payment is documented above as re-callable
        # against an already-settled invoice (e.g. a retried request, or
        # an operator recording a $0 reconciliation note) -- since
        # total_paid is recomputed from the ENTIRE payments list on every
        # call, `overage` stays the same (or grows, if a genuine further
        # payment lands) on every subsequent call. A naive per-call
        # insert would log a new credit row every retry. Instead, only
        # the INCREMENTAL overage beyond what's already been logged for
        # this invoice is inserted -- covers: (a) first-time overpayment
        # (nothing logged yet, insert the full overage), (b) a retried
        # call with no new payment (overage unchanged, already_credited
        # matches it, delta is 0, no insert), and (c) a genuine further
        # overpayment on top of an already-credited invoice (delta is
        # just the new increment). No DB-level uniqueness constraint is
        # used as a second defense here (unlike commission_ledger_
        # entries' idx_commission_ledger_source_unique) because multiple
        # credit rows per invoice are legitimate -- the constraint that
        # matters is this delta computation, not a source_invoice_id
        # uniqueness rule.
        total_paid = sum(p["amount"] for p in payments)
        overage = round(total_paid - row["amount"], 2)
        credit_delta = 0.0

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

            if overage > 0.001:
                already_credited = conn.execute(
                    "SELECT COALESCE(SUM(amount), 0.0) FROM customer_credits WHERE source_invoice_id = ?;",
                    (invoice_id,),
                ).fetchone()[0]
                credit_delta = round(overage - already_credited, 2)
                if credit_delta > 0.001:
                    conn.execute(
                        """
                        INSERT INTO customer_credits
                            (customer_id, source_invoice_id, amount, reason, created_by_user_id, created_at)
                        VALUES (?, ?, ?, 'overpayment', ?, ?);
                        """,
                        (row["customer_id"], invoice_id, credit_delta, actor.user_id, now),
                    )
                else:
                    credit_delta = 0.0

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
            assigned_user_id=row["assigned_user_id"],
            invoice_type=row["invoice_type"] or "other",
            line_items=json.loads(row["line_items_json"]) if row["line_items_json"] else [],
            created_at=row["created_at"],
            updated_at=now,
        )

        _side_effects: Dict[str, Any] = {"payment_recorded": {
            "amount": payment_amount,
            "method": payment_method,
            "reference": transaction_reference,
            "payment_type": payment_type,
            "new_balance": new_balance,
            "new_status": new_status,
        }}
        if credit_delta > 0.001:
            # B8.15: recorded in the SAME "pay" audit entry rather than a
            # new audit.log call -- test_crm_entity_lifecycle_with_audit_
            # trail (test_services.py) hard-asserts an exact log count,
            # and this credit insert is a side effect of THIS payment,
            # not an independently-authored action.
            _side_effects["credit_recorded"] = {
                "amount": credit_delta,
                "reason": "overpayment",
                "customer_id": row["customer_id"],
            }

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
                side_effects=_side_effects,
            ),
        )

        # B8.7a: automatic Phase-1 flat commission -- fires exactly on the
        # not-paid -> paid transition edge, never on every record_payment
        # call. record_payment can be invoked more than once against an
        # already-paid invoice (e.g. a retried request) -- this project
        # has hit exactly this shape of re-fired-side-effect bug before,
        # so this check is the first of two independent defenses. The
        # second is idx_commission_ledger_source_unique (database.py),
        # a DB-level partial unique index on (source_type, source_id)
        # that turns a genuine double-fire (e.g. two concurrent
        # record_payment calls racing past this same in-Python check)
        # into a straight IntegrityError rather than a silent double
        # payment -- caught narrowly below. Only acts on invoices
        # explicitly classified as an assessment sale (invoice_type ==
        # 'assessment'); every other invoice_type is untouched by this
        # round (B8.7b/c build Phase 2/3 commission logic later).
        if _before["status"] != "paid" and new_status == "paid" and row["invoice_type"] == "assessment":
            rep_user_id = row["assigned_user_id"]
            if rep_user_id is None:
                # Explicit product decision (Ish, B8.7a scoping): a
                # rep-less record must not silently pay nobody's
                # commission, and must not crash the payment either --
                # log it clearly so it's visible rather than vanishing
                # with no trace (see NEW-600 for the known gap where an
                # admin-converted lead's Customer, and therefore this
                # invoice's inherited assigned_user_id, can land
                # unclaimed). Attributed to the REAL actor (not the
                # system actor used below) so an operator reviewing the
                # audit log sees who recorded the payment that had no
                # rep to attribute a commission to.
                self.audit.log(
                    action="commission_skipped_no_rep",
                    entity_type="invoice",
                    entity_id=invoice_id,
                    change_summary=(
                        f"Assessment invoice #{row['invoice_number']} paid in full but has "
                        f"no assigned rep -- commission skipped, not paid to anyone"
                    ),
                    actor=actor,
                    details=build_audit_details(
                        after={"invoice_id": invoice_id, "customer_id": row["customer_id"]}
                    ),
                )
            else:
                # System actor, same shape/rationale as sign_contract's
                # pdf_system_actor above: recording a commission requires
                # PERM_WRITE_TEAM_COMMISSIONS, which the actor who merely
                # recorded a payment (PERM_WRITE_FINANCIALS) may not hold
                # -- this is an automatic side effect of the payment, not
                # an action the payment-recording actor is personally
                # authoring, so it must not be gated on their permission
                # set. The "pay" audit entry above already records the
                # real actor; only this ledger entry's own audit trail
                # (inside record_commission) is attributed to the system
                # actor.
                commission_system_actor = AuthContext(
                    user_id=1,
                    username="system_commission_engine",
                    role=ROLE_ADMIN,
                    actor_type="agent",
                )
                # Best-effort by design, same rationale as sign_contract's
                # PDF side effect above: the payment UPDATE has already
                # committed (and its own "pay" audit entry already
                # written) by the time this runs -- a commission-recording
                # failure of ANY kind must not fail or appear to roll back
                # the already-successful payment. Never silently swallowed
                # though: every failure path below is audit-logged so an
                # operator reviewing the log can see a paid assessment
                # invoice with no commission recorded and investigate/
                # manually correct, rather than the failure vanishing with
                # no trace or propagating as a false 500 on a payment that
                # actually succeeded.
                try:
                    plan = self.commission.get_commission_plan_config(commission_system_actor)
                    self.commission.record_commission(
                        CommissionLedgerEntry(
                            rep_user_id=rep_user_id,
                            source_type="assessment",
                            source_id=invoice_id,
                            basis_amount=plan.assessment_price,
                            commission_rate_or_flat=plan.assessment_flat_commission,
                            commission_amount=plan.assessment_flat_commission,
                            status="earned",
                            earned_at=now,
                            notes=f"Auto-recorded: assessment invoice #{row['invoice_number']} paid in full",
                        ),
                        commission_system_actor,
                    )
                except sqlite3.IntegrityError as exc:
                    # Narrowly distinguishes the EXPECTED second-layer
                    # no-op (idx_commission_ledger_source_unique rejecting
                    # a genuine double-fire -- this invoice already
                    # produced a commission row) from any OTHER integrity
                    # violation (e.g. a bogus rep_user_id violating
                    # commission_ledger_entries' real FK to users --
                    # reachable since create_invoice's assigned_user_id
                    # can be client-supplied via routes.py's
                    # Invoice(**json_body), and this connection runs with
                    # PRAGMA foreign_keys = ON, confirmed directly). Both
                    # branches are audit-logged and neither re-raises --
                    # unlike reverse_commission's narrow check (which DOES
                    # re-raise a non-matching IntegrityError), this call
                    # site sits after the payment has already committed,
                    # so re-raising here would surface as a false 500 on a
                    # payment that actually succeeded, with no way to
                    # retry the trigger since the invoice is now 'paid'.
                    if "commission_ledger_entries.source_type, commission_ledger_entries.source_id" in str(exc):
                        self.audit.log(
                            action="commission_duplicate_skipped",
                            entity_type="invoice",
                            entity_id=invoice_id,
                            change_summary=(
                                f"Commission already recorded for assessment invoice "
                                f"#{row['invoice_number']} -- duplicate trigger skipped"
                            ),
                            actor=actor,
                            details=build_audit_details(after={"invoice_id": invoice_id}),
                        )
                    else:
                        self.audit.log(
                            action="commission_recording_failed",
                            entity_type="invoice",
                            entity_id=invoice_id,
                            change_summary=(
                                f"Commission recording failed for assessment invoice "
                                f"#{row['invoice_number']}: {exc}"
                            ),
                            actor=actor,
                            details=build_audit_details(after={"invoice_id": invoice_id, "error": str(exc)}),
                        )
                except Exception as exc:
                    # Any other failure -- including get_commission_plan_config
                    # raising (now covered: the call sits inside this try
                    # block, immediately before record_commission consumes
                    # its result) as well as record_commission itself
                    # raising something other than sqlite3.IntegrityError.
                    # Same best-effort contract as above, deliberately broad
                    # since this is the last line of defense protecting an
                    # already-committed payment from an unrelated side-effect
                    # failure.
                    self.audit.log(
                        action="commission_recording_failed",
                        entity_type="invoice",
                        entity_id=invoice_id,
                        change_summary=(
                            f"Commission recording failed for assessment invoice "
                            f"#{row['invoice_number']}: {exc}"
                        ),
                        actor=actor,
                        details=build_audit_details(after={"invoice_id": invoice_id, "error": str(exc)}),
                    )

        # B8.7c, D6, sales_rep_portal.md §4 Phase 3: portfolio-override
        # commission (5% residual on gross collected revenue from major GC
        # projects, for a config-driven N months from a customer's initial
        # HomeCare enrollment). GENUINELY INDEPENDENT of the Phase-1 block
        # above -- fires on EVERY record_payment call against an eligible
        # invoice, not the not-paid -> paid transition edge Phase 1 uses.
        # "Collected" is any amount received, not full payoff, so the
        # basis is this call's own payment_amount increment, never the
        # invoice's cumulative total. Eligibility resolution is isolated
        # in _resolve_portfolio_override_eligibility (independently
        # testable, see its own docstring for the 5 gates).
        #
        # THE CONFIG READ (get_commission_plan_config) IS THE LITERAL
        # FIRST STATEMENT INSIDE THIS TRY BLOCK. This is the exact bug
        # B8.7a shipped in round 1 (a plan-config read sitting OUTSIDE its
        # own try/except let a config-read failure escape as a false error
        # on an already-committed payment) -- B8.7b's implementer
        # explicitly avoided repeating it, and this is that same
        # verification a third time. Best-effort, audit-logged, NEVER
        # re-raised: the payment UPDATE has already committed by the time
        # this runs, same rationale as the Phase-1 block above.
        #
        # KNOWN, ACCEPTED LIMITATIONS (disclosed, not fixed this round --
        # see the B8.7c round's NEW_ISSUES entries):
        #   - No DB-level double-fire guard on source_type='portfolio_
        #     override' rows (idx_commission_ledger_source_unique only
        #     covers 'assessment'/'subscription_upsell') -- there is no
        #     stable per-payment identity to key a unique index on, since
        #     payments_json is a plain append-only array with no per-
        #     payment id. `notes` below records the payment's own
        #     timestamp+amount explicitly so a human can identify a
        #     duplicate row from a retried record_payment call.
        #   - record_payment does not guard against being called with the
        #     SAME timestamp/amount twice -- a retried call still writes a
        #     second override row here. (NEW-651, fixed: negative
        #     payment_amount is now rejected before this point; a $0.00
        #     payment_amount is still legitimate -- see the idempotency
        #     comment below -- and still writes a $0.00 override row
        #     unchanged from that input, same as every other money field
        #     this function already trusts from the caller.)
        #
        # System actor, same shape/rationale/known FK-fragility as the
        # Phase-1 block's commission_system_actor above (see NEW-602) --
        # a fresh instance here since this block is unconditional and the
        # Phase-1 block's own instance only exists inside its own `if`.
        commission_config_actor = AuthContext(
            user_id=1,
            username="system_commission_engine",
            role=ROLE_ADMIN,
            actor_type="agent",
        )
        try:
            plan = self.commission.get_commission_plan_config(commission_config_actor)
            eligibility = self._resolve_portfolio_override_eligibility(
                invoice_id=invoice_id,
                project_id=row["project_id"],
                invoice_type=row["invoice_type"] or "other",
                payment_timestamp=now,
                window_months=plan.portfolio_override_window_months,
            )
            if eligibility.eligible:
                override_amount = round(payment_amount * plan.portfolio_override_rate, 2)
                self.commission.record_commission(
                    CommissionLedgerEntry(
                        rep_user_id=eligibility.rep_user_id,
                        source_type="portfolio_override",
                        source_id=invoice_id,
                        basis_amount=payment_amount,
                        commission_rate_or_flat=plan.portfolio_override_rate,
                        commission_amount=override_amount,
                        status="earned",
                        earned_at=now,
                        notes=(
                            f"Auto-recorded: portfolio override on invoice "
                            f"#{row['invoice_number']}, payment of ${payment_amount:.2f} "
                            f"recorded at {now}"
                        ),
                    ),
                    commission_config_actor,
                )
            elif eligibility.skip_reason == "contract_link_missing":
                # The disclosed fail-closed gap: Invoice.project_id or the
                # resolved Contract's own project_id is missing -- never
                # guessed, never crashed, skipped with an explicit audit
                # trail so an operator can investigate/manually correct.
                self.audit.log(
                    action="commission_skipped_no_contract_link",
                    entity_type="invoice",
                    entity_id=invoice_id,
                    change_summary=(
                        f"Invoice #{row['invoice_number']} payment recorded but has no "
                        f"resolvable project/contract link -- portfolio override skipped"
                    ),
                    actor=actor,
                    details=build_audit_details(
                        after={"invoice_id": invoice_id, "project_id": row["project_id"]}
                    ),
                )
        except Exception as exc:
            # Same best-effort contract as the Phase-1 block above,
            # deliberately broad since this is the last line of defense
            # protecting an already-committed payment from an unrelated
            # side-effect failure.
            self.audit.log(
                action="commission_recording_failed",
                entity_type="invoice",
                entity_id=invoice_id,
                change_summary=(
                    f"Portfolio-override commission recording failed for invoice "
                    f"#{row['invoice_number']}: {exc}"
                ),
                actor=actor,
                details=build_audit_details(after={"invoice_id": invoice_id, "error": str(exc)}),
            )

        return _updated

    # ==========================================
    # PRODUCTION HANDOFF CHECKLIST (B8.12b)
    # ==========================================

    @staticmethod
    def _row_to_handoff_checklist(row: Any) -> ProductionHandoffChecklist:
        items = json.loads(row["items_json"]) if row["items_json"] else {}
        return ProductionHandoffChecklist(
            id=row["id"],
            project_id=row["project_id"],
            items=items,
            completed_at=row["completed_at"],
            completed_by=row["completed_by"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _evaluate_handoff_conditions(
        self, project_id: int, items: Dict[str, str]
    ) -> Dict[str, Any]:
        """Evaluates the three independent completion-guard conditions
        (B8.12b, sales_rep_portal.md §B8.12) without mutating anything --
        shared by get_handoff_checklist (so the UI can render each
        condition's live status/disabled-reason before attempting
        completion) and complete_handoff_checklist (so the guard has
        exactly one implementation, not a second copy of the rules in
        the route/renderer).

        Condition (a): a signed contract exists for this project.
        Resolved as a direct `contracts.status = 'signed'` existence
        check, mirroring `_resolve_gc_contract_for_portfolio_override`'s
        gate-1b query shape -- deliberately not pinned to one specific
        contract row (a project can have more than one contract, e.g. a
        HomeCare enrollment alongside a general_remodeling contract; the
        guard only needs "a signed one exists", not "which one").

        Condition (b): a qualifying deposit payment exists. NEW-632 fix
        (2026-09-25): checks only invoices linked to this project_id with
        invoice_type == 'project' (not every invoice linked to the
        project regardless of type -- the original "any invoice
        satisfies it" reading let an unrelated invoice, e.g. a $0-deposit
        assessment invoice, void the deposit condition). For each
        eligible invoice, SUMS every payments_json entry with
        payment_type == 'deposit' (multiple deposit-tagged payments
        against the same invoice count together -- e.g. two $2,500
        deposit-tagged payments satisfy a $5,000 deposit_amount, neither
        needs to meet it alone) and requires that sum >= the invoice's
        own deposit_amount, AND deposit_amount > 0 (a genuinely
        zero-target deposit is not trivially satisfiable by a $0 tagged
        payment). Uses `.get('payment_type')`, never `['payment_type']`
        -- every payment recorded before this round has no payment_type
        key at all, and must be treated as non-deposit, not crash.

        NEW-631 (fixed in this same round): deposit_amount no longer
        feeds record_payment's/create_invoice's balance_due/status
        formula at all (see _recalculate_invoice_balance) -- a payment
        tagged payment_type='deposit' is a real payment like any other
        for balance purposes; tagging only matters to this guard's own
        check.

        Condition (c): every one of the 7 required items is 'done' or
        'na' -- never a partial/some-required scheme.
        """
        conn = self.db.get_connection()
        contract_signed = conn.execute(
            "SELECT 1 FROM contracts WHERE project_id = ? AND status = 'signed' LIMIT 1;",
            (project_id,),
        ).fetchone() is not None

        deposit_received = False
        invoice_rows = conn.execute(
            "SELECT deposit_amount, payments_json FROM invoices WHERE project_id = ? AND invoice_type = 'project';",
            (project_id,),
        ).fetchall()
        for inv_row in invoice_rows:
            if inv_row["deposit_amount"] <= 0.0:
                continue
            payments = json.loads(inv_row["payments_json"]) if inv_row["payments_json"] else []
            deposit_total = sum(
                p.get("amount", 0.0) for p in payments if p.get("payment_type") == "deposit"
            )
            # Epsilon tolerance (same 0.001 threshold _recalculate_invoice_
            # balance uses above), defensive against float accumulation
            # error in a summed comparison -- summing several
            # deposit-tagged payments is a new failure surface this
            # single-payment comparison never had. A GENUINE shortfall
            # (e.g. three payments totalling one cent under
            # deposit_amount) must still correctly block completion --
            # 0.001 is far smaller than a cent, so it only forgives true
            # floating-point drift, never a real underpayment. See
            # test_complete_handoff_checklist_genuine_one_cent_shortfall_
            # still_blocks for the negative case.
            if deposit_total >= inv_row["deposit_amount"] - 0.001:
                deposit_received = True
                break

        pending_items = [k for k in PRODUCTION_HANDOFF_CHECKLIST_ITEMS if items.get(k) not in ("done", "na")]
        items_complete = not pending_items

        reasons: List[str] = []
        if not contract_signed:
            reasons.append("contract is not signed")
        if not deposit_received:
            reasons.append(
                "no qualifying deposit payment recorded "
                "(payment_type='deposit' with amount >= the invoice's deposit_amount)"
            )
        if not items_complete:
            reasons.append(f"checklist item(s) still pending: {', '.join(pending_items)}")

        return {
            "contract_signed": contract_signed,
            "deposit_received": deposit_received,
            "items_complete": items_complete,
            "pending_items": pending_items,
            "blocking_reasons": reasons,
        }

    def create_handoff_checklist(
        self, project_id: int, actor: AuthContext
    ) -> ProductionHandoffChecklist:
        """Creates the (single, UNIQUE(project_id)) handoff checklist row
        for a project, all 7 items defaulted to 'pending'. Gated on
        PERM_WRITE_PROJECTS -- an operations/production-side action (PM/
        admin/manager tier); ROLE_SALES does not hold this permission
        (B8.12a removed it), so a rep who originated the sale cannot
        author or complete the checklist itself, only read its status
        (see get_handoff_checklist). Creating a checklist does NOT gate
        project creation or production tracking in any way -- a project
        can exist and be worked indefinitely with no checklist row at
        all; this table only gates complete_handoff_checklist.
        """
        if not actor.has_permission(PERM_WRITE_PROJECTS):
            raise PermissionError("Actor lacks permission to create a handoff checklist")

        conn = self.db.get_connection()
        project_row = conn.execute("SELECT id FROM projects WHERE id = ?;", (project_id,)).fetchone()
        if not project_row:
            raise ValueError(f"Project {project_id} not found")

        now = utc_now_iso()
        items = {k: "pending" for k in PRODUCTION_HANDOFF_CHECKLIST_ITEMS}
        items_json = json.dumps(items)

        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO production_handoff_checklists (
                        project_id, items_json, completed_at, completed_by,
                        created_by, created_at, updated_at
                    ) VALUES (?, ?, NULL, NULL, ?, ?, ?);
                    """,
                    (project_id, items_json, actor.user_id, now, now),
                )
                checklist_id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            if "production_handoff_checklists.project_id" in str(exc):
                raise ValueError(
                    f"Project {project_id} already has a handoff checklist"
                ) from exc
            raise

        checklist = ProductionHandoffChecklist(
            id=checklist_id,
            project_id=project_id,
            items=items,
            completed_at=None,
            completed_by=None,
            created_by=actor.user_id,
            created_at=now,
            updated_at=now,
        )

        self.audit.log(
            action="create",
            entity_type="production_handoff_checklist",
            entity_id=checklist_id,
            change_summary=f"Created handoff checklist for project ID {project_id}",
            actor=actor,
            details=build_audit_details(after=checklist.to_dict(), fields=_AUDITABLE_HANDOFF_CHECKLIST_FIELDS),
        )
        return checklist

    def get_handoff_checklist(
        self, project_id: int, actor: AuthContext
    ) -> Optional[Dict[str, Any]]:
        """Read-only. Authorization is delegated entirely to get_project's
        own permission gate + B8.12a rep-ownership narrowing (raises
        PermissionError / returns None exactly as get_project does) --
        a single source of truth for "can this actor see this project",
        rather than a second copy of that narrowing here. Returns the
        checklist merged with the live guard-condition status (see
        _evaluate_handoff_conditions) so a caller -- in particular the UI
        -- can render each condition's pass/fail state and a clear reason
        without attempting (and failing) a real completion call. Returns
        None if the project has no checklist row yet (this is normal, not
        an error -- see create_handoff_checklist's docstring)."""
        project = self.get_project(project_id, actor)
        if project is None:
            return None

        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM production_handoff_checklists WHERE project_id = ?;",
            (project_id,),
        ).fetchone()
        if not row:
            return None

        checklist = self._row_to_handoff_checklist(row)
        result = checklist.to_dict()
        if checklist.completed_at is None:
            result["guard"] = self._evaluate_handoff_conditions(project_id, checklist.items)
        else:
            # Already completed -- guard conditions are moot; report as
            # fully satisfied rather than re-running (a condition, e.g. a
            # contract, could theoretically change status after
            # completion, and this must not make an already-completed
            # checklist appear to "fail" retroactively).
            result["guard"] = {
                "contract_signed": True,
                "deposit_received": True,
                "items_complete": True,
                "pending_items": [],
                "blocking_reasons": [],
            }
        return result

    def update_handoff_checklist_item(
        self, project_id: int, item: str, status: str, actor: AuthContext
    ) -> ProductionHandoffChecklist:
        """Marks a single checklist item 'done' or 'na' (or back to
        'pending'). Gated on PERM_WRITE_PROJECTS, same tier as
        create_handoff_checklist. Rejected once the checklist is
        completed (completed_at is not None) -- a completed checklist's
        items must not be silently edited after the fact; the caller must
        go through whatever un-complete path a future round designs (none
        exists this round -- completion is a one-way gate, mirroring
        sign_contract's own idempotency convention)."""
        if not actor.has_permission(PERM_WRITE_PROJECTS):
            raise PermissionError("Actor lacks permission to update a handoff checklist")

        if item not in PRODUCTION_HANDOFF_CHECKLIST_ITEMS:
            raise ValueError(
                f"Invalid checklist item '{item}'; must be one of {list(PRODUCTION_HANDOFF_CHECKLIST_ITEMS)}"
            )
        if status not in PRODUCTION_HANDOFF_ITEM_STATUSES:
            raise ValueError(
                f"Invalid item status '{status}'; must be one of {list(PRODUCTION_HANDOFF_ITEM_STATUSES)}"
            )

        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM production_handoff_checklists WHERE project_id = ?;",
            (project_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Project {project_id} has no handoff checklist")

        if row["completed_at"] is not None:
            raise ValueError(
                f"Handoff checklist for project {project_id} is already completed; "
                f"items cannot be modified"
            )

        _before = self._row_to_handoff_checklist(row).to_dict()

        items = json.loads(row["items_json"]) if row["items_json"] else {}
        items[item] = status
        now = utc_now_iso()
        items_json = json.dumps(items)

        with conn:
            conn.execute(
                "UPDATE production_handoff_checklists SET items_json = ?, updated_at = ? WHERE id = ?;",
                (items_json, now, row["id"]),
            )

        updated = ProductionHandoffChecklist(
            id=row["id"],
            project_id=project_id,
            items=items,
            completed_at=None,
            completed_by=row["completed_by"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=now,
        )

        self.audit.log(
            action="update",
            entity_type="production_handoff_checklist",
            entity_id=row["id"],
            change_summary=f"Set handoff checklist item '{item}' to '{status}' for project {project_id}",
            actor=actor,
            details=build_audit_details(before=_before, after=updated.to_dict(), fields=_AUDITABLE_HANDOFF_CHECKLIST_FIELDS),
        )
        return updated

    def complete_handoff_checklist(
        self, project_id: int, actor: AuthContext
    ) -> ProductionHandoffChecklist:
        """The guarded completion action (B8.12b's central rule 4-category
        guard). Blocks completion ONLY -- never project creation or
        production tracking, see create_handoff_checklist's docstring.
        Raises ValueError identifying every specific unmet condition (not
        a generic message) via _evaluate_handoff_conditions' shared
        reasons list. Idempotency: re-completing an already-completed
        checklist raises, mirroring sign_contract's own "already signed"
        convention, rather than silently no-op'ing or re-stamping
        completed_at/completed_by."""
        if not actor.has_permission(PERM_WRITE_PROJECTS):
            raise PermissionError("Actor lacks permission to complete a handoff checklist")

        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM production_handoff_checklists WHERE project_id = ?;",
            (project_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"Project {project_id} has no handoff checklist")

        if row["completed_at"] is not None:
            raise ValueError(f"Handoff checklist for project {project_id} is already completed")

        _before = self._row_to_handoff_checklist(row).to_dict()
        items = json.loads(row["items_json"]) if row["items_json"] else {}

        conditions = self._evaluate_handoff_conditions(project_id, items)
        if conditions["blocking_reasons"]:
            raise ValueError(
                f"Cannot complete handoff checklist for project {project_id}: "
                + "; ".join(conditions["blocking_reasons"])
            )

        now = utc_now_iso()
        with conn:
            conn.execute(
                """
                UPDATE production_handoff_checklists
                SET completed_at = ?, completed_by = ?, updated_at = ?
                WHERE id = ?;
                """,
                (now, actor.user_id, now, row["id"]),
            )

        updated = ProductionHandoffChecklist(
            id=row["id"],
            project_id=project_id,
            items=items,
            completed_at=now,
            completed_by=actor.user_id,
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=now,
        )

        self.audit.log(
            action="complete",
            entity_type="production_handoff_checklist",
            entity_id=row["id"],
            change_summary=f"Completed handoff checklist for project {project_id}",
            actor=actor,
            details=build_audit_details(before=_before, after=updated.to_dict(), fields=_AUDITABLE_HANDOFF_CHECKLIST_FIELDS),
        )
        return updated

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
            user_id=row["user_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_subcontractor(
        self, sub: Subcontractor, actor: AuthContext,
        created_at: Optional[str] = None, updated_at: Optional[str] = None,
    ) -> Subcontractor:
        # NEW-218 (service-layer half): explicit override kwargs so a caller
        # migrating a record with a known source created_at/updated_at can
        # preserve it instead of getting "now" stamped on both. Currently
        # unused -- no existing caller passes them, so this is a
        # zero-behavior-change addition for every current call site.
        if not actor.has_permission(PERM_WRITE_SUBCONTRACTORS):
            raise PermissionError("Actor lacks permission to create subcontractors")

        now = utc_now_iso()
        sub.created_at = created_at or now
        sub.updated_at = updated_at or now
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
                    notes, qualification_data_json, user_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                    sub.user_id,
                    sub.created_at,
                    sub.updated_at,
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
        "user_id",
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

        if "qualification_data" in updates and not isinstance(updates["qualification_data"], dict):
            raise ValueError("Field 'qualification_data' must be a dict")
        if "secondary_trades" in updates and not isinstance(updates["secondary_trades"], list):
            raise ValueError("Field 'secondary_trades' must be a list")

        updates = dict(updates)
        if "email" in updates:
            _email = updates["email"].strip().lower()
            updates["email"] = _email if _email else None
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

    def _get_subcontractor_unguarded(self, subcontractor_id: int) -> Optional[Subcontractor]:
        """Unguarded row fetch -- no PERM_READ_SUBCONTRACTORS check.
        Mirrors AuthService.get_user_by_id, the analogous unguarded lookup
        the DELETE /api/v1/users/<id> route relies on: a caller authorized
        on PERM_WRITE_SUBCONTRACTORS alone (no READ) must still be able to
        look up the row it's about to delete (NEW-507, Delete-buttons
        round precedent, 2026-09-11)."""
        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM subcontractors WHERE id = ?;", (subcontractor_id,)).fetchone()
        if not row:
            return None
        return self._row_to_subcontractor(row)

    def delete_subcontractor(self, subcontractor_id: int, actor: AuthContext) -> bool:
        """Delete a subcontractor (NEW-507, Delete-buttons round precedent,
        Ish 2026-09-11). No archive step needed: subcontractors.user_id
        has no FK at all (NEW-494), and the one real inbound FK
        (work_orders.assigned_subcontractor_id) is ON DELETE SET NULL at
        the DB level, so the row delete itself is mechanically safe.

        NEW-510: the active-reference precheck (a linked user's active
        staff_schedules, and the subcontractor's own non-terminal
        work_orders) used to live ONLY in the /delete route handler in
        routes.py, so any other caller of this method bypassed it
        entirely. Moved in here so the guard applies to every caller, not
        just the HTTP route. Permission check now runs first (this is no
        longer just a defense-in-depth re-check after the route's own
        gate -- see the corrected comment at the route call site)."""
        if not actor.has_permission(PERM_WRITE_SUBCONTRACTORS):
            raise PermissionError("Actor lacks permission to delete subcontractors")

        sub = self._get_subcontractor_unguarded(subcontractor_id)
        if not sub:
            return False

        active_schedules: List[Dict[str, Any]] = []
        if sub.user_id is not None:
            active_schedules = self.scheduling._query_active_staff_schedules_for_user(sub.user_id)
        active_work_orders = self.operations._query_active_work_orders_for_subcontractor(subcontractor_id)
        if active_schedules or active_work_orders:
            parts = []
            if active_schedules:
                itemized = "; ".join(
                    f"id {s['id']}: {s['title']} ({s['start_time']})" for s in active_schedules
                )
                parts.append(f"{len(active_schedules)} active staff schedule(s) reference this record: {itemized}")
            if active_work_orders:
                itemized_wo = "; ".join(
                    f"id {w['id']}: {w['work_order_number']} ({w['status']})" for w in active_work_orders
                )
                parts.append(f"{len(active_work_orders)} active work order(s) reference this record: {itemized_wo}")
            raise ValueError("Cannot delete: " + " AND ".join(parts))

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute("DELETE FROM subcontractors WHERE id = ?;", (subcontractor_id,))
            if cursor.rowcount == 0:
                return False

        # B8.13a: audit call moved in here from the /delete route handler
        # so any caller of this method (not just the HTTP route) produces
        # an audited hard DELETE. Matches delete_contact's pattern (audit
        # call inside the service method, after the DELETE commits, using
        # the pre-delete snapshot).
        self.audit.log(
            "subcontractor_deleted", "subcontractor", subcontractor_id,
            f"Subcontractor '{sub.company_name}' deleted",
            actor=actor, details=build_audit_details(snapshot=sub.to_dict()),
        )
        return True

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

