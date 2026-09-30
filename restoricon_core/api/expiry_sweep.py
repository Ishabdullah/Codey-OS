"""
B9.2b -- estimate expiry sweep (`codey_estimator_service.md` §9 item 3).

A single daemon thread, started/stopped alongside `RestoriconAPIServer`
(same rule-4 process-lifecycle discipline `CLAUDE.md` rule 4 requires --
this module was reviewed by code-reviewer before commit). Runs an
`EstimateService.sweep_expired()` pass on a coarse interval (production
default: hourly) so `SENT`/`VIEWED` estimates past `expires_at` move to
`EXPIRED`.

No existing in-process scheduler/cron thread exists anywhere in
Codey-OS today to reuse (§9 item 3's own framing) -- `restoricon_core`'s
only prior "daemon" background work (B7's incremental document backup,
`core/backup_documents.py`) runs as a *separate OS process* managed by
`lib/service_manager.sh` (its own `--daemon`/`time.sleep(interval)` CLI
loop, started/stopped via a PID file, not a Python thread owned by
`RestoriconAPIServer`), not a thread inside the API server's own
process -- so there is no literal "B7 backup thread" class to mirror
inside this codebase. This class instead mirrors the two *in-process*
background-thread patterns that do exist here: `telemetry/store.py`'s
`TelemetryStore` (`threading.Event`-gated sleep loop, `shutdown(timeout=...)`
calling `_stop_event.set()` then a bounded `thread.join(timeout=...)`) and
`RestoriconAPIServer.start()`/`stop()`'s own bounded `self._thread.join(timeout=5.0)`
in this same package -- both stronger, already-reviewed precedents for
"never block shutdown" than a bare `time.sleep(3600)` loop would be
(a plain sleep cannot be woken early, so `stop()` would have to wait out
the remainder of the current hour-long sleep before the thread actually
exits). A `threading.Event.wait(interval)` sleep achieves the SAME
hourly cadence in production while still returning immediately once
`stop()` signals it -- this is a deliberate, minimal deviation from
§9 item 3's literal "a plain `time.sleep(3600)` loop is appropriate
here" suggestion, in service of that same section's later requirement
(and this task's own instruction) that the thread "never kills or
blocks server shutdown". No new library or scheduling abstraction is
introduced -- `threading.Event` is stdlib, already used the same way by
`telemetry/store.py`.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from ..services.estimate_service import EstimateService

logger = logging.getLogger("restoricon_core.api.expiry_sweep")

DEFAULT_INTERVAL_S = 3600.0


class EstimateExpirySweepThread:
    """Owns exactly one background thread that repeatedly calls
    `EstimateService.sweep_expired()`. Lifecycle shape matches
    `RestoriconAPIServer.start()`/`stop()` in this same package: `start()`
    is a no-op on an already-running instance, `stop()` signals and joins
    with a bounded timeout, and the thread itself is a daemon thread so a
    process crash/exit is never blocked on it even if `stop()` was never
    called.
    """

    def __init__(self, estimate_service: EstimateService, interval_s: float = DEFAULT_INTERVAL_S):
        self._estimate_service = estimate_service
        self._interval_s = interval_s
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the sweep thread. A second call while already running is
        a no-op, matching `RestoriconAPIServer.start()`'s own
        already-running guard (NEW-330) in this same package."""
        if self._thread is not None and self._thread.is_alive():
            logger.info("Estimate expiry sweep thread start() called again while already running -- no-op")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="estimate-expiry-sweep")
        self._thread.start()
        logger.info("Estimate expiry sweep thread started (interval=%.0fs)", self._interval_s)

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the loop to exit and join with a bounded timeout --
        never blocks server shutdown (mirrors
        `RestoriconAPIServer.stop()`'s own `self._thread.join(timeout=5.0)`
        in this same package). `_stop_event.set()` wakes an in-progress
        `Event.wait()` sleep immediately, so this returns as soon as the
        thread finishes whatever sweep pass (if any) was already running,
        not after the remainder of the current interval."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("Estimate expiry sweep thread stopped")

    def run_once(self) -> list:
        """Run exactly one sweep pass synchronously, on the calling
        thread, and return `EstimateService.sweep_expired()`'s result --
        the fast/testable entry point tests use instead of waiting out a
        real interval (mirrors this project's convention elsewhere of an
        injectable/manually-triggerable single-pass method rather than a
        real-time sleep in test code)."""
        return self._estimate_service.sweep_expired()

    def _loop(self) -> None:
        # Never let one bad tick kill the thread (rule 3 / this task's
        # explicit requirement): sweep_expired() itself already isolates
        # one bad *row* from the rest of its own pass (see its
        # docstring); this is the tick-level half of the same guarantee
        # -- an exception escaping sweep_expired() entirely (e.g. a
        # transient DB error) must not silently end the sweep for the
        # rest of the process's life.
        while not self._stop_event.is_set():
            try:
                expired_ids = self._estimate_service.sweep_expired()
                if expired_ids:
                    logger.info("expiry sweep: transitioned %d estimate(s) to EXPIRED: %s", len(expired_ids), expired_ids)
            except Exception:
                logger.exception("expiry sweep: unhandled error during sweep pass; will retry next interval")
            self._stop_event.wait(self._interval_s)
