"""
Unit tests for NEW-628 (ROLE_TECHNICIAN half): operations_service.py's nine
PERM_READ_OPERATIONS-gated methods (get_project, get_milestone,
list_milestones, get_work_order, list_work_orders, get_equipment,
list_equipment, list_project_deployments, get_project_summary) narrowed by
`projects.assigned_employees_json` membership for ROLE_TECHNICIAN, mirroring
crm_service.py's already-shipped identical check (crm_service.py ~L2833/
~L2894). ROLE_TECHNICIAN itself keeps PERM_READ_OPERATIONS/
PERM_WRITE_OPERATIONS org-wide (auth.py) -- this round only adds row-level
ownership narrowing in operations_service.py, no permission-set change.

ROLE_PROJECT_MANAGER is explicitly NOT touched by this round (it holds
PERM_READ_ALL_PROJECTS by design) -- covered here only as a regression check
that PM/admin access stays fully unnarrowed.
"""

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_READ_OPERATIONS,
    ROLE_ADMIN,
    ROLE_PROJECT_MANAGER,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    Equipment,
    EquipmentStatus,
    Project,
    ProjectMilestone,
    ProjectStage,
    WorkOrder,
)
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.operations_service import OperationsService


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)
    ops_service = OperationsService(db, audit_service)
    return {
        "db": db,
        "auth": auth_service,
        "crm": crm_service,
        "ops": ops_service,
    }


@pytest.fixture
def actors(env):
    auth = env["auth"]
    u_admin = auth.create_user("admin_628", "Pass123!", "Admin", "admin_628@test.com", role=ROLE_ADMIN)
    ctx_admin = AuthContext(u_admin.id, u_admin.username, ROLE_ADMIN, "human")

    u_pm = auth.create_user("pm_628", "Pass123!", "PM", "pm_628@test.com", role=ROLE_PROJECT_MANAGER)
    ctx_pm = AuthContext(u_pm.id, u_pm.username, ROLE_PROJECT_MANAGER, "human")

    u_tech_a = auth.create_user("tech_a_628", "Pass123!", "Tech A", "tech_a_628@test.com", role=ROLE_TECHNICIAN)
    ctx_tech_a = AuthContext(u_tech_a.id, u_tech_a.username, ROLE_TECHNICIAN, "human")

    u_tech_b = auth.create_user("tech_b_628", "Pass123!", "Tech B", "tech_b_628@test.com", role=ROLE_TECHNICIAN)
    ctx_tech_b = AuthContext(u_tech_b.id, u_tech_b.username, ROLE_TECHNICIAN, "human")

    return {
        "admin": ctx_admin,
        "pm": ctx_pm,
        "tech_a": ctx_tech_a,
        "tech_b": ctx_tech_b,
    }


@pytest.fixture
def customer(env, actors):
    from restoricon_core.models import Customer

    return env["crm"].create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane_628@example.com"),
        actors["admin"],
    )


@pytest.fixture
def assigned_project(env, actors, customer):
    """A project with tech_a in assigned_employees -- tech_a must keep
    read/write access; tech_b must be denied."""
    return env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Tech A's job",
            property_address="1 Oak St",
            project_type="water_damage",
            stage=ProjectStage.INTAKE,
            assigned_employees=[actors["tech_a"].user_id],
        ),
        actors["admin"],
    )


@pytest.fixture
def unassigned_project(env, actors, customer):
    """A project with no technician assigned at all -- tech_a must be
    denied."""
    return env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Nobody's job",
            property_address="2 Oak St",
            project_type="fire_damage",
            stage=ProjectStage.INTAKE,
        ),
        actors["admin"],
    )


def _make_milestone_and_work_order(env, actors, project):
    milestone = env["ops"].create_milestone(
        ProjectMilestone(project_id=project.id, name="Demo"),
        actors["admin"],
    )
    work_order = env["ops"].create_work_order(
        WorkOrder(project_id=project.id, title="WO 1", trade="general"),
        actors["admin"],
    )
    return milestone, work_order


# ==========================================
# get_project / list projects behavior
# ==========================================


def test_assigned_technician_sees_own_project(env, actors, assigned_project):
    proj = env["ops"].get_project(assigned_project.id, actors["tech_a"])
    assert proj is not None
    assert proj.id == assigned_project.id


def test_unassigned_technician_denied_project(env, actors, assigned_project):
    with pytest.raises(PermissionError):
        env["ops"].get_project(assigned_project.id, actors["tech_b"])


