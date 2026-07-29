#!/usr/bin/env python3
"""Test for task_queue plugin."""
import importlib.util
import json
import tempfile
from pathlib import Path

# _pathutil.py lives at ccos/plugins/_pathutil.py, two levels above this
# plugin's directory (test.py -> task_queue/ -> coding/ -> plugins/).
# Loaded by file path since the ccos package isn't importable yet.
_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

from ccos.plugins.coding.task_queue.task_queue import (
    taskqueue_add,
    taskqueue_create,
    taskqueue_list,
    taskqueue_mark_done,
    taskqueue_mark_failed,
    taskqueue_mark_running,
    taskqueue_status,
    test,
)

# Distinct project_dir/name so this never collides with real session data
# under ~/.codey_sessions/ (real queues use the caller's actual cwd).
_TEST_PROJECT_DIR = tempfile.mkdtemp(prefix="task_queue_plugin_test_project_")
_TEST_NAME = "ccos_plugin_test_queue"


def test_create_and_add():
    path = taskqueue_create(name=_TEST_NAME, project_dir=_TEST_PROJECT_DIR, original_request="test request")
    try:
        assert Path(path).exists(), "Queue file should exist after create"
        t1 = taskqueue_add(path, "first task")
        t2 = taskqueue_add(path, "second task")
        assert t1["id"] == 1 and t2["id"] == 2, "Expected sequential task ids"
        print("[PASS] taskqueue_create()/taskqueue_add() persist a new queue")
    finally:
        Path(path).unlink(missing_ok=True)


def test_status_transitions_and_persistence():
    path = taskqueue_create(name=_TEST_NAME, project_dir=_TEST_PROJECT_DIR)
    try:
        t1 = taskqueue_add(path, "task one")
        t2 = taskqueue_add(path, "task two")
        t3 = taskqueue_add(path, "task three")

        taskqueue_mark_running(path, t1["id"])
        taskqueue_mark_done(path, t1["id"], result="did it")
        taskqueue_mark_failed(path, t2["id"], error="broke")

        status = taskqueue_status(path)
        assert status["done_count"] == 1, f"Expected done_count 1, got {status['done_count']}"
        assert status["pending_count"] == 1, f"Expected pending_count 1, got {status['pending_count']}"
        assert status["current_task"]["id"] == t3["id"], "Expected remaining pending task as current"
        assert status["is_complete"] is False, "Queue should not be complete (t3 still pending)"

        # Prove real disk persistence: raw JSON file content, not in-memory state.
        raw = json.loads(Path(path).read_text())
        statuses = {t["id"]: t["status"] for t in raw["tasks"]}
        assert statuses[t1["id"]] == "done", "Disk JSON should show task 1 as done"
        assert statuses[t2["id"]] == "failed", "Disk JSON should show task 2 as failed"
        assert statuses[t3["id"]] == "pending", "Disk JSON should show task 3 as pending"
        assert raw["tasks"][0]["result"] == "did it", "Disk JSON should show persisted result"
        assert raw["tasks"][1]["error"] == "broke", "Disk JSON should show persisted error"

        # Reload via a fresh call (simulates a new process/session reading the same path).
        reloaded = taskqueue_status(path)
        assert reloaded == status, "Status from a fresh reload should match"

        print("[PASS] status transitions persist to disk and survive a fresh reload")
        print(f"       raw JSON: {json.dumps(raw, indent=2)}")
    finally:
        Path(path).unlink(missing_ok=True)


def test_list_includes_created_queue():
    path = taskqueue_create(name=_TEST_NAME, project_dir=_TEST_PROJECT_DIR)
    try:
        taskqueue_add(path, "only task")
        queues = taskqueue_list()
        paths = [q["path"] for q in queues]
        assert path in paths, "taskqueue_list() should include the newly created queue"
        print("[PASS] taskqueue_list() reports the created queue")
    finally:
        Path(path).unlink(missing_ok=True)


def test_self_test():
    result = test()
    assert result is True
    print("[PASS] Self-test passed")


if __name__ == "__main__":
    test_create_and_add()
    test_status_transitions_and_persistence()
    test_list_includes_created_queue()
    test_self_test()
    print("\nAll task_queue tests passed!")
