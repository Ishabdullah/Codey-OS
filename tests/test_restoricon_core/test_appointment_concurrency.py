"""
Tests for appointment_types.max_concurrent enforcement (final scheduling
round, Phase 4). Ish's decision: caps count SAME-TYPE only (no shared/
global cap across types this round). Buffer-minutes semantics mirror
Aigentik-CLI's calendar.js `hasConflict()` exactly: the buffer expands
the EXISTING appointment's window on both sides (symmetric), and the
comparison is a strict half-open `new_start < row_end+buf and
new_end > row_start-buf`.
"""

import json

import pytest

from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Appointment, AppointmentType, ScheduleConfig
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.scheduling_service import SchedulingService
from restoricon_core.api.routes import APIRouter


@pytest.fixture
def test_setup():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)
    scheduling_service = SchedulingService(db, audit_service)
    automation_service = AutomationService(db, audit_service)
    communication_service = CommunicationService(db)

    admin_user = auth_service.create_user(
        username="admin",
        plain_password="Password123",
        full_name="Admin",
        email="admin@test.com",
        role=ROLE_ADMIN,
    )
    admin_actor = AuthContext(
        user_id=admin_user.id, username="admin", role=ROLE_ADMIN, actor_type="human"
    )
    admin_token = auth_service.create_token(admin_user)

    router = APIRouter(
        auth_service=auth_service,
        crm_service=crm_service,
        scheduling_service=scheduling_service,
        automation_service=automation_service,
        comm_service=communication_service,
        audit_service=audit_service,
    )

    return {
        "db": db,
        "scheduling": scheduling_service,
        "admin_actor": admin_actor,
        "admin_token": admin_token,
        "router": router,
    }


def _make_type(setup, max_concurrent=1, active=1):
    svc = setup["scheduling"]
    admin = setup["admin_actor"]
    t = svc.create_appointment_type(
        AppointmentType(name=f"Type-{max_concurrent}-{active}", max_concurrent=max_concurrent),
        admin,
    )
    if not active:
        svc.update_appointment_type(t.id, {"active": 0}, admin)
        t = svc.get_appointment_type(t.id, admin)
    return t


def _appt(**kwargs):
    defaults = dict(title="Booking", status="confirmed")
    defaults.update(kwargs)
    return Appointment(**defaults)


# ---------------------------------------------------------------------------
# create_appointment: cap enforcement
# ---------------------------------------------------------------------------

