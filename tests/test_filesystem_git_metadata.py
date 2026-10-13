"""NEW-894: deny write/patch/append mutation under a repository's own
`.git` directory (core.filesystem.Filesystem._reject_git_metadata_mutation).

Every Filesystem instance here is constructed directly against a
disposable tempfile.TemporaryDirectory() workspace -- NEVER the real
repo's get_filesystem() singleton with its default WORKSPACE_ROOT/
CODE_DIR. A fixture bug that accidentally targeted the real on-device
.git/config would be a live incident, not a test bug.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

import core.filesystem as filesystem_module
from core.filesystem import Filesystem, FilesystemAccessError


@pytest.fixture
def workspace():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def fs(workspace):
    return Filesystem(workspace=workspace)


# ---------------------------------------------------------------------------
# 1 + 2: denial with specific message, paired with an ordinary-file control
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("relative", [".git/config", ".git/hooks/pre-push"])
def test_write_denied_under_git_metadata(fs, workspace, relative):
    target = workspace / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(FilesystemAccessError, match="is inside a Git metadata directory"):
        fs.write(str(target), "content")


@pytest.mark.parametrize("relative", [".git/config", ".git/hooks/pre-push"])
def test_patch_denied_under_git_metadata(fs, workspace, relative):
    target = workspace / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("old content")
    with pytest.raises(FilesystemAccessError, match="is inside a Git metadata directory"):
        fs.patch(str(target), "old", "new")


@pytest.mark.parametrize("relative", [".git/config", ".git/hooks/pre-push"])
def test_append_denied_under_git_metadata(fs, workspace, relative):
    target = workspace / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(FilesystemAccessError, match="is inside a Git metadata directory"):
        fs.append(str(target), "content")


@pytest.mark.parametrize("op", ["write", "patch", "append"])
def test_ordinary_file_control_unaffected(fs, workspace, op):
    """Identical operations against a non-.git path succeed -- proves the
    denial is targeted, not an accidental broader breakage."""
    target = workspace / "notgit" / "config"
    target.parent.mkdir(parents=True, exist_ok=True)
    if op == "write":
        result = fs.write(str(target), "content")
        assert "Written" in result
    elif op == "patch":
        target.write_text("old content")
        fs.patch(str(target), "old", "new")
        assert target.read_text() == "new content"
    else:
        fs.append(str(target), "content")
        assert target.read_text() == "content"
    assert target.exists()


# ---------------------------------------------------------------------------
# 3: no partial effects on a denied attempt
# ---------------------------------------------------------------------------

def test_denied_write_never_creates_parent_directory(fs, workspace):
    (workspace / ".git").mkdir()
    target = workspace / ".git" / "newdir" / "x"
    with pytest.raises(FilesystemAccessError):
        fs.write(str(target), "content")
    assert not (workspace / ".git" / "newdir").exists()


@pytest.mark.parametrize("op", ["patch", "append"])
def test_denied_mutation_leaves_existing_file_byte_for_byte_unchanged(fs, workspace, op):
    git_dir = workspace / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    original_bytes = b"[core]\n\trepositoryformatversion = 0\n"
    config.write_bytes(original_bytes)
    with pytest.raises(FilesystemAccessError):
        if op == "patch":
            fs.patch(str(config), "core", "CORE")
        else:
            fs.append(str(config), "\n[extra]\n")
    assert config.read_bytes() == original_bytes


def test_denied_write_to_dotgit_as_a_file_itself(fs, workspace):
    """A worktree/submodule-style `.git` is sometimes a FILE (a "gitfile"
    containing `gitdir: <real location>`), not a directory. Writing it
    directly (not a path under it) must still be denied -- rel.parts[0]
    == ".git" catches this even when workspace/".git" has zero remaining
    path components."""
    target = workspace / ".git"
    with pytest.raises(FilesystemAccessError, match="is inside a Git metadata directory"):
        fs.write(str(target), "gitdir: /elsewhere/.git/worktrees/x\n")
    assert not target.exists()


# ---------------------------------------------------------------------------
# 3b: checkpoint/snapshot mechanics never run on a denied attempt
# ---------------------------------------------------------------------------

def test_denied_mutation_never_triggers_checkpoint_or_snapshot(fs, workspace, monkeypatch):
    """Ordering matters (per the implementation spec): the git-metadata
    check must run BEFORE _is_core_file()/_require_checkpoint() and
    _snapshot(). With the wrong ordering, a denied .git/config write
    would still call the real create_checkpoint(), which does a real
    `git add`/`git diff --cached` against the actual repository -- the
    riskiest regression to leave unpinned. Forcing _is_core_file() True
    here makes the checkpoint branch reachable if (and only if) the
    ordering is wrong, so this test genuinely exercises the hazard."""
    git_dir = workspace / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text("[core]\n")

    checkpoint_mock = Mock(side_effect=AssertionError("checkpoint must not run"))
    snapshot_mock = Mock(side_effect=AssertionError("snapshot must not run"))
    monkeypatch.setattr(filesystem_module, "_is_core_file", lambda _path: True)
    monkeypatch.setattr(filesystem_module, "create_checkpoint", checkpoint_mock)
    monkeypatch.setattr(filesystem_module, "_snapshot", snapshot_mock)

    with pytest.raises(FilesystemAccessError, match="is inside a Git metadata directory"):
        fs.write(str(config), "replaced")
    with pytest.raises(FilesystemAccessError, match="is inside a Git metadata directory"):
        fs.patch(str(config), "core", "CORE")
    with pytest.raises(FilesystemAccessError, match="is inside a Git metadata directory"):
        fs.append(str(config), "\nmore\n")

    checkpoint_mock.assert_not_called()
    snapshot_mock.assert_not_called()
    assert config.read_text() == "[core]\n"


# ---------------------------------------------------------------------------
# 4: introspection preserved
# ---------------------------------------------------------------------------

def test_introspection_still_succeeds_on_git_metadata(fs, workspace):
    git_dir = workspace / ".git"
    git_dir.mkdir()
    config = git_dir / "config"
    config.write_text("[core]\n")

    assert fs.exists(str(git_dir)) is True
    assert fs.exists(str(config)) is True
    assert fs.is_dir(str(git_dir)) is True
    assert fs.is_file(str(config)) is True
    assert fs.read(str(config)) == "[core]\n"
    assert "config" in fs.list_dir(str(git_dir))


# ---------------------------------------------------------------------------
# 5: nested repository's own .git is out of scope (root-only match)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("op", ["write", "patch", "append"])
def test_nested_repository_git_is_not_blocked(fs, workspace, op):
    nested_config = workspace / "vendor" / "sub" / ".git" / "config"
    nested_config.parent.mkdir(parents=True, exist_ok=True)
    nested_config.write_text("[core]\nold\n")

    if op == "write":
        result = fs.write(str(nested_config), "replaced")
        assert "Written" in result
        assert nested_config.read_text() == "replaced"
    elif op == "patch":
        fs.patch(str(nested_config), "old", "new")
        assert nested_config.read_text() == "[core]\nnew\n"
    else:
        fs.append(str(nested_config), "\nappended\n")
        assert nested_config.read_text() == "[core]\nold\n\nappended\n"


# ---------------------------------------------------------------------------
# 6: CODE_DIR + self-modification branch, monkeypatched off the real repo
# ---------------------------------------------------------------------------

def test_code_dir_git_metadata_also_denied(monkeypatch, workspace):
    with tempfile.TemporaryDirectory() as code_dir_raw:
        code_dir = Path(code_dir_raw)
        monkeypatch.setattr(filesystem_module, "CODE_DIR", code_dir)
        fs_self_mod = Filesystem(workspace=workspace, allow_self_modification=True)
        git_dir = code_dir / ".git"
        git_dir.mkdir()
        config = git_dir / "config"
        config.write_text("[core]\n")
        with pytest.raises(FilesystemAccessError, match="is inside a Git metadata directory"):
            fs_self_mod.write(str(config), "replaced")
        assert config.read_text() == "[core]\n"


# ---------------------------------------------------------------------------
# 7: audit/return shape through the gate_write()/gate_append() tool layer
# ---------------------------------------------------------------------------

@pytest.fixture
def gated(workspace, monkeypatch, tmp_path):
    from core import action_gateway
    from tools import file_tools

    audit = tmp_path / "audit.jsonl"
    instance = action_gateway.ActionGateway(audit_file=audit)
    fs_instance = Filesystem(workspace=workspace)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(file_tools, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(file_tools, "_get_fs", lambda: fs_instance)
    from types import SimpleNamespace
    return SimpleNamespace(audit=audit, fs=fs_instance, workspace=workspace, file_tools=file_tools)


def test_gate_write_outcome_failed_on_git_metadata(gated, monkeypatch):
    monkeypatch.setattr("utils.logger.confirm", lambda *_a, **_k: True)
    target = gated.workspace / ".git" / "config"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[core]\n")
    result = gated.file_tools.tool_write_file(str(target), "replaced")
    assert result.startswith("[ERROR] Access denied:")
    assert "is inside a Git metadata directory" in result
    rows = [json.loads(line) for line in gated.audit.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["outcome"] == "failed"
    assert target.read_text() == "[core]\n"


def test_gate_append_outcome_failed_on_git_metadata(gated):
    target = gated.workspace / ".git" / "config"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[core]\n")
    result = gated.file_tools.tool_append_file(str(target), "\nmore\n")
    assert result.startswith("[ERROR] Access denied:")
    assert "is inside a Git metadata directory" in result
    rows = [json.loads(line) for line in gated.audit.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["outcome"] == "failed"
    assert target.read_text() == "[core]\n"


def test_tool_patch_file_errors_with_no_audit_record(gated):
    """tool_patch_file() calls Filesystem.patch() directly (no gateway
    mediation) -- this is pre-existing behavior for every
    FilesystemAccessError, not a regression from this fix."""
    target = gated.workspace / ".git" / "config"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("[core]\n")
    result = gated.file_tools.tool_patch_file(str(target), "core", "CORE")
    assert result.startswith("[ERROR]")
    assert "is inside a Git metadata directory" in result
    assert not gated.audit.exists() or gated.audit.read_text() == ""
    assert target.read_text() == "[core]\n"
