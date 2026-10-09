"""Lower-level direct Git publishing; execution mocked, state isolated before collection."""

import json
import shlex
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, agent, task_executor
from core.action_gateway import ACT, HIGH_IMPACT, READ, ActionGateway
from tools import shell_tools
from utils.config import AGENT_CONFIG

FAMILIES = ["git send-pack", "git http-push", "git-send-pack", "git-http-push"]


@pytest.mark.parametrize("operation", ["send-pack", "http-push"])
@pytest.mark.parametrize("arguments", ["", "--dry-run", "--help", "--mirror", "--force", "--delete", "--stdin", "/temporary/remote HEAD:refs/heads/main"])
def test_operation_family_is_high_for_all_arguments(operation, arguments):
    assert shell_tools.classify_shell_command(f"git {operation} {arguments}") == HIGH_IMPACT


@pytest.mark.parametrize("executable", ["git-send-pack", "git-http-push"])
@pytest.mark.parametrize("form", ["{}", "/temporary/bin/{}", "./{}", "'/temporary/path with spaces/{}'"])
def test_standalone_executable_basename_paths_and_quotes(executable, form):
    assert shell_tools.classify_shell_command(f"{form.format(executable)} --help") == HIGH_IMPACT


@pytest.mark.parametrize("operation", ["send-pack", "http-push"])
@pytest.mark.parametrize("prefix", ["-C /temporary/repo", "-c foo.bar", "--git-dir=/temporary/repo/.git --work-tree /temporary/repo", "--namespace scoped --no-pager", "--config-env foo.bar=ENV --attr-source HEAD", "--exec-path=/temporary/bin", "-C '' -C '/temporary/path with spaces' -c 'foo.bar=value with spaces' -P"])
def test_effective_operations_after_globals(operation, prefix):
    assert shell_tools.classify_shell_command(f"git {prefix} {operation}") == HIGH_IMPACT


@pytest.mark.parametrize("value", ["send-pack", "http-push"])
@pytest.mark.parametrize("prefix", ["-C {}", "--namespace={}", "--attr-source {}", "-c alias.demo={}"])
def test_operand_values_do_not_exempt_direct_git(value, prefix):
    assert shell_tools.classify_shell_command(f"git {prefix.format(value)} status") == HIGH_IMPACT


@pytest.mark.parametrize("operation", ["send-pack", "http-push"])
@pytest.mark.parametrize("query", ["--version", "--help", "--exec-path", "--html-path", "--man-path", "--info-path", "--list-cmds=builtins"])
def test_terminal_queries_are_high(operation, query):
    assert shell_tools.classify_shell_command(f"git -C /temporary/repo {query} {operation}") == HIGH_IMPACT


@pytest.mark.parametrize("executable", ["git-send-pack", "git-http-push"])
@pytest.mark.parametrize("form", ["{} 'unterminated", "'{} argument", "'/temporary/path with spaces/{}' 'unterminated"])
def test_additional_executables_with_malformed_quotes(executable, form):
    assert shell_tools.classify_shell_command(form.format(executable)) == HIGH_IMPACT


@pytest.mark.parametrize(
    ("command", "expected"),
    [("git status", HIGH_IMPACT), ("git commit -m message", HIGH_IMPACT), ("git -C /repo status", HIGH_IMPACT), ("git custom-alias", HIGH_IMPACT), ("env git send-pack", READ), ("find . -exec git http-push", READ), ("python3 arbitrary.py", ACT), ("git --version send-pack push --force", HIGH_IMPACT), ("git --unknown http-push", HIGH_IMPACT)],
)
def test_unchanged_labels_patterns_and_ambiguity(command, expected):
    assert shell_tools.classify_shell_command(command) == expected


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    instance = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: instance)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", True)
    monkeypatch.delitem(AGENT_CONFIG, "_shell_fn", raising=False)
    return SimpleNamespace(instance=instance, audit=audit)


def assert_record(gateway, command, outcome, action="shell_tools.shell"):
    records = [json.loads(line) for line in gateway.audit.read_text().splitlines()]
    assert len(records) == 1
    row = records[0]
    assert isinstance(row.pop("ts"), float)
    assert row["authority"] == HIGH_IMPACT
    assert row["action"] == action and row["command"] == command
    assert row["outcome"] == outcome
    assert set(row) == {"authority", "action", "command", "outcome", "reason"}
    return row


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("mode", ["no-path", "yolo", "decline", "truthy-text", "truthy-int"])
def test_family_refusal_has_one_high_audit_no_subprocess(gateway, monkeypatch, family, mode):
    command = f"{family} /temporary/remote"
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", mode != "no-path")
    prompt = Mock(return_value="yes" if mode == "truthy-text" else 1 if mode == "truthy-int" else False)
    runner = Mock(side_effect=AssertionError("publishing must not execute without approval"))
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = shell_tools.shell(command, yolo=mode == "yolo")
    if mode in ("no-path", "yolo"):
        assert result.startswith("[BLOCKED]")
        prompt.assert_not_called()
    else:
        assert result == "[CANCELLED] User declined to run command."
        prompt.assert_called_once_with(f"Run shell command: `{command}`?")
    runner.assert_not_called()
    assert_record(gateway, command, "refused")


@pytest.mark.parametrize("family", FAMILIES)
def test_approved_family_preserves_argv_output_timeout(gateway, monkeypatch, family):
    command = f"{family} '/temporary/path with spaces' HEAD:refs/heads/main"
    prompt = Mock(return_value=True)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="original stdout\n", stderr="original stderr\n"))
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    assert shell_tools.shell(command, timeout=41) == "original stdout\n\n[stderr]\noriginal stderr"
    prompt.assert_called_once_with(f"Run shell command: `{command}`?")
    runner.assert_called_once_with(shlex.split(command), capture_output=True, text=True, timeout=41)
    assert_record(gateway, command, "allowed")


@pytest.mark.parametrize("family", FAMILIES)
def test_real_agent_tools_shell_refuses_family(gateway, monkeypatch, family):
    command = f"{family} /temporary/remote"
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    runner = Mock(side_effect=AssertionError("agent must not execute publication"))
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    assert agent.TOOLS["shell"]({"command": command}).startswith("[BLOCKED]")
    runner.assert_not_called()
    assert_record(gateway, command, "refused")


@pytest.mark.parametrize("family", FAMILIES)
def test_daemon_guard_still_refuses_family(gateway, monkeypatch, family):
    command = f"{family} /temporary/remote"
    shell = Mock(side_effect=AssertionError("daemon must not delegate publication"))
    monkeypatch.setattr(shell_tools, "shell", shell)
    monkeypatch.setattr(task_executor, "warning", Mock())
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert executor._daemon_shell(command).startswith("[BLOCKED] Daemon mode will not run")
    shell.assert_not_called()
    assert_record(gateway, command, "refused", action="task_executor.daemon_shell")


@pytest.mark.parametrize("family", FAMILIES)
def test_blocked_audit_sink_preserves_family_refusal(gateway, tmp_path, monkeypatch, family):
    blocker = tmp_path / "blocker"
    blocker.write_text("blocker")
    instance = ActionGateway(audit_file=blocker / "audit.jsonl")
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: instance)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    runner = Mock(side_effect=AssertionError("no execution under refusal"))
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    assert shell_tools.shell(f"{family} /temporary/remote").startswith("[BLOCKED]")
    runner.assert_not_called()
    assert blocker.read_text() == "blocker"
