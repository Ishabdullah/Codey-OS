"""Local branch mediation using isolated temporary Git repositories.

Run with config state redirected before gateway collection (NEW-855).
No project repository, remote, model, peer, or inference operation is used.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, git_execution, githelper
from core.action_gateway import ACT, ActionGateway, GatewayDecision


@pytest.fixture
def repository(tmp_path, monkeypatch):
    for name in list(os.environ):
        if name.startswith("GIT_") or name == "EMAIL":
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    empty = tmp_path / "empty-config"
    empty.mkdir()
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(empty))
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args, check=True):
        return subprocess.run([git_execution._trusted_git_executable(), *args], cwd=repo, capture_output=True, text=True, check=check)

    git("init", "-b", "main")
    for key, value in {
        "core.hooksPath": str(empty), "commit.gpgsign": "false", "tag.gpgsign": "false",
        "user.useConfigOnly": "true", "user.name": "Temporary Test",
        "user.email": "test@example.invalid",
    }.items():
        git("config", key, value)
    (repo / "staged.txt").write_text("staged baseline\n")
    (repo / "dirty.txt").write_text("dirty baseline\n")
    git("add", "--", "staged.txt", "dirty.txt")
    git("commit", "-m", "baseline")
    audit = tmp_path / "audit.jsonl"
    gateway = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: gateway)
    return SimpleNamespace(repo=repo, git=git, audit=audit, gateway=gateway)


def snapshot(r):
    return (
        r.git("show-ref").stdout, r.git("symbolic-ref", "HEAD").stdout,
        r.git("ls-files", "--stage").stdout,
        {path.name: path.read_bytes() for path in r.repo.iterdir() if path.is_file()},
    )


def assert_audit(r, outcome="allowed", reason="command executed"):
    records = [json.loads(line) for line in r.audit.read_text().splitlines()]
    assert len(records) == 1
    record = records[0]
    assert isinstance(record.pop("ts"), float)
    assert record == {
        "authority": ACT, "action": "githelper.git_branch_create",
        "command": "local git branch creation attempt",
        "outcome": outcome, "reason": reason,
    }


@pytest.mark.parametrize("explicit_path", [True, False], ids=["explicit-path", "cwd"])
def test_branch_success_preserves_head_staging_and_dirty(repository, tmp_path, monkeypatch, explicit_path):
    r = repository
    (r.repo / "staged.txt").write_text("staged change\n")
    (r.repo / "dirty.txt").write_text("dirty change\n")
    r.git("add", "--", "staged.txt")
    head = r.git("rev-parse", "HEAD").stdout.strip()
    entries = r.git("ls-files", "--stage").stdout
    if explicit_path:
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        result = githelper.git_branch_create("private-branch-name", path=str(r.repo))
        assert list(elsewhere.iterdir()) == []
    else:
        monkeypatch.chdir(r.repo)
        result = githelper.git_branch_create("private-branch-name")
    assert result == "Created and switched to branch 'private-branch-name'."
    assert r.git("rev-parse", "HEAD").stdout.strip() == head
    assert r.git("rev-parse", "main").stdout.strip() == head
    assert r.git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "private-branch-name"
    assert r.git("rev-list", "--count", "HEAD").stdout.strip() == "1"
    assert r.git("ls-files", "--stage").stdout == entries
    assert (r.repo / "staged.txt").read_text() == "staged change\n"
    assert (r.repo / "dirty.txt").read_text() == "dirty change\n"
    assert_audit(r)
    assert "private-branch-name" not in r.audit.read_text()


@pytest.mark.parametrize("case", ["duplicate", "non-repo", "git-invalid"])
def test_git_failure_preserves_exact_error_string(repository, tmp_path, case):
    r = repository
    before = snapshot(r)
    cwd = r.repo
    name = "main" if case == "duplicate" else "bad..name" if case == "git-invalid" else "new-branch"
    if case == "non-repo":
        cwd = tmp_path / "not-a-repo"
        cwd.mkdir()
    failure = subprocess.run(
        [git_execution._trusted_git_executable(), "checkout", "-b", name], cwd=cwd, capture_output=True, text=True, check=False,
    )
    assert failure.returncode != 0
    result = githelper.git_branch_create(name, path=str(cwd))
    assert result == f"[ERROR] {failure.stderr.strip()}"
    assert snapshot(r) == before
    assert_audit(r, "failed", result)


@pytest.mark.parametrize("name", ["", ".", "..", "-flag", "bad name", "bad~name", "bad:name", "bad[name"])
def test_rejected_names_do_not_reach_gateway_or_git(repository, monkeypatch, name):
    r = repository
    before = snapshot(r)
    gate = Mock(side_effect=AssertionError("invalid name must not reach gateway"))
    monkeypatch.setattr(r.gateway, "gate_exec", gate)
    with monkeypatch.context() as calls:
        runner = Mock(side_effect=AssertionError("invalid name must not invoke Git"))
        calls.setattr(git_execution.subprocess, "run", runner)
        result = githelper.git_branch_create(name, path=str(r.repo))
        runner.assert_not_called()
    expected = (
        f"[ERROR] Branch name cannot start with '-': '{name}'"
        if name.startswith("-") else f"[ERROR] Invalid branch name: '{name}'"
    )
    assert result == expected
    gate.assert_not_called()
    assert snapshot(r) == before
    assert not r.audit.exists()


def test_refusal_never_runs_git_or_changes_refs(repository, monkeypatch):
    r = repository
    before = snapshot(r)
    index = (r.repo / ".git/index").read_bytes()
    gate = Mock(return_value=GatewayDecision(ACT, "refused", "test policy"))
    monkeypatch.setattr(r.gateway, "gate_exec", gate)
    with monkeypatch.context() as calls:
        runner = Mock(side_effect=AssertionError("refusal must not invoke Git"))
        calls.setattr(git_execution.subprocess, "run", runner)
        assert githelper.git_branch_create("new-branch", path=str(r.repo)) == (
            "[ERROR] Local git branch creation refused: test policy"
        )
        runner.assert_not_called()
    assert snapshot(r) == before
    assert (r.repo / ".git/index").read_bytes() == index
    gate.assert_called_once()
    assert gate.call_args.kwargs["authority"] == ACT
    assert gate.call_args.kwargs["confirm_available"] is False
    assert gate.call_args.kwargs["command"] == "local git branch creation attempt"
    assert not r.audit.exists()


def test_subprocess_exception_object_is_preserved(repository, monkeypatch):
    r = repository
    original = OSError("original subprocess failure")
    runner = Mock(side_effect=original)
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    with pytest.raises(OSError) as caught:
        githelper.git_branch_create("new-branch", path=str(r.repo))
    assert caught.value is original
    runner.assert_called_once_with(
        [git_execution._trusted_git_executable(), "checkout", "-b", "new-branch"], capture_output=True, text=True, cwd=str(r.repo),
    )
    assert_audit(r, "failed", str(original))


def test_blocked_audit_directory_preserves_success(repository, tmp_path, monkeypatch):
    r = repository
    blocker = tmp_path / "audit-parent"
    blocker.write_text("blocker")
    monkeypatch.setattr(
        action_gateway, "get_action_gateway",
        lambda: ActionGateway(audit_file=blocker / "audit.jsonl"),
    )
    head = r.git("rev-parse", "HEAD").stdout.strip()
    assert githelper.git_branch_create("new-branch", path=str(r.repo)) == (
        "Created and switched to branch 'new-branch'."
    )
    assert r.git("rev-parse", "HEAD").stdout.strip() == head
    assert r.git("symbolic-ref", "HEAD").stdout.strip() == "refs/heads/new-branch"
    assert blocker.read_text() == "blocker"
    assert not (blocker / "audit.jsonl").exists()


def test_private_main_branch_handler_preserves_history(repository, monkeypatch):
    import core

    r = repository
    source = Path(__file__).resolve().parents[1] / "main.py"
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
        spec = importlib.util.spec_from_file_location("_branch_test_main", source)
        main = importlib.util.module_from_spec(spec)
        imports.setitem(sys.modules, spec.name, main)
        spec.loader.exec_module(main)
    monkeypatch.chdir(r.repo)
    monkeypatch.setattr(main, "success", Mock())
    monkeypatch.setattr(main, "error", Mock())
    monkeypatch.setattr(main, "_execute_agent_capability", Mock(side_effect=AssertionError("no agent loop")))
    monkeypatch.setattr(githelper, "generate_commit_message", Mock(side_effect=AssertionError("no inference")))
    history = [{"role": "user", "content": "existing"}]
    handled, returned = main.handle_command("/git branch main-branch", history)
    assert handled is True
    assert returned is history
    assert history == [{"role": "user", "content": "existing"}]
    main.success.assert_called_once_with("Created and switched to branch 'main-branch'.")
    main.error.assert_not_called()
    assert r.git("symbolic-ref", "HEAD").stdout.strip() == "refs/heads/main-branch"
    assert_audit(r)
