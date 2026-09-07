"""
Comprehensive Unit Test Suite for Track B / Phase B3: Operations Domain Engine
in Restoricon Core.

Tests:
1. Restoration Project Lifecycle & State Machine Transitions (Gates, Guards, Rejections)
2. Milestone Dependency Graph Validation
3. Work Order Generation, Numbering (WO-0001), Line-item Cost Calculations
4. Subcontractor Trade Matching, Scoring, Availability, and Compliance Filters
5. Equipment Deployment, Moisture Reading Tracking, Return & Maintenance Lifecycle
6. Granular RBAC Permissions Matrix & Zero-Permission Isolation
7. REST API Endpoints & Wire Payloads
"""

import json
import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_AI_AGENT,
    ROLE_CUSTOMER,
    ROLE_MANAGER,
    ROLE_PROJECT_MANAGER,
    ROLE_SALES,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    Customer,
    Equipment,
    EquipmentCategory,
    EquipmentStatus,
    MilestoneStatus,
    Project,
    ProjectMilestone,
    ProjectStage,
    Subcontractor,
    WorkOrder,
    WorkOrderStatus,
)
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService


class ZeroPermissionActor:
    """Actor that is unconditionally denied all permissions."""
    user_id = 999999
    username = "zero_perm"
    role = "nobody"
    actor_type = "agent"
    customer_id = None
    token = None

    def has_permission(self, permission: str) -> bool:
        return False


@pytest.fixture
def env():
    """Builds a test environment with in-memory SQLite and all domain services."""
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
        "ops": ops_service,
        "router": router,
    }


@pytest.fixture
def actors(env):
    auth = env["auth"]
    # Admin
    u_admin = auth.create_user("admin_user", "Pass123!", "Admin User", "admin@restoricon.com", role=ROLE_ADMIN)
    t_admin = auth.create_token(u_admin)
    ctx_admin = AuthContext(u_admin.id, u_admin.username, ROLE_ADMIN, "human", token=t_admin)

    # Manager
    u_mgr = auth.create_user("mgr_user", "Pass123!", "Manager User", "mgr@restoricon.com", role=ROLE_MANAGER)
    t_mgr = auth.create_token(u_mgr)
    ctx_mgr = AuthContext(u_mgr.id, u_mgr.username, ROLE_MANAGER, "human", token=t_mgr)

    # Project Manager
    u_pm = auth.create_user("pm_user", "Pass123!", "PM User", "pm@restoricon.com", role=ROLE_PROJECT_MANAGER)
    t_pm = auth.create_token(u_pm)
    ctx_pm = AuthContext(u_pm.id, u_pm.username, ROLE_PROJECT_MANAGER, "human", token=t_pm)

    # Sales
    u_sales = auth.create_user("sales_user", "Pass123!", "Sales User", "sales@restoricon.com", role=ROLE_SALES)
    t_sales = auth.create_token(u_sales)
    ctx_sales = AuthContext(u_sales.id, u_sales.username, ROLE_SALES, "human", token=t_sales)

    # Technician
    u_tech = auth.create_user("tech_user", "Pass123!", "Tech User", "tech@restoricon.com", role=ROLE_TECHNICIAN)
    t_tech = auth.create_token(u_tech)
    ctx_tech = AuthContext(u_tech.id, u_tech.username, ROLE_TECHNICIAN, "human", token=t_tech)

    # AI Agent
    u_agent = auth.create_user("agent_user", "Pass123!", "AI Agent", "agent@restoricon.com", role=ROLE_AI_AGENT)
    t_agent = auth.create_token(u_agent)
    ctx_agent = AuthContext(u_agent.id, u_agent.username, ROLE_AI_AGENT, "agent", token=t_agent)

    # Customer
    c = env["crm"].create_customer(Customer(first_name="Test", last_name="Customer", email="cust@example.com"), ctx_admin)
    u_cust = auth.create_user("cust_user", "Pass123!", "Customer User", "cust@example.com", role=ROLE_CUSTOMER, customer_id=c.id)
    t_cust = auth.create_token(u_cust)
    ctx_cust = AuthContext(u_cust.id, u_cust.username, ROLE_CUSTOMER, "human", customer_id=c.id, token=t_cust)

    return {
        "admin": ctx_admin,
        "manager": ctx_mgr,
        "pm": ctx_pm,
        "sales": ctx_sales,
        "tech": ctx_tech,
        "agent": ctx_agent,
        "customer": ctx_cust,
        "zero": ZeroPermissionActor(),
    }


