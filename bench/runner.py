"""Run an agent over the suite and append to an append-only JSONL ledger."""
import json
import shutil
import tempfile
import time
from pathlib import Path

from .lock import evaluator_hash, read_lock, suite_hash, verify_lock
from .suite import Task, load_tasks
from .verify import GradingError, grade


def run_suite(agent, label: str, ledger: Path, meta: dict | None = None,
              tasks=None, repeats: int = 1, require_lock: bool = True, traj_db=None) -> list:
    """Run `agent` over the tasks and append rows to `ledger`.

    The tasks (starter/hidden/reference) are snapshotted ONCE into a private
    temp dir after the lock check and graded from the snapshot, so a later edit
    of bench/tasks in the repo is never honored mid-run. The snapshot lives in
    the same uid's temp space, so it is also re-hashed before every rep and
    again before every grade; a mismatch aborts the run (RuntimeError, no rows
    appended). Row `suite_hash` is the hash of the tasks ACTUALLY graded (the
    snapshot; equal to the locked `tasks:` value for the default suite, the
    subset's own hash otherwise) and `evaluator_hash` is the bench/*.py hash
    (equal to the locked `evaluator:` value when require_lock).
    """
    if require_lock and not verify_lock():
        raise RuntimeError("bench/suite.lock mismatch: suite was modified; refusing to run")
    default_suite = tasks is None
    tasks = tasks if tasks is not None else load_tasks()
    eh = evaluator_hash()
    locked = read_lock() if require_lock else None
    if require_lock and (locked is None or locked["evaluator"] != eh):
        raise RuntimeError("bench evaluator files changed after the lock check; refusing to run")
    snap = Path(tempfile.mkdtemp(prefix="bench_suite_"))
    try:
        return _run_snapshotted(agent, label, ledger, meta, tasks, repeats, traj_db,
                                snap, eh, locked if default_suite else None)
    finally:
        shutil.rmtree(snap, ignore_errors=True)


def _snapshot(tasks, snap: Path) -> list:
    out = []
    for t in tasks:
        dest = snap / t.id
        shutil.copytree(t.dir, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        out.append(Task(t.id, dest))
    return out


def _run_snapshotted(agent, label, ledger, meta, tasks, repeats, traj_db, snap, eh, locked) -> list:
    tasks = _snapshot(tasks, snap)
    sh = suite_hash(snap)
    if locked is not None and sh != locked["tasks"]:
        raise RuntimeError("bench/tasks changed between lock check and snapshot; refusing to run")
    th = {t.id: suite_hash(t.dir) for t in tasks}

    def _unchanged(t):
        if suite_hash(t.dir) != th[t.id]:
            raise RuntimeError(f"bench task files changed during the run (task {t.id}); aborting")

    rows = []
    for t in tasks:
        for rep in range(repeats):
            _unchanged(t)
            with tempfile.TemporaryDirectory(prefix="bench_ws_") as td:
                ws = Path(td) / "ws"
                shutil.copytree(t.starter, ws)
                t0 = time.time()
                err = None
                try:
                    agent(t, ws)
                except Exception as e:  # agent crash = failure, recorded
                    err = repr(e)
                _unchanged(t)
                grading_error = None
                try:
                    passed = grade(t, ws)
                except GradingError as e:
                    passed = None
                    grading_error = repr(e)
                    print(f"bench/runner: grading error on task {t.id} rep {rep}: {grading_error}")
                # Label the agent's episodes with the EXTERNAL grader verdict; never
                # label a bogus (None/grading-error) verdict into the trajectory
                # store (NEW-761-sensitive: that's what the evaluation-leak finding
                # was about).
                if traj_db and passed is not None:
                    try:
                        from core.trajectory import label_tag
                        label_tag(f"bench:{t.id}", f"bench:{sh[:12]}", passed, since_ts=t0, path=traj_db)
                    except Exception as e:
                        # Logged, not raised: a trajectory-labeling failure must not
                        # lose the ledger rows this run already produced.
                        print(f"bench/runner: label_tag failed for task {t.id} rep {rep}: {e!r}")
                rows.append({"label": label, "task": t.id, "rep": rep, "passed": passed,
                             "secs": round(time.time() - t0, 2), "error": err,
                             "grading_error": grading_error,
                             "suite_hash": sh, "evaluator_hash": eh, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                             "meta": meta or {}})
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger, "a") as f:  # append-only
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return rows
