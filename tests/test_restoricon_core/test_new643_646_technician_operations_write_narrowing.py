"""
Unit tests for NEW-643/644/645/646 plus two newly-found gaps (create_milestone,
create_work_order): operations_service.py's write-path counterpart to NEW-628
(commit 661ce48), which narrowed nine READ methods to ROLE_TECHNICIAN's
`projects.assigned_employees_json` assignment. This round narrows the WRITE
side: create_milestone, create_work_order, update_work_order,
deploy_equipment, return_equipment, and get_active_work_orders_for_subcontractor,
all keyed on the same existing `_actor_assigned_to_project` /
`_technician_assigned_project_ids` helpers, matching NEW-628's precedent.

ROLE_PROJECT_MANAGER is explicitly NOT touched by this round (it holds
PERM_READ_ALL_PROJECTS/unnarrowed access by design) -- covered here only as a
regression check that PM/admin write access stays fully unnarrowed.
"""

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
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
    Subcontractor,
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
    u_admin = auth.create_user("admin_643", "Pass123!", "Admin", "admin_643@test.com", role=ROLE_ADMIN)
    ctx_admin = AuthContext(u_admin.id, u_admin.username, ROLE_ADMIN, "human")

    u_pm = auth.create_user("pm_643", "Pass123!", "PM", "pm_643@test.com", role=ROLE_PROJECT_MANAGER)
    ctx_pm = AuthContext(u_pm.id, u_pm.username, ROLE_PROJECT_MANAGER, "human")

    u_tech_a = auth.create_user("tech_a_643", "Pass123!", "Tech A", "tech_a_643@test.com", role=ROLE_TECHNICIAN)
    ctx_tech_a = AuthContext(u_tech_a.id, u_tech_a.username, ROLE_TECHNICIAN, "human")

    u_tech_b = auth.create_user("tech_b_643", "Pass123!", "Tech B", "tech_b_643@test.com", role=ROLE_TECHNICIAN)
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
        Customer(first_name="Jane", last_name="Doe", email="jane_643@example.com"),
        actors["admin"],
    )


@pytest.fixture
def assigned_project(env, actors, customer):
    """A project with tech_a in assigned_employees -- tech_a must keep
    write access; tech_b must be denied."""
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


# ==========================================
# create_milestone (write-path counterpart to NEW-628, task item 5)
# ==========================================


def test_assigned_technician_can_create_milestone(env, actors, assigned_project):
    m = env["ops"].create_milestone(
        ProjectMilestone(project_id=assigned_project.id, name="Demo"),
        actors["tech_a"],
    )
    assert m.id is not None


def test_unassigned_technician_denied_create_milestone(env, actors, unassigned_project):
    with pytest.raises(PermissionError):
        env["ops"].create_milestone(
            ProjectMilestone(project_id=unassigned_project.id, name="Demo"),
            actors["tech_a"],
        )


def test_pm_create_milestone_unnarrowed(env, actors, unassigned_project):
    m = env["ops"].create_milestone(
        ProjectMilestone(project_id=unassigned_project.id, name="Demo"),
        actors["pm"],
    )
    assert m.id is not None


# ==========================================
# create_work_order (write-path counterpart to NEW-628, task item 6)
# ==========================================


def test_assigned_technician_can_create_work_order(env, actors, assigned_project):
    wo = env["ops"].create_work_order(
        WorkOrder(project_id=assigned_project.id, title="WO", trade="general"),
        actors["tech_a"],
    )
    assert wo.id is not None


def test_unassigned_technician_denied_create_work_order(env, actors, unassigned_project):
    with pytest.raises(PermissionError):
        env["ops"].create_work_order(
            WorkOrder(project_id=unassigned_project.id, title="WO", trade="general"),
            actors["tech_a"],
        )


def test_pm_create_work_order_unnarrowed(env, actors, unassigned_project):
    wo = env["ops"].create_work_order(
        WorkOrder(project_id=unassigned_project.id, title="WO", trade="general"),
        actors["pm"],
    )
    assert wo.id is not None


# ==========================================
# update_work_order (NEW-643)
# ==========================================


def test_assigned_technician_can_update_work_order(env, actors, assigned_project):
    wo = env["ops"].create_work_order(
        WorkOrder(project_id=assigned_project.id, title="WO", trade="general"),
        actors["admin"],
    )
    wo.title = "Updated title"
    updated = env["ops"].update_work_order(wo, actors["tech_a"])
    assert updated.title == "Updated title"


def test_unassigned_technician_denied_update_work_order(env, actors, unassigned_project):
    wo = env["ops"].create_work_order(
        WorkOrder(project_id=unassigned_project.id, title="WO", trade="general"),
        actors["admin"],
    )
    wo.title = "Updated title"
    with pytest.raises(PermissionError):
        env["ops"].update_work_order(wo, actors["tech_a"])


