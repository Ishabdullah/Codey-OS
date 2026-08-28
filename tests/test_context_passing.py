"""
Integration and Unit Tests for In-Flight Context Passing and Stage Handoffs.

Covers:
- PluginManager.call_capability with and without TaskContext.
- Context injection for functions accepting context / **kwargs.
- Graceful backward compatibility for legacy functions without context / **kwargs.
- Multi-step Plan execution with Planner, TaskContext, and TaskBlackboard.
"""

import os
import tempfile
import time
import pytest
from unittest.mock import MagicMock, patch

from ccos.core.capability_registry import Capability, CapabilityStatus, CapabilityRegistry
from ccos.core.planner import Plan, PlanStep, StepStatus, StepType, Planner
from ccos.core.plugin_manager import Plugin, PluginManager, PluginStatus
from ccos.core.task_blackboard import TaskBlackboard
from ccos.core.task_context import TaskContext


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


# ── Mock Plugin Module Definitions ──────────────────────────────────

class MockPluginModule:
    """Module containing both context-aware and legacy capabilities."""

    @staticmethod
    def legacy_cap(x: int, y: int = 1) -> int:
        """Legacy capability: does not accept context or **kwargs."""
        return x + y

    @staticmethod
    def context_aware_cap(x: int, context: TaskContext = None) -> dict:
        """Context-aware capability: explicitly accepts context."""
        return {
            "result": x * 2,
            "received_task_id": context.task_id if context else None,
            "received_step_id": context.step_id if context else None,
        }

    @staticmethod
    def varkw_cap(x: int, **kwargs) -> dict:
        """Capability with **kwargs: should receive context when provided."""
        ctx = kwargs.get("context")
        return {
            "result": x + 10,
            "has_context": ctx is not None,
            "task_id": ctx.task_id if ctx else None,
        }


def create_test_plugin_manager():
    pm = PluginManager(plugin_dirs=[])
    # Register mock plugin
    mock_plugin = Plugin(
        name="test_plugin",
        path="/mock/path",
        manifest={"name": "test_plugin", "capabilities": []},
        status=PluginStatus.ACTIVE,
        capabilities=["test.legacy", "test.aware", "test.varkw"],
    )
    pm._plugins["test_plugin"] = mock_plugin
    pm._modules["test_plugin"] = MockPluginModule

    # Register in registry
    registry = pm._registry
    registry.register(
        Capability(
            name="test.legacy",
            description="Legacy capability",
            implementation="test_plugin:legacy_cap",
            status=CapabilityStatus.ACTIVE,
        )
    )
    registry.register(
        Capability(
            name="test.aware",
            description="Context-aware capability",
            implementation="test_plugin:context_aware_cap",
            status=CapabilityStatus.ACTIVE,
        )
    )
    registry.register(
        Capability(
            name="test.varkw",
            description="Var-kw capability",
            implementation="test_plugin:varkw_cap",
            status=CapabilityStatus.ACTIVE,
        )
    )
    return pm


def test_call_capability_legacy_without_context():
    pm = create_test_plugin_manager()
    res = pm.call_capability("test.legacy", x=5, y=3)
    assert res == 8


def test_call_capability_legacy_with_context_graceful_omission():
    pm = create_test_plugin_manager()
    ctx = TaskContext(task_id="t-legacy", step_id="s1", goal="Test legacy")

    # When context is provided, it should NOT be passed to legacy_cap to avoid TypeError
    res = pm.call_capability("test.legacy", x=10, y=5, context=ctx)
    assert res == 15


def test_call_capability_context_aware():
    pm = create_test_plugin_manager()
    ctx = TaskContext(task_id="t-aware", step_id="step-ctx-1", goal="Test aware")

    res = pm.call_capability("test.aware", x=7, context=ctx)
    assert res["result"] == 14
    assert res["received_task_id"] == "t-aware"
    assert res["received_step_id"] == "step-ctx-1"


def test_call_capability_varkw_with_and_without_context():
    pm = create_test_plugin_manager()

    # Without context
    res1 = pm.call_capability("test.varkw", x=5)
    assert res1["result"] == 15
    assert res1["has_context"] is False

    # With context
    ctx = TaskContext(task_id="t-varkw", step_id="step-kw-1", goal="Test varkw")
    res2 = pm.call_capability("test.varkw", x=5, context=ctx)
    assert res2["result"] == 15
    assert res2["has_context"] is True
    assert res2["task_id"] == "t-varkw"


def test_multi_step_plan_execution_context_handoff(temp_db):
    pm = create_test_plugin_manager()
    bb = TaskBlackboard(temp_db)
    planner = Planner()

    # Define a 3-step plan:
    # Step 1: test.aware with x=10 -> produces result dict with "result" key. Output mapped to blackboard "step1_output".
    # Step 2: test.varkw taking "x" from "step1_output" (context_in_keys). Output mapped to "step2_output".
    # Step 3: test.legacy taking "x" from "step2_output".
    steps = [
        PlanStep(
            id=1,
            description="Run aware step",
            step_type=StepType.CAPABILITY_CALL,
            capability="test.aware",
            metadata={"inputs": {"x": 10}},
            context_out_keys=["result"],
        ),
        PlanStep(
            id=2,
            description="Run varkw step consuming step 1 result as x",
            step_type=StepType.CAPABILITY_CALL,
            capability="test.varkw",
            context_in_keys={"x": "result"},
            context_out_keys=["result"],
        ),
        PlanStep(
            id=3,
            description="Run legacy step consuming step 2 result as x",
            step_type=StepType.CAPABILITY_CALL,
            capability="test.legacy",
            context_in_keys={"x": "result"},
            context_out_keys=["final_val"],
        ),
    ]

    plan = Plan(goal="Multi-step handoff pipeline", steps=steps)
    initial_ctx = TaskContext(
        task_id="task-pipeline-1",
        step_id="init",
        goal="Multi-step handoff pipeline",
        state={"pipeline": "active"},
    )

    result = planner.execute_plan(
        plan=plan,
        context=initial_ctx,
        blackboard=bb,
        plugin_manager=pm,
    )

    assert result["status"] == "completed"
    assert plan.steps[0].status == StepStatus.COMPLETED
    assert plan.steps[1].status == StepStatus.COMPLETED
    assert plan.steps[2].status == StepStatus.COMPLETED

    # Step 1: 10 * 2 = 20
    assert plan.steps[0].result["result"] == 20
    # Step 2: 20 + 10 = 30
    assert plan.steps[1].result["result"] == 30
    # Step 3: 30 + 1 = 31
    assert plan.steps[2].result == 31

    # Verify blackboard entries
    assert bb.get("task-pipeline-1", "result") == 30
    assert bb.get("task-pipeline-1", "final_val") == 31

    # Verify checkpoints
    checkpoints = bb.get_checkpoints("task-pipeline-1")
    # Initial + 3 steps = 4 checkpoints
    assert len(checkpoints) == 4
    assert checkpoints[0].step_id == "init"
    assert checkpoints[1].step_id == "step_1"
    assert checkpoints[2].step_id == "step_2"
    assert checkpoints[3].step_id == "step_3"
    assert checkpoints[3].parent_step_id == "step_2"

    bb.close()
