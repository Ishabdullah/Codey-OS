"""
Tests for Peer-CLI Escalation Redesign & Review Queue on TaskBlackboard (Track A / Item 4.5).
"""

import json
from unittest.mock import Mock, patch

import pytest

from ccos.core.task_blackboard import TaskBlackboard
from core.action_gateway import HIGH_IMPACT, ActionGateway
from core.peer_cli import (
    PeerCLI,
    PeerCLIManager,
    escalate_or_park,
    execute_parked_escalation,
    is_interactive_environment,
)


@pytest.fixture
def temp_blackboard(tmp_path):
    db_file = str(tmp_path / "test_blackboard.db")
    bb = TaskBlackboard(db_path=db_file)
    yield bb
    bb.close()


def test_blackboard_park_and_list_escalation(temp_blackboard):
    bb = temp_blackboard

    # Park a task
    assert bb.park_escalation(
        task_id="task_001",
        goal="Fix syntax error in database.py",
        reason="exhausted_retries",
        error_summary="SyntaxError: invalid syntax at line 42",
        files_touched=["database.py"],
        preferred_peer="antigravity",
    ) is True

    # Retrieve escalation
    item = bb.get_escalation("task_001")
    assert item is not None
    assert item["task_id"] == "task_001"
    assert item["goal"] == "Fix syntax error in database.py"
    assert item["status"] == "pending"
    assert item["preferred_peer"] == "antigravity"
    assert item["files_touched"] == ["database.py"]

    # Verify task session status
    task = bb.get_task("task_001")
    assert task is not None
    assert task["status"] == "escalated_pending_review"

    # List pending escalations
    pending = bb.list_escalations(status="pending")
    assert len(pending) == 1
    assert pending[0]["task_id"] == "task_001"

    # Resolve escalation
    assert bb.resolve_escalation(
        task_id="task_001",
        status="resolved",
        resolution_notes="Fixed manually by operator",
    ) is True

    resolved_item = bb.get_escalation("task_001")
    assert resolved_item["status"] == "resolved"
    assert resolved_item["resolution_notes"] == "Fixed manually by operator"

    # No longer in pending list
    assert len(bb.list_escalations(status="pending")) == 0


def test_is_interactive_environment(monkeypatch):
    # When CODEY_DAEMON_MODE is 1
    monkeypatch.setenv("CODEY_DAEMON_MODE", "1")
    assert is_interactive_environment() is False

    # When CODEY_NON_INTERACTIVE is 1
    monkeypatch.delenv("CODEY_DAEMON_MODE", raising=False)
    monkeypatch.setenv("CODEY_NON_INTERACTIVE", "1")
    assert is_interactive_environment() is False

    monkeypatch.delenv("CODEY_NON_INTERACTIVE", raising=False)
    # Mock sys.stdin.isatty
    with patch("sys.stdin.isatty", return_value=True):
        assert is_interactive_environment() is True
    with patch("sys.stdin.isatty", return_value=False):
        assert is_interactive_environment() is False


