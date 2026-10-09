"""Direct Git push classification; bootstrap config before eager imports."""

import json
import os
import shlex
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, agent, task_executor
from core.action_gateway import ACT, HIGH_IMPACT, READ, ActionGateway
from tools import shell_tools
from utils.config import AGENT_CONFIG


@pytest.mark.parametrize(
    "command",
    [
        "git push", "git push origin main", "git push --dry-run", "git push --help",
        "git push --delete origin old", "git push --mirror", "git push --tags",
        "git-push origin main", "/temporary/bin/git push", "/temporary/git-push",
        "'/temporary/path with spaces/git' push", '"/temporary/path with spaces/git-push" origin',
        "git -C /repo push", "git -c foo.bar push", "git -c foo.bar=value push",
        "git --git-dir /repo/.git push", "git --git-dir=/repo/.git push",
        "git --work-tree /repo push", "git --work-tree=/repo push",
        "git --namespace push push", "git --namespace=push push",
        "git --config-env foo.bar=ENV push", "git --config-env=foo.bar=ENV push",
        "git --attr-source HEAD push", "git --attr-source=HEAD push",
        "git --exec-path=/temporary/bin push", "git -C '' push",
        "git -C '/repo with spaces' -C sub -c 'foo.bar=value with spaces' --no-pager push origin main",
    ],
)
def test_direct_push_variants_are_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize(
    "option",
    ["-p", "--paginate", "-P", "--no-pager", "--bare", "--no-replace-objects", "--no-lazy-fetch", "--no-optional-locks", "--no-advice", "--literal-pathspecs", "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs"],
)
def test_operand_free_globals_before_push(option):
    assert shell_tools.classify_shell_command(f"git {option} push") == HIGH_IMPACT


@pytest.mark.parametrize(
    "command",
    ["git -C push status", "git -c alias.demo=push status", "git --git-dir push status", "git --work-tree=push log", "git --namespace push show", "git --attr-source push diff", "git --exec-path=push status", "git -C '' status", "git -c foo.bar status", "git", "git -C /repo", "git --no-pager"],
)
def test_nonpush_globals_are_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize(
    "query",
    ["-v", "--version", "-h", "--help", "--exec-path", "--html-path", "--man-path", "--info-path", "--list-cmds=builtins"],
)
def test_terminal_queries_are_high(query):
    assert shell_tools.classify_shell_command(f"git {query} push") == HIGH_IMPACT
    assert shell_tools.classify_shell_command(f"git -C /repo {query} push") == HIGH_IMPACT


@pytest.mark.parametrize(
    "command",
    ["git -C", "git -c", "git --git-dir", "git --work-tree", "git --namespace", "git --config-env", "git --attr-source", "git --git-dir= push", "git --work-tree '' status", "git -c '' status", "git --exec-path= status", "git --list-cmds= push", "git --list-cmds push", "git --unknown push", "git -- push", "git -C/tmp push", "git -cfoo=bar push", "git '' push", "git push 'unterminated", "git status 'unterminated", "'git push", "'/temporary/path with spaces/git' push 'unterminated"],
)
def test_ambiguous_direct_git_is_conservatively_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize(
    ("command", "expected"),
    [("git status", HIGH_IMPACT), ("git log", HIGH_IMPACT), ("git diff", HIGH_IMPACT), ("git show HEAD", HIGH_IMPACT), ("git commit -m message", HIGH_IMPACT), ("git -C /repo commit", HIGH_IMPACT), ("python3 -c 'print(1)'", ACT), ("env git push", READ), ("git custom-alias", HIGH_IMPACT), ("git send-pack /remote", HIGH_IMPACT), ("git-http-push /remote", HIGH_IMPACT), ("git-send-pack /remote", HIGH_IMPACT), ("find . -exec git push", READ), ("git --version push --force", HIGH_IMPACT), ("find . -delete", HIGH_IMPACT), ("python3 'unterminated", ACT)],
)
def test_prior_labels_and_pattern_precedence(command, expected):
    assert shell_tools.classify_shell_command(command) == expected


def test_parser_is_pure_no_subprocess_or_config(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("classifier must not perform I/O"))
    monkeypatch.setattr(shell_tools.subprocess, "run", forbidden)
    monkeypatch.setattr(shell_tools, "AGENT_CONFIG", SimpleNamespace(get=forbidden))
    assert shell_tools.classify_shell_command("git -C /repo -c foo.bar=push push") == HIGH_IMPACT
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


