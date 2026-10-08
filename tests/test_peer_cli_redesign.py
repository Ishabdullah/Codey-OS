"""
Unit tests for Track A / Phase A2 Item 4.5: Peer-CLI Escalation Redesign.
"""

import json
from unittest.mock import patch

from core.agent import _detect_peer_delegation, tool_peer_delegate
from core.peer_cli import (
    PEER_REGISTRY,
    PeerCLIManager,
    is_peer_enabled,
    resolve_peer_name,
)
from core.peer_shell import _strip_peer_noise


def test_peer_registry_metadata():
    """Verify registry entries for antigravity, qwen, and claude."""
    peers = {p.name: p for p in PEER_REGISTRY}

    assert "antigravity" in peers
    agy = peers["antigravity"]
    assert agy.cmd == "agy"
    assert "agy" in agy.aliases
    assert "gemini" in agy.aliases
    assert agy.enabled is True
    assert agy.prompt_flag == "-p"
    assert agy.yolo_flag == "--dangerously-skip-permissions"
    assert "explain" in agy.strengths

    assert "qwen" in peers
    qwen = peers["qwen"]
    assert qwen.cmd == "qwen"
    assert "qwen-code" in qwen.aliases
    assert "qwen3.5" in qwen.aliases
    assert qwen.enabled is True
    assert qwen.prompt_flag == "-p"
    assert qwen.yolo_flag == "-y"

    assert "claude" in peers
    claude = peers["claude"]
    assert claude.cmd == "claude"
    assert "claude-code" in claude.aliases
    assert claude.enabled is False
    assert "credits" in claude.disabled_reason.lower() or "disabled" in claude.disabled_reason.lower()


def test_resolve_peer_name():
    """Verify canonical resolution of peer names and aliases."""
    assert resolve_peer_name("antigravity") == "antigravity"
    assert resolve_peer_name("agy") == "antigravity"
    assert resolve_peer_name("gemini") == "antigravity"
    assert resolve_peer_name("AGY") == "antigravity"
    assert resolve_peer_name("Gemini") == "antigravity"

    assert resolve_peer_name("qwen") == "qwen"
    assert resolve_peer_name("qwen-code") == "qwen"
    assert resolve_peer_name("qwen3.5") == "qwen"

    assert resolve_peer_name("claude") == "claude"
    assert resolve_peer_name("claude-code") == "claude"

    assert resolve_peer_name("unknown_peer") is None
    assert resolve_peer_name("") is None


def test_is_peer_enabled():
    """Verify enablement checking for canonical names, aliases, and PeerCLI objects."""
    assert is_peer_enabled("antigravity") is True
    assert is_peer_enabled("agy") is True
    assert is_peer_enabled("gemini") is True
    assert is_peer_enabled("qwen") is True
    assert is_peer_enabled("qwen3.5") is True

    assert is_peer_enabled("claude") is False
    assert is_peer_enabled("claude-code") is False
    assert is_peer_enabled("nonexistent") is False


def test_available_filtering():
    """Verify PeerCLIManager.available respects include_disabled parameter."""
    mgr = PeerCLIManager()
    with patch.object(mgr, "_is_installed", return_value=True):
        enabled = mgr.available(include_disabled=False)
        all_peers = mgr.available(include_disabled=True)

        enabled_names = {c.name for c in enabled}
        all_names = {c.name for c in all_peers}

        assert "antigravity" in enabled_names
        assert "qwen" in enabled_names
        assert "claude" not in enabled_names

        assert "claude" in all_names
        assert "antigravity" in all_names
        assert "qwen" in all_names


def test_select_cli_skips_disabled():
    """Verify select_cli does not pick disabled peers like claude."""
    mgr = PeerCLIManager()
    with patch.object(mgr, "_is_installed", return_value=True):
        selected = mgr.select_cli("debugging")
        assert selected is not None
        assert selected.name in ("antigravity", "qwen")
        assert selected.name != "claude"


def test_select_cli_exclude_alias():
    """Verify select_cli handles excluded names including aliases."""
    mgr = PeerCLIManager()
    with patch.object(mgr, "_is_installed", return_value=True):
        # Exclude antigravity by alias "gemini"
        selected = mgr.select_cli("debugging", exclude=["gemini"])
        assert selected is not None
        assert selected.name == "qwen"


