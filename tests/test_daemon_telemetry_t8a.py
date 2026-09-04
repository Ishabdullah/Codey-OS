"""
T8a (docs/telemetry_layer_design.md) — categories B, C, D, daemon-side G at
core/daemon.py, plus the `superseded_by_plan` terminal status.

Mirrors tests/test_task_executor_telemetry.py / tests/test_plannd_telemetry.py's
coverage pattern: TELEMETRY_ENABLED forced True within this file (overriding
tests/conftest.py's session-wide False default), telemetry/store.record()
monkeypatched to a capture list so no test touches a real writer thread or
the filesystem, real system state (meminfo/thermal/battery/zram) never
touched directly — every `Daemon` method under test here is exercised on a
bare instance (`Daemon.__new__`, __init__'s side effects never run) wired to
a real tmp-path StateStore, matching tests/test_daemon_dispatch_gate.py's
existing convention for this file (CLAUDE.md rule 2, NEW-1).

Scope: this file does NOT re-test can_dispatch_task()/should_trip_shutdown()/
get_resource_snapshot()'s own decision logic (already covered by
tests/test_resource_gate.py) — only the daemon-side telemetry wiring around
them.
"""
from __future__ import annotations

import os
import time
from unittest.mock import MagicMock

import pytest

import core.daemon as daemon_mod
from core.resource_gate import DispatchDecision, TripDecision
from core.state import StateStore
from telemetry import envelope, recorders


@pytest.fixture(autouse=True)
def _capture_telemetry(monkeypatch):
    captured = []

    def fake_record(rec):
        captured.append(rec)

    monkeypatch.setattr(recorders.store, "record", fake_record)
    monkeypatch.setattr(recorders.store, "get_run_id", lambda: "daemon-t8a-telemetry-test")
    monkeypatch.setattr(recorders.store, "TELEMETRY_ENABLED", True)
    envelope.reset_seq()
    return captured


def _records_by_event_type(captured, event_type):
    return [r for r in captured if r.get("event_type") == event_type]


def _bare_daemon(db_path=None):
    """A Daemon instance with none of __init__'s side effects run — mirrors
    tests/test_daemon_dispatch_gate.py's own `_bare_daemon()` helper."""
    d = daemon_mod.Daemon.__new__(daemon_mod.Daemon)
    if db_path is not None:
        d.state = StateStore(db_path=db_path)
    d._gate_dedup = {}
    d._interactive_active_last = None
    d._interactive_state_since_mono = time.monotonic()
    d._deferral_state = {}
    d._dispatch_battery_cache_ts = 0.0
    d._dispatch_battery_cache_value = (None, False)
    return d


# ── B. Gate-decision dedup ───────────────────────────────────────────────────


def test_gate_dedup_transitions(monkeypatch, _capture_telemetry):
    d = _bare_daemon()
    allowed = DispatchDecision(allowed=True, reason="within resource limits")
    refused = DispatchDecision(allowed=False, reason="interactive TUI session active — deferring background dispatch")

    # 1. First evaluation for this call_site: always an immediate emission.
    d._emit_gate_telemetry_deduped(event_type="can_dispatch_task", decision=allowed, call_site="site.a")
    records = _records_by_event_type(_capture_telemetry, "can_dispatch_task")
    assert len(records) == 1
    assert records[0]["body"]["repeat_count"] == 1
    # dedup_window_ms=None on a state-change record is pruned from the body
    # entirely (recorders._emit()'s "not applicable yet" contract), not
    # kept as an unreasoned null.
    assert "dedup_window_ms" not in records[0]["body"]

    # 2. Same key repeated -> suppressed (no new record) until 60s elapse.
    d._emit_gate_telemetry_deduped(event_type="can_dispatch_task", decision=allowed, call_site="site.a")
    d._emit_gate_telemetry_deduped(event_type="can_dispatch_task", decision=allowed, call_site="site.a")
    records = _records_by_event_type(_capture_telemetry, "can_dispatch_task")
    assert len(records) == 1  # still just the first

    # 3. Key change (allowed -> refused) re-emits immediately, even though
    #    < 60s has elapsed since the first window opened.
    d._emit_gate_telemetry_deduped(event_type="can_dispatch_task", decision=refused, call_site="site.a")
    records = _records_by_event_type(_capture_telemetry, "can_dispatch_task")
    assert len(records) == 2
    assert records[1]["body"]["decision"]["reason"] == refused.reason
    assert records[1]["body"]["repeat_count"] == 1
    assert "dedup_window_ms" not in records[1]["body"]

    # 4. One more suppressed evaluation with the same (post-key-change) key,
    #    then simulate 60s elapsed -> heartbeat emission carrying the
    #    collapsed repeat_count/dedup_window_ms. repeat_count must reflect
    #    ONLY the evaluations collapsed into THIS window (the suppressed one
    #    just below + this heartbeat evaluation itself = 2) -- NOT also
    #    re-counting record[1]'s own single evaluation, which was already
    #    fully accounted for by record[1]'s own repeat_count=1. Summing every
    #    emitted repeat_count for this call_site is a LOWER BOUND on the true
    #    evaluation count, not exact (§2.B point 3 caveat): 1 (record 0) + 1
    #    (record 1) + 2 (record 2) = 4, but 6 real calls to
    #    _emit_gate_telemetry_deduped have been made in this test so far --
    #    the 2 suppressed "allowed" evaluations at step 2 were discarded,
    #    unflushed, when the key changed to "refused" at step 3.
    d._emit_gate_telemetry_deduped(event_type="can_dispatch_task", decision=refused, call_site="site.a")
    window = d._gate_dedup["site.a"]
    window["window_start_mono"] = time.monotonic() - 61.0
    d._emit_gate_telemetry_deduped(event_type="can_dispatch_task", decision=refused, call_site="site.a")
    records = _records_by_event_type(_capture_telemetry, "can_dispatch_task")
    assert len(records) == 3
    assert records[2]["body"]["repeat_count"] == 2
    assert records[2]["body"]["dedup_window_ms"] >= 60_000.0


