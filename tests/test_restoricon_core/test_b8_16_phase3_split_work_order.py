"""
Unit tests for B8.16 Phase 3 (work-order intake pipeline -- admin split,
2026-09-29; see CODEY_MASTER_PLAN.md's B8.16 entry for full phase
history). Covers:

  - OperationsService.split_work_order: valid 2-way split (line items
    correctly partitioned, each child's total_cost recomputed, children
    sum back to the parent's original total, parent ends
    status=SPLIT/total_cost=0/line_items=[], each child DRAFT or
    DISPATCHED if an assignee was specified).
  - The load-bearing regression: get_project_summary's cost roll-up
    (an unfiltered sum across a project's work orders) is unchanged
    before vs. after a split.
  - Rejections: empty splits, single-entry splits, overlapping line-item
    subsets, an incomplete partition, a nonexistent line-item index,
    a parent not in DRAFT status.
  - RBAC: ROLE_TECHNICIAN and ROLE_SUBCONTRACTOR both rejected
    (PermissionError); ROLE_ADMIN (a real PERM_DISPATCH_WORK_ORDERS
    holder) succeeds.
  - The one invoice for the job (Phase 2's orchestrator shape, created
    directly here) is unaffected by a later split of its work order.
  - Migration: work_orders.status's CHECK constraint widening
    (_migrate_work_orders_status_constraint) against a scratch copy of
    a real pre-Phase-3 schema with existing rows, not just the
    in-memory fresh-schema suite (rule 12) -- data preserved, children
    tables' FK-referencing DDL untouched, PRAGMA foreign_key_check
    clean, idempotent re-run.
"""

import os
import sqlite3

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_SUBCONTRACTOR,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Invoice, Project, Subcontractor, WorkOrder, WorkOrderStatus
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.operations_service import OperationsService

# Same fixture shape as test_b8_16_phase2_intake_orchestrator.py's real
# water-heater job, minus the negative SCF/zero-tax lines (this phase
# splits a plain positive-cost job across two trades instead).
_LINE_ITEMS = [
    {"description": "Drywall patch", "quantity": 2.0, "unit_cost": 100.0, "total_cost": 200.0},
    {"description": "Plumbing fixture", "quantity": 1.0, "unit_cost": 300.0, "total_cost": 300.0},
]


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    ops = OperationsService(db, audit)
    crm = CRMService(db, audit, operations_service=ops)
    admin_user = auth.create_user(
        username="admin", plain_password="Password123", full_name="Admin", email="admin@test.com", role=ROLE_ADMIN,
    )
    admin = AuthContext(user_id=admin_user.id, username="admin", role=ROLE_ADMIN, actor_type="human")
    customer = crm.create_customer(Customer(first_name="Joy", last_name="Clark", email="joy@test.com"), admin)
    project = crm.create_project(Project(customer_id=customer.id, title="Water heater job"), admin)
    return {
        "db": db,
        "auth": auth,
        "audit": audit,
        "ops": ops,
        "crm": crm,
        "admin": admin,
        "customer": customer,
        "project": project,
    }


def _make_actor(env, username, role):
    user = env["auth"].create_user(
        username=username, plain_password="Password123", full_name=username.title(),
        email=f"{username}@test.com", role=role,
    )
    return AuthContext(user_id=user.id, username=username, role=role, actor_type="human")


def _make_parent_work_order(env):
    ops = env["ops"]
    return ops.create_work_order(
        WorkOrder(
            title="Water heater replacement",
            project_id=env["project"].id,
            trade="general",
            line_items=[dict(item) for item in _LINE_ITEMS],
        ),
        env["admin"],
    )


# ==========================================
# Valid split
# ==========================================


