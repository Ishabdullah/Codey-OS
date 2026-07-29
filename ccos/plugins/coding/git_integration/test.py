#!/usr/bin/env python3
"""Test for git_integration plugin."""

import importlib.util
import shutil
import subprocess
import tempfile
from pathlib import Path

# _pathutil.py lives at ccos/plugins/_pathutil.py, two levels above this
# plugin's directory (test.py -> git_integration/ -> coding/ -> plugins/).
# Loaded by file path since the ccos package isn't importable yet.
_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

from ccos.plugins.coding.git_integration.git_integration import (
    detect_conflicts,
    git_branch_create,
    git_checkout,
    git_commit,
    git_current_branch,
    git_log,
    git_status,
    is_git_repo,
    test,
)


def _make_throwaway_repo() -> str:
    """Create a throwaway git repo with one commit. Caller must clean up."""
    repo = tempfile.mkdtemp(prefix="git_integration_test_")
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)
    (Path(repo) / "file.txt").write_text("hello\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, capture_output=True, text=True)
    return repo


def test_is_git_repo_on_real_repo():
    # This repo (Codey-OS) is a real git repo — read-only check, safe.
    assert is_git_repo(str(Path(__file__).resolve().parent.parent.parent.parent.parent)) is True
    print("[PASS] is_git_repo() detects the real repo")


def test_is_git_repo_on_non_repo():
    tmp = tempfile.mkdtemp(prefix="not_a_repo_")
    try:
        assert is_git_repo(tmp) is False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("[PASS] is_git_repo() rejects a non-repo directory")


def test_detect_conflicts_clean_repo():
    repo = _make_throwaway_repo()
    try:
        assert detect_conflicts(repo) == []
    finally:
        shutil.rmtree(repo, ignore_errors=True)
    print("[PASS] detect_conflicts() reports no conflicts in a clean repo")


def test_git_commit_and_branch_on_throwaway_repo():
    repo = _make_throwaway_repo()
    try:
        before_branch = git_current_branch(repo)
        before_log = git_log(10, repo)

        (Path(repo) / "new_file.txt").write_text("throwaway content\n")
        commit_result = git_commit("test: add new_file.txt", path=repo)
        assert "[ERROR]" not in commit_result

        branch_result = git_branch_create("feature-test", path=repo)
        assert "Created and switched to branch 'feature-test'" in branch_result
        after_branch = git_current_branch(repo)
        assert after_branch == "feature-test"
        assert after_branch != before_branch

        checkout_result = git_checkout(before_branch, path=repo)
        assert "[ERROR]" not in checkout_result

        after_log = git_log(10, repo)
        assert after_log != before_log

        print(
            f"[PASS] git_commit()/git_branch_create()/git_checkout() mutated "
            f"throwaway repo only (branch {before_branch!r} -> 'feature-test' -> {before_branch!r})"
        )
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_status_reflects_changes():
    repo = _make_throwaway_repo()
    try:
        clean_status = git_status(repo)
        assert clean_status == "Nothing to commit."
        (Path(repo) / "dirty.txt").write_text("x\n")
        dirty_status = git_status(repo)
        assert "dirty.txt" in dirty_status
        print("[PASS] git_status() reflects working tree changes")
    finally:
        shutil.rmtree(repo, ignore_errors=True)


def test_self_test():
    result = test()
    assert result is True
    print("[PASS] Self-test passed")


if __name__ == "__main__":
    test_is_git_repo_on_real_repo()
    test_is_git_repo_on_non_repo()
    test_detect_conflicts_clean_repo()
    test_git_commit_and_branch_on_throwaway_repo()
    test_status_reflects_changes()
    test_self_test()
    print("\nAll git_integration tests passed!")