def test_gate_dedup_swap_flag_only_change_is_a_new_key(_capture_telemetry):
    """A DispatchDecision with the same (allowed, reason) but a different
    dispatched_via_swap must be treated as a distinct dedup key -- the
    swap-assist path is a materially different fact even when the coarse
    allow/deny outcome and human-readable reason happen to collide."""
    d = _bare_daemon()
    via_ram = DispatchDecision(allowed=True, reason="within resource limits", dispatched_via_swap=False)
    via_swap = DispatchDecision(allowed=True, reason="within resource limits", dispatched_via_swap=True)

    d._emit_gate_telemetry_deduped(event_type="can_dispatch_task", decision=via_ram, call_site="site.b")
    d._emit_gate_telemetry_deduped(event_type="can_dispatch_task", decision=via_swap, call_site="site.b")

    records = _records_by_event_type(_capture_telemetry, "can_dispatch_task")
    assert len(records) == 2
    assert records[0]["body"]["dispatched_via_swap"] is False
    assert records[1]["body"]["dispatched_via_swap"] is True


def test_gate_dedup_trip_decision_uses_should_trip_field(_capture_telemetry):
    """TripDecision has no `allowed` field (only `should_trip`) -- the dedup
    key extraction must fall back to it rather than always reading None."""
    d = _bare_daemon()
    not_tripped = TripDecision(should_trip=False, reason="thermal history nominal")
    d._emit_gate_telemetry_deduped(
        event_type="should_trip_shutdown", decision=not_tripped, call_site="site.c"
    )
    records = _records_by_event_type(_capture_telemetry, "should_trip_shutdown")
    assert len(records) == 1
    assert records[0]["body"]["decision"]["should_trip"] is False

    tripped = TripDecision(should_trip=True, reason="sustained critical temperature")
    d._emit_gate_telemetry_deduped(
        event_type="should_trip_shutdown", decision=tripped, call_site="site.c"
    )
    records = _records_by_event_type(_capture_telemetry, "should_trip_shutdown")
    assert len(records) == 2  # should_trip flipped -> new key -> immediate re-emit


def test_gate_dedup_call_sites_are_independent(_capture_telemetry):
    d = _bare_daemon()
    decision = DispatchDecision(allowed=True, reason="within resource limits")
    d._emit_gate_telemetry_deduped(event_type="can_dispatch_task", decision=decision, call_site="site.x")
    d._emit_gate_telemetry_deduped(event_type="can_dispatch_task", decision=decision, call_site="site.y")
    records = _records_by_event_type(_capture_telemetry, "can_dispatch_task")
    # Each call_site gets its own dedup window -- both are "first
    # evaluation for this call_site" and both emit.
    assert len(records) == 2


# ── C. Device sample honest-null paths ───────────────────────────────────────


def _stub_thermal_status(throttled=False, total_inference_sec=12.5):
    return {
        "total_inference_sec": total_inference_sec,
        "total_inference_min": total_inference_sec / 60,
        "current_threads": 4,
        "original_threads": 4,
        "warnings_issued": 0,
        "thread_reductions": 0,
        "throttled": throttled,
    }


