"""Mediated ACT persistence for high-frequency fixed-location writes.

Session and task-queue files are rewritten every turn / planned step. Exact
semantics:

- The policy gate is consulted on EVERY write: each save calls
  ``ActionGateway.gate_exec`` (ACT, static action and command labels, no
  paths or content), so any present or future gateway policy applies to all
  saves, not just the first. There is no per-process "already audited" mark.
- Audit rows are coalesced per target: the gateway's ``coalesce_key`` (the
  target path, held in memory and hashed, never written to the ledger)
  suppresses a row only when the previous outcome recorded for that target
  was the same non-refused outcome. A first row, any change
  (allowed->failed, failed->allowed) and every refusal are always written. A
  persistently failing target therefore yields one failed row, not one per save.
- The failure reason is a fixed label; the original exception is handed back
  to the caller and never placed in the audit.
"""

from typing import Callable, Optional, Tuple

_FAIL_LABEL = "persistence write failed"


def persist_coalesced(
    *, action: str, command: str, target_key: str, write: Callable[[], None]
) -> Tuple[bool, Optional[BaseException], str]:
    """Run ``write`` under mediated ACT with per-target audit coalescing.

    Returns ``(ok, original_error, reason)``. ``original_error`` is the
    exception ``write`` raised (never placed in the audit), or None when the
    gate refused without attempting the write.
    """
    from core.action_gateway import ACT, get_action_gateway

    original_error: Optional[BaseException] = None

    def execute() -> str:
        nonlocal original_error
        try:
            write()
        except Exception as exc:
            # gate_exec audits str(exc), which may carry paths or project
            # names; keep the original for the caller and audit a fixed text.
            original_error = exc
            raise RuntimeError(_FAIL_LABEL) from None
        return "persisted"

    decision = get_action_gateway().gate_exec(
        authority=ACT, action=action, command=command,
        confirm_available=False, execute=execute, coalesce_key=target_key,
    )
    if decision.allowed:
        return True, None, "persisted"
    return False, original_error, decision.reason
