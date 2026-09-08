#!/usr/bin/env python3
"""
Tests for the NEW-42 mitigation in ccos/core/sandbox.py: literal
path-shaped tokens in a command string are now checked against the
sandbox's allowed dirs, on top of the pre-existing `cwd`-only check.
"""

import importlib.util
from pathlib import Path

# _pathutil.py lives at ccos/plugins/_pathutil.py, one level above this
# file's directory (test_sandbox_path_validation.py -> tests/ -> ccos/).
# Loaded by file path since the ccos package isn't importable yet.
_pathutil_path = Path(__file__).resolve().parent.parent / "plugins" / "_pathutil.py"
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

from ccos.core.sandbox import Sandbox


def test_path_outside_allowed_dirs_is_blocked():
    """A literal out-of-sandbox path argument is blocked even though the
    command runs from an allowed cwd (the gap the cwd-only check missed)."""
    sandbox = Sandbox()
    try:
        result = sandbox.run_command("cat /etc/passwd")
        assert not result.success, "Path outside allowed dirs should be blocked"
        assert "VIOLATION" in result.stderr
        assert "/etc/passwd" in result.stderr
    finally:
        sandbox.cleanup()


def test_path_inside_allowed_dirs_still_runs():
    """A command referencing a path inside the sandbox's allowed dirs is
    unaffected by the new check."""
    sandbox = Sandbox()
    try:
        allowed_file = sandbox._tmp_dir / "inside.txt"
        allowed_file.write_text("hello from inside the sandbox")

        result = sandbox.run_command(f"cat {allowed_file}")
        assert result.success, f"In-sandbox path should still run: {result.stderr}"
        assert "hello from inside the sandbox" in result.stdout
    finally:
        sandbox.cleanup()


def test_path_inside_repo_allowed_dir_still_runs():
    """A command referencing an absolute path under the `ccos/` allowed
    dir (the ALLOWED_DIRS entry that isn't the platform temp dir) still
    runs -- distinct from test_path_inside_allowed_dirs_still_runs, whose
    self._tmp_dir path lands under tempfile.gettempdir() and so doesn't
    exercise the ccos/ entry at all."""
    sandbox = Sandbox()
    try:
        repo_file = Path(__file__).resolve().parent.parent / "core" / "sandbox.py"
        result = sandbox.run_command(f"cat {repo_file}")
        assert result.success, f"In-repo allowed path should still run: {result.stderr}"
        assert "class Sandbox" in result.stdout
    finally:
        sandbox.cleanup()


def test_preexisting_blocked_commands_still_blocked():
    """The new path-token check runs alongside, not instead of, the
    existing BLOCKED_COMMANDS check."""
    sandbox = Sandbox()
    try:
        result = sandbox.run_command("rm -rf /")
        assert not result.success, "Blocked command should still fail"
        assert "VIOLATION" in result.stderr
        assert "Blocked command" in result.stderr
    finally:
        sandbox.cleanup()


if __name__ == "__main__":
    test_path_outside_allowed_dirs_is_blocked()
    print("  [PASS] Path outside allowed dirs is blocked")
    test_path_inside_allowed_dirs_still_runs()
    print("  [PASS] Path inside allowed dirs still runs")
    test_path_inside_repo_allowed_dir_still_runs()
    print("  [PASS] Path inside ccos/ allowed dir still runs")
    test_preexisting_blocked_commands_still_blocked()
    print("  [PASS] Pre-existing BLOCKED_COMMANDS behavior untouched")
