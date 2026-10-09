"""Scoped checkpoint commits in isolated temporary Git and SQLite stores.

Use the bounded runner to redirect config state before collection (NEW-855).
No Filesystem.write, live repository, model, peer, or remote operation is used.
"""

import json
import os
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, checkpoint, git_execution
from core.action_gateway import ACT, ActionGateway, GatewayDecision
from core.state import StateStore


@pytest.fixture
def checkpoint_repo(tmp_path, monkeypatch, request):
    for name in list(os.environ):
        if name.startswith("GIT_") or name == "EMAIL":
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    empty = tmp_path / "empty-config"
    empty.mkdir()
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(empty))
    child_home = tmp_path / "child-home"
    child_xdg = tmp_path / "child-xdg"
    child_home.mkdir()
    child_xdg.mkdir()
    original_environment = git_execution._local_commit_environment

    def child_environment():
        environment = original_environment()
        environment.update(HOME=str(child_home), XDG_CONFIG_HOME=str(child_xdg))
        return environment

    monkeypatch.setattr(git_execution, "_local_commit_environment", child_environment)
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
    (repo / "core").mkdir()
    trigger = repo / "core/example.py"
    trigger.write_text("baseline = True\n")
    (repo / "other.txt").write_text("other baseline\n")
    if getattr(request, "param", True):
        git("add", "--", "core/example.py", "other.txt")
        git("commit", "-m", "baseline")
    audit = tmp_path / "audit.jsonl"
    gateway = ActionGateway(audit_file=audit)
    state = StateStore(db_path=tmp_path / "state.db")
    backups = tmp_path / "checkpoints"
    monkeypatch.setattr(checkpoint, "CODE_DIR", repo)
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", backups)
    monkeypatch.setattr(checkpoint, "get_state_store", lambda: state)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: gateway)
    warnings = Mock()
    monkeypatch.setattr(checkpoint, "warning", warnings)
    yield SimpleNamespace(
        repo=repo, git=git, trigger=trigger, audit=audit, gateway=gateway,
        state=state, backups=backups, warnings=warnings,
    )
    state.close()


def assert_audit(r, outcome="allowed", reason="command executed"):
    ledger = [json.loads(line) for line in r.audit.read_text().splitlines()]
    assert len(ledger) == 1
    record = ledger[0]
    assert isinstance(record.pop("ts"), float)
    assert record == {
        "authority": ACT, "action": "checkpoint.create_git_commit",
        "command": "checkpoint local git commit attempt",
        "outcome": outcome, "reason": reason,
    }


def test_changed_trigger_excludes_unrelated_staged_and_dirty(checkpoint_repo):
    r = checkpoint_repo
    old_head = r.git("rev-parse", "HEAD").stdout.strip()
    r.trigger.write_text("private_content = True\n")
    (r.repo / "other.txt").write_text("other staged\n")
    (r.repo / "dirty.txt").write_text("unrelated dirty\n")
    r.git("add", "--", "other.txt")
    result = checkpoint._create_git_commit("private-reason", [str(r.trigger)])
    assert result == r.git("rev-parse", "HEAD").stdout.strip()
    assert r.git("rev-parse", "HEAD^").stdout.strip() == old_head
    assert r.git("log", "-1", "--format=%s").stdout.strip() == "Codey checkpoint: private-reason"
    assert r.git("show", "HEAD:core/example.py").stdout == "private_content = True\n"
    assert r.git("show", "HEAD:other.txt").stdout == "other baseline\n"
    assert r.git("diff", "--cached", "--name-only").stdout.strip() == "other.txt"
    assert (r.repo / "dirty.txt").read_text() == "unrelated dirty\n"
    assert_audit(r)
    for secret in ("private-reason", "private_content", str(r.trigger)):
        assert secret not in r.audit.read_text()


def test_clean_trigger_does_not_commit_unrelated_index(checkpoint_repo):
    r = checkpoint_repo
    (r.repo / "other.txt").write_text("other staged\n")
    r.git("add", "--", "other.txt")
    head = r.git("rev-parse", "HEAD").stdout.strip()
    # git add may refresh index cache metadata; compare staged entries.
    index_entries = r.git("ls-files", "--stage").stdout
    assert checkpoint._create_git_commit("clean", ["core/example.py"]) == head
    assert r.git("rev-parse", "HEAD").stdout.strip() == head
    assert r.git("ls-files", "--stage").stdout == index_entries
    assert r.git("diff", "--cached", "--name-only").stdout.strip() == "other.txt"
    assert_audit(r)


