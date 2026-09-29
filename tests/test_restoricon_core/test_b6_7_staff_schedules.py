import pytest
from unittest.mock import Mock
from restoricon_core.models import StaffSchedule
from restoricon_core.auth import AuthContext
from restoricon_core.services.scheduling_service import SchedulingService
from restoricon_core.services.notification_service import NotificationService
from restoricon_core.database import DatabaseManager
from restoricon_core.services.audit_service import AuditService

def test_staff_schedules_rbac():
    """Negative control: Test that RBAC prevents unauthorized access to staff schedules."""
    db_manager = DatabaseManager(":memory:")
    audit_service = AuditService(db_manager)
    scheduling_service = SchedulingService(db_manager, audit_service)
    
    # Actor without permissions
    actor = AuthContext(user_id=1, username="tech", role="technician", actor_type="human")
    
    # Read should fail
    with pytest.raises(PermissionError):
        scheduling_service.list_staff_schedules(actor)
        
    # Write should fail
    sched = StaffSchedule(
        id=None,
        user_id=1,
        title="Test Schedule",
        start_time="2026-09-01T09:00:00Z",
        end_time="2026-09-01T17:00:00Z",
        status="scheduled",
        notes="Notes"
    )
    with pytest.raises(PermissionError):
        scheduling_service.create_staff_schedule(sched, actor)
        
    with pytest.raises(PermissionError):
        scheduling_service.update_staff_schedule(1, {"title": "New Title"}, actor)
        
    with pytest.raises(PermissionError):
        scheduling_service.delete_staff_schedule(1, actor)

    with pytest.raises(PermissionError):
        scheduling_service.get_staff_schedule(1, actor)

def test_staff_schedules_crud():
    """Negative control: Test that CRUD operations work and audit logs are created."""
    db_manager = DatabaseManager(":memory:")
    audit_service = AuditService(db_manager)
    scheduling_service = SchedulingService(db_manager, audit_service)
    
    # Actor with permissions
    actor = AuthContext(user_id=1, username="admin", role="admin", actor_type="human")
    
    conn = db_manager.get_connection()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, full_name, email, role, created_at, updated_at) VALUES (1, 'admin', 'hash', 'Admin User', 'admin@example.com', 'admin', '2024-01-01', '2024-01-01')"
    )
    conn.execute(
        "INSERT INTO users (id, username, password_hash, full_name, email, role, created_at, updated_at) VALUES (99, 'testuser', 'hash', 'Test User', 'test@example.com', 'technician', '2024-01-01', '2024-01-01')"
    )
    conn.commit()
    
    # 1. Create
    sched = StaffSchedule(
        id=None,
        user_id=99,
        title="Shift 1",
        start_time="2026-09-01T09:00:00Z",
        end_time="2026-09-01T17:00:00Z",
        status="scheduled",
        notes="Notes"
    )
    created = scheduling_service.create_staff_schedule(sched, actor)
    assert created.id is not None
    assert created.title == "Shift 1"
    
    # 2. List
    schedules = scheduling_service.list_staff_schedules(actor)
    assert len(schedules) >= 1
    assert any(s.id == created.id for s in schedules)
    
    # 3. Update
    updated = scheduling_service.update_staff_schedule(created.id, {"title": "Shift 1 Updated", "status": "completed"}, actor)
    assert updated is not None
    assert updated.title == "Shift 1 Updated"
    assert updated.status == "completed"
    
    # Verify in DB
    schedules = scheduling_service.list_staff_schedules(actor, user_id=99)
    assert len(schedules) == 1
    assert schedules[0].title == "Shift 1 Updated"
    
    # 4. Delete
    scheduling_service.delete_staff_schedule(created.id, actor)
    schedules = scheduling_service.list_staff_schedules(actor, user_id=99)
    assert len(schedules) == 0

