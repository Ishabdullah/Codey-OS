"""
NEW-12 regression tests: cross-process start lock for LlamaServer, and the
sequential-swap arbiter between the primary (7B) ModelLoader and the
planner (1.5B) PlannerLoader.

Part 1 (core/loader_v2.py):
  - LlamaServer.__init__ takes an explicit port (default: SERVER_PORT).
  - LlamaServer.start() takes a per-port flock'd lock file around its
    check-port-then-spawn critical section; if another process holds the
    lock, it polls for that process's server to come up and reuses it
    instead of double-spawning.

Part 2 (core/planner_loader.py + core/loader_v2.py):
  - ModelLoader.ensure_model() and PlannerLoader.ensure_planner() are
    mutually exclusive (never both resident) via a shared in-process
    SWAP_GUARD, and each evicts the other side before loading.
  - PlannerLoader fails closed (does not load) if it can't confirm the
    primary's port is actually free after eviction, rather than risking
    both models resident at once.

All tests use a fake LlamaServer / mocked subprocess — no real
llama-server process is spawned.
"""
import fcntl
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

import core.loader_v2 as lv
import core.planner_loader as pl


class FakeServer:
    """Stand-in for LlamaServer that never spawns a real subprocess."""

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


@pytest.fixture(autouse=True)
def reset_singletons():
    lv._loader = None
    pl._planner_loader = None
    yield
    lv._loader = None
    pl._planner_loader = None


# ── Part 1: cross-process lock ──────────────────────────────────────────────


def test_llama_server_accepts_explicit_port_defaulting_to_server_port():
    s1 = lv.LlamaServer(lv.MODEL_PATH)
    assert s1.port == lv.SERVER_PORT
    s2 = lv.LlamaServer(lv.MODEL_PATH, port=9999)
    assert s2.port == 9999


