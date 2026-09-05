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
        import threading

        import core.agent as agent_mod

        # [NEW-345] Mirrors run_agent()'s own top-of-call
        # _reset_run_stats(threading.get_ident()) bucket-keying so
        # _execute_task()'s thread-id lookup in its finally block finds
        # this call's own bucket, exactly like a real run_agent() call
        # running on this same (executor) worker thread would.
        bucket = agent_mod._reset_run_stats(threading.get_ident())
        bucket["step_count"] = 3
        bucket["max_steps"] = 20
        bucket["hit_max_steps"] = False
        bucket["tools_called"] = {"write_file": 2, "shell": 1}
        bucket["auto_retries"] = 1
        bucket["escalated"] = False
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
    """[NEW-345] Rewritten: the old premise here ("set stale stats on the
    single shared dict from the main thread, assert the next task doesn't
    see them") is structurally impossible under thread-identity keying --
    the main/event-loop thread that calls _execute_task() never has its
    own run_agent() bucket in the first place (only a worker thread that
    actually executed run_agent() does). The real invariant to assert
    now: when the executor callable never even started running (an
    exception fires before run_in_executor() dispatch, so
    `_worker_thread_id` stays empty), _execute_task() must report an
    honest empty stats dict -- never some *other*, unrelated thread's
    still-populated leftover bucket (e.g. an orphaned, still-running
    call from an earlier timed-out task)."""
    import core.agent as agent_mod

    # Simulate an orphaned earlier call's still-populated bucket, keyed by
    # some OS thread id that is guaranteed not to be reused by this test's
    # own dispatch (this call never reaches the executor at all, so no
    # worker thread is even spawned for it).
    _orphaned_thread_id = 999_999_999
    agent_mod._RUN_STATS_BY_THREAD[_orphaned_thread_id] = {
        "_seq": 12345,
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
    # None of the orphaned thread's counters (step_count=99, tools_called
    # with shell=5, etc.) leaked into this task's record -- they are
    # absent entirely, not a guessed/stale value.
    assert "step_count" not in f
    assert "tools_called" not in f
    assert "retries" not in f
    assert f["terminal_status"] == "failed"

    # The orphaned bucket itself is untouched -- this codepath never read
    # or popped a thread id other than its own (nonexistent) worker's.
    assert agent_mod._RUN_STATS_BY_THREAD.get(_orphaned_thread_id, {}).get(
        "step_count"
    ) == 99
    del agent_mod._RUN_STATS_BY_THREAD[_orphaned_thread_id]


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
        import threading

        import core.agent as agent_mod

        bucket = agent_mod._reset_run_stats(threading.get_ident())
        bucket["step_count"] = 4
        bucket["max_steps"] = 20
        bucket["hit_max_steps"] = False
        bucket["tools_called"] = {"patch_file": 2}
        bucket["auto_retries"] = 2
        bucket["escalated"] = True
        bucket["escalation_reason"] = "patch_failure"
        bucket["escalation_outcome"] = None
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


def test_orphaned_thread_never_corrupts_concurrent_tasks_stats(
    executor, monkeypatch, _capture_telemetry
):
    """[NEW-345] The load-bearing regression test for the fix itself: a
    run_agent() call whose awaiting run_in_executor() future is
    cancelled/timed out is NOT killed -- Python's executor has no
    mechanism to interrupt a running worker thread, so it keeps executing
    in the background ("orphaned"). If a second, freshly-dispatched task
    then runs concurrently (or after) on a *different* worker thread, the
    orphaned thread's still-in-flight writes must never corrupt the new
    task's stats. Pure threading.Event synchronization, no model load
    involved -- safe under CLAUDE.md rule 2 without any `free -h`
    precondition."""
    import threading

    import core.agent as agent_mod

    a_started = threading.Event()
    a_release = threading.Event()
    a_late_write_done = threading.Event()
    b_started = threading.Event()
    b_may_finish = threading.Event()
    thread_ids: dict = {}

    def fake_run_agent(user_message, history, **kwargs):
        tid = threading.get_ident()
        if user_message == "TASK_A":
            thread_ids["A"] = tid
            bucket = agent_mod._reset_run_stats(tid)
            bucket["step_count"] = 1
            bucket["tools_called"] = {"before_release": 1}
            a_started.set()
            # Bounded wait -- never hang the suite even if `a_release` is
            # somehow never set (test bug elsewhere).
            a_release.wait(timeout=5)
            # The orphaned call's late write. Deliberately timed (via the
            # b_started/b_may_finish gating below) to land *while* B's own
            # bucket is live -- reset and written, but not yet read -- the
            # exact interleaving that would corrupt a single shared dict
            # under the pre-fix design. Written through the same
            # thread_id-keyed helper run_agent() itself uses, not the
            # direct `bucket` reference, so this exercises the real
            # write path (core.agent._set_run_stat / _incr_run_stat),
            # not just a local Python object mutation.
            agent_mod._set_run_stat(tid, "step_count", 999)
            agent_mod._incr_run_stat_tool(tid, "after_release")
            a_late_write_done.set()
            return "A done", history
        else:
            thread_ids["B"] = tid
            bucket = agent_mod._reset_run_stats(tid)
            bucket["step_count"] = 2
            bucket["tools_called"] = {"b_tool": 1}
            b_started.set()
            # Held open so A's late write (gated to fire only after this)
            # has a real window to land while B's bucket is still
            # unread -- see the comment in the TASK_A branch above.
            b_may_finish.wait(timeout=5)
            return "B done", history

    monkeypatch.setattr("core.agent.run_agent", fake_run_agent, raising=False)

    async def _run():
        task_a = asyncio.ensure_future(
            executor._execute_task(
                "TASK_A", task_id=1, task_type="direct", needs_planning=False
            )
        )
        # Wait (off the event loop thread, so we don't block it) until A's
        # fake run_agent has actually started running on its worker
        # thread, so the timeout below reliably lands mid-execution.
        await asyncio.get_event_loop().run_in_executor(None, a_started.wait, 5)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(task_a, timeout=0.01)
        # A's worker thread is now orphaned -- still running, blocked on
        # `a_release` -- even though the awaiting coroutine above raised.

        task_b = asyncio.ensure_future(
            executor._execute_task(
                "TASK_B", task_id=2, task_type="direct", needs_planning=False
            )
        )
        # Wait until B has reset and written its own bucket, then hold it
        # open (b_may_finish) before letting A's late write fire, so the
        # late write genuinely lands between B's reset and B's read.
        await asyncio.get_event_loop().run_in_executor(None, b_started.wait, 5)
        assert "A" in thread_ids and "B" in thread_ids
        assert thread_ids["A"] != thread_ids["B"]

        a_release.set()
        await asyncio.get_event_loop().run_in_executor(
            None, a_late_write_done.wait, 5
        )

        # Now let B finish and read its own (still-uncorrupted) bucket.
        b_may_finish.set()
        result_b = await task_b
        assert result_b == "B done"

        finished = _records_by_event_type(_capture_telemetry, "task_finished")
        b_records = [r for r in finished if r["body"]["task_id"] == 2]
        assert len(b_records) == 1
        b_body = b_records[0]["body"]
        # B's own counters survived A's late, concurrent, differently-
        # thread-id-keyed write untouched -- not A's step_count=999 /
        # "after_release" tool.
        assert b_body["step_count"] == 2
        assert b_body["tools_called"] == {"b_tool": 1}

        # B's bucket was popped on read (get_last_run_stats' pop-on-read
        # contract) and is not left behind in the backing store.
        assert thread_ids["B"] not in agent_mod._RUN_STATS_BY_THREAD

        # A's own emitted record, meanwhile, genuinely reflects whatever
        # partial counters existed at the moment its awaiting coroutine
        # was cancelled (its finally block runs and reads/pops A's bucket
        # immediately on cancellation -- well before A's worker thread is
        # released to do its late write). This is expected, pre-existing
        # behaviour for any cancelled/timed-out task, not something this
        # fix changes -- pinned here so a future change can't silently
        # alter it.
        a_records = [r for r in finished if r["body"]["task_id"] == 1]
        assert len(a_records) == 1
        a_body = a_records[0]["body"]
        assert a_body["terminal_status"] == "cancelled"
        assert a_body["step_count"] == 1
        assert a_body["tools_called"] == {"before_release": 1}

    try:
        asyncio.run(_run())
    finally:
        # A's task-level telemetry record was already emitted (as
        # "cancelled", with whatever partial counters existed at
        # cancellation time) before its worker thread's late write
        # landed -- the fix does not, and should not, retroactively
        # re-emit telemetry for an orphaned call. A's late write went
        # through _set_run_stat/_incr_run_stat_tool, which recreate a
        # bucket for `tid` via setdefault if it was already popped --
        # exactly the KeyError-avoidance behaviour this fix depends on.
        # Clean up whatever bucket A left behind so it doesn't leak into
        # a later test.
        agent_mod._RUN_STATS_BY_THREAD.pop(thread_ids.get("A"), None)


# ── NEW-357: wait_for()-timeout corrective task_finished emission ───────────
#
# The daemon-side guard (`isinstance(exc.__cause__, asyncio.CancelledError)`)
# and its call site live in core/daemon.py (out of this module's scope), but
# the two asyncio-mechanics proofs below (#1/#2) and the
# emit_task_timeout_correction() unit tests (#5/#6) don't need a real Daemon
# instance -- they exercise the underlying asyncio ordering guarantee itself
# and this module's own new public function directly. See
# tests/test_daemon_dispatch_gate.py for the integration tests that drive
# the real dispatch sites end-to-end (#3/#4), and its
# test_socket_timeout_from_execute_task_does_not_trigger_correction for the
# guard exercised through the real daemon.py call site.


def test_wait_for_timeout_unwinds_inner_before_caller_sees_timeouterror():
    """Ordering proof, independent of any Codey-OS code: guards against a
    future Python version changing asyncio.wait_for()'s cancellation
    ordering out from under the NEW-357 fix's core assumption -- that the
    inner coroutine's own CancelledError handler runs to completion BEFORE
    the caller's wait_for() call ever sees a TimeoutError."""
    order = []

    async def inner():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            order.append("inner_cancelled_handler")
            raise

    async def caller():
        try:
            await asyncio.wait_for(inner(), timeout=0.05)
        except asyncio.TimeoutError as exc:
            order.append("caller_timeout_handler")
            assert isinstance(exc.__cause__, asyncio.CancelledError)

    asyncio.run(caller())
    assert order == ["inner_cancelled_handler", "caller_timeout_handler"]


def test_external_cancel_does_not_convert_to_timeouterror():
    """A cancellation NOT caused by wait_for()'s own timeout firing (an
    external task.cancel() under a long wait_for that never itself times
    out) must propagate as CancelledError, never get converted to
    TimeoutError -- the guard's premise depends on this distinction
    actually holding."""

    async def inner():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            raise

    async def dispatch():
        await asyncio.wait_for(inner(), timeout=5)  # long -- won't fire

    async def _run():
        t = asyncio.ensure_future(dispatch())
        await asyncio.sleep(0.05)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t

    asyncio.run(_run())


def test_socket_timeout_has_no_cancelled_cause(monkeypatch):
    """Socket-timeout guard, isolated to the exception-shape claim itself:
    a bare `TimeoutError()` raised directly out of an awaited coroutine
    (simulating a real HTTP/socket timeout inside run_agent(), which
    `asyncio.TimeoutError is TimeoutError` makes indistinguishable by class
    alone) propagates through `asyncio.wait_for()` with no `__cause__`
    chain to a CancelledError -- so `core/daemon.py`'s
    `isinstance(exc.__cause__, asyncio.CancelledError)` guard correctly
    evaluates False for it. The full integration proof that this actually
    suppresses `emit_task_timeout_correction` at the real dispatch site is
    tests/test_daemon_dispatch_gate.py's
    test_socket_timeout_from_execute_task_does_not_trigger_correction."""

    async def inner():
        raise TimeoutError("socket timed out")

    async def caller():
        with pytest.raises(asyncio.TimeoutError) as exc_info:
            await asyncio.wait_for(inner(), timeout=30)
        assert exc_info.value.__cause__ is None

    asyncio.run(caller())


def test_emit_task_timeout_correction_records_timeout_status(monkeypatch, _capture_telemetry):
    from core.task_executor import emit_task_timeout_correction

    emit_task_timeout_correction(
        task_id=55,
        task_type="direct",
        needs_planning=True,
        duration_ms=1234.5,
        timeout_sec=1800,
    )

    finished = _records_by_event_type(_capture_telemetry, "task_finished")
    assert len(finished) == 1
    f = finished[0]["body"]
    assert f["task_id"] == 55
    assert f["task_type"] == "direct"
    assert f["needs_planning"] is True
    assert f["terminal_status"] == "timeout"
    assert f["duration_ms"] == 1234.5
    assert f["timeout_sec"] == 1800
    assert "error_class" not in f
    # Run-stats-derived fields are deliberately never re-queried by this
    # function -- see its own docstring for why a wrong value would be
    # worse than an honest null here.
    assert "step_count" not in f
    assert "tools_called" not in f
    assert "retries" not in f


def test_emit_task_timeout_correction_never_raises(monkeypatch):
    """Standing never-crash-the-host contract every telemetry emitter in
    this codebase follows: a failure inside the emitter itself (here,
    telemetry.recorders.record_task_finished raising) must never propagate
    out and disrupt the caller's own control flow (fail_task()/dispatch)."""
    from core.task_executor import emit_task_timeout_correction
    from telemetry import recorders, store

    monkeypatch.setattr(store, "TELEMETRY_ENABLED", True)

    def _boom(**kwargs):
        raise RuntimeError("telemetry backend exploded")

    monkeypatch.setattr(recorders, "record_task_finished", _boom)

    # Must not raise.
    emit_task_timeout_correction(
        task_id=1, task_type="direct", needs_planning=False,
        duration_ms=10.0, timeout_sec=1800,
    )


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
