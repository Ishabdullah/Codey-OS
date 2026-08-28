"""
Tests for Agent Orchestrator execution wiring and live Safety Agent veto.

Covers:
1. Safety veto on destructive goals preventing tool execution & setting blackboard status.
2. Safety veto with raise_on_veto=False returning structured veto result.
3. Safe execution of multi-step plans with TaskContext handoffs and blackboard integration.
4. Optimizer step rewrites executing live in the translated plan.
5. Planner.execute_goal routing and fallback.
6. Audit trail completeness in return dictionary and TaskBlackboard.
7. validate_tool_safety checks on tool router.
8. Direct execute_plan with safety enforcement.
"""

import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional
import pytest

from ccos.core.agent_orchestrator import (
    AgentOrchestrator,
    AgentRole,
    DecisionStatus,
    ExecutionPlan,
    PlanStep as OrchPlanStep,
    RiskLevel,
    SafetyVetoError,
    execution_plan_to_planner_plan,
    get_agent_orchestrator,
)
from ccos.core.capability_registry import Capability, CapabilityRegistry
from ccos.core.performance_tracker import PerformanceTracker
from ccos.core.planner import Plan, Planner, StepStatus, StepType, get_planner
from ccos.core.task_blackboard import TaskBlackboard
from ccos.core.task_context import TaskContext
from ccos.core.tool_router import ToolRouter, validate_tool_safety


class MockPluginManager:
    """Mock plugin manager for testing capability execution."""

    def __init__(self):
        self.calls = []

    def call_capability(self, capability_name: str, context: Optional[TaskContext] = None, **kwargs) -> Any:
        self.calls.append({
            "capability": capability_name,
            "context_task_id": context.task_id if context else None,
            "kwargs": kwargs,
        })
        if capability_name == "system.info":
            return {"os": "Linux", "arch": "aarch64", "status": "ok"}
        elif capability_name == "system.processes":
            return {"processes": ["python", "daemon"], "count": 2}
        elif capability_name == "failing.cap":
            raise RuntimeError("Capability invocation failed")
        return {"result": f"Executed {capability_name}"}


@pytest.fixture
def temp_env():
    """Create isolated temp blackboard, registry, tracker, and orchestrator."""
    bb_f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    bb_f.close()
    reg_f = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    reg_f.close()
    tr_f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tr_f.close()

    bb = TaskBlackboard(db_path=bb_f.name)
    registry = CapabilityRegistry(store_path=reg_f.name)
    tracker = PerformanceTracker(db_path=tr_f.name)
    pm = MockPluginManager()

    # Seed capabilities
    registry.register(Capability(
        name="system.info",
        description="Inspect system information",
        implementation="/tmp/mock_sysinfo.py",
        category="system",
    ))
    registry.register(Capability(
        name="system.processes",
        description="List running processes",
        implementation="/tmp/mock_proc.py",
        category="system",
    ))

    # Pre-populate tracker with successful executions
    for _ in range(5):
        tracker.record_execution("system.info", "1.0.0", 50.0, True)
        tracker.record_execution("system.processes", "1.0.0", 60.0, True)

    orchestrator = AgentOrchestrator()
    orchestrator._planner._registry = registry
    orchestrator._planner._tracker = tracker
    orchestrator._capability._registry = registry
    orchestrator._capability._tracker = tracker

    planner = Planner()
    planner._registry = registry

    yield {
        "blackboard": bb,
        "registry": registry,
        "tracker": tracker,
        "plugin_manager": pm,
        "orchestrator": orchestrator,
        "planner": planner,
    }

    bb.close()
    Path(bb_f.name).unlink(missing_ok=True)
    Path(reg_f.name).unlink(missing_ok=True)
    Path(tr_f.name).unlink(missing_ok=True)


def test_safety_veto_destructive_goal_raises_error(temp_env):
    orch = temp_env["orchestrator"]
    bb = temp_env["blackboard"]
    pm = temp_env["plugin_manager"]

    goal = "delete all files and rm -rf /"
    task_id = "task_veto_test_1"
    ctx = TaskContext(task_id=task_id, step_id="init", goal=goal)

    with pytest.raises(SafetyVetoError) as excinfo:
        orch.execute_request(
            goal=goal,
            context=ctx,
            blackboard=bb,
            plugin_manager=pm,
            raise_on_veto=True,
        )

    err = excinfo.value
    assert err.goal == goal
    assert "rm -rf" in err.reason or "destructive" in err.reason.lower() or "blocked" in err.reason.lower()
    assert err.deliberation is not None
    assert err.deliberation.status == DecisionStatus.VETOED
    assert err.deliberation.safety_blocked is True

    # Check that NO capability was invoked
    assert len(pm.calls) == 0

    # Blackboard must have recorded deliberation status and vetoed task state
    assert bb.get(task_id, "deliberation_status") == "vetoed"
    assert bb.get(task_id, "deliberation_agreement") is not None

    # Checkpoints must include safety_veto
    checkpoints = bb.get_checkpoints(task_id)
    step_ids = [c.step_id for c in checkpoints]
    assert "init" in step_ids
    assert "safety_veto" in step_ids


