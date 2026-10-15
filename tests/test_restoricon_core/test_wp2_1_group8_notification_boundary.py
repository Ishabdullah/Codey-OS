"""Regression tests for WP2.1 group 8 ("Notification boundary",
NEW-925/926).

NEW-925: four `NotificationService` call sites in
`restoricon_core/services/scheduling_service.py` (create_staff_schedule's
invite, update_staff_schedule's invite, update_staff_schedule's
reassignment cancellation to the old assignee, and
delete_staff_schedule's cancellation) previously had zero audit trail on
send outcome. This mirrors WP0.2's existing
notify_email_sent/notify_email_failed pattern
(tests/test_restoricon_core/test_wp0_2_notification_audit.py) at all four
sites.

NEW-926: the B8.10c compose-email route is reachable in principle by a
ROLE_AI_AGENT actor (holds PERM_LOG_COMMUNICATION, is not ROLE_CUSTOMER)
to send a real, free-text-content email to a real customer with zero
confirmation gate. This asserts the new `confirmed` gate mirrors the
NEW-919/920/921 pattern: unconfirmed ai_agent -> 403 + audit row;
confirmed ai_agent -> 200 + real send; human/admin actor unaffected.
"""
import json
import unittest.mock

import pytest

from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN, ROLE_AI_AGENT
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, StaffSchedule
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.notification_service import NotificationService
from restoricon_core.services.scheduling_service import SchedulingService
from restoricon_core.api.routes import APIRouter


def _admin_actor(user_id=1):
    return AuthContext(user_id, "admin", ROLE_ADMIN, "human")


@pytest.fixture
def sched_env():
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    notif = unittest.mock.MagicMock(spec=NotificationService)
    sched = SchedulingService(db, audit, notif)

    conn = db.get_connection()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, email, full_name, role, created_at, updated_at) "
        "VALUES (1, 'admin', 'hash', 'admin@example.com', 'Admin', 'admin', '2023', '2023')"
    )
    conn.execute(
        "INSERT INTO users (id, username, password_hash, email, full_name, role, created_at, updated_at) "
        "VALUES (99, 'tech', 'hash', 'tech@example.com', 'Tech User', 'technician', '2023', '2023')"
    )
    conn.execute(
        "INSERT INTO users (id, username, password_hash, email, full_name, role, created_at, updated_at) "
        "VALUES (100, 'tech2', 'hash', 'tech2@example.com', 'Tech Two', 'technician', '2023', '2023')"
    )
    conn.commit()
    return db, audit, notif, sched


def _make_schedule(user_id=99, title="Shift 1"):
    return StaffSchedule(
        id=None,
        user_id=user_id,
        title=title,
        start_time="2026-09-01T09:00:00Z",
        end_time="2026-09-01T17:00:00Z",
        status="scheduled",
        notes="Notes",
    )


# ------------------------------------------------------------------
# NEW-925: create_staff_schedule invite
# ------------------------------------------------------------------

def test_create_staff_schedule_invite_success_is_audited(sched_env):
    db, audit, notif, sched = sched_env
    notif.send_calendar_invite.return_value = True
    actor = _admin_actor()

    created = sched.create_staff_schedule(_make_schedule(), actor)

    logs = audit.query_logs(actor, entity_type="staff_schedule", entity_id=created.id, action="notify_email_sent")
    assert len(logs) == 1


def test_create_staff_schedule_invite_failure_is_audited(sched_env):
    db, audit, notif, sched = sched_env
    notif.send_calendar_invite.return_value = False
    actor = _admin_actor()

    created = sched.create_staff_schedule(_make_schedule(), actor)

    logs = audit.query_logs(actor, entity_type="staff_schedule", entity_id=created.id, action="notify_email_failed")
    assert len(logs) == 1


def test_create_staff_schedule_invite_exception_is_audited(sched_env):
    db, audit, notif, sched = sched_env
    notif.send_calendar_invite.side_effect = RuntimeError("connection refused")
    actor = _admin_actor()

    # Must not raise -- pre-existing behavior is "log and continue".
    created = sched.create_staff_schedule(_make_schedule(), actor)

    logs = audit.query_logs(actor, entity_type="staff_schedule", entity_id=created.id, action="notify_email_failed")
    assert len(logs) == 1
    assert "connection refused" in logs[0].change_summary


