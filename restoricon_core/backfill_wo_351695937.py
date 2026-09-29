"""
One-off backfill script: Joy Clark's real, already-completed, already-paid
service call (work order #351695937, water heater replacement) entered
directly into restoricon_core via the service layer.

B8.16 Phase 5 (CODEY_MASTER_PLAN.md's B8.16 entry has the full phase
history -- Phase 0-slim/1 line-items + server-computed amount, Phase 0b
ROLE_SUBCONTRACTOR, Phase 2 submit_work_order_intake orchestrator, Phase 3
admin split, Phase 4 intake form UI). This is the original, motivating
request behind the whole B8.16 effort.

Why NOT submit_work_order_intake (Phase 2/4's own pipeline)
-------------------------------------------------------------
submit_work_order_intake's terminus is a DRAFT, unassigned work order and a
'draft' invoice awaiting admin dispatch -- states this job has already
passed through (it happened and was paid in the real world before this
script was written). This script instead calls
CRMService.create_customer/create_project, OperationsService.
create_work_order, CRMService.create_invoice/record_payment directly, with
every object set to its real, final, completed/paid state from the start.

AuthContext bootstrap
----------------------
Mirrors migrate_aigentik.py's build_migration_actor() pattern (see that
module's "AuthContext bootstrap" docstring section for the full
rationale: offline script, never network-reachable, one identical actor
object needed for both dry-run and --apply).

One deliberate difference from migrate_aigentik.py: that script's actor
uses user_id=None, safe there because the only place it's read is
audit_log.actor_id (a nullable FK). record_payment additionally writes
`recorded_by_user_id: actor.user_id` into the invoice's own payments_json
blob for a real $790 payment -- a None operator on that money-path field
is a materially different thing from a None audit-log actor on migration
metadata. So this script's actor uses user_id=1, matching the SAME
established "system actor" id this codebase already hardcodes for
exactly this class of internal/elevated action (intake_system_actor,
commission_system_actor, pdf_system_actor -- all user_id=1, see NEW-602
for the known FK-fragility of that convention). Verified directly
(read-only query) that users.id == 1 is a real, existing row in the live
DB (~/.codeyOS/restoricon.db) before relying on it here.

Idempotency
------------
Single gate: if a work order whose `notes` field already contains the
marker line "Original work order number: 351695937" exists, the entire
backfill is treated as already done and no further writes are attempted
(customer/project/work-order/invoice/payment are all created in one
straight-line sequence by this script, in that order, so nothing else
needs its own independent check). Customer/project lookups additionally
reuse an existing row if one is found by email / customer_id+address --
not because a second run is expected, but so a partial prior run (e.g.
a customer created, then the process interrupted before the work order)
can be resumed without duplicating the customer.

Work order numbering
----------------------
Does NOT hardcode "WO-351695937" as work_order_number. Read directly
(rule 12): OperationsService.generate_work_order_number() derives the
NEXT sequential number from the newest existing row's own trailing
digits (`work_orders.work_order_number` ORDER BY id DESC LIMIT 1). A
hand-set "WO-351695937" landing as the newest row would poison every
future auto-generated number on the live DB (the regex would parse
351695937 as the counter and increment from there). This script lets
generate_work_order_number() assign the real next sequential number and
carries the historical number as a labeled "Original work order number:
351695937" line in `notes` instead (Phase 2's own established
fold-into-notes pattern for fields with no dedicated column).

Portfolio-override commission interaction (checked, not just assumed)
------------------------------------------------------------------------
record_payment's flat-commission trigger (B8.7a, widened to invoice_type
'project' in Phase 2) checks portfolio-override eligibility first and
skips the flat commission if eligible (Ish's NEW-673 decision,
2026-09-27: override wins, no stacking). Read
_resolve_portfolio_override_eligibility's gate 1b directly: it requires a
SIGNED Contract row linking to the invoice's project_id. This script
creates a brand-new Project with no Contract ever attached to it, so gate
1b's `contract_rows` query is unconditionally empty and eligibility
always resolves to `eligible=False, skip_reason='contract_link_missing'`
-- there is no live-data path by which this specific invoice could ever
be portfolio-override eligible, regardless of Joy Clark's or Mike
Regina's real history elsewhere in the DB. So the flat commission fires
normally; exactly one commission_ledger_entries row is expected after
record_payment. Mike Regina holds ROLE_ADMIN in the live DB -- verified
directly (read-only query) that neither record_payment's trigger nor
CommissionService.record_commission has ANY role-keyed special case for
the rep_user_id being an admin; a ROLE_ADMIN-attributed commission is
recorded identically to any other role.

Live execution
---------------
This script has NOT been run against the real database
(~/.codeyOS/restoricon.db). It is tested against an isolated in-memory
DB only (see
tests/test_restoricon_core/test_b8_16_phase5_wo_351695937_backfill.py).
Per this project's rule 2 (RAM discipline) / general real-data caution,
actually executing --apply against the live DB path is live-verifier's
job, not this implementer's.

Usage
-----
    python -m restoricon_core.backfill_wo_351695937                # dry run
    python -m restoricon_core.backfill_wo_351695937 --apply         # writes
    python -m restoricon_core.backfill_wo_351695937 --db-path PATH
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, Optional

from .auth import AuthContext, ROLE_ADMIN
from .database import DatabaseManager
from .models import Customer, Invoice, Project, ProjectStage, WorkOrder, WorkOrderStatus
from .services.audit_service import AuditService
from .services.commission_service import CommissionService
from .services.crm_service import CRMService
from .services.operations_service import OperationsService

# The historical, real work order number from the source document --
# never used as the DB's own work_order_number (see module docstring's
# "Work order numbering" section). Also this script's idempotency marker.
ORIGINAL_WORK_ORDER_NUMBER = "351695937"
_WO_MARKER_LINE = f"Original work order number: {ORIGINAL_WORK_ORDER_NUMBER}"

CUSTOMER_FIRST_NAME = "Joy"
CUSTOMER_LAST_NAME = "Clark"
CUSTOMER_SERVICE_ADDRESS = "31 High St Apt 5303, East Hartford, CT 06118"
CUSTOMER_PHONE = "8609859469"
CUSTOMER_EMAIL = "godblesschild58@gmail.com"

MIKE_REGINA_USERNAME = "mike.regina"
MIKE_REGINA_FULL_NAME = "Mike Regina"

# Same shape as WorkOrder.line_items/Invoice.line_items elsewhere in this
# codebase ({"description", "quantity", "unit_cost", "total_cost"}) --
# total_cost is recomputed server-side by both create_work_order and
# create_invoice, never trusted from here. Sums to $790.00 (verified by
# the accompanying test, not just arithmetic by inspection).
LINE_ITEMS = [
    {"description": "Labor Charge", "quantity": 4.0, "unit_cost": 55.0, "total_cost": 220.0},
    {"description": "rheem XE30S06ST45U1", "quantity": 1.0, "unit_cost": 530.0, "total_cost": 530.0},
    {"description": "water supply line hoses", "quantity": 1.0, "unit_cost": 70.0, "total_cost": 70.0},
    {"description": "3/4\" copper", "quantity": 1.0, "unit_cost": 25.0, "total_cost": 25.0},
    {"description": "pex pipe 10' 1/2\"", "quantity": 1.0, "unit_cost": 10.0, "total_cost": 10.0},
    {"description": "pex 90 elbow 1/2\"", "quantity": 1.0, "unit_cost": 2.0, "total_cost": 2.0},
    {"description": "male 3/4\" to 1/2\" pex connector", "quantity": 1.0, "unit_cost": 8.0, "total_cost": 8.0},
    {"description": "Service Call Fee (SCF) credit", "quantity": 1.0, "unit_cost": -75.0, "total_cost": -75.0},
    {"description": "Tax", "quantity": 1.0, "unit_cost": 0.0, "total_cost": 0.0},
]

# Diagnostic/appliance-report fields with no dedicated WorkOrder column --
# folded into notes as labeled lines, mirroring Phase 2's own
# submit_work_order_intake fold-in pattern exactly (crm_service.py's
# `notes_lines` assembly in that method).
DIAGNOSTIC_NOTE_LINES = [
    "Diagnostic type: Tank - Electric",
    "Issue: Leaking water (Unknown how long)",
    "Last time working: 09/24/2026",
    "Age/install date: 2/2/2018",
    "Cause: the anode has never been replaced, which has caused corrosion to form and crack",
    "Failure: Replacement recommended - tank is leaking from bottom base plate, tank has crack",
    "Fuel: Electric",
    "Leaks: Yes, located in laundry closet",
    "Make: Rheem",
    "Model: XE30S06ST45U1",
    "Needs: Replace unit",
    "Rust or Corrosion: Rusted, light, at base plate",
    "Serial: A061803443",
    "Size: 30 gallon, Low Boy type",
    "Supplies: entire (unit)",
    "Units: 1",
    "Appointment: 09/26/2026, 3:00 PM-8:00 PM, type Diagnosis, "
    "technician Mike Regina (860) 807-5479, At Home: Yes, logged 09/26/2026 02:43 PM",
]

APPOINTMENT_START = "2026-09-26T15:00:00"
APPOINTMENT_END = "2026-09-26T20:00:00"

PAYMENT_AMOUNT = 790.00
PAYMENT_METHOD = "card"
PAYMENT_REFERENCE = f"HISTORICAL-BACKFILL-WO-{ORIGINAL_WORK_ORDER_NUMBER}"


def build_backfill_actor() -> AuthContext:
    """Hand-constructed AuthContext for this offline script, mirroring
    migrate_aigentik.py's build_migration_actor(). See the module
    docstring's "AuthContext bootstrap" section for why user_id=1 (not
    None, unlike migrate_aigentik.py) is used here."""
    return AuthContext(
        user_id=1,
        username="backfill_wo_351695937",
        role=ROLE_ADMIN,
        actor_type="agent",
        customer_id=None,
        token=None,
    )


def find_mike_regina_user_id(db_manager: DatabaseManager) -> int:
    """Look up Mike Regina's real user id directly -- never hardcoded
    (rule 12). Tries username first (the stable, unique identifier),
    falls back to full_name. Raises if not found or inactive rather than
    silently attributing this job's sale/commission to a wrong id."""
    conn = db_manager.get_connection()
    row = conn.execute(
        "SELECT id, active FROM users WHERE username = ?;", (MIKE_REGINA_USERNAME,)
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT id, active FROM users WHERE full_name = ?;", (MIKE_REGINA_FULL_NAME,)
        ).fetchone()
    if row is None:
        raise RuntimeError(
            f"Could not find a user with username='{MIKE_REGINA_USERNAME}' or "
            f"full_name='{MIKE_REGINA_FULL_NAME}' -- refusing to guess an id."
        )
    if not row["active"]:
        raise RuntimeError(f"User id {row['id']} (Mike Regina) is not active.")
    return row["id"]


