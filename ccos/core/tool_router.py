"""
Tool Router — Intelligent tool selection engine.

Chooses the best tool for a task based on:
- Hardware availability
- Past performance metrics
- Speed and reliability
- User preferences learned over time
"""

import time
from typing import Any, Dict, List, Optional, Tuple

from ccos.core.capability_registry import (
    Capability,
    CapabilityStatus,
    get_capability_registry,
)
from ccos.core.device_manager import get_device_manager
from ccos.core.sandbox import BLOCKED_COMMANDS


def validate_tool_safety(
    capability_name: str,
    params: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """
    Validate whether capability name and parameters conform to safety rules.
    Checks against BLOCKED_COMMANDS and destructive operations.

    Returns:
        (is_safe, reason)
    """
    target_texts = [str(capability_name).lower()]

    if params:
        def _extract_strings(val: Any) -> List[str]:
            res = []
            if isinstance(val, str):
                res.append(val.lower())
            elif isinstance(val, dict):
                for k, v in val.items():
                    res.append(str(k).lower())
                    res.extend(_extract_strings(v))
            elif isinstance(val, (list, tuple, set)):
                for item in val:
                    res.extend(_extract_strings(item))
            elif val is not None:
                res.append(str(val).lower())
            return res

        target_texts.extend(_extract_strings(params))

    combined_text = " ".join(target_texts)

    for blocked in BLOCKED_COMMANDS:
        if blocked.lower() in combined_text:
            return False, f"Blocked command detected: '{blocked}'"

    destructive_keywords = [
        "rm -rf", "delete all", "drop table", "truncate",
        "format disk", "mkfs", "dd if=", ":(){:|:&};:",
        "chmod 777 /", "chown root", "> /dev/sda",
    ]
    for kw in destructive_keywords:
        if kw in combined_text:
            return False, f"Destructive operation detected: '{kw}'"

    # System directory modification
    for sys_dir in ["/etc/", "/var/", "/usr/", "/root/"]:
        if sys_dir in combined_text:
            if not any(safe_op in combined_text for safe_op in ["read", "list", "check", "inspect", "get", "status"]):
                return False, f"System directory modification detected for '{sys_dir}'"

    return True, "Safe"


class ToolCandidate:
    """A candidate tool for a task."""

    def __init__(self, capability: Capability, score: float = 0.0, reason: str = ""):
        self.capability = capability
        self.score = score
        self.reason = reason


class ToolRouter:
    """
    Selects the best tool for a given task.

    Scoring factors:
    - Hardware compatibility (must-have)
    - Success rate (learned from past use)
    - Average response time
    - Recency of last successful use
    - Category match to task
    """

    def __init__(self):
        self._registry = get_capability_registry()
        self._device = get_device_manager()
        self._task_history: List[Dict[str, Any]] = []

    def route(self, task: str, category_hint: str = None) -> Optional[ToolCandidate]:
        """
        Find the best tool for a task.

        Returns the top-scored candidate, or None if nothing matches.
        """
        hardware_hints = self._device.get_capabilities_hints()
        candidates = self._registry.find_for_task(task, hardware_hints)

        if not candidates:
            return None

        scored = []
        for cap in candidates:
            score, reason = self._score_candidate(cap, task, category_hint, hardware_hints)
            scored.append(ToolCandidate(capability=cap, score=score, reason=reason))

        scored.sort(key=lambda c: -c.score)
        return scored[0] if scored else None

    def route_all(self, task: str, category_hint: str = None, limit: int = 5) -> List[ToolCandidate]:
        """Get all matching candidates ranked by score."""
        hardware_hints = self._device.get_capabilities_hints()
        candidates = self._registry.find_for_task(task, hardware_hints)

        scored = []
        for cap in candidates:
            score, reason = self._score_candidate(cap, task, category_hint, hardware_hints)
            scored.append(ToolCandidate(capability=cap, score=score, reason=reason))

        scored.sort(key=lambda c: -c.score)
        return scored[:limit]

    def _score_candidate(
        self,
        cap: Capability,
        task: str,
        category_hint: str,
        hardware_hints: List[str],
    ) -> Tuple[float, str]:
        """Score a capability candidate for a task."""
        score = 0.0
        reasons = []

        # Hardware compatibility — hard requirement
        for req in cap.hardware_requirements:
            if req not in hardware_hints:
                return 0.0, f"missing hardware: {req}"

        # Base score from keyword match
        task_words = set(task.lower().split())
        cap_text = f"{cap.name} {cap.description}".lower()
        matches = sum(1 for w in task_words if w in cap_text)
        keyword_score = min(1.0, matches / max(1, len(task_words)))
        score += keyword_score * 30
        if keyword_score > 0.5:
            reasons.append(f"keyword match ({keyword_score:.0%})")

        # Category bonus
        if category_hint and cap.category == category_hint:
            score += 20
            reasons.append("category match")

        # Success rate (learned performance)
        score += cap.success_rate * 25
        if cap.use_count > 0:
            reasons.append(f"success rate {cap.success_rate:.0%}")

        # Speed bonus (faster = higher score)
        if cap.avg_duration_ms > 0:
            speed_score = max(0, 15 - (cap.avg_duration_ms / 1000))
            score += speed_score
            reasons.append(f"avg {cap.avg_duration_ms:.0f}ms")

        # Recency bonus
        if cap.last_used > 0:
            age_hours = (time.time() - cap.last_used) / 3600
            recency = max(0, 10 - age_hours)
            score += recency

        # Experimental penalty
        if cap.status == CapabilityStatus.EXPERIMENTAL:
            score *= 0.7
            reasons.append("experimental")

        return score, "; ".join(reasons) if reasons else "no strong signal"

    def record_task_result(self, task: str, capability_name: str, success: bool, duration_ms: float = 0):
        """Record the result of using a tool for learning."""
        self._registry.record_use(capability_name, success, duration_ms)
        self._task_history.append({
            "task": task[:200],
            "capability": capability_name,
            "success": success,
            "duration_ms": duration_ms,
            "timestamp": time.time(),
        })

    def get_recommendations(self, task: str) -> List[Dict[str, Any]]:
        """
        Get tool recommendations for a task with explanations.
        Returns a list of options ranked by suitability.
        """
        candidates = self.route_all(task)
        return [
            {
                "name": c.capability.name,
                "description": c.capability.description,
                "score": round(c.score, 1),
                "reason": c.reason,
                "success_rate": f"{c.capability.success_rate:.0%}",
                "uses": c.capability.use_count,
            }
            for c in candidates
        ]

    def validate_tool_safety(
        self,
        capability_name: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Validate safety of a tool/capability and its parameters."""
        return validate_tool_safety(capability_name, params)


# Singleton
_router: Optional[ToolRouter] = None


def get_tool_router() -> ToolRouter:
    global _router
    if _router is None:
        _router = ToolRouter()
    return _router
