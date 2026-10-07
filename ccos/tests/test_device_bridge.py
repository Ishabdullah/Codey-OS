#!/usr/bin/env python3
"""
Unit tests for Device Bridge IPC envelopes, action dispatch, safety vetoes, and socket comms.
"""

import time

import pytest

from ccos.core.device_bridge import (
    ACTION_INSPECT_UI,
    ACTION_MAKE_CALL,
    ACTION_LAUNCH_APP,
    ACTION_PERFORM_GESTURE,
    ACTION_READ_NOTIFICATIONS,
    ACTION_SEND_SMS,
    DeviceBridgeRequest,
    DeviceBridgeResponse,
    DeviceBridgeServer,
    DeviceBridgeClient,
    DeviceBridgeError,
    SafetyVetoError,
    validate_telephony_safety,
    normalize_phone_number,
)


def _register_fake_connected_handlers(server: DeviceBridgeServer) -> None:
    """WP0.3 (NEW-767): production no longer registers mock handlers by
    default -- an unconnected bridge must fail loudly. These tests exist
    to exercise dispatch/auth/safety-veto/socket plumbing, which still
    needs *some* handler behind it, so each test that wants a successful
    dispatch explicitly simulates "a real device is connected" via
    register_handler(), the same mechanism a real limb integration would
    use. This is a test fixture, not a production default."""
    server.register_handler(ACTION_INSPECT_UI, lambda p: {
        "ui_hierarchy": {"root": {"class": "FrameLayout", "children": []}},
        "screen_width": 1080,
        "screen_height": 2400,
        "focused_app": p.get("package_name", "com.android.launcher"),
    })
    server.register_handler(ACTION_PERFORM_GESTURE, lambda p: {
        "performed": True,
        "gesture": p.get("gesture", "tap"),
        "coordinates": (p.get("x", 0), p.get("y", 0)),
    })
    server.register_handler(ACTION_SEND_SMS, lambda p: {
        "sent": True,
        "recipient": p.get("phone_number"),
        "message_id": f"sms_{int(time.time())}",
    })
    server.register_handler(ACTION_MAKE_CALL, lambda p: {
        "initiated": True,
        "recipient": p.get("phone_number"),
        "call_id": f"call_{int(time.time())}",
    })
    server.register_handler(ACTION_LAUNCH_APP, lambda p: {
        "launched": True,
        "package_name": p.get("package_name"),
        "activity": p.get("activity"),
    })
    server.register_handler(ACTION_READ_NOTIFICATIONS, lambda p: {
        "notifications": [
            {
                "id": 1,
                "package": "com.android.mms",
                "title": "System Update",
                "text": "All services nominal",
                "timestamp": time.time(),
            }
        ][: p.get("limit", 10)]
    })


def test_phone_normalization():
    assert normalize_phone_number("911") == "911"
    assert normalize_phone_number("+1 (555) 123-4567") == "15551234567"
    assert normalize_phone_number("112") == "112"
    assert normalize_phone_number("  999 ") == "999"


def test_safety_veto_telephony():
    # Emergency numbers must fail safety check
    for num in ("911", "112", "999", "000", "110", "119", "120", "122", "100", "101", "102"):
        is_safe, reason = validate_telephony_safety(num)
        assert is_safe is False
        assert "Safety veto" in reason

    # Empty number fails
    is_safe, reason = validate_telephony_safety("")
    assert is_safe is False

    # Normal phone numbers pass safety check
    is_safe, reason = validate_telephony_safety("+1 (555) 234-5678")
    assert is_safe is True
    assert reason is None


def test_request_response_envelopes():
    req = DeviceBridgeRequest(
        action_type=ACTION_INSPECT_UI,
        payload={"package_name": "com.android.settings"},
        timeout_ms=3000,
        auth_token="secret123",
    )
    d = req.to_dict()
    assert d["action_type"] == ACTION_INSPECT_UI
    assert d["payload"]["package_name"] == "com.android.settings"
    assert d["timeout_ms"] == 3000
    assert d["auth_token"] == "secret123"

    req2 = DeviceBridgeRequest.from_dict(d)
    assert req2.request_id == req.request_id
    assert req2.action_type == req.action_type
    assert req2.auth_token == "secret123"

    resp = DeviceBridgeResponse(
        request_id=req.request_id,
        status="success",
        data={"screen_width": 1080},
    )
    rd = resp.to_dict()
    assert rd["status"] == "success"
    assert rd["data"]["screen_width"] == 1080

    resp2 = DeviceBridgeResponse.from_dict(rd)
    assert resp2.request_id == req.request_id
    assert resp2.status == "success"


