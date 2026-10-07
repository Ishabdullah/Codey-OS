"""Grade a workspace against a task's hidden tests, in a fresh temp copy."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .suite import Task


class GradingError(Exception):
    """Raised when the grading harness itself fails to run (not an agent/test failure).

    Deliberately does NOT cover a hidden-test timeout -- that stays a `False`
    verdict (see grade()). If a timeout were treated as a harness error and
    excluded from the gate's comparison instead, a hanging agent would escape
    the denominator rather than lose it: a hanging agent must not score
    better than one that fails cleanly.
    """


def grade(task: Task, workspace: Path, timeout: int = 60) -> bool:
    """True iff hidden tests pass against the agent's workspace.

    Raises GradingError on a harness-side failure (e.g. a missing hidden/
    dir, a copytree I/O error) -- not on an agent/test failure. A hidden-test
    timeout is still a False verdict, not an error (see GradingError).
    """
    try:
        with tempfile.TemporaryDirectory(prefix="bench_grade_") as td:
            work = Path(td) / "w"
            shutil.copytree(workspace, work, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
            # hidden tests (and any fixture subdirs) overwrite any agent-written file of same name
            shutil.copytree(task.hidden, work, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc"))
            r = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", str(work)],
                cwd=work, capture_output=True, text=True, timeout=timeout)
            return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception as e:
        raise GradingError(f"grading harness failed for task {task.id}: {e!r}") from e
