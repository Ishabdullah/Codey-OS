"""
Comprehensive unit test suite for Track B / Phase B3: CRM & Sales Domain Engine in Restoricon Core.

Tests cover:
1. Data models & constants (PipelineStage, Lead, Opportunity, Task).
2. Lead qualification deterministic scoring (5 dimensions, grades, DB updates).
3. Pipeline stage transitions (canonical stages, lost_reason validation on LOST, probability & stage_entered_at).
4. Insurance tracking (carrier, claim_number, adjuster info, deductible, status).
5. Pipeline summary aggregation (stage metrics, totals, weighted value, win rate).
6. Cadence task generation and task lifecycle management.
7. REST API endpoints (pipeline, opportunities, leads scoring, tasks, cadence, RBAC enforcement).
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
    Lead,
    Opportunity,
    PipelineStage,
    STAGE_DEFAULT_PROBABILITIES,
    STAGE_ORDER,
    Task,
)
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.scheduling_service import SchedulingService


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    comm = CommunicationService(db)
    crm = CRMService(db, audit)
    sched = SchedulingService(db, audit)
    auto = AutomationService(db, audit)
    router = APIRouter(auth, crm, comm, audit, sched, auto)

    # Create users for all roles
    admin_user = auth.create_user("admin_user", "Pass123!", "Admin User", "admin@test.com", ROLE_ADMIN)
    admin_actor_tmp = AuthContext(admin_user.id, "admin_user", ROLE_ADMIN, "human")
    demo_cust = crm.create_customer(Customer(first_name="Cust", last_name="User", email="cust@test.com"), admin_actor_tmp)

    manager_user = auth.create_user("mgr_user", "Pass123!", "Manager User", "mgr@test.com", ROLE_MANAGER)
    sales_user = auth.create_user("sales_user", "Pass123!", "Sales User", "sales@test.com", ROLE_SALES)
    pm_user = auth.create_user("pm_user", "Pass123!", "PM User", "pm@test.com", ROLE_PROJECT_MANAGER)
    tech_user = auth.create_user("tech_user", "Pass123!", "Tech User", "tech@test.com", ROLE_TECHNICIAN)
    cust_user = auth.create_user("cust_user", "Pass123!", "Cust User", "cust@test.com", ROLE_CUSTOMER, customer_id=demo_cust.id)
    agent_user = auth.create_user("agent_user", "Pass123!", "Agent User", "agent@test.com", ROLE_AI_AGENT)

    tokens = {
        ROLE_ADMIN: auth.create_token(admin_user),
        ROLE_MANAGER: auth.create_token(manager_user),
        ROLE_SALES: auth.create_token(sales_user),
        ROLE_PROJECT_MANAGER: auth.create_token(pm_user),
        ROLE_TECHNICIAN: auth.create_token(tech_user),
        ROLE_CUSTOMER: auth.create_token(cust_user),
        ROLE_AI_AGENT: auth.create_token(agent_user),
    }

    actors = {
        ROLE_ADMIN: AuthContext(admin_user.id, "admin_user", ROLE_ADMIN, "human", token=tokens[ROLE_ADMIN]),
        ROLE_MANAGER: AuthContext(manager_user.id, "mgr_user", ROLE_MANAGER, "human", token=tokens[ROLE_MANAGER]),
        ROLE_SALES: AuthContext(sales_user.id, "sales_user", ROLE_SALES, "human", token=tokens[ROLE_SALES]),
        ROLE_PROJECT_MANAGER: AuthContext(pm_user.id, "pm_user", ROLE_PROJECT_MANAGER, "human", token=tokens[ROLE_PROJECT_MANAGER]),
        ROLE_TECHNICIAN: AuthContext(tech_user.id, "tech_user", ROLE_TECHNICIAN, "human", token=tokens[ROLE_TECHNICIAN]),
        ROLE_CUSTOMER: AuthContext(cust_user.id, "cust_user", ROLE_CUSTOMER, "human", token=tokens[ROLE_CUSTOMER]),
        ROLE_AI_AGENT: AuthContext(agent_user.id, "agent_user", ROLE_AI_AGENT, "agent", token=tokens[ROLE_AI_AGENT]),
    }

    return {
        "db": db,
        "auth": auth,
        "audit": audit,
        "crm": crm,
        "router": router,
        "actors": actors,
        "tokens": tokens,
    }


# ==========================================
# 1. DATA MODELS & CONSTANTS
# ==========================================

def test_pipeline_stages_and_constants():
    assert len(PipelineStage.STAGE_ORDER) == 9
    assert len(STAGE_ORDER) == 9
    expected = [
        PipelineStage.NEW_LEAD,
        PipelineStage.CONTACTED,
        PipelineStage.APPOINTMENT_SET,
        PipelineStage.ESTIMATE_SCHEDULED,
        PipelineStage.ESTIMATE_SENT,
        PipelineStage.PROPOSAL_SENT,
        PipelineStage.NEGOTIATION,
        PipelineStage.WON,
        PipelineStage.LOST,
    ]
    assert PipelineStage.STAGE_ORDER == expected

    # Default probabilities
    assert STAGE_DEFAULT_PROBABILITIES[PipelineStage.NEW_LEAD] == 0.10
    assert STAGE_DEFAULT_PROBABILITIES[PipelineStage.WON] == 1.0
    assert STAGE_DEFAULT_PROBABILITIES[PipelineStage.LOST] == 0.0

    # Stage normalization
    assert PipelineStage.normalize("New Lead") == PipelineStage.NEW_LEAD
    assert PipelineStage.normalize("proposal sent") == PipelineStage.PROPOSAL_SENT
    assert PipelineStage.normalize("estimate") == PipelineStage.ESTIMATE_SCHEDULED
    assert PipelineStage.is_valid("negotiation") is True
    assert PipelineStage.is_valid("invalid_stage_xyz") is False


# ==========================================
# 2. LEAD QUALIFICATION SCORING
# ==========================================

def test_lead_qualification_scoring_algorithm(env):
    crm = env["crm"]
    actor = env["actors"][ROLE_SALES]

    # Create customer & lead
    cust = crm.create_customer(Customer(first_name="Jane", last_name="Smith", phone="8605551234"), actor)
    lead = crm.create_lead(
        Lead(
            customer_id=cust.id,
            source="website",
            property_type="commercial",
            project_scope="full_restoration",
            urgency_level="emergency",
            insurance_status="claim_filed",
        ),
        actor,
    )

    # Score Hot Lead: commercial (15) + full_restoration (25) + emergency (25) + claim_filed (20) + default resp (10) = 95
    score_res = crm.score_lead(lead.id, actor, factors={"responsiveness": "high"})
    assert score_res["score"] >= 95
    assert score_res["grade"] == "Hot"
    assert score_res["score_factors"]["project_scope"]["points"] == 25
    assert score_res["score_factors"]["property_type"]["points"] == 15
    assert score_res["score_factors"]["urgency_level"]["points"] == 25
    assert score_res["score_factors"]["insurance_status"]["points"] == 20
    assert score_res["score_factors"]["responsiveness"]["points"] == 15

    # Check that lead was updated in DB
    refetched = crm.get_lead(lead.id, actor)
    assert refetched.score == score_res["score"]
    assert refetched.score_factors["grade"] == "Hot"


def test_lead_qualification_scoring_grades(env):
    crm = env["crm"]
    actor = env["actors"][ROLE_SALES]

    # Warm Lead: residential (12) + water_mitigation (20) + high (20) + filing_claim (15) + medium resp (10) = 77
    res_warm = crm.score_lead(
        {
            "property_type": "residential",
            "project_scope": "water_mitigation",
            "urgency_level": "high",
            "insurance_status": "filing_claim",
            "responsiveness": "medium",
        },
        actor,
    )
    assert res_warm["score"] == 77
    assert res_warm["grade"] == "Warm"

    # Cold Lead: condo (8) + repairs (12) + medium (12) + self_pay (12) + low resp (5) = 49
    res_cold = crm.score_lead(
        {
            "property_type": "condo",
            "project_scope": "repairs",
            "urgency_level": "medium",
            "insurance_status": "self_pay",
            "responsiveness": "low",
        },
        actor,
    )
    assert res_cold["score"] == 49
    assert res_cold["grade"] == "Cold"

    # Unqualified Lead: other (5) + minor (5) + low (5) + uninsured (5) + low resp (5) = 25
    res_unqual = crm.score_lead(
        {
            "property_type": "other",
            "project_scope": "minor inspection",
            "urgency_level": "low",
            "insurance_status": "uninsured",
            "responsiveness": "low",
        },
        actor,
    )
    assert res_unqual["score"] <= 30
    assert res_unqual["grade"] == "Unqualified"


# ==========================================
# 3. OPPORTUNITY MANAGEMENT & INSURANCE TRACKING
# ==========================================

def test_opportunity_creation_with_insurance(env):
    crm = env["crm"]
    actor = env["actors"][ROLE_SALES]

    cust = crm.create_customer(Customer(first_name="Bob", last_name="Miller"), actor)
    opp = Opportunity(
        customer_id=cust.id,
        title="Fire Damage Reconstruction",
        estimated_value=85000.0,
        pipeline_stage=PipelineStage.NEW_LEAD,
        insurance_carrier="Travelers",
        claim_number="CLM-987654",
        adjuster_name="Sarah Connor",
        adjuster_phone="8605559876",
        adjuster_email="sconnor@travelers.com",
        deductible=1000.0,
        insurance_claim_status="adjuster_assigned",
    )
    created = crm.create_opportunity(opp, actor)
    assert created.id is not None
    assert created.probability == 0.10
    assert created.insurance_carrier == "Travelers"
    assert created.claim_number == "CLM-987654"
    assert created.adjuster_name == "Sarah Connor"
    assert created.deductible == 1000.0
    assert created.stage_entered_at is not None

    # Fetch and verify persistence
    fetched = crm.get_opportunity(created.id, actor)
    assert fetched is not None
    assert fetched.insurance_carrier == "Travelers"
    assert fetched.claim_number == "CLM-987654"
    assert fetched.adjuster_phone == "8605559876"


# ==========================================
# 4. PIPELINE STAGE TRANSITIONS & LOST REASON VALIDATION
# ==========================================

def test_pipeline_stage_transitions(env):
    crm = env["crm"]
    actor = env["actors"][ROLE_SALES]

    cust = crm.create_customer(Customer(first_name="Alice", last_name="Wonderland"), actor)
    opp = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Basement Flood", estimated_value=12000.0),
        actor,
    )

    # Transition to CONTACTED
    t1 = crm.transition_opportunity_stage(opp.id, PipelineStage.CONTACTED, actor)
    assert t1.pipeline_stage == PipelineStage.CONTACTED
    assert t1.probability == 0.20

    # Transition to ESTIMATE_SENT
    t2 = crm.transition_opportunity_stage(opp.id, PipelineStage.ESTIMATE_SENT, actor)
    assert t2.pipeline_stage == PipelineStage.ESTIMATE_SENT
    assert t2.probability == 0.60

    # Transition to WON
    t3 = crm.transition_opportunity_stage(opp.id, PipelineStage.WON, actor)
    assert t3.pipeline_stage == PipelineStage.WON
    assert t3.probability == 1.0


def test_transition_to_lost_requires_reason(env):
    crm = env["crm"]
    actor = env["actors"][ROLE_SALES]

    cust = crm.create_customer(Customer(first_name="Mark", last_name="Twain"), actor)
    opp = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Storm Damage", estimated_value=20000.0),
        actor,
    )

    # Transitioning to LOST without lost_reason must raise ValueError
    with pytest.raises(ValueError, match="lost_reason is required"):
        crm.transition_opportunity_stage(opp.id, PipelineStage.LOST, actor)

    with pytest.raises(ValueError, match="lost_reason is required"):
        crm.transition_opportunity_stage(opp.id, PipelineStage.LOST, actor, lost_reason="   ")

    # Transitioning to LOST with lost_reason succeeds
    lost_opp = crm.transition_opportunity_stage(
        opp.id, PipelineStage.LOST, actor, lost_reason="Price too high / Competitor chosen"
    )
    assert lost_opp.pipeline_stage == PipelineStage.LOST
    assert lost_opp.probability == 0.0
    assert lost_opp.lost_reason == "Price too high / Competitor chosen"


def test_invalid_stage_transition_raises_error(env):
    crm = env["crm"]
    actor = env["actors"][ROLE_SALES]

    cust = crm.create_customer(Customer(first_name="Invalid", last_name="Stage"), actor)
    opp = crm.create_opportunity(Opportunity(customer_id=cust.id, title="Test Opp"), actor)

    with pytest.raises(ValueError, match="Invalid pipeline stage"):
        crm.transition_opportunity_stage(opp.id, "stage_that_does_not_exist", actor)


# ==========================================
# 5. AUTOMATED CADENCE TASK GENERATION & TASK LIFECYCLE
# ==========================================

def test_cadence_task_generation(env):
    crm = env["crm"]
    actor = env["actors"][ROLE_SALES]

    cust = crm.create_customer(Customer(first_name="Diana", last_name="Prince"), actor)
    opp = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Roof Leak Repair", estimated_value=15000.0),
        actor,
    )

    # Transitioning to ESTIMATE_SENT triggers cadence task
    crm.transition_opportunity_stage(opp.id, PipelineStage.ESTIMATE_SENT, actor)

    tasks = crm.list_tasks(actor, opportunity_id=opp.id)
    assert len(tasks) >= 1
    estimate_task = next((t for t in tasks if t.rule_name == "cadence_estimate_sent"), None)
    assert estimate_task is not None
    assert estimate_task.task_type == "estimate_follow_up"
    assert estimate_task.priority == "high"
    assert estimate_task.status == "pending"

    # Complete the task
    completed = crm.complete_task(estimate_task.id, actor, notes="Called customer, review scheduled.")
    assert completed.status == "completed"
    assert completed.completed_at is not None
    assert "Called customer" in completed.notes


def test_custom_task_crud(env):
    crm = env["crm"]
    actor = env["actors"][ROLE_SALES]

    cust = crm.create_customer(Customer(first_name="Clark", last_name="Kent"), actor)
    task = Task(
        title="Follow up on moisture meter reading",
        description="Verify moisture levels dropped below 15%",
        task_type="inspection",
        priority="urgent",
        customer_id=cust.id,
    )
    created = crm.create_task(task, actor)
    assert created.id is not None
    assert created.priority == "urgent"

    # Update task
    updated = crm.update_task(created.id, {"priority": "medium", "notes": "Reading completed"}, actor)
    assert updated.priority == "medium"
    assert updated.notes == "Reading completed"


# ==========================================
# 6. PIPELINE SUMMARY AGGREGATION
# ==========================================

def test_pipeline_summary_aggregation(env):
    crm = env["crm"]
    actor = env["actors"][ROLE_SALES]

    cust = crm.create_customer(Customer(first_name="Bruce", last_name="Wayne"), actor)

    # Create opps in various stages
    o1 = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Opp 1", estimated_value=10000.0, pipeline_stage=PipelineStage.NEW_LEAD),
        actor,
    )
    o2 = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Opp 2", estimated_value=20000.0, pipeline_stage=PipelineStage.ESTIMATE_SENT),
        actor,
    )
    o3 = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Opp 3", estimated_value=50000.0, pipeline_stage=PipelineStage.WON),
        actor,
    )
    o4 = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Opp 4", estimated_value=15000.0, pipeline_stage=PipelineStage.NEW_LEAD),
        actor,
    )
    crm.transition_opportunity_stage(o4.id, PipelineStage.LOST, actor, lost_reason="Customer postponed project")

    summary = crm.get_pipeline_summary(actor)
    assert summary["total_deals"] == 4
    assert summary["won_deals"] == 1
    assert summary["won_value"] == 50000.0
    assert summary["lost_deals"] == 1
    assert summary["lost_value"] == 15000.0
    # Win rate = 1 / (1 + 1) = 0.5
    assert summary["win_rate"] == 0.5

    # Check stage breakdowns
    stages = summary["stages"]
    assert stages[PipelineStage.NEW_LEAD]["count"] == 1
    assert stages[PipelineStage.NEW_LEAD]["total_value"] == 10000.0
    assert stages[PipelineStage.ESTIMATE_SENT]["count"] == 1
    assert stages[PipelineStage.ESTIMATE_SENT]["total_value"] == 20000.0
    assert stages[PipelineStage.WON]["count"] == 1


# ==========================================
# 7. REST API ENDPOINTS & RBAC
# ==========================================

def test_api_pipeline_summary(env):
    router = env["router"]
    token = env["tokens"][ROLE_SALES]

    status, _, data = router.handle_request(
        "GET",
        "/api/v1/crm/pipeline",
        {"Authorization": f"Bearer {token}"},
        b"",
    )
    assert status == 200
    assert "pipeline" in data
    assert "total_deals" in data["pipeline"]


def test_api_opportunity_transitions_and_updates(env):
    router = env["router"]
    token = env["tokens"][ROLE_SALES]

    # Create customer first
    s, _, c_data = router.handle_request(
        "POST",
        "/api/v1/customers",
        {"Authorization": f"Bearer {token}"},
        json.dumps({"first_name": "API", "last_name": "Tester"}).encode("utf-8"),
    )
    assert s == 201
    cust_id = c_data["customer"]["id"]

    # POST opportunity
    s, _, o_data = router.handle_request(
        "POST",
        "/api/v1/opportunities",
        {"Authorization": f"Bearer {token}"},
        json.dumps({
            "customer_id": cust_id,
            "title": "API Lead Opp",
            "estimated_value": 30000.0,
            "pipeline_stage": PipelineStage.NEW_LEAD,
        }).encode("utf-8"),
    )
    assert s == 201
    opp_id = o_data["opportunity"]["id"]

    # GET opportunity by id
    s, _, get_opp = router.handle_request(
        "GET",
        f"/api/v1/opportunities/{opp_id}",
        {"Authorization": f"Bearer {token}"},
        b"",
    )
    assert s == 200
    assert get_opp["opportunity"]["title"] == "API Lead Opp"

    # POST transition to PROPOSAL_SENT
    s, _, t_data = router.handle_request(
        "POST",
        f"/api/v1/opportunities/{opp_id}/transition",
        {"Authorization": f"Bearer {token}"},
        json.dumps({"stage": PipelineStage.PROPOSAL_SENT}).encode("utf-8"),
    )
    assert s == 200
    assert t_data["opportunity"]["pipeline_stage"] == PipelineStage.PROPOSAL_SENT
    assert t_data["opportunity"]["probability"] == 0.70

    # POST transition to LOST without reason -> 400
    s, _, err_data = router.handle_request(
        "POST",
        f"/api/v1/opportunities/{opp_id}/transition",
        {"Authorization": f"Bearer {token}"},
        json.dumps({"stage": PipelineStage.LOST}).encode("utf-8"),
    )
    assert s == 400
    assert "lost_reason" in err_data["error"]

    # POST transition to LOST with reason -> 200
    s, _, lost_data = router.handle_request(
        "POST",
        f"/api/v1/opportunities/{opp_id}/transition",
        {"Authorization": f"Bearer {token}"},
        json.dumps({"stage": PipelineStage.LOST, "lost_reason": "Price out of budget"}).encode("utf-8"),
    )
    assert s == 200
    assert lost_data["opportunity"]["pipeline_stage"] == PipelineStage.LOST
    assert lost_data["opportunity"]["lost_reason"] == "Price out of budget"


def test_api_lead_scoring(env):
    router = env["router"]
    token = env["tokens"][ROLE_SALES]

    # Create lead
    s, _, lead_data = router.handle_request(
        "POST",
        "/api/v1/leads",
        {"Authorization": f"Bearer {token}"},
        json.dumps({
            "source": "website",
            "property_type": "residential",
            "project_scope": "mold_remediation",
            "urgency_level": "emergency",
            "insurance_status": "claim_filed",
        }).encode("utf-8"),
    )
    assert s == 201
    lead_id = lead_data["lead"]["id"]

    # GET score
    s, _, score_data = router.handle_request(
        "GET",
        f"/api/v1/leads/{lead_id}/score",
        {"Authorization": f"Bearer {token}"},
        b"",
    )
    assert s == 200
    assert score_data["grade"] in ["Hot", "Warm"]
    assert score_data["score"] > 60

    # POST score with overrides
    s, _, rescore_data = router.handle_request(
        "POST",
        f"/api/v1/leads/{lead_id}/score",
        {"Authorization": f"Bearer {token}"},
        json.dumps({"urgency_level": "low", "responsiveness": "low"}).encode("utf-8"),
    )
    assert s == 200
    assert rescore_data["score"] < score_data["score"]


def test_api_tasks_and_cadence(env):
    router = env["router"]
    token = env["tokens"][ROLE_SALES]

    # Create Task
    s, _, task_data = router.handle_request(
        "POST",
        "/api/v1/crm/tasks",
        {"Authorization": f"Bearer {token}"},
        json.dumps({
            "title": "Call adjuster regarding line item approval",
            "task_type": "phone_call",
            "priority": "high",
        }).encode("utf-8"),
    )
    assert s == 201
    task_id = task_data["task"]["id"]

    # Complete Task
    s, _, comp_data = router.handle_request(
        "POST",
        f"/api/v1/crm/tasks/{task_id}/complete",
        {"Authorization": f"Bearer {token}"},
        json.dumps({"notes": "Adjuster approved supplementary drying equipment."}).encode("utf-8"),
    )
    assert s == 200
    assert comp_data["task"]["status"] == "completed"

    # List tasks
    s, _, list_data = router.handle_request(
        "GET",
        "/api/v1/crm/tasks?status=completed",
        {"Authorization": f"Bearer {token}"},
        b"",
    )
    assert s == 200
    assert any(t["id"] == task_id for t in list_data["tasks"])


def test_rbac_crm_permissions(env):
    router = env["router"]
    tech_token = env["tokens"][ROLE_TECHNICIAN]
    cust_token = env["tokens"][ROLE_CUSTOMER]
    admin_token = env["tokens"][ROLE_ADMIN]

    # Technician attempting to manage pipeline summary -> 403
    s, _, data = router.handle_request(
        "GET",
        "/api/v1/crm/pipeline",
        {"Authorization": f"Bearer {tech_token}"},
        b"",
    )
    assert s == 403

    # Customer attempting to access CRM tasks -> 403
    s, _, data = router.handle_request(
        "GET",
        "/api/v1/crm/tasks",
        {"Authorization": f"Bearer {cust_token}"},
        b"",
    )
    assert s == 403

    # Admin allowed -> 200
    s, _, data = router.handle_request(
        "GET",
        "/api/v1/crm/pipeline",
        {"Authorization": f"Bearer {admin_token}"},
        b"",
    )
    assert s == 200
