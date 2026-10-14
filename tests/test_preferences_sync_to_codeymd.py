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

import core.codeymd
import core.filesystem
import utils.config
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


class TestSyncToCodeymdSelfModFix(unittest.TestCase):
    """NEW-901: `gate_write()`'s call site in `_sync_to_codeymd` must pass
    `filesystem=get_filesystem(allow_self_modification=...)` explicitly
    rather than falling through to `core.action_gateway`'s own internal
    `get_filesystem()` default (which always means self-mod OFF,
    regardless of the live `AGENT_CONFIG` value).

    Round 1's fix called `get_filesystem(...)` eagerly as a keyword-argument
    expression. Keyword arguments are evaluated before the call they're
    passed into runs, so that eager call executed on EVERY invocation of
    this method — including the real production call shape
    (`confirm_available=False`), which `gate_write()` then refuses before
    ever touching the `filesystem` argument. `get_filesystem()` has a real
    side effect (it replaces the process-wide `Filesystem` singleton
    whenever the requested `allow_self_modification` differs from the
    cached instance's), so even a correctly-refused write silently flipped
    the shared singleton. The round 1 "DORMANT ... behavioral no-op at
    HEAD" claim was false; see NEW_ISSUES.md's NEW-901 entry, corrected in
    round 2. The round 1 "zero calls" spy that appeared to support that
    claim was also vacuous — it never actually reached `gate_write()`
    because `find_codeymd()` returned `None` and `_sync_to_codeymd`
    returned early, before the call it was meant to observe.

    Round 2 fixed this by making the `filesystem=` keyword argument lazy
    (a conditional expression, only calling `get_filesystem()` when
    `confirm_available` is True, i.e. when `gate_write()` could actually
    proceed to use it). `test_confirm_unavailable_leaves_singleton_untouched`
    below is the regression test for the actual production call shape
    (`confirm_available=False`, a real path from a patched `find_codeymd`)
    and proves the singleton is left alone on a refused write. The other
    tests below still use `confirm_available=True` directly to exercise
    the write-success/self-mod-on/self-mod-off paths, since those remain
    unreachable from today's only real caller.
    """

    def setUp(self):
        # Two distinct stale-binding hazards, both guarded against here:
        #  - utils.config.WORKSPACE_ROOT is read into core.filesystem's
        #    `_config.WORKSPACE_ROOT` module reference, but Filesystem
        #    .__init__ (filesystem.py:54) captures it into `self.workspace`
        #    only ONCE, at construction — so patching WORKSPACE_ROOT alone
        #    has no effect on an already-built singleton; reset_filesystem()
        #    below forces the next get_filesystem() call to rebuild against
        #    the patched value (NEW-899's class of bug).
        #  - core/filesystem.py's top-level `from utils.config import
        #    CODE_DIR` binds its OWN module-level `CODE_DIR` name at import
        #    time, so patching utils.config.CODE_DIR would silently do
        #    nothing here — CODE_DIR must be patched on core.filesystem
        #    itself for core.filesystem._validate_path()'s `path.relative_to
        #    (CODE_DIR)` check to see it.
        self.code_dir_tmp = Path(tempfile.mkdtemp()).resolve()
        self.codeymd_path = self.code_dir_tmp / "CODEY.md"
        self.codeymd_path.write_text("# Project\nDemo\n\n# Conventions\n", encoding="utf-8")

        # Narrow workspace: one level inside CODE_DIR, so a CODEY.md found
        # by walking up from it (find_codeymd checks up to 2 parents)
        # resolves into CODE_DIR itself — the scenario NEW-901 described.
        self.narrow_ws = self.code_dir_tmp / "narrow"
        self.narrow_ws.mkdir()

        audit_dir = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, audit_dir, ignore_errors=True)
        self.audit_file = audit_dir / "audit.jsonl"
        env_patch = patch.dict("os.environ", {"CODEY_ACTION_GATEWAY_AUDIT": str(self.audit_file)})
        env_patch.start()
        self.addCleanup(env_patch.stop)

        # addCleanup (not tearDown) for every patch below: if the
        # find_codeymd sanity assertion a few lines down fails, unittest
        # skips tearDown entirely, which would otherwise leak the patched
        # WORKSPACE_ROOT/CODE_DIR into every later test in the run.
        self.addCleanup(shutil.rmtree, self.code_dir_tmp, ignore_errors=True)
        workspace_patch = patch.object(utils.config, "WORKSPACE_ROOT", self.narrow_ws)
        workspace_patch.start()
        self.addCleanup(workspace_patch.stop)
        code_dir_patch = patch.object(core.filesystem, "CODE_DIR", self.code_dir_tmp)
        code_dir_patch.start()
        self.addCleanup(code_dir_patch.stop)
        core.filesystem.reset_filesystem()
        self.addCleanup(core.filesystem.reset_filesystem)

        # Confirm find_codeymd(), run for real, actually resolves into
        # CODE_DIR from the narrowed workspace before relying on a patched
        # stand-in for it below.
        resolved = core.codeymd.find_codeymd(start=str(self.narrow_ws))
        self.assertEqual(resolved, self.codeymd_path)

        find_codeymd_patch = patch("core.codeymd.find_codeymd", return_value=self.codeymd_path)
        find_codeymd_patch.start()
        self.addCleanup(find_codeymd_patch.stop)

        # Pre-seed the shared Filesystem singleton with self-mod ON so a
        # reverted fix (bare get_filesystem() fallback, always self-mod
        # OFF) is forced to overwrite it with the wrong value rather than
        # accidentally inheriting the right one from this seed.
        core.filesystem.get_filesystem(allow_self_modification=True)

        self.statedb = self.code_dir_tmp / "state.db"
        self.pm = _make_manager(self.statedb)
        self.pm._cache["test_framework"] = {"value": "pytest", "confidence": 0.82, "observations": 3}
        self.addCleanup(self.pm.state.close)

        create_checkpoint_patch = patch(
            "core.filesystem.create_checkpoint", return_value="test-ckpt"
        )
        create_checkpoint_patch.start()
        self.addCleanup(create_checkpoint_patch.stop)

    def _read_ledger(self):
        if not self.audit_file.exists():
            return []
        return [
            json.loads(line)
            for line in self.audit_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_write_allowed_with_self_mod_on(self):
        """Test A: with the fix in place and allow_self_modification=True,
        the HIGH_IMPACT write into CODE_DIR succeeds."""
        with patch.dict(utils.config.AGENT_CONFIG, {"allow_self_modification": True}):
            self.pm._sync_to_codeymd("test_framework", "pytest", confirm_available=True)

        content = self.codeymd_path.read_text(encoding="utf-8")
        self.assertIn("- Test framework: pytest", content)

        records = self._read_ledger()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["outcome"], OUTCOME_ALLOWED)
        self.assertEqual(records[0]["authority"], "HIGH_IMPACT")

    def test_write_still_refused_with_self_mod_off(self):
        """Test B: regression guard — with self-mod OFF, the write into
        CODE_DIR (outside the narrowed WORKSPACE_ROOT) is still refused,
        confirming the fix doesn't overcorrect."""
        before = self.codeymd_path.read_text(encoding="utf-8")

        with patch.dict(utils.config.AGENT_CONFIG, {"allow_self_modification": False}):
            self.pm._sync_to_codeymd("test_framework", "pytest", confirm_available=True)

        after = self.codeymd_path.read_text(encoding="utf-8")
        self.assertEqual(before, after, "CODEY.md must be untouched when self-mod is off")

        records = self._read_ledger()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["outcome"], OUTCOME_FAILED)
        self.assertEqual(records[0]["authority"], "HIGH_IMPACT")

    def test_confirm_unavailable_leaves_singleton_untouched(self):
        """NEW-901 round 2 regression test: the REAL production call shape
        (`confirm_available=False`, with `find_codeymd()` resolving to a
        real path — not short-circuited by an unrelated early return) must
        never touch the shared Filesystem singleton, even though
        `gate_write()` correctly refuses the write before using it.

        setUp() already seeded the singleton with
        `allow_self_modification=True`. The ambient `AGENT_CONFIG` here is
        deliberately forced to False (the opposite of the seed) — if this
        call's `filesystem=` argument were still evaluated eagerly, it
        would call `get_filesystem(allow_self_modification=False)`, which
        differs from the seeded instance's flag and would rebuild the
        singleton, flipping it to False. Leaving `AGENT_CONFIG` at its
        ambient value would not discriminate between the two code shapes
        if that value happened to already be True.
        """
        seeded = core.filesystem._filesystem
        self.assertIsNotNone(seeded)
        self.assertTrue(seeded.allow_self_modification)

        with patch.dict(utils.config.AGENT_CONFIG, {"allow_self_modification": False}):
            with patch(
                "core.filesystem.get_filesystem", wraps=core.filesystem.get_filesystem
            ) as spy:
                self.pm._sync_to_codeymd(
                    "test_framework", "pytest", confirm_available=False
                )
                spy.assert_not_called()

        # The singleton object itself, and its flag, must be untouched.
        self.assertIs(core.filesystem._filesystem, seeded)
        self.assertTrue(core.filesystem._filesystem.allow_self_modification)

        content = self.codeymd_path.read_text(encoding="utf-8")
        self.assertNotIn("- Test framework: pytest", content)

        records = self._read_ledger()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["outcome"], OUTCOME_REFUSED)
        self.assertEqual(records[0]["authority"], "HIGH_IMPACT")


if __name__ == "__main__":
    unittest.main()
