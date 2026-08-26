"""
Day-One-or-Never Append-Only Communication History Service for Restoricon Core.
Tracks all omnichannel customer and team interactions across phone, email, SMS,
chat, AI conversations, and internal notes. Strict append-only semantics.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..auth import (
    AuthContext,
    PERM_LOG_COMMUNICATION,
    PERM_READ_COMMUNICATIONS,
    PERM_READ_OWN_COMMUNICATIONS,
    ROLE_CUSTOMER,
)
from ..database import DatabaseManager
from ..models import CommunicationRecord, utc_now_iso

VALID_CHANNELS = {
    "phone",
    "email",
    "sms",
    "voicemail",
    "web_chat",
    "social",
    "internal_note",
    "ai_conversation",
    "appointment",
}

VALID_DIRECTIONS = {"inbound", "outbound", "internal"}


class CommunicationService:
    """Manages immutable communication history records."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def record_communication(
        self,
        channel: str,
        direction: str,
        content: str,
        actor: AuthContext,
        subject: Optional[str] = None,
        customer_id: Optional[int] = None,
        project_id: Optional[int] = None,
        opportunity_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CommunicationRecord:
        """
        Append an immutable communication interaction to the history.
        """
        if not actor.has_permission(PERM_LOG_COMMUNICATION):
            raise PermissionError("Actor lacks permission to log communications")

        if channel not in VALID_CHANNELS:
            raise ValueError(f"Invalid channel '{channel}'. Must be one of {sorted(VALID_CHANNELS)}")

        if direction not in VALID_DIRECTIONS:
            raise ValueError(f"Invalid direction '{direction}'. Must be one of {sorted(VALID_DIRECTIONS)}")

        # Customer role cannot log internal notes or log for another customer
        if actor.role == ROLE_CUSTOMER:
            if channel == "internal_note" or direction == "internal":
                raise PermissionError("Customer cannot log internal communications")
            if customer_id and customer_id != actor.customer_id:
                raise PermissionError("Customer cannot log communication for another customer")
            customer_id = actor.customer_id

        now = utc_now_iso()
        metadata_json = json.dumps(metadata or {})

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO communication_history (
                    timestamp, channel, direction, subject, content,
                    actor_id, actor_role, actor_type, customer_id, project_id,
                    opportunity_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    now,
                    channel,
                    direction,
                    subject,
                    content.strip(),
                    actor.user_id,
                    actor.role,
                    actor.actor_type,
                    customer_id,
                    project_id,
                    opportunity_id,
                    metadata_json,
                ),
            )
            comm_id = cursor.lastrowid

        return CommunicationRecord(
            id=comm_id,
            timestamp=now,
            channel=channel,
            direction=direction,
            subject=subject,
            content=content.strip(),
            actor_id=actor.user_id,
            actor_role=actor.role,
            actor_type=actor.actor_type,
            customer_id=customer_id,
            project_id=project_id,
            opportunity_id=opportunity_id,
            metadata=metadata or {},
        )

    def query_communications(
        self,
        actor: AuthContext,
        customer_id: Optional[int] = None,
        project_id: Optional[int] = None,
        channel: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[CommunicationRecord]:
        """Query communication history with strict role-based visibility filtering."""
        query = "SELECT * FROM communication_history WHERE 1=1"
        params: List[Any] = []

        # Customer role scoping
        if actor.role == ROLE_CUSTOMER:
            if not actor.customer_id:
                return []
            query += " AND customer_id = ? AND channel != 'internal_note' AND direction != 'internal'"
            params.append(actor.customer_id)
        else:
            if not actor.has_permission(PERM_READ_COMMUNICATIONS):
                raise PermissionError("Actor lacks permission to read communications")
            if customer_id is not None:
                query += " AND customer_id = ?"
                params.append(customer_id)

        if project_id is not None:
            query += " AND project_id = ?"
            params.append(project_id)

        if channel:
            query += " AND channel = ?"
            params.append(channel)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()

        results = []
        for row in rows:
            meta = {}
            if row["metadata_json"]:
                try:
                    meta = json.loads(row["metadata_json"])
                except Exception:
                    meta = {}
            results.append(
                CommunicationRecord(
                    id=row["id"],
                    timestamp=row["timestamp"],
                    channel=row["channel"],
                    direction=row["direction"],
                    subject=row["subject"],
                    content=row["content"],
                    actor_id=row["actor_id"],
                    actor_role=row["actor_role"],
                    actor_type=row["actor_type"],
                    customer_id=row["customer_id"],
                    project_id=row["project_id"],
                    opportunity_id=row["opportunity_id"],
                    metadata=meta,
                )
            )
        return results
