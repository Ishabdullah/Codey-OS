#!/usr/bin/env python3
"""
CCOS Telemetry Engine Test Suite.

Tests execution logging, drift detection, sandbox-vs-real gap
analysis, health scoring, and feedback injection.
"""

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ccos.core.telemetry_engine import (
    TelemetryEngine,
    ExecutionRecord,
    DriftAlert,
    HealthReport,
    get_telemetry_engine,
)


def _make_temp_engine():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return TelemetryEngine(db_path=f.name), f.name


def test_execution_logging():
    """Every execution should be logged."""
    print("Testing Execution Logging...")
    engine, path = _make_temp_engine()

    engine.record(
        task="read system information",
        success=True,
        capability="system.info",
        duration_ms=45,
        source="real",
    )
    engine.record(
        task="list processes",
        success=True,
        capability="system.processes",
        duration_ms=30,
        source="real",
    )
    engine.force_flush()

    recent = engine.get_recent_executions(limit=10, source="real")
    assert len(recent) == 2
    assert recent[0]["capability"] == "system.processes"
    assert recent[1]["capability"] == "system.info"

    print(f"  [PASS] Logged {len(recent)} executions")
    Path(path).unlink(missing_ok=True)
    return True


def test_buffered_writes():
    """Writes should be buffered for performance."""
    print("Testing Buffered Writes...")
    engine, path = _make_temp_engine()
    engine._buffer_size = 5

    # Write 4 records (below buffer threshold)
    for i in range(4):
        engine.record(task=f"task {i}", success=True, capability="test.cap")
    assert len(engine._buffer) == 4

    # 5th record triggers flush
    engine.record(task="task 4", success=True, capability="test.cap")
    assert len(engine._buffer) == 0  # Flushed

    recent = engine.get_recent_executions(limit=10)
    assert len(recent) == 5

    print(f"  [PASS] Buffer flushed at threshold, {len(recent)} records persisted")
    Path(path).unlink(missing_ok=True)
    return True


def test_sandbox_vs_real_tracking():
    """Sandbox and real executions should be tracked separately."""
    print("Testing Sandbox vs Real Tracking...")
    engine, path = _make_temp_engine()

    # Record sandbox executions
    for i in range(5):
        engine.record(task=f"sandbox test {i}", success=True,
                     capability="test.cap", duration_ms=100, source="sandbox")

    # Record real executions (slower, some failures)
    for i in range(5):
        engine.record(task=f"real task {i}", success=i < 4,
                     capability="test.cap", duration_ms=200, source="real")
    engine.force_flush()

    stats = engine.get_execution_stats()
    assert stats["sandbox_executions"] == 5
    assert stats["real_executions"] == 5
    assert stats["real_success_rate"] == 0.8

    print(f"  [PASS] Sandbox: {stats['sandbox_executions']}, Real: {stats['real_executions']}")
    Path(path).unlink(missing_ok=True)
    return True


def test_baseline_update():
    """Baselines should be computed from real-world data."""
    print("Testing Baseline Update...")
    engine, path = _make_temp_engine()

    # Record enough real executions
    for i in range(10):
        engine.record(task=f"task {i}", success=True,
                     capability="system.info", duration_ms=50 + i * 5,
                     source="real")
    engine.force_flush()

    engine.update_baseline("system.info")
    baselines = engine.get_baselines()

    assert "system.info" in baselines
    assert baselines["system.info"]["duration_ms"] > 0
    assert baselines["system.info"]["success_rate"] == 1.0
    assert baselines["system.info"]["sample_count"] == 10

    print(f"  [PASS] Baseline: avg={baselines['system.info']['duration_ms']:.0f}ms, "
          f"success={baselines['system.info']['success_rate']:.0%}")
    Path(path).unlink(missing_ok=True)
    return True


def test_drift_detection_speed():
    """Should detect when capability gets slower."""
    print("Testing Speed Drift Detection...")
    engine, path = _make_temp_engine()

    # Establish baseline (fast)
    for i in range(10):
        engine.record(task=f"fast {i}", success=True,
                     capability="slow.cap", duration_ms=100, source="real")
    engine.force_flush()
    engine.update_baseline("slow.cap")

    # Simulate degradation (3x slower)
    for i in range(10):
        engine.record(task=f"slow {i}", success=True,
                     capability="slow.cap", duration_ms=300, source="real")
    engine.force_flush()

    # Detect drift
    alert = engine.detect_drift("slow.cap")
    assert alert is not None
    assert alert.drift_type == "speed"
    assert alert.drift_pct > 30  # At least 30% slower
    assert alert.severity in ("medium", "high")

    print(f"  [PASS] Drift detected: {alert.drift_type}, {alert.drift_pct:.0f}%, severity={alert.severity}")
    Path(path).unlink(missing_ok=True)
    return True


def test_drift_detection_reliability():
    """Should detect when capability becomes less reliable."""
    print("Testing Reliability Drift Detection...")
    engine, path = _make_temp_engine()

    # Establish baseline (reliable)
    for i in range(10):
        engine.record(task=f"reliable {i}", success=True,
                     capability="flakey.cap", duration_ms=100, source="real")
    engine.force_flush()
    engine.update_baseline("flakey.cap")

    # Simulate unreliability (50% failures)
    for i in range(10):
        engine.record(task=f"flakey {i}", success=i < 5,
                     capability="flakey.cap", duration_ms=100, source="real")
    engine.force_flush()

    alert = engine.detect_drift("flakey.cap")
    assert alert is not None
    assert alert.drift_type == "reliability"
    assert alert.severity in ("medium", "high")

    print(f"  [PASS] Reliability drift: {alert.drift_pct:.0f}% increase in errors")
    Path(path).unlink(missing_ok=True)
    return True


