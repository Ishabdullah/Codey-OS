#!/usr/bin/env python3
"""
Daemon core for Codey-OS.

Main daemon process with:
- Unix socket server for CLI communication
- Signal handlers (SIGTERM for graceful shutdown, SIGUSR1 for reload)
- PID file management for single-instance enforcement
- Main event loop for background tasks

The daemon runs continuously in the background, accepting commands
from the CLI client via a Unix domain socket.
"""

import asyncio
import json
import os
import re
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.daemon_config import get_config
from core.state import StateStore, get_state_store
from core.task_executor import TaskExecutor, emit_task_timeout_correction
from utils.config import CODEY_STATE_DIR, DAEMON_LOG_FILE, DAEMON_PID_FILE, DAEMON_SOCKET_FILE
from utils.logger import (error, info, set_log_level, setup_file_logging,
                          warning)

# ==================== Resource-gate slot-release outcomes ====================
# 7.4 sub-task 4 (NEW-69 prerequisite): `release_model_slot` command outcomes.
# String constants (not an enum) to match the existing LOAD_OUTCOME_*
# convention in core/loader_v2.py.
RELEASE_OUTCOME_RELEASED = "released"
RELEASE_OUTCOME_ALREADY_UNLOADED = "already_unloaded"
RELEASE_OUTCOME_BUSY_TASK = "busy_task_running"
RELEASE_OUTCOME_BUSY_SWAP = "busy_swap_in_flight"
RELEASE_OUTCOME_COOLDOWN = "cooldown"
RELEASE_OUTCOME_INVALID_MODEL = "invalid_model_id"
RELEASE_OUTCOME_UNCONFIRMED = "unload_attempted_unconfirmed"
RELEASE_OUTCOME_ERROR = "error"

# Minimum seconds between two successful releases of the SAME model_id via
# this command. Only armed on an actual confirmed release (not on a busy/
# cooldown decline, and not on an "already unloaded" no-op) — a decline
# must not burn a legitimate retry's budget. This is deliberately narrow:
# it prevents THIS command from being used to force rapid repeated
# unload/reload thrashing against the daemon's own model, but it does NOT
# prevent a slower unload -> 30s-watchdog-reload -> ask-again cycle: that
# would need the watchdog itself to back off, which is out of this
# sub-task's scope (daemon-side release command only, not CLI/watchdog
# interaction — see TODO.md 7.4 sub-task 5).
RELEASE_SLOT_COOLDOWN_S = 5.0

# Bounded poll: after unload() returns, how long to wait for the model's
# health port to actually stop answering before reporting the release as
# confirmed. unload() itself already blocks on the subprocess actually
# exiting when this loader owns the process (core/loader_v2.py
# LlamaServer.stop() -> process.wait(timeout=8)), so this is normally
# near-instant; it exists for the "reused, not spawned by this loader"
# edge case where stop() has nothing of its own to wait on. Mirrors the
# load-direction confirm (`confirm_resident_and_mark_slot()`) already
# established in sub-tasks 2/3, using the same `probe_port_health()` a
# planner-eviction confirm used before M1-D (2026-08-23) retired that
# whole path.
RELEASE_CONFIRM_TIMEOUT_S = 3.0
RELEASE_CONFIRM_POLL_INTERVAL_S = 0.3

# 7.4 sub-task C: cadence for `Daemon._cached_read_battery_fn()`'s refresh,
# matching the existing 30s watchdog tick (`_main_loop()`'s `_watchdog_ticks
# >= 60` at a 0.5s per-tick sleep). `get_resource_snapshot()`'s own
# docstring (core/resource_gate.py) warns that its default `read_battery_fn`
# shells out to `termux-battery-status` with a 2s subprocess timeout on
# every call, and that a hot, frequently-ticking caller (this one —
# `_process_planner_tasks()` runs every ~0.5s) must supply a cached/
# rate-limited reader instead. No such cache existed anywhere in this
# codebase at a compatible cadence (core/sysmon.py's SystemMonitor caches on
# its own background thread, but that thread is never started in the
# daemon process and pulls in `rich` at import time — not worth adding for
# this alone), so this is a new, daemon-local cache.
DISPATCH_BATTERY_CACHE_INTERVAL_S = 30.0

# T8a telemetry (docs/telemetry_layer_design.md §2.D): defensive cap on
# `Daemon._deferral_state`'s size (rule 2 — bounds unbounded growth). A
# task can be refused, tracked here, and then never resolved (e.g.
# cancelled before ever being claimed) — without a cap, a daemon that
# runs long enough would leak one dict entry per such abandoned task
# forever. Evicted oldest-first by `first_refused_mono` when full; see
# `Daemon._track_dispatch_refusal()`.
_DEFERRAL_STATE_MAX_ENTRIES = 256

# ==================== Configuration ====================

# Daemon directory — defined at module level so check_pid_file / is_daemon_running
# can use it without triggering a full Daemon init.
DAEMON_DIR = CODEY_STATE_DIR

# Stable path constants with hardcoded defaults.
# These may be overridden when Daemon.__init__ reads the config file.
PID_FILE = DAEMON_PID_FILE
SOCKET_FILE = DAEMON_SOCKET_FILE
LOG_FILE = DAEMON_LOG_FILE


# ==================== PID File Management ====================


def check_pid_file() -> bool:
    """
    Check if daemon is already running.

    Returns True if another daemon is running.
    Removes stale PID file if process is dead.
    """
    import fcntl

    if PID_FILE.exists():
        try:
            with open(PID_FILE, "r") as f:
                fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
                try:
                    pid = int(f.read().strip())
                    if pid == os.getpid():
                        # codeydOS writes this process's own PID into the
                        # file before Python starts, to close the H-4
                        # daemon-start race. Finding our own PID here is
                        # therefore expected on every startup — it is not
                        # evidence of a second instance.
                        return False
                    os.kill(pid, 0)
                    return True
                except (ProcessLookupError, ValueError):
                    warning("Removing stale PID file")
                    PID_FILE.unlink(missing_ok=True)
                    return False
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except (IOError, OSError):
            return True
    return False


