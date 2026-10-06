"""
NEW-754 Part E — main.py's `_warn_if_model_load_incomplete()` and its
placement at all 4 model-load call sites (repl(), args.init/--tdd/--fix).

Before this fix, a `LOAD_OUTCOME_SPAWN_FAILED`/`LOAD_OUTCOME_ERROR` outcome
fell through `_is_unrecovered_gate_denial()`'s hard-bail silently and
execution proceeded into the REPL or `run_init()`/`run_tdd_loop()`/
`fix_file()` as if a model were resident. This file asserts the warning
helper itself, and that each of the 4 real call sites invokes it with the
real loader/outcome right before the next visible action — not back at
the original `ok = ...` line.

No real llama-server subprocess, no real daemon socket (CLAUDE.md rule 2)
— `get_loader()`/`_load_primary_with_gate_recovery()` are faked at every
site, same posture as tests/test_main_gate_recovery.py.
"""
from unittest.mock import MagicMock, patch

import pytest

import main as main_mod
from core.loader_v2 import (
    LOAD_OUTCOME_ERROR,
    LOAD_OUTCOME_OK,
    LOAD_OUTCOME_SPAWN_FAILED,
)


class FakeLoader:
    def __init__(self, outcome, reason="boom"):
        self._outcome = outcome
        self._reason = reason

    def get_last_ensure_outcome(self):
        return self._outcome

    def get_last_ensure_reason(self):
        return self._reason


# ---------------------------------------------------------------------------
# _warn_if_model_load_incomplete() itself
# ---------------------------------------------------------------------------


def test_warns_when_not_ok(capsys):
    loader = FakeLoader(LOAD_OUTCOME_SPAWN_FAILED, "llama-server process died (exit code 1)")
    main_mod._warn_if_model_load_incomplete(loader, False)
    out = capsys.readouterr().out
    assert "No model is currently loaded" in out
    # rich's console wraps long lines -- compare with whitespace
    # normalized rather than requiring the exact substring on one line.
    assert "llama-server process died (exit code 1)" in " ".join(out.split())


def test_no_warning_when_ok(capsys):
    loader = FakeLoader(LOAD_OUTCOME_OK, "")
    main_mod._warn_if_model_load_incomplete(loader, True)
    out = capsys.readouterr().out
    assert "No model is currently loaded" not in out


@pytest.mark.parametrize("outcome", [LOAD_OUTCOME_SPAWN_FAILED, LOAD_OUTCOME_ERROR])
def test_warns_for_spawn_failed_and_error_outcomes(outcome, capsys):
    """These are exactly the outcomes `_is_unrecovered_gate_denial()` does
    NOT catch -- the class this fix exists for."""
    loader = FakeLoader(outcome, "binary not found")
    main_mod._warn_if_model_load_incomplete(loader, False)
    out = capsys.readouterr().out
    assert "No model is currently loaded" in out


# ---------------------------------------------------------------------------
# Placement at the 3 automation call sites (args.init / --tdd / --fix)
# ---------------------------------------------------------------------------


def _run_main_with_argv(monkeypatch, argv):
    monkeypatch.setattr("sys.argv", ["codeyOS"] + argv)
    main_mod.main()


@pytest.fixture
def _silence_cli_telemetry(monkeypatch):
    monkeypatch.setattr(main_mod, "_record_cli_telemetry_run_start", lambda: None)


def test_init_site_warns_before_run_init(monkeypatch, tmp_path, _silence_cli_telemetry):
    loader = FakeLoader(LOAD_OUTCOME_SPAWN_FAILED, "spawn died")
    monkeypatch.setattr(main_mod, "get_loader", lambda: loader)
    monkeypatch.setattr(main_mod, "_load_primary_with_gate_recovery", lambda l: False)
    calls = []
    monkeypatch.setattr(
        main_mod, "_warn_if_model_load_incomplete", lambda l, ok: calls.append((l, ok))
    )
    mock_run_init = MagicMock()
    monkeypatch.setattr(main_mod, "run_init", mock_run_init)
    monkeypatch.setattr(main_mod, "shutdown", lambda: None)
    # CODEY.md generation reads cwd -- keep it isolated.
    monkeypatch.chdir(tmp_path)

    _run_main_with_argv(monkeypatch, ["--init"])

    assert calls == [(loader, False)]
    mock_run_init.assert_called_once()


