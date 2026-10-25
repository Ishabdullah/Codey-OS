"""Strict manifest opt-out: no imports, services, stale or direct dispatch."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ccos.core import plugin_manager as pm
from ccos.core.capability_registry import Capability, CapabilityRegistry
from ccos.core.manifest_schema_v2 import (
    MANIFEST_V2_JSON_SCHEMA, normalize_manifest, validate_manifest_v2,
)
from core.action_gateway import HIGH_IMPACT, READ

REPO = Path(__file__).resolve().parents[1]
INVALID = [0, 1, None, "false", "true", [], {}, 0.0, 1.0]
REASON = "Plugin disabled by manifest (enabled=false)"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    for key, value in {"HOME": tmp_path, "CODEY_STATE_DIR": tmp_path / "state",
                       "CODEY_ACTION_GATEWAY_AUDIT": tmp_path / "audit.jsonl",
                       "RESTORICON_DB_PATH": tmp_path / "restoricon.db"}.items():
        monkeypatch.setenv(key, str(value))
    monkeypatch.setattr(pm, "PLUGIN_PID_DIR", tmp_path / "state/plugins")
    for key in list(os.environ):
        if key.lower().endswith("_proxy"):
            monkeypatch.delenv(key)

    def forbidden(*args, **kwargs):
        raise AssertionError("Real process/network/signal effect forbidden")

    monkeypatch.setattr(pm.subprocess, "Popen", forbidden)
    monkeypatch.setattr(pm.urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(pm.os, "kill", forbidden)
    yield
    sys.modules.pop("ccos_plugin_policy_fixture", None)


def data(**fields):
    result = {"name": "policy_fixture", "version": "1.0.0", "description": "Fixture",
              "capabilities": [{"name": "policy.read", "description": "Read",
                                "implementation": "policy_fixture:read"}]}
    result.update(fields)
    return result


def write(root, manifest, directory="fixture", source="def read(): return 'fixture'\n"):
    path = root / "test" / directory
    path.mkdir(parents=True, exist_ok=True)
    (path / "manifest.json").write_text(json.dumps(manifest))
    (path / "__init__.py").write_text(source)
    return path


def manager(tmp_path, *roots, registry=None):
    return pm.PluginManager([str(r) for r in roots],
                            registry or CapabilityRegistry(str(tmp_path / "registry.json")))


def test_json_schema_contract():
    assert MANIFEST_V2_JSON_SCHEMA["properties"]["enabled"] == {"type": "boolean", "default": True}


@pytest.mark.parametrize("v2", [False, True])
@pytest.mark.parametrize("value", [False, True, *INVALID])
def test_normalize_preserves_strict_enabled(v2, value):
    manifest = data(enabled=value)
    if v2:
        manifest["schema_version"] = "2.0.0"
    normalized = normalize_manifest(manifest)
    assert normalized["enabled"] is value
    valid, errors = validate_manifest_v2(normalized)
    assert valid is (type(value) is bool)
    if type(value) is not bool:
        assert "Field 'enabled' must be a boolean" in errors


def test_default_enabled_loads_and_dispatches(tmp_path, monkeypatch):
    root = tmp_path / "plugins"
    write(root, data())
    assert normalize_manifest(data())["enabled"] is True
    obj = manager(tmp_path, root)
    monkeypatch.setitem(pm.CAPABILITY_AUTHORITY, "policy.read", READ)
    assert obj.load("policy_fixture") is True
    assert obj.call_capability("policy.read") == "fixture"
    assert obj.execute("policy_fixture", "read") == "fixture"


@pytest.mark.parametrize("mode", ["in_process", "external_process", "remote_bridge"])
@pytest.mark.parametrize("value", [False, *INVALID])
def test_disabled_and_invalid_never_activate(tmp_path, monkeypatch, mode, value):
    root = tmp_path / "plugins"
    write(root, data(enabled=value, execution_mode=mode),
          source="raise AssertionError('disabled module imported')\n")
    obj = manager(tmp_path, root)
    plugin = obj.get_plugin("policy_fixture")
    assert plugin.status == pm.PluginStatus.DISABLED
    assert "enabled" in plugin.error
    assert plugin.capabilities == ["policy.read"]
    start = Mock(side_effect=AssertionError("supervisor start"))
    health = Mock(side_effect=AssertionError("health probe"))
    imported = Mock(side_effect=AssertionError("module import"))
    monkeypatch.setattr(obj.supervisor, "start_external_plugin", start)
    monkeypatch.setattr(obj.supervisor, "check_health", health)
    monkeypatch.setattr(pm.importlib.util, "spec_from_file_location", imported)
    assert obj.load("policy_fixture") is False
    assert obj.load_all() == {"policy_fixture": False}
    assert obj._registry.get("policy.read") is None
    with pytest.raises(ValueError, match="enabled"):
        obj._stage_capabilities(plugin)
    with pytest.raises(pm.CapabilityRefused, match="enabled"):
        obj.execute("policy_fixture", "read")
    start.assert_not_called()
    health.assert_not_called()
    imported.assert_not_called()


@pytest.mark.parametrize("value", [False, *INVALID])
def test_direct_supervisor_refuses_before_liveness_env_or_pid_io(tmp_path, monkeypatch, value):
    plugin = pm.Plugin("policy_fixture", str(tmp_path), data(enabled=value))
    supervisor = pm.ProcessSupervisor()
    child = Mock()
    supervisor._processes[plugin.name] = child
    env = Mock(side_effect=AssertionError("env inspected"))
    pid = Mock(side_effect=AssertionError("PID inspected"))
    monkeypatch.setattr(pm, "_plugin_child_env", env)
    monkeypatch.setattr(pm, "_resolve_pid_path", pid)
    assert supervisor.start_external_plugin(plugin) is False
    assert supervisor._processes[plugin.name] is child
    child.poll.assert_not_called()
    child.terminate.assert_not_called()
    env.assert_not_called()
    pid.assert_not_called()


@pytest.mark.parametrize("trusted", [False, True])
@pytest.mark.parametrize("handler", [False, True])
def test_disabled_blocks_shared_persisted_registry_and_handlers(tmp_path, monkeypatch, trusted, handler):
    root = tmp_path / "plugins"
    write(root, data(enabled=False, execution_mode="remote_bridge"))
    file = tmp_path / "shared.json"
    registry = CapabilityRegistry(str(file))
    registry.register(Capability("policy.read", "stale", "http://invalid.test/cap",
                                 execution_mode="remote_bridge"))
    shared = CapabilityRegistry(str(file))
    obj = manager(tmp_path, root, registry=shared)
    other = manager(tmp_path, tmp_path / "empty", registry=shared)
    invoked = Mock()
    if handler:
        obj.register_capability_handler("policy.read", invoked, authority=READ)
    monkeypatch.setitem(pm.CAPABILITY_AUTHORITY, "policy.read", READ)
    call = obj.call_capability_trusted if trusted else obj.call_capability
    with pytest.raises(pm.CapabilityRefused, match="enabled=false"):
        call("policy.read")
    invoked.assert_not_called()
    assert shared.get("policy.read") is other._registry.get("policy.read")
    assert shared.get("policy.read").use_count == 0
    row = json.loads((tmp_path / "audit.jsonl").read_text().splitlines()[-1])
    assert row["authority"] == HIGH_IMPACT and row["outcome"] == "refused"


@pytest.mark.parametrize("collision", ["name", "capability"])
def test_disabled_still_reserves_crossroot_claims(tmp_path, collision):
    a, b = tmp_path / "a", tmp_path / "b"
    write(a, data(enabled=False))
    rival = data(name="policy_rival")
    if collision == "name":
        rival = data(capabilities=[{"name": "policy.other"}])
    write(b, rival)
    obj = manager(tmp_path, a, b)
    assert all(p["status"] == "disabled" for p in obj.list_plugins())
    assert not any(obj.load_all().values())
    invoked = Mock()
    obj.register_capability_handler("policy.read", invoked, authority=READ)
    with pytest.raises(pm.CapabilityRefused):
        obj.call_capability_trusted("policy.read")
    invoked.assert_not_called()


def test_canonical_disabled_entries_and_reservations(tmp_path):
    obj = manager(tmp_path, REPO / "ccos/plugins")
    disabled = [p for p in obj.list_plugins() if p["enabled"] is False]
    assert {p["name"] for p in disabled} == {"private_agent", "aigentik"}
    for row in disabled:
        assert row["status"] == "disabled" and row["error"] == REASON
        plugin = obj.get_plugin(row["name"])
        assert obj.load(plugin.name) is False
        assert obj.supervisor.start_external_plugin(plugin) is False
        for index, cap in enumerate(plugin.capabilities):
            assert cap in pm._CANONICAL_CAPABILITY_NAMES
            root = tmp_path / f"rogue-{plugin.name}-{index}"
            write(root, data(capabilities=[{"name": cap}]))
            rogue = manager(tmp_path, root)
            assert "canonical" in rogue.get_plugin("policy_fixture").error
            obj._registry.register(Capability(cap, "stale", "http://invalid.test/cap"))
            for call in (obj.call_capability, obj.call_capability_trusted):
                with pytest.raises(pm.CapabilityRefused, match="enabled=false"):
                    call(cap)
    assert obj.supervisor._processes == {}


def test_deliberate_reenable_still_checks_containment(tmp_path, monkeypatch):
    root = tmp_path / "plugins"
    manifest = data(enabled=False)
    path = write(root, manifest)
    obj = manager(tmp_path, root)
    assert obj.load("policy_fixture") is False
    manifest.update(enabled=True, entry_point="../escape.py")
    (path / "manifest.json").write_text(json.dumps(manifest))
    obj._discover()
    assert obj.load("policy_fixture") is False
    assert "escapes" in obj.get_plugin("policy_fixture").error
    manifest["entry_point"] = "__init__.py"
    (path / "manifest.json").write_text(json.dumps(manifest))
    obj._discover()
    assert obj.load("policy_fixture") is True
    monkeypatch.setitem(pm.CAPABILITY_AUTHORITY, "policy.read", READ)
    assert obj.call_capability("policy.read") == "fixture"


def test_observed_disable_retains_owned_child_until_explicit_unload(tmp_path):
    root = tmp_path / "plugins"
    manifest = data(enabled=True, execution_mode="external_process")
    path = write(root, manifest)
    obj = manager(tmp_path, root)
    plugin = obj.get_plugin("policy_fixture")
    plugin.status, plugin.capabilities, plugin.pid = pm.PluginStatus.ACTIVE, ["policy.read"], 123456789
    child = SimpleNamespace(pid=plugin.pid, stdout=None, stderr=None)
    child.poll = Mock(return_value=None)
    child.wait = Mock(return_value=0)
    child.terminate = Mock(side_effect=lambda: setattr(child.poll, "return_value", 0))
    child.kill = Mock(side_effect=AssertionError("unexpected escalation"))
    obj.supervisor._processes[plugin.name] = child
    obj.supervisor._ready.add(plugin.name)
    obj._registry.register(Capability("policy.read", "fixture", "http://invalid.test/cap"))
    invoked = Mock(return_value="before")
    obj.register_capability_handler("policy.read", invoked, authority=READ)
    assert obj.call_capability("policy.read") == "before"
    obj._modules[plugin.name] = SimpleNamespace(read=invoked)
    manifest["enabled"] = False
    (path / "manifest.json").write_text(json.dumps(manifest))
    obj._discover()
    assert obj.get_plugin(plugin.name) is plugin
    assert plugin.manifest["enabled"] is False
    assert plugin.pid == child.pid and plugin.status == pm.PluginStatus.ACTIVE
    assert obj.supervisor._processes[plugin.name] is child
    child.poll.assert_not_called()
    child.terminate.assert_not_called()
    assert obj.load(plugin.name) is False
    assert obj.supervisor.start_external_plugin(plugin) is False
    child.poll.assert_not_called()
    for call in (obj.call_capability, obj.call_capability_trusted):
        with pytest.raises(pm.CapabilityRefused):
            call("policy.read")
    with pytest.raises(pm.CapabilityRefused):
        obj.execute(plugin.name, "read")
    assert invoked.call_count == 1
    assert obj.unload(plugin.name) is True
    child.terminate.assert_called_once_with()
    child.wait.assert_called_once()
    assert obj.supervisor._processes == {} and plugin.pid is None
    obj._discover()
    assert obj.get_plugin(plugin.name).status == pm.PluginStatus.DISABLED


def test_disable_observed_in_activation_preserves_attempt_identity(tmp_path, monkeypatch):
    import builtins

    root = tmp_path / "plugins"
    manifest = data(enabled=True)
    path = write(root, manifest, source=(
        "import builtins\nbuiltins._policy_disable_during_import()\n"
        "def read(): return 'fixture'\n"))
    obj = manager(tmp_path, root)
    original = obj.get_plugin("policy_fixture")
    observed = []

    def disable():
        attempt = obj._activation_attempts[original.name]
        manifest["enabled"] = False
        (path / "manifest.json").write_text(json.dumps(manifest))
        obj._discover()
        assert obj.get_plugin(original.name) is original
        assert obj._activation_attempts[original.name] is attempt
        observed.append(True)

    monkeypatch.setattr(builtins, "_policy_disable_during_import", disable, raising=False)
    # Already-started activation may finish; observed policy blocks new work.
    assert obj.load(original.name) is True
    assert observed == [True] and original.manifest["enabled"] is False
    assert obj.load(original.name) is False
    with pytest.raises(pm.CapabilityRefused):
        obj.call_capability_trusted("policy.read")
    with pytest.raises(pm.CapabilityRefused):
        obj.execute(original.name, "read")
    assert obj.unload(original.name) is True


def test_audit_contract_discovery_policy_vs_attempted_actions(tmp_path):
    root = tmp_path / "plugins"
    write(root, data(enabled=False))
    obj = manager(tmp_path, root)
    audit = tmp_path / "audit.jsonl"
    assert not audit.exists()  # Ordinary installed opt-out is not an attempt.
    assert obj.load("policy_fixture") is False
    assert obj.supervisor.start_external_plugin(obj.get_plugin("policy_fixture")) is False
    with pytest.raises(pm.CapabilityRefused):
        obj.call_capability("policy.read")
    actions = [json.loads(line)["action"] for line in audit.read_text().splitlines()]
    assert actions == ["ccos.plugin_activate:policy_fixture", "ccos.plugin_spawn:policy_fixture",
                       "ccos.call_capability:policy.read"]
    bad_root = tmp_path / "bad"
    write(bad_root, data(enabled="false"))
    manager(tmp_path, bad_root)
    invalid = json.loads(audit.read_text().splitlines()[-1])
    assert invalid["action"] == "ccos.plugin_discover:policy_fixture"
    assert "expected boolean" in invalid["reason"]
