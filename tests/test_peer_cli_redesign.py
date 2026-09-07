"""
Unit tests for Track A / Phase A2 Item 4.5: Peer-CLI Escalation Redesign.
"""

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
    """Verify tool_peer_delegate redirects disabled peers to an enabled peer."""
    with patch("core.peer_cli.PeerCLIManager.available") as mock_avail, \
         patch("core.peer_cli.PeerCLIManager.call", return_value="def hello(): pass") as mock_call:
        agy_cli = next(c for c in PEER_REGISTRY if c.name == "antigravity")
        mock_avail.return_value = [agy_cli]

        result = tool_peer_delegate("claude", "write hello function")
        assert "disabled" in result.lower() or "redirected" in result.lower()
        assert "antigravity" in result.lower()
        assert "def hello(): pass" in result


def test_tool_peer_delegate_success():
    """Verify tool_peer_delegate executes enabled peer and formats output."""
    with patch("core.peer_cli.PeerCLIManager.available") as mock_avail, \
         patch("core.peer_cli.PeerCLIManager.call", return_value="Success peer output"):
        qwen_cli = next(c for c in PEER_REGISTRY if c.name == "qwen")
        mock_avail.return_value = [qwen_cli]

        result = tool_peer_delegate("qwen", "build script")
        assert "[Peer CLI — qwen]" in result
        assert "Success peer output" in result


def test_tool_peer_delegate_unknown_peer():
    """Verify tool_peer_delegate handles unknown peer names."""
    result = tool_peer_delegate("unknown_cli", "do something")
    assert "[Peer delegate error: unknown peer 'unknown_cli']" in result


def test_tool_peer_delegate_missing_args():
    """Verify tool_peer_delegate handles missing arguments."""
    result = tool_peer_delegate("", "")
    assert "[Peer delegate error:" in result
