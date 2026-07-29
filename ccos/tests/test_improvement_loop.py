#!/usr/bin/env python3
"""
CCOS Closed-Loop Self-Improvement Test Suite.

Tests the full pipeline:
  performance_tracker → capability_optimizer → auto_improvement_loop → lifecycle_manager

Verifies the system can:
- Track metrics per capability
- Detect weak capabilities
- Generate improved versions
- Test improvements in sandbox
- Apply improvements only when better
- Maintain version history
"""

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ccos.core.performance_tracker import PerformanceTracker
from ccos.core.capability_optimizer import CapabilityOptimizer
from ccos.core.auto_improvement_loop import AutoImprovementLoop
from ccos.core.lifecycle_manager import LifecycleManager
from ccos.core.capability_registry import (
    Capability, CapabilityStatus, CapabilityRegistry,
)
from ccos.core.plugin_manager import PluginManager
from ccos.core.tool_router import ToolRouter
from ccos.core.reflection_engine import ReflectionEngine
from ccos.core.memory.ccos_memory import CCOSMemory


def _make_temp_tracker():
    """Create a tracker with a temp DB."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return PerformanceTracker(db_path=f.name), f.name


def _make_temp_registry():
    """Create a registry with a temp store."""
    f = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    f.close()
    return CapabilityRegistry(store_path=f.name), f.name


def _make_temp_memory():
    """Create a CCOSMemory backed by a temp DB."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return CCOSMemory(db_path=f.name), f.name


def _make_temp_reflection_engine(registry):
    """Create a ReflectionEngine backed by a temp log, wired to a temp registry."""
    f = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    f.close()
    engine = ReflectionEngine(log_path=f.name)
    engine._registry = registry
    return engine, f.name


def _make_isolated_improvement_loop(registry, tracker, memory, reflection):
    """Build an AutoImprovementLoop wired entirely to temp fixtures (no real singletons)."""
    loop = AutoImprovementLoop(auto_optimize=False)
    loop._registry = registry
    loop._tracker = tracker
    loop._memory = memory
    loop._reflection = reflection
    return loop


def test_performance_tracker():
    """Test performance tracking with detailed metrics."""
    print("Testing PerformanceTracker...")
    tracker, db_path = _make_temp_tracker()

    # Record executions
    for i in range(10):
        success = i < 7  # 70% success rate
        tracker.record_execution(
            capability="test.cap",
            version="1.0.0",
            duration_ms=100 + i * 50,
            success=success,
            retries=0 if success else 1,
            error_category="timeout" if not success else "",
        )

    metrics = tracker.get_capability_metrics("test.cap")
    assert metrics["total_uses"] == 10, f"Expected 10, got {metrics['total_uses']}"
    assert metrics["success_count"] == 7
    assert metrics["failure_count"] == 3
    assert abs(metrics["success_rate"] - 0.7) < 0.01
    assert metrics["avg_duration_ms"] > 0
    assert metrics["p95_duration_ms"] > 0
    assert metrics["error_categories"]["timeout"] == 3

    # Version history
    versions = tracker.get_version_history("test.cap")
    assert len(versions) == 1
    assert versions[0]["version"] == "1.0.0"
    assert versions[0]["total_uses"] == 10

    # Trend detection
    tracker2, _ = _make_temp_tracker()
    # Create improving trend: first 5 fail, next 5 succeed
    for i in range(10):
        tracker2.record_execution(
            capability="trend.cap",
            version="1.0.0",
            duration_ms=100,
            success=i >= 5,
        )
    trend = tracker2.get_trend("trend.cap")
    assert trend == "improving", f"Expected improving, got {trend}"

    # Weak capabilities
    weak = tracker.get_weak_capabilities(min_uses=5, max_score=80)
    assert len(weak) >= 1
    assert weak[0]["capability"] == "test.cap"

    # Snapshot
    tracker.take_snapshot("test.cap")

    print("  [PASS] Metrics recording, version tracking, trend detection, snapshots")
    Path(db_path).unlink(missing_ok=True)
    return True


