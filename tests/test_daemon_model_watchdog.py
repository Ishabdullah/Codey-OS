"""
core/daemon.py's `Daemon._watchdog_check_model()` (TODO.md 7.4 sub-task 3,
amended by 7.4b sub-task C's NEW-145 fix) — the 30s watchdog tick that turns
`ensure_model()`'s outcome into a log message.

`ensure_model()` (core/loader_v2.py) already routes through the resource
gate as of sub-task 2 (both its branches end in `load_primary()`, which
reserves/confirms/releases a slot) — there is no bypass to close here. What
sub-task 3 closed is that daemon.py previously discarded `ensure_model()`'s
return value entirely (a bare `_loader.ensure_model()` call whose result was
never read) and unconditionally logged "died — restarting" on any falsy
`get_model_instance()`, including "never loaded at all" and "the resource
gate denied a reservation" — neither of which is a crash.

U.27/NEW-96 closed a follow-on gap: `LOAD_OUTCOME_EVICTION_FAILED` (the
sequential-swap guard failing to confirm the planner freed port 8081 before
the primary's cold-load, which happens BEFORE `can_admit()` is ever reached)
wasn't one of the outcomes the watchdog named explicitly, so it fell through
to the generic fallback branch. The watchdog's generic fallback is honest
("attempted load, still not running") and was left alone; the watchdog now
names `LOAD_OUTCOME_EVICTION_FAILED` explicitly with an accurate,
non-promising message.

7.4b sub-task C's NEW-145 fix (2026-08-11) removed the daemon's own eager
startup preload of the coder (7B) model entirely — it always ran before any
TUI session could register itself as interactive
(`is_interactive_session_active()`), so it always spawned the coder at the
background 16384 `n_ctx` ceiling, and the interactive TUI then reused that
same under-provisioned server instead of getting its own 32768 one. The
coder now loads lazily on first real request. This surfaced the SAME race
on the watchdog's own 30s tick — the daemon's actual steady state under
`codey-start`, since a running daemon skips the one-time startup preload
path entirely (`codey-start` only starts a daemon when none is running) —
because the watchdog called `ensure_model()` unconditionally every tick with
no distinction between "was loaded and died, restart it" and "never loaded,
nobody has asked yet, leave it alone." The watchdog now gates on
`ModelLoader.was_ever_loaded()` (set at `load_primary()`'s success point,
which is the convergence point for both a genuine spawn and the port-in-use
adoption/reuse branch) before calling `ensure_model()` at all.

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

    def __init__(self, ensure_result, outcome, reason, instance=None, ever_loaded=True):
        self._ensure_result = ensure_result
        self._outcome = outcome
        self._reason = reason
        self._instance = instance
        # Defaults True: every existing test in this file predates the
        # NEW-145 gate and is exercising "was loaded before, is ensure_model()
        # called and its outcome reported correctly" — not the new
        # never-loaded-and-unrequested case, which has its own dedicated
        # test below with ever_loaded=False.
        self._ever_loaded = ever_loaded

    def get_model_instance(self):
        return self._instance

    def ensure_model(self):
        return self._ensure_result

    def get_last_ensure_outcome(self):
        return self._outcome

    def get_last_ensure_reason(self):
        return self._reason

    def was_ever_loaded(self):
        return self._ever_loaded


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


def test_watchdog_eviction_failed_names_the_outcome_and_does_not_promise_retry():
    """U.27/NEW-96: eviction_failed must be its own named branch (not the
    generic fallback), logged as a warning (not self-resolving like
    DEFERRED), and must not claim the server "died" -- it never got past
    the sequential-swap guard to attempt a real load."""
    fake = FakeLoader(
        ensure_result=False,
        outcome=lv.LOAD_OUTCOME_EVICTION_FAILED,
        reason="could not confirm the planner (1.5B) freed its port before "
        "loading the primary (7B) — sequential-swap guard",
        instance=None,
    )
    with patch.object(daemon_mod, "warning") as mock_warning:
        _run_watchdog_with_fake_loader(fake)

    assert mock_warning.call_count == 1
    msg = mock_warning.call_args[0][0]
    assert "died" not in msg
    assert "planner hasn't freed its port" in msg
    assert "will load on first request" not in msg


def test_watchdog_eviction_failed_takes_precedence_over_died_branch():
    """If the primary WAS running and then a cold-load retry hits a failed
    eviction (e.g. the planner started re-occupying the port after a
    restart), the named EVICTION_FAILED branch must still win over the
    generic "server died" fallback -- same precedence the other three named
    outcomes (GATE_DENIED_HARD/GATE_DENIED/DEFERRED) already have above it,
    intentional per the outcome-naming pattern this task follows."""
    server = MagicMock()
    server.is_running.return_value = False
    fake = FakeLoader(
        ensure_result=False,
        outcome=lv.LOAD_OUTCOME_EVICTION_FAILED,
        reason="could not confirm the planner (1.5B) freed its port before "
        "loading the primary (7B) — sequential-swap guard",
        instance=server,
    )
    with patch.object(daemon_mod, "warning") as mock_warning:
        _run_watchdog_with_fake_loader(fake)

    assert mock_warning.call_count == 1
    msg = mock_warning.call_args[0][0]
    assert "died" not in msg
    assert "planner hasn't freed its port" in msg


def test_watchdog_no_current_instance_but_loaded_before_says_not_loaded_not_died():
    """No server instance right now (e.g. this loader loaded/adopted a
    server before, unload() cleared the instance, and this reload attempt
    also failed -- was_ever_loaded() stays True, that's what gets us past
    the new NEW-145 gate and into ensure_model() at all) -- must not claim
    the server "died"; there's no currently-known process that stopped
    running."""
    fake = FakeLoader(
        ensure_result=False,
        outcome=lv.LOAD_OUTCOME_SPAWN_FAILED,
        reason="llama-server process failed to start",
        instance=None,
        ever_loaded=True,
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


def test_watchdog_never_loaded_and_unrequested_does_nothing():
    """7.4b sub-task C's NEW-145 fix: a coder that has never been spawned
    NOR adopted by this loader (was_ever_loaded() False) and isn't running
    now must be left alone -- ensure_model() must NOT be called, since
    calling it here would reproduce NEW-145's race (spawning the coder at
    the background n_ctx ceiling before any TUI session can register as
    interactive)."""
    fake = FakeLoader(
        ensure_result=True,  # would succeed if called -- must not be called
        outcome=lv.LOAD_OUTCOME_OK,
        reason="",
        instance=None,
        ever_loaded=False,
    )
    with patch.object(fake, "ensure_model") as mock_ensure, patch.object(
        daemon_mod, "warning"
    ) as mock_warning, patch.object(daemon_mod, "info") as mock_info:
        _run_watchdog_with_fake_loader(fake)

    mock_ensure.assert_not_called()
    mock_warning.assert_not_called()


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