def test_staff_schedules_notification():
    """Negative control: Test that calendar invites are sent when scheduling."""
    db_manager = DatabaseManager(":memory:")
    audit_service = AuditService(db_manager)
    mock_notification = Mock(spec=NotificationService)
    scheduling_service = SchedulingService(db_manager, audit_service, mock_notification)
    
    actor = AuthContext(user_id=1, username="admin", role="admin", actor_type="human")
    
    conn = db_manager.get_connection()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, full_name, email, role, created_at, updated_at) VALUES (1, 'admin', 'hash', 'Admin User', 'admin@example.com', 'admin', '2024-01-01', '2024-01-01')"
    )
    conn.execute(
        "INSERT INTO users (id, username, password_hash, full_name, email, role, created_at, updated_at) VALUES (100, 'notifyuser', 'hash', 'Notify User', 'notify@example.com', 'technician', '2024-01-01', '2024-01-01')"
    )
    conn.commit()
    
    # Create triggers invite
    sched = StaffSchedule(
        id=None,
        user_id=100,
        title="Shift 2",
        start_time="2026-09-02T09:00:00Z",
        end_time="2026-09-02T17:00:00Z",
        status="scheduled",
        notes=""
    )
    created = scheduling_service.create_staff_schedule(sched, actor)
    
    assert mock_notification.send_calendar_invite.call_count == 1
    kwargs = mock_notification.send_calendar_invite.call_args.kwargs
    assert kwargs["to_email"] == "notify@example.com"
    assert kwargs["appointment"]["title"] == "Shift 2"
    
    # Update triggers invite again
    scheduling_service.update_staff_schedule(created.id, {"start_time": "2026-09-02T10:00:00Z"}, actor)
    assert mock_notification.send_calendar_invite.call_count == 2
    kwargs = mock_notification.send_calendar_invite.call_args.kwargs
    assert kwargs["appointment"]["start"] == "2026-09-02T10:00:00Z"


# ---------------------------------------------------------------------------
# Cloud-review round 2026-09-15: user_id reassignment (F4) and delete_staff_
# schedule's bool return (NEW-491 DELETE half).
# ---------------------------------------------------------------------------

def _two_user_env():
    db_manager = DatabaseManager(":memory:")
    audit_service = AuditService(db_manager)
    mock_notification = Mock(spec=NotificationService)
    scheduling_service = SchedulingService(db_manager, audit_service, mock_notification)
    actor = AuthContext(user_id=1, username="admin", role="admin", actor_type="human")
    conn = db_manager.get_connection()
    for uid, uname, email in ((1, "admin", "admin@example.com"), (98, "alice", "alice@example.com"), (99, "bob", "bob@example.com")):
        conn.execute(
            "INSERT INTO users (id, username, password_hash, full_name, email, role, created_at, updated_at) "
            "VALUES (?, ?, 'hash', ?, ?, 'technician', '2024-01-01', '2024-01-01')",
            (uid, uname, uname.title(), email),
        )
    conn.commit()
    created = scheduling_service.create_staff_schedule(
        StaffSchedule(id=None, user_id=98, title="Shift", start_time="2026-09-01T09:00:00Z",
                      end_time="2026-09-01T17:00:00Z", status="scheduled", notes=None),
        actor,
    )
    mock_notification.reset_mock()
    return db_manager, scheduling_service, mock_notification, actor, created


def test_update_staff_schedule_user_id_reassignment_is_persisted():
    """Before the fix, `user_id` was silently dropped by the SET-clause
    allow-list: the Calendar edit modal's Person dropdown reported success
    while the row stayed bound to the original user."""
    db_manager, svc, notif, actor, created = _two_user_env()
    updated = svc.update_staff_schedule(created.id, {"user_id": 99}, actor)
    assert updated.user_id == 99
    row = db_manager.get_connection().execute(
        "SELECT user_id FROM staff_schedules WHERE id = ?", (created.id,)
    ).fetchone()
    assert row["user_id"] == 99
    # The new assignee gets the invite, not the old one.
    assert notif.send_calendar_invite.call_count == 1
    assert notif.send_calendar_invite.call_args.kwargs["to_email"] == "bob@example.com"
    # NEW-506: the OLD assignee gets a cancellation for the same UID -- a
    # wrong UID here would silently be useless and nothing else would
    # catch it.
    assert notif.send_calendar_cancellation.call_count == 1
    cancel_kwargs = notif.send_calendar_cancellation.call_args.kwargs
    assert cancel_kwargs["to_email"] == "alice@example.com"
    assert cancel_kwargs["appointment"]["uid"] == f"staff-sched-{created.id}"


