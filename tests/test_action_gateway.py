"""Unit tests for core.action_gateway (WP2.1 slice 1).

Covers:
  - Classification into the three authority classes.
  - READ is never blocked by confirm_available.
  - HIGH_IMPACT with confirm_available=False fails closed and is audited.
  - HIGH_IMPACT with confirm_available=True delegates to Filesystem and
    is audited on success.
  - ACT is never fail-closed, regardless of confirm_available.
  - The audit ledger is append-only JSONL; both successes and failures
    land in it.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from core.action_gateway import (
    ACT,
    HIGH_IMPACT,
    READ,
    OUTCOME_ALLOWED,
    OUTCOME_FAILED,
    OUTCOME_REFUSED,
    ActionGateway,
)
from core.filesystem import Filesystem


class TestActionGatewayClassification(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.audit_file = Path(self.tmpdir) / "audit.jsonl"
        self.gateway = ActionGateway(audit_file=self.audit_file)
        self.fs = Filesystem(workspace=Path(self.tmpdir))

    def _read_ledger(self):
        if not self.audit_file.exists():
            return []
        return [
            json.loads(line)
            for line in self.audit_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def test_read_never_blocked_by_confirm_available(self):
        decision = self.gateway.gate_read(action="test.read")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.authority, READ)

    def test_high_impact_refused_without_confirmation_path(self):
        target = Path(self.tmpdir) / "CODEY.md"
        decision = self.gateway.gate_write(
            authority=HIGH_IMPACT,
            action="test.high_impact",
            path=str(target),
            content="hello",
            confirm_available=False,
            filesystem=self.fs,
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.outcome, OUTCOME_REFUSED)
        self.assertFalse(target.exists())

    def test_high_impact_allowed_with_confirmation_path(self):
        target = Path(self.tmpdir) / "CODEY.md"
        decision = self.gateway.gate_write(
            authority=HIGH_IMPACT,
            action="test.high_impact",
            path=str(target),
            content="hello",
            confirm_available=True,
            filesystem=self.fs,
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.outcome, OUTCOME_ALLOWED)
        self.assertEqual(target.read_text(encoding="utf-8"), "hello")

    def test_act_never_fails_closed(self):
        target = Path(self.tmpdir) / "notes.txt"
        for confirm_available in (False, True):
            decision = self.gateway.gate_write(
                authority=ACT,
                action="test.act",
                path=str(target),
                content="act-content",
                confirm_available=confirm_available,
                filesystem=self.fs,
            )
            self.assertTrue(
                decision.allowed,
                f"ACT must not fail closed (confirm_available={confirm_available})",
            )

    def test_audit_ledger_is_append_only_jsonl_with_both_outcomes(self):
        target = Path(self.tmpdir) / "CODEY.md"
        self.gateway.gate_write(
            authority=HIGH_IMPACT,
            action="test.refuse",
            path=str(target),
            content="x",
            confirm_available=False,
            filesystem=self.fs,
        )
        self.gateway.gate_write(
            authority=HIGH_IMPACT,
            action="test.allow",
            path=str(target),
            content="x",
            confirm_available=True,
            filesystem=self.fs,
        )
        records = self._read_ledger()
        self.assertEqual(len(records), 2, "each gated action appends exactly one line")
        outcomes = {r["outcome"] for r in records}
        self.assertEqual(outcomes, {OUTCOME_REFUSED, OUTCOME_ALLOWED})
        # Every record is self-contained JSON with a timestamp.
        for r in records:
            self.assertIn("ts", r)
            self.assertIn("authority", r)

    def test_failed_write_outside_workspace_is_audited_as_failed_not_refused(self):
        outside = Path(tempfile.mkdtemp()) / "CODEY.md"
        outside.write_text("existing", encoding="utf-8")
        decision = self.gateway.gate_write(
            authority=HIGH_IMPACT,
            action="test.outside_workspace",
            path=str(outside),
            content="new",
            confirm_available=True,
            filesystem=self.fs,  # fs's workspace is self.tmpdir, not `outside`'s dir
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.outcome, OUTCOME_FAILED)
        records = self._read_ledger()
        self.assertEqual(records[-1]["outcome"], OUTCOME_FAILED)


if __name__ == "__main__":
    unittest.main()
