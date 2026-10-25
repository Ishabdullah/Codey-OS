"""Dashboard activates only its monitor adapter; all state is disposable."""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rich.text import Text

from core import dashboard_data as dashboard
from ccos.core import plugin_manager as pm
from ccos.core.capability_registry import CapabilityRegistry


REPO = Path(__file__).resolve().parents[1]
SNAPSHOT = {"cpu": 23.0, "ram_used": 2 * 1024**3, "ram_total": 8 * 1024**3,
            "temp": 42.0, "battery_pct": 80, "battery_charging": False}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("RESTORICON_DB_PATH", str(tmp_path / "restoricon.db"))
    for key in list(os.environ):
        if key.lower().endswith("_proxy"):
            monkeypatch.delenv(key)
    monkeypatch.setattr(dashboard, "_plugins", None)

    def forbidden(*args, **kwargs):
        raise AssertionError("Dashboard attempted a real process or HTTP request")

    monkeypatch.setattr(pm.subprocess, "Popen", forbidden)
    monkeypatch.setattr(pm.urllib.request, "urlopen", forbidden)


class RecordingManager:
    def __init__(self, outcomes=(True,)):
        self.outcomes = iter(outcomes)
        self.loads = []
        self.calls = []
        self.active = False

    def load_all(self):
        raise AssertionError("Unrelated plugin activation forbidden")

    def load(self, name):
        assert name == "thermal_monitor", "Unrelated plugin load"
        self.loads.append(name)
        result = next(self.outcomes)
        if isinstance(result, Exception):
            raise result
        self.active = result
        return result

    def call_capability(self, name):
        assert self.active, "Dispatch before activation"
        assert name == "system.monitor_snapshot"
        self.calls.append(name)
        return dict(SNAPSHOT)


def test_repeated_snapshots_cache_only_successful_target_load(monkeypatch):
    manager = RecordingManager()
    get_manager = Mock(return_value=manager)
    monkeypatch.setattr(pm, "get_plugin_manager", get_manager)
    assert dashboard.get_snapshot() == SNAPSHOT
    assert dashboard.get_snapshot() == SNAPSHOT
    assert manager.loads == ["thermal_monitor"]
    assert manager.calls == ["system.monitor_snapshot"] * 2
    get_manager.assert_called_once_with()
    assert dashboard._plugins is manager


def test_failed_load_is_not_cached_or_dispatched_and_can_retry(monkeypatch):
    manager = RecordingManager((False, True))
    get_manager = Mock(return_value=manager)
    monkeypatch.setattr(pm, "get_plugin_manager", get_manager)
    with pytest.raises(RuntimeError, match="^Dashboard thermal_monitor plugin unavailable$"):
        dashboard.get_snapshot()
    assert dashboard._plugins is None
    assert manager.calls == []
    assert dashboard.get_snapshot() == SNAPSHOT
    assert manager.loads == ["thermal_monitor"] * 2
    assert manager.calls == ["system.monitor_snapshot"]
    assert get_manager.call_count == 2


def test_failed_manager_is_not_pinned_when_shared_singleton_changes(monkeypatch):
    failed, good = RecordingManager((False,)), RecordingManager()
    get_manager = Mock(side_effect=[failed, good])
    monkeypatch.setattr(pm, "get_plugin_manager", get_manager)
    with pytest.raises(RuntimeError):
        dashboard.get_snapshot()
    assert dashboard.get_snapshot() == SNAPSHOT
    assert failed.calls == []
    assert dashboard._plugins is good


def test_activation_exception_leaves_cache_empty_and_retries(monkeypatch):
    failure = RuntimeError("fixture activation failure")
    manager = RecordingManager((failure, True))
    monkeypatch.setattr(pm, "get_plugin_manager", lambda: manager)
    with pytest.raises(RuntimeError) as caught:
        dashboard.get_snapshot()
    assert caught.value is failure
    assert dashboard._plugins is None
    assert manager.calls == []
    assert dashboard.get_snapshot() == SNAPSHOT


def test_snapshot_dispatch_failure_keeps_successful_activation(monkeypatch):
    manager = RecordingManager()
    failure = RuntimeError("fixture read failure")
    manager.call_capability = Mock(side_effect=[failure, dict(SNAPSHOT)])
    monkeypatch.setattr(pm, "get_plugin_manager", lambda: manager)
    with pytest.raises(RuntimeError) as caught:
        dashboard.get_snapshot()
    assert caught.value is failure
    assert dashboard.get_snapshot() == SNAPSHOT
    assert manager.loads == ["thermal_monitor"]
    assert dashboard._plugins is manager


def test_render_text_preserves_stats_bar_and_snapshot_dispatch(monkeypatch):
    manager = RecordingManager()
    monkeypatch.setattr(pm, "get_plugin_manager", lambda: manager)
    first = dashboard.get_render_text()
    second = dashboard.get_render_text()
    assert isinstance(first, Text)
    assert first.plain == second.plain
    assert "23.0%" in first.plain
    assert "2.0/8.0 GB" in first.plain
    assert "42°C" in first.plain
    assert manager.loads == ["thermal_monitor"]
    assert manager.calls == ["system.monitor_snapshot"] * 2


def test_real_canonical_manager_only_loads_monitor_adapter(monkeypatch, tmp_path):
    """Real manifest/discovery/module/gateway route, fake sampler, no spawning."""
    import sys
    import core.sysmon

    manifest = json.loads((REPO / "ccos/plugins/system/thermal_monitor/manifest.json").read_text())
    assert manifest["name"] == "thermal_monitor"
    assert "system.monitor_snapshot" in [c["name"] for c in manifest["capabilities"]]
    monitor = SimpleNamespace(start=Mock(), snapshot=dict(SNAPSHOT))
    monkeypatch.setattr(core.sysmon, "get_monitor", lambda: monitor)
    # Register restoration before dynamic plugin loading changes this key.
    monkeypatch.setitem(sys.modules, "ccos_plugin_thermal_monitor",
                        sys.modules.get("ccos_plugin_thermal_monitor"))
    manager = pm.PluginManager(
        [str(REPO / "ccos/plugins")], CapabilityRegistry(str(tmp_path / "registry.json")))
    monkeypatch.setattr(manager, "load_all", Mock(side_effect=AssertionError("eager activation")))
    monkeypatch.setattr(manager.supervisor, "start_external_plugin", Mock(side_effect=AssertionError("service spawn")))
    monkeypatch.setattr(pm, "get_plugin_manager", lambda: manager)
    assert dashboard.get_snapshot() == SNAPSHOT
    assert dashboard.get_snapshot() == SNAPSHOT
    assert monitor.start.call_count == 2
    assert [name for name, plugin in manager._plugins.items()
            if plugin.status == pm.PluginStatus.ACTIVE] == ["thermal_monitor"]
    manager.load_all.assert_not_called()
    manager.supervisor.start_external_plugin.assert_not_called()
