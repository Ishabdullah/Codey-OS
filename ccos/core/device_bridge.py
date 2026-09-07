"""
Device Bridge — Loopback IPC bridge for device limbs (Private-Codey-Agent / Android Limbs).

Provides:
- Standard loopback IPC request/response envelopes
- Safety veto validation (blocking emergency numbers: 911, 112, 999, etc.)
- Action types: inspect_ui, perform_gesture, send_sms, make_call, launch_app, read_notifications
- DeviceBridgeServer & DeviceBridgeClient
"""

import json
import re
import socket
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional, Set, Tuple

# Standard Action Types
ACTION_INSPECT_UI = "inspect_ui"
ACTION_PERFORM_GESTURE = "perform_gesture"
ACTION_SEND_SMS = "send_sms"
ACTION_MAKE_CALL = "make_call"
ACTION_LAUNCH_APP = "launch_app"
ACTION_READ_NOTIFICATIONS = "read_notifications"
ACTION_THIRD_PARTY_MESSAGE = "third_party_message"
ACTION_EXECUTE_TASK = "execute_task"

ALL_ACTIONS = {
    ACTION_INSPECT_UI,
    ACTION_PERFORM_GESTURE,
    ACTION_SEND_SMS,
    ACTION_MAKE_CALL,
    ACTION_LAUNCH_APP,
    ACTION_READ_NOTIFICATIONS,
    ACTION_THIRD_PARTY_MESSAGE,
    ACTION_EXECUTE_TASK,
}

# Emergency Numbers Veto Set
EMERGENCY_NUMBERS: Set[str] = {
    "911",
    "112",
    "999",
    "000",
    "110",
    "119",
    "120",
    "122",
    "100",
    "101",
    "102",
    "08",
}


class SafetyVetoError(Exception):
    """Raised when an action violates safety constraints."""
    pass


class DeviceBridgeError(Exception):
    """Base error for device bridge failures."""
    pass


def normalize_phone_number(raw_number: str) -> str:
    """Strip spaces, dashes, parentheses, dots and non-digits (keeping + if leading)."""
    if not raw_number:
        return ""
    cleaned = re.sub(r"[^\d+]", "", str(raw_number).strip())
    # Strip leading + for standard comparison
    digits_only = re.sub(r"\D", "", cleaned)
    return digits_only


def validate_telephony_safety(phone_number: str) -> Tuple[bool, Optional[str]]:
    """
    Check if a phone number targets an emergency responder.
    Returns: (is_safe, error_reason)
    """
    if not phone_number or not str(phone_number).strip():
        return False, "Phone number cannot be empty"

    digits = normalize_phone_number(phone_number)
    if digits in EMERGENCY_NUMBERS:
        return False, f"Safety veto: Emergency number '{phone_number}' is blocked"

    # Handle +1 prefix for North America e.g. +1-911 -> digits '1911'
    if digits.startswith("1") and len(digits) == 4 and digits[1:] in EMERGENCY_NUMBERS:
        return False, f"Safety veto: Emergency number '{phone_number}' is blocked"

    # Also block 911 / 112 / 999 anywhere in short codes (<= 4 digits)
    if len(digits) <= 4:
        for em in EMERGENCY_NUMBERS:
            if em == digits or em in digits:
                return False, f"Safety veto: Emergency short code '{phone_number}' is blocked"

    return True, None


class DeviceBridgeRequest:
    """IPC Request Envelope."""

    def __init__(
        self,
        action_type: str,
        payload: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        timeout_ms: int = 5000,
        auth_token: Optional[str] = None,
    ):
        self.request_id = request_id or str(uuid.uuid4())
        self.action_type = action_type
        self.payload = payload or {}
        self.timeout_ms = timeout_ms
        self.auth_token = auth_token

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action_type": self.action_type,
            "payload": self.payload,
            "timeout_ms": self.timeout_ms,
            "auth_token": self.auth_token,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeviceBridgeRequest":
        return cls(
            action_type=data.get("action_type", ""),
            payload=data.get("payload", {}),
            request_id=data.get("request_id"),
            timeout_ms=data.get("timeout_ms", 5000),
            auth_token=data.get("auth_token"),
        )


