"""
gui/server.py's `_write_gui_clients_count()` — Track 3 Phase 5a / 7.4
sub-task B (GUI half of the interactive-session signal).

`gui/server.py` is not a package member (no `gui/__init__.py`), so it's
loaded here via `importlib` from its file path rather than a normal
`import gui.server` — matching how `main.py` (also outside a package) is
already imported directly (`import main as main_mod`) elsewhere in this
test suite.

No real aiohttp server, websocket, or event loop is started anywhere in
this file — `clients` (a plain `Set[web.WebSocketResponse]`) is exercised
directly with plain placeholder objects standing in for real
`WebSocketResponse` instances, since `_write_gui_clients_count()` only
ever calls `len(clients)`.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_SERVER_PATH = Path(__file__).parent.parent / "gui" / "server.py"
_spec = importlib.util.spec_from_file_location("codey_gui_server_under_test", _SERVER_PATH)
gui_server = importlib.util.module_from_spec(_spec)
# gui/server.py reads sys.argv[1] at import time as an optional port
# override — save/restore around the import so pytest's own argv (e.g.
# `pytest tests/...`) isn't misread as a port number.
_saved_argv = sys.argv
sys.argv = [_saved_argv[0]] if _saved_argv else ["gui/server.py"]
try:
    _spec.loader.exec_module(gui_server)
finally:
    sys.argv = _saved_argv


@pytest.fixture(autouse=True)
def _clean_clients():
    """Every test starts from an empty `clients` set — it's process-global
    module state, otherwise tests would leak connections into each other."""
    gui_server.clients.clear()
    yield
    gui_server.clients.clear()


@pytest.fixture
def clients_file(tmp_path, monkeypatch):
    path = tmp_path / "gui-clients.count"
    monkeypatch.setattr(gui_server, "GUI_CLIENTS_FILE", path)
    return path


def test_write_gui_clients_count_zero_when_empty(clients_file):
    gui_server._write_gui_clients_count()
    assert clients_file.read_text().strip() == "0"


def test_write_gui_clients_count_reflects_current_size(clients_file):
    gui_server.clients.add(object())
    gui_server.clients.add(object())
    gui_server._write_gui_clients_count()
    assert clients_file.read_text().strip() == "2"


def test_write_gui_clients_count_updates_on_change(clients_file):
    ws = object()
    gui_server.clients.add(ws)
    gui_server._write_gui_clients_count()
    assert clients_file.read_text().strip() == "1"

    gui_server.clients.discard(ws)
    gui_server._write_gui_clients_count()
    assert clients_file.read_text().strip() == "0"


def test_write_gui_clients_count_unwritable_dir_does_not_raise(tmp_path, monkeypatch):
    # Point at a path whose parent can never be created (a file, not a
    # directory, sitting where a parent directory would need to go) so the
    # write fails — this must be swallowed (best-effort signal only), not
    # raised, since it's called from inside live websocket-handling code.
    blocker = tmp_path / "blocker"
    blocker.write_text("x")
    unwritable = blocker / "gui-clients.count"
    monkeypatch.setattr(gui_server, "GUI_CLIENTS_FILE", unwritable)
    gui_server._write_gui_clients_count()  # must not raise


def test_handle_ws_source_calls_write_on_connect_and_disconnect():
    # No real aiohttp WebSocketResponse/event loop is exercised here (see
    # this module's docstring) — this only verifies, by reading
    # handle_ws()'s own source, that `_write_gui_clients_count()` is still
    # wired to both `clients.add(ws)` and the `finally: clients.discard(ws)`
    # block. That wiring is real-connection behavior this file's other
    # tests don't exercise (they call `_write_gui_clients_count()`
    # directly); this is a cheap tripwire against someone adding a new
    # connect/disconnect path later that silently skips the write, without
    # standing up a full aiohttp test client. Not a substitute for
    # live-verifier actually opening a browser tab against a running GUI
    # server.
    import inspect

    source = inspect.getsource(gui_server.handle_ws)
    connect_idx = source.index("clients.add(ws)")
    finally_idx = source.index("finally:")
    discard_idx = source.index("clients.discard(ws)", finally_idx)

    connect_write_idx = source.index("_write_gui_clients_count()", connect_idx)
    disconnect_write_idx = source.index("_write_gui_clients_count()", discard_idx)

    # The write after clients.add() must come before the finally block
    # (i.e. it's the connect-time write, not accidentally the same line
    # picked up twice).
    assert connect_write_idx < finally_idx
    assert disconnect_write_idx > discard_idx


def test_resource_gate_sees_written_count(clients_file, tmp_path):
    import core.resource_gate as rg

    gui_pid_file = tmp_path / "gui-server.pid"
    import os

    gui_pid_file.write_text(str(os.getpid()))

    gui_server.clients.add(object())
    gui_server._write_gui_clients_count()

    assert (
        rg.is_gui_client_connected(clients_file=clients_file, gui_pid_file=gui_pid_file) is True
    )

    gui_server.clients.clear()
    gui_server._write_gui_clients_count()
    assert (
        rg.is_gui_client_connected(clients_file=clients_file, gui_pid_file=gui_pid_file) is False
    )
