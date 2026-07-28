#!/usr/bin/env python3
"""
CCOS Test Suite — Tests for all core modules.
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

# _pathutil.py lives at ccos/plugins/_pathutil.py, one level above this
# file's directory (test_ccos.py -> tests/ -> ccos/). Loaded by file path
# since the ccos package isn't importable yet.
_pathutil_path = Path(__file__).resolve().parent.parent / "plugins" / "_pathutil.py"
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

from ccos.core.device_manager import get_device_manager
from ccos.core.capability_registry import Capability, CapabilityStatus, get_capability_registry
from ccos.core.plugin_manager import get_plugin_manager
from ccos.core.sandbox import get_sandbox, Sandbox
from ccos.core.tool_router import get_tool_router
from ccos.core.planner import get_planner
from ccos.core.reflection_engine import get_reflection_engine
from ccos.core.memory.ccos_memory import get_ccos_memory


def test_device_manager():
    print("Testing DeviceManager...")
    dm = get_device_manager()
    profile = dm.get_profile()

    assert "os" in profile, "Missing 'os' in profile"
    assert "cpu" in profile, "Missing 'cpu' in profile"
    assert "ram" in profile, "Missing 'ram' in profile"
    assert profile["cpu"]["cores"] > 0, "CPU cores should be > 0"

    summary = dm.get_summary()
    assert len(summary) > 0, "Summary should not be empty"

    hints = dm.get_capabilities_hints()
    assert isinstance(hints, list), "Hints should be a list"

    print(f"  [PASS] Device: {profile['os']['name']}, {profile['cpu']['cores']} cores")
    print(f"  [PASS] Hardware hints: {hints}")
    return True


def test_capability_registry():
    print("Testing CapabilityRegistry...")
    # Use a temp path to avoid polluting the real registry
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        temp_path = f.name

    from ccos.core.capability_registry import CapabilityRegistry
    reg = CapabilityRegistry(store_path=temp_path)

    cap = Capability(
        name="test.cap",
        description="Test capability",
        implementation="test.py",
        category="test",
    )
    assert reg.register(cap), "Register should succeed"
    assert reg.has("test.cap"), "Should have test.cap"
    assert reg.count() == 1, "Count should be 1"

    # Query
    results = reg.query(category="test")
    assert len(results) == 1
    assert results[0].name == "test.cap"

    # Performance tracking
    reg.record_use("test.cap", True, 100)
    cap = reg.get("test.cap")
    assert cap.use_count == 1
    assert cap.success_count == 1
    assert cap.success_rate == 1.0

    # Unregister
    assert reg.unregister("test.cap"), "Unregister should succeed"
    assert not reg.has("test.cap"), "Should not have test.cap after unregister"

    Path(temp_path).unlink(missing_ok=True)
    print("  [PASS] Registration, querying, performance tracking")
    return True


def test_sandbox():
    print("Testing Sandbox...")
    sandbox = Sandbox()

    # Basic command
    result = sandbox.run_command("echo hello")
    assert result.success, f"echo should succeed: {result.stderr}"
    assert "hello" in result.stdout

    # Blocked command
    result = sandbox.run_command("rm -rf /")
    assert not result.success, "Blocked command should fail"
    assert "VIOLATION" in result.stderr

    # Python execution
    result = sandbox.run_python("print(2 + 2)")
    assert result.success, f"Python should succeed: {result.stderr}"
    assert "4" in result.stdout

    # Timeout
    result = sandbox.run_command("sleep 10", timeout=1)
    assert result.timed_out, "Should timeout"
    assert not result.success

    sandbox.cleanup()
    print("  [PASS] Command execution, blocking, Python, timeout")
    return True


def test_plugin_manager():
    print("Testing PluginManager...")
    pm = get_plugin_manager()

    plugins = pm.list_plugins()
    assert isinstance(plugins, list), "Plugins should be a list"
    assert len(plugins) >= 2, f"Expected at least 2 plugins, got {len(plugins)}"

    # Load all
    results = pm.load_all()
    loaded = sum(1 for v in results.values() if v)
    failed = {
        name: pm.get_plugin(name).error
        for name, v in results.items()
        if not v
    }
    assert loaded == len(plugins), (
        f"Expected all {len(plugins)} discovered plugins to load, got {loaded}. "
        f"Failed: {failed}"
    )

    # Check capabilities were registered
    from ccos.core.capability_registry import get_capability_registry
    reg = get_capability_registry()
    active = reg.get_active()
    assert len(active) >= 1, "Should have at least 1 active capability"

    print(f"  [PASS] Discovered {len(plugins)} plugins, loaded {loaded}, {len(active)} capabilities")
    return True


def test_tool_router():
    print("Testing ToolRouter...")
    router = get_tool_router()

    # Ensure some capabilities are loaded
    pm = get_plugin_manager()
    pm.load_all()

    recommendations = router.get_recommendations("read system information")
    assert isinstance(recommendations, list), "Recommendations should be a list"

    print(f"  [PASS] Got {len(recommendations)} recommendation(s)")
    for rec in recommendations[:3]:
        print(f"    - {rec['name']} (score: {rec['score']})")
    return True


def test_planner():
    print("Testing Planner...")
    planner = get_planner()

    # Ensure plugins are loaded
    pm = get_plugin_manager()
    pm.load_all()

    analysis = planner.analyze_request("capture a photo from the camera")
    assert isinstance(analysis, dict)
    assert "available_capabilities" in analysis
    assert "hardware_hints" in analysis

    plan = planner.create_plan("read system information")
    assert plan.goal == "read system information"
    assert len(plan.steps) > 0

    print(f"  [PASS] Analysis: {len(analysis['available_capabilities'])} capabilities")
    print(f"  [PASS] Plan: {len(plan.steps)} steps")
    return True


def test_reflection_engine():
    print("Testing ReflectionEngine...")
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        temp_path = f.name

    from ccos.core.reflection_engine import ReflectionEngine
    engine = ReflectionEngine(log_path=temp_path)

    reflection = engine.reflect(
        task="test task",
        success=True,
        capability_used="test.cap",
        duration_ms=100,
    )
    assert reflection.success
    assert reflection.task == "test task"

    summary = engine.get_improvement_summary()
    assert summary["total_tasks"] == 1

    Path(temp_path).unlink(missing_ok=True)
    print("  [PASS] Reflection and improvement tracking")
    return True


def test_memory():
    print("Testing CCOS Memory...")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = f.name

    from ccos.core.memory.ccos_memory import CCOSMemory
    mem = CCOSMemory(db_path=temp_path)

    # Store skill
    assert mem.structured.store_skill("test_skill", "A test skill", "test.py")
    skill = mem.structured.get_skill("test_skill")
    assert skill is not None
    assert skill["name"] == "test_skill"

    # Store workflow
    assert mem.structured.store_workflow(
        "test_workflow", "do something", ["step1", "step2"], "done", True, 100
    )
    workflows = mem.structured.get_successful_workflows()
    assert len(workflows) == 1

    # Event log
    mem.events.log("test_event", "test_source", "test details")
    events = mem.events.get_recent()
    assert len(events) >= 1

    # Store task result
    mem.store_task_result("test task", "test result", True, "test.cap", 150)

    Path(temp_path).unlink(missing_ok=True)
    print("  [PASS] Skills, workflows, events, task results")
    return True


def main():
    print("=" * 50)
    print("  CCOS Test Suite")
    print("=" * 50)
    print()

    tests = [
        test_device_manager,
        test_capability_registry,
        test_sandbox,
        test_plugin_manager,
        test_tool_router,
        test_planner,
        test_reflection_engine,
        test_memory,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
                print(f"  [FAIL] {test.__name__}")
        except Exception as e:
            failed += 1
            print(f"  [ERROR] {test.__name__}: {e}")
        print()

    print("=" * 50)
    print(f"  Results: {passed} passed, {failed} failed")
    print("=" * 50)
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
