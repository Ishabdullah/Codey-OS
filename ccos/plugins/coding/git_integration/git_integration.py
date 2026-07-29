"""
Git Integration Plugin — thin CCOS adapter over core/githelper.py.

Wraps the existing git helper functions as capabilities without
duplicating any of their logic. All actual git work stays in
core/githelper.py.

`uses_conventional_commits` is intentionally not exposed — it's an
internal predicate used only by `generate_commit_message` and isn't
called anywhere else in the codebase, so it doesn't warrant a
top-level capability of its own.
"""

from ccos.plugins._pathutil import ensure_repo_root_on_path

ensure_repo_root_on_path()

from core.githelper import (
    detect_conflicts,
    generate_commit_message,
    get_conflict_sections,
    git_branch_create,
    git_branches,
    git_checkout,
    git_commit,
    git_commit_log_messages,
    git_current_branch,
    git_diff_for_commit,
    git_diff_stat,
    git_log,
    git_merge,
    git_push,
    git_status,
    is_git_repo,
)


def test() -> bool:
    """Plugin self-test — verify a read-only capability runs without raising."""
    result = is_git_repo(".")
    assert isinstance(result, bool), "Expected bool"
    return True
