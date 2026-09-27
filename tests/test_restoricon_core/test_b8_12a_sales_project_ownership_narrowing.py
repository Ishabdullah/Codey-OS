"""
Unit tests for B8.12a: ROLE_SALES project/operations RBAC narrowing.

Removes PERM_READ_ALL_PROJECTS/PERM_READ_OPERATIONS from ROLE_SALES (both
flat, company-wide over-grants with zero per-row ownership check anywhere
in crm_service.py/operations_service.py -- NEW-628) and replaces them with
PERM_READ_OWN_SOLD_PROJECTS, narrowed via a matching `contracts` row
(Contract.assigned_user_id == actor.user_id for Contract.project_id ==
the project). An unclaimed contract (assigned_user_id IS NULL) is denied,
not treated as visible -- deliberately different from the leads/
opportunities unclaimed-pool leniency. ROLE_SALES_MANAGER (holds
PERM_READ_TEAM_SALES_DATA) must keep full, unnarrowed project/work-order
visibility via that bypass. Equipment/deployment visibility specifically
was NOT covered by this round's PERM_READ_TEAM_SALES_DATA bypass and was
logged as NEW-630 -- briefly resolved (2026-09-25, dd244d5) by re-granting
PERM_READ_OPERATIONS itself to ROLE_SALES_MANAGER in auth.py, then
reversed (2026-09-27, direct Ish decision): a sales manager should not
get equipment/deployment visibility after all. See
test_ops_sales_manager_loses_equipment_visibility_new630 below.
"""

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_MANAGE_PROJECTS,
    PERM_READ_OPERATIONS,
    PERM_READ_OWN_PROJECTS,
    PERM_READ_OWN_SOLD_PROJECTS,
    PERM_WRITE_OPERATIONS,
    PERM_WRITE_PROJECTS,
    ROLE_ADMIN,
    ROLE_SALES,
    ROLE_SALES_MANAGER,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Contract, Customer, Project, ProjectStage, WorkOrder
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
        "crm": crm_service,
        "ops": ops_service,
        "router": router,
    }


@pytest.fixture
def actors(env):
    auth = env["auth"]
    u_admin = auth.create_user("admin_u", "Pass123!", "Admin", "admin_b812@test.com", role=ROLE_ADMIN)
    ctx_admin = AuthContext(u_admin.id, u_admin.username, ROLE_ADMIN, "human")

    u_rep_a = auth.create_user("rep_a_b812", "Pass123!", "Rep A", "repa_b812@test.com", role=ROLE_SALES)
    ctx_rep_a = AuthContext(u_rep_a.id, u_rep_a.username, ROLE_SALES, "human")

    u_rep_b = auth.create_user("rep_b_b812", "Pass123!", "Rep B", "repb_b812@test.com", role=ROLE_SALES)
    ctx_rep_b = AuthContext(u_rep_b.id, u_rep_b.username, ROLE_SALES, "human")

    u_mgr = auth.create_user("mgr_b812", "Pass123!", "Sales Mgr", "mgr_b812@test.com", role=ROLE_SALES_MANAGER)
    ctx_mgr = AuthContext(u_mgr.id, u_mgr.username, ROLE_SALES_MANAGER, "human")

    return {
        "admin": ctx_admin,
        "rep_a": ctx_rep_a,
        "rep_b": ctx_rep_b,
        "manager": ctx_mgr,
    }


@pytest.fixture
def customer(env, actors):
    return env["crm"].create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane_b812@example.com"),
        actors["admin"],
    )


@pytest.fixture
def sold_project(env, actors, customer):
    """A project sold by rep_a: rep_a's own Contract row references it."""
    proj = env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Rep A's job",
            property_address="1 Elm St",
            project_type="water_damage",
            stage=ProjectStage.INTAKE,
        ),
        actors["admin"],
    )
    env["crm"].create_contract(
        Contract(contract_number="CTR-B812-A", customer_id=customer.id, project_id=proj.id, title="Contract A", content="..."),
        actors["rep_a"],
    )
    return proj


@pytest.fixture
def other_rep_project(env, actors, customer):
    """A project sold by rep_b -- rep_a must not see this."""
    proj = env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Rep B's job",
            property_address="2 Elm St",
            project_type="fire_damage",
            stage=ProjectStage.INTAKE,
        ),
        actors["admin"],
    )
    env["crm"].create_contract(
        Contract(contract_number="CTR-B812-B", customer_id=customer.id, project_id=proj.id, title="Contract B", content="..."),
        actors["rep_b"],
    )
    return proj


