"""Device Bridge Plugin Package."""
from ccos.plugins.device.bridge.bridge import (
    inspect_ui_capability,
    perform_gesture_capability,
    send_sms_capability,
    make_call_capability,
    launch_app_capability,
    read_notifications_capability,
    install,
    uninstall,
    test,
)

__all__ = [
    "inspect_ui_capability",
    "perform_gesture_capability",
    "send_sms_capability",
    "make_call_capability",
    "launch_app_capability",
    "read_notifications_capability",
    "install",
    "uninstall",
    "test",
]