# ------------------------------------------------------------------
# NEW-925: update_staff_schedule invite + reassignment cancellation
# ------------------------------------------------------------------

def test_update_staff_schedule_invite_success_is_audited(sched_env):
    db, audit, notif, sched = sched_env
    # Creation's own invite send is made to fail here so it doesn't add
    # a spurious notify_email_sent row that would conflate with the
    # update-triggered invite under test.
    notif.send_calendar_invite.return_value = False
    actor = _admin_actor()
    created = sched.create_staff_schedule(_make_schedule(), actor)

    notif.send_calendar_invite.return_value = True
    updated = sched.update_staff_schedule(created.id, {"title": "New Title"}, actor)

    logs = audit.query_logs(actor, entity_type="staff_schedule", entity_id=updated.id, action="notify_email_sent")
    assert len(logs) == 1


def test_update_staff_schedule_invite_failure_is_audited(sched_env):
    db, audit, notif, sched = sched_env
    notif.send_calendar_invite.return_value = True
    actor = _admin_actor()
    created = sched.create_staff_schedule(_make_schedule(), actor)

    notif.send_calendar_invite.return_value = False
    updated = sched.update_staff_schedule(created.id, {"title": "New Title"}, actor)

    logs = audit.query_logs(actor, entity_type="staff_schedule", entity_id=updated.id, action="notify_email_failed")
    assert len(logs) == 1


def test_update_staff_schedule_invite_exception_is_audited(sched_env):
    db, audit, notif, sched = sched_env
    notif.send_calendar_invite.return_value = False
    actor = _admin_actor()
    created = sched.create_staff_schedule(_make_schedule(), actor)

    notif.send_calendar_invite.side_effect = RuntimeError("connection refused")
    # Must not raise -- pre-existing behavior is "log and continue".
    updated = sched.update_staff_schedule(created.id, {"title": "New Title"}, actor)

    # Filtered by the exception-path's "raised" wording, not just the
    # action name -- the creation step above also logs a
    # notify_email_failed row (its own invite send returns False), so
    # a bare action-name filter would see two rows.
    logs = [
        l for l in audit.query_logs(actor, entity_type="staff_schedule", entity_id=updated.id, action="notify_email_failed")
        if "raised" in l.change_summary
    ]
    assert len(logs) == 1
    assert "connection refused" in logs[0].change_summary


def test_update_staff_schedule_reassignment_cancellation_success_is_audited(sched_env):
    db, audit, notif, sched = sched_env
    # Creation's own invite send is made to fail here so it doesn't add
    # a spurious notify_email_sent row (see test_update_staff_schedule_
    # invite_success_is_audited's comment above).
    notif.send_calendar_invite.return_value = False
    actor = _admin_actor()
    created = sched.create_staff_schedule(_make_schedule(user_id=99), actor)

    notif.send_calendar_invite.return_value = True
    notif.send_calendar_cancellation.return_value = True
    updated = sched.update_staff_schedule(created.id, {"user_id": 100}, actor)

    # Two notify_email_sent rows expected: the new-assignee invite AND
    # the old-assignee cancellation, both entity_type="staff_schedule".
    logs = audit.query_logs(actor, entity_type="staff_schedule", entity_id=updated.id, action="notify_email_sent")
    assert len(logs) == 2
    summaries = [l.change_summary for l in logs]
    assert any("reassignment cancellation" in s for s in summaries)
    assert any("invite sent" in s for s in summaries)


def test_update_staff_schedule_reassignment_cancellation_failure_is_audited(sched_env):
    db, audit, notif, sched = sched_env
    notif.send_calendar_invite.return_value = True
    notif.send_calendar_cancellation.return_value = False
    actor = _admin_actor()
    created = sched.create_staff_schedule(_make_schedule(user_id=99), actor)

    updated = sched.update_staff_schedule(created.id, {"user_id": 100}, actor)

    logs = audit.query_logs(actor, entity_type="staff_schedule", entity_id=updated.id, action="notify_email_failed")
    assert len(logs) == 1
    assert "reassignment cancellation" in logs[0].change_summary


