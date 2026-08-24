"""
Resource-gate slot-awareness tests — CODEY_OS_MASTER_VISION.md Section 7.4
(2026-08-08 amendment), TODO.md 7.4 sub-task 2.

Covers the actual wiring added in this sub-task:
  - core/loader_v2.py:ModelLoader.load_primary()/unload()
  - core/embed_server.py:EmbedServer.start()/stop() (accounted-but-exempt)

M1-D (2026-08-23): this file used to also cover
core/planner_loader.py:PlannerLoader.load()/unload() — that module (and
the dedicated planner server it managed) is deleted, planning now shares
the primary server, and its own "PlannerLoader (1.5B)" test section below
is removed along with it, not adapted.

All tests use a fake LlamaServer / mocked subprocess — no real llama-server
process is spawned (RAM-discipline rule, CLAUDE.md rule 2). Most tests patch
core.resource_gate's slot functions directly for determinism/speed; one
("test_real_gate_...") deliberately exercises the REAL resource_gate module
(synthetic meminfo + a tmp_path-backed state store) end-to-end, so the wiring
itself — not just that the loader calls some mock — is proven.
"""
import os
import signal
import subprocess
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

import core.embed_server as es
import core.loader_v2 as lv
import core.resource_gate as rg


def _meminfo_with_drop_after(n_before: int, high: int = 10**10, low: int = 0):
    """
    Returns a stand-in for resource_gate.read_meminfo() that reports `high`
    MemAvailable for the first `n_before` calls (matching reserve_slot()'s
    internal read + the loader's own pre-spawn baseline capture) and `low`
    MemAvailable afterward (matching confirm_resident_and_mark_slot()'s poll
    loop) -- so its very first poll iteration observes a confirming drop and
    returns immediately, instead of the real polling loop actually waiting
    out real wall-clock time in tests that aren't specifically about that
    loop's own timing (see test_confirm_resident_marks_* below for those).
    """
    calls = {"n": 0}

    def _fake(*a, **k):
        calls["n"] += 1
        return {"MemAvailable": high if calls["n"] <= n_before else low}

    return _fake


class FakeServerSpawned:
    """Stand-in for LlamaServer that "spawned" its own process (process is
    a real-looking MagicMock, matching a genuine spawn, not a reuse).

    `.process.pid` is this test process's OWN pid (os.getpid()), not an
    arbitrary placeholder. Every current caller of this fixture except
    test_real_gate_reserve_confirm_release_end_to_end is unaffected by this
    fixture's pid value either way: they mock resource_gate.mark_resident()
    directly (so the pid never reaches real PID-liveness logic), or -- like
    test_ensure_model_eviction_failed_sets_outcome -- take a code path that
    returns before mark_resident() is ever called. But
    test_real_gate_reserve_confirm_release_end_to_end exercises the REAL
    resource_gate module end-to-end, and mark_resident() (as of the NEW-81
    ghost-slot fix) now honors a forwarded real pid -- a hardcoded dead pid
    like 12345 gets reaped mid-test by the real list_slots() liveness
    check, which broke that test. os.getpid() is guaranteed alive for the
    whole test process's lifetime, so it can never be mistaken for a dead
    process by that same reap logic.

    Limitation: os.getpid() is also reserve_slot()'s own default pid (its
    `if pid is None: pid = os.getpid()`), so this fixture alone can't
    distinguish "pid was rebound to the spawned child" from "pid was left
    at the caller default" -- test_real_gate_reserve_confirm_release_end_to_end
    doesn't assert on pid, so this doesn't weaken it. That rebinding
    assertion (a genuinely distinct, independently-alive child pid) lives
    in test_load_primary_crash_then_reload_not_denied_by_ghost_slot_new81
    via the separate _fake_server_with_pid() factory below."""

    def __init__(self, *a, **k):
        self.process = MagicMock(pid=os.getpid())
        self._started = True

    def start(self):
        return True

    def stop(self):
        self.process = None
        self._started = False

    def is_running(self):
        return self._started


class FakeServerReused:
    """Stand-in for LlamaServer.start() returning True via one of its reuse
    branches (already running on the port / another process's in-flight
    start) — self.process stays None, matching the real class's behavior
    (see core/loader_v2.py:LlamaServer.start())."""

    def __init__(self, *a, **k):
        self.process = None
        self._started = True

    def start(self):
        return True

    def stop(self):
        self._started = False

    def is_running(self):
        return self._started