@pytest.fixture
def sample_customer(env, actors):
    cust = Customer(
        first_name="Jane",
        last_name="Doe",
        phone="555-123-4567",
        email="jane.doe@example.com",
        service_address="742 Evergreen Terrace, Springfield, OR",
    )
    return env["crm"].create_customer(cust, actors["admin"])


@pytest.fixture
def sample_project(env, actors, sample_customer):
    proj = Project(
        customer_id=sample_customer.id,
        title="Basement Flood Restoration & Reconstruction",
        property_address="742 Evergreen Terrace, Springfield, OR",
        project_type="water_damage",
        stage=ProjectStage.INTAKE,
        status="planning",
        estimated_cost=8500.0,
        contract_amount=12000.0,
        insurance_carrier="State Farm",
        insurance_claim_number="CLM-982314-SF",
    )
    return env["crm"].create_project(proj, actors["pm"])


# ==============================================================================
# 1. Project Lifecycle & State Machine Tests
# ==============================================================================

def test_project_stage_canonical_definitions():
    """Verify canonical 10 stages and normalization rules."""
    assert len(ProjectStage.STAGE_ORDER) == 10
    assert ProjectStage.INTAKE == "intake"
    assert ProjectStage.ASSESSMENT_SCOPING == "assessment_scoping"
    assert ProjectStage.INSURANCE_APPROVAL == "insurance_approval"
    assert ProjectStage.SCHEDULED == "scheduled"
    assert ProjectStage.IN_PROGRESS == "in_progress"
    assert ProjectStage.QUALITY_INSPECTION == "quality_inspection"
    assert ProjectStage.FINAL_WALKTHROUGH == "final_walkthrough"
    assert ProjectStage.COMPLETED == "completed"
    assert ProjectStage.BILLED == "billed"
    assert ProjectStage.CLOSED == "closed"

    # Aliases normalization
    assert ProjectStage.normalize("scoping") == ProjectStage.ASSESSMENT_SCOPING
    assert ProjectStage.normalize("insurance") == ProjectStage.INSURANCE_APPROVAL
    assert ProjectStage.normalize("done") == ProjectStage.COMPLETED
    assert ProjectStage.normalize("In-Progress") == ProjectStage.IN_PROGRESS