def test_sandbox_vs_real_gap():
    """Should compare sandbox and real performance."""
    print("Testing Sandbox vs Real Gap Analysis...")
    engine, path = _make_temp_engine()

    # Sandbox: fast, reliable
    for i in range(5):
        engine.record(task=f"sandbox {i}", success=True,
                     capability="gap.cap", duration_ms=100, source="sandbox")

    # Real: slower, some failures
    for i in range(5):
        engine.record(task=f"real {i}", success=i < 4,
                     capability="gap.cap", duration_ms=150, source="real")
    engine.force_flush()

    gap = engine.compare_sandbox_vs_real("gap.cap")
    assert gap["available"] is True
    assert gap["speed_delta_pct"] > 0  # Real is slower
    assert gap["sandbox"]["avg_ms"] < gap["real"]["avg_ms"]
    assert gap["insight"] != ""

    print(f"  [PASS] Gap: speed delta={gap['speed_delta_pct']:.0f}%, "
          f"success delta={gap['success_delta_pct']:.0f}%")
    print(f"  Insight: {gap['insight']}")

    Path(path).unlink(missing_ok=True)
    return True


def test_health_report():
    """Health report should reflect system state."""
    print("Testing Health Report...")
    engine, path = _make_temp_engine()

    # Record mixed executions
    for i in range(20):
        engine.record(
            task=f"task {i}", success=i < 18,  # 90% success
            capability="test.cap", duration_ms=100, source="real",
        )
    engine.force_flush()

    report = engine.get_health_report()
    assert isinstance(report, HealthReport)
    assert 0 <= report.health_score <= 1
    assert report.trend in ("improving", "stable", "degrading")
    assert isinstance(report.risk_flags, list)
    assert "execution_stability" in report.component_scores

    print(f"  [PASS] Health: {report.health_score:.3f}, trend={report.trend}")
    print(f"  Components: {report.component_scores}")
    if report.risk_flags:
        print(f"  Risk flags: {report.risk_flags}")

    Path(path).unlink(missing_ok=True)
    return True


def test_goal_engine_insights():
    """Telemetry should generate insights for goal engine."""
    print("Testing Goal Engine Insights...")
    engine, path = _make_temp_engine()

    # Create drift scenario
    for i in range(10):
        engine.record(task=f"fast {i}", success=True,
                     capability="degrading.cap", duration_ms=100, source="real")
    engine.force_flush()
    engine.update_baseline("degrading.cap")

    for i in range(10):
        engine.record(task=f"slow {i}", success=i < 6,
                     capability="degrading.cap", duration_ms=400, source="real")
    engine.force_flush()
    engine.detect_drift("degrading.cap")

    insights = engine.get_insights_for_goal_engine()
    assert len(insights) >= 1
    drift_insights = [i for i in insights if i["type"] == "drift"]
    assert len(drift_insights) >= 1

    print(f"  [PASS] {len(insights)} insight(s) for goal engine")
    for ins in insights[:3]:
        print(f"    [{ins['type']}] {ins.get('suggestion', '')[:80]}")

    Path(path).unlink(missing_ok=True)
    return True


def test_optimization_recommendations():
    """Telemetry should recommend optimizations."""
    print("Testing Optimization Recommendations...")
    engine, path = _make_temp_engine()

    # Slow, unreliable capability
    for i in range(10):
        engine.record(task=f"task {i}", success=i < 5,
                     capability="bad.cap", duration_ms=5000, source="real")
    engine.force_flush()

    recs = engine.get_optimization_recommendations()
    assert len(recs) >= 1
    assert any("bad.cap" in r["capability"] for r in recs)

    print(f"  [PASS] {len(recs)} recommendation(s)")
    for r in recs[:3]:
        print(f"    {r['recommendation']}")

    Path(path).unlink(missing_ok=True)
    return True


def test_no_drift_when_stable():
    """No drift alert when performance is stable."""
    print("Testing No Drift When Stable...")
    engine, path = _make_temp_engine()

    # Consistent performance
    for i in range(20):
        engine.record(task=f"stable {i}", success=True,
                     capability="stable.cap", duration_ms=100, source="real")
    engine.force_flush()
    engine.update_baseline("stable.cap")

    alert = engine.detect_drift("stable.cap")
    assert alert is None

    print(f"  [PASS] No false drift alert for stable capability")
    Path(path).unlink(missing_ok=True)
    return True


def test_persistence():
    """Telemetry data should persist across engine instances."""
    print("Testing Persistence...")
    engine, path = _make_temp_engine()

    for i in range(5):
        engine.record(task=f"persist test {i}", success=True,
                     capability="test.cap", duration_ms=50, source="real")
    engine.force_flush()
    engine.update_baseline("test.cap")

    # New engine instance
    engine2 = TelemetryEngine(db_path=path)
    recent = engine2.get_recent_executions(limit=10)
    assert len(recent) >= 1
    baselines = engine2.get_baselines()
    assert "test.cap" in baselines

    print(f"  [PASS] Data persisted: {len(recent)} executions, {len(baselines)} baselines")
    Path(path).unlink(missing_ok=True)
    return True


def main():
    print("=" * 55)
    print("  CCOS Telemetry Engine Test Suite")
    print("=" * 55)
    print()

    tests = [
        test_execution_logging,
        test_buffered_writes,
        test_sandbox_vs_real_tracking,
        test_baseline_update,
        test_drift_detection_speed,
        test_drift_detection_reliability,
        test_sandbox_vs_real_gap,
        test_health_report,
        test_goal_engine_insights,
        test_optimization_recommendations,
        test_no_drift_when_stable,
        test_persistence,
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
