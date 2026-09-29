"""
Financing Records Domain Engine for Restoricon Core (B8.8b-1,
sales_rep_portal.md §4/§8).

DELIBERATELY INERT this round: table + CRUD + RBAC only, reads into
nothing else. B8.8b-2 (a separate, higher-scrutiny round -- Ish decided
2026-09-23 that a recorded financed amount should offset AR, a rule-4
money computation) will wire FinancingRecord.amount_financed into
FinanceService.get_ar_aging/get_financial_summary/get_project_pnl as an
AR offset for records whose application_status IN ('approved', 'funded')
AND status == 'active' -- BOTH conditions together, never
application_status alone: voiding a record does NOT clear
application_status, so a voided 'approved' record must still be
excluded via status='active'. That eligibility concept belongs entirely
to B8.8b-2 -- it is NOT used as a business-logic concept anywhere in
this file, only as the partial unique index's WHERE clause (a
structural double-financing guard, not offset math).

Minimal surface per B8.8b-1's scope: create_financing_record,
update_financing_record (allow-list enforced, mirrors update_contract's
shape -- invoice_id IS in the allow-list, since the table's whole
nullable-invoice_id design exists so financing can be recorded before
the invoice does, then linked later), get_financing_record,
list_financing_records_for_project. Gated on PERM_WRITE_CUSTOMERS
(write) / PERM_READ_FINANCIALS (read) -- matches the assessment_records
precedent for write (ROLE_SALES already holds PERM_WRITE_CUSTOMERS) and
the NEW-565 invoice-adjacent-visibility precedent for read (ROLE_SALES
already holds PERM_READ_FINANCIALS). Every base role holding
PERM_WRITE_CUSTOMERS also holds PERM_READ_FINANCIALS (verified directly
against auth.ROLE_PERMISSIONS), so update_financing_record's no-op path
(empty updates dict falls through to get_financing_record, a different
permission domain) cannot itself deny a legitimate writer -- this could
only diverge under the pre-existing NEW-306 custom_permissions sharp
edge, not a gap this round introduces.

KNOWN, ACCEPTED LIMITATIONS carried into B8.8b-2 (not fixed here,
logged as NEW-614 -- B8.8b-2 must design its offset query around BOTH):
1. idx_financing_records_invoice_active is inert for rows with
   invoice_id IS NULL (SQLite treats NULLs as distinct in a UNIQUE
   index, same as idx_commission_ledger_source_unique's own documented
   NULL hole). Two 'approved'/'funded' financing records on the SAME
   project but both with invoice_id still NULL are not blocked by this
   index -- since get_project_pnl's offset (once B8.8b-2 wires it) is
   project-scoped, not invoice-scoped, this is a real double-count
   exposure.
2. The index also does not protect against a VOIDED 'approved'/'funded'
   record coexisting with an active one on the SAME invoice_id (voiding
   never clears application_status, and the index's own WHERE clause
   already excludes status != 'active' rows from the constraint, so a
   voided row simply falls outside it entirely). B8.8b-2's offset query
   MUST filter on status='active' AND application_status IN
   ('approved','funded') together -- application_status alone is not
   sufficient, see this module's own docstring above.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from ..auth import AuthContext, PERM_READ_FINANCIALS, PERM_WRITE_CUSTOMERS
from ..database import DatabaseManager
from ..models import FinancingRecord, utc_now_iso
from .audit_service import AuditService, build_audit_details, _AUDITABLE_FINANCING_RECORD_FIELDS

_VALID_APPLICATION_STATUSES = {"submitted", "approved", "funded", "denied", "cancelled"}
_VALID_STATUSES = {"active", "voided"}


class FinancingService:
    """Manages financing_records. See module docstring for scope and the
    money-computation isolation this round deliberately preserves."""

    # invoice_id is deliberately updatable (not just create-time): the
    # table's own nullable-invoice_id design exists specifically so
    # financing can be recorded before the invoice does, then linked
    # later via update_financing_record -- excluding it here would make
    # that link-later step impossible. project_id is NOT updatable
    # (mirrors ALLOWED_CONTRACT_UPDATE_FIELDS excluding customer_id/
    # project_id -- an entity's owning project is fixed at create time).
    ALLOWED_FINANCING_RECORD_UPDATE_FIELDS = {
        "invoice_id",
        "provider",
        "application_status",
        "amount_financed",
        "customer_contribution",
        "document_ids",
        "status",
    }

    def __init__(self, db: DatabaseManager, audit: AuditService):
        self.db = db
        self.audit = audit

    @staticmethod
    def _row_to_record(row: Any) -> FinancingRecord:
        document_ids = json.loads(row["document_ids_json"]) if row["document_ids_json"] else []
        return FinancingRecord(
            id=row["id"],
            project_id=row["project_id"],
            invoice_id=row["invoice_id"],
            provider=row["provider"],
            application_status=row["application_status"],
            amount_financed=float(row["amount_financed"]),
            customer_contribution=float(row["customer_contribution"]),
            document_ids=document_ids,
            status=row["status"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _validate_application_status(value: str) -> None:
        if value not in _VALID_APPLICATION_STATUSES:
            raise ValueError(
                f"Invalid application_status '{value}'; must be one of {sorted(_VALID_APPLICATION_STATUSES)}"
            )

    @staticmethod
    def _validate_status(value: str) -> None:
        if value not in _VALID_STATUSES:
            raise ValueError(f"Invalid status '{value}'; must be one of {sorted(_VALID_STATUSES)}")

    @staticmethod
    def _validate_non_negative_amount(field_name: str, value: float) -> None:
        # code-reviewer finding (B8.8b-1 review): amount_financed had no
        # guard, unlike FinanceService.record_transaction's sibling
        # money-writer (which rejects amount <= 0). A negative
        # amount_financed would silently INCREASE reported AR once
        # B8.8b-2 wires the offset -- nothing reads this field yet, but
        # the guard belongs here now, while the service is still small,
        # not deferred to B8.8b-2's read side. customer_contribution
        # guarded identically for the same reason (it's also money on
        # this row), even though it's excluded from the AR offset itself.
        if value < 0:
            raise ValueError(f"'{field_name}' cannot be negative, got {value}")

    @staticmethod
    def _round_money_fields(record: FinancingRecord) -> None:
        # code-reviewer finding (B8.8b-2 review): _validate_non_negative_amount
        # never rounded, so a sub-cent amount_financed (e.g. 166.665) could
        # make B8.8b-2's "total_ar_gross - total_financed_offset == total_ar"
        # reconciliation identity off by a cent across several invoices --
        # not a regression B8.8b-2 introduced (the gap is here, at the
        # write side), but the right place to close it is at the source,
        # not by making every downstream AR computation defensive against
        # sub-cent currency that should never have been stored in the
        # first place. Rounded in-place before validation/storage, same
        # 2-decimal-place currency convention every other money field in
        # this codebase uses (round(x, 2) at write time).
        record.amount_financed = round(record.amount_financed, 2)
        record.customer_contribution = round(record.customer_contribution, 2)

    def create_financing_record(
        self, record: FinancingRecord, actor: AuthContext
    ) -> FinancingRecord:
        if not actor.has_permission(PERM_WRITE_CUSTOMERS):
            raise PermissionError("Actor lacks permission to create financing records")

        self._validate_application_status(record.application_status)
        self._validate_status(record.status)
        self._round_money_fields(record)
        self._validate_non_negative_amount("amount_financed", record.amount_financed)
        self._validate_non_negative_amount("customer_contribution", record.customer_contribution)

        now = utc_now_iso()
        record.created_at = now
        record.updated_at = now
        record.created_by = actor.user_id
        document_ids_json = json.dumps(record.document_ids)

        conn = self.db.get_connection()
        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO financing_records (
                        project_id, invoice_id, provider, application_status,
                        amount_financed, customer_contribution, document_ids_json,
                        status, created_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        record.project_id,
                        record.invoice_id,
                        record.provider,
                        record.application_status,
                        record.amount_financed,
                        record.customer_contribution,
                        document_ids_json,
                        record.status,
                        record.created_by,
                        now,
                        now,
                    ),
                )
                record.id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            if "financing_records.invoice_id" in str(exc):
                raise ValueError(
                    f"Invoice {record.invoice_id} already has an active "
                    f"approved/funded financing record; cannot create a second one"
                ) from exc
            raise

        self.audit.log(
            action="create",
            entity_type="financing_record",
            entity_id=record.id,
            change_summary=(
                f"Created financing record for project_id={record.project_id}, "
                f"invoice_id={record.invoice_id}, amount_financed={record.amount_financed:.2f}"
            ),
            actor=actor,
            details=build_audit_details(after=record.to_dict(), fields=_AUDITABLE_FINANCING_RECORD_FIELDS),
        )
        return record

    def update_financing_record(
        self, record_id: int, updates: Dict[str, Any], actor: AuthContext
    ) -> Optional[FinancingRecord]:
        if not actor.has_permission(PERM_WRITE_CUSTOMERS):
            raise PermissionError("Actor lacks permission to update financing records")

        unknown = set(updates) - self.ALLOWED_FINANCING_RECORD_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unknown field(s) for financing record update: {sorted(unknown)}")

        for key, value in updates.items():
            if value is None:
                raise ValueError(
                    f"Field '{key}' cannot be set to None via update_financing_record; omit the key instead"
                )

        if "application_status" in updates:
            self._validate_application_status(updates["application_status"])
        if "status" in updates:
            self._validate_status(updates["status"])
        # Round before validating/storing -- same sub-cent-currency fix as
        # create_financing_record's _round_money_fields, applied here
        # in-place on the updates dict since update's record is built via
        # setattr from this dict further down, not via _round_money_fields
        # itself (which takes a FinancingRecord, not a raw updates dict).
        if "amount_financed" in updates:
            updates["amount_financed"] = round(updates["amount_financed"], 2)
            self._validate_non_negative_amount("amount_financed", updates["amount_financed"])
        if "customer_contribution" in updates:
            updates["customer_contribution"] = round(updates["customer_contribution"], 2)
            self._validate_non_negative_amount("customer_contribution", updates["customer_contribution"])

        if not updates:
            return self.get_financing_record(record_id, actor)

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM financing_records WHERE id = ?;", (record_id,)).fetchone()
        if not row:
            return None

        record = self._row_to_record(row)
        _before = record.to_dict()

        for key, value in updates.items():
            setattr(record, key, value)

        now = utc_now_iso()
        record.updated_at = now
        document_ids_json = json.dumps(record.document_ids)

        try:
            with conn:
                conn.execute(
                    """
                    UPDATE financing_records SET
                        invoice_id = ?, provider = ?, application_status = ?,
                        amount_financed = ?, customer_contribution = ?,
                        document_ids_json = ?, status = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (
                        record.invoice_id,
                        record.provider,
                        record.application_status,
                        record.amount_financed,
                        record.customer_contribution,
                        document_ids_json,
                        record.status,
                        now,
                        record_id,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if "financing_records.invoice_id" in str(exc):
                raise ValueError(
                    f"Invoice {record.invoice_id} already has an active "
                    f"approved/funded financing record; cannot update this "
                    f"record into that same state"
                ) from exc
            raise

        self.audit.log(
            action="update",
            entity_type="financing_record",
            entity_id=record_id,
            change_summary=f"Updated financing record {record_id}",
            actor=actor,
            details=build_audit_details(before=_before, after=record.to_dict(), fields=_AUDITABLE_FINANCING_RECORD_FIELDS),
        )
        updated_row = conn.execute("SELECT * FROM financing_records WHERE id = ?;", (record_id,)).fetchone()
        return self._row_to_record(updated_row)

    def get_financing_record(
        self, record_id: int, actor: AuthContext
    ) -> Optional[FinancingRecord]:
        if not actor.has_permission(PERM_READ_FINANCIALS):
            raise PermissionError("Actor lacks permission to view financing records")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM financing_records WHERE id = ?;", (record_id,)).fetchone()
        if not row:
            return None
        return self._row_to_record(row)

    def list_financing_records_for_project(
        self, project_id: int, actor: AuthContext
    ) -> List[FinancingRecord]:
        if not actor.has_permission(PERM_READ_FINANCIALS):
            raise PermissionError("Actor lacks permission to list financing records")

        conn = self.db.get_connection()
        rows = conn.execute(
            "SELECT * FROM financing_records WHERE project_id = ? ORDER BY id DESC;",
            (project_id,),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]
