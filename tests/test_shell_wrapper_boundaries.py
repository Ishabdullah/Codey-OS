"""Restricted wrappers and utilities; execution mocked and startup state isolated."""

import json
import shlex
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, agent, task_executor
from core.action_gateway import ACT, HIGH_IMPACT, READ, ActionGateway
from tools import shell_tools
from utils.config import AGENT_CONFIG


@pytest.mark.parametrize("command", ["find", "find --help", "find . -name '*.py'", "find . -exec git status ;", "find . -execdir helper {} +", "find . -ok helper {} ;", "find . -okdir helper {} ;", "find . -delete", "find . -fprint /temporary/output", "xargs", "xargs --help", "xargs -a /temporary/input", "xargs -I {} helper {}", "xargs -P 2 helper", "xargs -p helper", "xargs -- helper", "env X=value", "env ''", "env --help", "env -i", "env --", "env -- git status", "env env", "env helper"])
@pytest.mark.parametrize("form", ["{}", "/temporary/bin/{}", "'./path with spaces/{}'"])
def test_restricted_utility_forms(command, form):
    executable, separator, arguments = command.partition(" ")
    assert shell_tools.classify_shell_command(form.format(executable) + separator + arguments) == HIGH_IMPACT


@pytest.mark.parametrize("command", ["env", "  env  ", "'/temporary/path with spaces/env'", "/temporary/bin/env"])
def test_only_bare_env_is_read(command):
    assert shell_tools.classify_shell_command(command) == READ


@pytest.mark.parametrize("executable", ["git", "git-custom", "find", "xargs", "env"])
@pytest.mark.parametrize("form", ["{} 'unterminated", "'{} argument", "'/temporary/path with spaces/{}' 'unterminated"])
def test_identifiable_malformed_restricted_quotes(executable, form):
    assert shell_tools.classify_shell_command(form.format(executable)) == HIGH_IMPACT


@pytest.mark.parametrize(("command", "expected"), [("pwd", READ), ("printenv", READ), ("ls -la", READ), ("grep x file", READ), ("echo safe", ACT), ("python3 arbitrary.py", ACT), ("python3 'unterminated", ACT), ("rm -rf /temporary", HIGH_IMPACT)])
def test_unrelated_classifications_unchanged(command, expected):
    assert shell_tools.classify_shell_command(command) == expected


def test_classifier_does_not_discover_or_parse_children(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("no discovery"))
    monkeypatch.setattr(shell_tools.subprocess, "run", forbidden)
    monkeypatch.setattr(shell_tools, "AGENT_CONFIG", SimpleNamespace(get=forbidden))
    monkeypatch.setattr(Path, "exists", forbidden)
    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr("os.getenv", forbidden)
    for command in ["env", "env X=value", "find . -exec opaque ;", "xargs opaque"]:
        assert shell_tools.classify_shell_command(command) in {READ, HIGH_IMPACT}
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


@pytest.mark.parametrize("command", ["find . -delete", "xargs helper", "env X=value helper"])
@pytest.mark.parametrize("mode", ["no-path", "yolo"])
def test_refusal_before_warning_prompt_spawn_preserves_marker(gateway, tmp_path, monkeypatch, command, mode):
    marker = tmp_path / "marker"
    marker.write_text("unchanged")
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
    assert marker.read_text() == "unchanged"
    assert_record(gateway, command, "refused")


@pytest.mark.parametrize("command", ["find . -name 'quoted name'", "xargs -I {} helper {}", "env X='quoted value' helper"])
@pytest.mark.parametrize("answer", [True, False, "yes", 1])
def test_confirmation_and_execution_contract(gateway, monkeypatch, command, answer):
    prompt = Mock(return_value=answer)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="original stdout\n", stderr="original stderr\n"))
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = shell_tools.shell(command, timeout=53)
    prompt.assert_called_once_with(f"Run shell command: `{command}`?")
    if answer is True:
        assert result == "original stdout\n\n[stderr]\noriginal stderr"
        runner.assert_called_once_with(shlex.split(command), capture_output=True, text=True, timeout=53)
        assert_record(gateway, command, "allowed")
    else:
        assert result == "[CANCELLED] User declined to run command."
        runner.assert_not_called()
        assert_record(gateway, command, "refused")


@pytest.mark.parametrize("command", ["find . -name '*.py'", "env helper", "xargs helper"])
@pytest.mark.parametrize("caller", ["agent", "daemon"])
def test_agent_and_daemon_refuse_utilities(gateway, monkeypatch, command, caller):
    runner, prompt = Mock(), Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    if caller == "agent":
        result = agent.TOOLS["shell"]({"command": command})
    else:
        executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
        result = executor._daemon_shell(command)
    assert result.startswith("[BLOCKED]")
    runner.assert_not_called()
    prompt.assert_not_called()
    if caller == "daemon" and command.startswith("xargs"):
        assert result == "[BLOCKED] Daemon mode will not run 'xargs helper' without explicit authorization. Add the command prefix to _DAEMON_ALLOWED_PREFIXES in core/task_executor.py to enable it."
        row = json.loads(gateway.audit.read_text())
        assert row["authority"] == HIGH_IMPACT and row["action"] == "task_executor.daemon_shell" and row["outcome"] == "refused"
        assert len(gateway.audit.read_text().splitlines()) == 1
    else:
        assert_record(gateway, command, "refused")


def test_daemon_bare_env_remains_read(gateway, monkeypatch):
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="temporary environment", stderr=""))
    prompt = Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert executor._daemon_shell("env") == "temporary environment"
    runner.assert_called_once_with(["env"], capture_output=True, text=True, timeout=1800)
    prompt.assert_not_called()
    row = json.loads(gateway.audit.read_text())
    assert row["authority"] == READ and row["outcome"] == "allowed"
    assert len(gateway.audit.read_text().splitlines()) == 1


@pytest.mark.parametrize("command", ["find .", "env helper", "xargs helper"])
def test_execute_tool_refusal_has_no_episodic_success(gateway, monkeypatch, command):
    import core.memory_v2 as memory_module

    log = Mock()
    monkeypatch.setattr(memory_module.memory, "log_action", log)
    monkeypatch.setattr(agent, "_get_learning", Mock(return_value=Mock()))
    monkeypatch.setattr(agent, "show_shell", Mock())
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    runner = Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = agent.execute_tool({"name": "shell", "args": {"command": command}})
    assert result.startswith("[BLOCKED]")
    log.assert_not_called()
    runner.assert_not_called()
    assert_record(gateway, command, "refused")


def test_sink_failure_preserves_refusal(gateway, tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("unchanged")
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: ActionGateway(audit_file=blocker / "audit.jsonl"))
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    runner = Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    assert shell_tools.shell("env helper").startswith("[BLOCKED]")
    runner.assert_not_called()
    assert blocker.read_text() == "unchanged"
