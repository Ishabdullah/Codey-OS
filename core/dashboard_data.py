#!/usr/bin/env python3
"""
Shared dashboard data layer for the TUI and GUI.

CODEY_OS_MASTER_VISION.md Section 3 ("Unified system dashboard") and
Section 6 require the GUI and TUI to read CPU/RAM/temperature from the
same source instead of each maintaining its own status logic. This
module is that shared source: it calls through the CCOS capability
layer (`system.monitor_snapshot`, backed by the thermal_monitor plugin,
which itself just wraps core/sysmon.py's SystemMonitor singleton)
instead of main.py/core/recursive.py holding a direct SystemMonitor
reference and gui/server.py parsing /proc/meminfo on its own.

Only CPU/RAM/temperature are covered here — that's all the TUI status
bar and GUI metrics currently display. observability_full_status
reports this *process's own* CPU/RSS usage (a different question,
see ccos/plugins/system/observability/observability.py's docstring),
not the system-wide numbers the dashboard shows, so it isn't used here.
"""

from typing import Dict

from rich.text import Text

_plugins = None


def _plugin_manager():
    global _plugins
    if _plugins is None:
        from ccos.core.plugin_manager import get_plugin_manager

        _plugins = get_plugin_manager()
        _plugins.load_all()
    return _plugins


def get_snapshot() -> Dict:
    """cpu, ram_used, ram_total, temp, battery_pct, battery_charging — via system.monitor_snapshot."""
    return _plugin_manager().call_capability("system.monitor_snapshot")


def get_render_text() -> Text:
    """Rich Text CPU/RAM/Temp stats bar (TUI status bar), from the capability-sourced snapshot."""
    from core.sysmon import render_snapshot

    return render_snapshot(get_snapshot())
