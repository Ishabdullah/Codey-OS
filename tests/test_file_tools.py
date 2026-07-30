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

import os
import sys
import unittest
from pathlib import Path

from utils import config

config.AGENT_CONFIG["confirm_write"] = False
from tools.file_tools import tool_write_file  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
