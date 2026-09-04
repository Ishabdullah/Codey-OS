"""
T7 (docs/telemetry_layer_design.md §7 / §2.E) — category-E task-outcome
telemetry wired into core/task_executor.py::_execute_task() and the
step/tool/retry/escalation side-channel it reads from core/agent.py.

Mirrors tests/test_plannd_telemetry.py's coverage pattern: TELEMETRY_ENABLED
forced True within this file (overriding tests/conftest.py's session-wide
False default), telemetry/store.record() monkeypatched to a capture list so
no test touches a real writer thread or the filesystem, and
core.agent.run_agent is mocked directly rather than exercising a real
inference call (never load a real model in a unit test — CLAUDE.md rule 2).

Scope note repeated from core/task_executor.py's own module comment: since
core/daemon.py is out of this sub-task's scope, no production call site
passes task_id/task_type yet -- these tests exercise `_execute_task()`
called directly with the new keyword-only parameters, which is exactly how
a future daemon.py change (T8) would call it.
"""
from __future__ import annotations

import asyncio

import pytest

from core.daemon_config import DaemonConfig
from core.state import StateStore
from core.task_executor import TaskExecutor
from telemetry import envelope, recorders


@pytest.fixture(autouse=True)
def _capture_telemetry(monkeypatch):
    captured = []

    def fake_record(rec):
        captured.append(rec)

    monkeypatch.setattr(recorders.store, "record", fake_record)
    monkeypatch.setattr(recorders.store, "get_run_id", lambda: "task-executor-telemetry-test")
    monkeypatch.setattr(recorders.store, "TELEMETRY_ENABLED", True)
    envelope.reset_seq()
    return captured


@pytest.fixture
def executor(tmp_path):
    state = StateStore(db_path=tmp_path / "state.db")
    config = DaemonConfig()
    return TaskExecutor(state=state, config=config)


def _records_by_event_type(captured, event_type):
    return [r for r in captured if r.get("event_type") == event_type]


def test_no_telemetry_without_task_id(executor, monkeypatch, _capture_telemetry):
    """Passivity/no-guess gate: task_id is the sole trigger for emission.
    A caller that only supplies `prompt` (every current production caller)
    gets no task-telemetry records at all -- never a guessed task_id."""
    monkeypatch.setattr(
        "core.agent.run_agent", lambda *a, **kw: ("done", []), raising=False
    )
    result = asyncio.run(executor._execute_task("do the thing"))
    assert result == "done"
    assert _capture_telemetry == []


def test_successful_task_emits_started_and_finished_with_counts(
    executor, monkeypatch, _capture_telemetry
):
    def fake_run_agent(user_message, history, **kwargs):
        import core.agent as agent_mod

        # Mirrors run_agent()'s own reset-and-bump-"_seq" behaviour so the
        # _execute_task()-side "_seq" mismatch guard sees this as a real
        # (simulated) run_agent() invocation, not a leftover stale dict.
        agent_mod._run_agent_call_seq += 1
        stats = agent_mod._LAST_RUN_STATS
        stats.clear()
        stats["_seq"] = agent_mod._run_agent_call_seq
        stats["step_count"] = 3
        stats["max_steps"] = 20
        stats["hit_max_steps"] = False
        stats["tools_called"] = {"write_file": 2, "shell": 1}
        stats["auto_retries"] = 1
        stats["escalated"] = False
        return "task complete", history

    monkeypatch.setattr("core.agent.run_agent", fake_run_agent, raising=False)

    result = asyncio.run(
        executor._execute_task(
            "step 1/1: do the thing",
            task_id=42,
            task_type="direct",
            needs_planning=False,
        )
    )
    assert result == "task complete"

    started = _records_by_event_type(_capture_telemetry, "task_started")
    finished = _records_by_event_type(_capture_telemetry, "task_finished")
    assert len(started) == 1
    assert len(finished) == 1

    s = started[0]["body"]
    assert s["task_id"] == 42
    assert s["task_type"] == "direct"
    assert s["needs_planning"] is False
    # None-valued fields not yet meaningful on a task_started record (e.g.
    # terminal_status) are pruned from the body entirely rather than kept
    # as an unreasoned null (recorders.py's _emit() "not applicable yet"
    # contract, distinct from an honest-null observation failure).
    assert "terminal_status" not in s

    f = finished[0]["body"]
    assert f["task_id"] == 42
    assert f["terminal_status"] == "done"
    assert f["step_count"] == 3
    assert f["max_steps"] == 20
    assert f["hit_max_steps"] is False
    assert f["tools_called"] == {"write_file": 2, "shell": 1}
    assert f["tool_call_total"] == 3
    assert f["retries"] == 1
    assert f["escalated"] is False
    assert f["duration_ms"] > 0
    assert "error_class" not in f
    assert f["timeout_sec"] == 1800


