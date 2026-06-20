"""
Reflection Engine — Self-improvement loop (no model training).

After every task, evaluates:
- Was the result correct?
- Could tool selection be better?
- Did a missing capability appear?
- Should a new plugin be created?
- Should memory be updated?

This is system-level learning — the system gets better
by recording experience, not by retraining weights.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ccos.core.capability_registry import get_capability_registry
from ccos.core.device_manager import get_device_manager


@dataclass
class TaskReflection:
    """Reflection on a single task execution."""
    task: str
    timestamp: float = field(default_factory=time.time)
    success: bool = False
    capability_used: str = ""
    duration_ms: float = 0
    missing_capabilities: List[str] = field(default_factory=list)
    tool_selection_score: float = 0.0
    improvements: List[str] = field(default_factory=list)
    should_create_plugin: bool = False
    plugin_category: str = ""
    memory_updated: bool = False
    error: str = ""


class ReflectionEngine:
    """
    Evaluates task executions and generates improvement insights.

    Does NOT retrain models. Instead:
    - Tracks which tools work best for which tasks
    - Identifies capability gaps
    - Suggests new plugins to create
    - Updates capability performance metrics
    - Records successful patterns for future reference
    """

    def __init__(self, log_path: str = None):
        self._log_path = log_path or str(
            Path(__file__).parent.parent / "data" / "reflections.jsonl"
        )
        self._registry = get_capability_registry()
        self._device = get_device_manager()
        self._reflections: List[TaskReflection] = []
        self._load()

    def reflect(
        self,
        task: str,
        success: bool,
        capability_used: str = "",
        duration_ms: float = 0,
        error: str = "",
        result: Any = None,
    ) -> TaskReflection:
        """
        Reflect on a completed task execution.

        Returns insights and recommendations for improvement.
        """
        reflection = TaskReflection(
            task=task,
            success=success,
            capability_used=capability_used,
            duration_ms=duration_ms,
            error=error,
        )

        # 1. Evaluate tool selection
        if capability_used:
            cap = self._registry.get(capability_used)
            if cap:
                reflection.tool_selection_score = cap.success_rate

                # Could a better tool have been used?
                hardware_hints = self._device.get_capabilities_hints()
                alternatives = self._registry.find_for_task(task, hardware_hints)
                for alt in alternatives:
                    if alt.name != capability_used and alt.success_rate > cap.success_rate:
                        reflection.improvements.append(
                            f"Consider using {alt.name} (success rate {alt.success_rate:.0%} "
                            f"vs {cap.success_rate:.0%})"
                        )

        # 2. Check for missing capabilities
        request_lower = task.lower()
        needed_signals = {
            "camera": ["photo", "picture", "camera", "capture", "screenshot"],
            "tts": ["speak", "say", "voice", "read aloud", "tts"],
            "stt": ["listen", "hear", "transcribe", "speech to text"],
            "ocr": ["ocr", "read text from image", "extract text"],
            "translation": ["translate", "translation"],
        }

        hardware_hints = self._device.get_capabilities_hints()
        available = self._registry.find_for_task(task, hardware_hints)
        available_categories = {c.category for c in available}

        for category, signals in needed_signals.items():
            if any(s in request_lower for s in signals):
                if category not in available_categories:
                    reflection.missing_capabilities.append(category)

        if reflection.missing_capabilities:
            reflection.should_create_plugin = True
            reflection.plugin_category = reflection.missing_capabilities[0]

        # 3. Generate improvement suggestions
        if not success and error:
            if "timeout" in error.lower():
                reflection.improvements.append("Increase timeout or optimize execution")
            elif "not found" in error.lower():
                reflection.improvements.append("Missing dependency — install or create plugin")
            elif "permission" in error.lower():
                reflection.improvements.append("Permission issue — check sandbox rules")

        if duration_ms > 10000:
            reflection.improvements.append("Task took >10s — consider caching or optimization")

        # Store reflection
        self._reflections.append(reflection)
        self._save(reflection)

        return reflection

    def get_improvement_summary(self) -> Dict[str, Any]:
        """
        Summarize all reflections into actionable insights.
        """
        if not self._reflections:
            return {"total_tasks": 0, "insights": []}

        total = len(self._reflections)
        successful = sum(1 for r in self._reflections if r.success)
        all_missing = set()
        all_improvements = []

        for r in self._reflections:
            all_missing.update(r.missing_capabilities)
            all_improvements.extend(r.improvements)

        # Count improvement frequency
        improvement_counts = {}
        for imp in all_improvements:
            improvement_counts[imp] = improvement_counts.get(imp, 0) + 1

        sorted_improvements = sorted(
            improvement_counts.items(), key=lambda x: -x[1]
        )

        return {
            "total_tasks": total,
            "success_rate": f"{successful / total:.0%}" if total > 0 else "N/A",
            "missing_capabilities": list(all_missing),
            "top_improvements": [
                {"suggestion": imp, "frequency": count}
                for imp, count in sorted_improvements[:5]
            ],
            "should_create_plugins": list(all_missing),
        }

    def get_capability_recommendations(self) -> List[Dict[str, str]]:
        """
        Recommend new capabilities based on reflection history.
        """
        all_missing = set()
        for r in self._reflections:
            all_missing.update(r.missing_capabilities)

        recommendations = []
        for cap in all_missing:
            recommendations.append({
                "capability": cap,
                "reason": f"Requested {sum(1 for r in self._reflections if cap in r.missing_capabilities)} times",
                "priority": "high" if sum(
                    1 for r in self._reflections if cap in r.missing_capabilities
                ) > 2 else "medium",
            })

        return recommendations

    def _save(self, reflection: TaskReflection):
        """Append reflection to log file."""
        try:
            path = Path(self._log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "task": reflection.task[:500],
                "timestamp": reflection.timestamp,
                "success": reflection.success,
                "capability_used": reflection.capability_used,
                "duration_ms": reflection.duration_ms,
                "missing_capabilities": reflection.missing_capabilities,
                "improvements": reflection.improvements,
                "should_create_plugin": reflection.should_create_plugin,
                "plugin_category": reflection.plugin_category,
            }
            with open(path, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            pass

    def _load(self):
        """Load recent reflections from log."""
        try:
            path = Path(self._log_path)
            if path.exists():
                lines = path.read_text().strip().splitlines()
                for line in lines[-100:]:  # last 100
                    try:
                        data = json.loads(line)
                        self._reflections.append(TaskReflection(**data))
                    except Exception:
                        continue
        except Exception:
            pass

    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent reflections."""
        return [
            {
                "task": r.task[:100],
                "success": r.success,
                "capability": r.capability_used,
                "improvements": r.improvements,
            }
            for r in self._reflections[-limit:]
        ]


# Singleton
_engine: Optional[ReflectionEngine] = None


def get_reflection_engine() -> ReflectionEngine:
    global _engine
    if _engine is None:
        _engine = ReflectionEngine()
    return _engine
