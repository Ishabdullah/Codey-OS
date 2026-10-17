"""NEW-971: the human-confirmed peer escalation dispatch is HIGH-gated.

Fake managers/CLIs only. No subprocess, network, os.kill or real peer agent
is reachable: every dispatch goes through a Mock manager, and the process /
network primitives are replaced with failing guards before any invocation.
The gateway is a private ActionGateway writing to a tmp_path audit file.
"""

import ast
import json
import os
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import core.peer_cli as peers
from core.action_gateway import ActionGateway

REPO = Path(__file__).resolve().parents[1]
SECRET_PROMPT = "SECRET-PROMPT-TEXT-123"
SECRET_ERR = "SECRET-ERROR-TEXT-456"
SECRET_OUT = "SECRET-OUTPUT-TEXT-789"


def _forbid(*_a, **_k):
    raise AssertionError("forbidden process/network primitive reached")


def _cli(name):
    return SimpleNamespace(name=name)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CODEY_DAEMON_MODE", raising=False)
    monkeypatch.delenv("CODEY_NON_INTERACTIVE", raising=False)
    for mod, attr in (
        (subprocess, "Popen"), (subprocess, "run"), (subprocess, "call"),
        (subprocess, "check_output"), (os, "kill"), (os, "killpg"),
        (socket, "create_connection"), (socket.socket, "connect"),
    ):
        monkeypatch.setattr(mod, attr, _forbid)
    audit = tmp_path / "audit.jsonl"
    gateway = ActionGateway(audit_file=audit)
    monkeypatch.setattr("core.action_gateway.get_action_gateway", lambda: gateway)
    agy, qwen = _cli("antigravity"), _cli("qwen")
    mgr = Mock()
    mgr.available.return_value = [agy, qwen]
    mgr.detect_task_type.return_value = "code"
    mgr.select_cli.side_effect = lambda task_type, exclude=(): next(
        (c for c in (agy, qwen) if c.name not in exclude), None
    )
    mgr.build_prompt.return_value = SECRET_PROMPT
    mgr.call.return_value = SECRET_OUT
    mgr.is_peer_error.side_effect = peers.PeerCLIManager.is_peer_error
    mgr.summarize_result.side_effect = lambda n, o, t: f"SUMMARY:{o}"
    monkeypatch.setattr(peers, "get_peer_cli_manager", lambda: mgr)
    for name in ("warning", "info", "success"):
        monkeypatch.setattr(peers, name, Mock())
    return SimpleNamespace(mgr=mgr, audit=audit, agy=agy, qwen=qwen, gateway=gateway)


def rows(env):
    if not env.audit.exists():
        return []
    return [json.loads(line) for line in env.audit.read_text().splitlines()]


def test_accept_dispatches_once_with_one_high_row(env):
    env.mgr.confirm.return_value = (True, None)
    out = peers.escalate("do thing", [SECRET_ERR], ["f.py"])
    assert out == f"SUMMARY:{SECRET_OUT}"
    env.mgr.call.assert_called_once_with(env.agy, SECRET_PROMPT)
    env.mgr.confirm.assert_called_once()
    (row,) = rows(env)
    assert row["authority"] == "HIGH_IMPACT"
    assert row["action"] == "peer_cli.escalate"
    assert row["command"] == "antigravity :: human_confirmed_escalation"
    assert row["outcome"] == "allowed"


def test_valid_switch_dispatches_selected_peer_once(env):
    env.mgr.confirm.return_value = ("switch", "qwen")
    peers.escalate("do thing", [], [])
    env.mgr.call.assert_called_once_with(env.qwen, SECRET_PROMPT)
    env.mgr.confirm.assert_called_once()  # no reprompt
    (row,) = rows(env)
    assert row["command"] == "qwen :: human_confirmed_escalation"


def test_switch_to_unavailable_peer_then_decline_no_dispatch(env):
    env.mgr.confirm.side_effect = [("switch", "ghost"), (False, None)]
    assert peers.escalate("t", [], []) is None
    env.mgr.call.assert_not_called()
    assert rows(env) == []


@pytest.mark.parametrize("confirm", [
    (False, None),
    ("redirect", "do it differently"),
])
def test_decline_and_redirect_never_dispatch(env, confirm):
    env.mgr.confirm.return_value = confirm
    out = peers.escalate("t", [], [])
    env.mgr.call.assert_not_called()
    assert rows(env) == []
    assert out == (None if confirm[0] is False else "[redirect]: do it differently")


@pytest.mark.parametrize("exc", [EOFError, KeyboardInterrupt])
def test_eof_and_interrupt_in_confirm_never_dispatch(env, exc):
    env.mgr.confirm.side_effect = exc
    with pytest.raises(exc):
        peers.escalate("t", [], [])
    env.mgr.call.assert_not_called()
    assert rows(env) == []


