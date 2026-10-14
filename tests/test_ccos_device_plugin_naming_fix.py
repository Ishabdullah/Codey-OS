"""Refusal-proof tests for the WP2.1 group 6 manifest-naming fix
(device_bridge, termux_api, termux_api_extended -- the NEW-750 bug class).

Before the fix, each plugin's capabilities were dispatch-unreachable via a
bare, unaudited RuntimeError ("No loaded plugin implements ...") because
the `implementation` string's module prefix didn't match the manifest's
own "name" (what PluginManager._discover() keys self._modules by). After
the fix, dispatch correctly REACHES the authority gate:
  - device_bridge is HIGH_IMPACT via its device:write/device:telephony
    manifest permissions (_MANIFEST_RAISE_TAGS) -> CapabilityRefused,
    confirm_available=False unconditionally for CCOS dispatch.
  - termux_api / termux_api_extended declare no `permissions` at all, so
    _authority_for() returns None and the fail-closed "unclassified"
    refusal fires immediately -- CapabilityRefused("... fail-closed
    default ..."), never even reaching the (now-fixed) module lookup.

All three remain dormant either way -- this fix only changes HOW they are
unreachable, from a naming bug to a proper, audited gate refusal. None of
the real backing device/subprocess functions is ever invoked; each is
mocked and asserted not-called.
"""
from unittest import mock

import pytest

from ccos.core.capability_registry import CapabilityRegistry
from ccos.core.plugin_manager import CapabilityRefused, PluginManager
from core.action_gateway import ActionGateway, HIGH_IMPACT


@pytest.fixture
def pm_and_gateway(tmp_path, monkeypatch):
    """Real discovery (default plugin_dirs), fresh registry + audit file,
    same monkeypatch-the-getter pattern as
    tests/test_ccos_capability_authority_gating.py's fixture."""
    import ccos.core.plugin_manager as plugin_manager_module

    audit = tmp_path / "audit.jsonl"
    gateway = ActionGateway(audit_file=audit)
    monkeypatch.setattr(plugin_manager_module, "get_action_gateway", lambda: gateway)

    registry = CapabilityRegistry(store_path=str(tmp_path / "caps.json"))
    pm = PluginManager(registry=registry)
    return pm, gateway, audit


def test_device_bridge_send_sms_now_refuses_at_authority_gate_not_runtimeerror(pm_and_gateway):
    pm, gateway, audit = pm_and_gateway
    assert pm.load("device_bridge") is True

    with mock.patch(
        "ccos.core.device_bridge.DeviceBridgeClient.send_request"
    ) as send_request, mock.patch("subprocess.run") as run_mock, mock.patch(
        "subprocess.Popen"
    ) as popen_mock:
        with pytest.raises(CapabilityRefused) as exc_info:
            pm.call_capability("device.send_sms", phone_number="555", message="hi")

    send_request.assert_not_called()
    run_mock.assert_not_called()
    popen_mock.assert_not_called()

    pm.unload("device_bridge")


def test_termux_api_camera_photo_now_refuses_with_capabilityrefused_not_runtimeerror(pm_and_gateway):
    pm, gateway, audit = pm_and_gateway
    assert pm.load("termux_api") is True

    with mock.patch(
        "ccos.plugins.device.termux_api.termux_api.TermuxAPI.execute"
    ) as execute_mock, mock.patch("subprocess.run") as run_mock, mock.patch(
        "subprocess.Popen"
    ) as popen_mock:
        with pytest.raises(CapabilityRefused, match="fail-closed default"):
            pm.call_capability("device.camera_photo")

    execute_mock.assert_not_called()
    run_mock.assert_not_called()
    popen_mock.assert_not_called()

    pm.unload("termux_api")