def test_project_lifecycle_full_canonical_progression(env, actors, sample_project):
    """Test full sequential lifecycle progression from INTAKE to CLOSED."""
    ops = env["ops"]
    pm = actors["pm"]
    pid = sample_project.id

    # 1. INTAKE -> ASSESSMENT_SCOPING
    p1 = ops.transition_project_stage(pid, ProjectStage.ASSESSMENT_SCOPING, pm)
    assert p1.stage == ProjectStage.ASSESSMENT_SCOPING
    assert p1.status == "planning"
    assert p1.stage_entered_at is not None

    # Milestones should be auto-seeded
    ms = ops.list_milestones(pid, pm)
    assert len(ms) == 3

    # 2. ASSESSMENT_SCOPING -> INSURANCE_APPROVAL
    p2 = ops.transition_project_stage(pid, ProjectStage.INSURANCE_APPROVAL, pm)
    assert p2.stage == ProjectStage.INSURANCE_APPROVAL

    # 3. INSURANCE_APPROVAL -> SCHEDULED
    p3 = ops.transition_project_stage(pid, ProjectStage.SCHEDULED, pm)
    assert p3.stage == ProjectStage.SCHEDULED
    assert p3.status == "scheduled"

    # 4. SCHEDULED -> IN_PROGRESS
    # Add a work order first
    wo = WorkOrder(project_id=pid, title="Demolition & Extraction", trade="mitigation")
    ops.create_work_order(wo, pm)

    p4 = ops.transition_project_stage(pid, ProjectStage.IN_PROGRESS, pm)
    assert p4.stage == ProjectStage.IN_PROGRESS
    assert p4.status == "in_progress"

    # Complete the work order before moving to QA
    wos = ops.list_work_orders(pm, project_id=pid)
    ops.complete_work_order(wos[0].id, pm)

    # 5. IN_PROGRESS -> QUALITY_INSPECTION
    p5 = ops.transition_project_stage(pid, ProjectStage.QUALITY_INSPECTION, pm)
    assert p5.stage == ProjectStage.QUALITY_INSPECTION

    # 6. QUALITY_INSPECTION -> FINAL_WALKTHROUGH
    p6 = ops.transition_project_stage(pid, ProjectStage.FINAL_WALKTHROUGH, pm)
    assert p6.stage == ProjectStage.FINAL_WALKTHROUGH

    # 7. FINAL_WALKTHROUGH -> COMPLETED
    p7 = ops.transition_project_stage(pid, ProjectStage.COMPLETED, pm)
    assert p7.stage == ProjectStage.COMPLETED
    assert p7.status == "completed"
    assert p7.actual_completion is not None

    # 8. COMPLETED -> BILLED
    p8 = ops.transition_project_stage(pid, ProjectStage.BILLED, pm)
    assert p8.stage == ProjectStage.BILLED

    # 9. BILLED -> CLOSED
    p9 = ops.transition_project_stage(pid, ProjectStage.CLOSED, pm, reason="All payments collected")
    assert p9.stage == ProjectStage.CLOSED


def test_project_non_insurance_fast_path(env, actors, sample_customer):
    """Non-insurance jobs can bypass INSURANCE_APPROVAL straight to SCHEDULED."""
    ops = env["ops"]
    pm = actors["pm"]
    proj = env["crm"].create_project(
        Project(
            customer_id=sample_customer.id,
            title="Private Remodel Job",
            property_address="100 Elm St",
            contract_amount=5000.0,
            stage=ProjectStage.INTAKE,
        ),
        pm,
    )

    ops.transition_project_stage(proj.id, ProjectStage.ASSESSMENT_SCOPING, pm)
    # Direct transition from assessment to scheduled
    p_sched = ops.transition_project_stage(proj.id, ProjectStage.SCHEDULED, pm)
    assert p_sched.stage == ProjectStage.SCHEDULED


def test_project_illegal_stage_transitions(env, actors, sample_project):
    """Verify illegal transitions are rejected."""
    ops = env["ops"]
    pm = actors["pm"]
    pid = sample_project.id

    # Cannot jump from INTAKE directly to COMPLETED or CLOSED
    with pytest.raises(ValueError, match="Invalid stage transition"):
        ops.transition_project_stage(pid, ProjectStage.COMPLETED, pm)

    with pytest.raises(ValueError, match="Invalid stage transition"):
        ops.transition_project_stage(pid, ProjectStage.CLOSED, pm)


def test_project_on_hold_and_resume(env, actors, sample_project):
    """Test putting a project on hold and resuming back to active lifecycle."""
    ops = env["ops"]
    pm = actors["pm"]
    pid = sample_project.id

    ops.transition_project_stage(pid, ProjectStage.ASSESSMENT_SCOPING, pm)
    p_hold = ops.transition_project_stage(pid, ProjectStage.ON_HOLD, pm, notes="Awaiting customer decision on scope")
    assert p_hold.stage == ProjectStage.ON_HOLD
    assert p_hold.status == "on_hold"

    p_resumed = ops.transition_project_stage(pid, ProjectStage.ASSESSMENT_SCOPING, pm, notes="Resumed scoping")
    assert p_resumed.stage == ProjectStage.ASSESSMENT_SCOPING