@pytest.mark.parametrize("files", [None, []], ids=["none", "empty"])
@pytest.mark.parametrize("checkpoint_repo", [True, False], indirect=True, ids=["has-head", "unborn"])
def test_no_paths_are_read_only_without_mutation_audit(checkpoint_repo, files):
    r = checkpoint_repo
    head = r.git("rev-parse", "HEAD", check=False)
    index_path = r.repo / ".git/index"
    index = index_path.read_bytes() if index_path.exists() else None
    assert checkpoint._create_git_commit("read only", files) == (
        head.stdout.strip() if head.returncode == 0 else None
    )
    assert (index_path.read_bytes() if index_path.exists() else None) == index
    assert not r.audit.exists()


def test_no_repository_is_read_only_without_mutation_audit(checkpoint_repo, tmp_path, monkeypatch):
    r = checkpoint_repo
    empty = tmp_path / "not-a-repo"
    empty.mkdir()
    monkeypatch.setattr(checkpoint, "CODE_DIR", empty)
    assert checkpoint._create_git_commit("no repo", ["missing.py"]) is None
    assert not r.audit.exists()
    assert list(empty.iterdir()) == []


@pytest.mark.parametrize("checkpoint_repo", [False], indirect=True)
def test_initial_commit_with_nonempty_paths(checkpoint_repo):
    r = checkpoint_repo
    result = checkpoint._create_git_commit("initial", ["core/example.py"])
    assert result == r.git("rev-parse", "HEAD").stdout.strip()
    assert r.git("rev-list", "--count", "HEAD").stdout.strip() == "1"
    assert r.git("show", "HEAD:core/example.py").stdout == "baseline = True\n"
    assert r.git("ls-tree", "--name-only", "HEAD").stdout.strip() == "core"
    assert_audit(r)


def test_invalid_add_fails_without_old_head_fallback(checkpoint_repo, monkeypatch):
    r = checkpoint_repo
    head = r.git("rev-parse", "HEAD").stdout.strip()
    with monkeypatch.context() as calls:
        runner = Mock(wraps=subprocess.run)
        calls.setattr(git_execution.subprocess, "run", runner)
        assert checkpoint._create_git_commit("invalid", ["missing.py"]) is None
    commands = [call.args[0] for call in runner.call_args_list]
    assert commands == [[git_execution._trusted_git_executable(), "rev-parse", "--git-dir"], [git_execution._trusted_git_executable(), "add", "--", "missing.py"]]
    assert r.git("rev-parse", "HEAD").stdout.strip() == head
    reason = r.warnings.call_args.args[0].split("Checkpoint: git commit failed: ", 1)[1]
    assert reason.startswith("git add failed:")
    assert_audit(r, "failed", reason)


def test_commit_failure_retains_staging_and_returns_none(checkpoint_repo):
    r = checkpoint_repo
    r.trigger.write_text("changed = True\n")
    r.git("config", "--unset", "user.name")
    r.git("config", "--unset", "user.email")
    head = r.git("rev-parse", "HEAD").stdout.strip()
    assert checkpoint._create_git_commit("no identity", ["core/example.py"]) is None
    assert r.git("rev-parse", "HEAD").stdout.strip() == head
    assert r.git("diff", "--cached", "--name-only").stdout.strip() == "core/example.py"
    reason = r.warnings.call_args.args[0].split("Checkpoint: git commit failed: ", 1)[1]
    assert reason.startswith("git commit failed:")
    assert_audit(r, "failed", reason)


def test_diff_error_is_not_treated_as_changes(checkpoint_repo, monkeypatch):
    r = checkpoint_repo
    r.trigger.write_text("changed = True\n")
    head = r.git("rev-parse", "HEAD").stdout.strip()
    real_run = subprocess.run
    commands = []

    def run(args, **kwargs):
        commands.append(args)
        if args[:4] == [git_execution._trusted_git_executable(), "diff", "--cached", "--quiet"]:
            return subprocess.CompletedProcess(args, 2, "", "diff failed")
        return real_run(args, **kwargs)

    with monkeypatch.context() as calls:
        calls.setattr(git_execution.subprocess, "run", run)
        assert checkpoint._create_git_commit("diff error", ["core/example.py"]) is None
    assert not any(args[:2] == [git_execution._trusted_git_executable(), "commit"] for args in commands)
    assert r.git("rev-parse", "HEAD").stdout.strip() == head
    assert_audit(r, "failed", "git diff failed: diff failed")


