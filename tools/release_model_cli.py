"""
release_model_cli.py — NEW-413 (piece 1, this repo only), delegated
model-release entry point mirroring `tools/ensure_model_cli.py`'s
delegated model-LOAD entry point.

NEW-413's mechanism: `~/Codey-Aigentik` delegates a real primary-model
load to the Codey-OS daemon on startup (`tools/ensure_model_cli.py`), but
if Aigentik's own subsequent warm-up call fails, Aigentik's node process
exits with no path to tell the daemon "release what you just loaded for
me" — orphaning the llama-server it caused to spawn. This script is that
missing release path: a thin CLI wrapper around `core/daemon.py`'s
already-safe `release_model_slot` socket command (the exact same command
`main.py`'s `_load_primary_with_gate_recovery()` already calls as a live
client — see that function for the send_command() call shape this
mirrors). `_handle_release_model_slot()` already declines to release
when `ThermalManager.is_inference_active()` is true or `SWAP_GUARD` is
held (see its own docstring), so calling this unconditionally on
Aigentik's warm-up-failure exit path cannot kill a model server anything
else is legitimately using — it will simply decline (a normal outcome
this script treats as non-fatal, not an error).

This is deliberately ONLY the Codey-OS-side half of the NEW-413 fix. The
other half — Aigentik's own warm-up-failure exit path actually calling
this script — is a change to a separate repo (`~/Codey-Aigentik`) and is
out of this script's scope; see NEW_ISSUES.md's NEW-413 entry for the
full split.

Usage:
    python3 tools/release_model_cli.py

Exit codes:
    0 — the daemon confirmed the slot is free (either it released the
        model just now, or it was already unloaded — both satisfy this
        script's caller's goal).
    1 — could not reach the daemon at all (not running, socket error,
        timeout) or the daemon returned an unexpected "error" status.
        Non-fatal to the caller's own shutdown (there is nothing more
        this script can do), but distinguished from a clean release so a
        caller can log it.
    2 — the daemon is reachable and responded, but did not confirm a free
        slot: either it declined to release the slot right now (busy
        with an in-flight task, a concurrent swap, or a recent-release
        cooldown), or it attempted the unload but could not confirm the
        port went down (`RELEASE_OUTCOME_UNCONFIRMED` — see
        `core/daemon.py`'s `RELEASE_OUTCOME_*` constants for the full
        set). The busy/cooldown declines are `_handle_release_model_slot()`
        correctly refusing to release a model something else may still
        be using, not an error in this script. The unconfirmed-unload
        case is different — an unload WAS attempted — so a caller relying
        on exit code alone to know whether a process still needs
        cleaning up should not treat exit 2 as uniformly "nothing
        happened"; check the printed message/outcome if that distinction
        matters.
"""

from __future__ import annotations

import os
import sys

# Mirrors tools/ensure_model_cli.py's own comment: needed so `from
# core.daemon import send_command` below resolves when this file is
# invoked directly (`python3 /path/to/tools/release_model_cli.py`) from
# Aigentik, where sys.path[0] is this file's own `tools/` directory, not
# the Codey-OS repo root above it.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    from core.daemon import (
        RELEASE_OUTCOME_ALREADY_UNLOADED,
        RELEASE_OUTCOME_RELEASED,
        send_command,
    )

    try:
        response = send_command(
            "release_model_slot",
            {"model_id": "primary"},
            timeout=20.0,
        )
    except Exception as e:
        # send_command() raises for socket errors, no daemon running, a
        # timeout, or the daemon's own "error" status — all treated the
        # same here as "could not confirm release", since there is
        # nothing more a caller on its own way out can do about any of
        # these. Printed, not silently swallowed, so a caller's log
        # captures why.
        print(f"release_model_cli: could not reach daemon ({e})", file=sys.stderr)
        return 1

    outcome = response.get("outcome")
    if outcome in (RELEASE_OUTCOME_RELEASED, RELEASE_OUTCOME_ALREADY_UNLOADED):
        return 0

    # busy_task_running / busy_swap_in_flight / cooldown / an
    # unrecognized value — the daemon declined to release right now.
    # This is `_handle_release_model_slot()` working as designed (never
    # releasing a model something else may legitimately be using), not a
    # failure of this script.
    print(
        f"release_model_cli: daemon declined to release ({outcome}: "
        f"{response.get('message', '')})",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