class DeviceBridgeResponse:
    """IPC Response Envelope."""

    def __init__(
        self,
        request_id: str,
        status: str = "success",  # "success", "error", "blocked"
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ):
        self.request_id = request_id
        self.status = status
        self.data = data or {}
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "status": self.status,
            "data": self.data,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeviceBridgeResponse":
        return cls(
            request_id=data.get("request_id", ""),
            status=data.get("status", "error"),
            data=data.get("data", {}),
            error=data.get("error"),
        )


class DeviceBridgeServer:
    """
    Loopback IPC Server for Device Limb operations.
    Listens on 127.0.0.1 or handles direct dispatch with safety validation.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        auth_token: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.auth_token = auth_token
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self._running = False
        self._server_socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._register_default_handlers()

    def register_handler(
        self, action_type: str, handler: Callable[[Dict[str, Any]], Dict[str, Any]]
    ):
        """Register handler for a specific action type."""
        self._handlers[action_type] = handler

    def _register_default_handlers(self):
        """Register default mock/stub implementations for all actions."""
        self._handlers[ACTION_INSPECT_UI] = lambda p: {
            "ui_hierarchy": {"root": {"class": "FrameLayout", "children": []}},
            "screen_width": 1080,
            "screen_height": 2400,
            "focused_app": p.get("package_name", "com.android.launcher"),
        }
        self._handlers[ACTION_PERFORM_GESTURE] = lambda p: {
            "performed": True,
            "gesture": p.get("gesture", "tap"),
            "coordinates": (p.get("x", 0), p.get("y", 0)),
        }
        self._handlers[ACTION_SEND_SMS] = lambda p: {
            "sent": True,
            "recipient": p.get("phone_number"),
            "message_id": f"sms_{int(time.time())}",
        }
        self._handlers[ACTION_MAKE_CALL] = lambda p: {
            "initiated": True,
            "recipient": p.get("phone_number"),
            "call_id": f"call_{int(time.time())}",
        }
        self._handlers[ACTION_LAUNCH_APP] = lambda p: {
            "launched": True,
            "package_name": p.get("package_name"),
            "activity": p.get("activity"),
        }
        self._handlers[ACTION_READ_NOTIFICATIONS] = lambda p: {
            "notifications": [
                {
                    "id": 1,
                    "package": "com.android.mms",
                    "title": "System Update",
                    "text": "All services nominal",
                    "timestamp": time.time(),
                }
            ][: p.get("limit", 10)]
        }
        self._handlers[ACTION_THIRD_PARTY_MESSAGE] = lambda p: {
            "sent": True,
            "app": p.get("app", "whatsapp"),
            "recipient": p.get("recipient"),
            "message_id": f"msg_{p.get('app', 'app')}_{int(time.time())}",
        }
        self._handlers[ACTION_EXECUTE_TASK] = lambda p: {
            "success": True,
            "goal": p.get("goal"),
            "steps_executed": p.get("steps_executed", 1),
            "final_status": "completed",
        }

    def handle_envelope(self, req_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Validate safety, authenticate, and dispatch a request envelope."""
        try:
            req = DeviceBridgeRequest.from_dict(req_dict)
        except Exception as e:
            return DeviceBridgeResponse(
                request_id=req_dict.get("request_id", ""),
                status="error",
                error=f"Invalid request format: {e}",
            ).to_dict()

        # Check Auth
        if self.auth_token is not None and req.auth_token != self.auth_token:
            return DeviceBridgeResponse(
                request_id=req.request_id,
                status="error",
                error="Unauthorized: Invalid auth_token",
            ).to_dict()

        # Check Safety Vetoes for telephony and third-party messaging
        if req.action_type in (ACTION_SEND_SMS, ACTION_MAKE_CALL):
            phone = req.payload.get("phone_number", "")
            is_safe, reason = validate_telephony_safety(phone)
            if not is_safe:
                return DeviceBridgeResponse(
                    request_id=req.request_id,
                    status="blocked",
                    error=reason,
                ).to_dict()

        if req.action_type == ACTION_THIRD_PARTY_MESSAGE:
            recipient = str(req.payload.get("recipient", "") or req.payload.get("phone_number", "")).strip()
            # If recipient looks like a phone number, validate against emergency numbers
            if any(char.isdigit() for char in recipient):
                digits = normalize_phone_number(recipient)
                if digits in EMERGENCY_NUMBERS or (len(digits) <= 4 and any(em == digits for em in EMERGENCY_NUMBERS)):
                    return DeviceBridgeResponse(
                        request_id=req.request_id,
                        status="blocked",
                        error=f"Safety veto: Emergency number '{recipient}' is blocked for third-party messaging",
                    ).to_dict()

        handler = self._handlers.get(req.action_type)
        if not handler:
            return DeviceBridgeResponse(
                request_id=req.request_id,
                status="error",
                error=f"Unsupported action type: '{req.action_type}'",
            ).to_dict()

        try:
            result_data = handler(req.payload)
            return DeviceBridgeResponse(
                request_id=req.request_id,
                status="success",
                data=result_data,
            ).to_dict()
        except Exception as e:
            return DeviceBridgeResponse(
                request_id=req.request_id,
                status="error",
                error=str(e),
            ).to_dict()

    def start(self):
        """Start listening on the loopback socket."""
        if self._running:
            return
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)
        self.port = self._server_socket.getsockname()[1]
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def _listen_loop(self):
        while self._running:
            try:
                self._server_socket.settimeout(0.5)
                client_sock, _ = self._server_socket.accept()
            except (socket.timeout, OSError):
                continue

            client_thread = threading.Thread(
                target=self._handle_client, args=(client_sock,), daemon=True
            )
            client_thread.start()

    def _handle_client(self, client_sock: socket.socket):
        try:
            client_sock.settimeout(10.0)
            data_buf = b""
            while True:
                chunk = client_sock.recv(4096)
                if not chunk:
                    break
                data_buf += chunk
                if b"\n" in data_buf:
                    line, _, _ = data_buf.partition(b"\n")
                    req_dict = json.loads(line.decode("utf-8"))
                    resp_dict = self.handle_envelope(req_dict)
                    resp_bytes = json.dumps(resp_dict).encode("utf-8") + b"\n"
                    client_sock.sendall(resp_bytes)
                    break
        except Exception:
            pass
        finally:
            client_sock.close()

    def stop(self):
        """Stop the loopback server."""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)


