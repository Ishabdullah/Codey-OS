"""Notes persistence mediation; run with state paths isolated before collection.

Importing the real gateway/agent can initialize unrelated SQLite state
(NEW-855); the bounded validation runner redirects config paths first.
Every notes write and action audit here uses explicit temporary paths.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import notes
from core.action_gateway import ACT, ActionGateway, GatewayDecision


@pytest.fixture
def note_store(tmp_path, monkeypatch):
    notes_file = tmp_path / "notes-state" / "notes.json"
    audit = tmp_path / "audit.jsonl"
    gateway = ActionGateway(audit_file=audit)
    monkeypatch.setattr(notes, "_NOTES_FILE", notes_file)
    monkeypatch.setattr("core.action_gateway.get_action_gateway", lambda: gateway)
    return SimpleNamespace(notes_file=notes_file, audit=audit, gateway=gateway)


def read_audits(store):
    if not store.audit.exists():
        return []
    return [json.loads(line) for line in store.audit.read_text().splitlines()]


def assert_audit(record, action, outcome="allowed", reason="command executed"):
    assert isinstance(record.pop("ts"), float)
    assert record == {
        "authority": ACT,
        "action": action,
        "command": "persist notes.json",
        "outcome": outcome,
        "reason": reason,
    }


def test_add_normalize_overwrite_remove(note_store, monkeypatch):
    store = note_store
    real_gate = store.gateway.gate_exec
    gate = Mock(wraps=real_gate)
    monkeypatch.setattr(store.gateway, "gate_exec", gate)

    assert notes.add_note("kept", "unchanged") is None
    assert notes.add_note("  Favorite COLOR  ", "  blue  ") is None
    assert store.notes_file.read_text() == json.dumps({"kept": "unchanged", "favorite color": "blue"}, indent=2)
    assert notes.add_note("Favorite Color", " green ") is None
    assert notes.get_note(" FAVORITE COLOR ") == "green"
    assert notes.get_all_notes() == {"kept": "unchanged", "favorite color": "green"}
    assert notes.remove_note("  FAVORITE COLOR ") is True
    assert store.notes_file.read_text() == json.dumps({"kept": "unchanged"}, indent=2)

    for call in gate.call_args_list:
        assert call.kwargs["authority"] == ACT
        assert call.kwargs["confirm_available"] is False
        assert call.kwargs["command"] == "persist notes.json"
    records = read_audits(store)
    assert len(records) == 4
    actions = ["notes.add_note", "notes.add_note", "notes.add_note", "notes.remove_note"]
    for record, action in zip(records, actions, strict=True):
        assert_audit(record, action)


@pytest.mark.parametrize("file_exists", [False, True], ids=["absent-store", "existing-store"])
def test_missing_remove_has_no_write_or_audit(note_store, monkeypatch, file_exists):
    store = note_store
    if file_exists:
        store.notes_file.parent.mkdir()
        store.notes_file.write_text('{"kept": "unchanged"}')
    before = store.notes_file.read_bytes() if file_exists else None
    gate = Mock(wraps=store.gateway.gate_exec)
    monkeypatch.setattr(store.gateway, "gate_exec", gate)
    write = Mock(side_effect=AssertionError("missing remove must not write"))
    monkeypatch.setattr(Path, "write_text", write)

    assert notes.remove_note(" MISSING ") is False
    gate.assert_not_called()
    write.assert_not_called()
    assert read_audits(store) == []
    assert store.notes_file.exists() is file_exists
    if file_exists:
        assert store.notes_file.read_bytes() == before
    else:
        assert not store.notes_file.parent.exists()


@pytest.mark.parametrize("operation", ["add", "remove"])
def test_persistence_error_preserves_exception(note_store, monkeypatch, operation):
    store = note_store
    store.notes_file.parent.mkdir()
    store.notes_file.write_text('{"kept": "unchanged"}')
    before = store.notes_file.read_bytes()
    failure = PermissionError("cannot persist notes")
    write = Mock(side_effect=failure)
    monkeypatch.setattr(Path, "write_text", write)

    with pytest.raises(PermissionError) as caught:
        if operation == "add":
            notes.add_note("new", "value")
        else:
            notes.remove_note("kept")
    assert caught.value is failure
    write.assert_called_once()
    assert store.notes_file.read_bytes() == before
    records = read_audits(store)
    assert len(records) == 1
    action = "notes.add_note" if operation == "add" else "notes.remove_note"
    assert_audit(records[0], action, "failed", "cannot persist notes")


def test_refusing_gateway_never_persists(note_store, monkeypatch):
    store = note_store
    gate = Mock(return_value=GatewayDecision(ACT, "refused", "test policy refuses"))
    monkeypatch.setattr(store.gateway, "gate_exec", gate)
    write = Mock(side_effect=AssertionError("refused thunk must not write"))
    monkeypatch.setattr(Path, "write_text", write)
    with pytest.raises(RuntimeError, match="Note persistence refused: test policy refuses"):
        notes.add_note("new", "value")
    gate.assert_called_once()
    write.assert_not_called()
    assert not store.notes_file.parent.exists()
    assert read_audits(store) == []  # This test double does not audit.


def test_audit_excludes_note_contents_and_reads_do_not_audit(note_store):
    store = note_store
    key = "secret-key-unique"
    value = "secret-value-unique"
    notes.add_note(key, value)
    audit_before = store.audit.read_bytes()
    assert key not in audit_before.decode()
    assert value not in audit_before.decode()
    assert notes.get_note(f" {key.upper()} ") == value
    assert notes.get_note("missing") is None
    assert notes.get_all_notes() == {key: value}
    assert notes.get_notes_block() == (
        "## User Notes\nThings the user has told you to remember:\n"
        f"- {key}: {value}"
    )
    assert store.audit.read_bytes() == audit_before
    notes.remove_note(key)
    assert key not in store.audit.read_text()
    assert value not in store.audit.read_text()
    audit_after = store.audit.read_bytes()
    assert notes.get_all_notes() == {}
    assert notes.get_notes_block() == ""
    assert store.audit.read_bytes() == audit_after


def test_real_agent_note_tools_preserve_strings_and_mutations(note_store, monkeypatch):
    from core import agent

    # Exercise only the registered tools. Any accidental agent/inference
    # invocation must fail before it can start a model.
    monkeypatch.setattr(agent, "run_agent", Mock(side_effect=AssertionError("no agent loop")))
    monkeypatch.setattr(agent, "infer", Mock(side_effect=AssertionError("no model inference")))
    store = note_store
    assert agent.TOOLS["note_save"]({"key": " Color ", "value": " blue "}) == "Remembered:  Color  =  blue "
    assert json.loads(store.notes_file.read_text()) == {"color": "blue"}
    assert agent.TOOLS["note_forget"]({"key": " COLOR "}) == "Forgot:  COLOR "
    assert json.loads(store.notes_file.read_text()) == {}
    assert agent.TOOLS["note_forget"]({"key": " COLOR "}) == "No note found for:  COLOR "
    records = read_audits(store)
    assert len(records) == 2
    assert_audit(records[0], "notes.add_note")
    assert_audit(records[1], "notes.remove_note")