def test_termux_api_extended_infrared_frequencies_now_refuses_with_capabilityrefused(pm_and_gateway):
    pm, gateway, audit = pm_and_gateway
    assert pm.load("termux_api_extended") is True

    with mock.patch(
        "ccos.plugins.device.termux_api.extended_api._run"
    ) as run_fn_mock, mock.patch("subprocess.run") as run_mock, mock.patch(
        "subprocess.Popen"
    ) as popen_mock:
        with pytest.raises(CapabilityRefused, match="fail-closed default"):
            pm.call_capability("hardware.ir_frequencies")

    run_fn_mock.assert_not_called()
    run_mock.assert_not_called()
    popen_mock.assert_not_called()

    pm.unload("termux_api_extended")


def test_termux_api_module_lookup_fix_is_reached_when_forced_past_unclassified_gate(
    pm_and_gateway, monkeypatch
):
    """termux_api/termux_api_extended declare no `permissions`, so the
    plain refusal-proof tests above are satisfied by the pre-existing
    fail-closed "unclassified" gate -- they never actually exercise the
    fixed self._modules lookup. Force a HIGH_IMPACT classification here
    (test-only CAPABILITY_AUTHORITY override, not a real table change) so
    dispatch proceeds past that gate into the module lookup this round's
    manifest fix actually touches, and assert it STILL ends in
    CapabilityRefused (not the old naming-bug RuntimeError), confirming
    the fix is real and not just coincidentally masked by the earlier
    gate."""
    import ccos.core.plugin_manager as plugin_manager_module

    pm, gateway, audit = pm_and_gateway
    assert pm.load("termux_api") is True
    monkeypatch.setitem(plugin_manager_module.CAPABILITY_AUTHORITY, "device.camera_photo", HIGH_IMPACT)

    with mock.patch(
        "ccos.plugins.device.termux_api.termux_api.TermuxAPI.execute"
    ) as execute_mock, mock.patch("subprocess.run") as run_mock, mock.patch(
        "subprocess.Popen"
    ) as popen_mock:
        with pytest.raises(CapabilityRefused) as exc_info:
            pm.call_capability("device.camera_photo")

    assert "fail-closed default" not in str(exc_info.value)
    execute_mock.assert_not_called()
    run_mock.assert_not_called()
    popen_mock.assert_not_called()

    pm.unload("termux_api")


def test_camera_capture_now_refuses_with_capabilityrefused_not_runtimeerror(pm_and_gateway):
    """4th instance of the identical NEW-750 bug class, found by the
    class-closing invariant test (tests/test_ccos_plugin_manifest_naming_invariant.py)
    and fixed in the same round per rule 8 ("fix related findings
    immediately"): ccos/plugins/vision/camera_capture/manifest.json's
    name is "camera_capture" but its capabilities' implementation prefix
    was "camera:...", never matching self._modules's key. No `permissions`
    field is declared, so (same shape as termux_api/termux_api_extended)
    this is refused at the earlier "unclassified" fail-closed gate
    regardless of the naming fix -- confirming this plugin remains
    dormant, same as the other three, just unreachable via a proper
    audited refusal now instead of a bare RuntimeError.
    """
    pm, gateway, audit = pm_and_gateway
    assert pm.load("camera_capture") is True

    module = pm._modules["camera_capture"]
    with mock.patch.object(module, "capture_image") as capture_mock:
        with pytest.raises(CapabilityRefused, match="fail-closed default"):
            pm.call_capability("vision.camera_capture")

    capture_mock.assert_not_called()

    pm.unload("camera_capture")


def test_device_bridge_reaches_gate_via_manifest_permissions_raise_tag(pm_and_gateway):
    """Confirms _authority_for's claimed path for device_bridge: no core
    CAPABILITY_AUTHORITY entry for device.send_sms, classified purely by
    the device:write/device:telephony manifest permissions raise tags."""
    import ccos.core.plugin_manager as plugin_manager_module

    pm, gateway, audit = pm_and_gateway
    assert pm.load("device_bridge") is True
    assert "device.send_sms" not in plugin_manager_module.CAPABILITY_AUTHORITY

    cap = pm._registry.get("device.send_sms")
    assert pm._authority_for("device.send_sms", cap) == HIGH_IMPACT

    pm.unload("device_bridge")
