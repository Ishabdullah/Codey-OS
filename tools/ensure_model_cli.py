"""
ensure_model_cli.py — NEW-358 follow-up (Site 3), delegated model-load
entry point for Codey-Aigentik's `startLlamaServer()`
(Codey-Aigentik/index.js, `execSync(...)` around line 221).

Aigentik currently delegates the actual model load to Codey-OS via an
inline `python3 -c "..."` one-liner that only calls
`get_loader().ensure_model('primary')`. That path reaches
`core/loader_v2.py`'s `load_primary()` and is exactly the caller
`_ensure_run_start_fallback()` (NEW-358) was confirmed live to catch —
see that function's docstring — under the generic, caller-agnostic
`emitter="codey-os.loader"` identity. This script gives that specific,
known caller (Aigentik's delegated subprocess) its own purpose-built
`run_start` record with `emitter="aigentik"` instead, recorded BEFORE
`ensure_model()` runs so it wins the loader's one-shot
`store.claim_run_start()` race and the fallback never fires for this
path. Mirrors Codey-Aigentik/index.js's own `recordTelemetryRunStart()`
(around line 1632) so the two are faithful siblings — same emitter,
same repo identity — just recorded from the Python subprocess Aigentik
spawns rather than from Aigentik's own Node process.

Deliberately does NOT pass `models=` to `record_run_start()` — same
reasoning as `_ensure_run_start_fallback()`'s own docstring: this
script's whole job is to load the model as fast as possible, and
`models=` would schedule a background full-file hash
(`schedule_cold_model_digests()`, ~5.2s cold) concurrently with the
real llama-server spawn this script exists to trigger.

Usage:
    python3 tools/ensure_model_cli.py
"""

from __future__ import annotations

import os
import sys
import time

# Not redundant with pytest's rootdir handling (which is why this test's
# `from tools.ensure_model_cli import main` works without it) — this line
# is what makes `from telemetry import recorders` / `from core.loader_v2
# import get_loader` below resolve at all when Aigentik's index.js invokes
# this file directly (`python3 /path/to/tools/ensure_model_cli.py`), where
# sys.path[0] is this file's own `tools/` directory, not the Codey-OS repo
# root above it. Do not remove as apparently-dead code without checking
# the direct-invocation path, not just the test suite.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _record_aigentik_run_start() -> None:
    """
    Best-effort, exception-wrapped telemetry call only — never allowed to
    block or delay the real work below (`get_loader().ensure_model()`).
    Same broad-except-with-comment pattern used by every other run_start
    call site in this codebase (main.py's `_record_tui_telemetry_run_start`,
    core/daemon.py's `_record_daemon_telemetry_run_start`,
    core/loader_v2.py's `_ensure_run_start_fallback`): telemetry is
    diagnostic, not load-bearing.
    """
    try:
        from telemetry import recorders
        from utils.config import LLAMA_SERVER_BIN, get_aigentik_config

        aigentik_dir = get_aigentik_config()["dir"]
        recorders.record_run_start(
            emitter="aigentik",
            pid=os.getpid(),
            repo="Codey-Aigentik",
            started_ts_wall=time.time(),
            repo_dir=aigentik_dir,
            llama_server_bin=LLAMA_SERVER_BIN,
        )
    except Exception:
        # Telemetry must never block or fail the real work (ensure_model()
        # below) — see docstring above and this module's siblings for why
        # this broad except is deliberate, not an oversight.
        try:
            import logging

            logging.getLogger(__name__).warning(
                "telemetry: failed to record run_start for delegated "
                "Aigentik ensure_model call",
                exc_info=True,
            )
        except Exception:
            pass


def main() -> int:
    _record_aigentik_run_start()

    from core.loader_v2 import get_loader

    get_loader().ensure_model("primary")
    return 0


if __name__ == "__main__":
    sys.exit(main())
