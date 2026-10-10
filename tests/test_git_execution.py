"""Invocation-time Git selection; real isolated Git and temporary state only."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, checkpoint, git_execution, githelper
from core.action_gateway import ActionGateway
from core.state import StateStore


@pytest.mark.parametrize(("prefix", "expected"), [("/installation", ["/installation/bin/git", "/usr/bin/git", "/bin/git"]), ("/usr", ["/usr/bin/git", "/bin/git"]), ("/", ["/bin/git", "/usr/bin/git"])])
def test_candidate_order_and_deduplication(monkeypatch, prefix, expected):
    monkeypatch.setattr(git_execution.sys, "base_prefix", prefix)
    assert git_execution._git_candidates() == tuple(Path(path) for path in expected)


def executable(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("temporary executable fixture")
    path.chmod(0o755)
    return path


def test_preferred_missing_falls_back_in_order_without_path_lookup(tmp_path, monkeypatch):
    preferred = tmp_path / "missing"
    second = executable(tmp_path / "second")
    third = executable(tmp_path / "third")
    monkeypatch.setattr(git_execution, "_git_candidates", lambda: (preferred, second, third))
    original = Path.lstat
    inspected = []

    def lstat(path):
        inspected.append(path)
        return original(path)

    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setenv("PATH", str(tmp_path / "untrusted"))
    monkeypatch.setenv("GIT_EXEC_PATH", str(tmp_path / "other"))
    getenv = Mock(side_effect=AssertionError("selection must not consult environment overrides"))
    monkeypatch.setattr(git_execution.os, "getenv", getenv)
    assert git_execution._trusted_git_executable() == str(second)
    assert inspected == [preferred, second]
    getenv.assert_not_called()


@pytest.mark.parametrize("kind", ["directory", "nonexecutable", "broken-link", "relative"])
def test_unusable_preferred_candidate_does_not_fall_back_or_spawn(tmp_path, monkeypatch, kind):
    preferred = tmp_path / "preferred"
    if kind == "directory":
        preferred.mkdir()
    elif kind == "nonexecutable":
        preferred.write_text("not executable")
        preferred.chmod(0o644)
    elif kind == "broken-link":
        preferred.symlink_to(tmp_path / "missing")
    else:
        preferred = Path("relative/git")
    fallback = executable(tmp_path / "fallback")
    monkeypatch.setattr(git_execution, "_git_candidates", lambda: (preferred, fallback))
    runner = Mock()
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    with pytest.raises(PermissionError):
        git_execution.run_git(["git", "status"])
    runner.assert_not_called()


def test_all_candidates_missing_is_explicit_and_never_spawns(tmp_path, monkeypatch):
    monkeypatch.setattr(git_execution, "_git_candidates", lambda: (tmp_path / "one", tmp_path / "two"))
    runner = Mock()
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    with pytest.raises(FileNotFoundError, match="trusted installation locations"):
        git_execution.run_git(["git", "status"])
    runner.assert_not_called()


def test_existing_installation_link_to_regular_executable_is_accepted(tmp_path, monkeypatch):
    target = executable(tmp_path / "target")
    link = tmp_path / "git"
    link.symlink_to(target)
    monkeypatch.setattr(git_execution, "_git_candidates", lambda: (link,))
    assert git_execution._trusted_git_executable() == str(link)


@pytest.mark.parametrize("vector", [["git", "status", "--", "operand with spaces"], ("git", "status", "--", "operand with spaces")])
def test_exact_forwarding_result_and_input_unchanged(monkeypatch, vector):
    before = list(vector)
    result = object()
    runner = Mock(return_value=result)
    selector = Mock(return_value="/trusted/bin/git")
    monkeypatch.setattr(git_execution, "_trusted_git_executable", selector)
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    environment = {"TEMP_TEST": "value"}
    kwargs = {"cwd": Path("/temporary/repository"), "capture_output": True, "text": True, "check": False, "timeout": 27, "env": environment, "input": "original input"}
    assert git_execution.run_git(vector, **kwargs) is result
    runner.assert_called_once_with(["/trusted/bin/git", *before[1:]], **kwargs)
    assert runner.call_args.kwargs["env"] is environment
    assert list(vector) == before
    selector.assert_called_once_with()


@pytest.mark.parametrize("vector", [None, [], (), "git status", ["/untrusted/git", "status"], ["other", "status"]])
def test_invalid_prefix_rejected_before_selection(monkeypatch, vector):
    forbidden = Mock()
    monkeypatch.setattr(git_execution, "_trusted_git_executable", forbidden)
    monkeypatch.setattr(git_execution.subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="literal 'git'"):
        git_execution.run_git(vector)
    forbidden.assert_not_called()


def test_selection_repeated_at_invocation_time(monkeypatch):
    selector = Mock(side_effect=["/first/git", "/second/git"])
    runner = Mock()
    monkeypatch.setattr(git_execution, "_trusted_git_executable", selector)
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    git_execution.run_git(["git", "status"])
    git_execution.run_git(["git", "status"])
    assert selector.call_count == 2
    assert [call.args[0][0] for call in runner.call_args_list] == ["/first/git", "/second/git"]


@pytest.mark.parametrize("stage", ["selection", "spawn"])
def test_original_exception_identity_preserved(monkeypatch, stage):
    original = OSError("original failure")
    monkeypatch.setattr(git_execution, "_trusted_git_executable", Mock(side_effect=original if stage == "selection" else None, return_value="/trusted/git"))
    runner = Mock(side_effect=original)
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    with pytest.raises(OSError) as caught:
        git_execution.run_git(["git", "status"])
    assert caught.value is original
    assert runner.call_count == int(stage == "spawn")


def test_import_has_no_selection_filesystem_or_subprocess_effect(monkeypatch):
    source = Path(git_execution.__file__)
    forbidden = Mock(side_effect=AssertionError("import must be pure"))
    monkeypatch.setattr(Path, "lstat", forbidden)
    monkeypatch.setattr(git_execution.os, "access", forbidden)
    monkeypatch.setattr(git_execution.subprocess, "run", forbidden)
    spec = importlib.util.spec_from_file_location("_private_git_execution", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.run_git)
    forbidden.assert_not_called()


@pytest.fixture
def repository(tmp_path, monkeypatch):
    trusted_git = git_execution._trusted_git_executable()
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
        return subprocess.run([trusted_git, *args], cwd=repo, capture_output=True, text=True, check=check)

    git("init", "-b", "main")
    for key, value in {"core.hooksPath": str(empty), "commit.gpgsign": "false", "tag.gpgsign": "false", "user.useConfigOnly": "true", "user.name": "Temporary Test", "user.email": "test@example.invalid"}.items():
        git("config", key, value)
    (repo / "core").mkdir()
    trigger = repo / "core/example.py"
    trigger.write_text("baseline = True\n")
    (repo / "other.txt").write_text("baseline other\n")
    git("add", "--", "core/example.py", "other.txt")
    git("commit", "-m", "baseline")
    state = StateStore(db_path=tmp_path / "state.db")
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: ActionGateway(audit_file=audit))
    monkeypatch.setattr(checkpoint, "CODE_DIR", repo)
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "backups")
    monkeypatch.setattr(checkpoint, "get_state_store", lambda: state)
    monkeypatch.setattr(checkpoint, "warning", Mock())
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    marker = tmp_path / "fake-git-used"
    fake = fake_bin / "git"
    fake.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nPath({str(marker)!r}).write_text('used')\nraise SystemExit(99)\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin))
    yield SimpleNamespace(repo=repo, trigger=trigger, state=state, audit=audit, git=git, marker=marker)
    state.close()


def test_fake_path_git_never_used_by_queries_and_local_commit(repository):
    r = repository
    assert githelper.is_git_repo(str(r.repo)) is True
    assert githelper.git_current_branch(str(r.repo)) == "main"
    assert githelper.git_status(str(r.repo)) == "Nothing to commit."
    assert "baseline" in githelper.git_log(path=str(r.repo))
    r.trigger.write_text("updated = True\n")
    assert "example.py" in githelper.git_diff_stat(str(r.repo))
    assert not githelper.git_commit_paths("trusted local commit", ["core/example.py"], str(r.repo)).startswith("[ERROR]")
    assert r.git("show", "HEAD:core/example.py").stdout == "updated = True\n"
    assert not r.marker.exists()
    assert len(r.audit.read_text().splitlines()) == 1


def test_fake_path_git_checkpoint_changed_scoped_and_clean_hash(repository):
    r = repository
    (r.repo / "other.txt").write_text("staged unrelated\n")
    r.git("add", "--", "other.txt")
    old_head = r.git("rev-parse", "HEAD").stdout.strip()
    assert checkpoint._create_git_commit("clean", [str(r.trigger)]) == old_head
    r.trigger.write_text("checkpoint_change = True\n")
    new_head = checkpoint._create_git_commit("changed", [str(r.trigger)])
    assert new_head == r.git("rev-parse", "HEAD").stdout.strip() and new_head != old_head
    assert r.git("show", "HEAD:other.txt").stdout == "baseline other\n"
    assert r.git("diff", "--cached", "--name-only").stdout.strip() == "other.txt"
    assert not r.marker.exists()
    assert [json.loads(line)["outcome"] for line in r.audit.read_text().splitlines()] == ["allowed", "allowed"]


@pytest.mark.parametrize("operation", ["push", "rollback"])
@pytest.mark.parametrize("confirmation", [None, False])
def test_refusal_does_not_select_or_spawn_and_keeps_effects(repository, monkeypatch, operation, confirmation):
    r = repository
    head = r.git("rev-parse", "HEAD").stdout
    index = (r.repo / ".git/index").read_bytes()
    content = r.trigger.read_bytes()
    forbidden = Mock(side_effect=AssertionError("refusal cannot select or spawn"))
    with monkeypatch.context() as calls:
        calls.setattr(git_execution, "_trusted_git_executable", forbidden)
        calls.setattr(git_execution.subprocess, "run", forbidden)
        callback = None if confirmation is None else lambda: False
        if operation == "push":
            assert githelper.git_push(str(r.repo), confirm=callback).startswith("[ERROR] Git push refused:")
        else:
            assert checkpoint.rollback("not-read", confirm=callback) is False
        forbidden.assert_not_called()
    assert r.git("rev-parse", "HEAD").stdout == head
    assert (r.repo / ".git/index").read_bytes() == index
    assert r.trigger.read_bytes() == content and not r.marker.exists()
    rows = [json.loads(line) for line in r.audit.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["outcome"] == "refused" and rows[0]["authority"] == "HIGH_IMPACT"


def test_missing_git_preserves_helper_exception_checkpoint_none_without_old_head(repository, monkeypatch):
    r = repository
    original = FileNotFoundError("trusted Git missing")
    selector = Mock(side_effect=original)
    monkeypatch.setattr(git_execution, "_trusted_git_executable", selector)
    with pytest.raises(FileNotFoundError) as caught:
        githelper.git_status(str(r.repo))
    assert caught.value is original
    assert checkpoint._create_git_commit("missing", [str(r.trigger)]) is None
    checkpoint.warning.assert_called_once_with("Checkpoint: git commit failed: trusted Git missing")
    rows = [json.loads(line) for line in r.audit.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["outcome"] == "failed" and rows[0]["authority"] == "ACT"
    assert rows[0]["reason"] == str(original) and not r.marker.exists()


def test_preferred_inspection_error_does_not_silently_fall_back(tmp_path, monkeypatch):
    preferred, fallback = tmp_path / "preferred", tmp_path / "fallback"
    monkeypatch.setattr(git_execution, "_git_candidates", lambda: (preferred, fallback))
    failure = PermissionError("preferred inspection denied")
    inspector = Mock(side_effect=failure)
    runner = Mock()
    monkeypatch.setattr(Path, "lstat", inspector)
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    with pytest.raises(PermissionError) as caught:
        git_execution.run_git(["git", "status"])
    assert caught.value is failure
    inspector.assert_called_once_with()
    runner.assert_not_called()


@pytest.mark.parametrize("operation", ["helper-commit", "checkpoint-thunk"])
def test_missing_git_during_mediated_mutation_is_failed_without_old_head(repository, monkeypatch, operation):
    r = repository
    trusted_git = git_execution._trusted_git_executable()
    old_head = r.git("rev-parse", "HEAD").stdout
    failure = FileNotFoundError("trusted Git disappeared")
    selector = Mock(side_effect=failure if operation == "helper-commit" else [trusted_git, failure])
    monkeypatch.setattr(git_execution, "_trusted_git_executable", selector)
    if operation == "helper-commit":
        with pytest.raises(FileNotFoundError) as caught:
            githelper.git_commit_paths("missing", ["core/example.py"], str(r.repo))
        assert caught.value is failure
    else:
        r.trigger.write_text("pending change\n")
        assert checkpoint._create_git_commit("missing", [str(r.trigger)]) is None
        checkpoint.warning.assert_called_once_with("Checkpoint: git commit failed: trusted Git disappeared")
    assert r.git("rev-parse", "HEAD").stdout == old_head
    rows = [json.loads(line) for line in r.audit.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["outcome"] == "failed" and rows[0]["reason"] == str(failure)
    assert not r.marker.exists()
