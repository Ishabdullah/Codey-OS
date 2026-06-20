#!/usr/bin/env python3
"""
CCOS Goal Engine Demo.

Demonstrates:
1. System accumulates usage data over time
2. Goal engine analyzes data and generates improvement goals
3. Goals are scored and prioritized
4. Top goal is injected into planner for proactive execution
5. Full cycle: usage → analysis → goals → improvement

Run: PYTHONPATH=/root/Codey-v3 python3 ccos/demo_goal_engine.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    from ccos.core.device_manager import get_device_manager
    from ccos.core.plugin_manager import get_plugin_manager
    from ccos.core.goal_engine import get_goal_engine
    from ccos.core.performance_tracker import get_performance_tracker
    from ccos.core.capability_registry import get_capability_registry
    from ccos.core.memory.ccos_memory import get_ccos_memory
    from ccos.core.reflection_engine import get_reflection_engine
    from ccos.core.lifecycle_manager import get_lifecycle_manager

    print("=" * 60)
    print("  CCOS Goal Engine Demo")
    print("  From reactive improvement → proactive self-direction")
    print("=" * 60)
    print()

    # Bootstrap
    device = get_device_manager()
    pm = get_plugin_manager()
    pm.load_all()
    tracker = get_performance_tracker()
    registry = get_capability_registry()
    memory = get_ccos_memory()
    reflection = get_reflection_engine()
    lifecycle = get_lifecycle_manager()
    goal_engine = get_goal_engine()

    print(f"Device: {device.get_profile()['os']['name']}, "
          f"{device.get_profile()['cpu']['cores']} cores")
    print(f"Active capabilities: {len(registry.get_active())}")
    print()

    # ── Phase 1: Simulate accumulated usage ────────────────────────
    print("=" * 60)
    print("  PHASE 1: Accumulating Usage Data")
    print("  (Simulating repeated task execution)")
    print("=" * 60)
    print()

    # Execute tasks to build performance data
    tasks = [
        ("system.info", True, 50),
        ("system.info", True, 45),
        ("system.info", False, 3000),  # Slow failure
        ("system.info", True, 55),
        ("system.processes", True, 30),
        ("system.processes", True, 25),
        ("system.processes", True, 35),
    ]

    for cap_name, success, duration in tasks:
        tracker.record_execution(
            capability=cap_name, version="1.0.0",
            duration_ms=duration, success=success,
            error_category="timeout" if not success else "",
        )
        registry.record_use(cap_name, success, duration)

    # Store workflows for recombination detection
    for i in range(4):
        steps = [
            {"capability": "system.info", "task": "info"},
            {"capability": "system.processes", "task": "procs"},
        ]
        memory.structured.store_workflow(
            name=f"monitor_{i}", goal="system check",
            steps=[json.dumps(s) for s in steps],
            result="ok", success=True,
        )

    # Log some reflections
    for i in range(3):
        reflection.reflect(
            task=f"check camera photo {i}",
            success=False,
            capability_used="system.info",
            duration_ms=100,
            error="camera not found",
        )

    print(f"  Recorded {len(tasks)} capability executions")
    print(f"  Stored 4 multi-step workflows")
    print(f"  Logged 3 reflection events")
    print()

    # ── Phase 2: Goal Generation ───────────────────────────────────
    print("=" * 60)
    print("  PHASE 2: Goal Generation")
    print("  (Analyzing data for improvement opportunities)")
    print("=" * 60)
    print()

    new_goals = goal_engine.analyze_and_generate()

    print(f"  Generated {len(new_goals)} new goal(s):")
    print()

    for i, goal in enumerate(new_goals, 1):
        print(f"  Goal {i}: {goal.title}")
        print(f"    Type: {goal.goal_type.value}")
        print(f"    Score: {goal.score:.3f}")
        print(f"    Reason: {goal.reason}")
        print(f"    Evidence:")
        for ev in goal.evidence:
            print(f"      - {ev}")
        print()

    # ── Phase 3: Goal Queue ────────────────────────────────────────
    print("=" * 60)
    print("  PHASE 3: Prioritized Goal Queue")
    print("=" * 60)
    print()

    queue = goal_engine.get_queue()
    print(f"  Queue size: {len(queue)}")
    print()
    for i, g in enumerate(queue[:5], 1):
        print(f"  #{i} [{g['status']}] score={g['score']:.3f} — {g['title']}")
    print()

    # ── Phase 4: Planner Injection ─────────────────────────────────
    print("=" * 60)
    print("  PHASE 4: Proactive Planner Injection")
    print("  (Top goal becomes a planner task)")
    print("=" * 60)
    print()

    injected_task = goal_engine.inject_into_planner()
    if injected_task:
        print(f"  Injected into planner:")
        print(f"    \"{injected_task}\"")
        print()

        # Show that the planner can handle it
        from ccos.core.planner import get_planner
        planner = get_planner()
        analysis = planner.analyze_request(injected_task)
        print(f"  Planner analysis:")
        print(f"    Available capabilities: {len(analysis['available_capabilities'])}")
        print(f"    Missing capabilities: {len(analysis['missing_capabilities'])}")
    else:
        print("  No goals available for injection")
    print()

    # ── Phase 5: Stats ─────────────────────────────────────────────
    print("=" * 60)
    print("  PHASE 5: Goal Engine Statistics")
    print("=" * 60)
    print()

    stats = goal_engine.get_stats()
    print(f"  Total goals: {stats['total_goals']}")
    print(f"  By status: {stats['by_status']}")
    print(f"  By type: {stats['by_type']}")
    print(f"  Average score: {stats['avg_score']:.3f}")
    print(f"  Top goal: {stats['top_goal']}")
    print()

    # ── Architecture Flow ──────────────────────────────────────────
    print("=" * 60)
    print("  UPDATED ARCHITECTURE FLOW")
    print("=" * 60)
    print()
    print("  task executed")
    print("     ↓")
    print("  reflection engine evaluates")
    print("     ↓")
    print("  performance tracker logs metrics")
    print("     ↓")
    print("  skill recombiner detects patterns")
    print("     ↓")
    print("  GOAL ENGINE analyzes all data")
    print("     ↓")
    print("  goals generated + scored + ranked")
    print("     ↓")
    print("  top goal injected into planner")
    print("     ↓")
    print("  CCOS proactively improves itself")
    print()

    # ── Summary ────────────────────────────────────────────────────
    print("=" * 60)
    print("  GOAL ENGINE DEMO COMPLETE")
    print("=" * 60)
    print()
    print("  Key behaviors demonstrated:")
    print("    - Goals derived ONLY from observed data")
    print("    - Scoring considers frequency, impact, complexity,")
    print("      dependency availability, and failure history")
    print("    - Queue persisted to disk across sessions")
    print("    - Top goal injected into planner automatically")
    print("    - No user prompting required")
    print()
    print("  CCOS has transitioned from reactive self-improvement")
    print("  to PROACTIVE self-directed optimization.")
    print()


if __name__ == "__main__":
    main()
