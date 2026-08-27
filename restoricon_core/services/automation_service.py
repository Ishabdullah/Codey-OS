"""
Automation Rules, Business Profile, and Do-Not-Contact Service for
Restoricon Core (B2/NEW-209 schema expansion, 2026-08-27). Groups three
concerns that were separate flat-file stores in Aigentik-CLI
(email-rules.json/sms-rules.json, profile.json, do-not-contact.json) under
one "automation/config" service, RBAC-gated and audit-logged on mutation
like every other Core service -- except `record_rule_match`, which is a
deliberate exception (see its docstring).
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..auth import (
    AuthContext,
    PERM_READ_AUTOMATION_RULES,
    PERM_WRITE_AUTOMATION_RULES,
    PERM_READ_BUSINESS_PROFILE,
    PERM_WRITE_BUSINESS_PROFILE,
    PERM_READ_DNC,
    PERM_WRITE_DNC,
)
from ..database import DatabaseManager
from ..models import AutomationRule, BusinessProfile, DoNotContactEntry, utc_now_iso
from .audit_service import AuditService

VALID_CHANNELS = {"email", "sms"}
VALID_DNC_TYPES = {"email", "phone"}


def normalize_email(email: Optional[str]) -> Optional[str]:
    """Lowercase + trim. Must stay byte-for-byte equivalent to
    do-not-contact.js's normalizeEmail() -- a mismatch here means a
    suppressed contact could silently be re-contacted (see
    DoNotContactEntry's docstring)."""
    if not email:
        return None
    return email.lower().strip()


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """Strip to digits and keep the last 10. Must stay byte-for-byte
    equivalent to do-not-contact.js's normalizePhone()."""
    if not phone:
        return None
    digits = re.sub(r"[^0-9]", "", phone)
    return digits[-10:] if digits else None


def classify_identifier(identifier: Optional[str]) -> Optional[Dict[str, str]]:
    """Mirrors do-not-contact.js's classifyIdentifier(): decide whether a
    raw identifier is an email or a US-style phone number, and normalize
    it accordingly."""
    if not identifier:
        return None
    trimmed = identifier.strip()
    if "@" in trimmed:
        return {"type": "email", "value": normalize_email(trimmed)}
    phone = normalize_phone(trimmed)
    if phone and len(phone) == 10:
        return {"type": "phone", "value": phone}
    return None


class AutomationService:
    """Manages inbound-handling rules, the singleton business profile,
    and the permanent do-not-contact list."""

    def __init__(self, db_manager: DatabaseManager, audit_service: AuditService):
        self.db = db_manager
        self.audit = audit_service

    # ==========================================
    # AUTOMATION RULES (email/sms)
    # ==========================================

    @staticmethod
    def _row_to_rule(row) -> AutomationRule:
        return AutomationRule(
            id=row["id"],
            external_id=row["external_id"],
            channel=row["channel"],
            description=row["description"],
            condition_type=row["condition_type"],
            condition_value=row["condition_value"],
            action=row["action"],
            added_by=row["added_by"],
            match_count=row["match_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_rule(self, rule: AutomationRule, actor: AuthContext) -> AutomationRule:
        if not actor.has_permission(PERM_WRITE_AUTOMATION_RULES):
            raise PermissionError("Actor lacks permission to create automation rules")

        if rule.channel not in VALID_CHANNELS:
            raise ValueError(f"Invalid channel '{rule.channel}'. Must be one of {sorted(VALID_CHANNELS)}")

        now = utc_now_iso()
        rule.created_at = now
        rule.updated_at = now

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO automation_rules (
                    external_id, channel, description, condition_type, condition_value,
                    action, added_by, match_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    rule.external_id,
                    rule.channel,
                    rule.description,
                    rule.condition_type,
                    rule.condition_value,
                    rule.action,
                    rule.added_by,
                    rule.match_count,
                    now,
                    now,
                ),
            )
            rule.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="automation_rule",
            entity_id=rule.id,
            change_summary=f"Created {rule.channel} rule: {rule.description or rule.condition_type}",
            actor=actor,
            details=rule.to_dict(),
        )
        return rule

    def list_rules(
        self,
        actor: AuthContext,
        channel: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AutomationRule]:
        if not actor.has_permission(PERM_READ_AUTOMATION_RULES):
            raise PermissionError("Actor lacks permission to view automation rules")

        query = "SELECT * FROM automation_rules WHERE 1=1"
        params: List[Any] = []

        if channel:
            query += " AND channel = ?"
            params.append(channel)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_rule(row) for row in rows]

    def record_rule_match(self, rule_id: int, actor: AuthContext) -> Optional[AutomationRule]:
        """Increment a rule's hit counter. Deliberately NOT audit-logged:
        this fires on every inbound message a rule matches (a
        high-frequency, non-business event), and routing it through
        audit_log would flood the audit trail with noise that obscures
        the actual create/update/delete events the log exists to
        surface. Still gated on PERM_WRITE_AUTOMATION_RULES."""
        if not actor.has_permission(PERM_WRITE_AUTOMATION_RULES):
            raise PermissionError("Actor lacks permission to update automation rules")

        now = utc_now_iso()
        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                "UPDATE automation_rules SET match_count = match_count + 1, updated_at = ? WHERE id = ?;",
                (now, rule_id),
            )
            if cursor.rowcount == 0:
                return None

        row = conn.execute("SELECT * FROM automation_rules WHERE id = ?;", (rule_id,)).fetchone()
        return self._row_to_rule(row) if row else None

    # ==========================================
    # BUSINESS PROFILE (singleton)
    # ==========================================

    @staticmethod
    def _row_to_profile(row) -> BusinessProfile:
        return BusinessProfile(
            id=row["id"],
            configured=row["configured"],
            aigentik_name=row["aigentik_name"],
            agent_name_set=row["agent_name_set"],
            owner_name=row["owner_name"],
            business_name=row["business_name"],
            business_description=row["business_description"],
            onboarding_sent=row["onboarding_sent"],
            setup_date=row["setup_date"],
            updated_at=row["updated_at"],
        )

    def get_business_profile(self, actor: AuthContext) -> Optional[BusinessProfile]:
        if not actor.has_permission(PERM_READ_BUSINESS_PROFILE):
            raise PermissionError("Actor lacks permission to view the business profile")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM business_profile WHERE id = 1;").fetchone()
        if not row:
            return None
        return self._row_to_profile(row)

    def upsert_business_profile(self, profile: BusinessProfile, actor: AuthContext) -> BusinessProfile:
        """Create or update the single business_profile row (id fixed to 1)."""
        if not actor.has_permission(PERM_WRITE_BUSINESS_PROFILE):
            raise PermissionError("Actor lacks permission to update the business profile")

        now = utc_now_iso()
        profile.id = 1
        profile.updated_at = now

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO business_profile (
                    id, configured, aigentik_name, agent_name_set, owner_name,
                    business_name, business_description, onboarding_sent, setup_date, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    configured = excluded.configured,
                    aigentik_name = excluded.aigentik_name,
                    agent_name_set = excluded.agent_name_set,
                    owner_name = excluded.owner_name,
                    business_name = excluded.business_name,
                    business_description = excluded.business_description,
                    onboarding_sent = excluded.onboarding_sent,
                    setup_date = excluded.setup_date,
                    updated_at = excluded.updated_at;
                """,
                (
                    profile.configured,
                    profile.aigentik_name,
                    profile.agent_name_set,
                    profile.owner_name,
                    profile.business_name,
                    profile.business_description,
                    profile.onboarding_sent,
                    profile.setup_date,
                    now,
                ),
            )

        self.audit.log(
            action="update",
            entity_type="business_profile",
            entity_id=1,
            change_summary="Business profile updated",
            actor=actor,
            details=profile.to_dict(),
        )
        return profile

    # ==========================================
    # DO-NOT-CONTACT
    # ==========================================

    @staticmethod
    def _row_to_dnc(row) -> DoNotContactEntry:
        return DoNotContactEntry(
            id=row["id"],
            type=row["type"],
            value=row["value"],
            original=row["original"],
            name=row["name"],
            reason=row["reason"],
            source=row["source"],
            added_at=row["added_at"],
        )

    def add_to_do_not_contact(
        self,
        identifier: str,
        actor: AuthContext,
        name: Optional[str] = None,
        reason: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Optional[DoNotContactEntry]:
        """Idempotent add: re-adding an existing (type, value) pair
        refreshes name/reason/source/added_at, matching
        do-not-contact.js's addToDoNotContact()."""
        if not actor.has_permission(PERM_WRITE_DNC):
            raise PermissionError("Actor lacks permission to modify the do-not-contact list")

        classified = classify_identifier(identifier)
        if not classified:
            return None

        now = utc_now_iso()
        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO do_not_contact (type, value, original, name, reason, source, added_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(type, value) DO UPDATE SET
                    original = excluded.original,
                    name = COALESCE(excluded.name, do_not_contact.name),
                    reason = excluded.reason,
                    source = excluded.source,
                    added_at = excluded.added_at;
                """,
                (
                    classified["type"],
                    classified["value"],
                    identifier,
                    name,
                    reason or "requested removal",
                    source or "auto",
                    now,
                ),
            )

        row = conn.execute(
            "SELECT * FROM do_not_contact WHERE type = ? AND value = ?;",
            (classified["type"], classified["value"]),
        ).fetchone()
        entry = self._row_to_dnc(row) if row else None

        self.audit.log(
            action="create",
            entity_type="do_not_contact",
            entity_id=entry.id if entry else None,
            change_summary=f"Added {classified['type']} to do-not-contact: {classified['value']}",
            actor=actor,
            details={"reason": reason, "source": source},
        )
        return entry

    def remove_from_do_not_contact(self, identifier: str, actor: AuthContext) -> bool:
        if not actor.has_permission(PERM_WRITE_DNC):
            raise PermissionError("Actor lacks permission to modify the do-not-contact list")

        classified = classify_identifier(identifier)
        if not classified:
            return False

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                "DELETE FROM do_not_contact WHERE type = ? AND value = ?;",
                (classified["type"], classified["value"]),
            )
            removed = cursor.rowcount > 0

        if removed:
            self.audit.log(
                action="delete",
                entity_type="do_not_contact",
                entity_id=None,
                change_summary=f"Removed {classified['type']} from do-not-contact: {classified['value']}",
                actor=actor,
            )
        return removed

    def is_blocked(self, identifier: str, actor: AuthContext) -> bool:
        if not actor.has_permission(PERM_READ_DNC):
            raise PermissionError("Actor lacks permission to read the do-not-contact list")

        classified = classify_identifier(identifier)
        if not classified:
            return False

        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT 1 FROM do_not_contact WHERE type = ? AND value = ?;",
            (classified["type"], classified["value"]),
        ).fetchone()
        return row is not None

    def list_do_not_contact(self, actor: AuthContext, limit: int = 100, offset: int = 0) -> List[DoNotContactEntry]:
        if not actor.has_permission(PERM_READ_DNC):
            raise PermissionError("Actor lacks permission to view the do-not-contact list")

        conn = self.db.get_connection()
        rows = conn.execute(
            "SELECT * FROM do_not_contact ORDER BY added_at DESC LIMIT ? OFFSET ?;",
            (limit, offset),
        ).fetchall()
        return [self._row_to_dnc(row) for row in rows]
