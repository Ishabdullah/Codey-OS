"""Activation bookkeeping only: supervisor, signals and network are forbidden."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ccos.core import plugin_manager as pm
from ccos.core.capability_registry import Capability, CapabilityRegistry


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEY_STATE_DIR", str(tmp_path / "state"))
    def forbidden(*args, **kwargs):
        raise AssertionError("unit fixture attempted external effect")
    monkeypatch.setattr(pm.subprocess, "Popen", forbidden)
    monkeypatch.setattr(pm.os, "kill", forbidden)
    monkeypatch.setattr(pm.os, "getpgid", forbidden)
    monkeypatch.setattr(pm.os, "killpg", forbidden)
    monkeypatch.setattr(pm.urllib.request, "urlopen", forbidden)
    supervisor = Mock()
    supervisor.start_external_plugin.return_value = True
    supervisor.stop_external_plugin.return_value = True
    supervisor.check_health.return_value = True
    monkeypatch.setattr(pm, "ProcessSupervisor", lambda: supervisor)
    registry = CapabilityRegistry(str(tmp_path / "registry.json"))
    root = tmp_path / "plugins"
    directory = root / "test" / "fixture"
    directory.mkdir(parents=True)
    (directory / "__init__.py").write_text("def info(): return 'fixture'\n")
    manifest = {
        "name": "fixture", "execution_mode": "external_process",
        "capabilities": [{"name": "system.info"}, {"name": "system.processes"}],
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    # S2-B: this fixture's tmp tree stands in for the canonical plugin tree
    # (it declares CAPABILITY_AUTHORITY names such as system.info).
    monkeypatch.setattr(pm, "_CANONICAL_PLUGIN_ROOT", pm.os.path.realpath(root))
    obj = pm.PluginManager([str(root)], registry)
    obj.supervisor = supervisor
    gateway = SimpleNamespace(refuse_exec=Mock(return_value=SimpleNamespace(reason="activation incomplete")))
    monkeypatch.setattr(pm, "get_action_gateway", lambda: gateway)
    yield obj
    # No real process exists: supervisor is mocked before manager construction.


def inject_second_failure(manager, monkeypatch, failure=False):
    register = manager._registry.register
    def failing(cap):
        if cap.name == "system.processes":
            # Mutate before failure: rollback must include the failed call.
            register(cap)
            if failure is False:
                return False
            raise failure
        return register(cap)
    monkeypatch.setattr(manager._registry, "register", failing)
    return register


@pytest.mark.parametrize("mode", ["external_process", "in_process"])
def test_discovered_malformed_second_capability_stages_before_effects(manager, monkeypatch, mode):
    plugin = manager.get_plugin("fixture")
    manifest_file = pm.Path(plugin.path) / "manifest.json"
    raw = json.loads(manifest_file.read_text())
    raw["execution_mode"] = mode
    raw["capabilities"][1]["resource_limits"] = 1
    manifest_file.write_text(json.dumps(raw))
    manager._discover()
    imported = Mock(side_effect=AssertionError("import before validation"))
    monkeypatch.setattr(pm.importlib.util, "spec_from_file_location", imported)
    assert manager.load("fixture") is False
    assert manager.get_plugin("fixture").status == pm.PluginStatus.BROKEN
    manager.supervisor.start_external_plugin.assert_not_called()
    imported.assert_not_called()
    assert manager._registry.count() == 0


@pytest.mark.parametrize("field,value", [
    ("permissions", 2), ("inputs_schema", []), ("outputs_schema", "x"),
    ("implementation", 4), ("dependencies", [4]),
    ("hardware_requirements", "x"), ("name", "system.info"),
])
def test_invalid_consumed_fields_and_duplicate_names(manager, field, value):
    manager.get_plugin("fixture").manifest["capabilities"][1][field] = value
    assert manager.load("fixture") is False
    manager.supervisor.start_external_plugin.assert_not_called()


@pytest.mark.parametrize("failure", [False, RuntimeError("injected")])
def test_registration_failure_restores_original_and_unrelated(manager, monkeypatch, failure):
    original = Capability("system.info", "original", "old", use_count=12)
    unrelated = Capability("unrelated", "unrelated", "old", use_count=7)
    manager._registry.register(original)
    manager._registry.register(unrelated)
    inject_second_failure(manager, monkeypatch, failure)
    assert manager.load("fixture") is False
    plugin = manager.get_plugin("fixture")
    assert plugin.status == pm.PluginStatus.BROKEN
    assert plugin.capabilities == []
    assert manager._registry.get("system.info") is original
    assert original.use_count == 12
    assert manager._registry.get("unrelated") is unrelated
    assert unrelated.use_count == 7
    assert manager._registry.get("system.processes") is None
    manager.supervisor.stop_external_plugin.assert_called_once()


def test_stop_failure_retains_exact_owned_state_and_retry(manager, monkeypatch):
    plugin = manager.get_plugin("fixture")
    child = object()
    manager.supervisor._processes = {"fixture": child}
    def spawn(p):
        p.pid = 987654
        return True
    manager.supervisor.start_external_plugin.side_effect = spawn
    manager.supervisor.stop_external_plugin.return_value = False
    register = inject_second_failure(manager, monkeypatch)
    assert manager.load("fixture") is False
    assert plugin.pid == 987654
    assert manager.supervisor._processes["fixture"] is child
    assert manager.load("fixture") is False
    assert manager.supervisor.start_external_plugin.call_count == 1
    manager.supervisor.stop_external_plugin.return_value = True
    monkeypatch.setattr(manager._registry, "register", register)
    assert manager.load("fixture") is True
    assert plugin.capabilities == ["system.info", "system.processes"]
    assert manager.supervisor.start_external_plugin.call_count == 2


def test_rollback_failure_blocks_classified_read_and_retry_unload(manager, monkeypatch):
    inject_second_failure(manager, monkeypatch)
    unregister = manager._registry.unregister
    monkeypatch.setattr(manager._registry, "unregister", Mock(return_value=False))
    assert manager.load("fixture") is False
    assert pm.CAPABILITY_AUTHORITY["system.info"] == pm.READ
    handler = Mock()
    manager.register_capability_handler("system.info", handler, authority=pm.READ)
    with pytest.raises(pm.CapabilityRefused, match="activation incomplete"):
        manager.call_capability("system.info")
    handler.assert_not_called()
    assert manager.load("fixture") is False
    assert manager.supervisor.start_external_plugin.call_count == 1
    monkeypatch.setattr(manager._registry, "unregister", unregister)
    assert manager.unload("fixture") is True
    assert manager.get_plugin("fixture").status == pm.PluginStatus.INSTALLED
    assert manager._registry.count() == 0


def test_failed_restore_keeps_original_snapshot_until_retry(manager, monkeypatch):
    original = Capability("system.info", "original", "old")
    manager._registry.register(original)
    register = inject_second_failure(manager, monkeypatch)
    failing = manager._registry.register
    def reject_original(cap):
        if cap is original:
            raise OSError("restore failure")
        return failing(cap)
    monkeypatch.setattr(manager._registry, "register", reject_original)
    assert manager.load("fixture") is False
    assert "fixture" in manager._activation_attempts
    monkeypatch.setattr(manager._registry, "register", register)
    assert manager.unload("fixture") is True
    assert manager._registry.get("system.info") is original


@pytest.mark.parametrize("preexisting", [False, True])
@pytest.mark.parametrize("failure_kind", ["import", "registration"])
def test_module_failure_preserves_only_preexisting_module_state(manager, monkeypatch, preexisting, failure_kind):
    plugin = manager.get_plugin("fixture")
    plugin.execution_mode = "in_process"
    previous = SimpleNamespace(marker="preexisting")
    key = "ccos_plugin_fixture"
    if preexisting:
        monkeypatch.setitem(sys.modules, key, previous)
        manager._modules["fixture"] = previous
    else:
        monkeypatch.delitem(sys.modules, key, raising=False)
    if failure_kind == "import":
        (pm.Path(plugin.path) / "__init__.py").write_text("raise RuntimeError('import failure')\n")
    else:
        inject_second_failure(manager, monkeypatch)
    unrelated = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "plugin_unrelated_fixture", unrelated)
    assert manager.load("fixture") is False
    assert sys.modules.get(key) is (previous if preexisting else None)
    assert manager._modules.get("fixture") is (previous if preexisting else None)
    assert sys.modules["plugin_unrelated_fixture"] is unrelated
    assert plugin.status == pm.PluginStatus.BROKEN
    manager.supervisor.start_external_plugin.assert_not_called()


def test_interrupted_postspawn_registration_cleans_then_propagates(manager, monkeypatch):
    inject_second_failure(manager, monkeypatch, KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        manager.load("fixture")
    manager.supervisor.stop_external_plugin.assert_called_once()
    assert manager._registry.count() == 0
    assert manager.get_plugin("fixture").status == pm.PluginStatus.BROKEN


def test_start_exception_after_spawn_attempt_runs_cleanup(manager):
    manager.supervisor.start_external_plugin.side_effect = RuntimeError("after spawn")
    assert manager.load("fixture") is False
    manager.supervisor.stop_external_plugin.assert_called_once()


def test_concurrent_unload_waits_for_failed_activation(manager, monkeypatch):
    entered, release = Event(), Event()
    register = manager._registry.register
    def failing(cap):
        if cap.name == "system.processes":
            entered.set()
            assert release.wait(3)
            raise RuntimeError("registration failure")
        return register(cap)
    monkeypatch.setattr(manager._registry, "register", failing)
    with ThreadPoolExecutor(2) as executor:
        load = executor.submit(manager.load, "fixture")
        assert entered.wait(3)
        unload = executor.submit(manager.unload, "fixture")
        try:
            assert not unload.done()
        finally:
            release.set()
        assert load.result(3) is False
        assert unload.result(3) is True
    assert manager._registry.count() == 0


@pytest.mark.parametrize("spec", [
    1, {"env": ["x"]}, {"env": {"x": 1}}, {"pid_file": 1},
    {"health_endpoint": []}, {"start_command": "python"},
])
def test_process_shapes_rejected_before_spawn(manager, spec):
    manager.get_plugin("fixture").manifest["process_spec"] = spec
    assert manager.load("fixture") is False
    manager.supervisor.start_external_plugin.assert_not_called()


def test_independent_registry_replacement_is_never_erased(manager, monkeypatch):
    original = Capability("system.info", "old", "old")
    replacement = Capability("system.info", "other actor", "other")
    manager._registry.register(original)
    register = manager._registry.register
    def failing(cap):
        if cap.name == "system.processes":
            register(replacement)
            raise RuntimeError("independent replacement")
        return register(cap)
    monkeypatch.setattr(manager._registry, "register", failing)
    assert manager.load("fixture") is False
    assert manager._registry.get("system.info") is replacement
    assert manager.unload("fixture") is False
    assert manager._registry.get("system.info") is replacement
    assert "fixture" in manager._activation_attempts


def test_inprocess_failure_retry_registers_each_once(manager, monkeypatch):
    plugin = manager.get_plugin("fixture")
    plugin.execution_mode = "in_process"
    monkeypatch.delitem(sys.modules, "ccos_plugin_fixture", raising=False)
    register = inject_second_failure(manager, monkeypatch)
    assert manager.load("fixture") is False
    observed = Mock(side_effect=register)
    monkeypatch.setattr(manager._registry, "register", observed)
    assert manager.load("fixture") is True
    assert [call.args[0].name for call in observed.call_args_list] == ["system.info", "system.processes"]
    assert manager.execute("fixture", "info") == "fixture"
    assert manager.unload("fixture") is True


def test_interrupted_rollback_retains_marker_and_blocks_module_execution(manager, monkeypatch):
    plugin = manager.get_plugin("fixture")
    plugin.execution_mode = "in_process"
    monkeypatch.delitem(sys.modules, "ccos_plugin_fixture", raising=False)
    inject_second_failure(manager, monkeypatch)
    monkeypatch.setattr(manager._registry, "unregister", Mock(side_effect=KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        manager.load("fixture")
    assert "fixture" in manager._activation_attempts
    with pytest.raises(RuntimeError, match="activation incomplete"):
        manager.execute("fixture", "info")


def test_dispatch_cannot_capture_staged_read_across_high_impact_restore(manager, monkeypatch, tmp_path):
    """Replay the stale-object race with explicit events, never sleep ordering."""
    from threading import get_ident

    from core.action_gateway import ActionGateway

    original = Capability("system.info", "private original", "old", permissions=["fs:private"])
    manager._registry.register(original)
    handler = Mock(return_value="must never execute")
    manager.register_capability_handler("system.info", handler, authority=pm.READ)
    staged_ready, release_registration = Event(), Event()
    dispatch_checkpoint, release_gateway = Event(), Event()
    dispatch_thread = []
    original_lock = manager._lifecycle_lock

    class ObservedLock:
        def __enter__(self):
            if dispatch_thread and get_ident() == dispatch_thread[0]:
                dispatch_checkpoint.set()
            return original_lock.__enter__()

        def __exit__(self, *args):
            return original_lock.__exit__(*args)

    manager._lifecycle_lock = ObservedLock()
    gateway = ActionGateway(audit_file=tmp_path / "concurrent-audit.jsonl")

    def paused_gateway_lookup():
        dispatch_checkpoint.set()
        assert release_gateway.wait(3)
        return gateway

    monkeypatch.setattr(pm, "get_action_gateway", paused_gateway_lookup)
    register = manager._registry.register

    def fail_registration(cap):
        if cap.name == "system.processes":
            staged_ready.set()
            assert release_registration.wait(3)
            raise RuntimeError("force rollback after staged READ publication")
        return register(cap)

    monkeypatch.setattr(manager._registry, "register", fail_registration)

    def dispatch():
        dispatch_thread.append(get_ident())
        return manager.call_capability("system.info")

    with ThreadPoolExecutor(2) as executor:
        loading = executor.submit(manager.load, "fixture")
        assert staged_ready.wait(3)
        calling = executor.submit(dispatch)
        try:
            # Fixed code reaches the lock attempt; vulnerable code instead
            # reaches gateway lookup after capturing the staged READ object.
            assert dispatch_checkpoint.wait(3)
            release_registration.set()
            assert loading.result(3) is False
            assert manager._registry.get("system.info") is original
        finally:
            release_registration.set()
            release_gateway.set()
        with pytest.raises(pm.CapabilityRefused, match="HIGH_IMPACT"):
            calling.result(3)
    handler.assert_not_called()
    rows = [json.loads(line) for line in (tmp_path / "concurrent-audit.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["authority"] == pm.HIGH_IMPACT
    assert rows[0]["outcome"] == "refused"


def test_dispatch_holds_lifecycle_through_gated_callback(manager, monkeypatch, tmp_path):
    from threading import get_ident

    from core.action_gateway import ActionGateway

    original = Capability("system.info", "original READ", "old")
    manager._registry.register(original)
    manager.get_plugin("fixture").manifest["capabilities"][0]["permissions"] = ["fs:private"]
    gateway_entered, release_gateway = Event(), Event()
    activation_attempted, handler_ran, mutated_before_handler = Event(), Event(), Event()
    activation_thread = []
    lock = manager._lifecycle_lock

    class ObservedLock:
        def __enter__(self):
            if activation_thread and get_ident() == activation_thread[0]:
                activation_attempted.set()
            return lock.__enter__()

        def __exit__(self, *args):
            return lock.__exit__(*args)

    manager._lifecycle_lock = ObservedLock()
    gateway = ActionGateway(audit_file=tmp_path / "dispatch-first-audit.jsonl")

    def paused_lookup():
        gateway_entered.set()
        assert release_gateway.wait(3)
        return gateway

    monkeypatch.setattr(pm, "get_action_gateway", paused_lookup)

    def handler():
        assert manager._registry.get("system.info") is original
        handler_ran.set()
        return "original READ completed"

    manager.register_capability_handler("system.info", handler, authority=pm.READ)
    register = manager._registry.register

    def failed_registration(cap):
        if not handler_ran.is_set():
            mutated_before_handler.set()
        if cap.name == "system.processes":
            raise RuntimeError("registration failure")
        return register(cap)

    monkeypatch.setattr(manager._registry, "register", failed_registration)

    def activate():
        activation_thread.append(get_ident())
        return manager.load("fixture")

    with ThreadPoolExecutor(2) as executor:
        calling = executor.submit(manager.call_capability, "system.info")
        assert gateway_entered.wait(3)
        loading = executor.submit(activate)
        try:
            assert activation_attempted.wait(3)
        finally:
            release_gateway.set()
        assert calling.result(3) == "original READ completed"
        assert loading.result(3) is False
    assert handler_ran.is_set()
    assert not mutated_before_handler.is_set()
    assert manager._registry.get("system.info") is original
    rows = [json.loads(line) for line in (tmp_path / "dispatch-first-audit.jsonl").read_text().splitlines()]
    assert [(row["authority"], row["outcome"]) for row in rows] == [(pm.READ, "allowed")]


def test_direct_execute_waits_for_activation_rollback_and_uses_restored_module(manager, monkeypatch):
    from threading import get_ident

    plugin = manager.get_plugin("fixture")
    plugin.execution_mode = "in_process"
    previous = SimpleNamespace(info=Mock(return_value="restored original"))
    manager._modules["fixture"] = previous
    monkeypatch.setitem(sys.modules, "ccos_plugin_fixture", previous)
    registration_entered, release_registration, execute_attempted = Event(), Event(), Event()
    executing_thread = []
    lock = manager._lifecycle_lock

    class ObservedLock:
        def __enter__(self):
            if executing_thread and get_ident() == executing_thread[0]:
                execute_attempted.set()
            return lock.__enter__()

        def __exit__(self, *args):
            return lock.__exit__(*args)

    manager._lifecycle_lock = ObservedLock()
    register = manager._registry.register

    def failed_registration(cap):
        if cap.name == "system.processes":
            registration_entered.set()
            assert release_registration.wait(3)
            raise RuntimeError("rollback imported partial module")
        return register(cap)

    monkeypatch.setattr(manager._registry, "register", failed_registration)

    def execute():
        executing_thread.append(get_ident())
        return manager.execute("fixture", "info")

    with ThreadPoolExecutor(2) as executor:
        loading = executor.submit(manager.load, "fixture")
        assert registration_entered.wait(3)
        calling = executor.submit(execute)
        try:
            assert execute_attempted.wait(3)
            previous.info.assert_not_called()
        finally:
            release_registration.set()
        assert loading.result(3) is False
        assert calling.result(3) == "restored original"
    previous.info.assert_called_once_with()
    assert manager._modules["fixture"] is previous


def test_direct_execute_holds_lifecycle_through_module_lookup_and_callback(manager, monkeypatch):
    from threading import get_ident

    plugin = manager.get_plugin("fixture")
    plugin.execution_mode = "in_process"
    lookup_entered, release_lookup, activation_attempted = Event(), Event(), Event()
    original_called, mutated_before_callback = Event(), Event()
    activation_thread = []
    execution_thread = []
    lock = manager._lifecycle_lock

    class ObservedLock:
        def __enter__(self):
            if activation_thread and get_ident() == activation_thread[0]:
                activation_attempted.set()
            return lock.__enter__()

        def __exit__(self, *args):
            return lock.__exit__(*args)

    manager._lifecycle_lock = ObservedLock()

    def original_callback():
        original_called.set()
        return "original executed"

    previous = SimpleNamespace(info=original_callback)
    monkeypatch.setitem(sys.modules, "ccos_plugin_fixture", previous)

    class PausedModuleLookup(dict):
        def get(self, key, default=None):
            if execution_thread and get_ident() == execution_thread[0] and key == "fixture":
                lookup_entered.set()
                assert release_lookup.wait(3)
            return super().get(key, default)

    manager._modules = PausedModuleLookup(fixture=previous)
    register = manager._registry.register

    def failed_registration(cap):
        if not original_called.is_set():
            mutated_before_callback.set()
        if cap.name == "system.processes":
            raise RuntimeError("activation rollback")
        return register(cap)

    monkeypatch.setattr(manager._registry, "register", failed_registration)

    def execute():
        execution_thread.append(get_ident())
        return manager.execute("fixture", "info")

    def activate():
        activation_thread.append(get_ident())
        return manager.load("fixture")

    with ThreadPoolExecutor(2) as executor:
        calling = executor.submit(execute)
        assert lookup_entered.wait(3)
        loading = executor.submit(activate)
        try:
            assert activation_attempted.wait(3)
        finally:
            release_lookup.set()
        assert calling.result(3) == "original executed"
        assert loading.result(3) is False
    assert original_called.is_set()
    assert not mutated_before_callback.is_set()
    assert manager._modules["fixture"] is previous
