"""Exercise the real /peer handler without eager memory/model imports.

A private gateway import stubs its unrelated Filesystem dependency before
execution. Private main imports stub unused eager dependencies, so this file
alone is safe even when collected without a preconfigured state directory.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from core.peer_cli import PeerCLIManager

REPO = Path(__file__).resolve().parents[1]


def load_private(monkeypatch, name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def peer_handler(tmp_path, monkeypatch):
    import core
    import core.peer_cli as peers

    # Save and restore both sys.modules and package attributes. These stubs
    # must never contaminate real gateway/filesystem tests in the same run.
    with monkeypatch.context() as imports:
        # main.py prepends its directory; confine that mutation to this import.
        imports.setattr(sys, "path", list(sys.path))
        for name, attrs in {
            "context": {},
            "dashboard_data": {"get_render_text": Mock()},
            "inference_v2": {"was_last_streamed": Mock()},
            "loader_v2": {"get_loader": Mock()},
            "sysmon": {"get_monitor": Mock()},
            "filesystem": {"Filesystem": object, "FilesystemAccessError": RuntimeError},
        }.items():
            stub = ModuleType(f"core.{name}")
            stub.__dict__.update(attrs)
            imports.setitem(sys.modules, f"core.{name}", stub)
            imports.setattr(core, name, stub, raising=False)
        gateway_module = load_private(
            imports, "_peer_test_gateway", REPO / "core/action_gateway.py",
        )
        main_module = load_private(imports, "_peer_test_main", REPO / "main.py")

    # The objects retain their private globals after imports are restored.
    audit = tmp_path / "audit.jsonl"
    gateway = gateway_module.ActionGateway(audit_file=audit)
    monkeypatch.setitem(sys.modules, "core.action_gateway", gateway_module)
    monkeypatch.setattr(core, "action_gateway", gateway_module, raising=False)
    monkeypatch.setattr(gateway_module, "get_action_gateway", lambda: gateway)
    mgr = PeerCLIManager()
    installed = list(peers.PEER_REGISTRY)
    mgr.available = Mock(side_effect=lambda include_disabled=False: [
        peer for peer in installed if include_disabled or peer.enabled
    ])
    mgr.call = Mock(return_value="Applied a complete peer fix")
    mgr.summarize_result = Mock(wraps=mgr.summarize_result)
    monkeypatch.setattr(peers, "get_peer_cli_manager", lambda: mgr)
    for name in ("warning", "error", "info", "success", "console"):
        monkeypatch.setattr(main_module, name, Mock())
    return SimpleNamespace(
        main=main_module, mgr=mgr, installed=installed,
        gateway=gateway, audit=audit, gateway_module=gateway_module,
    )


def assert_audit(h, peer, task, outcome, reason):
    records = [json.loads(line) for line in h.audit.read_text().splitlines()]
    assert len(records) == 1
    record = records[0]
    assert isinstance(record.pop("ts"), float)
    assert record == {
        "authority": "HIGH_IMPACT",
        "action": "peer_cli.handle_command_peer",
        "command": f"{peer} :: {task[:200]}",
        "outcome": outcome,
        "reason": reason,
    }


def allow_dispatch(h, monkeypatch):
    real_gate = h.gateway.gate_exec

    def allow(**kwargs):
        assert kwargs["authority"] == "HIGH_IMPACT"
        assert kwargs["confirm_available"] is False
        kwargs["confirm_available"] = True  # Test only; dispatch remains mocked.
        return real_gate(**kwargs)

    monkeypatch.setattr(h.gateway, "gate_exec", allow)


@pytest.mark.parametrize(
    ("command", "selected", "task", "yolo"),
    [
        ("/peer qwen write code", "qwen", "write code", False),
        ("/peer agy fix a bug", "antigravity", "fix a bug", False),
        ("/peer fix this bug", "antigravity", "fix this bug", False),
        ("/peer claude fix this", "antigravity", "fix this", False),
        ("/peer qwen", "qwen", "", False),
        ("/peer qwen write code", "qwen", "write code", True),
        ("/peer qwen " + "x" * 220, "qwen", "x" * 220, False),
    ],
    ids=["named", "alias", "auto", "fallback", "no-task", "yolo", "audit-truncation"],
)
def test_peer_refusal(peer_handler, command, selected, task, yolo):
    h = peer_handler
    history = [{"role": "user", "content": "existing context"}]
    before = history.copy()
    handled, returned = h.main.handle_command(command, history, yolo=yolo)
    assert handled is True
    assert returned is history
    assert history == before
    h.mgr.call.assert_not_called()
    h.mgr.summarize_result.assert_not_called()
    h.main.success.assert_not_called()
    h.main.error.assert_not_called()
    reason = (
        "HIGH_IMPACT command with no confirmation path available; "
        "failing closed per policy (not attempted)."
    )
    h.main.warning.assert_any_call(f"Peer {selected} refused: {reason}")
    assert_audit(h, selected, task, "refused", reason)


@pytest.mark.parametrize(
    ("command", "availability"),
    [
        ("/peer", "all"),
        ("/help", "all"),
        ("/peer qwen write code", "none"),
        ("/peer claude", "all"),
        ("/peer claude fix bug", "disabled-only"),
        ("/peer fix bug", "disabled-only"),
    ],
    ids=["listing", "help", "no-peers", "disabled-no-task", "no-fallback", "no-auto-peer"],
)
def test_peer_without_dispatch_candidate(peer_handler, command, availability, monkeypatch):
    h = peer_handler
    if availability == "none":
        h.installed.clear()
    elif availability == "disabled-only":
        h.installed[:] = [peer for peer in h.installed if not peer.enabled]
    gate = Mock(wraps=h.gateway.gate_exec)
    monkeypatch.setattr(h.gateway, "gate_exec", gate)
    history = [{"role": "user", "content": "existing"}]
    before = history.copy()
    handled, returned = h.main.handle_command(command, history)
    assert handled is True
    assert returned is history
    assert history == before
    gate.assert_not_called()
    h.mgr.call.assert_not_called()
    h.mgr.summarize_result.assert_not_called()
    assert not h.audit.exists()
    if command in ("/peer", "/help"):
        printed = "\n".join(str(call.args[0]) for call in h.main.console.print.call_args_list)
        assert "Dispatch is blocked until a peer confirmation UI is available (including YOLO)." in printed


def test_peer_allowed_raw_prompt_history(peer_handler, monkeypatch):
    h = peer_handler
    allow_dispatch(h, monkeypatch)
    history = [{"role": "user", "content": "existing"}]
    before = history.copy()
    # Splitting preserves the raw task's internal whitespace/newline.
    task = "fix  this\nfunction"
    handled, returned = h.main.handle_command(f"/peer agy {task}", history)
    assert handled is True
    assert returned is history
    peer = next(peer for peer in h.installed if peer.name == "antigravity")
    h.mgr.call.assert_called_once_with(peer, task)
    h.mgr.summarize_result.assert_called_once_with(peer.name, h.mgr.call.return_value, task)
    summary = PeerCLIManager().summarize_result(peer.name, h.mgr.call.return_value, task)
    assert history == before + [
        {"role": "user", "content": f"/peer antigravity: {task}"},
        {"role": "assistant", "content": summary},
    ]
    h.main.success.assert_called_once_with("Result from antigravity added to conversation context.")
    h.main.warning.assert_not_called()
    h.main.error.assert_not_called()
    assert_audit(h, "antigravity", task, "allowed", "command executed")


@pytest.mark.parametrize("output", ["[PEER_ERROR: no peer]", "short", "", "          "])
def test_peer_allowed_non_readable_output(peer_handler, monkeypatch, output):
    h = peer_handler
    allow_dispatch(h, monkeypatch)
    h.mgr.call.return_value = output
    history = [{"role": "user", "content": "existing"}]
    before = history.copy()
    handled, returned = h.main.handle_command("/peer qwen task", history)
    assert handled is True
    assert returned is history
    assert history == before
    h.mgr.call.assert_called_once()
    h.mgr.summarize_result.assert_not_called()
    h.main.success.assert_not_called()
    if output.startswith("[PEER_ERROR:"):
        h.main.error.assert_called_once_with(f"Peer qwen failed: {output}")
    else:
        h.main.error.assert_not_called()
    assert_audit(h, "qwen", "task", "allowed", "command executed")


def test_peer_dispatch_exception(peer_handler, monkeypatch):
    h = peer_handler
    allow_dispatch(h, monkeypatch)
    h.mgr.call.side_effect = RuntimeError("dispatch crashed")
    history = [{"role": "user", "content": "existing"}]
    before = history.copy()
    handled, returned = h.main.handle_command("/peer qwen task", history)
    assert handled is True
    assert returned is history
    assert history == before
    h.mgr.call.assert_called_once()
    h.mgr.summarize_result.assert_not_called()
    h.main.success.assert_not_called()
    h.main.warning.assert_not_called()
    h.main.error.assert_called_once_with("Peer qwen failed: dispatch crashed")
    assert_audit(h, "qwen", "task", "failed", "dispatch crashed")


def test_peer_summary_exception_retains_dispatch_audit(peer_handler, monkeypatch):
    h = peer_handler
    allow_dispatch(h, monkeypatch)
    h.mgr.summarize_result.side_effect = RuntimeError("summary crashed")
    history = [{"role": "user", "content": "existing"}]
    before = history.copy()
    with pytest.raises(RuntimeError, match="summary crashed"):
        h.main.handle_command("/peer qwen task", history)
    assert history == before
    h.mgr.call.assert_called_once()
    h.main.success.assert_not_called()
    assert_audit(h, "qwen", "task", "allowed", "command executed")
