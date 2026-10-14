#!/usr/bin/env python3
"""
Unit tests for external process plugin supervision and capability dispatch
in CCOS PluginManager and ProcessSupervisor.
"""

import json
import os
import sys
from unittest import mock

import pytest

from ccos.core.capability_registry import CapabilityRegistry
from ccos.core.plugin_manager import (
    CAPABILITY_AUTHORITY,
    CapabilityRefused,
    Plugin,
    PluginManager,
    PluginStatus,
    ProcessSupervisor,
    _DEFAULT_DISPATCH_TIMEOUT,
    _DISPATCH_TIMEOUT_CEILING,
)
from core.action_gateway import READ


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


def test_plugin_manager_external_process_lifecycle(tmp_path, monkeypatch):
    """Verify PluginManager loads, registers capabilities, and unloads external plugins."""
    # WP2.1 group 4 (NEW-910/911/912): call_capability() now fail-closed-
    # refuses any name not in CAPABILITY_AUTHORITY. "voice.mock_transcribe"
    # is this test's own synthetic manifest capability (a mock transcribe
    # HTTP endpoint), not a real production one, so classify it for the
    # duration of this test only rather than add it to the core table.
    monkeypatch.setitem(CAPABILITY_AUTHORITY, "voice.mock_transcribe", READ)
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


def test_relative_pid_file_resolves_to_state_dir_not_plugin_path(tmp_path, monkeypatch):
    """NEW-278 regression: a relative `pid_file` must resolve against the
    runtime state dir, not the plugin's source directory (`plugin.path`).
    """
    from ccos.core import plugin_manager as pm_module

    state_dir = tmp_path / "state"
    plugin_dir = tmp_path / "plugin_src"
    plugin_dir.mkdir()

    monkeypatch.setattr(pm_module, "PLUGIN_PID_DIR", state_dir / "plugins")

    script_file = plugin_dir / "dummy_server.py"
    script_file.write_text("import time\ntime.sleep(60)\n")

    manifest = {
        "schema_version": "2.0.0",
        "name": "dummy_plugin",
        "version": "1.0.0",
        "description": "Dummy external plugin",
        "domain": "test",
        "execution_mode": "external_process",
        "process_spec": {
            "start_command": [sys.executable, str(script_file)],
            "pid_file": "dummy.pid",  # relative, bare filename
        },
        "capabilities": [],
    }

    plugin = Plugin(
        name="dummy_plugin",
        path=str(plugin_dir),
        manifest=manifest,
        execution_mode="external_process",
    )

    supervisor = pm_module.ProcessSupervisor()
    started = supervisor.start_external_plugin(plugin)
    assert started is True
    tracked_pid = plugin.pid

    try:
        expected_pid_path = state_dir / "plugins" / "dummy.pid"
        assert expected_pid_path.exists(), (
            "relative pid_file must resolve under the runtime state dir"
        )
        assert int(expected_pid_path.read_text().strip()) == tracked_pid

        # The old (buggy) location — inside the plugin's source directory —
        # must NOT be used.
        stale_path = plugin_dir / "dummy.pid"
        assert not stale_path.exists(), (
            "relative pid_file must not resolve inside plugin.path"
        )
    finally:
        # Stop the spawned child by its exact tracked PID (Rule 3).
        stopped = supervisor.stop_external_plugin(
            "dummy_plugin", pid_file=str(expected_pid_path)
        )
        assert stopped is True
        try:
            os.kill(tracked_pid, 0)
            assert False, f"Process {tracked_pid} should have been killed"
        except (ProcessLookupError, PermissionError):
            pass