# Populated by RealSpawnLlamaServer.start() below, read (and cleared) by the
# confirm-raises regression tests. A module-level list rather than reading
# `loader._server.process`/`planner._server.process` back off the loader
# afterward, because the fix under test deliberately resets `self._server`
# to None as part of its cleanup path (see load_primary()'s/load()'s
# finally block) — the test needs an out-of-band handle to the spawned
# process captured at spawn time, independent of what the loader's own
# post-cleanup state looks like.
_REAL_SPAWNED_PROCESSES: list = []


class RealSpawnLlamaServer(lv.LlamaServer):
    """
    Stand-in for LlamaServer that spawns a REAL (but harmless, no model
    involved — CLAUDE.md rule 2 RAM discipline) subprocess in place of
    llama-server, and otherwise inherits the real LlamaServer.stop()/
    is_running() unmodified. Used by the confirm-raises regression tests
    below so they exercise genuine process teardown (os.killpg etc.), not a
    mocked stop() that could pass even if the real cleanup path were
    broken — this is exactly what the reviewer flagged: the existing 15
    tests all mocked the server, so a real orphaned-process leak wouldn't
    have been caught by them.
    """

    def start(self) -> bool:
        self.process = subprocess.Popen(
            ["sleep", "300"], preexec_fn=os.setsid if os.name != "nt" else None
        )
        self._started = True
        _REAL_SPAWNED_PROCESSES.append(self.process)
        return True


def _fake_server_with_pid(pid: int):
    """
    Factory (mirrors `_meminfo_with_drop_after()`'s closure-factory pattern
    above) for a `FakeServerSpawned`-shaped stand-in whose `.process.pid` is
    caller-supplied instead of `FakeServerSpawned`'s fixed `os.getpid()` --
    needed so a test can attach a genuine (and independently
    killable/already-dead) PID *distinct from this test process's own*, to
    exercise resource_gate's real PID-liveness reaping rather than a pid
    that's guaranteed alive for the whole test run regardless of what's
    under test.
    """

    class _FakeServer:
        def __init__(self, *a, **k):
            self.process = MagicMock(pid=pid)
            self._started = True

        def start(self):
            return True

        def stop(self):
            self.process = None
            self._started = False

        def is_running(self):
            return self._started

    return _FakeServer


class FakeServerSpawnFails:
    def __init__(self, *a, **k):
        self.process = None
        self._started = False

    def start(self):
        return False

    def stop(self):
        pass

    def is_running(self):
        return False


@pytest.fixture(autouse=True)
def reset_singletons():
    lv._loader = None
    es._embed_server = None
    yield
    lv._loader = None
    es._embed_server = None


# ── ModelLoader (primary, 7B) ────────────────────────────────────────────────


def test_load_primary_reserves_and_marks_resident_on_real_spawn(monkeypatch):
    fake_decision = MagicMock(admitted=True, estimated_cost_bytes=1024, reason="ok")
    reserve_calls = []
    mark_calls = []

    monkeypatch.setattr(
        rg,
        "reserve_slot",
        lambda spec, **k: (reserve_calls.append(spec) or fake_decision, "slot-1"),
    )
    monkeypatch.setattr(rg, "mark_resident", lambda slot_id, **k: mark_calls.append(slot_id) or True)
    monkeypatch.setattr(rg, "release_slot", lambda *a, **k: True)
    # 1 pre-spawn read (load_primary()'s own baseline capture -- reserve_slot()
    # itself is mocked above, so it never calls the real read_meminfo()), then
    # a drop on every subsequent read so confirm_resident_and_mark_slot()'s
    # loop confirms on its first iteration instead of waiting out real time.
    monkeypatch.setattr(rg, "read_meminfo", _meminfo_with_drop_after(1))

    with patch.object(lv, "LlamaServer", FakeServerSpawned), patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        assert loader.load_primary() is True

    assert loader._slot_id == "slot-1"
    assert reserve_calls[0].model_id == "primary"
    assert mark_calls == ["slot-1"]
    # NEW-152 (narrows 7.4b sub-task C's NEW-145 fix): a genuine spawn sets
    # was_ever_spawned() True (used by core/daemon.py's watchdog to
    # distinguish "never spawned, nothing to restart" from "this loader
    # spawned it, restart it").
    assert loader.was_ever_spawned() is True


def test_load_primary_denied_reservation_does_not_spawn(monkeypatch):
    fake_decision = MagicMock(admitted=False, estimated_cost_bytes=0, reason="no headroom")
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, None))

    with patch.object(lv, "LlamaServer") as MockServer, patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is False
    MockServer.assert_not_called()
    assert loader.is_loaded() is False
    assert loader.get_load_failures() == 1
    # 7.4b sub-task C's NEW-145 fix: a gate-denied load never reaches the
    # success point, so was_ever_spawned() stays False -- this is exactly
    # the case core/daemon.py's watchdog must leave alone rather than
    # eagerly loading on its own 30s tick.
    assert loader.was_ever_spawned() is False