def test_project_cancellation_requires_reason(env, actors, sample_project):
    """Cancelling a project requires a non-empty reason."""
    ops = env["ops"]
    pm = actors["pm"]
    pid = sample_project.id

    with pytest.raises(ValueError, match="Cancellation requires a non-empty reason"):
        ops.transition_project_stage(pid, ProjectStage.CANCELLED, pm, reason="")

    p_canc = ops.transition_project_stage(pid, ProjectStage.CANCELLED, pm, reason="Customer terminated contract")
    assert p_canc.stage == ProjectStage.CANCELLED
    assert p_canc.status == "cancelled"


def test_project_quality_inspection_gate_blocks_on_incomplete_work_orders(env, actors, sample_project):
    """Cannot transition to QUALITY_INSPECTION if work orders are still in progress."""
    ops = env["ops"]
    pm = actors["pm"]
    pid = sample_project.id

    ops.transition_project_stage(pid, ProjectStage.ASSESSMENT_SCOPING, pm)
    ops.transition_project_stage(pid, ProjectStage.SCHEDULED, pm)

    wo = ops.create_work_order(WorkOrder(project_id=pid, title="Drywall", trade="drywall"), pm)
    ops.transition_project_stage(pid, ProjectStage.IN_PROGRESS, pm)

    # Work order is still in draft / in_progress
    with pytest.raises(ValueError, match="work order\\(s\\) are not completed/verified"):
        ops.transition_project_stage(pid, ProjectStage.QUALITY_INSPECTION, pm)

    # Complete work order and transition succeeds
    ops.complete_work_order(wo.id, pm)
    p_qa = ops.transition_project_stage(pid, ProjectStage.QUALITY_INSPECTION, pm)
    assert p_qa.stage == ProjectStage.QUALITY_INSPECTION


# ==============================================================================
# 2. Milestone Dependencies Tests
# ==============================================================================

def test_milestone_dependency_graph(env, actors, sample_project):
    """Test milestone creation, dependencies, and blocked progression."""
    ops = env["ops"]
    pm = actors["pm"]
    pid = sample_project.id

    # Create parent milestone
    m1 = ops.create_milestone(
        ProjectMilestone(project_id=pid, name="Initial Moisture Mapping", stage=ProjectStage.ASSESSMENT_SCOPING),
        pm,
    )
    # Create dependent milestone
    m2 = ops.create_milestone(
        ProjectMilestone(
            project_id=pid,
            name="Containment & Equipment Staging",
            stage=ProjectStage.SCHEDULED,
            dependencies=[m1.id],
        ),
        pm,
    )

    # Attempting to complete m2 while m1 is PENDING must fail
    with pytest.raises(ValueError, match="Cannot progress milestone: prerequisite milestone"):
        ops.update_milestone_status(m2.id, MilestoneStatus.COMPLETED, pm)

    # Complete m1 first
    ops.complete_milestone(m1.id, pm)
    m1_updated = ops.get_milestone(m1.id, pm)
    assert m1_updated.status == MilestoneStatus.COMPLETED
    assert m1_updated.completion_date is not None

    # Now m2 can be completed
    ops.complete_milestone(m2.id, pm)
    m2_updated = ops.get_milestone(m2.id, pm)
    assert m2_updated.status == MilestoneStatus.COMPLETED


# ==============================================================================
# 3. Work Order Management & Numbering Tests
# ==============================================================================

def test_work_order_sequential_numbering(env, actors, sample_project):
    """Test auto-generation of sequential WO-0001, WO-0002 numbers."""
    ops = env["ops"]
    pm = actors["pm"]
    pid = sample_project.id

    wo1 = ops.create_work_order(WorkOrder(project_id=pid, title="Task 1", trade="mitigation"), pm)
    wo2 = ops.create_work_order(WorkOrder(project_id=pid, title="Task 2", trade="drywall"), pm)
    wo3 = ops.create_work_order(WorkOrder(project_id=pid, title="Task 3", trade="paint"), pm)

    assert wo1.work_order_number == "WO-0001"
    assert wo2.work_order_number == "WO-0002"
    assert wo3.work_order_number == "WO-0003"