def test_plugin_manager_unload_finds_relative_pid_file_written_by_load(tmp_path, monkeypatch):
    """NEW-278 regression: `PluginManager.unload()` must resolve a relative
    manifest `pid_file` the same way `start_external_plugin()` did when
    writing it, or the file `load()` wrote is never found/unlinked on
    unload (the file would silently persist under the old CWD-relative
    fallback in `stop_external_plugin()`).
    """
    from ccos.core import plugin_manager as pm_module

    state_dir = tmp_path / "state"
    monkeypatch.setattr(pm_module, "PLUGIN_PID_DIR", state_dir / "plugins")

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
            "pid_file": "voice.pid",  # relative, bare filename
        },
        "capabilities": [],
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest))
    (plugin_dir / "__init__.py").write_text("def test(): return True\n")

    registry = CapabilityRegistry(store_path=str(tmp_path / "caps.json"))
    pm = PluginManager(plugin_dirs=[str(tmp_path)], registry=registry)

    plugin = pm.get_plugin("mock_voice")
    assert plugin is not None

    assert pm.load("mock_voice") is True
    tracked_pid = plugin.pid
    expected_pid_path = state_dir / "plugins" / "voice.pid"
    assert expected_pid_path.exists(), "load() must write the pid file under the state dir"

    assert pm.unload("mock_voice") is True
    # This is the real discriminator: with the pre-fix code (unload()
    # passing the raw relative manifest string straight to
    # stop_external_plugin(), which resolves it against the CWD instead),
    # this file would never be found and would still exist here.
    assert not expected_pid_path.exists(), (
        "unload() must resolve the same relative pid_file location "
        "load() wrote to, and unlink it"
    )

    try:
        os.kill(tracked_pid, 0)
        assert False, f"Process {tracked_pid} should have been killed"
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


# --- WP2.1 group 5 (dormant remote_bridge/external_process HTTP dispatch
# timeout enforcement) -------------------------------------------------
#
# plugin_manager.py's HTTP dispatch thunk (call_capability()) used a
# hardcoded `timeout=10.0`, ignoring the capability's/plugin's declared
# `resource_limits.timeout_seconds`. This branch is confirmed unreachable
# in production today (no caller passes a device.*/voice.* capability
# name; both real manifests' permissions force HIGH_IMPACT, which fails
# closed before execute() runs; and even if it ran, both plugins'
# start_commands reference non-existent target scripts). Fixed anyway as
# dormant-but-reachable-if-ever-activated code, matching group 4's
# existing coverage pattern for dormant callers.


def _load_synthetic_http_plugin(tmp_path, monkeypatch, capabilities, plugin_resource_limits=None):
    """Discover+load a synthetic external_process plugin with one or more
    HTTP-implementation capabilities, classifying each as READ so dispatch
    reaches the HTTP thunk instead of failing closed on authority.

    `ProcessSupervisor.start_external_plugin` is mocked (return True, no
    real process) -- these tests are purely about `_resolve_dispatch_
    timeout()`'s precedence/clamp logic via the real `call_capability()`
    dispatch path (with `urllib.request.urlopen` itself mocked per-test),
    not about process supervision, which is already covered by
    `test_supervisor_start_and_stop_external_plugin`. A real `start_
    command` here would spawn a real (if short-lived) child process this
    helper has no caller-visible handle to stop (Rule 3: never leave a
    process this code spawned untracked/unstopped).
    """
    cat_dir = tmp_path / "test_domain"
    cat_dir.mkdir(parents=True)
    plugin_dir = cat_dir / "timeout_test_plugin"
    plugin_dir.mkdir()

    manifest = {
        "schema_version": "2.0.0",
        "name": "timeout_test_plugin",
        "version": "1.0.0",
        "description": "Synthetic plugin for dispatch-timeout tests",
        "domain": "test_domain",
        "execution_mode": "external_process",
        "process_spec": {
            # Never actually executed -- start_external_plugin is mocked
            # below -- but kept schema-shaped for clarity/documentation.
            "start_command": [sys.executable, "-c", "pass"],
            "pid_file": str(plugin_dir / "server.pid"),
        },
        "capabilities": capabilities,
    }
    if plugin_resource_limits is not None:
        manifest["resource_limits"] = plugin_resource_limits
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest))
    (plugin_dir / "__init__.py").write_text("def test(): return True\n")

    for cap_def in capabilities:
        monkeypatch.setitem(CAPABILITY_AUTHORITY, cap_def["name"], READ)

    monkeypatch.setattr(ProcessSupervisor, "start_external_plugin", lambda self, plugin, state_dir=None: True)

    registry = CapabilityRegistry(store_path=str(tmp_path / "caps.json"))
    pm = PluginManager(plugin_dirs=[str(tmp_path)], registry=registry)
    assert pm.load("timeout_test_plugin") is True
    return pm