@pytest.fixture
def unclaimed_project(env, actors, customer):
    """A project with a Contract row whose assigned_user_id has been
    cleared to NULL -- must be DENIED to a plain rep, fail-closed, not
    treated as an unclaimed-pool row visible to everyone (deliberately
    different from the leads/opportunities convention)."""
    proj = env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Nobody's job",
            property_address="3 Elm St",
            project_type="mold",
            stage=ProjectStage.INTAKE,
        ),
        actors["admin"],
    )
    contract = env["crm"].create_contract(
        Contract(contract_number="CTR-B812-C", customer_id=customer.id, project_id=proj.id, title="Contract C", content="..."),
        actors["admin"],
    )
    conn = env["db"].get_connection()
    with conn:
        conn.execute("UPDATE contracts SET assigned_user_id = NULL WHERE id = ?;", (contract.id,))
    return proj


@pytest.fixture
def contractless_project(env, actors, customer):
    """A project with NO contract row at all -- distinct denial case from
    unclaimed_project (contract exists but assigned_user_id IS NULL)."""
    return env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="No contract yet",
            property_address="4 Elm St",
            project_type="water_damage",
            stage=ProjectStage.INTAKE,
        ),
        actors["admin"],
    )


# ==========================================
# crm_service.py: get_project / list_projects
# ==========================================


def test_rep_sees_own_sold_project(env, actors, sold_project):
    proj = env["crm"].get_project(sold_project.id, actors["rep_a"])
    assert proj is not None
    assert proj.id == sold_project.id


def test_rep_denied_another_reps_project(env, actors, other_rep_project):
    with pytest.raises(PermissionError):
        env["crm"].get_project(other_rep_project.id, actors["rep_a"])


def test_rep_denied_unclaimed_contract_project(env, actors, unclaimed_project):
    """NULL assigned_user_id on the matching contract is DENIED, not
    treated as an unclaimed-pool row visible to a plain rep."""
    with pytest.raises(PermissionError):
        env["crm"].get_project(unclaimed_project.id, actors["rep_a"])


def test_rep_denied_contractless_project(env, actors, contractless_project):
    """A project with no contract row at all is also denied (distinct
    from the unclaimed-contract case, both must fail closed)."""
    with pytest.raises(PermissionError):
        env["crm"].get_project(contractless_project.id, actors["rep_a"])


def test_list_projects_filters_to_own_sold_only(env, actors, sold_project, other_rep_project, unclaimed_project):
    rows = env["crm"].list_projects(actors["rep_a"])
    ids = {p.id for p in rows}
    assert sold_project.id in ids
    assert other_rep_project.id not in ids
    assert unclaimed_project.id not in ids


def test_list_projects_customer_360_shape_returns_own_sold_project(env, actors, customer, sold_project, other_rep_project):
    """Regression check for the Customer 360 Projects panel's exact call
    shape (`GET /api/v1/projects?customer_id=X` -> list_projects(actor,
    customer_id=X)) -- a rep viewing a customer they sold a job to must
    still see that project after the narrowing."""
    rows = env["crm"].list_projects(actors["rep_a"], customer_id=customer.id)
    ids = {p.id for p in rows}
    assert sold_project.id in ids
    assert other_rep_project.id not in ids


def test_sales_manager_sees_all_projects_via_crm_service(env, actors, sold_project, other_rep_project, unclaimed_project, contractless_project):
    """ROLE_SALES_MANAGER (PERM_READ_TEAM_SALES_DATA) keeps full,
    unfiltered visibility -- zero additional grant beyond the derived
    ROLE_SALES permission set."""
    rows = env["crm"].list_projects(actors["manager"])
    ids = {p.id for p in rows}
    assert sold_project.id in ids
    assert other_rep_project.id in ids
    assert unclaimed_project.id in ids
    assert contractless_project.id in ids

    proj = env["crm"].get_project(other_rep_project.id, actors["manager"])
    assert proj is not None


def test_rep_write_project_still_denied_preexisting_behavior(env, actors, sold_project):
    """Regression: ROLE_SALES never held PERM_WRITE_PROJECTS before this
    round either -- confirming update_project stays denied, not a new
    behavior introduced by B8.12a."""
    with pytest.raises(PermissionError):
        env["crm"].update_project(sold_project.id, {"title": "Hacked"}, actors["rep_a"])
    assert not actors["rep_a"].has_permission(PERM_WRITE_PROJECTS)


