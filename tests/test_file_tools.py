"""
Unit tests for the syntax-check guardrail in tools.file_tools.tool_write_file()
(added as part of the NEW-15 fix).

Covers:
  1. Overwriting an existing .py file with broken syntax is blocked, and the
     on-disk content is left untouched.
  2. Overwriting an existing .py file with valid syntax succeeds.
  3. Creating a brand-new .py file with broken syntax is allowed — the guard
     only applies to overwrites of files that already exist.
  4. Fail-open behavior: if core.linter is unavailable, the write proceeds
     rather than being blocked.
"""

import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from utils import config

config.AGENT_CONFIG["confirm_write"] = False
from tools.file_tools import tool_append_file, tool_write_file  # noqa: E402


class TestWriteFileSyntaxGuard(unittest.TestCase):
    def setUp(self):
        # Keep existing-file content small (< 200 bytes) so the separate
        # "drastically smaller content" size guard never fires and we're
        # only exercising the syntax-check guard.
        self.existing_file = Path("test_write_guard_existing.py")
        self.existing_content = "def foo():\n    return 1\n"
        self.existing_file.write_text(self.existing_content)

        self.new_file = Path("test_write_guard_new.py")
        if self.new_file.exists():
            self.new_file.unlink()

    def tearDown(self):
        for f in (self.existing_file, self.new_file):
            if f.exists():
                os.remove(f)

    def test_blocks_overwrite_with_broken_syntax(self):
        broken_content = "def foo(:\n    return 1\n"
        result = tool_write_file(str(self.existing_file), broken_content)

        self.assertIn("[ERROR]", result)
        self.assertIn("syntax error", result.lower())
        # File on disk must be unchanged.
        self.assertEqual(self.existing_file.read_text(), self.existing_content)

    def test_allows_overwrite_with_valid_syntax(self):
        valid_content = "def foo():\n    return 2\n"
        result = tool_write_file(str(self.existing_file), valid_content)

        self.assertNotIn("[ERROR]", result)
        self.assertEqual(self.existing_file.read_text(), valid_content)

    def test_allows_new_file_with_broken_syntax(self):
        # Guard only applies when overwriting an EXISTING .py file — brand
        # new files are unaffected regardless of syntax validity.
        broken_content = "def foo(:\n    return 1\n"
        self.assertFalse(self.new_file.exists())

        result = tool_write_file(str(self.new_file), broken_content)

        self.assertNotIn("[ERROR]", result)
        self.assertTrue(self.new_file.exists())
        self.assertEqual(self.new_file.read_text(), broken_content)

    def test_fails_open_when_linter_unavailable(self):
        # Simulate core.linter being unavailable: install a stub module in
        # sys.modules that lacks check_syntax, so the guard's
        # `from core.linter import check_syntax` raises ImportError, which is
        # caught (fail-open, same as patch_file's existing behavior) and the
        # write proceeds normally.
        broken_content = "def foo(:\n    return 1\n"

        import types

        stub_linter = types.ModuleType("core.linter")
        original_linter = sys.modules.get("core.linter")
        sys.modules["core.linter"] = stub_linter
        try:
            result = tool_write_file(str(self.existing_file), broken_content)
        finally:
            if original_linter is not None:
                sys.modules["core.linter"] = original_linter
            else:
                del sys.modules["core.linter"]

        self.assertNotIn("[ERROR]", result)
        self.assertEqual(self.existing_file.read_text(), broken_content)