def test_valid_two_way_split(env):
    ops = env["ops"]
    parent = _make_parent_work_order(env)
    assert parent.total_cost == 500.0

    result = ops.split_work_order(
        parent.id,
        [
            {"trade": "drywall", "line_item_indices": [0]},
            {"trade": "plumbing", "line_item_indices": [1]},
        ],
        env["admin"],
    )

    parent_after = result["parent"]
    assert parent_after["status"] == WorkOrderStatus.SPLIT
    assert parent_after["total_cost"] == 0.0
    assert parent_after["line_items"] == []

    children = result["children"]
    assert len(children) == 2
    drywall_child = next(c for c in children if c["trade"] == "drywall")
    plumbing_child = next(c for c in children if c["trade"] == "plumbing")
    assert drywall_child["total_cost"] == 200.0
    assert drywall_child["line_items"] == [dict(_LINE_ITEMS[0])]
    assert drywall_child["status"] == WorkOrderStatus.DRAFT
    assert drywall_child["parent_work_order_id"] == parent.id
    assert plumbing_child["total_cost"] == 300.0
    assert plumbing_child["parent_work_order_id"] == parent.id

    # Sum back to the parent's original total.
    assert round(drywall_child["total_cost"] + plumbing_child["total_cost"], 2) == 500.0

    # parent_work_order_id round-trips through get_work_order, not just
    # the object returned by create_work_order/split_work_order itself
    # (NEW-259-shaped regression: the INSERT column list and
    # _row_to_work_order read path are two separate places this field
    # could silently fail to persist).
    fetched_drywall = ops.get_work_order(drywall_child["id"], env["admin"])
    assert fetched_drywall.parent_work_order_id == parent.id
    fetched_parent = ops.get_work_order(parent.id, env["admin"])
    assert fetched_parent.status == WorkOrderStatus.SPLIT
    assert fetched_parent.line_items == []
    assert fetched_parent.total_cost == 0.0


def test_split_with_immediate_subcontractor_assignment(env):
    ops = env["ops"]
    crm = env["crm"]
    parent = _make_parent_work_order(env)
    sub = crm.create_subcontractor(Subcontractor(company_name="Drywall Co", primary_trade="drywall"), env["admin"])

    result = ops.split_work_order(
        parent.id,
        [
            {"trade": "drywall", "line_item_indices": [0], "assigned_subcontractor_id": sub.id},
            {"trade": "plumbing", "line_item_indices": [1]},
        ],
        env["admin"],
    )

    drywall_child = next(c for c in result["children"] if c["trade"] == "drywall")
    plumbing_child = next(c for c in result["children"] if c["trade"] == "plumbing")
    assert drywall_child["status"] == WorkOrderStatus.DISPATCHED
    assert drywall_child["assigned_subcontractor_id"] == sub.id
    assert plumbing_child["status"] == WorkOrderStatus.DRAFT
    assert plumbing_child["assigned_subcontractor_id"] is None


# ==========================================
# The load-bearing regression: project cost roll-up
# ==========================================


def test_project_cost_rollup_unchanged_after_split(env):
    ops = env["ops"]
    parent = _make_parent_work_order(env)

    before = ops.get_project_summary(env["project"].id, env["admin"])
    assert before["work_order_summary"]["total_cost"] == 500.0

    ops.split_work_order(
        parent.id,
        [
            {"trade": "drywall", "line_item_indices": [0]},
            {"trade": "plumbing", "line_item_indices": [1]},
        ],
        env["admin"],
    )

    after = ops.get_project_summary(env["project"].id, env["admin"])
    assert after["work_order_summary"]["total_cost"] == before["work_order_summary"]["total_cost"] == 500.0


# ==========================================
# Rejections
# ==========================================


def test_rejects_empty_splits(env):
    ops = env["ops"]
    parent = _make_parent_work_order(env)
    with pytest.raises(ValueError, match="cannot be empty"):
        ops.split_work_order(parent.id, [], env["admin"])


def test_rejects_single_entry_split(env):
    ops = env["ops"]
    parent = _make_parent_work_order(env)
    with pytest.raises(ValueError, match="not a split"):
        ops.split_work_order(parent.id, [{"trade": "drywall", "line_item_indices": [0, 1]}], env["admin"])


def test_rejects_overlapping_line_item_subsets(env):
    ops = env["ops"]
    parent = _make_parent_work_order(env)
    with pytest.raises(ValueError, match="overlap"):
        ops.split_work_order(
            parent.id,
            [
                {"trade": "drywall", "line_item_indices": [0, 1]},
                {"trade": "plumbing", "line_item_indices": [1]},
            ],
            env["admin"],
        )