def test_update_staff_schedule_reassignment_cancellation_exception_is_audited(sched_env):
    db, audit, notif, sched = sched_env
    notif.send_calendar_invite.return_value = False
    actor = _admin_actor()
    created = sched.create_staff_schedule(_make_schedule(user_id=99), actor)

    notif.send_calendar_invite.return_value = True
    notif.send_calendar_cancellation.side_effect = RuntimeError("timed out")
    # Must not raise -- pre-existing behavior is "log and continue".
    updated = sched.update_staff_schedule(created.id, {"user_id": 100}, actor)

    # Filtered the same way as the invite-exception test above -- the
    # creation step's own (failing) invite send also logs a
    # notify_email_failed row for this entity_id.
    logs = [
        l for l in audit.query_logs(actor, entity_type="staff_schedule", entity_id=updated.id, action="notify_email_failed")
        if "raised" in l.change_summary
    ]
    assert len(logs) == 1
    assert "reassignment cancellation" in logs[0].change_summary
    assert "timed out" in logs[0].change_summary


# ------------------------------------------------------------------
# NEW-925: delete_staff_schedule cancellation
# ------------------------------------------------------------------

def test_delete_staff_schedule_cancellation_success_is_audited(sched_env):
    db, audit, notif, sched = sched_env
    # Creation's own invite send is made to fail here so it doesn't add
    # a spurious notify_email_sent row (see test_update_staff_schedule_
    # invite_success_is_audited's comment above).
    notif.send_calendar_invite.return_value = False
    actor = _admin_actor()
    created = sched.create_staff_schedule(_make_schedule(), actor)

    notif.send_calendar_cancellation.return_value = True
    deleted = sched.delete_staff_schedule(created.id, actor)
    assert deleted is True

    logs = audit.query_logs(actor, entity_type="staff_schedule", entity_id=created.id, action="notify_email_sent")
    assert len(logs) == 1


def test_delete_staff_schedule_cancellation_failure_is_audited(sched_env):
    db, audit, notif, sched = sched_env
    notif.send_calendar_invite.return_value = True
    notif.send_calendar_cancellation.return_value = False
    actor = _admin_actor()
    created = sched.create_staff_schedule(_make_schedule(), actor)

    deleted = sched.delete_staff_schedule(created.id, actor)
    assert deleted is True

    logs = audit.query_logs(actor, entity_type="staff_schedule", entity_id=created.id, action="notify_email_failed")
    assert len(logs) == 1


def test_delete_staff_schedule_cancellation_exception_is_audited(sched_env):
    db, audit, notif, sched = sched_env
    notif.send_calendar_invite.return_value = True
    notif.send_calendar_cancellation.side_effect = RuntimeError("timed out")
    actor = _admin_actor()
    created = sched.create_staff_schedule(_make_schedule(), actor)

    deleted = sched.delete_staff_schedule(created.id, actor)
    assert deleted is True

    logs = audit.query_logs(actor, entity_type="staff_schedule", entity_id=created.id, action="notify_email_failed")
    assert len(logs) == 1
    assert "timed out" in logs[0].change_summary


# ------------------------------------------------------------------
# NEW-926: compose-email ROLE_AI_AGENT confirmed gate
# ------------------------------------------------------------------

@pytest.fixture
def router_env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    comm = CommunicationService(db)
    notif = NotificationService()
    crm = CRMService(db, audit, notif)
    sched = SchedulingService(db, audit)
    auto = AutomationService(db, audit)
    router = APIRouter(auth, crm, comm, audit, sched, auto)

    admin_user = auth.create_user("admin_user", "Pass123!", "Admin User", "admin@test.com", ROLE_ADMIN)
    admin_actor = AuthContext(admin_user.id, "admin_user", ROLE_ADMIN, "human")
    admin_token = auth.create_token(admin_user)

    agent_user = auth.create_user(
        "codey-aigentik-agent", "Pass123!", "Codey-Aigentik", "agent@test.com", ROLE_AI_AGENT
    )
    agent_token = auth.create_token(agent_user)

    cust = crm.create_customer(
        Customer(first_name="Cust", last_name="A", email="custa@example.com"),
        admin_actor,
    )
    return router, audit, admin_actor, admin_token, agent_token, cust


