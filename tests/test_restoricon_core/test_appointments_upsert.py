"""
Tests for update_appointment, upsert_appointment, and schedule_config routes.
Part of B2 task 4 calendar.js write-through.
"""

import json
import pytest
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_AI_AGENT,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Appointment, ScheduleConfig
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.scheduling_service import SchedulingService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
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
        user_id=admin_user.id,
        username="admin",
        role=ROLE_ADMIN,
        actor_type="human",
    )

    agent_user = auth_service.create_user(
        username="agent",
        plain_password="Password123",
        full_name="AI Agent",
        email="agent@test.com",
        role=ROLE_AI_AGENT,
    )
    agent_actor = AuthContext(
        user_id=agent_user.id,
        username="agent",
        role=ROLE_AI_AGENT,
        actor_type="agent",
    )
    token = auth_service.create_token(agent_user)

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
        "agent_actor": agent_actor,
        "token": token,
        "router": router,
    }


def test_update_appointment(test_setup):
    svc = test_setup["scheduling"]
    actor = test_setup["agent_actor"]

    appt = Appointment(
        external_id="appt_0001",
        title="Roof Inspection",
        start_time="2026-08-30T10:00:00Z",
        end_time="2026-08-30T10:30:00Z",
        status="negotiating",
        offered_slots=[{"start": "2026-08-30T10:00:00Z", "end": "2026-08-30T10:30:00Z"}],
    )
    created = svc.create_appointment(appt, actor)

    # Partial update
    updated = svc.update_appointment(
        created.id,
        {
            "status": "confirmed",
            "notes": "Gate code 1234",
            "form_sent": 1,
            "pending_reschedule": {"start": "2026-08-31T10:00:00Z", "end": "2026-08-31T10:30:00Z"},
        },
        actor,
    )
    assert updated is not None
    assert updated.status == "confirmed"
    assert updated.notes == "Gate code 1234"
    assert updated.form_sent == 1
    assert updated.pending_reschedule == {"start": "2026-08-31T10:00:00Z", "end": "2026-08-31T10:30:00Z"}


def test_update_appointment_invalid_status(test_setup):
    svc = test_setup["scheduling"]
    actor = test_setup["agent_actor"]

    appt = Appointment(external_id="appt_0002", title="Estimate", status="confirmed")
    created = svc.create_appointment(appt, actor)

    with pytest.raises(ValueError, match="Invalid status"):
        svc.update_appointment(created.id, {"status": "invalid_status"}, actor)


def test_upsert_appointment(test_setup):
    svc = test_setup["scheduling"]
    actor = test_setup["agent_actor"]

    # Initial upsert creates
    appt = Appointment(
        external_id="appt_0003",
        title="Initial Consultation",
        status="negotiating",
        attendee_name="Alice",
    )
    res1 = svc.upsert_appointment(appt, actor)
    assert res1.id is not None
    assert res1.attendee_name == "Alice"

    # Second upsert with same external_id updates
    appt_update = Appointment(
        external_id="appt_0003",
        title="Confirmed Consultation",
        status="confirmed",
        attendee_name="Alice Smith",
    )
    res2 = svc.upsert_appointment(appt_update, actor)
    assert res2.id == res1.id
    assert res2.title == "Confirmed Consultation"
    assert res2.attendee_name == "Alice Smith"
    assert res2.status == "confirmed"


def test_router_appointment_update_and_upsert(test_setup):
    router = test_setup["router"]
    token = test_setup["token"]

    # 1. Create via POST /api/v1/appointments
    status, headers, body = router.handle_request(
        "POST",
        "/api/v1/appointments",
        headers={"Authorization": f"Bearer {token}"},
        body_bytes=json.dumps({"external_id": "appt_0010", "title": "Inspection", "status": "negotiating"}).encode(),
    )
    assert status == 201
    appt_id = body["appointment"]["id"]

    # 2. Update via POST /api/v1/appointments/:id/update
    status, headers, body = router.handle_request(
        "POST",
        f"/api/v1/appointments/{appt_id}/update",
        headers={"Authorization": f"Bearer {token}"},
        body_bytes=json.dumps({"status": "confirmed", "notes": "Customer confirmed over SMS"}).encode(),
    )
    assert status == 200
    assert body["appointment"]["status"] == "confirmed"
    assert body["appointment"]["notes"] == "Customer confirmed over SMS"

    # 3. Upsert via POST /api/v1/appointments/upsert
    status, headers, body = router.handle_request(
        "POST",
        "/api/v1/appointments/upsert",
        headers={"Authorization": f"Bearer {token}"},
        body_bytes=json.dumps({"external_id": "appt_0010", "title": "Inspection Updated", "notes": "New note"}).encode(),
    )
    assert status == 200
    assert body["appointment"]["id"] == appt_id
    assert body["appointment"]["title"] == "Inspection Updated"
    assert body["appointment"]["notes"] == "New note"


def test_router_schedule_config_get_and_post(test_setup):
    router = test_setup["router"]
    token = test_setup["token"]

    # 1. Initial GET before configured returns 404
    status, headers, body = router.handle_request(
        "GET",
        "/api/v1/schedule-config",
        headers={"Authorization": f"Bearer {token}"},
        body_bytes=b"",
    )
    assert status == 404

    # 2. POST to configure schedule-config
    status, headers, body = router.handle_request(
        "POST",
        "/api/v1/schedule-config",
        headers={"Authorization": f"Bearer {token}"},
        body_bytes=json.dumps({
            "working_hours": {"mon": {"start": "09:00", "end": "17:00"}},
            "default_duration_minutes": 45,
            "buffer_minutes": 15,
            "booking_window_days": 180,
        }).encode(),
    )
    assert status == 200
    assert body["schedule_config"]["default_duration_minutes"] == 45
    assert body["schedule_config"]["working_hours"] == {"mon": {"start": "09:00", "end": "17:00"}}

    # 3. Subsequent GET returns configured schedule-config
    status, headers, body = router.handle_request(
        "GET",
        "/api/v1/schedule-config",
        headers={"Authorization": f"Bearer {token}"},
        body_bytes=b"",
    )
    assert status == 200
    assert body["schedule_config"]["default_duration_minutes"] == 45