def test_start_reuses_existing_server_when_lock_held_by_another_process(tmp_path, monkeypatch):
    """
    If another process holds the per-port lock file, start() must not spawn
    a second server — it should poll for health and reuse, then give up
    cleanly (not raise, not double-spawn) if nothing answers in time.
    """
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)

    port = 18081
    lock_path = tmp_path / f"llama-server-{port}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    held_fd = open(lock_path, "w")
    fcntl.flock(held_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    try:
        server = lv.LlamaServer(lv.MODEL_PATH, port=port)
        # Patch subprocess.Popen too, matching the sibling test below — the
        # lock in this test is held by an fd this test itself opened (never
        # released within the test), so start() should never reach _spawn_locked()
        # at all, but a real Popen call must be impossible regardless of that
        # assumption (belt-and-braces against a real 7B spawn, see NEW-12
        # fix-up round 2, Bug 3 / the disclosed PID-1388 incident).
        with patch.object(server, "_is_port_in_use", return_value=False), patch.object(
            server, "_check_health", return_value=False
        ), patch.object(lv.time, "sleep", return_value=None), patch(
            "subprocess.Popen"
        ) as mock_popen:
            result = server.start()
        assert result is False  # never answered -> times out, does not spawn
        assert server.process is None
        mock_popen.assert_not_called()
    finally:
        fcntl.flock(held_fd, fcntl.LOCK_UN)
        held_fd.close()


def test_start_spawns_normally_when_lock_is_free(tmp_path, monkeypatch):
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)
    port = 18082
    server = lv.LlamaServer(lv.MODEL_PATH, port=port)

    fake_process = MagicMock()
    fake_process.poll.return_value = None
    fake_process.pid = 42

    with patch.object(server, "_is_port_in_use", return_value=False), patch.object(
        server, "_check_health", return_value=True
    ), patch("subprocess.Popen", return_value=fake_process), patch.object(
        lv.time, "sleep", return_value=None
    ):
        result = server.start()

    assert result is True
    assert server._started is True
    # Lock file must exist and be unlocked after start() returns (released).
    lock_path = tmp_path / f"llama-server-{port}.lock"
    assert lock_path.exists()
    check_fd = open(lock_path, "w")
    # Should be acquirable immediately -- proves start() released its lock.
    fcntl.flock(check_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fcntl.flock(check_fd, fcntl.LOCK_UN)
    check_fd.close()


# ── Part 2: sequential-swap arbiter ─────────────────────────────────────────


def _load_fake_primary():
    with patch.object(lv, "LlamaServer", FakeServer), patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        assert loader.load_primary() is True
    return loader


def test_ensure_planner_evicts_loaded_primary_and_loads():
    loader = _load_fake_primary()
    assert loader.is_loaded() is True

    with patch.object(lv, "LlamaServer", FakeServer), patch(
        "pathlib.Path.exists", return_value=True
    ), patch.object(lv, "probe_port_health", return_value=False):
        planner = pl.get_planner_loader()
        result = planner.ensure_planner()

    assert result is True
    assert planner.is_loaded() is True
    assert loader.is_loaded() is False  # evicted


def test_ensure_model_evicts_loaded_planner_and_loads():
    # Load planner first
    with patch.object(lv, "LlamaServer", FakeServer), patch(
        "pathlib.Path.exists", return_value=True
    ), patch.object(lv, "probe_port_health", return_value=False):
        planner = pl.get_planner_loader()
        assert planner.ensure_planner() is True

    assert planner.is_loaded() is True

    with patch.object(lv, "LlamaServer", FakeServer), patch(
        "pathlib.Path.exists", return_value=True
    ):
        loader = lv.get_loader()
        result = loader.ensure_model()

    assert result is True
    assert loader.is_loaded() is True
    assert planner.is_loaded() is False  # evicted


def test_ensure_planner_fails_closed_if_primary_port_still_answers_after_evict():
    """
    LlamaServer.stop() swallows exceptions and unconditionally clears its
    own 'loaded' state -- if the OS process didn't actually die (or another
    process owns the port), ensure_planner() must not proceed to load,
    since that would risk both models resident at once.
    """
    loader = _load_fake_primary()

    with patch.object(lv, "LlamaServer", FakeServer), patch(
        "pathlib.Path.exists", return_value=True
    ), patch.object(lv, "probe_port_health", return_value=True):  # port still bound
        planner = pl.get_planner_loader()
        result = planner.ensure_planner()

    assert result is False
    assert planner.is_loaded() is False


def test_ensure_model_deferred_when_swap_guard_held():
    """Non-blocking: if SWAP_GUARD is already held (another swap in flight
    in-process), ensure_model() must return False immediately, not block."""
    lv.SWAP_GUARD.acquire()
    try:
        with patch.object(lv, "LlamaServer", FakeServer), patch(
            "pathlib.Path.exists", return_value=True
        ):
            loader = lv.get_loader()
            t0 = time.time()
            result = loader.ensure_model()
            elapsed = time.time() - t0
    finally:
        lv.SWAP_GUARD.release()

    assert result is False
    assert elapsed < 1.0  # must not block waiting for the guard


def test_ensure_planner_deferred_when_swap_guard_held():
    lv.SWAP_GUARD.acquire()
    try:
        with patch.object(lv, "LlamaServer", FakeServer), patch(
            "pathlib.Path.exists", return_value=True
        ):
            planner = pl.get_planner_loader()
            t0 = time.time()
            result = planner.ensure_planner()
            elapsed = time.time() - t0
    finally:
        lv.SWAP_GUARD.release()

    assert result is False
    assert elapsed < 1.0


def test_ensure_model_thermal_restart_holds_swap_guard_against_concurrent_planner_swap():
    """
    Regression test for NEW-12 fix-up round 2, Bug 1: a thermal-triggered
    restart inside ensure_model()'s "already loaded" branch must hold
    SWAP_GUARD for its whole unload()->load_primary() window, not just the
    cold-load branch — otherwise a concurrent ensure_planner() (run in a
    different thread, as core/plannd.py:get_plan() actually does via
    run_in_executor) can observe "primary not loaded, port not responding"
    mid-restart and spawn the planner, landing both models resident.

    This forces the real interleaving with actual threads (not just
    inspecting the source) so it exercises the fix, not just the
    non-blocking-return behavior already covered by the other
    swap-guard-held tests above. The thermal restart's load_primary() is
    made to block on an Event so a background thread's ensure_planner()
    call is guaranteed to land while the guard is still held.
    """
    loader = _load_fake_primary()
    assert loader.is_loaded() is True

    reload_started = threading.Event()
    release_reload = threading.Event()
    real_load_primary = loader.load_primary

    def blocking_load_primary():
        reload_started.set()
        # Hold the "restart in progress" window open until the concurrent
        # ensure_planner() attempt (below) has had a chance to run and
        # observe the guard as held.
        release_reload.wait(timeout=5)
        return real_load_primary()

    fake_tm = MagicMock()
    fake_tm.restart_recommended = True
    fake_tm.current_threads = 4

    planner_result = {}

    def concurrent_planner_attempt():
        reload_started.wait(timeout=5)
        planner = pl.get_planner_loader()
        planner_result["result"] = planner.ensure_planner()
        planner_result["is_loaded"] = planner.is_loaded()
        release_reload.set()

    # IMPORTANT (belt-and-braces against a real 7B spawn, see NEW-12 fix-up
    # round 2, Bug 3 / the disclosed PID-1388 incident, and the identical
    # mistake caught live during this test's own development — see report):
    # `lv.LlamaServer` and `pathlib.Path.exists` must stay patched for the
    # ENTIRE span in which `real_load_primary()` (the true, unpatched
    # `ModelLoader.load_primary`, captured above so `blocking_load_primary`
    # can still exercise it) might run — including while the background
    # thread is alive — not just around the initial `_load_fake_primary()`
    # call. `real_load_primary()` looks up the module-level `LlamaServer`
    # name at call time, so if that patch has already exited by the time it
    # runs, it constructs a REAL `LlamaServer` against the real model path
    # and spawns an actual llama-server subprocess.
    # Also patch subprocess.Popen directly, matching the belt-and-braces
    # pattern used elsewhere in this file (see
    # test_start_reuses_existing_server_when_lock_held_by_another_process) —
    # a real spawn must be impossible even if the LlamaServer patch above
    # somehow failed to cover the call, not just unlikely.
    with patch.object(lv, "LlamaServer", FakeServer), patch(
        "pathlib.Path.exists", return_value=True
    ), patch.object(loader, "load_primary", side_effect=blocking_load_primary), patch(
        "core.thermal.get_thermal_manager", return_value=fake_tm
    ), patch(
        "subprocess.Popen"
    ) as mock_popen:
        t = threading.Thread(target=concurrent_planner_attempt)
        t.start()
        model_result = loader.ensure_model()
        t.join(timeout=10)

    mock_popen.assert_not_called()

    # The concurrent planner attempt must have been deferred (SWAP_GUARD
    # held by the in-flight thermal restart) — never loaded, never both
    # resident.
    assert planner_result.get("result") is False
    assert planner_result.get("is_loaded") is False
    # The thermal restart itself must still have completed successfully
    # once it held the guard uncontested (planner backed off, didn't fight
    # it).
    assert model_result is True
    assert loader.is_loaded() is True