def assert_record(gateway, command, outcome, action="shell_tools.shell"):
    rows = [json.loads(line) for line in gateway.audit.read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row.pop("ts"), float)
    assert row["authority"] == HIGH_IMPACT
    assert row["action"] == action and row["command"] == command
    assert row["outcome"] == outcome
    assert set(row) == {"authority", "action", "command", "outcome", "reason"}


@pytest.fixture
def repository(tmp_path, monkeypatch):
    for name in list(os.environ):
        if name.startswith("GIT_") or name == "EMAIL":
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    empty = tmp_path / "empty-config"
    empty.mkdir()
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(empty))
    repo = tmp_path / "repo with spaces"
    repo.mkdir()

    def git(*args, cwd=repo, check=True):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)

    git("init", "-b", "main")
    for key, value in {
        "core.hooksPath": str(empty), "commit.gpgsign": "false", "tag.gpgsign": "false",
        "user.useConfigOnly": "true", "user.name": "Temporary Test",
        "user.email": "test@example.invalid", "protocol.allow": "never", "protocol.file.allow": "always",
    }.items():
        git("config", key, value)
    (repo / "content.txt").write_text("local content\n")
    git("add", "--", "content.txt")
    git("commit", "-m", "baseline")
    remote = tmp_path / "bare remote.git"
    git("init", "--bare", str(remote))
    git("config", "core.hooksPath", str(empty), cwd=remote)
    command = f"git -C {shlex.quote(str(repo))} push {shlex.quote(str(remote))} HEAD:refs/heads/main"
    return SimpleNamespace(repo=repo, remote=remote, git=git, command=command)


@pytest.mark.parametrize("mode", ["no-path", "yolo", "declined"])
def test_direct_push_refused_without_subprocess_or_remote_effect(repository, gateway, monkeypatch, mode):
    r = repository
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", mode != "no-path")
    prompt = Mock(return_value=False)
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    with monkeypatch.context() as calls:
        runner = Mock(side_effect=AssertionError("refused publication must not spawn Git"))
        calls.setattr(shell_tools.subprocess, "run", runner)
        result = shell_tools.shell(r.command, yolo=mode == "yolo")
        runner.assert_not_called()
    if mode == "declined":
        assert result == "[CANCELLED] User declined to run command."
    else:
        assert result.startswith("[BLOCKED]")
    assert prompt.call_count == int(mode == "declined")
    assert r.git("show-ref", cwd=r.remote, check=False).returncode == 1
    assert_record(gateway, r.command, "refused")


def test_approved_real_local_push_exact_ref(repository, gateway, monkeypatch):
    r = repository
    prompt = Mock(return_value=True)
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    original = subprocess.run
    with monkeypatch.context() as calls:
        runner = Mock(wraps=original)
        calls.setattr(shell_tools.subprocess, "run", runner)
        result = shell_tools.shell(r.command, timeout=19)
        runner.assert_called_once_with(shlex.split(r.command), capture_output=True, text=True, timeout=19)
    prompt.assert_called_once_with(f"Run shell command: `{r.command}`?")
    assert "[stderr]" in result and "main" in result
    assert r.git("rev-parse", "refs/heads/main", cwd=r.remote).stdout == r.git("rev-parse", "HEAD").stdout
    assert_record(gateway, r.command, "allowed")


def test_approval_preserves_raw_argv_timeout_and_output(gateway, monkeypatch):
    command = "git -C '/temporary/path with spaces' push origin HEAD:refs/heads/main"
    prompt = Mock(return_value=True)
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="original stdout\n", stderr="original stderr\n"))
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    assert shell_tools.shell(command, timeout=29) == "original stdout\n\n[stderr]\noriginal stderr"
    prompt.assert_called_once_with(f"Run shell command: `{command}`?")
    runner.assert_called_once_with(shlex.split(command), capture_output=True, text=True, timeout=29)
    assert_record(gateway, command, "allowed")


def test_real_agent_tools_shell_refuses_direct_push(gateway, monkeypatch):
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    command = "git -C /temporary/repo push"
    runner = Mock(side_effect=AssertionError("agent refused shell cannot execute"))
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    assert agent.TOOLS["shell"]({"command": command}).startswith("[BLOCKED]")
    runner.assert_not_called()
    assert_record(gateway, command, "refused")


def test_daemon_existing_push_rejection_is_high(gateway, monkeypatch):
    command = "git push origin main"
    shell = Mock(side_effect=AssertionError("daemon allowlist must still reject push"))
    monkeypatch.setattr(shell_tools, "shell", shell)
    monkeypatch.setattr(task_executor, "warning", Mock())
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert executor._daemon_shell(command).startswith("[BLOCKED] Daemon mode will not run")
    shell.assert_not_called()
    assert_record(gateway, command, "refused", action="task_executor.daemon_shell")