def test_safety_veto_without_raising(temp_env):
    orch = temp_env["orchestrator"]
    bb = temp_env["blackboard"]
    pm = temp_env["plugin_manager"]

    goal = "format disk and drop table users"
    task_id = "task_veto_test_2"
    ctx = TaskContext(task_id=task_id, step_id="init", goal=goal)

    result = orch.execute_request(
        goal=goal,
        context=ctx,
        blackboard=bb,
        plugin_manager=pm,
        raise_on_veto=False,
    )

    assert result["status"] == "vetoed"
    assert result["goal"] == goal
    assert result["plan"] is None
    assert "destructive" in result["reason"].lower() or "blocked" in result["reason"].lower() or "drop table" in result["reason"].lower()
    assert len(pm.calls) == 0

    # Context checkpointed as safety_veto
    latest_cp = bb.get_latest_checkpoint(task_id)
    assert latest_cp is not None
    assert latest_cp.step_id == "safety_veto"


def test_safety_veto_system_directory_mutation(temp_env):
    orch = temp_env["orchestrator"]
    bb = temp_env["blackboard"]
    pm = temp_env["plugin_manager"]

    # Goal requiring modification of system directory /etc/
    goal = "write custom root config to /etc/shadow"
    task_id = "task_veto_sys_dir"
    ctx = TaskContext(task_id=task_id, step_id="init", goal=goal)

    result = orch.execute_request(
        goal=goal,
        context=ctx,
        blackboard=bb,
        plugin_manager=pm,
        raise_on_veto=False,
    )

    assert result["status"] == "vetoed"
    assert len(pm.calls) == 0
    assert bb.get(task_id, "deliberation_status") == "vetoed"


def test_safe_execution_with_task_context_handoffs(temp_env):
    orch = temp_env["orchestrator"]
    bb = temp_env["blackboard"]
    pm = temp_env["plugin_manager"]

    goal = "inspect system information and check status"
    task_id = "task_safe_exec_1"
    ctx = TaskContext(task_id=task_id, step_id="init", goal=goal)

    result = orch.execute_request(
        goal=goal,
        context=ctx,
        blackboard=bb,
        plugin_manager=pm,
        raise_on_veto=True,
    )

    assert result["status"] == "completed"
    assert result["goal"] == goal
    assert result["plan"] is not None
    assert result["deliberation"] is not None
    assert result["deliberation"].status in (DecisionStatus.APPROVED, DecisionStatus.MODIFIED)

    # Capability should have been called
    assert len(pm.calls) >= 1
    assert pm.calls[0]["capability"] == "system.info"

    # Blackboard audit checks
    assert bb.get(task_id, "deliberation_status") in ("approved", "modified")
    assert bb.get(task_id, "deliberation_agreement") > 0.5
    assert isinstance(bb.get(task_id, "deliberation_gain"), float)

    # Checkpoint chain audit
    checkpoints = bb.get_checkpoints(task_id)
    step_ids = [c.step_id for c in checkpoints]
    assert "init" in step_ids
    assert "plan_approved" in step_ids
    assert any("step_" in sid for sid in step_ids)


def test_optimizer_step_rewrites_live_execution(temp_env):
    orch = temp_env["orchestrator"]
    bb = temp_env["blackboard"]
    pm = temp_env["plugin_manager"]

    # Goal requiring multiple capabilities to trigger critic duplicate check or error handling addition
    goal = "system information review and process listing"
    task_id = "task_opt_rewrite"
    ctx = TaskContext(task_id=task_id, step_id="init", goal=goal)

    result = orch.execute_request(
        goal=goal,
        context=ctx,
        blackboard=bb,
        plugin_manager=pm,
        raise_on_veto=True,
    )

    assert result["status"] == "completed"
    plan = result["plan"]
    assert isinstance(plan, Plan)

    # If optimizer added validation / error handling step, verify it was translated and completed
    step_types = [s.step_type for s in plan.steps]
    step_statuses = [s.status for s in plan.steps]
    assert all(st == StepStatus.COMPLETED for st in step_statuses)


