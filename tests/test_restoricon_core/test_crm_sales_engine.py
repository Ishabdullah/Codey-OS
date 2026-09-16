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
    PERM_READ_TEAM_SALES_DATA,
    ROLE_ADMIN,
    ROLE_AI_AGENT,
    ROLE_CUSTOMER,
    ROLE_MANAGER,
    ROLE_PROJECT_MANAGER,
    ROLE_SALES,
    ROLE_SALES_MANAGER,
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
from restoricon_core.services.crm_service import CRMService, ClaimConflictError
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


# ==========================================
# 8. NEW-533: PERM_READ_TEAM_SALES_DATA NARROWING
# ==========================================

def _second_sales_actor(env):
    """Creates a second, independent `sales`-role user (actor B) so
    cross-actor narrowing can be tested against a distinct assigned_user_id,
    without touching the shared `env` fixture's single sales_user."""
    auth = env["auth"]
    user_b = auth.create_user("sales_user_b", "Pass123!", "Sales User B", "salesb@test.com", ROLE_SALES)
    token_b = auth.create_token(user_b)
    return AuthContext(user_b.id, "sales_user_b", ROLE_SALES, "human", token=token_b)


def test_list_leads_narrowed_to_own_and_unclaimed(env):
    crm = env["crm"]
    actor_a = env["actors"][ROLE_SALES]
    actor_b = _second_sales_actor(env)

    cust = crm.create_customer(Customer(first_name="A", last_name="Owner"), actor_a)

    lead_a = crm.create_lead(Lead(customer_id=cust.id, source="website", assigned_user_id=actor_a.user_id), actor_a)
    lead_unclaimed = crm.create_lead(Lead(customer_id=cust.id, source="referral"), actor_a)

    # Actor B (plain sales, no PERM_READ_TEAM_SALES_DATA) must not see
    # actor A's assigned lead, but must see the unclaimed one.
    leads_b = crm.list_leads(actor_b)
    ids_b = {l.id for l in leads_b}
    assert lead_a.id not in ids_b
    assert lead_unclaimed.id in ids_b

    # get_lead on another rep's assigned lead is treated as not-found.
    assert crm.get_lead(lead_a.id, actor_b) is None
    # get_lead on the unclaimed lead is visible.
    assert crm.get_lead(lead_unclaimed.id, actor_b) is not None

    # Grant PERM_READ_TEAM_SALES_DATA to actor B -> now sees everything.
    actor_b_manager = AuthContext(
        actor_b.user_id, actor_b.username, actor_b.role, actor_b.actor_type,
        token=actor_b.token, custom_permissions={PERM_READ_TEAM_SALES_DATA: True},
    )
    leads_manager = crm.list_leads(actor_b_manager)
    ids_manager = {l.id for l in leads_manager}
    assert lead_a.id in ids_manager
    assert lead_unclaimed.id in ids_manager
    assert crm.get_lead(lead_a.id, actor_b_manager) is not None


def test_list_opportunities_narrowed_to_own_and_unclaimed(env):
    crm = env["crm"]
    actor_a = env["actors"][ROLE_SALES]
    actor_b = _second_sales_actor(env)

    cust = crm.create_customer(Customer(first_name="B", last_name="Owner"), actor_a)

    opp_a = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="A's deal", estimated_value=5000.0, assigned_user_id=actor_a.user_id),
        actor_a,
    )
    opp_unclaimed = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Unclaimed deal", estimated_value=3000.0),
        actor_a,
    )

    opps_b = crm.list_opportunities(actor_b)
    ids_b = {o.id for o in opps_b}
    assert opp_a.id not in ids_b
    assert opp_unclaimed.id in ids_b

    assert crm.get_opportunity(opp_a.id, actor_b) is None
    assert crm.get_opportunity(opp_unclaimed.id, actor_b) is not None

    actor_b_manager = AuthContext(
        actor_b.user_id, actor_b.username, actor_b.role, actor_b.actor_type,
        token=actor_b.token, custom_permissions={PERM_READ_TEAM_SALES_DATA: True},
    )
    opps_manager = crm.list_opportunities(actor_b_manager)
    ids_manager = {o.id for o in opps_manager}
    assert opp_a.id in ids_manager
    assert opp_unclaimed.id in ids_manager
    assert crm.get_opportunity(opp_a.id, actor_b_manager) is not None


