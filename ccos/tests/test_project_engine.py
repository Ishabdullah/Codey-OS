#!/usr/bin/env python3
"""
CCOS Project Engine Test Suite.

Tests project creation, decomposition, milestone tracking,
task execution, persistence, and resume across sessions.
"""

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ccos.core.project_engine import (
    ProjectEngine,
    Project,
    ProjectStatus,
    Milestone,
    MilestoneStatus,
    ProjectTask,
    TaskStatus,
    ProjectDecomposer,
    get_project_engine,
)


def _make_temp_engine():
    f = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    f.close()
    return ProjectEngine(projects_path=f.name), f.name


def test_project_creation_from_goal():
    """Projects should be created from high-value goals."""
    print("Testing Project Creation from Goal...")
    engine, path = _make_temp_engine()

    project = engine.create_project_from_goal(
        goal_id="opt_system_info",
        goal_title="Optimize system.info",
        goal_type="optimize",
        goal_score=0.85,
        target_capability="system.info",
        expected_impact={"metric": "performance_score", "current": 50, "target": 80},
    )

    assert project.project_id.startswith("proj_")
    assert project.name == "Optimize system.info"
    assert project.status == ProjectStatus.ACTIVE
    assert project.goal_score == 0.85
    assert len(project.milestones) == 3  # analyze, optimize, validate
    assert project.progress == 0.0

    print(f"  [PASS] Created project: {project.name}")
    print(f"    Milestones: {len(project.milestones)}")
    print(f"    Status: {project.status.value}")

    Path(path).unlink(missing_ok=True)
    return True


def test_project_decomposition_optimize():
    """Optimize goals should decompose into analyze → optimize → validate."""
    print("Testing Optimization Decomposition...")
    decomposer = ProjectDecomposer()

    milestones = decomposer.decompose_goal(
        "test", "Optimize X", "optimize", 0.8, "x.cap",
        {"current": 50, "target": 80},
    )

    assert len(milestones) == 3
    assert milestones[0].milestone_id == "analyze"
    assert milestones[1].milestone_id == "optimize"
    assert milestones[2].milestone_id == "validate"
    assert all(len(m.tasks) >= 2 for m in milestones)

    print(f"  [PASS] {len(milestones)} milestones, {sum(len(m.tasks) for m in milestones)} tasks")

    for m in milestones:
        print(f"    {m.milestone_id}: {m.description} ({len(m.tasks)} tasks)")
    return True


def test_project_decomposition_create():
    """Create goals should decompose into research → implement → validate."""
    print("Testing Creation Decomposition...")
    decomposer = ProjectDecomposer()

    milestones = decomposer.decompose_goal(
        "test", "Create OCR", "create", 0.7, "ocr",
        {"new_capability": "ocr"},
    )

    assert len(milestones) == 3
    assert milestones[0].milestone_id == "research"
    assert milestones[1].milestone_id == "implement"
    assert milestones[2].milestone_id == "validate"

    print(f"  [PASS] {len(milestones)} milestones for creation goal")
    return True


def test_milestone_progress():
    """Milestone progress should reflect task completion."""
    print("Testing Milestone Progress...")
    engine, path = _make_temp_engine()

    project = engine.create_project_from_goal(
        "test", "Test project", "optimize", 0.8, "test.cap",
    )

    # First milestone
    ms = project.milestones[0]
    assert ms.progress == 0.0
    assert not ms.is_complete

    # Complete first task
    ms.tasks[0].status = TaskStatus.DONE
    assert ms.progress > 0.0
    assert not ms.is_complete

    # Complete all tasks
    for t in ms.tasks:
        t.status = TaskStatus.DONE
    assert ms.is_complete
    assert ms.progress == 1.0

    print(f"  [PASS] Progress tracking works correctly")

    Path(path).unlink(missing_ok=True)
    return True


def test_task_execution_flow():
    """Tasks should be completable and update project progress."""
    print("Testing Task Execution Flow...")
    engine, path = _make_temp_engine()

    project = engine.create_project_from_goal(
        "test_flow", "Test flow", "optimize", 0.85, "test.cap",
    )
    pid = project.project_id

    # Get next task
    next_task = engine.get_next_task()
    assert next_task is not None
    assert next_task["project_id"] == pid
    assert next_task["task_id"] == "collect_metrics"

    # Complete it
    result = engine.complete_task(
        pid, next_task["milestone_id"], next_task["task_id"],
        success=True, result="Metrics collected",
    )
    assert result.success

    # Get next task (should be second task in first milestone)
    next_task2 = engine.get_next_task()
    assert next_task2 is not None
    assert next_task2["task_id"] == "identify_bottleneck"

    print(f"  [PASS] Task flow: collect_metrics → identify_bottleneck")

    Path(path).unlink(missing_ok=True)
    return True


