"""
Device Bridge Plugin Implementation.
Exposes CCOS capability wrapper functions mapped to DeviceBridgeClient.
"""

from typing import Any, Dict, List, Optional
from ccos.core.device_bridge import (
    DeviceBridgeClient,
    get_default_device_bridge_client,
)

_client: Optional[DeviceBridgeClient] = None


def _get_client() -> DeviceBridgeClient:
    global _client
    if _client is None:
        _client = get_default_device_bridge_client()
    return _client


def inspect_ui_capability(package_name: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    """Inspect the device UI hierarchy and active package."""
    return _get_client().inspect_ui(package_name=package_name)


def perform_gesture_capability(gesture: str = "tap", x: int = 0, y: int = 0, **kwargs) -> Dict[str, Any]:
    """Perform touch gestures on the screen."""
    return _get_client().perform_gesture(gesture=gesture, x=x, y=y, **kwargs)


def send_sms_capability(phone_number: str, message: str, **kwargs) -> Dict[str, Any]:
    """Send SMS to phone number with safety veto enforcement."""
    return _get_client().send_sms(phone_number=phone_number, message=message)


def make_call_capability(phone_number: str, **kwargs) -> Dict[str, Any]:
    """Initiate voice call to phone number with safety veto enforcement."""
    return _get_client().make_call(phone_number=phone_number)


def launch_app_capability(package_name: str, activity: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    """Launch an Android application."""
    return _get_client().launch_app(package_name=package_name, activity=activity)


def read_notifications_capability(limit: int = 10, **kwargs) -> Dict[str, Any]:
    """Read recent notifications from device."""
    return _get_client().read_notifications(limit=limit)


def third_party_message_capability(
    app: str, recipient: str, message: str, customer_id: Optional[int] = None, project_id: Optional[int] = None, **kwargs
) -> Dict[str, Any]:
    """Send message via third party app (WhatsApp, Messenger, etc.) with safety validation."""
    return _get_client().send_third_party_message(
        app=app, recipient=recipient, message=message, customer_id=customer_id, project_id=project_id, **kwargs
    )


def execute_task_capability(goal: str, max_steps: int = 15, context: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    """Execute multi-step screen automation task via Android accessibility."""
    return _get_client().execute_task(goal=goal, max_steps=max_steps, context=context, **kwargs)


def install() -> bool:
    """Plugin install lifecycle hook."""
    return True


def uninstall() -> bool:
    """Plugin uninstall lifecycle hook."""
    return True


def test() -> bool:
    """Plugin self-test verifying UI inspection and safe dispatch."""
    client = _get_client()
    ui = client.inspect_ui()
    assert isinstance(ui, dict), "UI response must be dict"
    assert "ui_hierarchy" in ui, "UI response must include ui_hierarchy"
    return True
