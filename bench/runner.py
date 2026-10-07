"""Run an agent over the suite and append to an append-only JSONL ledger."""
import json
import shutil
import tempfile
import time
from pathlib import Path

from .lock import suite_hash, verify_lock
from .suite import load_tasks
from .verify import GradingError, grade


def run_suite(agent, label: str, ledger: Path, meta: dict | None = None,
              tasks=None, repeats: int = 1, require_lock: bool = True, traj_db=None) -> list:
    if require_lock and not verify_lock():
        raise RuntimeError("bench/suite.lock mismatch: suite was modified; refusing to run")
    tasks = tasks if tasks is not None else load_tasks()
    sh = suite_hash()
    rows = []
    for t in tasks:
        for rep in range(repeats):
            with tempfile.TemporaryDirectory(prefix="bench_ws_") as td:
                ws = Path(td) / "ws"
                shutil.copytree(t.starter, ws)
                t0 = time.time()
                err = None
                try:
                    agent(t, ws)
                except Exception as e:  # agent crash = failure, recorded
                    err = repr(e)
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
                             "suite_hash": sh, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                             "meta": meta or {}})
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger, "a") as f:  # append-only
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return rows
