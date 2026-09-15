"""
NEW-507 (Subcontractors follow-on round, 2026-09-15): delete route +
active-reference precheck for subcontractors, blocking on BOTH (a) the
linked user's active staff_schedules and (b) the subcontractor's own
non-terminal work_orders -- mirrors the Users/Appointment-Types
active-reference-precheck-then-delete pattern (Delete-buttons round,
Ish 2026-09-11), but combined across two distinct reference types
instead of one.
"""

import json

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Project, StaffSchedule, Subcontractor, WorkOrder
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    auth = AuthService(db)
    crm = CRMService(db, audit)
    comm = CommunicationService(db)
    sched = SchedulingService(db, audit)
    auto = AutomationService(db, audit)
    ops = OperationsService(db, audit)

    router = APIRouter(
        auth_service=auth,
        crm_service=crm,
        comm_service=comm,
        audit_service=audit,
        scheduling_service=sched,
        automation_service=auto,
        operations_service=ops,
    )

    admin = auth.create_user("admin_chief", "AdminMaster123!", "Chief Administrator", "chief@restoricon.com", ROLE_ADMIN)
    admin_token = auth.create_token(admin)
    admin_ctx = auth.authenticate_token(admin_token)

    # A no-permission actor (technician role has neither
    # read:subcontractors nor write:subcontractors).
    tech = auth.create_user("tech_dan", "TechSecret123!", "Dan Technician", "dan@restoricon.com", ROLE_TECHNICIAN, actor_context=admin_ctx)
    tech_token = auth.create_token(tech)

    return {
        "db": db,
        "auth": auth,
        "crm": crm,
        "sched": sched,
        "ops": ops,
        "router": router,
        "admin": admin,
        "admin_token": admin_token,
        "admin_ctx": admin_ctx,
        "tech": tech,
        "tech_token": tech_token,
    }


def _make_project(env):
    cust = env["crm"].create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@example.com"),
        env["admin_ctx"],
    )
    proj = Project(
        customer_id=cust.id,
        title="Basement Restoration",
        property_address="1 Main St",
        project_type="water_damage",
    )
    return env["crm"].create_project(proj, env["admin_ctx"])


def _make_subcontractor(env, **kwargs):
    return env["crm"].create_subcontractor(
        Subcontractor(company_name=kwargs.pop("company_name", "Acme Roofing"), **kwargs),
        env["admin_ctx"],
    )


def _make_work_order(env, sub_id, status="dispatched"):
    proj = _make_project(env)
    wo = WorkOrder(
        project_id=proj.id, title="Roof tarp", trade="roofing",
        assigned_subcontractor_id=sub_id, status=status,
    )
    return env["ops"].create_work_order(wo, env["admin_ctx"])


# ---------------------------------------------------------------------------
# Active-references route
# ---------------------------------------------------------------------------

def test_active_references_empty_when_no_user_and_no_work_orders(env):
    router = env["router"]
    admin_token = env["admin_token"]
    sub = _make_subcontractor(env)
    headers = {"authorization": f"Bearer {admin_token}"}

    status, _, res = router.handle_request(
        "GET", f"/api/v1/subcontractors/{sub.id}/active-references", headers, b""
    )
    assert status == 200
    assert res["active_references"] == {"staff_schedules": [], "work_orders": []}


def test_active_references_404_for_missing_subcontractor(env):
    router = env["router"]
    admin_token = env["admin_token"]
    headers = {"authorization": f"Bearer {admin_token}"}

    status, _, res = router.handle_request(
        "GET", "/api/v1/subcontractors/999999/active-references", headers, b""
    )
    assert status == 404
    assert res["error"] == "Subcontractor not found"


def test_active_references_reports_linked_users_scheduled_schedule(env):
    router = env["router"]
    admin_token = env["admin_token"]
    admin = env["admin"]
    sched = env["sched"]
    admin_ctx = env["admin_ctx"]
    headers = {"authorization": f"Bearer {admin_token}"}

    sub = _make_subcontractor(env, user_id=admin.id)
    sched.create_staff_schedule(
        StaffSchedule(
            user_id=admin.id, title="Job site visit",
            start_time="2027-01-05T09:00:00", end_time="2027-01-05T11:00:00",
            status="scheduled", notes=None,
        ),
        admin_ctx,
    )

    status, _, res = router.handle_request(
        "GET", f"/api/v1/subcontractors/{sub.id}/active-references", headers, b""
    )
    assert status == 200
    assert len(res["active_references"]["staff_schedules"]) == 1
    assert res["active_references"]["staff_schedules"][0]["title"] == "Job site visit"
    assert res["active_references"]["work_orders"] == []


