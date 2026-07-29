"""
Thermal Monitor Plugin — thin CCOS adapter over core/sysmon.py and
core/thermal.py.

Wraps the existing system monitor and thermal manager as capabilities
without duplicating any of their logic. All actual sampling and
throttling logic stays in core/sysmon.py and core/thermal.py.

core/sysmon.py's SystemMonitor is the shared data source for the
"unified system dashboard" requirement (CODEY_OS_MASTER_VISION.md
Section 3) — GUI and TUI must read the same live numbers, so
`monitor_snapshot` returns a plain dict rather than the Rich-formatted
bar. `monitor_render_text` exposes the TUI bar too, as plain text,
for callers that just want to display it.

`start()`/`stop()` on the monitor are intentionally NOT exposed as
capabilities. The monitor is a per-process singleton; in the CCOS
process it's typically not already running the way it is under
main.py, so `monitor_snapshot` calls `start()` itself (idempotent —
a no-op if the sampler thread is already alive) to guarantee real
data on first use, without handing callers a way to stop a sampler
some other part of the process may depend on.
"""

from ccos.plugins._pathutil import ensure_repo_root_on_path

ensure_repo_root_on_path()

from core.sysmon import get_monitor
from core.thermal import (
    end_inference,
    get_current_threads,
    get_thermal_status,
    is_throttled,
    reset_thermal,
    start_inference,
)


def monitor_snapshot() -> dict:
    """Live structured snapshot: cpu, ram_used, ram_total, temp, battery_pct, battery_charging."""
    monitor = get_monitor()
    monitor.start()  # idempotent — seeds real data if the sampler isn't already running
    return monitor.snapshot


def monitor_render_text() -> str:
    """TUI-formatted CPU/RAM/temp stats bar, as plain text."""
    monitor = get_monitor()
    monitor.start()
    return monitor.render().plain


def thermal_status() -> dict:
    """Thermal management status: inference time, thread counts, warnings, throttled flag."""
    return get_thermal_status()


def thermal_is_throttled() -> bool:
    """Whether thermal throttling is currently reducing inference thread count."""
    return is_throttled()


def thermal_current_threads() -> int:
    """Current inference thread count (may be thermally reduced)."""
    return get_current_threads()


def thermal_start_inference() -> None:
    """Mark the start of an inference run for thermal tracking."""
    start_inference()


def thermal_end_inference() -> None:
    """Mark the end of an inference run and evaluate thermal thresholds."""
    end_inference()


def thermal_reset() -> None:
    """Reset thermal tracking (drops the global thermal manager singleton)."""
    reset_thermal()


def test() -> bool:
    """Plugin self-test — verify a read-only capability runs without raising."""
    snap = monitor_snapshot()
    assert isinstance(snap, dict), "Expected dict"
    assert "cpu" in snap, "Missing cpu"
    return True
