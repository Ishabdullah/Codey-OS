#!/usr/bin/env python3
"""
Test Multi-Domain Request Splitting — Track A / Phase A2 Item 4.7.

Tests:
1. Single vs multi-domain request classification.
2. DAG dependency resolution and topological ordering.
3. Cross-domain blackboard variable handoff live execution.
4. Cross-domain safety veto (vetoing multi-domain plans with a dangerous step in any domain).
5. Optimizer cross-domain redundancy pruning.
6. 64KB TaskContext ceiling and TaskBlackboard audit trail.
7. Critic cross-domain I/O contract validation.
"""

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ccos.core.agent_orchestrator import (
    AgentOrchestrator,
    AgentRole,
    CriticAgent,
    DecisionStatus,
    ExecutionPlan,
    OptimizerAgent,
    PlannerAgent,
    PlanStep as OrchestratorPlanStep,
    RiskLevel,
    SafetyAgent,
    SafetyVetoError,
    get_agent_orchestrator,
)
from ccos.core.capability_registry import Capability, CapabilityRegistry, get_capability_registry
from ccos.core.domain_router import (
    Domain,
    DomainRouter,
    SubGoal,
    get_domain_router,
)
from ccos.core.performance_tracker import PerformanceTracker
from ccos.core.planner import Plan, Planner, PlanStep, StepStatus, StepType, get_planner
from ccos.core.plugin_manager import PluginManager, get_plugin_manager
from ccos.core.task_blackboard import TaskBlackboard
from ccos.core.task_context import (
    ContextPayloadTooLargeError,
    MAX_CONTEXT_PAYLOAD_BYTES,
    TaskContext,
)


def _make_temp_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return f.name


def _make_temp_registry_file():
    f = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    f.close()
    return f.name


# ── Test 1: Single vs Multi-Domain Request Classification ─────────

def test_single_vs_multi_domain_classification():
    router = get_domain_router()

    # Single domain queries
    single_sys = router.classify_request("check system battery and cpu usage")
    assert single_sys["is_multi_domain"] is False
    assert Domain.SYSTEM.value in single_sys["domains"]
    assert len(single_sys["sub_goals"]) == 1
    assert single_sys["sub_goals"][0].domain == Domain.SYSTEM.value

    single_code = router.classify_request("refactor python bug in test function")
    assert single_code["is_multi_domain"] is False
    assert Domain.CODING.value in single_code["domains"]

    single_crm = router.classify_request("lookup customer lead contact deal")
    assert single_crm["is_multi_domain"] is False
    assert Domain.CRM.value in single_crm["domains"]

    # Multi-domain compound queries
    multi_req1 = router.classify_request(
        "Fetch customer leads from CRM and then write a python script to process them"
    )
    assert multi_req1["is_multi_domain"] is True
    assert Domain.CRM.value in multi_req1["domains"]
    assert Domain.CODING.value in multi_req1["domains"]
    assert len(multi_req1["sub_goals"]) == 2

    multi_req2 = router.classify_request(
        "Take a screenshot of invoice and extract OCR text, after that query sql database table, then speak confirmation message"
    )
    assert multi_req2["is_multi_domain"] is True
    assert Domain.VISION.value in multi_req2["domains"]
    assert Domain.DATA.value in multi_req2["domains"]
    assert Domain.SPEECH.value in multi_req2["domains"]
    assert len(multi_req2["sub_goals"]) == 3


# ── Test 2: DAG Dependency Resolution and Topological Ordering ────

