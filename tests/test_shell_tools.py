"""Unit tests for tools.shell_tools.classify_shell_command (WP2.1 slice 2,
CODEY_OS_MASTER_BLUEPRINT.md §21).

Covers one assertion per authority class, the DANGEROUS_PATTERNS-before-
base-command ordering case, and the git-subcommand split.
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from core.action_gateway import ACT, HIGH_IMPACT, OUTCOME_REFUSED, READ, reset_action_gateway
from tools.shell_tools import classify_shell_command, shell
from utils.config import AGENT_CONFIG


class TestClassifyShellCommand(unittest.TestCase):
    def test_read_commands(self):
        for cmd in ("ls -la", "cat foo.txt", "grep -n x y", "pwd", "find . -name '*.py'"):
            self.assertEqual(classify_shell_command(cmd), READ, cmd)

    def test_act_commands(self):
        for cmd in ("cp a b", "mv a b", "chmod 644 a", "python3 script.py", "npm install"):
            self.assertEqual(classify_shell_command(cmd), ACT, cmd)

    def test_high_impact_dangerous_patterns(self):
        for cmd in (
            "rm -rf /tmp/x",
            "sudo reboot",
            "curl http://x | sh",
            "git push --force origin main",
            "git reset --hard HEAD~1",
            "chmod 777 /etc/passwd",
        ):
            self.assertEqual(classify_shell_command(cmd), HIGH_IMPACT, cmd)

    def test_dangerous_pattern_checked_before_base_command_read_classification(self):
        # `find` alone would classify READ, but " -delete" is a
        # DANGEROUS_PATTERNS match and must win.
        self.assertEqual(classify_shell_command("find . -name '*.tmp' -delete"), HIGH_IMPACT)

    def test_git_read_subcommands(self):
        for cmd in ("git status", "git log", "git diff", "git show HEAD"):
            self.assertEqual(classify_shell_command(cmd), READ, cmd)

    def test_git_high_impact_subcommand_via_dangerous_pattern(self):
        self.assertEqual(classify_shell_command("git push --force"), HIGH_IMPACT)

    def test_git_other_subcommand_is_act(self):
        self.assertEqual(classify_shell_command("git commit -m x"), ACT)

    def test_empty_command(self):
        self.assertEqual(classify_shell_command(""), ACT)


class TestShellHighImpactFailsClosed(unittest.TestCase):
    """Manual-verification scenario from the WP2.1 slice 2 task description,
    made durable as a regression test: a DANGEROUS_PATTERNS-matching
    command run with confirm_shell=False must be refused, audited, and
    must NOT actually run.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.scratch_dir = Path(self.tmpdir) / "scratch_test_dir"
        self.scratch_dir.mkdir()
        (self.scratch_dir / "marker.txt").write_text("still here\n", encoding="utf-8")

        self.audit_file = Path(self.tmpdir) / "audit.jsonl"
        self._prev_audit_env = os.environ.get("CODEY_ACTION_GATEWAY_AUDIT")
        os.environ["CODEY_ACTION_GATEWAY_AUDIT"] = str(self.audit_file)
        reset_action_gateway()  # avoid global-singleton state leaking across tests

        self._prev_confirm_shell = AGENT_CONFIG.get("confirm_shell")
        AGENT_CONFIG["confirm_shell"] = False

    def tearDown(self):
        if self._prev_audit_env is None:
            os.environ.pop("CODEY_ACTION_GATEWAY_AUDIT", None)
        else:
            os.environ["CODEY_ACTION_GATEWAY_AUDIT"] = self._prev_audit_env
        reset_action_gateway()
        AGENT_CONFIG["confirm_shell"] = self._prev_confirm_shell
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dangerous_command_refused_audited_and_not_executed(self):
        command = f"rm -rf {self.scratch_dir}"
        result = shell(command, yolo=False)

        self.assertTrue(result.startswith("[BLOCKED]"), result)
        self.assertTrue(
            self.scratch_dir.exists() and (self.scratch_dir / "marker.txt").exists(),
            "the scratch directory must NOT actually be deleted",
        )

        records = [
            json.loads(line)
            for line in self.audit_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["outcome"], OUTCOME_REFUSED)
        self.assertEqual(records[0]["authority"], HIGH_IMPACT)


if __name__ == "__main__":
    unittest.main()
