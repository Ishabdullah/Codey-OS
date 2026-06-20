"""
Auto-Improvement Loop — Runs after every task.

Connects: reflection → performance tracking → optimization → registry update

This is the closed-loop system that makes CCOS self-improving.
After each task execution, it:
1. Calls reflection engine to evaluate the result
2. Logs detailed metrics via performance tracker
3. If inefficiency detected, triggers capability optimizer
4. Updates capability registry with any improvements
5. Stores everything in memory DB
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ccos.core.capability_optimizer import get_capability_optimizer
from ccos.core.capability_registry import get_capability_registry
from ccos.core.memory.ccos_memory import get_ccos_memory
from ccos.core.performance_tracker import get_performance_tracker
from ccos.core.reflection_engine import TaskReflection, get_reflection_engine


@dataclass
class LoopResult:
    """Result of a single improvement loop iteration."""
    task: str
    capability_used: str
    success: bool
    duration_ms: float
    reflection: Optional[TaskReflection] = None
    optimization_triggered: bool = False
    optimization_result: Optional[Any] = None
    new_version: str = ""
    improved: bool = False
    stored_in_memory: bool = False


class AutoImprovementLoop:
    """
    The closed-loop self-improvement engine.

    Runs automatically after every task execution.
    Ensures continuous learning and capability improvement
    without model retraining.
    """

    def __init__(self, auto_optimize: bool = True, min_uses_for_optimize: int = 3):
        self._reflection = get_reflection_engine()
        self._tracker = get_performance_tracker()
        self._optimizer = get_capability_optimizer()
        self._registry = get_capability_registry()
        self._memory = get_ccos_memory()
        self._auto_optimize = auto_optimize
        self._min_uses = min_uses_for_optimize
        self._loop_history: List[LoopResult] = []

    def after_task(
        self,
        task: str,
        success: bool,
        capability_used: str = "",
        duration_ms: float = 0,
        error: str = "",
        result: Any = None,
        retries: int = 0,
    ) -> LoopResult:
        """
        Execute the full improvement loop after a task.

        This is the main entry point — call after every task execution.
        """
        loop_result = LoopResult(
            task=task,
            capability_used=capability_used,
            success=success,
            duration_ms=duration_ms,
        )

        # ── Step 1: Reflect ──────────────────────────────────────────
        reflection = self._reflection.reflect(
            task=task,
            success=success,
            capability_used=capability_used,
            duration_ms=duration_ms,
            error=error,
            result=result,
        )
        loop_result.reflection = reflection

        # ── Step 2: Track performance ────────────────────────────────
        if capability_used:
            cap = self._registry.get(capability_used)
            version = cap.version if cap else "1.0.0"

            # Classify error
            error_category = self._classify_error(error)

            self._tracker.record_execution(
                capability=capability_used,
                version=version,
                duration_ms=duration_ms,
                success=success,
                retries=retries,
                error_category=error_category,
                error_detail=error[:500] if error else "",
            )

            # Take periodic snapshots
            cap_metrics = self._tracker.get_capability_metrics(capability_used)
            if cap_metrics.get("total_uses", 0) % 10 == 0:
                self._tracker.take_snapshot(capability_used)

        # ── Step 3: Check for optimization opportunity ───────────────
        if self._auto_optimize and capability_used:
            should_optimize = self._should_optimize(capability_used)

            if should_optimize:
                loop_result.optimization_triggered = True
                opt_result = self._optimizer.optimize(capability_used)
                loop_result.optimization_result = opt_result

                if opt_result and opt_result.improved:
                    loop_result.improved = True
                    loop_result.new_version = opt_result.new_version

                    # Log the improvement
                    self._memory.events.log(
                        event_type="capability_improved",
                        source=capability_used,
                        details=f"v{opt_result.old_version} → v{opt_result.new_version}",
                        metadata={
                            "old_score": opt_result.old_score,
                            "new_score": opt_result.new_score,
                        },
                    )

        # ── Step 4: Store in memory ──────────────────────────────────
        self._memory.store_task_result(
            task=task,
            result=str(result)[:500] if result else "",
            success=success,
            capability=capability_used,
            duration_ms=duration_ms,
        )

        # Store reflection insights
        if reflection.improvements:
            for imp in reflection.improvements:
                self._memory.events.log(
                    event_type="improvement_suggestion",
                    source=capability_used,
                    details=imp,
                )

        loop_result.stored_in_memory = True
        self._loop_history.append(loop_result)

        return loop_result

    def _should_optimize(self, capability: str) -> bool:
        """
        Decide whether to trigger optimization for a capability.

        Triggers when:
        - Success rate drops below 70% (with enough data)
        - Performance trend is degrading
        - Error rate is increasing
        """
        metrics = self._tracker.get_capability_metrics(capability)
        total_uses = metrics.get("total_uses", 0)

        if total_uses < self._min_uses:
            return False

        # Check success rate
        success_rate = metrics.get("success_rate", 1.0)
        if success_rate < 0.7:
            return True

        # Check trend
        trend = self._tracker.get_trend(capability)
        if trend == "degrading":
            return True

        # Check score
        score = metrics.get("performance_score", 100)
        if score < 50:
            return True

        return False

    def _classify_error(self, error: str) -> str:
        """Classify an error string into a category."""
        if not error:
            return ""
        error_lower = error.lower()
        if "timeout" in error_lower:
            return "timeout"
        if "permission" in error_lower:
            return "permission"
        if "not found" in error_lower or "filenotfound" in error_lower:
            return "not_found"
        if "import" in error_lower or "modulenotfound" in error_lower:
            return "import"
        if "memory" in error_lower or "oom" in error_lower:
            return "memory"
        if "connection" in error_lower or "network" in error_lower:
            return "network"
        if "syntax" in error_lower:
            return "syntax"
        if "type" in error_lower or "value" in error_lower:
            return "type_error"
        return "other"

    def get_loop_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent loop iteration results."""
        results = []
        for r in self._loop_history[-limit:]:
            entry = {
                "task": r.task[:100],
                "capability": r.capability_used,
                "success": r.success,
                "duration_ms": r.duration_ms,
                "optimization_triggered": r.optimization_triggered,
                "improved": r.improved,
                "new_version": r.new_version,
            }
            if r.reflection:
                entry["improvements_suggested"] = r.reflection.improvements
            results.append(entry)
        return results

    def get_system_health(self) -> Dict[str, Any]:
        """
        Get overall system health metrics.
        Shows how the improvement loop is performing.
        """
        all_metrics = self._tracker.get_all_metrics()
        total_caps = len(all_metrics)
        healthy = sum(1 for m in all_metrics if m.get("performance_score", 0) >= 70)
        weak = sum(1 for m in all_metrics if m.get("performance_score", 100) < 50)

        improvements = sum(1 for r in self._loop_history if r.improved)
        optimizations = sum(1 for r in self._loop_history if r.optimization_triggered)

        return {
            "total_capabilities": total_caps,
            "healthy": healthy,
            "weak": weak,
            "total_loop_iterations": len(self._loop_history),
            "optimizations_triggered": optimizations,
            "successful_improvements": improvements,
            "improvement_rate": (
                f"{improvements / optimizations:.0%}"
                if optimizations > 0 else "N/A"
            ),
        }


# Singleton
_loop: Optional[AutoImprovementLoop] = None


def get_improvement_loop() -> AutoImprovementLoop:
    global _loop
    if _loop is None:
        _loop = AutoImprovementLoop()
    return _loop
