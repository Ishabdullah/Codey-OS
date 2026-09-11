"""
Final scheduling round, Phase 3: Business Hours (schedule_config.
working_hours) vs. per-type scheduling hours (appointment_types.
scheduling_hours) semantics guard-rail.

No new schema and no new enforcement logic this phase -- these tests lock
in the two things Phase 3 is documenting:

  1. Both fields round-trip a full/partial 7-day grid unchanged (storage
     only -- no interpretation happens on write or read).
  2. F3: Core does NOT enforce either field against Appointment.start_time/
     end_time anywhere. The guard-rail test below books/updates/transitions
     an appointment well outside any configured hours window and asserts
     it is accepted -- if someone later "helpfully" adds Core-side hours
     validation without re-reading this constraint, this test is the one
     that fails.

Hours enforcement is entirely client-side in calendar.js (device-local
Date math) -- Core has no timezone field, and Appointment.start_time/
end_time are UTC ISO strings, so a naive "HH:MM" vs. UTC-timestamp
comparison here would be silently wrong by hours.
"""

import pytest

from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Appointment, AppointmentType, ScheduleConfig
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.scheduling_service import SchedulingService


# A full 7-day business-hours grid: closed Sun, otherwise 09:00-17:00.
FULL_WEEK_GRID = {
    "mon": {"start": "09:00", "end": "17:00"},
    "tue": {"start": "09:00", "end": "17:00"},
    "wed": {"start": "09:00", "end": "17:00"},
    "thu": {"start": "09:00", "end": "17:00"},
    "fri": {"start": "09:00", "end": "17:00"},
    "sat": {"start": "10:00", "end": "14:00"},
    "sun": None,
}

PARTIAL_GRID = {"mon": {"start": "10:00", "end": "16:00"}}


@pytest.fixture
def setup():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    scheduling_service = SchedulingService(db, audit_service)

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

    return {
        "db": db,
        "scheduling": scheduling_service,
        "admin": admin_actor,
    }


# ---------------------------------------------------------------------------
# Round-trip: business hours (schedule_config.working_hours)
# ---------------------------------------------------------------------------

def test_business_hours_full_week_grid_round_trips_unchanged(setup):
    svc = setup["scheduling"]
    admin = setup["admin"]

    saved = svc.upsert_schedule_config(ScheduleConfig(working_hours=FULL_WEEK_GRID), admin)
    assert saved.working_hours == FULL_WEEK_GRID

    fetched = svc.get_schedule_config(admin)
    assert fetched is not None
    assert fetched.working_hours == FULL_WEEK_GRID


# ---------------------------------------------------------------------------
# Round-trip: per-type scheduling hours (appointment_types.scheduling_hours)
# ---------------------------------------------------------------------------

def test_appointment_type_scheduling_hours_empty_by_default_means_inherit(setup):
    """Empty {} is the default on create and means 'inherit business
    hours, no narrower window' -- not 'never available'. This test only
    pins the round-trip; the guard-rail test below confirms Core places
    no interpretation on this at all."""
    svc = setup["scheduling"]
    admin = setup["admin"]

    created = svc.create_appointment_type(AppointmentType(name="Standard"), admin)
    assert created.scheduling_hours == {}
    assert svc.get_appointment_type(created.id, admin).scheduling_hours == {}


def test_appointment_type_scheduling_hours_create_with_partial_grid_round_trips(setup):
    """Coverage gap vs. the Phase 2 test suite: passing a non-empty
    scheduling_hours directly into create_appointment_type (not just via
    a later update)."""
    svc = setup["scheduling"]
    admin = setup["admin"]

    created = svc.create_appointment_type(
        AppointmentType(name="Consultation", scheduling_hours=PARTIAL_GRID), admin
    )
    assert created.scheduling_hours == PARTIAL_GRID
    assert svc.get_appointment_type(created.id, admin).scheduling_hours == PARTIAL_GRID


