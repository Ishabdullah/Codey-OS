"""
Commission Ledger Domain Engine for Restoricon Core (B8.1, D4,
sales_rep_portal.md §4, Ish-approved 2026-09-16).

Strictly append-only, same discipline as audit_log/communication_history
(see database.py's commission_ledger_entries comment). reverse_commission
NEVER issues UPDATE/DELETE against an existing row -- a correction or
chargeback is always a new row referencing the original via
reversed_entry_id.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from ..auth import (
    AuthContext,
    PERM_READ_TEAM_COMMISSIONS,
    PERM_WRITE_TEAM_COMMISSIONS,
)
from ..database import DatabaseManager
from ..models import CommissionLedgerEntry, utc_now_iso
from .audit_service import AuditService, build_audit_details

# Must stay byte-for-byte identical to the CHECK constraint in
# database.py's commission_ledger_entries DDL -- validated in Python too
# so callers get a clean ValueError instead of a raw sqlite3.IntegrityError
# (mirrors finance_service.py's record_transaction valid_types check).
_VALID_SOURCE_TYPES = {
    "assessment",
    "subscription_upsell",
    "portfolio_override",
    "bonus",
    "adjustment",
    "chargeback",
}
_VALID_STATUSES = {"pending", "earned", "paid", "reversed"}


class CommissionService:
    """Manages the append-only commission ledger. Minimal surface per
    B8.1's scope: record_commission (create), get_commission (read one),
    reverse_commission (append a reversing row); list_commissions is added
    alongside them since a read-only listing is needed to exercise the
    PERM_READ_TEAM_COMMISSIONS narrowing at all."""

    def __init__(self, db: DatabaseManager, audit: AuditService):
        self.db = db
        self.audit = audit

    @staticmethod
    def _row_to_entry(row: Any) -> CommissionLedgerEntry:
        return CommissionLedgerEntry(
            id=row["id"],
            rep_user_id=row["rep_user_id"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            basis_amount=float(row["basis_amount"]) if row["basis_amount"] is not None else None,
            commission_rate_or_flat=float(row["commission_rate_or_flat"]) if row["commission_rate_or_flat"] is not None else None,
            commission_amount=float(row["commission_amount"]),
            status=row["status"],
            earned_at=row["earned_at"],
            paid_at=row["paid_at"],
            reversed_entry_id=row["reversed_entry_id"],
            created_by=row["created_by"],
            notes=row["notes"],
            created_at=row["created_at"],
        )

    def record_commission(
        self, entry: CommissionLedgerEntry, actor: AuthContext
    ) -> CommissionLedgerEntry:
        """Insert a new commission ledger entry.

        Gated on PERM_WRITE_TEAM_COMMISSIONS (code-reviewer round 2, B8.1):
        split from PERM_READ_TEAM_COMMISSIONS following the exact
        PERM_SIGN_CONTRACTS / PERM_WRITE_CONTRACTS precedent (auth.py) --
        being able to see every rep's commissions doesn't imply authority
        to author or reverse money-moving ledger rows. Granted to the same
        default set as the read permission (admin/manager/ai_agent/
        sales_manager), so behavior for those roles is unchanged; the
        difference only matters for a future role/custom-permission grant
        that holds read but not write. An ordinary sales rep can read
        their own rows (see get_commission/list_commissions) but never
        author or alter one.

        rep_user_id is required here even though the schema column is
        nullable+ON DELETE SET NULL (that nullability exists only so a
        historical row survives after its rep's user account is later
        deleted -- see database.py's commission_ledger_entries comment).
        """
        if not actor.has_permission(PERM_WRITE_TEAM_COMMISSIONS):
            raise PermissionError("Actor lacks permission to record commission ledger entries")

        if entry.rep_user_id is None:
            raise ValueError("record_commission requires a non-null rep_user_id")

        if entry.source_type not in _VALID_SOURCE_TYPES:
            raise ValueError(f"Invalid source_type: {entry.source_type}")

        if entry.status not in _VALID_STATUSES:
            raise ValueError(f"Invalid status: {entry.status}")

        now = utc_now_iso()
        entry.created_at = now
        entry.created_by = actor.user_id
        entry.reversed_entry_id = None  # a freshly-recorded entry is never itself a reversal

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO commission_ledger_entries (
                    rep_user_id, source_type, source_id, basis_amount,
                    commission_rate_or_flat, commission_amount, status,
                    earned_at, paid_at, reversed_entry_id, created_by,
                    notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    entry.rep_user_id,
                    entry.source_type,
                    entry.source_id,
                    entry.basis_amount,
                    entry.commission_rate_or_flat,
                    entry.commission_amount,
                    entry.status,
                    entry.earned_at,
                    entry.paid_at,
                    entry.reversed_entry_id,
                    entry.created_by,
                    entry.notes,
                    entry.created_at,
                ),
            )
            entry.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="commission_ledger_entry",
            entity_id=entry.id,
            change_summary=f"Recorded {entry.source_type} commission of {entry.commission_amount:.2f} for rep {entry.rep_user_id}",
            actor=actor,
            details=build_audit_details(after=entry.to_dict()),
        )
        return entry

    def get_commission(self, entry_id: int, actor: AuthContext) -> Optional[CommissionLedgerEntry]:
        """Read a single ledger entry. Mirrors CRMService.get_lead's
        narrowing shape (crm_service.py:607-624): a holder of
        PERM_READ_TEAM_COMMISSIONS sees any row; anyone else only sees a
        row whose rep_user_id is their own -- an out-of-scope row is
        treated as not-found (returns None), not a 403, matching that
        same precedent."""
        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM commission_ledger_entries WHERE id = ?;", (entry_id,)
        ).fetchone()
        if not row:
            return None

        entry = self._row_to_entry(row)
        if not actor.has_permission(PERM_READ_TEAM_COMMISSIONS):
            if entry.rep_user_id is None or entry.rep_user_id != actor.user_id:
                return None
        return entry

    def _scoped_rep_filter(self, actor: AuthContext, requested_rep_user_id: Optional[int]) -> Optional[int]:
        """Resolves the effective rep_user_id filter for a read, mirroring
        CRMService._scoped_assignee_filter (crm_service.py:626-640)."""
        if actor.has_permission(PERM_READ_TEAM_COMMISSIONS):
            return requested_rep_user_id
        return actor.user_id

    def list_commissions(
        self,
        actor: AuthContext,
        rep_user_id: Optional[int] = None,
        status: Optional[str] = None,
        include_reversed: bool = False,
    ) -> List[CommissionLedgerEntry]:
        """List ledger entries, optionally filtered by status.

        code-reviewer round 2 (B8.1): a status filter (e.g. status='earned')
        must not silently return an original row that has since been
        reversed -- the original row's own status never changes
        (append-only), so without this exclusion a caller doing
        "give me earned commissions for payout" would double-count a
        reversed entry. When `status` is given and `include_reversed` is
        False (the default), any row that is the *target* of a reversal
        (i.e. appears as some other row's reversed_entry_id) is excluded.
        Pass include_reversed=True, or omit `status` entirely, to see the
        full append-only history (both the original and its reversal row)
        for audit purposes.
        """
        effective_uid = self._scoped_rep_filter(actor, rep_user_id)

        query = "SELECT * FROM commission_ledger_entries WHERE 1=1"
        params: List[Any] = []
        if effective_uid is not None:
            query += " AND rep_user_id = ?"
            params.append(effective_uid)
        if status:
            query += " AND status = ?"
            params.append(status)
            if not include_reversed:
                query += (
                    " AND id NOT IN ("
                    "SELECT reversed_entry_id FROM commission_ledger_entries "
                    "WHERE reversed_entry_id IS NOT NULL)"
                )
        query += " ORDER BY id DESC;"

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def reverse_commission(
        self, entry_id: int, actor: AuthContext, notes: Optional[str] = None
    ) -> CommissionLedgerEntry:
        """Reverse a commission ledger entry by INSERTing a new row with
        status='reversed' and reversed_entry_id pointing at the original --
        the original row is never UPDATEd or DELETEd (append-only, see
        module docstring). The reversal row's commission_amount is the
        NEGATION of the original's; summing commission_amount over a rep's
        ledger nets out correctly PROVIDED a reversed original is excluded
        the way list_commissions' status filter now does (see its
        docstring) -- an unfiltered sum that includes reversed originals
        directly is fine too since the negation cancels it exactly, but a
        status='earned'-style filtered read must go through
        list_commissions' exclusion logic rather than raw SQL to avoid
        double-counting.

        Reversing an entry that has already been reversed is rejected
        (code-reviewer round 2, B8.1) -- double-reversal was found live to
        corrupt the ledger (two -100 reversal rows against one +100
        original nets to -100, not 0). The guard is enforced by a partial
        unique index at the schema level
        (idx_commission_ledger_reversed_entry_id_unique on
        reversed_entry_id WHERE reversed_entry_id IS NOT NULL) rather than
        a plain pre-check SELECT, specifically so two concurrent
        reverse_commission() calls on the same entry_id can't both pass a
        TOCTOU pre-check and both INSERT (NEW-135/136/534 is this exact
        race class) -- SQLite's own constraint rejects the second
        concurrent insert with sqlite3.IntegrityError, which is caught
        below and re-raised as a ValueError."""
        if not actor.has_permission(PERM_WRITE_TEAM_COMMISSIONS):
            raise PermissionError("Actor lacks permission to reverse commission ledger entries")

        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM commission_ledger_entries WHERE id = ?;", (entry_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Commission ledger entry {entry_id} not found")

        original = self._row_to_entry(row)

        existing_reversal = conn.execute(
            "SELECT id FROM commission_ledger_entries WHERE reversed_entry_id = ?;",
            (entry_id,),
        ).fetchone()
        if existing_reversal:
            raise ValueError(
                f"Commission ledger entry {entry_id} has already been reversed "
                f"(by entry {existing_reversal['id']})"
            )
        now = utc_now_iso()
        reversal = CommissionLedgerEntry(
            rep_user_id=original.rep_user_id,
            source_type=original.source_type,
            source_id=original.source_id,
            basis_amount=original.basis_amount,
            commission_rate_or_flat=original.commission_rate_or_flat,
            commission_amount=-original.commission_amount,
            status="reversed",
            earned_at=None,
            paid_at=None,
            reversed_entry_id=original.id,
            created_by=actor.user_id,
            notes=notes,
            created_at=now,
        )

        try:
            with conn:
                cursor = conn.execute(
                    """
                    INSERT INTO commission_ledger_entries (
                        rep_user_id, source_type, source_id, basis_amount,
                        commission_rate_or_flat, commission_amount, status,
                        earned_at, paid_at, reversed_entry_id, created_by,
                        notes, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        reversal.rep_user_id,
                        reversal.source_type,
                        reversal.source_id,
                        reversal.basis_amount,
                        reversal.commission_rate_or_flat,
                        reversal.commission_amount,
                        reversal.status,
                        reversal.earned_at,
                        reversal.paid_at,
                        reversal.reversed_entry_id,
                        reversal.created_by,
                        reversal.notes,
                        reversal.created_at,
                    ),
                )
                reversal.id = cursor.lastrowid
        except sqlite3.IntegrityError as exc:
            # Narrowly scoped to the specific partial unique index that is
            # the actual race-safe guard (see docstring above) -- this
            # catches the case where a concurrent reverse_commission()
            # call on the same entry_id won the race between our
            # pre-check above and this INSERT, and turns SQLite's raw
            # IntegrityError into the same domain-level ValueError the
            # pre-check raises, so callers don't need to know about the
            # DB-level mechanism. Deliberately checks for this specific
            # UNIQUE-constraint violation in the error text (SQLite's
            # IntegrityError message names the constrained column, e.g.
            # "UNIQUE constraint failed: commission_ledger_entries.
            # reversed_entry_id" -- it does NOT name the index itself,
            # verified directly against sqlite3's actual error text
            # rather than assumed) rather than catching IntegrityError
            # unconditionally -- an FK violation on rep_user_id/created_by
            # or some other future constraint on this INSERT must NOT be
            # silently reported to the caller as "already reversed"; it
            # should propagate as the real error.
            if "commission_ledger_entries.reversed_entry_id" not in str(exc):
                raise
            raise ValueError(
                f"Commission ledger entry {entry_id} has already been reversed"
            ) from exc

        self.audit.log(
            action="update",
            entity_type="commission_ledger_entry",
            entity_id=reversal.id,
            change_summary=f"Reversed commission ledger entry {original.id} via new entry {reversal.id}",
            actor=actor,
            details=build_audit_details(
                after=reversal.to_dict(),
                side_effects={"reversed_entry_id": original.id},
            ),
        )
        return reversal