def test_active_references_reports_non_terminal_work_order(env):
    router = env["router"]
    admin_token = env["admin_token"]
    headers = {"authorization": f"Bearer {admin_token}"}

    sub = _make_subcontractor(env)
    wo = _make_work_order(env, sub.id, status="dispatched")

    status, _, res = router.handle_request(
        "GET", f"/api/v1/subcontractors/{sub.id}/active-references", headers, b""
    )
    assert status == 200
    assert res["active_references"]["staff_schedules"] == []
    assert len(res["active_references"]["work_orders"]) == 1
    assert res["active_references"]["work_orders"][0]["id"] == wo.id


@pytest.mark.parametrize("terminal_status", ["completed", "verified", "cancelled"])
def test_active_references_excludes_terminal_work_orders(env, terminal_status):
    router = env["router"]
    admin_token = env["admin_token"]
    headers = {"authorization": f"Bearer {admin_token}"}

    sub = _make_subcontractor(env)
    _make_work_order(env, sub.id, status=terminal_status)

    status, _, res = router.handle_request(
        "GET", f"/api/v1/subcontractors/{sub.id}/active-references", headers, b""
    )
    assert status == 200
    assert res["active_references"]["work_orders"] == []


def test_active_references_rbac_403(env):
    router = env["router"]
    tech_token = env["tech_token"]
    sub = _make_subcontractor(env)
    headers = {"authorization": f"Bearer {tech_token}"}

    status, _, _ = router.handle_request(
        "GET", f"/api/v1/subcontractors/{sub.id}/active-references", headers, b""
    )
    assert status == 403


# ---------------------------------------------------------------------------
# Delete route
# ---------------------------------------------------------------------------

def test_delete_clean_subcontractor_succeeds(env):
    router = env["router"]
    crm = env["crm"]
    admin_token = env["admin_token"]
    headers = {"authorization": f"Bearer {admin_token}"}

    sub = _make_subcontractor(env)
    status, _, res = router.handle_request(
        "POST", f"/api/v1/subcontractors/{sub.id}/delete", headers, b""
    )
    assert status == 200
    assert res["deleted"] is True
    assert res["subcontractor_id"] == sub.id
    assert crm._get_subcontractor_unguarded(sub.id) is None


def test_delete_blocked_by_active_staff_schedule_itemized(env):
    router = env["router"]
    crm = env["crm"]
    admin = env["admin"]
    admin_ctx = env["admin_ctx"]
    admin_token = env["admin_token"]
    sched = env["sched"]
    headers = {"authorization": f"Bearer {admin_token}"}

    sub = _make_subcontractor(env, user_id=admin.id)
    created = sched.create_staff_schedule(
        StaffSchedule(
            user_id=admin.id, title="Job site visit",
            start_time="2027-01-05T09:00:00", end_time="2027-01-05T11:00:00",
            status="scheduled", notes=None,
        ),
        admin_ctx,
    )

    status, _, res = router.handle_request(
        "POST", f"/api/v1/subcontractors/{sub.id}/delete", headers, b""
    )
    assert status == 400
    assert str(created.id) in res["error"]
    assert "Job site visit" in res["error"]
    assert "staff schedule" in res["error"]
    assert crm._get_subcontractor_unguarded(sub.id) is not None


def test_delete_blocked_by_non_terminal_work_order_itemized(env):
    router = env["router"]
    crm = env["crm"]
    admin_token = env["admin_token"]
    headers = {"authorization": f"Bearer {admin_token}"}

    sub = _make_subcontractor(env)
    wo = _make_work_order(env, sub.id, status="in_progress")

    status, _, res = router.handle_request(
        "POST", f"/api/v1/subcontractors/{sub.id}/delete", headers, b""
    )
    assert status == 400
    assert wo.work_order_number in res["error"]
    assert "work order" in res["error"]
    assert crm._get_subcontractor_unguarded(sub.id) is not None


