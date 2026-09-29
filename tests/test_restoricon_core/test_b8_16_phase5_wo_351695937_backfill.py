"""
Unit tests for B8.16 Phase 5 (restoricon_core/backfill_wo_351695937.py --
Joy Clark's real, already-completed/paid water heater replacement,
work order #351695937, backfilled directly via the service layer, not
submit_work_order_intake's DRAFT-terminus pipeline). See
CODEY_MASTER_PLAN.md's B8.16 entry and the script's own module docstring
for the full phase history and design rationale.

Run against an isolated in-memory DB only -- this script has NOT been run
against the real live DB (~/.codeyOS/restoricon.db); that is a separate
live-verifier pass.
"""

import pytest

from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import ProjectStage, WorkOrderStatus
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.commission_service import CommissionService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.operations_service import OperationsService

from restoricon_core.backfill_wo_351695937 import (
    CUSTOMER_EMAIL,
    CUSTOMER_SERVICE_ADDRESS,
    LINE_ITEMS,
    MIKE_REGINA_USERNAME,
    ORIGINAL_WORK_ORDER_NUMBER,
    PAYMENT_AMOUNT,
    find_mike_regina_user_id,
    run_backfill,
)


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    commission = CommissionService(db, audit)
    ops = OperationsService(db, audit)
    crm = CRMService(db, audit, operations_service=ops, commission_service=commission)
    # System actor (user_id=1 in build_backfill_actor()) must correspond
    # to a REAL row for record_commission's created_by FK, mirroring the
    # live DB's own users.id == 1 row (verified directly before writing
    # this script). Created first so it lands id == 1.
    auth.create_user(
        username="ai_agent_system", plain_password="Password123",
        full_name="Codey Aigentik", email="system@test.com", role=ROLE_ADMIN,
    )
    mike = auth.create_user(
        username=MIKE_REGINA_USERNAME, plain_password="Password123",
        full_name="Mike Regina", email="mike.regina@restoricon.com", role=ROLE_ADMIN,
    )
    admin = AuthContext(user_id=1, username="ai_agent_system", role=ROLE_ADMIN, actor_type="agent")
    return {"db": db, "auth": auth, "audit": audit, "commission": commission,
            "ops": ops, "crm": crm, "admin": admin, "mike": mike}


def test_find_mike_regina_user_id(env):
    assert find_mike_regina_user_id(env["db"]) == env["mike"].id


def test_find_mike_regina_user_id_raises_when_not_found():
    db = DatabaseManager(":memory:")
    AuthService(db)
    with pytest.raises(RuntimeError):
        find_mike_regina_user_id(db)


def test_dry_run_makes_no_writes(env):
    db = env["db"]
    report = run_backfill(db, apply=False)
    assert report["mode"] == "dry_run"
    assert report["already_backfilled"] is False

    conn = db.get_connection()
    assert conn.execute("SELECT COUNT(*) c FROM customers;").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM projects;").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM work_orders;").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM invoices;").fetchone()["c"] == 0


def test_apply_full_pipeline(env):
    db = env["db"]
    crm = env["crm"]
    ops = env["ops"]
    commission = env["commission"]
    admin = env["admin"]
    mike_id = env["mike"].id

    report = run_backfill(db, apply=True)

    assert report["already_backfilled"] is False
    assert report["mike_regina_user_id"] == mike_id
    assert report["customer_created"] is True
    assert report["project_created"] is True

    # --- customer ---
    customer = crm.get_customer(report["customer_id"], admin)
    assert customer.first_name == "Joy"
    assert customer.last_name == "Clark"
    assert customer.email == CUSTOMER_EMAIL
    assert customer.phone == "8609859469"
    assert customer.service_address == CUSTOMER_SERVICE_ADDRESS
    assert customer.customer_type == "residential"

    # --- project ---
    project = crm.get_project(report["project_id"], admin)
    assert project.stage == ProjectStage.BILLED
    assert project.status == "completed"
    assert project.customer_id == customer.id

    # --- work order ---
    work_order = ops.get_work_order(report["work_order_id"], admin)
    assert work_order.trade == "plumbing"
    assert work_order.status == WorkOrderStatus.COMPLETED
    assert work_order.assigned_crew_lead == "Mike Regina"
    assert work_order.project_id == project.id
    assert f"Original work order number: {ORIGINAL_WORK_ORDER_NUMBER}" in work_order.notes
    assert "Model: XE30S06ST45U1" in work_order.notes
    assert "XE30S06ST4501" not in work_order.notes
    # work_order_number is server-generated, NOT the historical number
    # (see module docstring's "Work order numbering" section).
    assert work_order.work_order_number != f"WO-{ORIGINAL_WORK_ORDER_NUMBER}"
    assert work_order.work_order_number.startswith("WO-")
    assert len(work_order.line_items) == len(LINE_ITEMS)
    assert work_order.total_cost == 790.00

    # --- invoice ---
    invoice = crm.get_invoice(report["invoice_id"], admin)
    assert invoice.invoice_type == "project"
    assert invoice.assigned_user_id == mike_id
    assert invoice.amount == 790.00
    assert len(invoice.line_items) == len(LINE_ITEMS)

    # --- payment / commission ---
    assert invoice.status == "paid"
    assert invoice.balance_due == 0.0

    entries = commission.list_commissions(admin, rep_user_id=mike_id)
    assert len(entries) == 1
    assert entries[0].source_id == invoice.id
    assert entries[0].status == "earned"


def test_second_apply_run_is_idempotent_no_op(env):
    db = env["db"]
    crm = env["crm"]
    commission = env["commission"]
    admin = env["admin"]
    mike_id = env["mike"].id

    first = run_backfill(db, apply=True)
    second = run_backfill(db, apply=True)

    assert second["already_backfilled"] is True
    assert second["existing_work_order_id"] == first["work_order_id"]

    conn = db.get_connection()
    assert conn.execute("SELECT COUNT(*) c FROM customers;").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM projects;").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM work_orders;").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM invoices;").fetchone()["c"] == 1

    entries = commission.list_commissions(admin, rep_user_id=mike_id)
    assert len(entries) == 1


def test_negative_scf_line_item_nets_correctly(env):
    """The -$75 Service Call Fee credit line must net into the $790 total,
    not be rejected or clamped -- server-computed sum, not client-trusted."""
    db = env["db"]
    crm = env["crm"]

    report = run_backfill(db, apply=True)
    invoice = crm.get_invoice(report["invoice_id"], env["admin"])

    scf_item = next(i for i in invoice.line_items if "Service Call Fee" in i["description"])
    assert scf_item["total_cost"] == -75.0
    assert invoice.amount == 790.00
