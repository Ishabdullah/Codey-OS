"""WP2.1 group 11a: prune_checkpoints() hardening (NEW-941).

Covers: checkpoint_id path-traversal/symlink containment (mirroring
_rollback_files's own guard, now shared via _resolve_checkpoint_dir),
keep_count validation, the get_checkpoints(100) "get all" bug fix,
DB-row-deleted-before-rmtree ordering, and HIGH_IMPACT gateway
mediation (fail-closed with no confirmation path, same as rollback()).
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, checkpoint
from core.action_gateway import HIGH_IMPACT, ActionGateway
from core.state import StateStore


@pytest.fixture
def prune_env(tmp_path, monkeypatch):
    backups = tmp_path / "checkpoints"
    backups.mkdir()
    audit = tmp_path / "audit.jsonl"
    gateway = ActionGateway(audit_file=audit)
    state = StateStore(db_path=tmp_path / "state.db")
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", backups)
    monkeypatch.setattr(checkpoint, "get_state_store", lambda: state)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: gateway)
    monkeypatch.setattr(checkpoint, "success", Mock())
    monkeypatch.setattr(checkpoint, "info", Mock())
    warnings = Mock()
    monkeypatch.setattr(checkpoint, "warning", warnings)
    yield SimpleNamespace(
        backups=backups, audit=audit, gateway=gateway, state=state, warnings=warnings,
    )
    state.close()


def add_row(r, checkpoint_id, created_at, make_dir=True, content=None):
    if make_dir:
        directory = r.backups / checkpoint_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "marker.txt").write_text(content or checkpoint_id)
    r.state.execute(
        "INSERT INTO checkpoints (id, created_at, reason, files_modified, git_commit_hash) "
        "VALUES (?, ?, ?, ?, ?)",
        (checkpoint_id, created_at, "test", "[]", None),
    )


def audit_rows(r):
    if not r.audit.exists():
        return []
    return [json.loads(line) for line in r.audit.read_text().splitlines()]


def remaining_ids(r):
    return {cp["id"] for cp in r.state.get_checkpoints(None)}


# ---------------------------------------------------------------------------
# keep_count validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("keep_count", [0, -1, -5])
def test_keep_count_non_positive_refused(prune_env, keep_count):
    r = prune_env
    add_row(r, "cp1", 1)
    add_row(r, "cp2", 2)
    with pytest.raises(ValueError):
        checkpoint.prune_checkpoints(keep_count, confirm=lambda: True)
    # Raised before any gateway mediation: no audit row, nothing touched.
    assert audit_rows(r) == []
    assert remaining_ids(r) == {"cp1", "cp2"}


@pytest.mark.parametrize("keep_count", [True, False, 1.5, "5", None])
def test_keep_count_non_int_refused(prune_env, keep_count):
    r = prune_env
    with pytest.raises(ValueError):
        checkpoint.prune_checkpoints(keep_count, confirm=lambda: True)
    assert audit_rows(r) == []


# ---------------------------------------------------------------------------
# HIGH_IMPACT gateway mediation
# ---------------------------------------------------------------------------

def test_refusal_without_confirm_path_does_no_work(prune_env):
    r = prune_env
    add_row(r, "cp1", 1)
    add_row(r, "cp2", 2)
    add_row(r, "cp3", 3)
    assert checkpoint.prune_checkpoints(1) == 0  # confirm=None (default)
    assert remaining_ids(r) == {"cp1", "cp2", "cp3"}
    assert (r.backups / "cp1").exists()
    rows = audit_rows(r)
    assert len(rows) == 1
    assert rows[0]["authority"] == HIGH_IMPACT
    assert rows[0]["action"] == "checkpoint.prune"
    assert rows[0]["outcome"] == "refused"


def test_declined_confirmation_does_no_work(prune_env):
    r = prune_env
    add_row(r, "cp1", 1)
    add_row(r, "cp2", 2)
    assert checkpoint.prune_checkpoints(1, confirm=lambda: False) == 0
    assert remaining_ids(r) == {"cp1", "cp2"}
    assert audit_rows(r)[-1]["outcome"] == "refused"


# ---------------------------------------------------------------------------
# Normal, legitimate prune
# ---------------------------------------------------------------------------

def test_normal_prune_keeps_newest_removes_rest(prune_env):
    r = prune_env
    for i in range(8):
        add_row(r, f"cp{i}", i)
    removed = checkpoint.prune_checkpoints(5, confirm=lambda: True)
    assert removed == 3
    # Newest 5 by created_at are cp3..cp7.
    assert remaining_ids(r) == {"cp3", "cp4", "cp5", "cp6", "cp7"}
    for i in range(3):
        assert not (r.backups / f"cp{i}").exists()
    for i in range(3, 8):
        assert (r.backups / f"cp{i}").exists()
    r.success_mock = checkpoint.success
    checkpoint.success.assert_called_once()
    rows = audit_rows(r)
    assert rows[-1]["outcome"] == "allowed"


def test_nothing_to_prune_when_at_or_under_keep_count(prune_env):
    r = prune_env
    add_row(r, "cp1", 1)
    add_row(r, "cp2", 2)
    assert checkpoint.prune_checkpoints(5, confirm=lambda: True) == 0
    assert remaining_ids(r) == {"cp1", "cp2"}


# ---------------------------------------------------------------------------
# get_checkpoints(100) -> genuinely-all-rows fix
# ---------------------------------------------------------------------------

def test_prune_handles_more_than_100_checkpoints(prune_env):
    r = prune_env
    for i in range(150):
        add_row(r, f"cp{i:04d}", i, make_dir=False)
    removed = checkpoint.prune_checkpoints(5, confirm=lambda: True)
    assert removed == 145
    assert remaining_ids(r) == {f"cp{i:04d}" for i in range(145, 150)}


# ---------------------------------------------------------------------------
# Path traversal / symlink containment
# ---------------------------------------------------------------------------

def test_traversal_checkpoint_id_refused_and_nothing_pruned(prune_env, tmp_path):
    r = prune_env
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "secret.txt").write_text("do not touch")
    # cp1..cp5 are newest-to-oldest at created_at 5..1; "../victim" is
    # the very oldest (created_at=0), so with keep_count=2 it falls into
    # the prunable tail alongside cp3/cp2/cp1 -- exactly where a real
    # attacker-controlled row would need to land to matter.
    for i in range(1, 6):
        add_row(r, f"cp{i}", i)
    add_row(r, "../victim", 0, make_dir=False)
    before = (victim / "secret.txt").read_bytes()
    assert checkpoint.prune_checkpoints(2, confirm=lambda: True) == 0
    assert (victim / "secret.txt").read_bytes() == before
    # Abort-all: none of the otherwise-legitimate candidates in the same
    # prunable tail (cp1/cp2/cp3) were removed either, since the whole
    # candidate set is validated before any writes.
    assert remaining_ids(r) == {f"cp{i}" for i in range(1, 6)} | {"../victim"}
    for i in range(1, 6):
        assert (r.backups / f"cp{i}").exists()
    assert audit_rows(r)[-1]["outcome"] == "failed"


@pytest.mark.parametrize("checkpoint_id", ["/abs/path", "sub/name", "sub\\name", "nul\0name", ".", ".."])
def test_unsafe_id_shapes_refused(prune_env, checkpoint_id):
    r = prune_env
    add_row(r, "cp0", 1)  # newest -- kept, not a prune candidate
    r.state.execute(
        "INSERT INTO checkpoints (id, created_at, reason, files_modified, git_commit_hash) "
        "VALUES (?, ?, ?, ?, ?)",
        (checkpoint_id, 0, "test", "[]", None),  # oldest -- falls into to_remove
    )
    assert checkpoint.prune_checkpoints(1, confirm=lambda: True) == 0
    assert "cp0" in remaining_ids(r)
    assert (r.backups / "cp0").exists()
    assert audit_rows(r)[-1]["outcome"] == "failed"
    assert audit_rows(r)[-1]["reason"] == "Invalid checkpoint ID"


def test_symlinked_checkpoint_dir_refused_and_target_survives(prune_env, tmp_path):
    r = prune_env
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "payload.txt").write_text("outside data")
    add_row(r, "cp0", 1)  # newest -- kept, not a prune candidate
    (r.backups / "linked").symlink_to(outside, target_is_directory=True)
    r.state.execute(
        "INSERT INTO checkpoints (id, created_at, reason, files_modified, git_commit_hash) "
        "VALUES (?, ?, ?, ?, ?)",
        ("linked", 0, "test", "[]", None),  # oldest -- falls into to_remove
    )
    before = (outside / "payload.txt").read_bytes()
    assert checkpoint.prune_checkpoints(1, confirm=lambda: True) == 0
    assert (outside / "payload.txt").read_bytes() == before
    assert outside.exists()
    assert remaining_ids(r) == {"cp0", "linked"}
    assert audit_rows(r)[-1]["outcome"] == "failed"


def test_checkpoint_root_itself_symlinked_refused(prune_env, tmp_path, monkeypatch):
    r = prune_env
    real_backups = r.backups
    outside = tmp_path / "outside-root"
    outside.mkdir()
    link = tmp_path / "backups-link"
    link.symlink_to(real_backups, target_is_directory=True)
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", link)
    add_row(r, "cp0", 0)
    add_row(r, "cp1", 1)
    assert checkpoint.prune_checkpoints(1, confirm=lambda: True) == 0
    assert remaining_ids(r) == {"cp0", "cp1"}
    assert audit_rows(r)[-1]["outcome"] == "failed"


def test_in_tree_symlinked_checkpoint_dir_refused_by_is_symlink_not_containment(prune_env):
    """Code-reviewer Suggestion 2 (round 1): an IN-TREE symlink (target
    still resolves inside CHECKPOINT_DIR) is caught by
    `backup_dir.is_symlink()` specifically, not by the `relative_to()`
    containment check -- containment alone would pass here, since the
    symlink's resolved target never leaves CHECKPOINT_DIR. Without the
    is_symlink guard, prune would delete the row, then
    `shutil.rmtree(lnk)` would raise ("Cannot call rmtree on a symbolic
    link") -- the guard is independently load-bearing, not redundant
    with containment, and this case (unlike the out-of-tree symlink
    test above) proves it."""
    r = prune_env
    add_row(r, "cp0", 1)  # newest -- kept, real directory
    (r.backups / "lnk").symlink_to(r.backups / "cp0", target_is_directory=True)
    r.state.execute(
        "INSERT INTO checkpoints (id, created_at, reason, files_modified, git_commit_hash) "
        "VALUES (?, ?, ?, ?, ?)",
        ("lnk", 0, "test", "[]", None),  # oldest -- falls into to_remove
    )
    before = (r.backups / "cp0" / "marker.txt").read_bytes()
    assert checkpoint.prune_checkpoints(1, confirm=lambda: True) == 0
    assert remaining_ids(r) == {"cp0", "lnk"}
    assert (r.backups / "cp0" / "marker.txt").read_bytes() == before
    assert audit_rows(r)[-1]["outcome"] == "failed"


# ---------------------------------------------------------------------------
# DB-row-deleted-before-rmtree ordering
# ---------------------------------------------------------------------------

def test_db_row_removed_before_rmtree_failure_leaves_orphan_dir(prune_env, monkeypatch):
    r = prune_env
    for i in range(5):
        add_row(r, f"cp{i}", i)
    # checkpoints sorted newest-first: cp4, cp3, cp2, cp1, cp0.
    # keep_count=2 keeps cp4/cp3; to_remove is processed in that same
    # newest-first order: cp2, then cp1, then cp0.
    original_rmtree = checkpoint.shutil.rmtree

    def failing_rmtree(path, *args, **kwargs):
        if str(path).endswith("cp1"):
            raise OSError("simulated rmtree failure")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(checkpoint.shutil, "rmtree", failing_rmtree)
    removed = checkpoint.prune_checkpoints(2, confirm=lambda: True)
    # Code-reviewer finding (round 1): gate_exec reports OUTCOME_FAILED
    # for the whole call (cp1's rmtree raised), but cp2 was genuinely
    # pruned before that failure -- the return value must reflect real
    # progress, not lie that nothing happened.
    assert removed == 1
    # cp2 (processed before the failing cp1) is fully pruned: row gone,
    # directory gone.
    assert "cp2" not in remaining_ids(r)
    assert not (r.backups / "cp2").exists()
    # cp1 failed mid-rmtree: its DB row is already gone (deleted before
    # the rmtree attempt), but its directory survives as a harmless
    # orphan rather than a DB row claiming a backup that no longer
    # fully exists.
    assert "cp1" not in remaining_ids(r)
    assert (r.backups / "cp1").exists()
    # cp0 (after the failing one in iteration order) was never reached:
    # untouched.
    assert "cp0" in remaining_ids(r)
    assert (r.backups / "cp0").exists()
    assert audit_rows(r)[-1]["outcome"] == "failed"
    assert "simulated rmtree failure" in audit_rows(r)[-1]["reason"]


# ---------------------------------------------------------------------------
# Mutation test: prove the symlink guard is genuinely discriminating,
# not vacuously passing. Run manually (not part of the normal suite) by
# temporarily removing the guard and confirming
# test_symlinked_checkpoint_dir_refused_and_target_survives then fails.
# See the implementer's report for the verbatim before/after output.
