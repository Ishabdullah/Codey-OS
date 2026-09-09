"""
Regression tests for NEW-107 / NEW-109 (core/observability.py).

NEW-109: `State.daemon_pid` used to return `psutil.Process(os.getpid()).pid`
-- always the CALLING process's own PID, never the daemon's, and
unconditionally `None` when psutil wasn't installed regardless of whether a
daemon was actually running. `State.uptime` read a `daemon_started_at`
value that's written once per daemon startup and never cleared on exit, so
it kept reporting a stale figure forever after that daemon exited --
producing the exact "pid: null, uptime_seconds: <large non-zero>"
contradiction NEW-109 reported live. The fix reads `DAEMON_PID_FILE`
(the same file `core.daemon.write_pid_file()`/`check_pid_file()` use) with
an `os.kill(pid, 0)` liveness check, and gates `uptime` on a live PID being
found AND on `daemon_started_at` not predating the PID file's own mtime
(the narrower startup-window version of the same contradiction -- see
`State.uptime`'s docstring).

NEW-107: `State.cpu_usage`/`State.memory_usage` report the CALLING
process's own CPU%/RSS, not system-wide or daemon-wide figures. Confirmed
during this round to be a deliberate, pre-existing split (see
`ccos/plugins/system/observability/observability.py`'s module docstring,
and `core/resource_gate.py`'s "Signal source 1" comment) from the
system-wide reads `core/resource_gate.py`/`main.py --status`'s
`"resources"` key already provide -- NOT re-pointed at the daemon or the
system here (doing so would also break
`ccos/plugins/system/observability/test.py::
test_memory_usage_has_real_data`'s `rss_mb > 0` assertion whenever no
daemon is running, which is the common case in this test suite). Instead,
`get_full_status()`'s `"memory"`/`"cpu"` blocks now carry an explicit
`"scope": "process"` label so the output is no longer misleading about
what it measures.

Isolation note: `State.uptime`/`State.daemon_pid` read the REAL,
shared `~/.codeyOS/state.db` (`core.state.get_state_store()`) --
`tests/conftest.py`'s autouse isolation fixture only redirects
telemetry's `METRICS_DIR`, not this. `_isolated_daemon_started_at`
below saves and restores the real `daemon_started_at` value around every
test in this module so a test run never leaves that shared value mutated
for whatever else reads it afterward (e.g. a live daemon's own
`_handle_health`).
"""

import os
import time

import pytest

import core.observability as observability


@pytest.fixture(autouse=True)
def _isolated_daemon_started_at():
    store = observability.get_state_store()
    original = store.get("daemon_started_at", 0)
    try:
        yield
    finally:
        store.set("daemon_started_at", original)


def _reload_state():
    observability.reset_state()
    return observability.get_state()


def test_daemon_pid_none_when_no_pid_file(tmp_path, monkeypatch):
    """No PID file at all -> no daemon running -> None."""
    monkeypatch.setattr(observability, "DAEMON_PID_FILE", tmp_path / "codeyOS.pid")
    state = _reload_state()
    assert state.daemon_pid is None


def test_daemon_pid_none_for_stale_pid_file(tmp_path, monkeypatch):
    """PID file points at a PID that no longer exists -> None, not a guess."""
    pid_file = tmp_path / "codeyOS.pid"
    # A PID essentially guaranteed not to be alive in this test process's
    # namespace.
    pid_file.write_text("999999")
    monkeypatch.setattr(observability, "DAEMON_PID_FILE", pid_file)
    state = _reload_state()
    assert state.daemon_pid is None


def test_daemon_pid_returns_real_pid_when_alive(tmp_path, monkeypatch):
    """PID file points at a live PID (this test process itself) -> that PID."""
    pid_file = tmp_path / "codeyOS.pid"
    pid_file.write_text(str(os.getpid()))
    monkeypatch.setattr(observability, "DAEMON_PID_FILE", pid_file)
    state = _reload_state()
    assert state.daemon_pid == os.getpid()


def test_uptime_is_zero_when_no_daemon_running_even_if_started_at_stale(tmp_path, monkeypatch):
    """
    NEW-109's core contradiction: a stale `daemon_started_at` in the state
    store must not produce a non-zero uptime once no live daemon is found.
    """
    monkeypatch.setattr(observability, "DAEMON_PID_FILE", tmp_path / "codeyOS.pid")
    state = _reload_state()
    state.state_store.set("daemon_started_at", 1)  # deliberately stale/ancient
    assert state.daemon_pid is None
    assert state.uptime == 0


def test_uptime_nonzero_when_daemon_pid_alive_and_started_at_fresh(tmp_path, monkeypatch):
    """
    A live daemon PID plus a `daemon_started_at` that is NOT older than the
    PID file's own mtime -> a real uptime. Mirrors real startup ordering
    (`core/daemon.py`'s `Daemon.run()` writes the PID file, then
    `_main_loop()` records `daemon_started_at` a little later) by backdating
    both the PID file's mtime and `daemon_started_at` to the same instant.
    """
    pid_file = tmp_path / "codeyOS.pid"
    pid_file.write_text(str(os.getpid()))
    started_at = int(time.time()) - 42
    os.utime(pid_file, (started_at, started_at))
    monkeypatch.setattr(observability, "DAEMON_PID_FILE", pid_file)
    state = _reload_state()
    state.state_store.set("daemon_started_at", started_at)
    assert state.daemon_pid == os.getpid()
    assert state.uptime >= 42


def test_uptime_zero_during_startup_window_before_started_at_recorded(tmp_path, monkeypatch):
    """
    NEW-109 startup-window case: the PID file was (re)written by the
    CURRENT daemon run, but `daemon_started_at` in the state store still
    holds a value from a PREVIOUS run (predates the PID file's mtime).
    `uptime` must report 0 (unknown), not the stale previous run's figure,
    even though `daemon_pid` correctly finds a live PID.
    """
    pid_file = tmp_path / "codeyOS.pid"
    pid_file.write_text(str(os.getpid()))
    # PID file's mtime is "now" (just written). daemon_started_at holds an
    # old value from a previous run -- predates this PID file write.
    monkeypatch.setattr(observability, "DAEMON_PID_FILE", pid_file)
    state = _reload_state()
    state.state_store.set("daemon_started_at", int(time.time()) - 9999)
    assert state.daemon_pid == os.getpid()
    assert state.uptime == 0


def test_pid_and_uptime_never_contradict(tmp_path, monkeypatch):
    """
    Direct regression for NEW-109's reported symptom: pid is None and
    uptime is simultaneously non-zero must never both be true.
    """
    monkeypatch.setattr(observability, "DAEMON_PID_FILE", tmp_path / "codeyOS.pid")
    state = _reload_state()
    state.state_store.set("daemon_started_at", 1)
    status = state.get_full_status()
    assert status["daemon"]["pid"] is None
    assert status["daemon"]["uptime_seconds"] == 0


def test_memory_and_cpu_usage_labeled_process_scope():
    """
    NEW-107 labeling fix: get_full_status()'s memory/cpu blocks say what
    they measure, without changing memory_usage()/cpu_usage()'s own
    return shape (still pinned to rss_mb/vms_mb by the CCOS plugin test).
    """
    state = _reload_state()
    status = state.get_full_status()
    assert status["memory"]["scope"] == "process"
    assert status["cpu"]["scope"] == "process"
    assert "rss_mb" in status["memory"]["usage"]
    assert "vms_mb" in status["memory"]["usage"]
