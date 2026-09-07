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
