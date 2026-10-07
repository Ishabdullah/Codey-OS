"""Tests for core.preferences.PreferenceManager._sync_to_codeymd routed
through core.action_gateway (WP2.1 slice 1, NEW-817).

Covers:
  1. No direct write_text/open(...,"w") call remains in preferences.py for
     this call site (invariant test scoped to the one call site).
  2. confirm_available=False (the realistic case for this call site
     today): fail-closed refusal, audited, CODEY.md left untouched.
  3. confirm_available=True (simulating a future interactive context):
     write succeeds, includes the provenance marker, audited as allowed.
  4. An induced write failure (target resolves outside the Filesystem
     workspace root) in the confirm_available=True case is audited as
     failed, not silently swallowed.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.action_gateway import OUTCOME_ALLOWED, OUTCOME_FAILED, OUTCOME_REFUSED
from core.preferences import PreferenceManager
from core.state import StateStore

PREFERENCES_SOURCE = Path(__file__).resolve().parent.parent / "core" / "preferences.py"


def _make_manager(tmp_statedb: Path) -> PreferenceManager:
    """Build a PreferenceManager backed by a throwaway state DB, bypassing
    __init__'s use of the real on-device singleton StateStore."""
    pm = PreferenceManager.__new__(PreferenceManager)
    pm.state = StateStore(db_path=tmp_statedb)
    pm._cache = {}
    return pm


class TestNoDirectWritePrimitive(unittest.TestCase):
    def test_sync_to_codeymd_has_no_direct_write_text_or_open_write(self):
        source = PREFERENCES_SOURCE.read_text(encoding="utf-8")
        # Isolate just the _sync_to_codeymd method body.
        match = re.search(
            r"def _sync_to_codeymd\(.*?\n(?=    def |\Z)", source, re.DOTALL
        )
        self.assertIsNotNone(match, "could not locate _sync_to_codeymd in core/preferences.py")
        body = match.group(0)
        self.assertNotIn("write_text(", body)
        self.assertNotIn('open(', body)


class TestSyncToCodeymdGated(unittest.TestCase):
    def setUp(self):
        # Must live inside WORKSPACE_ROOT (utils.config.WORKSPACE_ROOT, this
        # repo's root at import time) so core.filesystem.Filesystem's
        # workspace-boundary check actually allows the write in the
        # confirm_available=True success case — the dedicated failure test
        # below instead deliberately points outside the workspace root.
        from utils.config import WORKSPACE_ROOT

        self.tmpdir = Path(tempfile.mkdtemp(dir=str(WORKSPACE_ROOT)))
        self.statedb = self.tmpdir / "state.db"
        self.codeymd_path = self.tmpdir / "CODEY.md"
        self.codeymd_path.write_text("# Project\nDemo\n\n# Conventions\n", encoding="utf-8")
        self.audit_file = self.tmpdir / "audit.jsonl"

        self.env_patch = patch.dict(
            "os.environ", {"CODEY_ACTION_GATEWAY_AUDIT": str(self.audit_file)}
        )
        self.env_patch.start()

        self.find_codeymd_patch = patch(
            "core.codeymd.find_codeymd", return_value=self.codeymd_path
        )
        self.find_codeymd_patch.start()

        self.pm = _make_manager(self.statedb)
        self.pm._cache["test_framework"] = {"value": "pytest", "confidence": 0.82, "observations": 3}

    def tearDown(self):
        self.find_codeymd_patch.stop()
        self.env_patch.stop()
        self.pm.state.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _read_ledger(self):
        if not self.audit_file.exists():
            return []
        return [
            json.loads(line)
            for line in self.audit_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_confirm_unavailable_fails_closed_and_leaves_codeymd_untouched(self):
        before = self.codeymd_path.read_text(encoding="utf-8")

        self.pm._sync_to_codeymd("test_framework", "pytest", confirm_available=False)

        after = self.codeymd_path.read_text(encoding="utf-8")
        self.assertEqual(before, after, "CODEY.md must be untouched on fail-closed refusal")

        records = self._read_ledger()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["outcome"], OUTCOME_REFUSED)
        self.assertEqual(records[0]["authority"], "HIGH_IMPACT")

    def test_confirm_available_writes_with_provenance_marker_and_audits_success(self):
        self.pm._sync_to_codeymd("test_framework", "pytest", confirm_available=True)

        content = self.codeymd_path.read_text(encoding="utf-8")
        self.assertIn("- Test framework: pytest", content)
        self.assertIn("<!-- auto-learned, confidence 0.82,", content)

        records = self._read_ledger()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["outcome"], OUTCOME_ALLOWED)
        self.assertEqual(records[0]["authority"], "HIGH_IMPACT")

    def test_induced_write_failure_is_audited_not_silently_swallowed(self):
        # Point find_codeymd() at a file that exists (so the read succeeds)
        # but resolves outside the Filesystem workspace root used by
        # core.filesystem.get_filesystem() (WORKSPACE_ROOT), so
        # Filesystem.write() raises FilesystemAccessError.
        outside_dir = Path(tempfile.mkdtemp())
        outside_codeymd = outside_dir / "CODEY.md"
        outside_codeymd.write_text("# Conventions\n", encoding="utf-8")

        from utils.config import WORKSPACE_ROOT

        try:
            outside_codeymd.resolve().relative_to(WORKSPACE_ROOT)
            self.skipTest("test tmp dir unexpectedly landed inside WORKSPACE_ROOT")
        except ValueError:
            pass  # expected: outside_codeymd is outside the workspace root

        self.find_codeymd_patch.stop()
        patch_outside = patch("core.codeymd.find_codeymd", return_value=outside_codeymd)
        patch_outside.start()
        try:
            self.pm._sync_to_codeymd("test_framework", "pytest", confirm_available=True)
        finally:
            patch_outside.stop()
            self.find_codeymd_patch.start()

        records = self._read_ledger()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["outcome"], OUTCOME_FAILED)


if __name__ == "__main__":
    unittest.main()