def test_load_primary_spawn_failure_releases_slot_not_leaked(monkeypatch):
    fake_decision = MagicMock(admitted=True, estimated_cost_bytes=1024, reason="ok")
    released = []
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, "slot-2"))
    monkeypatch.setattr(rg, "release_slot", lambda slot_id, **k: released.append(slot_id) or True)
    monkeypatch.setattr(rg, "read_meminfo", lambda *a, **k: {"MemAvailable": 10**10})

    with patch.object(lv, "LlamaServer", FakeServerSpawnFails), patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is False
    assert released == ["slot-2"]  # not leaked
    assert loader._slot_id is None


def test_load_primary_reuse_path_releases_own_slot_does_not_mark_resident(monkeypatch):
    """
    If LlamaServer.start() reused an existing server (self.process stays
    None), this loader does not own that process's residency — it must
    release its own reservation instead of double-accounting, and must not
    call mark_resident() for a process it didn't spawn.
    """
    fake_decision = MagicMock(admitted=True, estimated_cost_bytes=1024, reason="ok")
    released = []
    mark_calls = []
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, "slot-3"))
    monkeypatch.setattr(rg, "release_slot", lambda slot_id, **k: released.append(slot_id) or True)
    monkeypatch.setattr(rg, "mark_resident", lambda slot_id, **k: mark_calls.append(slot_id) or True)
    monkeypatch.setattr(rg, "read_meminfo", lambda *a, **k: {"MemAvailable": 10**10})

    with patch.object(lv, "LlamaServer", FakeServerReused), patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is True  # server usable (reused), load itself succeeded
    assert loader._slot_id is None
    assert released == ["slot-3"]
    assert mark_calls == []  # never marked resident for a process we don't own
    # NEW-152: the reuse/adoption branch converges on the same success
    # point as a genuine spawn, but was_ever_spawned() only answers "did
    # THIS loader's own subprocess.Popen() actually run" -- adoption
    # deliberately does NOT set it (see NEW-152 in NEW_ISSUES.md: the
    # previous, broader "spawned OR adopted" flag was the root cause of a
    # sticky watchdog gate that stopped protecting the daemon after the
    # first adoption). This is the regression assertion for that fix.
    assert loader.was_ever_spawned() is False


def test_unload_releases_slot(monkeypatch):
    fake_decision = MagicMock(admitted=True, estimated_cost_bytes=1024, reason="ok")
    released = []
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, "slot-4"))
    monkeypatch.setattr(rg, "mark_resident", lambda *a, **k: True)
    monkeypatch.setattr(rg, "release_slot", lambda slot_id, **k: released.append(slot_id) or True)
    monkeypatch.setattr(rg, "read_meminfo", _meminfo_with_drop_after(1))

    with patch.object(lv, "LlamaServer", FakeServerSpawned), patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        assert loader.load_primary() is True
        loader.unload()

    assert loader._slot_id is None
    assert released == ["slot-4"]


# ── ensure_model()/load_primary() outcome tracking (TODO.md 7.4 sub-task 3) ──
# core/daemon.py's watchdog/preload/shutdown call sites need to distinguish a
# gate denial (real, expected 7.4 outcome) from a process crash or spawn
# failure -- these tests cover get_last_ensure_outcome()/get_last_ensure_reason()
# at every return point, including the "stale value from a prior call" trap
# (deferred/eviction-failed paths that never reach load_primary()).


def test_load_primary_gate_denied_transient_sets_outcome(monkeypatch):
    fake_decision = MagicMock(
        admitted=False, hard_reject=False, estimated_cost_bytes=0, reason="no headroom"
    )
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, None))

    with patch.object(lv, "LlamaServer") as MockServer, patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is False
    MockServer.assert_not_called()
    assert loader.get_last_ensure_outcome() == lv.LOAD_OUTCOME_GATE_DENIED
    assert loader.get_last_ensure_reason() == "no headroom"


def test_load_primary_gate_denied_hard_sets_outcome(monkeypatch):
    fake_decision = MagicMock(
        admitted=False, hard_reject=True, estimated_cost_bytes=0, reason="model too big for device"
    )
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, None))

    with patch.object(lv, "LlamaServer") as MockServer, patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is False
    MockServer.assert_not_called()
    assert loader.get_last_ensure_outcome() == lv.LOAD_OUTCOME_GATE_DENIED_HARD
    assert loader.get_last_ensure_reason() == "model too big for device"