def test_list_tasks_narrowed_to_own_and_unclaimed(env):
    crm = env["crm"]
    actor_a = env["actors"][ROLE_SALES]
    actor_b = _second_sales_actor(env)

    task_a = crm.create_task(
        Task(title="A's follow-up", task_type="follow_up", assigned_user_id=actor_a.user_id), actor_a
    )
    task_unclaimed = crm.create_task(
        Task(title="Unclaimed follow-up", task_type="follow_up"), actor_a
    )

    tasks_b = crm.list_tasks(actor_b)
    ids_b = {t.id for t in tasks_b}
    assert task_a.id not in ids_b
    assert task_unclaimed.id in ids_b

    assert crm.get_task(task_a.id, actor_b) is None
    assert crm.get_task(task_unclaimed.id, actor_b) is not None

    actor_b_manager = AuthContext(
        actor_b.user_id, actor_b.username, actor_b.role, actor_b.actor_type,
        token=actor_b.token, custom_permissions={PERM_READ_TEAM_SALES_DATA: True},
    )
    tasks_manager = crm.list_tasks(actor_b_manager)
    ids_manager = {t.id for t in tasks_manager}
    assert task_a.id in ids_manager
    assert task_unclaimed.id in ids_manager
    assert crm.get_task(task_a.id, actor_b_manager) is not None


def test_reassign_away_from_self_still_records_audit_after_image(env):
    """NEW-533 audit-correctness guard: a narrowed actor (no
    PERM_READ_TEAM_SALES_DATA) reassigning a lead/opportunity/task's
    assigned_user_id AWAY from themselves must still produce an audit
    row with a real `after` image, not `after=None`. Before the fix,
    update_lead/update_opportunity/update_task built their after-image via
    a self.get_*(id, actor) re-read, which re-ran the new narrowing gate
    and returned None for exactly this case (actor no longer "owns" the
    row post-reassignment) -- silently losing the post-image for the
    reassignment event itself."""
    crm = env["crm"]
    actor_a = env["actors"][ROLE_SALES]
    actor_b = _second_sales_actor(env)

    cust = crm.create_customer(Customer(first_name="D", last_name="Owner"), actor_a)

    # build_audit_details() diffs before/after into a changed_fields map,
    # it does not store a raw "after" key -- so the pre-fix bug's actual
    # symptom was changed_fields['assigned_user_id']['new'] coming back
    # None (audit claims the field was cleared) instead of the real new
    # owner, since after=None collapses to an empty dict inside the diff.
    lead = crm.create_lead(Lead(customer_id=cust.id, source="website", assigned_user_id=actor_a.user_id), actor_a)
    record = crm.update_lead(lead.id, {"assigned_user_id": actor_b.user_id}, actor_a)
    assert record.assigned_user_id == actor_b.user_id
    logs = env["audit"].query_logs(env["actors"][ROLE_ADMIN], entity_type="lead", entity_id=lead.id, action="update")
    assert logs, "Expected an audit row for the lead reassignment"
    changed = logs[0].details.get("changed_fields", {})
    assert changed.get("assigned_user_id") == {"old": actor_a.user_id, "new": actor_b.user_id}

    opp = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Reassign me", estimated_value=1000.0, assigned_user_id=actor_a.user_id),
        actor_a,
    )
    updated_opp = crm.update_opportunity(opp.id, {"assigned_user_id": actor_b.user_id}, actor_a)
    assert updated_opp.assigned_user_id == actor_b.user_id
    opp_logs = env["audit"].query_logs(env["actors"][ROLE_ADMIN], entity_type="opportunity", entity_id=opp.id, action="update")
    assert opp_logs
    opp_changed = opp_logs[0].details.get("changed_fields", {})
    assert opp_changed.get("assigned_user_id") == {"old": actor_a.user_id, "new": actor_b.user_id}

    task = crm.create_task(
        Task(title="Reassign task", task_type="follow_up", assigned_user_id=actor_a.user_id), actor_a
    )
    updated_task = crm.update_task(task.id, {"assigned_user_id": actor_b.user_id}, actor_a)
    assert updated_task.assigned_user_id == actor_b.user_id
    task_logs = env["audit"].query_logs(env["actors"][ROLE_ADMIN], entity_type="task", entity_id=task.id, action="update")
    assert task_logs
    task_changed = task_logs[0].details.get("changed_fields", {})
    assert task_changed.get("assigned_user_id") == {"old": actor_a.user_id, "new": actor_b.user_id}


