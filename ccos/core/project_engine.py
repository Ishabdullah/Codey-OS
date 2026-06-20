"""
Project Engine — Long-horizon autonomous execution for CCOS.

Converts high-value goals into persistent projects with milestones,
tracks progress across sessions, and coordinates execution with
the agent orchestrator.

This transforms CCOS from single-task execution to long-running
multi-step autonomous objectives that survive restarts.

Data model:
  Goal (scored) → Project (persistent) → Milestones → Tasks → Execution
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECTS_PATH = str(
    Path(__file__).parent.parent / "data" / "projects.json"
)


# ── Enums ──────────────────────────────────────────────────────────

class ProjectStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class MilestoneStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    BLOCKED = "blocked"


# ── Data structures ────────────────────────────────────────────────

@dataclass
class ProjectTask:
    """A single executable task within a milestone."""
    task_id: str
    description: str
    capability: str = ""
    status: TaskStatus = TaskStatus.PENDING
    result: str = ""
    error: str = ""
    attempts: int = 0
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "capability": self.capability,
            "status": self.status.value,
            "result": self.result[:500],
            "error": self.error[:300],
            "attempts": self.attempts,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


@dataclass
class Milestone:
    """A milestone within a project — a logical grouping of tasks."""
    milestone_id: str
    description: str
    status: MilestoneStatus = MilestoneStatus.PENDING
    tasks: List[ProjectTask] = field(default_factory=list)
    success_criteria: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def progress(self) -> float:
        if not self.tasks:
            return 0.0
        done = sum(1 for t in self.tasks if t.status == TaskStatus.DONE)
        return done / len(self.tasks)

    @property
    def is_complete(self) -> bool:
        return all(t.status == TaskStatus.DONE for t in self.tasks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "milestone_id": self.milestone_id,
            "description": self.description,
            "status": self.status.value,
            "progress": round(self.progress, 2),
            "tasks": [t.to_dict() for t in self.tasks],
            "success_criteria": self.success_criteria,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


@dataclass
class Project:
    """A persistent execution unit — the top-level organizational structure."""
    project_id: str
    name: str
    goal_source: str = ""
    goal_score: float = 0.0
    status: ProjectStatus = ProjectStatus.ACTIVE
    milestones: List[Milestone] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_updated: float = field(default_factory=time.time)
    completed_at: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def progress(self) -> float:
        if not self.milestones:
            return 0.0
        return sum(m.progress for m in self.milestones) / len(self.milestones)

    @property
    def is_complete(self) -> bool:
        return all(m.is_complete for m in self.milestones)

    @property
    def current_milestone(self) -> Optional[Milestone]:
        """Get the next incomplete milestone."""
        for m in self.milestones:
            if m.status != MilestoneStatus.DONE:
                return m
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "goal_source": self.goal_source,
            "goal_score": self.goal_score,
            "status": self.status.value,
            "progress": round(self.progress, 2),
            "milestones": [m.to_dict() for m in self.milestones],
            "dependencies": self.dependencies,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
            "completed_at": self.completed_at,
        }


@dataclass
class ProjectResult:
    """Result of a project engine operation."""
    action: str
    project_id: str
    success: bool
    details: str = ""
    milestone_id: str = ""
    task_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# ── Project Decomposer ─────────────────────────────────────────────

class ProjectDecomposer:
    """
    Breaks high-level goals into structured milestones and tasks.
    Uses goal metadata to determine decomposition strategy.
    """

    def decompose_goal(self, goal_id: str, goal_title: str,
                       goal_type: str, goal_score: float,
                       target_capability: str = "",
                       expected_impact: Dict[str, Any] = None) -> List[Milestone]:
        """
        Decompose a goal into milestones based on its type.
        """
        impact = expected_impact or {}

        if goal_type == "optimize":
            return self._decompose_optimize(goal_title, target_capability, impact)
        elif goal_type == "create":
            return self._decompose_create(goal_title, target_capability, impact)
        elif goal_type == "fix":
            return self._decompose_fix(goal_title, target_capability, impact)
        elif goal_type == "recombine":
            return self._decompose_recombine(goal_title, target_capability, impact)
        else:
            return self._decompose_generic(goal_title, target_capability)

    def _decompose_optimize(self, title: str, target: str,
                            impact: Dict) -> List[Milestone]:
        return [
            Milestone(
                milestone_id="analyze",
                description=f"Analyze performance of {target}",
                tasks=[
                    ProjectTask(task_id="collect_metrics", description=f"Collect metrics for {target}"),
                    ProjectTask(task_id="identify_bottleneck", description=f"Identify bottleneck in {target}"),
                ],
                success_criteria="Bottleneck identified with evidence",
            ),
            Milestone(
                milestone_id="optimize",
                description=f"Implement optimization for {target}",
                tasks=[
                    ProjectTask(task_id="generate_improvement", description=f"Generate improved version of {target}",
                               capability=target),
                    ProjectTask(task_id="sandbox_test", description=f"Test improved version in sandbox"),
                ],
                success_criteria="Improved version passes sandbox tests",
            ),
            Milestone(
                milestone_id="validate",
                description=f"Validate optimization results",
                tasks=[
                    ProjectTask(task_id="compare_performance", description=f"Compare old vs new performance"),
                    ProjectTask(task_id="register", description=f"Register optimized version if better"),
                ],
                success_criteria="New version outperforms old version",
            ),
        ]

    def _decompose_create(self, title: str, target: str,
                          impact: Dict) -> List[Milestone]:
        return [
            Milestone(
                milestone_id="research",
                description=f"Research implementation for {target}",
                tasks=[
                    ProjectTask(task_id="check_alternatives", description=f"Check for existing implementations"),
                    ProjectTask(task_id="design_implementation", description=f"Design {target} implementation"),
                ],
                success_criteria="Implementation design complete",
            ),
            Milestone(
                milestone_id="implement",
                description=f"Build {target} capability",
                tasks=[
                    ProjectTask(task_id="scaffold_plugin", description=f"Create plugin scaffold for {target}"),
                    ProjectTask(task_id="implement_code", description=f"Implement {target} code"),
                    ProjectTask(task_id="write_tests", description=f"Write tests for {target}"),
                ],
                success_criteria="Plugin code and tests complete",
            ),
            Milestone(
                milestone_id="validate",
                description=f"Validate and register {target}",
                tasks=[
                    ProjectTask(task_id="sandbox_test", description=f"Run sandbox tests for {target}"),
                    ProjectTask(task_id="register_capability", description=f"Register {target} as active capability"),
                ],
                success_criteria="Capability registered and passing tests",
            ),
        ]

    def _decompose_fix(self, title: str, target: str,
                       impact: Dict) -> List[Milestone]:
        error_cat = impact.get("error_category", "unknown")
        return [
            Milestone(
                milestone_id="diagnose",
                description=f"Diagnose {error_cat} errors in {target}",
                tasks=[
                    ProjectTask(task_id="collect_errors", description=f"Collect error logs for {target}"),
                    ProjectTask(task_id="classify_root_cause", description=f"Classify root cause of {error_cat} errors"),
                ],
                success_criteria="Root cause identified",
            ),
            Milestone(
                milestone_id="fix",
                description=f"Implement fix for {target}",
                tasks=[
                    ProjectTask(task_id="generate_fix", description=f"Generate fix for {error_cat} in {target}",
                               capability=target),
                    ProjectTask(task_id="sandbox_test", description=f"Test fix in sandbox"),
                ],
                success_criteria="Fix passes sandbox tests",
            ),
            Milestone(
                milestone_id="verify",
                description=f"Verify fix resolves errors",
                tasks=[
                    ProjectTask(task_id="run_fixed_version", description=f"Run fixed version and check for errors"),
                    ProjectTask(task_id="update_registry", description=f"Update capability registry with fix"),
                ],
                success_criteria="Error rate drops to zero",
            ),
        ]

    def _decompose_recombine(self, title: str, target: str,
                             impact: Dict) -> List[Milestone]:
        parts = target.split("+") if "+" in target else [target]
        return [
            Milestone(
                milestone_id="analyze_pattern",
                description=f"Analyze usage pattern for {' + '.join(parts)}",
                tasks=[
                    ProjectTask(task_id="extract_pattern", description="Extract repeated workflow pattern"),
                    ProjectTask(task_id="validate_frequency", description="Validate pattern frequency meets threshold"),
                ],
                success_criteria="Pattern confirmed with ≥3 occurrences",
            ),
            Milestone(
                milestone_id="generate_skill",
                description=f"Generate compound skill",
                tasks=[
                    ProjectTask(task_id="generate_pipeline", description="Generate pipeline code"),
                    ProjectTask(task_id="generate_tests", description="Generate test code"),
                ],
                success_criteria="Pipeline and test code generated",
            ),
            Milestone(
                milestone_id="validate_register",
                description=f"Validate and register compound skill",
                tasks=[
                    ProjectTask(task_id="sandbox_test", description="Run sandbox tests"),
                    ProjectTask(task_id="register", description="Register as new capability"),
                ],
                success_criteria="Compound skill registered and tested",
            ),
        ]

    def _decompose_generic(self, title: str, target: str) -> List[Milestone]:
        return [
            Milestone(
                milestone_id="plan",
                description=f"Plan approach for: {title}",
                tasks=[
                    ProjectTask(task_id="analyze", description="Analyze requirements"),
                    ProjectTask(task_id="design", description="Design solution"),
                ],
                success_criteria="Plan approved by agent orchestrator",
            ),
            Milestone(
                milestone_id="execute",
                description=f"Execute plan",
                tasks=[
                    ProjectTask(task_id="implement", description="Implement solution"),
                    ProjectTask(task_id="test", description="Test solution"),
                ],
                success_criteria="Solution tested and working",
            ),
        ]


# ── Project Engine ─────────────────────────────────────────────────

class ProjectEngine:
    """
    Manages long-horizon autonomous execution.

    Converts high-value goals into persistent projects,
    decomposes them into milestones, tracks progress
    across sessions, and coordinates with the agent orchestrator.
    """

    def __init__(self, projects_path: str = None):
        self._path = projects_path or PROJECTS_PATH
        self._projects: Dict[str, Project] = {}
        self._decomposer = ProjectDecomposer()
        self._history: List[ProjectResult] = []
        self._load()

    # ── Project lifecycle ──────────────────────────────────────────

    def create_project_from_goal(self, goal_id: str, goal_title: str,
                                  goal_type: str, goal_score: float,
                                  target_capability: str = "",
                                  expected_impact: Dict[str, Any] = None) -> Project:
        """Convert a high-value goal into a persistent project."""
        project_id = f"proj_{goal_id}_{int(time.time())}"

        milestones = self._decomposer.decompose_goal(
            goal_id, goal_title, goal_type, goal_score,
            target_capability, expected_impact or {},
        )

        project = Project(
            project_id=project_id,
            name=goal_title,
            goal_source=goal_id,
            goal_score=goal_score,
            milestones=milestones,
            dependencies=[target_capability] if target_capability else [],
        )

        self._projects[project_id] = project
        self._save()

        self._history.append(ProjectResult(
            action="create", project_id=project_id, success=True,
            details=f"Created project from goal '{goal_title}' (score={goal_score:.2f})",
        ))

        return project

    def get_project(self, project_id: str) -> Optional[Project]:
        return self._projects.get(project_id)

    def list_projects(self, status: ProjectStatus = None) -> List[Project]:
        projects = list(self._projects.values())
        if status:
            projects = [p for p in projects if p.status == status]
        return sorted(projects, key=lambda p: -p.goal_score)

    def pause_project(self, project_id: str):
        project = self._projects.get(project_id)
        if project:
            project.status = ProjectStatus.PAUSED
            project.last_updated = time.time()
            self._save()

    def resume_project(self, project_id: str):
        project = self._projects.get(project_id)
        if project and project.status == ProjectStatus.PAUSED:
            project.status = ProjectStatus.ACTIVE
            project.last_updated = time.time()
            self._save()

    # ── Execution ──────────────────────────────────────────────────

    def get_next_task(self) -> Optional[Dict[str, Any]]:
        """
        Get the next executable task from the highest-priority active project.
        Returns task context for the agent orchestrator.
        """
        active = self.list_projects(ProjectStatus.ACTIVE)
        if not active:
            return None

        for project in active:
            milestone = project.current_milestone
            if not milestone:
                # Project complete
                project.status = ProjectStatus.COMPLETED
                project.completed_at = time.time()
                project.last_updated = time.time()
                self._save()
                continue

            # Find next pending task
            for task in milestone.tasks:
                if task.status == TaskStatus.PENDING:
                    milestone.status = MilestoneStatus.IN_PROGRESS
                    return {
                        "project_id": project.project_id,
                        "project_name": project.name,
                        "milestone_id": milestone.milestone_id,
                        "milestone_description": milestone.description,
                        "task_id": task.task_id,
                        "task_description": task.description,
                        "capability": task.capability,
                        "success_criteria": milestone.success_criteria,
                    }

        return None

    def complete_task(self, project_id: str, milestone_id: str,
                      task_id: str, success: bool,
                      result: str = "", error: str = "") -> ProjectResult:
        """Mark a task as complete and update project progress."""
        project = self._projects.get(project_id)
        if not project:
            return ProjectResult(
                action="complete_task", project_id=project_id,
                success=False, details="Project not found",
            )

        # Find the task
        for milestone in project.milestones:
            if milestone.milestone_id == milestone_id:
                for task in milestone.tasks:
                    if task.task_id == task_id:
                        task.status = TaskStatus.DONE if success else TaskStatus.FAILED
                        task.result = result
                        task.error = error
                        task.attempts += 1
                        task.completed_at = time.time()

                        # Check milestone completion
                        if milestone.is_complete:
                            milestone.status = MilestoneStatus.DONE
                            milestone.completed_at = time.time()

                        # Check project completion
                        if project.is_complete:
                            project.status = ProjectStatus.COMPLETED
                            project.completed_at = time.time()

                        project.last_updated = time.time()
                        self._save()

                        self._history.append(ProjectResult(
                            action="complete_task", project_id=project_id,
                            success=success, milestone_id=milestone_id,
                            task_id=task_id,
                            details=f"Task {'done' if success else 'failed'}: {task.description}",
                        ))

                        return ProjectResult(
                            action="complete_task", project_id=project_id,
                            success=success, milestone_id=milestone_id,
                            task_id=task_id,
                            details=f"Progress: {project.progress:.0%}",
                        )

        return ProjectResult(
            action="complete_task", project_id=project_id,
            success=False, details=f"Task {task_id} not found in milestone {milestone_id}",
        )

    def fail_task(self, project_id: str, milestone_id: str,
                  task_id: str, error: str) -> ProjectResult:
        """Mark a task as failed."""
        return self.complete_task(
            project_id, milestone_id, task_id,
            success=False, error=error,
        )

    # ── Resume on startup ──────────────────────────────────────────

    def resume_active_projects(self) -> List[Dict[str, Any]]:
        """
        On startup, load and resume active projects.
        Returns list of projects that need attention.
        """
        active = self.list_projects(ProjectStatus.ACTIVE)
        needs_attention = []

        for project in active:
            milestone = project.current_milestone
            if milestone:
                pending_tasks = [
                    t for t in milestone.tasks
                    if t.status in (TaskStatus.PENDING, TaskStatus.FAILED)
                ]
                needs_attention.append({
                    "project_id": project.project_id,
                    "name": project.name,
                    "progress": project.progress,
                    "current_milestone": milestone.description,
                    "pending_tasks": len(pending_tasks),
                    "goal_score": project.goal_score,
                })

        return needs_attention

    # ── Metrics ────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        """Get project engine statistics."""
        all_projects = list(self._projects.values())
        total = len(all_projects)
        if total == 0:
            return {
                "total_projects": 0,
                "active": 0,
                "completed": 0,
                "avg_progress": 0,
                "milestone_success_rate": 0,
            }

        active = sum(1 for p in all_projects if p.status == ProjectStatus.ACTIVE)
        completed = sum(1 for p in all_projects if p.status == ProjectStatus.COMPLETED)
        failed = sum(1 for p in all_projects if p.status == ProjectStatus.FAILED)

        total_milestones = sum(len(p.milestones) for p in all_projects)
        done_milestones = sum(
            sum(1 for m in p.milestones if m.status == MilestoneStatus.DONE)
            for p in all_projects
        )

        total_tasks = sum(
            sum(len(m.tasks) for m in p.milestones)
            for p in all_projects
        )
        done_tasks = sum(
            sum(1 for m in p.milestones for t in m.tasks if t.status == TaskStatus.DONE)
            for p in all_projects
        )

        avg_progress = sum(p.progress for p in all_projects) / total if total else 0

        return {
            "total_projects": total,
            "active": active,
            "completed": completed,
            "failed": failed,
            "avg_progress": round(avg_progress, 3),
            "total_milestones": total_milestones,
            "completed_milestones": done_milestones,
            "milestone_success_rate": round(done_milestones / total_milestones, 3) if total_milestones else 0,
            "total_tasks": total_tasks,
            "completed_tasks": done_tasks,
            "task_success_rate": round(done_tasks / total_tasks, 3) if total_tasks else 0,
        }

    def get_project_report(self, project_id: str) -> Dict[str, Any]:
        """Get detailed report for a specific project."""
        project = self._projects.get(project_id)
        if not project:
            return {"error": "Project not found"}

        return {
            "project": project.to_dict(),
            "current_milestone": project.current_milestone.milestone_id if project.current_milestone else None,
            "next_task": self.get_next_task(),
        }

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent project engine activity."""
        return [
            {
                "action": r.action,
                "project_id": r.project_id,
                "success": r.success,
                "details": r.details,
                "milestone_id": r.milestone_id,
                "task_id": r.task_id,
            }
            for r in self._history[-limit:]
        ]

    # ── Persistence ────────────────────────────────────────────────

    def _save(self):
        """Persist all projects to disk."""
        try:
            path = Path(self._path)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {pid: p.to_dict() for pid, p in self._projects.items()}
            path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass

    def _load(self):
        """Load projects from disk."""
        try:
            path = Path(self._path)
            if path.exists():
                data = json.loads(path.read_text())
                for pid, pdata in data.items():
                    milestones = []
                    for mdata in pdata.get("milestones", []):
                        tasks = [
                            ProjectTask(
                                task_id=t["task_id"],
                                description=t["description"],
                                capability=t.get("capability", ""),
                                status=TaskStatus(t.get("status", "pending")),
                                result=t.get("result", ""),
                                error=t.get("error", ""),
                                attempts=t.get("attempts", 0),
                                created_at=t.get("created_at", 0),
                                completed_at=t.get("completed_at", 0),
                            )
                            for t in mdata.get("tasks", [])
                        ]
                        milestones.append(Milestone(
                            milestone_id=mdata["milestone_id"],
                            description=mdata["description"],
                            status=MilestoneStatus(mdata.get("status", "pending")),
                            tasks=tasks,
                            success_criteria=mdata.get("success_criteria", ""),
                            created_at=mdata.get("created_at", 0),
                            completed_at=mdata.get("completed_at", 0),
                        ))

                    self._projects[pid] = Project(
                        project_id=pdata["project_id"],
                        name=pdata["name"],
                        goal_source=pdata.get("goal_source", ""),
                        goal_score=pdata.get("goal_score", 0),
                        status=ProjectStatus(pdata.get("status", "active")),
                        milestones=milestones,
                        dependencies=pdata.get("dependencies", []),
                        created_at=pdata.get("created_at", 0),
                        last_updated=pdata.get("last_updated", 0),
                        completed_at=pdata.get("completed_at", 0),
                    )
        except Exception:
            pass


# Singleton
_engine: Optional[ProjectEngine] = None


def get_project_engine() -> ProjectEngine:
    global _engine
    if _engine is None:
        _engine = ProjectEngine()
    return _engine