# ==========================================
# operations_service.py: get_project / get_project_summary /
# get_milestone / list_milestones / get_work_order / list_work_orders
# ==========================================


def test_ops_get_project_rep_sees_own_sold_project(env, actors, sold_project):
    proj = env["ops"].get_project(sold_project.id, actors["rep_a"])
    assert proj is not None


def test_ops_get_project_rep_denied_other_reps_project(env, actors, other_rep_project):
    with pytest.raises(PermissionError):
        env["ops"].get_project(other_rep_project.id, actors["rep_a"])


def test_ops_get_project_rep_denied_unclaimed_contract(env, actors, unclaimed_project):
    with pytest.raises(PermissionError):
        env["ops"].get_project(unclaimed_project.id, actors["rep_a"])


def test_ops_sales_manager_sees_all_via_operations_service(env, actors, sold_project, other_rep_project):
    """The derived-permission no-op specifically for operations_service.py
    -- this is where losing PERM_READ_OPERATIONS would actually bite a
    manager if the PERM_READ_TEAM_SALES_DATA bypass were missing."""
    proj = env["ops"].get_project(other_rep_project.id, actors["manager"])
    assert proj is not None


def _make_milestone_and_work_order(env, actors, project):
    from restoricon_core.models import ProjectMilestone

    milestone = env["ops"].create_milestone(
        ProjectMilestone(project_id=project.id, name="Demo"),
        actors["admin"],
    )
    work_order = env["ops"].create_work_order(
        WorkOrder(project_id=project.id, title="WO 1", trade="general"),
        actors["admin"],
    )
    return milestone, work_order


def test_ops_get_milestone_and_work_order_rep_owned_vs_denied(env, actors, sold_project, other_rep_project):
    own_milestone, own_wo = _make_milestone_and_work_order(env, actors, sold_project)
    other_milestone, other_wo = _make_milestone_and_work_order(env, actors, other_rep_project)

    assert env["ops"].get_milestone(own_milestone.id, actors["rep_a"]) is not None
    with pytest.raises(PermissionError):
        env["ops"].get_milestone(other_milestone.id, actors["rep_a"])

    assert env["ops"].get_work_order(own_wo.id, actors["rep_a"]) is not None
    with pytest.raises(PermissionError):
        env["ops"].get_work_order(other_wo.id, actors["rep_a"])


def test_ops_list_milestones_denied_for_other_reps_project(env, actors, other_rep_project):
    with pytest.raises(PermissionError):
        env["ops"].list_milestones(other_rep_project.id, actors["rep_a"])


def test_ops_list_work_orders_project_id_none_only_returns_own_sold(env, actors, sold_project, other_rep_project):
    """No project_id filter given -- the subquery must still keep the
    result to the rep's own sold projects' work orders, not leak
    everything (this is the path a missing subquery would silently leak
    through)."""
    _, own_wo = _make_milestone_and_work_order(env, actors, sold_project)
    _, other_wo = _make_milestone_and_work_order(env, actors, other_rep_project)

    rows = env["ops"].list_work_orders(actors["rep_a"])
    ids = {wo.id for wo in rows}
    assert own_wo.id in ids
    assert other_wo.id not in ids


def test_ops_write_operations_still_denied_preexisting_behavior(env, actors, sold_project):
    """Regression: ROLE_SALES never held PERM_WRITE_OPERATIONS/
    PERM_MANAGE_PROJECTS before this round -- confirm still denied."""
    assert not actors["rep_a"].has_permission(PERM_WRITE_OPERATIONS)
    assert not actors["rep_a"].has_permission(PERM_MANAGE_PROJECTS)
    with pytest.raises(PermissionError):
        env["ops"].transition_project_stage(sold_project.id, ProjectStage.ASSESSMENT_SCOPING, actors["rep_a"])


def test_ops_equipment_and_deployment_routes_denied_for_rep(env, actors, sold_project):
    """Equipment/deployment visibility is deliberately NOT part of
    PERM_READ_OWN_SOLD_PROJECTS -- these become correctly denied once
    PERM_READ_OPERATIONS is removed from ROLE_SALES, the intended outcome
    of this round, not a gap."""
    assert not actors["rep_a"].has_permission(PERM_READ_OPERATIONS)
    with pytest.raises(PermissionError):
        env["ops"].list_equipment(actors["rep_a"])
    with pytest.raises(PermissionError):
        env["ops"].list_project_deployments(sold_project.id, actors["rep_a"])


