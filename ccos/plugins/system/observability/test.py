#!/usr/bin/env python3
"""Test for observability plugin."""

import importlib.util
from pathlib import Path

# _pathutil.py lives at ccos/plugins/_pathutil.py, two levels above this
# plugin's directory (test.py -> observability/ -> system/ -> plugins/).
# Loaded by file path since the ccos package isn't importable yet.
_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

from ccos.plugins.system.observability.observability import (
    context_size,
    cpu_usage,
    daemon_pid,
    full_status,
    health,
    memory_loaded,
    memory_usage,
    model_active,
    model_state,
    reset_state,
    tasks_pending,
    tasks_running,
    temperature,
    test,
    tokens_used,
    uptime,
)


def test_tokens_used_is_int():
    tokens = tokens_used()
    assert isinstance(tokens, int)
    print(f"[PASS] tokens_used() -> {tokens}")


def test_memory_loaded_is_dict():
    mem = memory_loaded()
    assert isinstance(mem, dict)
    print(f"[PASS] memory_loaded() -> {mem}")


def test_tasks_pending_and_running_are_ints():
    pending = tasks_pending()
    running = tasks_running()
    assert isinstance(pending, int)
    assert isinstance(running, int)
    print(f"[PASS] tasks_pending()={pending}, tasks_running()={running}")


def test_model_active_and_state():
    active = model_active()
    state = model_state()
    assert active is None or isinstance(active, str)
    assert isinstance(state, dict)
    print(f"[PASS] model_active()={active!r}, model_state()={state}")


def test_temperature_and_context_size():
    temp = temperature()
    ctx = context_size()
    assert isinstance(temp, float)
    assert isinstance(ctx, int) and ctx > 0
    print(f"[PASS] temperature()={temp}, context_size()={ctx}")


def test_memory_usage_has_real_data():
    mem = memory_usage()
    assert isinstance(mem, dict)
    assert "rss_mb" in mem and "vms_mb" in mem
    assert mem["rss_mb"] > 0, "Expected real RSS, got 0"
    print(f"[PASS] memory_usage() returned real data: {mem}")


def test_cpu_usage_is_float():
    cpu = cpu_usage()
    assert isinstance(cpu, float)
    print(f"[PASS] cpu_usage() -> {cpu}")


def test_uptime_is_int():
    up = uptime()
    assert isinstance(up, int)
    print(f"[PASS] uptime() -> {up}")


def test_daemon_pid():
    pid = daemon_pid()
    assert pid is None or isinstance(pid, int)
    print(f"[PASS] daemon_pid() -> {pid}")


def test_health_shape():
    h = health()
    assert isinstance(h, dict)
    for key in ("memory_usage", "cpu_usage", "uptime_seconds", "tasks_pending", "model_loaded"):
        assert key in h, f"Missing key {key}"
    print(f"[PASS] health() -> {h}")


def test_full_status_shape():
    status = full_status()
    assert isinstance(status, dict)
    for key in ("version", "daemon", "model", "tasks", "memory", "cpu", "tokens", "health"):
        assert key in status, f"Missing key {key}"
    print(f"[PASS] full_status() -> {status}")


def test_reset_state_is_safe():
    before = full_status()
    reset_state()
    after = full_status()
    assert isinstance(after, dict)
    assert after["version"] == before["version"]
    print("[PASS] reset_state() left full_status() callable and consistent")


def test_self_test():
    result = test()
    assert result is True
    print("[PASS] Self-test passed")


if __name__ == "__main__":
    test_tokens_used_is_int()
    test_memory_loaded_is_dict()
    test_tasks_pending_and_running_are_ints()
    test_model_active_and_state()
    test_temperature_and_context_size()
    test_memory_usage_has_real_data()
    test_cpu_usage_is_float()
    test_uptime_is_int()
    test_daemon_pid()
    test_health_shape()
    test_full_status_shape()
    test_reset_state_is_safe()
    test_self_test()
    print("\nAll observability tests passed!")
