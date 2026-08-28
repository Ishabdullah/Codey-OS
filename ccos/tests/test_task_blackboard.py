"""
Tests for TaskContext and TaskBlackboard (Track A / Phase A2 Item 7.5).
"""

import os
import tempfile
import threading
import time
import pytest
from dataclasses import FrozenInstanceError

from ccos.core.task_context import (
    MAX_CONTEXT_PAYLOAD_BYTES,
    ContextPayloadTooLargeError,
    TaskContext,
)
from ccos.core.task_blackboard import (
    TaskBlackboard,
    get_task_blackboard,
)


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


# ── TaskContext Tests ───────────────────────────────────────────────

def test_task_context_creation_and_immutability():
    ctx = TaskContext(
        task_id="t-100",
        step_id="step-1",
        goal="Find files",
        current_app="finder",
        state={"scanned": 10},
        inputs={"pattern": "*.py"},
        output="found 5 files",
        next_action="filter_results",
        confidence=0.95,
        metadata={"priority": "high"},
    )

    assert ctx.task_id == "t-100"
    assert ctx.step_id == "step-1"
    assert ctx.goal == "Find files"
    assert ctx.current_app == "finder"
    assert ctx.state == {"scanned": 10}
    assert ctx.inputs == {"pattern": "*.py"}
    assert ctx.output == "found 5 files"
    assert ctx.next_action == "filter_results"
    assert ctx.confidence == 0.95
    assert ctx.metadata == {"priority": "high"}

    # Immutability check
    with pytest.raises(FrozenInstanceError):
        ctx.step_id = "step-2"  # type: ignore

    with pytest.raises(FrozenInstanceError):
        ctx.output = "new output"  # type: ignore


def test_task_context_evolve():
    ctx1 = TaskContext(
        task_id="t-100",
        step_id="step-1",
        goal="Process order",
        state={"stage": "auth"},
        inputs={"user_id": 42},
    )

    # Progression to step-2 with automatic parent_step_id linking
    ctx2 = ctx1.evolve(
        step_id="step-2",
        output={"authorized": True},
        state={"stage": "billing"},
        inputs={"amount": 99.9},
        next_action="charge_card",
        confidence=0.99,
    )

    assert ctx2.task_id == "t-100"
    assert ctx2.step_id == "step-2"
    assert ctx2.parent_step_id == "step-1"
    assert ctx2.output == {"authorized": True}
    assert ctx2.state == {"stage": "billing"}
    assert ctx2.inputs == {"user_id": 42, "amount": 99.9}
    assert ctx2.next_action == "charge_card"
    assert ctx2.confidence == 0.99
    assert ctx2.goal == "Process order"

    # Original context remains unchanged
    assert ctx1.step_id == "step-1"
    assert ctx1.parent_step_id is None
    assert ctx1.output is None


def test_task_context_serialization_roundtrip():
    ctx = TaskContext(
        task_id="t-200",
        step_id="s-1",
        goal="Analyze log",
        current_app="terminal",
        state={"lines": 500},
        inputs={"query": "error"},
        output=["err1", "err2"],
        next_action="notify",
        confidence=0.88,
        parent_step_id="s-0",
        metadata={"tag": "debug"},
    )

    d = ctx.to_dict()
    assert isinstance(d, dict)
    assert d["task_id"] == "t-200"

    json_str = ctx.to_json()
    assert isinstance(json_str, str)

    reconstructed_from_dict = TaskContext.from_dict(d)
    assert reconstructed_from_dict.task_id == ctx.task_id
    assert reconstructed_from_dict.step_id == ctx.step_id
    assert reconstructed_from_dict.state == ctx.state
    assert reconstructed_from_dict.output == ctx.output
    assert reconstructed_from_dict.parent_step_id == ctx.parent_step_id

    reconstructed_from_json = TaskContext.from_json(json_str)
    assert reconstructed_from_json.task_id == ctx.task_id
    assert reconstructed_from_json.inputs == ctx.inputs
    assert reconstructed_from_json.confidence == ctx.confidence


def test_task_context_size_validation():
    # Valid size context (< 64KB)
    small_ctx = TaskContext(
        task_id="t-300",
        step_id="s-1",
        goal="Small payload test",
        state={"data": "a" * 1000},
    )
    size = small_ctx.validate_size()
    assert size > 1000
    assert size <= MAX_CONTEXT_PAYLOAD_BYTES

    # Exceeding MAX_CONTEXT_PAYLOAD_BYTES (64KB)
    with pytest.raises(ContextPayloadTooLargeError):
        TaskContext(
            task_id="t-300",
            step_id="s-1",
            goal="Large payload test",
            state={"large_dump": "x" * (MAX_CONTEXT_PAYLOAD_BYTES + 1024)},
        )


# ── TaskBlackboard Tests ────────────────────────────────────────────