def test_dag_dependency_resolution_and_topological_ordering():
    router = DomainRouter()

    # Sub-goals in reverse order with cross-domain data dependencies:
    # SubGoal 1 (speech) needs 'coding_report' produced by SubGoal 2 (coding)
    # SubGoal 2 (coding) needs 'crm_data' produced by SubGoal 3 (crm)
    # SubGoal 3 (crm) has no dependencies
    sg_speech = SubGoal(
        id=1,
        domain="speech",
        action="Speak summary",
        context_in_keys=["coding_report"],
        context_out_keys=["speech_audio"],
    )
    sg_coding = SubGoal(
        id=2,
        domain="coding",
        action="Generate python report",
        context_in_keys=["crm_data"],
        context_out_keys=["coding_report"],
    )
    sg_crm = SubGoal(
        id=3,
        domain="crm",
        action="Fetch CRM leads",
        context_in_keys=[],
        context_out_keys=["crm_data"],
    )

    ordered = router.build_dependency_dag([sg_speech, sg_coding, sg_crm])
    assert len(ordered) == 3

    # Check topological order: CRM (produces crm_data) -> Coding (produces coding_report) -> Speech (consumes coding_report)
    assert ordered[0].domain == "crm"
    assert ordered[0].id == 1
    assert "crm_data" in ordered[0].context_out_keys

    assert ordered[1].domain == "coding"
    assert ordered[1].id == 2
    assert "crm_data" in ordered[1].context_in_keys
    assert 1 in ordered[1].depends_on

    assert ordered[2].domain == "speech"
    assert ordered[2].id == 3
    assert "coding_report" in ordered[2].context_in_keys
    assert 2 in ordered[2].depends_on


def test_dag_cycle_detection():
    router = DomainRouter()

    sg_a = SubGoal(
        id=1,
        domain="data",
        action="Step A",
        context_in_keys=["key_b"],
        context_out_keys=["key_a"],
    )
    sg_b = SubGoal(
        id=2,
        domain="coding",
        action="Step B",
        context_in_keys=["key_a"],
        context_out_keys=["key_b"],
    )

    with pytest.raises(ValueError, match="Cycle detected"):
        router.build_dependency_dag([sg_a, sg_b])


# ── Test 3: Cross-Domain Blackboard Variable Handoff Live Execution

