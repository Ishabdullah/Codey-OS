#!/usr/bin/env python3
"""
Unit tests for Device Bridge IPC envelopes, action dispatch, safety vetoes, and socket comms.
"""

import pytest

from ccos.core.device_bridge import (
    ACTION_INSPECT_UI,
    DeviceBridgeRequest,
    DeviceBridgeResponse,
    DeviceBridgeServer,
    DeviceBridgeClient,
    DeviceBridgeError,
    SafetyVetoError,
    validate_telephony_safety,
    normalize_phone_number,
)


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


def test_server_dispatch_all_actions():
    server = DeviceBridgeServer()
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
    client_bad = DeviceBridgeClient(server_instance=server, auth_token="wrong_token")
    client_good = DeviceBridgeClient(server_instance=server, auth_token="valid_secret_token")

    with pytest.raises(DeviceBridgeError) as exc_info:
        client_bad.inspect_ui()
    assert "Unauthorized" in str(exc_info.value)

    res = client_good.inspect_ui()
    assert "ui_hierarchy" in res


def test_loopback_tcp_socket_communication():
    server = DeviceBridgeServer(host="127.0.0.1", port=0)
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
