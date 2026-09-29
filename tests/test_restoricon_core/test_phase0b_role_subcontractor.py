"""
Unit tests for Phase 0b (B8.16 work-order intake pipeline): ROLE_SUBCONTRACTOR
as a real RBAC role, not a stand-in (NEW-641 resolved).

Covers:
  - ALL_ROLES / create_user accepting role="subcontractor" (previously
    raised ValueError since the role didn't exist).
  - ROLE_PERMISSIONS[ROLE_SUBCONTRACTOR]'s exact permission subset --
    included permissions present, explicitly excluded ones absent.
  - AuthContext.subcontractor_id populated correctly by
    AuthService.authenticate_token for a user with users.subcontractor_id
    set via AuthService.update_user (create_user has no parameter for it,
    same convention as territory_id -- update_user's allowed_fields is the
    one supported way to populate it, see auth.py).
  - operations_service.py's create_work_order/update_work_order/
    list_work_orders/get_work_order row-level narrowing to
    assigned_subcontractor_id == actor.subcontractor_id.
"""

import pytest

from restoricon_core.auth import (
    ALL_ROLES,
    AuthContext,
    AuthService,
    PERM_DISPATCH_WORK_ORDERS,
    PERM_MANAGE_PROJECTS,
    PERM_READ_COMPLIANCE,
    PERM_READ_DOCUMENTS,
    PERM_READ_HR,
    PERM_READ_OPERATIONS,
    PERM_WRITE_CUSTOMERS,
    PERM_WRITE_DOCUMENTS,
    PERM_WRITE_FINANCIALS,
    PERM_WRITE_HR,
    PERM_WRITE_OPERATIONS,
    PERM_LOG_COMMUNICATION,
    ROLE_ADMIN,
    ROLE_PERMISSIONS,
    ROLE_SUBCONTRACTOR,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Project, ProjectStage, Subcontractor, WorkOrder
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


# ==========================================
# Role registration / permission set
# ==========================================


def test_role_subcontractor_is_a_real_role():
    assert ROLE_SUBCONTRACTOR == "subcontractor"
    assert ROLE_SUBCONTRACTOR in ALL_ROLES


def test_create_user_with_role_subcontractor_succeeds(env):
    user = env["auth"].create_user(
        username="sub_user",
        plain_password="Password123",
        full_name="Sub Contractor",
        email="sub_user@test.com",
        role=ROLE_SUBCONTRACTOR,
    )
    assert user.id is not None
    assert user.role == ROLE_SUBCONTRACTOR


def test_role_subcontractor_permission_set_included(env):
    perms = ROLE_PERMISSIONS[ROLE_SUBCONTRACTOR]
    assert PERM_READ_OPERATIONS in perms
    assert PERM_WRITE_OPERATIONS in perms
    assert PERM_LOG_COMMUNICATION in perms


def test_role_subcontractor_permission_set_excludes_employee_and_privileged_perms():
    perms = ROLE_PERMISSIONS[ROLE_SUBCONTRACTOR]
    assert PERM_READ_HR not in perms
    assert PERM_WRITE_HR not in perms
    assert PERM_DISPATCH_WORK_ORDERS not in perms
    assert PERM_MANAGE_PROJECTS not in perms
    assert PERM_WRITE_CUSTOMERS not in perms
    assert PERM_WRITE_FINANCIALS not in perms
    # C2 fix (code-reviewer, 2026-09-27, NEW-668): PERM_READ_COMPLIANCE was
    # removed from this role's grant -- BusinessOpsService.list_compliance_items
    # has zero entity-level narrowing, so holding it would leak every other
    # party's license/insurance/COI records to an external subcontractor.
    assert PERM_READ_COMPLIANCE not in perms
    # Round-2 fix (code-reviewer, 2026-09-27, NEW-669): PERM_READ_DOCUMENTS/
    # PERM_WRITE_DOCUMENTS were removed from this role's grant -- get_document/
    # list_documents only narrow when the actor lacks PERM_READ_DOCUMENTS, and
    # create_document has no role/entity check at all, so holding either would
    # expose or let a subcontractor create documents under any customer/project.
    assert PERM_READ_DOCUMENTS not in perms
    assert PERM_WRITE_DOCUMENTS not in perms


# ==========================================
# AuthContext.subcontractor_id population
# ==========================================


def test_update_user_sets_subcontractor_id(env):
    """create_user has no subcontractor_id parameter (same convention as
    territory_id) -- update_user's allowed_fields is the one supported way
    to populate it, gated on PERM_MANAGE_USERS like every other field it
    accepts."""
    admin = env["auth"].create_user("admin_upd_0b", "Pass123!", "Admin", "admin_upd_0b@test.com", role=ROLE_ADMIN)
    admin_ctx = AuthContext(admin.id, admin.username, ROLE_ADMIN, "human")

    user = env["auth"].create_user(
        username="sub_update_user",
        plain_password="Password123",
        full_name="Sub Contractor",
        email="sub_update_user@test.com",
        role=ROLE_SUBCONTRACTOR,
    )
    updated, role_changed = env["auth"].update_user(user.id, {"subcontractor_id": 7}, admin_ctx)
    assert role_changed is False
    assert updated.subcontractor_id == 7


def test_authenticate_token_populates_subcontractor_id(env):
    admin = env["auth"].create_user("admin_tok_0b", "Pass123!", "Admin", "admin_tok_0b@test.com", role=ROLE_ADMIN)
    admin_ctx = AuthContext(admin.id, admin.username, ROLE_ADMIN, "human")

    user = env["auth"].create_user(
        username="sub_token_user",
        plain_password="Password123",
        full_name="Sub Contractor",
        email="sub_token_user@test.com",
        role=ROLE_SUBCONTRACTOR,
    )
    env["auth"].update_user(user.id, {"subcontractor_id": 42}, admin_ctx)
    user = env["auth"].get_user_by_id(user.id)

    token = env["auth"].create_token(user)
    ctx = env["auth"].authenticate_token(token)
    assert ctx is not None
    assert ctx.role == ROLE_SUBCONTRACTOR
    assert ctx.subcontractor_id == 42


def test_authenticate_token_subcontractor_id_none_for_unset_user(env):
    user = env["auth"].create_user(
        username="sub_unset_user",
        plain_password="Password123",
        full_name="Sub Contractor",
        email="sub_unset_user@test.com",
        role=ROLE_SUBCONTRACTOR,
    )
    token = env["auth"].create_token(user)
    ctx = env["auth"].authenticate_token(token)
    assert ctx is not None
    assert ctx.subcontractor_id is None


# ==========================================
# operations_service.py row-scoping
# ==========================================


@pytest.fixture
def actors(env):
    auth = env["auth"]
    u_admin = auth.create_user("admin_0b", "Pass123!", "Admin", "admin_0b@test.com", role=ROLE_ADMIN)
    ctx_admin = AuthContext(u_admin.id, u_admin.username, ROLE_ADMIN, "human")

    u_sub_a = auth.create_user("sub_a_0b", "Pass123!", "Sub A", "sub_a_0b@test.com", role=ROLE_SUBCONTRACTOR)
    ctx_sub_a = AuthContext(u_sub_a.id, u_sub_a.username, ROLE_SUBCONTRACTOR, "human", subcontractor_id=1)

    u_sub_b = auth.create_user("sub_b_0b", "Pass123!", "Sub B", "sub_b_0b@test.com", role=ROLE_SUBCONTRACTOR)
    ctx_sub_b = AuthContext(u_sub_b.id, u_sub_b.username, ROLE_SUBCONTRACTOR, "human", subcontractor_id=2)

    # A subcontractor-role actor whose own subcontractor_id was never set --
    # must never match any work order, including one with no subcontractor
    # assigned (assigned_subcontractor_id IS NULL).
    u_sub_unset = auth.create_user(
        "sub_unset_0b", "Pass123!", "Sub Unset", "sub_unset_0b@test.com", role=ROLE_SUBCONTRACTOR
    )
    ctx_sub_unset = AuthContext(u_sub_unset.id, u_sub_unset.username, ROLE_SUBCONTRACTOR, "human")

    return {
        "admin": ctx_admin,
        "sub_a": ctx_sub_a,
        "sub_b": ctx_sub_b,
        "sub_unset": ctx_sub_unset,
    }


@pytest.fixture
def customer(env, actors):
    from restoricon_core.models import Customer

    return env["crm"].create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane_0b@example.com"),
        actors["admin"],
    )


