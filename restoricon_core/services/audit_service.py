"""
Day-One-or-Never Append-Only Audit Log Service for Restoricon Core.
Records every human and AI agent action with actor, timestamp, action type,
and entity details. Strict append-only semantics.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..auth import AuthContext, PERM_READ_AUDIT_LOG
from ..database import DatabaseManager
from ..models import AuditRecord, utc_now_iso


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

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?;"
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