def test_admin_and_manager_unaffected_by_narrowing(env):
    """Admin/manager hold PERM_READ_TEAM_SALES_DATA by default -- confirm
    they see another rep's assigned lead without any special grant."""
    crm = env["crm"]
    actor_a = env["actors"][ROLE_SALES]
    admin_actor = env["actors"][ROLE_ADMIN]
    manager_actor = env["actors"][ROLE_MANAGER]

    cust = crm.create_customer(Customer(first_name="C", last_name="Owner"), actor_a)
    lead_a = crm.create_lead(Lead(customer_id=cust.id, source="website", assigned_user_id=actor_a.user_id), actor_a)

    assert lead_a.id in {l.id for l in crm.list_leads(admin_actor)}
    assert lead_a.id in {l.id for l in crm.list_leads(manager_actor)}
    assert crm.get_lead(lead_a.id, admin_actor) is not None
    assert crm.get_lead(lead_a.id, manager_actor) is not None


def test_real_sales_manager_role_sees_team_data_with_no_custom_permission_grant(env):
    """D2, sales_rep_portal.md §4: a real ROLE_SALES_MANAGER-role actor
    must see another rep's assigned lead/opportunity/task via both the
    list and get paths, with zero `custom_permissions` grant needed --
    unlike test_list_*_narrowed_to_own_and_unclaimed above, which grants
    PERM_READ_TEAM_SALES_DATA via the original NEW-533 custom_permissions
    mechanism."""
    auth = env["auth"]
    crm = env["crm"]
    actor_a = env["actors"][ROLE_SALES]

    sales_manager_user = auth.create_user(
        "sales_manager_user", "Pass123!", "Sales Manager User", "salesmgr@test.com", ROLE_SALES_MANAGER
    )
    sales_manager_token = auth.create_token(sales_manager_user)
    sales_manager_actor = AuthContext(
        sales_manager_user.id, "sales_manager_user", ROLE_SALES_MANAGER, "human",
        token=sales_manager_token,
    )

    cust = crm.create_customer(Customer(first_name="E", last_name="Owner"), actor_a)

    lead = crm.create_lead(
        Lead(customer_id=cust.id, source="website", assigned_user_id=actor_a.user_id), actor_a
    )
    opp = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="E's deal", estimated_value=2000.0, assigned_user_id=actor_a.user_id),
        actor_a,
    )
    task = crm.create_task(
        Task(title="E's follow-up", task_type="follow_up", assigned_user_id=actor_a.user_id), actor_a
    )

    assert lead.id in {l.id for l in crm.list_leads(sales_manager_actor)}
    assert opp.id in {o.id for o in crm.list_opportunities(sales_manager_actor)}
    assert task.id in {t.id for t in crm.list_tasks(sales_manager_actor)}

    assert crm.get_lead(lead.id, sales_manager_actor) is not None
    assert crm.get_opportunity(opp.id, sales_manager_actor) is not None
    assert crm.get_task(task.id, sales_manager_actor) is not None


# ==========================================
# 9. NEW-534: ATOMIC CLAIM WORKFLOW
# ==========================================

def test_claim_lead_success_updates_assignment_and_narrows_visibility(env):
    crm = env["crm"]
    actor_a = env["actors"][ROLE_SALES]
    actor_b = _second_sales_actor(env)

    cust = crm.create_customer(Customer(first_name="F", last_name="Owner"), actor_a)
    lead = crm.create_lead(Lead(customer_id=cust.id, source="website"), actor_a)
    assert lead.assigned_user_id is None

    claimed = crm.claim_lead(lead.id, actor_b)
    assert claimed is not None
    assert claimed.assigned_user_id == actor_b.user_id

    # NEW-533 narrowing kicks in immediately: actor_a (no
    # PERM_READ_TEAM_SALES_DATA) can no longer see the now-claimed-by-
    # actor_b lead via either the get or list path.
    assert crm.get_lead(lead.id, actor_a) is None
    assert lead.id not in {l.id for l in crm.list_leads(actor_a)}
    # actor_b, who claimed it, sees it fine.
    assert crm.get_lead(lead.id, actor_b) is not None


def test_claim_lead_api_route_200_and_body_shape(env):
    router = env["router"]
    crm = env["crm"]
    actor_a = env["actors"][ROLE_SALES]
    token = env["tokens"][ROLE_SALES]

    cust = crm.create_customer(Customer(first_name="G", last_name="Owner"), actor_a)
    lead = crm.create_lead(Lead(customer_id=cust.id, source="referral"), actor_a)

    s, _, data = router.handle_request(
        "POST", f"/api/v1/leads/{lead.id}/claim", {"Authorization": f"Bearer {token}"}, b"",
    )
    assert s == 200
    assert data["lead"]["id"] == lead.id
    assert data["lead"]["assigned_user_id"] == actor_a.user_id


