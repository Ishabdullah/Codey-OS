"""WP2.4: patch_file leaves exactly one /undo history entry per applied patch.

Regression for the double snapshot (patch_tools used to snapshot, then
Filesystem.write snapshotted again; with filehistory.MAX_VERSIONS == 2 the
original was evicted after two patches). Uses the REAL core.filehistory and
a tmp workspace + fake code dir, so no real git checkpoint is taken and the
real repo is never written. No model, network or process control.
"""

import os
from types import SimpleNamespace

import pytest

import core.checkpoint as checkpoint_module
import core.filesystem as filesystem_module
from core import filehistory
from core.action_gateway import reset_action_gateway
from core.filesystem import Filesystem
from tools import file_tools, patch_tools
from utils.config import AGENT_CONFIG


@pytest.fixture
def env(tmp_path, monkeypatch):
    import utils.config as cfg

    ws = tmp_path / "ws"
    code = tmp_path / "code"
    state = tmp_path / "state"
    audit = tmp_path / "audit" / "ledger.jsonl"
    for d in (ws, code / "core", state, audit.parent):
        d.mkdir(parents=True)
    monkeypatch.setenv("CODEY_STATE_DIR", str(state))
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(audit))
    monkeypatch.setattr(cfg, "CODEY_STATE_DIR", state)
    monkeypatch.setattr(cfg, "CODEY_DIR", code)
    monkeypatch.setattr(filesystem_module, "CODE_DIR", code)
    monkeypatch.setattr(checkpoint_module, "CODE_DIR", code)
    checkpoints = []
    monkeypatch.setattr(
        filesystem_module, "create_checkpoint", lambda **kw: checkpoints.append(kw)
    )
    monkeypatch.chdir(ws)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_write", False)
    monkeypatch.setitem(AGENT_CONFIG, "allow_self_modification", False)
    reset_action_gateway()
    filehistory.clear_history()
    fs = Filesystem(workspace=ws, allow_self_modification=True)
    monkeypatch.setattr(filesystem_module, "get_filesystem", lambda *a, **k: fs)
    monkeypatch.setattr(file_tools, "_fs", fs)
    monkeypatch.setattr(file_tools, "_fs_allow_self_mod", True)
    yield SimpleNamespace(ws=ws, code=code, fs=fs, checkpoints=checkpoints)
    filehistory.clear_history()
    reset_action_gateway()


def _contents(path):
    return [c for _, c in filehistory.get_versions(str(path))]


def test_two_patches_keep_original_in_history_and_first_undo_restores_previous(env):
    f = env.ws / "a.txt"
    f.write_text("A\n")
    assert patch_tools.tool_patch_file(str(f), "A", "B").startswith("Patched")
    assert patch_tools.tool_patch_file(str(f), "B", "C").startswith("Patched")
    assert f.read_text() == "C\n"
    # Pre-fix this was ['B\n', 'B\n']: the original A had been evicted.
    assert _contents(f) == ["A\n", "B\n"]
    assert filehistory.undo(str(f), filesystem=env.fs).startswith("Restored")
    assert f.read_text() == "B\n"
    # A is still retained (index 0); only the walk-back is limited, see xfail below.
    assert _contents(f)[0] == "A\n"


@pytest.mark.xfail(
    strict=True,
    reason="WP2.4 DoD contract (A->B->C, two undos -> A) is not met: "
    "filehistory.undo deliberately pushes a '(pre-undo)' entry (WP2.1 14b "
    "redo/diff design, pinned by test_undo_action_boundaries), so a second "
    "consecutive undo restores C. Needs an Ish/design decision (redo stack); "
    "not pinned as expected behaviour.",
)
def test_two_consecutive_undos_walk_back_to_original(env):
    f = env.ws / "a.txt"
    f.write_text("A\n")
    patch_tools.tool_patch_file(str(f), "A", "B")
    patch_tools.tool_patch_file(str(f), "B", "C")
    filehistory.undo(str(f), filesystem=env.fs)
    filehistory.undo(str(f), filesystem=env.fs)
    assert f.read_text() == "A\n"


def test_one_patch_adds_exactly_one_history_entry(env):
    f = env.ws / "a.txt"
    f.write_text("A\n")
    patch_tools.tool_patch_file(str(f), "A", "B")
    assert _contents(f) == ["A\n"]


def test_refused_patch_adds_no_entry_and_undo_still_reaches_original(env, monkeypatch):
    f = env.ws / "a.txt"
    f.write_text("A\n")
    patch_tools.tool_patch_file(str(f), "A", "B")
    core = env.code / "core" / "x.py"
    core.write_text("X = 1\n")
    # Core file, no confirmation path: HIGH_IMPACT fails closed ([BLOCKED]).
    monkeypatch.setitem(AGENT_CONFIG, "allow_self_modification", False)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_write", False)
    for _ in range(3):
        res = patch_tools.tool_patch_file(str(core), "X = 1", "X = 2")
        assert res.startswith("[BLOCKED]") or res.startswith("[ERROR]"), res
    assert core.read_text() == "X = 1\n"
    assert _contents(core) == []
    assert _contents(f) == ["A\n"]
    assert filehistory.undo(str(f), filesystem=env.fs).startswith("Restored")
    assert f.read_text() == "A\n"


def test_failed_syntax_error_and_cancelled_patches_add_no_entry(env, monkeypatch):
    t = env.ws / "t.txt"
    t.write_text("A\n")
    assert patch_tools.tool_patch_file(str(t), "ZZZ", "Q").startswith("[PATCH_FAILED]")
    assert _contents(t) == []

    py = env.ws / "m.py"
    py.write_text("x = 1\n")
    res = patch_tools.tool_patch_file(str(py), "x = 1", "x = (")
    assert "syntax error" in res
    assert py.read_text() == "x = 1\n"
    assert _contents(py) == []

    monkeypatch.setitem(AGENT_CONFIG, "confirm_write", True)
    monkeypatch.setattr(patch_tools, "ask_confirm", lambda *a, **k: False)
    assert patch_tools.tool_patch_file(str(t), "A", "B").startswith("[CANCELLED]")
    assert t.read_text() == "A\n"
    assert _contents(t) == []


def test_core_file_patch_then_undo_restores_with_fake_code_dir(env, monkeypatch):
    core = env.code / "core" / "x.py"
    core.write_text("X = 1\n")
    monkeypatch.setitem(AGENT_CONFIG, "allow_self_modification", True)
    res = patch_tools.tool_patch_file(str(core), "X = 1", "X = 2")
    assert res.startswith("Patched"), res
    assert core.read_text() == "X = 2\n"
    assert _contents(core) == ["X = 1\n"]
    assert env.checkpoints, "core write should have requested a (stubbed) checkpoint"
    msg = filehistory.undo(str(core), confirm=lambda: True, filesystem=env.fs)
    assert msg.startswith("Restored"), msg
    assert core.read_text() == "X = 1\n"


def test_mutation_guard_filesystem_write_is_the_snapshot_source(env, monkeypatch):
    """If Filesystem.write stops snapshotting, undo has nothing to restore."""
    monkeypatch.setattr(filesystem_module, "_snapshot", lambda p: False)
    f = env.ws / "a.txt"
    f.write_text("A\n")
    patch_tools.tool_patch_file(str(f), "A", "B")
    assert _contents(f) == []
    assert filehistory.undo(str(f), filesystem=env.fs).startswith("[ERROR] No history")
