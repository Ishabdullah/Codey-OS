"""Authorized rollback in disposable Git/backups/SQLite; isolate state before collection."""

import json
import os
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, checkpoint, git_execution
from core.action_gateway import HIGH_IMPACT, ActionGateway
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
    monkeypatch.setattr(checkpoint, "success", Mock())
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
        "authority": HIGH_IMPACT, "action": "checkpoint.rollback",
        "command": "checkpoint restore attempt",
        "outcome": outcome, "reason": reason,
    }


def backup(r, checkpoint_id="saved", git_hash=None, *, row=True):
    directory = r.backups / checkpoint_id
    (directory / "core").mkdir(parents=True)
    (directory / "core/example.py").write_text("restored = True\n")
    if row:
        r.state.execute(
            "INSERT INTO checkpoints (id, created_at, reason, files_modified, git_commit_hash) VALUES (?, ?, ?, ?, ?)",
            (checkpoint_id, 1, "temporary", "[]", git_hash),
        )
    return directory


def audit_outcome(r, outcome, reason=None, preflight=False):
    rows = [json.loads(line) for line in r.audit.read_text().splitlines()]
    if preflight:
        query = rows.pop(0)
        assert isinstance(query.pop("ts"), float)
        assert query == {"authority": "READ", "action": "checkpoint.git_head", "command": "checkpoint Git HEAD query", "outcome": "allowed", "reason": "command executed"}
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row.pop("ts"), float)
    assert row["authority"] == HIGH_IMPACT
    assert row["action"] == "checkpoint.rollback"
    assert row["command"] == "checkpoint restore attempt"
    assert row["outcome"] == outcome
    if reason is not None:
        assert row["reason"] == reason
    assert set(row) == {"authority", "action", "command", "outcome", "reason"}
    return row


@pytest.mark.parametrize(
    "confirmation",
    [None, False, "yes", EOFError(), KeyboardInterrupt(), RuntimeError("private callback"), "not-callable"],
)
def test_denial_does_no_work(checkpoint_repo, monkeypatch, confirmation):
    r = checkpoint_repo
    forbidden = Mock(side_effect=AssertionError("refusal cannot do work"))
    monkeypatch.setattr(checkpoint, "get_state_store", forbidden)
    monkeypatch.setattr(checkpoint, "_rollback_files", forbidden)
    monkeypatch.setattr(checkpoint.shutil, "copy2", forbidden)
    monkeypatch.setattr(git_execution.subprocess, "run", forbidden)
    if confirmation is None or confirmation == "not-callable":
        callback = confirmation
    elif isinstance(confirmation, BaseException):
        callback = Mock(side_effect=confirmation)
    else:
        callback = Mock(return_value=confirmation)
    assert checkpoint.rollback("not-even-looked-up", confirm=callback) is False
    forbidden.assert_not_called()
    checkpoint.success.assert_not_called()
    row = audit_outcome(r, "refused")
    assert "private callback" not in row["reason"]
    if callable(callback):
        callback.assert_called_once_with()