def write_pid_file():
    """Write current PID to PID file with file locking."""
    import fcntl

    with open(PID_FILE, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            f.write(str(os.getpid()))
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def remove_pid_file():
    """Remove PID file on shutdown."""
    PID_FILE.unlink(missing_ok=True)


# ==================== Unix Socket Server ====================


class DaemonServer:
    """
    Unix socket server for CLI communication.

    Handles incoming commands from CLI clients and routes them
    to appropriate handlers.
    """

    def __init__(self, state: StateStore):
        self.state = state
        self.server: Optional[asyncio.Server] = None
        self.running = False
        self._handlers: Dict[str, Callable] = {}
        # Per-model_id monotonic timestamp of the last CONFIRMED release via
        # release_model_slot — see RELEASE_SLOT_COOLDOWN_S above.
        self._release_slot_last_release: Dict[str, float] = {}
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register default command handlers."""
        self.register_handler("ping", self._handle_ping)
        self.register_handler("command", self._handle_command)
        self.register_handler("status", self._handle_status)
        self.register_handler("health", self._handle_health)
        self.register_handler("task", self._handle_task)
        self.register_handler("cancel", self._handle_cancel)
        self.register_handler("release_model_slot", self._handle_release_model_slot)

    def register_handler(self, cmd: str, handler: Callable):
        """Register a command handler."""
        self._handlers[cmd] = handler

    async def _handle_ping(self, data: Dict) -> Dict:
        """Handle ping command."""
        return {"status": "ok", "message": "pong"}

    async def _handle_command(self, data: Dict) -> Dict:
        """Handle a user command (prompt).

        Two distinct contracts, selected by `plan_only` (7.4 sub-task C,
        NEW-112): repo-wide search found exactly one live caller of this
        handler — `core/planner_service.py`'s `_request_daemon_plan()`,
        always sending `plan_only: True` — a synchronous planning-oracle RPC
        used by the interactive CLI to get plan text back for local,
        step-by-step `run_agent()` execution. That path's behavior below is
        UNCHANGED from before this sub-task, and is deliberately exempt from
        the daemon's interactive-session dispatch gate: the caller of this
        RPC *is* the interactive session asking on its own behalf, not the
        daemon doing background work while a user is looking away.

        `plan_only` falsy is the real, currently-unused-in-production
        "submit a new prompt for the daemon to execute" entry point (per
        `daemon_control.py`'s own docstring) — this now just enqueues the
        raw prompt and returns immediately; planning (if any) happens later
        on the pull side, in `_process_planner_tasks()`, gated by
        `can_dispatch_task()` like any other dispatch.
        """
        prompt = data.get("prompt", "")
        if not prompt:
            return {"status": "error", "message": "No prompt provided"}

        # Log to episodic log
        self.state.log_action("command_received", prompt[:200])

        if not data.get("plan_only", False):
            # Real "submit a new prompt for the daemon to execute" path —
            # no live caller today (NEW-112), but real intended-future
            # functionality. No synchronous planning here: this returns
            # immediately, and needs_planning=1 tells the pull side
            # (_process_planner_tasks()) to plan this row before dispatch.
            # `no_plan` (same flag the old code checked before this sub-task)
            # is still honored here — it means "do not plan this at all,"
            # not just "don't plan it synchronously at enqueue time," so a
            # caller that explicitly asked to skip planning must not have
            # needs_planning set for it on the pull side either.
            needs_planning = 0 if data.get("no_plan", False) else 1
            task_id = self.state.add_task(prompt, needs_planning=needs_planning)
            return {"status": "ok", "message": "Task queued", "task_id": task_id}

        # ── plan_only=True: synchronous planning-oracle RPC (unchanged) ──────
        no_plan = data.get("no_plan", False)
        if not no_plan:
            try:
                from core.plannd import PLANNER_PROMPT, compute_outer_plan_timeout
                from core.planner_client import send_plan_request_async
                from core.tokens import estimate_tokens
                from utils.config import (PLANNER_MAX_TOKENS,
                                          PLANNER_MAX_TOKENS_MEDIUM)

                # 7.3 sub-task E Task B (2026-08-24): additive field —
                # missing on an old client's payload defaults safely to
                # today's hard-tier behavior.
                tier = data.get("tier", "hard")
                enable_thinking = tier != "medium"
                max_tokens_for_this_request = (
                    PLANNER_MAX_TOKENS_MEDIUM if tier == "medium" else PLANNER_MAX_TOKENS
                )

                # NEW-165 fix 3: derive the outer wait_for timeout from the
                # same formula plannd.py uses for its own inner urlopen
                # timeout (plus a small buffer), instead of a second
                # hardcoded guess. Otherwise raising plannd's inner
                # timeout (formula-based, can exceed 180s) just relocates
                # NEW-165 one layer up, and worse — cancellation here
                # carries none of plannd's new diagnostic logging.
                #
                # 7.3 sub-task E Task B: sized against
                # max_tokens_for_this_request (the tier actually in play for
                # THIS request), not a flat PLANNER_MAX_TOKENS — this is the
                # daemon's own internal per-request timeout, which DOES
                # scale per-tier (unlike core/planner_service.py's outer
                # client-side socket timeout, which stays pinned to the
                # hard-tier worst case regardless of tier — see that
                # module's comment for why those two must not match).
                # §8 Q11 (2026-08-26): compute_outer_plan_timeout() adds a
                # buffer for get_plan()'s own new context-budget queue wait
                # on top of compute_planner_timeout()'s inner-urlopen sizing
                # — see that function's own docstring.
                prompt_tokens_estimate = estimate_tokens(PLANNER_PROMPT) + estimate_tokens(prompt)
                outer_timeout = compute_outer_plan_timeout(prompt_tokens_estimate, max_tokens_for_this_request)

                steps = await asyncio.wait_for(
                    send_plan_request_async(prompt, enable_thinking=enable_thinking),
                    timeout=outer_timeout,
                )
                if steps and len(steps) > 1:
                    info(f"plannd: returned {len(steps)}-step plan (plan_only)")
                    return {
                        "status": "ok",
                        "message": f"Plan created: {len(steps)} steps",
                        "task_ids": [],
                        "plan": steps,
                    }
                # plannd returned ≤1 step — fall through to single-task path
                if steps:
                    info("plannd returned only 1 step — using single-task path")
            except asyncio.TimeoutError:
                warning(f"plannd request timed out after {outer_timeout:.0f}s — falling back to direct task")
            except ConnectionRefusedError:
                # plannd not running — silent fallback
                pass
            except Exception as _e:
                warning(f"plannd unavailable ({_e}) — falling back to direct task")

        # ── Fallback: single direct task (existing behaviour) ────────────────
        task_id = self.state.add_task(prompt)
        return {
            "status": "ok",
            "message": f"Task queued with ID {task_id}",
            "task_id": task_id,
        }

    async def _handle_status(self, data: Dict) -> Dict:
        """Handle status query."""
        pending = len(self.state.get_tasks_by_status("pending"))
        running_tasks = self.state.get_tasks_by_status("running")
        running = len(running_tasks)
        done = len(self.state.get_tasks_by_status("done"))

        # ── NEW-145/NEW-149/NEW-155 chain, Option C (2026-08-27) ────────────
        # `running_active` is `running` age-filtered against the
        # `task_timeout` config value (default 1800s). Note this is NOT
        # the same threshold as `_handle_health()`'s own stuck-task
        # detection below (`:370`), which hardcodes a literal `1800`
        # rather than reading `task_timeout` from config — a known
        # inconsistency, tracked separately as NEW-256 and out of scope
        # here. This code path reads the config value correctly; a task
        # row stuck in 'running' by a daemon that died ungracefully
        # mid-task (NEW-146's orphan-state shape applied to task rows)
        # must not read as "busy" forever to a caller like
        # `daemon_task_in_progress()` below. A task with no `started_at`
        # (shouldn't happen for a genuinely-running row, but not asserted
        # here) is conservatively counted as active rather than stale, so
        # ambiguity resolves toward "busy," matching this whole chain's
        # fail-closed posture.
        #
        # Uses the module-level get_config() singleton (imported at the top
        # of this file), not `self._config` -- `DaemonServer.__init__`
        # never sets that attribute (only `Daemon.__init__`, a different
        # class, does). The original version of this fix referenced
        # `self._config` here, which would have raised AttributeError on
        # every real invocation; every existing unit test masked this by
        # manually stubbing `handler._config` onto the test double,
        # bypassing real construction entirely. Found via live-verification
        # attempt, 2026-08-27 -- see NEW-259.
        task_timeout = get_config().get("tasks", "task_timeout", default=1800)
        now = int(time.time())
        running_active = len(
            [
                t
                for t in running_tasks
                if not t.get("started_at") or (now - t["started_at"]) <= task_timeout
            ]
        )

        return {
            "status": "ok",
            "daemon": "running",
            "pid": os.getpid(),
            "tasks": {
                "pending": pending,
                "running": running,
                "running_active": running_active,
                "done": done,
            },
            "state": self.state.get_all(),
        }

    async def _handle_health(self, data: Dict) -> Dict:
        """Handle health check query."""
        import resource

        # Get process memory usage
        try:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            memory_mb = usage.ru_maxrss / 1024  # Convert to MB (on Linux)
        except (ValueError, ZeroDivisionError, OSError):
            memory_mb = 0

        # Get task stats
        all_tasks = self.state.get_all_tasks()
        pending_count = len([t for t in all_tasks if t["status"] == "pending"])
        stuck_tasks = []
        now = int(time.time())
        # NEW-256: read the same `task_timeout` config key `_handle_status()`'s
        # `running_active` filter reads (module-level get_config() singleton,
        # not self._config — see that call site's comment), instead of the
        # hardcoded literal 1800 this used to diverge to whenever task_timeout
        # was ever configured away from its default.
        task_timeout = get_config().get("tasks", "task_timeout", default=1800)
        for t in all_tasks:
            if t["status"] == "running" and t.get("started_at"):
                running_time = now - t["started_at"]
                if running_time > task_timeout:
                    stuck_tasks.append(t["id"])

        # Get recent actions count
        recent_actions = len(self.state.get_recent_actions(100))

        # Get uptime
        started_at = self.state.get("daemon_started_at", 0)
        uptime_seconds = int(time.time()) - int(started_at) if started_at else 0

        return {
            "status": "ok",
            "healthy": True,
            "pid": os.getpid(),
            "uptime_seconds": uptime_seconds,
            "memory_mb": round(memory_mb, 1),
            "tasks": {"pending": pending_count, "stuck": stuck_tasks},
            "recent_actions": recent_actions,
        }

    async def _handle_task(self, data: Dict) -> Dict:
        """Handle task query (get task by ID or list all)."""
        task_id = data.get("id")

        if task_id is not None:
            # Get specific task
            task = self.state.get_task(task_id)
            if not task:
                return {"status": "error", "message": f"Task {task_id} not found"}
            return {"status": "ok", "task": task}
        else:
            # List all tasks
            limit = data.get("limit", 20)
            tasks = self.state.get_all_tasks()[:limit]
            return {"status": "ok", "tasks": tasks}

    async def _handle_cancel(self, data: Dict) -> Dict:
        """Handle task cancellation."""
        task_id = data.get("id")
        if not task_id:
            return {"status": "error", "message": "Task ID required"}

        cancelled = self.state.cancel_task(task_id)
        if cancelled:
            self.state.log_action("task_cancelled", f"Task {task_id}")
            return {"status": "ok", "message": f"Task {task_id} cancelled"}
        else:
            task = self.state.get_task(task_id)
            if task:
                return {"status": "error", "message": f"Task {task_id} already {task['status']}"}
            return {"status": "error", "message": f"Task {task_id} not found"}

    @staticmethod
    def _release_model_slot_sync(loader, port: int):
        """
        Blocking body of a release attempt — run via `run_in_executor` since
        `unload()` can block on `process.wait(timeout=8)` (core/loader_v2.py
        `LlamaServer.stop()`), and must never stall the daemon's asyncio
        event loop (same reasoning as `_execute_task()`'s use of
        `run_in_executor` for `run_agent()`).

        Returns (did_unload: bool, confirmed_freed: bool). `did_unload` is
        False only when the model was already not loaded (clean no-op).
        `confirmed_freed` is True once the model's health port stops
        answering, polled for up to RELEASE_CONFIRM_TIMEOUT_S — unload()
        itself already blocks on process exit when this loader owns the
        spawned process, so this is normally immediate; it exists for the
        edge case where the loader's `_server` was a reused reference to a
        process this loader didn't spawn (nothing for `stop()` to wait on
        there).
        """
        if not loader.is_loaded():
            return False, True

        loader.unload()

        from core.loader_v2 import probe_port_health

        deadline = time.monotonic() + RELEASE_CONFIRM_TIMEOUT_S
        while True:
            if not probe_port_health(port):
                return True, True
            if time.monotonic() >= deadline:
                return True, False
            time.sleep(RELEASE_CONFIRM_POLL_INTERVAL_S)

    async def _handle_release_model_slot(self, data: Dict) -> Dict:
        """
        Release (unload) a model this DAEMON's own loader holds a
        resource-gate slot for, on request from an external caller.

        Built for NEW-69 / TODO.md 7.4 sub-task 4: interactive CLI
        (`main.py`) invocations will (sub-task 5, separate/later) be able to
        ask the running daemon to free a slot so the CLI's own reservation
        can be admitted, instead of being denied with no way to recover.

        Request: {"model_id": "primary"}
        Response (all well-formed requests return status "ok"; only an
        invalid model_id or an unexpected exception during unload returns
        "error"):
            {"status": "ok"|"error", "released": bool,
             "outcome": <RELEASE_OUTCOME_* constant>, "message": str}

        Busy handling (deliberately conservative — this command exists so a
        different, unprivileged, potentially adversarial-by-accident
        process can ask the daemon to give up a resource it may be using
        mid-inference):
          - If a task is actively executing right now (`ThermalManager`'s
            `is_inference_active()` — the same in-flight bracket
            `core/task_executor.py`'s `_execute_task()` already sets around
            every `run_agent()` call; process-local, so unlike the SQLite
            task `running` status it can never stay stuck if the daemon
            dies mid-task), the request is declined as busy. Releasing a
            model out from under an in-flight task would corrupt that
            task's response, not just be wasteful.
          - If `core.loader_v2.SWAP_GUARD` can't be acquired non-blocking,
            another loaded/not-loaded transition (e.g. a concurrent
            watchdog `ensure_model()` restart) is already in flight
            elsewhere in this process — declined as busy rather than
            racing it. The guard is then HELD across the unload (not
            probed-and-dropped), for the same reason `ensure_model()` holds
            it for its entire body: the loaded/not-loaded transition window
            is exactly the race the guard exists to prevent.
          - Already-not-loaded is a clean success no-op (`released: False`,
            `outcome: already_unloaded`), not an error — the caller's goal
            (a free slot) is already satisfied.
          - A confirmed release only counts toward the per-model_id cooldown
            (RELEASE_SLOT_COOLDOWN_S) — a busy/cooldown decline never arms
            the cooldown itself, so a legitimate retry right after a decline
            clears isn't punished for the decline.

        M1-D (2026-08-23): `model_id == "planner"` used to also be accepted
        here, releasing this daemon process's own (usually-irrelevant, per
        this handler's pre-M1-D docstring) in-process `PlannerLoader`
        singleton — `plannd`, the actual separate OS process holding the
        real planner slot, was never reachable through this handler at all.
        With `core/planner_loader.py` deleted and planning collapsed onto
        the primary server, `"planner"` is no longer a meaningful value
        here; only `"primary"` is accepted now, and this handler's only
        live caller (`main.py`'s `_load_primary_with_gate_recovery()`) has
        only ever sent `"primary"` — see `ccos/plugins/system/daemon_control/
        daemon_control.py`'s own note on this handler's sole live caller.
        """
        model_id = data.get("model_id")
        if model_id != "primary":
            return {
                "status": "error",
                "released": False,
                "outcome": RELEASE_OUTCOME_INVALID_MODEL,
                "message": f"model_id must be 'primary', got {model_id!r}",
            }

        now = time.monotonic()
        last_release = self._release_slot_last_release.get(model_id)
        if last_release is not None and (now - last_release) < RELEASE_SLOT_COOLDOWN_S:
            remaining = RELEASE_SLOT_COOLDOWN_S - (now - last_release)
            return {
                "status": "ok",
                "released": False,
                "outcome": RELEASE_OUTCOME_COOLDOWN,
                "message": f"released {model_id!r} too recently — retry in {remaining:.1f}s",
            }

        try:
            from core.thermal import get_thermal_manager

            if get_thermal_manager().is_inference_active():
                return {
                    "status": "ok",
                    "released": False,
                    "outcome": RELEASE_OUTCOME_BUSY_TASK,
                    "message": "a task is actively executing — declined to avoid "
                    "releasing a model out from under in-flight inference",
                }
        except Exception as e:
            # Fail closed: if we can't confirm the daemon is idle, treat it
            # as busy rather than risk releasing a model mid-inference.
            warning(f"release_model_slot: thermal busy-check failed ({e}) — declining as busy")
            return {
                "status": "ok",
                "released": False,
                "outcome": RELEASE_OUTCOME_BUSY_TASK,
                "message": "could not confirm daemon idle state — declined",
            }

        from core.loader_v2 import SWAP_GUARD, get_loader
        from utils.config import PRIMARY_SERVER_PORT

        if not SWAP_GUARD.acquire(blocking=False):
            return {
                "status": "ok",
                "released": False,
                "outcome": RELEASE_OUTCOME_BUSY_SWAP,
                "message": "a primary load/restart is already in flight — declined",
            }

        try:
            loader = get_loader()
            port = PRIMARY_SERVER_PORT

            loop = asyncio.get_event_loop()
            try:
                did_unload, confirmed = await loop.run_in_executor(
                    None, self._release_model_slot_sync, loader, port
                )
            except Exception as e:
                error(f"release_model_slot: unload of {model_id!r} raised: {e}")
                return {
                    "status": "error",
                    "released": False,
                    "outcome": RELEASE_OUTCOME_ERROR,
                    "message": str(e),
                }
        finally:
            SWAP_GUARD.release()

        if not did_unload:
            return {
                "status": "ok",
                "released": False,
                "outcome": RELEASE_OUTCOME_ALREADY_UNLOADED,
                "message": f"{model_id!r} was not loaded — nothing to release",
            }

        if confirmed:
            self._release_slot_last_release[model_id] = time.monotonic()
            info(f"release_model_slot: released {model_id!r} on external request")
            return {
                "status": "ok",
                "released": True,
                "outcome": RELEASE_OUTCOME_RELEASED,
                "message": f"{model_id!r} released and confirmed freed",
            }

        warning(
            f"release_model_slot: unload of {model_id!r} issued but not confirmed "
            f"freed within {RELEASE_CONFIRM_TIMEOUT_S}s"
        )
        return {
            "status": "ok",
            "released": False,
            "outcome": RELEASE_OUTCOME_UNCONFIRMED,
            "message": f"unload of {model_id!r} issued but not confirmed freed in time",
        }

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming client connection with peer credential verification."""
        try:
            # Verify peer credentials (same user only)
            peer_pid = writer.get_extra_info("peer_pid")
            peer_uid = writer.get_extra_info("peer_uid")
            if peer_uid is not None and peer_uid != os.getuid():
                error(f"Rejected connection from different UID: {peer_uid}")
                writer.write(
                    json.dumps({"status": "error", "message": "Unauthorized"}).encode("utf-8")
                )
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            # Read request (JSON message)
            data = await reader.read(65536)
            if not data:
                return

            request = json.loads(data.decode("utf-8"))
            cmd = request.get("cmd", "unknown")

            info(f"Received command: {cmd}")

            # Route to handler
            handler = self._handlers.get(cmd)
            if handler:
                response = await handler(request.get("data", {}))
            else:
                response = {"status": "error", "message": f"Unknown command: {cmd}"}

            # Send response
            writer.write(json.dumps(response).encode("utf-8"))
            await writer.drain()

        except json.JSONDecodeError as e:
            error(f"Invalid JSON from client: {e}")
            writer.write(json.dumps({"status": "error", "message": "Invalid JSON"}).encode("utf-8"))
            await writer.drain()
        except Exception as e:
            error(f"Error handling client: {e}")
            try:
                writer.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
                await writer.drain()
            except (ConnectionError, OSError):
                pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def start(self):
        """Start the socket server."""
        # Remove old socket file if exists
        SOCKET_FILE.unlink(missing_ok=True)

        self.server = await asyncio.start_unix_server(self._handle_client, path=str(SOCKET_FILE))

        # Set socket permissions (user only)
        os.chmod(SOCKET_FILE, 0o600)

        self.running = True
        info(f"Daemon listening on {SOCKET_FILE}")

        async with self.server:
            await self.server.serve_forever()

    async def stop(self):
        """Stop the socket server."""
        self.running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        SOCKET_FILE.unlink(missing_ok=True)
        info("Daemon socket stopped")


# ==================== T8a telemetry — module-level provenance helpers ======
# Category-G (docs/telemetry_layer_design.md §2.G) + meta counter_reset/
# writer_stopped. Module-level (not Daemon methods) mirroring main.py's
# T2 `_record_tui_telemetry_run_start()` exactly — no `self` state is
# needed, and the daemon's own single call site passes nothing instance-
# specific in.


def _record_daemon_telemetry_run_start():
    """
    Category-G run provenance (docs/telemetry_layer_design.md §2.G) plus
    the `counter_reset` meta event (§2.C's "emitted at run start listing
    every counter that reset with this process"). Emitted once, at the
    very start of `_main_loop()`, before the socket server task is
    created — mirrors main.py's `_record_tui_telemetry_run_start()` (T2,
    commit a53db3d) exactly: local imports, one broad `except Exception`,
    never allowed to block the daemon's main loop from starting.

    `counter_reset` is emitted here via `record_meta_event()`, NOT
    `record_device_sample()` — despite §2.C's prose placing it under the
    device category, `telemetry/schema/v1.json`'s `device` category has
    no `counters_reset` body field; only `meta` does (meta.event_types
    includes `counter_reset`, and `meta.body_fields` has `counters_reset`
    + `reason`). Verified against the schema file directly, not assumed
    from the design doc's prose.
    """
    try:
        from telemetry import provenance, recorders
        from utils.config import (CODEY_DIR, EMBED_MODEL_PATH,
                                  LLAMA_SERVER_BIN, MODEL_PATH)

        models = provenance.build_model_entries(
            [("primary", MODEL_PATH), ("embed", EMBED_MODEL_PATH)]
        )
        recorders.record_run_start(
            emitter="codey-os.daemon",
            pid=os.getpid(),
            repo="Codey-OS",
            started_ts_wall=time.time(),
            repo_dir=CODEY_DIR,
            models=models,
            llama_server_bin=LLAMA_SERVER_BIN,
        )
        recorders.record_meta_event(
            event_type="counter_reset",
            emitter="codey-os.daemon",
            pid=os.getpid(),
            counters_reset=[
                "thermal.total_inference_sec",
                "telemetry.seq",
                "telemetry.dropped_count",
            ],
            reason="daemon process (re)start",
        )
    except Exception:
        warning("telemetry: failed to record run_start/counter_reset for daemon")


def _record_daemon_telemetry_writer_stopped():
    """
    Meta `writer_stopped` event (docs/telemetry_layer_design.md — see
    `telemetry/cli.py`'s existing `no_clean_shutdown` check, which already
    anticipates this record arriving from a future daemon-shutdown sub-
    task). Emitted as the LAST statement of `_main_loop()`'s `finally:`
    block — after every other shutdown step has already run — same
    never-block-shutdown contract as every other telemetry call site in
    this file: local imports, broad `except Exception`, logged not
    raised.
    """
    try:
        from telemetry import recorders

        recorders.record_meta_event(
            event_type="writer_stopped",
            emitter="codey-os.daemon",
            pid=os.getpid(),
            reason="daemon shutdown",
        )
    except Exception:
        warning("telemetry: failed to record writer_stopped for daemon")


# ==================== Daemon Core ====================


# NEW-351 fix: masks embedded live-formatted numbers (RAM MiB, °C, %, sample
# counts, seconds) out of a gate/trip `reason` string before it is hashed
# into _emit_gate_telemetry_deduped()'s dedup key. can_dispatch_task()'s/
# should_trip_shutdown()'s reason strings (core/resource_gate.py) are
# f-strings with :.0f/:.1f/:.0% formatted values baked in -- under sustained
# pressure, near-every evaluation produces a slightly different number,
# defeating dedup exactly when the 60s-suppression window matters most
# (NEW-351). Masking only touches the KEY: the caller still passes the full,
# unmasked decision.reason into record_gate_decision()'s `reason=` kwarg, so
# the emitted record body always carries the real numbers.
#
# \d+(?:\.\d+)? (not [-+]?\d+\.?\d*) deliberately: none of these templates'
# :.0f/:.1f/:.0% formatting ever emits a negative number or a thousands
# separator, and a leading sign class would corrupt adjacent non-numeric
# text (e.g. "NEW-108" -> "NEWN"), which is confusing on inspection even
# though it wouldn't break determinism.
_GATE_REASON_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _normalize_gate_reason_for_dedup(reason: str) -> str:
    """Mask embedded numeric values out of a gate/trip decision's `reason`
    string for dedup-key purposes only (NEW-351) -- see
    _GATE_REASON_NUMBER_RE's comment for why regex-masking was chosen over
    a hand-maintained reason-category enum. Two reason strings differing
    only in their embedded numbers (e.g. two different RAM-headroom MiB
    readings against the same static wording) normalize to the same
    string; two reason strings with different wording -- even if
    structurally similar, e.g. the "leg not satisfied" vs "leg satisfied"
    trailing-run templates in resource_gate.py -- remain distinct.

    Accepted limitation: this masks threshold changes too, not just
    measured-value changes (e.g. DISPATCH_MIN_HEADROOM_BYTES, temp_critical,
    duration_sec are embedded in the same strings and some are
    env-overridable/re-read per call). If a threshold changes mid-run, the
    dedup key alone won't register it as a state change until the next
    natural key-changing event -- but the real new-threshold number still
    reaches the record body within <=60s via the next heartbeat emission
    regardless, since record_gate_decision() is always called with the
    unmasked decision.reason. Not treated as a bug to fix.
    """
    return _GATE_REASON_NUMBER_RE.sub("N", reason)


class Daemon:
    """
    Main daemon class.

    Manages the event loop, signal handlers, and socket server.
    """

    def __init__(self):
        global PID_FILE, SOCKET_FILE, LOG_FILE

        # Load config and apply logging — done here, not at module level,
        # so importing core.daemon for CLI helpers doesn't trigger side effects.
        self._config = get_config()
        DAEMON_DIR.mkdir(parents=True, exist_ok=True)

        log_level = self._config.get("daemon", "log_level", default="INFO")
        set_log_level(log_level)

        log_file_path = self._config.get("daemon", "log_file", default=str(LOG_FILE))
        setup_file_logging(log_file_path)

        # Override path constants from config so all other functions see them.
        PID_FILE = Path(
            self._config.get("daemon", "pid_file", default=str(DAEMON_PID_FILE))
        )
        SOCKET_FILE = Path(
            self._config.get("daemon", "socket_file", default=str(DAEMON_SOCKET_FILE))
        )
        LOG_FILE = Path(log_file_path)

        self.state = get_state_store()
        self.server = DaemonServer(self.state)
        self.executor = TaskExecutor(self.state, self._config)
        from core.planner_v2 import get_planner

        self.planner = get_planner()
        from core.background import (get_background_manager,
                                     get_file_watch_manager)

        self.background = get_background_manager()
        self.file_watch = get_file_watch_manager()
        self.running = True
        self._reload_requested = False

        # 7.4 sub-task C: cache for _cached_read_battery_fn() — see
        # DISPATCH_BATTERY_CACHE_INTERVAL_S's comment above.
        self._dispatch_battery_cache_ts = 0.0
        self._dispatch_battery_cache_value = (None, False)

        # T8a telemetry state (docs/telemetry_layer_design.md §2.B/§2.D).
        # Category-B gate-decision dedup: per call_site, the last emitted
        # dedup key + when that key was first seen + how many evaluations
        # have collapsed into it since — see _emit_gate_telemetry_deduped().
        self._gate_dedup: Dict[str, Dict[str, Any]] = {}
        # Category-D co-tenancy: last-observed interactive-session state
        # and when that state began, so a transition's `state_duration_ms`
        # can be computed — see _observe_interactive_state(). None means
        # "not yet observed" (the first observation only seeds this, it
        # never emits — there is no "previous" state to compare against).
        self._interactive_active_last: Optional[bool] = None
        self._interactive_state_since_mono: float = time.monotonic()
        # Category-D deferral tracking: task_id -> {first_refused_mono,
        # refusal_count}, for tasks refused at least once while the gate
        # was consulted. Bounded by _DEFERRAL_STATE_MAX_ENTRIES — see that
        # constant's comment. See _track_dispatch_refusal() /
        # _resolve_deferral_if_any().
        self._deferral_state: Dict[int, Dict[str, float]] = {}

        # Register signal handlers
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGUSR1, self._handle_sigusr1)

        # Wire ProjectMemory: load CODEY.md and config.json at boot (never evicted)
        try:

            from core.codeymd import find_codeymd, read_codeymd
            from core.memory_v2 import memory as _mem

            # Load CODEY.md if it exists
            _codeymd_path = find_codeymd()
            if _codeymd_path:
                _codeymd_content = read_codeymd()
                if _codeymd_content and not _codeymd_content.startswith("[ERROR]"):
                    _mem.add_to_project(_codeymd_path, _codeymd_content, is_protected=True)
                    info(f"ProjectMemory: loaded {_codeymd_path}")

            # Load config.json if it exists
            from utils.config import DAEMON_CONFIG_FILE as _config_path
            if _config_path.exists():
                _config_content = _config_path.read_text(encoding="utf-8", errors="replace")
                _mem.add_to_project(str(_config_path), _config_content, is_protected=True)
                info(f"ProjectMemory: loaded {_config_path}")
        except Exception as _e:
            warning(f"ProjectMemory initialization skipped: {_e}")

    def _trigger_shutdown(self):
        """
        Trigger a graceful daemon exit. Sole live caller (as of 7.4 sub-task
        D): `_main_loop()`'s watchdog tick, when `should_trip_shutdown()`
        decides a sustained-severe-thermal (and, on hardware where CPU is
        genuinely measurable, CPU) condition warrants an autonomous shutdown.
        There is no socket-triggerable path to this anymore — the
        `shutdown` command handler and the module-level `daemon_shutdown()`
        helper that used to route here were retired in the same sub-task
        (confirmed zero live callers repo-wide beforehand); a client that
        still sends `{"cmd": "shutdown"}` now gets the dispatcher's existing
        generic "Unknown command" response instead.

        Setting `self.running = False` and closing the socket server here is
        what lets `_main_loop()`'s `while self.running:` loop exit on its own
        next iteration and fall into its `finally:` block, which is what
        actually calls `get_loader().unload()` to stop the detached
        `llama-server` process — this function must never be bypassed with a
        raw `sys.exit()`/`os._exit()`, or that unload never runs.
        """
        info("Daemon shutdown triggered")
        self.running = False
        if self.server.server:
            self.server.server.close()

    def _handle_sigterm(self, signum, frame):
        """Handle SIGTERM (graceful shutdown)."""
        info("SIGTERM received, shutting down...")
        self.running = False

    def _handle_sigusr1(self, signum, frame):
        """Handle SIGUSR1 (reload configuration)."""
        info("SIGUSR1 received, reload requested")
        self._reload_requested = True

    def _watchdog_check_model(self):
        """
        30s watchdog for the 7B primary model server — extracted out of
        `_main_loop()` (Track 3 Phase 5a / 7.4 sub-task 3) so the gate-denial
        vs. crash distinction below is independently testable, and so this
        block reads as one named unit instead of being buried inline in the
        90-line async main loop.

        `ensure_model()` is gate-aware (7.4 sub-tasks 2/3): a `False` return
        here can mean several distinct things, and treating them all as "the
        process died, log a restart" is wrong for at least the gate-denial
        cases — a denial isn't a crash, and a hard denial will never resolve
        by retrying. See `core/loader_v2.py`'s `LOAD_OUTCOME_*` constants.
        """
        try:
            from core.loader_v2 import (LOAD_OUTCOME_DEFERRED,
                                         LOAD_OUTCOME_GATE_DENIED,
                                         LOAD_OUTCOME_GATE_DENIED_HARD,
                                         get_loader)

            loader = get_loader()
            server = loader.get_model_instance()
            was_running = bool(server and server.is_running())

            if not was_running and not loader.was_ever_spawned():
                # NEW-152 (code-reviewer retroactive pass on the 7.4b
                # sub-task C / NEW-145 fix, 2026-08-13): this used to gate
                # on `was_ever_loaded()`, which was sticky-True after
                # EITHER a genuine spawn OR the port-in-use adoption
                # branch. Under the normal `codey-start` steady state (TUI
                # spawns the coder; the daemon's own loader later adopts
                # it via its first background dispatch), that flag went
                # True on the very first adoption and never came back down
                # — so every later tick where the coder wasn't running
                # (including the ordinary case of the TUI session simply
                # ending, not crashing) fell through to `ensure_model()`
                # below and respawned the coder at the smaller 16384
                # background ceiling. A TUI reattaching afterward reused
                # that under-provisioned server via `LlamaServer.start()`'s
                # reuse branch — reproducing NEW-145's original symptom
                # through adoption instead of through the deleted eager
                # preload.
                #
                # `was_ever_spawned()` narrows this to "this loader itself
                # spawned a coder subprocess at least once" — adoption no
                # longer counts. Crash-restart coverage for coder loads
                # this daemon genuinely spawned (background-dispatched
                # loads) is unconditional and unchanged; a coder this
                # loader has only ever ADOPTED (or never loaded at all) is
                # left alone here until a real request comes in, matching
                # Ish's decision 3 ("loads lazily on first real request")
                # instead of being eagerly restarted just because it
                # existed once. See `was_ever_spawned()`'s own docstring
                # for the full case-by-case breakdown, including the
                # deliberate reduction in crash-restart coverage for
                # adopted-only coders this accepts.
                return

            if loader.ensure_model():
                return  # loaded/still running/restarted cleanly — nothing to report

            outcome = loader.get_last_ensure_outcome()
            reason = loader.get_last_ensure_reason()

            if outcome == LOAD_OUTCOME_GATE_DENIED_HARD:
                # Not a crash, and retrying every 30s forever cannot help —
                # this model alone exceeds the device ceiling. Still retried
                # (no gate-side "give up" state to persist against, and this
                # sub-task's scope doesn't extend to adding one), but logged
                # accurately instead of as a restart.
                warning(f"7B model: resource gate permanently denies this load — {reason}")
            elif outcome == LOAD_OUTCOME_GATE_DENIED:
                # Transient — headroom/thermal. Not a crash; will keep
                # retrying on subsequent ticks as conditions change.
                warning(f"7B model load denied by resource gate (transient) — {reason}")
            elif outcome == LOAD_OUTCOME_DEFERRED:
                # SWAP_GUARD busy (a concurrent release_model_slot request,
                # or — before M1-D, 2026-08-23 — a planner mid-swap) —
                # expected, benign, self-resolves on the next tick. Not
                # worth a warning.
                info(f"7B model watchdog: {reason}")
            elif was_running is False and server is None:
                # Reachable only because `was_ever_spawned()` (NEW-152)
                # gated us into calling `ensure_model()` at all (7.4b
                # sub-task C's NEW-145 fix removed the daemon's startup
                # preload, so there is no longer a preload-failure path
                # here) — this loader genuinely spawned a server at least
                # once before, but `unload()` cleared the instance and
                # this reload attempt also failed. "died" would
                # misdescribe this: there's no currently-known process
                # that stopped running.
                warning(f"7B model not loaded ({outcome}: {reason}) — attempted load, still not running")
            else:
                # The process really was running and now isn't — this is the
                # "died, restarting" case the original message described.
                warning(f"7B model server died ({outcome}: {reason}) — restart attempt failed")
        except Exception as e:
            # Watchdog itself must never crash the daemon's main loop — but
            # unlike a truly best-effort signal read, a swallowed exception
            # here would silently stop the 7B model from ever being retried
            # again with no trace, so this is logged (not a bare `pass`)
            # before being swallowed.
            warning(f"7B model watchdog check failed: {e}")

    async def _main_loop(self):
        """Main daemon event loop."""
        info("Daemon started")
        self.state.set("daemon_started_at", int(time.time()))
        self.state.log_action("daemon_started", f"PID {os.getpid()}")

        # T8a telemetry: category-G run provenance + counter_reset meta
        # event, once per daemon process start. Deliberately synchronous
        # and placed before the server task is created (mirrors main.py's
        # T2 `_record_tui_telemetry_run_start()` placement at the very
        # start of the TUI session it instruments) — see that function's
        # own docstring for the full never-block contract.
        _record_daemon_telemetry_run_start()

        # Start socket server
        server_task = asyncio.create_task(self.server.start())

        # NOTE: We do NOT start executor.start() as a background task.
        # The executor's auto-poll loop and _process_planner_tasks both poll the
        # same SQLite task_queue, creating a race where the same task could be
        # claimed and executed twice.  All task dispatch goes through
        # _process_planner_tasks, which uses try_claim_task() for atomic claiming.

        # 7.4b sub-task C's NEW-145 fix: the daemon no longer eagerly
        # pre-loads the 7B coder model at startup. Eager preload always ran
        # before any TUI session could register itself as interactive (see
        # `core/resource_gate.py`'s `is_interactive_session_active()`), so
        # it always evaluated False and spawned the coder at the background
        # 16384 ceiling — the interactive TUI then reused that same
        # under-provisioned server via `LlamaServer.start()`'s port-in-use
        # reuse branch instead of getting its own 32768 one (NEW-145). The
        # coder now loads lazily on first real request — interactive or
        # background — so the interactive-session signal is evaluated at
        # actual spawn time. Accepted tradeoff: the first real coder
        # request after daemon start pays full model-load latency instead
        # of finding an already-warm model.
        from utils.config import CODEY_BACKEND as _backend
        from utils.config import is_remote_backend as _is_remote

        if not _is_remote():
            info("Coder (7B) will load lazily on first request — no startup preload")
        else:
            info(f"Backend: {_backend} — skipping local model server startup")

        # Start dedicated embedding server (nomic-embed on port 8082)
        try:
            from core.embed_server import start_embed_server

            if start_embed_server():
                info("Embed server started (port 8082)")
            else:
                warning("Embed server unavailable — BM25-only KB search active")
        except Exception as _e:
            warning(f"Embed server startup skipped: {_e}")

        # Start file watch manager
        self.file_watch.start()

        _watchdog_ticks = 0
        try:
            while self.running:
                # Check for reload request
                if self._reload_requested:
                    info("Processing reload...")
                    self._reload_requested = False

                # Dispatch next ready task (planner queue + direct commands)
                await self._process_planner_tasks()

                # Cleanup completed background tasks periodically
                self.background.cleanup_completed(max_age=3600)

                # Watchdog — check servers every 30s (60 × 0.5s)
                _watchdog_ticks += 1
                if _watchdog_ticks >= 60:
                    _watchdog_ticks = 0
                    # Rolling system-wide CPU% sample for
                    # core/resource_gate.py's snapshot composer (Track 3
                    # Phase 5a / 7.4 sub-task A). Deliberately OUTSIDE the
                    # `if not _is_remote()` guard below — CPU/thermal state
                    # is backend-independent, and 7.4 sub-task D's future
                    # 20-minute sustained-CPU tripwire needs an unbroken
                    # history regardless of local/remote backend.
                    try:
                        from core.resource_gate import sample_cpu_percent

                        sample_cpu_percent()
                    except Exception as e:
                        # Best-effort signal only (same posture as this
                        # module's other watchdog sub-checks below) — a
                        # sampling failure must not stop the model/embed
                        # watchdogs that follow it in this same tick.
                        warning(f"resource_gate CPU sample failed: {e}")
                    # Rolling thermal sample, same placement/reasoning as the
                    # CPU sample immediately above (7.4 sub-task D) — also
                    # outside the `if not _is_remote()` guard, since thermal
                    # state is backend-independent and should_trip_shutdown()
                    # needs an unbroken history regardless of local/remote
                    # backend.
                    _sampled_temp_c = None
                    try:
                        from core.resource_gate import sample_temperature_c

                        _sampled_temp_c = sample_temperature_c()
                    except Exception as e:
                        # Same best-effort posture as the CPU sample above —
                        # a read failure here must not stop the watchdogs
                        # that follow it in this same tick.
                        warning(f"resource_gate temperature sample failed: {e}")
                    # Autonomous shutdown tripwire (7.4 sub-task D) — see the
                    # except: clause below for why this is not the same
                    # best-effort "log and continue silently" posture as the
                    # sampling calls above.
                    try:
                        from core.resource_gate import should_trip_shutdown
                        from utils.config import THERMAL_CONFIG as _tc

                        _trip = should_trip_shutdown()
                        # T8a telemetry: category-B gate-decision record for
                        # this call site, deduped/edge-triggered (see
                        # _emit_gate_telemetry_deduped()'s own docstring).
                        # Wrapped in its OWN try/except — separate from the
                        # outer except below, which has a specific safety
                        # meaning (a failure evaluating should_trip_shutdown()
                        # itself must stay visible and distinguishable from a
                        # telemetry bug). _emit_gate_telemetry_deduped()
                        # already never raises (it catches and logs
                        # internally), so this is defense-in-depth, not the
                        # primary safety net — but per CLAUDE.md's exception-
                        # handling rule, a bare `except: pass` here is safe
                        # specifically because it can only ever suppress a
                        # telemetry-recording failure, never a
                        # should_trip_shutdown() evaluation failure (that
                        # already returned above this line).
                        try:
                            self._emit_gate_telemetry_deduped(
                                event_type="should_trip_shutdown",
                                decision=_trip,
                                call_site="daemon._main_loop.should_trip_shutdown",
                            )
                        except Exception:
                            pass
                        _temp_critical = _tc.get("temp_critical", 90)
                        if _trip.should_trip:
                            warning(f"Autonomous shutdown tripwire fired: {_trip.reason}")
                            self._trigger_shutdown()
                            # NEW-118: `_trigger_shutdown()` only flips
                            # `self.running` False and closes the socket
                            # server — it does not itself stop this tick from
                            # continuing on into the model-load/embed-server
                            # watchdogs below, which could otherwise start
                            # loading a model in the same tick the daemon just
                            # decided to shut down. `continue` re-evaluates
                            # `while self.running:` immediately, which is now
                            # False, so this tick ends here and falls straight
                            # into `_main_loop()`'s `finally:` unload block.
                            continue
                        elif _sampled_temp_c is not None and _sampled_temp_c >= _temp_critical:
                            # Log at warning (not the routine info/debug level
                            # below) whenever THIS tick's own reading is
                            # already at/above the critical threshold, even
                            # though the sustained window isn't satisfied yet
                            # — this is what lets a live-verification session
                            # watch the per-tick progress toward a trip in the
                            # log, without every routine cool tick logging a
                            # warning line in normal operation.
                            warning(f"resource_gate shutdown-tripwire check: {_trip.reason}")
                        else:
                            info(f"resource_gate shutdown-tripwire check: {_trip.reason}")
                    except Exception as e:
                        # Deliberately NOT the same best-effort "log and
                        # move on unremarked" posture as the sampling
                        # try/excepts above: should_trip_shutdown() is a
                        # safety-relevant decision (CLAUDE.md's exception-
                        # handling rule applies), so a failure evaluating it
                        # must be visible at warning level, distinguishable
                        # from a plain sample-read failure. Still caught
                        # (rather than left to propagate and kill this
                        # watchdog tick / the main loop entirely) because a
                        # bug in the trip-check itself must not prevent the
                        # model/embed watchdogs immediately below from
                        # running this tick — the daemon keeps running and
                        # re-evaluates next tick, which is the safe direction
                        # here (see should_trip_shutdown()'s docstring on
                        # fail-safe-toward-not-killing).
                        warning(f"resource_gate shutdown-tripwire check failed (daemon NOT stopped, will re-evaluate next tick): {e}")

                    # T8a telemetry: category-C device sample, once per
                    # watchdog tick (~30s) — unconditional on `_is_remote()`,
                    # same placement/reasoning as the CPU/thermal samples
                    # above (device state is backend-independent).
                    self._record_daemon_telemetry_device_sample()

                    # T8a telemetry: category-D co-tenancy — idle-queue
                    # coverage. _check_dispatch_gate() already calls
                    # _observe_interactive_state() on every tick it runs,
                    # but it only runs when a task is actually queued; this
                    # once-per-watchdog-tick call is what catches a
                    # transition during an otherwise-idle queue.
                    try:
                        from core.resource_gate import is_interactive_session_active

                        self._observe_interactive_state(is_interactive_session_active())
                    except Exception as e:
                        warning(f"telemetry: interactive-state watchdog sample failed: {e}")

                    # 7B model server watchdog (local only)
                    if not _is_remote():
                        self._watchdog_check_model()
                    # Embed server watchdog
                    try:
                        from core.embed_server import get_embed_server

                        if not get_embed_server().is_running():
                            warning("Embed server died — restarting...")
                            from core.embed_server import start_embed_server

                            start_embed_server()
                    except Exception as e:
                        # NEW-88: this used to be a bare `except Exception:
                        # pass`, silently swallowing a failure with no trace —
                        # same class of problem the 7B model watchdog
                        # (_watchdog_check_model(), same watchdog loop) was
                        # already fixed to avoid. Left broad (not narrowed to
                        # a specific exception type) because this wraps both
                        # an is_running() liveness probe and a
                        # start_embed_server() subprocess spawn, each with
                        # its own unpredictable failure modes — but now
                        # logged instead of silent, matching this file's
                        # established best-effort-but-not-silent posture.
                        warning(f"Embed server watchdog check failed: {e}")

                # Small sleep to avoid busy loop
                await asyncio.sleep(0.5)

        finally:
            # Stop file watch
            self.file_watch.stop()

            # Stop 7B model server (llama-server) — it runs detached (os.setsid)
            # so it survives daemon exit unless explicitly unloaded here.
            # unload() releases the resource-gate slot as its last step
            # (core/loader_v2.py) — a failure here can leave BOTH an orphaned
            # detached llama-server process AND a leaked gate slot, which
            # would wrongly count against every future admission decision on
            # this device, so this is logged rather than silently swallowed
            # (unlike the embed-server shutdown right below, which has no
            # comparable gate-accounting side effect).
            try:
                from core.loader_v2 import get_loader

                get_loader().unload()
            except Exception as e:
                warning(f"7B model unload during shutdown failed: {e}")

            # Stop embed server
            try:
                from core.embed_server import stop_embed_server

                stop_embed_server()
            except Exception:
                pass

            # Cleanup
            await self.server.stop()
            remove_pid_file()
            self.state.set("daemon_stopped_at", int(time.time()))
            self.state.log_action("daemon_stopped", f"PID {os.getpid()}")
            info("Daemon stopped")

            # T8a telemetry: meta writer_stopped — last statement in this
            # finally block, after every other shutdown step above. See
            # _record_daemon_telemetry_writer_stopped()'s own docstring.
            _record_daemon_telemetry_writer_stopped()

    def _cached_read_battery_fn(self):
        """
        Cached/rate-limited battery reader for `can_dispatch_task()`'s
        per-tick `ResourceSnapshot` in `_process_planner_tasks()` — see
        `DISPATCH_BATTERY_CACHE_INTERVAL_S`'s module-level comment.

        On a read failure, the last-known value is kept (not clobbered to
        None) and the failure is logged — a transient
        `termux-battery-status` failure shouldn't make the gate suddenly
        treat battery state as unknown when a perfectly good cached value
        already exists; `get_resource_snapshot()`'s own per-call wrapper
        still applies its own "unavailable" handling on top of whatever
        this returns.
        """
        now = time.monotonic()
        if now - self._dispatch_battery_cache_ts >= DISPATCH_BATTERY_CACHE_INTERVAL_S:
            self._dispatch_battery_cache_ts = now
            try:
                from core.sysmon import read_battery_status

                self._dispatch_battery_cache_value = read_battery_status()
            except Exception as e:
                warning(f"resource_gate: cached battery read failed, keeping last-known value: {e}")
        return self._dispatch_battery_cache_value

    def _record_daemon_telemetry_device_sample(self) -> None:
        """
        Category-C device-state telemetry (T8a,
        docs/telemetry_layer_design.md §2.C), called once per ~30s watchdog
        tick from `_main_loop()`, unconditional on `_is_remote()` (device
        state is backend-independent). Reuses this same tick's already-
        cached battery reader (`_cached_read_battery_fn`, 30s cache — see
        `DISPATCH_BATTERY_CACHE_INTERVAL_S`) rather than adding a new
        polling cadence; the only new per-tick cost is one extra
        `read_meminfo()`/`read_zram_stats()` pair of /proc and /sys reads,
        and — via `get_resource_snapshot()` — a `termux-battery-status`
        subprocess call whenever that 30s battery cache has actually
        expired (i.e. on roughly every tick here too, since this tick's
        own cadence matches the cache interval), not a new standalone
        polling loop.

        Honest-null contract (§2.0.1): a `None` from any of these reads is
        a genuine observation failure, recorded as null + a reason code,
        not silently pruned. `cpu_percent` is ALWAYS null on this device
        (NEW-108, `/proc/stat` permission-denied) — inherited verbatim
        from `core/resource_gate.py`, not fixed here.

        `throttle_level`: no dedicated multi-level enum exists anywhere in
        `core/thermal.py` today (only a `throttled: bool` on
        `get_thermal_status()`'s return dict) — mapped to the two coarse
        strings this schema field anticipates, not a guessed scale nothing
        in this codebase actually computes.

        Never allowed to affect the caller — kill switch checked first,
        broad `except Exception`, logged at warning on failure, same
        contract as every other T8a telemetry helper in this file.
        """
        try:
            from telemetry import store

            if not store.TELEMETRY_ENABLED:
                return

            from core.resource_gate import (compute_zram_compression_ratio,
                                             get_resource_snapshot, read_meminfo,
                                             read_zram_stats)
            from core.thermal import get_thermal_status, is_inference_active
            from telemetry import recorders

            meminfo = read_meminfo()
            snapshot = get_resource_snapshot(meminfo=meminfo, read_battery_fn=self._cached_read_battery_fn)
            zram_stats = read_zram_stats()
            zram_ratio = compute_zram_compression_ratio(zram_stats)
            thermal_status = get_thermal_status()

            nulls: Dict[str, str] = {}
            if snapshot.cpu_percent is None:
                nulls["body.cpu_percent"] = "proc_stat_permission_denied"
            if snapshot.temperature_c is None:
                nulls["body.temperature_c"] = "thermal_zone_unreadable"
            if snapshot.battery_percent is None:
                nulls["body.battery_percent"] = "battery_read_failed"
            if zram_stats is None:
                nulls["body.zram_compression_ratio"] = "zram_stats_unavailable"
                nulls["body.zram_orig_data_bytes"] = "zram_stats_unavailable"
                nulls["body.zram_compr_data_bytes"] = "zram_stats_unavailable"

            recorders.record_device_sample(
                emitter="codey-os.daemon",
                pid=os.getpid(),
                snapshot=snapshot,
                mem_free_bytes=meminfo.get("MemFree"),
                mem_available_bytes=meminfo.get("MemAvailable"),
                zram_compression_ratio=zram_ratio,
                zram_orig_data_bytes=zram_stats.get("orig_data_size_bytes") if zram_stats else None,
                zram_compr_data_bytes=zram_stats.get("compr_data_size_bytes") if zram_stats else None,
                inference_active=is_inference_active(),
                inference_seconds_this_run=thermal_status.get("total_inference_sec", 0.0),
                throttle_level="throttled" if thermal_status.get("throttled") else "normal",
                nulls=nulls,
            )
        except Exception as e:
            # Best-effort signal only, same posture as the CPU/thermal
            # sampling calls in _main_loop()'s watchdog tick — a telemetry
            # read/emit failure must not stop the watchdogs that follow it
            # in this same tick.
            warning(f"telemetry: failed to record device sample: {e}")

    def _check_dispatch_gate(self):
        """
        Build a `ResourceSnapshot` (with the cached battery reader above)
        and the current interactive-session signal, and run
        `can_dispatch_task()` — the 7.4 sub-task C pre-claim gate check.

        Returns a `(decision, interactive_active)` tuple (T8a) — the
        `DispatchDecision` (`allowed`, `reason`) plus the interactive-
        session signal this method already computed, since callers also
        need that same value for category-D co-tenancy telemetry
        (`_track_dispatch_refusal()`) and recomputing it a second time
        would risk observing a different value than the one the decision
        was actually made with. Callers must consult the decision BEFORE
        `state.try_claim_task()` — claiming first and gating after would
        strand a refused task in `running` status with no executor ever
        picking it back up.
        """
        from core.resource_gate import can_dispatch_task, get_resource_snapshot, is_interactive_session_active

        snapshot = get_resource_snapshot(read_battery_fn=self._cached_read_battery_fn)
        interactive_active = is_interactive_session_active()
        decision = can_dispatch_task(snapshot, interactive_active)
        # T8a telemetry: category-B gate-decision record (deduped/edge-
        # triggered) + category-D interactive-state observation. Both are
        # best-effort, never allowed to affect the decision returned below
        # — see _emit_gate_telemetry_deduped()/_observe_interactive_state()
        # for their own never-crash contracts.
        self._emit_gate_telemetry_deduped(
            event_type="can_dispatch_task",
            decision=decision,
            call_site="daemon._check_dispatch_gate",
            snapshot=snapshot,
        )
        self._observe_interactive_state(interactive_active)
        return decision, interactive_active

    def _emit_gate_telemetry_deduped(self, *, event_type: str, decision, call_site: str, snapshot=None) -> None:
        """
        Category-B gate-decision telemetry (T8a,
        docs/telemetry_layer_design.md §2.B), edge-triggered and deduped
        per `call_site` — §2.B's "Edge-triggered recording (this is load-
        bearing, not an optimization)": `_check_dispatch_gate()` alone can
        run twice per second, so recording every evaluation would produce
        ~172,800 gate records/day for what is scientifically one repeated
        fact, not 172,800 observations.

        Two live callers as of T8a: `_check_dispatch_gate()`
        (`event_type="can_dispatch_task"`) and the `should_trip_shutdown()`
        watchdog check (`event_type="should_trip_shutdown"`) — each tracked
        under its own `call_site` key in `self._gate_dedup`, so the two
        never collide or share a dedup window.

        Dedup key = `(primary_outcome,
        _normalize_gate_reason_for_dedup(decision.reason), via_swap)` —
        the reason string is masked (embedded live-formatted numbers like
        RAM MiB/°C/% replaced) for key purposes ONLY (NEW-351); the
        emitted record's `reason=decision.reason` and `decision=` body
        fields always carry the full, unmasked string. `primary_outcome`
        is `decision.allowed` when present (GateDecision/
        DispatchDecision) else `decision.should_trip` (TripDecision, which
        has no `allowed` field), and `via_swap` is
        `decision.dispatched_via_swap` when present else
        `decision.admitted_via_swap` else `None` — this one helper serves
        both decision-object shapes without importing either dataclass
        type (matching `record_gate_decision()`'s own `_as_dict()`
        duck-typed contract; this module already imports
        `core.resource_gate` lazily elsewhere, but there is no reason to
        import the dataclasses themselves just to read two named
        attributes).

        Rule: a key change re-emits immediately (`repeat_count=1`,
        `dedup_window_ms=None`). An unchanged key is suppressed until 60s
        have elapsed since the window last emitted, then re-emitted
        carrying `repeat_count` (evaluations collapsed into THIS window
        only — the internal counter resets to 0 immediately after every
        emission, so an evaluation is never counted toward two different
        emitted records) and `dedup_window_ms` (the span actually
        covered). This is NOT lossless: when a key change interrupts an
        in-progress window, that window's already-accumulated-but-not-
        yet-emitted `repeat_count` is discarded — the new key's emission
        starts a fresh window, it does not flush the old one first. So
        summing `repeat_count` across every record emitted for a given
        `call_site` recovers a lower bound on the true evaluation count,
        under-counting by at most one in-progress window's worth per key
        transition (bounded, not exact — accepted per T8a's own findings
        list rather than adding a flush-on-transition emission).

        Never allowed to affect the caller's control flow or the decision
        being reported: kill switch checked first, broad `except Exception`
        around the whole body, logged at warning on failure — same
        contract as every other T2/T5/T6/T7 telemetry helper.
        """
        try:
            from telemetry import store

            if not store.TELEMETRY_ENABLED:
                return

            from telemetry import recorders

            primary_outcome = getattr(decision, "allowed", None)
            if primary_outcome is None:
                primary_outcome = getattr(decision, "should_trip", None)
            via_swap = getattr(decision, "dispatched_via_swap", None)
            if via_swap is None:
                via_swap = getattr(decision, "admitted_via_swap", None)
            key = (primary_outcome, _normalize_gate_reason_for_dedup(decision.reason), via_swap)

            now = time.monotonic()
            window = self._gate_dedup.get(call_site)

            if window is None or window["key"] != key:
                # New window: this evaluation is the ONLY one it covers so
                # far, so the emitted record's own repeat_count is 1. The
                # window's internal counter is reset to 0 (not 1) — it only
                # accumulates evaluations that happen AFTER this emission,
                # so no evaluation is double-counted across two emitted
                # records. If a prior window was still in progress (had an
                # unflushed repeat_count > 0) when this key change hit, that
                # count is discarded, not flushed — summing repeat_count
                # over time is a lower bound, not an exact total (§2.B
                # point 3 caveat, see docstring above).
                self._gate_dedup[call_site] = {"key": key, "window_start_mono": now, "repeat_count": 0}
                recorders.record_gate_decision(
                    event_type=event_type,
                    emitter="codey-os.daemon",
                    pid=os.getpid(),
                    decision=decision,
                    call_site=call_site,
                    reason=decision.reason,
                    snapshot=snapshot,
                    repeat_count=1,
                    dedup_window_ms=None,
                )
                return

            window["repeat_count"] += 1
            elapsed_ms = (now - window["window_start_mono"]) * 1000.0
            if elapsed_ms >= 60_000.0:
                recorders.record_gate_decision(
                    event_type=event_type,
                    emitter="codey-os.daemon",
                    pid=os.getpid(),
                    decision=decision,
                    call_site=call_site,
                    reason=decision.reason,
                    snapshot=snapshot,
                    repeat_count=window["repeat_count"],
                    dedup_window_ms=elapsed_ms,
                )
                # Same reasoning as the new-window branch above: reset to 0,
                # not 1 — this heartbeat's repeat_count already covers every
                # evaluation collapsed into it (including this one), so the
                # next window must start counting from zero, not
                # double-count this evaluation into the next emission too.
                self._gate_dedup[call_site] = {"key": key, "window_start_mono": now, "repeat_count": 0}
        except Exception as e:
            warning(f"telemetry: failed to record gate decision ({call_site}): {e}")

    def _observe_interactive_state(self, active: bool) -> None:
        """
        Category-D co-tenancy telemetry (T8a,
        docs/telemetry_layer_design.md §2.D): emits `interactive_transition`
        only on an actual state change from the last-observed value — the
        very first observation this process makes just seeds
        `self._interactive_active_last`/`self._interactive_state_since_mono`
        with no emission, since there is no genuine "previous" state to
        report a transition from yet.

        Called from `_check_dispatch_gate()` (using the interactive-active
        value it already computed for the dispatch decision itself) AND
        once per 30s watchdog tick — the watchdog call exists for idle-
        queue coverage, since `_check_dispatch_gate()` only ever runs when
        a task is actually queued and a transition during an empty queue
        would otherwise never be observed at all.
        """
        now = time.monotonic()
        if self._interactive_active_last is None:
            self._interactive_active_last = active
            self._interactive_state_since_mono = now
            return
        if active == self._interactive_active_last:
            return

        previous_active = self._interactive_active_last
        state_duration_ms = (now - self._interactive_state_since_mono) * 1000.0
        self._interactive_active_last = active
        self._interactive_state_since_mono = now

        try:
            from telemetry import store

            if not store.TELEMETRY_ENABLED:
                return

            from telemetry import recorders

            recorders.record_cotenancy_transition(
                emitter="codey-os.daemon",
                pid=os.getpid(),
                active=active,
                previous_active=previous_active,
                live_session_pids=self._list_live_tui_session_pids(),
                state_duration_ms=state_duration_ms,
            )
        except Exception as e:
            warning(f"telemetry: failed to record interactive_transition: {e}")

    def _list_live_tui_session_pids(self) -> List[int]:
        """
        Passive, read-only listing of currently-live TUI session PIDs from
        `utils.config.TUI_SESSIONS_DIR` (T8a, for category-D's
        `live_session_pids` field). Mirrors the per-file liveness check
        `core/resource_gate.py`'s `is_tui_session_active()` already does
        (one file per session, `os.kill(pid, 0)` liveness probe) — but
        deliberately does NOT reap stale/dead-PID entries the way that
        function does. Reaping is `is_tui_session_active()`'s job (an
        explicit non-goal to touch here); this helper only observes and
        reports, so a telemetry read can never have a side effect on the
        real gate-decision signal.
        """
        pids: List[int] = []
        try:
            from utils.config import TUI_SESSIONS_DIR

            if not TUI_SESSIONS_DIR.exists():
                return pids
            entries = list(TUI_SESSIONS_DIR.iterdir())
        except OSError:
            return pids

        for entry in entries:
            if not entry.is_file() or entry.name.startswith("."):
                continue
            try:
                pid = int(entry.read_text().strip())
            except (OSError, ValueError):
                continue
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, PermissionError):
                continue
            except OSError:
                continue
            pids.append(pid)
        return pids

    def _track_dispatch_refusal(self, task_id: int, interactive_active: bool, refusal_reason: str) -> None:
        """
        Category-D co-tenancy telemetry (T8a): tracks first-refusal time +
        cumulative refusal count per `task_id` in `self._deferral_state`,
        so a later successful claim (`_resolve_deferral_if_any()`) can
        report the wall time an actually-dispatched task spent deferred.

        `self._deferral_state` entries are created/updated for EVERY
        refusal (any reason — thermal, battery, RAM, interactive), so
        `_resolve_deferral_if_any()` always has an accurate
        `deferral_refusal_count` to report and always clears the entry on
        resolution, regardless of what kind of refusal caused it. Emission
        of `dispatch_refused_human_present` itself, however, only happens
        on the task's FIRST refusal AND only when `interactive_active` is
        True — category D is co-tenancy-specific ("a human is watching"),
        not a general "any dispatch was refused" event; thermal/battery/
        RAM refusals are already fully captured by category B's gate-
        decision telemetry and must not also be double-counted here.
        """
        now = time.monotonic()
        existing = self._deferral_state.get(task_id)
        if existing is None:
            if len(self._deferral_state) >= _DEFERRAL_STATE_MAX_ENTRIES:
                # Defensive cap (rule 2) — bounds unbounded growth from
                # tasks refused and then abandoned (e.g. cancelled) before
                # ever reaching a matching _resolve_deferral_if_any() call.
                # Evict the single oldest entry by first_refused_mono.
                oldest_task_id = min(
                    self._deferral_state, key=lambda tid: self._deferral_state[tid]["first_refused_mono"]
                )
                del self._deferral_state[oldest_task_id]
            self._deferral_state[task_id] = {"first_refused_mono": now, "refusal_count": 1.0}
            first_refusal = True
        else:
            existing["refusal_count"] += 1
            first_refusal = False

        if not (first_refusal and interactive_active):
            return

        try:
            from telemetry import store

            if not store.TELEMETRY_ENABLED:
                return

            from telemetry import recorders

            recorders.record_dispatch_refused_human_present(
                emitter="codey-os.daemon",
                pid=os.getpid(),
                refused_task_id=task_id,
                refusal_reason=refusal_reason,
            )
        except Exception as e:
            warning(f"telemetry: failed to record dispatch_refused_human_present: {e}")

    def _resolve_deferral_if_any(self, task_id: int) -> None:
        """
        Category-D co-tenancy telemetry (T8a): counterpart to
        `_track_dispatch_refusal()`, called right after a task successfully
        claims (in EVERY branch, not just ones refused while interactive —
        `self._deferral_state` may hold an entry from a non-interactive
        refusal too, and this call is what clears it so the dict doesn't
        grow with stale resolved entries). Emits `deferral_resolved` only
        when `task_id` actually has a tracked prior refusal; a task that
        dispatched on its very first evaluation has no entry and this is a
        no-op.
        """
        state = self._deferral_state.pop(task_id, None)
        if state is None:
            return

        deferral_ms = (time.monotonic() - state["first_refused_mono"]) * 1000.0
        deferral_refusal_count = int(state["refusal_count"])

        try:
            from telemetry import store

            if not store.TELEMETRY_ENABLED:
                return

            from telemetry import recorders

            recorders.record_deferral_resolved(
                emitter="codey-os.daemon",
                pid=os.getpid(),
                deferral_ms=deferral_ms,
                deferral_refusal_count=deferral_refusal_count,
            )
        except Exception as e:
            warning(f"telemetry: failed to record deferral_resolved: {e}")

    async def _plan_claimed_task(self, prompt: str, tier: str = "hard"):
        """
        Pull-side planning step for a claimed `needs_planning=1` direct-
        command task (7.4 sub-task C) — relocated from `_handle_command`'s
        old synchronous enqueue-time planning call, fallback-to-single-task
        semantics as before. Returns the step list (possibly None/empty) or
        None on any failure; planner unavailability is always silent
        (logged only), matching the original behavior this replaces.

        NEW-165 fix 3 (2026-08-23): the timeout is no longer a flat 180s —
        it's derived from core.plannd.compute_planner_timeout(), the same
        formula plannd.py uses for its own inner HTTP timeout around this
        same call, plus a small buffer. See _handle_command's plan_only
        branch above for the identical reasoning.

        *tier* (7.3 sub-task E Task B, 2026-08-24) defaults to "hard": this
        function's only caller (`_process_planner_tasks()`'s
        needs_planning=1 branch) enqueues from `state.add_task()`'s
        `description` column, which does not carry a tier value through the
        tasks table (per NEW-112, this whole enqueue path has no live
        caller today) — plumbing tier through the DB schema is a separate,
        out-of-scope change, so this stays pinned to hard-tier behavior
        until/unless that's done.
        """
        try:
            from core.plannd import PLANNER_PROMPT, compute_outer_plan_timeout
            from core.planner_client import send_plan_request_async
            from core.tokens import estimate_tokens
            from utils.config import (PLANNER_MAX_TOKENS,
                                      PLANNER_MAX_TOKENS_MEDIUM)

            enable_thinking = tier != "medium"
            max_tokens_for_this_request = (
                PLANNER_MAX_TOKENS_MEDIUM if tier == "medium" else PLANNER_MAX_TOKENS
            )

            # §8 Q11 (2026-08-26): see _handle_command's plan_only branch
            # above — compute_outer_plan_timeout() adds a buffer for
            # get_plan()'s own new context-budget queue wait.
            prompt_tokens_estimate = estimate_tokens(PLANNER_PROMPT) + estimate_tokens(prompt)
            outer_timeout = compute_outer_plan_timeout(prompt_tokens_estimate, max_tokens_for_this_request)

            steps = await asyncio.wait_for(
                send_plan_request_async(prompt, enable_thinking=enable_thinking),
                timeout=outer_timeout,
            )
            return steps
        except asyncio.TimeoutError:
            warning(f"plannd request timed out after {outer_timeout:.0f}s — falling back to direct task")
        except ConnectionRefusedError:
            # plannd not running — silent fallback
            pass
        except Exception as _e:
            warning(f"plannd unavailable ({_e}) — falling back to direct task")
        return None

    async def _process_planner_tasks(self):
        """Dispatch one ready task per main-loop tick.

        Two task sources are unified here:

        1. Planner tasks  — added via Planner.add_task(); tracked in the planner's
           in-memory dict AND persisted to SQLite.
        2. Direct command tasks — added via the socket `command` handler directly
           into SQLite (not in the planner dict).

        All claiming is done with state.try_claim_task() which atomically flips
        status pending→running only once, preventing double-execution.
        """
        timeout = self._config.get("tasks", "task_timeout", default=1800)

        # ── 1. Try a planner task first (respects dependency ordering) ──────────
        planner_task = self.planner.get_next_task()
        if planner_task:
            # 7.4 sub-task C: gate check BEFORE try_claim_task() — claiming
            # first and gating after would strand a refused task in
            # 'running' status with no executor ever picking it back up.
            # planner.get_next_task() is a pure in-memory peek (no state
            # mutation), so it was safe to call before this check.
            decision, interactive_active = self._check_dispatch_gate()
            if not decision.allowed:
                info(f"Daemon: dispatch deferred (planner task {planner_task.id}) — {decision.reason}")
                self._track_dispatch_refusal(planner_task.id, interactive_active, decision.reason)
                return

            # Atomically claim in SQLite before any yield point.
            if not self.state.try_claim_task(planner_task.id):
                # Already claimed by a previous tick that somehow didn't clean up.
                # Sync in-memory state from SQLite.
                db = self.state.get_task(planner_task.id)
                if db:
                    if db["status"] == "done":
                        self.planner.complete_task(planner_task.id, db.get("result", ""))
                    elif db["status"] == "failed":
                        self.planner.fail_task(planner_task.id, db.get("result", "already failed"))
                return

            # T8a telemetry: category-D — resolve any tracked deferral for
            # this task_id now that it has actually claimed.
            self._resolve_deferral_if_any(planner_task.id)

            # Sync in-memory planner state. planner.start_task() re-runs the SQLite
            # UPDATE (harmless — overwrites 'running' with 'running') and sets the
            # in-memory task status and _current_task pointer.
            self.planner.start_task(planner_task.id)

            info(f"Planner: dispatching task {planner_task.id}: {planner_task.description[:50]}...")
            try:
                # T8b telemetry: activates task_executor.py's T7 category-E
                # task_started/task_finished for this branch. task_type=
                # "planner" per docs/telemetry_layer_design.md — branch
                # identity, not downstream fate (NOT "planning_expansion";
                # no dispatch site here can distinguish an expansion-
                # produced planner row from any other, see T8b handoff).
                #
                # needs_planning is re-read from SQLite (NEW-356), not
                # hardcoded False: Planner.__init__()'s _load_tasks()
                # (core/planner_v2.py) unconditionally rehydrates every
                # pending/running task_queue row into self._tasks with no
                # filter on origin or needs_planning, so a needs_planning=1
                # direct-command row (core/daemon.py's _handle_command path)
                # that is still pending at the exact moment of a daemon
                # restart can land here instead of the direct-task branch
                # below, which does read the real value. A live read (not a
                # field cached on Task at load time) is used because nothing
                # on this branch's path ever mutates needs_planning after
                # load -- state.clear_needs_planning() is only ever called
                # from the direct-task branch below, and only on rows NOT
                # tracked in self.planner._tasks -- so a fresh read here is
                # always accurate and carries no staleness risk to reason
                # about.
                _dispatch_start_mono = time.monotonic()
                db_task_row = self.state.get_task(planner_task.id)
                needs_planning_value = bool(db_task_row.get("needs_planning")) if db_task_row else False
                result = await asyncio.wait_for(
                    self.executor._execute_task(
                        planner_task.description,
                        task_id=planner_task.id,
                        task_type="planner",
                        needs_planning=needs_planning_value,
                    ),
                    timeout=timeout,
                )
                self.planner.complete_task(planner_task.id, result)
            except asyncio.TimeoutError as exc:
                err = f"Task timed out after {timeout}s"
                error(err)
                self.planner.fail_task(planner_task.id, err)
                # NEW-357: only emit the corrective task_finished record when
                # this TimeoutError genuinely came from THIS wait_for()'s own
                # timeout firing (wait_for always raises it via
                # `raise TimeoutError from exc` where exc is the
                # CancelledError it delivered internally). asyncio.TimeoutError
                # IS builtins.TimeoutError, and socket.timeout has been an
                # alias of it since Python 3.10 -- a genuine socket-level
                # timeout raised anywhere inside
                # pm.call_capability("coding.run_agent", ...) would propagate
                # out of _execute_task() through its own `except Exception`
                # branch (already correctly recording terminal_status="failed",
                # error_class="TimeoutError") and would ALSO be caught here,
                # since it's literally the same exception class. Without this
                # guard we would fabricate a terminal_status="timeout"
                # correction record on top of an accurate "failed" one.
                if isinstance(exc.__cause__, asyncio.CancelledError):
                    emit_task_timeout_correction(
                        task_id=planner_task.id,
                        task_type="planner",
                        needs_planning=needs_planning_value,
                        duration_ms=(time.monotonic() - _dispatch_start_mono) * 1000.0,
                        timeout_sec=int(timeout) if timeout is not None else None,
                    )
            except Exception as e:
                error(f"Planner: task {planner_task.id} error: {e}")
                self.planner.fail_task(planner_task.id, str(e))
            return

        # ── 2. Fall back to direct-command tasks (not in planner dict) ──────────
        db_task = self.state.get_next_pending()
        if not db_task:
            return
        # Only handle tasks that aren't tracked by the planner in memory.
        if db_task["id"] in self.planner._tasks:
            return  # planner will handle it next tick

        # 7.4 sub-task C: gate check BEFORE try_claim_task() — same
        # claim-order requirement as the planner-task branch above.
        decision, interactive_active = self._check_dispatch_gate()
        if not decision.allowed:
            info(f"Daemon: dispatch deferred (direct task {db_task['id']}) — {decision.reason}")
            self._track_dispatch_refusal(db_task["id"], interactive_active, decision.reason)
            return

        if not self.state.try_claim_task(db_task["id"]):
            return  # lost the race — another path claimed it

        # T8a telemetry: category-D — resolve any tracked deferral for this
        # task_id now that it has actually claimed.
        self._resolve_deferral_if_any(db_task["id"])

        # 7.4 sub-task C: pull-side planning for a raw task enqueued via
        # _handle_command's plan_only=False path (needs_planning=1) — moved
        # here from the old synchronous enqueue-time send_plan_request_async
        # call, fallback-to-single-task semantics (timeout is now
        # formula-derived, see _plan_claimed_task's own docstring, NEW-165).
        description = db_task["description"]
        if db_task.get("needs_planning"):
            steps = await self._plan_claimed_task(description)
            if steps and len(steps) > 1:
                total = len(steps)
                enriched = []
                for i, step in enumerate(steps):
                    if i == 0:
                        step_low = step.lower().strip()
                        if step_low.startswith(("edit", "patch", "update", "modify", "fix", "change")):
                            enriched.append(
                                f"User's full request: {description}\n\n"
                                f"Your task (step {i+1}/{total}): {step}\n\n"
                                "Apply ONLY the requested changes using patch_file. "
                                "Do not overwrite or rewrite unrelated code."
                            )
                        elif step_low.startswith(("create", "write", "build", "add")):
                            enriched.append(
                                f"User's full request: {description}\n\n"
                                f"Your task (step {i+1}/{total}): {step}\n\n"
                                "Write the COMPLETE file with ALL features "
                                "described above. Do not skip any requirement."
                            )
                        else:
                            enriched.append(
                                f"User's full request: {description}\n\n"
                                f"Your task (step {i+1}/{total}): {step}\n\n"
                                "Complete this step according to the requirements above."
                            )
                    else:
                        enriched.append(
                            f"Previous context: {description[:200]}\n\n"
                            f"Your task (step {i+1}/{total}): {step}\n\n"
                            "Complete only this step."
                        )
                task_ids = self.planner.add_tasks(enriched)
                info(f"plannd: expanded queued task {db_task['id']} into {total}-step plan {task_ids}")
                # The original raw row is superseded by the new enriched
                # tasks above — mark it done (not left 'running' forever
                # with nothing to execute it) rather than dispatching it.
                self.state.complete_task(
                    db_task["id"], f"Expanded into {total}-step plan: task_ids={task_ids}"
                )
                self.state.clear_needs_planning(db_task["id"])
                self._record_daemon_telemetry_superseded_by_plan(db_task["id"])
                return
            if steps:
                info(f"plannd returned only 1 step for task {db_task['id']} — using single-task path")
            self.state.clear_needs_planning(db_task["id"])

        info(f"Daemon: executing direct task {db_task['id']}: {description[:50]}...")
        try:
            # T8b telemetry: activates task_executor.py's T7 category-E
            # task_started/task_finished for this branch. task_type=
            # "direct" matches _record_daemon_telemetry_superseded_by_plan's
            # (T8a, above) hardcoded value for the sibling terminal state on
            # this same task row. needs_planning is read off `db_task` — the
            # pre-clear snapshot fetched above via state.get_next_pending(),
            # never re-fetched since — so a task that had needs_planning=1
            # but fell through to single-task execution (steps and len(steps)
            # <= 1) still reports its honest historical needs_planning value,
            # not the cleared-to-0 value clear_needs_planning() has already
            # written to SQLite by this point.
            _dispatch_start_mono = time.monotonic()
            result = await asyncio.wait_for(
                self.executor._execute_task(
                    description,
                    task_id=db_task["id"],
                    task_type="direct",
                    needs_planning=bool(db_task.get("needs_planning")),
                ),
                timeout=timeout,
            )
            self.state.complete_task(db_task["id"], result)
        except asyncio.TimeoutError as exc:
            self.state.fail_task(db_task["id"], f"Task timed out after {timeout}s")
            # NEW-357: see the sibling planner-branch dispatch site above for
            # the full explanation of why this __cause__ guard is required --
            # asyncio.TimeoutError IS builtins.TimeoutError (and
            # socket.timeout has aliased it since Python 3.10), so a genuine
            # socket-level timeout from inside run_agent() would otherwise be
            # mistaken for this wait_for()'s own timeout and get a fabricated
            # terminal_status="timeout" correction on top of the accurate
            # "failed" record _execute_task() already emitted for it.
            if isinstance(exc.__cause__, asyncio.CancelledError):
                emit_task_timeout_correction(
                    task_id=db_task["id"],
                    task_type="direct",
                    needs_planning=bool(db_task.get("needs_planning")),
                    duration_ms=(time.monotonic() - _dispatch_start_mono) * 1000.0,
                    timeout_sec=int(timeout) if timeout is not None else None,
                )
        except Exception as e:
            self.state.fail_task(db_task["id"], str(e))

    def _record_daemon_telemetry_superseded_by_plan(self, task_id: int) -> None:
        """
        Category-E task-outcome telemetry (T8a,
        docs/telemetry_layer_design.md §2.E) for the one terminal state a
        raw `task_queue` row can reach WITHOUT ever calling
        `TaskExecutor._execute_task()`: this call site (immediately above,
        `self.state.complete_task(db_task["id"], f"Expanded into
        {total}-step plan...")`) retires the raw row because it expanded
        into an N-step plan instead of being dispatched itself.

        Emits a LONE `task_finished` record — deliberately no matching
        `task_started` for this same `task_id`, by design: this task_id
        never enters `_execute_task()` at all (it is superseded by N new
        task_ids instead, each of which gets its own real
        `task_started`/`task_finished` pair when THEY dispatch — via
        `core/task_executor.py`'s T7 instrumentation, unaffected by this
        call). `duration_ms=0.0` because there is no execution duration to
        report — the row was retired, not run. `needs_planning=True` is
        hardcoded rather than re-read from the row: this method's only
        caller is the `if db_task.get("needs_planning"):` branch, so it is
        structurally always true here.
        """
        try:
            from telemetry import store

            if not store.TELEMETRY_ENABLED:
                return

            from telemetry import recorders

            recorders.record_task_finished(
                emitter="codey-os.daemon",
                pid=os.getpid(),
                task_id=task_id,
                task_type="direct",
                needs_planning=True,
                finished_ts_wall=time.time(),
                duration_ms=0.0,
                terminal_status="superseded_by_plan",
            )
        except Exception as e:
            warning(f"telemetry: failed to record superseded_by_plan task_finished for task {task_id}: {e}")

    def run(self):
        """Run the daemon."""
        write_pid_file()
        info(f"Daemon PID: {os.getpid()}")

        try:
            asyncio.run(self._main_loop())
        except KeyboardInterrupt:
            info("Interrupted")
        finally:
            remove_pid_file()


