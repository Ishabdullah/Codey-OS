"""
Task Queue Plugin — thin CCOS adapter over core/taskqueue.py.

core/taskqueue.py's TaskQueue is a stateful, instance-based class with its
own disk persistence (TaskQueue.save() / TaskQueue.load()). CCOS capability
calls are stateless — no capability holds a queue instance in memory across
calls — so this wrap is path-addressable: every capability here takes (or
returns) the queue's JSON file path, loading the TaskQueue from disk at the
start of the call and saving it back (where the operation mutates state)
before returning. This matches what TaskQueue.save()/.load() already exist
for, and avoids introducing an in-memory instance cache that would just be
a second, redundant source of truth alongside the file on disk.

core/orchestrator.py creates and mutates a TaskQueue directly, in-memory,
during a single planning/execution session — that usage is untouched here.
This plugin is for an external CCOS caller that wants to create, inspect,
or update a task queue without importing core/taskqueue.py directly, e.g.
across process/session boundaries where only the file path is durable.
"""
from ccos.plugins._pathutil import ensure_repo_root_on_path

ensure_repo_root_on_path()

from dataclasses import asdict

from core.taskqueue import TaskQueue, list_queues


def taskqueue_create(name="", project_dir=None, original_request=""):
    """Create a new task queue, save it to disk, and return its file path."""
    queue = TaskQueue(name=name, project_dir=project_dir)
    queue.original_request = original_request
    queue.save()
    return str(queue._path)


def taskqueue_add(path, description):
    """Add a task to a queue on disk. Returns the new task as a dict."""
    queue = TaskQueue.load(path)
    task = queue.add(description)
    queue.save()
    return asdict(task)


def taskqueue_mark_running(path, task_id):
    """Mark a task as running and persist. Returns the updated status dict."""
    queue = TaskQueue.load(path)
    queue.mark_running(task_id)
    return taskqueue_status(path)


def taskqueue_mark_done(path, task_id, result=""):
    """Mark a task as done (with an optional result) and persist."""
    queue = TaskQueue.load(path)
    queue.mark_done(task_id, result=result)
    return taskqueue_status(path)


def taskqueue_mark_failed(path, task_id, error=""):
    """Mark a task as failed (with an optional error) and persist."""
    queue = TaskQueue.load(path)
    queue.mark_failed(task_id, error=error)
    return taskqueue_status(path)


def taskqueue_status(path):
    """Return a snapshot of a queue's state: tasks, counts, completion."""
    queue = TaskQueue.load(path)
    current = queue.current()
    return {
        "name": queue.name,
        "project_dir": queue.project_dir,
        "original_request": queue.original_request,
        "tasks": [asdict(t) for t in queue.tasks],
        "pending_count": queue.pending_count(),
        "done_count": queue.done_count(),
        "is_complete": queue.is_complete(),
        "current_task": asdict(current) if current else None,
    }


def taskqueue_list():
    """List all saved queues (newest first) as [{path, name, project_dir, ...}]."""
    result = []
    for p, q in list_queues():
        result.append(
            {
                "path": str(p),
                "name": q.name,
                "project_dir": q.project_dir,
                "pending_count": q.pending_count(),
                "done_count": q.done_count(),
                "is_complete": q.is_complete(),
            }
        )
    return result


def test() -> bool:
    """Plugin self-test — create, mutate, and reload a throwaway queue."""
    import tempfile
    from pathlib import Path

    tmp_dir = tempfile.mkdtemp(prefix="taskqueue_selftest_")
    path = taskqueue_create(name="selftest", project_dir=tmp_dir)
    try:
        task = taskqueue_add(path, "do a thing")
        assert task["id"] == 1, "Expected first task id to be 1"
        status = taskqueue_mark_done(path, task["id"], result="ok")
        assert status["done_count"] == 1, "Expected done_count 1"
        assert status["is_complete"] is True, "Expected queue complete"
        return True
    finally:
        Path(path).unlink(missing_ok=True)