def test_project_completion():
    """Completing all tasks should complete the project."""
    print("Testing Project Completion...")
    engine, path = _make_temp_engine()

    project = engine.create_project_from_goal(
        "test_complete", "Complete me", "fix", 0.8, "test.cap",
        {"error_category": "timeout"},
    )
    pid = project.project_id

    # Complete all tasks
    for ms in project.milestones:
        for task in ms.tasks:
            engine.complete_task(pid, ms.milestone_id, task.task_id, success=True)

    # Project should be complete
    updated = engine.get_project(pid)
    assert updated.status == ProjectStatus.COMPLETED
    assert updated.progress == 1.0

    print(f"  [PASS] Project completed: progress={updated.progress:.0%}")

    Path(path).unlink(missing_ok=True)
    return True


def test_persistence_across_sessions():
    """Projects should persist across engine restarts."""
    print("Testing Persistence Across Sessions...")
    engine, path = _make_temp_engine()

    # Session 1: Create and partially complete
    project = engine.create_project_from_goal(
        "persist_test", "Persist me", "optimize", 0.8, "test.cap",
    )
    pid = project.project_id

    # Complete first task
    engine.complete_task(pid, "analyze", "collect_metrics", success=True)

    # Simulate session restart
    engine2 = ProjectEngine(projects_path=path)

    # Should reload from disk
    loaded = engine2.get_project(pid)
    assert loaded is not None
    assert loaded.name == "Persist me"
    assert loaded.status == ProjectStatus.ACTIVE

    # First task should still be done
    first_task = loaded.milestones[0].tasks[0]
    assert first_task.status == TaskStatus.DONE

    print(f"  [PASS] Project persisted and restored across session")

    Path(path).unlink(missing_ok=True)
    return True


def test_resume_on_startup():
    """Active projects should be resumable on startup."""
    print("Testing Resume on Startup...")
    engine, path = _make_temp_engine()

    # Create two projects
    p1 = engine.create_project_from_goal(
        "resume1", "Resume project 1", "optimize", 0.9, "cap1",
    )
    p2 = engine.create_project_from_goal(
        "resume2", "Resume project 2", "create", 0.8, "cap2",
    )

    # Complete one task in p1
    engine.complete_task(p1.project_id, "analyze", "collect_metrics", success=True)

    # Simulate restart
    engine2 = ProjectEngine(projects_path=path)

    # Resume should find active projects
    needs_attention = engine2.resume_active_projects()
    assert len(needs_attention) == 2

    # p1 should show progress
    p1_status = next(a for a in needs_attention if a["project_id"] == p1.project_id)
    assert p1_status["progress"] > 0

    print(f"  [PASS] {len(needs_attention)} projects need attention on resume")
    for a in needs_attention:
        print(f"    {a['name']}: progress={a['progress']:.0%}, pending={a['pending_tasks']}")

    Path(path).unlink(missing_ok=True)
    return True


def test_pause_and_resume():
    """Projects should be pausable and resumable."""
    print("Testing Pause and Resume...")
    engine, path = _make_temp_engine()

    project = engine.create_project_from_goal(
        "pause_test", "Pause me", "optimize", 0.8, "test.cap",
    )
    pid = project.project_id

    # Pause
    engine.pause_project(pid)
    assert engine.get_project(pid).status == ProjectStatus.PAUSED

    # Should not return tasks for paused projects
    next_task = engine.get_next_task()
    assert next_task is None

    # Resume
    engine.resume_project(pid)
    assert engine.get_project(pid).status == ProjectStatus.ACTIVE

    # Should return tasks again
    next_task = engine.get_next_task()
    assert next_task is not None

    print(f"  [PASS] Pause/resume works correctly")

    Path(path).unlink(missing_ok=True)
    return True


def test_parallel_projects():
    """Multiple projects should be manageable in parallel."""
    print("Testing Parallel Projects...")
    engine, path = _make_temp_engine()

    # Create 3 projects
    projects = []
    for i in range(3):
        p = engine.create_project_from_goal(
            f"parallel_{i}", f"Project {i}", "optimize", 0.8 - i * 0.05, f"cap{i}",
        )
        projects.append(p)

    # List active
    active = engine.list_projects(ProjectStatus.ACTIVE)
    assert len(active) == 3

    # Should be sorted by goal_score descending
    assert active[0].goal_score >= active[1].goal_score

    # Get next task (highest score first)
    next_task = engine.get_next_task()
    assert next_task["project_id"] == projects[0].project_id

    print(f"  [PASS] {len(active)} parallel projects, highest-priority task selected")

    Path(path).unlink(missing_ok=True)
    return True


