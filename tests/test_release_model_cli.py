"""
NEW-413 (piece 1, this repo) — tools/release_model_cli.py, the delegated
model-release entry point Codey-Aigentik's warm-up-failure exit path is
meant to call in a follow-up change to that separate repo (out of this
task's scope; see NEW_ISSUES.md's NEW-413 entry). Mirrors
tests/test_ensure_model_cli.py's conventions for its load-side sibling.

No real daemon, no real socket, no real subprocess (CLAUDE.md rule 2 RAM
discipline / rule 3 process-lifecycle care) — `core.daemon.send_command`
is faked/patched throughout.
"""
from unittest.mock import patch

from tools.release_model_cli import main as release_model_cli_main


def test_calls_send_command_with_expected_shape():
    calls = []

    def _fake_send_command(cmd, data=None, timeout=None):
        calls.append((cmd, data, timeout))
        return {"status": "ok", "released": True, "outcome": "released", "message": ""}

    with patch("core.daemon.send_command", side_effect=_fake_send_command):
        rc = release_model_cli_main()

    assert rc == 0
    assert len(calls) == 1
    cmd, data, timeout = calls[0]
    assert cmd == "release_model_slot"
    assert data == {"model_id": "primary"}
    assert timeout is not None


def test_already_unloaded_is_treated_as_success():
    with patch(
        "core.daemon.send_command",
        return_value={
            "status": "ok",
            "released": False,
            "outcome": "already_unloaded",
            "message": "'primary' was not loaded — nothing to release",
        },
    ):
        rc = release_model_cli_main()

    assert rc == 0


def test_busy_decline_is_nonfatal_but_nonzero():
    with patch(
        "core.daemon.send_command",
        return_value={
            "status": "ok",
            "released": False,
            "outcome": "busy_task_running",
            "message": "a task is actively executing",
        },
    ):
        rc = release_model_cli_main()

    assert rc == 2


def test_daemon_unreachable_returns_nonzero_and_does_not_raise():
    with patch(
        "core.daemon.send_command",
        side_effect=ConnectionError("Daemon socket not found."),
    ):
        rc = release_model_cli_main()

    assert rc == 1