def test_update_work_order_uses_db_project_id_not_model(env, actors, assigned_project, unassigned_project):
    """The model's project_id is never written back by update_work_order --
    NEW-643 requires the DB row's CURRENT project_id be used for the
    ownership check, not a caller-supplied (possibly stale/spoofed) model
    field. A work order that actually belongs to unassigned_project, but
    whose in-memory model object has been hand-edited to claim
    assigned_project.id, must still be denied for tech_a."""
    wo = env["ops"].create_work_order(
        WorkOrder(project_id=unassigned_project.id, title="WO", trade="general"),
        actors["admin"],
    )
    wo.project_id = assigned_project.id  # spoofed -- DB row is still unassigned_project.id
    with pytest.raises(PermissionError):
        env["ops"].update_work_order(wo, actors["tech_a"])


def test_pm_update_work_order_unnarrowed(env, actors, unassigned_project):
    wo = env["ops"].create_work_order(
        WorkOrder(project_id=unassigned_project.id, title="WO", trade="general"),
        actors["admin"],
    )
    wo.title = "PM edit"
    updated = env["ops"].update_work_order(wo, actors["pm"])
    assert updated.title == "PM edit"


# ==========================================
# deploy_equipment / return_equipment (NEW-644/645)
# ==========================================


_equipment_counter = [0]


def _make_equipment(env, actors):
    _equipment_counter[0] += 1
    return env["ops"].create_equipment(
        Equipment(asset_tag=f"AT-643-{_equipment_counter[0]}", name="Dehumidifier", category="dehumidifier"),
        actors["admin"],
    )


def test_technician_can_deploy_and_return_equipment_to_own_project(env, actors, assigned_project):
    eq = _make_equipment(env, actors)
    deployment = env["ops"].deploy_equipment(eq.id, assigned_project.id, actors["tech_a"])
    assert deployment.project_id == assigned_project.id

    returned = env["ops"].return_equipment(deployment.id, actors["tech_a"])
    assert returned.returned_at is not None


def test_technician_denied_deploy_equipment_to_unassigned_project(env, actors, unassigned_project):
    eq = _make_equipment(env, actors)
    with pytest.raises(PermissionError):
        env["ops"].deploy_equipment(eq.id, unassigned_project.id, actors["tech_a"])

    # No-write guarantee: the equipment must remain AVAILABLE, not DEPLOYED,
    # proving the check ran before the INSERT/UPDATE, not after.
    eq_after = env["ops"].get_equipment(eq.id, actors["admin"])
    assert eq_after.status == EquipmentStatus.AVAILABLE
    assert eq_after.current_project_id is None


def test_technician_denied_return_equipment_for_unassigned_project(env, actors, unassigned_project):
    eq = _make_equipment(env, actors)
    deployment = env["ops"].deploy_equipment(eq.id, unassigned_project.id, actors["admin"])

    with pytest.raises(PermissionError):
        env["ops"].return_equipment(deployment.id, actors["tech_a"])

    # No-write guarantee: the deployment must remain un-returned.
    eq_after = env["ops"].get_equipment(eq.id, actors["admin"])
    assert eq_after.status == EquipmentStatus.DEPLOYED


def test_pm_deploy_and_return_equipment_unnarrowed(env, actors, unassigned_project):
    eq = _make_equipment(env, actors)
    deployment = env["ops"].deploy_equipment(eq.id, unassigned_project.id, actors["pm"])
    assert deployment.project_id == unassigned_project.id
    returned = env["ops"].return_equipment(deployment.id, actors["pm"])
    assert returned.returned_at is not None


# ==========================================
# get_active_work_orders_for_subcontractor (NEW-646)
# ==========================================


def test_technician_active_work_orders_for_subcontractor_filtered_by_ownership(
    env, actors, assigned_project, unassigned_project
):
    sub = env["crm"].create_subcontractor(
        Subcontractor(company_name="Acme Restoration"), actors["admin"]
    )
    own_wo = env["ops"].create_work_order(
        WorkOrder(
            project_id=assigned_project.id, title="Own WO", trade="general",
            assigned_subcontractor_id=sub.id,
        ),
        actors["admin"],
    )
    other_wo = env["ops"].create_work_order(
        WorkOrder(
            project_id=unassigned_project.id, title="Other WO", trade="general",
            assigned_subcontractor_id=sub.id,
        ),
        actors["admin"],
    )

    rows = env["ops"].get_active_work_orders_for_subcontractor(sub.id, actors["tech_a"])
    ids = {r["id"] for r in rows}
    assert own_wo.id in ids
    assert other_wo.id not in ids


def test_technician_active_work_orders_for_subcontractor_empty_when_none_assigned(
    env, actors, unassigned_project
):
    sub = env["crm"].create_subcontractor(
        Subcontractor(company_name="Acme Restoration 2"), actors["admin"]
    )
    env["ops"].create_work_order(
        WorkOrder(
            project_id=unassigned_project.id, title="Other WO", trade="general",
            assigned_subcontractor_id=sub.id,
        ),
        actors["admin"],
    )

    rows = env["ops"].get_active_work_orders_for_subcontractor(sub.id, actors["tech_a"])
    assert rows == []