# ==================== CLI Functions ====================


def is_daemon_running() -> bool:
    """Check if daemon is running by testing socket."""
    if not SOCKET_FILE.exists():
        return False

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        sock.connect(str(SOCKET_FILE))
        sock.close()
        return True
    except (socket.error, OSError):
        return False


def send_command(cmd: str, data: Dict = None, timeout: float = 60.0) -> Dict:
    """Send a command to the daemon via socket."""
    if not SOCKET_FILE.exists():
        raise ConnectionError("Daemon socket not found. Is the daemon running?")

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)

    try:
        sock.connect(str(SOCKET_FILE))

        # Send request
        request = {"cmd": cmd, "data": data or {}}
        sock.sendall(json.dumps(request).encode("utf-8"))

        # Receive response
        response_data = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            response_data += chunk

        if not response_data:
            raise ConnectionError("No response from daemon. Connection closed.")

        response = json.loads(response_data.decode("utf-8"))

        # Check for error response
        if response.get("status") == "error":
            raise RuntimeError(response.get("message", "Unknown error"))

        return response

    except socket.timeout:
        raise ConnectionError("Connection timed out. Daemon may be busy.")
    except socket.error as e:
        raise ConnectionError(f"Socket error: {e}. Is the daemon running?")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid response from daemon: {e}")
    finally:
        try:
            sock.close()
        except (OSError, IOError):
            pass


