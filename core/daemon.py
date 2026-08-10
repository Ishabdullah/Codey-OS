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
import signal
import socket
import sys
import time
from pathlib import Path
from typing import Callable, Dict, Optional

from core.daemon_config import get_config
from core.state import StateStore, get_state_store
from core.task_executor import TaskExecutor
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
# load-direction confirm (`confirm_resident_and_mark_slot()`) and the
# eviction-direction confirm (`_evict_planner_and_confirm_free()`'s
# `probe_port_health()`) already established in sub-tasks 2/3.
RELEASE_CONFIRM_TIMEOUT_S = 3.0
RELEASE_CONFIRM_POLL_INTERVAL_S = 0.3

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

    def __init__(self, state: StateStore, shutdown_callback=None):
        self.state = state
        self.server: Optional[asyncio.Server] = None
        self.running = False
        self._handlers: Dict[str, Callable] = {}
        self._shutdown_callback = shutdown_callback
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
        self.register_handler("shutdown", self._handle_shutdown)
        self.register_handler("release_model_slot", self._handle_release_model_slot)

    def register_handler(self, cmd: str, handler: Callable):
        """Register a command handler."""
        self._handlers[cmd] = handler

    async def _handle_ping(self, data: Dict) -> Dict:
        """Handle ping command."""
        return {"status": "ok", "message": "pong"}

    async def _handle_command(self, data: Dict) -> Dict:
        """Handle a user command (prompt).

        The 1.5B model on port 8081 plans the task into numbered steps.
        Each step is added as a dependent task so the 7B agent works through
        them one at a time.

        If the planner is unavailable, times out, or returns fewer than 2 steps,
        the prompt is queued as a single direct task.  Planner failure is always
        silent (logged only) and never surfaces as an error.
        """
        prompt = data.get("prompt", "")
        if not prompt:
            return {"status": "error", "message": "No prompt provided"}

        # Log to episodic log
        self.state.log_action("command_received", prompt[:200])

        # ── plannd integration (Change 1) ────────────────────────────────────
        no_plan = data.get("no_plan", False)
        if not no_plan:
            try:
                from core.planner_client import send_plan_request_async

                steps = await asyncio.wait_for(
                    send_plan_request_async(prompt),
                    timeout=180.0,
                )
                if steps and len(steps) > 1:
                    if data.get("plan_only", False):
                        task_ids = []
                        info(f"plannd: returned {len(steps)}-step plan (plan_only)")
                    else:
                        # Inject original prompt into step 1 (the create step)
                        # so the executor has full requirements context.
                        # Later steps (run/verify) are usually self-contained
                        # and don't need the full prompt — just the step.
                        total = len(steps)
                        enriched = []
                        for i, step in enumerate(steps):
                            if i == 0:
                                # Step 1: full context — the executor needs
                                # all requirements to write the code
                                enriched.append(
                                    f"User's full request: {prompt}\n\n"
                                    f"Your task (step {i+1}/{total}): {step}\n\n"
                                    "Write the COMPLETE file with ALL features "
                                    "described above. Do not skip any requirement."
                                )
                            else:
                                enriched.append(
                                    f"Previous context: {prompt[:200]}\n\n"
                                    f"Your task (step {i+1}/{total}): {step}\n\n"
                                    "Complete only this step."
                                )
                        task_ids = self.planner.add_tasks(enriched)
                        info(f"plannd: queued {len(steps)}-step plan")
                    return {
                        "status": "ok",
                        "message": f"Plan created: {len(steps)} steps",
                        "task_ids": task_ids,
                        "plan": steps,
                    }
                # plannd returned ≤1 step — fall through to single-task path
                if steps:
                    info("plannd returned only 1 step — using single-task path")
            except asyncio.TimeoutError:
                warning("plannd request timed out after 180 s — falling back to direct task")
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
        running = len(self.state.get_tasks_by_status("running"))
        done = len(self.state.get_tasks_by_status("done"))

        return {
            "status": "ok",
            "daemon": "running",
            "pid": os.getpid(),
            "tasks": {"pending": pending, "running": running, "done": done},
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
        for t in all_tasks:
            if t["status"] == "running" and t.get("started_at"):
                running_time = now - t["started_at"]
                if running_time > 1800:  # 30 minutes
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

    async def _handle_shutdown(self, data: Dict) -> Dict:
        """Handle shutdown request — triggers the daemon's main loop to exit."""
        info("Shutdown requested via socket")
        if self._shutdown_callback:
            self._shutdown_callback()
        return {"status": "ok", "message": "Shutting down"}

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

        Request: {"model_id": "primary" | "planner"}
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
          - If `core.loader_v2.SWAP_GUARD` can't be acquired non-blocking, a
            primary/planner swap is already in flight elsewhere in this
            process — declined as busy rather than racing it. The guard is
            then HELD across the unload (not probed-and-dropped), for the
            same reason `ensure_model()` holds it for its entire body: the
            loaded/not-loaded transition window is exactly the race the
            guard exists to prevent.
          - Already-not-loaded is a clean success no-op (`released: False`,
            `outcome: already_unloaded`), not an error — the caller's goal
            (a free slot) is already satisfied.
          - A confirmed release only counts toward the per-model_id cooldown
            (RELEASE_SLOT_COOLDOWN_S) — a busy/cooldown decline never arms
            the cooldown itself, so a legitimate retry right after a decline
            clears isn't punished for the decline.

        NOTE (per this sub-task's own scope, not a bug): for `model_id ==
        "planner"`, this will almost always be the `already_unloaded`
        no-op in practice. `plannd` (the 1.5B planner) runs as a genuinely
        separate OS process (see codeydOS) with its OWN
        `core.planner_loader` singleton — this daemon process's own
        planner-loader singleton is only ever loaded here indirectly, via
        `ModelLoader._evict_planner_and_confirm_free()`'s in-process
        eviction check, and is not the process actually holding the
        planner's slot in the common case. Implemented generically per this
        sub-task's instructions regardless, since a future in-process
        planner load path isn't ruled out.
        """
        model_id = data.get("model_id")
        if model_id not in ("primary", "planner"):
            return {
                "status": "error",
                "released": False,
                "outcome": RELEASE_OUTCOME_INVALID_MODEL,
                "message": f"model_id must be 'primary' or 'planner', got {model_id!r}",
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
        from core.planner_loader import get_planner_loader
        from utils.config import PLANND_SERVER_PORT, PRIMARY_SERVER_PORT

        if not SWAP_GUARD.acquire(blocking=False):
            return {
                "status": "ok",
                "released": False,
                "outcome": RELEASE_OUTCOME_BUSY_SWAP,
                "message": "a primary/planner swap is already in flight — declined",
            }

        try:
            if model_id == "primary":
                loader = get_loader()
                port = PRIMARY_SERVER_PORT
            else:
                loader = get_planner_loader()
                port = PLANND_SERVER_PORT

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


# ==================== Daemon Core ====================


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
        self.server = DaemonServer(self.state, shutdown_callback=self._trigger_shutdown)
        self.executor = TaskExecutor(self.state, self._config)
        from core.planner_v2 import get_planner

        self.planner = get_planner()
        # Give DaemonServer access to the planner so _handle_command can queue steps.
        self.server.planner = self.planner
        from core.background import (get_background_manager,
                                     get_file_watch_manager)

        self.background = get_background_manager()
        self.file_watch = get_file_watch_manager()
        self.running = True
        self._reload_requested = False

        # Register signal handlers
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGUSR1, self._handle_sigusr1)

        # Wire ProjectMemory: load CODEY.md and config.json at boot (never evicted)
        try:
            from pathlib import Path as _Path

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
        """Called by DaemonServer when a socket shutdown command is received."""
        info("Daemon shutdown triggered via socket command")
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
                                         LOAD_OUTCOME_EVICTION_FAILED,
                                         LOAD_OUTCOME_GATE_DENIED,
                                         LOAD_OUTCOME_GATE_DENIED_HARD,
                                         get_loader)

            loader = get_loader()
            server = loader.get_model_instance()
            was_running = bool(server and server.is_running())

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
                # SWAP_GUARD busy (planner mid-swap) — expected, benign,
                # self-resolves on the next tick. Not worth a warning.
                info(f"7B model watchdog: {reason}")
            elif outcome == LOAD_OUTCOME_EVICTION_FAILED:
                # The sequential-swap guard couldn't confirm the planner
                # (1.5B, port 8081) freed its port — this never even reached
                # can_admit(). Under this project's actual default runtime
                # (`codeydOS start`, which always keeps `plannd` up as a
                # separate always-on process), nothing about a future
                # watchdog tick makes this self-resolve, so this is NOT
                # phrased as transient/self-resolving like DEFERRED above
                # (see NEW-96/U.27) — just state the fact.
                warning(f"7B model not loaded — the planner hasn't freed its port ({reason})")
            elif was_running is False and server is None:
                # Never successfully loaded in the first place (e.g. startup
                # preload failed) — "died" would misdescribe this.
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

    def _preload_primary_model(self):
        """
        Attempt to pre-load the 7B primary model (llama-server on port 8080)
        at daemon startup, and log an outcome-accurate message on failure.

        Extracted out of `_main_loop()` (mirrors the `_watchdog_check_model()`
        extraction from TODO.md 7.4 sub-task 3, for the same reason: a plain
        synchronous method with no `self` dependency is independently
        testable, where the equivalent block inline in the async main loop
        — which also starts the socket server and embed server — is not).

        `ensure_model()` is gate-aware (7.4 sub-tasks 2/3): a `False` return
        here can mean several distinct things, and logging them all as "will
        load on first request" is wrong for at least the gate-denial and
        eviction-failed cases below — none of those will actually resolve on
        a first-request retry. See `core/loader_v2.py`'s `LOAD_OUTCOME_*`
        constants.
        """
        try:
            from core.loader_v2 import (LOAD_OUTCOME_EVICTION_FAILED,
                                         LOAD_OUTCOME_GATE_DENIED,
                                         LOAD_OUTCOME_GATE_DENIED_HARD,
                                         get_loader)

            loader = get_loader()
            if loader.ensure_model():
                info("7B model pre-loaded (port 8080)")
            else:
                # Distinguish a resource-gate denial (real 7.4 outcome —
                # the gate refused admission, nothing "failed") from an
                # actual load failure. "Will load on first request" is a
                # false promise under a denial: the same gate will deny
                # that first-request load too unless headroom changes, or
                # (hard_reject) will never admit this model on this
                # device at all — say so instead of implying the retry
                # will just work.
                outcome = loader.get_last_ensure_outcome()
                reason = loader.get_last_ensure_reason()
                if outcome == LOAD_OUTCOME_GATE_DENIED_HARD:
                    warning(
                        "7B model pre-load denied by resource gate — model "
                        f"exceeds this device's ceiling, will never be admitted: {reason}"
                    )
                elif outcome == LOAD_OUTCOME_GATE_DENIED:
                    warning(
                        f"7B model pre-load denied by resource gate (transient — "
                        f"{reason}); will retry on the next watchdog tick"
                    )
                elif outcome == LOAD_OUTCOME_EVICTION_FAILED:
                    # Same rationale as the watchdog's EVICTION_FAILED branch
                    # (see NEW-96/U.27): under the default `codeydOS start`
                    # runtime, `plannd` stays up as a separate always-on
                    # process, so nothing about a "first request" makes this
                    # self-resolve — don't promise it will. "pre-load:" kept
                    # in the message (unlike the watchdog's) so a log reader
                    # can tell which call site produced it — NEW-96's own
                    # diagnosis depended on distinguishing the startup line
                    # from the 30s-tick line.
                    warning(
                        f"7B model pre-load: not loaded — the planner hasn't freed its port ({reason})"
                    )
                else:
                    warning(
                        f"7B model pre-load failed ({outcome}: {reason}) — "
                        "will load on first request"
                    )
        except Exception as _e:
            # Pre-load is best-effort: startup must not fail the daemon
            # over a model-load problem the watchdog will keep observing/
            # retrying anyway — but the failure is still logged (not a
            # bare `pass`) so it isn't silently lost.
            warning(f"7B model pre-load skipped: {_e}")

    async def _main_loop(self):
        """Main daemon event loop."""
        info("Daemon started")
        self.state.set("daemon_started_at", int(time.time()))
        self.state.log_action("daemon_started", f"PID {os.getpid()}")

        # Start socket server
        server_task = asyncio.create_task(self.server.start())

        # NOTE: We do NOT start executor.start() as a background task.
        # The executor's auto-poll loop and _process_planner_tasks both poll the
        # same SQLite task_queue, creating a race where the same task could be
        # claimed and executed twice.  All task dispatch goes through
        # _process_planner_tasks, which uses try_claim_task() for atomic claiming.

        # Pre-load 7B model (llama-server on port 8080) so it's ready for CLI
        # Skip when using a remote backend — no local server needed
        from utils.config import CODEY_BACKEND as _backend
        from utils.config import is_remote_backend as _is_remote

        if not _is_remote():
            self._preload_primary_model()
        else:
            info(f"Backend: {_backend} — skipping local 7B and 1.5B server startup")

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
                    except Exception:
                        pass

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

            # Sync in-memory planner state. planner.start_task() re-runs the SQLite
            # UPDATE (harmless — overwrites 'running' with 'running') and sets the
            # in-memory task status and _current_task pointer.
            self.planner.start_task(planner_task.id)

            info(f"Planner: dispatching task {planner_task.id}: {planner_task.description[:50]}...")
            try:
                result = await asyncio.wait_for(
                    self.executor._execute_task(planner_task.description),
                    timeout=timeout,
                )
                self.planner.complete_task(planner_task.id, result)
            except asyncio.TimeoutError:
                err = f"Task timed out after {timeout}s"
                error(err)
                self.planner.fail_task(planner_task.id, err)
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

        if not self.state.try_claim_task(db_task["id"]):
            return  # lost the race — another path claimed it

        info(f"Daemon: executing direct task {db_task['id']}: {db_task['description'][:50]}...")
        try:
            result = await asyncio.wait_for(
                self.executor._execute_task(db_task["description"]),
                timeout=timeout,
            )
            self.state.complete_task(db_task["id"], result)
        except asyncio.TimeoutError:
            self.state.fail_task(db_task["id"], f"Task timed out after {timeout}s")
        except Exception as e:
            self.state.fail_task(db_task["id"], str(e))

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


def daemon_health() -> Dict:
    """Get daemon health check."""
    return send_command("health")


def daemon_ping() -> Dict:
    """Ping the daemon."""
    return send_command("ping")


def daemon_shutdown():
    """Request daemon shutdown."""
    return send_command("shutdown")


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
