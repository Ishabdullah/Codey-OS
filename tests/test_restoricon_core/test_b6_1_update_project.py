"""
Unit tests for B6.1: CRMService.update_project, POST /api/v1/projects/{id}/update,
and the two-permission project-staff reassignment model.

Covers:
1. The base PERM_WRITE_PROJECTS gate and the ordinary-field vs reassignment-field split.
2. Permission-keyed ownership narrowing (_actor_may_reassign_project_staff) --
   proven with custom_permissions on roles that do NOT normally hold the perms,
   which is the only way to show the narrowing keys on permissions not role.
3. Field allow-list, stage/status rejection, None-guard, list-type guard,
   IntegrityError -> ValueError mapping, JSON round-trip, missing project.
4. Audit changed_fields nested map semantics.
5. Route-level wiring and status codes.
"""

import json

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_REASSIGN_ANY_PROJECT_STAFF,
    PERM_REASSIGN_PROJECT_STAFF,
    PERM_WRITE_PROJECTS,
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_PROJECT_MANAGER,
    ROLE_SALES,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Project, ProjectStage
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    comm_service = CommunicationService(db)
    crm_service = CRMService(db, audit_service)
    sched_service = SchedulingService(db, audit_service)
    auto_service = AutomationService(db, audit_service)
    ops_service = OperationsService(db, audit_service)
    router = APIRouter(
        auth_service=auth_service,
        crm_service=crm_service,
        comm_service=comm_service,
        audit_service=audit_service,
        scheduling_service=sched_service,
        automation_service=auto_service,
        operations_service=ops_service,
    )
    return {
        "db": db,
        "auth": auth_service,
        "audit": audit_service,
        "crm": crm_service,
        "router": router,
    }


def _ctx(user, role, **kw):
    return AuthContext(user.id, user.username, role, "human", token=kw.pop("token", None), **kw)


@pytest.fixture
def actors(env):
    auth = env["auth"]
    out = {}
    for key, role, uname in [
        ("admin", ROLE_ADMIN, "admin_u"),
        ("manager", ROLE_MANAGER, "mgr_u"),
        ("pm_owner", ROLE_PROJECT_MANAGER, "pm_owner_u"),
        ("pm_other", ROLE_PROJECT_MANAGER, "pm_other_u"),
        ("sales", ROLE_SALES, "sales_u"),
        ("tech", ROLE_TECHNICIAN, "tech_u"),
    ]:
        u = auth.create_user(uname, "Pass123!", uname, f"{uname}@r.com", role=role)
        t = auth.create_token(u)
        out[key] = _ctx(u, role, token=t)
    return out


@pytest.fixture
def customer(env, actors):
    return env["crm"].create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@example.com"), actors["admin"]
    )


@pytest.fixture
def project(env, actors, customer):
    """Project managed by pm_owner."""
    return env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Flood Restoration",
            property_address="1 Main St",
            project_type="water_damage",
            stage=ProjectStage.INTAKE,
            status="planning",
            project_manager_id=actors["pm_owner"].user_id,
        ),
        actors["admin"],
    )


@pytest.fixture
def unowned_project(env, actors, customer):
    """Project with no project manager."""
    return env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Roof Repair",
            property_address="2 Oak Ave",
            project_type="roofing",
            stage=ProjectStage.INTAKE,
            status="planning",
        ),
        actors["admin"],
    )


# ---------------------------------------------------------------------------
# 1. Permission matrix (service level)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "actor_key, field_ok, reassign_ok",
    [
        ("admin", True, True),
        ("manager", True, True),
        ("pm_owner", True, True),
        ("pm_other", True, False),
        ("sales", False, False),
        ("tech", False, False),
    ],
)
def test_permission_matrix(env, actors, project, actor_key, field_ok, reassign_ok):
    crm = env["crm"]
    actor = actors[actor_key]

    # Ordinary field: title
    if field_ok:
        res = crm.update_project(project.id, {"title": f"Updated by {actor_key}"}, actor)
        assert res.title == f"Updated by {actor_key}"
    else:
        with pytest.raises(PermissionError):
            crm.update_project(project.id, {"title": "nope"}, actor)

    # Reassignment field: project_manager_id (fresh fixtures each parametrized run).
    if reassign_ok:
        res = crm.update_project(project.id, {"project_manager_id": actors["pm_other"].user_id}, actor)
        assert res.project_manager_id == actors["pm_other"].user_id
    else:
        with pytest.raises(PermissionError):
            crm.update_project(project.id, {"project_manager_id": actors["pm_other"].user_id}, actor)


