"""
core/daemon.py's `Daemon._process_planner_tasks()` dispatch-gate wiring —
TODO.md 4.1 sub-task C (WORK_QUEUE.md Track 3 item 2).

Two things are covered here, independent of `can_dispatch_task()`'s own
five-check logic (already covered by tests/test_resource_gate.py's synthetic
ResourceSnapshot tests):

1. The claim-order regression test: `_check_dispatch_gate()` is consulted
   BEFORE `state.try_claim_task()`. A refused dispatch decision must leave a
   queued task `pending` (never `running`) — claiming first and gating after
   would strand a refused task with no executor ever picking it back up.
2. The pull-side planning step for a `needs_planning=1` direct-command task:
   on >=2 planned steps, the raw row is retired (`done`) and the enriched
   multi-step plan is queued via `planner.add_tasks()`, without executing
   anything that tick; on <=1 step/unavailable, `needs_planning` is cleared
   and the raw prompt is executed directly, as today's single-task path
   already does.

`Daemon._check_dispatch_gate()` itself is patched directly in every test
here (rather than exercised through real `get_resource_snapshot()`/
`is_interactive_session_active()` calls) — this file tests the daemon's
dispatch-loop *wiring* around that decision, not the decision logic itself,
and must not touch real system state (meminfo/thermal/battery) per this
project's test-isolation conventions (NEW-1) and CLAUDE.md rule 2.

No real llama-server subprocess is spawned anywhere in this file — the
executor is a MagicMock/AsyncMock, and the planner is a MagicMock standing
in for core/planner_v2.py's Planner (whose own get_next_task()/add_tasks()
are exercised by simple return-value/call assertions here, not re-tested).
A real `core.state.StateStore` backed by a tmp-path SQLite file is used so
task-row status transitions are asserted against real schema/queries rather
than a hand-rolled fake.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


import core.daemon as daemon_mod
import core.planner_v2 as planner_v2_mod
from core.resource_gate import DispatchDecision
from core.state import StateStore


def _bare_daemon(db_path):
    """A Daemon instance with none of __init__'s side effects run, wired to
    a real (tmp-path) StateStore and mock planner/executor/config."""
    d = daemon_mod.Daemon.__new__(daemon_mod.Daemon)
    d.state = StateStore(db_path=db_path)
    d.planner = MagicMock()
    d.planner.get_next_task.return_value = None  # no in-memory planner tasks
    d.planner._tasks = {}
    d.executor = MagicMock()
    d.executor._execute_task = AsyncMock(return_value="executed result")
    d._config = MagicMock()
    d._config.get.return_value = 1800
    # T8a telemetry state — __init__ normally seeds these; _bare_daemon
    # bypasses __init__ entirely, and _track_dispatch_refusal()/
    # _resolve_deferral_if_any() (both real, unmocked, on the
    # _process_planner_tasks() path this file exercises) touch
    # self._deferral_state unconditionally.
    d._deferral_state = {}
    d._gate_dedup = {}
    d._interactive_active_last = None
    d._interactive_state_since_mono = 0.0
    return d


def _run(coro):
    return asyncio.run(coro)


ALLOWED_DECISION = DispatchDecision(allowed=True, reason="within resource limits")
ALLOWED = (ALLOWED_DECISION, False)


def _refused(reason="refused for test", interactive_active=False):
    return (DispatchDecision(allowed=False, reason=reason), interactive_active)


# ── Claim-order regression test ──────────────────────────────────────────────


def test_refused_dispatch_leaves_direct_task_pending(tmp_path):
    d = _bare_daemon(tmp_path / "state.db")
    task_id = d.state.add_task("do something")

    with patch.object(daemon_mod.Daemon, "_check_dispatch_gate", return_value=_refused()):
        _run(d._process_planner_tasks())

    task = d.state.get_task(task_id)
    assert task["status"] == "pending"
    d.executor._execute_task.assert_not_called()


def test_refused_dispatch_leaves_planner_task_pending(tmp_path):
    """Mirror of the direct-task claim-order test above, for the OTHER
    try_claim_task() call site (the planner-task branch) — the spec named
    both branches as the hard correctness requirement, so both need their
    own regression coverage, not just whichever branch happens to run
    first."""
    d = _bare_daemon(tmp_path / "state.db")
    task_id = d.state.add_task("planner-tracked task")

    planner_task = MagicMock()
    planner_task.id = task_id
    planner_task.description = "planner-tracked task"
    d.planner.get_next_task.return_value = planner_task

    with patch.object(daemon_mod.Daemon, "_check_dispatch_gate", return_value=_refused()):
        _run(d._process_planner_tasks())

    task = d.state.get_task(task_id)
    assert task["status"] == "pending"
    d.executor._execute_task.assert_not_called()
    d.planner.start_task.assert_not_called()


def test_allowed_dispatch_claims_and_executes_planner_task(tmp_path):
    """T8b: the planner-task branch (Site 1) passes real
    task_id/task_type/needs_planning into _execute_task(), activating T7's
    category-E telemetry for this branch — task_type="planner",
    needs_planning=False (hardcoded; see T8b handoff)."""
    d = _bare_daemon(tmp_path / "state.db")
    task_id = d.state.add_task("planner-tracked task")

    planner_task = MagicMock()
    planner_task.id = task_id
    planner_task.description = "planner-tracked task"
    d.planner.get_next_task.return_value = planner_task

    with patch.object(daemon_mod.Daemon, "_check_dispatch_gate", return_value=ALLOWED):
        _run(d._process_planner_tasks())

    d.executor._execute_task.assert_awaited_once_with(
        "planner-tracked task", task_id=task_id, task_type="planner", needs_planning=False
    )
    d.planner.complete_task.assert_called_once_with(task_id, "executed result")


def test_allowed_dispatch_claims_and_executes_direct_task(tmp_path):
    d = _bare_daemon(tmp_path / "state.db")
    task_id = d.state.add_task("do something")

    with patch.object(daemon_mod.Daemon, "_check_dispatch_gate", return_value=ALLOWED):
        _run(d._process_planner_tasks())

    task = d.state.get_task(task_id)
    assert task["status"] == "done"
    assert task["result"] == "executed result"
    d.executor._execute_task.assert_awaited_once_with(
        "do something", task_id=task_id, task_type="direct", needs_planning=False
    )


# ── needs_planning pull-side planning step ───────────────────────────────────


def test_needs_planning_task_expands_into_multistep_plan(tmp_path):
    d = _bare_daemon(tmp_path / "state.db")
    task_id = d.state.add_task("build a thing", needs_planning=1)
    d.planner.add_tasks.return_value = [101, 102]

    with patch.object(daemon_mod.Daemon, "_check_dispatch_gate", return_value=ALLOWED), patch.object(
        daemon_mod.Daemon, "_plan_claimed_task", new=AsyncMock(return_value=["step one", "step two"])
    ):
        _run(d._process_planner_tasks())

    # The raw row is retired, not executed directly.
    d.executor._execute_task.assert_not_called()
    d.planner.add_tasks.assert_called_once()
    (enriched_arg,), _ = d.planner.add_tasks.call_args
    assert len(enriched_arg) == 2

    task = d.state.get_task(task_id)
    assert task["status"] == "done"
    assert task["needs_planning"] == 0


def test_needs_planning_task_falls_back_to_single_task_on_one_step(tmp_path):
    d = _bare_daemon(tmp_path / "state.db")
    task_id = d.state.add_task("build a thing", needs_planning=1)

    with patch.object(daemon_mod.Daemon, "_check_dispatch_gate", return_value=ALLOWED), patch.object(
        daemon_mod.Daemon, "_plan_claimed_task", new=AsyncMock(return_value=["only one step"])
    ):
        _run(d._process_planner_tasks())

    d.planner.add_tasks.assert_not_called()
    # needs_planning=True here reflects db_task's pre-clear snapshot (fetched
    # before clear_needs_planning() ran) — the honest historical value, not
    # the post-clear 0 now in SQLite. See T8b handoff.
    d.executor._execute_task.assert_awaited_once_with(
        "build a thing", task_id=task_id, task_type="direct", needs_planning=True
    )
    task = d.state.get_task(task_id)
    assert task["status"] == "done"
    assert task["needs_planning"] == 0


def test_needs_planning_task_falls_back_to_single_task_when_planner_unavailable(tmp_path):
    d = _bare_daemon(tmp_path / "state.db")
    task_id = d.state.add_task("build a thing", needs_planning=1)

    with patch.object(daemon_mod.Daemon, "_check_dispatch_gate", return_value=ALLOWED), patch.object(
        daemon_mod.Daemon, "_plan_claimed_task", new=AsyncMock(return_value=None)
    ):
        _run(d._process_planner_tasks())

    d.planner.add_tasks.assert_not_called()
    d.executor._execute_task.assert_awaited_once_with(
        "build a thing", task_id=task_id, task_type="direct", needs_planning=True
    )
    task = d.state.get_task(task_id)
    assert task["status"] == "done"
    assert task["needs_planning"] == 0


def test_refused_dispatch_leaves_needs_planning_task_pending_and_unplanned(tmp_path):
    d = _bare_daemon(tmp_path / "state.db")
    task_id = d.state.add_task("build a thing", needs_planning=1)

    with patch.object(daemon_mod.Daemon, "_check_dispatch_gate", return_value=_refused()), patch.object(
        daemon_mod.Daemon, "_plan_claimed_task", new=AsyncMock(return_value=["step one", "step two"])
    ) as plan_mock:
        _run(d._process_planner_tasks())

    plan_mock.assert_not_called()
    task = d.state.get_task(task_id)
    assert task["status"] == "pending"
    assert task["needs_planning"] == 1


# ── NEW-356: Site 1 (planner-task branch) must re-read needs_planning ───────
#
# Planner.__init__()'s _load_tasks() unconditionally rehydrates every
# pending/running task_queue row into self._tasks with no filter on origin
# or needs_planning (core/planner_v2.py). A needs_planning=1 direct-command
# row that is still pending at the exact moment of a daemon restart can
# therefore be dispatched via Site 1 (the planner-task branch above) instead
# of Site 2 (the direct-task branch), which reads the real value. These
# tests exercise a REAL Planner/StateStore pair (not a mocked planner) so
# the actual rehydration mechanism is what's under test, not an assumption
# about it.


def test_rehydrated_direct_task_dispatched_via_site1_reports_real_needs_planning(tmp_path, monkeypatch):
    db_path = tmp_path / "state.db"
    store = StateStore(db_path=db_path)
    # Created directly via StateStore.add_task(), never Planner.add_task()/
    # add_tasks() -- simulates the exact NEW-356 scenario: a needs_planning=1
    # direct-command row still pending at the instant of a daemon restart.
    task_id = store.add_task("build a thing", needs_planning=1)

    monkeypatch.setattr(planner_v2_mod, "get_state_store", lambda: store)
    real_planner = planner_v2_mod.Planner()
    # Confirms the rehydration mechanism itself, not just the DB read below.
    assert task_id in real_planner._tasks

    d = daemon_mod.Daemon.__new__(daemon_mod.Daemon)
    d.state = store
    d.planner = real_planner
    d.executor = MagicMock()
    d.executor._execute_task = AsyncMock(return_value="executed result")
    d._config = MagicMock()
    d._config.get.return_value = 1800
    d._deferral_state = {}
    d._gate_dedup = {}
    d._interactive_active_last = None
    d._interactive_state_since_mono = 0.0

    with patch.object(daemon_mod.Daemon, "_check_dispatch_gate", return_value=ALLOWED):
        _run(d._process_planner_tasks())

    d.executor._execute_task.assert_awaited_once_with(
        "build a thing", task_id=task_id, task_type="planner", needs_planning=True
    )


def test_normal_planner_task_still_reports_needs_planning_false(tmp_path, monkeypatch):
    """Regression: a task added the normal way (Planner.add_task(), never
    setting needs_planning -> defaults to 0/False via StateStore.add_task())
    still results in needs_planning=False reaching _execute_task()."""
    db_path = tmp_path / "state.db"
    store = StateStore(db_path=db_path)

    monkeypatch.setattr(planner_v2_mod, "get_state_store", lambda: store)
    real_planner = planner_v2_mod.Planner()
    task_id = real_planner.add_task("planner-tracked task")
    assert task_id in real_planner._tasks

    d = daemon_mod.Daemon.__new__(daemon_mod.Daemon)
    d.state = store
    d.planner = real_planner
    d.executor = MagicMock()
    d.executor._execute_task = AsyncMock(return_value="executed result")
    d._config = MagicMock()
    d._config.get.return_value = 1800
    d._deferral_state = {}
    d._gate_dedup = {}
    d._interactive_active_last = None
    d._interactive_state_since_mono = 0.0

    with patch.object(daemon_mod.Daemon, "_check_dispatch_gate", return_value=ALLOWED):
        _run(d._process_planner_tasks())

    d.executor._execute_task.assert_awaited_once_with(
        "planner-tracked task", task_id=task_id, task_type="planner", needs_planning=False
    )


# ── NEW-357: wait_for()-timeout corrective task_finished emission ───────────
#
# These drive `_process_planner_tasks()` end-to-end with a REAL
# `asyncio.wait_for()` and a genuinely slow `_execute_task()` mock (an
# `async def` side_effect that sleeps, not a hardcoded flag), so the
# wait_for-cancels-the-inner-await-then-raises-TimeoutError sequence is the
# real asyncio mechanism, not a simulated shortcut. Only
# `core.daemon.emit_task_timeout_correction` is patched here (asserting it
# is called/not called, with what arguments) — the two-record *shape* this
# produces end-to-end (via the real, unmocked TaskExecutor) is covered
# separately below by
# test_two_task_finished_records_emitted_cancelled_then_timeout_site1.


async def _slow_execute_task(*args, **kwargs):
    await asyncio.sleep(5)
    return "should not get here"


def test_timeout_emits_correction_exactly_once_site1_planner_branch(tmp_path):
    d = _bare_daemon(tmp_path / "state.db")
    task_id = d.state.add_task("planner-tracked task")
    d._config.get.return_value = 0.05  # small real timeout

    planner_task = MagicMock()
    planner_task.id = task_id
    planner_task.description = "planner-tracked task"
    d.planner.get_next_task.return_value = planner_task
    d.executor._execute_task = AsyncMock(side_effect=_slow_execute_task)

    with patch.object(
        daemon_mod.Daemon, "_check_dispatch_gate", return_value=ALLOWED
    ), patch.object(daemon_mod, "emit_task_timeout_correction") as mock_correction:
        _run(d._process_planner_tasks())

    d.planner.fail_task.assert_called_once()
    mock_correction.assert_called_once()
    call_kwargs = mock_correction.call_args.kwargs
    assert call_kwargs["task_id"] == task_id
    assert call_kwargs["task_type"] == "planner"
    assert call_kwargs["needs_planning"] is False
    assert call_kwargs["duration_ms"] > 0
    # int(0.05) == 0 -- not a meaningful zero, just the small real config
    # timeout truncated to an int as the production code does.
    assert call_kwargs["timeout_sec"] == 0


def test_timeout_emits_correction_exactly_once_site2_direct_branch(tmp_path):
    d = _bare_daemon(tmp_path / "state.db")
    task_id = d.state.add_task("do something")
    d._config.get.return_value = 0.05  # small real timeout
    d.executor._execute_task = AsyncMock(side_effect=_slow_execute_task)

    with patch.object(
        daemon_mod.Daemon, "_check_dispatch_gate", return_value=ALLOWED
    ), patch.object(daemon_mod, "emit_task_timeout_correction") as mock_correction:
        _run(d._process_planner_tasks())

    task = d.state.get_task(task_id)
    assert task["status"] == "failed"
    mock_correction.assert_called_once()
    call_kwargs = mock_correction.call_args.kwargs
    assert call_kwargs["task_id"] == task_id
    assert call_kwargs["task_type"] == "direct"
    assert call_kwargs["needs_planning"] is False
    assert call_kwargs["duration_ms"] > 0
    # int(0.05) == 0 -- not a meaningful zero, just the small real config
    # timeout truncated to an int as the production code does.
    assert call_kwargs["timeout_sec"] == 0


def test_two_task_finished_records_emitted_cancelled_then_timeout_site1(
    tmp_path, monkeypatch
):
    """Direct proof of the two-record outcome (real, unmocked TaskExecutor
    driving the actual _execute_task() cancellation/finally path, real
    wait_for() timeout at the daemon dispatch site) -- exactly two
    telemetry.recorders.record_task_finished() calls for the same task_id,
    terminal_status in order ["cancelled", "timeout"]."""
    import time as _time

    from core.daemon_config import DaemonConfig
    from core.task_executor import TaskExecutor
    from telemetry import recorders

    monkeypatch.setattr(recorders.store, "TELEMETRY_ENABLED", True)

    captured = []
    monkeypatch.setattr(recorders, "record_task_finished", lambda **kw: captured.append(kw))

    def fake_run_agent(user_message, history, **kwargs):
        _time.sleep(0.5)
        return "should not get here", history

    monkeypatch.setattr("core.agent.run_agent", fake_run_agent, raising=False)

    d = _bare_daemon(tmp_path / "state.db")
    task_id = d.state.add_task("planner-tracked task")
    config = DaemonConfig()
    monkeypatch.setattr(config, "get", lambda *a, **kw: 0.05)
    d._config = config
    d.executor = TaskExecutor(state=d.state, config=config)

    planner_task = MagicMock()
    planner_task.id = task_id
    planner_task.description = "planner-tracked task"
    d.planner.get_next_task.return_value = planner_task

    with patch.object(daemon_mod.Daemon, "_check_dispatch_gate", return_value=ALLOWED):
        _run(d._process_planner_tasks())

    task_records = [c for c in captured if c["task_id"] == task_id]
    assert len(task_records) == 2
    assert [r["terminal_status"] for r in task_records] == ["cancelled", "timeout"]


def test_socket_timeout_from_execute_task_does_not_trigger_correction(tmp_path):
    """Socket-timeout guard (the most important negative test): a bare
    `TimeoutError()` with no `__cause__` raised out of `_execute_task()`
    itself (simulating a real HTTP/socket timeout inside run_agent(), which
    `asyncio.TimeoutError is TimeoutError` makes indistinguishable by class
    alone) must NOT trigger `emit_task_timeout_correction` -- the daemon's
    `except asyncio.TimeoutError:` handling (fail_task) still fires exactly
    as it does today, but the earlier "failed"/error_class="TimeoutError"
    record _execute_task() already emitted for it remains the only record."""

    async def _raise_bare_timeout(*args, **kwargs):
        raise TimeoutError("socket timed out")

    d = _bare_daemon(tmp_path / "state.db")
    task_id = d.state.add_task("do something")
    d._config.get.return_value = 30  # long enough that wait_for itself never fires
    d.executor._execute_task = AsyncMock(side_effect=_raise_bare_timeout)

    with patch.object(
        daemon_mod.Daemon, "_check_dispatch_gate", return_value=ALLOWED
    ), patch.object(daemon_mod, "emit_task_timeout_correction") as mock_correction:
        _run(d._process_planner_tasks())

    task = d.state.get_task(task_id)
    assert task["status"] == "failed"
    mock_correction.assert_not_called()


def test_correction_emitter_failure_never_blocks_fail_task(tmp_path, monkeypatch):
    """Never-affect-control-flow, exercised through the real dispatch site
    (not just emit_task_timeout_correction() called in isolation, which
    tests/test_task_executor_telemetry.py already covers): the REAL
    emit_task_timeout_correction() is left unpatched here, but the
    telemetry backend it calls into is made to raise. fail_task()/dispatch
    must still complete normally -- this is the exact 'passed review
    twice, broke live' shape CLAUDE.md warns about, so it gets its own
    direct proof rather than relying on code inspection alone."""
    from telemetry import recorders, store

    monkeypatch.setattr(store, "TELEMETRY_ENABLED", True)

    def _boom(**kwargs):
        raise RuntimeError("telemetry backend exploded")

    monkeypatch.setattr(recorders, "record_task_finished", _boom)

    d = _bare_daemon(tmp_path / "state.db")
    task_id = d.state.add_task("do something")
    d._config.get.return_value = 0.05  # small real timeout
    d.executor._execute_task = AsyncMock(side_effect=_slow_execute_task)

    with patch.object(daemon_mod.Daemon, "_check_dispatch_gate", return_value=ALLOWED):
        _run(d._process_planner_tasks())

    task = d.state.get_task(task_id)
    assert task["status"] == "failed"


def test_site1_needs_planning_requery_defensive_none_row(tmp_path):
    """Defensive: if self.state.get_task(planner_task.id) returns None at
    the exact point Site 1 re-queries (e.g. the row was deleted from SQLite
    after already being tracked in self.planner._tasks), the code must
    degrade to needs_planning=False rather than raising AttributeError on
    None.get(...)."""
    d = _bare_daemon(tmp_path / "state.db")
    task_id = d.state.add_task("planner-tracked task")

    planner_task = MagicMock()
    planner_task.id = task_id
    planner_task.description = "planner-tracked task"
    d.planner.get_next_task.return_value = planner_task

    # try_claim_task() (the actual claim) is a raw SQL UPDATE, not a
    # get_task() call, so patching get_task() globally to always return
    # None isolates the re-query's None-handling without breaking the
    # claim step itself.
    with patch.object(daemon_mod.Daemon, "_check_dispatch_gate", return_value=ALLOWED), patch.object(
        StateStore, "get_task", return_value=None
    ):
        _run(d._process_planner_tasks())

    d.executor._execute_task.assert_awaited_once_with(
        "planner-tracked task", task_id=task_id, task_type="planner", needs_planning=False
    )
