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
("attempted load, still not running") and was left alone; the watchdog then
named `LOAD_OUTCOME_EVICTION_FAILED` explicitly with an accurate,
non-promising message.

M1-D (2026-08-23): `LOAD_OUTCOME_EVICTION_FAILED` and the eviction step
that produced it are both removed along with core/planner_loader.py —
`ensure_model()`'s cold-load branch now goes straight to `load_primary()`,
so this outcome can no longer occur. The two tests that pinned its watchdog
handling (`test_watchdog_eviction_failed_names_the_outcome_and_does_not_
promise_retry`, `test_watchdog_eviction_failed_takes_precedence_over_
died_branch`) are removed accordingly, not adapted — there is no scenario
left for them to exercise.

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
nobody has asked yet, leave it alone." The watchdog originally gated on
`ModelLoader.was_ever_loaded()`, set at `load_primary()`'s success point for
BOTH a genuine spawn and the port-in-use adoption/reuse branch.

**NEW-152 (2026-08-13, code-reviewer retroactive pass): that combined flag
was itself sticky-broken.** Under the normal `codey-start` steady state (TUI
spawns the coder; the daemon's own loader later adopts it via its first
background dispatch), the flag went True on the first adoption and never
reset, so the gate stopped protecting the daemon from that point on — an
ordinary TUI session ending (not a crash) still fell through to
`ensure_model()` and respawned the coder at the 16384 background ceiling.
The watchdog now gates on `ModelLoader.was_ever_spawned()` instead, which
answers "did this loader's own subprocess.Popen() actually run" and
deliberately excludes adoption — see `was_ever_spawned()`'s own docstring
in `core/loader_v2.py` for the full case-by-case breakdown, including the
accepted reduction in crash-restart coverage for adopted-only coders.

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

    def __init__(self, ensure_result, outcome, reason, instance=None, ever_spawned=True):
        self._ensure_result = ensure_result
        self._outcome = outcome
        self._reason = reason
        self._instance = instance
        # Defaults True: every existing test in this file predates the
        # NEW-145 gate and is exercising "was loaded before, is ensure_model()
        # called and its outcome reported correctly" — not the new
        # never-spawned-and-unrequested case, which has its own dedicated
        # test below with ever_spawned=False. NEW-152 renamed this from
        # ever_loaded/was_ever_loaded() to ever_spawned/was_ever_spawned() —
        # the daemon-visible behavior this FakeLoader exercises is identical
        # either way (neither the daemon nor this test file distinguishes
        # "never loaded at all" from "only ever adopted" — that distinction
        # lives in core/loader_v2.py and is covered by
        # tests/test_loader_resource_gate.py's reuse/adoption test instead).
        self._ever_spawned = ever_spawned

    def get_model_instance(self):
        return self._instance

    def ensure_model(self):
        return self._ensure_result

    def get_last_ensure_outcome(self):
        return self._outcome

    def get_last_ensure_reason(self):
        return self._reason

    def was_ever_spawned(self):
        return self._ever_spawned


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


def test_watchdog_no_current_instance_but_loaded_before_says_not_loaded_not_died():
    """No server instance right now (e.g. this loader genuinely spawned a
    server before, unload() cleared the instance, and this reload attempt
    also failed -- was_ever_spawned() stays True, that's what gets us past
    the NEW-145/NEW-152 gate and into ensure_model() at all) -- must not
    claim the server "died"; there's no currently-known process that
    stopped running."""
    fake = FakeLoader(
        ensure_result=False,
        outcome=lv.LOAD_OUTCOME_SPAWN_FAILED,
        reason="llama-server process failed to start",
        instance=None,
        ever_spawned=True,
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
    by this loader (was_ever_spawned() False) and isn't running now must be
    left alone -- ensure_model() must NOT be called, since calling it here
    would reproduce NEW-145's race (spawning the coder at the background
    n_ctx ceiling before any TUI session can register as interactive)."""
    fake = FakeLoader(
        ensure_result=True,  # would succeed if called -- must not be called
        outcome=lv.LOAD_OUTCOME_OK,
        reason="",
        instance=None,
        ever_spawned=False,
    )
    with patch.object(fake, "ensure_model") as mock_ensure, patch.object(
        daemon_mod, "warning"
    ) as mock_warning, patch.object(daemon_mod, "info") as mock_info:
        _run_watchdog_with_fake_loader(fake)

    mock_ensure.assert_not_called()
    mock_warning.assert_not_called()


def test_watchdog_adopted_only_not_running_no_interactive_does_nothing():
    """NEW-152: the exact gap the retroactive code-reviewer pass found.
    was_ever_spawned() is False (this loader has only ever ADOPTED a
    TUI-spawned coder via load_primary()'s port-in-use branch, or never
    loaded one at all -- both look identical to the watchdog, on purpose;
    see core/loader_v2.py's was_ever_spawned() docstring). The coder isn't
    running now (e.g. the TUI session that owned it simply exited). The
    watchdog must NOT call ensure_model() and must NOT respawn the coder at
    the background ceiling just because a coder existed once -- that
    respawn-on-adoption-then-exit path was NEW-152's exact reproduction of
    NEW-145's original symptom, through adoption instead of eager preload."""
    fake = FakeLoader(
        ensure_result=True,  # would succeed if called -- must not be called
        outcome=lv.LOAD_OUTCOME_OK,
        reason="",
        instance=None,
        ever_spawned=False,
    )
    with patch.object(fake, "ensure_model") as mock_ensure, patch.object(
        daemon_mod, "warning"
    ) as mock_warning:
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
