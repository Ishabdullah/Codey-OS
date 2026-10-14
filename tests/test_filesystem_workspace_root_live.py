"""NEW-899: WORKSPACE_ROOT must take live effect for the actual
production write path (tools.file_tools.tool_write_file), not just for
core.filesystem.get_filesystem() called directly.

Two independent stale-reference sites existed:
  Site A - core/filesystem.py did `from utils.config import WORKSPACE_ROOT`
           (one-time name binding), so Filesystem.__init__ never saw a
           later mutation of utils.config.WORKSPACE_ROOT.
  Site B - tools/file_tools.py's own module-level `_fs` cache was never
           invalidated by main.py's /cwd handler at all (it only called
           core.filesystem.reset_filesystem(), which clears that
           module's *own* singleton, not file_tools' independent one).

This test drives the real production path end to end: main.py's actual
/cwd handler (handle_command) followed by tools.file_tools.tool_write_file
-- not Filesystem directly, and not a hand-copy of the handler's reset
calls -- so deleting main.py's reset wiring would make this test fail.
It uses two tmp dirs both outside CODE_DIR so the CODE_DIR-allowance
branch in _validate_path() can't make the assertion pass for the wrong
reason.

The ActionGateway audit sink is redirected to a tmp_path file (same
pattern as the `gated` fixture in test_filesystem_git_metadata.py) so
this test's writes do not append to the real on-device
~/.codeyOS/audit.jsonl ledger.
"""

import os
import tempfile
from pathlib import Path

import pytest

import core.action_gateway as action_gateway_module
import core.filesystem as filesystem_module
import tools.file_tools as file_tools
import utils.config as config_module


@pytest.fixture
def two_dirs_outside_code_dir():
    with tempfile.TemporaryDirectory() as raw_a, tempfile.TemporaryDirectory() as raw_b:
        dir_a = Path(raw_a).resolve()
        dir_b = Path(raw_b).resolve()
        # Sanity: neither fixture dir may be inside CODE_DIR, or the
        # CODE_DIR-allowance branch in _validate_path() could make the
        # assertions below pass for the wrong reason.
        for d in (dir_a, dir_b):
            try:
                d.relative_to(config_module.CODE_DIR)
            except ValueError:
                continue
            pytest.skip(f"tmp dir {d} unexpectedly landed inside CODE_DIR")
        yield dir_a, dir_b


@pytest.fixture(autouse=True)
def reset_fs_singletons():
    """Leave both module-level Filesystem caches clean before and after,
    so this test can't leak a stale Filesystem into a later test."""
    filesystem_module.reset_filesystem()
    file_tools.reset_fs()
    yield
    filesystem_module.reset_filesystem()
    file_tools.reset_fs()


@pytest.fixture
def isolated_audit(tmp_path, monkeypatch):
    """Redirect ActionGateway's audit ledger to a disposable tmp_path
    file instead of the real ~/.codeyOS/audit.jsonl (same pattern as the
    `gated` fixture in test_filesystem_git_metadata.py)."""
    audit = tmp_path / "audit.jsonl"
    instance = action_gateway_module.ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway_module, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(file_tools, "get_action_gateway", lambda: instance)
    return audit


def test_cwd_switch_reaches_file_tools_write_path(
    monkeypatch, two_dirs_outside_code_dir, isolated_audit
):
    """Drives main.py's actual /cwd handler (handle_command), not a
    hand-copy of its reset calls -- this is load-bearing: a hand-copy
    would stay green even if main.py:1280-1282's wiring were deleted."""
    import main as main_module

    dir_a, dir_b = two_dirs_outside_code_dir
    original_cwd = os.getcwd()

    # monkeypatch.setattr (not raw assignment) so WORKSPACE_ROOT is
    # restored automatically at teardown, regardless of test outcome --
    # a leaked mutated WORKSPACE_ROOT would break
    # tests/test_preferences_sync_to_codeymd.py, which assumes the
    # default WORKSPACE_ROOT during its own run.
    monkeypatch.setattr(config_module, "WORKSPACE_ROOT", dir_a)

    try:
        # --- Step 1: write against dir A (the "before /cwd" workspace) ---
        os.chdir(dir_a)
        # Guard: if Site A regresses, _get_fs() would silently fall back
        # to the real repo workspace (import-time WORKSPACE_ROOT) and a
        # relative write below would land in the live repo tree instead
        # of a disposable tmp dir. Fail loudly before that can happen.
        assert file_tools._get_fs().workspace == dir_a
        result_a = file_tools.tool_write_file("a.txt", "content in dir A")
        assert not result_a.startswith("[ERROR]"), result_a
        assert (dir_a / "a.txt").exists()
        assert (dir_a / "a.txt").read_text() == "content in dir A"

        # --- Step 2: drive the real /cwd handler to switch to dir B ---
        main_module.handle_command(f"/cwd {dir_b}", [])

        # --- Step 3: a relative write must now land in dir B, not dir A ---
        assert file_tools._get_fs().workspace == dir_b
        result_b = file_tools.tool_write_file("b.txt", "content in dir B")
        assert not result_b.startswith("[ERROR]"), result_b
        assert (dir_b / "b.txt").exists(), (
            "relative write after /cwd-equivalent switch did not land in "
            "the new workspace (dir B) -- stale WORKSPACE_ROOT reference"
        )
        assert not (dir_a / "b.txt").exists(), (
            "relative write after /cwd-equivalent switch wrongly landed "
            "in the OLD workspace (dir A)"
        )

        # --- Step 4: an absolute path into dir B must not be rejected as
        # outside the (new) workspace. ---
        abs_target = dir_b / "c.txt"
        result_c = file_tools.tool_write_file(str(abs_target), "content C")
        assert not result_c.startswith("[ERROR]"), result_c
        assert abs_target.exists()
        assert abs_target.read_text() == "content C"
    finally:
        os.chdir(original_cwd)

# NOTE: Site B (tools/file_tools.py's reset_fs()) is independently
# necessary, not just defensive -- removing main.py's call to it (while
# keeping Site A's fix) makes the Step 3 assertion above fail, because
# file_tools._get_fs() still returns the Filesystem built against dir A.
# This is deliberately not captured as a *separate* permanent test here:
# a test that asserts the pre-fix (stale-cache) write landing in dir A
# would itself encode buggy behavior as a spec, and would go red the
# moment someone fixes this more robustly (e.g. by having _get_fs() stop
# caching at all). The single test above already pins both sites by
# asserting the post-fix (correct) outcome.
