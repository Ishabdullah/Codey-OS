"""
Appointment/Calendar Service for Restoricon Core (B2/NEW-209 schema
expansion, 2026-08-27). Mirrors Aigentik-CLI's calendar.js negotiate-then-
confirm appointment lifecycle: an appointment can be proposed with
offered_slots and later confirmed, or created directly as confirmed.
RBAC-gated and audit-logged on every mutation, matching crm_service.py's
established pattern.

Also owns schedule_config (NEW-216, 2026-08-27), the singleton business
scheduling defaults (working hours, slot lengths, booking window) that
mirror Aigentik-CLI's schedule-config.json -- grouped here rather than in
automation_service.py's business_profile because it's operational
scheduling config in the same domain as appointments, not business
identity/onboarding data.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..auth import (
    AuthContext,
    PERM_READ_APPOINTMENTS,
    PERM_READ_SCHEDULE_CONFIG,
    PERM_WRITE_APPOINTMENTS,
    PERM_WRITE_SCHEDULE_CONFIG,
)
from ..database import DatabaseManager
from ..models import Appointment, ScheduleConfig, utc_now_iso
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

    def get_appointment_by_external_id(self, external_id: str, actor: AuthContext) -> Optional[Appointment]:
        """Look up by Aigentik-CLI's own string ID (e.g. 'appt_0001').
        NEW-217: added so migrate_aigentik.py can check for an existing
        row before INSERT and skip re-migrating it, instead of hitting
        the `UNIQUE(external_id)` constraint as an IntegrityError."""
        if not actor.has_permission(PERM_READ_APPOINTMENTS):
            raise PermissionError("Actor lacks permission to view appointments")

        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM appointments WHERE external_id = ?;", (external_id,)
        ).fetchone()
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

    ALLOWED_UPDATE_FIELDS = {
        "title",
        "start_time",
        "end_time",
        "customer_id",
        "contact_external_id",
        "attendee_name",
        "attendee_email",
        "appointment_type",
        "status",
        "rsvp_status",
        "offered_slots",
        "requested_datetime",
        "pending_reschedule",
        "form_sent",
        "created_via",
        "notes",
        "ics_sequence",
        "history",
    }

    def update_appointment(
        self, appointment_id: int, updates: Dict[str, Any], actor: AuthContext
    ) -> Optional[Appointment]:
        """General partial-update method for appointments (B2 task 4, calendar write-through)."""
        if not actor.has_permission(PERM_WRITE_APPOINTMENTS):
            raise PermissionError("Actor lacks permission to update appointments")

        unknown = set(updates) - self.ALLOWED_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unknown field(s) for appointment update: {sorted(unknown)}")

        if "status" in updates and updates["status"] not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{updates['status']}'. Must be one of {sorted(VALID_STATUSES)}"
            )

        if not updates:
            return self.get_appointment(appointment_id, actor)

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM appointments WHERE id = ?;", (appointment_id,)).fetchone()
        if not row:
            return None

        # Build column assignments dynamically
        set_clauses = []
        params = []
        for key, value in updates.items():
            if key == "offered_slots":
                set_clauses.append("offered_slots_json = ?")
                params.append(json.dumps(value) if value is not None else "[]")
            elif key == "pending_reschedule":
                set_clauses.append("pending_reschedule_json = ?")
                params.append(json.dumps(value) if value is not None else None)
            elif key == "history":
                set_clauses.append("history_json = ?")
                params.append(json.dumps(value) if value is not None else "[]")
            elif key == "attendee_email":
                set_clauses.append("attendee_email = ?")
                params.append(value.strip().lower() if value else None)
            elif key == "title":
                set_clauses.append("title = ?")
                params.append(value.strip() if value else value)
            else:
                set_clauses.append(f"{key} = ?")
                params.append(value)

        now = utc_now_iso()
        set_clauses.append("updated_at = ?")
        params.append(now)
        params.append(appointment_id)

        with conn:
            conn.execute(
                f"UPDATE appointments SET {', '.join(set_clauses)} WHERE id = ?;",
                params,
            )

        self.audit.log(
            action="update",
            entity_type="appointment",
            entity_id=appointment_id,
            change_summary=f"Updated appointment {appointment_id}",
            actor=actor,
            details=updates,
        )
        return self.get_appointment(appointment_id, actor)

    def upsert_appointment(
        self,
        appt: Appointment,
        actor: AuthContext,
        raw_updates: Optional[Dict[str, Any]] = None,
    ) -> Appointment:
        """Create-or-update an appointment row keyed on external_id or id."""
        if not actor.has_permission(PERM_WRITE_APPOINTMENTS):
            raise PermissionError("Actor lacks permission to upsert appointments")

        existing = None
        if appt.id is not None:
            existing = self.get_appointment(appt.id, actor)
        elif appt.external_id and appt.external_id.strip():
            existing = self.get_appointment_by_external_id(appt.external_id, actor)

        if existing is None:
            return self.create_appointment(appt, actor)

        immutable = {"external_id", "created_at", "id"}
        source = raw_updates if raw_updates is not None else appt.to_dict()
        updates = {
            k: v
            for k, v in source.items()
            if k not in immutable and v is not None and k in self.ALLOWED_UPDATE_FIELDS
        }
        if not updates:
            return existing

        updated = self.update_appointment(existing.id, updates, actor)
        return updated or existing

    # ==========================================
    # SCHEDULE CONFIG (singleton, NEW-216, 2026-08-27)
    # ==========================================

    @staticmethod
    def _row_to_schedule_config(row) -> ScheduleConfig:
        return ScheduleConfig(
            id=row["id"],
            working_hours=json.loads(row["working_hours_json"]) if row["working_hours_json"] else {},
            default_duration_minutes=row["default_duration_minutes"],
            buffer_minutes=row["buffer_minutes"],
            booking_window_days=row["booking_window_days"],
            duration_by_relationship=json.loads(row["duration_by_relationship_json"]) if row["duration_by_relationship_json"] else {},
            updated_at=row["updated_at"],
        )

    def get_schedule_config(self, actor: AuthContext) -> Optional[ScheduleConfig]:
        """Fetch the single schedule_config row (id fixed to 1), or None
        if it has never been set. Returns None rather than raising so a
        caller can distinguish "not configured yet" from a permission
        failure (which still raises PermissionError below)."""
        if not actor.has_permission(PERM_READ_SCHEDULE_CONFIG):
            raise PermissionError("Actor lacks permission to view the schedule config")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM schedule_config WHERE id = 1;").fetchone()
        if not row:
            return None
        return self._row_to_schedule_config(row)

    def upsert_schedule_config(self, config: ScheduleConfig, actor: AuthContext) -> ScheduleConfig:
        """Create or update the single schedule_config row (id fixed to
        1), mirroring upsert_business_profile()'s ON CONFLICT pattern."""
        if not actor.has_permission(PERM_WRITE_SCHEDULE_CONFIG):
            raise PermissionError("Actor lacks permission to update the schedule config")

        now = utc_now_iso()
        config.id = 1
        config.updated_at = now
        working_hours_json = json.dumps(config.working_hours)
        duration_by_relationship_json = json.dumps(config.duration_by_relationship)

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO schedule_config (
                    id, working_hours_json, default_duration_minutes, buffer_minutes,
                    booking_window_days, duration_by_relationship_json, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    working_hours_json = excluded.working_hours_json,
                    default_duration_minutes = excluded.default_duration_minutes,
                    buffer_minutes = excluded.buffer_minutes,
                    booking_window_days = excluded.booking_window_days,
                    duration_by_relationship_json = excluded.duration_by_relationship_json,
                    updated_at = excluded.updated_at;
                """,
                (
                    working_hours_json,
                    config.default_duration_minutes,
                    config.buffer_minutes,
                    config.booking_window_days,
                    duration_by_relationship_json,
                    now,
                ),
            )

        self.audit.log(
            action="update",
            entity_type="schedule_config",
            entity_id=1,
            change_summary="Schedule config updated",
            actor=actor,
            details=config.to_dict(),
        )
        return config