def test_work_order_line_item_cost_calculation(env, actors, sample_project):
    """Verify total_cost is accurately computed from line items."""
    ops = env["ops"]
    pm = actors["pm"]
    pid = sample_project.id

    items = [
        {"description": "Water Extraction", "quantity": 500, "unit": "sqft", "unit_cost": 1.50},
        {"description": "Antimicrobial Treatment", "quantity": 500, "unit": "sqft", "unit_cost": 0.50},
    ]
    wo = ops.create_work_order(
        WorkOrder(project_id=pid, title="Extraction Job", trade="mitigation", line_items=items),
        pm,
    )
    # 500 * 1.50 = 750; 500 * 0.50 = 250; total = 1000.00
    assert wo.total_cost == 1000.00
    assert wo.line_items[0]["total_cost"] == 750.00
    assert wo.line_items[1]["total_cost"] == 250.00


def test_work_order_execution_lifecycle(env, actors, sample_project):
    """Test full work order execution state changes."""
    ops = env["ops"]
    pm = actors["pm"]
    pid = sample_project.id

    wo = ops.create_work_order(WorkOrder(project_id=pid, title="Plumbing Repair", trade="plumbing"), pm)
    assert wo.status == WorkOrderStatus.DRAFT

    # Accept
    wo_acc = ops.accept_work_order(wo.id, pm, notes="Confirmed start time")
    assert wo_acc.status == WorkOrderStatus.ACCEPTED
    assert wo_acc.accepted_at is not None

    # In Progress
    wo_prog = ops.update_work_order_execution_status(wo.id, WorkOrderStatus.IN_PROGRESS, pm)
    assert wo_prog.status == WorkOrderStatus.IN_PROGRESS
    assert wo_prog.actual_start is not None

    # Completed
    wo_comp = ops.complete_work_order(wo.id, pm, notes="Fixed copper pipe joint")
    assert wo_comp.status == WorkOrderStatus.COMPLETED
    assert wo_comp.completed_at is not None

    # Verified
    wo_ver = ops.verify_work_order(wo.id, pm, notes="Pressure test passed")
    assert wo_ver.status == WorkOrderStatus.VERIFIED
    assert wo_ver.verified_at is not None


# ==============================================================================
# 4. Subcontractor Matching & Dispatching Tests
# ==============================================================================

@pytest.fixture
def sample_subcontractors(env, actors):
    crm = env["crm"]
    admin = actors["admin"]

    # 1. Qualified Mitigation Sub (High Score)
    s1 = crm.create_subcontractor(
        Subcontractor(
            company_name="Apex Restoration Pros",
            primary_trade="mitigation",
            secondary_trades=["demolition", "drying"],
            service_area="Springfield",
            license_number="LIC-MIT-100",
            license_status="active",
            coi_received=1,
            coi_expiration="2027-12-31",
            general_liability="active",
            workers_comp="active",
            msa_signed=1,
            w9_received=1,
            dnc_status=0,
        ),
        admin,
    )

    # 2. Secondary Trade Sub
    s2 = crm.create_subcontractor(
        Subcontractor(
            company_name="General Reconstruction LLC",
            primary_trade="general_contractor",
            secondary_trades=["mitigation", "drywall"],
            service_area="Springfield",
            license_number="LIC-GC-200",
            license_status="active",
            coi_received=1,
            coi_expiration="2027-12-31",
            msa_signed=1,
            w9_received=1,
            dnc_status=0,
        ),
        admin,
    )

    # 3. Expired Insurance Sub
    s3 = crm.create_subcontractor(
        Subcontractor(
            company_name="Budget Mitigation",
            primary_trade="mitigation",
            coi_received=1,
            coi_expiration="2024-01-01",  # Expired
            license_number="LIC-BM-300",
            dnc_status=0,
        ),
        admin,
    )

    # 4. DNC Sub
    s4 = crm.create_subcontractor(
        Subcontractor(
            company_name="Banned Contractor Inc",
            primary_trade="mitigation",
            dnc_status=1,  # Do not contact
        ),
        admin,
    )

    return {"apex": s1, "general": s2, "expired": s3, "dnc": s4}


