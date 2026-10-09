"""Every direct Git shell invocation requires confirmation; execution is mocked."""

import json
import shlex
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, agent, task_executor
from core.action_gateway import HIGH_IMPACT, ActionGateway
from tools import shell_tools
from utils.config import AGENT_CONFIG


@pytest.mark.parametrize("arguments", ["", "status", "log", "diff", "show HEAD", "commit -m message", "--version", "--help", "--exec-path", "--list-cmds=builtins", "-C /repo status", "-c core.fsmonitor=helper status", "-c core.pager=helper log", "-c help.viewer=helper help status", "-c core.editor=helper commit", "-c gpg.program=helper commit -S", "-c diff.demo.textconv=helper show", "-c diff.external=helper diff", "-c core.hooksPath=/hooks commit"])
@pytest.mark.parametrize("executable", ["git", "/temporary/bin/git", "'./path with spaces/git'"])
def test_all_direct_git_forms_are_high(arguments, executable):
    assert shell_tools.classify_shell_command(f"{executable} {arguments}") == HIGH_IMPACT


def test_classification_is_pure_even_with_opaque_configuration(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("no discovery"))
    monkeypatch.setattr(shell_tools.subprocess, "run", forbidden)
    monkeypatch.setattr(shell_tools, "AGENT_CONFIG", SimpleNamespace(get=forbidden))
    monkeypatch.setattr(Path, "exists", forbidden)
    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr("os.getenv", forbidden)
    for command in ["git", "git -c core.fsmonitor=helper status", "git --version", "git-custom 'unterminated"]:
        assert shell_tools.classify_shell_command(command) == HIGH_IMPACT
    forbidden.assert_not_called()


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    instance = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: instance)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", True)
    monkeypatch.delitem(AGENT_CONFIG, "_shell_fn", raising=False)
    return SimpleNamespace(audit=audit, instance=instance)


def assert_record(gateway, command, outcome):
    rows = [json.loads(line) for line in gateway.audit.read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row.pop("ts"), float)
    assert row == {"authority": HIGH_IMPACT, "action": "shell_tools.shell", "command": command, "outcome": outcome, "reason": row["reason"]}


@pytest.mark.parametrize("command", ["git", "git status", "git --version", "git -c core.fsmonitor=helper status"])
@pytest.mark.parametrize("mode", ["no-path", "yolo"])
def test_refusal_before_warning_prompt_or_spawn(gateway, monkeypatch, command, mode):
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", mode != "no-path")
    warning, prompt, runner = Mock(), Mock(), Mock()
    monkeypatch.setattr(shell_tools, "warning", warning)
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = shell_tools.shell(command, yolo=mode == "yolo")
    assert result.startswith("[BLOCKED]") and "no confirmation path available" in result
    warning.assert_not_called()
    prompt.assert_not_called()
    runner.assert_not_called()
    assert_record(gateway, command, "refused")


@pytest.mark.parametrize("answer", [False, "yes", 1, True])
def test_strict_confirmation_and_exact_execution(gateway, monkeypatch, answer):
    command = "git -C '/temporary/path with spaces' status"
    prompt = Mock(return_value=answer)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="original stdout\n", stderr="original stderr\n"))
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = shell_tools.shell(command, timeout=47)
    prompt.assert_called_once_with(f"Run shell command: `{command}`?")
    if answer is True:
        assert result == "original stdout\n\n[stderr]\noriginal stderr"
        runner.assert_called_once_with(shlex.split(command), capture_output=True, text=True, timeout=47)
        assert_record(gateway, command, "allowed")
    else:
        assert result == "[CANCELLED] User declined to run command."
        runner.assert_not_called()
        assert_record(gateway, command, "refused")


@pytest.mark.parametrize("operation", ["status", "log", "diff", "show"])
@pytest.mark.parametrize("caller", ["agent", "daemon"])
def test_real_agent_and_allowlisted_daemon_queries_block(gateway, monkeypatch, operation, caller):
    command = f"git {operation}"
    runner, prompt = Mock(), Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    if caller == "agent":
        monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
        result = agent.TOOLS["shell"]({"command": command})
    else:
        executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
        result = executor._daemon_shell(command)
    assert result.startswith("[BLOCKED]")
    runner.assert_not_called()
    prompt.assert_not_called()
    assert_record(gateway, command, "refused")


def test_audit_sink_failure_preserves_query_refusal(gateway, tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("unchanged")
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: ActionGateway(audit_file=blocker / "audit.jsonl"))
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    runner = Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    assert shell_tools.shell("git status").startswith("[BLOCKED]")
    runner.assert_not_called()
    assert blocker.read_text() == "unchanged"