def test_planner_execute_goal_routing(temp_env):
    planner = temp_env["planner"]
    orch = temp_env["orchestrator"]
    bb = temp_env["blackboard"]
    pm = temp_env["plugin_manager"]

    # Temporarily monkeypatch singleton orchestrator
    import ccos.core.agent_orchestrator as ao_mod
    original_orch = ao_mod._orchestrator
    ao_mod._orchestrator = orch

    try:
        # 1. Routing with orchestrator + safety veto
        with pytest.raises(SafetyVetoError):
            planner.execute_goal(
                goal="rm -rf /",
                blackboard=bb,
                plugin_manager=pm,
                use_orchestrator=True,
                raise_on_veto=True,
            )

        # 2. Routing with orchestrator + safe goal
        safe_res = planner.execute_goal(
            goal="inspect system information",
            blackboard=bb,
            plugin_manager=pm,
            use_orchestrator=True,
            raise_on_veto=True,
        )
        assert safe_res["status"] == "completed"
        assert safe_res["deliberation"] is not None

        # 3. Direct planner execution without orchestrator
        fallback_res = planner.execute_goal(
            goal="inspect system information",
            blackboard=bb,
            plugin_manager=pm,
            use_orchestrator=False,
        )
        assert fallback_res["status"] == "completed"
        assert "deliberation" not in fallback_res or fallback_res.get("deliberation") is None
    finally:
        ao_mod._orchestrator = original_orch


def test_validate_tool_safety():
    # 1. Safe commands
    is_safe, reason = validate_tool_safety("system.info", {"path": "/tmp/test.txt"})
    assert is_safe is True
    assert reason == "Safe"

    # 2. Blocked command
    is_safe, reason = validate_tool_safety("bash.exec", {"command": "rm -rf /"})
    assert is_safe is False
    assert "Blocked command" in reason

    # 3. Fork bomb
    is_safe, reason = validate_tool_safety("bash.exec", {"code": ":(){:|:&};:"})
    assert is_safe is False

    # 4. Destructive keyword in nested parameter
    is_safe, reason = validate_tool_safety("db.query", {"payload": {"query": "drop table users"}})
    assert is_safe is False
    assert "Destructive operation" in reason

    # 5. System directory write
    is_safe, reason = validate_tool_safety("file.write", {"filepath": "/etc/sudoers", "content": "all"})
    assert is_safe is False
    assert "System directory modification" in reason

    # 6. System directory read is permitted
    is_safe, reason = validate_tool_safety("file.read", {"filepath": "/etc/hosts", "action": "read"})
    assert is_safe is True


def test_execution_plan_to_planner_plan_bridge():
    exec_plan = ExecutionPlan(
        goal="multi step task",
        steps=[
            OrchPlanStep(id=1, action="Execute capability", capability="system.info", tool="sysinfo", args={"verbose": True}, risk=RiskLevel.LOW, notes="note1", context_in_keys=["k1"], context_out_keys=["k2"]),
            OrchPlanStep(id=2, action="Validate results", risk=RiskLevel.LOW),
            OrchPlanStep(id=3, action="Store in memory", risk=RiskLevel.LOW),
            OrchPlanStep(id=4, action="General inference fallback", risk=RiskLevel.MEDIUM),
        ],
    )

    plan = execution_plan_to_planner_plan(exec_plan)
    assert isinstance(plan, Plan)
    assert plan.goal == "multi step task"
    assert len(plan.steps) == 4

    assert plan.steps[0].step_type == StepType.CAPABILITY_CALL
    assert plan.steps[0].capability == "system.info"
    assert plan.steps[0].metadata.get("tool") == "sysinfo"
    assert plan.steps[0].context_in_keys == ["k1"]
    assert plan.steps[0].context_out_keys == ["k2"]

    assert plan.steps[1].step_type == StepType.VALIDATION
    assert plan.steps[2].step_type == StepType.MEMORY_STORE
    assert plan.steps[3].step_type == StepType.INFERENCE


def test_execute_plan_direct(temp_env):
    orch = temp_env["orchestrator"]
    bb = temp_env["blackboard"]
    pm = temp_env["plugin_manager"]

    # Direct safe ExecutionPlan
    safe_exec_plan = ExecutionPlan(
        goal="direct safe execution",
        steps=[
            OrchPlanStep(id=1, action="inspect system information", capability="system.info"),
        ],
    )
    res = orch.execute_plan(
        plan=safe_exec_plan,
        blackboard=bb,
        plugin_manager=pm,
        raise_on_veto=True,
    )
    assert res["status"] == "completed"

    # Direct unsafe ExecutionPlan
    unsafe_exec_plan = ExecutionPlan(
        goal="direct unsafe execution",
        steps=[
            OrchPlanStep(id=1, action="rm -rf /"),
        ],
    )
    with pytest.raises(SafetyVetoError):
        orch.execute_plan(
            plan=unsafe_exec_plan,
            blackboard=bb,
            plugin_manager=pm,
            raise_on_veto=True,
        )