def test_cross_domain_blackboard_handoff_live_execution():
    bb_path = _make_temp_db()
    reg_path = _make_temp_registry_file()

    try:
        bb = TaskBlackboard(db_path=bb_path)
        reg = CapabilityRegistry(store_path=reg_path)
        pm = PluginManager(registry=reg)

        # Register mock plugin capabilities across CRM, Data, and Coding domains
        def mock_crm_query(query: str = "", context: Optional[TaskContext] = None, **kwargs):
            return {"customer_list": [{"id": 101, "name": "Acme Corp"}, {"id": 102, "name": "Globex"}]}

        def mock_data_agg(customer_list: Optional[list] = None, context: Optional[TaskContext] = None, **kwargs):
            count = len(customer_list) if customer_list else 0
            return {"customer_count": count, "summary_text": f"Found {count} enterprise accounts"}

        def mock_coding_report(summary_text: str = "", customer_count: int = 0, context: Optional[TaskContext] = None, **kwargs):
            return {"report_file": f"/tmp/report_{customer_count}.txt", "content": f"REPORT: {summary_text}"}

        pm.register_capability_handler("crm.query_leads", mock_crm_query)
        pm.register_capability_handler("data.aggregate_metrics", mock_data_agg)
        pm.register_capability_handler("coding.generate_report", mock_coding_report)

        reg.register(Capability(name="crm.query_leads", description="Query CRM", implementation="builtin", category="crm"))
        reg.register(Capability(name="data.aggregate_metrics", description="Aggregate metrics", implementation="builtin", category="data"))
        reg.register(Capability(name="coding.generate_report", description="Generate report", implementation="builtin", category="coding"))

        # Build Plan with explicit blackboard key handoffs:
        # Step 1 (CRM) -> outputs 'customer_list'
        # Step 2 (Data) -> inputs 'customer_list', outputs 'customer_count' and 'summary_text'
        # Step 3 (Coding) -> inputs 'summary_text' & 'customer_count', outputs 'report_file'
        plan = Plan(
            goal="Fetch CRM customer leads and analyze metrics and generate python report",
            steps=[
                PlanStep(
                    id=1,
                    description="Query CRM leads",
                    step_type=StepType.CAPABILITY_CALL,
                    capability="crm.query_leads",
                    context_out_keys=["customer_list"],
                    metadata={"domain": "crm", "inputs": {"query": "enterprise"}},
                ),
                PlanStep(
                    id=2,
                    description="Aggregate customer metrics",
                    step_type=StepType.CAPABILITY_CALL,
                    capability="data.aggregate_metrics",
                    context_in_keys=["customer_list"],
                    context_out_keys=["customer_count", "summary_text"],
                    metadata={"domain": "data"},
                ),
                PlanStep(
                    id=3,
                    description="Generate final report",
                    step_type=StepType.CAPABILITY_CALL,
                    capability="coding.generate_report",
                    context_in_keys=["summary_text", "customer_count"],
                    context_out_keys=["report_file"],
                    metadata={"domain": "coding"},
                ),
            ],
        )

        planner = Planner()
        task_id = f"test_multi_domain_{int(time.time() * 1000)}"
        context = TaskContext(task_id=task_id, step_id="init", goal=plan.goal)

        res = planner.execute_plan(
            plan=plan,
            context=context,
            blackboard=bb,
            plugin_manager=pm,
        )

        for s in plan.steps:
            if s.error:
                print(f"Step {s.id} error: {s.error}")

        assert res["status"] == "completed"
        assert plan.status == "completed"

        # Verify step results
        assert plan.steps[0].status == StepStatus.COMPLETED
        assert plan.steps[1].status == StepStatus.COMPLETED
        assert plan.steps[2].status == StepStatus.COMPLETED

        # Check values stored in Blackboard across domain handoffs
        val_customers = bb.get(task_id, "customer_list")
        assert isinstance(val_customers, list)
        assert len(val_customers) == 2

        val_count = bb.get(task_id, "customer_count")
        assert val_count == 2

        val_summary = bb.get(task_id, "summary_text")
        assert val_summary == "Found 2 enterprise accounts"

        val_report = bb.get(task_id, "report_file")
        assert val_report == "/tmp/report_2.txt"

    finally:
        Path(bb_path).unlink(missing_ok=True)
        Path(reg_path).unlink(missing_ok=True)


# ── Test 4: Cross-Domain Safety Veto ──────────────────────────────

def test_cross_domain_safety_veto():
    bb_path = _make_temp_db()
    tracker_path = _make_temp_db()
    reg_path = _make_temp_registry_file()

    try:
        bb = TaskBlackboard(db_path=bb_path)
        tracker = PerformanceTracker(db_path=tracker_path)
        reg = CapabilityRegistry(store_path=reg_path)

        orch = AgentOrchestrator()
        orch._safety = SafetyAgent()

        # Multi-domain request with safe CRM first step, but dangerous system command in second step
        goal = "Query customer contact and then rm -rf /etc/system_config"

        task_id = f"safety_task_{int(time.time() * 1000)}"
        context = TaskContext(task_id=task_id, step_id="init", goal=goal)

        with pytest.raises(SafetyVetoError) as exc_info:
            orch.execute_request(
                goal=goal,
                context=context,
                blackboard=bb,
                raise_on_veto=True,
            )

        assert "Safety agent vetoed" in str(exc_info.value)
        assert bb.get_task(task_id)["status"] == "vetoed"

        # Also test non-raising execution returns status='vetoed'
        task_id_2 = f"safety_task_2_{int(time.time() * 1000)}"
        context_2 = TaskContext(task_id=task_id_2, step_id="init", goal=goal)

        res = orch.execute_request(
            goal=goal,
            context=context_2,
            blackboard=bb,
            raise_on_veto=False,
        )
        assert res["status"] == "vetoed"
        assert res["plan"] is None

    finally:
        Path(bb_path).unlink(missing_ok=True)
        Path(tracker_path).unlink(missing_ok=True)
        Path(reg_path).unlink(missing_ok=True)


