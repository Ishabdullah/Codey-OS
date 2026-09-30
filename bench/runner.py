"""Run an agent over the suite and append to an append-only JSONL ledger."""
import json
import shutil
import tempfile
import time
from pathlib import Path

from .lock import suite_hash, verify_lock
from .suite import load_tasks
from .verify import grade


def run_suite(agent, label: str, ledger: Path, meta: dict | None = None,
              tasks=None, repeats: int = 1, require_lock: bool = True) -> list:
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
                passed = grade(t, ws)
                rows.append({"label": label, "task": t.id, "rep": rep, "passed": passed,
                             "secs": round(time.time() - t0, 2), "error": err,
                             "suite_hash": sh, "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                             "meta": meta or {}})
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger, "a") as f:  # append-only
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return rows