def test_load_primary_spawn_failure_sets_outcome(monkeypatch):
    fake_decision = MagicMock(admitted=True, hard_reject=False, estimated_cost_bytes=1024, reason="ok")
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, "slot-x"))
    monkeypatch.setattr(rg, "release_slot", lambda *a, **k: True)
    monkeypatch.setattr(rg, "read_meminfo", lambda *a, **k: {"MemAvailable": 10**10})

    with patch.object(lv, "LlamaServer", FakeServerSpawnFails), patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is False
    assert loader.get_last_ensure_outcome() == lv.LOAD_OUTCOME_SPAWN_FAILED


def test_load_primary_success_sets_ok_outcome(monkeypatch):
    fake_decision = MagicMock(admitted=True, hard_reject=False, estimated_cost_bytes=1024, reason="ok")
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, "slot-y"))
    monkeypatch.setattr(rg, "mark_resident", lambda *a, **k: True)
    monkeypatch.setattr(rg, "release_slot", lambda *a, **k: True)
    monkeypatch.setattr(rg, "read_meminfo", _meminfo_with_drop_after(1))

    with patch.object(lv, "LlamaServer", FakeServerSpawned), patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        assert loader.load_primary() is True

    assert loader.get_last_ensure_outcome() == lv.LOAD_OUTCOME_OK
    assert loader.get_last_ensure_reason() == ""


def test_ensure_model_deferred_outcome_not_stale_from_prior_gate_denial(monkeypatch):
    """
    Regression for the staleness trap: a prior call denied by the gate must
    not leak its outcome into a LATER call that's deferred by SWAP_GUARD for
    an unrelated reason (planner mid-swap) -- ensure_model() must overwrite
    the outcome at every one of its own return points, not just inside
    load_primary().
    """
    fake_decision = MagicMock(
        admitted=False, hard_reject=False, estimated_cost_bytes=0, reason="no headroom"
    )
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, None))

    with patch.object(lv, "LlamaServer") as MockServer, patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        assert loader.ensure_model() is False
        assert loader.get_last_ensure_outcome() == lv.LOAD_OUTCOME_GATE_DENIED

        lv.SWAP_GUARD.acquire()
        try:
            assert loader.ensure_model() is False
        finally:
            lv.SWAP_GUARD.release()

    assert loader.get_last_ensure_outcome() == lv.LOAD_OUTCOME_DEFERRED


# M1-D (2026-08-23): a test_ensure_model_eviction_failed_sets_outcome test
# used to sit here, pinning ensure_model()'s cold-load branch failing
# closed (LOAD_OUTCOME_EVICTION_FAILED) when it couldn't confirm the
# dedicated planner's port had freed before loading the primary. That
# eviction step (and the outcome constant itself) is removed along with
# core/planner_loader.py — ensure_model()'s cold-load branch now goes
# straight to load_primary(), so this scenario can no longer occur; see
# core/loader_v2.py's own comment on the removed constant.


def test_ensure_model_already_loaded_sets_outcome(monkeypatch):
    fake_decision = MagicMock(admitted=True, hard_reject=False, estimated_cost_bytes=1024, reason="ok")
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, "slot-w"))
    monkeypatch.setattr(rg, "mark_resident", lambda *a, **k: True)
    monkeypatch.setattr(rg, "release_slot", lambda *a, **k: True)
    monkeypatch.setattr(rg, "read_meminfo", _meminfo_with_drop_after(1))

    with patch.object(lv, "LlamaServer", FakeServerSpawned), patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        assert loader.load_primary() is True
        # Second call: already loaded and running, no thermal restart --
        # thermal import will raise inside the try/except (no core.thermal
        # module state mocked) which is fine, that branch fails open.
        result = loader.ensure_model()

    assert result is True
    assert loader.get_last_ensure_outcome() == lv.LOAD_OUTCOME_ALREADY_LOADED


# ── confirm_resident_and_mark_slot() ─────────────────────────────────────────


def test_confirm_resident_marks_immediately_when_drop_observed(monkeypatch):
    """A MemAvailable drop matching the cost estimate is observed on the
    first poll -- no need to wait out the timeout."""
    monkeypatch.setattr(rg, "read_meminfo", lambda *a, **k: {"MemAvailable": 100})
    marked = []
    monkeypatch.setattr(rg, "mark_resident", lambda slot_id, **k: marked.append(slot_id) or True)
    sleeps = []
    monkeypatch.setattr(lv.time, "sleep", lambda s: sleeps.append(s))

    lv.confirm_resident_and_mark_slot(
        "slot-x", baseline_meminfo={"MemAvailable": 1000}, estimated_cost_bytes=1000
    )

    assert marked == ["slot-x"]
    assert sleeps == []  # drop (900) >= threshold (500) on the very first read