def test_create_checkpoint_and_full_repository_detached_restore(checkpoint_repo, monkeypatch):
    r = checkpoint_repo
    (r.repo / "codeyOS").write_text("original executable\n")
    (r.repo / "codeyOS").chmod(0o755)
    r.git("add", "--", "codeyOS")
    r.git("commit", "-m", "executable baseline")
    saved_hash = r.git("rev-parse", "HEAD").stdout.strip()
    checkpoint_id = checkpoint.create_checkpoint("private reason", [])
    assert r.state.get_checkpoint(checkpoint_id)["git_commit_hash"] == saved_hash
    assert (r.backups / checkpoint_id / "codeyOS").stat().st_mode & 0o111
    r.trigger.write_text("new version = True\n")
    (r.repo / "other.txt").write_text("versioned non-backup change\n")
    (r.repo / "codeyOS").write_text("new executable\n")
    (r.repo / "codeyOS").chmod(0o644)
    r.git("add", "--", "other.txt")
    r.git("commit", "-m", "later version")
    checkpoint.success.reset_mock()
    original_run = subprocess.run
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return original_run(args, **kwargs)

    with monkeypatch.context() as operations:
        operations.setattr(git_execution.subprocess, "run", run)
        assert checkpoint.rollback(checkpoint_id, confirm=lambda: True) is True
    assert calls == [
        ([git_execution._trusted_git_executable(), "cat-file", "-t", saved_hash], {"cwd": r.repo, "capture_output": True, "text": True}),
        ([git_execution._trusted_git_executable(), "checkout", "--detach", saved_hash, "--"], {"cwd": r.repo, "capture_output": True, "text": True}),
    ]
    assert r.git("rev-parse", "HEAD").stdout.strip() == saved_hash
    assert r.git("symbolic-ref", "HEAD", check=False).returncode != 0
    assert r.trigger.read_text() == "baseline = True\n"
    assert (r.repo / "other.txt").read_text() == "other baseline\n"
    assert (r.repo / "codeyOS").read_text() == "original executable\n"
    assert (r.repo / "codeyOS").stat().st_mode & 0o111
    assert r.state.get_recent_actions()[0]["action"] == "rollback"
    checkpoint.success.assert_called_once()
    row = audit_outcome(r, "allowed", preflight=True)
    for secret in (checkpoint_id, saved_hash, "private reason", "baseline = True"):
        assert secret not in json.dumps(row)


@pytest.mark.parametrize("row", [True, False], ids=["null-hash", "missing-row"])
def test_file_only_compatibility_and_recursive_producer_scope(checkpoint_repo, monkeypatch, row):
    r = checkpoint_repo
    directory = backup(r, row=row)
    for name in ("tools/sub/module.py", "utils/deep/module.py", "prompts/sub/module.py", "main.py", "codey", "codeyOS"):
        source = directory / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"saved {name}\n")
    forbidden = Mock(side_effect=AssertionError("no Git for file-only"))
    with monkeypatch.context() as calls:
        calls.setattr(git_execution.subprocess, "run", forbidden)
        assert checkpoint.rollback("saved", confirm=lambda: True) is True
        forbidden.assert_not_called()
    assert r.trigger.read_text() == "restored = True\n"
    for name in ("tools/sub/module.py", "utils/deep/module.py", "prompts/sub/module.py", "main.py", "codey", "codeyOS"):
        assert (r.repo / name).read_text() == f"saved {name}\n"
    assert r.state.get_recent_actions()[0]["action"] == "rollback"
    audit_outcome(r, "allowed")


def test_empty_file_only_backup_is_allowed(checkpoint_repo):
    r = checkpoint_repo
    (r.backups / "empty").mkdir(parents=True)
    before = r.trigger.read_bytes()
    assert checkpoint.rollback("empty", confirm=lambda: True) is True
    assert r.trigger.read_bytes() == before
    assert len(r.state.get_recent_actions()) == 1
    audit_outcome(r, "allowed")


@pytest.mark.parametrize("checkpoint_id", ["", ".", "..", "../outside", "/absolute", "sub/name", "sub\\name", "nul\0name"])
def test_invalid_ids_fail_before_state_and_copy(checkpoint_repo, monkeypatch, checkpoint_id):
    r = checkpoint_repo
    forbidden = Mock(side_effect=AssertionError("invalid ID must not proceed"))
    monkeypatch.setattr(checkpoint, "get_state_store", forbidden)
    monkeypatch.setattr(checkpoint.shutil, "copy2", forbidden)
    monkeypatch.setattr(git_execution.subprocess, "run", forbidden)
    assert checkpoint.rollback(checkpoint_id, confirm=lambda: True) is False
    forbidden.assert_not_called()
    checkpoint.success.assert_not_called()
    audit_outcome(r, "failed", "Invalid checkpoint ID")


