"""Local commit mediation using fresh, isolated temporary Git repositories.

Run with config state paths redirected before gateway/agent collection.
No project repository, model, peer, or remote Git operation is used.
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

from core import action_gateway, githelper
from core.action_gateway import ACT, ActionGateway, GatewayDecision


@pytest.fixture
def repository(tmp_path, monkeypatch):
    # Clear every inherited Git injection/identity/repository variable before
    # even git init, then disable system/global config, templates, hooks, signing.
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
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=check,
        )

    git("init", "-b", "main")
    for key, value in {
        "core.hooksPath": str(empty), "commit.gpgsign": "false",
        "tag.gpgsign": "false", "user.useConfigOnly": "true",
        "user.name": "Temporary Test", "user.email": "test@example.invalid",
    }.items():
        git("config", key, value)
    (repo / "one.txt").write_text("one baseline\n")
    (repo / "two.txt").write_text("two baseline\n")
    git("add", "--", "one.txt", "two.txt")
    git("commit", "-m", "baseline")
    audit = tmp_path / "audit.jsonl"
    gateway = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: gateway)
    return SimpleNamespace(repo=repo, git=git, audit=audit, gateway=gateway)


def records(r):
    return [json.loads(line) for line in r.audit.read_text().splitlines()]


def assert_audit(r, action, outcome="allowed", reason="command executed"):
    ledger = records(r)
    assert len(ledger) == 1
    record = ledger[0]
    assert isinstance(record.pop("ts"), float)
    assert record == {
        "authority": ACT, "action": action, "command": "local git commit attempt",
        "outcome": outcome, "reason": reason,
    }


def invoke(r, scoped, message="test commit"):
    if scoped:
        return githelper.git_commit_paths(message, ["one.txt"], path=str(r.repo))
    return githelper.git_commit(message, path=str(r.repo))


def snapshot(r):
    return (
        r.git("rev-parse", "HEAD").stdout,
        (r.repo / ".git/index").read_bytes(),
        {path.name: path.read_bytes() for path in r.repo.iterdir() if path.is_file()},
    )


def test_broad_commit_content_history_and_static_audit(repository):
    r = repository
    parent = r.git("rev-parse", "HEAD").stdout.strip()
    (r.repo / "one.txt").write_text("one changed\n")
    (r.repo / "new-secret.txt").write_text("private-content-unique\n")
    result = githelper.git_commit("private-message-unique", path=str(r.repo))
    assert "private-message-unique" in result
    assert r.git("rev-parse", "HEAD^").stdout.strip() == parent
    assert r.git("rev-list", "--count", "HEAD").stdout.strip() == "2"
    assert r.git("log", "-1", "--format=%s").stdout.strip() == "private-message-unique"
    assert r.git("show", "HEAD:one.txt").stdout == "one changed\n"
    assert r.git("show", "HEAD:new-secret.txt").stdout == "private-content-unique\n"
    assert r.git("status", "--porcelain").stdout == ""
    assert_audit(r, "githelper.git_commit")
    for private in ("private-message-unique", "private-content-unique", "new-secret.txt"):
        assert private not in r.audit.read_text()


def test_scoped_commit_excludes_dirty_and_already_staged(repository):
    r = repository
    (r.repo / "one.txt").write_text("one changed\n")
    (r.repo / "two.txt").write_text("two staged\n")
    (r.repo / "unrelated.txt").write_text("unrelated dirty\n")
    r.git("add", "--", "two.txt")
    assert not invoke(r, True).startswith("[ERROR]")
    assert r.git("show", "HEAD:one.txt").stdout == "one changed\n"
    assert r.git("show", "HEAD:two.txt").stdout == "two baseline\n"
    assert r.git("diff", "--cached", "--name-only").stdout.strip() == "two.txt"
    assert r.git("status", "--porcelain").stdout.splitlines() == ["M  two.txt", "?? unrelated.txt"]
    assert_audit(r, "githelper.git_commit_paths")


def test_add_all_false_commits_only_staged(repository):
    r = repository
    (r.repo / "one.txt").write_text("one staged\n")
    (r.repo / "two.txt").write_text("two unstaged\n")
    r.git("add", "--", "one.txt")
    result = githelper.git_commit("staged only", path=str(r.repo), add_all=False)
    assert not result.startswith("[ERROR]")
    assert r.git("show", "HEAD:one.txt").stdout == "one staged\n"
    assert r.git("show", "HEAD:two.txt").stdout == "two baseline\n"
    assert r.git("status", "--porcelain").stdout.strip() == "M two.txt"
    assert_audit(r, "githelper.git_commit")


@pytest.mark.parametrize("scoped", [False, True])
def test_clean_attempt_preserves_exact_string(repository, scoped):
    r = repository
    before = r.git("rev-parse", "HEAD").stdout
    assert invoke(r, scoped) == "Nothing to commit — working tree clean."
    assert r.git("rev-parse", "HEAD").stdout == before
    assert_audit(r, "githelper.git_commit_paths" if scoped else "githelper.git_commit")


def test_no_paths_attempt_preserves_exact_string(repository):
    r = repository
    before = snapshot(r)
    assert githelper.git_commit_paths("unused", [], path=str(r.repo)) == "Nothing to commit."
    assert snapshot(r) == before
    assert_audit(r, "githelper.git_commit_paths")


@pytest.mark.parametrize("scoped", [False, True])
def test_non_repository_is_failed_exact_string(repository, tmp_path, scoped):
    r = repository
    empty = tmp_path / "not-a-repo"
    empty.mkdir()
    if scoped:
        result = githelper.git_commit_paths("unused", [], path=str(empty))
    else:
        result = githelper.git_commit("unused", path=str(empty))
    assert result == "[ERROR] Not a git repository."
    assert_audit(r, "githelper.git_commit_paths" if scoped else "githelper.git_commit", "failed", result)


def test_real_add_failure_preserves_error_string(repository):
    r = repository
    before = snapshot(r)
    stderr = r.git("add", "--", "missing-path", check=False).stderr
    result = githelper.git_commit_paths("unused", ["missing-path"], path=str(r.repo))
    assert result == f"[ERROR] git add failed: {stderr}"
    assert snapshot(r) == before
    assert_audit(r, "githelper.git_commit_paths", "failed", result)


@pytest.mark.parametrize("scoped", [False, True])
def test_missing_identity_commit_failure_retains_staging(repository, scoped):
    r = repository
    (r.repo / "one.txt").write_text("one changed\n")
    r.git("config", "--unset", "user.name")
    r.git("config", "--unset", "user.email")
    before = r.git("rev-parse", "HEAD").stdout
    result = invoke(r, scoped)
    assert result.startswith("[ERROR]")
    assert "identity" in result.lower()
    assert r.git("rev-parse", "HEAD").stdout == before
    assert r.git("diff", "--cached", "--name-only").stdout.strip() == "one.txt"
    assert_audit(r, "githelper.git_commit_paths" if scoped else "githelper.git_commit", "failed", result)


@pytest.mark.parametrize("scoped", [False, True])
def test_refusal_never_runs_subprocess_or_mutates(repository, scoped, monkeypatch):
    r = repository
    (r.repo / "one.txt").write_text("one changed\n")
    r.git("add", "--", "one.txt")
    (r.repo / "two.txt").write_text("two dirty\n")
    before = snapshot(r)
    gate = Mock(return_value=GatewayDecision(ACT, "refused", "test policy"))
    monkeypatch.setattr(r.gateway, "gate_exec", gate)
    with monkeypatch.context() as calls:
        runner = Mock(side_effect=AssertionError("refusal must not invoke Git"))
        calls.setattr(githelper.subprocess, "run", runner)
        assert invoke(r, scoped) == "[ERROR] Local git commit refused: test policy"
        runner.assert_not_called()
    assert snapshot(r) == before
    gate.assert_called_once()
    assert gate.call_args.kwargs["authority"] == ACT
    assert gate.call_args.kwargs["confirm_available"] is False
    assert gate.call_args.kwargs["command"] == "local git commit attempt"
    assert not r.audit.exists()


@pytest.mark.parametrize("scoped", [False, True])
def test_subprocess_exception_identity_is_preserved(repository, scoped, monkeypatch):
    r = repository
    failure = OSError("original subprocess error")
    runner = Mock(side_effect=failure)
    monkeypatch.setattr(githelper.subprocess, "run", runner)
    with pytest.raises(OSError) as caught:
        invoke(r, scoped)
    assert caught.value is failure
    runner.assert_called_once()
    assert_audit(r, "githelper.git_commit_paths" if scoped else "githelper.git_commit", "failed", str(failure))


def test_blocked_audit_sink_does_not_hide_successful_commit(repository, tmp_path, monkeypatch):
    r = repository
    blocker = tmp_path / "audit-parent"
    blocker.write_text("blocker")
    gateway = ActionGateway(audit_file=blocker / "audit.jsonl")
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: gateway)
    (r.repo / "one.txt").write_text("one changed\n")
    assert not invoke(r, False).startswith("[ERROR]")
    assert r.git("show", "HEAD:one.txt").stdout == "one changed\n"
    assert r.git("log", "-1", "--format=%s").stdout.strip() == "test commit"
    assert blocker.read_text() == "blocker"
    assert not (blocker / "audit.jsonl").exists()


@pytest.mark.parametrize("accept", [False, True], ids=["decline", "accept"])
def test_real_agent_commit_offer(repository, monkeypatch, accept):
    from core import agent
    from utils import logger

    r = repository
    monkeypatch.chdir(r.repo)
    monkeypatch.setattr(logger, "confirm", Mock(return_value=accept))
    monkeypatch.setattr(agent, "infer", Mock(side_effect=AssertionError("no inference")))
    monkeypatch.setattr(agent, "run_agent", Mock(side_effect=AssertionError("no agent loop")))
    (r.repo / "one.txt").write_text("one changed\n")
    before = r.git("rev-parse", "HEAD").stdout
    assert agent.check_git_and_offer_commit("fix a bug", ["write_file"], ["one.txt"]) is None
    if accept:
        assert r.git("log", "-1", "--format=%s").stdout.strip() == "Codey: fix a bug..."
        assert r.git("show", "HEAD:one.txt").stdout == "one changed\n"
        assert_audit(r, "githelper.git_commit_paths")
    else:
        assert r.git("rev-parse", "HEAD").stdout == before
        assert not r.audit.exists()


def test_private_main_explicit_commit_handler(repository, monkeypatch):
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
        spec = importlib.util.spec_from_file_location("_git_test_main", source)
        main = importlib.util.module_from_spec(spec)
        imports.setitem(sys.modules, spec.name, main)
        spec.loader.exec_module(main)
    monkeypatch.chdir(r.repo)
    monkeypatch.setattr(main, "success", Mock())
    monkeypatch.setattr(main, "error", Mock())
    monkeypatch.setattr(githelper, "generate_commit_message", Mock(side_effect=AssertionError("no generation")))
    (r.repo / "one.txt").write_text("one changed\n")
    history = [{"role": "user", "content": "existing"}]
    handled, returned = main.handle_command("/git commit explicit message", history)
    assert handled is True
    assert returned is history
    assert history == [{"role": "user", "content": "existing"}]
    assert r.git("log", "-1", "--format=%s").stdout.strip() == "explicit message"
    assert r.git("show", "HEAD:one.txt").stdout == "one changed\n"
    main.success.assert_called_once()
    main.error.assert_not_called()
    assert_audit(r, "githelper.git_commit")