def test_subcontractor_trade_matching_and_ranking(env, actors, sample_subcontractors):
    """Test ranking calculation and compliance filtering."""
    ops = env["ops"]
    pm = actors["pm"]

    matches = ops.match_subcontractors_for_trade("mitigation", pm, service_area="Springfield")
    # Expired and DNC subs must be disqualified / excluded
    match_ids = [m["subcontractor_id"] for m in matches]
    assert sample_subcontractors["apex"].id in match_ids
    assert sample_subcontractors["general"].id in match_ids
    assert sample_subcontractors["expired"].id not in match_ids
    assert sample_subcontractors["dnc"].id not in match_ids

    # Apex (primary trade) should rank higher than General (secondary trade)
    assert matches[0]["subcontractor_id"] == sample_subcontractors["apex"].id
    assert matches[0]["match_score"] > matches[1]["match_score"]


def test_dispatch_work_order_enforces_compliance(env, actors, sample_project, sample_subcontractors):
    """Test dispatching to compliant sub succeeds and non-compliant sub fails."""
    ops = env["ops"]
    pm = actors["pm"]
    pid = sample_project.id

    wo = ops.create_work_order(WorkOrder(project_id=pid, title="Mitigation", trade="mitigation"), pm)

    # Dispatch to DNC sub fails
    with pytest.raises(ValueError, match="Do-Not-Contact"):
        ops.dispatch_work_order(wo.id, sample_subcontractors["dnc"].id, pm)

    # Dispatch to expired COI sub fails without override
    with pytest.raises(ValueError, match="COI expired"):
        ops.dispatch_work_order(wo.id, sample_subcontractors["expired"].id, pm)

    # Dispatch to qualified sub succeeds
    disp_wo = ops.dispatch_work_order(
        wo.id,
        sample_subcontractors["apex"].id,
        pm,
        scheduled_start="2026-09-01T08:00:00Z",
        scheduled_end="2026-09-01T17:00:00Z",
        instructions="Access key in lockbox 1234",
    )
    assert disp_wo.status == WorkOrderStatus.DISPATCHED
    assert disp_wo.assigned_subcontractor_id == sample_subcontractors["apex"].id
    assert disp_wo.dispatched_at is not None


# ==============================================================================
# 5. Equipment Tracking & Deployment Tests
# ==============================================================================

def test_equipment_deployment_and_return_lifecycle(env, actors, sample_project):
    """Test deploying equipment with moisture readings and returning it."""
    ops = env["ops"]
    pm = actors["pm"]
    pid = sample_project.id

    eq = ops.create_equipment(
        Equipment(
            asset_tag="EQ-DH-101",
            name="Phoenix DryMAX XL LGR Dehumidifier",
            category=EquipmentCategory.DEHUMIDIFIER,
            daily_rate=75.00,
        ),
        pm,
    )
    assert eq.status == EquipmentStatus.AVAILABLE

    # Deploy equipment
    dep = ops.deploy_equipment(
        equipment_id=eq.id,
        project_id=pid,
        actor=pm,
        initial_reading="RH: 85%, Moisture: 44% WME",
        condition_out="good",
        notes="Placed in main basement living area",
    )
    assert dep.deployed_at is not None
    assert dep.initial_reading == "RH: 85%, Moisture: 44% WME"

    # Equipment should now be marked deployed and tied to current project
    eq_deployed = ops.get_equipment(eq.id, pm)
    assert eq_deployed.status == EquipmentStatus.DEPLOYED
    assert eq_deployed.current_project_id == pid

    # Double deployment must be rejected
    with pytest.raises(ValueError, match="is not available"):
        ops.deploy_equipment(eq.id, pid, pm)

    # Return equipment
    ret_dep = ops.return_equipment(
        deployment_id=dep.id,
        actor=pm,
        final_reading="RH: 35%, Moisture: 11% WME",
        condition_in="good",
        notes="Filter cleaned",
    )
    assert ret_dep.returned_at is not None
    assert ret_dep.final_reading == "RH: 35%, Moisture: 11% WME"

    # Equipment status should be reset to available
    eq_returned = ops.get_equipment(eq.id, pm)
    assert eq_returned.status == EquipmentStatus.AVAILABLE
    assert eq_returned.current_project_id is None