def test_pm_list_field_reassign_owned_vs_unowned(env, actors, project, unowned_project):
    """The decision-2 case that turns on ownership for the JSON list fields,
    not just project_manager_id: role-based PM, scoped grant."""
    crm = env["crm"]
    res = crm.update_project(project.id, {"assigned_employees": [7, 8]}, actors["pm_owner"])
    assert res.assigned_employees == [7, 8]

    with pytest.raises(PermissionError):
        crm.update_project(unowned_project.id, {"assigned_employees": [7, 8]}, actors["pm_owner"])
    with pytest.raises(PermissionError):
        crm.update_project(project.id, {"subcontractors": ["X"]}, actors["pm_other"])


def test_unchanged_values_bump_updated_at_no_audit(env, actors, project):
    crm = env["crm"]
    before = env["crm"].get_project(project.id, actors["admin"]).updated_at
    res = crm.update_project(
        project.id,
        {"title": project.title, "project_type": project.project_type},
        actors["admin"],
    )
    assert res.updated_at != before
    rows = env["audit"].query_logs(
        actors["admin"], entity_type="project", entity_id=project.id, action="update"
    )
    assert rows == []


# ---------------------------------------------------------------------------
# 2. Permission-keyed-ness (the actual point)
# ---------------------------------------------------------------------------

def test_sales_with_custom_scoped_perm_can_reassign_own_managed_project(env, actors, customer):
    auth = env["auth"]
    crm = env["crm"]
    su = auth.create_user("sales_pk", "Pass123!", "sales_pk", "sales_pk@r.com", role=ROLE_SALES)
    ctx = _ctx(
        su,
        ROLE_SALES,
        custom_permissions={PERM_WRITE_PROJECTS: True, PERM_REASSIGN_PROJECT_STAFF: True},
    )
    managed = crm.create_project(
        Project(
            customer_id=customer.id,
            title="Managed by sales",
            property_address="3 Elm St",
            project_type="water_damage",
            project_manager_id=su.id,
        ),
        actors["admin"],
    )
    not_managed = crm.create_project(
        Project(
            customer_id=customer.id,
            title="Not managed by sales",
            property_address="4 Elm St",
            project_type="water_damage",
            project_manager_id=actors["pm_owner"].user_id,
        ),
        actors["admin"],
    )

    res = crm.update_project(managed.id, {"assigned_employees": [su.id]}, ctx)
    assert res.assigned_employees == [su.id]

    with pytest.raises(PermissionError):
        crm.update_project(not_managed.id, {"assigned_employees": [su.id]}, ctx)


def test_admin_with_any_perm_denied_falls_back_to_owner_scope(env, actors, customer):
    """custom_permissions turning OFF reassign:any_project_staff must drop the
    admin to owner-scoped behaviour, not leave a role-keyed bypass (NEW-194)."""
    auth = env["auth"]
    crm = env["crm"]
    au = auth.create_user("adm2", "Pass123!", "adm2", "adm2@r.com", role=ROLE_ADMIN)
    ctx = _ctx(au, ROLE_ADMIN, custom_permissions={PERM_REASSIGN_ANY_PROJECT_STAFF: False})

    managed = crm.create_project(
        Project(
            customer_id=customer.id,
            title="Adm2 managed",
            property_address="5 Elm St",
            project_type="water_damage",
            project_manager_id=au.id,
        ),
        actors["admin"],
    )
    not_managed = crm.create_project(
        Project(
            customer_id=customer.id,
            title="Adm2 not managed",
            property_address="6 Elm St",
            project_type="water_damage",
            project_manager_id=actors["pm_owner"].user_id,
        ),
        actors["admin"],
    )

    res = crm.update_project(managed.id, {"subcontractors": ["Acme"]}, ctx)
    assert res.subcontractors == ["Acme"]

    with pytest.raises(PermissionError):
        crm.update_project(not_managed.id, {"subcontractors": ["Acme"]}, ctx)


def test_pm_may_reassign_away_from_self(env, actors, project):
    """Pre-update ownership: pm_owner manages it, so may hand it off."""
    res = env["crm"].update_project(
        project.id, {"project_manager_id": actors["pm_other"].user_id}, actors["pm_owner"]
    )
    assert res.project_manager_id == actors["pm_other"].user_id


# ---------------------------------------------------------------------------
# 3. Validation / guards
# ---------------------------------------------------------------------------

def test_unknown_field_rejected(env, actors, project):
    with pytest.raises(ValueError, match="Unknown field"):
        env["crm"].update_project(project.id, {"bogus": 1}, actors["admin"])


@pytest.mark.parametrize("payload", [{"stage": "completed"}, {"status": "on_hold"}])
def test_stage_status_rejected_with_pointer(env, actors, project, payload):
    with pytest.raises(ValueError, match="stage-transition endpoint"):
        env["crm"].update_project(project.id, payload, actors["admin"])


