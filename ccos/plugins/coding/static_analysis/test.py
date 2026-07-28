#!/usr/bin/env python3
"""Test for static_analysis plugin."""

import importlib.util
from pathlib import Path

# _pathutil.py lives at ccos/plugins/_pathutil.py, two levels above this
# plugin's directory (test.py -> static_analysis/ -> coding/ -> plugins/).
# Loaded by file path since the ccos package isn't importable yet.
_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

from ccos.plugins.coding.static_analysis.static_analysis import (
    check_syntax,
    lint,
    test,
)


def test_lint_clean_file():
    issues, linter_name = lint(__file__)
    assert isinstance(issues, list)
    assert isinstance(linter_name, str)
    print(f"[PASS] lint() returned ({len(issues)} issues, linter={linter_name})")


def test_lint_non_python_file():
    issues, linter_name = lint("README.md")
    assert issues == []
    assert linter_name == "none"
    print("[PASS] lint() skips non-Python files")


def test_check_syntax_valid():
    result = check_syntax("x = 1\n")
    assert result is None
    print("[PASS] check_syntax() accepts valid code")


def test_check_syntax_invalid():
    result = check_syntax("def f(:\n")
    assert result is not None
    assert "SyntaxError" in result
    print("[PASS] check_syntax() flags invalid code")


def test_self_test():
    result = test()
    assert result is True
    print("[PASS] Self-test passed")


if __name__ == "__main__":
    test_lint_clean_file()
    test_lint_non_python_file()
    test_check_syntax_valid()
    test_check_syntax_invalid()
    test_self_test()
    print("\nAll static_analysis tests passed!")
