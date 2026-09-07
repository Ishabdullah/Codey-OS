#!/usr/bin/env python3
"""
Unit tests for external process plugin supervision and capability dispatch
in CCOS PluginManager and ProcessSupervisor.
"""

import json
import os
import sys
from unittest import mock

from ccos.core.capability_registry import CapabilityRegistry
from ccos.core.plugin_manager import Plugin, PluginManager, PluginStatus, ProcessSupervisor


def test_supervisor_start_and_stop_external_plugin(tmp_path):
    """Verify ProcessSupervisor starts a process, tracks its PID in a pid file, and cleans it up."""
    # Create a dummy script that sleeps
    script_file = tmp_path / "dummy_server.py"
    script_file.write_text("import time\ntime.sleep(60)\n")

    pid_file = tmp_path / "dummy.pid"
    manifest = {
        "schema_version": "2.0.0",
        "name": "dummy_plugin",
        "version": "1.0.0",
        "description": "Dummy external plugin",
        "domain": "test",
        "execution_mode": "external_process",
        "process_spec": {
            "start_command": [sys.executable, str(script_file)],
            "pid_file": str(pid_file),
        },
        "capabilities": [],
    }

    plugin = Plugin(
        name="dummy_plugin",
        path=str(tmp_path),
        manifest=manifest,
        execution_mode="external_process",
    )

    supervisor = ProcessSupervisor()
    started = supervisor.start_external_plugin(plugin)
    assert started is True
    assert plugin.pid is not None
    assert pid_file.exists()
    tracked_pid = int(pid_file.read_text().strip())
    assert tracked_pid == plugin.pid

    # Check health (alive)
    assert supervisor.check_health("dummy_plugin") is True

    # Stop process cleanly (Rule 3)
    stopped = supervisor.stop_external_plugin("dummy_plugin", pid_file=pid_file)
    assert stopped is True
    assert not pid_file.exists()

    # Process should no longer be running
    try:
        os.kill(tracked_pid, 0)
        assert False, f"Process {tracked_pid} should have been killed"
    except (ProcessLookupError, PermissionError):
        pass


def test_plugin_manager_external_process_lifecycle(tmp_path):
    """Verify PluginManager loads, registers capabilities, and unloads external plugins."""
    cat_dir = tmp_path / "voice"
    cat_dir.mkdir(parents=True)
    plugin_dir = cat_dir / "mock_voice"
    plugin_dir.mkdir()

    script_file = plugin_dir / "voice_server.py"
    script_file.write_text("import time\ntime.sleep(60)\n")

    manifest = {
        "schema_version": "2.0.0",
        "name": "mock_voice",
        "version": "1.0.0",
        "description": "Mock voice external agent",
        "domain": "voice",
        "execution_mode": "external_process",
        "process_spec": {
            "start_command": [sys.executable, str(script_file)],
            "pid_file": str(plugin_dir / "voice.pid"),
        },
        "capabilities": [
            {
                "id": "transcribe",
                "name": "voice.mock_transcribe",
                "description": "Transcribe audio",
                "implementation": "http://127.0.0.1:9999/transcribe",
            }
        ],
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest))
    (plugin_dir / "__init__.py").write_text("def test(): return True\n")

    registry = CapabilityRegistry(store_path=str(tmp_path / "caps.json"))
    pm = PluginManager(plugin_dirs=[str(tmp_path)], registry=registry)

    # 1. Discover
    plugin = pm.get_plugin("mock_voice")
    assert plugin is not None
    assert plugin.execution_mode == "external_process"

    # 2. Load (starts process & registers capabilities)
    assert pm.load("mock_voice") is True
    assert plugin.status == PluginStatus.ACTIVE
    assert plugin.pid is not None

    cap = registry.get("voice.mock_transcribe")
    assert cap is not None
    assert cap.execution_mode == "external_process"

    # 3. Capability dispatch (with mock HTTP response)
    with mock.patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = json.dumps({"result": "hello from voice server"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = pm.call_capability("voice.mock_transcribe", audio_data="abc123")
        assert res == "hello from voice server"

    # 4. Unload (stops process)
    tracked_pid = plugin.pid
    assert pm.unload("mock_voice") is True
    assert plugin.status == PluginStatus.INSTALLED
    assert registry.get("voice.mock_transcribe") is None

    # Check process is stopped
    try:
        os.kill(tracked_pid, 0)
        assert False, f"Process {tracked_pid} should have stopped"
    except (ProcessLookupError, PermissionError):
        pass


def test_discovered_deployed_manifests(tmp_path):
    """Verify newly deployed voice and device manifests are discovered and valid."""
    pm = PluginManager()
    aigentik = pm.get_plugin("aigentik")
    assert aigentik is not None
    assert aigentik.execution_mode == "external_process"
    assert aigentik.domain == "voice"

    private_agent = pm.get_plugin("private_agent")
    assert private_agent is not None
    assert private_agent.execution_mode == "external_process"
    assert private_agent.domain == "device"