def test_update_staff_schedule_unknown_user_id_is_value_error_not_integrity_error():
    """A nonexistent user must be a caller error (ValueError -> route 400),
    not an sqlite3.IntegrityError from the NOT NULL FK (-> 500)."""
    _, svc, _, actor, created = _two_user_env()
    with pytest.raises(ValueError, match="Unknown user_id"):
        svc.update_staff_schedule(created.id, {"user_id": 424242}, actor)
    assert svc.update_staff_schedule(created.id, {}, actor).user_id == 98  # untouched


def test_delete_staff_schedule_returns_true_then_false_and_audits_once():
    db_manager, svc, notif, actor, created = _two_user_env()
    conn = db_manager.get_connection()
    before = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE entity_type = 'staff_schedule' AND action = 'delete'"
    ).fetchone()[0]
    assert svc.delete_staff_schedule(created.id, actor) is True
    assert svc.delete_staff_schedule(created.id, actor) is False  # already gone
    assert svc.delete_staff_schedule(999999, actor) is False       # never existed
    after = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE entity_type = 'staff_schedule' AND action = 'delete'"
    ).fetchone()[0]
    assert after - before == 1, "a no-op delete must not write a 'Deleted staff schedule' audit row"

    # NEW-506: the first (real) delete fires exactly one cancellation to
    # the assigned user (alice) with the correct UID; the two no-op
    # deletes after it fire NO further cancellations -- proving the
    # pre-delete SELECT added for this doesn't break the no-op contract.
    assert notif.send_calendar_cancellation.call_count == 1
    cancel_kwargs = notif.send_calendar_cancellation.call_args.kwargs
    assert cancel_kwargs["to_email"] == "alice@example.com"
    assert cancel_kwargs["appointment"]["uid"] == f"staff-sched-{created.id}"


# ---------------------------------------------------------------------------
# NEW-547: sales reps' "My Schedule" panel silently 403s -- ROLE_SALES/
# ROLE_SALES_MANAGER get a new narrow, self-only PERM_READ_OWN_STAFF_SCHEDULE
# instead of the full company-wide PERM_READ_STAFF_SCHEDULES.
# ---------------------------------------------------------------------------

def _narrow_tier_env():
    """Two staff_schedules rows, one for the narrow-tier actor (user_id=1,
    sales) and one for a different user (user_id=2, technician), created by
    an admin actor so the create/permission paths under test stay isolated
    to list_staff_schedules/get_staff_schedule."""
    db_manager = DatabaseManager(":memory:")
    audit_service = AuditService(db_manager)
    scheduling_service = SchedulingService(db_manager, audit_service)
    admin = AuthContext(user_id=99, username="admin", role="admin", actor_type="human")

    conn = db_manager.get_connection()
    for uid, uname, role, email in (
        (99, "admin", "admin", "admin@example.com"),
        (1, "rep", "sales", "rep@example.com"),
        (2, "other", "technician", "other@example.com"),
    ):
        conn.execute(
            "INSERT INTO users (id, username, password_hash, full_name, email, role, created_at, updated_at) "
            "VALUES (?, ?, 'hash', ?, ?, ?, '2024-01-01', '2024-01-01')",
            (uid, uname, uname.title(), email, role),
        )
    conn.commit()

    own = scheduling_service.create_staff_schedule(
        StaffSchedule(id=None, user_id=1, title="Rep Shift", start_time="2026-09-01T09:00:00Z",
                      end_time="2026-09-01T17:00:00Z", status="scheduled", notes=None),
        admin,
    )
    other = scheduling_service.create_staff_schedule(
        StaffSchedule(id=None, user_id=2, title="Other Shift", start_time="2026-09-02T09:00:00Z",
                      end_time="2026-09-02T17:00:00Z", status="scheduled", notes=None),
        admin,
    )
    return db_manager, scheduling_service, own, other


def test_list_staff_schedules_narrow_tier_defaults_to_own_rows():
    """Plain ROLE_SALES actor, no user_id param -> only their own rows."""
    _, svc, own, other = _narrow_tier_env()
    rep = AuthContext(user_id=1, username="rep", role="sales", actor_type="human")
    results = svc.list_staff_schedules(rep)
    ids = {s.id for s in results}
    assert ids == {own.id}
    assert other.id not in ids


