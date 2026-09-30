"""AGI audit 4.1: error-DB read side, default off, fail-open."""
import core.agent as ag


class _L:
    def suggest_fix(self, et, msg):
        return f"try X for {et}"


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("CODEY_USE_FIX_MEMORY", raising=False)
    monkeypatch.setattr(ag, "_get_learning", lambda: _L())
    assert ag._fix_memory_hint("ModuleNotFoundError: no module x") == ""


def test_on_returns_hint_with_parsed_error_type(monkeypatch):
    monkeypatch.setenv("CODEY_USE_FIX_MEMORY", "1")
    monkeypatch.setattr(ag, "_get_learning", lambda: _L())
    h = ag._fix_memory_hint("[ERROR] ModuleNotFoundError: no module x")
    assert "try X for ModuleNotFoundError" in h


def test_fail_open(monkeypatch):
    monkeypatch.setenv("CODEY_USE_FIX_MEMORY", "1")

    def boom():
        raise RuntimeError("db broken")
    monkeypatch.setattr(ag, "_get_learning", boom)
    assert ag._fix_memory_hint("KeyError: a") == ""


def test_no_suggestion_returns_empty(monkeypatch):
    monkeypatch.setenv("CODEY_USE_FIX_MEMORY", "1")

    class N:
        def suggest_fix(self, *a):
            return None
    monkeypatch.setattr(ag, "_get_learning", lambda: N())
    assert ag._fix_memory_hint("weird failure") == ""
