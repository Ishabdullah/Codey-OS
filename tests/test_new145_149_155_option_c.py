"""
NEW-145/NEW-149/NEW-155 chain, Option C (2026-08-27) — respawn-on-upgrade
at interactive attach, plus the separate NEW-155 `_ever_spawned` hygiene
fix. See CODEY_MASTER_PLAN.md Appendix A's 7.4b-C entry for the full
design and the four judgment calls recorded there.

Two independent concerns, tested separately per this round's own
"separate commit/hunk" instruction:

  - Change 1 (Option C): `LlamaServer._resident_n_ctx_if_smaller()`,
    `core.daemon.daemon_task_in_progress()`, and the `allow_upgrade`
    wiring into exactly two of `start()`'s three reuse-return branches.
  - Change 2 (NEW-155 hygiene): `ModelLoader.unload()` resets
    `_ever_spawned` so the watchdog's crash-restart gate stops being
    permanently sticky-True after a single genuine spawn.

All tests use fakes/mocks — no real llama-server process is spawned
(RAM-discipline rule, CLAUDE.md rule 2), and no real subprocess is killed
(os.kill/os.killpg are patched wherever a kill would otherwise fire).
"""
import asyncio
import fcntl
from unittest.mock import MagicMock, patch

import pytest

import core.daemon as daemon_mod
import core.loader_v2 as lv
import core.resource_gate as rg


def _run(coro):
    """This project has no pytest-asyncio dependency (see
    tests/test_daemon_release_model_slot.py's own note) — drive an async
    handler coroutine directly via asyncio.run() instead."""
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def reset_singletons():
    lv._loader = None
    yield
    lv._loader = None


# ── _resident_n_ctx_if_smaller() / _resolve_resident_pid_and_n_ctx() ────────
#
# NEW-200 (confirmed in CODEY_MASTER_PLAN.md / core/resource_gate.py:
# resolve_port_owner_pid()'s own docstring): /proc/net/tcp[6] are
# PermissionError for EVERY caller on this project's real target device,
# so resolution here must check the resource-gate slot store FIRST
# (find_resident_slot()) and fall back to the /proc scan
# (resolve_port_owner_pid()) only when the store has nothing — the
# ordering these tests exist to pin down, not just the end result. Every
# test in this section explicitly patches find_resident_slot() (rather
# than relying on a shared autouse default) so it's unambiguous which
# resolution path each one is exercising.


def test_resident_n_ctx_if_smaller_slot_store_path_returns_none_when_no_slot(monkeypatch):
    server = lv.LlamaServer("/fake/model.gguf", port=1234, n_ctx=65536)
    monkeypatch.setattr(rg, "find_resident_slot", lambda *a, **k: None)
    monkeypatch.setattr(rg, "resolve_port_owner_pid", lambda port: None)
    assert server._resident_n_ctx_if_smaller() is None


def test_resident_n_ctx_if_smaller_slot_store_path_used_first(monkeypatch):
    """The slot store, not the /proc scan, must be consulted first — and
    when it has a match, the /proc scan must not even be attempted."""
    server = lv.LlamaServer("/fake/model.gguf", port=1234, n_ctx=65536)
    monkeypatch.setattr(
        rg, "find_resident_slot", lambda *a, **k: {"pid": 999, "n_ctx": 16384}
    )
    monkeypatch.setattr(rg, "pid_cmdline_contains", lambda pid, needle: True)
    proc_scan = MagicMock(side_effect=AssertionError("should not fall back to /proc scan"))
    monkeypatch.setattr(rg, "resolve_port_owner_pid", proc_scan)
    assert server._resident_n_ctx_if_smaller() == 16384
    proc_scan.assert_not_called()


def test_resident_n_ctx_if_smaller_slot_store_path_returns_none_when_cmdline_unconfirmed(
    monkeypatch,
):
    """A slot record exists, but the PID it names no longer looks like a
    llama-server (recycled PID) — must not treat it as a real match."""
    server = lv.LlamaServer("/fake/model.gguf", port=1234, n_ctx=65536)
    monkeypatch.setattr(
        rg, "find_resident_slot", lambda *a, **k: {"pid": 999, "n_ctx": 16384}
    )
    monkeypatch.setattr(rg, "pid_cmdline_contains", lambda pid, needle: False)
    assert server._resident_n_ctx_if_smaller() is None


