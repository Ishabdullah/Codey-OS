#!/usr/bin/env python3
"""
Planner (1.5B) model loader for Codey-OS.

Mirrors core/loader_v2.py's ModelLoader/LlamaServer pattern for the 7B
primary model, but for the dedicated 1.5B planning model (see
core/plannd.py's PLANNER_PROMPT / get_plan()). Reuses LlamaServer directly
(parameterized by port) instead of duplicating its subprocess/health-check/
teardown logic — that duplication is exactly the NEW-12 dual-launcher
problem class this module exists to avoid repeating.

Sequential-swap contract (Ish's decision, not negotiable here): the primary
7B model and this 1.5B planner must never be resident at the same time on
this device. ensure_planner() below unloads the primary first if it's
loaded; core/loader_v2.py's ModelLoader.ensure_model() does the symmetric
thing in the other direction. See core/loader_v2.py's SWAP_GUARD docstring
for the in-process concurrency story (daemon watchdog vs. an in-flight
get_plan() swap) and probe_port_health() for the cross-process story (don't
evict a server this process didn't spawn).
"""

import time
from pathlib import Path
from typing import Optional

from utils.config import LLAMA_SERVER_BIN, PLANND_SERVER_PORT, PLANNER_MODEL_PATH
from utils.logger import error, info, success, warning


class PlannerLoader:
    """Manages the dedicated 1.5B planner llama-server, sequential-swap with primary."""

    def __init__(self):
        self._loaded: bool = False
        self._server = None  # Optional[core.loader_v2.LlamaServer]
        self._loaded_at: float = 0
        self._load_failures: int = 0

    def load(self) -> bool:
        """Load the planner (1.5B) model. Does NOT itself handle the swap — see ensure_planner()."""
        try:
            from core.loader_v2 import LlamaServer  # local import: avoid import-time cycle

            info(f"Loading planner model: {PLANNER_MODEL_PATH.name}")

            if not PLANNER_MODEL_PATH.exists():
                error(f"Planner model file not found: {PLANNER_MODEL_PATH}")
                self._load_failures += 1
                return False

            llama_bin = Path(LLAMA_SERVER_BIN)
            if not llama_bin.exists():
                error(f"llama-server not found: {LLAMA_SERVER_BIN}")
                self._load_failures += 1
                return False

            self._server = LlamaServer(PLANNER_MODEL_PATH, port=PLANND_SERVER_PORT)
            if not self._server.start():
                self._load_failures += 1
                return False

            self._loaded = True
            self._loaded_at = time.time()
            success(f"Loaded planner model ({PLANNER_MODEL_PATH.name})")
            return True

        except Exception as e:
            error(f"Failed to load planner model: {e}")
            self._load_failures += 1
            return False

    def unload(self):
        """Unload (stop) the planner model server."""
        if self._server:
            info("Stopping planner model server...")
            self._server.stop()
            self._server = None
            self._loaded = False

    def get_pid(self) -> Optional[int]:
        """Return the PID of the llama-server process this loader spawned, if any."""
        if self._server and self._server.process:
            return self._server.process.pid
        return None

    def is_loaded(self) -> bool:
        return bool(self._loaded and self._server and self._server.is_running())

    def ensure_planner(self) -> bool:
        """
        Ensure the planner model is loaded, swapping out the primary 7B
        model first if it's currently loaded. Never blocks more than the
        underlying LlamaServer.start()'s own bounded waits (port lock
        contention poll + spawn health-wait, each up to 60s — see
        core/loader_v2.py:LlamaServer.start()).

        Returns False (never raises) if the swap can't be completed safely
        — callers (core/plannd.py:get_plan()) treat False the same as "no
        local planner available right now" and fall back to unplanned
        single-task execution (core/daemon.py's existing fallback path).
        """
        if self.is_loaded():
            return True

        from core.loader_v2 import SWAP_GUARD

        # Non-blocking: see SWAP_GUARD's docstring in loader_v2.py. If the
        # daemon watchdog's ensure_model() is mid-swap in this same process,
        # defer rather than fight over it — the caller (get_plan()) will
        # simply report "no plan" for this one request.
        if not SWAP_GUARD.acquire(blocking=False):
            info("Planner load deferred — primary swap in flight")
            return False
        try:
            if not self._evict_primary_and_confirm_free():
                return False
            return self.load()
        finally:
            SWAP_GUARD.release()

    def _evict_primary_and_confirm_free(self) -> bool:
        """
        Unload the primary 7B model if THIS process spawned it, then confirm
        its port is actually free before we proceed to spawn the planner —
        LlamaServer.stop() swallows exceptions and unconditionally clears
        its own "loaded" state in a finally block, so "unloaded" can be a
        lie if the OS process didn't actually die; re-checking the port
        catches that instead of trusting the flag.

        Returns False (deliberate design choice, not an oversight) when the
        primary's port is bound by something we can't identify as our own
        spawned process — CLAUDE.md rule 3 forbids killing a process we
        didn't spawn, so in that case we do not load the planner at all
        (leaving both models correctly non-resident together is preferred
        over risking two loaded at once); the caller falls back to
        unplanned execution.

        The whole body is wrapped in try/except, mirroring
        core/loader_v2.py:ModelLoader._evict_planner_and_confirm_free()
        exactly — this method's caller, ensure_planner(), documents "Returns
        False (never raises)", so any unexpected error here (e.g. a
        malformed HTTP status line from a half-dead server, which
        probe_port_health()'s own except clause does not catch) must fail
        closed instead of propagating.
        """
        try:
            from core.loader_v2 import get_loader, probe_port_health
            from utils.config import PRIMARY_SERVER_PORT

            loader = get_loader()
            if loader.is_loaded():
                info("Sequential swap: unloading primary (7B) before loading planner (1.5B)")
                loader.unload()

            if probe_port_health(PRIMARY_SERVER_PORT):
                # Either our own unload() didn't actually kill the process, or
                # some other process owns the primary port. Either way we can't
                # safely proceed — fail closed rather than risk both resident.
                warning(
                    f"Primary model still answering on port {PRIMARY_SERVER_PORT} after "
                    "eviction attempt — not loading planner (would violate sequential-swap)"
                )
                return False
            return True
        except Exception as e:
            # A failure in this cooperative check (import error, unexpected
            # exception from probe_port_health(), etc.) is treated the same
            # as "couldn't confirm free" — fail closed rather than risk both
            # models resident, consistent with the primary-side mirror of
            # this method (ModelLoader._evict_planner_and_confirm_free()).
            warning(f"Primary eviction check failed: {e} — not loading planner")
            return False

    def get_status(self) -> dict:
        return {
            "loaded": self.is_loaded(),
            "loaded_at": self._loaded_at,
            "uptime_seconds": time.time() - self._loaded_at if self._loaded_at else 0,
            "load_failures": self._load_failures,
        }


_planner_loader: Optional[PlannerLoader] = None


def get_planner_loader() -> PlannerLoader:
    """Get the global planner-loader instance."""
    global _planner_loader
    if _planner_loader is None:
        _planner_loader = PlannerLoader()
    return _planner_loader


def reset_planner_loader():
    """Reset the global planner loader (for testing)."""
    global _planner_loader
    if _planner_loader:
        _planner_loader.unload()
        _planner_loader = None
