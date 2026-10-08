"""
Persistent user notes for Codey-OS.

Simple key-value store for facts the user asks Codey to remember
(e.g., "my name is Ish", "I prefer tabs over spaces").

Stored at ~/.codeyOS/notes.json — survives across sessions.
"""

import json
from typing import Optional

from utils.config import NOTES_FILE as _NOTES_FILE


def _load() -> dict:
    """Load notes from disk."""
    if _NOTES_FILE.exists():
        try:
            return json.loads(_NOTES_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save(notes: dict, *, action: str):
    """Persist an ACT action, which proceeds audited without confirmation."""
    from core.action_gateway import ACT, get_action_gateway

    original_error = None

    def persist():
        nonlocal original_error
        try:
            _NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
            _NOTES_FILE.write_text(json.dumps(notes, indent=2))
        except Exception as exc:
            # gate_exec records failure instead of raising; retain the
            # original exception so callers still observe persistence errors.
            original_error = exc
            raise
        return "notes persisted"

    decision = get_action_gateway().gate_exec(
        authority=ACT,
        action=action,
        command="persist notes.json",
        confirm_available=False,
        execute=persist,
    )
    if not decision.allowed:
        if original_error is not None:
            raise original_error
        raise RuntimeError(f"Note persistence {decision.outcome}: {decision.reason}")


def add_note(key: str, value: str):
    """Save a note (overwrites if key exists)."""
    notes = _load()
    notes[key.lower().strip()] = value.strip()
    _save(notes, action="notes.add_note")


def remove_note(key: str) -> bool:
    """Remove a note. Missing keys return False without a mutation or audit."""
    notes = _load()
    k = key.lower().strip()
    if k in notes:
        del notes[k]
        _save(notes, action="notes.remove_note")
        return True
    return False


def get_note(key: str) -> Optional[str]:
    """Get a specific note."""
    return _load().get(key.lower().strip())


def get_all_notes() -> dict:
    """Get all notes."""
    return _load()


def get_notes_block() -> str:
    """Format notes as a system prompt block."""
    notes = _load()
    if not notes:
        return ""
    lines = [f"- {k}: {v}" for k, v in notes.items()]
    return "## User Notes\nThings the user has told you to remember:\n" + "\n".join(lines)