def test_resident_n_ctx_if_smaller_slot_store_path_returns_none_when_equal_or_larger(
    monkeypatch,
):
    server = lv.LlamaServer("/fake/model.gguf", port=1234, n_ctx=16384)
    monkeypatch.setattr(
        rg, "find_resident_slot", lambda *a, **k: {"pid": 999, "n_ctx": 65536}
    )
    monkeypatch.setattr(rg, "pid_cmdline_contains", lambda pid, needle: True)
    assert server._resident_n_ctx_if_smaller() is None


def test_resident_n_ctx_if_smaller_proc_fallback_used_when_no_slot(monkeypatch):
    """NEW-200's fallback path, kept for portability (a no-op in
    production on this device, but exercised here so a regression in the
    fallback logic itself is still caught)."""
    server = lv.LlamaServer("/fake/model.gguf", port=1234, n_ctx=65536)
    monkeypatch.setattr(rg, "find_resident_slot", lambda *a, **k: None)
    monkeypatch.setattr(rg, "resolve_port_owner_pid", lambda port: 999)
    monkeypatch.setattr(rg, "pid_cmdline_contains", lambda pid, needle: True)
    monkeypatch.setattr(rg, "resolve_spawned_n_ctx", lambda pid: 16384)
    assert server._resident_n_ctx_if_smaller() == 16384


def test_resident_n_ctx_if_smaller_proc_fallback_returns_none_when_pid_unresolved(monkeypatch):
    server = lv.LlamaServer("/fake/model.gguf", port=1234, n_ctx=65536)
    monkeypatch.setattr(rg, "find_resident_slot", lambda *a, **k: None)
    monkeypatch.setattr(rg, "resolve_port_owner_pid", lambda port: None)
    assert server._resident_n_ctx_if_smaller() is None


def test_resident_n_ctx_if_smaller_fails_toward_none_on_exception(monkeypatch):
    """Best-effort diagnostic only — any resolution failure must fail
    toward 'nothing to upgrade,' never toward a false positive that could
    trigger an unwanted kill."""
    server = lv.LlamaServer("/fake/model.gguf", port=1234, n_ctx=65536)

    def _boom(*a, **k):
        raise OSError("simulated slot-store/proc read failure")

    monkeypatch.setattr(rg, "find_resident_slot", _boom)
    assert server._resident_n_ctx_if_smaller() is None


# ── core.daemon.daemon_task_in_progress() ───────────────────────────────────


def test_daemon_task_in_progress_false_when_daemon_not_running(monkeypatch):
    monkeypatch.setattr(daemon_mod, "is_daemon_running", lambda: False)
    assert daemon_mod.daemon_task_in_progress() is False


def test_daemon_task_in_progress_true_when_running_active_positive(monkeypatch):
    monkeypatch.setattr(daemon_mod, "is_daemon_running", lambda: True)
    monkeypatch.setattr(
        daemon_mod,
        "send_command",
        lambda cmd, timeout=3: {"status": "ok", "tasks": {"running_active": 1}},
    )
    assert daemon_mod.daemon_task_in_progress() is True


def test_daemon_task_in_progress_false_when_running_active_zero(monkeypatch):
    monkeypatch.setattr(daemon_mod, "is_daemon_running", lambda: True)
    monkeypatch.setattr(
        daemon_mod,
        "send_command",
        lambda cmd, timeout=3: {"status": "ok", "tasks": {"running_active": 0}},
    )
    assert daemon_mod.daemon_task_in_progress() is False


def test_daemon_task_in_progress_fails_closed_on_send_command_exception(monkeypatch):
    monkeypatch.setattr(daemon_mod, "is_daemon_running", lambda: True)

    def _boom(cmd, timeout=3):
        raise ConnectionError("simulated socket failure")

    monkeypatch.setattr(daemon_mod, "send_command", _boom)
    assert daemon_mod.daemon_task_in_progress() is True


def test_daemon_task_in_progress_fails_closed_on_malformed_response(monkeypatch):
    monkeypatch.setattr(daemon_mod, "is_daemon_running", lambda: True)
    monkeypatch.setattr(daemon_mod, "send_command", lambda cmd, timeout=3: {"status": "ok"})
    assert daemon_mod.daemon_task_in_progress() is True


# ── _handle_status()'s age-filtered running_active ──────────────────────────


class _FakeState:
    def __init__(self, tasks_by_status, all_state=None):
        self._tasks_by_status = tasks_by_status
        self._all_state = all_state or {}

    def get_tasks_by_status(self, status):
        return self._tasks_by_status.get(status, [])

    def get_all(self):
        return self._all_state


