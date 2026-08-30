"""
Operations Business Service for Restoricon Core.
Orchestrates Project Lifecycle & Milestone State Machine, Work Orders & Line Items,
Subcontractor Matching & Dispatching, and Equipment Tracking with RBAC enforcement
and automated audit logging.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..auth import (
    AuthContext,
    PERM_DISPATCH_WORK_ORDERS,
    PERM_MANAGE_PROJECTS,
    PERM_READ_OPERATIONS,
    PERM_READ_SUBCONTRACTORS,
    PERM_WRITE_OPERATIONS,
    ROLE_CUSTOMER,
    ROLE_TECHNICIAN,
)
from ..database import DatabaseManager
from ..models import (
    Equipment,
    EquipmentCategory,
    EquipmentDeployment,
    EquipmentStatus,
    MilestoneStatus,
    Project,
    ProjectMilestone,
    ProjectStage,
    Subcontractor,
    WorkOrder,
    WorkOrderStatus,
    utc_now_iso,
)
from .audit_service import AuditService


class OperationsService:
    """Core domain operations engine for Restoricon Core."""

    def __init__(self, db_manager: DatabaseManager, audit_service: AuditService):
        self.db = db_manager
        self.audit = audit_service

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

    def get_project(self, project_id: int, actor: AuthContext) -> Optional[Project]:
        if not (
            actor.has_permission(PERM_READ_OPERATIONS)
            or actor.has_permission(PERM_MANAGE_PROJECTS)
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

        # Gate Checks
        if target == ProjectStage.CANCELLED:
            if not reason or not reason.strip():
                raise ValueError("Cancellation requires a non-empty reason")

        elif current_stage == ProjectStage.INTAKE and target == ProjectStage.ASSESSMENT_SCOPING:
            if not project.property_address or not project.property_address.strip():
                raise ValueError("Project must have a property address to enter assessment scoping")
            self._ensure_default_milestones(project_id, target, actor)

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
            unpaid_invoices = conn.execute(
                "SELECT id, balance_due FROM invoices WHERE project_id = ? AND balance_due > 0 AND status NOT IN ('void', 'paid');",
                (project_id,),
            ).fetchall()
            if unpaid_invoices and not reason:
                total_unpaid = sum(r["balance_due"] for r in unpaid_invoices)
                raise ValueError(f"Cannot close project with outstanding balance of ${total_unpaid:.2f} without an override reason")

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

        self.audit.log(
            action="project_stage_transition",
            entity_type="project",
            entity_id=project_id,
            change_summary=f"Project #{project_id} transitioned from '{current_stage}' to '{target}'",
            actor=actor,
            details={
                "previous_stage": current_stage,
                "target_stage": target,
                "reason": reason,
                "notes": notes,
            },
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
        if not (
            actor.has_permission(PERM_WRITE_OPERATIONS)
            or actor.has_permission(PERM_MANAGE_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to create project milestones")

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
            details=milestone.to_dict(),
        )
        return milestone

    def get_milestone(self, milestone_id: int, actor: AuthContext) -> Optional[ProjectMilestone]:
        if not actor.has_permission(PERM_READ_OPERATIONS):
            raise PermissionError("Actor lacks permission to view milestones")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM project_milestones WHERE id = ?;", (milestone_id,)).fetchone()
        if not row:
            return None
        return self._row_to_milestone(row)

    def list_milestones(self, project_id: int, actor: AuthContext) -> List[ProjectMilestone]:
        if not (
            actor.has_permission(PERM_READ_OPERATIONS)
            or (actor.role == ROLE_CUSTOMER and actor.customer_id is not None)
        ):
            raise PermissionError("Actor lacks permission to list milestones")

        conn = self.db.get_connection()
        if actor.role == ROLE_CUSTOMER:
            proj = conn.execute("SELECT customer_id FROM projects WHERE id = ?;", (project_id,)).fetchone()
            if not proj or proj["customer_id"] != actor.customer_id:
                raise PermissionError("Customer cannot view milestones for other customers' projects")

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
            details={"previous_status": milestone.status, "new_status": new_status, "notes": notes},
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
        if not (
            actor.has_permission(PERM_WRITE_OPERATIONS)
            or actor.has_permission(PERM_MANAGE_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to create work orders")

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
            details=work_order.to_dict(),
        )
        return work_order

    def get_work_order(self, work_order_id: int, actor: AuthContext) -> Optional[WorkOrder]:
        if not actor.has_permission(PERM_READ_OPERATIONS):
            raise PermissionError("Actor lacks permission to view work orders")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM work_orders WHERE id = ?;", (work_order_id,)).fetchone()
        if not row:
            return None
        return self._row_to_work_order(row)

    def list_work_orders(
        self,
        actor: AuthContext,
        project_id: Optional[int] = None,
        trade: Optional[str] = None,
        status: Optional[str] = None,
        subcontractor_id: Optional[int] = None,
    ) -> List[WorkOrder]:
        if not actor.has_permission(PERM_READ_OPERATIONS):
            raise PermissionError("Actor lacks permission to list work orders")

        query = "SELECT * FROM work_orders WHERE 1=1"
        params: List[Any] = []

        if project_id is not None:
            query += " AND project_id = ?"
            params.append(project_id)
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
        return [self._row_to_work_order(r) for r in rows]

    def update_work_order(self, work_order: WorkOrder, actor: AuthContext) -> WorkOrder:
        if not (
            actor.has_permission(PERM_WRITE_OPERATIONS)
            or actor.has_permission(PERM_MANAGE_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to update work orders")

        if not work_order.id:
            raise ValueError("Work order ID is required for update")

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
            details=work_order.to_dict(),
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
        if coi_expiration and coi_expiration < today_str and not override_compliance:
            raise ValueError(
                f"Subcontractor #{subcontractor_id} compliance failure: COI expired on {coi_expiration}"
            )

        if sub_row["license_required"] == 1 and not override_compliance:
            license_status = (sub_row["license_status"] or "").strip().lower()
            if license_status != "active" and not sub_row["license_number"]:
                raise ValueError(f"Subcontractor #{subcontractor_id} license is not active")

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

        self.audit.log(
            action="work_order_dispatch",
            entity_type="work_order",
            entity_id=work_order_id,
            change_summary=f"Dispatched work order {wo.work_order_number} to subcontractor #{subcontractor_id}",
            actor=actor,
            details=wo.to_dict(),
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

        self.audit.log(
            action="work_order_accept",
            entity_type="work_order",
            entity_id=work_order_id,
            change_summary=f"Work order {wo.work_order_number} accepted",
            actor=actor,
            details={"notes": notes},
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

        self.audit.log(
            action="status_change",
            entity_type="work_order",
            entity_id=work_order_id,
            change_summary=f"Work order {wo.work_order_number} status updated to '{new_status}'",
            actor=actor,
            details={"previous_status": wo.status, "new_status": new_status, "notes": notes},
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
            details=equipment.to_dict(),
        )
        return equipment

    def get_equipment(self, equipment_id: int, actor: AuthContext) -> Optional[Equipment]:
        if not actor.has_permission(PERM_READ_OPERATIONS):
            raise PermissionError("Actor lacks permission to view equipment")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM equipment WHERE id = ?;", (equipment_id,)).fetchone()
        if not row:
            return None
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
        """
        if not (
            actor.has_permission(PERM_WRITE_OPERATIONS)
            or actor.has_permission(PERM_MANAGE_PROJECTS)
        ):
            raise PermissionError("Actor lacks permission to deploy equipment")

        eq = self.get_equipment(equipment_id, actor)
        if not eq:
            raise ValueError(f"Equipment #{equipment_id} not found")

        if eq.status != EquipmentStatus.AVAILABLE:
            raise ValueError(f"Equipment #{equipment_id} is not available (current status: {eq.status})")

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

        self.audit.log(
            action="equipment_deploy",
            entity_type="equipment",
            entity_id=equipment_id,
            change_summary=f"Deployed {eq.asset_tag} to project #{project_id}",
            actor=actor,
            details={
                "deployment_id": deployment_id,
                "project_id": project_id,
                "work_order_id": work_order_id,
                "initial_reading": initial_reading,
                "condition_out": condition_out,
            },
        )

        dep_row = conn.execute("SELECT * FROM equipment_deployments WHERE id = ?;", (deployment_id,)).fetchone()
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

        self.audit.log(
            action="equipment_return",
            entity_type="equipment",
            entity_id=equipment_id,
            change_summary=f"Returned equipment #{equipment_id} from deployment #{deployment_id}",
            actor=actor,
            details={
                "deployment_id": deployment_id,
                "final_reading": final_reading,
                "condition_in": condition_in,
                "next_status": next_status,
            },
        )

        updated_row = conn.execute("SELECT * FROM equipment_deployments WHERE id = ?;", (deployment_id,)).fetchone()
        return self._row_to_equipment_deployment(updated_row)

    def list_project_deployments(
        self,
        project_id: int,
        actor: AuthContext,
        active_only: bool = False,
    ) -> List[EquipmentDeployment]:
        if not actor.has_permission(PERM_READ_OPERATIONS):
            raise PermissionError("Actor lacks permission to list equipment deployments")

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
        """
        project = self.get_project(project_id, actor)
        if not project:
            raise ValueError(f"Project #{project_id} not found")

        milestones = self.list_milestones(project_id, actor)
        work_orders = self.list_work_orders(actor, project_id=project_id)
        deployments = self.list_project_deployments(project_id, actor, active_only=True)

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
            "equipment_summary": {
                "active_deployed_count": len(deployments),
                "deployments": [d.to_dict() for d in deployments],
            },
        }
