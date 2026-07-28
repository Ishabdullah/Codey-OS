"""
Static Analysis Plugin — thin CCOS adapter over core/linter.py.

Wraps the existing static-analysis pipeline as a capability without
duplicating any of its logic. All actual linting work stays in
core/linter.py.
"""

from ccos.plugins._pathutil import ensure_repo_root_on_path

ensure_repo_root_on_path()

from core.linter import (
    LintIssue,
    check_syntax,
    format_issues,
    get_available_linters,
    run_all_linters,
    run_linter,
)


def lint(filepath: str, content: str = None):
    """Run the best available linter on a file. Returns (issues, linter_name)."""
    return run_linter(filepath, content=content)


def test() -> bool:
    """Plugin self-test — verify lint() runs without raising."""
    issues, linter_name = lint(__file__)
    assert isinstance(issues, list), "Expected list"
    assert isinstance(linter_name, str), "Expected str"
    return True