def _fake_urlopen_success():
    fake_response = unittest.mock.MagicMock()
    fake_response.getcode.return_value = 200
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False
    return fake_response


def test_ai_agent_compose_email_unconfirmed_refused_and_audited(router_env):
    router, audit, admin_actor, admin_token, agent_token, cust = router_env

    # Patch urlopen so the test would catch a regression that let the
    # gate fall through -- if the gate failed to refuse, this would
    # otherwise attempt a real network call instead of failing loudly.
    with unittest.mock.patch("urllib.request.urlopen") as mock_urlopen:
        status, _, body = router.handle_request(
            "POST", f"/api/v1/customers/{cust.id}/compose-email",
            {"Authorization": f"Bearer {agent_token}", "Content-Type": "application/json"},
            json.dumps({"subject": "Hi", "body": "test"}).encode("utf-8"),
        )

    assert status == 403, body
    assert not mock_urlopen.called
    logs = audit.query_logs(admin_actor, entity_type="notification_send", entity_id=cust.id, action="refused")
    assert len(logs) == 1


def test_ai_agent_compose_email_confirmed_false_still_refused(router_env):
    """Strict identity check (mirrors group 7's delete_contact case):
    an explicit `confirmed: false` must still be refused, not treated as
    merely a falsy default."""
    router, audit, admin_actor, admin_token, agent_token, cust = router_env

    with unittest.mock.patch("urllib.request.urlopen") as mock_urlopen:
        status, _, body = router.handle_request(
            "POST", f"/api/v1/customers/{cust.id}/compose-email",
            {"Authorization": f"Bearer {agent_token}", "Content-Type": "application/json"},
            json.dumps({"subject": "Hi", "body": "test", "confirmed": False}).encode("utf-8"),
        )

    assert status == 403, body
    assert not mock_urlopen.called


def test_ai_agent_compose_email_truthy_string_does_not_count(router_env):
    """`confirmed` must be a strict `is True` check -- a truthy string
    ("true") must not satisfy it (mirrors group 7's delete_contact
    case)."""
    router, audit, admin_actor, admin_token, agent_token, cust = router_env

    with unittest.mock.patch("urllib.request.urlopen") as mock_urlopen:
        status, _, body = router.handle_request(
            "POST", f"/api/v1/customers/{cust.id}/compose-email",
            {"Authorization": f"Bearer {agent_token}", "Content-Type": "application/json"},
            json.dumps({"subject": "Hi", "body": "test", "confirmed": "true"}).encode("utf-8"),
        )

    assert status == 403, body
    assert not mock_urlopen.called


def test_ai_agent_compose_email_confirmed_succeeds_and_sends(router_env):
    router, audit, admin_actor, admin_token, agent_token, cust = router_env

    with unittest.mock.patch("urllib.request.urlopen", return_value=_fake_urlopen_success()) as mock_urlopen:
        status, _, body = router.handle_request(
            "POST", f"/api/v1/customers/{cust.id}/compose-email",
            {"Authorization": f"Bearer {agent_token}", "Content-Type": "application/json"},
            json.dumps({"subject": "Hi", "body": "test", "confirmed": True}).encode("utf-8"),
        )

    assert status == 201, body
    assert mock_urlopen.called


def test_human_actor_compose_email_no_confirmed_field_still_succeeds(router_env):
    router, audit, admin_actor, admin_token, agent_token, cust = router_env

    with unittest.mock.patch("urllib.request.urlopen", return_value=_fake_urlopen_success()):
        status, _, body = router.handle_request(
            "POST", f"/api/v1/customers/{cust.id}/compose-email",
            {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json.dumps({"subject": "Hi", "body": "test"}).encode("utf-8"),
        )

    assert status == 201, body
