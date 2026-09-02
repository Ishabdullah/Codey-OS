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


def build_audit_details(
    *,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    fields: Optional[Iterable[str]] = None,
    side_effects: Optional[Dict[str, Any]] = None,
    snapshot: Optional[Dict[str, Any]] = None,
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
