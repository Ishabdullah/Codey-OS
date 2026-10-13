"""Copied-index Git worktree READ contracts; all Git/state effects are disposable."""

import json

import pytest

from core import git_worktree_context, githelper
from core.git_worktree_context import GitWorktreeError
from tests.test_git_broad_commit_context import conflict
from tests.test_git_literal_paths import repository as isolated_repository


@pytest.fixture
def repository(tmp_path, monkeypatch):
    parent = tmp_path / "worktree-admin"
    parent.mkdir()
    monkeypatch.setattr(git_worktree_context, "_temporary_candidates", lambda: (parent,))
    yield from isolated_repository.__wrapped__(tmp_path, monkeypatch)
    assert list(parent.iterdir()) == []


def records(r):
    return [json.loads(line) for line in r.audit.read_text().splitlines()]


def snapshot(r):
    result = {}
    for path in [r.repo, *r.repo.rglob("*")]:
        st = path.lstat()
        result[str(path.relative_to(r.repo))] = (st.st_dev, st.st_ino, st.st_mode, path.read_bytes() if path.is_file() and not path.is_symlink() else None)
    return result


# ── git_status ────────────────────────────────────────────────────────────────


def test_clean_status(repository):
    r = repository
    before = snapshot(r)
    assert githelper.git_status(str(r.repo)) == "Nothing to commit."
    assert snapshot(r) == before
    assert len(records(r)) == 1 and records(r)[0]["authority"] == "READ" and records(r)[0]["outcome"] == "allowed"
    assert records(r)[0]["action"] == "githelper.git_status"
    assert records(r)[0]["command"] == "git worktree query"


def test_dirty_status(repository):
    r = repository
    (r.repo / "core/example.py").write_text("changed\n")
    (r.repo / "untracked.py").write_text("new\n")
    status = githelper.git_status(str(r.repo))
    assert "core/example.py" in status and "untracked.py" in status


def test_unborn_status(repository, tmp_path):
    r = repository
    cwd = tmp_path / "unborn"
    cwd.mkdir()
    r.git("init", "-b", "fresh", cwd=cwd)
    (cwd / "new.py").write_text("content\n")
    assert "new.py" in githelper.git_status(str(cwd))


# ── git_status_paths (NEW-879 carryover) ────────────────────────────────────────


def test_status_paths_directory_selects_subtree(repository):
    r = repository
    (r.repo / "core/example.py").write_text("changed\n")
    (r.repo / "unrelated.txt").write_text("changed\n")
    status = githelper.git_status_paths(["core"], str(r.repo))
    assert "core/example.py" in status and "unrelated.txt" not in status


def test_status_paths_dot_selects_cwd_subtree(repository):
    r = repository
    (r.repo / "core/example.py").write_text("changed\n")
    (r.repo / "unrelated.txt").write_text("changed\n")
    status = githelper.git_status_paths(["."], str(r.repo / "core"))
    assert "example.py" in status and "unrelated.txt" not in status


def test_status_paths_bytes_operand_is_forwarded_verbatim(repository):
    """NEW-879: path operands are forwarded verbatim, including bytes -
    not narrowed to str by the READ gate added in this slice."""
    r = repository
    (r.repo / "core/example.py").write_text("changed\n")
    status = githelper.git_status_paths([b"core/example.py"], str(r.repo))
    assert "core/example.py" in status


def test_status_paths_empty_list_unrestricted(repository):
    r = repository
    (r.repo / "core/example.py").write_text("changed\n")
    (r.repo / "unrelated.txt").write_text("changed\n")
    status = githelper.git_status_paths([], str(r.repo))
    assert "core/example.py" in status and "unrelated.txt" in status


# ── git_diff_stat ───────────────────────────────────────────────────────────────


def test_diff_stat_normal_head(repository):
    r = repository
    (r.repo / "core/example.py").write_text("changed content\n")
    stat = githelper.git_diff_stat(str(r.repo))
    assert "example.py" in stat


def test_diff_stat_unborn_is_explicit_empty(repository, tmp_path):
    r = repository
    cwd = tmp_path / "unborn-stat"
    cwd.mkdir()
    r.git("init", "-b", "fresh", cwd=cwd)
    (cwd / "new.py").write_text("content\n")
    assert githelper.git_diff_stat(str(cwd)) == ""
    assert records(r)[0]["outcome"] == "allowed"


# ── detect_conflicts ─────────────────────────────────────────────────────────────


def test_detect_conflicts_clean_repo_is_empty(repository):
    r = repository
    assert githelper.detect_conflicts(str(r.repo)) == []


def test_detect_conflicts_real_forced_merge_conflict(repository):
    r = repository
    conflict(r)
    files = githelper.detect_conflicts(str(r.repo))
    assert files == ["core/example.py"]


def test_detect_conflicts_mid_merge_is_explicitly_supported_not_rejected(repository):
    """Active merge state (MERGE_HEAD present) must not be structurally
    rejected: detect_conflicts exists specifically to report unmerged paths,
    which only exist mid-merge (contrast core/git_commit_context.py's
    _ACTIVE rejection, intentionally not imported here)."""
    r = repository
    conflict(r)
    assert (r.repo / ".git/MERGE_HEAD").exists()
    before = (r.repo / ".git/MERGE_HEAD").read_bytes()
    assert githelper.detect_conflicts(str(r.repo)) == ["core/example.py"]
    assert (r.repo / ".git/MERGE_HEAD").read_bytes() == before
    assert records(r)[0]["outcome"] == "allowed"


