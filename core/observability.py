#!/usr/bin/env python3
"""
Observability for Codey-OS.

Agent can query its own state:
- Token usage
- Memory contents
- Task queue status
- Model loaded
- Thermal status
- Health metrics

Exposed via /status CLI command and agent-internal queries.
"""

import os
import time
from typing import Dict, Optional

# psutil is optional - will use fallback if not available
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from core.state import get_state_store
from utils.config import CODEY_VERSION, DAEMON_PID_FILE, MODEL_CONFIG


class State:
    """
    Observable state for Codey-OS.

    Provides property accessors for:
    - tokens_used
    - memory_loaded
    - tasks_pending
    - model_active
    - temperature
    - health metrics
    """

    def __init__(self):
        self.state_store = get_state_store()
        if HAS_PSUTIL:
            self._process = psutil.Process(os.getpid())
        else:
            self._process = None

    @property
    def tokens_used(self) -> int:
        """Get total tokens used (from state)."""
        return int(self.state_store.get("tokens_used", 0))

    @tokens_used.setter
    def tokens_used(self, value: int):
        """Set total tokens used."""
        self.state_store.set("tokens_used", value)

    @property
    def memory_loaded(self) -> Dict:
        """Get memory status."""
        try:
            from core.memory_v2 import get_memory

            memory = get_memory()
            return memory.status()
        except (ImportError, AttributeError, TypeError, ValueError):
            return {"error": "Memory not initialized"}

    @property
    def tasks_pending(self) -> int:
        """Get number of pending tasks."""
        try:
            from core.planner_v2 import get_planner

            planner = get_planner()
            return len(planner.get_pending_tasks())
        except (ImportError, AttributeError, TypeError, ValueError):
            # Fallback to state store
            tasks = self.state_store.get_tasks_by_status("pending")
            return len(tasks)

    @property
    def tasks_running(self) -> int:
        """Get number of running tasks."""
        try:
            from core.planner_v2 import get_planner

            planner = get_planner()
            return len(planner.get_running_tasks())
        except (ImportError, AttributeError, TypeError, ValueError):
            tasks = self.state_store.get_tasks_by_status("running")
            return len(tasks)

    @property
    def model_active(self) -> Optional[str]:
        """Get currently active model."""
        try:
            from core.loader_v2 import get_loader

            loader = get_loader()
            return loader.get_loaded_model()
        except (ImportError, AttributeError, TypeError, ValueError):
            return None

    @property
    def model_state(self) -> Dict:
        """Get model state from database."""
        return self.state_store.get_model_state()

    @property
    def temperature(self) -> float:
        """Get current temperature (from model config)."""
        return MODEL_CONFIG.get("temperature", 0.2)

    @property
    def context_size(self) -> int:
        """Get context size (from model config)."""
        return MODEL_CONFIG.get("n_ctx", 4096)

    @property
    def memory_usage(self) -> Dict:
        """
        Get THIS PROCESS'S OWN memory usage (RSS/VMS) — i.e. whatever
        process is calling this property (the CLI, the daemon, a test),
        NOT the daemon's memory if called from outside the daemon, and
        NOT system-wide RAM (NEW-107/NEW-109). This is a deliberate,
        pre-existing split from `core/resource_gate.py`'s
        `read_meminfo()`/`compute_headroom_bytes()` (true system-wide
        RAM, already surfaced separately by `main.py --status`'s
        `"resources"` key) and from
        `ccos/plugins/system/thermal_monitor` (system-wide via
        `core/sysmon.py`) — see
        `ccos/plugins/system/observability/observability.py`'s module
        docstring for the CCOS-side statement of the same split. NEW-107
        originally read this as a bug because the property name/key
        don't say "process-scoped" anywhere in the output; that's now
        corrected in `get_full_status()`'s `"memory"`/`"cpu"` blocks via
        an explicit `"scope"` key, without changing this property's
        return shape (pinned by
        `ccos/plugins/system/observability/test.py::
        test_memory_usage_has_real_data`'s `rss_mb`/`vms_mb` assertion).
        """
        if HAS_PSUTIL and self._process:
            try:
                mem_info = self._process.memory_info()
                return {
                    "rss_mb": round(mem_info.rss / 1024 / 1024, 1),
                    "vms_mb": round(mem_info.vms / 1024 / 1024, 1),
                }
            except (ImportError, AttributeError, TypeError, ValueError):
                pass
        # Fallback: read from /proc on Linux
        try:
            with open(f"/proc/{os.getpid()}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        rss_kb = int(line.split()[1])
                        return {"rss_mb": round(rss_kb / 1024, 1), "vms_mb": 0}
        except (ImportError, AttributeError, TypeError, ValueError):
            pass
        return {"rss_mb": 0, "vms_mb": 0}

    @property
    def cpu_usage(self) -> float:
        """
        Get THIS PROCESS'S OWN CPU usage percentage — same process-scoped
        caveat as `memory_usage` above (NEW-107/NEW-109); see that
        docstring for the full explanation of why this is deliberate and
        not re-pointed at the daemon or the system.
        """
        if HAS_PSUTIL and self._process:
            try:
                return round(self._process.cpu_percent(interval=0.1), 1)
            except (ImportError, AttributeError, TypeError, ValueError):
                pass
        return 0.0

    @property
    def uptime(self) -> int:
        """
        Get daemon uptime in seconds, or 0 if no daemon is currently
        running, or if the currently-running daemon's own start time
        hasn't been recorded yet.

        Gated on `daemon_pid` finding a live daemon (NEW-109): the
        underlying `daemon_started_at` state-store value is written once
        per daemon startup (`core/daemon.py`'s `Daemon._main_loop()`)
        and never cleared on exit, so without this gate it silently kept
        reporting a stale figure from the daemon's last run indefinitely
        after that daemon had exited — the exact "pid: null,
        uptime_seconds: <large non-zero>" contradiction NEW-109 reported
        live (`python main.py --status` with no daemon running).

        Also gated against a narrower, transient version of the same
        contradiction: `core/daemon.py`'s `Daemon.run()` writes
        `DAEMON_PID_FILE` (`write_pid_file()`, line ~2155) BEFORE
        `_main_loop()` records `daemon_started_at` (line ~1091) a little
        later during the same startup — so there's a real, if narrow,
        window where `daemon_pid` already finds a live PID but
        `daemon_started_at` in the state store still holds the
        *previous* run's value. Comparing `daemon_started_at` against
        `DAEMON_PID_FILE`'s own mtime (which is always <= this run's
        `daemon_started_at`, since the file write always happens first)
        catches that case too: a `daemon_started_at` older than the PID
        file's own write time cannot belong to the daemon that wrote
        that file.
        """
        if self.daemon_pid is None:
            return 0
        started_at = int(self.state_store.get("daemon_started_at", 0))
        if not started_at:
            return 0
        try:
            pid_file_mtime = int(DAEMON_PID_FILE.stat().st_mtime)
        except OSError:
            # Can't verify freshness (e.g. the file vanished between the
            # `daemon_pid` liveness check above and this stat) -- fall
            # back to trusting `started_at` rather than guessing stale.
            pid_file_mtime = 0
        if started_at < pid_file_mtime:
            return 0
        return int(time.time()) - started_at

    @property
    def daemon_pid(self) -> Optional[int]:
        """
        Get the real daemon PID, or None if no daemon is currently
        running.

        Previously returned `self._process.pid`, i.e.
        `psutil.Process(os.getpid()).pid` — always the CALLING
        process's own PID (the CLI, a test, whatever imports this
        module), never the daemon's, and unconditionally `None` when
        psutil wasn't installed regardless of whether a daemon was
        actually running (this device has no psutil — see NEW-108).
        That's NEW-109's root cause.

        Reads `utils.config.DAEMON_PID_FILE` instead — the same file
        `core.daemon.write_pid_file()`/`check_pid_file()` already use —
        and verifies the PID is still alive via `os.kill(pid, 0)`,
        mirroring `check_pid_file()`'s own liveness check. Unlike
        `check_pid_file()`, this has no "is this a duplicate of ME"
        dedup logic: if this property is called from inside the daemon
        process itself, finding its own PID in the file is the correct
        answer, not evidence of anything to guard against.
        """
        try:
            with open(DAEMON_PID_FILE, "r") as f:
                pid = int(f.read().strip())
        except (OSError, ValueError):
            # No PID file, unreadable, or corrupt contents -> no daemon
            # running (or we genuinely can't tell) -> None is the
            # honest answer, not a guess.
            return None
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            # Stale PID file (the process that wrote it is gone) -> no
            # daemon running.
            return None
        except PermissionError:
            # Process exists but is owned by a different user -- still
            # evidence *something* is alive at this PID; treat it as
            # running rather than guessing it's dead.
            pass
        return pid

    @property
    def health(self) -> Dict:
        """Get health metrics."""
        return {
            "memory_usage": self.memory_usage,
            "cpu_usage": self.cpu_usage,
            "uptime_seconds": self.uptime,
            "tasks_pending": self.tasks_pending,
            "model_loaded": self.model_active is not None,
        }

    def get_full_status(self) -> Dict:
        """Get complete observability status."""
        return {
            "version": CODEY_VERSION,
            "daemon": {
                "pid": self.daemon_pid,
                "uptime_seconds": self.uptime,
            },
            "model": {
                "active": self.model_active,
                "temperature": self.temperature,
                "context_size": self.context_size,
                "state": self.model_state,
            },
            "tasks": {
                "pending": self.tasks_pending,
                "running": self.tasks_running,
            },
            "memory": {
                "usage": self.memory_usage,
                # NEW-107/NEW-109 labeling fix: "usage" above is the
                # CALLING process's own RSS/VMS, not the daemon's or the
                # system's — see State.memory_usage's docstring. True
                # system-wide RAM is `main.py --status`'s separate
                # "resources" key (core.resource_gate.read_meminfo()).
                "scope": "process",
                "loaded": self.memory_loaded,
            },
            "cpu": {
                "usage": self.cpu_usage,
                "scope": "process",
            },
            "tokens": {
                "used": self.tokens_used,
            },
            "health": self.health,
        }

    def to_dict(self) -> Dict:
        """Alias for get_full_status()."""
        return self.get_full_status()


# Global state instance
_state: Optional[State] = None


def get_state() -> State:
    """Get the global state instance."""
    global _state
    if _state is None:
        _state = State()
    return _state


def reset_state():
    """Reset global state (for testing)."""
    global _state
    if _state:
        _state = None


def status() -> Dict:
    """Get current status (convenience function)."""
    return get_state().get_full_status()
