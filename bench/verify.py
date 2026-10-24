"""Grade a workspace against a task's hidden tests, in a fresh temp copy."""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Mapping

from .suite import Task

# Names the grading pytest child may inherit. Everything else (PYTEST_ADDOPTS,
# PYTEST_PLUGINS, PYTHON*, API keys, proxies, ALLOW_SELF_MOD ...) is dropped:
# an ambient PYTEST_ADDOPTS=--collect-only would otherwise turn every run into
# a zero-test "pass" at the exit-code level.
_GRADER_ENV_ALLOW = ("PATH", "TMPDIR", "LANG", "LC_ALL", "PREFIX", "ANDROID_ROOT", "ANDROID_DATA")

# A hidden dir must hold only test modules. With --noconftest and an empty -c
# file these would silently stop working, so their presence is a harness defect.
_HIDDEN_FORBIDDEN = frozenset({"conftest.py", "pytest.ini", "tox.ini", "pyproject.toml",
                               "setup.cfg", "sitecustomize.py", "usercustomize.py"})

_JUNIT_MAX_BYTES = 1024 * 1024  # a junit file bigger than this is treated as no evidence
_EXPECTED_TIMEOUT = 120  # fixed, independent of grade()'s timeout: the reference run is harness-side
_expected_cache: dict = {}


def _copy_ignore(directory, names):
    """copytree ignore hook: skip caches/bytecode, symlinks and special files (FIFOs, sockets, devices).

    A dangling symlink, a symlink loop or a FIFO would otherwise make copytree
    raise (GradingError -> passed=None -> the agent escapes the denominator) or
    block forever. A symlink copied into the grading tree could also redirect
    the hidden-test overlay write to a file outside it. Skipping them turns
    these into an ordinary failed grade.
    """
    skip = set(shutil.ignore_patterns("__pycache__", ".pytest_cache", "*.pyc")(directory, names))
    for n in names:
        full = os.path.join(directory, n)
        if os.path.islink(full) or not (os.path.isdir(full) or os.path.isfile(full)):
            skip.add(n)
    return skip


class GradingError(Exception):
    """Raised when the grading harness itself fails to run (not an agent/test failure).

    Deliberately does NOT cover a hidden-test timeout -- that stays a `False`
    verdict (see grade()). If a timeout were treated as a harness error and
    excluded from the gate's comparison instead, a hanging agent would escape
    the denominator rather than lose it: a hanging agent must not score
    better than one that fails cleanly.
    """


def _grader_env(base: Mapping[str, str], home: Path) -> dict:
    """Build the pytest child's environment: allowlisted system names plus an empty HOME.

    Pure function of its inputs so a test can feed a hostile mapping. Anything
    not in _GRADER_ENV_ALLOW is dropped, which is what keeps PYTEST_ADDOPTS /
    PYTEST_PLUGINS / PYTHON* and credentials out of the grader.
    """
    env = {k: base[k] for k in _GRADER_ENV_ALLOW if k in base}
    env["HOME"] = str(home)
    return env


def _junit_counts(path: Path):
    """Return (tests, failures, errors, skipped) summed over all <testsuite>, or None.

    None means "no usable evidence" (missing, oversized, unparseable). The file
    is written by the pytest child and an agent module could overwrite it, so
    the read is capped and any parse problem is a None rather than an exception.
    """
    try:
        with open(path, "rb") as fh:
            data = fh.read(_JUNIT_MAX_BYTES + 1)
        if len(data) > _JUNIT_MAX_BYTES:
            return None
        root = ET.fromstring(data)
        totals = [0, 0, 0, 0]
        for ts in root.iter("testsuite"):
            for i, key in enumerate(("tests", "failures", "errors", "skipped")):
                totals[i] += int(ts.get(key, "0"))
        return tuple(totals)
    except Exception:
        # Any I/O or parse failure means the agent's code (or a crash) left no
        # trustworthy evidence; the caller maps None to a False verdict, which
        # is the fail-closed direction, so swallowing the detail here is safe.
        return None


def _verdict(rc: int, counts, expected: int) -> bool:
    """The evidence rule: exit 0 AND junit shows exactly `expected` tests, none failed/errored/skipped.

    A skipped test still exits 0, so the skipped count must be checked
    explicitly; missing evidence (counts is None) is never a pass.
    """
    if rc != 0 or counts is None:
        return False
    tests, failures, errors, skipped = counts
    return tests == expected and failures == errors == skipped == 0


def _hidden_tests(task: Task) -> list:
    """Sorted relative paths of the hidden test files; GradingError on a defective hidden dir."""
    hidden = Path(task.hidden)
    files = sorted(p for p in hidden.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts)
    bad = [p.name for p in files if p.name in _HIDDEN_FORBIDDEN]
    if bad:
        raise GradingError(f"hidden fixtures must live in the test file, found {bad} for task {task.id}")
    tests = [p.relative_to(hidden) for p in files if p.name.startswith("test_") and p.suffix == ".py"]
    if not tests:
        raise GradingError(f"task {task.id} has no hidden test_*.py files")
    return tests


