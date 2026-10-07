"""Action gateway (WP2.1 slice 1, CODEY_OS_MASTER_BLUEPRINT.md §21, §16.9/§23.4.1).

Codey-OS has ~42 direct write/exec sites scattered across the repo with no
shared mediation, classification, or audit trail (the "disjoint safety
surfaces" problem). This module is the first piece of a single mediation
point: every action the agent takes is classified into one of three
authority classes, a policy decision is made, and the outcome — success
or refusal — is recorded to an append-only audit ledger.

This slice enforces the gateway at exactly one call site
(`core/preferences.py`'s `_sync_to_codeymd`, NEW-817). The other ~41 sites
found by the architect's repo-wide grep are explicitly out of scope here
(see WP2.1's own rollout — slices 2+ reroute them one at a time).

Authority classes
------------------
- READ: device state, messages, files, sensors. Mediated + audited,
  never confirmed per-act (the user isn't interrupted to approve reads).
- ACT: send/modify/create/execute. Confirmed when a confirmation path
  exists; proceeds (audited) when one doesn't — no fail-closed rule for
  this class. Inventing a fail-closed rule for ACT "for symmetry" would
  be scope drift past Ish's decision, which is scoped to HIGH_IMPACT only.
- HIGH_IMPACT: delete important data, spend money, change security
  settings, publish externally, modify Codey itself. Confirmed when a
  confirmation path exists; **fails closed + audited when none exists**
  (Ish's decision, final, not provisional: refuse and audit, never fall
  through and allow it).

`confirm_available` is supplied by the caller and means "a human
confirmation path exists in this context" (e.g. an interactive session),
NOT "confirmation was actually obtained" — this slice has no confirmation
callback/UI wiring yet, so `confirm_available=True` only unblocks the
HIGH_IMPACT fail-closed rule; it does not itself constitute consent.
Wiring a real confirmation prompt is later WP2.1 work.

The gateway's job is classification + policy decision + audit — NOT
reimplementing file-write mechanics. Actual file writes are delegated to
`core.filesystem.Filesystem` (workspace-boundary enforcement, checkpoint-
before-self-modification, snapshotting), never duplicated here.
"""

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from core.filesystem import Filesystem, FilesystemAccessError

READ = "READ"
ACT = "ACT"
HIGH_IMPACT = "HIGH_IMPACT"

AUTHORITY_CLASSES = (READ, ACT, HIGH_IMPACT)

# Outcome values recorded to the audit ledger. Kept distinct so the
# ledger is readable without cross-referencing other fields: a refusal
# (policy decision, no attempt made) and a write failure (attempted,
# Filesystem raised) are different failure modes worth telling apart.
OUTCOME_ALLOWED = "allowed"
OUTCOME_REFUSED = "refused"
OUTCOME_FAILED = "failed"


@dataclass
class GatewayDecision:
    """Result of a gateway-mediated action: whether it was allowed, and
    (if attempted) whether the delegated operation itself succeeded."""

    authority: str
    outcome: str  # OUTCOME_ALLOWED / OUTCOME_REFUSED / OUTCOME_FAILED
    reason: str
    detail: Dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.outcome == OUTCOME_ALLOWED


def audit_path() -> Path:
    """Append-only audit ledger location.

    `core/data/` (the path the WP2.1 task description suggested as an
    example) does not exist in this repo and nothing else writes there —
    the project's actual convention for this kind of persistent,
    cross-session state is `CODEY_STATE_DIR` (~/.codeyOS/), the same
    directory `core/checkpoint.py`'s CHECKPOINT_DIR, the telemetry
    layer's METRICS_DIR, and `core/trajectory.py`'s trajectories.db all
    live under. This mirrors that convention instead of introducing a
    second state root.

    Env-overridable (mirrors core/trajectory.py's db_path()) so tests
    never append to the real on-device ledger.
    """
    p = os.environ.get("CODEY_ACTION_GATEWAY_AUDIT")
    if p:
        return Path(p)
    from utils.config import CODEY_STATE_DIR

    return Path(CODEY_STATE_DIR) / "action_gateway_audit.jsonl"


