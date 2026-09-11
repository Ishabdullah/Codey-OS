"""
Tests for the appointment_types table/model/service/routes (final
scheduling round, Phase 2). This is the "service type" axis (Emergency /
Standard estimate / Consultation) -- SEPARATE from appointments.appointment_type
(the call/in_person modality the bot auto-detects), which stays untouched.
"""

import json
import sqlite3

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_AI_AGENT,
    ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Appointment, AppointmentType
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.scheduling_service import SchedulingService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.api.routes import APIRouter


# Pre-Phase-2 appointments DDL: the shape the table had before
# appointment_type_id existed, and with no appointment_types table at all.
# Used to exercise the additive migration + one-time seed path.
_LEGACY_APPOINTMENTS_DDL = """
CREATE TABLE appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE,
    uid TEXT,
    ics_sequence INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    customer_id INTEGER,
    contact_external_id TEXT,
    attendee_name TEXT,
    attendee_email TEXT COLLATE NOCASE,
    appointment_type TEXT CHECK(appointment_type IN ('call', 'in_person') OR appointment_type IS NULL),
    status TEXT NOT NULL DEFAULT 'confirmed' CHECK(status IN ('confirmed', 'negotiating', 'cancelled', 'completed')),
    rsvp_status TEXT NOT NULL DEFAULT 'pending',
    offered_slots_json TEXT NOT NULL DEFAULT '[]',
    requested_datetime TEXT,
    pending_reschedule_json TEXT,
    form_sent INTEGER NOT NULL DEFAULT 0 CHECK(form_sent IN (0, 1)),
    created_via TEXT NOT NULL DEFAULT 'owner',
    notes TEXT,
    history_json TEXT NOT NULL DEFAULT '[]',
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

    agent_user = auth_service.create_user(
        username="agent",
        plain_password="Password123",
        full_name="AI Agent",
        email="agent@test.com",
        role=ROLE_AI_AGENT,
    )
    agent_actor = AuthContext(
        user_id=agent_user.id, username="agent", role=ROLE_AI_AGENT, actor_type="agent"
    )
    token = auth_service.create_token(agent_user)
    admin_token = auth_service.create_token(admin_user)

    sales_user = auth_service.create_user(
        username="sales",
        plain_password="Password123",
        full_name="Sales Rep",
        email="sales@test.com",
        role=ROLE_SALES,
    )
    sales_actor = AuthContext(
        user_id=sales_user.id, username="sales", role=ROLE_SALES, actor_type="human"
    )

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
        "audit": audit_service,
        "admin_actor": admin_actor,
        "agent_actor": agent_actor,
        "sales_actor": sales_actor,
        "token": token,
        "admin_token": admin_token,
        "router": router,
    }


# ---------------------------------------------------------------------------
# Migration + one-time seed
# ---------------------------------------------------------------------------

def test_migration_creates_table_and_seeds_defaults_once(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_LEGACY_APPOINTMENTS_DDL)
    conn.execute(
        "INSERT INTO appointments (title, created_at, updated_at) "
        "VALUES ('Old Appt', '2020-01-01', '2020-01-01');"
    )
    conn.commit()
    conn.close()

    db = DatabaseManager(str(db_path))
    conn = db.get_connection()

    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")}
    assert "appointment_types" in tables

    appt_cols = {r["name"] for r in conn.execute("PRAGMA table_info(appointments);")}
    assert "appointment_type_id" in appt_cols
    # The untouched modality column is still there.
    assert "appointment_type" in appt_cols

    rows = conn.execute(
        "SELECT name, active, max_concurrent, sort_order FROM appointment_types ORDER BY sort_order;"
    ).fetchall()
    assert [r["name"] for r in rows] == ["Emergency", "Standard estimate", "Consultation"]
    assert all(r["active"] == 1 for r in rows)
    assert all(r["max_concurrent"] == 1 for r in rows)
    assert [r["sort_order"] for r in rows] == [0, 1, 2]

    # Existing appointment row preserved, new column NULL.
    old = conn.execute("SELECT title, appointment_type_id FROM appointments;").fetchone()
    assert old["title"] == "Old Appt"
    assert old["appointment_type_id"] is None
    db.close()

    # Second construction: no re-seed, no error.
    db2 = DatabaseManager(str(db_path))
    conn2 = db2.get_connection()
    count = conn2.execute("SELECT COUNT(*) FROM appointment_types;").fetchone()[0]
    assert count == 3
    db2.close()


def test_fresh_db_seeds_three_defaults(test_setup):
    conn = test_setup["db"].get_connection()
    count = conn.execute("SELECT COUNT(*) FROM appointment_types;").fetchone()[0]
    assert count == 3


# ---------------------------------------------------------------------------
# Service: list / get
# ---------------------------------------------------------------------------

def test_list_appointment_types_active_and_include_inactive(test_setup):
    svc = test_setup["scheduling"]
    actor = test_setup["admin_actor"]

    active = svc.list_appointment_types(actor)
    assert len(active) == 3
    assert [t.name for t in active] == ["Emergency", "Standard estimate", "Consultation"]

    svc.update_appointment_type(active[0].id, {"active": 0}, actor)

    assert len(svc.list_appointment_types(actor)) == 2
    assert len(svc.list_appointment_types(actor, include_inactive=True)) == 3


def test_get_appointment_type(test_setup):
    svc = test_setup["scheduling"]
    actor = test_setup["admin_actor"]
    first = svc.list_appointment_types(actor)[0]
    fetched = svc.get_appointment_type(first.id, actor)
    assert fetched is not None
    assert fetched.name == first.name
    assert svc.get_appointment_type(9999, actor) is None


# ---------------------------------------------------------------------------
# Service: create / update + audit
# ---------------------------------------------------------------------------

def test_create_appointment_type_writes_row_and_audit(test_setup):
    svc = test_setup["scheduling"]
    audit = test_setup["audit"]
    actor = test_setup["admin_actor"]

    created = svc.create_appointment_type(
        AppointmentType(name="Warranty visit", sort_order=5, max_concurrent=2), actor
    )
    assert created.id is not None
    assert created.name == "Warranty visit"
    assert created.max_concurrent == 2

    logs = audit.query_logs(actor, entity_type="appointment_type", entity_id=created.id)
    assert len(logs) == 1
    assert logs[0].action == "create"


def test_update_appointment_type_persists_and_audits(test_setup):
    svc = test_setup["scheduling"]
    audit = test_setup["audit"]
    actor = test_setup["admin_actor"]

    target = svc.list_appointment_types(actor)[2]
    updated = svc.update_appointment_type(
        target.id, {"name": "Consult (virtual)", "max_concurrent": 3, "active": 0}, actor
    )
    assert updated.name == "Consult (virtual)"
    assert updated.max_concurrent == 3
    assert updated.active == 0

    refetched = svc.get_appointment_type(target.id, actor)
    assert refetched.name == "Consult (virtual)"
    assert refetched.max_concurrent == 3

    logs = audit.query_logs(actor, entity_type="appointment_type", entity_id=target.id, action="update")
    assert len(logs) == 1
    changed = logs[0].details["changed_fields"]
    assert changed["name"]["new"] == "Consult (virtual)"
    assert changed["max_concurrent"]["new"] == 3


def test_update_appointment_type_ignores_only_identity_timestamp_fields(test_setup):
    svc = test_setup["scheduling"]
    actor = test_setup["admin_actor"]
    target = svc.list_appointment_types(actor)[0]

    # id/created_at/updated_at are silently ignored; the known field still
    # applies. This is the ignore-set's stated rationale: a caller passing
    # a full to_dict() should not error.
    updated = svc.update_appointment_type(
        target.id,
        {"name": "Emergency (24/7)", "id": 123, "created_at": "bogus", "updated_at": "bogus"},
        actor,
    )
    assert updated.name == "Emergency (24/7)"
    assert updated.id == target.id


def test_update_appointment_type_full_to_dict_round_trip_does_not_raise(test_setup):
    svc = test_setup["scheduling"]
    actor = test_setup["admin_actor"]
    target = svc.list_appointment_types(actor)[0]

    existing = svc.get_appointment_type(target.id, actor)
    updated = svc.update_appointment_type(target.id, existing.to_dict(), actor)
    assert updated.name == existing.name


def test_update_appointment_type_unknown_field_raises(test_setup):
    svc = test_setup["scheduling"]
    actor = test_setup["admin_actor"]
    target = svc.list_appointment_types(actor)[0]

    with pytest.raises(ValueError):
        svc.update_appointment_type(target.id, {"bogus_field": "x"}, actor)


def test_update_appointment_type_nonexistent_raises(test_setup):
    svc = test_setup["scheduling"]
    actor = test_setup["admin_actor"]
    with pytest.raises(ValueError):
        svc.update_appointment_type(9999, {"name": "X"}, actor)


# ---------------------------------------------------------------------------
# W2: name / max_concurrent validation
# ---------------------------------------------------------------------------

def test_create_appointment_type_blank_name_raises(test_setup):
    svc = test_setup["scheduling"]
    actor = test_setup["admin_actor"]
    with pytest.raises(ValueError):
        svc.create_appointment_type(AppointmentType(name="   "), actor)


def test_create_appointment_type_max_concurrent_zero_raises(test_setup):
    svc = test_setup["scheduling"]
    actor = test_setup["admin_actor"]
    with pytest.raises(ValueError):
        svc.create_appointment_type(AppointmentType(name="Zero cap", max_concurrent=0), actor)


def test_create_appointment_type_strips_name(test_setup):
    svc = test_setup["scheduling"]
    actor = test_setup["admin_actor"]
    created = svc.create_appointment_type(AppointmentType(name="  Padded  "), actor)
    assert created.name == "Padded"


def test_update_appointment_type_blank_name_raises(test_setup):
    svc = test_setup["scheduling"]
    actor = test_setup["admin_actor"]
    target = svc.list_appointment_types(actor)[0]
    with pytest.raises(ValueError):
        svc.update_appointment_type(target.id, {"name": "   "}, actor)


def test_update_appointment_type_max_concurrent_zero_raises(test_setup):
    svc = test_setup["scheduling"]
    actor = test_setup["admin_actor"]
    target = svc.list_appointment_types(actor)[0]
    with pytest.raises(ValueError):
        svc.update_appointment_type(target.id, {"max_concurrent": 0}, actor)


def test_appointment_types_max_concurrent_check_constraint(test_setup):
    db = test_setup["db"]
    conn = db.get_connection()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO appointment_types "
            "(name, active, sort_order, max_concurrent, scheduling_hours_json, created_at, updated_at) "
            "VALUES ('Bad', 1, 0, 0, '{}', '2020-01-01', '2020-01-01');"
        )


def test_scheduling_hours_round_trip(test_setup):
    svc = test_setup["scheduling"]
    actor = test_setup["admin_actor"]

    created = svc.create_appointment_type(AppointmentType(name="After hours"), actor)
    assert created.scheduling_hours == {}

    hours = {"mon": {"start": "10:00", "end": "16:00"}}
    updated = svc.update_appointment_type(created.id, {"scheduling_hours": hours}, actor)
    assert updated.scheduling_hours == hours

    assert svc.get_appointment_type(created.id, actor).scheduling_hours == hours


# ---------------------------------------------------------------------------
# RBAC (dedicated PERM_READ/WRITE_APPOINTMENT_TYPES, W4)
# ---------------------------------------------------------------------------

def test_rbac_write_requires_write_appointment_types(test_setup):
    svc = test_setup["scheduling"]
    sales = test_setup["sales_actor"]

    with pytest.raises(PermissionError):
        svc.create_appointment_type(AppointmentType(name="Nope"), sales)

    admin = test_setup["admin_actor"]
    existing = svc.list_appointment_types(admin)[0]
    with pytest.raises(PermissionError):
        svc.update_appointment_type(existing.id, {"name": "Nope"}, sales)


def test_rbac_list_requires_read_appointment_types(test_setup):
    svc = test_setup["scheduling"]
    sales = test_setup["sales_actor"]
    with pytest.raises(PermissionError):
        svc.list_appointment_types(sales)


def test_rbac_ai_agent_can_read_but_not_write(test_setup):
    """ROLE_AI_AGENT holds PERM_WRITE_SCHEDULE_CONFIG but must NOT hold
    PERM_WRITE_APPOINTMENT_TYPES (W4) -- reusing the schedule-config pair
    would have handed the agent create/rename/deactivate power over
    business service types. It must still be able to READ (calendar.js
    needs caps/hours to offer slots)."""
    svc = test_setup["scheduling"]
    agent = test_setup["agent_actor"]
    admin = test_setup["admin_actor"]

    # Read: allowed.
    types = svc.list_appointment_types(agent)
    assert len(types) == 3

    # Write: denied.
    with pytest.raises(PermissionError):
        svc.create_appointment_type(AppointmentType(name="Agent-created"), agent)

    existing = svc.list_appointment_types(admin)[0]
    with pytest.raises(PermissionError):
        svc.update_appointment_type(existing.id, {"name": "Agent-renamed"}, agent)


def test_rbac_admin_can_read_and_write(test_setup):
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]

    assert len(svc.list_appointment_types(admin)) == 3
    created = svc.create_appointment_type(AppointmentType(name="Admin-created"), admin)
    updated = svc.update_appointment_type(created.id, {"name": "Admin-renamed"}, admin)
    assert updated.name == "Admin-renamed"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def test_route_round_trip(test_setup):
    router = test_setup["router"]
    token = test_setup["token"]  # AI_AGENT: read-only after W4
    admin_token = test_setup["admin_token"]
    hdr = {"Authorization": f"Bearer {token}"}
    admin_hdr = {"Authorization": f"Bearer {admin_token}"}

    status, _, body = router.handle_request(
        "POST", "/api/v1/appointment-types", headers=admin_hdr,
        body_bytes=json.dumps({"name": "Storm response", "sort_order": 9}).encode(),
    )
    assert status == 201
    new_id = body["appointment_type"]["id"]

    # Agent (read-only) can still GET.
    status, _, body = router.handle_request(
        "GET", "/api/v1/appointment-types", headers=hdr, body_bytes=b"",
    )
    assert status == 200
    assert any(t["name"] == "Storm response" for t in body["appointment_types"])

    status, _, body = router.handle_request(
        "POST", f"/api/v1/appointment-types/{new_id}/update", headers=admin_hdr,
        body_bytes=json.dumps({"max_concurrent": 4}).encode(),
    )
    assert status == 200
    assert body["appointment_type"]["max_concurrent"] == 4


def test_route_agent_write_denied_403(test_setup):
    """W4: ROLE_AI_AGENT holds PERM_READ_APPOINTMENT_TYPES but not WRITE."""
    router = test_setup["router"]
    token = test_setup["token"]
    hdr = {"Authorization": f"Bearer {token}"}

    status, _, body = router.handle_request(
        "POST", "/api/v1/appointment-types", headers=hdr,
        body_bytes=json.dumps({"name": "Agent attempt"}).encode(),
    )
    assert status == 403


def test_route_unknown_key_is_400_not_500(test_setup):
    router = test_setup["router"]
    admin_token = test_setup["admin_token"]
    hdr = {"Authorization": f"Bearer {admin_token}"}

    status, _, body = router.handle_request(
        "POST", "/api/v1/appointment-types", headers=hdr,
        body_bytes=json.dumps({"name": "Bad", "totally_unknown": True}).encode(),
    )
    assert status == 400
    assert "error" in body


def test_route_update_typo_key_is_400_not_silent_noop(test_setup):
    """W3: a typo'd update key (e.g. max_concurent) must 400, not silently
    no-op with a 200."""
    router = test_setup["router"]
    admin_token = test_setup["admin_token"]
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    hdr = {"Authorization": f"Bearer {admin_token}"}

    target = svc.list_appointment_types(admin)[0]
    status, _, body = router.handle_request(
        "POST", f"/api/v1/appointment-types/{target.id}/update", headers=hdr,
        body_bytes=json.dumps({"max_concurent": 4}).encode(),
    )
    assert status == 400
    assert "error" in body


def test_route_include_inactive_query(test_setup):
    router = test_setup["router"]
    token = test_setup["token"]
    svc = test_setup["scheduling"]
    admin = test_setup["admin_actor"]
    hdr = {"Authorization": f"Bearer {token}"}

    first = svc.list_appointment_types(admin)[0]
    svc.update_appointment_type(first.id, {"active": 0}, admin)

    status, _, body = router.handle_request(
        "GET", "/api/v1/appointment-types", headers=hdr, body_bytes=b"",
    )
    assert len(body["appointment_types"]) == 2

    status, _, body = router.handle_request(
        "GET", "/api/v1/appointment-types?include_inactive=true", headers=hdr, body_bytes=b"",
    )
    assert len(body["appointment_types"]) == 3


# ---------------------------------------------------------------------------
# Audit drift guard (W1)
# ---------------------------------------------------------------------------

def test_auditable_appointment_type_fields_matches_dataclass():
    from dataclasses import fields as dc_fields
    from restoricon_core.services.audit_service import _AUDITABLE_APPOINTMENT_TYPE_FIELDS

    assert _AUDITABLE_APPOINTMENT_TYPE_FIELDS == frozenset(f.name for f in dc_fields(AppointmentType))
