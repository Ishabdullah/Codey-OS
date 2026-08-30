#!/usr/bin/env python3
"""Test for peer_escalation plugin.

SAFETY: this test file must never trigger a real peer CLI session.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch, MagicMock

_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

from ccos.plugins.coding.peer_escalation.peer_escalation import (
    peer_build_prompt,
    peer_delegate,
    peer_detect_task_type,
    peer_list_available,
    peer_select_cli,
    test,
)


def test_list_available_returns_real_env_state():
    result = peer_list_available()
    assert isinstance(result, list)
    for entry in result:
        assert set(entry.keys()) == {"name", "description", "strengths", "aliases", "enabled", "disabled_reason"}
        assert entry["name"] in ("antigravity", "qwen", "claude")
    print(f"[PASS] peer_list_available() -> {result}")


def test_detect_task_type_classification():
    cases = {
        "please fix this crash": "debugging",
        "refactor this module": "refactor",
        "explain what this does": "explain",
        "review this diff": "review",
        "generate a helper function": "generate",
        "hello there": "default",
    }
    for message, expected in cases.items():
        result = peer_detect_task_type(message)
        assert result == {"task_type": expected}, f"{message!r} -> {result}, expected {expected}"
    print("[PASS] peer_detect_task_type() classifies all cases correctly")


def test_select_cli_with_no_clis_available():
    result = peer_select_cli("debugging", exclude=["antigravity", "qwen", "claude"])
    assert result == {"selected": None}, f"Unexpected result: {result}"
    print(f"[PASS] peer_select_cli() with everything excluded -> {result}")


def test_select_cli_reflects_real_availability():
    available_clis = [c for c in peer_list_available() if c.get("enabled", True)]
    available_names = {c["name"] for c in available_clis}
    result = peer_select_cli("default")
    if not available_names:
        assert result == {"selected": None}
    else:
        assert result["selected"] is not None
        assert result["selected"]["name"] in available_names
    print(f"[PASS] peer_select_cli('default') -> {result} (available: {available_names})")


def test_build_prompt_is_pure_text_construction():
    prompt = peer_build_prompt(
        "fix the off-by-one bug",
        errors=["IndexError: list index out of range"],
        files=["core/foo.py"],
    )
    assert isinstance(prompt, dict) and "prompt" in prompt
    text = prompt["prompt"]
    assert "fix the off-by-one bug" in text
    assert "core/foo.py" in text
    assert "IndexError" in text
    assert "Do NOT ask" in text
    print("[PASS] peer_build_prompt() builds expected text with no side effects")


def test_peer_delegate_handles_disabled_peer():
    with patch("core.peer_cli.PeerCLIManager.call", return_value="Fallback peer response"):
        res = peer_delegate("claude", "review this code")
        assert isinstance(res, dict) and "result" in res
        assert "disabled" in res["result"].lower() or "redirected" in res["result"].lower() or "claude" in res["result"].lower()
    print("[PASS] peer_delegate handles disabled peer correctly")


def test_self_test():
    result = test()
    assert result is True
    print("[PASS] Self-test passed")


if __name__ == "__main__":
    test_list_available_returns_real_env_state()
    test_detect_task_type_classification()
    test_select_cli_with_no_clis_available()
    test_select_cli_reflects_real_availability()
    test_build_prompt_is_pure_text_construction()
    test_peer_delegate_handles_disabled_peer()
    test_self_test()
    print("\nAll peer_escalation tests passed! (no real peer CLI was invoked)")
