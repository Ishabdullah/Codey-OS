#!/usr/bin/env python3
"""
CCOS Goal Engine Test Suite.

Tests goal generation from real system data,
scoring, prioritization, queue management,
and planner injection.
"""

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ccos.core.goal_engine import (
    GoalEngine,
    Goal,
    GoalType,
    GoalStatus,
    get_goal_engine,
)
from ccos.core.performance_tracker import PerformanceTracker
from ccos.core.capability_registry import (
    Capability,
    CapabilityRegistry,
    CapabilityStatus,
)
from ccos.core.memory.ccos_memory import CCOSMemory
from ccos.core.reflection_engine import ReflectionEngine


def _make_temp_tracker():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return PerformanceTracker(db_path=f.name), f.name


def _make_temp_registry():
    f = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    f.close()
    return CapabilityRegistry(store_path=f.name), f.name


def _make_temp_memory():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return CCOSMemory(db_path=f.name), f.name


def _make_temp_reflection():
    f = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    f.close()
    return ReflectionEngine(log_path=f.name), f.name


def _seed_capabilities(registry):
    caps = [
        Capability(name="system.info", description="Read system info",
                   implementation="/tmp/si.py", category="system"),
        Capability(name="system.processes", description="List processes",
                   implementation="/tmp/sp.py", category="system"),
        Capability(name="vision.camera_capture", description="Capture image",
                   implementation="/tmp/cam.py", category="vision"),
    ]
    for c in caps:
        registry.register(c)


def test_goal_from_weak_capabilities():
    """Goals should be generated for underperforming capabilities."""
    print("Testing Goals from Weak Capabilities...")
    tracker, db = _make_temp_tracker()
    registry, reg = _make_temp_registry()
    memory, mem = _make_temp_memory()
    reflection, ref = _make_temp_reflection()

    _seed_capabilities(registry)

    # Create weak performance data
    for i in range(10):
        tracker.record_execution(
            capability="system.info", version="1.0.0",
            duration_ms=200, success=i < 5,
            error_category="timeout" if i >= 5 else "",
        )

    engine = GoalEngine(queue_path=tempfile.mktemp(suffix=".json"))
    engine._tracker = tracker
    engine._registry = registry
    engine._memory = memory
    engine._reflection = reflection

    goals = engine.analyze_and_generate()
    assert len(goals) >= 1, f"Expected at least 1 goal, got {len(goals)}"

    weak_goals = [g for g in goals if g.goal_type == GoalType.OPTIMIZE]
    assert len(weak_goals) >= 1, "Should have optimization goal for weak capability"
    assert any("system.info" in g.target_capability for g in weak_goals)
    assert all(g.score > 0 for g in goals)

    print(f"  [PASS] Generated {len(goals)} goal(s)")
    for g in goals[:3]:
        print(f"    [{g.goal_type.value}] {g.title} (score={g.score})")

    Path(db).unlink(missing_ok=True)
    Path(reg).unlink(missing_ok=True)
    Path(mem).unlink(missing_ok=True)
    Path(ref).unlink(missing_ok=True)
    return True


def test_goal_from_slow_capabilities():
    """Goals should be generated for slow capabilities."""
    print("Testing Goals from Slow Capabilities...")
    tracker, db = _make_temp_tracker()
    registry, reg = _make_temp_registry()
    memory, mem = _make_temp_memory()
    reflection, ref = _make_temp_reflection()

    _seed_capabilities(registry)

    # Create slow performance data (>2s average)
    for i in range(5):
        tracker.record_execution(
            capability="system.info", version="1.0.0",
            duration_ms=3000 + i * 500, success=True,
        )

    engine = GoalEngine(queue_path=tempfile.mktemp(suffix=".json"))
    engine._tracker = tracker
    engine._registry = registry
    engine._memory = memory
    engine._reflection = reflection

    goals = engine.analyze_and_generate()
    speed_goals = [g for g in goals if "Speed" in g.title or "speed" in g.title.lower()]
    assert len(speed_goals) >= 1, "Should have speed goal for slow capability"
    assert speed_goals[0].expected_impact.get("current", 0) > 2000

    print(f"  [PASS] Speed goal: {speed_goals[0].title}")

    Path(db).unlink(missing_ok=True)
    Path(reg).unlink(missing_ok=True)
    Path(mem).unlink(missing_ok=True)
    Path(ref).unlink(missing_ok=True)
    return True