def test_none_value_rejected(env, actors, project):
    with pytest.raises(ValueError, match="cannot be set to None"):
        env["crm"].update_project(project.id, {"title": None}, actors["admin"])


def test_project_manager_id_cannot_be_nulled(env, actors, project):
    with pytest.raises(ValueError, match="cannot be set to None"):
        env["crm"].update_project(project.id, {"project_manager_id": None}, actors["admin"])


def test_assigned_employees_must_be_list(env, actors, project):
    with pytest.raises(ValueError, match="must be a list"):
        env["crm"].update_project(project.id, {"assigned_employees": {"a": 1}}, actors["admin"])


def test_assigned_employees_round_trip(env, actors, project):
    env["crm"].update_project(project.id, {"assigned_employees": [2, 3]}, actors["admin"])
    fetched = env["crm"].get_project(project.id, actors["admin"])
    assert fetched.assigned_employees == [2, 3]


def test_bad_project_manager_fk_maps_to_value_error(env, actors, project):
    with pytest.raises(ValueError, match="data constraint"):
        env["crm"].update_project(project.id, {"project_manager_id": 999999}, actors["admin"])


def test_missing_project_returns_none(env, actors):
    assert env["crm"].update_project(999999, {"title": "x"}, actors["admin"]) is None


def test_empty_updates_returns_project_no_audit(env, actors, project):
    res = env["crm"].update_project(project.id, {}, actors["admin"])
    assert res.id == project.id
    rows = env["audit"].query_logs(actors["admin"], entity_type="project", entity_id=project.id, action="update")
    assert rows == []


# ---------------------------------------------------------------------------
# 4. Audit changed_fields semantics
# ---------------------------------------------------------------------------

def test_audit_changed_fields_nested_map(env, actors, project):
    crm = env["crm"]
    old_pm = project.project_manager_id
    new_pm = actors["pm_other"].user_id
    crm.update_project(
        project.id,
        {"project_manager_id": new_pm, "notes": "site visited", "title": project.title},
        actors["manager"],
    )
    rows = env["audit"].query_logs(
        actors["admin"], entity_type="project", entity_id=project.id, action="update"
    )
    assert len(rows) == 1
    changed = rows[0].details["changed_fields"]
    assert changed["project_manager_id"] == {"old": old_pm, "new": new_pm}
    assert "notes" in changed
    # title was passed unchanged -> not logged
    assert "title" not in changed


def test_audit_logs_list_reorder(env, actors, project):
    crm = env["crm"]
    crm.update_project(project.id, {"assigned_employees": [1, 2]}, actors["admin"])
    crm.update_project(project.id, {"assigned_employees": [2, 1]}, actors["admin"])
    rows = env["audit"].query_logs(
        actors["admin"], entity_type="project", entity_id=project.id, action="update"
    )
    # most recent first
    changed = rows[0].details["changed_fields"]
    assert changed["assigned_employees"] == {"old": [1, 2], "new": [2, 1]}


# ---------------------------------------------------------------------------
# 5. Route level
# ---------------------------------------------------------------------------

def _hdr(ctx):
    return {"Authorization": f"Bearer {ctx.token}"}


def test_route_admin_update_title_200(env, actors, project):
    status, _, data = env["router"].handle_request(
        "POST", f"/api/v1/projects/{project.id}/update", _hdr(actors["admin"]),
        json.dumps({"title": "X"}).encode(),
    )
    assert status == 200
    assert data["project"]["title"] == "X"


def test_route_unknown_field_400(env, actors, project):
    status, _, data = env["router"].handle_request(
        "POST", f"/api/v1/projects/{project.id}/update", _hdr(actors["admin"]),
        json.dumps({"bogus": 1}).encode(),
    )
    assert status == 400


def test_route_pm_not_owner_reassign_403(env, actors, project):
    status, _, _ = env["router"].handle_request(
        "POST", f"/api/v1/projects/{project.id}/update", _hdr(actors["pm_other"]),
        json.dumps({"project_manager_id": actors["pm_other"].user_id}).encode(),
    )
    assert status == 403


def test_route_bad_fk_400(env, actors, project):
    status, _, _ = env["router"].handle_request(
        "POST", f"/api/v1/projects/{project.id}/update", _hdr(actors["admin"]),
        json.dumps({"project_manager_id": 999999}).encode(),
    )
    assert status == 400


def test_route_missing_project_404(env, actors):
    status, _, _ = env["router"].handle_request(
        "POST", "/api/v1/projects/999999/update", _hdr(actors["admin"]),
        json.dumps({"title": "X"}).encode(),
    )
    assert status == 404
