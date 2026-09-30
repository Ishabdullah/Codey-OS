"""Grade a workspace against a task's hidden tests, in a fresh temp copy."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .suite import Task


def grade(task: Task, workspace: Path, timeout: int = 60) -> bool:
    """True iff hidden tests pass against the agent's workspace. Never raises."""
    try:
        with tempfile.TemporaryDirectory(prefix="bench_grade_") as td:
            work = Path(td) / "w"
            shutil.copytree(workspace, work, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
            for f in task.hidden.iterdir():  # hidden tests overwrite any agent-written file of same name
                shutil.copy2(f, work / f.name)
            r = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", str(work)],
                cwd=work, capture_output=True, text=True, timeout=timeout)
            return r.returncode == 0
    except Exception:
        return False
