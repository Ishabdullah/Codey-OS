"""Structured Termux:API tools for CCOS.

Design goals:
- Keep the LLM-facing surface structured and discoverable.
- Validate arguments before invoking Termux commands.
- Return JSON-friendly results.
- Never expose a general shell tool through this adapter.
- Allow unavailable commands to fail cleanly instead of crashing CCOS.

Requires the Termux:API Android app plus the corresponding termux-api
package inside Termux. Individual commands may additionally require Android
permissions or hardware.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence


class TermuxAPIError(RuntimeError):
    """A Termux API command could not be executed."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    command: str
    category: str
    parameters: Dict[str, Any]
    dangerous: bool = False
    permission: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "command": self.command,
            "category": self.category,
            "parameters": self.parameters,
            "dangerous": self.dangerous,
            "permission": self.permission,
        }


def _param(name: str, kind: str = "string", required: bool = False, description: str = "") -> Dict[str, Any]:
    return {"name": name, "type": kind, "required": required, "description": description}


# The registry is intentionally data-driven so the agent can inspect it and
# generate native function/tool schemas without learning Termux command names.
_TOOL_DATA = [
    # Device / system
    ("device.battery", "Get battery status and charging information", "termux-battery-status", "device", [], False, None),
    ("device.brightness", "Get or set screen brightness", "termux-brightness", "device", [_param("value", "integer", False, "Brightness 0-255; omit to query current value")], False, None),
    ("device.camera_info", "List available device cameras", "termux-camera-info", "camera", [], False, "camera"),
    ("device.camera_photo", "Capture a photo with a device camera", "termux-camera-photo", "camera", [_param("path", "string", True, "Output image path"), _param("camera_id", "integer", False, "Camera ID")], False, "camera"),
    ("device.camera_record", "Record a video from a device camera", "termux-camera-photo", "camera", [_param("path", "string", True, "Output path")], False, "camera"),
    ("device.clipboard_get", "Read the Android clipboard", "termux-clipboard-get", "clipboard", [], False, None),
    ("device.clipboard_set", "Set the Android clipboard", "termux-clipboard-set", "clipboard", [_param("text", "string", True)], False, None),
    ("device.contact_list", "List contacts from the Android contacts provider", "termux-contact-list", "contacts", [], False, "contacts"),
    ("device.dialog", "Show a native Termux dialog and return its result", "termux-dialog", "ui", [_param("type", "string", True, "Dialog type such as text, confirm, checkbox, radio, or spinner"), _param("title", "string", False), _param("hint", "string", False), _param("value", "string", False)], False, None),
    ("device.location", "Get the device's current location", "termux-location", "location", [_param("provider", "string", False, "gps, network, or passive"), _param("request", "string", False, "once or last")], False, "location"),
    ("device.microphone_record", "Record audio from the microphone", "termux-microphone-record", "audio", [_param("file", "string", True), _param("limit", "integer", False, "Maximum duration in seconds"), _param("encoder", "string", False)], False, "microphone"),
    ("device.microphone_info", "Get microphone recording status", "termux-microphone-record", "audio", [], False, "microphone"),
    ("device.notification", "Create an Android notification", "termux-notification", "notification", [_param("title", "string", True), _param("content", "string", False), _param("id", "string", False), _param("priority", "string", False), _param("sound", "boolean", False)], False, None),
    ("device.notification_remove", "Remove an Android notification", "termux-notification-remove", "notification", [_param("id", "string", True)], False, None),
    ("device.sensor_list", "List available device sensors", "termux-sensor", "sensor", [], False, "sensors"),
    ("device.sensor_read", "Read one or more device sensors", "termux-sensor", "sensor", [_param("sensor", "string", True), _param("delay", "integer", False), _param("limit", "integer", False)], False, "sensors"),
    ("device.share", "Share text or a file through Android sharing", "termux-share", "sharing", [_param("path", "string", True), _param("title", "string", False), _param("content_type", "string", False)], True, None),
    ("device.sms_list", "List SMS messages", "termux-sms-list", "sms", [_param("limit", "integer", False), _param("offset", "integer", False), _param("sender", "string", False), _param("thread_id", "string", False), _param("type", "string", False)], False, "sms"),
    ("device.sms_send", "Send an SMS message", "termux-sms-send", "sms", [_param("number", "string", True), _param("message", "string", True), _param("slot", "integer", False)], True, "sms"),
    ("device.storage_get", "Read a file using Android's storage provider", "termux-storage-get", "storage", [_param("destination", "string", False)], False, "storage"),
    ("device.storage_scan", "Scan shared storage for media/files", "termux-storage-get", "storage", [], False, "storage"),
    ("device.torch", "Turn the device flashlight on or off", "termux-torch", "device", [_param("state", "string", True, "on or off")], False, None),
    ("device.tts_speak", "Speak text using Android text-to-speech", "termux-tts-speak", "speech", [_param("text", "string", True), _param("language", "string", False), _param("rate", "number", False), _param("pitch", "number", False), _param("stream", "string", False)], False, None),
    ("device.tts_engines", "List installed text-to-speech engines", "termux-tts-engines", "speech", [], False, None),
    ("device.vibrate", "Vibrate the device", "termux-vibrate", "device", [_param("duration", "integer", False), _param("force", "boolean", False)], False, None),
    ("device.volume", "Get or set Android audio stream volume", "termux-volume", "audio", [_param("stream", "string", False), _param("volume", "integer", False)], False, None),
    ("device.wallpaper", "Get or set the device wallpaper", "termux-wallpaper", "device", [_param("file", "string", False), _param("url", "string", False), _param("lockscreen", "boolean", False)], True, None),
    ("device.wifi_connection", "Get current Wi-Fi connection information", "termux-wifi-connectioninfo", "network", [], False, "wifi"),
    ("device.wifi_scan", "Scan nearby Wi-Fi networks", "termux-wifi-scaninfo", "network", [], False, "wifi"),
    ("device.wifi_enable", "Enable or disable Wi-Fi", "termux-wifi-enable", "network", [_param("enabled", "boolean", True)], True, "wifi"),
    ("device.telephony_deviceinfo", "Get telephony/device information", "termux-telephony-deviceinfo", "telephony", [], False, "telephony"),
    ("device.telephony_cellinfo", "Get nearby/current cell information", "termux-telephony-cellinfo", "telephony", [], False, "telephony"),
    ("device.telephony_call", "Place a phone call", "termux-telephony-call", "telephony", [_param("number", "string", True)], True, "phone"),
    ("device.usb", "List USB devices", "termux-usb", "hardware", [], False, "usb"),
    ("device.job_scheduler", "Schedule a Termux job", "termux-job-scheduler", "automation", [_param("script", "string", True), _param("period_ms", "integer", False), _param("job_id", "integer", False), _param("persisted", "boolean", False)], True, None),
    # Web / networking
    ("network.download", "Download a URL to a local file", "termux-download", "network", [_param("url", "string", True), _param("output", "string", False), _param("title", "string", False)], True, None),
    ("network.websearch", "Open a web search through Android", "termux-open-url", "network", [_param("query", "string", True)], False, None),
    ("network.open_url", "Open a URL using the Android handler", "termux-open-url", "network", [_param("url", "string", True)], False, None),
    # Infrared / hardware
    ("hardware.ir_transmit", "Transmit an infrared pattern", "termux-infrared-transmit", "hardware", [_param("frequency", "integer", True), _param("pattern", "array", True)], False, "ir"),
    # Speech recognition
    ("speech.to_text", "Recognize speech from the microphone", "termux-speech-to-text", "speech", [_param("language", "string", False), _param("prefer_offline", "boolean", False)], False, "microphone"),
    # Contacts / notification extras
    ("device.notification_list", "List active notifications", "termux-notification-list", "notification", [], False, "notifications"),
]