def _append_audit(record: Dict[str, Any], path: Optional[Path] = None) -> None:
    path = path or audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, default=str) + "\n"
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        # The audit ledger is a best-effort record, not a safety gate
        # itself — the policy decision (allow/refuse) has already been
        # made and, for refusals, already enforced before this call. A
        # disk-full or permissions failure writing the *log entry* must
        # not crash the caller or retroactively un-refuse an action; it
        # only means this one event has no durable trace.
        pass


class ActionGateway:
    """Single mediation point: classify an action, apply policy, delegate
    the real operation, and record the outcome.

    Does not hold any Filesystem state itself — a Filesystem instance is
    passed in (or the global one is used) per call, matching how
    tools/file_tools.py already obtains one via get_filesystem().
    """

    def __init__(self, audit_file: Optional[Path] = None):
        self._audit_file = audit_file

    def _audit(self, **fields: Any) -> None:
        record = {"ts": time.time(), **fields}
        _append_audit(record, self._audit_file)

    def gate_write(
        self,
        *,
        authority: str,
        action: str,
        path: str,
        content: str,
        confirm_available: bool,
        filesystem: Optional[Filesystem] = None,
    ) -> GatewayDecision:
        """Mediate a file write through `Filesystem.write()`.

        Args:
            authority: one of READ/ACT/HIGH_IMPACT (READ writes make no
                sense but the caller's classification is trusted, not
                re-derived here).
            action: short label for the audit record (e.g.
                "preferences.sync_to_codeymd") identifying the call site.
            path: path to write, forwarded to Filesystem.write() verbatim.
            content: content to write.
            confirm_available: True iff a human confirmation path exists
                in the caller's current context. See module docstring —
                this is NOT "confirmation was obtained."
            filesystem: Filesystem instance to delegate the write to.
                Defaults to core.filesystem.get_filesystem().
        """
        if authority not in AUTHORITY_CLASSES:
            raise ValueError(f"Unknown authority class: {authority!r}")

        if authority == HIGH_IMPACT and not confirm_available:
            # Ish's decision (final): HIGH_IMPACT with no confirmation
            # path fails closed — refuse and audit, never fall through.
            decision = GatewayDecision(
                authority=authority,
                outcome=OUTCOME_REFUSED,
                reason="HIGH_IMPACT action with no confirmation path available; "
                "failing closed per policy (not attempted).",
                detail={"action": action, "path": path},
            )
            self._audit(
                authority=authority,
                action=action,
                path=path,
                outcome=decision.outcome,
                reason=decision.reason,
            )
            return decision

        # READ is never confirm-gated; ACT proceeds regardless of
        # confirm_available (confirmation, when available, is applied by
        # the caller's UI layer before the action reaches here — this
        # slice has no confirmation callback yet); HIGH_IMPACT only
        # reaches this point when confirm_available is True.
        if filesystem is None:
            from core.filesystem import get_filesystem

            filesystem = get_filesystem()

        try:
            filesystem.write(path, content)
        except FilesystemAccessError as e:
            decision = GatewayDecision(
                authority=authority,
                outcome=OUTCOME_FAILED,
                reason=str(e),
                detail={"action": action, "path": path},
            )
            self._audit(
                authority=authority,
                action=action,
                path=path,
                outcome=decision.outcome,
                reason=decision.reason,
            )
            return decision

        decision = GatewayDecision(
            authority=authority,
            outcome=OUTCOME_ALLOWED,
            reason="write succeeded",
            detail={"action": action, "path": path},
        )
        self._audit(
            authority=authority,
            action=action,
            path=path,
            outcome=decision.outcome,
            reason=decision.reason,
        )
        return decision

    def gate_read(self, *, action: str, detail: Optional[Dict[str, Any]] = None) -> GatewayDecision:
        """Mediate+audit a READ action. Never blocked by confirm_available —
        reads are audited, not confirmed."""
        decision = GatewayDecision(
            authority=READ, outcome=OUTCOME_ALLOWED, reason="read permitted", detail=detail or {}
        )
        self._audit(
            authority=READ, action=action, outcome=decision.outcome, detail=detail or {}
        )
        return decision


_gateway: Optional[ActionGateway] = None


def get_action_gateway() -> ActionGateway:
    """Get the global ActionGateway instance."""
    global _gateway
    if _gateway is None:
        _gateway = ActionGateway()
    return _gateway


def reset_action_gateway() -> None:
    """Reset the global ActionGateway instance (for testing)."""
    global _gateway
    _gateway = None