@pytest.mark.parametrize(
    "unsafe",
    ["missing", "checkpoint-symlink", "backup-file-symlink", "backup-dir-symlink", "fifo", "outside-file", "git-file", "git-dir", "dest-leaf-symlink", "dest-dir-symlink", "dest-leaf-dir", "code-root-symlink", "checkpoint-root-symlink"],
)
def test_unsafe_backups_fail_before_any_copy(checkpoint_repo, tmp_path, monkeypatch, unsafe):
    r = checkpoint_repo
    directory = backup(r)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "example.py").write_text("outside unchanged\n")
    if unsafe == "missing":
        checkpoint_id = "missing"
    else:
        checkpoint_id = "saved"
        if unsafe == "checkpoint-symlink":
            (r.backups / "linked").symlink_to(directory, target_is_directory=True)
            checkpoint_id = "linked"
        elif unsafe == "backup-file-symlink":
            (directory / "core/link.py").symlink_to(outside / "example.py")
        elif unsafe == "backup-dir-symlink":
            (directory / "tools").symlink_to(outside, target_is_directory=True)
        elif unsafe == "fifo":
            os.mkfifo(directory / "core/pipe.py")
        elif unsafe == "outside-file":
            (directory / "other.txt").write_text("outside producer scope")
        elif unsafe == "git-file":
            (directory / ".git").mkdir()
            (directory / ".git/config").write_text("unsafe")
        elif unsafe == "git-dir":
            (directory / "core/.git").mkdir()
        elif unsafe == "dest-leaf-symlink":
            r.trigger.unlink()
            r.trigger.symlink_to(outside / "example.py")
        elif unsafe == "dest-dir-symlink":
            (directory / "tools").mkdir()
            (directory / "tools/example.py").write_text("unsafe destination")
            (r.repo / "tools").symlink_to(outside, target_is_directory=True)
        elif unsafe == "dest-leaf-dir":
            r.trigger.unlink()
            r.trigger.mkdir()
        elif unsafe == "code-root-symlink":
            link = tmp_path / "code-link"
            link.symlink_to(r.repo, target_is_directory=True)
            monkeypatch.setattr(checkpoint, "CODE_DIR", link)
        elif unsafe == "checkpoint-root-symlink":
            link = tmp_path / "backups-link"
            link.symlink_to(r.backups, target_is_directory=True)
            monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", link)
    before = (outside / "example.py").read_bytes()
    forbidden = Mock(side_effect=AssertionError("no copy/Git after unsafe preflight"))
    monkeypatch.setattr(checkpoint.shutil, "copy2", forbidden)
    monkeypatch.setattr(git_execution.subprocess, "run", forbidden)
    assert checkpoint.rollback(checkpoint_id, confirm=lambda: True) is False
    forbidden.assert_not_called()
    assert (outside / "example.py").read_bytes() == before
    assert r.state.get_recent_actions() == []
    checkpoint.success.assert_not_called()
    audit_outcome(r, "failed")


@pytest.mark.parametrize("kind", ["empty", "abbreviated", "option", "missing", "blob", "tree", "tag"])
def test_invalid_or_noncommit_hash_fails_before_copy(checkpoint_repo, monkeypatch, kind):
    r = checkpoint_repo
    head = r.git("rev-parse", "HEAD").stdout.strip()
    if kind == "empty":
        value = ""
    elif kind == "abbreviated":
        value = head[:8]
    elif kind == "option":
        value = "--force"
    elif kind == "missing":
        value = "0" * 40
    elif kind == "blob":
        value = r.git("rev-parse", "HEAD:core/example.py").stdout.strip()
    elif kind == "tree":
        value = r.git("rev-parse", "HEAD^{tree}").stdout.strip()
    else:
        r.git("tag", "-a", "saved-tag", "-m", "annotated", "HEAD")
        value = r.git("rev-parse", "saved-tag").stdout.strip()
    backup(r, git_hash=value)
    copier = Mock(side_effect=AssertionError("invalid hash cannot copy"))
    monkeypatch.setattr(checkpoint.shutil, "copy2", copier)
    assert checkpoint.rollback("saved", confirm=lambda: True) is False
    copier.assert_not_called()
    assert r.trigger.read_text() == "baseline = True\n"
    assert r.git("rev-parse", "HEAD").stdout.strip() == head
    assert r.state.get_recent_actions() == []
    audit_outcome(r, "failed")