class DeviceBridgeClient:
    """
    Client for interacting with DeviceBridgeServer via loopback TCP or direct binding.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: Optional[int] = None,
        auth_token: Optional[str] = None,
        server_instance: Optional[DeviceBridgeServer] = None,
    ):
        self.host = host
        self.port = port
        self.auth_token = auth_token
        self.server_instance = server_instance

    def send_request(
        self, action_type: str, payload: Optional[Dict[str, Any]] = None, timeout_ms: int = 5000
    ) -> Dict[str, Any]:
        """Send a request envelope and return the resulting data dictionary or raise error."""
        req = DeviceBridgeRequest(
            action_type=action_type,
            payload=payload or {},
            timeout_ms=timeout_ms,
            auth_token=self.auth_token,
        )
        req_dict = req.to_dict()

        # Direct in-process server fallback if port is not set or server_instance is given
        if self.server_instance is not None or self.port is None:
            server = self.server_instance or get_default_device_bridge_server()
            resp_dict = server.handle_envelope(req_dict)
        else:
            # Send via TCP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout_ms / 1000.0)
            try:
                sock.connect((self.host, self.port))
                req_bytes = json.dumps(req_dict).encode("utf-8") + b"\n"
                sock.sendall(req_bytes)

                resp_buf = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    resp_buf += chunk
                    if b"\n" in resp_buf:
                        break

                if not resp_buf:
                    raise DeviceBridgeError("Empty response from DeviceBridgeServer")

                resp_dict = json.loads(resp_buf.decode("utf-8").strip())
            except socket.timeout:
                raise TimeoutError(f"DeviceBridge request timed out after {timeout_ms}ms")
            except Exception as e:
                raise DeviceBridgeError(f"DeviceBridge socket error: {e}")
            finally:
                sock.close()

        resp = DeviceBridgeResponse.from_dict(resp_dict)
        if resp.status == "blocked":
            raise SafetyVetoError(resp.error or "Action blocked by safety policy")
        if resp.status == "error":
            raise DeviceBridgeError(resp.error or "DeviceBridge action failed")

        return resp.data

    def inspect_ui(self, package_name: Optional[str] = None) -> Dict[str, Any]:
        """Inspect current device UI hierarchy."""
        payload = {}
        if package_name:
            payload["package_name"] = package_name
        return self.send_request(ACTION_INSPECT_UI, payload)

    def perform_gesture(
        self, gesture: str = "tap", x: int = 0, y: int = 0, **kwargs
    ) -> Dict[str, Any]:
        """Perform touch gesture (tap, swipe, long_press, etc.)."""
        payload = {"gesture": gesture, "x": x, "y": y, **kwargs}
        return self.send_request(ACTION_PERFORM_GESTURE, payload)

    def send_sms(self, phone_number: str, message: str) -> Dict[str, Any]:
        """Send SMS message to a phone number (with emergency number protection)."""
        payload = {"phone_number": phone_number, "message": message}
        return self.send_request(ACTION_SEND_SMS, payload)

    def make_call(self, phone_number: str) -> Dict[str, Any]:
        """Initiate phone call (with emergency number protection)."""
        payload = {"phone_number": phone_number}
        return self.send_request(ACTION_MAKE_CALL, payload)

    def launch_app(self, package_name: str, activity: Optional[str] = None) -> Dict[str, Any]:
        """Launch an Android application package."""
        payload = {"package_name": package_name}
        if activity:
            payload["activity"] = activity
        return self.send_request(ACTION_LAUNCH_APP, payload)

    def read_notifications(self, limit: int = 10) -> Dict[str, Any]:
        """Read recent device notifications."""
        payload = {"limit": limit}
        return self.send_request(ACTION_READ_NOTIFICATIONS, payload)

    def send_third_party_message(
        self,
        app: str,
        recipient: str,
        message: str,
        customer_id: Optional[int] = None,
        project_id: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Send message via third party app (WhatsApp, Messenger, Instagram, etc.)."""
        payload = {
            "app": app.lower(),
            "recipient": recipient,
            "message": message,
            "customer_id": customer_id,
            "project_id": project_id,
            **kwargs,
        }
        return self.send_request(ACTION_THIRD_PARTY_MESSAGE, payload)

    def execute_task(
        self,
        goal: str,
        max_steps: int = 15,
        context: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Dispatch a multi-step accessibility screen automation task on device."""
        payload = {
            "goal": goal,
            "max_steps": max_steps,
            "context": context or {},
            **kwargs,
        }
        return self.send_request(ACTION_EXECUTE_TASK, payload)


def record_device_interaction_to_core(
    comm_service: Any,
    actor: Any,
    customer_id: int,
    channel: str,
    direction: str,
    body: str,
    subject: Optional[str] = None,
    sender: Optional[str] = None,
    recipient: Optional[str] = None,
    provider_message_id: Optional[str] = None,
    project_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Any:
    """Helper to record device limb interactions into Restoricon Core communication history."""
    if comm_service is None:
        return None

    # Map app channels into valid Core channels if needed
    mapped_channel = channel
    if mapped_channel not in ("phone", "email", "sms", "voicemail", "web_chat", "social", "internal_note", "ai_conversation", "appointment"):
        mapped_channel = "social"

    meta = metadata or {}
    if sender:
        meta["sender"] = sender
    if recipient:
        meta["recipient"] = recipient
    if channel != mapped_channel:
        meta["original_channel"] = channel

    return comm_service.record_communication(
        channel=mapped_channel,
        direction=direction,
        content=body,
        actor=actor,
        subject=subject,
        customer_id=customer_id,
        project_id=project_id,
        metadata=meta,
        provider_message_id=provider_message_id,
    )


# Global Default Server Instance
_default_server: Optional[DeviceBridgeServer] = None


def get_default_device_bridge_server() -> DeviceBridgeServer:
    global _default_server
    if _default_server is None:
        _default_server = DeviceBridgeServer()
    return _default_server


def get_default_device_bridge_client() -> DeviceBridgeClient:
    return DeviceBridgeClient(server_instance=get_default_device_bridge_server())