def test_delete_blocked_when_both_categories_present_covers_both(env):
    router = env["router"]
    admin = env["admin"]
    admin_ctx = env["admin_ctx"]
    admin_token = env["admin_token"]
    sched = env["sched"]
    headers = {"authorization": f"Bearer {admin_token}"}

    sub = _make_subcontractor(env, user_id=admin.id)
    sched.create_staff_schedule(
        StaffSchedule(
            user_id=admin.id, title="Job site visit",
            start_time="2027-01-05T09:00:00", end_time="2027-01-05T11:00:00",
            status="scheduled", notes=None,
        ),
        admin_ctx,
    )
    wo = _make_work_order(env, sub.id, status="accepted")

    status, _, res = router.handle_request(
        "POST", f"/api/v1/subcontractors/{sub.id}/delete", headers, b""
    )
    assert status == 400
    assert "staff schedule" in res["error"]
    assert "work order" in res["error"]
    assert "Job site visit" in res["error"]
    assert wo.work_order_number in res["error"]


def test_delete_succeeds_with_only_terminal_references(env):
    router = env["router"]
    admin = env["admin"]
    admin_ctx = env["admin_ctx"]
    admin_token = env["admin_token"]
    sched = env["sched"]
    crm = env["crm"]
    headers = {"authorization": f"Bearer {admin_token}"}

    sub = _make_subcontractor(env, user_id=admin.id)
    sched.create_staff_schedule(
        StaffSchedule(
            user_id=admin.id, title="Old completed job",
            start_time="2020-01-01T09:00:00", end_time="2020-01-01T11:00:00",
            status="completed", notes=None,
        ),
        admin_ctx,
    )
    _make_work_order(env, sub.id, status="cancelled")

    status, _, res = router.handle_request(
        "POST", f"/api/v1/subcontractors/{sub.id}/delete", headers, b""
    )
    assert status == 200
    assert res["deleted"] is True
    assert crm._get_subcontractor_unguarded(sub.id) is None


def test_delete_404_for_missing_subcontractor(env):
    router = env["router"]
    admin_token = env["admin_token"]
    headers = {"authorization": f"Bearer {admin_token}"}

    status, _, res = router.handle_request(
        "POST", "/api/v1/subcontractors/999999/delete", headers, b""
    )
    assert status == 404
    assert res["error"] == "Subcontractor not found"


def test_delete_rbac_403_before_any_db_read_no_data_leak(env):
    """Unprivileged actor gets a bare 403 -- not a 400 that leaks itemized
    schedule/work-order data. Mirrors
    test_route_delete_user_rbac_403_even_with_active_reference_present."""
    router = env["router"]
    admin = env["admin"]
    admin_ctx = env["admin_ctx"]
    admin_token = env["admin_token"]
    tech_token = env["tech_token"]
    sched = env["sched"]
    headers = {"authorization": f"Bearer {tech_token}"}

    sub = _make_subcontractor(env, user_id=admin.id)
    sched.create_staff_schedule(
        StaffSchedule(
            user_id=admin.id, title="Sensitive job site visit",
            start_time="2027-03-01T09:00:00", end_time="2027-03-01T11:00:00",
            status="scheduled", notes=None,
        ),
        admin_ctx,
    )

    status, _, res = router.handle_request(
        "POST", f"/api/v1/subcontractors/{sub.id}/delete", headers, b""
    )
    assert status == 403
    assert "Sensitive job site visit" not in str(res)

    # Sanity: the admin (who DOES hold write:subcontractors) is still
    # blocked with the itemized 400, confirming the reference check
    # itself still runs for a privileged actor.
    admin_headers = {"authorization": f"Bearer {admin_token}"}
    status, _, res = router.handle_request(
        "POST", f"/api/v1/subcontractors/{sub.id}/delete", admin_headers, b""
    )
    assert status == 400
    assert "Sensitive job site visit" in res["error"]


def test_delete_audit_logs_snapshot(env):
    router = env["router"]
    db = env["db"]
    admin_token = env["admin_token"]
    headers = {"authorization": f"Bearer {admin_token}"}

    sub = _make_subcontractor(env, company_name="Zenith Drywall")
    status, _, res = router.handle_request(
        "POST", f"/api/v1/subcontractors/{sub.id}/delete", headers, b""
    )
    assert status == 200

    conn = db.get_connection()
    row = conn.execute(
        "SELECT * FROM audit_log WHERE action = 'subcontractor_deleted' AND entity_id = ?;",
        (sub.id,),
    ).fetchone()
    assert row is not None
    details = json.loads(row["details_json"])
    assert details["snapshot"]["company_name"] == "Zenith Drywall"
