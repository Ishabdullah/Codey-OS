"""
Day-One-or-Never Append-Only Audit Log Service for Restoricon Core.
Records every human and AI agent action with actor, timestamp, action type,
and entity details. Strict append-only semantics.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

from ..auth import AuthContext, PERM_READ_AUDIT_LOG
from ..database import DatabaseManager
from ..models import AuditRecord, utc_now_iso


# Fields that are safe to surface as old/new values in a user-entity audit
# payload. Used as the diff domain / filter by the api/routes.py user-mutation
# sites. This is an allow-list rather than a try/except around json.dumps
# because AuditService.log serializes `details` with an *unguarded*
# json.dumps that runs AFTER the mutation's `with conn:` block has already
# committed -- a serialization failure there would raise past a committed row
# with no audit trail. Keeping password_hash / raw passwords / unserializable
# objects out of the payload by construction is the only safe design.
_AUDITABLE_USER_FIELDS = frozenset({
    "full_name", "email", "phone", "role", "department",
    "customer_id", "custom_permissions", "active",
})

# NEW-314: Contract diff domain -- excludes customer_signature_data / content.
_AUDITABLE_CONTRACT_FIELDS = frozenset({
    "id", "contract_number", "customer_id", "project_id", "estimate_id",
    "title", "template_name", "status", "customer_signed_at", "version",
    "created_at", "updated_at",
})

# NEW-314: Invoice diff domain -- excludes payments.
_AUDITABLE_INVOICE_FIELDS = frozenset({
    "id", "invoice_number", "customer_id", "project_id", "status", "amount",
    "deposit_amount", "balance_due", "due_date", "notes",
    "created_at", "updated_at",
})

# NEW-314: Subcontractor diff domain -- excludes license_number,
# general_liability, workers_comp, references, qualification_data.
_AUDITABLE_SUBCONTRACTOR_FIELDS = frozenset({
    "id", "external_id", "contact_external_id", "company_name", "legal_name",
    "dba", "contact_name", "title", "phone", "email", "website",
    "primary_trade", "secondary_trades", "service_area", "years_in_business",
    "crew_size", "residential_experience", "commercial_experience",
    "typical_project_size", "availability", "emergency_availability",
    "license_required", "license_type", "license_expiration", "license_status",
    "coi_received", "coi_expiration", "additional_insured_status",
    "insurance_status", "w9_received", "msa_sent", "msa_signed",
    "portfolio_url", "qualification_status", "recruitment_step", "lead_source",
    "last_contact_at", "next_followup_at", "contact_attempts", "dnc_status",
    "notes", "created_at", "updated_at",
})

# NEW-314: Employee diff domain -- excludes hourly_rate / emergency_contact.
_AUDITABLE_EMPLOYEE_FIELDS = frozenset({
    "id", "user_id", "first_name", "last_name", "role_title", "department",
    "phone", "email", "hire_date", "status", "created_at", "updated_at",
})

# NEW-314: Project diff domain. Unlike the other NEW-314 constants this
# excludes nothing -- Project carries no secret/PII-grade fields. It exists
# as a drift guard: a future Project field cannot enter the audit payload
# without an edit here (mirrors _AUDITABLE_USER_FIELDS' rationale).
_AUDITABLE_PROJECT_FIELDS = frozenset({
    "id", "customer_id", "title", "property_address", "project_type",
    "status", "stage", "start_date", "expected_completion",
    "actual_completion", "project_manager_id", "assigned_employees",
    "subcontractors", "scope_of_work", "estimated_cost", "contract_amount",
    "actual_cost", "profit", "notes", "warranty_info", "stage_entered_at",
    "insurance_claim_number", "insurance_carrier", "adjuster_name",
    "adjuster_phone", "adjuster_email", "deductible", "created_at",
    "updated_at",
})

# NEW-314: WorkOrder diff domain. Excludes nothing -- WorkOrder carries no
# secret/PII-grade columns. Drift guard only: a future WorkOrder field cannot
# enter the audit payload without an edit here. Key is `line_items` (the
# to_dict key), not the `line_items_json` column.
_AUDITABLE_WORK_ORDER_FIELDS = frozenset({
    "id", "work_order_number", "title", "project_id", "trade",
    "assigned_subcontractor_id", "assigned_crew_lead", "scheduled_start",
    "scheduled_end", "actual_start", "actual_end", "status", "line_items",
    "total_cost", "instructions", "notes", "dispatched_at", "accepted_at",
    "completed_at", "verified_at", "created_at", "updated_at",
})

# NEW-314: ProjectMilestone diff domain. Excludes nothing -- no secret/PII
# columns. Drift guard only. Includes `dependencies` (the to_dict key).
_AUDITABLE_MILESTONE_FIELDS = frozenset({
    "id", "project_id", "name", "stage", "target_date", "completion_date",
    "status", "dependencies", "notes", "created_at", "updated_at",
})

# NEW-314: Equipment diff domain. Excludes nothing -- no secret/PII columns.
# Drift guard only.
_AUDITABLE_EQUIPMENT_FIELDS = frozenset({
    "id", "asset_tag", "name", "category", "model_number", "serial_number",
    "status", "daily_rate", "current_project_id", "notes", "created_at",
    "updated_at",
})

# NEW-314: EquipmentDeployment diff domain. Excludes nothing -- no secret/PII
# columns. Drift guard only. Used solely for the nested side_effects diff in
# return_equipment, never as a top-level `fields=` domain.
_AUDITABLE_DEPLOYMENT_FIELDS = frozenset({
    "id", "equipment_id", "project_id", "work_order_id", "deployed_at",
    "return_due_at", "returned_at", "deployed_by_user_id",
    "received_by_user_id", "condition_out", "condition_in", "initial_reading",
    "final_reading", "notes", "created_at", "updated_at",
})

# NEW-314: Contact diff domain -- excludes license_number and references,
# mirroring _AUDITABLE_SUBCONTRACTOR_FIELDS' exclusion rationale:
# license_number is a credential; references is a JSON list of third-party
# names/phones. phones/emails are KEPT (precedent: _AUDITABLE_USER_FIELDS
# audits email/phone).
_AUDITABLE_CONTACT_FIELDS = frozenset({
    "id", "external_id", "name", "aliases", "phones", "emails", "address",
    "relationship", "type", "notes", "instructions", "reply_behavior",
    "roles", "active_role", "business_name", "trade", "trade_raw", "licensed",
    "gl_insurance", "wc_insurance", "has_tools", "crew_size",
    "weekly_capacity", "source", "first_seen", "last_contact",
    "contact_count", "history", "created_at", "updated_at",
})

# NEW-314: Appointment diff domain. Excludes nothing -- Appointment carries
# no secret/PII-grade fields. Drift guard only (mirrors
# _AUDITABLE_PROJECT_FIELDS' rationale).
_AUDITABLE_APPOINTMENT_FIELDS = frozenset({
    "id", "external_id", "uid", "ics_sequence", "title", "start_time",
    "end_time", "customer_id", "contact_external_id", "attendee_name",
    "attendee_email", "appointment_type", "appointment_type_id", "status", "rsvp_status",
    "offered_slots", "requested_datetime", "pending_reschedule", "form_sent",
    "created_via", "notes", "history", "created_at", "updated_at",
})

# Final scheduling round Phase 2: AppointmentType diff domain. Excludes
# nothing -- AppointmentType carries no secret/PII-grade fields. Drift
# guard only (mirrors _AUDITABLE_APPOINTMENT_FIELDS' rationale). Uses the
# dataclass field name `scheduling_hours` (not the `_json` column) since
# build_audit_details sees to_dict() keys.
_AUDITABLE_APPOINTMENT_TYPE_FIELDS = frozenset({
    "id", "name", "active", "sort_order", "max_concurrent",
    "scheduling_hours", "created_at", "updated_at",
})

# NEW-314: ReviewRequest diff domain. Excludes nothing -- drift guard only.
_AUDITABLE_REVIEW_REQUEST_FIELDS = frozenset({
    "id", "customer_id", "project_id", "platform", "rating", "feedback",
    "status", "sent_at", "completed_at", "created_at",
})

# NEW-314: PurchaseOrder diff domain. Excludes nothing -- drift guard only.
_AUDITABLE_PURCHASE_ORDER_FIELDS = frozenset({
    "id", "po_number", "vendor_id", "project_id", "status", "items",
    "subtotal", "tax_amount", "total_amount", "ordered_date", "expected_date",
    "received_date", "notes", "created_at", "updated_at",
})


def build_audit_details(
    *,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    fields: Optional[Iterable[str]] = None,
    side_effects: Optional[Dict[str, Any]] = None,
    snapshot: Optional[Dict[str, Any]] = None,
    snapshot_fields: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Build the canonical audit-details envelope for a mutation.

    The envelope has up to three slots -- ``changed_fields`` (a
    ``{field: {"old": <v>, "new": <v>}}`` map derived by diffing ``before``
    against ``after``), ``side_effects`` (verbatim), and ``snapshot``
    (verbatim) -- and each slot is omitted when empty. ``old`` comes from
    ``before`` and ``new`` from ``after``; both must be already-sanitized
    plain dicts (e.g. ``User.to_dict()``), never model objects, because this
    payload is handed to ``AuditService.log`` which json.dumps it *unguarded*
    and *after* the caller's transaction has already committed -- an
    unserializable value would raise past a committed row. For that reason
    ``changed_fields`` keys are additionally filtered to ``fields`` when a
    diff domain is supplied, so within ``changed_fields`` a stray
    ``password_hash`` or raw password can never reach serialization even if
    the caller passes a fuller dict. This filter applies to
    ``changed_fields`` only -- ``side_effects`` and ``snapshot`` pass through
    verbatim and unfiltered, so their callers are responsible for not
    handing in sensitive or unserializable values.
    """
    details: Dict[str, Any] = {}

    if before is not None or after is not None:
        b = before or {}
        a = after or {}
        if fields is not None:
            domain: Iterable[str] = fields
        else:
            domain = set(b) | set(a)

        changed: Dict[str, Any] = {}
        for key in domain:
            in_b = key in b
            in_a = key in a
            if not in_b and not in_a:
                continue
            old = b.get(key)
            new = a.get(key)
            if in_b and in_a and old == new:
                continue
            changed[key] = {"old": old, "new": new}

        if changed:
            details["changed_fields"] = changed

    if side_effects:
        details["side_effects"] = side_effects

    if snapshot:
        if snapshot_fields is not None:
            details["snapshot"] = {k: v for k, v in snapshot.items() if k in snapshot_fields}
        else:
            details["snapshot"] = snapshot

    return details


