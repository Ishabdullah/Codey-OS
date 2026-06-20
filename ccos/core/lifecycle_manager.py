"""
Lifecycle Manager — Orchestrates the full CCOS task lifecycle.

Pipeline: task → plan → execute → evaluate → improve → register → store

This is the top-level orchestrator that ensures every task
passes through the complete closed-loop improvement cycle.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ccos.core.auto_improvement_loop import LoopResult, get_improvement_loop
from ccos.core.capability_registry import get_capability_registry
from ccos.core.memory.ccos_memory import get_ccos_memory
from ccos.core.performance_tracker import get_performance_tracker
from ccos.core.planner import get_planner, Plan, PlanStep, StepType
from ccos.core.plugin_manager import get_plugin_manager
from ccos.core.reflection_engine import get_reflection_engine
from ccos.core.tool_router import get_tool_router


class LifecycleStage(str, Enum):
    RECEIVED = "received"
    PLANNING = "planning"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    IMPROVING = "improving"
    REGISTERING = "registering"
    STORING = "storing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class LifecycleEvent:
    """A single event in the lifecycle pipeline."""
    stage: LifecycleStage
    timestamp: float = field(default_factory=time.time)
    details: str = ""
    duration_ms: float = 0
    success: bool = True


@dataclass
class LifecycleResult:
    """Complete result of a lifecycle-managed task execution."""
    task: str
    stage: LifecycleStage
    success: bool
    plan: Optional[Plan] = None
    execution_result: Any = None
    loop_result: Optional[LoopResult] = None
    events: List[LifecycleEvent] = field(default_factory=list)
    total_duration_ms: float = 0
    capability_used: str = ""
    improvement_applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task[:200],
            "final_stage": self.stage.value,
            "success": self.success,
            "capability_used": self.capability_used,
            "total_duration_ms": round(self.total_duration_ms, 1),
            "improvement_applied": self.improvement_applied,
            "plan_steps": len(self.plan.steps) if self.plan else 0,
            "events": len(self.events),
        }

    def summary(self) -> str:
        lines = [f"Task: {self.task[:80]}"]
        lines.append(f"Status: {'SUCCESS' if self.success else 'FAILED'} at {self.stage.value}")
        if self.capability_used:
            lines.append(f"Capability: {self.capability_used}")
        lines.append(f"Duration: {self.total_duration_ms:.0f}ms")
        if self.improvement_applied:
            lines.append(f"Improvement applied: v{self.loop_result.new_version}")
        if self.loop_result and self.loop_result.reflection:
            imps = self.loop_result.reflection.improvements
            if imps:
                lines.append(f"Suggestions: {'; '.join(imps[:3])}")
        return "\n".join(lines)


class LifecycleManager:
    """
    Orchestrates the full CCOS task lifecycle.

    Ensures every task goes through:
    1. Planning (capability check, gap detection)
    2. Execution (tool routing, plugin invocation)
    3. Evaluation (reflection, performance tracking)
    4. Improvement (optimization if needed)
    5. Registration (capability registry update)
    6. Storage (memory DB persistence)
    """

    def __init__(self):
        self._planner = get_planner()
        self._router = get_tool_router()
        self._plugin_manager = get_plugin_manager()
        self._improvement_loop = get_improvement_loop()
        self._memory = get_ccos_memory()
        self._registry = get_capability_registry()
        self._tracker = get_performance_tracker()

    def execute_task(
        self,
        task: str,
        executor: Callable = None,
        yolo: bool = False,
    ) -> LifecycleResult:
        """
        Execute a task through the full lifecycle pipeline.

        Args:
            task: The user's task/request
            executor: Optional callable that performs the actual task execution.
                      If None, uses plugin_manager.call_capability or falls back
                      to routing through the tool router.
            yolo: Skip confirmation prompts

        Returns:
            LifecycleResult with complete execution trace
        """
        start_time = time.time()
        result = LifecycleResult(task=task, stage=LifecycleStage.RECEIVED, success=False)

        # ── Stage 1: Planning ────────────────────────────────────────
        result.events.append(LifecycleEvent(
            stage=LifecycleStage.PLANNING, details="Analyzing task"
        ))
        result.stage = LifecycleStage.PLANNING

        plan = self._planner.create_plan(task)
        result.plan = plan

        # ── Stage 2: Route to best capability ────────────────────────
        candidate = self._router.route(task)
        capability_name = ""
        if candidate:
            capability_name = candidate.capability.name
        result.capability_used = capability_name

        # ── Stage 3: Execute ─────────────────────────────────────────
        result.events.append(LifecycleEvent(
            stage=LifecycleStage.EXECUTING,
            details=f"Using capability: {capability_name or 'general inference'}",
        ))
        result.stage = LifecycleStage.EXECUTING

        exec_start = time.time()
        exec_success = False
        exec_result = None
        exec_error = ""

        try:
            if executor:
                # Custom executor provided
                exec_result = executor(task)
                exec_success = True
            elif capability_name:
                # Use plugin system
                exec_result = self._plugin_manager.call_capability(capability_name)
                exec_success = True
            else:
                # No capability matched — return analysis
                exec_result = {
                    "status": "no_capability",
                    "analysis": self._planner.analyze_request(task),
                    "message": "No matching capability found. Task passed to general inference.",
                }
                exec_success = True  # Not a failure, just no match
        except Exception as e:
            exec_error = str(e)
            exec_result = {"error": exec_error}

        exec_duration = (time.time() - exec_start) * 1000
        result.execution_result = exec_result
        result.events.append(LifecycleEvent(
            stage=LifecycleStage.EXECUTING,
            details=f"{'Success' if exec_success else 'Failed'} in {exec_duration:.0f}ms",
            duration_ms=exec_duration,
            success=exec_success,
        ))

        # ── Stage 4: Evaluate + Improve ──────────────────────────────
        result.events.append(LifecycleEvent(
            stage=LifecycleStage.EVALUATING, details="Running reflection + improvement loop"
        ))
        result.stage = LifecycleStage.EVALUATING

        loop_result = self._improvement_loop.after_task(
            task=task,
            success=exec_success,
            capability_used=capability_name,
            duration_ms=exec_duration,
            error=exec_error,
            result=exec_result,
        )
        result.loop_result = loop_result
        result.improvement_applied = loop_result.improved

        if loop_result.improved:
            result.events.append(LifecycleEvent(
                stage=LifecycleStage.IMPROVING,
                details=f"Upgraded to v{loop_result.new_version}",
            ))

        # ── Stage 5: Register ────────────────────────────────────────
        if capability_name:
            result.events.append(LifecycleEvent(
                stage=LifecycleStage.REGISTERING,
                details="Updating capability registry",
            ))
            result.stage = LifecycleStage.REGISTERING

            # Performance is already tracked by improvement_loop,
            # but we also update the registry's basic counters
            self._registry.record_use(
                capability_name, exec_success, exec_duration
            )

        # ── Stage 6: Store ───────────────────────────────────────────
        result.events.append(LifecycleEvent(
            stage=LifecycleStage.STORING, details="Persisting to memory"
        ))
        result.stage = LifecycleStage.STORING
        # Memory storage is handled by improvement_loop.after_task

        # ── Complete ─────────────────────────────────────────────────
        result.stage = LifecycleStage.COMPLETE
        result.success = exec_success
        result.total_duration_ms = (time.time() - start_time) * 1000
        result.events.append(LifecycleEvent(
            stage=LifecycleStage.COMPLETE,
            details=f"Total: {result.total_duration_ms:.0f}ms",
        ))

        return result

    def run_diagnostic(self) -> Dict[str, Any]:
        """
        Run a full system diagnostic.
        Shows health of all capabilities and improvement loop status.
        """
        health = self._improvement_loop.get_system_health()
        all_metrics = self._tracker.get_all_metrics()
        weak = self._tracker.get_weak_capabilities()

        return {
            "system_health": health,
            "total_capabilities": len(all_metrics),
            "weak_capabilities": [
                {"name": w["capability"], "score": w["performance_score"]}
                for w in weak
            ],
            "version_history": {
                m["capability"]: self._tracker.get_version_history(m["capability"])
                for m in all_metrics[:10]
            },
        }

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent lifecycle execution history."""
        return self._improvement_loop.get_loop_history(limit)


# Singleton
_manager: Optional[LifecycleManager] = None


def get_lifecycle_manager() -> LifecycleManager:
    global _manager
    if _manager is None:
        _manager = LifecycleManager()
    return _manager