def test_confirm_resident_forwards_pid_to_mark_resident(monkeypatch):
    """
    NEW-81 fix: confirm_resident_and_mark_slot()'s optional `pid` must be
    forwarded straight through to resource_gate.mark_resident(), so
    load_primary()'s/PlannerLoader.load()'s real spawned-subprocess PID
    actually reaches the slot store, not silently dropped along the way.
    """
    monkeypatch.setattr(rg, "read_meminfo", lambda *a, **k: {"MemAvailable": 100})
    mark_calls = []
    monkeypatch.setattr(
        rg,
        "mark_resident",
        lambda slot_id, **k: mark_calls.append((slot_id, k.get("pid"))) or True,
    )
    monkeypatch.setattr(lv.time, "sleep", lambda s: None)

    lv.confirm_resident_and_mark_slot(
        "slot-x", baseline_meminfo={"MemAvailable": 1000}, estimated_cost_bytes=1000, pid=54321
    )

    assert mark_calls == [("slot-x", 54321)]


def test_confirm_resident_marks_anyway_after_timeout_with_no_drop(monkeypatch):
    """No confirming drop within the timeout -- still marks resident (see
    confirm_resident_and_mark_slot()'s docstring for why: a permanently
    PENDING slot for an actually-loaded model double-counts against
    reserved_bytes)."""
    monkeypatch.setattr(rg, "read_meminfo", lambda *a, **k: {"MemAvailable": 1000})  # no drop
    marked = []
    monkeypatch.setattr(rg, "mark_resident", lambda slot_id, **k: marked.append(slot_id) or True)
    monkeypatch.setattr(lv.time, "sleep", lambda s: None)  # don't actually wait

    lv.confirm_resident_and_mark_slot(
        "slot-y",
        baseline_meminfo={"MemAvailable": 1000},
        estimated_cost_bytes=1000,
        timeout_s=0.05,
        poll_interval_s=0.01,
    )

    assert marked == ["slot-y"]


# ── Embed server: accounted-but-exempt ───────────────────────────────────────


def test_embed_server_registers_slot_as_resident_on_start(monkeypatch, tmp_path):
    fake_model = tmp_path / "embed.gguf"
    fake_model.write_bytes(b"x" * 4096)

    registered = []
    monkeypatch.setattr(
        rg,
        "register_slot",
        lambda **kwargs: registered.append(kwargs) or "embed-slot-1",
    )

    fake_process = MagicMock()
    fake_process.poll.return_value = None
    fake_process.pid = 999

    server = es.EmbedServer()
    server.model_path = fake_model

    with patch.object(server, "_is_port_open", return_value=False), patch(
        "subprocess.Popen", return_value=fake_process
    ), patch.object(server, "_check_health", return_value=True), patch.object(
        es.time, "sleep", return_value=None
    ), patch.object(Path, "exists", return_value=True):
        result = server.start()

    assert result is True
    assert len(registered) == 1
    kwargs = registered[0]
    assert kwargs["model_id"] == "embed"
    assert kwargs["status"] == rg.SLOT_STATUS_RESIDENT
    assert kwargs["pid"] == 999
    assert kwargs["cost_bytes"] == 4096
    assert server._slot_id == "embed-slot-1"


def test_embed_server_releases_slot_on_stop(monkeypatch, tmp_path):
    fake_model = tmp_path / "embed.gguf"
    fake_model.write_bytes(b"x" * 4096)

    monkeypatch.setattr(rg, "register_slot", lambda **kwargs: "embed-slot-2")
    released = []
    monkeypatch.setattr(rg, "release_slot", lambda slot_id, **k: released.append(slot_id) or True)

    fake_process = MagicMock()
    fake_process.poll.return_value = None
    fake_process.pid = 999

    server = es.EmbedServer()
    server.model_path = fake_model

    with patch.object(server, "_is_port_open", return_value=False), patch(
        "subprocess.Popen", return_value=fake_process
    ), patch.object(server, "_check_health", return_value=True), patch.object(
        es.time, "sleep", return_value=None
    ), patch.object(Path, "exists", return_value=True):
        assert server.start() is True
        server.stop()

    assert released == ["embed-slot-2"]
    assert server._slot_id is None


# ── Real resource-gate end-to-end (not mocked) ──────────────────────────────