def test_escalate_or_park_non_interactive(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test_bb_escalate.db")
    test_bb = TaskBlackboard(db_path=db_file)

    with patch("ccos.core.task_blackboard.get_task_blackboard", return_value=test_bb), \
         patch("core.peer_cli.PeerCLIManager.select_cli", return_value=None):
        # In non-interactive mode
        monkeypatch.setenv("CODEY_NON_INTERACTIVE", "1")

        result = escalate_or_park(
            task_id="task_auto_99",
            user_message="Implement complex shader algorithm",
            errors=["NameError: glUniformMatrix4fv not found"],
            files=["shader.py"],
        )

        assert result is not None
        assert result.startswith("[parked]:")
        assert "task_auto_99" in result

        # Verify it was parked on blackboard
        esc = test_bb.get_escalation("task_auto_99")
        assert esc is not None
        assert esc["status"] == "pending"
        assert esc["files_touched"] == ["shader.py"]

    test_bb.close()


def test_escalate_or_park_interactive_calls_escalate(monkeypatch):
    with patch("core.peer_cli.is_interactive_environment", return_value=True), \
         patch("core.peer_cli.escalate", return_value="[Peer CLI output]") as mock_esc:
        res = escalate_or_park(
            task_id="task_int_1",
            user_message="Test message",
            errors=[],
            files=[],
            non_blocking=False,
        )
        assert res == "[Peer CLI output]"
        mock_esc.assert_called_once_with("Test message", [], [])


@pytest.fixture
def parked_execution(temp_blackboard, tmp_path, monkeypatch):
    """Real queue and audit; peer subprocess calls never leave this fixture."""
    bb = temp_blackboard
    goal = "Fix memory leak in buffer " + "x" * 220
    assert bb.park_escalation(
        task_id="task_exec_1",
        goal=goal,
        reason="exhausted_retries",
        error_summary="Valgrind leaked 128MB\nSecond error",
        files_touched=["buffer.c", "buffer.h"],
        preferred_peer="antigravity",
    )
    mgr = PeerCLIManager()
    peers = [
        PeerCLI(name=name, description=name, cmd=name, check_cmd="", strengths=[])
        for name in ("antigravity", "qwen")
    ]
    mgr.available = Mock(return_value=peers)
    mgr.call = Mock(return_value="Applied buffer fix in buffer.c")
    mgr.summarize_result = Mock(wraps=mgr.summarize_result)
    mgr.build_prompt = Mock(wraps=mgr.build_prompt)
    monkeypatch.setattr("core.peer_cli.get_peer_cli_manager", lambda: mgr)
    monkeypatch.setattr("ccos.core.task_blackboard.get_task_blackboard", lambda: bb)
    audit = tmp_path / "action_audit.jsonl"
    gateway = ActionGateway(audit_file=audit)
    monkeypatch.setattr("core.action_gateway.get_action_gateway", lambda: gateway)
    warning_mock = Mock()
    monkeypatch.setattr("core.peer_cli.warning", warning_mock)
    return bb, mgr, peers, gateway, audit, warning_mock


def assert_dispatch_audit(audit, name, goal, outcome, reason):
    records = [json.loads(line) for line in audit.read_text().splitlines()]
    assert len(records) == 1
    record = records[0]
    assert isinstance(record.pop("ts"), float)
    assert record == {
        "authority": HIGH_IMPACT,
        "action": "peer_cli.execute_parked_escalation",
        "command": f"{name} :: {goal[:200]}",
        "outcome": outcome,
        "reason": reason,
    }


def allow_test_dispatch(gateway, monkeypatch):
    """Test-only confirmation override; retain real dispatch/audit mechanics."""
    real_gate = gateway.gate_exec
    calls = []

    def allow(**kwargs):
        assert kwargs["authority"] == HIGH_IMPACT
        assert kwargs["confirm_available"] is False
        calls.append(kwargs.copy())
        kwargs["confirm_available"] = True
        return real_gate(**kwargs)

    monkeypatch.setattr(gateway, "gate_exec", allow)
    return calls


@pytest.mark.parametrize(
    ("peer_name", "stored_peer", "available_names", "resolved_name"),
    [
        ("qwen", "antigravity", ["antigravity", "qwen"], "qwen"),
        (None, "qwen", ["antigravity", "qwen"], "qwen"),
        (None, None, ["antigravity", "qwen"], "antigravity"),
        ("missing-peer", "antigravity", ["qwen"], "qwen"),
    ],
    ids=["explicit", "stored", "default", "fallback"],
)
def test_execute_parked_escalation_refused(
    parked_execution, peer_name, stored_peer, available_names, resolved_name,
):
    bb, mgr, peers, _gateway, audit, warnings = parked_execution
    initial = bb.get_escalation("task_exec_1")
    assert bb.park_escalation(
        task_id="task_exec_1", goal=initial["goal"], reason=initial["reason"],
        error_summary=initial["error_summary"], files_touched=initial["files_touched"],
        preferred_peer=stored_peer,
    )
    mgr.available.return_value = [peer for peer in peers if peer.name in available_names]
    before = bb.get_escalation("task_exec_1"), bb.get_task("task_exec_1")
    with patch.object(bb, "resolve_escalation", wraps=bb.resolve_escalation) as resolve:
        assert execute_parked_escalation("task_exec_1", peer_name=peer_name) is None
        resolve.assert_not_called()
    assert (bb.get_escalation("task_exec_1"), bb.get_task("task_exec_1")) == before
    mgr.call.assert_not_called()
    mgr.summarize_result.assert_not_called()
    reason = (
        "HIGH_IMPACT command with no confirmation path available; "
        "failing closed per policy (not attempted)."
    )
    warnings.assert_called_once_with(f"Parked escalation for task_exec_1 refused: {reason}")
    assert_dispatch_audit(audit, resolved_name, initial["goal"], "refused", reason)


def test_execute_parked_escalation_allowed(parked_execution, monkeypatch):
    bb, mgr, peers, gateway, audit, warnings = parked_execution
    before = bb.get_escalation("task_exec_1")
    calls = allow_test_dispatch(gateway, monkeypatch)
    expected_prompt = PeerCLIManager().build_prompt(
        before["goal"], [before["error_summary"]], before["files_touched"],
    )

    out = execute_parked_escalation("task_exec_1", peer_name="qwen")

    assert out == PeerCLIManager().summarize_result(
        "qwen", mgr.call.return_value, before["goal"],
    )
    assert len(calls) == 1
    assert calls[0]["command"] == f"qwen :: {before['goal'][:200]}"
    mgr.build_prompt.assert_called_once_with(
        before["goal"], [before["error_summary"]], before["files_touched"],
    )
    mgr.call.assert_called_once_with(peers[1], expected_prompt)
    mgr.summarize_result.assert_called_once_with("qwen", mgr.call.return_value, before["goal"])
    after = bb.get_escalation("task_exec_1")
    assert after["status"] == "resolved"
    assert after["preferred_peer"] == "qwen"
    assert after["resolution_notes"] == "Executed via qwen"
    assert after["resolved_at"] is not None
    assert bb.get_task("task_exec_1")["status"] == "active"
    warnings.assert_not_called()
    assert_dispatch_audit(audit, "qwen", before["goal"], "allowed", "command executed")


def test_execute_parked_escalation_dispatch_failure(parked_execution, monkeypatch):
    bb, mgr, _peers, gateway, audit, warnings = parked_execution
    before = bb.get_escalation("task_exec_1"), bb.get_task("task_exec_1")
    allow_test_dispatch(gateway, monkeypatch)
    mgr.call.side_effect = RuntimeError("peer failed to start")
    with patch.object(bb, "resolve_escalation", wraps=bb.resolve_escalation) as resolve:
        assert execute_parked_escalation("task_exec_1") is None
        resolve.assert_not_called()
    mgr.call.assert_called_once()
    mgr.summarize_result.assert_not_called()
    assert (bb.get_escalation("task_exec_1"), bb.get_task("task_exec_1")) == before
    warnings.assert_called_once_with(
        "Parked escalation for task_exec_1 failed: peer failed to start",
    )
    assert_dispatch_audit(audit, "antigravity", before[0]["goal"], "failed", "peer failed to start")


def test_execute_parked_escalation_summary_failure(parked_execution, monkeypatch):
    bb, mgr, _peers, gateway, audit, warnings = parked_execution
    before = bb.get_escalation("task_exec_1"), bb.get_task("task_exec_1")
    allow_test_dispatch(gateway, monkeypatch)
    mgr.summarize_result.side_effect = RuntimeError("summary failed")
    with patch.object(bb, "resolve_escalation", wraps=bb.resolve_escalation) as resolve:
        assert execute_parked_escalation("task_exec_1") is None
        resolve.assert_not_called()
    mgr.call.assert_called_once()
    assert (bb.get_escalation("task_exec_1"), bb.get_task("task_exec_1")) == before
    warnings.assert_called_once_with("Failed to execute parked escalation for task_exec_1: summary failed")
    assert_dispatch_audit(audit, "antigravity", before[0]["goal"], "allowed", "command executed")


@pytest.mark.parametrize("missing_record", [True, False], ids=["missing-record", "no-peers"])
def test_execute_parked_escalation_no_dispatch_candidate(parked_execution, missing_record):
    bb, mgr, _peers, gateway, audit, warnings = parked_execution
    before = bb.get_escalation("task_exec_1"), bb.get_task("task_exec_1")
    if not missing_record:
        mgr.available.return_value = []
    task_id = "missing-task" if missing_record else "task_exec_1"
    with patch.object(gateway, "gate_exec", wraps=gateway.gate_exec) as gate:
        assert execute_parked_escalation(task_id) is None
        gate.assert_not_called()
    mgr.call.assert_not_called()
    mgr.build_prompt.assert_not_called()
    mgr.summarize_result.assert_not_called()
    assert not audit.exists()
    assert (bb.get_escalation("task_exec_1"), bb.get_task("task_exec_1")) == before
    expected = "No escalation review found for task missing-task" if missing_record else "No peer CLIs available."
    warnings.assert_called_once_with(expected)