def test_rejects_incomplete_partition(env):
    ops = env["ops"]
    # Three line items so one can be left unclaimed by either split entry
    # without tripping the separate "missing non-empty line_item_indices"
    # check first.
    parent = ops.create_work_order(
        WorkOrder(
            title="Three-item job",
            project_id=env["project"].id,
            trade="general",
            line_items=[
                {"description": "A", "quantity": 1.0, "unit_cost": 100.0},
                {"description": "B", "quantity": 1.0, "unit_cost": 200.0},
                {"description": "C", "quantity": 1.0, "unit_cost": 300.0},
            ],
        ),
        env["admin"],
    )
    with pytest.raises(ValueError, match="partition ALL"):
        ops.split_work_order(
            parent.id,
            [
                {"trade": "drywall", "line_item_indices": [0]},
                {"trade": "plumbing", "line_item_indices": [1]},
            ],
            env["admin"],
        )


def test_rejects_nonexistent_line_item_reference(env):
    ops = env["ops"]
    parent = _make_parent_work_order(env)
    with pytest.raises(ValueError, match="does not exist"):
        ops.split_work_order(
            parent.id,
            [
                {"trade": "drywall", "line_item_indices": [0]},
                {"trade": "plumbing", "line_item_indices": [99]},
            ],
            env["admin"],
        )


def test_rejects_non_draft_parent(env):
    ops = env["ops"]
    parent = _make_parent_work_order(env)
    ops.update_work_order_execution_status(parent.id, WorkOrderStatus.CANCELLED, env["admin"])
    with pytest.raises(ValueError, match="must be in 'draft' status"):
        ops.split_work_order(
            parent.id,
            [
                {"trade": "drywall", "line_item_indices": [0]},
                {"trade": "plumbing", "line_item_indices": [1]},
            ],
            env["admin"],
        )


# ==========================================
# RBAC
# ==========================================


def test_technician_cannot_split(env):
    ops = env["ops"]
    parent = _make_parent_work_order(env)
    tech = _make_actor(env, "tech1", ROLE_TECHNICIAN)
    with pytest.raises(PermissionError):
        ops.split_work_order(
            parent.id,
            [
                {"trade": "drywall", "line_item_indices": [0]},
                {"trade": "plumbing", "line_item_indices": [1]},
            ],
            tech,
        )


def test_subcontractor_cannot_split(env):
    ops = env["ops"]
    parent = _make_parent_work_order(env)
    sub_actor = _make_actor(env, "sub1", ROLE_SUBCONTRACTOR)
    with pytest.raises(PermissionError):
        ops.split_work_order(
            parent.id,
            [
                {"trade": "drywall", "line_item_indices": [0]},
                {"trade": "plumbing", "line_item_indices": [1]},
            ],
            sub_actor,
        )


def test_admin_can_split(env):
    ops = env["ops"]
    parent = _make_parent_work_order(env)
    result = ops.split_work_order(
        parent.id,
        [
            {"trade": "drywall", "line_item_indices": [0]},
            {"trade": "plumbing", "line_item_indices": [1]},
        ],
        env["admin"],
    )
    assert len(result["children"]) == 2


# ==========================================
# update_work_order / update_work_order_execution_status SPLIT guards
# ==========================================


def test_execution_status_rejects_setting_split_directly(env):
    ops = env["ops"]
    parent = _make_parent_work_order(env)
    with pytest.raises(ValueError, match="split_work_order"):
        ops.update_work_order_execution_status(parent.id, WorkOrderStatus.SPLIT, env["admin"])


def test_update_work_order_rejects_mutating_a_split_parent(env):
    ops = env["ops"]
    parent = _make_parent_work_order(env)
    ops.split_work_order(
        parent.id,
        [
            {"trade": "drywall", "line_item_indices": [0]},
            {"trade": "plumbing", "line_item_indices": [1]},
        ],
        env["admin"],
    )
    split_parent = ops.get_work_order(parent.id, env["admin"])
    split_parent.notes = "trying to edit a split parent"
    with pytest.raises(ValueError, match="can no longer be updated"):
        ops.update_work_order(split_parent, env["admin"])


