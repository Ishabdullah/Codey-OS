"""
NEW-118 — `core/daemon.py`'s watchdog tick used to keep running the rest of
that same tick's checks (the 7B model watchdog, the embed-server watchdog)
after `_trigger_shutdown()` had already fired within it. `_trigger_shutdown()`
only flips `self.running = False` and closes the socket server — it does not
raise/return/interrupt its caller — so the fall-through was silent unless the
post-trip checks happened to be independently denied (as they were in the
live-verification run this finding was found from).

This exercises `Daemon._main_loop()` directly (not a smaller extracted unit,
since the watchdog tick's control flow lives inline in that function) with
every real subsystem it touches replaced by lightweight fakes/mocks — no
real socket server, state DB, or subprocess is started (CLAUDE.md rule 2 RAM
discipline: no model server is spawned anywhere in this file).
`should_trip_shutdown()` is patched to report a trip on the very first
watchdog tick and `asyncio.sleep` is patched to a no-op so the 60-tick
watchdog cadence resolves near-instantly instead of needing real wall-clock
time.
"""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import core.daemon as daemon_mod


def _bare_daemon():
    """A Daemon instance with none of __init__'s side effects run, with just
    enough attribute surface for _main_loop() to execute one full tick."""
    d = daemon_mod.Daemon.__new__(daemon_mod.Daemon)
    d.state = MagicMock()
    d.server = MagicMock()
    d.server.server = None  # _trigger_shutdown()'s `if self.server.server:` guard
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


def _fake_trip(should_trip=True, reason="test trip"):
    return SimpleNamespace(should_trip=should_trip, reason=reason)


def test_watchdog_tick_short_circuits_after_trigger_shutdown():
    """The 7B model watchdog and embed-server watchdog must NOT run in the
    same tick that _trigger_shutdown() fires."""
    d = _bare_daemon()
    d._watchdog_check_model = MagicMock()

    fake_embed_server = MagicMock()
    fake_embed_server.is_running.return_value = False  # would otherwise trip a restart

    with patch.object(daemon_mod, "_record_daemon_telemetry_run_start"), \
         patch("core.resource_gate.should_trip_shutdown", return_value=_fake_trip(True)), \
         patch("core.resource_gate.sample_cpu_percent", return_value=None), \
         patch("core.resource_gate.sample_temperature_c", return_value=None), \
         patch("core.resource_gate.is_interactive_session_active", return_value=False), \
         patch("core.embed_server.start_embed_server", return_value=True) as fake_start_embed, \
         patch("core.embed_server.get_embed_server", return_value=fake_embed_server), \
         patch("utils.config.is_remote_backend", return_value=False), \
         patch.object(asyncio, "sleep", new=AsyncMock()):
        asyncio.run(d._main_loop())

    # Model watchdog must not have run this tick (short-circuited).
    d._watchdog_check_model.assert_not_called()
    # Embed-server watchdog must not have run this tick either — is_running()
    # would have reported False and triggered a restart if it had.
    fake_embed_server.is_running.assert_not_called()
    # start_embed_server() IS called once during _main_loop()'s own startup
    # section (before the watchdog loop begins) — that call is fine; assert
    # it was not called a SECOND time by the (short-circuited) watchdog's
    # restart branch.
    assert fake_start_embed.call_count <= 1
    # The tick that decided to shut down must actually have shut down.
    assert d.running is False


def test_watchdog_tick_runs_checks_when_no_trip():
    """Sanity check for the test harness itself: with should_trip_shutdown()
    reporting no trip, the model/embed watchdogs DO run — proves the
    short-circuit in the test above is due to the trip, not the mocking."""
    d = _bare_daemon()
    d._watchdog_check_model = MagicMock()
    # Force the loop to stop after one tick by flipping self.running off
    # from inside the mocked model watchdog itself (called once no-trip).
    def _stop_after_one_tick():
        d.running = False

    d._watchdog_check_model.side_effect = _stop_after_one_tick

    fake_embed_server = MagicMock()
    fake_embed_server.is_running.return_value = True  # already fine, no restart

    with patch.object(daemon_mod, "_record_daemon_telemetry_run_start"), \
         patch("core.resource_gate.should_trip_shutdown", return_value=_fake_trip(False)), \
         patch("core.resource_gate.sample_cpu_percent", return_value=None), \
         patch("core.resource_gate.sample_temperature_c", return_value=None), \
         patch("core.resource_gate.is_interactive_session_active", return_value=False), \
         patch("core.embed_server.start_embed_server", return_value=True), \
         patch("core.embed_server.get_embed_server", return_value=fake_embed_server), \
         patch("utils.config.is_remote_backend", return_value=False), \
         patch.object(asyncio, "sleep", new=AsyncMock()):
        asyncio.run(d._main_loop())

    d._watchdog_check_model.assert_called_once()
    fake_embed_server.is_running.assert_called_once()