def test_partial_copy_failure_stops_before_git_and_log(checkpoint_repo, monkeypatch):
    r = checkpoint_repo
    directory = backup(r, git_hash=r.git("rev-parse", "HEAD").stdout.strip())
    (directory / "core/second.py").write_text("second restored\n")
    real_copy = checkpoint.shutil.copy2
    copies = []

    def copy(source, destination):
        copies.append(destination)
        if len(copies) == 2:
            raise OSError("second copy failed")
        return real_copy(source, destination)

    monkeypatch.setattr(checkpoint.shutil, "copy2", copy)
    original_run = subprocess.run
    with monkeypatch.context() as calls:
        runner = Mock(wraps=original_run)
        calls.setattr(git_execution.subprocess, "run", runner)
        assert checkpoint.rollback("saved", confirm=lambda: True) is False
        assert [call.args[0][:3] for call in runner.call_args_list] == [[git_execution._trusted_git_executable(), "cat-file", "-t"]]
    assert len(copies) == 2
    assert r.trigger.read_text() == "restored = True\n"
    assert not (r.repo / "core/second.py").exists()
    assert r.state.get_recent_actions() == []
    checkpoint.success.assert_not_called()
    audit_outcome(r, "failed", "second copy failed")


def test_mkdir_failure_stops_without_copy(checkpoint_repo, monkeypatch):
    from pathlib import Path

    r = checkpoint_repo
    backup(r)
    original = Path.mkdir

    def mkdir(path, *args, **kwargs):
        if path == r.repo / "core":
            raise OSError("destination mkdir failed")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    copier = Mock(side_effect=AssertionError("no copy after mkdir failure"))
    monkeypatch.setattr(checkpoint.shutil, "copy2", copier)
    assert checkpoint.rollback("saved", confirm=lambda: True) is False
    copier.assert_not_called()
    assert r.state.get_recent_actions() == []
    audit_outcome(r, "failed", "destination mkdir failed")


def test_dirty_checkout_failure_keeps_partial_file_restore(checkpoint_repo):
    r = checkpoint_repo
    saved = r.git("rev-parse", "HEAD").stdout.strip()
    backup(r, git_hash=saved)
    (r.repo / "other.txt").write_text("later committed\n")
    r.git("add", "--", "other.txt")
    r.git("commit", "-m", "later")
    later = r.git("rev-parse", "HEAD").stdout.strip()
    (r.repo / "other.txt").write_text("dirty local content\n")
    assert checkpoint.rollback("saved", confirm=lambda: True) is False
    assert r.trigger.read_text() == "restored = True\n"
    assert r.git("rev-parse", "HEAD").stdout.strip() == later
    assert (r.repo / "other.txt").read_text() == "dirty local content\n"
    assert r.state.get_recent_actions() == []
    checkpoint.success.assert_not_called()
    assert "Rollback git checkout failed:" in audit_outcome(r, "failed")["reason"]


