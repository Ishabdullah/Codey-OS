#!/usr/bin/env python3
"""Test for agent plugin."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# Resolve repo root using _pathutil
_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

from ccos.core.capability_registry import get_capability_registry
from ccos.core.plugin_manager import PluginManager, get_plugin_manager
from ccos.plugins.coding.agent.agent import (
    AgentExecutionResult,
    classify_breadth_capability,
    run_agent_capability,
    run_recursive_capability,
    scoped_agent_permissions,
    test,
)
from utils.config import AGENT_CONFIG


def test_manifest_structure():
    manifest_path = Path(__file__).parent / "manifest.json"
    assert manifest_path.exists(), "manifest.json must exist"
    manifest = json.loads(manifest_path.read_text())

    assert manifest["name"] == "agent"
    assert manifest["category"] == "coding"
    assert manifest["entry_point"] == "agent.py"

    cap_names = [c["name"] for c in manifest.get("capabilities", [])]
    assert "coding.run_agent" in cap_names
    assert "coding.run_recursive" in cap_names
    assert "coding.classify_breadth" in cap_names

    impls = {c["name"]: c["implementation"] for c in manifest["capabilities"]}
    assert impls["coding.run_agent"] == "agent:run_agent_capability"
    assert impls["coding.run_recursive"] == "agent:run_recursive_capability"
    assert impls["coding.classify_breadth"] == "agent:classify_breadth_capability"
    print("[PASS] test_manifest_structure")


def test_plugin_loading_via_plugin_manager():
    pm = PluginManager()
    assert pm.load("agent") is True, "PluginManager.load('agent') should succeed"

    plugin = pm.get_plugin("agent")
    assert plugin is not None
    assert plugin.status.value == "active"
    assert "coding.run_agent" in plugin.capabilities
    assert "coding.run_recursive" in plugin.capabilities
    assert "coding.classify_breadth" in plugin.capabilities

    registry = get_capability_registry()
    for cap_name in ["coding.run_agent", "coding.run_recursive", "coding.classify_breadth"]:
        cap = registry.get(cap_name)
        assert cap is not None, f"Capability {cap_name} should be registered in registry"
    print("[PASS] test_plugin_loading_via_plugin_manager")


def test_scoped_agent_permissions_success_and_exception():
    # Set initial baseline values
    orig_shell = AGENT_CONFIG.get("confirm_shell", True)
    orig_write = AGENT_CONFIG.get("confirm_write", True)
    orig_fn = AGENT_CONFIG.get("_shell_fn", None)

    dummy_shell = lambda cmd: "mock_shell"

    # Test clean exit
    with scoped_agent_permissions(confirm_shell=False, confirm_write=False, shell_fn=dummy_shell):
        assert AGENT_CONFIG.get("confirm_shell") is False
        assert AGENT_CONFIG.get("confirm_write") is False
        assert AGENT_CONFIG.get("_shell_fn") is dummy_shell

    assert AGENT_CONFIG.get("confirm_shell") == orig_shell
    assert AGENT_CONFIG.get("confirm_write") == orig_write
    assert AGENT_CONFIG.get("_shell_fn") == orig_fn

    # Test exception exit
    try:
        with scoped_agent_permissions(confirm_shell=False, confirm_write=False, shell_fn=dummy_shell):
            assert AGENT_CONFIG.get("confirm_shell") is False
            assert AGENT_CONFIG.get("confirm_write") is False
            raise ValueError("intentional error")
    except ValueError:
        pass

    assert AGENT_CONFIG.get("confirm_shell") == orig_shell
    assert AGENT_CONFIG.get("confirm_write") == orig_write
    assert AGENT_CONFIG.get("_shell_fn") == orig_fn
    print("[PASS] test_scoped_agent_permissions_success_and_exception")


def test_agent_execution_result_unpacking_and_dict():
    sample_history = [{"role": "user", "content": "hello"}]
    res = AgentExecutionResult(
        response="test response",
        history=sample_history,
        success=True,
        error="",
    )

    # 1. Unpacking test
    response, history = res
    assert response == "test response"
    assert history == sample_history

    # 2. Dict access
    assert res["response"] == "test response"
    assert res["history"] == sample_history
    assert res["success"] is True
    assert res["error"] == ""

    # 3. Attribute access
    assert res.response == "test response"
    assert res.history == sample_history
    assert res.success is True
    assert res.error == ""

    # 4. JSON serialization
    serialized = json.dumps(res)
    deserialized = json.loads(serialized)
    assert deserialized["response"] == "test response"
    assert deserialized["success"] is True
    print("[PASS] test_agent_execution_result_unpacking_and_dict")


def test_call_capabilities_via_plugin_manager():
    pm = PluginManager()
    pm.load("agent")

    # 1. coding.classify_breadth
    breadth = pm.call_capability("coding.classify_breadth", user_message="what is 2+2?")
    assert breadth == "minimal"

    # 2. coding.run_agent with mocked run_agent
    mock_response = "agent finished"
    mock_history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "agent finished"}]

    with patch("core.agent.run_agent", return_value=(mock_response, mock_history)) as mock_ra:
        result = pm.call_capability(
            "coding.run_agent",
            prompt="write code",
            history=[],
            yolo=True,
            no_plan=True,
            confirm_shell=False,
            confirm_write=False,
        )
        assert isinstance(result, dict)
        assert result.__class__.__name__ == "AgentExecutionResult"
        resp, hist = result
        assert resp == mock_response
        assert hist == mock_history
        assert result.success is True
        mock_ra.assert_called_once()

    print("[PASS] test_call_capabilities_via_plugin_manager")


def test_self_test():
    assert test() is True
    print("[PASS] test_self_test")


if __name__ == "__main__":
    test_manifest_structure()
    test_plugin_loading_via_plugin_manager()
    test_scoped_agent_permissions_success_and_exception()
    test_agent_execution_result_unpacking_and_dict()
    test_call_capabilities_via_plugin_manager()
    test_self_test()
    print("\nAll agent plugin tests passed!")