def test_unconnected_bridge_fails_loudly_not_fabricated():
    """WP0.3 (NEW-767): the whole point of this fix. No handler
    registered -- a real response must never be fabricated."""
    server = DeviceBridgeServer()
    client = DeviceBridgeClient(server_instance=server)

    with pytest.raises(DeviceBridgeError) as exc_info:
        client.inspect_ui()
    assert "not connected" in str(exc_info.value).lower()

    with pytest.raises(DeviceBridgeError) as exc_info:
        client.send_sms("+1-555-0100", "test")
    assert "not connected" in str(exc_info.value).lower()


def test_genuinely_unknown_action_is_unsupported_not_not_connected():
    """The two error branches emitted an identical string before this
    fix (both said "Unsupported action type") -- this proves the new
    split actually discriminates: an action outside ALL_ACTIONS is a
    different failure (client error) from a known action with no real
    handler behind it (not connected)."""
    server = DeviceBridgeServer()
    client = DeviceBridgeClient(server_instance=server)

    with pytest.raises(DeviceBridgeError) as exc_info:
        client.send_request("not_a_real_action_type")
    assert "unsupported" in str(exc_info.value).lower()
    assert "not connected" not in str(exc_info.value).lower()


def test_server_dispatch_all_actions():
    server = DeviceBridgeServer()
    _register_fake_connected_handlers(server)
    client = DeviceBridgeClient(server_instance=server)

    # 1. inspect_ui
    ui = client.inspect_ui("com.example.app")
    assert "ui_hierarchy" in ui
    assert ui["focused_app"] == "com.example.app"

    # 2. perform_gesture
    gesture = client.perform_gesture("tap", x=150, y=300)
    assert gesture["performed"] is True
    assert gesture["gesture"] == "tap"

    # 3. send_sms (safe number)
    sms = client.send_sms("+1-555-0100", "Testing message")
    assert sms["sent"] is True

    # 4. make_call (safe number)
    call = client.make_call("+1-555-0100")
    assert call["initiated"] is True

    # 5. launch_app
    app = client.launch_app("com.android.vending")
    assert app["launched"] is True
    assert app["package_name"] == "com.android.vending"

    # 6. read_notifications
    notifs = client.read_notifications(limit=3)
    assert "notifications" in notifs
    assert len(notifs["notifications"]) <= 3


def test_safety_veto_blocks_emergency_sms_and_call():
    server = DeviceBridgeServer()
    client = DeviceBridgeClient(server_instance=server)

    # Attempt SMS to 911
    with pytest.raises(SafetyVetoError) as exc_info:
        client.send_sms("911", "Emergency text")
    assert "Safety veto" in str(exc_info.value)

    # Attempt Call to 112
    with pytest.raises(SafetyVetoError) as exc_info:
        client.make_call("112")
    assert "Safety veto" in str(exc_info.value)

    # Attempt Call to 999
    with pytest.raises(SafetyVetoError) as exc_info:
        client.make_call("999")
    assert "Safety veto" in str(exc_info.value)


def test_auth_token_verification():
    server = DeviceBridgeServer(auth_token="valid_secret_token")
    _register_fake_connected_handlers(server)
    client_bad = DeviceBridgeClient(server_instance=server, auth_token="wrong_token")
    client_good = DeviceBridgeClient(server_instance=server, auth_token="valid_secret_token")

    with pytest.raises(DeviceBridgeError) as exc_info:
        client_bad.inspect_ui()
    assert "Unauthorized" in str(exc_info.value)

    res = client_good.inspect_ui()
    assert "ui_hierarchy" in res


def test_loopback_tcp_socket_communication():
    server = DeviceBridgeServer(host="127.0.0.1", port=0)
    _register_fake_connected_handlers(server)
    server.start()
    try:
        assert server.port > 0
        client = DeviceBridgeClient(host="127.0.0.1", port=server.port)

        # Inspect UI over TCP socket
        ui = client.inspect_ui("com.example.tcp")
        assert ui["focused_app"] == "com.example.tcp"

        # Safe SMS over TCP socket
        sms = client.send_sms("5551234567", "Hello over socket")
        assert sms["sent"] is True

        # Safety veto over TCP socket
        with pytest.raises(SafetyVetoError):
            client.send_sms("911", "Should block")

    finally:
        server.stop()