def test_device_sample_all_signals_present(monkeypatch, _capture_telemetry):
    from core.resource_gate import ResourceSnapshot

    d = _bare_daemon()
    snapshot = ResourceSnapshot(
        cpu_percent=None,  # always null on this device regardless of other signals
        ram_headroom_bytes=1_000_000,
        ram_total_bytes=8_000_000,
        temperature_c=45.0,
        queue_pending=0,
        queue_running=0,
        battery_percent=80,
        battery_charging=True,
        timestamp=time.time(),
        swap_total_bytes=2_000_000,
        swap_free_bytes=1_500_000,
    )
    monkeypatch.setattr(daemon_mod, "warning", lambda *a, **kw: None)
    monkeypatch.setattr("core.resource_gate.read_meminfo", lambda: {"MemFree": 111, "MemAvailable": 222})
    monkeypatch.setattr("core.resource_gate.get_resource_snapshot", lambda **kw: snapshot)
    monkeypatch.setattr(
        "core.resource_gate.read_zram_stats",
        lambda: {"orig_data_size_bytes": 400, "compr_data_size_bytes": 100, "mem_used_total_bytes": 120},
    )
    monkeypatch.setattr("core.resource_gate.compute_zram_compression_ratio", lambda stats: 4.0)
    monkeypatch.setattr("core.thermal.get_thermal_status", lambda: _stub_thermal_status(throttled=False))
    monkeypatch.setattr("core.thermal.is_inference_active", lambda: False)

    d._record_daemon_telemetry_device_sample()

    records = _records_by_event_type(_capture_telemetry, "sample")
    assert len(records) == 1
    body = records[0]["body"]
    assert body["mem_free_bytes"] == 111
    assert body["mem_available_bytes"] == 222
    assert body["zram_compression_ratio"] == 4.0
    assert body["zram_orig_data_bytes"] == 400
    assert body["zram_compr_data_bytes"] == 100
    assert body["throttle_level"] == "normal"
    # cpu_percent is always null on this device -- honest null with reason,
    # not silently pruned.
    assert records[0]["nulls"]["body.cpu_percent"] == "proc_stat_permission_denied"
    assert "body.temperature_c" not in records[0]["nulls"]
    assert "body.battery_percent" not in records[0]["nulls"]


def test_device_sample_honest_nulls_on_read_failures(monkeypatch, _capture_telemetry):
    from core.resource_gate import ResourceSnapshot

    d = _bare_daemon()
    snapshot = ResourceSnapshot(
        cpu_percent=None,
        ram_headroom_bytes=1_000_000,
        ram_total_bytes=8_000_000,
        temperature_c=None,  # thermal read failed
        queue_pending=0,
        queue_running=0,
        battery_percent=None,  # battery read failed
        battery_charging=False,
        timestamp=time.time(),
        swap_total_bytes=0,
        swap_free_bytes=0,
    )
    monkeypatch.setattr("core.resource_gate.read_meminfo", lambda: {"MemFree": 0, "MemAvailable": 0})
    monkeypatch.setattr("core.resource_gate.get_resource_snapshot", lambda **kw: snapshot)
    monkeypatch.setattr("core.resource_gate.read_zram_stats", lambda: None)  # unavailable
    monkeypatch.setattr("core.resource_gate.compute_zram_compression_ratio", lambda stats: None)
    monkeypatch.setattr("core.thermal.get_thermal_status", lambda: _stub_thermal_status(throttled=True))
    monkeypatch.setattr("core.thermal.is_inference_active", lambda: True)

    d._record_daemon_telemetry_device_sample()

    records = _records_by_event_type(_capture_telemetry, "sample")
    assert len(records) == 1
    body = records[0]["body"]
    nulls = records[0]["nulls"]
    assert body["zram_compression_ratio"] is None
    assert body["zram_orig_data_bytes"] is None
    assert body["zram_compr_data_bytes"] is None
    assert nulls["body.cpu_percent"] == "proc_stat_permission_denied"
    assert nulls["body.temperature_c"] == "thermal_zone_unreadable"
    assert nulls["body.battery_percent"] == "battery_read_failed"
    assert nulls["body.zram_compression_ratio"] == "zram_stats_unavailable"
    assert nulls["body.zram_orig_data_bytes"] == "zram_stats_unavailable"
    assert nulls["body.zram_compr_data_bytes"] == "zram_stats_unavailable"
    assert body["throttle_level"] == "throttled"
    assert body["inference_active"] is True


