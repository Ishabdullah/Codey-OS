"""
Goal Engine — Proactive self-direction for CCOS.

Analyzes system usage history, detects inefficiencies,
generates candidate improvement goals, scores them by
expected utility, and injects top goals into the planner
so CCOS can proactively improve without user prompting.

This transforms CCOS from reactive self-improvement
to proactive self-directed optimization.

Data sources:
  - performance_tracker: capability metrics, trends, weak spots
  - memory DB: workflow history, event log
  - reflection_engine: improvement suggestions, missing capabilities
  - skill_recombiner: compound skill stats, pipeline patterns
  - capability_registry: registered capabilities and their metadata

Goals are derived ONLY from observed data — no hallucination.
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from ccos.core.capability_registry import get_capability_registry
from ccos.core.memory.ccos_memory import get_ccos_memory
from ccos.core.performance_tracker import get_performance_tracker
from ccos.core.reflection_engine import get_reflection_engine

GOALS_QUEUE_PATH = str(
    Path(__file__).parent.parent / "data" / "goals_queue.json"
)


# ── Data structures ────────────────────────────────────────────────

class GoalType(str, Enum):
    OPTIMIZE = "optimize"           # Improve existing capability speed/reliability
    CREATE = "create"               # Build missing capability
    RECOMBINE = "recombine"         # Combine existing capabilities into new skill
    FIX = "fix"                     # Fix broken or unreliable capability
    CONSOLIDATE = "consolidate"     # Merge redundant capabilities


class GoalStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    DEFERRED = "deferred"


@dataclass
class Goal:
    """A self-generated improvement goal."""
    id: str
    goal_type: GoalType
    title: str
    description: str
    target_capability: str = ""
    score: float = 0.0
    status: GoalStatus = GoalStatus.PROPOSED
    reason: str = ""
    evidence: List[str] = field(default_factory=list)
    expected_impact: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0
    attempts: int = 0
    result: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "goal_type": self.goal_type.value,
            "title": self.title,
            "description": self.description,
            "target_capability": self.target_capability,
            "score": round(self.score, 3),
            "status": self.status.value,
            "reason": self.reason,
            "evidence": self.evidence,
            "expected_impact": self.expected_impact,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "attempts": self.attempts,
            "result": self.result,
        }


# ── Scoring weights ────────────────────────────────────────────────

WEIGHT_FREQUENCY = 0.30      # How often the issue occurs
WEIGHT_IMPACT = 0.30         # Performance impact magnitude
WEIGHT_COMPLEXITY = 0.15     # Inverse of implementation complexity (higher = easier)
WEIGHT_DEPENDENCY = 0.10     # Are dependencies available?
WEIGHT_FAILURES = 0.15       # Historical failure rate for this area


# ── Goal Engine ────────────────────────────────────────────────────

class GoalEngine:
    """
    Generates, scores, and prioritizes improvement goals
    based on observed system performance and usage patterns.

    Runs after each task cycle to update the goal queue.
    Top goals are injected into the planner for proactive execution.
    """

    def __init__(self, queue_path: str = None):
        self._queue_path = queue_path or GOALS_QUEUE_PATH
        self._tracker = get_performance_tracker()
        self._registry = get_capability_registry()
        self._memory = get_ccos_memory()
        self._reflection = get_reflection_engine()
        self._goals: List[Goal] = []
        self._goal_counter = 0
        self._load_queue()

    def analyze_and_generate(self) -> List[Goal]:
        """
        Full pipeline: gather data → generate goals → score → sort → persist.

        Returns newly generated goals (not previously seen).
        """
        existing_ids = {g.id for g in self._goals}
        new_goals = []

        # Source 1: Weak capabilities → optimization goals
        new_goals.extend(self._goals_from_weak_capabilities())

        # Source 2: Missing capabilities from reflection → creation goals
        new_goals.extend(self._goals_from_missing_capabilities())

        # Source 3: Slow capabilities → speed optimization goals
        new_goals.extend(self._goals_from_slow_capabilities())

        # Source 4: Error-prone capabilities → fix goals
        new_goals.extend(self._goals_from_error_patterns())

        # Source 5: Compound skill opportunities → recombination goals
        new_goals.extend(self._goals_from_recombination_opportunities())

        # Source 6: Consolidation opportunities
        new_goals.extend(self._goals_from_redundancy())

        # Filter duplicates
        truly_new = [g for g in new_goals if g.id not in existing_ids]

        # Score all goals
        for goal in truly_new:
            goal.score = self._score_goal(goal)

        # Add to queue and sort
        self._goals.extend(truly_new)
        self._goals.sort(key=lambda g: -g.score)

        # Prune low-scoring goals (keep top 20)
        self._goals = self._goals[:20]

        # Persist
        self._save_queue()

        # Return new goals sorted by score
        truly_new.sort(key=lambda g: -g.score)
        return truly_new

    # ── Goal generators ────────────────────────────────────────────

    def _goals_from_weak_capabilities(self) -> List[Goal]:
        """Generate optimization goals for underperforming capabilities."""
        goals = []
        weak = self._tracker.get_weak_capabilities(min_uses=2, max_score=65)

        for w in weak:
            name = w["capability"]
            score_val = w.get("performance_score", 0)
            metrics = self._tracker.get_capability_metrics(name)
            trend = self._tracker.get_trend(name)

            evidence = []
            if score_val < 50:
                evidence.append(f"Performance score: {score_val}")
            if metrics.get("success_rate", 1) < 0.8:
                evidence.append(f"Success rate: {metrics['success_rate']:.0%}")
            if trend == "degrading":
                evidence.append(f"Trend: degrading")

            if evidence:
                goals.append(Goal(
                    id=f"opt_{name.replace('.', '_')}",
                    goal_type=GoalType.OPTIMIZE,
                    title=f"Optimize {name} (score: {score_val})",
                    description=f"Capability '{name}' has low performance score ({score_val}). "
                                f"Success rate: {metrics.get('success_rate', 'N/A')}. "
                                f"Trend: {trend}.",
                    target_capability=name,
                    reason=f"Low performance score ({score_val}) with {len(evidence)} indicators",
                    evidence=evidence,
                    expected_impact={
                        "metric": "performance_score",
                        "current": score_val,
                        "target": min(80, score_val + 25),
                    },
                ))

        return goals

    def _goals_from_missing_capabilities(self) -> List[Goal]:
        """Generate creation goals for capabilities users keep asking for."""
        goals = []
        reflection_summary = self._reflection.get_improvement_summary()
        missing = reflection_summary.get("missing_capabilities", [])

        # Count frequency of each missing capability from recent reflections
        recent = self._reflection.get_recent(limit=50)
        missing_counts: Dict[str, int] = {}
        for r in recent:
            for cap in r.get("improvements", []):
                if "missing" in cap.lower() or "create" in cap.lower():
                    missing_counts[cap] = missing_counts.get(cap, 0) + 1

        for category in missing:
            count = sum(1 for r in recent
                        if any(category in m.lower() for m in r.get("improvements", [])))
            count = max(count, 1)

            goals.append(Goal(
                id=f"create_{category}",
                goal_type=GoalType.CREATE,
                title=f"Create {category} capability",
                description=f"Users have requested '{category}' functionality {count} time(s). "
                            f"This capability does not currently exist.",
                target_capability=category,
                reason=f"Missing capability requested {count} time(s)",
                evidence=[f"Requested {count} times in recent reflections",
                          f"Category '{category}' has no active implementation"],
                expected_impact={
                    "metric": "capability_coverage",
                    "new_capability": category,
                },
            ))

        return goals

    def _goals_from_slow_capabilities(self) -> List[Goal]:
        """Generate speed optimization goals for slow capabilities."""
        goals = []
        all_metrics = self._tracker.get_all_metrics()

        for m in all_metrics:
            name = m.get("capability", "")
            if not name:
                continue
            detailed = self._tracker.get_capability_metrics(name)
            avg_ms = detailed.get("avg_duration_ms", 0)
            p95_ms = detailed.get("p95_duration_ms", 0)

            # Flag capabilities averaging > 2 seconds
            if avg_ms > 2000:
                goals.append(Goal(
                    id=f"speed_{name.replace('.', '_')}",
                    goal_type=GoalType.OPTIMIZE,
                    title=f"Speed up {name} (avg: {avg_ms:.0f}ms)",
                    description=f"Capability '{name}' averages {avg_ms:.0f}ms "
                                f"(p95: {p95_ms:.0f}ms). Consider caching or optimization.",
                    target_capability=name,
                    reason=f"Average execution time {avg_ms:.0f}ms exceeds 2s threshold",
                    evidence=[f"avg={avg_ms:.0f}ms", f"p95={p95_ms:.0f}ms"],
                    expected_impact={
                        "metric": "avg_duration_ms",
                        "current": avg_ms,
                        "target": avg_ms * 0.5,
                    },
                ))

        return goals

    def _goals_from_error_patterns(self) -> List[Goal]:
        """Generate fix goals for capabilities with high error rates."""
        goals = []
        all_metrics = self._tracker.get_all_metrics()

        for m in all_metrics:
            name = m.get("capability", "")
            if not name:
                continue
            detailed = self._tracker.get_capability_metrics(name)
            error_cats = detailed.get("error_categories", {})
            total_failures = detailed.get("failure_count", 0)
            total_uses = detailed.get("total_uses", 0)

            if total_uses < 3 or not error_cats:
                continue

            # Find dominant error category
            dominant_error = max(error_cats.items(), key=lambda x: x[1])
            error_name, error_count = dominant_error

            if error_count >= 2:
                goals.append(Goal(
                    id=f"fix_{name.replace('.', '_')}_{error_name}",
                    goal_type=GoalType.FIX,
                    title=f"Fix {error_name} errors in {name}",
                    description=f"Capability '{name}' has {error_count} '{error_name}' errors "
                                f"out of {total_uses} uses ({total_failures} total failures).",
                    target_capability=name,
                    reason=f"Repeated '{error_name}' errors ({error_count} occurrences)",
                    evidence=[
                        f"Error '{error_name}': {error_count} times",
                        f"Total failures: {total_failures}/{total_uses}",
                    ],
                    expected_impact={
                        "metric": "error_rate",
                        "current": total_failures / total_uses if total_uses else 0,
                        "target": 0,
                        "error_category": error_name,
                    },
                ))

        return goals

    def _goals_from_recombination_opportunities(self) -> List[Goal]:
        """Generate recombination goals for frequently co-used capabilities."""
        goals = []
        workflows = self._memory.structured.get_successful_workflows(limit=50)

        if len(workflows) < 3:
            return goals

        # Find capability pairs that appear together often
        pair_counts: Dict[tuple, int] = {}
        for wf in workflows:
            steps_raw = wf.get("steps", "[]")
            if isinstance(steps_raw, str):
                try:
                    steps = json.loads(steps_raw)
                except Exception:
                    continue
            else:
                steps = steps_raw

            caps = []
            for step in steps:
                if isinstance(step, dict) and "capability" in step:
                    caps.append(step["capability"])
                elif isinstance(step, str):
                    try:
                        parsed = json.loads(step)
                        if isinstance(parsed, dict) and "capability" in parsed:
                            caps.append(parsed["capability"])
                    except Exception:
                        pass

            # Count pairs
            for i in range(len(caps)):
                for j in range(i + 1, len(caps)):
                    pair = tuple(sorted([caps[i], caps[j]]))
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1

        for pair, count in pair_counts.items():
            if count >= 3:
                goals.append(Goal(
                    id=f"recomb_{pair[0].replace('.','_')}_{pair[1].replace('.','_')}",
                    goal_type=GoalType.RECOMBINE,
                    title=f"Combine {' + '.join(pair)} into compound skill",
                    description=f"Capabilities '{pair[0]}' and '{pair[1]}' are used together "
                                f"in {count} workflows. Consider creating a compound skill.",
                    target_capability=f"{pair[0]}+{pair[1]}",
                    reason=f"Co-used in {count} workflows",
                    evidence=[f"Pair appears in {count} successful workflows"],
                    expected_impact={
                        "metric": "workflow_efficiency",
                        "steps_reduced": 1,
                        "workflows_affected": count,
                    },
                ))

        return goals

    def _goals_from_redundancy(self) -> List[Goal]:
        """Generate consolidation goals for overlapping capabilities."""
        goals = []
        active = self._registry.get_active()

        # Group by category
        by_category: Dict[str, list] = {}
        for cap in active:
            by_category.setdefault(cap.category, []).append(cap)

        for category, caps in by_category.items():
            if len(caps) >= 3:
                # Check if descriptions overlap significantly
                names = [c.name for c in caps]
                goals.append(Goal(
                    id=f"consolidate_{category}",
                    goal_type=GoalType.CONSOLIDATE,
                    title=f"Review {category} capabilities ({len(caps)} exist)",
                    description=f"Category '{category}' has {len(caps)} capabilities: "
                                f"{', '.join(names[:5])}. Consider consolidating overlaps.",
                    target_capability=category,
                    reason=f"Category has {len(caps)} capabilities — potential redundancy",
                    evidence=[f"{len(caps)} capabilities in '{category}'"],
                    expected_impact={
                        "metric": "capability_clarity",
                        "capabilities_in_category": len(caps),
                    },
                ))

        return goals

    # ── Scoring ────────────────────────────────────────────────────

    def _score_goal(self, goal: Goal) -> float:
        """
        Score a goal on 0-1 scale based on:
        - Frequency of need (how often the issue occurs)
        - Performance impact (how much it would improve)
        - Complexity (easier goals score higher)
        - Dependency availability (can we build it now?)
        - Historical failures (more failures = higher priority)
        """
        scores = {}

        # Frequency — based on evidence count and goal type
        scores["frequency"] = min(1.0, len(goal.evidence) * 0.3)
        if goal.goal_type == GoalType.CREATE:
            # Missing capabilities requested multiple times
            for ev in goal.evidence:
                if "requested" in ev.lower():
                    import re
                    nums = re.findall(r"(\d+)", ev)
                    if nums:
                        scores["frequency"] = min(1.0, int(nums[0]) * 0.2)

        # Impact — based on expected impact magnitude
        impact = goal.expected_impact
        if "current" in impact and "target" in impact:
            current = impact["current"]
            target = impact["target"]
            if isinstance(current, (int, float)) and isinstance(target, (int, float)):
                if current > 0:
                    improvement = abs(current - target) / max(abs(current), 1)
                    scores["impact"] = min(1.0, improvement)
                else:
                    scores["impact"] = 0.5
            else:
                scores["impact"] = 0.5
        elif "new_capability" in impact:
            scores["impact"] = 0.8  # New capabilities have high impact
        elif "steps_reduced" in impact:
            scores["impact"] = min(1.0, impact.get("steps_reduced", 1) * 0.3)
        else:
            scores["impact"] = 0.4

        # Complexity — inverse of estimated difficulty
        complexity_map = {
            GoalType.FIX: 0.7,          # Fixes are usually straightforward
            GoalType.OPTIMIZE: 0.5,      # Moderate complexity
            GoalType.RECOMBINE: 0.8,     # Recombination is mostly automated
            GoalType.CREATE: 0.4,        # Creating new is harder
            GoalType.CONSOLIDATE: 0.3,   # Consolidation is risky
        }
        scores["complexity"] = complexity_map.get(goal.goal_type, 0.5)

        # Dependency — are prerequisites available?
        if goal.target_capability:
            cap = self._registry.get(goal.target_capability)
            if cap:
                scores["dependency"] = 0.9  # Capability exists
            elif goal.goal_type == GoalType.CREATE:
                scores["dependency"] = 0.6  # Need to build from scratch
            else:
                scores["dependency"] = 0.5
        else:
            scores["dependency"] = 0.7

        # Failure history — more failures = higher priority
        if goal.target_capability:
            metrics = self._tracker.get_capability_metrics(goal.target_capability)
            failure_count = metrics.get("failure_count", 0)
            scores["failures"] = min(1.0, failure_count * 0.15)
        else:
            scores["failures"] = 0.3

        # Weighted composite
        final = (
            scores["frequency"] * WEIGHT_FREQUENCY +
            scores["impact"] * WEIGHT_IMPACT +
            scores["complexity"] * WEIGHT_COMPLEXITY +
            scores["dependency"] * WEIGHT_DEPENDENCY +
            scores["failures"] * WEIGHT_FAILURES
        )

        return round(final, 3)

    # ── Queue management ───────────────────────────────────────────

    def get_top_goals(self, limit: int = 5) -> List[Goal]:
        """Get the highest-priority pending goals."""
        pending = [g for g in self._goals if g.status == GoalStatus.PROPOSED]
        return pending[:limit]

    def get_goal_by_id(self, goal_id: str) -> Optional[Goal]:
        return next((g for g in self._goals if g.id == goal_id), None)

    def update_goal_status(self, goal_id: str, status: GoalStatus,
                           result: str = ""):
        """Update a goal's status after execution attempt."""
        goal = self.get_goal_by_id(goal_id)
        if goal:
            goal.status = status
            goal.attempts += 1
            if result:
                goal.result = result
            if status in (GoalStatus.COMPLETED, GoalStatus.FAILED):
                goal.completed_at = time.time()
            self._save_queue()

    def get_queue(self) -> List[Dict[str, Any]]:
        """Get the full goal queue as dicts."""
        return [g.to_dict() for g in self._goals]

    def get_stats(self) -> Dict[str, Any]:
        """Get goal engine statistics."""
        total = len(self._goals)
        by_status = {}
        by_type = {}
        for g in self._goals:
            by_status[g.status.value] = by_status.get(g.status.value, 0) + 1
            by_type[g.goal_type.value] = by_type.get(g.goal_type.value, 0) + 1

        completed = [g for g in self._goals if g.status == GoalStatus.COMPLETED]
        avg_score = sum(g.score for g in self._goals) / total if total else 0

        return {
            "total_goals": total,
            "by_status": by_status,
            "by_type": by_type,
            "avg_score": round(avg_score, 3),
            "completed": len(completed),
            "top_goal": self._goals[0].title if self._goals else None,
        }

    # ── Persistence ────────────────────────────────────────────────

    def _save_queue(self):
        """Persist goal queue to disk."""
        try:
            path = Path(self._queue_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = [g.to_dict() for g in self._goals]
            path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def _load_queue(self):
        """Load goal queue from disk."""
        try:
            path = Path(self._queue_path)
            if path.exists():
                data = json.loads(path.read_text())
                for d in data:
                    d["goal_type"] = GoalType(d["goal_type"])
                    d["status"] = GoalStatus(d["status"])
                    self._goals.append(Goal(**d))
                self._goals.sort(key=lambda g: -g.score)
        except Exception:
            pass

    def inject_into_planner(self) -> Optional[str]:
        """
        Return the top goal as a task string for the planner.
        Returns None if no actionable goals exist.
        """
        top = self.get_top_goals(1)
        if not top:
            return None

        goal = top[0]
        goal.status = GoalStatus.IN_PROGRESS
        self._save_queue()

        # Format as a planner task
        if goal.goal_type == GoalType.OPTIMIZE:
            return f"Optimize capability '{goal.target_capability}': {goal.description}"
        elif goal.goal_type == GoalType.CREATE:
            return f"Create new capability for '{goal.target_capability}': {goal.description}"
        elif goal.goal_type == GoalType.FIX:
            return f"Fix errors in '{goal.target_capability}': {goal.description}"
        elif goal.goal_type == GoalType.RECOMBINE:
            parts = goal.target_capability.split("+")
            return f"Create compound skill combining {' and '.join(parts)}"
        elif goal.goal_type == GoalType.CONSOLIDATE:
            return f"Review and consolidate capabilities in '{goal.target_capability}'"
        return goal.description


# Singleton
_engine: Optional[GoalEngine] = None


def get_goal_engine() -> GoalEngine:
    global _engine
    if _engine is None:
        _engine = GoalEngine()
    return _engine
