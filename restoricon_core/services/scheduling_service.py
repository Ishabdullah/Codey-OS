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
    PERM_READ_APPOINTMENT_TYPES,
    PERM_READ_SCHEDULE_CONFIG,
    PERM_WRITE_APPOINTMENTS,
    PERM_WRITE_APPOINTMENT_TYPES,
    PERM_WRITE_SCHEDULE_CONFIG,
    PERM_READ_STAFF_SCHEDULES,
    PERM_WRITE_STAFF_SCHEDULES,
)
from ..database import DatabaseManager
from ..models import Appointment, AppointmentType, ScheduleConfig, StaffSchedule, utc_now_iso
from .audit_service import (
    AuditService,
    build_audit_details,
    _AUDITABLE_APPOINTMENT_FIELDS,
    _AUDITABLE_APPOINTMENT_TYPE_FIELDS,
)
from .notification_service import NotificationService

VALID_STATUSES = {"confirmed", "negotiating", "cancelled", "completed"}


class SchedulingService:
    """Manages appointment/calendar records."""

    def __init__(self, db_manager: DatabaseManager, audit_service: AuditService, notification_service: Optional[NotificationService] = None):
        self.db = db_manager
        self.audit = audit_service
        self.notification = notification_service

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
            appointment_type_id=row["appointment_type_id"],
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

    def create_appointment(
        self, appt: Appointment, actor: AuthContext,
        created_at: Optional[str] = None, updated_at: Optional[str] = None,
    ) -> Appointment:
        # NEW-218 (service-layer half): explicit override kwargs so a caller
        # migrating a record with a known source created_at/updated_at can
        # preserve it instead of getting "now" stamped on both. Currently
        # unused -- no existing caller passes them, so this is a
        # zero-behavior-change addition for every current call site.
        if not actor.has_permission(PERM_WRITE_APPOINTMENTS):
            raise PermissionError("Actor lacks permission to create appointments")

        if appt.status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{appt.status}'. Must be one of {sorted(VALID_STATUSES)}")

        now = utc_now_iso()
        appt.created_at = created_at or now
        appt.updated_at = updated_at or now
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
                    appointment_type, appointment_type_id, status, rsvp_status, offered_slots_json,
                    requested_datetime, pending_reschedule_json, form_sent, created_via,
                    notes, history_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
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
                    appt.appointment_type_id,
                    appt.status,
                    appt.rsvp_status,
                    offered_slots_json,
                    appt.requested_datetime,
                    pending_reschedule_json,
                    appt.form_sent,
                    appt.created_via,
                    appt.notes,
                    history_json,
                    appt.created_at,
                    appt.updated_at,
                ),
            )
            appt.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="appointment",
            entity_id=appt.id,
            change_summary=f"Created appointment '{appt.title}' ({appt.status})",
            actor=actor,
            details=build_audit_details(after=appt.to_dict()),
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
        # NEW-240: widened from `SELECT history_json` to the full row so the
        # return value can be built from a write-scoped re-fetch below
        # instead of the READ-gated get_appointment() (this method is
        # authorized on PERM_WRITE_APPOINTMENTS, not PERM_READ_APPOINTMENTS).
        # The audit entry below still uses a status-only snapshot per
        # NEW-311 C-none -- widening the SELECT here is for the return
        # value, not for an audit before/after diff.
        row = conn.execute("SELECT * FROM appointments WHERE id = ?;", (appointment_id,)).fetchone()
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
            updated_row = conn.execute(
                "SELECT * FROM appointments WHERE id = ?;", (appointment_id,)
            ).fetchone()

        self.audit.log(
            action="status_change",
            entity_type="appointment",
            entity_id=appointment_id,
            change_summary=f"Appointment {appointment_id} status set to '{status}'",
            actor=actor,
            # NEW-311 C-none: `status` is the only meaningfully written column
            # (history_json/updated_at are bookkeeping). The existing pre-read
            # selects history_json only, so the old status is not available
            # from an existing read and widening the SELECT is barred.
            details=build_audit_details(snapshot={"status": status}),
        )
        return self._row_to_appointment(updated_row) if updated_row else None

    ALLOWED_UPDATE_FIELDS = {
        "title",
        "start_time",
        "end_time",
        "customer_id",
        "contact_external_id",
        "attendee_name",
        "attendee_email",
        "appointment_type",
        "appointment_type_id",
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

        # Audit pre-image: both sides built through the same
        # _row_to_appointment builder so JSON-column normalization can't
        # produce a phantom diff.
        _before = self._row_to_appointment(row).to_dict()

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

        _after_row = conn.execute(
            "SELECT * FROM appointments WHERE id = ?;", (appointment_id,)
        ).fetchone()
        _after = self._row_to_appointment(_after_row).to_dict() if _after_row else None

        self.audit.log(
            action="update",
            entity_type="appointment",
            entity_id=appointment_id,
            change_summary=f"Updated appointment {appointment_id}",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_after,
                fields=_AUDITABLE_APPOINTMENT_FIELDS,
            ),
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
            # Singleton ON CONFLICT upsert with no post-write read; adding a
            # SELECT to build a diff is barred under NEW-311. Snapshot is
            # input-derived (not a re-read). ScheduleConfig has no sensitive
            # fields, so no allow-list is applied.
            details=build_audit_details(snapshot=config.to_dict()),
        )
        return config

    # ==========================================
    # APPOINTMENT TYPES (service-type axis, final scheduling round Phase 2)
    # ==========================================

    @staticmethod
    def _row_to_appointment_type(row) -> AppointmentType:
        # Hand-written reader -- every column read explicitly (NEW-259).
        # scheduling_hours mirrors _row_to_schedule_config's working_hours.
        return AppointmentType(
            id=row["id"],
            name=row["name"],
            active=row["active"],
            sort_order=row["sort_order"],
            max_concurrent=row["max_concurrent"],
            scheduling_hours=json.loads(row["scheduling_hours_json"]) if row["scheduling_hours_json"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_appointment_types(
        self, actor: AuthContext, include_inactive: bool = False
    ) -> List[AppointmentType]:
        if not actor.has_permission(PERM_READ_APPOINTMENT_TYPES):
            raise PermissionError("Actor lacks permission to view appointment types")

        query = "SELECT * FROM appointment_types"
        if not include_inactive:
            query += " WHERE active = 1"
        query += " ORDER BY sort_order, id;"

        conn = self.db.get_connection()
        rows = conn.execute(query).fetchall()
        return [self._row_to_appointment_type(row) for row in rows]

    def get_appointment_type(
        self, appointment_type_id: int, actor: AuthContext
    ) -> Optional[AppointmentType]:
        if not actor.has_permission(PERM_READ_APPOINTMENT_TYPES):
            raise PermissionError("Actor lacks permission to view appointment types")

        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM appointment_types WHERE id = ?;", (appointment_type_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_appointment_type(row)

    def create_appointment_type(
        self, appt_type: AppointmentType, actor: AuthContext
    ) -> AppointmentType:
        if not actor.has_permission(PERM_WRITE_APPOINTMENT_TYPES):
            raise PermissionError("Actor lacks permission to create appointment types")

        if not appt_type.name or not str(appt_type.name).strip():
            raise ValueError("Appointment type name is required")
        if appt_type.max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        appt_type.name = str(appt_type.name).strip()

        now = utc_now_iso()
        appt_type.created_at = now
        appt_type.updated_at = now
        scheduling_hours_json = json.dumps(appt_type.scheduling_hours)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO appointment_types (
                    name, active, sort_order, max_concurrent,
                    scheduling_hours_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    appt_type.name,
                    appt_type.active,
                    appt_type.sort_order,
                    appt_type.max_concurrent,
                    scheduling_hours_json,
                    now,
                    now,
                ),
            )
            appt_type.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="appointment_type",
            entity_id=appt_type.id,
            change_summary=f"Created appointment type '{appt_type.name}'",
            actor=actor,
            details=build_audit_details(after=appt_type.to_dict()),
        )
        return appt_type

    # scheduling_hours_json (the raw column) is deliberately NOT accepted
    # here: an unparseable string would commit successfully and then every
    # subsequent read of the row would raise JSONDecodeError in
    # _row_to_appointment_type. Only the dict form is accepted -- it is
    # always json.dumps'd, so it can never write invalid JSON.
    _APPOINTMENT_TYPE_UPDATE_FIELDS = {
        "name",
        "active",
        "sort_order",
        "max_concurrent",
        "scheduling_hours",
    }

    def update_appointment_type(
        self, appointment_type_id: int, updates: Dict[str, Any], actor: AuthContext
    ) -> AppointmentType:
        if not actor.has_permission(PERM_WRITE_APPOINTMENT_TYPES):
            raise PermissionError("Actor lacks permission to update appointment types")

        # Silently ignore only the immutable identity/timestamp keys (so a
        # caller passing a full to_dict() does not error); any OTHER key
        # outside the allow-list is a caller mistake -> ValueError -> 400
        # (mirrors update_appointment's behavior).
        _ignorable = {"id", "created_at", "updated_at"}
        unknown = set(updates) - self._APPOINTMENT_TYPE_UPDATE_FIELDS - _ignorable
        if unknown:
            raise ValueError(f"Unknown field(s) for appointment type: {sorted(unknown)}")

        if "name" in updates and (updates["name"] is None or not str(updates["name"]).strip()):
            raise ValueError("Appointment type name is required")
        if "max_concurrent" in updates and updates["max_concurrent"] < 1:
            raise ValueError("max_concurrent must be >= 1")

        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM appointment_types WHERE id = ?;", (appointment_type_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Appointment type {appointment_type_id} does not exist")

        _before = self._row_to_appointment_type(row).to_dict()

        set_clauses = []
        params: List[Any] = []
        for key, value in updates.items():
            if key not in self._APPOINTMENT_TYPE_UPDATE_FIELDS:
                continue
            if key == "scheduling_hours":
                set_clauses.append("scheduling_hours_json = ?")
                params.append(json.dumps(value) if value is not None else "{}")
            elif key == "name":
                set_clauses.append("name = ?")
                params.append(str(value).strip())
            else:
                set_clauses.append(f"{key} = ?")
                params.append(value)

        if not set_clauses:
            return self._row_to_appointment_type(row)

        now = utc_now_iso()
        set_clauses.append("updated_at = ?")
        params.append(now)
        params.append(appointment_type_id)

        with conn:
            conn.execute(
                f"UPDATE appointment_types SET {', '.join(set_clauses)} WHERE id = ?;",
                params,
            )
            updated_row = conn.execute(
                "SELECT * FROM appointment_types WHERE id = ?;", (appointment_type_id,)
            ).fetchone()

        _after = self._row_to_appointment_type(updated_row).to_dict()

        self.audit.log(
            action="update",
            entity_type="appointment_type",
            entity_id=appointment_type_id,
            change_summary=f"Updated appointment type {appointment_type_id}",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_after,
                fields=_AUDITABLE_APPOINTMENT_TYPE_FIELDS,
            ),
        )
        return self._row_to_appointment_type(updated_row)

    # ==========================================
    # STAFF SCHEDULES (B6.7)
    # ==========================================

    def create_staff_schedule(self, schedule: StaffSchedule, actor: AuthContext) -> StaffSchedule:
        if not actor.has_permission(PERM_WRITE_STAFF_SCHEDULES):
            raise PermissionError("Actor lacks permission to write staff schedules")

        now = utc_now_iso()
        schedule.created_at = now
        schedule.updated_at = now

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO staff_schedules (user_id, title, start_time, end_time, status, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (schedule.user_id, schedule.title, schedule.start_time, schedule.end_time, schedule.status, schedule.notes, now, now)
            )
            schedule.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="staff_schedule",
            entity_id=schedule.id,
            change_summary=f"Created staff schedule '{schedule.title}'",
            actor=actor,
            details=build_audit_details(after=schedule.to_dict()),
        )

        if self.notification:
            user_row = conn.execute("SELECT email, full_name FROM users WHERE id = ?", (schedule.user_id,)).fetchone()
            if user_row and user_row["email"]:
                appointment_dict = {
                    "uid": f"staff-sched-{schedule.id}",
                    "ics_sequence": 0,
                    "title": schedule.title,
                    "start": schedule.start_time,
                    "end": schedule.end_time,
                    "attendee_email": user_row["email"],
                    "attendee_name": user_row["full_name"]
                }
                try:
                    self.notification.send_calendar_invite(
                        to_email=user_row["email"],
                        appointment=appointment_dict,
                        text=f"You have been scheduled: {schedule.title}"
                    )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("Failed to send staff schedule ICS invite: %s", e)

        return schedule

    def list_staff_schedules(self, actor: AuthContext, user_id: Optional[int] = None) -> List[StaffSchedule]:
        if not actor.has_permission(PERM_READ_STAFF_SCHEDULES):
            raise PermissionError("Actor lacks permission to read staff schedules")

        query = "SELECT * FROM staff_schedules WHERE 1=1"
        params = []
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)

        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [StaffSchedule.from_row(row) for row in rows]

    def update_staff_schedule(self, schedule_id: int, updates: Dict[str, Any], actor: AuthContext) -> Optional[StaffSchedule]:
        if not actor.has_permission(PERM_WRITE_STAFF_SCHEDULES):
            raise PermissionError("Actor lacks permission to write staff schedules")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM staff_schedules WHERE id = ?", (schedule_id,)).fetchone()
        if not row:
            return None

        before = StaffSchedule.from_row(row).to_dict()

        set_clauses = []
        params = []
        allowed = {"title", "start_time", "end_time", "status", "notes"}
        for k, v in updates.items():
            if k in allowed:
                set_clauses.append(f"{k} = ?")
                params.append(v)

        if not set_clauses:
            return StaffSchedule.from_row(row)

        now = utc_now_iso()
        set_clauses.append("updated_at = ?")
        params.append(now)
        params.append(schedule_id)

        with conn:
            conn.execute(
                f"UPDATE staff_schedules SET {', '.join(set_clauses)} WHERE id = ?",
                params
            )

        after_row = conn.execute("SELECT * FROM staff_schedules WHERE id = ?", (schedule_id,)).fetchone()
        after = StaffSchedule.from_row(after_row)

        self.audit.log(
            action="update",
            entity_type="staff_schedule",
            entity_id=schedule_id,
            change_summary=f"Updated staff schedule {schedule_id}",
            actor=actor,
            details=build_audit_details(before=before, after=after.to_dict()),
        )

        needs_invite = any(k in updates for k in ("title", "start_time", "end_time"))
        if self.notification and needs_invite:
            user_row = conn.execute("SELECT email, full_name FROM users WHERE id = ?", (after.user_id,)).fetchone()
            if user_row and user_row["email"]:
                import time
                appointment_dict = {
                    "uid": f"staff-sched-{after.id}",
                    "ics_sequence": int(time.time()),
                    "title": after.title,
                    "start": after.start_time,
                    "end": after.end_time,
                    "attendee_email": user_row["email"],
                    "attendee_name": user_row["full_name"]
                }
                try:
                    self.notification.send_calendar_invite(
                        to_email=user_row["email"],
                        appointment=appointment_dict,
                        text=f"Your schedule has been updated: {after.title}"
                    )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning("Failed to send staff schedule ICS invite on update: %s", e)

        return after

    def delete_staff_schedule(self, schedule_id: int, actor: AuthContext) -> None:
        if not actor.has_permission(PERM_WRITE_STAFF_SCHEDULES):
            raise PermissionError("Actor lacks permission to write staff schedules")

        conn = self.db.get_connection()
        with conn:
            conn.execute("DELETE FROM staff_schedules WHERE id = ?", (schedule_id,))

        self.audit.log(
            action="delete",
            entity_type="staff_schedule",
            entity_id=schedule_id,
            change_summary=f"Deleted staff schedule {schedule_id}",
            actor=actor,
            details=build_audit_details(snapshot={"id": schedule_id}),
        )