@pytest.mark.parametrize("stage", ["accessor", "lookup", "verification", "checkout", "log"])
def test_operation_exceptions_are_failed_without_success(checkpoint_repo, monkeypatch, stage):
    r = checkpoint_repo
    saved = r.git("rev-parse", "HEAD").stdout.strip()
    backup(r, git_hash=saved)
    failure = OSError(f"{stage} failed")
    if stage == "accessor":
        monkeypatch.setattr(checkpoint, "get_state_store", Mock(side_effect=failure))
    elif stage == "lookup":
        monkeypatch.setattr(r.state, "get_checkpoint", Mock(side_effect=failure))
    elif stage == "log":
        monkeypatch.setattr(r.state, "log_action", Mock(side_effect=failure))
    else:
        original_run = subprocess.run

        def run(args, **kwargs):
            if args[1] == ("cat-file" if stage == "verification" else "checkout"):
                raise failure
            return original_run(args, **kwargs)

        monkeypatch.setattr(git_execution.subprocess, "run", run)
    assert checkpoint.rollback("saved", confirm=lambda: True) is False
    assert r.state.get_recent_actions() == []
    checkpoint.success.assert_not_called()
    audit_outcome(r, "failed", str(failure))
    if stage in ("accessor", "lookup", "verification"):
        assert r.trigger.read_text() == "baseline = True\n"
    else:
        assert r.trigger.read_text() == "restored = True\n"


def test_nonzero_checkout_never_logs_success(checkpoint_repo, monkeypatch):
    r = checkpoint_repo
    saved = r.git("rev-parse", "HEAD").stdout.strip()
    backup(r, git_hash=saved)
    original_run = subprocess.run

    def run(args, **kwargs):
        if args[1] == "checkout":
            return SimpleNamespace(returncode=1, stdout="", stderr="original checkout error\n")
        return original_run(args, **kwargs)

    monkeypatch.setattr(git_execution.subprocess, "run", run)
    assert checkpoint.rollback("saved", confirm=lambda: True) is False
    assert r.trigger.read_text() == "restored = True\n"
    assert r.state.get_recent_actions() == []
    checkpoint.success.assert_not_called()
    audit_outcome(r, "failed", "Rollback git checkout failed: original checkout error")


@pytest.mark.parametrize("approved", [True, False])
def test_blocked_audit_sink_does_not_change_result(checkpoint_repo, tmp_path, monkeypatch, approved):
    r = checkpoint_repo
    backup(r)
    blocker = tmp_path / "blocker"
    blocker.write_text("blocker")
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: ActionGateway(audit_file=blocker / "audit.jsonl"))
    assert checkpoint.rollback("saved", confirm=lambda: approved) is approved
    assert r.trigger.read_text() == ("restored = True\n" if approved else "baseline = True\n")
    assert len(r.state.get_recent_actions()) == int(approved)
    assert blocker.read_text() == "blocker"
def test_newer_committed_backup_file_can_block_checked_checkout(checkpoint_repo):
    r = checkpoint_repo
    saved = r.git("rev-parse", "HEAD").stdout.strip()
    directory = backup(r, git_hash=saved)
    (directory / "core/example.py").write_text("baseline = True\n")
    r.trigger.write_text("new committed content\n")
    r.git("add", "--", "core/example.py")
    r.git("commit", "-m", "new backup-file version")
    later = r.git("rev-parse", "HEAD").stdout.strip()
    assert checkpoint.rollback("saved", confirm=lambda: True) is False
    assert r.trigger.read_text() == "baseline = True\n"
    assert r.git("rev-parse", "HEAD").stdout.strip() == later
    assert r.git("symbolic-ref", "HEAD").stdout.strip() == "refs/heads/main"
    assert r.state.get_recent_actions() == []
    checkpoint.success.assert_not_called()
    assert "would be overwritten by checkout" in audit_outcome(r, "failed")["reason"]


def test_backup_enumeration_error_precedes_any_copy(checkpoint_repo, monkeypatch):
    from pathlib import Path

    r = checkpoint_repo
    directory = backup(r)
    original = Path.iterdir

    def iterdir(path):
        if path == directory / "core":
            raise PermissionError("backup enumeration failed")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    forbidden = Mock(side_effect=AssertionError("no work after enumeration failure"))
    monkeypatch.setattr(checkpoint.shutil, "copy2", forbidden)
    monkeypatch.setattr(checkpoint, "get_state_store", forbidden)
    assert checkpoint.rollback("saved", confirm=lambda: True) is False
    forbidden.assert_not_called()
    audit_outcome(r, "failed", "backup enumeration failed")