def test_device_sample_disabled_when_telemetry_off(monkeypatch, _capture_telemetry):
    monkeypatch.setattr(recorders.store, "TELEMETRY_ENABLED", False)
    d = _bare_daemon()
    # Deliberately do NOT stub resource_gate/thermal here -- if the kill
    # switch isn't checked first, this would touch real system state
    # (CLAUDE.md rule 2) and likely raise/hang in the test environment.
    d._record_daemon_telemetry_device_sample()
    assert _capture_telemetry == []


def test_device_sample_read_failure_does_not_raise(monkeypatch, _capture_telemetry):
    d = _bare_daemon()
    monkeypatch.setattr(
        "core.resource_gate.read_meminfo", lambda: (_ for _ in ()).throw(OSError("boom"))
    )
    # Must not raise -- best-effort, logged and swallowed.
    d._record_daemon_telemetry_device_sample()
    assert _capture_telemetry == []


# ── D. Deferral-state cap eviction ───────────────────────────────────────────


def test_deferral_state_cap_evicts_oldest(monkeypatch):
    d = _bare_daemon()
    monkeypatch.setattr(recorders.store, "TELEMETRY_ENABLED", False)  # emission not under test here

    fake_now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])

    max_entries = daemon_mod._DEFERRAL_STATE_MAX_ENTRIES
    for i in range(max_entries):
        fake_now[0] += 1.0
        d._track_dispatch_refusal(i, False, "refused for test")

    assert len(d._deferral_state) == max_entries
    assert 0 in d._deferral_state  # oldest (task_id 0) still present

    # One more refusal for a brand-new task_id must evict the oldest
    # (task_id 0, first_refused_mono earliest) to stay within the cap.
    fake_now[0] += 1.0
    d._track_dispatch_refusal(max_entries, False, "refused for test")

    assert len(d._deferral_state) == max_entries
    assert 0 not in d._deferral_state
    assert max_entries in d._deferral_state


def test_deferral_resolved_clears_state_and_reports_ms(monkeypatch, _capture_telemetry):
    d = _bare_daemon()
    fake_now = [2000.0]
    monkeypatch.setattr(time, "monotonic", lambda: fake_now[0])

    d._track_dispatch_refusal(7, True, "interactive TUI session active — deferring background dispatch")
    fake_now[0] += 5.0
    d._track_dispatch_refusal(7, True, "interactive TUI session active — deferring background dispatch")
    fake_now[0] += 10.0

    d._resolve_deferral_if_any(7)

    assert 7 not in d._deferral_state
    finished = _records_by_event_type(_capture_telemetry, "deferral_resolved")
    assert len(finished) == 1
    body = finished[0]["body"]
    assert body["deferral_refusal_count"] == 2
    assert body["deferral_ms"] == pytest.approx(15_000.0, rel=1e-6)


def test_resolve_deferral_no_prior_refusal_is_a_noop(_capture_telemetry):
    d = _bare_daemon()
    d._resolve_deferral_if_any(99)  # never refused
    assert _capture_telemetry == []


def test_dispatch_refused_emits_only_when_interactive_and_first_refusal(_capture_telemetry):
    d = _bare_daemon()
    # Non-interactive refusal (e.g. thermal) -- tracked, but no
    # dispatch_refused_human_present emission (already covered by category B).
    d._track_dispatch_refusal(1, False, "thermal critical")
    assert _records_by_event_type(_capture_telemetry, "dispatch_refused_human_present") == []

    # Interactive refusal -- first refusal for this task_id emits.
    d._track_dispatch_refusal(2, True, "interactive TUI session active — deferring background dispatch")
    records = _records_by_event_type(_capture_telemetry, "dispatch_refused_human_present")
    assert len(records) == 1
    assert records[0]["body"]["refused_task_id"] == 2

    # Second interactive refusal for the SAME task_id -- count tracked, no
    # second emission.
    d._track_dispatch_refusal(2, True, "interactive TUI session active — deferring background dispatch")
    records = _records_by_event_type(_capture_telemetry, "dispatch_refused_human_present")
    assert len(records) == 1
    assert d._deferral_state[2]["refusal_count"] == 2


# ── D. _list_live_tui_session_pids() ─────────────────────────────────────────


def test_list_live_tui_session_pids_missing_dir(tmp_path, monkeypatch):
    d = _bare_daemon()
    missing = tmp_path / "does-not-exist"
    monkeypatch.setattr("utils.config.TUI_SESSIONS_DIR", missing)
    assert d._list_live_tui_session_pids() == []