# ── git_diff_for_commit ──────────────────────────────────────────────────────────


def test_diff_for_commit_staged(repository):
    r = repository
    (r.repo / "core/example.py").write_text("staged content\n")
    r.git("add", "core/example.py")
    diff = githelper.git_diff_for_commit(str(r.repo))
    assert "staged content" in diff


def test_diff_for_commit_unstaged(repository):
    r = repository
    (r.repo / "core/example.py").write_text("unstaged content\n")
    diff = githelper.git_diff_for_commit(str(r.repo))
    assert "unstaged content" in diff


def test_diff_for_commit_unborn_is_sentinel(repository, tmp_path):
    r = repository
    cwd = tmp_path / "unborn-diff"
    cwd.mkdir()
    r.git("init", "-b", "fresh", cwd=cwd)
    assert githelper.git_diff_for_commit(str(cwd)) == "(no diff available)"


def test_diff_for_commit_single_commit_no_parent_is_sentinel(repository, tmp_path):
    r = repository
    cwd = tmp_path / "single-commit"
    cwd.mkdir()
    r.git("init", "-b", "fresh", cwd=cwd)
    (cwd / "only.py").write_text("content\n")
    r.git("add", "-A", cwd=cwd)
    r.git("config", "user.name", "Temp", cwd=cwd)
    r.git("config", "user.email", "temp@example.invalid", cwd=cwd)
    r.git("commit", "-m", "only commit", cwd=cwd)
    assert githelper.git_diff_for_commit(str(cwd)) == "(no diff available)"


def test_diff_for_commit_truncates(repository):
    r = repository
    (r.repo / "core/example.py").write_text("x" * 5000 + "\n")
    diff = githelper.git_diff_for_commit(str(r.repo), max_chars=100)
    assert diff.endswith("... (truncated)") and len(diff) < 200


# ── Sparse / split index rejection (inversion #1 vs. prior slices) ──────────────


def test_sparse_index_is_rejected(repository):
    r = repository
    r.git("sparse-checkout", "init", "--cone", "--sparse-index")
    with pytest.raises(GitWorktreeError):
        githelper.git_status(str(r.repo))
    assert records(r)[0]["outcome"] == "failed"


def test_split_index_is_rejected(repository):
    r = repository
    r.git("update-index", "--split-index")
    with pytest.raises(GitWorktreeError):
        githelper.git_status(str(r.repo))
    assert records(r)[0]["outcome"] == "failed"


# ── CRLF / native attribute fidelity ─────────────────────────────────────────────


def test_autocrlf_fidelity(repository):
    r = repository
    r.git("config", "core.autocrlf", "true")
    (r.repo / "core/example.py").write_bytes(b"line one\r\nline two\r\n")
    diff = githelper.git_diff_for_commit(str(r.repo))
    assert "line one" in diff


# ── info/exclude affecting untracked reporting ──────────────────────────────────


def test_info_exclude_affects_untracked_reporting(repository):
    r = repository
    (r.repo / ".git/info").mkdir(exist_ok=True)
    (r.repo / ".git/info/exclude").write_text("ignored.py\n")
    (r.repo / "ignored.py").write_text("excluded\n")
    (r.repo / "visible.py").write_text("tracked new\n")
    status = githelper.git_status(str(r.repo))
    assert "visible.py" in status and "ignored.py" not in status


def test_grafts_rewrite_history_seen_by_diff_for_commit(repository, tmp_path):
    """info/grafts is copied read-only into the admin dir (mirrors
    core/git_query_context.py:239-242): a grafted single-parent history must
    still be treated as having a parent for the HEAD~1..HEAD diff leg."""
    r = repository
    r.git("commit", "--allow-empty", "-m", "second")
    current = r.git("rev-parse", "HEAD").stdout.strip()
    first = r.git("rev-parse", "HEAD~1").stdout.strip()
    info = r.repo / ".git/info"
    info.mkdir(exist_ok=True)
    # Graft: rewrite the current commit's parent list to none (as if it were
    # a root commit) - has_parent() must observe this, not the real parent.
    (info / "grafts").write_text(f"{current}\n")
    assert r.git("rev-parse", "--verify", "HEAD~1", check=False).returncode != 0
    assert githelper.git_diff_for_commit(str(r.repo)) == "(no diff available)"


# ── Filter-attribute rejection ────────────────────────────────────────────────────


def test_filter_attribute_is_rejected_before_content_runs(repository):
    r = repository
    (r.repo / ".gitattributes").write_text("*.secret filter=evil\n")
    r.git("add", ".gitattributes")
    r.git("commit", "-m", "attributes")
    (r.repo / "data.secret").write_text("content\n")
    with pytest.raises(GitWorktreeError):
        githelper.git_status(str(r.repo))
    assert records(r)[-1]["outcome"] == "failed"