class _FakeConfig:
    def __init__(self, task_timeout=1800):
        self._task_timeout = task_timeout

    def get(self, section, key, default=None):
        if section == "tasks" and key == "task_timeout":
            return self._task_timeout
        return default


def test_handle_status_running_active_excludes_stale_rows():
    import time

    now = int(time.time())
    fresh_task = {"id": 1, "status": "running", "started_at": now - 10}
    stale_task = {"id": 2, "status": "running", "started_at": now - 5000}
    handler = daemon_mod.DaemonServer.__new__(daemon_mod.DaemonServer)
    handler.state = _FakeState({"pending": [], "running": [fresh_task, stale_task], "done": []})
    handler._config = _FakeConfig(task_timeout=1800)

    result = _run(handler._handle_status({}))
    assert result["tasks"]["running"] == 2
    assert result["tasks"]["running_active"] == 1


def test_handle_status_running_active_zero_when_all_stale():
    import time

    now = int(time.time())
    stale_task = {"id": 1, "status": "running", "started_at": now - 5000}
    handler = daemon_mod.DaemonServer.__new__(daemon_mod.DaemonServer)
    handler.state = _FakeState({"pending": [], "running": [stale_task], "done": []})
    handler._config = _FakeConfig(task_timeout=1800)

    result = _run(handler._handle_status({}))
    assert result["tasks"]["running"] == 1
    assert result["tasks"]["running_active"] == 0


def test_handle_status_running_active_reads_configured_non_default_timeout():
    """Code-reviewer negative control (2026-08-27): hardcoding a literal
    `1800` inline instead of reading `task_timeout` from config still
    passed the two tests above, because both use the default-matching
    value of 1800 — a hardcode would coincidentally produce the same
    result. This test uses a NON-default `task_timeout` (60s) with a task
    old enough to be stale against that configured value but still fresh
    against the (wrong, hardcoded) 1800 default, so a silent hardcode
    would make this test fail: `running_active` would incorrectly read 1
    instead of 0 if the config value isn't actually being read."""
    import time

    now = int(time.time())
    # 100s old: older than a configured 60s task_timeout (must count as
    # stale), but younger than the unrelated 1800s default/health-check
    # constant (would incorrectly still count as active under a hardcode).
    task = {"id": 1, "status": "running", "started_at": now - 100}
    handler = daemon_mod.DaemonServer.__new__(daemon_mod.DaemonServer)
    handler.state = _FakeState({"pending": [], "running": [task], "done": []})
    handler._config = _FakeConfig(task_timeout=60)

    result = _run(handler._handle_status({}))
    assert result["tasks"]["running"] == 1
    assert result["tasks"]["running_active"] == 0


# ── LlamaServer.__init__'s allow_upgrade flag ───────────────────────────────


def test_allow_upgrade_defaults_false():
    server = lv.LlamaServer("/fake/model.gguf")
    assert server.allow_upgrade is False


def test_allow_upgrade_explicit_true():
    server = lv.LlamaServer("/fake/model.gguf", allow_upgrade=True)
    assert server.allow_upgrade is True


# ── start()'s allow_upgrade wiring ───────────────────────────────────────────


@pytest.fixture
def fake_resource_gate(monkeypatch):
    """Deterministic, fast resource_gate stand-ins — this file's concern
    is the allow_upgrade wiring, not resource_gate's own admission math."""
    fake_decision = MagicMock(admitted=True, estimated_cost_bytes=1024, reason="ok")
    monkeypatch.setattr(rg, "reserve_slot", lambda *a, **k: (fake_decision, "fake-slot-id"))
    monkeypatch.setattr(rg, "mark_resident", lambda *a, **k: True)
    monkeypatch.setattr(rg, "release_slot", lambda *a, **k: True)
    monkeypatch.setattr(rg, "read_meminfo", lambda *a, **k: {"MemAvailable": 10**10})
    monkeypatch.setattr(rg, "find_resident_slot", lambda *a, **k: None)
    yield


def test_start_without_allow_upgrade_never_checks_for_smaller_resident(tmp_path, monkeypatch):
    """Today's existing behavior, unchanged: allow_upgrade defaults False,
    so even a genuinely-smaller resident server is reused as-is, and the
    (expensive) resident-n_ctx resolution is never even attempted."""
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)
    port = 28001
    server = lv.LlamaServer("/fake/model.gguf", port=port, n_ctx=65536)
    assert server.allow_upgrade is False

    with patch.object(server, "_is_port_in_use", return_value=True), patch.object(
        server, "_resident_n_ctx_if_smaller"
    ) as mock_resolve:
        result = server.start()

    assert result is True
    assert server._started is True
    mock_resolve.assert_not_called()


