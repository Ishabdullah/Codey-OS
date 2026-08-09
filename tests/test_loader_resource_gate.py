"""
Resource-gate slot-awareness tests — CODEY_OS_MASTER_VISION.md Section 7.4
(2026-08-08 amendment), TODO.md 7.4 sub-task 2.

Covers the actual wiring added in this sub-task:
  - core/loader_v2.py:ModelLoader.load_primary()/unload()
  - core/planner_loader.py:PlannerLoader.load()/unload()
  - core/embed_server.py:EmbedServer.start()/stop() (accounted-but-exempt)

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
import core.planner_loader as pl
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
    a real-looking MagicMock, matching a genuine spawn, not a reuse)."""

    def __init__(self, *a, **k):
        self.process = MagicMock(pid=12345)
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
    pl._planner_loader = None
    es._embed_server = None
    yield
    lv._loader = None
    pl._planner_loader = None
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


def test_ensure_model_eviction_failed_sets_outcome(monkeypatch):
    fake_decision = MagicMock(admitted=True, hard_reject=False, estimated_cost_bytes=1024, reason="ok")
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, "slot-z"))
    monkeypatch.setattr(rg, "release_slot", lambda *a, **k: True)

    with patch.object(lv, "LlamaServer", FakeServerSpawned), patch(
        "pathlib.Path.exists", return_value=True
    ), patch.object(lv, "probe_port_health", return_value=True):  # planner port still answering
        loader = lv.get_loader()
        result = loader.ensure_model()

    assert result is False
    assert loader.get_last_ensure_outcome() == lv.LOAD_OUTCOME_EVICTION_FAILED


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


# ── PlannerLoader (1.5B) ─────────────────────────────────────────────────────


def test_planner_load_reserves_and_marks_resident(monkeypatch):
    fake_decision = MagicMock(admitted=True, estimated_cost_bytes=512, reason="ok")
    reserve_calls = []
    mark_calls = []
    monkeypatch.setattr(
        rg,
        "reserve_slot",
        lambda spec, **k: (reserve_calls.append(spec) or fake_decision, "planner-slot-1"),
    )
    monkeypatch.setattr(rg, "mark_resident", lambda slot_id, **k: mark_calls.append(slot_id) or True)
    monkeypatch.setattr(rg, "release_slot", lambda *a, **k: True)
    monkeypatch.setattr(rg, "read_meminfo", _meminfo_with_drop_after(1))

    with patch.object(lv, "LlamaServer", FakeServerSpawned), patch(
        "pathlib.Path.exists", return_value=True
    ):
        planner = pl.get_planner_loader()
        assert planner.load() is True

    assert planner._slot_id == "planner-slot-1"
    assert reserve_calls[0].model_id == "planner"
    assert mark_calls == ["planner-slot-1"]


def test_planner_load_denied_reservation_does_not_spawn(monkeypatch):
    fake_decision = MagicMock(admitted=False, estimated_cost_bytes=0, reason="no headroom")
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, None))

    with patch.object(lv, "LlamaServer") as MockServer, patch(
        "pathlib.Path.exists", return_value=True
    ):
        planner = pl.get_planner_loader()
        result = planner.load()

    assert result is False
    MockServer.assert_not_called()
    assert planner.is_loaded() is False


def test_planner_load_spawn_failure_releases_slot(monkeypatch):
    fake_decision = MagicMock(admitted=True, estimated_cost_bytes=512, reason="ok")
    released = []
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, "planner-slot-2"))
    monkeypatch.setattr(rg, "release_slot", lambda slot_id, **k: released.append(slot_id) or True)
    monkeypatch.setattr(rg, "read_meminfo", lambda *a, **k: {"MemAvailable": 10**10})

    with patch.object(lv, "LlamaServer", FakeServerSpawnFails), patch(
        "pathlib.Path.exists", return_value=True
    ):
        planner = pl.get_planner_loader()
        result = planner.load()

    assert result is False
    assert released == ["planner-slot-2"]
    assert planner._slot_id is None


def test_planner_unload_releases_slot(monkeypatch):
    fake_decision = MagicMock(admitted=True, estimated_cost_bytes=512, reason="ok")
    released = []
    monkeypatch.setattr(rg, "reserve_slot", lambda spec, **k: (fake_decision, "planner-slot-3"))
    monkeypatch.setattr(rg, "mark_resident", lambda *a, **k: True)
    monkeypatch.setattr(rg, "release_slot", lambda slot_id, **k: released.append(slot_id) or True)
    monkeypatch.setattr(rg, "read_meminfo", _meminfo_with_drop_after(1))

    with patch.object(lv, "LlamaServer", FakeServerSpawned), patch(
        "pathlib.Path.exists", return_value=True
    ):
        planner = pl.get_planner_loader()
        assert planner.load() is True
        planner.unload()

    assert planner._slot_id is None
    assert released == ["planner-slot-3"]


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


def test_planner_load_confirm_raises_slot_not_leaked_no_orphan(tmp_path, monkeypatch):
    """
    Same scenario as test_load_primary_confirm_raises_slot_not_leaked_no_orphan
    but for core/planner_loader.py:PlannerLoader.load() — the two loaders
    are separate call sites with separate (near-identical) control flow, so
    this must be verified independently, not assumed from the primary-side
    test alone.
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
            planner = pl.get_planner_loader()
            result = planner.load()
            # Read from the out-of-band spawn list, not planner._server —
            # the fix under test resets self._server to None on this
            # cleanup path (see load()'s finally block).
            proc = _REAL_SPAWNED_PROCESSES[0] if _REAL_SPAWNED_PROCESSES else None

        assert result is False
        assert planner._slot_id is None
        assert planner._loaded is False

        slots = rg.list_slots(state_dir=tmp_path)
        assert [s for s in slots if s.get("model_id") == "planner"] == [], (
            f"slot leaked after confirm-raise: {slots}"
        )

        assert proc is not None, "test setup bug: server never actually spawned"
        assert proc.poll() is not None, (
            f"process pid={proc.pid} is still running — orphaned by a leaked spawn"
        )
    finally:
        _kill_if_still_alive(proc)
