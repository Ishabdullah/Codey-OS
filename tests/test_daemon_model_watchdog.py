"""
core/daemon.py's `Daemon._watchdog_check_model()` — TODO.md 7.4 sub-task 3.

`ensure_model()` (core/loader_v2.py) already routes through the resource
gate as of sub-task 2 (both its branches end in `load_primary()`, which
reserves/confirms/releases a slot) — there is no bypass to close here. What
this sub-task closes is that daemon.py previously discarded `ensure_model()`'s
return value entirely (a bare `_loader.ensure_model()` call whose result was
never read) and unconditionally logged "died — restarting" on any falsy
`get_model_instance()`, including "never loaded at all" and "the resource
gate denied a reservation" — neither of which is a crash.

`_watchdog_check_model()` is a plain method with no dependency on `Daemon`
instance state (`self` is unused inside it), so these tests call it via
`Daemon.__new__(Daemon)` rather than running `Daemon.__init__()`'s full
state-store/planner/background-manager/signal-handler setup, which is far
more than this narrow behavior needs.

No real llama-server subprocess is spawned anywhere in this file (CLAUDE.md
rule 2 RAM discipline) — `core.loader_v2.get_loader()`'s singleton is reset
per test and its `ensure_model()`/`get_last_ensure_outcome()` behavior is
exercised through a lightweight FakeLoader, not the real gate/subprocess
plumbing (already covered by tests/test_loader_resource_gate.py).
"""
from unittest.mock import MagicMock, patch

import pytest

import core.daemon as daemon_mod
import core.loader_v2 as lv


def _bare_daemon():
    """A Daemon instance with none of __init__'s side effects run."""
    return daemon_mod.Daemon.__new__(daemon_mod.Daemon)


class FakeLoader:
    """
    Stand-in for core.loader_v2.ModelLoader exposing exactly the surface
    _watchdog_check_model() uses: get_model_instance(), ensure_model(), and
    the two outcome getters.
    """

    def __init__(self, ensure_result, outcome, reason, instance=None):
        self._ensure_result = ensure_result
        self._outcome = outcome
        self._reason = reason
        self._instance = instance

    def get_model_instance(self):
        return self._instance

    def ensure_model(self):
        return self._ensure_result

    def get_last_ensure_outcome(self):
        return self._outcome

    def get_last_ensure_reason(self):
        return self._reason


def _run_watchdog_with_fake_loader(fake_loader):
    d = _bare_daemon()
    with patch.object(lv, "get_loader", return_value=fake_loader):
        d._watchdog_check_model()


def test_watchdog_success_logs_nothing_alarming(caplog):
    server = MagicMock()
    server.is_running.return_value = True
    fake = FakeLoader(ensure_result=True, outcome=lv.LOAD_OUTCOME_OK, reason="", instance=server)
    with patch.object(daemon_mod, "warning") as mock_warning, patch.object(
        daemon_mod, "info"
    ) as mock_info:
        _run_watchdog_with_fake_loader(fake)
    mock_warning.assert_not_called()


def test_watchdog_gate_denied_hard_does_not_say_died(caplog):
    fake = FakeLoader(
        ensure_result=False,
        outcome=lv.LOAD_OUTCOME_GATE_DENIED_HARD,
        reason="model exceeds device ceiling",
        instance=None,
    )
    with patch.object(daemon_mod, "warning") as mock_warning:
        _run_watchdog_with_fake_loader(fake)

    assert mock_warning.call_count == 1
    msg = mock_warning.call_args[0][0]
    assert "died" not in msg
    assert "permanently denies" in msg


def test_watchdog_gate_denied_transient_does_not_say_died():
    server = MagicMock()
    server.is_running.return_value = True
    fake = FakeLoader(
        ensure_result=False,
        outcome=lv.LOAD_OUTCOME_GATE_DENIED,
        reason="no headroom",
        instance=server,
    )
    with patch.object(daemon_mod, "warning") as mock_warning:
        _run_watchdog_with_fake_loader(fake)

    assert mock_warning.call_count == 1
    msg = mock_warning.call_args[0][0]
    assert "died" not in msg
    assert "transient" in msg


def test_watchdog_deferred_logs_info_not_warning():
    fake = FakeLoader(
        ensure_result=False,
        outcome=lv.LOAD_OUTCOME_DEFERRED,
        reason="planner swap in flight",
        instance=None,
    )
    with patch.object(daemon_mod, "warning") as mock_warning, patch.object(
        daemon_mod, "info"
    ) as mock_info:
        _run_watchdog_with_fake_loader(fake)

    mock_warning.assert_not_called()
    mock_info.assert_called()


def test_watchdog_never_loaded_says_not_loaded_not_died():
    """No server instance at all (e.g. startup preload never succeeded) --
    must not claim the server "died"; it never came up in the first place."""
    fake = FakeLoader(
        ensure_result=False,
        outcome=lv.LOAD_OUTCOME_SPAWN_FAILED,
        reason="llama-server process failed to start",
        instance=None,
    )
    with patch.object(daemon_mod, "warning") as mock_warning:
        _run_watchdog_with_fake_loader(fake)

    assert mock_warning.call_count == 1
    msg = mock_warning.call_args[0][0]
    assert "not loaded" in msg
    assert "died" not in msg


def test_watchdog_real_crash_still_says_died():
    """A server that WAS running and now isn't, with ensure_model() also
    failing to restart it -- this is the genuine "died, restart failed" case
    the original (pre-sub-task-3) message described; must still be reported
    as such, not lost in the new outcome-specific branches."""
    server = MagicMock()
    server.is_running.return_value = False  # process died
    fake = FakeLoader(
        ensure_result=False,
        outcome=lv.LOAD_OUTCOME_SPAWN_FAILED,
        reason="llama-server process failed to start",
        instance=server,
    )
    with patch.object(daemon_mod, "warning") as mock_warning:
        _run_watchdog_with_fake_loader(fake)

    assert mock_warning.call_count == 1
    msg = mock_warning.call_args[0][0]
    assert "died" in msg


def test_watchdog_swallows_and_logs_unexpected_exception_not_bare_pass():
    """The watchdog must never crash the daemon's main loop, but an
    unexpected exception must be LOGGED, not silently swallowed (CLAUDE.md:
    exception handling around safety-relevant code must not silently
    swallow failures without a comment explaining why that's safe -- this
    path has no such justification, so it must log)."""
    d = _bare_daemon()
    with patch.object(lv, "get_loader", side_effect=RuntimeError("boom")), patch.object(
        daemon_mod, "warning"
    ) as mock_warning:
        d._watchdog_check_model()  # must not raise

    assert mock_warning.call_count == 1
    assert "boom" in mock_warning.call_args[0][0]
