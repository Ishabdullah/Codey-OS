"""D-9 (Ish, 2026-10-24) / G15b-47: --tdd keeps human confirmations unless
--yolo is also given.

Recording fakes only: run_agent, load_file and the loader are faked, no model
is loaded. The loop's pytest run is faked at TestResult level.
"""
import io
import sys
from unittest.mock import MagicMock, patch

import pytest

import main as main_mod
from core import tdd
from utils import config as _cfg


@pytest.fixture
def cfg(monkeypatch):
    """Restore AGENT_CONFIG confirm flags to a known True baseline."""
    monkeypatch.setitem(_cfg.AGENT_CONFIG, "confirm_write", True)
    monkeypatch.setitem(_cfg.AGENT_CONFIG, "confirm_shell", True)
    return _cfg.AGENT_CONFIG


@pytest.fixture
def recorded(monkeypatch, cfg, tmp_path):
    """Run run_tdd_loop over one failing iteration; record what run_agent saw."""
    from core import agent, context

    calls = []

    def fake_run_agent(prompt, history, yolo=False, **kw):
        calls.append({
            "yolo": yolo,
            "confirm_write": cfg["confirm_write"],
            "confirm_shell": cfg["confirm_shell"],
        })
        return "ok", history

    monkeypatch.setattr(agent, "run_agent", fake_run_agent)
    monkeypatch.setattr(context, "load_file", lambda p: None)
    results = iter([
        tdd.TestResult(0, 1, 0, "x FAILED", [("test_x", "boom")], returncode=1),
        tdd.TestResult(1, 0, 0, "x PASSED", [], returncode=0),
    ])
    monkeypatch.setattr(tdd, "run_tests", lambda *a, **k: next(results))
    src = tmp_path / "source.py"
    src.write_text("value = 1\n")
    test = tmp_path / "test_source.py"
    test.write_text("def test_x(): pass\n")
    return calls, str(src), str(test)


def test_tdd_default_keeps_confirmations(recorded, cfg):
    calls, src, test = recorded
    tdd.run_tdd_loop(src, test)  # no yolo argument: default is confirm-on
    assert len(calls) == 1
    assert calls[0] == {"yolo": False, "confirm_write": True, "confirm_shell": True}
    assert cfg["confirm_write"] is True and cfg["confirm_shell"] is True


def test_tdd_explicit_no_yolo_keeps_confirmations(recorded, cfg):
    calls, src, test = recorded
    tdd.run_tdd_loop(src, test, yolo=False)
    assert calls == [{"yolo": False, "confirm_write": True, "confirm_shell": True}]


def test_tdd_yolo_is_confirmless(recorded, cfg):
    calls, src, test = recorded
    tdd.run_tdd_loop(src, test, yolo=True)
    assert calls == [{"yolo": True, "confirm_write": False, "confirm_shell": False}]


def test_tdd_generate_path_passes_yolo_through(monkeypatch, cfg, tmp_path):
    """Initial-generation and retry run_agent calls honour yolo too."""
    from core import agent, context

    seen = []
    monkeypatch.setattr(
        agent, "run_agent",
        lambda p, h, yolo=False, **k: (seen.append(yolo), ("ok", h))[1],
    )
    monkeypatch.setattr(context, "load_file", lambda p: None)
    monkeypatch.setattr(tdd, "run_tests", lambda *a, **k: tdd.TestResult(1, 0, 0, "PASSED", [], returncode=0))
    test = tmp_path / "test_new.py"
    test.write_text("def test_x(): pass\n")
    tdd.run_tdd_loop(str(tmp_path / "new.py"), str(test))  # never created -> generate + retry
    assert seen == [False, False]
    seen.clear()
    tdd.run_tdd_loop(str(tmp_path / "new.py"), str(test), yolo=True)
    assert seen == [True, True]


def test_tdd_no_tty_gated_overwrite_fails_closed_without_hang(monkeypatch, cfg, tmp_path):
    """--tdd without --yolo and no human (stdin at EOF): the model's overwrite
    of the source is cancelled, not hung and not approved."""
    from core import agent, context
    from tools import file_tools

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(file_tools, "_fs", None, raising=False)
    src = tmp_path / "source.py"
    src.write_text("value = 1  # original content that must survive the refusal\n")
    test = tmp_path / "test_source.py"
    test.write_text("def test_x(): pass\n")
    outcomes = []

    def fake_run_agent(prompt, history, yolo=False, **kw):
        outcomes.append(file_tools.tool_write_file(str(src), "value = 2  # rewritten by the model\n"))
        return "ok", history

    monkeypatch.setattr(agent, "run_agent", fake_run_agent)
    monkeypatch.setattr(context, "load_file", lambda p: None)
    monkeypatch.setattr(tdd, "run_tests", lambda *a, **k: tdd.TestResult(0, 1, 0, "x FAILED", [("t", "e")], returncode=1))
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    tdd.run_tdd_loop(str(src), str(test))
    assert outcomes and all(o.startswith("[CANCELLED]") for o in outcomes)
    assert "original content" in src.read_text()


# --- main.py wiring --------------------------------------------------------

def _run_main(monkeypatch, argv, tmp_path):
    from core.loader_v2 import LOAD_OUTCOME_OK

    class L:
        def get_last_ensure_outcome(self):
            return LOAD_OUTCOME_OK

        def get_last_ensure_reason(self):
            return ""

    monkeypatch.setattr(main_mod, "get_loader", lambda: L())
    monkeypatch.setattr(main_mod, "_load_primary_with_gate_recovery", lambda l: True)
    monkeypatch.setattr(main_mod, "_record_cli_telemetry_run_start", lambda: None)
    monkeypatch.setattr(main_mod, "shutdown", lambda: None)
    test_file = tmp_path / "test_foo.py"
    test_file.write_text("pass\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["codeyOS"] + argv)
    with patch("core.tdd.run_tdd_loop") as run_loop, patch(
        "core.tdd.find_test_file", return_value=str(test_file)
    ):
        main_mod.main()
    return run_loop


def test_main_tdd_alone_passes_yolo_false_and_leaves_config(monkeypatch, cfg, tmp_path):
    run_loop = _run_main(monkeypatch, ["--tdd", "foo.py"], tmp_path)
    run_loop.assert_called_once()
    assert run_loop.call_args.kwargs["yolo"] is False
    assert cfg["confirm_write"] is True and cfg["confirm_shell"] is True


def test_main_tdd_with_yolo_is_confirmless(monkeypatch, cfg, tmp_path):
    run_loop = _run_main(monkeypatch, ["--tdd", "foo.py", "--yolo"], tmp_path)
    assert run_loop.call_args.kwargs["yolo"] is True
    assert cfg["confirm_write"] is False and cfg["confirm_shell"] is False
