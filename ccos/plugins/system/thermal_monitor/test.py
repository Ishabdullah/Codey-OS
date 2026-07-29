#!/usr/bin/env python3
"""Test for thermal_monitor plugin."""

import importlib.util
import time
from pathlib import Path

# _pathutil.py lives at ccos/plugins/_pathutil.py, two levels above this
# plugin's directory (test.py -> thermal_monitor/ -> system/ -> plugins/).
# Loaded by file path since the ccos package isn't importable yet.
_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

from ccos.plugins.system.thermal_monitor.thermal_monitor import (
    monitor_render_text,
    monitor_snapshot,
    test,
    thermal_current_threads,
    thermal_end_inference,
    thermal_is_throttled,
    thermal_reset,
    thermal_start_inference,
    thermal_status,
)


def test_monitor_snapshot_has_real_data():
    snap = monitor_snapshot()
    assert isinstance(snap, dict)
    for key in ("cpu", "ram_used", "ram_total", "temp", "battery_pct", "battery_charging"):
        assert key in snap, f"Missing key {key}"
    assert isinstance(snap["cpu"], float)
    assert snap["ram_total"] > 0, "Expected real RAM total, got 0"
    print(f"[PASS] monitor_snapshot() returned real data: {snap}")


def test_monitor_render_text():
    text = monitor_render_text()
    assert isinstance(text, str)
    assert "CPU" in text and "RAM" in text
    print(f"[PASS] monitor_render_text() -> {text!r}")


def test_thermal_status_shape():
    status = thermal_status()
    assert isinstance(status, dict)
    for key in (
        "total_inference_sec",
        "current_threads",
        "original_threads",
        "warnings_issued",
        "thread_reductions",
        "throttled",
    ):
        assert key in status, f"Missing key {key}"
    print(f"[PASS] thermal_status() -> {status}")


def test_thermal_is_throttled_and_threads_agree():
    throttled = thermal_is_throttled()
    threads = thermal_current_threads()
    status = thermal_status()
    assert throttled == status["throttled"]
    assert threads == status["current_threads"]
    print(f"[PASS] thermal_is_throttled()={throttled}, thermal_current_threads()={threads}")


def test_start_end_inference_updates_state():
    before = thermal_status()["total_inference_sec"]
    thermal_start_inference()
    time.sleep(0.05)
    thermal_end_inference()
    after = thermal_status()["total_inference_sec"]
    assert after > before, f"Expected total_inference_sec to increase ({before} -> {after})"
    print(f"[PASS] start/end_inference() advanced total_inference_sec {before} -> {after}")


def test_thermal_reset_clears_counters():
    thermal_start_inference()
    time.sleep(0.02)
    thermal_end_inference()
    assert thermal_status()["total_inference_sec"] > 0
    thermal_reset()
    assert thermal_status()["total_inference_sec"] == 0
    print("[PASS] thermal_reset() cleared tracked inference time")


def test_self_test():
    result = test()
    assert result is True
    print("[PASS] Self-test passed")


if __name__ == "__main__":
    test_monitor_snapshot_has_real_data()
    test_monitor_render_text()
    test_thermal_status_shape()
    test_thermal_is_throttled_and_threads_agree()
    test_start_end_inference_updates_state()
    test_thermal_reset_clears_counters()
    test_self_test()
    print("\nAll thermal_monitor tests passed!")