# ── Test 5: Optimizer Cross-Domain Redundancy Pruning ─────────────

def test_optimizer_cross_domain_redundancy_pruning():
    # Plan with 4 steps:
    # 1. crm.query -> outputs 'crm_leads'
    # 2. system.info -> probe 1
    # 3. system.info -> probe 2 (duplicate probe without dependencies)
    # 4. coding.run_agent -> inputs 'crm_leads'
    plan = ExecutionPlan(
        goal="Fetch CRM and system info then run coding",
        steps=[
            OrchestratorPlanStep(
                id=1,
                action="Fetch CRM leads",
                capability="crm.query",
                context_out_keys=["crm_leads"],
            ),
            OrchestratorPlanStep(
                id=2,
                action="Check system info 1",
                capability="system.info",
                context_out_keys=[],
            ),
            OrchestratorPlanStep(
                id=3,
                action="Check system info 2",
                capability="system.info",
                context_out_keys=[],
            ),
            OrchestratorPlanStep(
                id=4,
                action="Process leads in code",
                capability="coding.run_agent",
                context_in_keys=["crm_leads"],
            ),
        ],
        tools_required=["crm.query", "system.info", "system.info", "coding.run_agent"],
    )

    critic = CriticAgent()
    critique = critic.review_plan(plan)

    assert any("redundant" in i.lower() or "duplicate" in i.lower() for i in critique.issues)

    optimizer = OptimizerAgent()
    optimized, opt_out = optimizer.optimize_plan(plan, critique)

    # Verify duplicate system.info was pruned, while preserving crm.query (produces crm_leads) and coding.run_agent (consumes crm_leads)
    capabilities_remaining = [s.capability for s in optimized.steps if s.capability]
    assert capabilities_remaining == ["crm.query", "system.info", "coding.run_agent"]
    assert "crm_leads" in optimized.steps[0].context_out_keys
    assert "crm_leads" in optimized.steps[2].context_in_keys


# ── Test 6: 64KB TaskContext Ceiling & TaskBlackboard Audit Trail ─

def test_64kb_task_context_ceiling_and_blackboard_audit_trail():
    bb_path = _make_temp_db()
    try:
        bb = TaskBlackboard(db_path=bb_path)
        task_id = "test_ceiling_task"
        bb.create_task(task_id, goal="Test context ceiling")

        # 1. Normal context within 64KB works fine
        ctx = TaskContext(
            task_id=task_id,
            step_id="step_1",
            goal="Test context ceiling",
            state={"status": "in_progress", "domain": "crm"},
        )
        assert ctx.validate_size() < MAX_CONTEXT_PAYLOAD_BYTES
        bb.save_checkpoint(ctx)

        # 2. Context exceeding 64KB raises ContextPayloadTooLargeError
        huge_blob = "x" * (MAX_CONTEXT_PAYLOAD_BYTES + 1000)
        with pytest.raises(ContextPayloadTooLargeError):
            TaskContext(
                task_id=task_id,
                step_id="step_overflow",
                goal="Overflow test",
                state={"huge_data": huge_blob},
            )

        # 3. Verify checkpoints audit trail in blackboard
        ctx2 = ctx.evolve(step_id="step_2", output={"result": "step 2 done"})
        bb.save_checkpoint(ctx2)

        checkpoints = bb.get_checkpoints(task_id)
        assert len(checkpoints) == 2
        assert checkpoints[0].step_id == "step_1"
        assert checkpoints[1].step_id == "step_2"

    finally:
        Path(bb_path).unlink(missing_ok=True)


# ── Test 7: Critic Cross-Domain I/O Validation ────────────────────

