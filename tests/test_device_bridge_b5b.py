import time
import pytest
from ccos.core.device_bridge import (
    ACTION_EXECUTE_TASK,
    ACTION_INSPECT_UI,
    ACTION_MAKE_CALL,
    ACTION_SEND_SMS,
    ACTION_THIRD_PARTY_MESSAGE,
    DeviceBridgeClient,
    DeviceBridgeServer,
    SafetyVetoError,
    get_default_device_bridge_server,
    record_device_interaction_to_core,
    validate_telephony_safety,
)
from ccos.plugins.device.bridge.bridge import (
    third_party_message_capability,
    execute_task_capability,
    send_sms_capability,
    make_call_capability,
    inspect_ui_capability,
)


def _register_fake_connected_handlers(server: DeviceBridgeServer) -> None:
    """WP0.3 (NEW-767): production registers no handlers by default --
    these tests exist to exercise dispatch/safety-veto/write-through
    plumbing, which still needs *some* handler behind it. Simulates "a
    real device is connected" the same way a real limb integration
    would, via register_handler()."""
    server.register_handler(ACTION_INSPECT_UI, lambda p: {
        "ui_hierarchy": {"root": {"class": "FrameLayout", "children": []}},
        "focused_app": p.get("package_name", "com.android.launcher"),
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
    server.register_handler(ACTION_THIRD_PARTY_MESSAGE, lambda p: {
        "sent": True,
        "app": p.get("app", "whatsapp"),
        "recipient": p.get("recipient"),
        "message_id": f"msg_{p.get('app', 'app')}_{int(time.time())}",
    })
    server.register_handler(ACTION_EXECUTE_TASK, lambda p: {
        "success": True,
        "goal": p.get("goal"),
        "steps_executed": p.get("steps_executed", 1),
        "final_status": "completed",
    })
from restoricon_core.database import DatabaseManager
from restoricon_core.auth import AuthService, ROLE_ADMIN
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.models import Customer


@pytest.fixture
def test_db():
    db = DatabaseManager(":memory:")
    return db


@pytest.fixture
def core_services(test_db):
    audit = AuditService(test_db)
    auth = AuthService(test_db)
    crm = CRMService(test_db, audit)
    comm = CommunicationService(test_db)
    admin_u = auth.create_user("admin_test", "AdminPass123!", "Admin User", "admin@test.com", ROLE_ADMIN)
    token = auth.create_token(admin_u)
    admin_ctx = auth.authenticate_token(token)
    cust = crm.create_customer(Customer(first_name="Alice", last_name="Smith", phone="+15551234567"), admin_ctx)
    return {
        "db": test_db,
        "audit": audit,
        "auth": auth,
        "crm": crm,
        "comm": comm,
        "admin_ctx": admin_ctx,
        "cust": cust,
    }


def test_safety_veto_telephony_emergency():
    # Emergency numbers must be rejected
    is_safe, reason = validate_telephony_safety("911")
    assert not is_safe
    assert "Emergency number" in reason

    is_safe, reason = validate_telephony_safety("+1-911")
    assert not is_safe

    is_safe, reason = validate_telephony_safety("112")
    assert not is_safe

    is_safe, reason = validate_telephony_safety("999")
    assert not is_safe

    # Valid phone numbers must pass
    is_safe, reason = validate_telephony_safety("+1 (555) 234-5678")
    assert is_safe
    assert reason is None


def test_device_bridge_server_envelope_dispatch():
    server = DeviceBridgeServer()
    _register_fake_connected_handlers(server)

    # 1. Inspect UI
    resp = server.handle_envelope({"action_type": ACTION_INSPECT_UI, "payload": {}})
    assert resp["status"] == "success"
    assert "ui_hierarchy" in resp["data"]

    # 2. Third Party Message
    resp = server.handle_envelope({
        "action_type": ACTION_THIRD_PARTY_MESSAGE,
        "payload": {
            "app": "whatsapp",
            "recipient": "+15559876543",
            "message": "Hello from Codey-OS!",
        },
    })
    assert resp["status"] == "success"
    assert resp["data"]["sent"] is True
    assert resp["data"]["app"] == "whatsapp"

    # 3. Third Party Message with Emergency Number Veto
    resp = server.handle_envelope({
        "action_type": ACTION_THIRD_PARTY_MESSAGE,
        "payload": {
            "app": "whatsapp",
            "recipient": "911",
            "message": "Emergency test",
        },
    })
    assert resp["status"] == "blocked"
    assert "Emergency number" in resp["error"]

    # 4. Execute Task
    resp = server.handle_envelope({
        "action_type": ACTION_EXECUTE_TASK,
        "payload": {"goal": "Search contact and open chat"},
    })
    assert resp["status"] == "success"
    assert resp["data"]["final_status"] == "completed"


def test_device_bridge_client_methods():
    server = DeviceBridgeServer()
    _register_fake_connected_handlers(server)
    client = DeviceBridgeClient(server_instance=server)

    # UI inspection
    ui = client.inspect_ui("com.whatsapp")
    assert ui["focused_app"] == "com.whatsapp"

    # SMS dispatch
    sms_res = client.send_sms("+15553334444", "Inspection scheduled for tomorrow 9 AM")
    assert sms_res["sent"] is True

    # Third-party WhatsApp dispatch
    wa_res = client.send_third_party_message(
        app="whatsapp",
        recipient="+15553334444",
        message="Your restoration estimate is ready for review",
    )
    assert wa_res["sent"] is True
    assert wa_res["app"] == "whatsapp"

    # Safety Veto Exception on Client
    with pytest.raises(SafetyVetoError):
        client.send_sms("911", "Testing emergency veto")

    with pytest.raises(SafetyVetoError):
        client.send_third_party_message(app="whatsapp", recipient="911", message="Testing emergency veto")


def test_device_bridge_write_through_to_restoricon_core(core_services):
    comm = core_services["comm"]
    admin_ctx = core_services["admin_ctx"]
    cust = core_services["cust"]

    # Record WhatsApp message through device bridge helper
    entry = record_device_interaction_to_core(
        comm_service=comm,
        actor=admin_ctx,
        customer_id=cust.id,
        channel="whatsapp",
        direction="outbound",
        body="Water extraction crew has been dispatched to your property.",
        sender="Restoricon Dispatch",
        recipient=cust.phone,
        provider_message_id=f"wa_dev_{int(time.time())}",
    )

    assert entry is not None
    assert entry.id > 0
    assert entry.channel == "social"
    assert entry.direction == "outbound"

    # Verify history retrieval
    history = comm.query_communications(actor=admin_ctx, customer_id=cust.id)
    assert len(history) == 1
    assert history[0].channel == "social"
    assert history[0].metadata.get("original_channel") == "whatsapp"
    assert "Water extraction crew" in history[0].content


def test_ccos_plugin_capabilities():
    # Plugin capabilities route through the module-level default
    # server/client singleton, not a locally-constructed one -- register
    # fake handlers there to simulate "a device is connected" for this
    # test. Restored to empty afterward (code-review finding): other code
    # in this process -- e.g. ccos/plugins/device/bridge/test.py's own
    # suite, which asserts the opposite, that no handler means a loud
    # DeviceBridgeError -- must not see this singleton left in a
    # "fabricated device connected" state after this test runs.
    server = get_default_device_bridge_server()
    _register_fake_connected_handlers(server)
    try:
        ui = inspect_ui_capability()
        assert "ui_hierarchy" in ui

        sms = send_sms_capability(phone_number="+15550001111", message="Test CCOS SMS")
        assert sms["sent"] is True

        call = make_call_capability(phone_number="+15550001111")
        assert call["initiated"] is True

        tp = third_party_message_capability(
            app="messenger",
            recipient="AliceSmith",
            message="Appointment confirmed",
        )
        assert tp["sent"] is True
        assert tp["app"] == "messenger"

        task = execute_task_capability(goal="Open settings and toggle dark mode")
        assert task["success"] is True
    finally:
        server._handlers.clear()
