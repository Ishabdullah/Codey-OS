"""
Operations Business Service for Restoricon Core.
Orchestrates Project Lifecycle & Milestone State Machine, Work Orders & Line Items,
Subcontractor Matching & Dispatching, and Equipment Tracking with RBAC enforcement
and automated audit logging.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set

from ..auth import (
    AuthContext,
    PERM_DISPATCH_WORK_ORDERS,
    PERM_MANAGE_PROJECTS,
    PERM_READ_OPERATIONS,
    PERM_READ_OWN_SOLD_PROJECTS,
    PERM_READ_SUBCONTRACTORS,
    PERM_READ_TEAM_SALES_DATA,
    PERM_WRITE_OPERATIONS,
    ROLE_CUSTOMER,
    ROLE_TECHNICIAN,
)
from ..database import DatabaseManager
from ..models import (
    Equipment,
    EquipmentDeployment,
    EquipmentStatus,
    MilestoneStatus,
    Project,
    ProjectMilestone,
    ProjectStage,
    WorkOrder,
    WorkOrderStatus,
    utc_now_iso,
)
from .audit_service import (
    AuditService,
    build_audit_details,
    _AUDITABLE_DEPLOYMENT_FIELDS,
    _AUDITABLE_EQUIPMENT_FIELDS,
    _AUDITABLE_MILESTONE_FIELDS,
    _AUDITABLE_PROJECT_FIELDS,
    _AUDITABLE_WORK_ORDER_FIELDS,
)
from .finance_service import FinanceService


class OperationsService:
    """Core domain operations engine for Restoricon Core."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        audit_service: AuditService,
        finance_service: Optional[FinanceService] = None,
    ):
        self.db = db_manager
        self.audit = audit_service
        # NEW-613: lazily default-constructed only when not supplied, same
        # pattern as CRMService's `operations_service or OperationsService(
        # self.db, audit_service)` (crm_service.py:198). Only used by
        # transition_project_stage's CLOSED-stage gate below
        # (FinanceService.get_project_ar_net, an internal read-only,
        # no-actor helper -- see its own docstring), so a fallback instance
        # built with this same audit_service is harmless.
        self.finance_service = finance_service or FinanceService(db_manager, audit_service)

    # ==========================================
    # ROW CONVERTERS
    # ==========================================

    @staticmethod
    def _row_to_milestone(row: Any) -> ProjectMilestone:
        keys = row.keys() if hasattr(row, "keys") else []
        dependencies = json.loads(row["dependencies_json"]) if "dependencies_json" in keys and row["dependencies_json"] else []
        return ProjectMilestone(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            stage=ProjectStage.normalize(row["stage"]) if "stage" in keys else ProjectStage.INTAKE,
            target_date=row["target_date"] if "target_date" in keys else None,
            completion_date=row["completion_date"] if "completion_date" in keys else None,
            status=row["status"],
            dependencies=dependencies,
            notes=row["notes"] if "notes" in keys else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_work_order(row: Any) -> WorkOrder:
        keys = row.keys() if hasattr(row, "keys") else []
        line_items = json.loads(row["line_items_json"]) if "line_items_json" in keys and row["line_items_json"] else []
        return WorkOrder(
            id=row["id"],
            work_order_number=row["work_order_number"],
            title=row["title"],
            project_id=row["project_id"],
            trade=row["trade"],
            assigned_subcontractor_id=row["assigned_subcontractor_id"] if "assigned_subcontractor_id" in keys else None,
            assigned_crew_lead=row["assigned_crew_lead"] if "assigned_crew_lead" in keys else None,
            scheduled_start=row["scheduled_start"] if "scheduled_start" in keys else None,
            scheduled_end=row["scheduled_end"] if "scheduled_end" in keys else None,
            actual_start=row["actual_start"] if "actual_start" in keys else None,
            actual_end=row["actual_end"] if "actual_end" in keys else None,
            status=row["status"],
            line_items=line_items,
            total_cost=row["total_cost"] if "total_cost" in keys else 0.0,
            instructions=row["instructions"] if "instructions" in keys else None,
            notes=row["notes"] if "notes" in keys else None,
            dispatched_at=row["dispatched_at"] if "dispatched_at" in keys else None,
            accepted_at=row["accepted_at"] if "accepted_at" in keys else None,
            completed_at=row["completed_at"] if "completed_at" in keys else None,
            verified_at=row["verified_at"] if "verified_at" in keys else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_equipment(row: Any) -> Equipment:
        keys = row.keys() if hasattr(row, "keys") else []
        return Equipment(
            id=row["id"],
            asset_tag=row["asset_tag"],
            name=row["name"],
            category=row["category"],
            model_number=row["model_number"] if "model_number" in keys else None,
            serial_number=row["serial_number"] if "serial_number" in keys else None,
            status=row["status"],
            daily_rate=row["daily_rate"] if "daily_rate" in keys else 0.0,
            current_project_id=row["current_project_id"] if "current_project_id" in keys else None,
            notes=row["notes"] if "notes" in keys else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_equipment_deployment(row: Any) -> EquipmentDeployment:
        keys = row.keys() if hasattr(row, "keys") else []
        return EquipmentDeployment(
            id=row["id"],
            equipment_id=row["equipment_id"],
            project_id=row["project_id"],
            work_order_id=row["work_order_id"] if "work_order_id" in keys else None,
            deployed_at=row["deployed_at"],
            return_due_at=row["return_due_at"] if "return_due_at" in keys else None,
            returned_at=row["returned_at"] if "returned_at" in keys else None,
            deployed_by_user_id=row["deployed_by_user_id"] if "deployed_by_user_id" in keys else None,
            received_by_user_id=row["received_by_user_id"] if "received_by_user_id" in keys else None,
            condition_out=row["condition_out"] if "condition_out" in keys else "good",
            condition_in=row["condition_in"] if "condition_in" in keys else None,
            initial_reading=row["initial_reading"] if "initial_reading" in keys else None,
            final_reading=row["final_reading"] if "final_reading" in keys else None,
            notes=row["notes"] if "notes" in keys else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_project(row: Any, actor_role: str = "") -> Project:
        keys = row.keys() if hasattr(row, "keys") else []
        assigned_employees = json.loads(row["assigned_employees_json"]) if "assigned_employees_json" in keys and row["assigned_employees_json"] else []
        subcontractors = json.loads(row["subcontractors_json"]) if "subcontractors_json" in keys and row["subcontractors_json"] else []
        is_customer = actor_role == ROLE_CUSTOMER

        return Project(
            id=row["id"],
            customer_id=row["customer_id"],
            title=row["title"],
            property_address=row["property_address"],
            project_type=row["project_type"],
            status=row["status"],
            stage=ProjectStage.normalize(row["stage"]) if "stage" in keys and row["stage"] else ProjectStage.INTAKE,
            start_date=row["start_date"] if "start_date" in keys else None,
            expected_completion=row["expected_completion"] if "expected_completion" in keys else None,
            actual_completion=row["actual_completion"] if "actual_completion" in keys else None,
            project_manager_id=row["project_manager_id"] if "project_manager_id" in keys else None,
            assigned_employees=assigned_employees,
            subcontractors=subcontractors if not is_customer else [],
            scope_of_work=row["scope_of_work"] if "scope_of_work" in keys else None,
            estimated_cost=row["estimated_cost"] if "estimated_cost" in keys and not is_customer else 0.0,
            contract_amount=row["contract_amount"] if "contract_amount" in keys else 0.0,
            actual_cost=row["actual_cost"] if "actual_cost" in keys and not is_customer else 0.0,
            profit=row["profit"] if "profit" in keys and not is_customer else 0.0,
            notes=row["notes"] if "notes" in keys and not is_customer else None,
            warranty_info=row["warranty_info"] if "warranty_info" in keys else None,
            stage_entered_at=row["stage_entered_at"] if "stage_entered_at" in keys else None,
            insurance_claim_number=row["insurance_claim_number"] if "insurance_claim_number" in keys else None,
            insurance_carrier=row["insurance_carrier"] if "insurance_carrier" in keys else None,
            adjuster_name=row["adjuster_name"] if "adjuster_name" in keys else None,
            adjuster_phone=row["adjuster_phone"] if "adjuster_phone" in keys else None,
            adjuster_email=row["adjuster_email"] if "adjuster_email" in keys else None,
            deductible=row["deductible"] if "deductible" in keys else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ==========================================
    # PROJECT LIFECYCLE & STAGE TRANSITIONS
    # ==========================================

    def _actor_reaches_only_via_sold_projects(self, actor: AuthContext) -> bool:
        """True iff `actor` holds PERM_READ_OWN_SOLD_PROJECTS (B8.12a) but
        neither PERM_READ_OPERATIONS/PERM_MANAGE_PROJECTS (this domain's
        existing flat gates) nor PERM_READ_TEAM_SALES_DATA (the team-wide
        bypass -- this is how ROLE_SALES_MANAGER keeps full, unfiltered
        operations visibility, same mechanism as crm_service.py's
        identical narrowing). NEW-630 briefly granted PERM_READ_OPERATIONS
        itself to ROLE_SALES_MANAGER (dd244d5, 2026-09-25), which would
        have made this bypass a second, redundant route to the same
        unfiltered result for that role -- that grant was reversed
        (2026-09-27, direct Ish decision), so PERM_READ_TEAM_SALES_DATA
        remains the only route. Keyed on permission, never
        `actor.role`, so a custom_permissions_json grant of
        PERM_READ_OWN_SOLD_PROJECTS to any other role is narrowed
        identically."""
        return (
            actor.has_permission(PERM_READ_OWN_SOLD_PROJECTS)
            and not actor.has_permission(PERM_READ_OPERATIONS)
            and not actor.has_permission(PERM_MANAGE_PROJECTS)
            and not actor.has_permission(PERM_READ_TEAM_SALES_DATA)
        )

    def _actor_owns_sold_project(self, project_id: int, actor: AuthContext) -> bool:
        """True iff a `contracts` row exists with `project_id` matching and
        `assigned_user_id == actor.user_id`. A Contract row with
        assigned_user_id IS NULL (unclaimed) never matches this query --
        fail-closed, deliberately NOT the leads/opportunities unclaimed-pool
        leniency (see PERM_READ_OWN_SOLD_PROJECTS in auth.py)."""
        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT 1 FROM contracts WHERE project_id = ? AND assigned_user_id = ? LIMIT 1;",
            (project_id, actor.user_id),
        ).fetchone()
        return row is not None

    def _actor_assigned_to_project(self, project_id: int, actor: AuthContext) -> bool:
        """True iff `actor.user_id` appears in the owning project's
        `projects.assigned_employees_json` list (NEW-628). Deliberately
        role-keyed (`actor.role == ROLE_TECHNICIAN` at each call site, not a
        permission check) to mirror crm_service.py's identical, already-shipped
        ROLE_TECHNICIAN check on the same column (crm_service.py ~L2833) --
        unlike `_actor_reaches_only_via_sold_projects` above (permission-keyed,
        so a custom_permissions_json grant of PERM_READ_OWN_SOLD_PROJECTS to
        any role gets narrowed), assigned_employees ownership has no
        standalone permission of its own to key on; ROLE_TECHNICIAN's actual
        grant is PERM_READ_ASSIGNED_PROJECTS, which no other built-in role
        holds, so keying on role vs. that permission is equivalent for every
        role defined today. Python-side json.loads decode, not a SQL
        `json_each` subquery -- this codebase has never used json_each
        anywhere (checked), and crm_service.py's identical check decodes in
        Python too; matching that convention over inventing a third style."""
        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT assigned_employees_json FROM projects WHERE id = ?;",
            (project_id,),
        ).fetchone()
        if not row or not row["assigned_employees_json"]:
            return False
        assigned = json.loads(row["assigned_employees_json"])
        return actor.user_id in assigned

    def _technician_assigned_project_ids(self, actor: AuthContext) -> Set[int]:
        """Set of project ids `actor.user_id` is assigned to, for narrowing
        a *different* table's rows (work_orders/equipment) by their
        project_id/current_project_id in one pass instead of N+1 calls to
        `_actor_assigned_to_project`. Scans+decodes all `projects` rows in
        Python rather than a SQL subquery for the same json_each-avoidance
        reason as `_actor_assigned_to_project` above; mirrors
        crm_service.py's list_projects, which already does an unfiltered
        `SELECT * FROM projects` and filters technician rows in Python
        (crm_service.py ~L2888-2897)."""
        conn = self.db.get_connection()
        rows = conn.execute("SELECT id, assigned_employees_json FROM projects;").fetchall()
        ids: Set[int] = set()
        for r in rows:
            assigned = json.loads(r["assigned_employees_json"]) if r["assigned_employees_json"] else []
            if actor.user_id in assigned:
                ids.add(r["id"])
        return ids

    def get_project(self, project_id: int, actor: AuthContext) -> Optional[Project]:
        if not (
            actor.has_permission(PERM_READ_OPERATIONS)
            or actor.has_permission(PERM_MANAGE_PROJECTS)
            or actor.has_permission(PERM_READ_OWN_SOLD_PROJECTS)
            or (actor.role == ROLE_CUSTOMER and actor.customer_id is not None)
        ):
            raise PermissionError("Actor lacks permission to view projects in operations domain")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM projects WHERE id = ?;", (project_id,)).fetchone()
        if not row:
            return None

        if actor.role == ROLE_CUSTOMER:
            if not actor.customer_id or actor.customer_id != row["customer_id"]:
                raise PermissionError("Customer cannot view other customers' projects")
        elif self._actor_reaches_only_via_sold_projects(actor):
            # B8.12a (NEW-628): actor reached this gate only via
            # PERM_READ_OWN_SOLD_PROJECTS -- narrow to projects they sold.
            if not self._actor_owns_sold_project(project_id, actor):
                raise PermissionError("Actor cannot view a project they did not sell")
        elif actor.role == ROLE_TECHNICIAN:
            # NEW-628: ROLE_TECHNICIAN holds PERM_READ_OPERATIONS/
            # PERM_WRITE_OPERATIONS org-wide but only
            # PERM_READ_ASSIGNED_PROJECTS -- narrow to projects they're
            # assigned to, mirroring crm_service.py's identical check.
            assigned = json.loads(row["assigned_employees_json"]) if row["assigned_employees_json"] else []
            if actor.user_id not in assigned:
                raise PermissionError("Technician cannot view a project they are not assigned to")

        return self._row_to_project(row, actor.role)

    def transition_project_stage(
        self,
        project_id: int,
        target_stage: str,
        actor: AuthContext,
        notes: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Project:
        """
        Transition a project to a new lifecycle stage.
        Validates stage transition rules, prerequisite gates, and records audit trails.
        """
        if not actor.has_permission(PERM_MANAGE_PROJECTS):
            raise PermissionError("Actor lacks permission to manage project lifecycle transitions")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM projects WHERE id = ?;", (project_id,)).fetchone()
        if not row:
            raise ValueError(f"Project #{project_id} not found")

        project = self._row_to_project(row, actor.role)
        current_stage = ProjectStage.normalize(project.stage)
        target = ProjectStage.normalize(target_stage)

        if not ProjectStage.is_valid(target):
            raise ValueError(f"Invalid project stage: {target_stage}")

        if current_stage == target:
            return project

        if not ProjectStage.can_transition(current_stage, target):
            raise ValueError(f"Invalid stage transition from {current_stage} to {target}")

        # Audit pre-image: frozen before any in-memory mutation (e.g. the
        # COMPLETED gate sets project.actual_completion below) or DB write.
        _before = project.to_dict()
        _se: Dict[str, Any] = {}

        # Gate Checks
        if target == ProjectStage.CANCELLED:
            if not reason or not reason.strip():
                raise ValueError("Cancellation requires a non-empty reason")

        elif current_stage == ProjectStage.INTAKE and target == ProjectStage.ASSESSMENT_SCOPING:
            if not project.property_address or not project.property_address.strip():
                raise ValueError("Project must have a property address to enter assessment scoping")
            self._ensure_default_milestones(project_id, target, actor)
            _se["default_milestones_ensured"] = True

        elif target == ProjectStage.INSURANCE_APPROVAL:
            if not project.insurance_carrier and not project.insurance_claim_number:
                raise ValueError("Transition to insurance approval requires insurance carrier or claim number")

        elif target == ProjectStage.SCHEDULED:
            if project.contract_amount <= 0 and project.estimated_cost <= 0:
                approved_est = conn.execute(
                    "SELECT id FROM estimates WHERE project_id = ? AND status = 'approved';",
                    (project_id,),
                ).fetchone()
                if not approved_est:
                    raise ValueError("Transition to scheduled requires a contract amount, estimated cost, or approved estimate")

        elif target == ProjectStage.IN_PROGRESS:
            wo_count = conn.execute(
                "SELECT COUNT(*) as c FROM work_orders WHERE project_id = ?;",
                (project_id,),
            ).fetchone()["c"]
            if wo_count == 0 and not project.start_date:
                raise ValueError("Transition to in_progress requires at least one work order or a scheduled start date")

        elif target == ProjectStage.QUALITY_INSPECTION:
            active_wos = conn.execute(
                "SELECT id, status FROM work_orders WHERE project_id = ? AND status NOT IN ('completed', 'verified', 'cancelled');",
                (project_id,),
            ).fetchall()
            if active_wos:
                raise ValueError(f"Cannot transition to quality inspection: {len(active_wos)} work order(s) are not completed/verified")

        elif target == ProjectStage.FINAL_WALKTHROUGH:
            pending_insp = conn.execute(
                "SELECT id FROM project_milestones WHERE project_id = ? AND stage = 'quality_inspection' AND status != 'completed';",
                (project_id,),
            ).fetchall()
            if pending_insp:
                raise ValueError("Cannot proceed to final walkthrough until all quality inspection milestones are completed")

        elif target == ProjectStage.COMPLETED:
            if not project.actual_completion:
                project.actual_completion = utc_now_iso()

        elif target == ProjectStage.CLOSED:
            # NEW-613: was a raw balance_due query with no financing
            # offset, disagreeing with FinanceService.get_project_pnl on
            # the same project's AR. Now sourced from the same shared,
            # no-actor get_project_ar_net() helper get_project_pnl itself
            # calls, so this gate reconciles to
            # get_project_pnl(project_id)["total_outstanding"] by
            # construction. Behavior change (intended, not an incidental
            # refactor side effect): a project whose outstanding balance
            # is now fully covered by an eligible financing record can
            # transition to CLOSED with no override `reason`, where
            # previously it always required one regardless of financing.
            # Rounded before the `> 0` comparison -- total_outstanding is
            # a raw (unrounded) float subtraction, and float noise from
            # summing several invoice balances/offsets could otherwise
            # leave a residue like 4.5e-13 that reads as ">0" while every
            # displayed dollar figure is $0.00, producing a
            # self-contradictory error message.
            ar_net = self.finance_service.get_project_ar_net(project_id)
            net_outstanding = round(ar_net["total_outstanding"], 2)
            if net_outstanding > 0 and not reason:
                raise ValueError(f"Cannot close project with outstanding balance of ${net_outstanding:.2f} without an override reason")

        # Map to legacy status
        status_map = {
            ProjectStage.INTAKE: "planning",
            ProjectStage.ASSESSMENT_SCOPING: "planning",
            ProjectStage.INSURANCE_APPROVAL: "planning",
            ProjectStage.SCHEDULED: "scheduled",
            ProjectStage.IN_PROGRESS: "in_progress",
            ProjectStage.QUALITY_INSPECTION: "in_progress",
            ProjectStage.FINAL_WALKTHROUGH: "in_progress",
            ProjectStage.COMPLETED: "completed",
            ProjectStage.BILLED: "completed",
            ProjectStage.CLOSED: "completed",
            ProjectStage.ON_HOLD: "on_hold",
            ProjectStage.CANCELLED: "cancelled",
        }
        new_status = status_map.get(target, project.status)
        now = utc_now_iso()

        with conn:
            conn.execute(
                """
                UPDATE projects SET
                    stage = ?,
                    status = ?,
                    stage_entered_at = ?,
                    actual_completion = ?,
                    notes = COALESCE(?, notes),
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    target,
                    new_status,
                    now,
                    project.actual_completion,
                    notes if notes is not None else project.notes,
                    now,
                    project_id,
                ),
            )

        if reason is not None:
            _se["transition_reason"] = reason

        after_row = conn.execute("SELECT * FROM projects WHERE id = ?;", (project_id,)).fetchone()
        _after = self._row_to_project(after_row, actor.role).to_dict() if after_row else None

        self.audit.log(
            action="project_stage_transition",
            entity_type="project",
            entity_id=project_id,
            change_summary=f"Project #{project_id} transitioned from '{current_stage}' to '{target}'",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_after,
                fields=_AUDITABLE_PROJECT_FIELDS,
                side_effects=_se or None,
            ),
        )
        return self.get_project(project_id, actor)

    def get_default_milestones_for_stage(self, stage: str) -> List[Dict[str, Any]]:
        """Return canonical milestone templates associated with each project lifecycle stage."""
        stage_norm = ProjectStage.normalize(stage)
        templates: Dict[str, List[str]] = {
            ProjectStage.ASSESSMENT_SCOPING: [
                "Initial Site Inspection & Hazard Assessment",
                "Comprehensive Moisture Mapping & Documentation",
                "Scope of Work & Line-Item Estimate Finalized",
            ],
            ProjectStage.INSURANCE_APPROVAL: [
                "Claim Documentation & Photos Submitted to Carrier",
                "Adjuster On-Site Inspection / Joint Walkthrough",
                "Agreed Scope & Pricing Approved by Carrier",
            ],
            ProjectStage.SCHEDULED: [
                "Material Procurement & Staging Confirmed",
                "Trade Crew Lead & Subcontractors Scheduled",
                "Site Containment & Environmental Controls Planned",
            ],
            ProjectStage.IN_PROGRESS: [
                "Containment Setup & Demolition / Extraction Completed",
                "Structural Drying Goal / Antimicrobial Application Met",
                "Reconstruction & Finish Trade Installation Complete",
            ],
            ProjectStage.QUALITY_INSPECTION: [
                "Comprehensive QA Punch-List Completed",
                "Moisture Clearance & Environmental Testing Passed",
            ],
            ProjectStage.FINAL_WALKTHROUGH: [
                "Customer Final Walkthrough & Sign-off Completed",
                "Certificate of Satisfaction / Completion Signed",
            ],
            ProjectStage.COMPLETED: [
                "Job Closeout Documentation & Photos Archived",
                "Final Certificate of Completion Issued",
            ],
            ProjectStage.BILLED: [
                "Final Insurance / Owner Invoice Submitted",
                "Payment Received & Lien Waivers Executed",
            ],
        }
        milestone_names = templates.get(stage_norm, [])
        return [{"name": name, "stage": stage_norm} for name in milestone_names]

    def _ensure_default_milestones(self, project_id: int, stage: str, actor: AuthContext) -> None:
        """Create default milestones for a project if none exist yet for the stage."""
        conn = self.db.get_connection()
        existing = conn.execute(
            "SELECT COUNT(*) as c FROM project_milestones WHERE project_id = ? AND stage = ?;",
            (project_id, stage),
        ).fetchone()["c"]
        if existing == 0:
            defaults = self.get_default_milestones_for_stage(stage)
            for d in defaults:
                m = ProjectMilestone(
                    project_id=project_id,
                    name=d["name"],
                    stage=d["stage"],
                    status=MilestoneStatus.PENDING,
                )
                self.create_milestone(m, actor)

    # ==========================================
    # PROJECT MILESTONES
    # ==========================================

    def create_milestone(self, milestone: ProjectMilestone, actor: AuthContext) -> ProjectMilestone:
        """Create a milestone under `milestone.project_id`. Write-path
        counterpart to NEW-628: a ROLE_TECHNICIAN actor is additionally
        narrowed to projects they are assigned to
        (`_actor_assigned_to_project`) -- otherwise any technician with
        org-wide PERM_WRITE_OPERATIONS could create milestones on a project
        they have no assignment to at all."""
        if not (
            actor.has_permission(PERM_WRITE_OPERATIONS)
            or actor.has_permission(PERM_MANAGE_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to create project milestones")

        if actor.role == ROLE_TECHNICIAN and not self._actor_assigned_to_project(milestone.project_id, actor):
            raise PermissionError("Technician cannot create a milestone for a project they are not assigned to")

        if not milestone.name or not milestone.name.strip():
            raise ValueError("Milestone name cannot be empty")

        milestone.stage = ProjectStage.normalize(milestone.stage)
        now = utc_now_iso()
        milestone.created_at = now
        milestone.updated_at = now
        deps_json = json.dumps(milestone.dependencies)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO project_milestones (
                    project_id, name, stage, target_date, completion_date,
                    status, dependencies_json, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    milestone.project_id,
                    milestone.name.strip(),
                    milestone.stage,
                    milestone.target_date,
                    milestone.completion_date,
                    milestone.status,
                    deps_json,
                    milestone.notes,
                    now,
                    now,
                ),
            )
            milestone.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="milestone",
            entity_id=milestone.id,
            change_summary=f"Created milestone '{milestone.name}' for project #{milestone.project_id}",
            actor=actor,
            details=build_audit_details(after=milestone.to_dict()),
        )
        return milestone

    def get_milestone(self, milestone_id: int, actor: AuthContext) -> Optional[ProjectMilestone]:
        if not (
            actor.has_permission(PERM_READ_OPERATIONS)
            or actor.has_permission(PERM_READ_OWN_SOLD_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to view milestones")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM project_milestones WHERE id = ?;", (milestone_id,)).fetchone()
        if not row:
            return None

        # B8.12a (NEW-628): actor reached this gate only via
        # PERM_READ_OWN_SOLD_PROJECTS -- narrow to milestones on projects
        # they sold. (PERM_READ_OPERATIONS holders remain unfiltered here,
        # same as before this round -- see NEW-628 for that broader gap.)
        if self._actor_reaches_only_via_sold_projects(actor):
            if not self._actor_owns_sold_project(row["project_id"], actor):
                raise PermissionError("Actor cannot view a milestone for a project they did not sell")
        elif actor.role == ROLE_TECHNICIAN:
            # NEW-628: narrow to milestones on projects the technician is
            # assigned to.
            if not self._actor_assigned_to_project(row["project_id"], actor):
                raise PermissionError("Technician cannot view a milestone for a project they are not assigned to")

        return self._row_to_milestone(row)

    def list_milestones(self, project_id: int, actor: AuthContext) -> List[ProjectMilestone]:
        if not (
            actor.has_permission(PERM_READ_OPERATIONS)
            or actor.has_permission(PERM_READ_OWN_SOLD_PROJECTS)
            or (actor.role == ROLE_CUSTOMER and actor.customer_id is not None)
        ):
            raise PermissionError("Actor lacks permission to list milestones")

        conn = self.db.get_connection()
        if actor.role == ROLE_CUSTOMER:
            proj = conn.execute("SELECT customer_id FROM projects WHERE id = ?;", (project_id,)).fetchone()
            if not proj or proj["customer_id"] != actor.customer_id:
                raise PermissionError("Customer cannot view milestones for other customers' projects")
        elif self._actor_reaches_only_via_sold_projects(actor):
            if not self._actor_owns_sold_project(project_id, actor):
                raise PermissionError("Actor cannot list milestones for a project they did not sell")
        elif actor.role == ROLE_TECHNICIAN:
            # NEW-628: narrow to milestones on projects the technician is
            # assigned to.
            if not self._actor_assigned_to_project(project_id, actor):
                raise PermissionError("Technician cannot list milestones for a project they are not assigned to")

        rows = conn.execute(
            "SELECT * FROM project_milestones WHERE project_id = ? ORDER BY id ASC;",
            (project_id,),
        ).fetchall()
        return [self._row_to_milestone(r) for r in rows]

    def update_milestone_status(
        self,
        milestone_id: int,
        new_status: str,
        actor: AuthContext,
        notes: Optional[str] = None,
    ) -> ProjectMilestone:
        """
        Update milestone progress status with prerequisite dependency validation.
        """
        if not (
            actor.has_permission(PERM_WRITE_OPERATIONS)
            or actor.has_permission(PERM_MANAGE_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to update milestone status")

        if new_status not in MilestoneStatus.ALL_STATUSES:
            raise ValueError(f"Invalid milestone status: {new_status}")

        milestone = self.get_milestone(milestone_id, actor)
        if not milestone:
            raise ValueError(f"Milestone #{milestone_id} not found")
        _before = milestone.to_dict()

        # Dependency check when transitioning to in_progress or completed
        if new_status in (MilestoneStatus.IN_PROGRESS, MilestoneStatus.COMPLETED) and milestone.dependencies:
            conn = self.db.get_connection()
            for dep_id in milestone.dependencies:
                dep_row = conn.execute(
                    "SELECT id, name, status FROM project_milestones WHERE id = ?;",
                    (dep_id,),
                ).fetchone()
                if not dep_row:
                    raise ValueError(f"Prerequisite milestone #{dep_id} does not exist")
                if dep_row["status"] != MilestoneStatus.COMPLETED:
                    raise ValueError(
                        f"Cannot progress milestone: prerequisite milestone #{dep_id} ('{dep_row['name']}') is {dep_row['status']}"
                    )

        now = utc_now_iso()
        completion_date = milestone.completion_date
        if new_status == MilestoneStatus.COMPLETED and not completion_date:
            completion_date = now
        elif new_status != MilestoneStatus.COMPLETED:
            completion_date = None

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                UPDATE project_milestones SET
                    status = ?,
                    completion_date = ?,
                    notes = COALESCE(?, notes),
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    new_status,
                    completion_date,
                    notes if notes is not None else milestone.notes,
                    now,
                    milestone_id,
                ),
            )

        updated = self.get_milestone(milestone_id, actor)
        self.audit.log(
            action="status_change",
            entity_type="milestone",
            entity_id=milestone_id,
            change_summary=f"Milestone #{milestone_id} status updated from '{milestone.status}' to '{new_status}'",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=updated.to_dict() if updated else None,
                fields=_AUDITABLE_MILESTONE_FIELDS,
            ),
        )
        return updated

    def complete_milestone(self, milestone_id: int, actor: AuthContext, notes: Optional[str] = None) -> ProjectMilestone:
        return self.update_milestone_status(milestone_id, MilestoneStatus.COMPLETED, actor, notes)

    # ==========================================
    # WORK ORDERS & LINE ITEMS
    # ==========================================

    def generate_work_order_number(self) -> str:
        """Atomically generate the next sequential work order number: WO-0001, WO-0002, etc."""
        conn = self.db.get_connection()
        row = conn.execute("SELECT work_order_number FROM work_orders ORDER BY id DESC LIMIT 1;").fetchone()
        if not row or not row["work_order_number"]:
            return "WO-0001"

        match = re.search(r"(\d+)$", row["work_order_number"])
        if match:
            next_num = int(match.group(1)) + 1
            return f"WO-{next_num:04d}"
        return "WO-0001"

    def create_work_order(self, work_order: WorkOrder, actor: AuthContext) -> WorkOrder:
        """Create a work order under `work_order.project_id`. Write-path
        counterpart to NEW-628: a ROLE_TECHNICIAN actor is additionally
        narrowed to projects they are assigned to
        (`_actor_assigned_to_project`)."""
        if not (
            actor.has_permission(PERM_WRITE_OPERATIONS)
            or actor.has_permission(PERM_MANAGE_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to create work orders")

        if actor.role == ROLE_TECHNICIAN and not self._actor_assigned_to_project(work_order.project_id, actor):
            raise PermissionError("Technician cannot create a work order for a project they are not assigned to")

        if not work_order.title or not work_order.title.strip():
            raise ValueError("Work order title cannot be empty")
        if not work_order.trade or not work_order.trade.strip():
            raise ValueError("Work order trade cannot be empty")

        if not work_order.work_order_number:
            work_order.work_order_number = self.generate_work_order_number()

        # Compute total cost from line items
        if work_order.line_items:
            total = 0.0
            for item in work_order.line_items:
                qty = float(item.get("quantity", 1.0))
                unit_cost = float(item.get("unit_cost", 0.0))
                item_total = round(qty * unit_cost, 2)
                item["total_cost"] = item_total
                total += item_total
            work_order.total_cost = round(total, 2)

        now = utc_now_iso()
        work_order.created_at = now
        work_order.updated_at = now
        line_items_json = json.dumps(work_order.line_items)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO work_orders (
                    work_order_number, title, project_id, trade,
                    assigned_subcontractor_id, assigned_crew_lead,
                    scheduled_start, scheduled_end, actual_start, actual_end,
                    status, line_items_json, total_cost, instructions, notes,
                    dispatched_at, accepted_at, completed_at, verified_at,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    work_order.work_order_number,
                    work_order.title.strip(),
                    work_order.project_id,
                    work_order.trade.strip().lower(),
                    work_order.assigned_subcontractor_id,
                    work_order.assigned_crew_lead,
                    work_order.scheduled_start,
                    work_order.scheduled_end,
                    work_order.actual_start,
                    work_order.actual_end,
                    work_order.status,
                    line_items_json,
                    work_order.total_cost,
                    work_order.instructions,
                    work_order.notes,
                    work_order.dispatched_at,
                    work_order.accepted_at,
                    work_order.completed_at,
                    work_order.verified_at,
                    now,
                    now,
                ),
            )
            work_order.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="work_order",
            entity_id=work_order.id,
            change_summary=f"Created work order {work_order.work_order_number} ('{work_order.title}')",
            actor=actor,
            details=build_audit_details(after=work_order.to_dict()),
        )
        return work_order

    def get_work_order(self, work_order_id: int, actor: AuthContext) -> Optional[WorkOrder]:
        if not (
            actor.has_permission(PERM_READ_OPERATIONS)
            or actor.has_permission(PERM_READ_OWN_SOLD_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to view work orders")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM work_orders WHERE id = ?;", (work_order_id,)).fetchone()
        if not row:
            return None

        # B8.12a (NEW-628): actor reached this gate only via
        # PERM_READ_OWN_SOLD_PROJECTS -- narrow to work orders on projects
        # they sold.
        if self._actor_reaches_only_via_sold_projects(actor):
            if not self._actor_owns_sold_project(row["project_id"], actor):
                raise PermissionError("Actor cannot view a work order for a project they did not sell")
        elif actor.role == ROLE_TECHNICIAN:
            # NEW-628: narrow to work orders on projects the technician is
            # assigned to.
            if not self._actor_assigned_to_project(row["project_id"], actor):
                raise PermissionError("Technician cannot view a work order for a project they are not assigned to")

        return self._row_to_work_order(row)

    def list_work_orders(
        self,
        actor: AuthContext,
        project_id: Optional[int] = None,
        trade: Optional[str] = None,
        status: Optional[str] = None,
        subcontractor_id: Optional[int] = None,
    ) -> List[WorkOrder]:
        if not (
            actor.has_permission(PERM_READ_OPERATIONS)
            or actor.has_permission(PERM_READ_OWN_SOLD_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to list work orders")

        query = "SELECT * FROM work_orders WHERE 1=1"
        params: List[Any] = []

        if project_id is not None:
            query += " AND project_id = ?"
            params.append(project_id)

        # B8.12a: rep-ownership narrowing. When project_id is given, this
        # composes with the clause above (both AND-ed); when it isn't, this
        # is the only thing keeping a narrowed rep's list to their own sold
        # projects' work orders instead of leaking the whole company's --
        # see NEW-628 for why every OTHER caller of this method still gets
        # zero row-level filtering.
        if self._actor_reaches_only_via_sold_projects(actor):
            query += " AND project_id IN (SELECT project_id FROM contracts WHERE assigned_user_id = ?)"
            params.append(actor.user_id)

        if trade:
            query += " AND trade = ?"
            params.append(trade.strip().lower())
        if status:
            query += " AND status = ?"
            params.append(status.strip().lower())
        if subcontractor_id is not None:
            query += " AND assigned_subcontractor_id = ?"
            params.append(subcontractor_id)

        query += " ORDER BY id ASC;"
        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()

        if actor.role == ROLE_TECHNICIAN:
            # NEW-628: narrow to work orders on projects the technician is
            # assigned to. Python-side filter (not a SQL clause) since
            # assigned_employees_json isn't a queryable FK column -- mirrors
            # crm_service.py's list_projects, same reasoning as
            # `_technician_assigned_project_ids`'s docstring above.
            allowed_project_ids = self._technician_assigned_project_ids(actor)
            rows = [r for r in rows if r["project_id"] in allowed_project_ids]

        return [self._row_to_work_order(r) for r in rows]

    def _query_active_work_orders_for_subcontractor(self, subcontractor_id: int) -> List[Dict[str, Any]]:
        """Unguarded query -- 'active' = non-terminal work_orders rows
        assigned to this subcontractor. Terminal statuses
        ('completed', 'verified', 'cancelled') come from
        work_orders.status's own CHECK constraint (database.py) and match
        the same NOT IN set this module already uses for the
        QUALITY_INSPECTION stage-transition guard above. Shared,
        unfiltered core for both the RBAC-gated public read
        (get_active_work_orders_for_subcontractor) and the subcontractor
        DELETE route's server-side re-check, so the two can never drift
        (NEW-507, mirrors the staff_schedules/appointment_types
        active-reference precedent, Delete-buttons round 2026-09-11).

        NEW-646: `project_id` was added to the SELECT (additive column) so
        the RBAC-gated public method below can narrow its own return value
        for ROLE_TECHNICIAN by assigned-project membership. Deliberately NOT
        row-filtered in here -- crm_service.py's subcontractor-delete
        precheck (crm_service.py ~L6742) calls this exact unguarded method
        directly, bypassing the narrowed public method entirely, so a
        technician's narrowed (possibly empty) result must never reach it;
        doing so would let a subcontractor with real active work orders get
        deleted. Any future filtering belongs ONLY in the public method."""
        conn = self.db.get_connection()
        rows = conn.execute(
            "SELECT id, work_order_number, title, status, project_id FROM work_orders "
            "WHERE assigned_subcontractor_id = ? "
            "AND status NOT IN ('completed', 'verified', 'cancelled');",
            (subcontractor_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_active_work_orders_for_subcontractor(
        self, subcontractor_id: int, actor: AuthContext
    ) -> List[Dict[str, Any]]:
        """RBAC-gated read of active (non-terminal) work orders assigned to
        a subcontractor -- backs the admin-surface subcontractor-delete
        precheck popup (NEW-507).

        NEW-646: ROLE_TECHNICIAN is narrowed to rows whose `project_id` is
        one of their assigned projects (`_technician_assigned_project_ids`).
        This filtering lives here, not in the shared
        `_query_active_work_orders_for_subcontractor` helper, because that
        helper is also called unguarded by crm_service.py's
        subcontractor-delete precheck -- see that helper's docstring."""
        if not actor.has_permission(PERM_READ_OPERATIONS):
            raise PermissionError("Actor lacks permission to read work orders")
        rows = self._query_active_work_orders_for_subcontractor(subcontractor_id)
        if actor.role == ROLE_TECHNICIAN:
            allowed_project_ids = self._technician_assigned_project_ids(actor)
            rows = [r for r in rows if r["project_id"] in allowed_project_ids]
        return rows

    def update_work_order(self, work_order: WorkOrder, actor: AuthContext) -> WorkOrder:
        """Update an existing work order's dispatch/execution fields.
        NEW-643: for ROLE_TECHNICIAN, ownership is checked against the
        CURRENT `project_id` read fresh from the `work_orders` row in the
        DB -- never `work_order.project_id` off the caller-supplied model.
        The `UPDATE` below never writes `project_id` (it isn't a mutable
        field of this call), so the model's copy could be stale or spoofed;
        the DB row is the only authoritative source for which project this
        work order actually belongs to."""
        if not (
            actor.has_permission(PERM_WRITE_OPERATIONS)
            or actor.has_permission(PERM_MANAGE_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to update work orders")

        if not work_order.id:
            raise ValueError("Work order ID is required for update")

        if actor.role == ROLE_TECHNICIAN:
            conn = self.db.get_connection()
            row = conn.execute(
                "SELECT project_id FROM work_orders WHERE id = ?;", (work_order.id,)
            ).fetchone()
            if not row or not self._actor_assigned_to_project(row["project_id"], actor):
                raise PermissionError("Technician cannot update a work order for a project they are not assigned to")

        if work_order.line_items:
            total = 0.0
            for item in work_order.line_items:
                qty = float(item.get("quantity", 1.0))
                unit_cost = float(item.get("unit_cost", 0.0))
                item_total = round(qty * unit_cost, 2)
                item["total_cost"] = item_total
                total += item_total
            work_order.total_cost = round(total, 2)

        now = utc_now_iso()
        work_order.updated_at = now
        line_items_json = json.dumps(work_order.line_items)

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                UPDATE work_orders SET
                    title = ?,
                    trade = ?,
                    assigned_subcontractor_id = ?,
                    assigned_crew_lead = ?,
                    scheduled_start = ?,
                    scheduled_end = ?,
                    actual_start = ?,
                    actual_end = ?,
                    status = ?,
                    line_items_json = ?,
                    total_cost = ?,
                    instructions = ?,
                    notes = ?,
                    dispatched_at = ?,
                    accepted_at = ?,
                    completed_at = ?,
                    verified_at = ?,
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    work_order.title.strip(),
                    work_order.trade.strip().lower(),
                    work_order.assigned_subcontractor_id,
                    work_order.assigned_crew_lead,
                    work_order.scheduled_start,
                    work_order.scheduled_end,
                    work_order.actual_start,
                    work_order.actual_end,
                    work_order.status,
                    line_items_json,
                    work_order.total_cost,
                    work_order.instructions,
                    work_order.notes,
                    work_order.dispatched_at,
                    work_order.accepted_at,
                    work_order.completed_at,
                    work_order.verified_at,
                    now,
                    work_order.id,
                ),
            )

        self.audit.log(
            action="update",
            entity_type="work_order",
            entity_id=work_order.id,
            change_summary=f"Updated work order {work_order.work_order_number}",
            actor=actor,
            # C-none: WorkOrder has no sensitive/PII columns, so an unfiltered
            # snapshot of the caller-supplied model is deliberate here. The
            # sole caller (api/routes.py) fetches the WorkOrder via
            # get_work_order immediately before mutating and passing it; a
            # true before/after diff is deferred to B6.2b-4.
            details=build_audit_details(snapshot=work_order.to_dict()),
        )
        return work_order

    # ==========================================
    # SUBCONTRACTOR MATCHING & DISPATCHING
    # ==========================================

    def match_subcontractors_for_trade(
        self,
        trade: str,
        actor: AuthContext,
        required_date: Optional[str] = None,
        service_area: Optional[str] = None,
        require_active_insurance: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Rank and return eligible subcontractors for a work order.
        Scoring algorithm:
        1. Trade Match (Primary match: 50 pts, Secondary match: 30 pts)
        2. Compliance (Active GL/WC + valid COI: +25 pts; Expired/Missing: disqualified or penalized)
        3. Active License (Active: +15 pts, Unlicensed where required: disqualified)
        4. Signed MSA (+5 pts) & W9 (+5 pts)
        5. Availability Window Check (+15 pts if no conflicts)
        6. Contact DNC Check (dnc_status == 1: strictly disqualified)
        """
        if not (
            actor.has_permission(PERM_READ_OPERATIONS)
            or actor.has_permission(PERM_READ_SUBCONTRACTORS)
        ):
            raise PermissionError("Actor lacks permission to match subcontractors")

        conn = self.db.get_connection()
        rows = conn.execute("SELECT * FROM subcontractors WHERE dnc_status = 0;").fetchall()

        target_trade = trade.strip().lower()
        today_str = utc_now_iso()[:10]
        matches = []

        for r in rows:
            sub_id = r["id"]
            company_name = r["company_name"]
            primary = (r["primary_trade"] or "").strip().lower()
            secondary_raw = r["secondary_trades_json"]
            secondary = [t.strip().lower() for t in json.loads(secondary_raw)] if secondary_raw else []

            # 1. Trade Match
            trade_score = 0
            if primary == target_trade:
                trade_score = 50
            elif target_trade in secondary:
                trade_score = 30
            else:
                continue  # Must match trade

            # 2. Compliance
            score = trade_score
            coi_expiration = r["coi_expiration"]
            coi_received = bool(r["coi_received"])
            coi_valid = False

            if coi_expiration:
                if coi_expiration >= today_str:
                    coi_valid = True
                    score += 25
                else:
                    if require_active_insurance:
                        continue  # Disqualified
                    score -= 50
            elif coi_received:
                coi_valid = True
                score += 25
            else:
                if require_active_insurance:
                    continue  # Disqualified

            # License check
            license_required = bool(r["license_required"])
            license_num = r["license_number"]
            license_status = (r["license_status"] or "").strip().lower()
            licensed = bool(license_num or license_status == "active")

            if licensed:
                score += 15
            elif license_required:
                continue  # Disqualified

            # MSA & W9
            msa_signed = bool(r["msa_signed"])
            w9_received = bool(r["w9_received"])
            if msa_signed:
                score += 5
            if w9_received:
                score += 5

            # Service Area
            if service_area and r["service_area"]:
                if service_area.lower() in r["service_area"].lower():
                    score += 10

            # 3. Availability Check
            conflicts = 0
            availability_status = "available"
            if required_date:
                conflict_row = conn.execute(
                    """
                    SELECT COUNT(*) as c FROM work_orders
                    WHERE assigned_subcontractor_id = ?
                      AND status IN ('dispatched', 'accepted', 'in_progress')
                      AND ? >= scheduled_start AND ? <= scheduled_end;
                    """,
                    (sub_id, required_date, required_date),
                ).fetchone()
                conflicts = conflict_row["c"] if conflict_row else 0
                if conflicts > 0:
                    availability_status = "busy"
                else:
                    score += 15
            else:
                score += 15

            matches.append({
                "subcontractor_id": sub_id,
                "company_name": company_name,
                "match_score": score,
                "primary_trade": r["primary_trade"],
                "compliance": {
                    "coi_valid": coi_valid,
                    "coi_expiration": coi_expiration,
                    "licensed": licensed,
                    "msa_signed": msa_signed,
                    "w9_received": w9_received,
                },
                "availability": availability_status,
                "conflicts": conflicts,
            })

        matches.sort(key=lambda m: m["match_score"], reverse=True)
        return matches

    def dispatch_work_order(
        self,
        work_order_id: int,
        subcontractor_id: int,
        actor: AuthContext,
        scheduled_start: Optional[str] = None,
        scheduled_end: Optional[str] = None,
        instructions: Optional[str] = None,
        override_compliance: bool = False,
    ) -> WorkOrder:
        """
        Dispatch a work order to a qualified subcontractor with compliance enforcement.
        """
        if not actor.has_permission(PERM_DISPATCH_WORK_ORDERS):
            raise PermissionError("Actor lacks permission to dispatch work orders")

        wo = self.get_work_order(work_order_id, actor)
        if not wo:
            raise ValueError(f"Work order #{work_order_id} not found")
        _before = wo.to_dict()
        _compliance_overridden = False

        conn = self.db.get_connection()
        sub_row = conn.execute("SELECT * FROM subcontractors WHERE id = ?;", (subcontractor_id,)).fetchone()
        if not sub_row:
            raise ValueError(f"Subcontractor #{subcontractor_id} not found")

        # Do-not-contact check
        if sub_row["dnc_status"] == 1:
            raise ValueError(f"Subcontractor #{subcontractor_id} is on Do-Not-Contact list")

        # Compliance checks
        today_str = utc_now_iso()[:10]
        coi_expiration = sub_row["coi_expiration"]
        if coi_expiration and coi_expiration < today_str:
            if not override_compliance:
                raise ValueError(
                    f"Subcontractor #{subcontractor_id} compliance failure: COI expired on {coi_expiration}"
                )
            _compliance_overridden = True

        if sub_row["license_required"] == 1:
            license_status = (sub_row["license_status"] or "").strip().lower()
            if license_status != "active" and not sub_row["license_number"]:
                if not override_compliance:
                    raise ValueError(f"Subcontractor #{subcontractor_id} license is not active")
                _compliance_overridden = True

        now = utc_now_iso()
        wo.assigned_subcontractor_id = subcontractor_id
        wo.status = WorkOrderStatus.DISPATCHED
        wo.dispatched_at = now
        if scheduled_start:
            wo.scheduled_start = scheduled_start
        if scheduled_end:
            wo.scheduled_end = scheduled_end
        if instructions:
            wo.instructions = instructions
        wo.updated_at = now

        with conn:
            conn.execute(
                """
                UPDATE work_orders SET
                    assigned_subcontractor_id = ?,
                    status = ?,
                    dispatched_at = ?,
                    scheduled_start = ?,
                    scheduled_end = ?,
                    instructions = COALESCE(?, instructions),
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    subcontractor_id,
                    WorkOrderStatus.DISPATCHED,
                    now,
                    wo.scheduled_start,
                    wo.scheduled_end,
                    instructions,
                    now,
                    work_order_id,
                ),
            )

        _after = self.get_work_order(work_order_id, actor)
        _se = {"compliance_overridden": True} if _compliance_overridden else {}

        self.audit.log(
            action="work_order_dispatch",
            entity_type="work_order",
            entity_id=work_order_id,
            change_summary=f"Dispatched work order {wo.work_order_number} to subcontractor #{subcontractor_id}",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_after.to_dict() if _after else None,
                fields=_AUDITABLE_WORK_ORDER_FIELDS,
                side_effects=_se or None,
            ),
        )
        return self.get_work_order(work_order_id, actor)

    def accept_work_order(
        self,
        work_order_id: int,
        actor: AuthContext,
        notes: Optional[str] = None,
    ) -> WorkOrder:
        """Transition work order from DISPATCHED to ACCEPTED."""
        if not (
            actor.has_permission(PERM_WRITE_OPERATIONS)
            or actor.has_permission(PERM_DISPATCH_WORK_ORDERS)
        ):
            raise PermissionError("Actor lacks permission to accept work orders")

        wo = self.get_work_order(work_order_id, actor)
        if not wo:
            raise ValueError(f"Work order #{work_order_id} not found")
        _before = wo.to_dict()

        now = utc_now_iso()
        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                UPDATE work_orders SET
                    status = ?,
                    accepted_at = ?,
                    notes = COALESCE(?, notes),
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    WorkOrderStatus.ACCEPTED,
                    now,
                    notes,
                    now,
                    work_order_id,
                ),
            )

        _after = self.get_work_order(work_order_id, actor)
        self.audit.log(
            action="work_order_accept",
            entity_type="work_order",
            entity_id=work_order_id,
            change_summary=f"Work order {wo.work_order_number} accepted",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_after.to_dict() if _after else None,
                fields=_AUDITABLE_WORK_ORDER_FIELDS,
            ),
        )
        return self.get_work_order(work_order_id, actor)

    def update_work_order_execution_status(
        self,
        work_order_id: int,
        new_status: str,
        actor: AuthContext,
        actual_start: Optional[str] = None,
        actual_end: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> WorkOrder:
        """Progress work order through execution lifecycle: ACCEPTED -> IN_PROGRESS -> COMPLETED -> VERIFIED."""
        if not (
            actor.has_permission(PERM_WRITE_OPERATIONS)
            or actor.has_permission(PERM_MANAGE_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to update work order execution status")

        if new_status not in WorkOrderStatus.ALL_STATUSES:
            raise ValueError(f"Invalid work order status: {new_status}")

        wo = self.get_work_order(work_order_id, actor)
        if not wo:
            raise ValueError(f"Work order #{work_order_id} not found")
        _before = wo.to_dict()

        now = utc_now_iso()
        actual_start_val = actual_start or wo.actual_start
        actual_end_val = actual_end or wo.actual_end
        completed_at_val = wo.completed_at
        verified_at_val = wo.verified_at

        if new_status == WorkOrderStatus.IN_PROGRESS and not actual_start_val:
            actual_start_val = now
        elif new_status == WorkOrderStatus.COMPLETED:
            if not actual_end_val:
                actual_end_val = now
            if not completed_at_val:
                completed_at_val = now
        elif new_status == WorkOrderStatus.VERIFIED:
            if not verified_at_val:
                verified_at_val = now

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                UPDATE work_orders SET
                    status = ?,
                    actual_start = ?,
                    actual_end = ?,
                    completed_at = ?,
                    verified_at = ?,
                    notes = COALESCE(?, notes),
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    new_status,
                    actual_start_val,
                    actual_end_val,
                    completed_at_val,
                    verified_at_val,
                    notes,
                    now,
                    work_order_id,
                ),
            )

        _after = self.get_work_order(work_order_id, actor)
        self.audit.log(
            action="status_change",
            entity_type="work_order",
            entity_id=work_order_id,
            change_summary=f"Work order {wo.work_order_number} status updated to '{new_status}'",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_after.to_dict() if _after else None,
                fields=_AUDITABLE_WORK_ORDER_FIELDS,
            ),
        )
        return self.get_work_order(work_order_id, actor)

    def complete_work_order(
        self,
        work_order_id: int,
        actor: AuthContext,
        actual_end: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> WorkOrder:
        return self.update_work_order_execution_status(
            work_order_id, WorkOrderStatus.COMPLETED, actor, actual_end=actual_end, notes=notes
        )

    def verify_work_order(
        self,
        work_order_id: int,
        actor: AuthContext,
        notes: Optional[str] = None,
    ) -> WorkOrder:
        return self.update_work_order_execution_status(
            work_order_id, WorkOrderStatus.VERIFIED, actor, notes=notes
        )

    # ==========================================
    # EQUIPMENT & RESOURCE TRACKING
    # ==========================================

    def create_equipment(self, equipment: Equipment, actor: AuthContext) -> Equipment:
        if not (
            actor.has_permission(PERM_WRITE_OPERATIONS)
            or actor.has_permission(PERM_MANAGE_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to create equipment records")

        # NEW-647: flat denial, role-keyed like _actor_assigned_to_project's
        # ROLE_TECHNICIAN checks elsewhere in this file (no standalone
        # permission to key on instead). ROLE_TECHNICIAN holds
        # PERM_WRITE_OPERATIONS org-wide, so it passes the gate above and
        # must be checked here explicitly, before field validation -- a
        # technician's `equipment` payload could otherwise fail on a
        # ValueError (e.g. empty asset_tag) instead of the intended
        # PermissionError. Technicians may still deploy_equipment/
        # return_equipment existing stock (narrowed by NEW-644/NEW-645);
        # they may never register new equipment records.
        if actor.role == ROLE_TECHNICIAN:
            raise PermissionError("Technicians cannot register new equipment; use deploy_equipment on existing stock")

        if not equipment.asset_tag or not equipment.asset_tag.strip():
            raise ValueError("Asset tag cannot be empty")
        if not equipment.name or not equipment.name.strip():
            raise ValueError("Equipment name cannot be empty")

        now = utc_now_iso()
        equipment.created_at = now
        equipment.updated_at = now

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO equipment (
                    asset_tag, name, category, model_number, serial_number,
                    status, daily_rate, current_project_id, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    equipment.asset_tag.strip().upper(),
                    equipment.name.strip(),
                    equipment.category,
                    equipment.model_number,
                    equipment.serial_number,
                    equipment.status,
                    equipment.daily_rate,
                    equipment.current_project_id,
                    equipment.notes,
                    now,
                    now,
                ),
            )
            equipment.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="equipment",
            entity_id=equipment.id,
            change_summary=f"Added equipment '{equipment.name}' ({equipment.asset_tag})",
            actor=actor,
            details=build_audit_details(after=equipment.to_dict()),
        )
        return equipment

    def get_equipment(self, equipment_id: int, actor: AuthContext) -> Optional[Equipment]:
        if not actor.has_permission(PERM_READ_OPERATIONS):
            raise PermissionError("Actor lacks permission to view equipment")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM equipment WHERE id = ?;", (equipment_id,)).fetchone()
        if not row:
            return None

        # NEW-628: narrow to equipment currently deployed to a project the
        # technician is assigned to. Equipment with no current project
        # (current_project_id IS NULL, i.e. available warehouse stock) is
        # deliberately NOT narrowed -- deploy_equipment's own pre-read
        # (below) calls this same method on AVAILABLE equipment before it
        # has any project_id to check against, so denying NULL here would
        # make deploy_equipment permanently unusable for every technician.
        if actor.role == ROLE_TECHNICIAN and row["current_project_id"] is not None:
            if not self._actor_assigned_to_project(row["current_project_id"], actor):
                raise PermissionError("Technician cannot view equipment deployed to a project they are not assigned to")

        return self._row_to_equipment(row)

    def list_equipment(
        self,
        actor: AuthContext,
        category: Optional[str] = None,
        status: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> List[Equipment]:
        if not actor.has_permission(PERM_READ_OPERATIONS):
            raise PermissionError("Actor lacks permission to list equipment")

        query = "SELECT * FROM equipment WHERE 1=1"
        params: List[Any] = []

        if category:
            query += " AND category = ?"
            params.append(category)
        if status:
            query += " AND status = ?"
            params.append(status)
        if project_id is not None:
            query += " AND current_project_id = ?"
            params.append(project_id)

        query += " ORDER BY id ASC;"
        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()

        if actor.role == ROLE_TECHNICIAN:
            # NEW-628: same NULL-current_project_id allowance as
            # get_equipment above -- available stock stays visible so a
            # technician can find something to deploy.
            allowed_project_ids = self._technician_assigned_project_ids(actor)
            rows = [
                r for r in rows
                if r["current_project_id"] is None or r["current_project_id"] in allowed_project_ids
            ]

        return [self._row_to_equipment(r) for r in rows]

    def deploy_equipment(
        self,
        equipment_id: int,
        project_id: int,
        actor: AuthContext,
        work_order_id: Optional[int] = None,
        return_due_at: Optional[str] = None,
        initial_reading: Optional[str] = None,
        condition_out: str = "good",
        notes: Optional[str] = None,
    ) -> EquipmentDeployment:
        """
        Deploy available equipment to a project job site with moisture/environmental logs.

        NEW-645 (deploy_equipment write-path counterpart to NEW-628): for
        ROLE_TECHNICIAN, ownership is checked against `project_id` -- the
        deploy TARGET -- BEFORE the INSERT/UPDATE below, not after. A
        post-write check here would have the same problem the NEW-628
        comment further down (~L1595) documents for the audit re-read: it
        would raise PermissionError after the write already committed,
        producing a real deployment with no audit trail. Checking before
        the write means a denied technician never mutates any row.
        """
        if not (
            actor.has_permission(PERM_WRITE_OPERATIONS)
            or actor.has_permission(PERM_MANAGE_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to deploy equipment")

        eq = self.get_equipment(equipment_id, actor)
        if not eq:
            raise ValueError(f"Equipment #{equipment_id} not found")
        _before = eq.to_dict()

        if eq.status != EquipmentStatus.AVAILABLE:
            raise ValueError(f"Equipment #{equipment_id} is not available (current status: {eq.status})")

        if actor.role == ROLE_TECHNICIAN and not self._actor_assigned_to_project(project_id, actor):
            raise PermissionError("Technician cannot deploy equipment to a project they are not assigned to")

        now = utc_now_iso()
        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO equipment_deployments (
                    equipment_id, project_id, work_order_id, deployed_at,
                    return_due_at, deployed_by_user_id, condition_out,
                    initial_reading, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    equipment_id,
                    project_id,
                    work_order_id,
                    now,
                    return_due_at,
                    actor.user_id,
                    condition_out,
                    initial_reading,
                    notes,
                    now,
                    now,
                ),
            )
            deployment_id = cursor.lastrowid

            conn.execute(
                """
                UPDATE equipment SET
                    status = ?,
                    current_project_id = ?,
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    EquipmentStatus.DEPLOYED,
                    project_id,
                    now,
                    equipment_id,
                ),
            )

        # NEW-628: NOT self.get_equipment(equipment_id, actor) here. That
        # method now denies a technician read of equipment whose
        # current_project_id doesn't match one of their assigned projects --
        # and the UPDATE just above set current_project_id = project_id,
        # which this technician's own write just committed. Re-checking RBAC
        # on an actor's own just-completed write would raise PermissionError
        # AFTER the INSERT/UPDATE already committed and BEFORE audit.log
        # below runs, silently dropping the audit trail for a real
        # deployment. The actor already cleared the write gate and the
        # pre-read above; this is a same-transaction audit snapshot, not a
        # fresh access decision, so a direct read is safe here.
        _after_row = conn.execute("SELECT * FROM equipment WHERE id = ?;", (equipment_id,)).fetchone()
        _after = self._row_to_equipment(_after_row) if _after_row else None
        _se = {
            "deployment_created": {
                "deployment_id": deployment_id,
                "project_id": project_id,
                "work_order_id": work_order_id,
                "condition_out": condition_out,
                "initial_reading": initial_reading,
                "return_due_at": return_due_at,
                "notes": notes,
            }
        }

        self.audit.log(
            action="equipment_deploy",
            entity_type="equipment",
            entity_id=equipment_id,
            change_summary=f"Deployed {eq.asset_tag} to project #{project_id}",
            actor=actor,
            details=build_audit_details(
                before=_before,
                after=_after.to_dict() if _after else None,
                fields=_AUDITABLE_EQUIPMENT_FIELDS,
                side_effects=_se,
            ),
        )

        dep_row = conn.execute("SELECT * FROM equipment_deployments WHERE id = ?;", (deployment_id,)).fetchone()
        if not dep_row:
            raise ValueError(f"Equipment deployment #{deployment_id} not found")
        return self._row_to_equipment_deployment(dep_row)

    def return_equipment(
        self,
        deployment_id: int,
        actor: AuthContext,
        final_reading: Optional[str] = None,
        condition_in: str = "good",
        mark_for_maintenance: bool = False,
        notes: Optional[str] = None,
    ) -> EquipmentDeployment:
        """
        Record equipment return from job site with final dry-down readings.

        NEW-644 (return_equipment write-path counterpart to NEW-628): for
        ROLE_TECHNICIAN, ownership is checked against `dep_row["project_id"]`
        -- the project this deployment was made to -- BEFORE any UPDATE
        below, matching deploy_equipment's pre-write ordering for the same
        reason (see that method's docstring).
        """
        if not (
            actor.has_permission(PERM_WRITE_OPERATIONS)
            or actor.has_permission(PERM_MANAGE_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to return equipment")

        conn = self.db.get_connection()
        dep_row = conn.execute("SELECT * FROM equipment_deployments WHERE id = ?;", (deployment_id,)).fetchone()
        if not dep_row:
            raise ValueError(f"Equipment deployment #{deployment_id} not found")

        if dep_row["returned_at"]:
            raise ValueError("Equipment deployment has already been returned")

        if actor.role == ROLE_TECHNICIAN and not self._actor_assigned_to_project(dep_row["project_id"], actor):
            raise PermissionError("Technician cannot return equipment for a project they are not assigned to")

        equipment_id = dep_row["equipment_id"]
        now = utc_now_iso()

        next_status = EquipmentStatus.AVAILABLE
        if mark_for_maintenance or condition_in.lower() in ("damaged", "worn"):
            next_status = EquipmentStatus.MAINTENANCE

        with conn:
            conn.execute(
                """
                UPDATE equipment_deployments SET
                    returned_at = ?,
                    received_by_user_id = ?,
                    condition_in = ?,
                    final_reading = ?,
                    notes = COALESCE(?, notes),
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    now,
                    actor.user_id,
                    condition_in,
                    final_reading,
                    notes,
                    now,
                    deployment_id,
                ),
            )

            conn.execute(
                """
                UPDATE equipment SET
                    status = ?,
                    current_project_id = NULL,
                    updated_at = ?
                WHERE id = ?;
                """,
                (
                    next_status,
                    now,
                    equipment_id,
                ),
            )

        updated_row = conn.execute("SELECT * FROM equipment_deployments WHERE id = ?;", (deployment_id,)).fetchone()

        _se = {
            "deployment_returned": {
                "deployment_id": deployment_id,
                "changed_fields": build_audit_details(
                    before=self._row_to_equipment_deployment(dep_row).to_dict(),
                    after=self._row_to_equipment_deployment(updated_row).to_dict(),
                    fields=_AUDITABLE_DEPLOYMENT_FIELDS,
                ).get("changed_fields", {}),
            }
        }

        self.audit.log(
            action="equipment_return",
            entity_type="equipment",
            entity_id=equipment_id,
            change_summary=f"Returned equipment #{equipment_id} from deployment #{deployment_id}",
            actor=actor,
            # C-none for equipment: scoped snapshot of exactly the two equipment
            # columns this method writes (not a full to_dict).
            details=build_audit_details(
                snapshot={"status": next_status, "current_project_id": None},
                side_effects=_se,
            ),
        )

        return self._row_to_equipment_deployment(updated_row)

    def list_project_deployments(
        self,
        project_id: int,
        actor: AuthContext,
        active_only: bool = False,
    ) -> List[EquipmentDeployment]:
        if not actor.has_permission(PERM_READ_OPERATIONS):
            raise PermissionError("Actor lacks permission to list equipment deployments")

        if actor.role == ROLE_TECHNICIAN:
            # NEW-628: narrow to deployments for a project the technician is
            # assigned to. project_id is required here (unlike list_equipment),
            # so raise rather than silently filter, matching this file's
            # required-project_id convention (list_milestones above).
            if not self._actor_assigned_to_project(project_id, actor):
                raise PermissionError("Technician cannot list equipment deployments for a project they are not assigned to")

        query = "SELECT * FROM equipment_deployments WHERE project_id = ?"
        params: List[Any] = [project_id]

        if active_only:
            query += " AND returned_at IS NULL"

        query += " ORDER BY id DESC;"
        conn = self.db.get_connection()
        rows = conn.execute(query, params).fetchall()
        return [self._row_to_equipment_deployment(r) for r in rows]

    # ==========================================
    # PROJECT SUMMARY / OPERATIONS DASHBOARD
    # ==========================================

    def get_project_summary(self, project_id: int, actor: AuthContext) -> Dict[str, Any]:
        """
        Aggregate full operational status for a project: stage, milestones, work orders, equipment.

        NEW-628: no ROLE_TECHNICIAN-specific narrowing needed directly in
        this method -- it composes get_project/list_milestones/
        list_work_orders/list_project_deployments, all narrowed above, so an
        unassigned technician is denied at the get_project call below
        (PermissionError, same as B8.12a's rep case) and an assigned
        technician's downstream calls all resolve against the same
        already-verified project_id.
        """
        project = self.get_project(project_id, actor)
        if not project:
            raise ValueError(f"Project #{project_id} not found")

        milestones = self.list_milestones(project_id, actor)
        work_orders = self.list_work_orders(actor, project_id=project_id)

        # B8.12a: equipment/deployment visibility is deliberately NOT part
        # of PERM_READ_OWN_SOLD_PROJECTS' grant (no sales-rep use case, see
        # auth.py) -- list_project_deployments still only accepts
        # PERM_READ_OPERATIONS, so calling it unconditionally would raise
        # PermissionError for a plain rep and break this whole summary read.
        # Guard it explicitly rather than fabricating a deployments=[]/
        # active_deployed_count=0 that would misrepresent "not visible to
        # this actor" as "nothing deployed" -- equipment_summary is simply
        # omitted (None) for an actor who can't see it. No current UI
        # surface reads equipment_summary yet (checked web_surfaces.py), so
        # there is nothing to regress for a rep hitting this path today.
        if actor.has_permission(PERM_READ_OPERATIONS) or actor.has_permission(PERM_MANAGE_PROJECTS):
            deployments = self.list_project_deployments(project_id, actor, active_only=True)
            equipment_summary = {
                "active_deployed_count": len(deployments),
                "deployments": [d.to_dict() for d in deployments],
            }
        else:
            equipment_summary = None

        total_milestones = len(milestones)
        completed_milestones = sum(1 for m in milestones if m.status == MilestoneStatus.COMPLETED)
        milestone_progress = round((completed_milestones / total_milestones * 100), 1) if total_milestones > 0 else 0.0

        total_wo_cost = sum(wo.total_cost for wo in work_orders)
        completed_wos = sum(1 for wo in work_orders if wo.status in (WorkOrderStatus.COMPLETED, WorkOrderStatus.VERIFIED))

        return {
            "project": project.to_dict(),
            "stage": project.stage,
            "stage_entered_at": project.stage_entered_at,
            "milestone_summary": {
                "total": total_milestones,
                "completed": completed_milestones,
                "progress_percent": milestone_progress,
                "milestones": [m.to_dict() for m in milestones],
            },
            "work_order_summary": {
                "total": len(work_orders),
                "completed": completed_wos,
                "total_cost": total_wo_cost,
                "work_orders": [wo.to_dict() for wo in work_orders],
            },
            "equipment_summary": equipment_summary,
        }