def test_goal_from_error_patterns():
    """Goals should be generated for capabilities with repeated errors."""
    print("Testing Goals from Error Patterns...")
    tracker, db = _make_temp_tracker()
    registry, reg = _make_temp_registry()
    memory, mem = _make_temp_memory()
    reflection, ref = _make_temp_reflection()

    _seed_capabilities(registry)

    # Create error-prone data
    for i in range(8):
        tracker.record_execution(
            capability="vision.camera_capture", version="1.0.0",
            duration_ms=100, success=i >= 3,
            error_category="permission" if i < 3 else "",
            error_detail="Permission denied" if i < 3 else "",
        )

    engine = GoalEngine(queue_path=tempfile.mktemp(suffix=".json"))
    engine._tracker = tracker
    engine._registry = registry
    engine._memory = memory
    engine._reflection = reflection

    goals = engine.analyze_and_generate()
    fix_goals = [g for g in goals if g.goal_type == GoalType.FIX]
    assert len(fix_goals) >= 1, "Should have fix goal"
    assert "permission" in fix_goals[0].title.lower() or "permission" in fix_goals[0].description.lower()

    print(f"  [PASS] Fix goal: {fix_goals[0].title}")

    Path(db).unlink(missing_ok=True)
    Path(reg).unlink(missing_ok=True)
    Path(mem).unlink(missing_ok=True)
    Path(ref).unlink(missing_ok=True)
    return True


def test_goal_from_recombination():
    """Goals should be generated for frequently co-used capabilities."""
    print("Testing Goals from Recombination Opportunities...")
    tracker, db = _make_temp_tracker()
    registry, reg = _make_temp_registry()
    memory, mem = _make_temp_memory()
    reflection, ref = _make_temp_reflection()

    _seed_capabilities(registry)

    # Seed workflows with repeated co-usage
    for i in range(5):
        steps = [
            {"capability": "system.info", "task": "info"},
            {"capability": "system.processes", "task": "procs"},
        ]
        memory.structured.store_workflow(
            name=f"monitor_{i}", goal="monitor",
            steps=[json.dumps(s) for s in steps],
            result="ok", success=True,
        )

    engine = GoalEngine(queue_path=tempfile.mktemp(suffix=".json"))
    engine._tracker = tracker
    engine._registry = registry
    engine._memory = memory
    engine._reflection = reflection

    goals = engine.analyze_and_generate()
    recomb_goals = [g for g in goals if g.goal_type == GoalType.RECOMBINE]
    assert len(recomb_goals) >= 1, f"Should have recombination goal, got {len(goals)} goals total"

    print(f"  [PASS] Recombination goal: {recomb_goals[0].title}")

    Path(db).unlink(missing_ok=True)
    Path(reg).unlink(missing_ok=True)
    Path(mem).unlink(missing_ok=True)
    Path(ref).unlink(missing_ok=True)
    return True


