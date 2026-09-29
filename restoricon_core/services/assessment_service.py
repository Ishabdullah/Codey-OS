"""
Assessment Records Domain Engine for Restoricon Core (B8.5b,
sales_rep_portal.md §5/§6/§7).

Resolves NEW-567's deferred decision: property -> assessment_record ->
documents (via evidence_document_ids) is the real mechanism for
pre-project property photos -- deliberately NOT a Document.property_id
schema change. See database.py's assessment_records DDL comment.

Minimal surface per B8.5b's scope: create_assessment_record (create),
get_assessment_record (read one), list_assessment_records (read,
filterable by appointment_id and/or property_id) -- there is no
update/delete in this round, mirroring how Property/CommissionService
were scoped for their first cut.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..auth import AuthContext, PERM_READ_ALL_CUSTOMERS, PERM_WRITE_CUSTOMERS
from ..database import DatabaseManager
from ..models import AssessmentRecord, utc_now_iso
from .audit_service import AuditService, build_audit_details


class AssessmentService:
    """Manages assessment_records. Gated on PERM_WRITE_CUSTOMERS /
    PERM_READ_ALL_CUSTOMERS -- the same permissions that already gate
    Property CRUD (crm_service.py's PROPERTIES section) and Customer CRUD,
    rather than a new PERM_READ_ASSESSMENTS/PERM_WRITE_ASSESSMENTS pair:
    an assessment record carries no more sensitivity than a property or
    customer record already does, and no ownership-narrowing concept
    exists for properties either (no assigned_user_id to narrow on)."""

    def __init__(self, db: DatabaseManager, audit: AuditService):
        self.db = db
        self.audit = audit

    @staticmethod
    def _row_to_record(row: Any) -> AssessmentRecord:
        checklist = json.loads(row["checklist_json"]) if row["checklist_json"] else {}
        evidence_document_ids = (
            json.loads(row["evidence_document_ids_json"]) if row["evidence_document_ids_json"] else []
        )
        return AssessmentRecord(
            id=row["id"],
            appointment_id=row["appointment_id"],
            property_id=row["property_id"],
            checklist=checklist,
            evidence_document_ids=evidence_document_ids,
            customer_statements=row["customer_statements"],
            created_by=row["created_by"],
            created_at=row["created_at"],
        )

    def create_assessment_record(
        self, record: AssessmentRecord, actor: AuthContext
    ) -> AssessmentRecord:
        if not actor.has_permission(PERM_WRITE_CUSTOMERS):
            raise PermissionError("Actor lacks permission to create assessment records")

        now = utc_now_iso()
        record.created_at = now
        record.created_by = actor.user_id
        checklist_json = json.dumps(record.checklist)
        evidence_document_ids_json = json.dumps(record.evidence_document_ids)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO assessment_records (
                    appointment_id, property_id, checklist_json,
                    evidence_document_ids_json, customer_statements,
                    created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.appointment_id,
                    record.property_id,
                    checklist_json,
                    evidence_document_ids_json,
                    record.customer_statements,
                    record.created_by,
                    now,
                ),
            )
            record.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="assessment_record",
            entity_id=record.id,
            change_summary=f"Created assessment record for property_id={record.property_id}, appointment_id={record.appointment_id}",
            actor=actor,
            details=build_audit_details(after=record.to_dict()),
        )
        return record

    def get_assessment_record(
        self, record_id: int, actor: AuthContext
    ) -> Optional[AssessmentRecord]:
        if not actor.has_permission(PERM_READ_ALL_CUSTOMERS):
            raise PermissionError("Actor lacks permission to view assessment records")

        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM assessment_records WHERE id = ?;", (record_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def list_assessment_records(
        self,
        actor: AuthContext,
        appointment_id: Optional[int] = None,
        property_id: Optional[int] = None,
    ) -> List[AssessmentRecord]:
        if not actor.has_permission(PERM_READ_ALL_CUSTOMERS):
            raise PermissionError("Actor lacks permission to list assessment records")

        query = "SELECT * FROM assessment_records WHERE 1=1"
        params: List[Any] = []
        if appointment_id is not None:
            query += " AND appointment_id = ?"
            params.append(appointment_id)
        if property_id is not None:
            query += " AND property_id = ?"
            params.append(property_id)
        query += " ORDER BY id DESC;"

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_record(r) for r in rows]
