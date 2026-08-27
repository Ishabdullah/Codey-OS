"""
Appointment/Calendar Service for Restoricon Core (B2/NEW-209 schema
expansion, 2026-08-27). Mirrors Aigentik-CLI's calendar.js negotiate-then-
confirm appointment lifecycle: an appointment can be proposed with
offered_slots and later confirmed, or created directly as confirmed.
RBAC-gated and audit-logged on every mutation, matching crm_service.py's
established pattern.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..auth import (
    AuthContext,
    PERM_READ_APPOINTMENTS,
    PERM_WRITE_APPOINTMENTS,
)
from ..database import DatabaseManager
from ..models import Appointment, utc_now_iso
from .audit_service import AuditService

VALID_STATUSES = {"confirmed", "negotiating", "cancelled", "completed"}


class SchedulingService:
    """Manages appointment/calendar records."""

    def __init__(self, db_manager: DatabaseManager, audit_service: AuditService):
        self.db = db_manager
        self.audit = audit_service

    @staticmethod
    def _row_to_appointment(row) -> Appointment:
        return Appointment(
            id=row["id"],
            external_id=row["external_id"],
            uid=row["uid"],
            ics_sequence=row["ics_sequence"],
            title=row["title"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            customer_id=row["customer_id"],
            contact_external_id=row["contact_external_id"],
            attendee_name=row["attendee_name"],
            attendee_email=row["attendee_email"],
            appointment_type=row["appointment_type"],
            status=row["status"],
            rsvp_status=row["rsvp_status"],
            offered_slots=json.loads(row["offered_slots_json"]) if row["offered_slots_json"] else [],
            requested_datetime=row["requested_datetime"],
            pending_reschedule=json.loads(row["pending_reschedule_json"]) if row["pending_reschedule_json"] else None,
            form_sent=row["form_sent"],
            created_via=row["created_via"],
            notes=row["notes"],
            history=json.loads(row["history_json"]) if row["history_json"] else [],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_appointment(self, appt: Appointment, actor: AuthContext) -> Appointment:
        if not actor.has_permission(PERM_WRITE_APPOINTMENTS):
            raise PermissionError("Actor lacks permission to create appointments")

        if appt.status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{appt.status}'. Must be one of {sorted(VALID_STATUSES)}")

        now = utc_now_iso()
        appt.created_at = now
        appt.updated_at = now
        if not appt.history:
            appt.history = [{"event": "created", "at": now}]
        offered_slots_json = json.dumps(appt.offered_slots)
        pending_reschedule_json = json.dumps(appt.pending_reschedule) if appt.pending_reschedule is not None else None
        history_json = json.dumps(appt.history)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO appointments (
                    external_id, uid, ics_sequence, title, start_time, end_time,
                    customer_id, contact_external_id, attendee_name, attendee_email,
                    appointment_type, status, rsvp_status, offered_slots_json,
                    requested_datetime, pending_reschedule_json, form_sent, created_via,
                    notes, history_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    appt.external_id,
                    appt.uid,
                    appt.ics_sequence,
                    appt.title.strip() if appt.title else appt.title,
                    appt.start_time,
                    appt.end_time,
                    appt.customer_id,
                    appt.contact_external_id,
                    appt.attendee_name,
                    appt.attendee_email.strip().lower() if appt.attendee_email else None,
                    appt.appointment_type,
                    appt.status,
                    appt.rsvp_status,
                    offered_slots_json,
                    appt.requested_datetime,
                    pending_reschedule_json,
                    appt.form_sent,
                    appt.created_via,
                    appt.notes,
                    history_json,
                    now,
                    now,
                ),
            )
            appt.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="appointment",
            entity_id=appt.id,
            change_summary=f"Created appointment '{appt.title}' ({appt.status})",
            actor=actor,
            details=appt.to_dict(),
        )
        return appt

    def get_appointment(self, appointment_id: int, actor: AuthContext) -> Optional[Appointment]:
        if not actor.has_permission(PERM_READ_APPOINTMENTS):
            raise PermissionError("Actor lacks permission to view appointments")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM appointments WHERE id = ?;", (appointment_id,)).fetchone()
        if not row:
            return None
        return self._row_to_appointment(row)

    def list_appointments(
        self,
        actor: AuthContext,
        customer_id: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Appointment]:
        if not actor.has_permission(PERM_READ_APPOINTMENTS):
            raise PermissionError("Actor lacks permission to list appointments")

        query = "SELECT * FROM appointments WHERE 1=1"
        params: List[Any] = []

        if customer_id is not None:
            query += " AND customer_id = ?"
            params.append(customer_id)

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY start_time DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_appointment(row) for row in rows]

    def update_appointment_status(
        self,
        appointment_id: int,
        status: str,
        actor: AuthContext,
    ) -> Optional[Appointment]:
        """Transition an appointment (e.g. negotiating -> confirmed, or -> cancelled/completed)."""
        if not actor.has_permission(PERM_WRITE_APPOINTMENTS):
            raise PermissionError("Actor lacks permission to update appointments")

        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{status}'. Must be one of {sorted(VALID_STATUSES)}")

        now = utc_now_iso()
        conn = self.db.get_connection()
        row = conn.execute("SELECT history_json FROM appointments WHERE id = ?;", (appointment_id,)).fetchone()
        if not row:
            return None

        history = json.loads(row["history_json"]) if row["history_json"] else []
        history.append({"event": f"status_set:{status}", "at": now})
        history_json = json.dumps(history)

        with conn:
            conn.execute(
                "UPDATE appointments SET status = ?, history_json = ?, updated_at = ? WHERE id = ?;",
                (status, history_json, now, appointment_id),
            )

        self.audit.log(
            action="status_change",
            entity_type="appointment",
            entity_id=appointment_id,
            change_summary=f"Appointment {appointment_id} status set to '{status}'",
            actor=actor,
            details={"status": status},
        )
        return self.get_appointment(appointment_id, actor)