class TestWriteAndAppendFileActionGateway(unittest.TestCase):
    """WP2.1 slice 3: tool_write_file/tool_append_file routed through
    core.action_gateway. A core-file path (HIGH_IMPACT) with
    confirm_write=False must fail closed ([BLOCKED], audited); an
    ordinary workspace path (ACT) must proceed regardless.
    """

    def setUp(self):
        from core.action_gateway import reset_action_gateway
        from utils.config import CODE_DIR

        self.audit_dir = tempfile.mkdtemp()
        self.audit_file = Path(self.audit_dir) / "audit.jsonl"
        self._prev_audit_env = os.environ.get("CODEY_ACTION_GATEWAY_AUDIT")
        os.environ["CODEY_ACTION_GATEWAY_AUDIT"] = str(self.audit_file)
        reset_action_gateway()

        self._prev_confirm_write = config.AGENT_CONFIG.get("confirm_write")
        config.AGENT_CONFIG["confirm_write"] = False

        self._prev_allow_self_mod = config.AGENT_CONFIG.get("allow_self_modification")
        config.AGENT_CONFIG["allow_self_modification"] = False

        # A non-existent path under the repo's own core/ — matches
        # core.checkpoint.is_core_file()'s CORE_PATTERNS, so it classifies
        # HIGH_IMPACT, but the fail-closed path never attempts the write,
        # so nothing is ever created on disk.
        self.core_target = CODE_DIR / "core" / "__wp21_slice3_test_target.py"

        # Relative to cwd (matches WORKSPACE_ROOT, set to os.getcwd() at
        # utils.config import time) — a tempdir elsewhere would be outside
        # the workspace and fail for an unrelated reason (workspace
        # boundary, not this test's ACT-vs-HIGH_IMPACT distinction).
        self.workspace_target = Path("test_wp21_slice3_workspace_notes.txt")

    def tearDown(self):
        from core.action_gateway import reset_action_gateway

        if self._prev_audit_env is None:
            os.environ.pop("CODEY_ACTION_GATEWAY_AUDIT", None)
        else:
            os.environ["CODEY_ACTION_GATEWAY_AUDIT"] = self._prev_audit_env
        reset_action_gateway()
        config.AGENT_CONFIG["confirm_write"] = self._prev_confirm_write
        config.AGENT_CONFIG["allow_self_modification"] = self._prev_allow_self_mod
        # Guard against a regression actually creating this — it never
        # should on the fail-closed path, but don't leave it behind either.
        if self.core_target.exists():
            self.core_target.unlink()
        if self.workspace_target.exists():
            self.workspace_target.unlink()

    def _read_ledger(self):
        if not self.audit_file.exists():
            return []
        return [
            json.loads(line)
            for line in self.audit_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_write_file_core_path_blocked_with_confirm_write_false(self):
        result = tool_write_file(str(self.core_target), "print('hi')\n")
        self.assertTrue(result.startswith("[BLOCKED]"), result)
        self.assertFalse(self.core_target.exists())
        records = self._read_ledger()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["outcome"], "refused")
        self.assertEqual(records[0]["authority"], "HIGH_IMPACT")

    def test_write_file_workspace_path_succeeds_with_confirm_write_false(self):
        result = tool_write_file(str(self.workspace_target), "hello\n")
        self.assertFalse(result.startswith("[BLOCKED]"), result)
        self.assertFalse(result.startswith("[ERROR]"), result)
        self.assertEqual(self.workspace_target.read_text(encoding="utf-8"), "hello\n")

    def test_append_file_core_path_blocked_with_confirm_write_false(self):
        result = tool_append_file(str(self.core_target), "x = 1\n")
        self.assertTrue(result.startswith("[BLOCKED]"), result)
        self.assertFalse(self.core_target.exists())
        records = self._read_ledger()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["outcome"], "refused")
        self.assertEqual(records[0]["authority"], "HIGH_IMPACT")

    def test_append_file_workspace_path_succeeds_with_confirm_write_false(self):
        result = tool_append_file(str(self.workspace_target), "hello\n")
        self.assertFalse(result.startswith("[BLOCKED]"), result)
        self.assertFalse(result.startswith("[ERROR]"), result)
        self.assertTrue(self.workspace_target.exists())
        result2 = tool_append_file(str(self.workspace_target), "world\n")
        self.assertFalse(result2.startswith("[BLOCKED]"), result2)
        self.assertEqual(self.workspace_target.read_text(encoding="utf-8"), "hello\nworld\n")

    # ── allow_self_modification as an independent confirmation path
    # (code-reviewer finding, 2026-10-08) ─────────────────────────────

    def test_write_file_core_path_allowed_with_allow_self_modification_true(self):
        # confirm_write stays False (set in setUp) — allow_self_modification
        # alone must be enough to unblock a HIGH_IMPACT core-file write.
        # Without this, --yolo + --allow-self-mod (two independently
        # documented, simultaneously-usable flags) would have the gateway
        # silently defeat the one flag whose entire purpose is to permit
        # this.
        #
        # core.filesystem.create_checkpoint is patched out: the real
        # implementation does a full core/tools/utils/prompts backup PLUS
        # real `git add`/`git diff --cached` calls against this actual
        # repo (core/checkpoint.py) — out of scope for this gateway-level
        # test and not something a unit test should touch. What's under
        # test here is the gateway's confirm_available computation, not
        # the pre-existing (and explicitly out-of-scope, per this slice's
        # task description) checkpoint mechanism one layer down.
        config.AGENT_CONFIG["allow_self_modification"] = True
        try:
            with unittest.mock.patch("core.filesystem.create_checkpoint", return_value="test-ckpt"):
                result = tool_write_file(str(self.core_target), "print('hi')\n")
        finally:
            if self.core_target.exists():
                self.core_target.unlink()
        self.assertFalse(result.startswith("[BLOCKED]"), result)
        self.assertFalse(result.startswith("[ERROR]"), result)

    def test_write_file_core_path_still_blocked_without_allow_self_modification(self):
        # Regression guard: the fix must not overcorrect into never
        # failing closed for core-file writes. allow_self_modification
        # stays at its setUp default (False); confirm_write is also False.
        self.assertFalse(config.AGENT_CONFIG.get("allow_self_modification"))
        result = tool_write_file(str(self.core_target), "print('hi')\n")
        self.assertTrue(result.startswith("[BLOCKED]"), result)
        self.assertFalse(self.core_target.exists())

    def test_append_file_core_path_allowed_with_allow_self_modification_true(self):
        # See test_write_file_core_path_allowed_with_allow_self_modification_true
        # above for why create_checkpoint is patched out.
        config.AGENT_CONFIG["allow_self_modification"] = True
        try:
            with unittest.mock.patch("core.filesystem.create_checkpoint", return_value="test-ckpt"):
                result = tool_append_file(str(self.core_target), "x = 1\n")
        finally:
            if self.core_target.exists():
                self.core_target.unlink()
        self.assertFalse(result.startswith("[BLOCKED]"), result)
        self.assertFalse(result.startswith("[ERROR]"), result)


if __name__ == "__main__":
    unittest.main()