def test_technician_denied_project_with_no_assignments_at_all(env, actors, unassigned_project):
    with pytest.raises(PermissionError):
        env["ops"].get_project(unassigned_project.id, actors["tech_a"])


def test_pm_sees_any_project_unnarrowed(env, actors, assigned_project, unassigned_project):
    """Regression: ROLE_PROJECT_MANAGER is untouched by NEW-628 -- it holds
    PERM_READ_ALL_PROJECTS by design, no ownership narrowing applies."""
    proj1 = env["ops"].get_project(assigned_project.id, actors["pm"])
    proj2 = env["ops"].get_project(unassigned_project.id, actors["pm"])
    assert proj1 is not None
    assert proj2 is not None


def test_admin_sees_any_project_unnarrowed(env, actors, unassigned_project):
    proj = env["ops"].get_project(unassigned_project.id, actors["admin"])
    assert proj is not None


# ==========================================
# get_milestone / list_milestones / get_work_order / list_work_orders
# ==========================================


def test_technician_milestone_and_work_order_owned_vs_denied(env, actors, assigned_project, unassigned_project):
    own_m, own_wo = _make_milestone_and_work_order(env, actors, assigned_project)
    other_m, other_wo = _make_milestone_and_work_order(env, actors, unassigned_project)

    assert env["ops"].get_milestone(own_m.id, actors["tech_a"]) is not None
    with pytest.raises(PermissionError):
        env["ops"].get_milestone(other_m.id, actors["tech_a"])

    assert env["ops"].get_work_order(own_wo.id, actors["tech_a"]) is not None
    with pytest.raises(PermissionError):
        env["ops"].get_work_order(other_wo.id, actors["tech_a"])


def test_technician_list_milestones_denied_for_unassigned_project(env, actors, unassigned_project):
    with pytest.raises(PermissionError):
        env["ops"].list_milestones(unassigned_project.id, actors["tech_a"])


def test_technician_list_milestones_allowed_for_assigned_project(env, actors, assigned_project):
    _make_milestone_and_work_order(env, actors, assigned_project)
    rows = env["ops"].list_milestones(assigned_project.id, actors["tech_a"])
    assert len(rows) == 1


def test_technician_list_work_orders_project_id_none_only_returns_assigned(env, actors, assigned_project, unassigned_project):
    """No project_id filter given -- must still be narrowed to assigned
    projects' work orders, not leak everything."""
    _, own_wo = _make_milestone_and_work_order(env, actors, assigned_project)
    _, other_wo = _make_milestone_and_work_order(env, actors, unassigned_project)

    rows = env["ops"].list_work_orders(actors["tech_a"])
    ids = {wo.id for wo in rows}
    assert own_wo.id in ids
    assert other_wo.id not in ids


def test_technician_list_work_orders_with_project_id_denied_for_unassigned(env, actors, unassigned_project):
    _make_milestone_and_work_order(env, actors, unassigned_project)
    rows = env["ops"].list_work_orders(actors["tech_a"], project_id=unassigned_project.id)
    assert rows == []


def test_pm_list_work_orders_sees_all_unnarrowed(env, actors, assigned_project, unassigned_project):
    _, own_wo = _make_milestone_and_work_order(env, actors, assigned_project)
    _, other_wo = _make_milestone_and_work_order(env, actors, unassigned_project)

    rows = env["ops"].list_work_orders(actors["pm"])
    ids = {wo.id for wo in rows}
    assert own_wo.id in ids
    assert other_wo.id in ids


# ==========================================
# get_equipment / list_equipment / list_project_deployments
# ==========================================


_equipment_counter = [0]


def _make_equipment(env, actors):
    _equipment_counter[0] += 1
    return env["ops"].create_equipment(
        Equipment(asset_tag=f"AT-628-{_equipment_counter[0]}", name="Dehumidifier", category="dehumidifier"),
        actors["admin"],
    )


def test_technician_sees_available_equipment_not_yet_deployed(env, actors):
    """Available (current_project_id IS NULL) equipment stays visible to a
    technician -- required so deploy_equipment's own pre-read still works."""
    eq = _make_equipment(env, actors)
    fetched = env["ops"].get_equipment(eq.id, actors["tech_a"])
    assert fetched is not None
    assert fetched.status == EquipmentStatus.AVAILABLE


