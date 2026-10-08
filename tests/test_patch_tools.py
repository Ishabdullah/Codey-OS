"""Unit tests for tools.patch_tools.tool_patch_file's action-gateway wiring
(WP2.1 slice 3, CODEY_OS_MASTER_BLUEPRINT.md §21).

Mirrors tests/test_file_tools.py's HIGH_IMPACT/ACT split: a core-file path
with confirm_write=False must fail closed ([BLOCKED], audited, file left
untouched); an ordinary workspace path must proceed regardless.
"""

import json
import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from utils import config

config.AGENT_CONFIG["confirm_write"] = False
from tools.patch_tools import tool_patch_file  # noqa: E402


class TestPatchFileActionGateway(unittest.TestCase):
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

        # A real (but scratch, never-committed) file under the repo's own
        # core/ so core.checkpoint.is_core_file() classifies it
        # HIGH_IMPACT. patch_file requires the file to already exist (it
        # errors with [PATCH_FAILED]/[ERROR] on a missing file, which is
        # a different code path than this test exercises), so it's
        # created with known content first.
        self.core_target = CODE_DIR / "core" / "__wp21_slice3_patch_test_target.py"
        self.core_target.write_text("ORIGINAL = 1\n", encoding="utf-8")

        # Relative to cwd (WORKSPACE_ROOT) — see test_file_tools.py's
        # identical note on why a tempdir elsewhere would fail for an
        # unrelated reason (workspace boundary).
        self.workspace_target = Path("test_wp21_slice3_patch_workspace.txt")
        self.workspace_target.write_text("ORIGINAL = 1\n", encoding="utf-8")

    def tearDown(self):
        from core.action_gateway import reset_action_gateway

        if self._prev_audit_env is None:
            os.environ.pop("CODEY_ACTION_GATEWAY_AUDIT", None)
        else:
            os.environ["CODEY_ACTION_GATEWAY_AUDIT"] = self._prev_audit_env
        reset_action_gateway()
        config.AGENT_CONFIG["confirm_write"] = self._prev_confirm_write
        config.AGENT_CONFIG["allow_self_modification"] = self._prev_allow_self_mod
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

    def test_patch_core_file_blocked_with_confirm_write_false(self):
        result = tool_patch_file(str(self.core_target), "ORIGINAL = 1", "ORIGINAL = 2")
        self.assertTrue(result.startswith("[BLOCKED]"), result)
        self.assertEqual(self.core_target.read_text(encoding="utf-8"), "ORIGINAL = 1\n")
        records = self._read_ledger()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["outcome"], "refused")
        self.assertEqual(records[0]["authority"], "HIGH_IMPACT")

    def test_patch_workspace_file_succeeds_with_confirm_write_false(self):
        result = tool_patch_file(str(self.workspace_target), "ORIGINAL = 1", "ORIGINAL = 2")
        self.assertFalse(result.startswith("[BLOCKED]"), result)
        self.assertFalse(result.startswith("[ERROR]"), result)
        self.assertEqual(self.workspace_target.read_text(encoding="utf-8"), "ORIGINAL = 2\n")

    # ── allow_self_modification as an independent confirmation path
    # (code-reviewer finding, 2026-10-08) ─────────────────────────────

    def test_patch_core_file_allowed_with_allow_self_modification_true(self):
        # confirm_write stays False (set in setUp) — allow_self_modification
        # alone must be enough to unblock a HIGH_IMPACT core-file patch.
        #
        # core.filesystem.create_checkpoint is patched out — see
        # test_file_tools.py's identical note: the real implementation
        # does a full core/tools/utils/prompts backup plus real `git
        # add`/`git diff --cached` calls against this actual repo, out of
        # scope for this gateway-level regression test.
        config.AGENT_CONFIG["allow_self_modification"] = True
        with unittest.mock.patch("core.filesystem.create_checkpoint", return_value="test-ckpt"):
            result = tool_patch_file(str(self.core_target), "ORIGINAL = 1", "ORIGINAL = 2")
        self.assertFalse(result.startswith("[BLOCKED]"), result)
        self.assertFalse(result.startswith("[ERROR]"), result)
        self.assertEqual(self.core_target.read_text(encoding="utf-8"), "ORIGINAL = 2\n")

    def test_patch_core_file_still_blocked_without_allow_self_modification(self):
        # Regression guard: the fix must not overcorrect into never
        # failing closed for core-file patches.
        self.assertFalse(config.AGENT_CONFIG.get("allow_self_modification"))
        result = tool_patch_file(str(self.core_target), "ORIGINAL = 1", "ORIGINAL = 2")
        self.assertTrue(result.startswith("[BLOCKED]"), result)
        self.assertEqual(self.core_target.read_text(encoding="utf-8"), "ORIGINAL = 1\n")


if __name__ == "__main__":
    unittest.main()