def test_tdd_site_warns_before_run_tdd_loop(monkeypatch, tmp_path, _silence_cli_telemetry):
    loader = FakeLoader(LOAD_OUTCOME_ERROR, "model file missing")
    monkeypatch.setattr(main_mod, "get_loader", lambda: loader)
    monkeypatch.setattr(main_mod, "_load_primary_with_gate_recovery", lambda l: False)
    calls = []
    monkeypatch.setattr(
        main_mod, "_warn_if_model_load_incomplete", lambda l, ok: calls.append((l, ok))
    )
    monkeypatch.setattr(main_mod, "shutdown", lambda: None)

    src = tmp_path / "foo.py"
    src.write_text("pass\n")
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("pass\n")

    with patch("core.tdd.run_tdd_loop") as mock_run_tdd, patch(
        "core.tdd.find_test_file", return_value=str(test_file)
    ):
        monkeypatch.chdir(tmp_path)
        _run_main_with_argv(monkeypatch, ["--tdd", str(src)])
        mock_run_tdd.assert_called_once()

    assert calls == [(loader, False)]


def test_fix_site_warns_before_fix_file(monkeypatch, tmp_path, _silence_cli_telemetry):
    loader = FakeLoader(LOAD_OUTCOME_SPAWN_FAILED, "spawn died")
    monkeypatch.setattr(main_mod, "get_loader", lambda: loader)
    monkeypatch.setattr(main_mod, "_load_primary_with_gate_recovery", lambda l: False)
    calls = []
    monkeypatch.setattr(
        main_mod, "_warn_if_model_load_incomplete", lambda l, ok: calls.append((l, ok))
    )
    monkeypatch.setattr(main_mod, "shutdown", lambda: None)

    target = tmp_path / "foo.py"
    target.write_text("pass\n")

    with patch("core.fixmode.fix_file") as mock_fix_file:
        monkeypatch.chdir(tmp_path)
        _run_main_with_argv(monkeypatch, ["--fix", str(target)])
        mock_fix_file.assert_called_once()

    assert calls == [(loader, False)]


# ---------------------------------------------------------------------------
# Placement at the interactive repl() call site
# ---------------------------------------------------------------------------


def test_repl_site_warns_before_type_your_task_banner(monkeypatch, tmp_path):
    loader = FakeLoader(LOAD_OUTCOME_SPAWN_FAILED, "spawn died")
    monkeypatch.setattr(main_mod, "get_loader", lambda: loader)
    monkeypatch.setattr(main_mod, "_load_primary_with_gate_recovery", lambda l: False)
    calls = []
    monkeypatch.setattr(
        main_mod, "_warn_if_model_load_incomplete", lambda l, ok: calls.append((l, ok))
    )
    monkeypatch.setattr("utils.config.is_remote_backend", lambda: False)

    mock_monitor = MagicMock()
    monkeypatch.setattr(main_mod, "get_monitor", lambda: mock_monitor)
    monkeypatch.setattr("core.sessions.load_session", lambda *a, **k: [])

    # Drive repl() straight through to the "Type your task" banner and
    # bail out immediately after via a KeyboardInterrupt from the main
    # interactive loop that follows it -- we only need to observe the
    # warning call happened before that banner, not run a real session.
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        try:
            main_mod.repl(initial_prompt=None, one_shot=False)
        except (KeyboardInterrupt, SystemExit):
            pass

    assert calls == [(loader, False)]