def test_start_allow_upgrade_true_but_no_smaller_resident_reuses_normally(tmp_path, monkeypatch):
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)
    port = 28002
    server = lv.LlamaServer("/fake/model.gguf", port=port, n_ctx=65536, allow_upgrade=True)

    with patch.object(server, "_is_port_in_use", return_value=True), patch.object(
        server, "_resident_n_ctx_if_smaller", return_value=None
    ), patch.object(server, "_upgrade_resident_if_safe") as mock_upgrade:
        result = server.start()

    assert result is True
    assert server._started is True
    mock_upgrade.assert_not_called()


def test_start_allow_upgrade_true_daemon_busy_falls_back_to_reuse(tmp_path, monkeypatch):
    """Fast path finds a smaller resident and falls through to the lock;
    under the lock, the daemon reports busy — must fall back to today's
    reuse behavior, never kill."""
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)
    port = 28003
    server = lv.LlamaServer("/fake/model.gguf", port=port, n_ctx=65536, allow_upgrade=True)

    with patch.object(server, "_is_port_in_use", return_value=True), patch.object(
        server, "_resident_n_ctx_if_smaller", return_value=16384
    ), patch("core.daemon.daemon_task_in_progress", return_value=True):
        result = server.start()

    assert result is True
    assert server._started is True
    assert server.process is None  # nothing was spawned — pure reuse


def test_start_allow_upgrade_true_daemon_idle_kills_and_respawns(tmp_path, monkeypatch, fake_resource_gate):
    """The full happy path: daemon confirmed idle, resident PID
    re-confirmed under the lock, old server killed, port frees, genuine
    respawn at the caller's larger n_ctx."""
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)
    port = 28004
    server = lv.LlamaServer("/fake/model.gguf", port=port, n_ctx=65536, allow_upgrade=True)

    port_in_use_calls = {"n": 0}

    def _is_port_in_use():
        # True the first two times (fast-path check, post-lock re-check),
        # then False afterward (the post-kill poll loop confirming free).
        port_in_use_calls["n"] += 1
        return port_in_use_calls["n"] <= 2

    fake_process = MagicMock()
    fake_process.poll.return_value = None
    fake_process.pid = 4242

    killed_pids = []

    def _fake_kill(pid, wait_s=8.0):
        killed_pids.append(pid)

    with patch.object(server, "_is_port_in_use", side_effect=_is_port_in_use), patch.object(
        server, "_resident_n_ctx_if_smaller", return_value=16384
    ), patch("core.daemon.daemon_task_in_progress", return_value=False), patch.object(
        rg, "find_resident_slot", return_value={"pid": 9999, "n_ctx": 16384, "slot_id": "s1"}
    ), patch.object(rg, "pid_cmdline_contains", return_value=True), patch.object(
        lv, "_kill_single_pid_term_then_kill", _fake_kill
    ), patch("subprocess.Popen", return_value=fake_process), patch.object(
        server, "_check_health", return_value=True
    ), patch.object(lv.time, "sleep", return_value=None):
        result = server.start()

    assert result is True
    assert killed_pids == [9999]
    assert server.process is fake_process  # genuine spawn happened
    assert server._started is True


def test_start_allow_upgrade_true_daemon_idle_releases_old_slot_on_upgrade(
    tmp_path, monkeypatch, fake_resource_gate
):
    """Code-reviewer negative control (2026-08-27): deleting the
    `rg.release_slot(...)` call inside `_upgrade_resident_if_safe()`
    still left the full happy-path test above green, because
    `fake_resource_gate`'s `release_slot` stand-in is a bare
    `lambda *a, **k: True` that never records whether/how it was called.
    This test uses a real `MagicMock` for `release_slot` instead, so a
    slot-leak regression (the killed old server's resource-gate slot
    never being released, per this fix's own comment at
    `core/loader_v2.py:_upgrade_resident_if_safe()` `:485-499`) is
    actually caught: it must be called exactly once, with the OLD
    (undersized, now-killed) server's `slot_id` — not the new server's,
    which doesn't exist yet at this point in the upgrade."""
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)
    port = 28009
    server = lv.LlamaServer("/fake/model.gguf", port=port, n_ctx=65536, allow_upgrade=True)

    port_in_use_calls = {"n": 0}

    def _is_port_in_use():
        port_in_use_calls["n"] += 1
        return port_in_use_calls["n"] <= 2

    fake_process = MagicMock()
    fake_process.poll.return_value = None
    fake_process.pid = 4242

    old_slot = {"pid": 9999, "n_ctx": 16384, "slot_id": "old-slot-being-upgraded-away"}
    release_slot_mock = MagicMock(return_value=True)

    with patch.object(server, "_is_port_in_use", side_effect=_is_port_in_use), patch.object(
        server, "_resident_n_ctx_if_smaller", return_value=16384
    ), patch("core.daemon.daemon_task_in_progress", return_value=False), patch.object(
        rg, "find_resident_slot", return_value=old_slot
    ), patch.object(rg, "pid_cmdline_contains", return_value=True), patch.object(
        lv, "_kill_single_pid_term_then_kill", lambda pid, wait_s=8.0: None
    ), patch.object(
        rg, "release_slot", release_slot_mock
    ), patch("subprocess.Popen", return_value=fake_process), patch.object(
        server, "_check_health", return_value=True
    ), patch.object(lv.time, "sleep", return_value=None):
        result = server.start()

    assert result is True
    release_slot_mock.assert_called_once_with("old-slot-being-upgraded-away")


