"""
NEW-86 regression tests: `core/embed_server.py`'s `_kill_port_occupant()`
must re-verify the target PID is still the port's occupant immediately
before the kill, not just at identification time, so a PID-recycling
race can't make it kill an unrelated process.

Scenario under test: `_find_port_occupant_pid()` first identifies PID
4242 as the port's occupant. Before the kill actually runs, that real
occupant exits naturally and PID 4242 either gets recycled to an
unrelated process (a second call to `_find_port_occupant_pid()`
resolves a *different* PID, or none at all) — simulated here via
`side_effect` so the two calls `_kill_port_occupant()` makes return
different results, exactly like two real, temporally-separated /proc
scans would if the underlying kernel state changed in between. A naive
"cmdline read twice, a few microseconds apart" check would NOT catch
this (both reads would already see the same, already-recycled process
and appear to "match") — that's why the fix re-derives port ownership
itself as the second check, not a snapshot compared only against
itself.

Coverage caveat (see `core/embed_server.py`'s `_kill_port_occupant()`
comment for the full explanation): these tests mock
`_find_port_occupant_pid()` wholesale, so they exercise the
re-verification *mechanism* but not which of its two internal paths
(the `/proc/net/tcp` socket scan, vs. the registered-slot fallback) is
actually live on this device — that's unverified here (confirmed
`/proc/net/tcp` is permission-denied in this dev sandbox) and needs
live-verifier confirmation.
"""
from unittest.mock import patch

from core.embed_server import EmbedServer


class TestKillPortOccupantPidRecycleGuard:
    def test_aborts_kill_when_reverify_resolves_a_different_pid(self):
        """Identify PID 4242, but by the time we re-check immediately
        before the kill, the port's occupant now resolves to a
        *different* PID (4242 was recycled to some unrelated process
        that is NOT the port's occupant). Must never kill 4242."""
        srv = EmbedServer()
        with patch.object(
            srv, "_find_port_occupant_pid", side_effect=[4242, 9999]
        ), patch("os.kill") as fake_kill, patch("subprocess.run") as fake_run, patch(
            "time.sleep"
        ), patch.object(srv, "_port_is_bound", return_value=False):
            ok = srv._kill_port_occupant()

        # Must not have blindly killed PID 4242 — it's no longer
        # confirmed to be the port's occupant.
        for call in fake_kill.call_args_list:
            assert call.args[:2] != (4242, 9), "must never kill the stale PID 4242"
        fake_run.assert_not_called()
        # Port already came free on its own (the real occupant's own
        # exit), so this correctly reports success without ever having
        # touched the wrong process.
        assert ok is True

    def test_reports_failure_when_reverify_fails_and_port_stays_occupied(self):
        """Same recycling race, but the port is still occupied afterward
        (by the same or a different unrelated process) — must fail
        loudly, not silently report success, and still must never kill
        PID 4242."""
        srv = EmbedServer()
        with patch.object(
            srv, "_find_port_occupant_pid", side_effect=[4242, 9999]
        ), patch("os.kill") as fake_kill, patch("subprocess.run") as fake_run, patch(
            "time.sleep"
        ), patch.object(srv, "_port_is_bound", return_value=True):
            ok = srv._kill_port_occupant()

        for call in fake_kill.call_args_list:
            assert call.args[:2] != (4242, 9)
        fake_run.assert_not_called()
        assert ok is False

    def test_aborts_kill_when_reverify_finds_no_occupant_at_all(self):
        """The real occupant simply exited and nothing new is bound to
        the port yet at re-check time — `_find_port_occupant_pid()`
        resolves to `None` the second time. Must not kill the original
        PID on the strength of the first, now-stale identification."""
        srv = EmbedServer()
        with patch.object(
            srv, "_find_port_occupant_pid", side_effect=[4242, None]
        ), patch("os.kill") as fake_kill, patch("time.sleep"), patch.object(
            srv, "_port_is_bound", return_value=False
        ):
            ok = srv._kill_port_occupant()

        for call in fake_kill.call_args_list:
            assert call.args[:2] != (4242, 9)
        assert ok is True  # port already free on its own

    def test_kills_when_reverify_resolves_the_same_pid(self):
        """Sanity/control: the normal, non-recycled path (the same PID
        resolves both times, whether that's a real llama-server or any
        other legitimate port occupant — `_find_port_occupant_pid()`'s
        occupant need not be our own llama-server, its own docstring
        says so, and this re-verification check doesn't care either)
        must still proceed to kill exactly like before NEW-86's fix."""
        srv = EmbedServer()
        with patch.object(
            srv, "_find_port_occupant_pid", return_value=4242
        ), patch("os.kill") as fake_kill, patch("time.sleep"), patch.object(
            srv, "_port_is_bound", return_value=False
        ):
            ok = srv._kill_port_occupant()

        fake_kill.assert_called_once_with(4242, 9)
        assert ok is True
