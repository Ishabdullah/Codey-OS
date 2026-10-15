"""Shared mechanics for explicitly confirmed destructive persistence resets.

Callers supply fixed action labels and private reset mechanics. This is not
an authorization mechanism for arbitrary state writes or normal recording.
"""

import time


def _gate_reset(*, action, execute, confirm_available=None, confirm=None):
    from core.action_gateway import HIGH_IMPACT, get_action_gateway

    def reset():
        try:
            execute()
        except Exception:  # noqa: BLE001 - sanitize private database/trigger diagnostics
            # Database/trigger exception text may contain private stored data.
            raise RuntimeError("Persistence reset failed") from None
        return "Persistence reset completed"

    return get_action_gateway().gate_exec(
        authority=HIGH_IMPACT,
        action=action,
        command=action,
        confirm_available=callable(confirm) and confirm_available is not False,
        confirm=confirm if callable(confirm) else None,
        execute=reset,
    )


def _reset_state_record(state, key, replacement=None):
    """Change a fixed reset-owned state row, rolling back on any SQL failure.

    StateStore's ordinary set/delete primitives do not roll back failed
    transactions. Keep reset transactions isolated from later recording calls.
    """
    with state._lock:
        if state._conn.in_transaction:
            # A prior recording failure may have left unrelated writes pending.
            # Reset owns neither their commit nor their rollback; fail closed.
            raise RuntimeError("State transaction already active")
        with state._conn:
            if replacement is None:
                state._conn.execute("DELETE FROM state WHERE key = ?", (key,))
            else:
                state._conn.execute(
                    "INSERT OR REPLACE INTO state (key, value, updated_at) VALUES (?, ?, ?)",
                    (key, replacement, int(time.time())),
                )