def test_start_allow_upgrade_true_never_uses_killpg(tmp_path, monkeypatch, fake_resource_gate):
    """The flagged deviation from this round's prompt: `_kill_single_pid_
    term_then_kill()` must use `os.kill()` on the single positively-
    identified PID, never `os.killpg()` — which would kill an entire
    foreign process group from a single resolved PID (broader than what
    was positively identified; see `core/embed_server.py:_kill_port_
    occupant()`'s own reviewed decision against exactly this for the
    identical foreign-port-occupant scenario, and this round's
    `_kill_single_pid_term_then_kill()` docstring for the full reasoning).
    Exercises the REAL kill helper (not a stand-in), only os.kill/os.getpgid
    themselves are mocked."""
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)
    port = 28007
    server = lv.LlamaServer("/fake/model.gguf", port=port, n_ctx=65536, allow_upgrade=True)

    port_in_use_calls = {"n": 0}

    def _is_port_in_use():
        port_in_use_calls["n"] += 1
        return port_in_use_calls["n"] <= 2

    fake_process = MagicMock()
    fake_process.poll.return_value = None
    fake_process.pid = 4242

    # First os.kill() call (SIGTERM) succeeds; the second (the liveness
    # poll, signal 0) reports the process already gone, so the wait loop
    # returns immediately instead of spinning against real wall-clock time
    # for the full 8s wait_s.
    kill_calls = []

    def _fake_os_kill(pid, sig):
        kill_calls.append((pid, sig))
        if len(kill_calls) >= 2:
            raise ProcessLookupError()

    with patch.object(server, "_is_port_in_use", side_effect=_is_port_in_use), patch.object(
        server, "_resident_n_ctx_if_smaller", return_value=16384
    ), patch("core.daemon.daemon_task_in_progress", return_value=False), patch.object(
        rg, "find_resident_slot", return_value={"pid": 9999, "n_ctx": 16384, "slot_id": "s1"}
    ), patch.object(rg, "pid_cmdline_contains", return_value=True), patch.object(
        lv.os, "kill", side_effect=_fake_os_kill
    ), patch.object(
        lv.os, "killpg"
    ) as mock_killpg, patch.object(
        lv.os, "getpgid"
    ) as mock_getpgid, patch(
        "subprocess.Popen", return_value=fake_process
    ), patch.object(server, "_check_health", return_value=True), patch.object(
        lv.time, "sleep", return_value=None
    ):
        result = server.start()

    assert result is True
    mock_killpg.assert_not_called()
    mock_getpgid.assert_not_called()
    # os.kill() was used, and against the one positively-identified PID.
    assert all(pid == 9999 for pid, _sig in kill_calls)
    assert len(kill_calls) >= 1