def test_project_stats():
    """Stats should reflect project engine state."""
    print("Testing Project Stats...")
    engine, path = _make_temp_engine()

    # Create and complete some work
    p = engine.create_project_from_goal(
        "stats_test", "Stats project", "fix", 0.8, "test.cap",
        {"error_category": "timeout"},
    )
    engine.complete_task(p.project_id, "diagnose", "collect_errors", success=True)

    stats = engine.get_stats()
    assert stats["total_projects"] == 1
    assert stats["active"] == 1
    assert stats["total_milestones"] == 3
    assert stats["completed_tasks"] == 1
    assert stats["milestone_success_rate"] >= 0

    print(f"  [PASS] Stats: {json.dumps({k: v for k, v in stats.items() if k != 'avg_progress'}, indent=2)}")

    Path(path).unlink(missing_ok=True)
    return True


def test_goal_to_project_conversion():
    """High-scoring goals should be convertible to projects."""
    print("Testing Goal → Project Conversion...")
    engine, path = _make_temp_engine()

    # Simulate a high-value goal from goal engine
    project = engine.create_project_from_goal(
        goal_id="high_value_goal",
        goal_title="Create OCR capability for text extraction",
        goal_type="create",
        goal_score=0.92,
        target_capability="ocr",
        expected_impact={"new_capability": "ocr", "metric": "capability_coverage"},
    )

    assert project.goal_score == 0.92
    assert len(project.milestones) == 3
    assert project.milestones[0].milestone_id == "research"
    assert project.milestones[1].milestone_id == "implement"

    # Simulate executing the full project
    for ms in project.milestones:
        for task in ms.tasks:
            result = engine.complete_task(project.project_id, ms.milestone_id, task.task_id, success=True)
            assert result.success

    assert project.is_complete

    print(f"  [PASS] Goal → Project → Completion: {project.name}")
    print(f"    Milestones: {len(project.milestones)}")
    print(f"    Total tasks: {sum(len(m.tasks) for m in project.milestones)}")

    Path(path).unlink(missing_ok=True)
    return True


def test_multi_session_simulation():
    """Simulate project execution across multiple sessions."""
    print("Testing Multi-Session Simulation...")
    engine, path = _make_temp_engine()

    # Session 1: Create project
    project = engine.create_project_from_goal(
        "multi_session", "Build compound skill", "recombine", 0.85,
        "cap1+cap2", {"steps_reduced": 1},
    )
    pid = project.project_id

    # Session 1: Complete first milestone
    for task in project.milestones[0].tasks:
        engine.complete_task(pid, project.milestones[0].milestone_id, task.task_id, success=True)

    print(f"  Session 1: Completed milestone 1")

    # Simulate session restart
    engine2 = ProjectEngine(projects_path=path)
    needs = engine2.resume_active_projects()
    assert len(needs) == 1

    # Session 2: Continue with milestone 2
    project2 = engine2.get_project(pid)
    ms2 = project2.milestones[1]
    assert ms2.status == MilestoneStatus.PENDING

    for task in ms2.tasks:
        engine2.complete_task(pid, ms2.milestone_id, task.task_id, success=True)

    print(f"  Session 2: Completed milestone 2")

    # Simulate another restart
    engine3 = ProjectEngine(projects_path=path)
    project3 = engine3.get_project(pid)

    # Session 3: Complete final milestone
    ms3 = project3.milestones[2]
    for task in ms3.tasks:
        engine3.complete_task(pid, ms3.milestone_id, task.task_id, success=True)

    # Project should be complete
    assert project3.is_complete
    assert project3.status == ProjectStatus.COMPLETED

    print(f"  Session 3: Project complete!")
    print(f"  [PASS] Multi-session execution: 3 sessions, {sum(len(m.tasks) for m in project.milestones)} tasks")

    Path(path).unlink(missing_ok=True)
    return True


def main():
    print("=" * 55)
    print("  CCOS Project Engine Test Suite")
    print("=" * 55)
    print()

    tests = [
        test_project_creation_from_goal,
        test_project_decomposition_optimize,
        test_project_decomposition_create,
        test_milestone_progress,
        test_task_execution_flow,
        test_project_completion,
        test_persistence_across_sessions,
        test_resume_on_startup,
        test_pause_and_resume,
        test_parallel_projects,
        test_project_stats,
        test_goal_to_project_conversion,
        test_multi_session_simulation,
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