def test_real_gate_reserve_confirm_release_end_to_end(tmp_path, monkeypatch):
    """
    Exercises the REAL core.resource_gate module (synthetic meminfo, a
    tmp_path-backed cross-process state store) through the real loader path
    -- proves the wiring itself, not just that the loader calls some mock.
    """
    monkeypatch.setattr(rg, "CODEY_STATE_DIR", tmp_path)

    # First two real-meminfo reads (inside reserve_slot()'s can_admit() call,
    # then load_primary()'s own pre-spawn baseline capture) report generous
    # headroom; every read after that (inside
    # confirm_resident_and_mark_slot()'s poll loop) reports a drop
    # consistent with the model having landed, so the loop's very first
    # iteration confirms residency -- no real wall-clock wait needed to
    # exercise the real confirm-then-mark_resident() path end-to-end.
    call_count = {"n": 0}

    def fake_read_meminfo(*a, **k):
        call_count["n"] += 1
        if call_count["n"] <= 2:
            return {"MemTotal": 16 * 1024**3, "MemAvailable": 16 * 1024**3}
        return {"MemTotal": 16 * 1024**3, "MemAvailable": 1 * 1024**3}

    monkeypatch.setattr(rg, "read_meminfo", fake_read_meminfo)
    monkeypatch.setattr(rg, "read_current_temp_c", lambda: None)  # no thermal objection

    with patch.object(lv, "LlamaServer", FakeServerSpawned), patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        assert loader.load_primary() is True

    slots = rg.list_slots(state_dir=tmp_path)
    assert len(slots) == 1
    assert slots[0]["status"] == rg.SLOT_STATUS_RESIDENT
    assert slots[0]["model_id"] == "primary"

    loader.unload()
    assert rg.list_slots(state_dir=tmp_path) == []


def test_real_gate_denies_oversized_model_and_loader_does_not_spawn(tmp_path, monkeypatch):
    """Hard-ceiling denial (single model too big for the device) must
    propagate as a real load_primary() failure with no spawn."""
    monkeypatch.setattr(rg, "CODEY_STATE_DIR", tmp_path)

    tiny_device_meminfo = {"MemTotal": 1024, "MemAvailable": 1024}  # ~1KiB "device"
    monkeypatch.setattr(rg, "read_meminfo", lambda *a, **k: tiny_device_meminfo)
    monkeypatch.setattr(rg, "read_current_temp_c", lambda: None)

    with patch.object(lv, "LlamaServer") as MockServer, patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        result = loader.load_primary()

    assert result is False
    MockServer.assert_not_called()
    assert rg.list_slots(state_dir=tmp_path) == []  # nothing leaked


