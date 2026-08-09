"""
main.py's `_load_primary_with_gate_recovery()` / `_is_unrecovered_gate_denial()`
— TODO.md 7.4 sub-task 5 (the NEW-69 recovery path).

`main.py`'s four direct `loader.load_primary()` CLI call sites (repl(),
args.init/--tdd/--fix) already go through the resource gate's admission
check today, since `load_primary()` itself reserves a slot internally
(sub-tasks 1-2). What this sub-task adds is a recovery path for what
happens when that reservation is DENIED: if a daemon is running, ask it
to free a slot via the `release_model_slot` socket command and retry the
load exactly once; otherwise (or if the daemon declines/can't be reached)
report the original gate denial as a real, clear failure.

No real llama-server subprocess, no real daemon socket, and no real
resource_gate state store are touched anywhere in this file (CLAUDE.md
rule 2 RAM discipline) — the loader and `core.daemon.send_command()` are
both faked/patched.
"""
from unittest.mock import patch

import pytest

import main as main_mod
from core.daemon import (
    RELEASE_OUTCOME_ALREADY_UNLOADED,
    RELEASE_OUTCOME_BUSY_TASK,
    RELEASE_OUTCOME_COOLDOWN,
    RELEASE_OUTCOME_RELEASED,
    RELEASE_OUTCOME_UNCONFIRMED,
)
from core.loader_v2 import (
    LOAD_OUTCOME_ERROR,
    LOAD_OUTCOME_GATE_DENIED,
    LOAD_OUTCOME_GATE_DENIED_HARD,
    LOAD_OUTCOME_OK,
    LOAD_OUTCOME_SPAWN_FAILED,
)


class FakeLoader:
    """
    Stand-in for core.loader_v2.ModelLoader exposing exactly the surface
    `_load_primary_with_gate_recovery()` uses: `load_primary()` and the
    two outcome getters. `load_primary()` is scripted via a list of
    (result, outcome, reason) tuples consumed in call order, so tests can
    assert it's called AT MOST ONCE more (the single retry) after a gate
    denial.
    """

    def __init__(self, script):
        self._script = list(script)
        self.call_count = 0
        self._outcome = None
        self._reason = None

    def load_primary(self) -> bool:
        self.call_count += 1
        if not self._script:
            raise AssertionError("load_primary() called more times than scripted — "
                                  "sub-task 5 must retry at most once")
        result, outcome, reason = self._script.pop(0)
        self._outcome = outcome
        self._reason = reason
        return result

    def get_last_ensure_outcome(self) -> str:
        return self._outcome

    def get_last_ensure_reason(self) -> str:
        return self._reason


# ---------------------------------------------------------------------------
# _load_primary_with_gate_recovery()
# ---------------------------------------------------------------------------


def test_success_on_first_try_no_daemon_contact():
    loader = FakeLoader([(True, LOAD_OUTCOME_OK, "")])
    with patch("main._daemon_is_running") as daemon_check:
        assert main_mod._load_primary_with_gate_recovery(loader) is True
    daemon_check.assert_not_called()
    assert loader.call_count == 1


def test_non_gate_failure_not_retried_no_daemon_contact():
    """Spawn failure / missing file — not a gate denial, no recovery dance."""
    for outcome in (LOAD_OUTCOME_SPAWN_FAILED, LOAD_OUTCOME_ERROR, LOAD_OUTCOME_GATE_DENIED_HARD):
        loader = FakeLoader([(False, outcome, "boom")])
        with patch("main._daemon_is_running") as daemon_check:
            assert main_mod._load_primary_with_gate_recovery(loader) is False
        daemon_check.assert_not_called()
        assert loader.call_count == 1


def test_gate_denied_no_daemon_running_reports_failure_no_retry():
    loader = FakeLoader([(False, LOAD_OUTCOME_GATE_DENIED, "headroom too low")])
    with patch("main._daemon_is_running", return_value=False):
        assert main_mod._load_primary_with_gate_recovery(loader) is False
    assert loader.call_count == 1


def test_gate_denied_daemon_releases_retry_succeeds():
    loader = FakeLoader(
        [
            (False, LOAD_OUTCOME_GATE_DENIED, "headroom too low"),
            (True, LOAD_OUTCOME_OK, ""),
        ]
    )
    response = {"status": "ok", "released": True, "outcome": RELEASE_OUTCOME_RELEASED, "message": "ok"}
    with patch("main._daemon_is_running", return_value=True), patch(
        "core.daemon.send_command", return_value=response
    ) as send:
        assert main_mod._load_primary_with_gate_recovery(loader) is True
    assert loader.call_count == 2
    send.assert_called_once()
    assert send.call_args[0][0] == "release_model_slot"
    assert send.call_args[0][1] == {"model_id": "primary"}


