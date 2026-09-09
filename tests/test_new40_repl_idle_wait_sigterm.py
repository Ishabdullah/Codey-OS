"""
NEW-40 regression test: NEW-10's SIGTERM handler (main._sigterm_handler)
raises SystemExit wherever the process happens to be executing. The
REPL's steady-state input() wait (main.repl()'s `while True:` loop) had
its own `except (KeyboardInterrupt, EOFError):` clause that caught
KeyboardInterrupt (SIGINT) and ran shutdown() -- but did NOT catch
SystemExit, so a SIGTERM arriving while idle at the prompt propagated
straight out of repl()/main() uncaught, skipping shutdown() (which
unloads the model and kills llama-server).

This test simulates that exact scenario: mock input() to raise
SystemExit(143) (the code _sigterm_handler actually raises for SIGTERM,
128 + signal.SIGTERM), drive main.repl() with just enough mocking to
reach the idle input() wait without touching a real model or terminal,
and assert on the observable effects of shutdown() having actually run
(monitor.stop() and loader.unload() called) -- not just that some
`shutdown` symbol was invoked, so the test would catch the except
clause being unreachable or a no-op just as easily as it catches the
clause being entirely missing.

See NEW_ISSUES.md NEW-40 and NEW-10 for full context.
"""
import signal
from unittest.mock import MagicMock

import pytest

import main


def test_sigterm_at_idle_input_wait_runs_shutdown(monkeypatch, capsys):
    # --- Skip model loading entirely (remote backend path) ---
    monkeypatch.setattr("utils.config.is_remote_backend", lambda: True)

    # --- Project/memory banner lookups: keep them cheap and side-effect-free ---
    monkeypatch.setattr("core.project.detect_project", lambda: {"type": "unknown"})
    monkeypatch.setattr("core.codeymd.find_codeymd", lambda: False)

    # --- Session load/save: avoid touching real session files on disk ---
    monkeypatch.setattr("core.sessions.load_session", lambda *a, **k: [])
    saved_sessions = []
    monkeypatch.setattr(
        "core.sessions.save_session", lambda history, *a, **k: saved_sessions.append(history)
    )

    # --- System monitor: assert .stop() is reached via shutdown() ---
    mock_monitor = MagicMock()
    monkeypatch.setattr(main, "get_monitor", lambda: mock_monitor)

    # --- Loader: assert .unload() is reached via shutdown() ---
    mock_loader = MagicMock()
    mock_loader.get_pid.return_value = None
    monkeypatch.setattr(main, "_daemon_is_running", lambda: False)
    monkeypatch.setattr("core.loader_v2.get_loader", lambda: mock_loader)

    # --- ctx.list_loaded(): called once per loop iteration before input() ---
    monkeypatch.setattr(main.ctx, "list_loaded", lambda: [])

    # --- The actual signal simulation: input() raises SystemExit(143), ---
    # exactly what _sigterm_handler raises for a real SIGTERM (128 + 15).
    def _raise_sigterm(*args, **kwargs):
        raise SystemExit(128 + signal.SIGTERM)

    monkeypatch.setattr("builtins.input", _raise_sigterm)

    # repl() with no initial_prompt goes straight to the `while True:`
    # loop and hits input() on the first iteration.
    main.repl(initial_prompt=None, one_shot=False)

    # shutdown() must have actually run: monitor stopped, loader unloaded.
    mock_monitor.stop.assert_called_once()
    mock_loader.unload.assert_called_once()

    # Session must be saved before exiting, same as the KeyboardInterrupt path.
    assert saved_sessions == [[]]

    captured = capsys.readouterr()
    assert "Session saved. Goodbye!" in captured.out


def test_keyboard_interrupt_at_idle_input_wait_still_runs_shutdown(monkeypatch, capsys):
    """
    Guard against the fix regressing existing SIGINT behavior at the same
    site -- KeyboardInterrupt must still be caught and cleaned up exactly
    as it was before this change.
    """
    monkeypatch.setattr("utils.config.is_remote_backend", lambda: True)
    monkeypatch.setattr("core.project.detect_project", lambda: {"type": "unknown"})
    monkeypatch.setattr("core.codeymd.find_codeymd", lambda: False)
    monkeypatch.setattr("core.sessions.load_session", lambda *a, **k: [])
    saved_sessions = []
    monkeypatch.setattr(
        "core.sessions.save_session", lambda history, *a, **k: saved_sessions.append(history)
    )

    mock_monitor = MagicMock()
    monkeypatch.setattr(main, "get_monitor", lambda: mock_monitor)
    mock_loader = MagicMock()
    mock_loader.get_pid.return_value = None
    monkeypatch.setattr(main, "_daemon_is_running", lambda: False)
    monkeypatch.setattr("core.loader_v2.get_loader", lambda: mock_loader)
    monkeypatch.setattr(main.ctx, "list_loaded", lambda: [])

    def _raise_sigint(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr("builtins.input", _raise_sigint)

    main.repl(initial_prompt=None, one_shot=False)

    mock_monitor.stop.assert_called_once()
    mock_loader.unload.assert_called_once()
    assert saved_sessions == [[]]