def test_load_primary_crash_then_reload_not_denied_by_ghost_slot_new81(tmp_path, monkeypatch):
    """
    Regression for the gap TODO.md 7.4a sub-task C1's new
    MAX_CONCURRENT_MODEL_BUDGET_BYTES ceiling activated: NEW-81 ("slot
    records have no way to rebind pid at the PENDING->RESIDENT transition").

    Before this fix: reserve_slot() registers the primary's slot under this
    LOADER's own PID (its `if pid is None: pid = os.getpid()` default,
    called before the llama-server subprocess even exists yet). If that
    subprocess later crashes on its own (OOM-kill, etc.) while the loader
    process itself stays alive -- exactly ensure_model()'s cold-load
    fallthrough (is_running() False, no explicit unload()/release_slot() in
    between, matching this test: nothing calls unload() between the two
    load_primary() calls below) -- resource_gate's PID-liveness reap keeps
    checking the loader's own (still-alive) PID forever. The stale
    RESIDENT slot is never reaped, so a second load of the same primary
    sums to roughly double its single-load cost against the fixed
    MAX_CONCURRENT_MODEL_BUDGET_BYTES ceiling and is wrongly denied as
    unrecoverable.

    Real gate, real tmp_path-backed state store, and the real on-disk
    primary model file at whatever n_ctx utils.config.MODEL_CONFIG
    actually configures (Qwen3.5-4B, ~4.85GiB single-load cost at the
    current default n_ctx=65536 -- was Qwen2.5-Coder-7B at ~6.36GiB/
    n_ctx=32768 and an 8.90GiB ceiling before §1.4/M1-D/M1-F, 2026-08-24;
    see core/resource_gate.py's MAX_CONCURRENT_MODEL_BUDGET_BYTES comment
    for the current derivation) so this proves the actual admission math
    against real, current numbers, not a hand-picked cost that happens to
    clear the ceiling either way.
    """
    monkeypatch.setattr(rg, "CODEY_STATE_DIR", tmp_path)
    monkeypatch.setattr(rg, "read_current_temp_c", lambda: None)
    monkeypatch.setattr(lv.time, "sleep", lambda s: None)  # don't wait out real poll intervals

    # Cycle of 3 reads per load_primary() call: (1) reserve_slot()'s own
    # internal admission read (generous -- headroom must look fine), (2)
    # load_primary()'s pre-spawn baseline capture (generous, same value --
    # no drop yet), (3) confirm_resident_and_mark_slot()'s first poll
    # iteration (a big drop from that baseline, well over the ~3.2GiB
    # confirm threshold, so it confirms immediately instead of waiting out
    # CONFIRM_RESIDENT_TIMEOUT_S of real wall-clock time). Repeats
    # identically for the second load_primary() call.
    GIB = 1024**3
    call_count = {"n": 0}

    def fake_read_meminfo(*a, **k):
        n = call_count["n"]
        call_count["n"] += 1
        if n % 3 == 2:
            return {"MemTotal": 16 * GIB, "MemAvailable": 2 * GIB}
        return {"MemTotal": 16 * GIB, "MemAvailable": 16 * GIB}

    monkeypatch.setattr(rg, "read_meminfo", fake_read_meminfo)

    # A real, genuinely-alive-then-killed PID (same "sleep 300" +
    # os.killpg(SIGKILL) precedent as RealSpawnLlamaServer/
    # _kill_if_still_alive above) -- must be ALIVE at the moment the first
    # load_primary() call registers/confirms the slot (a real crash doesn't
    # happen until after the model has genuinely loaded), then killed
    # in-test to simulate the crash before the second load_primary() call.
    # A PID that's already dead when reserve_slot()/mark_resident() first
    # see it (e.g. subprocess.Popen(["true"]) + immediate wait()) would be
    # reaped by the very first post-load list_slots() read below regardless
    # of whether this fix works -- that would prove nothing.
    proc = subprocess.Popen(["sleep", "300"], preexec_fn=os.setsid if os.name != "nt" else None)
    real_pid = proc.pid
    # A second real-and-alive process, standing in for the NEW llama-server
    # the second (post-crash) load_primary() call spawns -- must be a
    # different, independently-alive PID from `real_pid` above, otherwise
    # the final list_slots() reap below would reap this one too (it would
    # coincidentally also be dead, proving nothing about whether the OLD
    # ghost slot specifically got reaped).
    proc2 = subprocess.Popen(["sleep", "300"], preexec_fn=os.setsid if os.name != "nt" else None)
    real_pid2 = proc2.pid

    try:
        with patch.object(lv, "LlamaServer", _fake_server_with_pid(real_pid)), patch(
            "pathlib.Path.exists", return_value=True
        ):
            loader = lv.get_loader()
            assert loader.load_primary() is True

        slots = rg.list_slots(state_dir=tmp_path)
        assert len(slots) == 1
        assert slots[0]["status"] == rg.SLOT_STATUS_RESIDENT
        assert slots[0]["pid"] == real_pid, (
            "slot must carry the real spawned subprocess PID, not this "
            "loader process's own PID, for crash-time reaping to work "
            "(NEW-81) -- got "
            f"{slots[0]['pid']!r}"
        )

        # Simulate the crash: kill the real subprocess the slot's pid now
        # points to, but deliberately do NOT call
        # loader.unload()/rg.release_slot() -- matches ensure_model()'s
        # actual cold-load fallthrough exactly (is_running() False, no
        # explicit cleanup in that branch). self._slot_id is still set to
        # the now-stale slot.
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait(timeout=5)

        # A second load of the same primary spec must NOT be denied
        # by the fixed MAX_CONCURRENT_MODEL_BUDGET_BYTES ceiling -- the
        # stale RESIDENT slot (real_pid, now genuinely dead) must be reaped
        # inside reserve_slot()'s own lock, before the committed-bytes sum
        # is computed against the candidate.
        decision_holder = {}
        orig_reserve_slot = rg.reserve_slot

        def _capturing_reserve_slot(spec, **kwargs):
            decision, slot_id = orig_reserve_slot(spec, **kwargs)
            decision_holder["decision"] = decision
            return decision, slot_id

        monkeypatch.setattr(rg, "reserve_slot", _capturing_reserve_slot)

        with patch.object(lv, "LlamaServer", _fake_server_with_pid(real_pid2)), patch(
            "pathlib.Path.exists", return_value=True
        ):
            assert loader.load_primary() is True, (
                f"second load wrongly denied: {decision_holder.get('decision')}"
            )
        assert decision_holder["decision"].budget_ceiling_exceeded is False

        final_slots = rg.list_slots(state_dir=tmp_path)
        # The stale ghost slot from the first (crashed) load was reaped --
        # only the new load's own slot (real_pid2, still alive) remains.
        assert len(final_slots) == 1
        assert final_slots[0]["status"] == rg.SLOT_STATUS_RESIDENT
        assert final_slots[0]["pid"] == real_pid2
    finally:
        _kill_if_still_alive(proc)
        _kill_if_still_alive(proc2)