def test_appointment_type_scheduling_hours_full_week_grid_round_trips_via_update(setup):
    svc = setup["scheduling"]
    admin = setup["admin"]

    created = svc.create_appointment_type(AppointmentType(name="Emergency"), admin)
    updated = svc.update_appointment_type(
        created.id, {"scheduling_hours": FULL_WEEK_GRID}, admin
    )
    assert updated.scheduling_hours == FULL_WEEK_GRID
    assert svc.get_appointment_type(created.id, admin).scheduling_hours == FULL_WEEK_GRID


def test_appointment_type_scheduling_hours_narrowed_back_to_empty_means_inherit_again(setup):
    """The other direction of the same semantic: a type with a populated
    per-type window can be reset to {} to fall back to inheriting business
    hours -- {} is a valid, meaningful state to return to, not an error."""
    svc = setup["scheduling"]
    admin = setup["admin"]

    created = svc.create_appointment_type(
        AppointmentType(name="Warranty visit", scheduling_hours=PARTIAL_GRID), admin
    )
    assert created.scheduling_hours == PARTIAL_GRID

    reverted = svc.update_appointment_type(created.id, {"scheduling_hours": {}}, admin)
    assert reverted.scheduling_hours == {}
    assert svc.get_appointment_type(created.id, admin).scheduling_hours == {}


# ---------------------------------------------------------------------------
# F3 guard-rail: Core enforces NEITHER hours field against appointment times
# ---------------------------------------------------------------------------

def test_core_does_not_enforce_hours_on_appointment_lifecycle(setup):
    """Configure a business-hours grid that is CLOSED (working_hours=None
    equivalent -- Sunday closed / narrow weekday windows) and a per-type
    scheduling_hours window that would also reject a 3am booking, then
    book, update, and status-transition an appointment at 3am UTC on a
    'closed' day. All three must succeed -- Core does not compare
    start_time/end_time against either hours field anywhere (F3); that
    enforcement lives entirely client-side in calendar.js. If someone
    later adds Core-side hours validation without re-reading this
    constraint, this test is the one that fails.
    """
    svc = setup["scheduling"]
    admin = setup["admin"]

    # Prove the hours actually persisted -- otherwise a silent
    # empty-merge bug would make this test pass for the wrong reason
    # (nothing to violate).
    saved_config = svc.upsert_schedule_config(ScheduleConfig(working_hours=FULL_WEEK_GRID), admin)
    assert saved_config.working_hours == FULL_WEEK_GRID
    assert svc.get_schedule_config(admin).working_hours == FULL_WEEK_GRID

    appt_type = svc.create_appointment_type(
        AppointmentType(name="Narrow window", scheduling_hours=PARTIAL_GRID), admin
    )
    assert svc.get_appointment_type(appt_type.id, admin).scheduling_hours == PARTIAL_GRID

    # 2026-09-13 is a Sunday (working_hours['sun'] is None / closed) and
    # 03:00 UTC is outside every configured window (business AND per-type).
    created = svc.create_appointment(
        Appointment(
            title="3am Sunday booking",
            start_time="2026-09-13T03:00:00Z",
            end_time="2026-09-13T03:30:00Z",
            appointment_type_id=appt_type.id,
            status="confirmed",
        ),
        admin,
    )
    assert created.id is not None
    assert created.start_time == "2026-09-13T03:00:00Z"

    # Updating times further out-of-window is also unconstrained.
    updated = svc.update_appointment(
        created.id,
        {"start_time": "2026-09-13T02:00:00Z", "end_time": "2026-09-13T02:30:00Z"},
        admin,
    )
    assert updated.start_time == "2026-09-13T02:00:00Z"

    # A status transition on this out-of-hours appointment still succeeds
    # (update_appointment_status never even looks at start_time/end_time).
    transitioned = svc.update_appointment_status(created.id, "completed", admin)
    assert transitioned.status == "completed"
