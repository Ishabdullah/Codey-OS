"""Bounded Git operation set; mock execution and bootstrap state before collection."""

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


@pytest.mark.parametrize("operation", ["custom-alias", "unknown", "STATUS", "Commit", "add", "branch", "checkout", "merge", "fetch", "config", "rev-parse", "maintenance", "lfs", "annex", "push", "send-pack", "http-push"])
def test_operations_outside_reviewed_set_are_high(operation):
    assert shell_tools.classify_shell_command(f"git {operation}") == HIGH_IMPACT


@pytest.mark.parametrize("executable", ["git-custom", "git-lfs", "git-annex", "git-status", "git-commit", "git-push", "git-send-pack", "git-http-push", "git-"])
@pytest.mark.parametrize("form", ["{}", "/temporary/bin/{}", "./{}", "'/temporary/path with spaces/{}'"])
def test_all_git_prefixed_executables_are_high(executable, form):
    assert shell_tools.classify_shell_command(f"{form.format(executable)} --help") == HIGH_IMPACT


@pytest.mark.parametrize("prefix", ["-C /repo", "-c foo.bar", "--git-dir /repo/.git", "--git-dir=/repo/.git", "--work-tree /repo", "--work-tree=/repo", "--namespace space", "--namespace=space", "--config-env foo.bar=ENV", "--config-env=foo.bar=ENV", "--attr-source HEAD", "--attr-source=HEAD", "--exec-path=/temporary/bin", "-C '' -C '/repo with spaces' -c 'foo.bar=quoted value' -P"])
def test_globals_reveal_unknown_effective_operation(prefix):
    assert shell_tools.classify_shell_command(f"git {prefix} custom-alias") == HIGH_IMPACT


@pytest.mark.parametrize("flag", ["-p", "--paginate", "-P", "--no-pager", "--bare", "--no-replace-objects", "--no-lazy-fetch", "--no-optional-locks", "--no-advice", "--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs"])
def test_operand_free_globals_preserve_unknown_restriction(flag):
    assert shell_tools.classify_shell_command(f"git {flag} custom-alias") == HIGH_IMPACT


@pytest.mark.parametrize("prefix", ["-C {}", "-c alias.demo={}", "--git-dir {}", "--work-tree={}", "--namespace {}", "--config-env foo.bar={}", "--attr-source {}", "--exec-path={}"])
def test_unknown_operation_name_in_operand_is_not_effective_operation(prefix):
    assert shell_tools.classify_shell_command(f"git {prefix.format('custom-alias')} status") == ACT


@pytest.mark.parametrize(("operation", "direct"), [("status", READ), ("log", READ), ("diff", READ), ("show", READ), ("commit", ACT)])
def test_five_reviewed_operations_keep_exact_prior_labels(operation, direct):
    assert shell_tools.classify_shell_command(f"git {operation}") == direct
    assert shell_tools.classify_shell_command(f"git -C /repo {operation}") == ACT
    assert shell_tools.classify_shell_command(f"'/temporary/path with spaces/git' {operation}") == direct


@pytest.mark.parametrize("command", ["git", "git -C /repo", "git --no-pager", "git --version custom-alias", "git --help checkout", "git --exec-path custom-alias", "git --html-path custom-alias", "git --man-path custom-alias", "git --info-path custom-alias", "git --list-cmds=builtins custom-alias"])
def test_queries_and_absent_operation_are_unchanged(command):
    assert shell_tools.classify_shell_command(command) == ACT


@pytest.mark.parametrize("command", ["git --unknown status", "git -- status", "git -C", "git status 'unterminated", "git-custom 'unterminated", "'git-custom argument", "'/temporary/path with spaces/git-custom' 'unterminated"])
def test_ambiguity_and_identifiable_malformed_git_quotes_are_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize(("command", "expected"), [("env git custom-alias", READ), ("find . -exec git custom-alias", READ), ("python3 arbitrary.py", ACT), ("echo safe", ACT), ("pwd", READ), ("find . -delete", HIGH_IMPACT), ("git --version push --force", HIGH_IMPACT)])
def test_other_labels_and_pattern_precedence_unchanged(command, expected):
    assert shell_tools.classify_shell_command(command) == expected


