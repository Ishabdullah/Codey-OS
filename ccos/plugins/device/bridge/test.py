#!/usr/bin/env python3
"""Test for device_bridge plugin."""

from pathlib import Path

_pathutil_path = Path(__file__).resolve().parent.parent.parent / "_pathutil.py"
import importlib.util
_spec = importlib.util.spec_from_file_location("_pathutil", _pathutil_path)
_pathutil = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pathutil)
_pathutil.ensure_repo_root_on_path()

from ccos.plugins.device.bridge.bridge import (
    inspect_ui_capability,
    perform_gesture_capability,
    send_sms_capability,
    make_call_capability,
    launch_app_capability,
    read_notifications_capability,
    test,
)


def test_device_bridge_capabilities():
    ui = inspect_ui_capability()
    assert "ui_hierarchy" in ui

    gesture = perform_gesture_capability("tap", 100, 200)
    assert gesture["performed"] is True

    sms = send_sms_capability("5551234567", "Hello from Codey-OS")
    assert sms["sent"] is True

    call = make_call_capability("5551234567")
    assert call["initiated"] is True

    app = launch_app_capability("com.android.settings")
    assert app["launched"] is True

    notifs = read_notifications_capability(limit=5)
    assert "notifications" in notifs


def test_plugin_self_test():
    assert test() is True


if __name__ == "__main__":
    test_device_bridge_capabilities()
    test_plugin_self_test()
    print("All device_bridge plugin tests passed!")