def test_equipment_return_damaged_marks_maintenance(env, actors, sample_project):
    """Returning damaged equipment marks status as maintenance."""
    ops = env["ops"]
    pm = actors["pm"]
    pid = sample_project.id

    eq = ops.create_equipment(
        Equipment(
            asset_tag="EQ-AM-202",
            name="Centrifugal Air Mover",
            category=EquipmentCategory.AIR_MOVER,
            daily_rate=30.00,
        ),
        pm,
    )
    dep = ops.deploy_equipment(eq.id, pid, pm)

    ops.return_equipment(dep.id, pm, condition_in="damaged", mark_for_maintenance=True)
    eq_maint = ops.get_equipment(eq.id, pm)
    assert eq_maint.status == EquipmentStatus.MAINTENANCE


# ==============================================================================
# 6. Granular RBAC & Zero-Permission Enforcement Tests
# ==============================================================================

def test_rbac_zero_permission_actor_rejections(env, actors, sample_project):
    """ZeroPermissionActor must be rejected by all operations methods."""
    ops = env["ops"]
    zero = actors["zero"]
    pid = sample_project.id

    with pytest.raises(PermissionError):
        ops.get_project(pid, zero)

    with pytest.raises(PermissionError):
        ops.transition_project_stage(pid, ProjectStage.ASSESSMENT_SCOPING, zero)

    with pytest.raises(PermissionError):
        ops.create_milestone(ProjectMilestone(project_id=pid, name="Test"), zero)

    with pytest.raises(PermissionError):
        ops.create_work_order(WorkOrder(project_id=pid, title="Test", trade="paint"), zero)

    with pytest.raises(PermissionError):
        ops.match_subcontractors_for_trade("mitigation", zero)

    with pytest.raises(PermissionError):
        ops.create_equipment(Equipment(asset_tag="EQ-001", name="Mover"), zero)


def test_technician_role_permissions(env, actors, sample_project):
    """Technicians have read/write operations (readings, execution), but cannot manage projects or dispatch."""
    ops = env["ops"]
    tech = actors["tech"]
    pm = actors["pm"]
    pid = sample_project.id

    # Tech CANNOT transition project lifecycle
    with pytest.raises(PermissionError, match="manage project lifecycle"):
        ops.transition_project_stage(pid, ProjectStage.ASSESSMENT_SCOPING, tech)

    # Tech CANNOT dispatch work orders
    wo = ops.create_work_order(WorkOrder(project_id=pid, title="Demo", trade="mitigation"), pm)
    with pytest.raises(PermissionError, match="dispatch work orders"):
        ops.dispatch_work_order(wo.id, 1, tech)

    # Tech CAN update work order execution status
    updated_wo = ops.update_work_order_execution_status(wo.id, WorkOrderStatus.IN_PROGRESS, tech)
    assert updated_wo.status == WorkOrderStatus.IN_PROGRESS


def test_customer_isolation_on_operations(env, actors, sample_project):
    """Customers cannot access other customers' project summaries or internal work orders."""
    ops = env["ops"]
    cust = actors["customer"]  # customer_id = 1
    sample_project.customer_id = 999  # Different customer

    with pytest.raises(PermissionError, match="other customers' projects"):
        ops.get_project(sample_project.id, cust)


# ==============================================================================
# 7. REST API Endpoints Router Tests
# ==============================================================================

def test_api_project_stage_transition(env, actors, sample_project):
    """Test POST /api/v1/operations/projects/{id}/stage."""
    router = env["router"]
    headers = {"Authorization": f"Bearer {actors['pm'].token}"}
    pid = sample_project.id

    body = json.dumps({"target_stage": "assessment_scoping", "notes": "On-site assessment complete"}).encode()
    status, _, data = router.handle_request("POST", f"/api/v1/operations/projects/{pid}/stage", headers, body)
    assert status == 200
    assert data["status"] == "ok"
    assert data["project"]["stage"] == "assessment_scoping"