def test_start_allow_upgrade_true_reresolves_n_ctx_under_lock_not_just_pid(
    tmp_path, monkeypatch, fake_resource_gate
):
    """A residual-TOCTOU-adjacent gap the mandatory rule-4 review pass
    must see closed: the resident found undersized PRE-lock could already
    have died and been replaced by a CORRECTLY-sized server (another TUI
    attaching, or the watchdog's own respawn) by the time the lock is
    acquired. Gating the in-lock re-check on "a llama-server PID exists"
    alone would kill that new, already-adequate server for no reason — the
    in-lock re-resolve must also re-check n_ctx, not just the PID."""
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)
    port = 28008
    server = lv.LlamaServer("/fake/model.gguf", port=port, n_ctx=65536, allow_upgrade=True)

    with patch.object(server, "_is_port_in_use", return_value=True), patch.object(
        server, "_resident_n_ctx_if_smaller", return_value=16384
    ), patch("core.daemon.daemon_task_in_progress", return_value=False), patch.object(
        # Pre-lock: undersized (16384). In-lock re-resolve: already
        # upgraded to 65536 by someone else in the meantime.
        rg,
        "find_resident_slot",
        return_value={"pid": 9999, "n_ctx": 65536, "slot_id": "s1"},
    ), patch.object(rg, "pid_cmdline_contains", return_value=True), patch.object(
        lv, "_kill_single_pid_term_then_kill"
    ) as mock_kill:
        result = server.start()

    assert result is True
    assert server.process is None  # pure reuse — nothing was killed
    mock_kill.assert_not_called()


def test_start_allow_upgrade_true_port_stuck_fails_outright(tmp_path, monkeypatch, fake_resource_gate):
    """Judgment call 2 (2026-08-27 scoping pass): if the port never frees
    after killing the undersized resident server, start() must fail
    outright rather than silently falling back to reusing the (now dead)
    old server."""
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)
    port = 28005
    server = lv.LlamaServer("/fake/model.gguf", port=port, n_ctx=65536, allow_upgrade=True)

    def _always_in_use():
        return True

    # The port-free-wait loop reads real wall-clock time (`time.time()`)
    # to bound itself to ~10s — fake it forward past the deadline on the
    # loop's second read so this test doesn't actually block for 10
    # real seconds.
    time_calls = {"n": 0}

    def _fake_time():
        time_calls["n"] += 1
        return 0.0 if time_calls["n"] == 1 else 1000.0

    with patch.object(server, "_is_port_in_use", side_effect=_always_in_use), patch.object(
        server, "_resident_n_ctx_if_smaller", return_value=16384
    ), patch("core.daemon.daemon_task_in_progress", return_value=False), patch.object(
        rg, "find_resident_slot", return_value={"pid": 9999, "n_ctx": 16384, "slot_id": "s1"}
    ), patch.object(rg, "pid_cmdline_contains", return_value=True), patch.object(
        lv, "_kill_single_pid_term_then_kill", lambda pid, wait_s=8.0: None
    ), patch.object(lv.time, "sleep", return_value=None), patch.object(
        lv.time, "time", side_effect=_fake_time
    ):
        result = server.start()

    assert result is False


def test_start_wait_for_in_flight_branch_never_upgrades(tmp_path, monkeypatch, fake_resource_gate):
    """The wait-for-another-process's-in-flight-start() branch must never
    consult allow_upgrade at all — killing there would kill the OTHER
    process's own in-flight server, a new, worse bug (see start()'s own
    comment on this branch)."""
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)
    port = 28006
    lock_path = tmp_path / f"llama-server-{port}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    held_fd = open(lock_path, "w")
    fcntl.flock(held_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    try:
        server = lv.LlamaServer("/fake/model.gguf", port=port, n_ctx=65536, allow_upgrade=True)
        with patch.object(server, "_is_port_in_use", return_value=False), patch.object(
            server, "_check_health", return_value=True
        ), patch.object(server, "_resident_n_ctx_if_smaller") as mock_resolve, patch.object(
            server, "_upgrade_resident_if_safe"
        ) as mock_upgrade, patch.object(lv.time, "sleep", return_value=None):
            result = server.start()
        assert result is True
        mock_resolve.assert_not_called()
        mock_upgrade.assert_not_called()
    finally:
        fcntl.flock(held_fd, fcntl.LOCK_UN)
        held_fd.close()


# ── NEW-155 hygiene fix: unload() resets _ever_spawned ──────────────────────


def test_unload_resets_ever_spawned_after_genuine_spawn():
    loader = lv.ModelLoader()
    fake_server = MagicMock()
    fake_server.process = MagicMock(pid=1234)
    loader._server = fake_server
    loader._ever_spawned = True
    loader._loaded = True

    loader.unload()

    assert loader.was_ever_spawned() is False


def test_unload_noop_when_no_server_does_not_touch_ever_spawned():
    """unload() with no active server (already unloaded) must not
    spuriously flip _ever_spawned — only a genuine confirmed stop does."""
    loader = lv.ModelLoader()
    loader._server = None
    loader._ever_spawned = True

    loader.unload()

    assert loader.was_ever_spawned() is True
