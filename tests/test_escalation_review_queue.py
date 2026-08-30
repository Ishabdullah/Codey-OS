"""
Tests for Peer-CLI Escalation Redesign & Review Queue on TaskBlackboard (Track A / Item 4.5).
"""

import os
import pytest
from unittest.mock import MagicMock, patch

from ccos.core.task_blackboard import TaskBlackboard
from core.peer_cli import (
    PeerCLI,
    get_peer_cli_manager,
    is_interactive_environment,
    escalate_or_park,
    list_parked_escalations,
    resolve_parked_escalation,
    execute_parked_escalation,
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

    with patch("ccos.core.task_blackboard.get_task_blackboard", return_value=test_bb):
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


def test_execute_parked_escalation(tmp_path):
    db_file = str(tmp_path / "test_bb_exec.db")
    test_bb = TaskBlackboard(db_path=db_file)
    test_bb.park_escalation(
        task_id="task_exec_1",
        goal="Fix memory leak in buffer",
        reason="exhausted_retries",
        error_summary="Valgrind leaked 128MB",
        files_touched=["buffer.c"],
        preferred_peer="antigravity",
    )

    with patch("ccos.core.task_blackboard.get_task_blackboard", return_value=test_bb), \
         patch("core.peer_cli.PeerCLIManager.available", return_value=[PeerCLI(name="antigravity", description="Antigravity CLI", cmd="agy", check_cmd="", strengths=[])]), \
         patch("core.peer_cli.PeerCLIManager.call", return_value="Applied buffer fix in buffer.c"):
        out = execute_parked_escalation("task_exec_1", peer_name="antigravity")
        assert out is not None
        assert "Applied buffer fix in buffer.c" in out

        # Check that it's marked as resolved
        esc = test_bb.get_escalation("task_exec_1")
        assert esc["status"] == "resolved"

    test_bb.close()