def test_unrelated_technician_updating_split_parent_gets_permission_error_not_split_oracle(env):
    """Reviewer-found permission-oracle regression: the SPLIT-immutability
    checks in update_work_order must run AFTER the ROLE_TECHNICIAN
    ownership branch, not before it -- an unrelated technician (not
    assigned to the project at all) probing an arbitrary split-parent id
    must get the pre-existing PermissionError, never this method's
    SPLIT-specific ValueError (which would leak the row's existence and
    split-status to an actor with no relationship to it)."""
    ops = env["ops"]
    parent = _make_parent_work_order(env)
    ops.split_work_order(
        parent.id,
        [
            {"trade": "drywall", "line_item_indices": [0]},
            {"trade": "plumbing", "line_item_indices": [1]},
        ],
        env["admin"],
    )
    # Unrelated technician: not assigned to this (or any) project.
    tech = _make_actor(env, "unrelated_tech", ROLE_TECHNICIAN)
    split_parent = ops.get_work_order(parent.id, env["admin"])
    split_parent.notes = "probing a split parent I have no relationship to"
    with pytest.raises(PermissionError):
        ops.update_work_order(split_parent, tech)


# ==========================================
# Reachable roll-up double-count (subcontractor-existence pre-check)
# ==========================================


def test_split_rejects_nonexistent_subcontractor_before_any_child_created(env):
    """Reviewer-found bug, live-reproduced with a bad
    assigned_subcontractor_id on the 2nd of 3 split entries specifically
    -- NOT the 1st -- because the whole point of the finding is that an
    EARLIER, otherwise-valid entry's child gets created and committed
    before the bad id is ever discovered. Before the fix, entry 0 (valid)
    would create its child, THEN entry 1's dispatch_work_order call would
    raise on the bad id -- by which point entry 0's child already exists
    and the parent has not yet been zeroed (children-first-parent-last is
    deliberate), permanently doubling the project's cost roll-up. The fix
    validates every entry's assigned_subcontractor_id up front, before ANY
    child is created, so this must now reject before entry 0's child ever
    gets created."""
    ops = env["ops"]
    parent = ops.create_work_order(
        WorkOrder(
            title="Three-item job",
            project_id=env["project"].id,
            trade="general",
            line_items=[
                {"description": "Drywall patch", "quantity": 2.0, "unit_cost": 100.0},
                {"description": "Plumbing fixture", "quantity": 1.0, "unit_cost": 300.0},
                {"description": "Electrical fix", "quantity": 1.0, "unit_cost": 150.0},
            ],
        ),
        env["admin"],
    )
    assert parent.total_cost == 650.0

    before = ops.get_project_summary(env["project"].id, env["admin"])
    assert before["work_order_summary"]["total_cost"] == 650.0

    with pytest.raises(ValueError, match="does not exist"):
        ops.split_work_order(
            parent.id,
            [
                {"trade": "drywall", "line_item_indices": [0]},
                {"trade": "plumbing", "line_item_indices": [1], "assigned_subcontractor_id": 999999},
                {"trade": "electrical", "line_item_indices": [2]},
            ],
            env["admin"],
        )

    # No child work order was created for this project -- not even entry
    # 0's (valid, drywall) child, which the pre-fix code would have
    # already committed by the time entry 1's bad id was discovered.
    work_orders = ops.list_work_orders(env["admin"], project_id=env["project"].id)
    assert [wo.id for wo in work_orders] == [parent.id]

    # Parent is untouched -- still DRAFT with its original cost, no
    # doubled roll-up.
    parent_after = ops.get_work_order(parent.id, env["admin"])
    assert parent_after.status == WorkOrderStatus.DRAFT
    assert parent_after.total_cost == 650.0

    after = ops.get_project_summary(env["project"].id, env["admin"])
    assert after["work_order_summary"]["total_cost"] == 650.0


