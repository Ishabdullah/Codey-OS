"""
Planner — Reasoning and planning engine for CCOS.

Interprets user requests, breaks them into steps,
checks capability availability, and triggers plugin
creation when capabilities are missing.

Planning loop:
1. Understand goal
2. Check capabilities
3. If missing → initiate research + plugin creation
4. Execute task
5. Validate output
6. Store result in memory
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from ccos.core.capability_registry import get_capability_registry
from ccos.core.device_manager import get_device_manager
from ccos.core.plugin_manager import get_plugin_manager
from ccos.core.task_blackboard import get_task_blackboard
from ccos.core.task_context import TaskContext
from ccos.core.tool_router import get_tool_router


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class StepType(str, Enum):
    CAPABILITY_CALL = "capability_call"
    PLUGIN_INSTALL = "plugin_install"
    PLUGIN_CREATE = "plugin_create"
    PLUGIN_TEST = "plugin_test"
    CODE_EXEC = "code_exec"
    INFERENCE = "inference"
    VALIDATION = "validation"
    MEMORY_STORE = "memory_store"


@dataclass
class PlanStep:
    """A single step in a plan."""
    id: int
    description: str
    step_type: StepType
    capability: str = ""
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str = ""
    duration_ms: float = 0
    context_in_keys: List[str] = field(default_factory=list)
    context_out_keys: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    """A complete execution plan."""
    goal: str
    steps: List[PlanStep]
    created_at: float = field(default_factory=time.time)
    status: str = "pending"
    current_step: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "status": self.status,
            "current_step": self.current_step,
            "steps": [
                {
                    "id": s.id,
                    "description": s.description,
                    "type": s.step_type.value,
                    "capability": s.capability,
                    "status": s.status.value,
                    "context_in_keys": s.context_in_keys,
                    "context_out_keys": s.context_out_keys,
                }
                for s in self.steps
            ],
        }


class Planner:
    """
    The planning engine.

    Given a user request, creates an execution plan by:
    1. Analyzing the goal
    2. Checking what capabilities are available
    3. Identifying gaps (missing capabilities)
    4. Planning plugin creation for gaps
    5. Sequencing execution steps
    """

    def __init__(self):
        self._registry = get_capability_registry()
        self._router = get_tool_router()
        self._device = get_device_manager()

    def analyze_request(self, user_request: str) -> Dict[str, Any]:
        """
        Analyze a user request and determine what's needed.
        Returns structured analysis without creating a full plan.
        """
        hardware_hints = self._device.get_capabilities_hints()
        candidates = self._registry.find_for_task(user_request, hardware_hints)

        analysis = {
            "request": user_request,
            "available_capabilities": [
                {"name": c.name, "category": c.category, "success_rate": c.success_rate}
                for c in candidates
            ],
            "missing_capabilities": [],
            "requires_plugin_creation": False,
            "hardware_hints": hardware_hints,
        }

        # Identify potential gaps
        request_lower = user_request.lower()
        gap_keywords = {
            "camera": "camera",
            "photo": "camera",
            "video": "camera",
            "speak": "tts",
            "voice": "tts",
            "listen": "stt",
            "speech": "stt",
            "ocr": "ocr",
            "image": "vision",
            "screenshot": "screenshot",
        }

        needed_categories = set()
        for keyword, category in gap_keywords.items():
            if keyword in request_lower:
                needed_categories.add(category)

        available_categories = {c.category for c in candidates}
        missing = needed_categories - available_categories

        if missing:
            analysis["missing_capabilities"] = list(missing)
            analysis["requires_plugin_creation"] = True

        return analysis

    def create_plan(self, user_request: str) -> Plan:
        """
        Create a full execution plan for a user request.
        """
        steps = []
        step_id = 0

        analysis = self.analyze_request(user_request)

        # Step 1: Check if we need new capabilities
        if analysis["requires_plugin_creation"]:
            for missing in analysis["missing_capabilities"]:
                step_id += 1
                steps.append(PlanStep(
                    id=step_id,
                    description=f"Research and create plugin for: {missing}",
                    step_type=StepType.PLUGIN_CREATE,
                    metadata={"category": missing},
                ))

                step_id += 1
                steps.append(PlanStep(
                    id=step_id,
                    description=f"Test {missing} plugin in sandbox",
                    step_type=StepType.PLUGIN_TEST,
                    metadata={"category": missing},
                ))

        # Step 2: Execute the main task using available capabilities
        hardware_hints = self._device.get_capabilities_hints()
        candidates = self._registry.find_for_task(user_request, hardware_hints)

        if candidates:
            best = candidates[0]
            step_id += 1
            steps.append(PlanStep(
                id=step_id,
                description=f"Execute using {best.name}",
                step_type=StepType.CAPABILITY_CALL,
                capability=best.name,
            ))
        else:
            # Fall back to general inference
            step_id += 1
            steps.append(PlanStep(
                id=step_id,
                description="Process request via general inference",
                step_type=StepType.INFERENCE,
            ))

        # Step 3: Validate output
        step_id += 1
        steps.append(PlanStep(
            id=step_id,
            description="Validate result",
            step_type=StepType.VALIDATION,
        ))

        # Step 4: Store in memory
        step_id += 1
        steps.append(PlanStep(
            id=step_id,
            description="Store result in memory",
            step_type=StepType.MEMORY_STORE,
        ))

        plan = Plan(goal=user_request, steps=steps)
        return plan

    def get_missing_capabilities(self, user_request: str) -> List[str]:
        """
        Identify what capabilities are missing for a request.
        Used by the self-extension engine to trigger plugin creation.
        """
        analysis = self.analyze_request(user_request)
        return analysis["missing_capabilities"]

    def execute_goal(
        self,
        goal: str,
        context: Optional[TaskContext] = None,
        blackboard: Optional[Any] = None,
        plugin_manager: Optional[Any] = None,
        use_orchestrator: bool = True,
        raise_on_veto: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute a goal end-to-end.
        When use_orchestrator is True, deliberates via AgentOrchestrator (Safety Agent veto is live).
        Otherwise generates and executes a single-path Plan.
        """
        if use_orchestrator:
            from ccos.core.agent_orchestrator import get_agent_orchestrator
            orch = get_agent_orchestrator()
            return orch.execute_request(
                goal=goal,
                context=context,
                blackboard=blackboard,
                plugin_manager=plugin_manager,
                raise_on_veto=raise_on_veto,
            )
        else:
            plan = self.create_plan(goal)
            return self.execute_plan(
                plan=plan,
                context=context,
                blackboard=blackboard,
                plugin_manager=plugin_manager,
            )

    def execute_plan(
        self,
        plan: Plan,
        context: Optional[TaskContext] = None,
        blackboard: Optional[Any] = None,
        plugin_manager: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute a plan with threaded TaskContext and TaskBlackboard.

        Args:
            plan: The execution Plan.
            context: Initial TaskContext or None to create a default.
            blackboard: TaskBlackboard instance or None for default singleton.
            plugin_manager: PluginManager instance or None for default singleton.

        Returns:
            Dict containing final plan, final context, and status.
        """
        bb = blackboard or get_task_blackboard()
        pm = plugin_manager or get_plugin_manager()

        if context is None:
            task_id = f"task_{int(time.time() * 1000)}"
            context = TaskContext(task_id=task_id, step_id="init", goal=plan.goal)
            bb.create_task(task_id=task_id, goal=plan.goal)
        else:
            bb._ensure_task_session(context.task_id, context.goal)

        bb.save_checkpoint(context)
        plan.status = "executing"

        for step in plan.steps:
            plan.current_step = step.id
            step.status = StepStatus.IN_PROGRESS

            # Gather step inputs from blackboard & metadata
            step_inputs = dict(step.metadata.get("inputs", {}))
            if isinstance(step.context_in_keys, dict):
                for param_name, bb_key in step.context_in_keys.items():
                    bb_val = bb.get(context.task_id, bb_key)
                    if bb_val is not None:
                        step_inputs[param_name] = bb_val
            elif isinstance(step.context_in_keys, (list, tuple)):
                for in_key in step.context_in_keys:
                    bb_val = bb.get(context.task_id, in_key)
                    if bb_val is not None:
                        step_inputs[in_key] = bb_val

            # Evolve context for this step
            context = context.evolve(
                step_id=f"step_{step.id}",
                inputs=step_inputs,
                next_action=step.capability or step.description,
            )

            start_t = time.time()
            try:
                if step.step_type == StepType.CAPABILITY_CALL and step.capability:
                    step.result = pm.call_capability(step.capability, context=context, **step_inputs)
                else:
                    step.result = f"Executed {step.step_type.value}: {step.description}"
                step.status = StepStatus.COMPLETED
            except Exception as e:
                step.error = str(e)
                step.status = StepStatus.FAILED
            finally:
                step.duration_ms = (time.time() - start_t) * 1000

            # Store output keys in blackboard if successful
            if step.status == StepStatus.COMPLETED and step.context_out_keys:
                if isinstance(step.context_out_keys, dict):
                    for bb_key, res_key in step.context_out_keys.items():
                        if isinstance(step.result, dict) and res_key in step.result:
                            bb.set(context.task_id, bb_key, step.result[res_key])
                        else:
                            bb.set(context.task_id, bb_key, step.result)
                elif isinstance(step.context_out_keys, (list, tuple)):
                    if isinstance(step.result, dict):
                        for out_key in step.context_out_keys:
                            if out_key in step.result:
                                bb.set(context.task_id, out_key, step.result[out_key])
                            else:
                                bb.set(context.task_id, out_key, step.result)
                    elif len(step.context_out_keys) == 1:
                        bb.set(context.task_id, step.context_out_keys[0], step.result)

            # Evolve context with step output and save checkpoint
            context = context.evolve(output=step.result)
            bb.save_checkpoint(context)

            if step.status == StepStatus.FAILED:
                plan.status = "failed"
                bb.complete_task(context.task_id, "failed")
                break

        if plan.status != "failed":
            plan.status = "completed"
            bb.complete_task(context.task_id, "completed")

        return {
            "plan": plan,
            "context": context,
            "status": plan.status,
        }


# Singleton
_planner: Optional[Planner] = None


def get_planner() -> Planner:
    global _planner
    if _planner is None:
        _planner = Planner()
    return _planner