def test_technician_can_deploy_and_return_equipment_to_own_project(env, actors, assigned_project):
    """Regression for the deploy_equipment _after re-read fix: a technician
    deploying equipment to their OWN assigned project must succeed end to
    end (write + audit), not raise PermissionError on the post-write
    re-read."""
    eq = _make_equipment(env, actors)
    deployment = env["ops"].deploy_equipment(eq.id, assigned_project.id, actors["tech_a"])
    assert deployment is not None
    assert deployment.project_id == assigned_project.id

    deployed_eq = env["ops"].get_equipment(eq.id, actors["tech_a"])
    assert deployed_eq is not None
    assert deployed_eq.status == EquipmentStatus.DEPLOYED

    returned = env["ops"].return_equipment(deployment.id, actors["tech_a"])
    assert returned.returned_at is not None


def test_technician_denied_equipment_deployed_to_other_project(env, actors, assigned_project, unassigned_project):
    eq = _make_equipment(env, actors)
    env["ops"].deploy_equipment(eq.id, unassigned_project.id, actors["admin"])

    with pytest.raises(PermissionError):
        env["ops"].get_equipment(eq.id, actors["tech_a"])


def test_technician_list_equipment_filters_by_deployment_ownership(env, actors, assigned_project, unassigned_project):
    available_eq = _make_equipment(env, actors)
    own_deployed_eq = _make_equipment(env, actors)
    other_deployed_eq = _make_equipment(env, actors)

    env["ops"].deploy_equipment(own_deployed_eq.id, assigned_project.id, actors["admin"])
    env["ops"].deploy_equipment(other_deployed_eq.id, unassigned_project.id, actors["admin"])

    rows = env["ops"].list_equipment(actors["tech_a"])
    ids = {e.id for e in rows}
    assert available_eq.id in ids
    assert own_deployed_eq.id in ids
    assert other_deployed_eq.id not in ids


def test_technician_list_project_deployments_denied_for_unassigned_project(env, actors, unassigned_project):
    with pytest.raises(PermissionError):
        env["ops"].list_project_deployments(unassigned_project.id, actors["tech_a"])


def test_technician_list_project_deployments_allowed_for_assigned_project(env, actors, assigned_project):
    eq = _make_equipment(env, actors)
    env["ops"].deploy_equipment(eq.id, assigned_project.id, actors["tech_a"])
    rows = env["ops"].list_project_deployments(assigned_project.id, actors["tech_a"])
    assert len(rows) == 1


def test_pm_equipment_and_deployments_unnarrowed(env, actors, unassigned_project):
    eq = _make_equipment(env, actors)
    env["ops"].deploy_equipment(eq.id, unassigned_project.id, actors["admin"])

    fetched = env["ops"].get_equipment(eq.id, actors["pm"])
    assert fetched is not None
    rows = env["ops"].list_project_deployments(unassigned_project.id, actors["pm"])
    assert len(rows) == 1


# ==========================================
# get_project_summary (transitive coverage, no direct edit)
# ==========================================


def test_technician_get_project_summary_works_for_assigned_project(env, actors, assigned_project):
    _make_milestone_and_work_order(env, actors, assigned_project)
    summary = env["ops"].get_project_summary(assigned_project.id, actors["tech_a"])
    assert summary["project"]["id"] == assigned_project.id
    assert summary["equipment_summary"] is not None
    assert "milestone_summary" in summary
    assert "work_order_summary" in summary


def test_technician_get_project_summary_denied_for_unassigned_project(env, actors, unassigned_project):
    with pytest.raises(PermissionError):
        env["ops"].get_project_summary(unassigned_project.id, actors["tech_a"])


# ==========================================
# writes: assigned technician retains write access (transitive via reads)
# ==========================================


def test_assigned_technician_can_update_milestone_status(env, actors, assigned_project):
    milestone, _ = _make_milestone_and_work_order(env, actors, assigned_project)
    updated = env["ops"].update_milestone_status(milestone.id, "in_progress", actors["tech_a"])
    assert updated.status == "in_progress"


def test_unassigned_technician_denied_update_milestone_status(env, actors, unassigned_project):
    """update_milestone_status inherits ownership narrowing via its own
    internal get_milestone(...) call -- no separate technician check needed
    in that method."""
    milestone, _ = _make_milestone_and_work_order(env, actors, unassigned_project)
    with pytest.raises(PermissionError):
        env["ops"].update_milestone_status(milestone.id, "in_progress", actors["tech_a"])


def test_technician_read_operations_permission_unchanged(env, actors):
    """Confirm this round did not touch ROLE_TECHNICIAN's permission set --
    it still holds PERM_READ_OPERATIONS org-wide, narrowing happens entirely
    in operations_service.py row-level checks."""
    assert actors["tech_a"].has_permission(PERM_READ_OPERATIONS)
