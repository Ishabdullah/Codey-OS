"""WP2.1 group 11 / NEW-863: create_checkpoint() ID collision resistance.

Before this fix, `checkpoint_id = str(int(time.time()))` plus
`backup_dir.mkdir(parents=True, exist_ok=True)` meant two checkpoints
created in the same wall-clock second got the *same* directory, and
the second create silently overwrote the first's backup files before
the second INSERT's primary-key uniqueness check even fired.
"""

import os
import subprocess
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, checkpoint, git_execution
from core.action_gateway import ActionGateway
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
        return subprocess.run(
            [git_execution._trusted_git_executable(), *args], cwd=repo,
            capture_output=True, text=True, check=check,
        )

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


def test_same_second_creates_produce_distinct_checkpoints_both_intact(checkpoint_repo, monkeypatch):
    """Two create_checkpoint() calls that would have collided under the
    old str(int(time.time())) scheme (same mocked wall-clock second)
    now get genuinely distinct IDs, and neither's backup overwrites
    the other's."""
    r = checkpoint_repo
    monkeypatch.setattr(checkpoint.time, "time", lambda: 1_700_000_000.0)

    r.trigger.write_text("first version\n")
    first_id = checkpoint.create_checkpoint("first reason", [])

    r.trigger.write_text("second version\n")
    second_id = checkpoint.create_checkpoint("second reason", [])

    assert first_id != second_id
    assert (r.backups / first_id / "core/example.py").read_text() == "first version\n"
    assert (r.backups / second_id / "core/example.py").read_text() == "second version\n"
    assert r.state.get_checkpoint(first_id)["reason"] == "first reason"
    assert r.state.get_checkpoint(second_id)["reason"] == "second reason"


def test_genuine_id_collision_raises_instead_of_silently_overwriting(checkpoint_repo, monkeypatch):
    """If the (vanishingly unlikely) timestamp+uuid collision ever did
    happen, exist_ok=False must make it a loud failure, not a silent
    directory reuse that overwrites the first checkpoint's backups."""
    r = checkpoint_repo
    monkeypatch.setattr(checkpoint.time, "time", lambda: 1_700_000_000.0)
    monkeypatch.setattr(checkpoint.uuid, "uuid4", lambda: uuid.UUID(int=0))

    first_id = checkpoint.create_checkpoint("first reason", [])
    assert (r.backups / first_id).is_dir()

    with pytest.raises(FileExistsError):
        checkpoint.create_checkpoint("second reason", [])
    # The first checkpoint's backup directory is untouched by the failed
    # second attempt.
    assert (r.backups / first_id / "core/example.py").read_text() == "baseline = True\n"


def test_normal_single_checkpoint_creation_unchanged(checkpoint_repo):
    """Regression: a single, ordinary create_checkpoint() call still
    returns the same shape and produces the same DB row shape as
    before this change."""
    r = checkpoint_repo
    checkpoint_id = checkpoint.create_checkpoint("ordinary reason", ["core/example.py"])
    assert isinstance(checkpoint_id, str)
    row = r.state.get_checkpoint(checkpoint_id)
    assert row["id"] == checkpoint_id
    assert row["reason"] == "ordinary reason"
    assert (r.backups / checkpoint_id / "core/example.py").is_file()
    assert checkpoint.list_checkpoints()[0]["id"] == checkpoint_id
    assert checkpoint.get_latest_checkpoint() == checkpoint_id


def test_rollback_and_list_checkpoints_work_with_new_id_format(checkpoint_repo):
    """_rollback_files()'s ID-shape validation and list_checkpoints()'s
    display assumptions both still work with the new
    "<timestamp>-<hex8>" ID shape."""
    r = checkpoint_repo
    saved_hash = r.git("rev-parse", "HEAD").stdout.strip()
    checkpoint_id = checkpoint.create_checkpoint("private reason", [])
    assert r.state.get_checkpoint(checkpoint_id)["git_commit_hash"] == saved_hash
    assert "-" in checkpoint_id  # new shape: "<int-timestamp>-<8 hex chars>"

    listing = checkpoint.list_checkpoints()
    assert listing[0]["id"] == checkpoint_id
    assert listing[0]["git_commit"] == saved_hash[:8]

    # other.txt is not part of the backup set, so committing a change to
    # it (rather than to the backed-up core/example.py) keeps this a
    # clean, non-dirty checkout -- mirrors
    # test_create_checkpoint_and_full_repository_detached_restore in
    # tests/test_checkpoint_rollback_gateway.py.
    (r.repo / "other.txt").write_text("later committed\n")
    r.git("add", "--", "other.txt")
    r.git("commit", "-m", "later")
    assert checkpoint.rollback(checkpoint_id, confirm=lambda: True) is True
    assert r.trigger.read_text() == "baseline = True\n"