def test_goal_scoring():
    """Goals should be scored and sorted correctly."""
    print("Testing Goal Scoring...")
    tracker, db = _make_temp_tracker()
    registry, reg = _make_temp_registry()
    memory, mem = _make_temp_memory()
    reflection, ref = _make_temp_reflection()

    _seed_capabilities(registry)

    # Create data for two capabilities with different severity
    for i in range(10):
        tracker.record_execution(
            capability="system.info", version="1.0.0",
            duration_ms=200, success=i < 4,  # 40% success — very bad
            error_category="timeout",
        )
        tracker.record_execution(
            capability="system.processes", version="1.0.0",
            duration_ms=200, success=i < 8,  # 80% success — mild
            error_category="timeout",
        )

    engine = GoalEngine(queue_path=tempfile.mktemp(suffix=".json"))
    engine._tracker = tracker
    engine._registry = registry
    engine._memory = memory
    engine._reflection = reflection

    goals = engine.analyze_and_generate()
    assert len(goals) >= 2

    # Goals should be sorted by score descending
    for i in range(len(goals) - 1):
        assert goals[i].score >= goals[i + 1].score, "Goals should be sorted by score"

    # The worse capability should have a higher score
    sys_info_goals = [g for g in goals if "system.info" in g.target_capability]
    sys_proc_goals = [g for g in goals if "system.processes" in g.target_capability]

    if sys_info_goals and sys_proc_goals:
        assert sys_info_goals[0].score >= sys_proc_goals[0].score, \
            "Worse capability should score higher"

    print(f"  [PASS] {len(goals)} goals scored and sorted")
    for g in goals[:3]:
        print(f"    {g.score:.3f} — {g.title}")

    Path(db).unlink(missing_ok=True)
    Path(reg).unlink(missing_ok=True)
    Path(mem).unlink(missing_ok=True)
    Path(ref).unlink(missing_ok=True)
    return True


def test_goal_queue_persistence():
    """Goals should persist across sessions."""
    print("Testing Goal Queue Persistence...")
    queue_path = tempfile.mktemp(suffix=".json")

    tracker, db = _make_temp_tracker()
    registry, reg = _make_temp_registry()
    memory, mem = _make_temp_memory()
    reflection, ref = _make_temp_reflection()

    _seed_capabilities(registry)

    for i in range(5):
        tracker.record_execution(
            capability="system.info", version="1.0.0",
            duration_ms=3000, success=True,
        )

    # First engine generates and saves
    engine1 = GoalEngine(queue_path=queue_path)
    engine1._tracker = tracker
    engine1._registry = registry
    engine1._memory = memory
    engine1._reflection = reflection
    goals1 = engine1.analyze_and_generate()
    assert len(goals1) >= 1

    # Second engine loads from disk
    engine2 = GoalEngine(queue_path=queue_path)
    engine2._tracker = tracker
    engine2._registry = registry
    engine2._memory = memory
    engine2._reflection = reflection
    queue = engine2.get_queue()

    assert len(queue) >= 1, "Should load persisted goals"
    assert queue[0]["score"] > 0

    print(f"  [PASS] {len(queue)} goals persisted and reloaded")

    Path(queue_path).unlink(missing_ok=True)
    Path(db).unlink(missing_ok=True)
    Path(reg).unlink(missing_ok=True)
    Path(mem).unlink(missing_ok=True)
    Path(ref).unlink(missing_ok=True)
    return True


def test_goal_status_lifecycle():
    """Goals should track status changes."""
    print("Testing Goal Status Lifecycle...")
    queue_path = tempfile.mktemp(suffix=".json")

    goal = Goal(
        id="test_goal",
        goal_type=GoalType.OPTIMIZE,
        title="Test goal",
        description="A test goal",
        score=0.8,
    )

    engine = GoalEngine(queue_path=queue_path)
    engine._goals = [goal]

    # Check initial status
    assert goal.status == GoalStatus.PROPOSED

    # Mark in progress
    engine.update_goal_status("test_goal", GoalStatus.IN_PROGRESS)
    assert goal.status == GoalStatus.IN_PROGRESS
    assert goal.attempts == 1

    # Complete
    engine.update_goal_status("test_goal", GoalStatus.COMPLETED, result="Fixed")
    assert goal.status == GoalStatus.COMPLETED
    assert goal.completed_at > 0
    assert goal.result == "Fixed"

    # Verify persistence
    engine2 = GoalEngine(queue_path=queue_path)
    loaded = engine2.get_goal_by_id("test_goal")
    assert loaded is not None
    assert loaded.status == GoalStatus.COMPLETED

    print("  [PASS] Status lifecycle: proposed → in_progress → completed")

    Path(queue_path).unlink(missing_ok=True)
    return True