def test_gate_denied_already_unloaded_retries_too():
    """already_unloaded means something else already freed it — retry."""
    loader = FakeLoader(
        [
            (False, LOAD_OUTCOME_GATE_DENIED, "headroom too low"),
            (True, LOAD_OUTCOME_OK, ""),
        ]
    )
    response = {
        "status": "ok",
        "released": False,
        "outcome": RELEASE_OUTCOME_ALREADY_UNLOADED,
        "message": "not loaded",
    }
    with patch("main._daemon_is_running", return_value=True), patch(
        "core.daemon.send_command", return_value=response
    ):
        assert main_mod._load_primary_with_gate_recovery(loader) is True
    assert loader.call_count == 2


@pytest.mark.parametrize(
    "outcome",
    [RELEASE_OUTCOME_BUSY_TASK, RELEASE_OUTCOME_COOLDOWN, RELEASE_OUTCOME_UNCONFIRMED],
)
def test_gate_denied_daemon_declines_reports_original_denial_no_retry(outcome):
    loader = FakeLoader([(False, LOAD_OUTCOME_GATE_DENIED, "headroom too low")])
    response = {"status": "ok", "released": False, "outcome": outcome, "message": "declined"}
    with patch("main._daemon_is_running", return_value=True), patch(
        "core.daemon.send_command", return_value=response
    ):
        assert main_mod._load_primary_with_gate_recovery(loader) is False
    # Only the original attempt — decline means no retry.
    assert loader.call_count == 1
    # The reported outcome/reason still reflect the ORIGINAL gate denial,
    # not the decline (loader wasn't called again to overwrite it).
    assert loader.get_last_ensure_outcome() == LOAD_OUTCOME_GATE_DENIED


def test_gate_denied_send_command_raises_treated_like_no_daemon():
    loader = FakeLoader([(False, LOAD_OUTCOME_GATE_DENIED, "headroom too low")])
    with patch("main._daemon_is_running", return_value=True), patch(
        "core.daemon.send_command", side_effect=ConnectionError("socket error")
    ):
        assert main_mod._load_primary_with_gate_recovery(loader) is False
    assert loader.call_count == 1


def test_gate_denied_second_denial_after_retry_not_retried_again():
    """Retried load also gate-denied — single retry only, no loop."""
    loader = FakeLoader(
        [
            (False, LOAD_OUTCOME_GATE_DENIED, "headroom too low"),
            (False, LOAD_OUTCOME_GATE_DENIED, "still too low"),
        ]
    )
    response = {"status": "ok", "released": True, "outcome": RELEASE_OUTCOME_RELEASED, "message": "ok"}
    with patch("main._daemon_is_running", return_value=True), patch(
        "core.daemon.send_command", return_value=response
    ):
        assert main_mod._load_primary_with_gate_recovery(loader) is False
    assert loader.call_count == 2


def test_send_command_called_with_bounded_timeout():
    loader = FakeLoader([(False, LOAD_OUTCOME_GATE_DENIED, "headroom too low")])
    response = {"status": "ok", "released": False, "outcome": RELEASE_OUTCOME_BUSY_TASK, "message": "x"}
    with patch("main._daemon_is_running", return_value=True), patch(
        "core.daemon.send_command", return_value=response
    ) as send:
        main_mod._load_primary_with_gate_recovery(loader)
    assert send.call_args.kwargs.get("timeout") == main_mod._RELEASE_SLOT_TIMEOUT_S
    assert main_mod._RELEASE_SLOT_TIMEOUT_S < 60.0  # not send_command()'s generic default


# ---------------------------------------------------------------------------
# _is_unrecovered_gate_denial()
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "outcome,expected",
    [
        (LOAD_OUTCOME_GATE_DENIED, True),
        (LOAD_OUTCOME_GATE_DENIED_HARD, True),
        (LOAD_OUTCOME_OK, False),
        (LOAD_OUTCOME_SPAWN_FAILED, False),
        (LOAD_OUTCOME_ERROR, False),
    ],
)
def test_is_unrecovered_gate_denial(outcome, expected):
    loader = FakeLoader([])
    loader._outcome = outcome
    loader._reason = "x"
    assert main_mod._is_unrecovered_gate_denial(loader) is expected