def test_strip_peer_noise():
    """Verify noise stripping for antigravity/gemini CLI output."""
    raw_output = (
        "Keychain initialization encountered an error\n"
        "Require stack:\n"
        "- /data/data/com.termux/files/usr/lib/node_modules/gemini/index.js\n"
        "Loaded cached credentials\n"
        "Yolo mode is enabled\n"
        "Here is the code:\n"
        "def add(a, b):\n"
        "    return a + b\n"
    )
    cleaned = _strip_peer_noise(raw_output, "antigravity")
    assert "Keychain" not in cleaned
    assert "Require stack" not in cleaned
    assert "node_modules" not in cleaned
    assert "Loaded cached credentials" not in cleaned
    assert "Yolo mode is enabled" not in cleaned
    assert "Here is the code:" in cleaned
    assert "def add(a, b):" in cleaned


def test_detect_peer_delegation():
    """Verify regex and alias matching for natural language delegation."""
    cases = [
        ("ask antigravity to fix the bug", "antigravity", "fix the bug"),
        ("ask agy to refactor this function", "antigravity", "refactor this function"),
        ("ask gemini to summarize the module", "antigravity", "summarize the module"),
        ("have qwen write a test", "qwen", "write a test"),
        ("call claude to review", "claude", "review"),
        ("let qwen check the output", "qwen", "check the output"),
        ("agy: optimize loop", "antigravity", "optimize loop"),
        ("gemini, analyze performance", "antigravity", "analyze performance"),
        ("qwen - generate docstrings", "qwen", "generate docstrings"),
    ]
    for prompt, expected_peer, expected_task in cases:
        peer, task = _detect_peer_delegation(prompt)
        assert peer == expected_peer, f"Prompt: {prompt} -> peer={peer}, expected={expected_peer}"
        assert task == expected_task, f"Prompt: {prompt} -> task={task}, expected={expected_task}"


def test_tool_peer_delegate_disabled_fallback():
    """WP2.1 slice 4: the disabled-peer fallback branch dispatches through
    core/peer_shell.py's auto-approving subprocess launch just like the
    primary branch, so it is gated the same way -- HIGH_IMPACT with no
    confirmation path fails closed. The fallback peer's `call()` must
    NEVER actually run."""
    with patch("core.peer_cli.PeerCLIManager.available") as mock_avail, \
         patch("core.peer_cli.PeerCLIManager.call", return_value="def hello(): pass") as mock_call:
        agy_cli = next(c for c in PEER_REGISTRY if c.name == "antigravity")
        mock_avail.return_value = [agy_cli]

        result = tool_peer_delegate("claude", "write hello function")
        assert result.startswith("[BLOCKED]")
        mock_call.assert_not_called()


def test_tool_peer_delegate_success():
    """WP2.1 slice 4: TOOLS['peer_delegate']'s direct dispatch is always
    HIGH_IMPACT with no confirmation path available yet, so it fails
    closed -- the peer's `call()` must NEVER actually run."""
    with patch("core.peer_cli.PeerCLIManager.available") as mock_avail, \
         patch("core.peer_cli.PeerCLIManager.call", return_value="Success peer output") as mock_call:
        qwen_cli = next(c for c in PEER_REGISTRY if c.name == "qwen")
        mock_avail.return_value = [qwen_cli]

        result = tool_peer_delegate("qwen", "build script")
        assert result.startswith("[BLOCKED]")
        mock_call.assert_not_called()


