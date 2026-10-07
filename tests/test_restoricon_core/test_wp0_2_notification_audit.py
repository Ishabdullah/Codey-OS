"""
WP0.2 (CODEY_OS_MASTER_BLUEPRINT.md §21): notification_service's two real
call sites previously had no audit record of the send itself, success or
failure -- only the triggering write (the project update) was audited at
the PM-assignment site, and the sales-portal compose route only recorded
anything on success (via communication_history). This asserts the new
audit coverage at both sites, for both outcomes.
"""
import unittest.mock
import json

import pytest

from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN, ROLE_SALES
from restoricon_core.database import DatabaseManager
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.notification_service import NotificationService
from restoricon_core.services.scheduling_service import SchedulingService
from restoricon_core.api.routes import APIRouter
from restoricon_core.models import Customer


def _admin_actor(user_id):
    return AuthContext(user_id, "admin", ROLE_ADMIN, "human")


@pytest.fixture
def crm_env():
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    notif = unittest.mock.MagicMock(spec=NotificationService)
    crm = CRMService(db, audit, notif)

    conn = db.get_connection()
    conn.execute(
        "INSERT INTO users (id, username, password_hash, email, full_name, role, created_at, updated_at) "
        "VALUES (1, 'pm', 'hash', 'pm@example.com', 'John', 'project_manager', '2023', '2023')"
    )
    conn.execute(
        "INSERT INTO customers (id, first_name, last_name, email, created_at) VALUES (1, 'Jane', 'Doe', 'j@d.com', '2023')"
    )
    conn.execute(
        "INSERT INTO projects (id, customer_id, title, property_address, project_type, stage, created_at, updated_at) "
        "VALUES (1, 1, 'Proj', 'Addr', 'Type', 'intake', '2023', '2023')"
    )
    conn.commit()
    return db, audit, notif, crm


def test_pm_assignment_notification_success_is_audited(crm_env):
    db, audit, notif, crm = crm_env
    notif.send_email.return_value = True
    actor = _admin_actor(1)

    crm.update_project(1, {"project_manager_id": 1}, actor)

    logs = audit.query_logs(actor, entity_type="project", entity_id=1, action="notify_email_sent")
    assert len(logs) == 1
    assert logs[0].actor_id == 1


def test_pm_assignment_notification_failure_is_audited(crm_env):
    db, audit, notif, crm = crm_env
    notif.send_email.return_value = False
    actor = _admin_actor(1)

    crm.update_project(1, {"project_manager_id": 1}, actor)

    logs = audit.query_logs(actor, entity_type="project", entity_id=1, action="notify_email_failed")
    assert len(logs) == 1


def test_pm_assignment_notification_exception_is_audited(crm_env):
    db, audit, notif, crm = crm_env
    notif.send_email.side_effect = RuntimeError("connection refused")
    actor = _admin_actor(1)

    # Must not raise -- the pre-existing behavior is "log and continue",
    # this just adds the audit record on top of the existing warning log.
    crm.update_project(1, {"project_manager_id": 1}, actor)

    logs = audit.query_logs(actor, entity_type="project", entity_id=1, action="notify_email_failed")
    assert len(logs) == 1
    assert "connection refused" in logs[0].change_summary


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
    rep_user = auth.create_user("rep_a", "Pass123!", "Rep Alpha", "repa@test.com", ROLE_SALES)
    token = auth.create_token(rep_user)

    cust = crm.create_customer(
        Customer(first_name="Cust", last_name="A", email="custa@example.com", assigned_user_id=rep_user.id),
        admin_actor,
    )
    return router, audit, admin_actor, token, cust


def test_compose_email_failure_is_audited(router_env):
    router, audit, admin_actor, token, cust = router_env
    import urllib.error

    with unittest.mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
        status, _, _ = router.handle_request(
            "POST", f"/api/v1/customers/{cust.id}/compose-email",
            {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json.dumps({"subject": "Hi", "body": "test"}).encode("utf-8"),
        )

    assert status == 502
    logs = audit.query_logs(admin_actor, entity_type="customer", entity_id=cust.id, action="notify_email_failed")
    assert len(logs) == 1


def test_compose_email_success_does_not_double_audit_notify_failed(router_env):
    """Success is already covered by communication_history -- this just
    confirms the new failure-path audit.log() isn't accidentally firing
    on the success path too."""
    router, audit, admin_actor, token, cust = router_env
    fake_response = unittest.mock.MagicMock()
    fake_response.getcode.return_value = 200
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False

    with unittest.mock.patch("urllib.request.urlopen", return_value=fake_response):
        status, _, _ = router.handle_request(
            "POST", f"/api/v1/customers/{cust.id}/compose-email",
            {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json.dumps({"subject": "Hi", "body": "test"}).encode("utf-8"),
        )

    assert status == 201
    logs = audit.query_logs(admin_actor, entity_type="customer", entity_id=cust.id, action="notify_email_failed")
    assert logs == []
