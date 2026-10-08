"""Audit sink failures cannot alter action outcomes (NEW-835).

Use the bounded runner to redirect state paths before gateway collection.
Filesystem blockers and notes are real temporary files; peer/model calls
are never invoked.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from core import action_gateway, notes
from core.action_gateway import (
    ACT,
    HIGH_IMPACT,
    OUTCOME_ALLOWED,
    OUTCOME_FAILED,
    OUTCOME_REFUSED,
    ActionGateway,
)
from core.filesystem import FilesystemAccessError


@pytest.fixture
def blocked_audit(tmp_path):
    blocker = tmp_path / "audit-parent"
    blocker.write_text("preserve blocker")
    audit = blocker / "audit.jsonl"
    yield SimpleNamespace(
        gateway=ActionGateway(audit_file=audit), blocker=blocker, audit=audit,
    )
    assert blocker.read_text() == "preserve blocker"
    assert not audit.exists()


def test_exec_success_survives_blocked_audit(blocked_audit, tmp_path):
    sink = blocked_audit
    target = tmp_path / "operation.txt"

    def execute():
        # Appending lets the file itself prove exactly one execution.
        with target.open("a") as stream:
            stream.write("executed\n")
        return "original result"

    decision = sink.gateway.gate_exec(
        authority=ACT, action="test.exec", command="temporary write",
        confirm_available=False, execute=execute,
    )
    assert decision.outcome == OUTCOME_ALLOWED
    assert decision.detail["result"] == "original result"
    assert target.read_text() == "executed\n"


def test_exec_refusal_survives_blocked_audit(blocked_audit):
    execute = Mock(side_effect=AssertionError("refused action must not run"))
    decision = blocked_audit.gateway.gate_exec(
        authority=HIGH_IMPACT, action="test.refusal", command="forbidden",
        confirm_available=False, execute=execute,
    )
    assert decision.outcome == OUTCOME_REFUSED
    assert decision.reason == (
        "HIGH_IMPACT command with no confirmation path available; "
        "failing closed per policy (not attempted)."
    )
    execute.assert_not_called()


def test_exec_failure_survives_blocked_audit(blocked_audit):
    execute = Mock(side_effect=RuntimeError("original operation failure"))
    decision = blocked_audit.gateway.gate_exec(
        authority=ACT, action="test.failure", command="failed operation",
        confirm_available=False, execute=execute,
    )
    execute.assert_called_once_with()
    assert decision.outcome == OUTCOME_FAILED
    assert decision.reason == "original operation failure"
    assert "result" not in decision.detail


@pytest.mark.parametrize("operation", ["write", "append"])
@pytest.mark.parametrize("fails", [False, True], ids=["success", "access-error"])
def test_filesystem_decision_survives_blocked_audit(blocked_audit, operation, fails):
    filesystem = Mock()
    delegate = getattr(filesystem, operation)
    if fails:
        delegate.side_effect = FilesystemAccessError("original access failure")
    else:
        delegate.return_value = "original filesystem result"
    decision = getattr(blocked_audit.gateway, f"gate_{operation}")(
        authority=ACT, action=f"test.{operation}", path="temporary target",
        content="content", confirm_available=False, filesystem=filesystem,
    )
    delegate.assert_called_once_with("temporary target", "content")
    assert decision.outcome == (OUTCOME_FAILED if fails else OUTCOME_ALLOWED)
    if fails:
        assert decision.reason == "original access failure"
        assert "result" not in decision.detail
    else:
        assert decision.detail["result"] == "original filesystem result"
        assert decision.reason == f"{operation} succeeded"


def test_read_survives_blocked_audit(blocked_audit):
    decision = blocked_audit.gateway.gate_read(action="test.read", detail={"value": "kept"})
    assert decision.allowed
    assert decision.reason == "read permitted"
    assert decision.detail == {"value": "kept"}


@pytest.mark.parametrize("failure_stage", ["open", "write"])
def test_append_oserror_remains_best_effort(tmp_path, monkeypatch, failure_stage):
    sink = tmp_path / "audit.jsonl"
    failure = OSError("audit sink failed")
    if failure_stage == "open":
        opener = Mock(side_effect=failure)
    else:
        stream = Mock()
        stream.write.side_effect = failure
        opener = MagicMock()
        opener.return_value.__enter__.return_value = stream
    monkeypatch.setattr(action_gateway, "open", opener, raising=False)
    decision = ActionGateway(audit_file=sink).gate_read(action="test.read")
    assert decision.allowed
    opener.assert_called_once_with(sink, "a", encoding="utf-8")
    if failure_stage == "write":
        stream.write.assert_called_once()
    assert not sink.exists()


def test_notes_success_survives_blocked_audit(blocked_audit, tmp_path, monkeypatch):
    target = tmp_path / "notes-state" / "notes.json"
    monkeypatch.setattr(notes, "_NOTES_FILE", target)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: blocked_audit.gateway)
    assert notes.add_note("kept", "unchanged") is None
    assert notes.add_note(" Color ", " blue ") is None
    assert notes.get_all_notes() == {"kept": "unchanged", "color": "blue"}
    assert notes.remove_note(" COLOR ") is True
    assert notes.get_all_notes() == {"kept": "unchanged"}
    assert target.read_text() == '{\n  "kept": "unchanged"\n}'


@pytest.mark.parametrize("operation", ["add", "remove"])
def test_notes_failure_preserves_original_error_with_blocked_audit(
    blocked_audit, tmp_path, monkeypatch, operation,
):
    target = tmp_path / "notes.json"
    target.write_text('{"kept": "unchanged"}')
    before = target.read_bytes()
    monkeypatch.setattr(notes, "_NOTES_FILE", target)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: blocked_audit.gateway)
    failure = PermissionError("original notes persistence error")
    writer = Mock(side_effect=failure)
    monkeypatch.setattr(Path, "write_text", writer)
    with pytest.raises(PermissionError) as caught:
        if operation == "add":
            notes.add_note("new", "value")
        else:
            notes.remove_note("kept")
    assert caught.value is failure
    writer.assert_called_once()
    assert target.read_bytes() == before
