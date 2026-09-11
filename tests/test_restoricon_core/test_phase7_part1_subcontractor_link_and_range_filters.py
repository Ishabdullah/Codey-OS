"""
Tests for Phase 7 Part 1 (final scheduling round, admin-dashboard program,
2026-09-11):

  Piece A -- subcontractors.user_id links a subcontractor to a real users
  row so staff_schedules (user_id NOT NULL) can represent their schedule
  unchanged (Ish's decision resolving NEW-486).

  Piece B -- date-range filters on list_appointments/list_staff_schedules
  for a calendar-view use case (previously "50 most recent system-wide"
  with no way to scope to a displayed month).
"""

import json
import sqlite3

import pytest

from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Appointment, StaffSchedule, Subcontractor
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.scheduling_service import SchedulingService
from restoricon_core.api.routes import APIRouter


# Pre-round subcontractors DDL: the shape the table had before user_id
# existed. Used to exercise the additive migration path in
# _migrate_schema() -- an in-memory DB always gets the column via CREATE
# TABLE, so it can never actually test the ALTER TABLE branch.
_LEGACY_SUBCONTRACTORS_DDL = """
CREATE TABLE subcontractors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE,
    contact_external_id TEXT,
    company_name TEXT NOT NULL,
    legal_name TEXT,
    dba TEXT,
    contact_name TEXT,
    title TEXT,
    phone TEXT,
    email TEXT COLLATE NOCASE,
    website TEXT,
    primary_trade TEXT,
    secondary_trades_json TEXT NOT NULL DEFAULT '[]',
    service_area TEXT,
    years_in_business INTEGER,
    crew_size INTEGER,
    residential_experience TEXT,
    commercial_experience TEXT,
    typical_project_size TEXT,
    availability TEXT,
    emergency_availability TEXT,
    license_required INTEGER,
    license_type TEXT,
    license_number TEXT,
    license_expiration TEXT,
    license_status TEXT,
    general_liability TEXT,
    workers_comp TEXT,
    coi_received INTEGER NOT NULL DEFAULT 0,
    coi_expiration TEXT,
    additional_insured_status TEXT,
    insurance_status TEXT,
    w9_received INTEGER NOT NULL DEFAULT 0,
    msa_sent INTEGER NOT NULL DEFAULT 0,
    msa_signed INTEGER NOT NULL DEFAULT 0,
    references_json TEXT NOT NULL DEFAULT '[]',
    portfolio_url TEXT,
    qualification_status TEXT NOT NULL DEFAULT 'QUALIFICATION_IN_PROGRESS',
    recruitment_step TEXT,
    lead_source TEXT,
    last_contact_at TEXT,
    next_followup_at TEXT,
    contact_attempts INTEGER NOT NULL DEFAULT 0,
    dnc_status INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    qualification_data_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


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
        "crm": crm_service,
        "scheduling": scheduling_service,
        "admin_user": admin_user,
        "admin_actor": admin_actor,
        "admin_token": admin_token,
        "router": router,
    }


# ---------------------------------------------------------------------------
# Piece A -- subcontractors.user_id
# ---------------------------------------------------------------------------

def test_subcontractor_user_id_migration_adds_column_to_legacy_db(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_LEGACY_SUBCONTRACTORS_DDL)
    conn.execute(
        "INSERT INTO subcontractors (company_name, created_at, updated_at) "
        "VALUES ('Old Sub Co', '2020-01-01', '2020-01-01');"
    )
    conn.commit()
    conn.close()

    db = DatabaseManager(str(db_path))
    conn = db.get_connection()

    cols = {r["name"] for r in conn.execute("PRAGMA table_info(subcontractors);")}
    assert "user_id" in cols

    # Existing row preserved, new column NULL.
    old = conn.execute("SELECT company_name, user_id FROM subcontractors;").fetchone()
    assert old["company_name"] == "Old Sub Co"
    assert old["user_id"] is None
    db.close()

    # Second construction: no "duplicate column name" error, no-op.
    db2 = DatabaseManager(str(db_path))
    conn2 = db2.get_connection()
    count = conn2.execute("SELECT COUNT(*) FROM subcontractors;").fetchone()[0]
    assert count == 1
    db2.close()


def test_subcontractor_create_defaults_user_id_none(test_setup):
    crm = test_setup["crm"]
    admin = test_setup["admin_actor"]
    sub = crm.create_subcontractor(Subcontractor(company_name="Acme Roofing"), admin)
    assert sub.user_id is None


def test_subcontractor_user_id_service_round_trip(test_setup):
    crm = test_setup["crm"]
    admin = test_setup["admin_actor"]
    admin_user = test_setup["admin_user"]

    sub = crm.create_subcontractor(Subcontractor(company_name="Acme Roofing"), admin)
    assert sub.user_id is None

    updated = crm.update_subcontractor(sub.id, {"user_id": admin_user.id}, admin)
    assert updated.user_id == admin_user.id

    fetched = crm.get_subcontractor(sub.id, admin)
    assert fetched.user_id == admin_user.id


def test_subcontractor_update_user_id_rejects_none(test_setup):
    """Unlinking (user_id -> None) is out of scope this round --
    update_subcontractor's existing None-guard applies uniformly."""
    crm = test_setup["crm"]
    admin = test_setup["admin_actor"]
    sub = crm.create_subcontractor(Subcontractor(company_name="Acme Roofing"), admin)
    with pytest.raises(ValueError):
        crm.update_subcontractor(sub.id, {"user_id": None}, admin)