def test_split_rejects_dnc_subcontractor_before_any_child_created(env):
    """NEW-679 round 3 (code-reviewer, 2026-09-29): round 2's fix only
    pre-checked assigned_subcontractor_id's EXISTENCE before the
    children-creation loop -- it did not pre-check
    dispatch_work_order's other rejection reasons (DNC status / expired
    COI / inactive license), so the exact same reachable roll-up
    double-count still fired whenever a split entry named a
    real-but-noncompliant subcontractor. Live-reproduced by the
    reviewer with a real subcontractor on Do-Not-Contact status named
    on the 2nd (not 1st) of two split entries, matching the same
    reachability shape as the existence-check regression test above:
    entry 0 (no assignee) creates its child cleanly, THEN entry 1's
    dispatch_work_order call raises on DNC -- by which point entry 0's
    child already exists and the parent has not yet been zeroed. The
    fix validates DNC/COI/license compliance for every entry's
    assigned_subcontractor_id up front, before ANY child is created, so
    this must now reject before entry 0's child ever gets created."""
    ops = env["ops"]
    crm = env["crm"]
    admin = env["admin"]

    dnc_sub = crm.create_subcontractor(
        Subcontractor(
            company_name="Blacklisted Plumbing Co",
            primary_trade="plumbing",
            service_area="Springfield",
            license_number="LIC-PLB-999",
            license_status="active",
            coi_received=1,
            coi_expiration="2027-12-31",
            msa_signed=1,
            w9_received=1,
            dnc_status=1,
        ),
        admin,
    )

    parent = _make_parent_work_order(env)
    assert parent.total_cost == 500.0

    before = ops.get_project_summary(env["project"].id, admin)
    assert before["work_order_summary"]["total_cost"] == 500.0

    with pytest.raises(ValueError, match="Do-Not-Contact"):
        ops.split_work_order(
            parent.id,
            [
                {"trade": "drywall", "line_item_indices": [0]},
                {
                    "trade": "plumbing",
                    "line_item_indices": [1],
                    "assigned_subcontractor_id": dnc_sub.id,
                },
            ],
            admin,
        )

    # No child work order was created for this project -- not even entry
    # 0's (valid, drywall, no assignee) child, which the pre-fix code
    # would have already committed by the time entry 1's DNC
    # subcontractor was discovered.
    work_orders = ops.list_work_orders(admin, project_id=env["project"].id)
    assert [wo.id for wo in work_orders] == [parent.id]

    # Parent is untouched -- still DRAFT with its original cost, no
    # doubled roll-up.
    parent_after = ops.get_work_order(parent.id, admin)
    assert parent_after.status == WorkOrderStatus.DRAFT
    assert parent_after.total_cost == 500.0

    after = ops.get_project_summary(env["project"].id, admin)
    assert after["work_order_summary"]["total_cost"] == 500.0


# ==========================================
# Concurrency guard on the final parent-zeroing UPDATE
# ==========================================


def test_split_raises_if_parent_already_split_concurrently(env, monkeypatch):
    """Simulates the TOCTOU race: a concurrent call fully completes its
    own split (flipping the parent's status away from 'draft') between
    this call's earlier DRAFT-status validation read and its own final
    parent-zeroing UPDATE. The final UPDATE's `AND status = 'draft'`
    clause must then match zero rows, and the method must raise rather
    than silently succeed with rowcount 0."""
    ops = env["ops"]
    parent = _make_parent_work_order(env)

    real_create_work_order = ops.create_work_order
    calls = {"n": 0}

    def _racing_create_work_order(work_order, actor):
        calls["n"] += 1
        result = real_create_work_order(work_order, actor)
        if calls["n"] == 1:
            # Simulate a concurrent split_work_order call fully completing
            # (its own children created, its own parent-zeroing UPDATE
            # committed) in between this call's validation read and its
            # own final UPDATE below.
            conn = env["db"].get_connection()
            with conn:
                conn.execute(
                    "UPDATE work_orders SET status = 'split', line_items_json = '[]', total_cost = 0.0 WHERE id = ?;",
                    (parent.id,),
                )
        return result

    monkeypatch.setattr(ops, "create_work_order", _racing_create_work_order)

    with pytest.raises(ValueError, match="concurrent"):
        ops.split_work_order(
            parent.id,
            [
                {"trade": "drywall", "line_item_indices": [0]},
                {"trade": "plumbing", "line_item_indices": [1]},
            ],
            env["admin"],
        )


# ==========================================
# Billing unaffected by a split
# ==========================================