def test_list_staff_schedules_narrow_tier_ignores_other_users_id_param():
    """Same actor explicitly requesting another user's user_id -- the
    narrow-tier filter must be unconditional, not just a default."""
    _, svc, own, other = _narrow_tier_env()
    rep = AuthContext(user_id=1, username="rep", role="sales", actor_type="human")
    results = svc.list_staff_schedules(rep, user_id=2)
    ids = {s.id for s in results}
    assert ids == {own.id}
    assert other.id not in ids


def test_list_staff_schedules_full_tier_unscoped_is_unchanged():
    """Regression guard: ROLE_PROJECT_MANAGER (full-tier) unscoped call
    still returns the whole company-wide table, proving this fix did not
    accidentally narrow the full-permission path."""
    _, svc, own, other = _narrow_tier_env()
    pm = AuthContext(user_id=3, username="pm", role="project_manager", actor_type="human")
    results = svc.list_staff_schedules(pm)
    ids = {s.id for s in results}
    assert ids == {own.id, other.id}


def test_get_staff_schedule_narrow_tier_own_row_visible():
    _, svc, own, other = _narrow_tier_env()
    rep = AuthContext(user_id=1, username="rep", role="sales", actor_type="human")
    fetched = svc.get_staff_schedule(own.id, rep)
    assert fetched is not None
    assert fetched.id == own.id


def test_get_staff_schedule_narrow_tier_other_row_is_not_found():
    """Narrow-tier actor fetching someone else's schedule by id gets None
    (-> route 404), not the row and not a PermissionError -- matching this
    codebase's not-found-not-leak convention."""
    _, svc, own, other = _narrow_tier_env()
    rep = AuthContext(user_id=1, username="rep", role="sales", actor_type="human")
    assert svc.get_staff_schedule(other.id, rep) is None


def test_get_active_staff_schedules_for_user_narrow_tier_only_is_denied():
    """A narrow-tier-only actor (ROLE_SALES) must still be denied the
    admin-precheck read -- it stays gated on the FULL permission only."""
    _, svc, own, other = _narrow_tier_env()
    rep = AuthContext(user_id=1, username="rep", role="sales", actor_type="human")
    with pytest.raises(PermissionError):
        svc.get_active_staff_schedules_for_user(1, rep)


def test_list_staff_schedules_archive_narrow_tier_only_is_denied():
    """A narrow-tier-only actor (ROLE_SALES) must still be denied the
    terminated-staff archive read -- it stays gated on the FULL permission
    only."""
    _, svc, own, other = _narrow_tier_env()
    rep = AuthContext(user_id=1, username="rep", role="sales", actor_type="human")
    with pytest.raises(PermissionError):
        svc.list_staff_schedules_archive(rep)


def test_role_sales_manager_gets_narrow_not_full_permission():
    """ROLE_SALES_MANAGER derives PERM_READ_OWN_STAFF_SCHEDULE automatically
    from ROLE_SALES (ROLE_PERMISSIONS[ROLE_SALES_MANAGER] = ROLE_PERMISSIONS
    [ROLE_SALES] | {...}) but must NOT get the full company-wide
    PERM_READ_STAFF_SCHEDULES -- staff schedules are on the staffing side
    of the line auth.py already draws for this role (pipeline, not
    project/staff assignment)."""
    from restoricon_core.auth import (
        ROLE_PERMISSIONS, ROLE_SALES_MANAGER,
        PERM_READ_OWN_STAFF_SCHEDULE, PERM_READ_STAFF_SCHEDULES,
    )
    perms = ROLE_PERMISSIONS[ROLE_SALES_MANAGER]
    assert PERM_READ_OWN_STAFF_SCHEDULE in perms
    assert PERM_READ_STAFF_SCHEDULES not in perms

    _, svc, own, other = _narrow_tier_env()
    manager = AuthContext(user_id=4, username="mgr", role="sales_manager", actor_type="human")
    conn = svc.db.get_connection()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, full_name, email, role, created_at, updated_at) "
        "VALUES (4, 'mgr', 'hash', 'Mgr', 'mgr@example.com', 'sales_manager', '2024-01-01', '2024-01-01')"
    )
    conn.commit()
    results = svc.list_staff_schedules(manager)
    assert results == []  # manager has no schedule of their own -> narrow, empty, not company-wide
    with pytest.raises(PermissionError):
        svc.list_staff_schedules_archive(manager)
