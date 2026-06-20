#!/usr/bin/env python3
"""
CCOS Project Engine Demo.

Demonstrates:
1. High-value goal → project conversion
2. Project decomposition into milestones
3. Multi-session execution with persistence
4. Resume on restart
5. Integration with goal engine + agent orchestrator

Run: PYTHONPATH=/root/Codey-v3 python3 ccos/demo_project_engine.py
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def main():
    from ccos.core.device_manager import get_device_manager
    from ccos.core.plugin_manager import get_plugin_manager
    from ccos.core.project_engine import get_project_engine, ProjectEngine
    from ccos.core.goal_engine import get_goal_engine
    from ccos.core.agent_orchestrator import get_agent_orchestrator
    from ccos.core.capability_registry import get_capability_registry

    print("=" * 60)
    print("  CCOS Project Engine Demo")
    print("  Long-horizon autonomous execution across sessions")
    print("=" * 60)
    print()

    # Bootstrap
    device = get_device_manager()
    pm = get_plugin_manager()
    pm.load_all()
    project_engine = get_project_engine()
    goal_engine = get_goal_engine()
    orchestrator = get_agent_orchestrator()
    registry = get_capability_registry()

    print(f"Device: {device.get_profile()['os']['name']}, "
          f"{device.get_profile()['cpu']['cores']} cores")
    print(f"Active capabilities: {len(registry.get_active())}")
    print()

    # ── Phase 1: Goal → Project conversion ─────────────────────────
    print("=" * 60)
    print("  PHASE 1: Goal → Project Conversion")
    print("=" * 60)
    print()

    # Generate goals
    new_goals = goal_engine.analyze_and_generate()
    top_goals = goal_engine.get_top_goals(3)

    if top_goals:
        print(f"  Top {len(top_goals)} goals from goal engine:")
        for g in top_goals:
            print(f"    [{g.score:.3f}] {g.title} ({g.goal_type.value})")
        print()

        # Convert highest-scoring goal to project
        best_goal = top_goals[0]
        project = project_engine.create_project_from_goal(
            goal_id=best_goal.id,
            goal_title=best_goal.title,
            goal_type=best_goal.goal_type.value,
            goal_score=best_goal.score,
            target_capability=best_goal.target_capability,
            expected_impact=best_goal.expected_impact,
        )

        print(f"  Created project: {project.name}")
        print(f"    Project ID: {project.project_id}")
        print(f"    Goal score: {project.goal_score:.3f}")
        print(f"    Milestones: {len(project.milestones)}")
        print(f"    Total tasks: {sum(len(m.tasks) for m in project.milestones)}")
        print()
    else:
        # Create a demo project manually
        project = project_engine.create_project_from_goal(
            goal_id="demo_goal",
            goal_title="Build system diagnostics compound skill",
            goal_type="recombine",
            goal_score=0.85,
            target_capability="system.info+system.processes",
            expected_impact={"steps_reduced": 1, "workflows_affected": 5},
        )
        print(f"  Created demo project: {project.name}")
        print()

    # ── Phase 2: Project Structure ─────────────────────────────────
    print("=" * 60)
    print("  PHASE 2: Project Structure")
    print("=" * 60)
    print()

    for i, ms in enumerate(project.milestones, 1):
        print(f"  Milestone {i}: {ms.description}")
        print(f"    Status: {ms.status.value}")
        print(f"    Success criteria: {ms.success_criteria}")
        print(f"    Tasks:")
        for task in ms.tasks:
            print(f"      - [{task.status.value}] {task.description}")
        print()

    # ── Phase 3: Simulated Multi-Session Execution ─────────────────
    print("=" * 60)
    print("  PHASE 3: Multi-Session Execution")
    print("  (Simulating 3 sessions with restarts)")
    print("=" * 60)
    print()

    pid = project.project_id

    # Session 1: Execute first milestone
    print("  --- Session 1 ---")
    ms1 = project.milestones[0]
    for task in ms1.tasks:
        # Simulate agent orchestrator deliberation
        result = project_engine.complete_task(
            pid, ms1.milestone_id, task.task_id, success=True,
            result=f"Completed: {task.description}",
        )
        print(f"  ✓ {task.description}")
    print(f"  Milestone 1 complete. Project progress: {project.progress:.0%}")
    print()

    # Simulate session restart
    print("  [Session restart — loading from disk]")
    project_engine2 = ProjectEngine(projects_path=project_engine._path)
    needs = project_engine2.resume_active_projects()
    print(f"  Resumed {len(needs)} active project(s)")
    for n in needs:
        print(f"    {n['name']}: progress={n['progress']:.0%}, "
              f"milestone='{n['current_milestone']}', pending={n['pending_tasks']}")
    print()

    # Session 2: Execute second milestone
    print("  --- Session 2 ---")
    project2 = project_engine2.get_project(pid)
    ms2 = project2.milestones[1]
    for task in ms2.tasks:
        project_engine2.complete_task(
            pid, ms2.milestone_id, task.task_id, success=True,
            result=f"Completed: {task.description}",
        )
        print(f"  ✓ {task.description}")
    print(f"  Milestone 2 complete. Project progress: {project2.progress:.0%}")
    print()

    # Another restart
    print("  [Session restart — loading from disk]")
    project_engine3 = ProjectEngine(projects_path=project_engine._path)
    project3 = project_engine3.get_project(pid)
    print(f"  Resumed: {project3.name}, progress={project3.progress:.0%}")
    print()

    # Session 3: Complete final milestone
    print("  --- Session 3 ---")
    remaining = [m for m in project3.milestones if m.status.value != "done"]
    if remaining:
        ms3 = remaining[0]
        for task in ms3.tasks:
            project_engine3.complete_task(
                pid, ms3.milestone_id, task.task_id, success=True,
                result=f"Completed: {task.description}",
            )
            print(f"  ✓ {task.description}")
    else:
        print("  All milestones already complete.")

    final = project_engine3.get_project(pid)
    print(f"  Project status: {final.status.value}")
    print(f"  Project progress: {final.progress:.0%}")
    print()

    # ── Phase 4: Integration with Agent Orchestrator ───────────────
    print("=" * 60)
    print("  PHASE 4: Agent Orchestrator Integration")
    print("=" * 60)
    print()

    # Get next task and run through orchestrator
    project_engine_fresh = ProjectEngine(projects_path=project_engine._path)

    # Create a new active project for orchestrator demo
    demo_project = project_engine_fresh.create_project_from_goal(
        goal_id="orchestrator_demo",
        goal_title="Optimize system diagnostics",
        goal_type="optimize",
        goal_score=0.88,
        target_capability="system.info",
    )

    next_task = project_engine_fresh.get_next_task()
    if next_task:
        print(f"  Next task from project engine:")
        print(f"    Project: {next_task['project_name']}")
        print(f"    Milestone: {next_task['milestone_description']}")
        print(f"    Task: {next_task['task_description']}")
        print()

        # Run through agent orchestrator
        deliberation = orchestrator.deliberate(next_task["task_description"])
        print(f"  Agent orchestrator deliberation:")
        print(f"    Status: {deliberation.status.value}")
        print(f"    Agreement: {deliberation.agreement_rate:.0%}")
        print(f"    Agents consulted: {len(deliberation.agent_outputs)}")

        # Complete the task based on deliberation
        if deliberation.status.value in ("approved", "modified"):
            project_engine_fresh.complete_task(
                next_task["project_id"], next_task["milestone_id"],
                next_task["task_id"], success=True,
                result=f"Approved by orchestrator (agreement={deliberation.agreement_rate:.0%})",
            )
            print(f"    Task completed via orchestrator approval")
    print()

    # ── Phase 5: Project Engine Stats ──────────────────────────────
    print("=" * 60)
    print("  PHASE 5: Project Engine Statistics")
    print("=" * 60)
    print()

    stats = project_engine_fresh.get_stats()
    print(f"  Total projects: {stats['total_projects']}")
    print(f"  Active: {stats['active']}")
    print(f"  Completed: {stats['completed']}")
    print(f"  Milestones: {stats['completed_milestones']}/{stats['total_milestones']}")
    print(f"  Tasks: {stats['completed_tasks']}/{stats['total_tasks']}")
    print(f"  Task success rate: {stats['task_success_rate']:.0%}")
    print()

    # ── Architecture ───────────────────────────────────────────────
    print("=" * 60)
    print("  ARCHITECTURE: Goal → Project → Milestone → Task")
    print("=" * 60)
    print()
    print("  task executed")
    print("     ↓")
    print("  reflection engine")
    print("     ↓")
    print("  goal engine")
    print("     ↓")
    print("  project engine ← NEW LAYER")
    print("     ↓")
    print("  ┌─────────────────────────────────────┐")
    print("  │  Project (persistent, multi-session) │")
    print("  │  ├─ Milestone 1 (analyze)            │")
    print("  │  │  ├─ Task: collect metrics          │")
    print("  │  │  └─ Task: identify bottleneck      │")
    print("  │  ├─ Milestone 2 (optimize)           │")
    print("  │  │  ├─ Task: generate improvement     │")
    print("  │  │  └─ Task: sandbox test             │")
    print("  │  └─ Milestone 3 (validate)           │")
    print("  │     ├─ Task: compare performance      │")
    print("  │     └─ Task: register if better       │")
    print("  └─────────────────────────────────────┘")
    print("     ↓")
    print("  agent orchestrator executes")
    print("     ↓")
    print("  sandbox execution")
    print("     ↓")
    print("  progress updated → persisted to disk")
    print("     ↓")
    print("  [session ends]")
    print("     ↓")
    print("  [next session: auto-resume active projects]")
    print()

    # ── Summary ────────────────────────────────────────────────────
    print("=" * 60)
    print("  PROJECT ENGINE DEMO COMPLETE")
    print("=" * 60)
    print()
    print("  Key behaviors demonstrated:")
    print("    - Goals converted to persistent projects")
    print("    - Projects decomposed into milestones and tasks")
    print("    - Progress tracked across simulated sessions")
    print("    - Auto-resume on startup")
    print("    - Integration with agent orchestrator")
    print("    - Parallel project support")
    print("    - Full persistence to disk")
    print()
    print("  CCOS now executes long-horizon objectives")
    print("  that survive across sessions.")
    print()


if __name__ == "__main__":
    main()
