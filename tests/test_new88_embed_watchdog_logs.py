"""
NEW-88 — `core/daemon.py`'s embed-server watchdog block (inside
`Daemon._main_loop()`'s watchdog tick) used to swallow any exception with a
bare `except Exception: pass` — no log, no trace. Fixed to log at warning
instead, matching the sibling 7B model watchdog's already-established
posture in the same watchdog loop.

Exercises `_main_loop()` directly (same harness as
`tests/test_new118_shutdown_short_circuit.py` — see that file's docstring
for why: the watchdog tick's control flow is inline, not a separately
callable unit) with `get_embed_server()` raising, and asserts the failure is
logged rather than silently discarded.
"""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import core.daemon as daemon_mod


def _bare_daemon():
    d = daemon_mod.Daemon.__new__(daemon_mod.Daemon)
    d.state = MagicMock()
    d.server = MagicMock()
    d.server.server = None
    d.server.start = AsyncMock()
    d.server.stop = AsyncMock()
    d.background = MagicMock()
    d.file_watch = MagicMock()
    d.running = True
    d._reload_requested = False
    d._dispatch_battery_cache_ts = 0.0
    d._dispatch_battery_cache_value = (None, False)
    d._gate_dedup = {}
    d._interactive_active_last = None
    d._interactive_state_since_mono = time.monotonic()
    d._deferral_state = {}
    d._process_planner_tasks = AsyncMock()
    return d


def _fake_trip(should_trip=False, reason="no trip"):
    return SimpleNamespace(should_trip=should_trip, reason=reason)


def test_embed_watchdog_exception_is_logged_not_silently_swallowed():
    d = _bare_daemon()

    def _stop_after_one_tick():
        d.running = False

    d._watchdog_check_model = MagicMock(side_effect=_stop_after_one_tick)

    def _boom():
        raise RuntimeError("embed server probe failed")

    with patch.object(daemon_mod, "_record_daemon_telemetry_run_start"), \
         patch("core.resource_gate.should_trip_shutdown", return_value=_fake_trip(False)), \
         patch("core.resource_gate.sample_cpu_percent", return_value=None), \
         patch("core.resource_gate.sample_temperature_c", return_value=None), \
         patch("core.resource_gate.is_interactive_session_active", return_value=False), \
         patch("core.embed_server.start_embed_server", return_value=True), \
         patch("core.embed_server.get_embed_server", side_effect=_boom), \
         patch("utils.config.is_remote_backend", return_value=False), \
         patch.object(daemon_mod, "warning") as fake_warning, \
         patch.object(asyncio, "sleep", new=AsyncMock()):
        asyncio.run(d._main_loop())

    logged = " ".join(str(c.args[0]) for c in fake_warning.call_args_list if c.args)
    assert "embed server probe failed" in logged.lower()