def daemon_status() -> Dict:
    """Get daemon status."""
    return send_command("status")


def daemon_task_in_progress() -> bool:
    """
    NEW-145/NEW-149/NEW-155 chain, Option C (2026-08-27): is the daemon
    currently mid-execution of a real task? Used by
    `core/loader_v2.py:LlamaServer.start()`'s `allow_upgrade` respawn gate
    to decide whether it's safe to kill+respawn a resident coder server
    that's undersized for an interactive caller's real `n_ctx` need —
    killing a server that's mid-request for a background task would be a
    new, worse bug than the one this fix addresses.

    **Fail-closed on any inability to determine** (daemon reachable but
    query errors/times out, malformed response, unexpected exception) —
    returns `True` ("assume busy," do not respawn this attach). The one
    legitimate `False` short-circuit is `is_daemon_running()` itself
    returning `False`: no daemon process means nothing can possibly be
    mid-task, a real (not degraded-signal) idle reading, not a guess.

    Queried via `send_command("status", ...)` — the existing socket RPC,
    not a second, independent sqlite3 connection against the daemon's own
    live state DB file (which the daemon process already holds open) — and
    reads `tasks.running_active` from `_handle_status()`'s response, which
    is already age-filtered against `task_timeout` so a stale 'running' row
    left behind by a daemon that died ungracefully mid-task (NEW-146's
    orphan-state shape) can't wedge this gate permanently busy.
    """
    try:
        if not is_daemon_running():
            return False
        response = send_command("status", timeout=3)
    except Exception as e:
        # Any failure to reach/parse the daemon here (socket error, timeout,
        # unexpected response shape) is exactly the "can't tell" case this
        # helper's docstring commits to treating as busy — a false "busy"
        # just means Option C's respawn skips this attach and the caller
        # falls through to today's existing reuse behavior unchanged, which
        # is always safe; a false "idle" could get a server killed out from
        # under a real in-flight task, which is not.
        warning(
            f"daemon_task_in_progress: could not query daemon status ({e}) — "
            "assuming busy (fail-closed)"
        )
        return True

    tasks = response.get("tasks") if isinstance(response, dict) else None
    running_active = tasks.get("running_active") if isinstance(tasks, dict) else None
    if running_active is None:
        # Malformed/unexpected response shape — same fail-closed reasoning
        # as the exception branch above, not a silent "treat as idle."
        warning(
            "daemon_task_in_progress: status response missing "
            "tasks.running_active — assuming busy (fail-closed)"
        )
        return True
    return running_active > 0


def daemon_health() -> Dict:
    """Get daemon health check."""
    return send_command("health")


def daemon_ping() -> Dict:
    """Ping the daemon."""
    return send_command("ping")


# ==================== Entry Point ====================


def main():
    """Main entry point for daemon."""
    if check_pid_file():
        error("Daemon is already running")
        sys.exit(1)

    daemon = Daemon()
    daemon.run()


if __name__ == "__main__":
    main()