def test_subcontractor_user_id_route_round_trip(test_setup):
    router = test_setup["router"]
    admin_token = test_setup["admin_token"]
    admin_user = test_setup["admin_user"]
    hdr = {"Authorization": f"Bearer {admin_token}"}

    status, _, body = router.handle_request(
        "POST", "/api/v1/subcontractors", headers=hdr,
        body_bytes=json.dumps({"company_name": "Route Roofing Co"}).encode(),
    )
    assert status == 201
    sub_id = body["subcontractor"]["id"]
    assert body["subcontractor"]["user_id"] is None

    status, _, body = router.handle_request(
        "POST", f"/api/v1/subcontractors/{sub_id}/update", headers=hdr,
        body_bytes=json.dumps({"user_id": admin_user.id}).encode(),
    )
    assert status == 200
    assert body["subcontractor"]["user_id"] == admin_user.id

    status, _, body = router.handle_request(
        "GET", f"/api/v1/subcontractors/{sub_id}", headers=hdr, body_bytes=b"",
    )
    assert status == 200
    assert body["subcontractor"]["user_id"] == admin_user.id


# ---------------------------------------------------------------------------
# Piece B -- date-range filters
# ---------------------------------------------------------------------------

def _appt(**kwargs):
    defaults = dict(title="Booking", status="confirmed")
    defaults.update(kwargs)
    return Appointment(**defaults)


def test_list_appointments_range_filter_inclusive_boundaries(test_setup):
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]

    a1 = svc.create_appointment(
        _appt(title="A1", start_time="2026-10-01T09:00:00+00:00", end_time="2026-10-01T10:00:00+00:00"),
        admin,
    )
    a2 = svc.create_appointment(
        _appt(title="A2", start_time="2026-10-15T09:00:00+00:00", end_time="2026-10-15T10:00:00+00:00"),
        admin,
    )
    a3 = svc.create_appointment(
        _appt(title="A3", start_time="2026-10-31T23:59:00+00:00", end_time="2026-11-01T00:59:00+00:00"),
        admin,
    )
    # Outside the range on both ends.
    svc.create_appointment(
        _appt(title="A0", start_time="2026-09-30T09:00:00+00:00", end_time="2026-09-30T10:00:00+00:00"),
        admin,
    )
    svc.create_appointment(
        _appt(title="A4", start_time="2026-11-01T00:00:01+00:00", end_time="2026-11-01T01:00:00+00:00"),
        admin,
    )

    results = svc.list_appointments(admin, start="2026-10-01", end="2026-10-31", limit=50)
    titles = {a.title for a in results}
    assert titles == {"A1", "A2", "A3"}
    ids = {a.id for a in results}
    assert ids == {a1.id, a2.id, a3.id}


def test_list_appointments_range_filter_excludes_null_start_time(test_setup):
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]

    # A negotiating appointment with no slot picked yet.
    svc.create_appointment(
        Appointment(title="Negotiating", status="negotiating"),
        admin,
    )
    svc.create_appointment(
        _appt(title="Confirmed", start_time="2026-10-05T09:00:00+00:00", end_time="2026-10-05T10:00:00+00:00"),
        admin,
    )

    results = svc.list_appointments(admin, start="2026-10-01", end="2026-10-31", limit=50)
    titles = {a.title for a in results}
    assert titles == {"Confirmed"}


def test_list_appointments_one_sided_ranges(test_setup):
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]

    svc.create_appointment(
        _appt(title="Early", start_time="2026-10-01T09:00:00+00:00", end_time="2026-10-01T10:00:00+00:00"),
        admin,
    )
    svc.create_appointment(
        _appt(title="Late", start_time="2026-10-20T09:00:00+00:00", end_time="2026-10-20T10:00:00+00:00"),
        admin,
    )

    only_start = svc.list_appointments(admin, start="2026-10-10", limit=50)
    assert {a.title for a in only_start} == {"Late"}

    only_end = svc.list_appointments(admin, end="2026-10-10", limit=50)
    assert {a.title for a in only_end} == {"Early"}


def test_list_appointments_no_range_unchanged(test_setup):
    """No start/end -> identical to pre-round behavior (customer_id/status/
    limit/offset only, ORDER BY start_time DESC)."""
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    svc.create_appointment(
        _appt(title="Only", start_time="2026-10-01T09:00:00+00:00", end_time="2026-10-01T10:00:00+00:00"),
        admin,
    )
    results = svc.list_appointments(admin, limit=50)
    assert any(a.title == "Only" for a in results)


