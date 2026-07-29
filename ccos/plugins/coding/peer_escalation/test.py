#!/usr/bin/env python3
"""Test for peer_escalation plugin.

SAFETY: this test file must never trigger a real peer CLI session. The
wrapped functions (peer_list_available/peer_detect_task_type/
peer_select_cli/peer_build_prompt) are discovery/selection/preview logic
only — none of them call core/peer_cli.py's escalate()/confirm()/call(),
and none of them import or exercise core/peer_shell.py at all. The one
subprocess peer_list_available() may run is `claude --version` (only for
the "claude" entry, which sets check_cmd — gemini/qwen have no check_cmd
and are probed via shutil.which only), used purely to detect a known
native-module crash signature; it costs no API usage and returns near-
instantly regardless of whether claude is actually installed correctly.
"""
import importlib.util
from pathlib import Path

_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

from ccos.plugins.coding.peer_escalation.peer_escalation import (
    peer_build_prompt,
    peer_detect_task_type,
    peer_list_available,
    peer_select_cli,
    test,
)


def test_list_available_returns_real_env_state():
    result = peer_list_available()
    assert isinstance(result, list)
    for entry in result:
        assert set(entry.keys()) == {"name", "description", "strengths"}
        assert entry["name"] in ("claude", "gemini", "qwen")
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
    # Excluding all three known names simulates "nothing available" without
    # needing to mock installation state, and without invoking anything.
    result = peer_select_cli("debugging", exclude=["claude", "gemini", "qwen"])
    assert result == {"selected": None}, f"Unexpected result: {result}"
    print(f"[PASS] peer_select_cli() with everything excluded -> {result}")


def test_select_cli_reflects_real_availability():
    available_names = {c["name"] for c in peer_list_available()}
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
    test_self_test()
    print("\nAll peer_escalation tests passed! (no real peer CLI was invoked)")