def test_api_project_summary(env, actors, sample_project):
    """Test GET /api/v1/operations/projects/{id}/summary."""
    router = env["router"]
    headers = {"Authorization": f"Bearer {actors['pm'].token}"}
    pid = sample_project.id

    status, _, data = router.handle_request("GET", f"/api/v1/operations/projects/{pid}/summary", headers, b"")
    assert status == 200
    assert "milestone_summary" in data
    assert "work_order_summary" in data
    assert "equipment_summary" in data


def test_api_work_order_crud_and_dispatch(env, actors, sample_project, sample_subcontractors):
    """Test work order endpoints: POST, GET, dispatch, accept, complete."""
    router = env["router"]
    headers = {"Authorization": f"Bearer {actors['pm'].token}"}
    pid = sample_project.id

    # Create Work Order
    wo_body = json.dumps({
        "project_id": pid,
        "title": "Air Scrubber & Moisture Extraction",
        "trade": "mitigation",
        "line_items": [{"description": "Extraction", "quantity": 100, "unit": "sqft", "unit_cost": 2.00}],
    }).encode()
    status, _, data = router.handle_request("POST", "/api/v1/operations/work-orders", headers, wo_body)
    assert status == 201
    wo_id = data["work_order"]["id"]
    assert data["work_order"]["total_cost"] == 200.00

    # Dispatch
    disp_body = json.dumps({
        "subcontractor_id": sample_subcontractors["apex"].id,
        "scheduled_start": "2026-09-02T08:00:00Z",
    }).encode()
    status, _, data = router.handle_request("POST", f"/api/v1/operations/work-orders/{wo_id}/dispatch", headers, disp_body)
    assert status == 200
    assert data["status"] == "dispatched"

    # Accept
    acc_body = json.dumps({"notes": "Crew assigned"}).encode()
    status, _, data = router.handle_request("POST", f"/api/v1/operations/work-orders/{wo_id}/accept", headers, acc_body)
    assert status == 200
    assert data["status"] == "accepted"


def test_api_subcontractor_matching_endpoint(env, actors, sample_subcontractors):
    """Test GET /api/v1/operations/subcontractors/match."""
    router = env["router"]
    headers = {"Authorization": f"Bearer {actors['pm'].token}"}

    status, _, data = router.handle_request("GET", "/api/v1/operations/subcontractors/match?trade=mitigation", headers, b"")
    assert status == 200
    assert "matches" in data
    assert len(data["matches"]) >= 1
    assert data["matches"][0]["primary_trade"] == "mitigation"


def test_api_equipment_deploy_and_return(env, actors, sample_project):
    """Test equipment deployment & return via REST API."""
    router = env["router"]
    headers = {"Authorization": f"Bearer {actors['pm'].token}"}
    pid = sample_project.id

    # Create Equipment
    eq_body = json.dumps({
        "asset_tag": "EQ-REST-99",
        "name": "Industrial Dehumidifier",
        "category": "dehumidifier",
        "daily_rate": 80.0,
    }).encode()
    status, _, data = router.handle_request("POST", "/api/v1/operations/equipment", headers, eq_body)
    assert status == 201
    eq_id = data["equipment"]["id"]

    # Deploy
    deploy_body = json.dumps({
        "equipment_id": eq_id,
        "project_id": pid,
        "initial_reading": "Moisture 40%",
    }).encode()
    status, _, data = router.handle_request("POST", "/api/v1/operations/equipment/deploy", headers, deploy_body)
    assert status == 200
    dep_id = data["deployment"]["id"]

    # Return
    return_body = json.dumps({
        "deployment_id": dep_id,
        "final_reading": "Moisture 12%",
        "condition_in": "good",
    }).encode()
    status, _, data = router.handle_request("POST", "/api/v1/operations/equipment/return", headers, return_body)
    assert status == 200
    assert data["status"] == "returned"