def test_cap_1_second_overlapping_same_type_confirmed_rejected(test_setup):
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    t = _make_type(test_setup, max_concurrent=1)

    svc.create_appointment(
        _appt(appointment_type_id=t.id, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    with pytest.raises(ValueError):
        svc.create_appointment(
            _appt(appointment_type_id=t.id, start_time="2026-10-01T10:30:00+00:00", end_time="2026-10-01T11:30:00+00:00"),
            admin,
        )


def test_cap_2_allows_exactly_two_third_rejected(test_setup):
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    t = _make_type(test_setup, max_concurrent=2)

    svc.create_appointment(
        _appt(appointment_type_id=t.id, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    svc.create_appointment(
        _appt(appointment_type_id=t.id, start_time="2026-10-01T10:15:00+00:00", end_time="2026-10-01T11:15:00+00:00"),
        admin,
    )
    with pytest.raises(ValueError):
        svc.create_appointment(
            _appt(appointment_type_id=t.id, start_time="2026-10-01T10:30:00+00:00", end_time="2026-10-01T11:30:00+00:00"),
            admin,
        )


def test_different_types_same_time_both_succeed(test_setup):
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    t1 = _make_type(test_setup, max_concurrent=1)
    t2 = _make_type(test_setup, max_concurrent=1)

    a1 = svc.create_appointment(
        _appt(appointment_type_id=t1.id, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    a2 = svc.create_appointment(
        _appt(appointment_type_id=t2.id, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    assert a1.id is not None and a2.id is not None


def test_negotiating_row_does_not_count_toward_cap(test_setup):
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    t = _make_type(test_setup, max_concurrent=1)

    # Two negotiating rows at the same slot -- never counted.
    svc.create_appointment(
        _appt(appointment_type_id=t.id, status="negotiating", start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    svc.create_appointment(
        _appt(appointment_type_id=t.id, status="negotiating", start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    # First confirmed at that slot succeeds.
    svc.create_appointment(
        _appt(appointment_type_id=t.id, status="confirmed", start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    # A second confirmed at the same slot is rejected (cap 1).
    with pytest.raises(ValueError):
        svc.create_appointment(
            _appt(appointment_type_id=t.id, status="confirmed", start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
            admin,
        )


def test_cancelled_row_does_not_count(test_setup):
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    t = _make_type(test_setup, max_concurrent=1)

    cancelled = svc.create_appointment(
        _appt(appointment_type_id=t.id, status="confirmed", start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    svc.update_appointment_status(cancelled.id, "cancelled", admin)

    # A new confirmed booking at the same slot succeeds -- the cancelled
    # row no longer counts.
    created = svc.create_appointment(
        _appt(appointment_type_id=t.id, status="confirmed", start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    assert created.id is not None


# ---------------------------------------------------------------------------
# update_appointment
# ---------------------------------------------------------------------------

def test_update_appointment_moving_onto_full_slot_rejected(test_setup):
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    t = _make_type(test_setup, max_concurrent=1)

    svc.create_appointment(
        _appt(appointment_type_id=t.id, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    other = svc.create_appointment(
        _appt(appointment_type_id=t.id, start_time="2026-10-02T10:00:00+00:00", end_time="2026-10-02T11:00:00+00:00"),
        admin,
    )
    with pytest.raises(ValueError):
        svc.update_appointment(
            other.id,
            {"start_time": "2026-10-01T10:15:00+00:00", "end_time": "2026-10-01T11:15:00+00:00"},
            admin,
        )


def test_update_appointment_no_time_status_change_on_full_slot_succeeds(test_setup):
    """Exclude-self must work: editing notes on a row that IS one of the
    (cap-1) confirmed rows at a full slot must not reject itself."""
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    t = _make_type(test_setup, max_concurrent=1)

    appt = svc.create_appointment(
        _appt(appointment_type_id=t.id, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    updated = svc.update_appointment(appt.id, {"notes": "Gate code 4321"}, admin)
    assert updated.notes == "Gate code 4321"


def test_update_appointment_type_id_none_never_blocked(test_setup):
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]

    a1 = svc.create_appointment(
        _appt(appointment_type_id=None, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    a2 = svc.create_appointment(
        _appt(appointment_type_id=None, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    a3 = svc.create_appointment(
        _appt(appointment_type_id=None, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    assert a1.id and a2.id and a3.id


# ---------------------------------------------------------------------------
# update_appointment_status
# ---------------------------------------------------------------------------

def test_status_transition_to_confirmed_onto_full_slot_rejected(test_setup):
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    t = _make_type(test_setup, max_concurrent=1)

    svc.create_appointment(
        _appt(appointment_type_id=t.id, status="confirmed", start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    negotiating = svc.create_appointment(
        _appt(appointment_type_id=t.id, status="negotiating", start_time="2026-10-01T10:15:00+00:00", end_time="2026-10-01T11:15:00+00:00"),
        admin,
    )
    with pytest.raises(ValueError):
        svc.update_appointment_status(negotiating.id, "confirmed", admin)


def test_status_transition_to_confirmed_onto_open_slot_succeeds(test_setup):
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    t = _make_type(test_setup, max_concurrent=1)

    negotiating = svc.create_appointment(
        _appt(appointment_type_id=t.id, status="negotiating", start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    confirmed = svc.update_appointment_status(negotiating.id, "confirmed", admin)
    assert confirmed.status == "confirmed"


def test_reconfirming_already_confirmed_row_at_full_slot_succeeds(test_setup):
    """Exclude-self on the status path: re-confirming a row that is ITSELF
    the cap-1 occupant (e.g. a client retry, or a UI that always posts the
    current status) must not count that row against itself and reject a
    legitimate no-op."""
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    t = _make_type(test_setup, max_concurrent=1)

    appt = svc.create_appointment(
        _appt(appointment_type_id=t.id, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    again = svc.update_appointment_status(appt.id, "confirmed", admin)
    assert again.status == "confirmed"


def test_update_appointment_status_only_confirm_onto_full_slot_rejected(test_setup):
    """Merged-value check on update_appointment: a negotiating row with
    real start/end times, confirmed via update_appointment's `status` key
    (not update_appointment_status), onto an already-full slot -> rejected.
    Exercises `merged_status = updates.get("status", row["status"])`."""
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    t = _make_type(test_setup, max_concurrent=1)

    svc.create_appointment(
        _appt(appointment_type_id=t.id, status="confirmed", start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    negotiating = svc.create_appointment(
        _appt(appointment_type_id=t.id, status="negotiating", start_time="2026-10-01T10:15:00+00:00", end_time="2026-10-01T11:15:00+00:00"),
        admin,
    )
    with pytest.raises(ValueError):
        svc.update_appointment(negotiating.id, {"status": "confirmed"}, admin)


# ---------------------------------------------------------------------------
# Buffer semantics (mirrors calendar.js hasConflict exactly)
# ---------------------------------------------------------------------------

def test_buffer_minutes_rejects_within_buffer_allows_outside(test_setup):
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    svc.upsert_schedule_config(ScheduleConfig(buffer_minutes=30), admin)
    t = _make_type(test_setup, max_concurrent=1)

    svc.create_appointment(
        _appt(appointment_type_id=t.id, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )

    # 11:15-11:45 is within the 30-min buffer of the existing 10:00-11:00
    # (buffered window 09:30-11:30) -> rejected.
    with pytest.raises(ValueError):
        svc.create_appointment(
            _appt(appointment_type_id=t.id, start_time="2026-10-01T11:15:00+00:00", end_time="2026-10-01T11:45:00+00:00"),
            admin,
        )

    # 11:45-12:15 is outside the buffered window -> allowed.
    allowed = svc.create_appointment(
        _appt(appointment_type_id=t.id, start_time="2026-10-01T11:45:00+00:00", end_time="2026-10-01T12:15:00+00:00"),
        admin,
    )
    assert allowed.id is not None


# ---------------------------------------------------------------------------
# Fail-open / fail-closed edge cases
# ---------------------------------------------------------------------------

def test_missing_appointment_type_id_fails_open(test_setup):
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]

    a1 = svc.create_appointment(
        _appt(appointment_type_id=99999, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    a2 = svc.create_appointment(
        _appt(appointment_type_id=99999, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    assert a1.id and a2.id


def test_deactivated_type_still_enforces_cap(test_setup):
    """Chosen interpretation: only a genuinely MISSING type id fails open.
    A deactivated type (active=0) keeps its previously-set max_concurrent
    and still enforces it -- Ish deactivating a type (stopping new bookings
    of it) should not also silently disable the cap on what's already
    booked under it."""
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    t = _make_type(test_setup, max_concurrent=1, active=0)
    assert t.active == 0

    svc.create_appointment(
        _appt(appointment_type_id=t.id, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )
    with pytest.raises(ValueError):
        svc.create_appointment(
            _appt(appointment_type_id=t.id, start_time="2026-10-01T10:30:00+00:00", end_time="2026-10-01T11:30:00+00:00"),
            admin,
        )


# ---------------------------------------------------------------------------
# Route-level: 400 not 500
# ---------------------------------------------------------------------------

def test_route_post_appointment_over_cap_is_400(test_setup):
    router = test_setup["router"]
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    admin_token = test_setup["admin_token"]
    hdr = {"Authorization": f"Bearer {admin_token}"}

    t = _make_type(test_setup, max_concurrent=1)
    svc.create_appointment(
        _appt(appointment_type_id=t.id, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )

    status, _, body = router.handle_request(
        "POST",
        "/api/v1/appointments",
        headers=hdr,
        body_bytes=json.dumps(
            {
                "title": "Overbooked",
                "status": "confirmed",
                "appointment_type_id": t.id,
                "start_time": "2026-10-01T10:30:00+00:00",
                "end_time": "2026-10-01T11:30:00+00:00",
            }
        ).encode(),
    )
    assert status == 400
    assert "error" in body


# ---------------------------------------------------------------------------
# NEW-501: precondition check for a would-be WHERE-clause push-down of the
# concurrency-cap query. Confirmed this round that a single normalized
# timestamp format does NOT hold across this codebase: routes.py's
# appointment create/update do zero timestamp normalization, models.py's
# start_time/end_time are plain unconstrained strings, the admin
# dashboard's date/time inputs are free-text, and migrate_aigentik.py
# pulls external start/end values verbatim -- a non-UTC offset can reach
# the DB through any of these paths. This is a mutation-style test proving
# the CURRENT Python parse-and-compare approach in
# _assert_within_concurrency_cap correctly handles a mixed-format set of
# already-stored rows (which a naive lexicographic SQL WHERE comparison
# would not) -- the property a future WHERE-clause optimization would
# silently break. Not fixed/changed this round: production code
# unchanged, this is a regression guard only.
# ---------------------------------------------------------------------------

def test_concurrency_cap_handles_mixed_timestamp_formats_across_stored_rows(test_setup):
    """Insert confirmed rows of the same type with start_time/end_time in
    five different formats -- trailing Z, +00:00 offset, microseconds,
    no-seconds, and a non-UTC offset (-05:00) -- all representing times
    that collide with a would-be new booking at the cap boundary. Asserts
    the cap still correctly raises once hit, proving the mixed formats are
    all parsed and compared correctly today."""
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    t = _make_type(test_setup, max_concurrent=5)
    db = test_setup["db"]
    conn = db.get_connection()

    # Insert rows directly (bypassing create_appointment's own possible
    # normalization, if any) so each row's stored format is exactly what
    # this test intends to exercise -- proving the READ/parse side of
    # _assert_within_concurrency_cap, not any write-side normalization.
    mixed_format_rows = [
        # (start_time, end_time) -- all overlap 2026-10-01T10:00-11:00 UTC.
        ("2026-10-01T10:00:00Z", "2026-10-01T11:00:00Z"),
        ("2026-10-01T10:00:00+00:00", "2026-10-01T11:00:00+00:00"),
        ("2026-10-01T10:00:00.123456+00:00", "2026-10-01T11:00:00.123456+00:00"),
        ("2026-10-01T10:00", "2026-10-01T11:00"),
        # Non-UTC offset representing the SAME real-world instant as the
        # first row above (05:00 -05:00 == 10:00 UTC).
        ("2026-10-01T05:00:00-05:00", "2026-10-01T06:00:00-05:00"),
    ]
    with conn:
        for start, end in mixed_format_rows:
            conn.execute(
                """
                INSERT INTO appointments (
                    appointment_type_id, title, status, start_time, end_time,
                    created_at, updated_at
                ) VALUES (?, 'Existing', 'confirmed', ?, ?, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                """,
                (t.id, start, end),
            )

    # Cap is 5; all 5 rows above collide with a new booking at the same
    # slot -> the 6th (this new one) must be rejected.
    with pytest.raises(ValueError):
        svc.create_appointment(
            _appt(appointment_type_id=t.id, start_time="2026-10-01T10:15:00+00:00", end_time="2026-10-01T10:45:00+00:00"),
            admin,
        )


# ---------------------------------------------------------------------------
# NEW-516: an existing row with a genuinely unparseable stored timestamp is
# silently SKIPPED (not counted) by _assert_within_concurrency_cap's
# `except ValueError: continue`. Chosen fix this round is instrumentation
# only -- log a warning when this happens -- with no change to the skip
# behavior itself. This test proves both halves: the skip is still a
# no-op skip (no regression), and a warning is now logged so it's no
# longer silent.
# ---------------------------------------------------------------------------

def test_unparseable_stored_timestamp_skipped_but_logs_warning(test_setup, caplog):
    """A row with a garbage (non-ISO) start_time must not count toward the
    cap (matches pre-existing behavior), but a warning must now be logged
    naming the row id and the unparseable value."""
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    t = _make_type(test_setup, max_concurrent=1)
    db = test_setup["db"]
    conn = db.get_connection()

    with conn:
        cursor = conn.execute(
            """
            INSERT INTO appointments (
                appointment_type_id, title, status, start_time, end_time,
                created_at, updated_at
            ) VALUES (?, 'Corrupt', 'confirmed', ?, ?, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
            """,
            (t.id, "not-a-real-timestamp", "2026-10-01T11:00:00+00:00"),
        )
        corrupt_row_id = cursor.lastrowid

    caplog.set_level("WARNING", logger="restoricon_core.services.scheduling_service")

    # Cap is 1; the only existing row has an unparseable start_time and
    # must be skipped (not counted), so this new booking at the same slot
    # must still succeed -- no regression from the pre-existing skip
    # behavior.
    svc.create_appointment(
        _appt(appointment_type_id=t.id, start_time="2026-10-01T10:00:00+00:00", end_time="2026-10-01T11:00:00+00:00"),
        admin,
    )

    recs = [
        r for r in caplog.records
        if r.name == "restoricon_core.services.scheduling_service" and r.levelname == "WARNING"
    ]
    assert len(recs) == 1, f"expected exactly one warning; log={caplog.text!r}"
    msg = recs[0].getMessage()
    assert f"id={corrupt_row_id}" in msg
    assert "not-a-real-timestamp" in msg
