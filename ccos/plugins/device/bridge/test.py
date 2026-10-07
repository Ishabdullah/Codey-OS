#!/usr/bin/env python3
"""Test for device_bridge plugin."""

from pathlib import Path

_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
import importlib.util
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

from ccos.core.device_bridge import DeviceBridgeError
from ccos.plugins.device.bridge.bridge import (
    inspect_ui_capability,
    perform_gesture_capability,
    send_sms_capability,
    make_call_capability,
    launch_app_capability,
    read_notifications_capability,
    test,
)


def _assert_not_connected(callable_, *args, **kwargs):
    """WP0.3 (NEW-767): this plugin's test.py runs as production --
    ccos/core/sandbox.py's run_plugin_test() invokes it directly for
    agent_orchestrator's PLUGIN_TEST step and skill_recombiner's
    generated-plugin verification. Registering fake handlers here (the
    tempting fix) would reintroduce NEW-767's exact hazard -- a
    fabricated success reaching the real orchestrator process. No real
    device is connected in this environment, so the only correct
    assertion is that every capability fails loudly."""
    try:
        callable_(*args, **kwargs)
    except DeviceBridgeError as e:
        assert "not connected" in str(e).lower(), f"unexpected DeviceBridgeError shape: {e}"
        return
    raise AssertionError(f"{callable_.__name__} succeeded with no device connected")


def test_device_bridge_capabilities():
    _assert_not_connected(inspect_ui_capability)
    _assert_not_connected(perform_gesture_capability, "tap", 100, 200)
    _assert_not_connected(send_sms_capability, "5551234567", "Hello from Codey-OS")
    _assert_not_connected(make_call_capability, "5551234567")
    _assert_not_connected(launch_app_capability, "com.android.settings")
    _assert_not_connected(read_notifications_capability, limit=5)


def test_plugin_self_test():
    assert test() is True


if __name__ == "__main__":
    test_device_bridge_capabilities()
    test_plugin_self_test()
    print("All device_bridge plugin tests passed!")