def test_invoice_unaffected_by_split(env):
    ops = env["ops"]
    crm = env["crm"]
    parent = _make_parent_work_order(env)

    invoice = crm.create_invoice(
        Invoice(
            customer_id=env["customer"].id,
            project_id=env["project"].id,
            invoice_type="project",
            line_items=[dict(item) for item in _LINE_ITEMS],
        ),
        env["admin"],
    )
    assert invoice.amount == 500.0

    ops.split_work_order(
        parent.id,
        [
            {"trade": "drywall", "line_item_indices": [0]},
            {"trade": "plumbing", "line_item_indices": [1]},
        ],
        env["admin"],
    )

    # Invoice has customer_id/project_id, no work_order_id column
    # (verified directly against models.py) -- completely unaffected by
    # however many work orders the job's labor later gets split into.
    invoice_count = env["db"].get_connection().execute(
        "SELECT COUNT(*) c FROM invoices WHERE project_id = ?;", (env["project"].id,)
    ).fetchone()["c"]
    assert invoice_count == 1

    refetched = crm.get_invoice(invoice.id, env["admin"])
    assert refetched.id == invoice.id
    assert refetched.amount == 500.0
    assert refetched.line_items == invoice.line_items


# ==========================================
# Migration: work_orders.status CHECK constraint widening
# ==========================================