@pytest.fixture
def project(env, actors, customer):
    return env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Sub-scoped job",
            property_address="10 Elm St",
            project_type="water_damage",
            stage=ProjectStage.INTAKE,
        ),
        actors["admin"],
    )


@pytest.fixture
def sub_a_id(env, actors):
    # subcontractor_id=1 in the actors fixture above must correspond to a
    # real `subcontractors` row for this fixture's own realism (not
    # required by the RBAC check itself, which only compares ids).
    sub = env["crm"].create_subcontractor(Subcontractor(company_name="Sub A Co"), actors["admin"])
    return sub.id


def test_subcontractor_can_create_work_order_assigned_to_self(env, actors, project, sub_a_id):
    ctx = AuthContext(
        actors["sub_a"].user_id, actors["sub_a"].username, ROLE_SUBCONTRACTOR, "human",
        subcontractor_id=sub_a_id,
    )
    wo = env["ops"].create_work_order(
        WorkOrder(project_id=project.id, title="WO", trade="general", assigned_subcontractor_id=sub_a_id),
        ctx,
    )
    assert wo.id is not None
    assert wo.assigned_subcontractor_id == sub_a_id


def test_subcontractor_denied_create_work_order_assigned_to_other_subcontractor(env, actors, project, sub_a_id):
    # An id guaranteed distinct from sub_a_id (a real subcontractors.id),
    # rather than relying on the actors fixture's fixed subcontractor_id
    # coincidentally differing from whatever id gets assigned.
    other_ctx = AuthContext(
        actors["sub_b"].user_id, actors["sub_b"].username, ROLE_SUBCONTRACTOR, "human",
        subcontractor_id=sub_a_id + 1000,
    )
    with pytest.raises(PermissionError):
        env["ops"].create_work_order(
            WorkOrder(project_id=project.id, title="WO", trade="general", assigned_subcontractor_id=sub_a_id),
            other_ctx,
        )


