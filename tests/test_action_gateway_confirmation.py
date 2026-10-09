"""Optional HIGH_IMPACT confirmations; collect with isolated config state."""

import json
from unittest.mock import Mock

import pytest

from core.action_gateway import ACT, HIGH_IMPACT, READ, ActionGateway


@pytest.mark.parametrize(
    ("answer", "exception", "outcome", "reason"),
    [
        (True, None, "allowed", "command executed"),
        (False, None, "refused", "Human confirmation declined; command not attempted."),
        ("yes", None, "refused", "Human confirmation declined; command not attempted."),
        (None, EOFError(), "refused", "Human confirmation unavailable or interrupted; command not attempted."),
        (None, KeyboardInterrupt(), "refused", "Human confirmation unavailable or interrupted; command not attempted."),
        (None, RuntimeError("private input"), "refused", "Human confirmation unavailable due to callback failure; command not attempted."),
    ],
)
def test_confirmation_outcomes(tmp_path, answer, exception, outcome, reason):
    audit = tmp_path / "audit.jsonl"
    confirm = Mock(return_value=answer, side_effect=exception)
    execute = Mock(return_value="private output")
    decision = ActionGateway(audit_file=audit).gate_exec(
        authority=HIGH_IMPACT, action="test.confirm", command="static attempt",
        confirm_available=True, confirm=confirm, execute=execute,
    )
    assert decision.outcome == outcome
    assert decision.reason == reason
    confirm.assert_called_once_with()
    assert execute.call_count == (1 if outcome == "allowed" else 0)
    records = [json.loads(line) for line in audit.read_text().splitlines()]
    assert len(records) == 1
    record = records[0]
    assert isinstance(record.pop("ts"), float)
    assert record == {
        "authority": HIGH_IMPACT, "action": "test.confirm", "command": "static attempt",
        "outcome": outcome, "reason": reason,
    }
    assert "private" not in audit.read_text()


@pytest.mark.parametrize("authority", [READ, ACT])
@pytest.mark.parametrize("available", [False, True])
def test_read_act_ignore_callback(tmp_path, authority, available):
    confirm = Mock(side_effect=AssertionError("callback must be ignored"))
    execute = Mock(return_value="done")
    decision = ActionGateway(audit_file=tmp_path / "audit.jsonl").gate_exec(
        authority=authority, action="test.ignore", command="attempt",
        confirm_available=available, confirm=confirm, execute=execute,
    )
    assert decision.allowed
    confirm.assert_not_called()
    execute.assert_called_once_with()


def test_unavailable_path_ignores_callback(tmp_path):
    confirm = Mock(return_value=True)
    execute = Mock()
    audit = tmp_path / "audit.jsonl"
    decision = ActionGateway(audit_file=audit).gate_exec(
        authority=HIGH_IMPACT, action="test.unavailable", command="attempt",
        confirm_available=False, confirm=confirm, execute=execute,
    )
    assert decision.outcome == "refused"
    assert "no confirmation path available" in decision.reason
    confirm.assert_not_called()
    execute.assert_not_called()
    assert json.loads(audit.read_text())["outcome"] == "refused"


def test_system_exit_is_not_swallowed(tmp_path):
    original = SystemExit(7)
    execute = Mock()
    with pytest.raises(SystemExit) as caught:
        ActionGateway(audit_file=tmp_path / "audit.jsonl").gate_exec(
            authority=HIGH_IMPACT, action="test.exit", command="attempt",
            confirm_available=True, confirm=Mock(side_effect=original), execute=execute,
        )
    assert caught.value is original
    execute.assert_not_called()


@pytest.mark.parametrize("approved", [True, False])
def test_blocked_audit_does_not_change_confirmation(tmp_path, approved):
    blocker = tmp_path / "blocker"
    blocker.write_text("blocker")
    execute = Mock(return_value="done")
    confirm = Mock(return_value=approved)
    decision = ActionGateway(audit_file=blocker / "audit.jsonl").gate_exec(
        authority=HIGH_IMPACT, action="test.blocked", command="attempt",
        confirm_available=True, confirm=confirm, execute=execute,
    )
    assert decision.outcome == ("allowed" if approved else "refused")
    assert execute.call_count == int(approved)
    confirm.assert_called_once_with()
    assert blocker.read_text() == "blocker"