def test_blackboard_crud_and_isolation(temp_db):
    bb = TaskBlackboard(temp_db)

    # Task A
    assert bb.create_task("task-A", goal="Goal A", metadata={"user": "alice"}) is True
    assert bb.set("task-A", "count", 42) is True
    assert bb.set("task-A", "config", {"theme": "dark", "verbose": True}) is True

    # Task B
    assert bb.create_task("task-B", goal="Goal B") is True
    assert bb.set("task-B", "count", 100) is True

    # Reads & isolation
    assert bb.get("task-A", "count") == 42
    assert bb.get("task-B", "count") == 100
    assert bb.get("task-A", "config") == {"theme": "dark", "verbose": True}
    assert bb.get("task-B", "config") is None
    assert bb.get("task-B", "missing_key", "default_val") == "default_val"

    # get_all
    all_a = bb.get_all("task-A")
    assert all_a["count"] == 42
    assert all_a["config"] == {"theme": "dark", "verbose": True}

    # delete_key
    assert bb.delete_key("task-A", "count") is True
    assert bb.get("task-A", "count") is None
    assert bb.delete_key("task-A", "nonexistent") is False

    bb.close()


def test_blackboard_checkpoints(temp_db):
    bb = TaskBlackboard(temp_db)

    ctx1 = TaskContext(task_id="task-C", step_id="step-1", goal="Goal C", output="step 1 done")
    ctx2 = ctx1.evolve(step_id="step-2", output="step 2 done")
    ctx3 = ctx2.evolve(step_id="step-3", output="step 3 done")

    cp1_id = bb.save_checkpoint(ctx1)
    cp2_id = bb.save_checkpoint(ctx2)
    cp3_id = bb.save_checkpoint(ctx3)

    assert cp1_id < cp2_id < cp3_id

    # Latest checkpoint
    latest = bb.get_latest_checkpoint("task-C")
    assert latest is not None
    assert latest.step_id == "step-3"
    assert latest.output == "step 3 done"
    assert latest.parent_step_id == "step-2"

    # All checkpoints
    checkpoints = bb.get_checkpoints("task-C")
    assert len(checkpoints) == 3
    assert [c.step_id for c in checkpoints] == ["step-1", "step-2", "step-3"]

    # Nonexistent task checkpoints
    assert bb.get_latest_checkpoint("nonexistent") is None
    assert bb.get_checkpoints("nonexistent") == []

    bb.close()


def test_blackboard_task_lifecycle_and_cleanup(temp_db):
    bb = TaskBlackboard(temp_db)

    bb.create_task("task-D", goal="Lifecycle test")
    bb.set("task-D", "key1", "val1")
    ctx = TaskContext(task_id="task-D", step_id="s1", goal="Lifecycle test")
    bb.save_checkpoint(ctx)

    assert bb.complete_task("task-D", "completed") is True

    # Cleanup task
    assert bb.cleanup_task("task-D") is True
    assert bb.get("task-D", "key1") is None
    assert bb.get_latest_checkpoint("task-D") is None

    bb.close()


def test_blackboard_ttl_purge(temp_db):
    bb = TaskBlackboard(temp_db)

    # Expired task (TTL = -10 seconds)
    bb.create_task("task-expired", goal="Expired", ttl_seconds=-10)
    bb.set("task-expired", "foo", "bar")

    # Active task (TTL = 3600 seconds)
    bb.create_task("task-active", goal="Active", ttl_seconds=3600)
    bb.set("task-active", "foo", "active_bar")

    # Persistent task (no TTL)
    bb.create_task("task-persistent", goal="Persistent")
    bb.set("task-persistent", "foo", "perm_bar")

    purged = bb.purge_expired()
    assert purged == 1

    assert bb.get("task-expired", "foo") is None
    assert bb.get("task-active", "foo") == "active_bar"
    assert bb.get("task-persistent", "foo") == "perm_bar"

    bb.close()


def test_blackboard_thread_safety(temp_db):
    bb = TaskBlackboard(temp_db)
    task_id = "task-threads"
    bb.create_task(task_id, goal="Thread safety test")

    num_threads = 10
    writes_per_thread = 20
    errors = []

    def worker(thread_idx):
        try:
            for i in range(writes_per_thread):
                key = f"t_{thread_idx}_k_{i}"
                bb.set(task_id, key, i)
                val = bb.get(task_id, key)
                assert val == i
                ctx = TaskContext(
                    task_id=task_id,
                    step_id=f"step_{thread_idx}_{i}",
                    goal="Thread test",
                    output=i,
                )
                bb.save_checkpoint(ctx)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    all_data = bb.get_all(task_id)
    assert len(all_data) == num_threads * writes_per_thread
    checkpoints = bb.get_checkpoints(task_id)
    assert len(checkpoints) == num_threads * writes_per_thread

    bb.close()
