#!/usr/bin/env python3
"""Test for daemon_control plugin.

The socket-based capabilities (ping/status/health/task/cancel) need a
real daemon listening on the Unix socket. Starting the full
`core.daemon.Daemon` (via `main.py`) pre-loads the 7B model — out of
scope and unwanted for a plugin test. `core.daemon.DaemonServer` is just
the asyncio Unix socket server plus its handlers; it does not touch any
model. This test starts a bare `DaemonServer` (backed by a throwaway
StateStore/socket, both pointed at a temp dir) in a background thread,
confirming the assumption that the socket layer alone is lightweight
compared to the full daemon.
"""
import asyncio
import importlib.util
import tempfile
import threading
import time
from pathlib import Path

# _pathutil.py lives at ccos/plugins/_pathutil.py, two levels above this
# plugin's directory (test.py -> daemon_control/ -> system/ -> plugins/).
_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

import core.daemon as daemon_mod
from core.state import StateStore

from ccos.plugins.system.daemon_control.daemon_control import (
    daemon_cancel_task,
    daemon_check_pid_file,
    daemon_get_task,
    daemon_health,
    daemon_is_running,
    daemon_ping,
    daemon_status,
    test,
)

_TMP_DIR = Path(tempfile.mkdtemp(prefix="daemon_control_plugin_test_"))
_TEST_SOCKET = _TMP_DIR / "test.sock"
_TEST_DB = _TMP_DIR / "test_state.db"


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
        self.server = daemon_mod.DaemonServer(self.state)
        self.loop.run_until_complete(self._start())

    async def _start(self):
        from core.daemon import SOCKET_FILE

        SOCKET_FILE.unlink(missing_ok=True)
        self.server.server = await asyncio.start_unix_server(
            self.server._handle_client, path=str(SOCKET_FILE)
        )
        self.server.running = True
        self._ready.set()
        async with self.server.server:
            await self.server.server.serve_forever()

    def stop(self):
        if self.loop and self.server.server:
            self.loop.call_soon_threadsafe(self.server.server.close)


def _start_test_daemon():
    """Monkeypatch the module-global SOCKET_FILE to a temp path and start a bare server."""
    daemon_mod.SOCKET_FILE = _TEST_SOCKET
    state = StateStore(db_path=_TEST_DB)
    thread = _TestServerThread(state)
    thread.start()
    if not thread._ready.wait(timeout=5.0):
        raise RuntimeError("Test daemon socket server failed to start in time")
    time.sleep(0.1)  # let serve_forever() settle
    return thread, state


def test_status_capabilities_without_daemon():
    # Real environment daemon state — no assumption that it's running.
    result = daemon_is_running()
    assert isinstance(result, dict) and "running" in result
    pid_result = daemon_check_pid_file()
    assert isinstance(pid_result, dict) and "running" in pid_result
    print(f"[PASS] daemon_is_running()={result}, daemon_check_pid_file()={pid_result} against real env state")


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
        daemon_mod.SOCKET_FILE.unlink(missing_ok=True)


def test_self_test():
    result = test()
    assert result is True
    print("[PASS] Self-test passed")


if __name__ == "__main__":
    test_status_capabilities_without_daemon()
    test_socket_capabilities_against_lightweight_test_daemon()
    test_self_test()
    print("\nAll daemon_control tests passed!")
