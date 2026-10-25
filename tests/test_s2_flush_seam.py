"""S2 flush seam: every default-Yes / y-N approval prompt must call
utils.logger._flush_stdin_typeahead() BEFORE it reads the answer, so stale
typeahead (a buffered Enter / 'y') cannot approve. Recording fakes; nothing
real executes. Order is recorded in one shared list."""

import importlib.util
import sys
import types
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

import utils.logger as logger

REPO = Path(__file__).resolve().parent.parent


class _Tty:
    def isatty(self):
        return True

    def readline(self, *a):
        raise AssertionError("stdin must not be read directly")


class _Console:
    def __init__(self, order, answers):
        self.order = order
        self.answers = list(answers)

    def input(self, prompt=""):
        self.order.append("read")
        return self.answers.pop(0) if self.answers else ""

    def print(self, *a, **k):
        pass

    def rule(self, *a, **k):
        pass


@pytest.fixture
def order(monkeypatch):
    o = []
    monkeypatch.setattr(logger, "_flush_stdin_typeahead", lambda: o.append("flush"))
    monkeypatch.setattr(logger, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr("builtins.input", lambda prompt="": (o.append("read"), "")[1])
    return o


def _load_main(monkeypatch):
    import core

    with monkeypatch.context() as imports:
        imports.setattr(sys, "path", list(sys.path))
        for name, attrs in {
            "context": {}, "dashboard_data": {"get_render_text": Mock()},
            "inference_v2": {"was_last_streamed": Mock()},
            "loader_v2": {"get_loader": Mock()}, "sysmon": {"get_monitor": Mock()},
        }.items():
            stub = ModuleType(f"core.{name}")
            stub.__dict__.update(attrs)
            imports.setitem(sys.modules, f"core.{name}", stub)
            imports.setattr(core, name, stub, raising=False)
        spec = importlib.util.spec_from_file_location("_s2_flush_main", REPO / "main.py")
        main = importlib.util.module_from_spec(spec)
        imports.setitem(sys.modules, spec.name, main)
        spec.loader.exec_module(main)
    for n in ("success", "error", "info", "warning"):
        monkeypatch.setattr(main, n, Mock())
    return main


def _assert_flush_first(order):
    assert order == ["flush", "read"], order


# ----------------------------------------------------- main.py confirmations

def test_init_confirm_flushes_first(order, monkeypatch):
    main = _load_main(monkeypatch)
    main._init_confirmation()()
    _assert_flush_first(order)


def test_voice_confirm_flushes_first(order, monkeypatch):
    main = _load_main(monkeypatch)
    main._voice_confirmation()()
    _assert_flush_first(order)


def test_undo_confirm_flushes_first(order, monkeypatch):
    main = _load_main(monkeypatch)
    main._undo_confirmation(path="core/x.py")()
    _assert_flush_first(order)


def test_git_push_confirm_flushes_first(order, monkeypatch):
    import core.githelper as gh

    main = _load_main(monkeypatch)
    monkeypatch.setattr(gh, "is_git_repo", lambda *a, **k: True)
    monkeypatch.setattr(gh, "git_push", lambda confirm=None: (confirm(), "Pushed")[1])
    main.handle_command("/git push", [])
    _assert_flush_first(order)


def test_graph_clear_confirm_flushes_first(order, monkeypatch):
    import core.memory_v2 as mem

    main = _load_main(monkeypatch)
    sym = types.SimpleNamespace(clear=lambda confirm=None: (confirm(), None)[1])
    monkeypatch.setattr(mem, "memory", types.SimpleNamespace(symbolic=sym))
    main.handle_command("/graph clear", [])
    _assert_flush_first(order)


def test_git_commit_accept_prompt_flushes_first(order, monkeypatch):
    import core.githelper as gh

    main = _load_main(monkeypatch)
    monkeypatch.setattr(gh, "is_git_repo", lambda *a, **k: True)
    monkeypatch.setattr(gh, "git_diff_for_commit", lambda *a, **k: "diff")
    monkeypatch.setattr(gh, "git_commit_log_messages", lambda *a, **k: [])
    monkeypatch.setattr(gh, "generate_commit_message", lambda *a, **k: "msg")
    monkeypatch.setattr(gh, "git_commit", lambda m: "committed")
    main.handle_command("/git commit", [])
    _assert_flush_first(order)


# ------------------------------------------------------------ plan prompts

def test_planner_approval_prompt_flushes_first(order, monkeypatch):
    import core.planner as planner

    monkeypatch.setattr(planner, "console", _Console(order, ["y"]))
    monkeypatch.setattr(planner, "separator", lambda: None)
    assert planner.show_and_confirm_plan("P") == (True, "P")
    _assert_flush_first(order)


def test_planner_revised_instruction_prompt_flushes_before_its_read(order, monkeypatch):
    import core.planner as planner

    monkeypatch.setattr(planner, "console", _Console(order, ["edit", "do X"]))
    monkeypatch.setattr(planner, "separator", lambda: None)
    assert planner.show_and_confirm_plan("P") == (True, "do X")
    assert order == ["flush", "read", "flush", "read"], order


def test_agent_plan_prompt_flushes_first(order, monkeypatch):
    import core.agent as agent
    import core.display as display
    import core.orchestrator as orch

    queue = types.SimpleNamespace(
        tasks=[types.SimpleNamespace(status="done", description="t")],
        done_count=lambda: 1,
    )
    monkeypatch.setattr(display, "console", _Console(order, ["y"]))
    monkeypatch.setattr(display, "show_task_plan", lambda q: None)
    monkeypatch.setattr(orch, "is_complex", lambda m, score=None: True)
    monkeypatch.setattr(orch, "plan_tasks", lambda m, c: queue)
    monkeypatch.setattr(orch, "run_queue", lambda q, yolo=False: None)
    monkeypatch.setattr(agent, "read_codeymd", lambda *a, **k: "")
    monkeypatch.setattr(agent, "auto_load_from_prompt", lambda *a, **k: None)
    monkeypatch.setattr(agent, "get_context_usage", lambda *a, **k: (10**9, 1))
    agent.run_agent("build and test a large multi step feature", [], yolo=True)
    _assert_flush_first(order)


# ---------------------------------------------------------------- peer confirm

def test_peer_confirm_flushes_first(order, monkeypatch):
    from unittest.mock import patch

    from core.peer_cli import PEER_REGISTRY, PeerCLIManager

    monkeypatch.setattr("utils.logger.console", _Console(order, ["n"]))
    qwen = next(c for c in PEER_REGISTRY if c.name == "qwen")
    with patch.object(PeerCLIManager, "available", return_value=[qwen]):
        PeerCLIManager().confirm(qwen, "code", "do a thing")
    _assert_flush_first(order)