def test_subcontractor_denied_create_work_order_with_no_subcontractor_assigned(env, project, actors):
    with pytest.raises(PermissionError):
        env["ops"].create_work_order(
            WorkOrder(project_id=project.id, title="WO", trade="general"),
            actors["sub_a"],
        )


def test_subcontractor_unset_id_denied_even_for_unassigned_work_order(env, project, actors):
    """A subcontractor actor with no subcontractor_id of their own must
    never match a work order with assigned_subcontractor_id IS NULL --
    both are None, and a naive equality check without a None-guard would
    incorrectly treat that as a match."""
    with pytest.raises(PermissionError):
        env["ops"].create_work_order(
            WorkOrder(project_id=project.id, title="WO", trade="general"),
            actors["sub_unset"],
        )


def test_subcontractor_can_update_own_work_order(env, actors, project, sub_a_id):
    ctx_a = AuthContext(
        actors["sub_a"].user_id, actors["sub_a"].username, ROLE_SUBCONTRACTOR, "human",
        subcontractor_id=sub_a_id,
    )
    wo = env["ops"].create_work_order(
        WorkOrder(project_id=project.id, title="WO", trade="general", assigned_subcontractor_id=sub_a_id),
        actors["admin"],
    )
    wo.title = "Updated by sub"
    updated = env["ops"].update_work_order(wo, ctx_a)
    assert updated.title == "Updated by sub"


def test_subcontractor_denied_reassigning_own_work_order_to_other_subcontractor(env, actors, project, sub_a_id):
    """C1 (code-reviewer, 2026-09-27): a subcontractor who genuinely owns a
    work order must not be able to reassign it to a different
    subcontractor's id -- that would hand the other subcontractor read/write
    access to it, which is PERM_DISPATCH_WORK_ORDERS behavior this role's
    grant explicitly excludes. Unlike
    test_subcontractor_update_uses_db_assigned_subcontractor_id_not_model
    (which covers a WO the actor never owned in the first place, tripping
    the ownership pre-check), this exercises the actual reassignment-of-an-
    owned-WO path: the actor genuinely owns the WO at call time and only
    the target id is spoofed."""
    other_sub = env["crm"].create_subcontractor(Subcontractor(company_name="Other Sub Co"), actors["admin"])
    wo = env["ops"].create_work_order(
        WorkOrder(project_id=project.id, title="WO", trade="general", assigned_subcontractor_id=sub_a_id),
        actors["admin"],
    )
    ctx_a = AuthContext(
        actors["sub_a"].user_id, actors["sub_a"].username, ROLE_SUBCONTRACTOR, "human",
        subcontractor_id=sub_a_id,
    )
    wo.assigned_subcontractor_id = other_sub.id
    with pytest.raises(PermissionError):
        env["ops"].update_work_order(wo, ctx_a)

    # Confirm the guard fires before any write -- the row must still be
    # assigned to sub_a_id, not silently reassigned.
    unchanged = env["ops"].get_work_order(wo.id, actors["admin"])
    assert unchanged.assigned_subcontractor_id == sub_a_id