def _run_hardened(td: Path, work: Path, targets: list, timeout: int):
    """Run the hardened pytest in `work`; return (returncode, junit counts or None).

    -I (no PYTHON* env, no cwd on sys.path, no user site) keeps sitecustomize in
    the workspace out; --noconftest and an empty -c file outside the workspace
    stop conftest/ini/tox/pyproject/setup.cfg from steering pytest;
    --disable-plugin-autoload stops entry-point plugins; only explicit hidden
    paths are collected so agent-written test files never run. May raise
    subprocess.TimeoutExpired.
    """
    cfg = td / "cfg"
    cfg.mkdir()
    # Harness-owned config: its only content is the workspace on sys.path
    # (pytest `pythonpath`), because -I removes the cwd and a workspace-root
    # __init__.py would otherwise make pytest's prepend import mode put the
    # workspace's parent on sys.path instead (ModuleNotFoundError).
    (cfg / "pytest.ini").write_text(f"[pytest]\npythonpath = {work}\n")
    home = td / "home"
    home.mkdir()
    junit = td / "junit.xml"
    r = subprocess.run(
        [sys.executable, "-I", "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
         "--noconftest", "--disable-plugin-autoload",
         "-c", str(cfg / "pytest.ini"), "--rootdir", str(work), f"--junitxml={junit}",
         *[str(t) for t in targets]],
        cwd=work, env=_grader_env(os.environ, home),
        capture_output=True, text=True, timeout=timeout)
    return r.returncode, _junit_counts(junit)


def _expected_tests(task: Task) -> int:
    """Number of hidden tests, measured by running the locked reference solution through the same hardened command.

    The reference must pass its own hidden tests with at least one test and no
    failures/errors/skips, else GradingError (harness defect, not an agent
    failure). Cached per (hidden bytes, reference bytes) so reps cost one
    extra pytest start per task per process.
    """
    targets = _hidden_tests(task)
    h = hashlib.sha256()
    for root in (Path(task.hidden), Path(task.reference)):
        for p in sorted(root.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                h.update(str(p.relative_to(root)).encode() + b"\0" + p.read_bytes() + b"\0")
    key = (str(Path(task.hidden).resolve()), h.hexdigest())
    if key in _expected_cache:
        return _expected_cache[key]
    try:
        with tempfile.TemporaryDirectory(prefix="bench_expect_") as td:
            td = Path(td)
            work = td / "w"
            shutil.copytree(task.reference, work, ignore=_copy_ignore)
            shutil.copytree(task.hidden, work, dirs_exist_ok=True,
                            ignore=_copy_ignore)
            rc, counts = _run_hardened(td, work, targets, _EXPECTED_TIMEOUT)
    except GradingError:
        raise
    except Exception as e:
        raise GradingError(f"could not measure expected test count for task {task.id}: {e!r}") from e
    if rc != 0 or counts is None or counts[0] < 1 or any(counts[1:]):
        raise GradingError(f"reference solution does not pass its hidden tests for task {task.id}: rc={rc} counts={counts}")
    _expected_cache[key] = counts[0]
    return counts[0]


def grade(task: Task, workspace: Path, timeout: int = 60) -> bool:
    """True iff hidden tests pass against the agent's workspace.

    Isolation: the workspace is copied (symlinks and special files skipped), hidden tests overlaid, and pytest runs
    hardened (see _run_hardened) in a scrubbed environment, collecting only
    the explicit hidden test paths. Evidence rule: a pass needs pytest exit 0
    AND a harness-owned junit file showing exactly the expected number of
    hidden tests (measured on the locked reference solution), all passed; exit
    0 without that evidence (e.g. os._exit(0) in the agent module) is False.

    Raises GradingError on a harness-side failure (e.g. a missing hidden/
    dir, a copytree I/O error, a reference that fails) -- not on an agent/test
    failure. A hidden-test timeout is still a False verdict, not an error (see
    GradingError). Residual: the agent's code runs inside the grader process,
    so an in-process forgery of the junit file with the correct count is not
    prevented (spec docs/wp2_1_g15f_spec.md 0.3); this is not a sandbox.
    """
    try:
        targets = _hidden_tests(task)
        expected = _expected_tests(task)
        with tempfile.TemporaryDirectory(prefix="bench_grade_") as td:
            td = Path(td)
            work = td / "w"
            shutil.copytree(workspace, work, ignore=_copy_ignore)
            # hidden tests (and any fixture subdirs) overwrite any agent-written file of same name
            shutil.copytree(task.hidden, work, dirs_exist_ok=True,
                            ignore=_copy_ignore)
            rc, counts = _run_hardened(td, work, targets, timeout)
            return _verdict(rc, counts, expected)
    except subprocess.TimeoutExpired:
        return False
    except GradingError:
        raise
    except Exception as e:
        raise GradingError(f"grading harness failed for task {task.id}: {e!r}") from e