def test_failed_task_emits_finished_with_failed_status_and_error_class(
    executor, monkeypatch, _capture_telemetry
):
    def fake_run_agent(user_message, history, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("core.agent.run_agent", fake_run_agent, raising=False)

    with pytest.raises(RuntimeError):
        asyncio.run(
            executor._execute_task(
                "do the thing", task_id=7, task_type="direct", needs_planning=False
            )
        )

    finished = _records_by_event_type(_capture_telemetry, "task_finished")
    assert len(finished) == 1
    f = finished[0]["body"]
    assert f["terminal_status"] == "failed"
    assert f["error_class"] == "RuntimeError"
    assert "step_count" not in f


def test_run_agent_never_reached_reports_no_stale_stats(
    executor, monkeypatch, _capture_telemetry
):
    """A prior task's leftover _LAST_RUN_STATS must never be attributed to
    a later task_id when run_agent() was never reached for that call (the
    "_seq" mismatch guard in _execute_task's finally block)."""
    import core.agent as agent_mod

    # Simulate a previous, unrelated run_agent() call having already
    # populated the side-channel.
    agent_mod._run_agent_call_seq += 1
    agent_mod._LAST_RUN_STATS = {
        "_seq": agent_mod._run_agent_call_seq,
        "step_count": 99,
        "max_steps": 20,
        "hit_max_steps": False,
        "tools_called": {"shell": 5},
        "auto_retries": 3,
        "escalated": False,
        "escalation_reason": None,
        "escalation_outcome": None,
    }

    # Fail before run_agent is ever reached.
    def _boom_invalidate_prompt_cache():
        raise RuntimeError("setup failed before run_agent")

    monkeypatch.setattr(
        "prompts.layered_prompt.invalidate_prompt_cache",
        _boom_invalidate_prompt_cache,
    )

    with pytest.raises(RuntimeError, match="setup failed before run_agent"):
        asyncio.run(
            executor._execute_task(
                "do the thing", task_id=99, task_type="direct", needs_planning=False
            )
        )

    finished = _records_by_event_type(_capture_telemetry, "task_finished")
    assert len(finished) == 1
    f = finished[0]["body"]
    # None of the previous call's counters (step_count=99, tools_called with
    # shell=5, etc.) leaked into this task's record -- they are absent
    # entirely, not a guessed/stale value.
    assert "step_count" not in f
    assert "tools_called" not in f
    assert "retries" not in f
    assert f["terminal_status"] == "failed"


def test_redirect_escalation_outcome_absent_not_pruned_field(
    executor, monkeypatch, _capture_telemetry
):
    """End-to-end: when core/agent.py leaves escalation_outcome=None with
    no matching `nulls` entry (the [redirect]: branch -- see
    core/agent.py's comment there for why no null_reason_codes value is
    available), telemetry/recorders.py's _emit() prunes the field from
    the body entirely rather than keeping it as an unreasoned null (it is
    not in record_task_finished's `always_keep_null` set). Confirms the
    real end-to-end behaviour, not just the agent.py-side stats dict."""

    def fake_run_agent(user_message, history, **kwargs):
        import core.agent as agent_mod

        agent_mod._run_agent_call_seq += 1
        stats = agent_mod._LAST_RUN_STATS
        stats.clear()
        stats["_seq"] = agent_mod._run_agent_call_seq
        stats["step_count"] = 4
        stats["max_steps"] = 20
        stats["hit_max_steps"] = False
        stats["tools_called"] = {"patch_file": 2}
        stats["auto_retries"] = 2
        stats["escalated"] = True
        stats["escalation_reason"] = "patch_failure"
        stats["escalation_outcome"] = None
        return "redirected", history

    monkeypatch.setattr("core.agent.run_agent", fake_run_agent, raising=False)

    result = asyncio.run(
        executor._execute_task(
            "do the thing", task_id=13, task_type="direct", needs_planning=False
        )
    )
    assert result == "redirected"

    finished = _records_by_event_type(_capture_telemetry, "task_finished")
    assert len(finished) == 1
    f = finished[0]["body"]
    assert f["escalated"] is True
    assert f["escalation_reason"] == "patch_failure"
    assert "escalation_outcome" not in f


def test_cancelled_task_emits_finished_with_cancelled_status(
    executor, monkeypatch, _capture_telemetry
):
    """A genuine cancellation of the awaiting coroutine (e.g. asyncio.run()'s
    own shutdown cancelling a still-pending task on SIGINT, per
    core/daemon.py's `except KeyboardInterrupt`) must record
    terminal_status="cancelled" -- not "timeout". This function's own scope
    has no asyncio.wait_for of its own, so CancelledError reaching it is
    never distinguishable from any other cancellation."""
    import time as _time

    def fake_run_agent(user_message, history, **kwargs):
        # Runs on the run_in_executor() worker thread; sleep long enough
        # that the outer task.cancel() below fires while this is still
        # "in flight" from the coroutine's perspective.
        _time.sleep(0.5)
        return "should not get here", history

    monkeypatch.setattr("core.agent.run_agent", fake_run_agent, raising=False)

    async def _run():
        task = asyncio.ensure_future(
            executor._execute_task(
                "do the thing", task_id=11, task_type="direct", needs_planning=False
            )
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_run())

    finished = _records_by_event_type(_capture_telemetry, "task_finished")
    assert len(finished) == 1
    f = finished[0]["body"]
    assert f["terminal_status"] == "cancelled"


def test_kill_switch_off_emits_nothing(executor, monkeypatch, _capture_telemetry):
    monkeypatch.setattr(recorders.store, "TELEMETRY_ENABLED", False)
    monkeypatch.setattr(
        "core.agent.run_agent", lambda *a, **kw: ("done", []), raising=False
    )

    result = asyncio.run(
        executor._execute_task(
            "do the thing", task_id=1, task_type="direct", needs_planning=False
        )
    )
    assert result == "done"
    assert _capture_telemetry == []
