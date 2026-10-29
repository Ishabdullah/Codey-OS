#!/usr/bin/env python3
"""Test for daemon_control plugin.

The socket-based capabilities (ping/status/health/task/cancel) need a
real daemon listening on the Unix socket. Starting the full
`core.daemon.Daemon` (via `main.py`) pre-loads the primary model — out of
scope and unwanted for a plugin test. `core.daemon.DaemonServer` is just
the asyncio Unix socket server plus its handlers; it does not touch any
model. This test starts a bare `DaemonServer` (backed by a throwaway
StateStore/socket, both pointed at a temp dir) in a background thread,
confirming the assumption that the socket layer alone is lightweight
compared to the full daemon.
"""
import asyncio
import importlib.util
import os
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

# _pathutil.py lives at ccos/plugins/_pathutil.py, two levels above this
# plugin's directory (test.py -> daemon_control/ -> system/ -> plugins/).
_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

import core.daemon as daemon_mod
from core.daemon_config import DaemonPaths
from core.process_identity import LifecycleRecord
from core.state import StateStore

from ccos.plugins.system.daemon_control.daemon_control import (
    daemon_cancel_task,
    daemon_check_pid_file,
    daemon_get_task,
    daemon_health,
    daemon_ping,
    daemon_status,
    daemon_is_running,
    test as _plugin_self_test,
)

_TMP_DIR = Path(tempfile.mkdtemp(prefix="daemon_control_plugin_test_"))
_TEST_SOCKET = _TMP_DIR / "test.sock"
_TEST_DB = _TMP_DIR / "test_state.db"
_TEST_PATHS = DaemonPaths(_TMP_DIR / "fixture.pid", _TEST_SOCKET, _TMP_DIR / "fixture.log")


class _TestServerThread(threading.Thread):
    """Runs a bare DaemonServer (no model loading) on a temp socket."""

    def __init__(self, state):
        super().__init__(daemon=True)
        self.state = state
        self.loop = None
        self.server = None
        self._ready = threading.Event()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.server = daemon_mod.DaemonServer(self.state, paths=_TEST_PATHS)
        try:
            self.loop.run_until_complete(self._start())
        except asyncio.CancelledError:
            pass  # fixture stop closes serve_forever
        finally:
            if self.server.server:
                self.loop.run_until_complete(self.server.server.wait_closed())
            self.loop.close()

    async def _start(self):
        _TEST_SOCKET.unlink(missing_ok=True)
        self.server.server = await asyncio.start_unix_server(
            self.server._handle_client, path=str(_TEST_SOCKET)
        )
        self.server.running = True
        self._ready.set()
        async with self.server.server:
            await self.server.server.serve_forever()

    def stop(self):
        if self.loop and self.server.server:
            self.loop.call_soon_threadsafe(self.server.server.close)


def _start_test_daemon():
    """Start a bare fixture socket server with explicit paths and self identity."""
    with LifecycleRecord(_TEST_PATHS.pid_file, "codeyOS") as record:
        record.publish(os.getpid())
    state = StateStore(db_path=_TEST_DB)
    thread = _TestServerThread(state)
    thread.start()
    if not thread._ready.wait(timeout=5.0):
        raise RuntimeError("Test daemon socket server failed to start in time")
    time.sleep(0.1)  # let serve_forever() settle
    return thread, state


@patch("ccos.plugins.system.daemon_control.daemon_control.resolve_daemon_paths", lambda: _TEST_PATHS)
@patch.object(daemon_mod, "resolve_daemon_paths", lambda: _TEST_PATHS)
def test_status_capabilities_without_daemon():
    # Explicit disposable paths; no real environment daemon state.
    result = daemon_is_running()
    assert isinstance(result, dict) and "running" in result
    pid_result = daemon_check_pid_file()
    assert isinstance(pid_result, dict) and "running" in pid_result
    print(f"[PASS] daemon_is_running()={result}, daemon_check_pid_file()={pid_result} against isolated state")


@patch.object(daemon_mod, "resolve_daemon_paths", lambda: _TEST_PATHS)
def test_socket_capabilities_against_lightweight_test_daemon():
    thread, state = _start_test_daemon()
    try:
        ping = daemon_ping()
        assert ping["status"] == "ok" and ping["message"] == "pong", f"Unexpected ping: {ping}"
        print(f"[PASS] daemon_ping() -> {ping}")

        status = daemon_status()
        assert status["status"] == "ok" and "tasks" in status, f"Unexpected status: {status}"
        print(f"[PASS] daemon_status() -> {status}")

        health = daemon_health()
        assert health["status"] == "ok" and health["healthy"] is True, f"Unexpected health: {health}"
        print(f"[PASS] daemon_health() -> {health}")

        task_id = state.add_task("test task for daemon_control plugin")
        got = daemon_get_task(task_id)
        assert got["status"] == "ok" and got["task"]["id"] == task_id, f"Unexpected task lookup: {got}"
        print(f"[PASS] daemon_get_task({task_id}) -> {got}")

        listed = daemon_get_task()
        assert listed["status"] == "ok" and any(t["id"] == task_id for t in listed["tasks"])
        print(f"[PASS] daemon_get_task() list includes task {task_id}")

        cancelled = daemon_cancel_task(task_id)
        assert cancelled["status"] == "ok", f"Unexpected cancel result: {cancelled}"
        # state.cancel_task() on a still-pending task sets a cancellation flag
        # for the executor to observe rather than flipping status immediately
        # (only a *running* task's status flips to "failed" on cancel).
        flag = state.get(f"task_cancelled_{task_id}")
        assert flag == "1", f"Expected cancellation flag set, got {flag!r}"
        print(f"[PASS] daemon_cancel_task({task_id}) -> {cancelled}, cancellation flag set")
    finally:
        thread.stop()
        thread.join(timeout=5)
        assert not thread.is_alive()
        state.close()
        _TEST_SOCKET.unlink(missing_ok=True)
        with LifecycleRecord(_TEST_PATHS.pid_file, "codeyOS") as record:
            record.cleanup(record.inspect(), current_self=True)


@patch("ccos.plugins.system.daemon_control.daemon_control.resolve_daemon_paths", lambda: _TEST_PATHS)
def test_self_test():
    result = _plugin_self_test()
    assert result is True
    print("[PASS] Self-test passed")


if __name__ == "__main__":
    test_status_capabilities_without_daemon()
    test_socket_capabilities_against_lightweight_test_daemon()
    test_self_test()
    print("\nAll daemon_control tests passed!")