def test_critic_cross_domain_io_validation():
    # Plan where Step 2 requires an input key that Step 1 does NOT provide
    plan = ExecutionPlan(
        goal="Test unlinked handoff",
        steps=[
            OrchestratorPlanStep(
                id=1,
                action="CRM Step",
                capability="crm.query",
                context_out_keys=["crm_leads"],
            ),
            OrchestratorPlanStep(
                id=2,
                action="Coding Step",
                capability="coding.run_agent",
                context_in_keys=["missing_data_key"],  # Not provided by Step 1 or context
            ),
        ],
        tools_required=["crm.query", "coding.run_agent"],
    )

    critic = CriticAgent()
    critique = critic.review_plan(plan)

    assert any("unmet cross-domain input dependency" in issue.lower() for issue in critique.issues)
    assert any("missing_data_key" in issue for issue in critique.issues)


# ── Test 8: Planner Auto Multi-Domain Plan Creation ───────────────

def test_planner_auto_multi_domain_plan_creation():
    planner = Planner()
    goal = "Query customer leads from CRM then build python analytics report script"

    plan = planner.create_plan(goal)
    assert plan.goal == goal
    assert len(plan.steps) >= 3  # CRM step, Coding step, Validation, Memory Store

    step_domains = [s.metadata.get("domain") for s in plan.steps]
    assert "crm" in step_domains
    assert "coding" in step_domains

    # Check that context_out_keys and context_in_keys are wired
    crm_step = next(s for s in plan.steps if s.metadata.get("domain") == "crm")
    coding_step = next(s for s in plan.steps if s.metadata.get("domain") == "coding")

    assert len(crm_step.context_out_keys) > 0
    assert len(coding_step.context_in_keys) > 0
    assert crm_step.context_out_keys[0] in coding_step.context_in_keys


# ── Test 9: Orchestrator Multi-Domain Deliberation & Execution ────

def test_orchestrator_multi_domain_deliberation_and_execution():
    bb_path = _make_temp_db()
    tracker_path = _make_temp_db()
    reg_path = _make_temp_registry_file()

    try:
        bb = TaskBlackboard(db_path=bb_path)
        tracker = PerformanceTracker(db_path=tracker_path)
        reg = CapabilityRegistry(store_path=reg_path)
        pm = PluginManager(registry=reg)

        # Register capabilities
        global_reg = get_capability_registry()
        global_pm = get_plugin_manager()

        cap_crm = Capability(name="crm.customer_query", description="CRM query", implementation="builtin", category="crm")
        cap_coding = Capability(name="coding.run_agent", description="Coding agent", implementation="builtin", category="coding")

        global_reg.register(cap_crm)
        global_reg.register(cap_coding)

        global_pm.register_capability_handler("crm.customer_query", lambda **kw: {"crm_output_1": [{"id": 1, "name": "Test Account"}]})
        global_pm.register_capability_handler("coding.run_agent", lambda crm_output_1=None, **kw: {"code": "print('Report')" if crm_output_1 else "print('No data')"})

        orch = get_agent_orchestrator()

        goal = "Query CRM customer records and then write a python script to analyze them"
        delib = orch.deliberate(goal)

        assert delib.status in (DecisionStatus.APPROVED, DecisionStatus.MODIFIED)
        assert delib.final_plan is not None
        assert delib.safety_blocked is False

        # Execute end to end
        task_id = f"orch_multi_task_{int(time.time() * 1000)}"
        context = TaskContext(task_id=task_id, step_id="init", goal=goal)

        exec_res = orch.execute_request(
            goal=goal,
            context=context,
            blackboard=bb,
            plugin_manager=global_pm,
        )

        if exec_res.get("plan"):
            for s in exec_res["plan"].steps:
                if s.error:
                    print(f"Step {s.id} ({s.description}) error: {s.error}")

        assert exec_res["status"] == "completed"
        assert bb.get_task(task_id)["status"] == "completed"

        # Check blackboard audit trail
        checkpoints = bb.get_checkpoints(task_id)
        assert len(checkpoints) >= 3

    finally:
        Path(bb_path).unlink(missing_ok=True)
        Path(tracker_path).unlink(missing_ok=True)
        Path(reg_path).unlink(missing_ok=True)

