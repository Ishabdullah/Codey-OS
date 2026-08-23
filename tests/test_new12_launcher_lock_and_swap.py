"""
NEW-12 regression tests: cross-process start lock for LlamaServer.

Part 1 (core/loader_v2.py):
  - LlamaServer.__init__ takes an explicit port (default: SERVER_PORT).
  - LlamaServer.start() takes a per-port flock'd lock file around its
    check-port-then-spawn critical section; if another process holds the
    lock, it polls for that process's server to come up and reuses it
    instead of double-spawning.

M1-D (2026-08-23): this file used to also have a "Part 2" covering the
sequential-swap arbiter between the primary (7B) ModelLoader and a
dedicated planner (1.5B) PlannerLoader — ModelLoader.ensure_model() and
PlannerLoader.ensure_planner() mutually evicting each other via
core/loader_v2.py's SWAP_GUARD, and PlannerLoader failing closed if it
couldn't confirm the primary's port was actually free. core/planner_loader.py
(and the dedicated planner process/server it managed) is deleted — planning
now shares the single primary server, so there is no second side left to
swap against, and Part 2's tests are removed along with it, not adapted.
SWAP_GUARD itself survives (see core/loader_v2.py's own updated docstring)
for an unrelated, still-real race — this file's remaining scope (Part 1
only) doesn't touch that race at all.

All tests use a fake LlamaServer / mocked subprocess — no real
llama-server process is spawned.
"""
import fcntl
from unittest.mock import MagicMock, patch

import pytest

import core.loader_v2 as lv
import core.resource_gate as rg
import utils.config as cfg


@pytest.fixture(autouse=True)
def reset_singletons():
    lv._loader = None
    yield
    lv._loader = None


@pytest.fixture(autouse=True)
def fake_resource_gate(monkeypatch):
    """
    This file's own concern is the cross-process start lock (Part 1), not
    the resource gate (that's tests/test_loader_resource_gate.py) — patch
    core.resource_gate's slot functions to fixed, fast, always-admitting
    stand-ins so these tests stay deterministic and don't touch a real
    /proc/meminfo read, a real cross-process state file, or the (up to 10s)
    confirm_resident_and_mark_slot() polling loop. `lv.rg` is this same
    module object (`import core.resource_gate as rg`), so patching the
    attributes on `rg` here covers that call site.
    """
    fake_decision = MagicMock(admitted=True, estimated_cost_bytes=1024, reason="ok")
    monkeypatch.setattr(rg, "reserve_slot", lambda *a, **k: (fake_decision, "fake-slot-id"))
    monkeypatch.setattr(rg, "mark_resident", lambda *a, **k: True)
    monkeypatch.setattr(rg, "release_slot", lambda *a, **k: True)
    monkeypatch.setattr(rg, "read_meminfo", lambda *a, **k: {"MemAvailable": 10**10})
    yield


# ── Part 1: cross-process lock ──────────────────────────────────────────────


def test_llama_server_accepts_explicit_port_defaulting_to_server_port():
    s1 = lv.LlamaServer(cfg.MODEL_PATH)
    assert s1.port == lv.SERVER_PORT
    s2 = lv.LlamaServer(cfg.MODEL_PATH, port=9999)
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
        server = lv.LlamaServer(cfg.MODEL_PATH, port=port)
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
    server = lv.LlamaServer(cfg.MODEL_PATH, port=port)

    fake_process = MagicMock()
    fake_process.poll.return_value = None
    fake_process.pid = 42

    with patch.object(server, "_is_port_in_use", return_value=False), patch.object(
        server, "_check_health", return_value=True
    ), patch("subprocess.Popen", return_value=fake_process) as mock_popen, patch.object(
        lv.time, "sleep", return_value=None
    ):
        result = server.start()

    assert result is True
    assert server._started is True
    # M1-C (NEW-162): --jinja and --reasoning-format deepseek must be made
    # explicit in the spawn command rather than left to the binary's default.
    spawned_cmd = mock_popen.call_args[0][0]
    assert "--jinja" in spawned_cmd
    assert "--reasoning-format" in spawned_cmd
    assert spawned_cmd[spawned_cmd.index("--reasoning-format") + 1] == "deepseek"
    # Lock file must exist and be unlocked after start() returns (released).
    lock_path = tmp_path / f"llama-server-{port}.lock"
    assert lock_path.exists()
    check_fd = open(lock_path, "w")
    # Should be acquirable immediately -- proves start() released its lock.
    fcntl.flock(check_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fcntl.flock(check_fd, fcntl.LOCK_UN)
    check_fd.close()