def test_final_head_failure_reports_failure_after_real_commit(checkpoint_repo, monkeypatch):
    r = checkpoint_repo
    r.trigger.write_text("changed = True\n")
    head = r.git("rev-parse", "HEAD").stdout.strip()
    real_run = subprocess.run

    def run(args, **kwargs):
        if args == [git_execution._trusted_git_executable(), "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 1, "", "HEAD lookup failed")
        return real_run(args, **kwargs)

    with monkeypatch.context() as calls:
        calls.setattr(git_execution.subprocess, "run", run)
        assert checkpoint._create_git_commit("HEAD error", ["core/example.py"]) is None
    # A failed attempt audit does not imply the earlier commit was undone.
    assert r.git("rev-parse", "HEAD").stdout.strip() != head
    assert r.git("show", "HEAD:core/example.py").stdout == "changed = True\n"
    assert_audit(r, "failed", "git rev-parse HEAD failed: HEAD lookup failed")


def test_refusal_never_stages_or_commits(checkpoint_repo, monkeypatch):
    r = checkpoint_repo
    r.trigger.write_text("changed = True\n")
    head = r.git("rev-parse", "HEAD").stdout.strip()
    index = (r.repo / ".git/index").read_bytes()
    gate = Mock(return_value=GatewayDecision(ACT, "refused", "test policy"))
    monkeypatch.setattr(r.gateway, "gate_exec", gate)
    with monkeypatch.context() as calls:
        runner = Mock(wraps=subprocess.run)
        calls.setattr(git_execution.subprocess, "run", runner)
        assert checkpoint._create_git_commit("refused", ["core/example.py"]) is None
    assert [call.args[0] for call in runner.call_args_list] == [[git_execution._trusted_git_executable(), "rev-parse", "--git-dir"]]
    assert r.git("rev-parse", "HEAD").stdout.strip() == head
    assert (r.repo / ".git/index").read_bytes() == index
    assert r.trigger.read_text() == "changed = True\n"
    assert gate.call_args.kwargs["authority"] == ACT
    assert gate.call_args.kwargs["confirm_available"] is False
    assert not r.audit.exists()
    r.warnings.assert_called_once_with("Checkpoint: git commit refused: test policy")


def test_blocked_audit_sink_preserves_committed_hash(checkpoint_repo, tmp_path, monkeypatch):
    r = checkpoint_repo
    blocker = tmp_path / "audit-parent"
    blocker.write_text("blocker")
    gateway = ActionGateway(audit_file=blocker / "audit.jsonl")
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: gateway)
    r.trigger.write_text("changed = True\n")
    assert checkpoint._create_git_commit("blocked audit", ["core/example.py"]) == r.git("rev-parse", "HEAD").stdout.strip()
    assert r.git("show", "HEAD:core/example.py").stdout == "changed = True\n"
    assert not (blocker / "audit.jsonl").exists()
    assert blocker.read_text() == "blocker"


@pytest.mark.parametrize("failure", [False, True], ids=["success", "commit-failure"])
def test_create_checkpoint_preserves_backups_and_real_sqlite_row(checkpoint_repo, failure):
    r = checkpoint_repo
    r.trigger.write_text("backup_content = True\n")
    if failure:
        r.git("config", "--unset", "user.name")
        r.git("config", "--unset", "user.email")
    checkpoint_id = checkpoint.create_checkpoint("integration", [str(r.trigger)])
    assert isinstance(checkpoint_id, str)
    assert (r.backups / checkpoint_id / "core/example.py").read_text() == "backup_content = True\n"
    row = r.state.get_checkpoint(checkpoint_id)
    assert row["id"] == checkpoint_id
    assert row["reason"] == "integration"
    assert json.loads(row["files_modified"]) == [str(r.trigger)]
    if failure:
        assert row["git_commit_hash"] is None
        assert r.git("rev-list", "--count", "HEAD").stdout.strip() == "1"
    else:
        assert row["git_commit_hash"] == r.git("rev-parse", "HEAD").stdout.strip()
        assert r.git("rev-list", "--count", "HEAD").stdout.strip() == "2"
    ledger = [json.loads(line) for line in r.audit.read_text().splitlines()]
    assert len(ledger) == 1
    assert ledger[0]["outcome"] == ("failed" if failure else "allowed")