class AuditService:
    """Provides append-only activity and audit logging."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def log(
        self,
        action: str,
        entity_type: str,
        entity_id: Optional[int],
        change_summary: str,
        actor: Optional[AuthContext] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditRecord:
        """
        Record an immutable audit event in the database.
        Cannot be updated or deleted through the service interface.
        """
        now = utc_now_iso()
        actor_id = actor.user_id if actor else None
        actor_role = actor.role if actor else "system"
        actor_type = actor.actor_type if actor else "agent"
        details_json = json.dumps(details or {})

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_log (
                    timestamp, actor_id, actor_role, actor_type,
                    action, entity_type, entity_id, change_summary, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    now,
                    actor_id,
                    actor_role,
                    actor_type,
                    action,
                    entity_type,
                    entity_id,
                    change_summary,
                    details_json,
                ),
            )
            audit_id = cursor.lastrowid

        return AuditRecord(
            id=audit_id,
            timestamp=now,
            actor_id=actor_id,
            actor_role=actor_role,
            actor_type=actor_type,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            change_summary=change_summary,
            details=details or {},
        )

    def query_logs(
        self,
        actor_context: AuthContext,
        entity_type: Optional[str] = None,
        entity_id: Optional[int] = None,
        actor_id: Optional[int] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditRecord]:
        """Query audit log entries. Restricted to authorized staff roles (Admin/Manager)."""
        if not actor_context.has_permission(PERM_READ_AUDIT_LOG):
            raise PermissionError("Actor lacks permission to view audit log")

        query = "SELECT * FROM audit_log WHERE 1=1"
        params: List[Any] = []

        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type)

        if entity_id is not None:
            query += " AND entity_id = ?"
            params.append(entity_id)

        if actor_id is not None:
            query += " AND actor_id = ?"
            params.append(actor_id)

        if action:
            query += " AND action = ?"
            params.append(action)

        query += " ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()

        records = []
        for row in rows:
            details = {}
            if row["details_json"]:
                try:
                    details = json.loads(row["details_json"])
                except Exception:
                    details = {}
            records.append(
                AuditRecord(
                    id=row["id"],
                    timestamp=row["timestamp"],
                    actor_id=row["actor_id"],
                    actor_role=row["actor_role"],
                    actor_type=row["actor_type"],
                    action=row["action"],
                    entity_type=row["entity_type"],
                    entity_id=row["entity_id"],
                    change_summary=row["change_summary"],
                    details=details,
                )
            )
        return records
