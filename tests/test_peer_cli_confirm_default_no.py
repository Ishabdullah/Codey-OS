"""D-4: PeerCLIManager.confirm Enter defaults to No; is_interactive_environment fails closed."""
from unittest.mock import patch

import pytest

from core import peer_cli
from core.peer_cli import PEER_REGISTRY, PeerCLIManager, is_interactive_environment


class _Console:
    def __init__(self, answer):
        self.answer = answer
        self.lines = []

    def print(self, *a, **k):
        self.lines.append(" ".join(str(x) for x in a))

    def rule(self, *a, **k):
        pass

    def input(self, *a, **k):
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer


def _confirm(answer, monkeypatch):
    qwen = next(c for c in PEER_REGISTRY if c.name == "qwen")
    agy = next(c for c in PEER_REGISTRY if c.name == "antigravity")
    con = _Console(answer)
    monkeypatch.setattr("utils.logger.console", con)
    with patch.object(PeerCLIManager, "available", return_value=[qwen, agy]):
        return PeerCLIManager().confirm(qwen, "code", "do a thing"), con


@pytest.mark.parametrize("ans", ["", "   ", "n", "No", "NO"])
def test_enter_and_no_decline(ans, monkeypatch):
    res, _ = _confirm(ans, monkeypatch)
    assert res == (False, None)


@pytest.mark.parametrize("ans", ["y", "YES", " yes ", "Y"])
def test_explicit_yes_approves(ans, monkeypatch):
    res, _ = _confirm(ans, monkeypatch)
    assert res == (True, None)


def test_switch_redirect_and_interrupts(monkeypatch):
    assert _confirm("antigravity", monkeypatch)[0] == ("switch", "antigravity")
    assert _confirm("try another approach", monkeypatch)[0] == ("redirect", "try another approach")
    assert _confirm(EOFError(), monkeypatch)[0] == (False, None)
    assert _confirm(KeyboardInterrupt(), monkeypatch)[0] == (False, None)


def test_prompt_text_shows_enter_as_skip(monkeypatch):
    _, con = _confirm("", monkeypatch)
    text = "\n".join(con.lines)
    assert "n / enter" in text
    assert "y / enter" not in text


def test_escalate_with_enter_never_dispatches(monkeypatch):
    qwen = next(c for c in PEER_REGISTRY if c.name == "qwen")
    con = _Console("")
    monkeypatch.setattr("utils.logger.console", con)
    with patch.object(PeerCLIManager, "available", return_value=[qwen]), \
         patch.object(PeerCLIManager, "select_cli", return_value=qwen), \
         patch.object(PeerCLIManager, "call") as mock_call, \
         patch("core.action_gateway.get_action_gateway") as mock_gw:
        res = peer_cli.escalate("do a thing", ["err"], [])
    assert res is None
    mock_call.assert_not_called()
    mock_gw.assert_not_called()


def test_is_interactive_environment_fails_closed(monkeypatch):
    monkeypatch.delenv("CODEY_DAEMON_MODE", raising=False)
    monkeypatch.delenv("CODEY_NON_INTERACTIVE", raising=False)
    with patch("sys.stdin.isatty", side_effect=ValueError("closed")):
        assert is_interactive_environment() is False