def test_classifier_does_not_discover_executables_config_or_paths(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("classification must be pure"))
    monkeypatch.setattr(shell_tools.subprocess, "run", forbidden)
    monkeypatch.setattr(shell_tools, "AGENT_CONFIG", SimpleNamespace(get=forbidden))
    monkeypatch.setattr(Path, "exists", forbidden)
    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr("os.getenv", forbidden)
    assert shell_tools.classify_shell_command("git -C /repo -c alias.custom=other custom") == HIGH_IMPACT
    assert shell_tools.classify_shell_command("'/temporary/unknown/git-custom' arg") == HIGH_IMPACT
    forbidden.assert_not_called()


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


@pytest.mark.parametrize("command", ["git custom-alias", "git -C /repo checkout branch", "'/temporary/path with spaces/git-lfs' status"])
@pytest.mark.parametrize("mode", ["no-path", "yolo"])
def test_no_path_refusal_precedes_warning_prompt_and_spawn(gateway, monkeypatch, command, mode):
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", mode != "no-path")
    warning = Mock()
    prompt = Mock()
    runner = Mock(side_effect=AssertionError("no spawn without confirmation"))
    monkeypatch.setattr(shell_tools, "warning", warning)
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = shell_tools.shell(command, yolo=mode == "yolo")
    assert result.startswith("[BLOCKED]") and "no confirmation path available" in result
    warning.assert_not_called()
    prompt.assert_not_called()
    runner.assert_not_called()
    assert_record(gateway, command, "refused")


@pytest.mark.parametrize("answer", [True, False, "yes", 1])
@pytest.mark.parametrize("command", ["git custom-alias 'quoted argument'", "'/temporary/path with spaces/git-custom' arg"])
def test_strict_approval_once_preserves_execution_contract(gateway, monkeypatch, answer, command):
    prompt = Mock(return_value=answer)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="original stdout\n", stderr="original stderr\n"))
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = shell_tools.shell(command, timeout=43)
    prompt.assert_called_once_with(f"Run shell command: `{command}`?")
    if answer is True:
        assert result == "original stdout\n\n[stderr]\noriginal stderr"
        runner.assert_called_once_with(shlex.split(command), capture_output=True, text=True, timeout=43)
        assert_record(gateway, command, "allowed")
    else:
        assert result == "[CANCELLED] User declined to run command."
        runner.assert_not_called()
        assert_record(gateway, command, "refused")


@pytest.mark.parametrize("command", ["git custom-alias", "git-lfs status"])
def test_agent_tools_and_daemon_guard_integrations(gateway, monkeypatch, command):
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    runner = Mock(side_effect=AssertionError("no execution"))
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    assert agent.TOOLS["shell"]({"command": command}).startswith("[BLOCKED]")
    assert_record(gateway, command, "refused")
    gateway.audit.unlink()
    shell = Mock(side_effect=AssertionError("daemon must not delegate"))
    monkeypatch.setattr(shell_tools, "shell", shell)
    monkeypatch.setattr(task_executor, "warning", Mock())
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert executor._daemon_shell(command).startswith("[BLOCKED] Daemon mode will not run")
    shell.assert_not_called()
    runner.assert_not_called()
    assert_record(gateway, command, "refused", action="task_executor.daemon_shell")


def test_audit_sink_failure_does_not_allow_unknown_operation(gateway, tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("blocker")
    instance = ActionGateway(audit_file=blocker / "audit.jsonl")
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: instance)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    runner = Mock(side_effect=AssertionError("refusal never executes"))
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    assert shell_tools.shell("git custom-alias").startswith("[BLOCKED]")
    runner.assert_not_called()
    assert blocker.read_text() == "blocker"