def test_dispatch_uses_plugin_level_timeout_when_no_capability_override(tmp_path, monkeypatch):
    """A capability with no per-capability timeout_seconds uses the
    plugin-level resource_limits.timeout_seconds, not the old hardcoded
    10.0.
    """
    pm = _load_synthetic_http_plugin(
        tmp_path,
        monkeypatch,
        capabilities=[
            {
                "id": "action",
                "name": "test_domain.action",
                "description": "test",
                "implementation": "http://127.0.0.1:9988/action",
            }
        ],
        plugin_resource_limits={"timeout_seconds": 45},
    )

    with mock.patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = json.dumps({"result": "ok"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        pm.call_capability("test_domain.action")

        _, call_kwargs = mock_urlopen.call_args
        assert call_kwargs["timeout"] == 45


@pytest.mark.parametrize("invalid_timeout", [True, float("nan"), "20"])
def test_dispatch_rejects_non_numeric_or_bool_timeout_falls_back_to_plugin_level(
    tmp_path, monkeypatch, invalid_timeout
):
    """Code-reviewer warning: _resolve_dispatch_timeout()'s docstring
    claims bool/NaN/string values are rejected, but no test previously
    exercised that path directly (only -5/0, which fail a different
    branch of the same check). True is an int subclass in Python, so
    without the explicit `not isinstance(value, bool)` guard,
    timeout_seconds: true would silently produce a 1.0s timeout --
    this test would catch that regression."""
    pm = _load_synthetic_http_plugin(
        tmp_path,
        monkeypatch,
        capabilities=[
            {
                "id": "action",
                "name": "test_domain.action",
                "description": "test",
                "implementation": "http://127.0.0.1:9988/action",
                "timeout_seconds": invalid_timeout,
            }
        ],
        plugin_resource_limits={"timeout_seconds": 45},
    )

    with mock.patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = json.dumps({"result": "ok"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        pm.call_capability("test_domain.action")

        _, call_kwargs = mock_urlopen.call_args
        assert call_kwargs["timeout"] == 45


def test_dispatch_capability_level_timeout_overrides_plugin_level(tmp_path, monkeypatch):
    """A capability's own timeout_seconds override wins over the
    plugin-level value (trap 1 regression: normalize_manifest() places
    this as a sibling key on the capability dict, not nested under that
    capability's own resource_limits)."""
    pm = _load_synthetic_http_plugin(
        tmp_path,
        monkeypatch,
        capabilities=[
            {
                "id": "action",
                "name": "test_domain.action",
                "description": "test",
                "implementation": "http://127.0.0.1:9988/action",
                "timeout_seconds": 5,
            }
        ],
        plugin_resource_limits={"timeout_seconds": 45},
    )

    with mock.patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = json.dumps({"result": "ok"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        pm.call_capability("test_domain.action")

        _, call_kwargs = mock_urlopen.call_args
        assert call_kwargs["timeout"] == 5


def test_dispatch_falls_back_to_default_when_timeout_unset_or_zero(tmp_path, monkeypatch):
    """No resource_limits anywhere, and an explicit capability-level 0,
    both fall back to _DEFAULT_DISPATCH_TIMEOUT -- 0 must never be passed
    through literally (urlopen(timeout=0) is non-blocking, not "no
    timeout")."""
    pm = _load_synthetic_http_plugin(
        tmp_path,
        monkeypatch,
        capabilities=[
            {
                "id": "action",
                "name": "test_domain.action",
                "description": "test",
                "implementation": "http://127.0.0.1:9988/action",
                "timeout_seconds": 0,
            },
        ],
    )

    with mock.patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = json.dumps({"result": "ok"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        pm.call_capability("test_domain.action")

        _, call_kwargs = mock_urlopen.call_args
        assert call_kwargs["timeout"] == _DEFAULT_DISPATCH_TIMEOUT


def test_dispatch_falls_back_to_default_when_timeout_negative(tmp_path, monkeypatch):
    """A negative timeout_seconds (never schema-validated today --
    `_discover()` does not run manifests through `validate_manifest_v2()`)
    must fall back to the default, not be clamped-through as a negative
    `urlopen(timeout=...)` value (which would raise)."""
    pm = _load_synthetic_http_plugin(
        tmp_path,
        monkeypatch,
        capabilities=[
            {
                "id": "action",
                "name": "test_domain.action",
                "description": "test",
                "implementation": "http://127.0.0.1:9988/action",
                "timeout_seconds": -5,
            },
        ],
    )

    with mock.patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = json.dumps({"result": "ok"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        pm.call_capability("test_domain.action")

        _, call_kwargs = mock_urlopen.call_args
        assert call_kwargs["timeout"] == _DEFAULT_DISPATCH_TIMEOUT


def test_dispatch_timeout_clamped_to_core_ceiling(tmp_path, monkeypatch):
    """A capability declaring a timeout above the core-owned ceiling is
    clamped to the ceiling, not honored as-is -- manifests may only
    request something tighter, never looser."""
    pm = _load_synthetic_http_plugin(
        tmp_path,
        monkeypatch,
        capabilities=[
            {
                "id": "action",
                "name": "test_domain.action",
                "description": "test",
                "implementation": "http://127.0.0.1:9988/action",
                "timeout_seconds": 200,
            },
        ],
    )
    assert 200 > _DISPATCH_TIMEOUT_CEILING

    with mock.patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = json.dumps({"result": "ok"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        pm.call_capability("test_domain.action")

        _, call_kwargs = mock_urlopen.call_args
        assert call_kwargs["timeout"] == _DISPATCH_TIMEOUT_CEILING


def test_load_real_private_agent_manifest_folds_per_capability_timeout(tmp_path, monkeypatch):
    """End-to-end regression for trap 1 using the real deployed manifest
    (ccos/plugins/device/private_agent/manifest.json, not a hand-built
    Capability): device.local_action declares its own timeout_seconds:15,
    tighter than the plugin-level resource_limits.timeout_seconds:20;
    device.secure_relay declares timeout_seconds:20, matching the plugin
    level. Both must show up correctly on the registered Capability's
    resource_limits -- and on the timeout `_resolve_dispatch_timeout()`
    would actually use -- after going through the real
    PluginManager.load() path, not just an isolated helper-function check.

    This also proves the branch's current dormancy is unaffected by this
    fix: dispatching device.local_action through the real, unmodified
    call_capability() (no gating bypassed) still raises CapabilityRefused
    without ever calling urlopen(), because "device:control"/"fs:private"
    force HIGH_IMPACT and no confirmation path exists for CCOS dispatch
    (group 4, unchanged by this round).

    start_external_plugin() is mocked (return True, no real process) --
    this test is about capability data flow through load(), not process
    supervision (already covered by test_supervisor_start_and_stop_external_plugin),
    and the real manifest's start_command references a script that does
    not exist in this repo (confirmed unreachable dispatch path per
    WP2.1 group 5 scoping). PLUGIN_PID_DIR is also redirected into
    tmp_path (NEW-278 tests' pattern): unload()'s PID-file lookup
    otherwise resolves against the real runtime state dir, and with
    start_external_plugin mocked there's no tracked PID of our own to
    guard it -- Rule 3 requires never signaling a PID this test didn't
    itself spawn.
    """
    from ccos.core import plugin_manager as pm_module

    monkeypatch.setattr(pm_module, "PLUGIN_PID_DIR", tmp_path / "plugins")

    registry = CapabilityRegistry(store_path=str(tmp_path / "caps.json"))
    pm = PluginManager(registry=registry)  # default discovery: real ccos/plugins/

    plugin = pm.get_plugin("private_agent")
    assert plugin is not None
    assert plugin.resource_limits.get("timeout_seconds") == 20

    with mock.patch.object(ProcessSupervisor, "start_external_plugin", return_value=True):
        assert pm.load("private_agent") is True

    try:
        relay_cap = registry.get("device.secure_relay")
        local_cap = registry.get("device.local_action")
        assert relay_cap is not None
        assert local_cap is not None

        # Plugin-level value, correctly present (not dropped).
        assert relay_cap.resource_limits.get("timeout_seconds") == 20
        # Per-capability override wins over the plugin-level 20.
        assert local_cap.resource_limits.get("timeout_seconds") == 15

        # The actual timeout _resolve_dispatch_timeout() would use for
        # dispatch, not just the raw dict value.
        assert pm._resolve_dispatch_timeout(local_cap, plugin) == 15.0
        assert pm._resolve_dispatch_timeout(relay_cap, plugin) == 20.0

        # Dormancy: dispatch is still refused before urlopen() is ever
        # reached, through the real, un-bypassed call_capability() gating.
        with mock.patch("urllib.request.urlopen") as mock_urlopen:
            try:
                pm.call_capability("device.local_action")
                assert False, "expected CapabilityRefused"
            except CapabilityRefused:
                pass
            mock_urlopen.assert_not_called()
    finally:
        pm.unload("private_agent")