def test_no_peer_never_dispatches(env):
    env.mgr.available.return_value = []
    assert peers.escalate("t", [], []) is None
    env.mgr.select_cli.side_effect = lambda *a, **k: None
    env.mgr.available.return_value = [env.agy]
    assert peers.escalate("t", [], []) is None
    env.mgr.call.assert_not_called()
    env.mgr.confirm.assert_not_called()
    assert rows(env) == []


def test_peer_error_sentinel_is_failed_and_not_reported_success(env):
    sentinel = f"[PEER_ERROR: launch failed {SECRET_ERR}]"
    env.mgr.confirm.return_value = (True, None)
    env.mgr.call.return_value = sentinel
    out = peers.escalate("t", [], [])
    assert out == f"SUMMARY:{sentinel}"  # existing sentinel pass-through
    env.mgr.call.assert_called_once()
    peers.success.assert_not_called()
    (row,) = rows(env)
    assert row["outcome"] == "failed"
    assert row["reason"] == "peer dispatch reported an error"
    raw = env.audit.read_bytes()
    for secret in (SECRET_ERR, SECRET_PROMPT, SECRET_OUT):
        assert secret.encode() not in raw


def test_call_raising_is_failed_without_payload_leak(env):
    env.mgr.confirm.return_value = (True, None)
    env.mgr.call.side_effect = RuntimeError(f"boom {SECRET_ERR} {SECRET_PROMPT}")
    out = peers.escalate("t", [], [])
    assert out == "[PEER_ERROR: peer escalation failed]"
    (row,) = rows(env)
    assert row["outcome"] == "failed"
    raw = env.audit.read_bytes()
    for secret in (SECRET_ERR, SECRET_PROMPT):
        assert secret.encode() not in raw


def test_summarizer_failure_cannot_rewrite_audit(env):
    env.mgr.confirm.return_value = (True, None)
    env.mgr.summarize_result.side_effect = ValueError("summary broke")
    with pytest.raises(ValueError):
        peers.escalate("t", [], [])
    env.mgr.call.assert_called_once()
    (row,) = rows(env)
    assert row["outcome"] == "allowed"  # executed action stays executed


def test_no_payload_in_audit_bytes_on_success(env):
    env.mgr.confirm.return_value = (True, None)
    peers.escalate(SECRET_PROMPT, [SECRET_ERR], [])
    raw = env.audit.read_bytes()
    for secret in (SECRET_ERR, SECRET_PROMPT, SECRET_OUT):
        assert secret.encode() not in raw


def test_escalate_or_park_interactive_reaches_same_boundary(env):
    env.mgr.confirm.return_value = (True, None)
    out = peers.escalate_or_park("task_1", "t", [], [])
    assert out == f"SUMMARY:{SECRET_OUT}"
    env.mgr.call.assert_called_once()
    assert len(rows(env)) == 1


def test_escalate_or_park_parked_never_dispatches(env, monkeypatch):
    fake_bb = Mock()
    monkeypatch.setitem(
        __import__("sys").modules, "ccos.core.task_blackboard",
        SimpleNamespace(get_task_blackboard=lambda: fake_bb),
    )
    out = peers.escalate_or_park("task_1", "t", [], [], non_blocking=True)
    assert out.startswith("[parked]:")
    env.mgr.call.assert_not_called()
    env.mgr.confirm.assert_not_called()
    assert rows(env) == []


def test_agent_exhausted_branches_both_use_escalate_or_park():
    tree = ast.parse((REPO / "core/agent.py").read_text())
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "escalate_or_park"
    ]
    assert len(calls) == 2
    # Neither agent branch dispatches or gates a peer itself.
    src = (REPO / "core/agent.py").read_text()
    assert "peer_cli.escalate" not in src.replace("core.peer_cli import escalate_or_park", "")


def test_existing_delegation_paths_gate_once_each(env):
    src = (REPO / "core/peer_cli.py").read_text()
    assert src.count("gate_exec(") == 2  # execute_parked_escalation + escalate
    assert src.count('action="peer_cli.escalate"') == 1
    assert src.count('action="peer_cli.execute_parked_escalation"') == 1
    mgr_call_src = ast.get_source_segment(
        src, next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "call"))
    assert "gate" not in mgr_call_src  # no shared unconditional mgr.call gate
    agent_src = (REPO / "core/agent.py").read_text()
    assert agent_src.count('action="peer_cli.tool_peer_delegate"') == 1
    assert "confirm_available=False" in agent_src
    main_src = (REPO / "main.py").read_text()
    assert main_src.count('action="peer_cli.handle_command_peer"') == 1