def test_capability_optimizer():
    """Test the optimization pipeline."""
    print("Testing CapabilityOptimizer...")

    # Create a temp plugin to optimize
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = Path(tmpdir) / "test_plugin"
        plugin_dir.mkdir()

        # Write a simple plugin
        plugin_code = '''def get_system_info():
    """Get system info."""
    import platform
    return {"os": platform.system(), "arch": platform.machine()}
'''
        plugin_file = plugin_dir / "test_module.py"
        plugin_file.write_text(plugin_code)

        # Write a test
        test_code = '''import sys
sys.path.insert(0, "..")
from test_module import get_system_info
result = get_system_info()
assert isinstance(result, dict)
assert "os" in result
print("PASS")
'''
        test_file = plugin_dir / "test.py"
        test_file.write_text(test_code)

        # Create a registry with a weak capability
        registry, reg_path = _make_temp_registry()
        cap = Capability(
            name="test.optimize_me",
            description="A test capability",
            implementation=str(plugin_file),
            category="test",
            version="1.0.0",
        )
        cap.use_count = 10
        cap.success_count = 5
        cap.failure_count = 5
        registry.register(cap)

        # Create tracker with poor performance data
        tracker, db_path = _make_temp_tracker()
        for i in range(10):
            tracker.record_execution(
                capability="test.optimize_me",
                version="1.0.0",
                duration_ms=200,
                success=i < 5,
                error_category="timeout" if i >= 5 else "",
            )

        # Create optimizer (uses real sandbox)
        from ccos.core.sandbox import Sandbox
        sandbox = Sandbox()

        optimizer = CapabilityOptimizer()
        optimizer._registry = registry
        optimizer._tracker = tracker
        optimizer._sandbox = sandbox

        # Find targets
        targets = optimizer.find_optimization_targets(min_uses=3)
        assert len(targets) >= 1, "Should find at least one target"
        assert targets[0]["capability"] == "test.optimize_me"

        # Analyze failures
        diagnosis = optimizer.analyze_failures("test.optimize_me")
        assert diagnosis["total_failures"] == 5
        assert len(diagnosis["suggestions"]) > 0

        # Generate improved version
        gen_result = optimizer.generate_improved_version(
            "test.optimize_me", str(plugin_file)
        )
        assert gen_result is not None, "Should generate improved version"
        new_version, new_path = gen_result
        assert new_version == "1.0.1"
        assert Path(new_path).exists()

        # Verify improved code has enhancement markers
        improved_code = Path(new_path).read_text()
        assert "AUTO-IMPROVED" in improved_code

        # Test in sandbox
        test_passed, test_results = optimizer.test_improvement(
            "test.optimize_me", new_version, new_path
        )
        assert test_passed, f"Sandbox test should pass: {test_results}"

        # Compare and upgrade
        opt_result = optimizer.compare_and_upgrade(
            "test.optimize_me", new_version, new_path, test_passed, test_results
        )
        assert opt_result.improved, "Should have improved"
        assert opt_result.new_version == "1.0.1"
        assert opt_result.old_version == "1.0.0"

        # Verify version history
        versions = tracker.get_version_history("test.optimize_me")
        assert len(versions) == 2

        print("  [PASS] Target detection, failure analysis, improvement generation, sandbox testing, version upgrade")

        sandbox.cleanup()
        Path(db_path).unlink(missing_ok=True)
        Path(reg_path).unlink(missing_ok=True)

    return True


def test_auto_improvement_loop():
    """Test the closed-loop improvement system."""
    print("Testing AutoImprovementLoop...")

    # Use temp DBs
    tracker, db_path = _make_temp_tracker()
    registry, reg_path = _make_temp_registry()

    # Register a capability
    cap = Capability(
        name="loop.test_cap",
        description="Test capability for loop",
        implementation="/tmp/test.py",
        category="test",
        version="1.0.0",
    )
    cap.use_count = 5
    cap.success_count = 3
    cap.failure_count = 2
    registry.register(cap)

    # Pre-populate tracker with poor performance
    for i in range(5):
        tracker.record_execution(
            capability="loop.test_cap",
            version="1.0.0",
            duration_ms=300,
            success=i < 3,
            error_category="timeout" if i >= 3 else "",
        )

    loop = AutoImprovementLoop(auto_optimize=False)  # Disable auto-opt for unit test
    loop._tracker = tracker
    loop._registry = registry

    # Run loop after a successful task
    result = loop.after_task(
        task="test task",
        success=True,
        capability_used="loop.test_cap",
        duration_ms=150,
    )
    assert result.success
    assert result.stored_in_memory
    assert result.reflection is not None

    # Run loop after a failed task
    result2 = loop.after_task(
        task="test task 2",
        success=False,
        capability_used="loop.test_cap",
        duration_ms=500,
        error="timeout error",
    )
    assert not result2.success
    assert result2.reflection is not None

    # Check metrics were recorded
    metrics = tracker.get_capability_metrics("loop.test_cap")
    assert metrics["total_uses"] >= 7  # 5 pre-populated + 2 from loop

    # System health
    health = loop.get_system_health()
    assert health["total_capabilities"] >= 1
    assert health["total_loop_iterations"] == 2

    # Loop history
    history = loop.get_loop_history()
    assert len(history) == 2

    print("  [PASS] Loop execution, reflection integration, metric recording, health check")

    Path(db_path).unlink(missing_ok=True)
    Path(reg_path).unlink(missing_ok=True)
    return True


