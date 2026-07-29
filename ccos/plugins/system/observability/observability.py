"""
Observability Plugin — thin CCOS adapter over core/observability.py.

core/observability.py's `State` class (accessed via the module-level
`get_state()` singleton) is the "self-status introspection" capability
listed in CODEY_OS_MASTER_VISION.md Section 3 — token usage, memory
status, task queue depth, active model, temperature/context size,
process CPU/memory usage, daemon uptime/PID, and rolled-up health. Every
property on `State` is a read-only computed value; there is no
mutation involved in reading them.

Overlap check against ccos/plugins/system/thermal_monitor (Phase 2 item
4, wraps core/sysmon.py + core/thermal.py): thermal_monitor's
`monitor_snapshot()` reports *system-wide* CPU%, RAM used/total, and
temperature via core/sysmon.py's SystemMonitor (reads /proc, battery,
thermal zones). This plugin's `cpu_usage` and `memory_usage` instead
report *this process's own* CPU% and RSS/VMS via `psutil.Process(pid)`
(or a /proc/<pid>/status fallback) — a different question (how much of
the machine is Codey's own process using) answered a different way, not
a duplicate read of the same data. Both are kept as independent
capabilities; `full_status`/`health` below assemble the process-level
numbers, and a caller wanting the system-wide picture goes to
`thermal_monitor.monitor_snapshot` instead.

`get_full_status()`, `to_dict()`, and the module-level `status()` are
all identical (`to_dict` is a literal alias for `get_full_status`, and
`status()` just calls `get_state().get_full_status()`) — rather than
exposing three near-identical capabilities, only `full_status` is
exposed here, backed by `get_full_status()`.

`reset_state()` drops the process-wide `State` singleton so the next
`get_state()` call rebuilds it (re-opening the psutil Process handle,
etc.). It's included as `reset_state` despite being the one mutating
call in this module: nothing in the codebase currently depends on
`core/observability.py`'s state (per the task, there are no existing
callers at all), so there's nothing to protect from a reset, and it's
useful for tests exercising this plugin or a future `/status` wiring.
"""
from ccos.plugins._pathutil import ensure_repo_root_on_path

ensure_repo_root_on_path()

from typing import Dict, Optional

from core.observability import get_state
from core.observability import reset_state as _reset_state


def tokens_used() -> int:
    """Total tokens used so far, from the shared state store."""
    return get_state().tokens_used


def memory_loaded() -> Dict:
    """Five-tier memory system's status dict (or an error dict if uninitialized)."""
    return get_state().memory_loaded


def tasks_pending() -> int:
    """Number of pending tasks in the task queue/planner."""
    return get_state().tasks_pending


def tasks_running() -> int:
    """Number of currently running tasks."""
    return get_state().tasks_running


def model_active() -> Optional[str]:
    """Name of the currently loaded/active model, or None."""
    return get_state().model_active


def model_state() -> Dict:
    """Model state dict from the shared state store."""
    return get_state().model_state


def temperature() -> float:
    """Configured inference temperature."""
    return get_state().temperature


def context_size() -> int:
    """Configured context window size (n_ctx)."""
    return get_state().context_size


def memory_usage() -> Dict:
    """This process's own RSS/VMS memory usage in MB (not system-wide)."""
    return get_state().memory_usage


def cpu_usage() -> float:
    """This process's own CPU usage percentage (not system-wide)."""
    return get_state().cpu_usage


def uptime() -> int:
    """Daemon uptime in seconds, or 0 if no daemon start time is recorded."""
    return get_state().uptime


def daemon_pid() -> Optional[int]:
    """PID of this process, or None if psutil isn't available."""
    return get_state().daemon_pid


def health() -> Dict:
    """Rolled-up health summary: memory usage, CPU usage, uptime, pending tasks, model-loaded flag."""
    return get_state().health


def full_status() -> Dict:
    """Complete observability status (version, daemon, model, tasks, memory, cpu, tokens, health)."""
    return get_state().get_full_status()


def reset_state() -> None:
    """Drop the process-wide State singleton so the next call rebuilds it. Minor mutation; see module docstring."""
    _reset_state()


def test() -> bool:
    """Plugin self-test — verify a read-only capability runs without raising."""
    status = full_status()
    assert isinstance(status, dict), "Expected dict"
    assert "health" in status, "Missing health"
    return True