def test_tool_peer_delegate_gated_through_action_gateway():
    """Invariant: tool_peer_delegate's real dispatch is unreachable except
    via ActionGateway.gate_exec(), called as HIGH_IMPACT with
    confirm_available=False (mirrors slices 1-3's own invariant-test
    pattern, tests/test_action_gateway.py). The audit ledger must record
    the refusal."""
    import tempfile
    from pathlib import Path

    from core.action_gateway import HIGH_IMPACT, OUTCOME_REFUSED, ActionGateway

    with tempfile.TemporaryDirectory() as tmpdir:
        audit_file = Path(tmpdir) / "audit.jsonl"
        test_gateway = ActionGateway(audit_file=audit_file)

        with patch("core.action_gateway.get_action_gateway", return_value=test_gateway), \
             patch("core.peer_cli.PeerCLIManager.available") as mock_avail, \
             patch("core.peer_cli.PeerCLIManager.call") as mock_call:
            qwen_cli = next(c for c in PEER_REGISTRY if c.name == "qwen")
            mock_avail.return_value = [qwen_cli]

            result = tool_peer_delegate("qwen", "build script")

        assert result.startswith("[BLOCKED]")
        mock_call.assert_not_called()

        records = [
            json.loads(line)
            for line in audit_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(records) == 1
        assert records[0]["authority"] == HIGH_IMPACT
        assert records[0]["outcome"] == OUTCOME_REFUSED
        assert records[0]["action"] == "peer_cli.tool_peer_delegate"


def test_tool_peer_delegate_dispatch_thunk_correct_when_allowed():
    """WP2.1 slice 4's gate_exec() call wraps the real `mgr.call()` dispatch
    in a thunk that is never exercised by the (now fail-closed-by-default)
    production path or by the [BLOCKED] tests above. Force an ALLOWED
    decision (as a future confirmation-UI slice would produce) to prove
    the thunk/result_wrapper wiring itself -- cli selection, summarize_result
    formatting, the disabled-peer-redirect message, and _record_teacher's
    argument order -- is actually correct, not just unreached."""
    import tempfile
    from pathlib import Path

    from core.action_gateway import ActionGateway, GatewayDecision, OUTCOME_ALLOWED

    class _AllowAllGateway(ActionGateway):
        def gate_exec(self, *, authority, action, command, confirm_available, execute):
            result = execute()
            return GatewayDecision(
                authority=authority, outcome=OUTCOME_ALLOWED, reason="test-allow",
                detail={"action": action, "command": command, "result": result},
            )

    allow_gateway = _AllowAllGateway(
        audit_file=Path(tempfile.mkdtemp()) / "audit.jsonl"
    )

    # Success branch: peer enabled and installed.
    with patch("core.action_gateway.get_action_gateway", return_value=allow_gateway), \
         patch("core.agent._record_teacher") as mock_teacher, \
         patch("core.peer_cli.PeerCLIManager.available") as mock_avail, \
         patch("core.peer_cli.PeerCLIManager.call", return_value="Success peer output") as mock_call:
        qwen_cli = next(c for c in PEER_REGISTRY if c.name == "qwen")
        mock_avail.return_value = [qwen_cli]

        result = tool_peer_delegate("qwen", "build script")

        mock_call.assert_called_once_with(qwen_cli, "build script")
        mock_teacher.assert_called_once_with("qwen", "build script", "Success peer output")
        assert "[Peer CLI — qwen]" in result
        assert "Success peer output" in result

    # Disabled-peer fallback branch.
    with patch("core.action_gateway.get_action_gateway", return_value=allow_gateway), \
         patch("core.agent._record_teacher") as mock_teacher, \
         patch("core.peer_cli.PeerCLIManager.available") as mock_avail, \
         patch("core.peer_cli.PeerCLIManager.call", return_value="def hello(): pass") as mock_call:
        agy_cli = next(c for c in PEER_REGISTRY if c.name == "antigravity")
        mock_avail.return_value = [agy_cli]

        result = tool_peer_delegate("claude", "write hello function")

        mock_call.assert_called_once_with(agy_cli, "write hello function")
        mock_teacher.assert_called_once_with("antigravity", "write hello function", "def hello(): pass")
        assert "[claude was disabled:" in result
        assert "Redirected to antigravity]" in result
        assert "def hello(): pass" in result


def test_tools_dict_peer_delegate_gated_and_arg_keys_normalized():
    """Invariant: TOOLS['peer_delegate'] (the actual model-reachable tool,
    not just the underlying function) is unreachable except via
    ActionGateway.gate_exec(), and its arg-key normalization (peer_name/
    name, prompt/command fallbacks) still works under the gate."""
    from core.agent import TOOLS

    with patch("core.peer_cli.PeerCLIManager.available") as mock_avail, \
         patch("core.peer_cli.PeerCLIManager.call") as mock_call:
        qwen_cli = next(c for c in PEER_REGISTRY if c.name == "qwen")
        mock_avail.return_value = [qwen_cli]

        result = TOOLS["peer_delegate"]({"peer_name": "qwen", "prompt": "build script"})

        assert result.startswith("[BLOCKED]")
        mock_call.assert_not_called()


def test_tool_peer_delegate_unknown_peer():
    """Verify tool_peer_delegate handles unknown peer names."""
    result = tool_peer_delegate("unknown_cli", "do something")
    assert "[Peer delegate error: unknown peer 'unknown_cli']" in result


def test_tool_peer_delegate_missing_args():
    """Verify tool_peer_delegate handles missing arguments."""
    result = tool_peer_delegate("", "")
    assert "[Peer delegate error:" in result