def test_subcontractor_denied_update_other_subcontractor_work_order(env, actors, project, sub_a_id):
    wo = env["ops"].create_work_order(
        WorkOrder(project_id=project.id, title="WO", trade="general", assigned_subcontractor_id=sub_a_id),
        actors["admin"],
    )
    wo.title = "Should not stick"
    other_ctx = AuthContext(
        actors["sub_b"].user_id, actors["sub_b"].username, ROLE_SUBCONTRACTOR, "human",
        subcontractor_id=sub_a_id + 1000,
    )
    with pytest.raises(PermissionError):
        env["ops"].update_work_order(wo, other_ctx)


def test_subcontractor_update_uses_db_assigned_subcontractor_id_not_model(env, actors, project, sub_a_id):
    """Mirrors NEW-643's discipline for ROLE_TECHNICIAN: ownership must be
    checked against the CURRENT DB row, never a caller-supplied (possibly
    spoofed) model field."""
    wo = env["ops"].create_work_order(
        WorkOrder(project_id=project.id, title="WO", trade="general", assigned_subcontractor_id=sub_a_id),
        actors["admin"],
    )
    ctx_b = AuthContext(
        actors["sub_b"].user_id, actors["sub_b"].username, ROLE_SUBCONTRACTOR, "human",
        subcontractor_id=999,
    )
    wo.assigned_subcontractor_id = 999  # spoofed -- DB row still says sub_a_id
    with pytest.raises(PermissionError):
        env["ops"].update_work_order(wo, ctx_b)


def test_subcontractor_list_work_orders_scoped_to_own(env, actors, project, sub_a_id):
    env["ops"].create_work_order(
        WorkOrder(project_id=project.id, title="Own WO", trade="general", assigned_subcontractor_id=sub_a_id),
        actors["admin"],
    )
    other_sub = env["crm"].create_subcontractor(Subcontractor(company_name="Other Sub Co"), actors["admin"])
    env["ops"].create_work_order(
        WorkOrder(project_id=project.id, title="Other WO", trade="general", assigned_subcontractor_id=other_sub.id),
        actors["admin"],
    )

    ctx_a = AuthContext(
        actors["sub_a"].user_id, actors["sub_a"].username, ROLE_SUBCONTRACTOR, "human",
        subcontractor_id=sub_a_id,
    )
    rows = env["ops"].list_work_orders(ctx_a)
    titles = {r.title for r in rows}
    assert titles == {"Own WO"}


def test_subcontractor_get_work_order_denied_for_other_subcontractor(env, actors, project, sub_a_id):
    wo = env["ops"].create_work_order(
        WorkOrder(project_id=project.id, title="WO", trade="general", assigned_subcontractor_id=sub_a_id),
        actors["admin"],
    )
    other_ctx = AuthContext(
        actors["sub_b"].user_id, actors["sub_b"].username, ROLE_SUBCONTRACTOR, "human",
        subcontractor_id=sub_a_id + 1000,
    )
    with pytest.raises(PermissionError):
        env["ops"].get_work_order(wo.id, other_ctx)


def test_admin_unaffected_by_subcontractor_narrowing(env, actors, project, sub_a_id):
    wo = env["ops"].create_work_order(
        WorkOrder(project_id=project.id, title="WO", trade="general", assigned_subcontractor_id=sub_a_id),
        actors["admin"],
    )
    fetched = env["ops"].get_work_order(wo.id, actors["admin"])
    assert fetched.id == wo.id