def test_list_staff_schedules_range_filter_inclusive_boundaries(test_setup):
    db = test_setup["db"]
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    admin_user = test_setup["admin_user"]

    conn = db.get_connection()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, full_name, email, role, created_at, updated_at) "
        "VALUES (99, 'tech', 'hash', 'Tech User', 'tech@test.com', 'technician', '2024-01-01', '2024-01-01')"
    )
    conn.commit()

    s1 = svc.create_staff_schedule(
        StaffSchedule(id=None, user_id=99, title="S1", start_time="2026-10-01T09:00:00Z",
                       end_time="2026-10-01T17:00:00Z", status="scheduled", notes=None),
        admin,
    )
    s2 = svc.create_staff_schedule(
        StaffSchedule(id=None, user_id=99, title="S2", start_time="2026-10-31T09:00:00Z",
                       end_time="2026-10-31T17:00:00Z", status="scheduled", notes=None),
        admin,
    )
    svc.create_staff_schedule(
        StaffSchedule(id=None, user_id=99, title="Outside", start_time="2026-11-01T09:00:00Z",
                       end_time="2026-11-01T17:00:00Z", status="scheduled", notes=None),
        admin,
    )

    results = svc.list_staff_schedules(admin, start="2026-10-01", end="2026-10-31")
    titles = {s.title for s in results}
    assert titles == {"S1", "S2"}
    ids = {s.id for s in results}
    assert ids == {s1.id, s2.id}
    assert admin_user.id != 99  # sanity: distinct users, filter is on start_time not user_id


def test_list_staff_schedules_default_limit_applied(test_setup):
    """Previously unlimited -- now defaults to 200 so a plain list call
    can't return an unbounded table."""
    db = test_setup["db"]
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]

    conn = db.get_connection()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, full_name, email, role, created_at, updated_at) "
        "VALUES (99, 'tech', 'hash', 'Tech User', 'tech@test.com', 'technician', '2024-01-01', '2024-01-01')"
    )
    conn.commit()

    for i in range(5):
        svc.create_staff_schedule(
            StaffSchedule(id=None, user_id=99, title=f"S{i}", start_time=f"2026-10-{i+1:02d}T09:00:00Z",
                           end_time=f"2026-10-{i+1:02d}T17:00:00Z", status="scheduled", notes=None),
            admin,
        )

    results = svc.list_staff_schedules(admin, limit=3)
    assert len(results) == 3


def test_route_appointments_start_end_query_params(test_setup):
    router = test_setup["router"]
    admin_token = test_setup["admin_token"]
    hdr = {"Authorization": f"Bearer {admin_token}"}

    status, _, body = router.handle_request(
        "POST", "/api/v1/appointments", headers=hdr,
        body_bytes=json.dumps({
            "title": "In range", "status": "confirmed",
            "start_time": "2026-10-05T09:00:00+00:00", "end_time": "2026-10-05T10:00:00+00:00",
        }).encode(),
    )
    assert status == 201
    router.handle_request(
        "POST", "/api/v1/appointments", headers=hdr,
        body_bytes=json.dumps({
            "title": "Out of range", "status": "confirmed",
            "start_time": "2026-11-05T09:00:00+00:00", "end_time": "2026-11-05T10:00:00+00:00",
        }).encode(),
    )

    status, _, body = router.handle_request(
        "GET", "/api/v1/appointments?start=2026-10-01&end=2026-10-31", headers=hdr, body_bytes=b"",
    )
    assert status == 200
    titles = {a["title"] for a in body["appointments"]}
    assert titles == {"In range"}


def test_route_staff_schedules_start_end_query_params(test_setup):
    db = test_setup["db"]
    router = test_setup["router"]
    admin_token = test_setup["admin_token"]
    hdr = {"Authorization": f"Bearer {admin_token}"}

    conn = db.get_connection()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, full_name, email, role, created_at, updated_at) "
        "VALUES (99, 'tech', 'hash', 'Tech User', 'tech@test.com', 'technician', '2024-01-01', '2024-01-01')"
    )
    conn.commit()

    router.handle_request(
        "POST", "/api/v1/staff-schedules", headers=hdr,
        body_bytes=json.dumps({
            "id": None, "user_id": 99, "title": "In range",
            "start_time": "2026-10-05T09:00:00Z", "end_time": "2026-10-05T17:00:00Z",
            "status": "scheduled", "notes": None,
        }).encode(),
    )
    router.handle_request(
        "POST", "/api/v1/staff-schedules", headers=hdr,
        body_bytes=json.dumps({
            "id": None, "user_id": 99, "title": "Out of range",
            "start_time": "2026-11-05T09:00:00Z", "end_time": "2026-11-05T17:00:00Z",
            "status": "scheduled", "notes": None,
        }).encode(),
    )

    status, _, body = router.handle_request(
        "GET", "/api/v1/staff-schedules?start=2026-10-01&end=2026-10-31", headers=hdr, body_bytes=b"",
    )
    assert status == 200
    titles = {s["title"] for s in body["schedules"]}
    assert titles == {"In range"}