def test_claim_lead_ignores_body_supplied_assignee(env):
    """Hardcoded self-claim: a request body naming someone else as
    assigned_user_id must be ignored entirely -- claim_lead's signature
    takes no updates dict at all (unlike update_lead), so this also
    verifies the route never threads json_body into claim_lead."""
    router = env["router"]
    crm = env["crm"]
    actor_a = env["actors"][ROLE_SALES]
    actor_b = _second_sales_actor(env)
    token = env["tokens"][ROLE_SALES]

    cust = crm.create_customer(Customer(first_name="H", last_name="Owner"), actor_a)
    lead = crm.create_lead(Lead(customer_id=cust.id, source="referral"), actor_a)

    s, _, data = router.handle_request(
        "POST", f"/api/v1/leads/{lead.id}/claim", {"Authorization": f"Bearer {token}"},
        json.dumps({"assigned_user_id": actor_b.user_id}).encode("utf-8"),
    )
    assert s == 200
    assert data["lead"]["assigned_user_id"] == actor_a.user_id
    assert data["lead"]["assigned_user_id"] != actor_b.user_id


def test_claim_lead_conflict_on_already_claimed_record(env):
    router = env["router"]
    crm = env["crm"]
    actor_a = env["actors"][ROLE_SALES]
    actor_b = _second_sales_actor(env)

    cust = crm.create_customer(Customer(first_name="I", last_name="Owner"), actor_a)
    lead = crm.create_lead(
        Lead(customer_id=cust.id, source="referral", assigned_user_id=actor_a.user_id), actor_a
    )

    s, _, data = router.handle_request(
        "POST", f"/api/v1/leads/{lead.id}/claim", {"Authorization": f"Bearer {actor_b.token}"}, b"",
    )
    assert s == 409
    assert data["error"] == "already claimed"


def test_claim_lead_not_found_returns_404(env):
    router = env["router"]
    token = env["tokens"][ROLE_SALES]
    s, _, data = router.handle_request(
        "POST", "/api/v1/leads/999999/claim", {"Authorization": f"Bearer {token}"}, b"",
    )
    assert s == 404
    assert data["error"] == "Lead not found"


def test_claim_lead_audit_log_records_correct_before_after(env):
    crm = env["crm"]
    audit = env["audit"]
    actor_a = env["actors"][ROLE_SALES]

    cust = crm.create_customer(Customer(first_name="J", last_name="Owner"), actor_a)
    lead = crm.create_lead(Lead(customer_id=cust.id, source="referral"), actor_a)

    crm.claim_lead(lead.id, actor_a)

    logs = audit.query_logs(env["actors"][ROLE_ADMIN], entity_type="lead", entity_id=lead.id, action="claim")
    assert logs, "Expected an audit row for the lead claim"
    changed = logs[0].details.get("changed_fields", {})
    assert changed.get("assigned_user_id") == {"old": None, "new": actor_a.user_id}


def test_claim_lead_sequential_race_second_call_conflicts(env):
    """Concurrency-shaped: two sequential claim calls against the same
    unclaimed row (the simpler of the spec's two allowed approaches).
    This exercises the conditional UPDATE's own `rowcount` check -- the
    thing that actually guarantees correctness under real concurrency --
    not the test's thread count. Chosen over a genuine 2-thread test
    because DatabaseManager.get_connection() returns a single shared
    sqlite3 connection (check_same_thread=False, confirmed by reading
    database.py before writing this test): SQLite already serializes all
    writes made through that one connection regardless of Python-level
    threading, so a real multi-threaded variant would exercise the exact
    same `WHERE assigned_user_id IS NULL` + rowcount code path with no
    additional guarantee proven beyond what this sequential version
    already demonstrates."""
    crm = env["crm"]
    actor_a = env["actors"][ROLE_SALES]
    actor_b = _second_sales_actor(env)

    cust = crm.create_customer(Customer(first_name="K", last_name="Owner"), actor_a)
    lead = crm.create_lead(Lead(customer_id=cust.id, source="referral"), actor_a)

    first = crm.claim_lead(lead.id, actor_a)
    assert first.assigned_user_id == actor_a.user_id

    with pytest.raises(ClaimConflictError):
        crm.claim_lead(lead.id, actor_b)