def test_ops_get_project_summary_works_for_rep_with_null_equipment_summary(env, actors, sold_project):
    """B8.12a's one intended new read for a rep -- status/stage/work
    orders/milestones in one call. equipment_summary must be None (not a
    fabricated zero) since the rep has no equipment visibility."""
    summary = env["ops"].get_project_summary(sold_project.id, actors["rep_a"])
    assert summary["project"]["id"] == sold_project.id
    assert summary["equipment_summary"] is None
    assert "milestone_summary" in summary
    assert "work_order_summary" in summary


def test_ops_get_project_summary_denied_for_other_reps_project(env, actors, other_rep_project):
    """get_project_summary's own get_project() call raises PermissionError
    for a project the rep didn't sell -- this propagates unchanged (not
    get_project_summary's separate ValueError, which is reserved for a
    genuinely nonexistent project_id)."""
    with pytest.raises(PermissionError):
        env["ops"].get_project_summary(other_rep_project.id, actors["rep_a"])


def test_ops_get_project_summary_admin_still_has_equipment_summary(env, actors, sold_project):
    """Confirm the equipment_summary guard doesn't regress an actor who
    genuinely holds PERM_READ_OPERATIONS/PERM_MANAGE_PROJECTS."""
    summary = env["ops"].get_project_summary(sold_project.id, actors["admin"])
    assert summary["equipment_summary"] is not None
    assert summary["equipment_summary"]["active_deployed_count"] == 0


def test_ops_sales_manager_loses_equipment_visibility_new630(env, actors, other_rep_project):
    """NEW-630 (reversed 2026-09-27, direct Ish decision -- previously
    granted 2026-09-25 via dd244d5, now undone): ROLE_SALES_MANAGER's
    derived-permissions union never re-adds PERM_READ_OPERATIONS itself
    (only the narrower PERM_READ_OWN_SOLD_PROJECTS, via the ROLE_SALES
    union), so a manager loses equipment/deployment visibility identically
    to a plain rep -- this is a real, tested side effect of this round,
    not an assumption. get_project/list_work_orders/etc. stay fully
    unnarrowed for a manager (see test_ops_sales_manager_sees_all_via_operations_service);
    equipment specifically does not."""
    assert not actors["manager"].has_permission(PERM_READ_OPERATIONS)
    with pytest.raises(PermissionError):
        env["ops"].list_equipment(actors["manager"])
    with pytest.raises(PermissionError):
        env["ops"].list_project_deployments(other_rep_project.id, actors["manager"])

    summary = env["ops"].get_project_summary(other_rep_project.id, actors["manager"])
    assert summary["equipment_summary"] is None


def test_get_project_bypass_exempts_own_projects_permission_too(env, actors, other_rep_project):
    """code-reviewer finding (B8.12a round 1): _actor_lacks_sold_project_ownership's
    first draft only exempted PERM_READ_ALL_PROJECTS/PERM_READ_TEAM_SALES_DATA
    from the ownership filter, not the two other independent entitlements
    (PERM_READ_ASSIGNED_PROJECTS/PERM_READ_OWN_PROJECTS) get_project's own
    outer gate already accepts -- so a hypothetical actor holding both
    PERM_READ_OWN_SOLD_PROJECTS and PERM_READ_OWN_PROJECTS (only reachable
    via a custom_permissions_json grant, no built-in role combines them
    today) would have been narrowed BELOW what PERM_READ_OWN_PROJECTS alone
    already grants -- contradicting the helper's own "narrowed identically"
    docstring claim. Fixed inline before commit; this proves it."""
    # rep_b is a plain ROLE_SALES actor (holds PERM_READ_OWN_SOLD_PROJECTS
    # by role default) with an ADDITIONAL custom grant of
    # PERM_READ_OWN_PROJECTS -- simulating the hypothetical custom_permissions_json
    # combination the reviewer flagged as latent, not live via any built-in role.
    ctx = AuthContext(
        actors["rep_b"].user_id,
        actors["rep_b"].username,
        ROLE_SALES,
        "human",
        custom_permissions={PERM_READ_OWN_PROJECTS: True},
    )
    # other_rep_project belongs to rep_a, not rep_b -- before the fix this
    # would have raised PermissionError (over-narrowed); after the fix the
    # PERM_READ_OWN_PROJECTS grant exempts the actor from the ownership
    # filter, matching what that permission alone would have granted.
    project = env["crm"].get_project(other_rep_project.id, ctx)
    assert project is not None
    assert project.id == other_rep_project.id