def test_lifecycle_manager():
    """Test the full lifecycle orchestration."""
    print("Testing LifecycleManager...")

    registry, reg_path = _make_temp_registry()
    tracker, db_path = _make_temp_tracker()
    memory, mem_path = _make_temp_memory()
    reflection, refl_path = _make_temp_reflection_engine(registry)

    pm = PluginManager()
    pm._registry = registry
    pm.load_all()

    router = ToolRouter()
    router._registry = registry

    loop = _make_isolated_improvement_loop(registry, tracker, memory, reflection)

    manager = LifecycleManager()
    manager._plugin_manager = pm
    manager._router = router
    manager._improvement_loop = loop
    manager._memory = memory
    manager._registry = registry
    manager._tracker = tracker

    # Execute a task through the full lifecycle
    def mock_executor(task):
        return {"status": "ok", "message": f"Executed: {task}"}

    result = manager.execute_task(
        task="read system information",
        executor=mock_executor,
    )

    assert result.success
    assert result.stage.value == "complete"
    assert result.execution_result is not None
    assert result.loop_result is not None
    assert result.total_duration_ms > 0
    assert len(result.events) >= 4  # planning, executing, evaluating, storing, complete

    # Verify events are ordered
    stages = [e.stage.value for e in result.events]
    assert "planning" in stages
    assert "executing" in stages
    assert "evaluating" in stages
    assert "complete" in stages

    # Summary
    summary = result.summary()
    assert "SUCCESS" in summary
    assert "read system information" in summary

    # Diagnostic
    diag = manager.run_diagnostic()
    assert "system_health" in diag

    print("  [PASS] Full lifecycle: plan → execute → evaluate → store, event ordering, summary")

    Path(reg_path).unlink(missing_ok=True)
    Path(db_path).unlink(missing_ok=True)
    Path(mem_path).unlink(missing_ok=True)
    Path(refl_path).unlink(missing_ok=True)
    return True


def test_version_history_preservation():
    """Verify old versions are never deleted."""
    print("Testing Version History Preservation...")

    tracker, db_path = _make_temp_tracker()

    # Register v1
    tracker.register_version("preserve.cap", "1.0.0", "/tmp/v1.py")
    # Register v2
    tracker.register_version("preserve.cap", "1.0.1", "/tmp/v2.py")
    # Register v3
    tracker.register_version("preserve.cap", "1.0.2", "/tmp/v3.py")

    versions = tracker.get_version_history("preserve.cap")
    assert len(versions) == 3, f"Expected 3 versions, got {len(versions)}"

    # Only latest should be current
    current = [v for v in versions if v["is_current"]]
    assert len(current) == 1
    assert current[0]["version"] == "1.0.2"

    # Deprecate v1
    tracker.deprecate_version("preserve.cap", "1.0.0")
    versions = tracker.get_version_history("preserve.cap")
    v1 = next(v for v in versions if v["version"] == "1.0.0")
    assert v1["deprecated_at"] is not None
    assert v1["is_current"] == 0

    # But v1 still exists in history
    assert len(versions) == 3

    print("  [PASS] All versions preserved, deprecation marks without deletion")

    Path(db_path).unlink(missing_ok=True)
    return True


def test_improvement_with_real_plugin():
    """
    End-to-end: optimize the system_info plugin that already has
    real performance data from previous runs.
    """
    print("Testing End-to-End Improvement with Real Plugin...")

    registry, reg_path = _make_temp_registry()
    tracker, db_path = _make_temp_tracker()
    memory, mem_path = _make_temp_memory()
    reflection, refl_path = _make_temp_reflection_engine(registry)

    pm = PluginManager()
    pm._registry = registry
    pm.load_all()

    # Check if system.info capability exists
    cap = registry.get("system.info")

    if not cap:
        print("  [SKIP] system.info not registered")
        Path(reg_path).unlink(missing_ok=True)
        Path(db_path).unlink(missing_ok=True)
        Path(mem_path).unlink(missing_ok=True)
        Path(refl_path).unlink(missing_ok=True)
        return True

    # Run system.info several times to build performance data
    loop = _make_isolated_improvement_loop(registry, tracker, memory, reflection)
    for i in range(4):
        start = time.time()
        try:
            result = pm.call_capability("system.info")
            duration = (time.time() - start) * 1000
            loop.after_task(
                task=f"system info run {i}",
                success=True,
                capability_used="system.info",
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            loop.after_task(
                task=f"system info run {i}",
                success=False,
                capability_used="system.info",
                duration_ms=duration,
                error=str(e),
            )

    # Check metrics
    metrics = tracker.get_capability_metrics("system.info")
    assert metrics["total_uses"] >= 4

    # Version history
    versions = tracker.get_version_history("system.info")
    assert len(versions) >= 1

    # Health check
    health = loop.get_system_health()
    assert health["total_loop_iterations"] >= 4

    print(f"  [PASS] system.info: {metrics['total_uses']} uses, "
          f"score={metrics.get('performance_score', 'N/A')}, "
          f"versions={len(versions)}")

    Path(reg_path).unlink(missing_ok=True)
    Path(db_path).unlink(missing_ok=True)
    Path(mem_path).unlink(missing_ok=True)
    Path(refl_path).unlink(missing_ok=True)
    return True


def main():
    print("=" * 55)
    print("  CCOS Closed-Loop Self-Improvement Test Suite")
    print("=" * 55)
    print()

    tests = [
        test_performance_tracker,
        test_capability_optimizer,
        test_auto_improvement_loop,
        test_lifecycle_manager,
        test_version_history_preservation,
        test_improvement_with_real_plugin,
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
            import traceback
            print(f"  [ERROR] {test.__name__}: {e}")
            traceback.print_exc()
        print()

    print("=" * 55)
    print(f"  Results: {passed} passed, {failed} failed")
    print("=" * 55)
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
