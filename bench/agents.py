"""Agent adapters. An agent is a callable (task, workspace_path) -> None that edits the workspace."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .suite import Task

REPO = Path(__file__).resolve().parent.parent


def null_agent(task: Task, workspace: Path) -> None:
    """Does nothing. Must score 0 (proves tasks are not pre-solved)."""


def oracle_agent(task: Task, workspace: Path) -> None:
    """Copies the reference solution. Must score 100% (proves tasks are solvable)."""
    for f in task.reference.iterdir():
        shutil.copy2(f, workspace / f.name)


def make_codey_cli_agent(timeout: int = 900, extra_env: dict | None = None, extra_args: list | None = None):
    """Real Codey-OS via one-shot CLI. Needs a running llama-server: on-device only."""
    def agent(task: Task, workspace: Path) -> None:
        env = dict(os.environ)
        env.update({"CODEY_TRAJECTORY": "1", "CODEY_TRAJECTORY_TAG": f"bench:{task.id}"})
        env.update(extra_env or {})
        cmd = [sys.executable, str(REPO / "main.py"), task.prompt, "--yolo", "--no-resume"] + (extra_args or [])
        try:
            subprocess.run(cmd, cwd=workspace, env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            pass  # graded as-is; a timeout is a failure only if tests fail
    return agent