def test_claim_opportunity_api_route_200_409_404(env):
    """Route-level coverage for POST /api/v1/opportunities/{id}/claim --
    distinct path-slicing arithmetic from the lead route (different prefix
    length subtracted for '/claim'), so passing lead-route tests prove
    nothing about this one; must be exercised independently through
    router.handle_request, not just CRMService.claim_opportunity directly."""
    router = env["router"]
    crm = env["crm"]
    actor_a = env["actors"][ROLE_SALES]
    actor_b = _second_sales_actor(env)
    token_a = env["tokens"][ROLE_SALES]

    cust = crm.create_customer(Customer(first_name="N", last_name="Owner"), actor_a)
    opp = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Route-tested deal", estimated_value=1500.0), actor_a,
    )

    s, _, data = router.handle_request(
        "POST", f"/api/v1/opportunities/{opp.id}/claim", {"Authorization": f"Bearer {token_a}"}, b"",
    )
    assert s == 200
    assert data["opportunity"]["id"] == opp.id
    assert data["opportunity"]["assigned_user_id"] == actor_a.user_id

    s, _, data = router.handle_request(
        "POST", f"/api/v1/opportunities/{opp.id}/claim", {"Authorization": f"Bearer {actor_b.token}"}, b"",
    )
    assert s == 409
    assert data["error"] == "already claimed"

    s, _, data = router.handle_request(
        "POST", "/api/v1/opportunities/999999/claim", {"Authorization": f"Bearer {token_a}"}, b"",
    )
    assert s == 404
    assert data["error"] == "Opportunity not found"


def test_claim_task_api_route_200_409_404(env):
    """Route-level coverage for POST /api/v1/crm/tasks/{id}/claim -- note
    the real prefix is /api/v1/crm/tasks/, distinct from both the lead and
    opportunity routes' path-slicing arithmetic; must be exercised
    independently through router.handle_request."""
    router = env["router"]
    crm = env["crm"]
    actor_a = env["actors"][ROLE_SALES]
    actor_b = _second_sales_actor(env)
    token_a = env["tokens"][ROLE_SALES]

    task = crm.create_task(Task(title="Route-tested follow-up", task_type="follow_up"), actor_a)

    s, _, data = router.handle_request(
        "POST", f"/api/v1/crm/tasks/{task.id}/claim", {"Authorization": f"Bearer {token_a}"}, b"",
    )
    assert s == 200
    assert data["task"]["id"] == task.id
    assert data["task"]["assigned_user_id"] == actor_a.user_id

    s, _, data = router.handle_request(
        "POST", f"/api/v1/crm/tasks/{task.id}/claim", {"Authorization": f"Bearer {actor_b.token}"}, b"",
    )
    assert s == 409
    assert data["error"] == "already claimed"

    s, _, data = router.handle_request(
        "POST", "/api/v1/crm/tasks/999999/claim", {"Authorization": f"Bearer {token_a}"}, b"",
    )
    assert s == 404
    assert data["error"] == "Task not found"


def test_claim_opportunity_and_claim_task_basic_flow(env):
    """Lighter-weight coverage for claim_opportunity/claim_task (full
    success/conflict/audit/body-ignored permutations are already covered
    in depth for claim_lead above; the three methods are structurally
    identical)."""
    crm = env["crm"]
    actor_a = env["actors"][ROLE_SALES]
    actor_b = _second_sales_actor(env)

    cust = crm.create_customer(Customer(first_name="L", last_name="Owner"), actor_a)

    opp = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Claimable deal", estimated_value=4000.0), actor_a,
    )
    claimed_opp = crm.claim_opportunity(opp.id, actor_b)
    assert claimed_opp.assigned_user_id == actor_b.user_id
    with pytest.raises(ClaimConflictError):
        crm.claim_opportunity(opp.id, actor_a)
    assert crm.claim_opportunity(999999, actor_a) is None

    task = crm.create_task(Task(title="Claimable follow-up", task_type="follow_up"), actor_a)
    claimed_task = crm.claim_task(task.id, actor_b)
    assert claimed_task.assigned_user_id == actor_b.user_id
    with pytest.raises(ClaimConflictError):
        crm.claim_task(task.id, actor_a)
    assert crm.claim_task(999999, actor_a) is None


def test_claim_permission_denied_without_write_permission(env):
    crm = env["crm"]
    actor_a = env["actors"][ROLE_SALES]
    cust_actor = env["actors"][ROLE_CUSTOMER]

    cust = crm.create_customer(Customer(first_name="M", last_name="Owner"), actor_a)
    lead = crm.create_lead(Lead(customer_id=cust.id, source="referral"), actor_a)

    with pytest.raises(PermissionError):
        crm.claim_lead(lead.id, cust_actor)