TOOL_DEFINITIONS: Dict[str, ToolSpec] = {
    name: ToolSpec(name, description, command, category, {"type": "object", "properties": {p["name"]: p for p in params}}, dangerous, permission)
    for name, description, command, category, params, dangerous, permission in _TOOL_DATA
}


class TermuxAPI:
    """Execute only registered Termux API commands."""

    def __init__(self, timeout: int = 30, allow_dangerous: bool = False):
        self.timeout = timeout
        self.allow_dangerous = allow_dangerous

    def available(self, tool_name: str) -> bool:
        spec = TOOL_DEFINITIONS.get(tool_name)
        return bool(spec and shutil.which(spec.command))

    def list_tools(self, category: Optional[str] = None, include_dangerous: bool = True) -> List[Dict[str, Any]]:
        tools = TOOL_DEFINITIONS.values()
        if category:
            tools = [t for t in tools if t.category == category]
        if not include_dangerous:
            tools = [t for t in tools if not t.dangerous]
        return [t.as_dict() for t in tools]

    def execute(self, tool_name: str, **kwargs: Any) -> Dict[str, Any]:
        spec = TOOL_DEFINITIONS.get(tool_name)
        if not spec:
            raise TermuxAPIError(f"Unknown Termux capability: {tool_name}")
        if spec.dangerous and not self.allow_dangerous:
            raise TermuxAPIError(f"Capability requires explicit permission: {tool_name}")
        if not shutil.which(spec.command):
            raise TermuxAPIError(f"Termux API command unavailable: {spec.command}")
        args = self._build_args(spec, kwargs)
        try:
            proc = subprocess.run(
                [spec.command, *args],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TermuxAPIError(f"Timed out after {self.timeout}s: {tool_name}") from exc
        except OSError as exc:
            raise TermuxAPIError(f"Could not execute {spec.command}: {exc}") from exc

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()
        result: Any = stdout
        if stdout:
            try:
                result = json.loads(stdout)
            except json.JSONDecodeError:
                pass
        if proc.returncode != 0:
            raise TermuxAPIError(stderr or stdout or f"{spec.command} exited with {proc.returncode}")
        return {"ok": True, "tool": tool_name, "result": result, "stderr": stderr}

    def _build_args(self, spec: ToolSpec, values: Dict[str, Any]) -> List[str]:
        # Explicit command mapping keeps model-controlled values from becoming
        # shell syntax. subprocess receives argv directly; no shell is used.
        args: List[str] = []
        if spec.name == "device.brightness":
            if values.get("value") is not None: args += [str(values["value"])]
        elif spec.name == "device.camera_photo":
            if values.get("camera_id") is not None: args += ["-c", str(values["camera_id"])]
            args += [str(values["path"])]
        elif spec.name == "device.camera_record":
            args += [str(values["path"])]
        elif spec.name == "device.clipboard_set": args += [str(values["text"])]
        elif spec.name == "device.location":
            for flag, key in (("-p", "provider"), ("-r", "request")):
                if values.get(key) is not None: args += [flag, str(values[key])]
        elif spec.name == "device.microphone_record":
            args += ["-f", str(values["file"])]
            if values.get("limit") is not None: args += ["-l", str(values["limit"])]
            if values.get("encoder") is not None: args += ["-e", str(values["encoder"])]
        elif spec.name == "device.notification":
            mapping = [("-t", "title"), ("-c", "content"), ("-i", "id"), ("-p", "priority")]
            for flag, key in mapping:
                if values.get(key) is not None: args += [flag, str(values[key])]
            if values.get("sound") is True: args += ["--sound"]
        elif spec.name == "device.notification_remove": args += [str(values["id"])]
        elif spec.name == "device.sensor_read":
            args += ["-s", str(values["sensor"])]
            if values.get("delay") is not None: args += ["-d", str(values["delay"])]
            if values.get("limit") is not None: args += ["-n", str(values["limit"])]
        elif spec.name == "device.sms_list":
            for flag, key in (("-l", "limit"), ("-o", "offset"), ("-n", "sender"), ("-t", "thread_id"), ("-t", "type")):
                if values.get(key) is not None: args += [flag, str(values[key])]
        elif spec.name == "device.sms_send":
            args += ["-n", str(values["number"])]
            if values.get("slot") is not None: args += ["-s", str(values["slot"])]
            args += [str(values["message"])]
        elif spec.name == "device.share":
            args += [str(values["path"])]
            if values.get("title") is not None: args += ["-t", str(values["title"])]
            if values.get("content_type") is not None: args += ["-c", str(values["content_type"])]
        elif spec.name == "device.storage_get":
            if values.get("destination") is not None: args += [str(values["destination"])]
        elif spec.name == "device.torch": args += [str(values["state"])]
        elif spec.name == "device.tts_speak":
            for flag, key in (("-l", "language"), ("-r", "rate"), ("-p", "pitch"), ("-s", "stream")):
                if values.get(key) is not None: args += [flag, str(values[key])]
            args += [str(values["text"])]
        elif spec.name == "device.vibrate":
            if values.get("duration") is not None: args += ["-d", str(values["duration"])]
            if values.get("force") is True: args += ["-f"]
        elif spec.name == "device.volume":
            if values.get("stream") is not None: args += ["-s", str(values["stream"])]
            if values.get("volume") is not None: args += ["-v", str(values["volume"])]
        elif spec.name == "device.wallpaper":
            if values.get("file") is not None: args += ["-f", str(values["file"])]
            if values.get("url") is not None: args += ["-u", str(values["url"])]
            if values.get("lockscreen") is True: args += ["-l"]
        elif spec.name == "device.wifi_enable": args += ["true" if values["enabled"] else "false"]
        elif spec.name == "device.telephony_call": args += [str(values["number"])]
        elif spec.name == "device.job_scheduler":
            args += ["--script", str(values["script"])]
            if values.get("period_ms") is not None: args += ["--period-ms", str(values["period_ms"])]
            if values.get("job_id") is not None: args += ["--job-id", str(values["job_id"])]
            if values.get("persisted") is True: args += ["--persisted"]
        elif spec.name == "network.download":
            args += [str(values["url"])]
            if values.get("output") is not None: args += ["-o", str(values["output"])]
            if values.get("title") is not None: args += ["-t", str(values["title"])]
        elif spec.name in ("network.websearch", "network.open_url"): args += [str(values["query"] if "query" in values else values["url"])]
        elif spec.name == "speech.to_text":
            if values.get("language") is not None: args += ["-l", str(values["language"])]
            if values.get("prefer_offline") is True: args += ["--prefer-offline"]
        elif spec.name == "hardware.ir_transmit": args += ["-f", str(values["frequency"]), *[str(x) for x in values["pattern"]]]
        else:
            # Simple commands with no flags.
            pass
        return args

    def health(self) -> Dict[str, Any]:
        available = [name for name in TOOL_DEFINITIONS if self.available(name)]
        return {
            "termux_api": bool(available),
            "available_count": len(available),
            "total_tools": len(TOOL_DEFINITIONS),
            "missing": [name for name in TOOL_DEFINITIONS if name not in available],
        }


_instance: Optional[TermuxAPI] = None


def get_termux_api() -> TermuxAPI:
    global _instance
    if _instance is None:
        _instance = TermuxAPI()
    return _instance