def test_pm_active_work_orders_for_subcontractor_unnarrowed(env, actors, unassigned_project):
    sub = env["crm"].create_subcontractor(
        Subcontractor(company_name="Acme Restoration 3"), actors["admin"]
    )
    wo = env["ops"].create_work_order(
        WorkOrder(
            project_id=unassigned_project.id, title="Other WO", trade="general",
            assigned_subcontractor_id=sub.id,
        ),
        actors["admin"],
    )
    rows = env["ops"].get_active_work_orders_for_subcontractor(sub.id, actors["pm"])
    ids = {r["id"] for r in rows}
    assert wo.id in ids


def test_subcontractor_delete_precheck_unaffected_by_technician_narrowing(env, actors, unassigned_project):
    """Critical constraint (task item 4): the shared
    `_query_active_work_orders_for_subcontractor` helper, called directly
    (unguarded) by crm_service.py's subcontractor-delete precheck, must
    keep seeing the FULL unfiltered result -- never the narrowed result a
    ROLE_TECHNICIAN actor would get from the public method. This test
    proves both paths coexist correctly on the same fixture data: the
    narrowed public method (called as tech_a, who is NOT assigned to
    unassigned_project) returns [], while delete_subcontractor (an
    admin-gated internal precheck with no actor-narrowing at all) still
    sees the real active work order and refuses the delete."""
    sub = env["crm"].create_subcontractor(
        Subcontractor(company_name="Acme Restoration 4"), actors["admin"]
    )
    wo = env["ops"].create_work_order(
        WorkOrder(
            project_id=unassigned_project.id, title="Blocking WO", trade="general",
            assigned_subcontractor_id=sub.id,
        ),
        actors["admin"],
    )

    # (i) narrowed public method, called as an unassigned technician -> empty
    rows = env["ops"].get_active_work_orders_for_subcontractor(sub.id, actors["tech_a"])
    assert rows == []

    # (ii) the delete precheck (crm_service.py ~L6742) still uses the
    # unfiltered shared helper directly and must still block the delete.
    with pytest.raises(ValueError, match="active work order"):
        env["crm"].delete_subcontractor(sub.id, actors["admin"])


# ==========================================
# create_equipment (NEW-647): flat denial for ROLE_TECHNICIAN
# ==========================================


def test_technician_denied_create_equipment(env, actors):
    """NEW-647: a technician holds PERM_WRITE_OPERATIONS org-wide (passes
    create_equipment's permission gate) but is flatly denied by the
    role-keyed check that follows it -- unlike create_milestone/
    create_work_order/deploy_equipment/return_equipment, there is no
    ownership narrowing here; technicians may never register new
    equipment at all, regardless of project assignment."""
    with pytest.raises(PermissionError, match="cannot register new equipment"):
        env["ops"].create_equipment(
            Equipment(asset_tag="AT-647-TECH", name="Dehumidifier", category="dehumidifier"),
            actors["tech_a"],
        )


def test_technician_denied_create_equipment_regardless_of_project_assignment(env, actors, assigned_project):
    """Confirms the denial is genuinely flat, not accidentally re-using
    the ownership-narrowing pattern -- tech_a is assigned to
    assigned_project, yet create_equipment takes no project_id at all and
    still denies tech_a outright."""
    with pytest.raises(PermissionError, match="cannot register new equipment"):
        env["ops"].create_equipment(
            Equipment(asset_tag="AT-647-TECH-2", name="Air Mover", category="air_mover"),
            actors["tech_a"],
        )


def test_technician_deploy_and_return_equipment_unaffected_by_new647(env, actors, assigned_project):
    """NEW-647 only touches create_equipment -- deploy_equipment/
    return_equipment (already correctly ownership-narrowed by
    NEW-645/NEW-644) remain unaffected for the same tech_a actor."""
    eq = env["ops"].create_equipment(
        Equipment(asset_tag="AT-647-DEPLOY", name="Dehumidifier", category="dehumidifier"),
        actors["admin"],
    )
    deployment = env["ops"].deploy_equipment(eq.id, assigned_project.id, actors["tech_a"])
    assert deployment.project_id == assigned_project.id

    returned = env["ops"].return_equipment(deployment.id, actors["tech_a"])
    assert returned.returned_at is not None


def test_pm_create_equipment_unaffected_by_new647(env, actors):
    eq = env["ops"].create_equipment(
        Equipment(asset_tag="AT-647-PM", name="Dehumidifier", category="dehumidifier"),
        actors["pm"],
    )
    assert eq.id is not None


def test_admin_create_equipment_unaffected_by_new647(env, actors):
    eq = env["ops"].create_equipment(
        Equipment(asset_tag="AT-647-ADMIN", name="Dehumidifier", category="dehumidifier"),
        actors["admin"],
    )
    assert eq.id is not None
