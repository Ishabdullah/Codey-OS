"""Unit tests for the Termux API adapter.

These tests do not require Android or Termux:API; execution is mocked at the
subprocess boundary.
"""

from unittest.mock import patch

from ccos.plugins.device.termux_api.termux_api import TermuxAPI, TOOL_DEFINITIONS


def test_registry_is_nonempty_and_has_core_capabilities():
    assert len(TOOL_DEFINITIONS) >= 30
    for name in ("device.battery", "device.clipboard_get", "device.tts_speak", "device.sms_send"):
        assert name in TOOL_DEFINITIONS


def test_dangerous_tools_require_permission():
    api = TermuxAPI(allow_dangerous=False)
    try:
        api.execute("device.sms_send", number="5551234", message="hello")
    except Exception as exc:
        assert "explicit permission" in str(exc)
    else:
        raise AssertionError("dangerous capability executed without permission")


def test_command_execution_uses_argv_not_shell():
    api = TermuxAPI(allow_dangerous=True)
    fake = type("Proc", (), {"returncode": 0, "stdout": '{"percentage": 80}', "stderr": ""})()
    with patch("ccos.plugins.device.termux_api.termux_api.shutil.which", return_value="/data/data/com.termux/files/usr/bin/termux-battery-status"), patch("ccos.plugins.device.termux_api.termux_api.subprocess.run", return_value=fake) as run:
        result = api.execute("device.battery")
        assert result["result"]["percentage"] == 80
        kwargs = run.call_args.kwargs
        assert kwargs["shell"] is False
        assert run.call_args.args[0] == ["termux-battery-status"]


def test_tool_definitions_are_agent_discoverable():
    api = TermuxAPI()
    tools = api.list_tools(include_dangerous=False)
    assert tools
    assert all("name" in t and "description" in t and "parameters" in t for t in tools)