def test_migration_widens_status_check_against_legacy_db_with_data(tmp_path):
    """Builds a scratch DB the same way a real pre-Phase-3 DB file would
    look (full current schema via DatabaseManager, then work_orders
    downgraded -- via the same never-rename-the-real-table procedure the
    production migration itself uses, so child tables' REFERENCES DDL is
    never touched by the downgrade either -- back to its pre-'split'
    CHECK constraint and missing parent_work_order_id column), with a
    real row in work_orders plus real rows in both FK-referencing child
    tables (equipment_deployments, timesheets). Then re-opens it through
    the real DatabaseManager and confirms: the CHECK constraint is
    widened, existing data is preserved, both children's FK-referencing
    DDL still says REFERENCES work_orders(...), PRAGMA foreign_key_check
    is clean, and a second re-open (re-running the migration) is a
    no-op (rule 12: verified directly against a real DB file, not just
    reasoned about against the in-memory fresh-schema suite)."""
    path = str(tmp_path / "legacy_pre_phase3.db")

    db = DatabaseManager(path)
    audit = AuditService(db)
    auth = AuthService(db)
    crm = CRMService(db, audit)
    admin_user = auth.create_user(
        username="admin", plain_password="Password123", full_name="Admin", email="admin@test.com", role=ROLE_ADMIN,
    )
    admin = AuthContext(user_id=admin_user.id, username="admin", role=ROLE_ADMIN, actor_type="human")
    customer = crm.create_customer(Customer(first_name="A", last_name="B", email="legacy@test.com"), admin)
    project = crm.create_project(Project(customer_id=customer.id, title="Legacy Proj", status="planning"), admin)
    db.close()

    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = OFF;")
    conn.executescript(
        """
        CREATE TABLE _work_orders_old_shape (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_order_number TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            project_id INTEGER NOT NULL,
            trade TEXT NOT NULL,
            assigned_subcontractor_id INTEGER,
            assigned_crew_lead TEXT,
            scheduled_start TEXT,
            scheduled_end TEXT,
            actual_start TEXT,
            actual_end TEXT,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'dispatched', 'accepted', 'in_progress', 'completed', 'verified', 'cancelled')),
            line_items_json TEXT NOT NULL DEFAULT '[]',
            total_cost REAL NOT NULL DEFAULT 0.0,
            instructions TEXT,
            notes TEXT,
            dispatched_at TEXT,
            accepted_at TEXT,
            completed_at TEXT,
            verified_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
            FOREIGN KEY (assigned_subcontractor_id) REFERENCES subcontractors(id) ON DELETE SET NULL
        );
        INSERT INTO _work_orders_old_shape (id, work_order_number, title, project_id, trade, assigned_subcontractor_id, assigned_crew_lead, scheduled_start, scheduled_end, actual_start, actual_end, status, line_items_json, total_cost, instructions, notes, dispatched_at, accepted_at, completed_at, verified_at, created_at, updated_at)
        SELECT id, work_order_number, title, project_id, trade, assigned_subcontractor_id, assigned_crew_lead, scheduled_start, scheduled_end, actual_start, actual_end, status, line_items_json, total_cost, instructions, notes, dispatched_at, accepted_at, completed_at, verified_at, created_at, updated_at
        FROM work_orders;
        DROP TABLE work_orders;
        ALTER TABLE _work_orders_old_shape RENAME TO work_orders;
        """
    )
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.commit()

    conn.execute(
        "INSERT INTO work_orders (work_order_number, title, project_id, trade, status, created_at, updated_at) "
        "VALUES ('WO-LEG-1','Legacy WO', ?, 'drywall', 'draft', '2026-01-01', '2026-01-01');",
        (project.id,),
    )
    wo_id = conn.execute("SELECT id FROM work_orders WHERE work_order_number='WO-LEG-1';").fetchone()[0]
    conn.execute(
        "INSERT INTO equipment (id, asset_tag, name, category, created_at, updated_at) "
        "VALUES (1, 'EQ-1', 'Dehu', 'dehumidifier', '2026-01-01', '2026-01-01');"
    )
    conn.execute(
        "INSERT INTO equipment_deployments (equipment_id, project_id, work_order_id, deployed_at, created_at, updated_at) "
        "VALUES (1, ?, ?, '2026-01-01', '2026-01-01', '2026-01-01');",
        (project.id, wo_id),
    )
    conn.execute(
        "INSERT INTO employees (id, first_name, last_name, role_title, department, created_at, updated_at) "
        "VALUES (1, 'Emp', '1', 'Tech', 'field_technician', '2026-01-01', '2026-01-01');"
    )
    conn.execute(
        "INSERT INTO timesheets (employee_id, work_order_id, work_date, hours_worked, created_at) "
        "VALUES (1, ?, '2026-01-01', 8.0, '2026-01-01');",
        (wo_id,),
    )
    conn.commit()
    conn.close()

    # Sanity: confirm the pre-migration DB really is pre-Phase-3 shaped
    # (no parent_work_order_id column, CHECK constraint has no 'split').
    pre_conn = sqlite3.connect(path)
    pre_conn.row_factory = sqlite3.Row
    pre_cols = {r["name"] for r in pre_conn.execute("PRAGMA table_info(work_orders);")}
    assert "parent_work_order_id" not in pre_cols
    pre_ddl = pre_conn.execute("SELECT sql FROM sqlite_master WHERE name='work_orders';").fetchone()["sql"]
    assert "'split'" not in pre_ddl
    pre_conn.close()

    # Re-open through the real DatabaseManager -- this is what actually
    # runs _migrate_schema() -> _migrate_work_orders_status_constraint().
    db2 = DatabaseManager(path)
    conn2 = db2.get_connection()

    ddl = conn2.execute("SELECT sql FROM sqlite_master WHERE name='work_orders';").fetchone()["sql"]
    assert "'split'" in ddl

    cols = {r["name"] for r in conn2.execute("PRAGMA table_info(work_orders);")}
    assert "parent_work_order_id" in cols

    row = conn2.execute("SELECT * FROM work_orders WHERE work_order_number='WO-LEG-1';").fetchone()
    assert row["id"] == wo_id
    assert row["status"] == "draft"
    assert row["parent_work_order_id"] is None

    for child_table in ("equipment_deployments", "timesheets"):
        child_ddl = conn2.execute(
            "SELECT sql FROM sqlite_master WHERE name=?;", (child_table,)
        ).fetchone()["sql"]
        assert "REFERENCES work_orders" in child_ddl

    assert conn2.execute(
        "SELECT work_order_id FROM equipment_deployments WHERE work_order_id = ?;", (wo_id,)
    ).fetchone()["work_order_id"] == wo_id
    assert conn2.execute(
        "SELECT work_order_id FROM timesheets WHERE work_order_id = ?;", (wo_id,)
    ).fetchone()["work_order_id"] == wo_id

    assert conn2.execute("PRAGMA foreign_key_check;").fetchall() == []

    # A new row can now use the widened 'split' value.
    conn2.execute(
        "INSERT INTO work_orders (work_order_number, title, project_id, trade, status, created_at, updated_at) "
        "VALUES ('WO-LEG-2', 'T2', ?, 'drywall', 'split', '2026-01-01', '2026-01-01');",
        (project.id,),
    )
    conn2.commit()

    db2.close()

    # Idempotent re-open: no error, row count unchanged.
    db3 = DatabaseManager(path)
    conn3 = db3.get_connection()
    count = conn3.execute("SELECT COUNT(*) c FROM work_orders;").fetchone()["c"]
    assert count == 2
    db3.close()