def test_planner_injection():
    """Top goals should be injectable as planner tasks."""
    print("Testing Planner Injection...")
    queue_path = tempfile.mktemp(suffix=".json")

    goal = Goal(
        id="inject_test",
        goal_type=GoalType.OPTIMIZE,
        title="Optimize system.info",
        description="system.info is slow",
        target_capability="system.info",
        score=0.9,
    )

    engine = GoalEngine(queue_path=queue_path)
    engine._goals = [goal]

    task = engine.inject_into_planner()
    assert task is not None
    assert "system.info" in task
    assert goal.status == GoalStatus.IN_PROGRESS

    print(f"  [PASS] Injected task: {task[:80]}")

    Path(queue_path).unlink(missing_ok=True)
    return True


def test_goal_stats():
    """Stats should reflect goal queue state."""
    print("Testing Goal Stats...")
    queue_path = tempfile.mktemp(suffix=".json")

    goals = [
        Goal(id="g1", goal_type=GoalType.OPTIMIZE, title="A", description="A", score=0.8),
        Goal(id="g2", goal_type=GoalType.CREATE, title="B", description="B", score=0.6),
        Goal(id="g3", goal_type=GoalType.FIX, title="C", description="C", score=0.4,
             status=GoalStatus.COMPLETED),
    ]

    engine = GoalEngine(queue_path=queue_path)
    engine._goals = goals

    stats = engine.get_stats()
    assert stats["total_goals"] == 3
    assert stats["completed"] == 1
    assert stats["by_type"]["optimize"] == 1
    assert stats["by_type"]["create"] == 1
    assert stats["top_goal"] == "A"  # Highest score

    print(f"  [PASS] Stats: {stats}")

    Path(queue_path).unlink(missing_ok=True)
    return True


def test_no_hallucinated_goals():
    """Goals should ONLY come from observed data, not fabricated."""
    print("Testing No Hallucinated Goals...")
    tracker, db = _make_temp_tracker()
    registry, reg = _make_temp_registry()
    memory, mem = _make_temp_memory()
    reflection, ref = _make_temp_reflection()

    # Empty system — no data
    engine = GoalEngine(queue_path=tempfile.mktemp(suffix=".json"))
    engine._tracker = tracker
    engine._registry = registry
    engine._memory = memory
    engine._reflection = reflection

    goals = engine.analyze_and_generate()
    assert len(goals) == 0, f"Empty system should produce 0 goals, got {len(goals)}"

    print("  [PASS] No goals generated from empty data")

    Path(db).unlink(missing_ok=True)
    Path(reg).unlink(missing_ok=True)
    Path(mem).unlink(missing_ok=True)
    Path(ref).unlink(missing_ok=True)
    return True


def main():
    print("=" * 55)
    print("  CCOS Goal Engine Test Suite")
    print("=" * 55)
    print()

    tests = [
        test_goal_from_weak_capabilities,
        test_goal_from_slow_capabilities,
        test_goal_from_error_patterns,
        test_goal_from_recombination,
        test_goal_scoring,
        test_goal_queue_persistence,
        test_goal_status_lifecycle,
        test_planner_injection,
        test_goal_stats,
        test_no_hallucinated_goals,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
                print(f"  [FAIL] {test.__name__}")
        except Exception as e:
            failed += 1
            import traceback
            print(f"  [ERROR] {test.__name__}: {e}")
            traceback.print_exc()
        print()

    print("=" * 55)
    print(f"  Results: {passed} passed, {failed} failed")
    print("=" * 55)
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