def _find_existing_backfill_work_order(db_manager: DatabaseManager) -> Optional[Dict[str, Any]]:
    """Idempotency gate: a work order whose notes already carry this
    script's marker line means the whole backfill already ran."""
    conn = db_manager.get_connection()
    row = conn.execute(
        "SELECT id, work_order_number, project_id FROM work_orders WHERE notes LIKE ?;",
        (f"%{_WO_MARKER_LINE}%",),
    ).fetchone()
    if row is None:
        return None
    return {"id": row["id"], "work_order_number": row["work_order_number"], "project_id": row["project_id"]}


def run_backfill(db_manager: DatabaseManager, apply: bool) -> Dict[str, Any]:
    """Run the backfill (dry-run unless apply=True) and return a
    structured report. Never performs a write unless ``apply`` is True."""
    actor = build_backfill_actor()
    audit = AuditService(db_manager)
    commission = CommissionService(db_manager, audit)
    operations = OperationsService(db_manager, audit)
    crm = CRMService(db_manager, audit, operations_service=operations, commission_service=commission)

    mike_regina_id = find_mike_regina_user_id(db_manager)

    existing = _find_existing_backfill_work_order(db_manager)
    if existing is not None:
        return {
            "already_backfilled": True,
            "existing_work_order_id": existing["id"],
            "existing_work_order_number": existing["work_order_number"],
            "existing_project_id": existing["project_id"],
            "mike_regina_user_id": mike_regina_id,
        }

    report: Dict[str, Any] = {
        "already_backfilled": False,
        "mike_regina_user_id": mike_regina_id,
        "mode": "apply" if apply else "dry_run",
    }

    if not apply:
        report["would_create"] = {
            "customer": {
                "first_name": CUSTOMER_FIRST_NAME,
                "last_name": CUSTOMER_LAST_NAME,
                "email": CUSTOMER_EMAIL,
                "phone": CUSTOMER_PHONE,
                "service_address": CUSTOMER_SERVICE_ADDRESS,
            },
            "project": {"stage": ProjectStage.BILLED, "status": "completed"},
            "work_order": {"trade": "plumbing", "status": WorkOrderStatus.COMPLETED},
            "invoice": {"invoice_type": "project", "assigned_user_id": mike_regina_id},
            "payment": {"amount": PAYMENT_AMOUNT},
        }
        return report

    # --- customer: find-or-create by email, mirroring Phase 2's dedup
    # philosophy (never blindly duplicate) ---
    existing_customer = crm.get_customer_by_email(CUSTOMER_EMAIL, actor)
    if existing_customer is not None:
        customer_id = existing_customer.id
        report["customer_created"] = False
    else:
        new_customer = Customer(
            first_name=CUSTOMER_FIRST_NAME,
            last_name=CUSTOMER_LAST_NAME,
            phone=CUSTOMER_PHONE,
            email=CUSTOMER_EMAIL,
            service_address=CUSTOMER_SERVICE_ADDRESS,
            customer_type="residential",
            customer_source="historical_backfill",
            assigned_user_id=mike_regina_id,
        )
        created_customer = crm.create_customer(new_customer, actor)
        customer_id = created_customer.id
        report["customer_created"] = True
    report["customer_id"] = customer_id

    # --- project: find-or-create by customer_id + property_address,
    # mirroring _find_or_create_intake_project's own key exactly ---
    conn = db_manager.get_connection()
    project_row = conn.execute(
        "SELECT id FROM projects WHERE customer_id = ? AND property_address = ?;",
        (customer_id, CUSTOMER_SERVICE_ADDRESS),
    ).fetchone()
    if project_row is not None:
        project_id = project_row["id"]
        report["project_created"] = False
    else:
        new_project = Project(
            customer_id=customer_id,
            title=f"Water Heater Replacement - WO {ORIGINAL_WORK_ORDER_NUMBER}",
            property_address=CUSTOMER_SERVICE_ADDRESS,
            project_type="repair",
            status="completed",
            stage=ProjectStage.BILLED,
            actual_completion=APPOINTMENT_END,
        )
        created_project = crm.create_project(new_project, actor)
        project_id = created_project.id
        report["project_created"] = True
    report["project_id"] = project_id

    # --- work order: created COMPLETED, crew-lead-attributed to Mike
    # Regina, diagnostic details folded into notes ---
    notes_lines = [_WO_MARKER_LINE] + DIAGNOSTIC_NOTE_LINES
    new_work_order = WorkOrder(
        title=f"Water Heater Replacement - WO {ORIGINAL_WORK_ORDER_NUMBER}",
        project_id=project_id,
        trade="plumbing",
        assigned_crew_lead=MIKE_REGINA_FULL_NAME,
        scheduled_start=APPOINTMENT_START,
        scheduled_end=APPOINTMENT_END,
        actual_start=APPOINTMENT_START,
        actual_end=APPOINTMENT_END,
        status=WorkOrderStatus.COMPLETED,
        line_items=[dict(item) for item in LINE_ITEMS],
        notes="\n".join(notes_lines),
        dispatched_at=APPOINTMENT_START,
        accepted_at=APPOINTMENT_START,
        completed_at=APPOINTMENT_END,
    )
    created_work_order = operations.create_work_order(new_work_order, actor)
    report["work_order_id"] = created_work_order.id
    report["work_order_number"] = created_work_order.work_order_number
    report["work_order_total_cost"] = created_work_order.total_cost

    # --- invoice: invoice_type='project' (Ish's explicit decision --
    # NOT 'assessment', see module docstring / task spec), assigned_user_id
    # explicitly set to Mike Regina (this is what actually drives commission
    # attribution -- see record_payment's flat-commission trigger). amount
    # is server-computed from line_items, never passed explicitly. ---
    new_invoice = Invoice(
        customer_id=customer_id,
        project_id=project_id,
        invoice_type="project",
        line_items=[dict(item) for item in LINE_ITEMS],
        assigned_user_id=mike_regina_id,
    )
    created_invoice = crm.create_invoice(new_invoice, actor)
    report["invoice_id"] = created_invoice.id
    report["invoice_number"] = created_invoice.invoice_number
    report["invoice_amount"] = created_invoice.amount

    # --- payment: full payment, one shot, marks the invoice paid and
    # fires the commission trigger (see module docstring for the
    # portfolio-override-eligibility analysis backing the "exactly one
    # commission_ledger row" expectation). ---
    paid_invoice = crm.record_payment(
        created_invoice.id,
        PAYMENT_AMOUNT,
        PAYMENT_METHOD,
        PAYMENT_REFERENCE,
        actor,
        payment_type="installment",
    )
    report["invoice_status_after_payment"] = paid_invoice.status
    report["invoice_balance_due_after_payment"] = paid_invoice.balance_due

    commission_entries = commission.list_commissions(actor, rep_user_id=mike_regina_id)
    report["commission_entries_for_mike_regina"] = len(commission_entries)

    return report


def print_report(report: Dict[str, Any]) -> None:
    print("=== Joy Clark / WO-351695937 backfill report ===")
    for key, value in report.items():
        print(f"  {key}: {value}")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill Joy Clark's real, completed/paid WO #351695937 into restoricon_core."
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to restoricon_core's SQLite DB (default: restoricon_core.database.DEFAULT_DB_PATH)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to the database. Without this flag, the script only reports what it would do.",
    )
    args = parser.parse_args(argv)

    db_manager = (
        DatabaseManager(args.db_path, init_schema=False)
        if args.db_path
        else DatabaseManager(init_schema=False)
    )
    report = run_backfill(db_manager, args.apply)
    print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
