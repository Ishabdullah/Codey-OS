#!/usr/bin/env python3
"""Test for system_info plugin."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from ccos.plugins.system.system_info.system_info import get_system_info, list_processes, test


def test_get_system_info():
    info = get_system_info()
    assert isinstance(info, dict)
    assert "hostname" in info
    assert "cpu" in info
    assert "memory" in info
    assert info["cpu"]["cores"] > 0
    print(f"[PASS] System info: {info['hostname']}, {info['cpu']['cores']} cores, {info['memory']['total_mb']}MB RAM")


def test_list_processes():
    procs = list_processes(5)
    assert isinstance(procs, list)
    print(f"[PASS] Found {len(procs)} processes")


def test_self_test():
    result = test()
    assert result is True
    print("[PASS] Self-test passed")


if __name__ == "__main__":
    test_get_system_info()
    test_list_processes()
    test_self_test()
    print("\nAll system_info tests passed!")