def test_list_live_tui_session_pids_mixed_liveness(tmp_path, monkeypatch):
    d = _bare_daemon()
    sessions_dir = tmp_path / "tui-sessions"
    sessions_dir.mkdir()

    own_pid = os.getpid()
    (sessions_dir / f"{own_pid}.pid").write_text(str(own_pid))

    # A PID astronomically unlikely to be alive on this system.
    dead_pid = 2_147_483_000
    (sessions_dir / f"{dead_pid}.pid").write_text(str(dead_pid))

    # Malformed entry -- must be skipped, not raise.
    (sessions_dir / "garbage.pid").write_text("not-a-pid")

    # In-progress temp file -- must be skipped (mirrors
    # is_tui_session_active()'s own ".{pid}.tmp" convention).
    (sessions_dir / ".999.tmp").write_text("999")

    monkeypatch.setattr("utils.config.TUI_SESSIONS_DIR", sessions_dir)

    pids = d._list_live_tui_session_pids()
    assert own_pid in pids
    assert dead_pid not in pids
    assert len(pids) == 1

    # Passive: no reaping of the dead-PID file (that's
    # is_tui_session_active()'s job, an explicit non-goal here).
    assert (sessions_dir / f"{dead_pid}.pid").exists()


# ── D. _observe_interactive_state() ──────────────────────────────────────────


def test_observe_interactive_state_first_observation_seeds_no_emit(_capture_telemetry):
    d = _bare_daemon()
    d._observe_interactive_state(True)
    assert _capture_telemetry == []
    assert d._interactive_active_last is True


def test_observe_interactive_state_transition_emits(monkeypatch, _capture_telemetry):
    d = _bare_daemon()
    monkeypatch.setattr(d, "_list_live_tui_session_pids", lambda: [4242])
    d._observe_interactive_state(False)  # seed
    assert _capture_telemetry == []

    d._observe_interactive_state(True)  # real transition
    records = _records_by_event_type(_capture_telemetry, "interactive_transition")
    assert len(records) == 1
    assert records[0]["body"]["active"] is True
    assert records[0]["body"]["previous_active"] is False
    assert records[0]["body"]["live_session_pids"] == [4242]

    d._observe_interactive_state(True)  # unchanged -- no re-emit
    assert len(_records_by_event_type(_capture_telemetry, "interactive_transition")) == 1


# ── superseded_by_plan ───────────────────────────────────────────────────────


def test_superseded_by_plan_emits_lone_task_finished(_capture_telemetry):
    d = _bare_daemon()
    d._record_daemon_telemetry_superseded_by_plan(555)

    started = _records_by_event_type(_capture_telemetry, "task_started")
    finished = _records_by_event_type(_capture_telemetry, "task_finished")
    assert started == []  # by design: this task_id never enters _execute_task()
    assert len(finished) == 1
    body = finished[0]["body"]
    assert body["task_id"] == 555
    assert body["task_type"] == "direct"
    assert body["needs_planning"] is True
    assert body["terminal_status"] == "superseded_by_plan"
    assert body["duration_ms"] == 0.0


def test_superseded_by_plan_wired_into_process_planner_tasks(tmp_path, monkeypatch, _capture_telemetry):
    """End-to-end (through _process_planner_tasks(), not the helper called
    directly) -- a needs_planning=1 task that expands into >=2 steps emits
    the lone task_finished, and no task_started for the same task_id."""
    from unittest.mock import AsyncMock, patch

    d = daemon_mod.Daemon.__new__(daemon_mod.Daemon)
    d.state = StateStore(db_path=tmp_path / "state.db")
    d.planner = MagicMock()
    d.planner.get_next_task.return_value = None
    d.planner._tasks = {}
    d.planner.add_tasks.return_value = [101, 102]
    d.executor = MagicMock()
    d.executor._execute_task = AsyncMock(return_value="executed result")
    d._config = MagicMock()
    d._config.get.return_value = 1800
    d._deferral_state = {}
    d._gate_dedup = {}
    d._interactive_active_last = None
    d._interactive_state_since_mono = time.monotonic()

    task_id = d.state.add_task("build a thing", needs_planning=1)

    allowed = DispatchDecision(allowed=True, reason="within resource limits")
    with patch.object(daemon_mod.Daemon, "_check_dispatch_gate", return_value=(allowed, False)), patch.object(
        daemon_mod.Daemon, "_plan_claimed_task", new=AsyncMock(return_value=["step one", "step two"])
    ):
        import asyncio

        asyncio.run(d._process_planner_tasks())

    finished = _records_by_event_type(_capture_telemetry, "task_finished")
    matching = [r for r in finished if r["body"]["task_id"] == task_id]
    assert len(matching) == 1
    assert matching[0]["body"]["terminal_status"] == "superseded_by_plan"
    started_for_task = [
        r for r in _records_by_event_type(_capture_telemetry, "task_started") if r["body"]["task_id"] == task_id
    ]
    assert started_for_task == []
