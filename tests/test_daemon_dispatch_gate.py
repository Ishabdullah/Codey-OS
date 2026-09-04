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

import pytest

import core.daemon as daemon_mod
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


def test_allowed_dispatch_claims_and_executes_direct_task(tmp_path):
    d = _bare_daemon(tmp_path / "state.db")
    task_id = d.state.add_task("do something")

    with patch.object(daemon_mod.Daemon, "_check_dispatch_gate", return_value=ALLOWED):
        _run(d._process_planner_tasks())

    task = d.state.get_task(task_id)
    assert task["status"] == "done"
    assert task["result"] == "executed result"
    d.executor._execute_task.assert_awaited_once_with("do something")


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
    d.executor._execute_task.assert_awaited_once_with("build a thing")
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
    d.executor._execute_task.assert_awaited_once_with("build a thing")
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