# ── confirm_resident_and_mark_slot() raising: reserve→spawn→confirm leak ────
# (.claude/agent-memory/code-reviewer/
#  resource_gate_subtask2_confirm_mark_slot_leak.md)


def _real_gate_generous_meminfo(monkeypatch, tmp_path):
    """
    Shared setup for the two tests below: real resource_gate module, real
    tmp_path-backed state store, generous synthetic headroom so reserve_slot()
    admits, then a confirming MemAvailable drop from the 3rd read onward so
    confirm_resident_and_mark_slot()'s poll loop confirms on its very first
    iteration instead of waiting out CONFIRM_RESIDENT_TIMEOUT_S of real
    wall-clock time (its default arg binds at def time, so patching the
    module constant has no effect here — must control this via read_meminfo).
    """
    monkeypatch.setattr(rg, "CODEY_STATE_DIR", tmp_path)
    monkeypatch.setattr(rg, "read_current_temp_c", lambda: None)

    call_count = {"n": 0}

    def fake_read_meminfo(*a, **k):
        call_count["n"] += 1
        # First 2 reads: reserve_slot()'s can_admit() check + the loader's
        # own pre-spawn baseline capture. From the 3rd read on (inside
        # confirm_resident_and_mark_slot()'s poll loop): a large drop.
        if call_count["n"] <= 2:
            return {"MemTotal": 16 * 1024**3, "MemAvailable": 16 * 1024**3}
        return {"MemTotal": 16 * 1024**3, "MemAvailable": 1 * 1024**3}

    monkeypatch.setattr(rg, "read_meminfo", fake_read_meminfo)


def _kill_if_still_alive(proc: Optional[subprocess.Popen]):
    """
    Same-PID safety-net kill (never a bare-name pkill, CLAUDE.md rule 3) for
    a subprocess spawned by RealSpawnLlamaServer in the two tests below.
    Called from a `finally` in BOTH tests so this always runs regardless of
    which assertion (if any) fails first — a leaked "sleep 300" from a
    broken fix under test must not itself become an orphaned process left
    behind by the test suite.
    """
    if proc is None:
        return
    if proc.poll() is None:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def test_load_primary_confirm_raises_slot_not_leaked_no_orphan(tmp_path, monkeypatch):
    """
    Live-reproduces the leak: confirm_resident_and_mark_slot() (specifically
    rg.mark_resident(), a _LockedState flock()+os.replace() operation that
    can raise under fd exhaustion/disk pressure) raises AFTER the server has
    genuinely spawned. load_primary() must not leave the reservation stuck
    PENDING nor the spawned process orphaned — asserted against the REAL
    resource_gate module and a REAL spawned subprocess, not mocks.
    """
    _real_gate_generous_meminfo(monkeypatch, tmp_path)

    def boom(slot_id, state_dir=None):
        raise OSError("simulated flock()/os.replace() failure under fd exhaustion")

    monkeypatch.setattr(rg, "mark_resident", boom)

    _REAL_SPAWNED_PROCESSES.clear()
    proc = None
    try:
        with patch.object(lv, "LlamaServer", RealSpawnLlamaServer), patch(
            "pathlib.Path.exists", return_value=True
        ):
            loader = lv.get_loader()
            result = loader.load_primary()
            # Read from the out-of-band spawn list, not loader._server —
            # the fix under test resets self._server to None on this
            # cleanup path (see load_primary()'s finally block).
            proc = _REAL_SPAWNED_PROCESSES[0] if _REAL_SPAWNED_PROCESSES else None

        assert result is False
        assert loader._slot_id is None
        assert loader._loaded is False

        # Not left reserved: no leftover "primary" slot in the real gate store.
        slots = rg.list_slots(state_dir=tmp_path)
        assert [s for s in slots if s.get("model_id") == "primary"] == [], (
            f"slot leaked after confirm-raise: {slots}"
        )

        assert proc is not None, "test setup bug: server never actually spawned"
        assert proc.poll() is not None, (
            f"process pid={proc.pid} is still running — orphaned by a leaked spawn"
        )
    finally:
        _kill_if_still_alive(proc)


# M1-D (2026-08-23): a test_planner_load_confirm_raises_slot_not_leaked_
# no_orphan test used to sit here, the planner-side mirror of
# test_load_primary_confirm_raises_slot_not_leaked_no_orphan above for
# core/planner_loader.py:PlannerLoader.load() — that module is deleted
# along with the dedicated planner server it managed, so it's removed
# rather than adapted. The primary-side test above still covers this
# failure mode for the one loader that remains.
