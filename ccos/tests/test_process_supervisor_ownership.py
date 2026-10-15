"""Group13b owned-handle lifecycle tests; real fixture children always reaped."""

import io
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ccos.core import plugin_manager as module
from ccos.core.capability_registry import (
    Capability,
    CapabilityRegistry,
    CapabilityStatus,
)
from ccos.core.plugin_manager import (
    Plugin,
    PluginManager,
    PluginStatus,
    ProcessSupervisor,
)


class Child:
    """Deterministic Popen-shaped fake, never a real PID to signal."""

    def __init__(self, *, alive=True):
        self.pid = 12345
        self.alive = alive
        self.returncode = None if alive else 1
        self.stdout = io.BytesIO()
        self.stderr = io.BytesIO()
        self.terminate = Mock(side_effect=self._terminate)
        self.kill = Mock(side_effect=self._kill)
        self.wait = Mock(side_effect=self._wait)
        self.term_works = True
        self.kill_works = True

    def poll(self):
        return None if self.alive else self.returncode

    def _terminate(self):
        if self.term_works:
            self.alive, self.returncode = False, -15

    def _kill(self):
        if self.kill_works:
            self.alive, self.returncode = False, -9

    def _wait(self, timeout):
        if self.alive:
            raise subprocess.TimeoutExpired("fixture", timeout)
        return self.returncode


@pytest.fixture
def env(tmp_path, monkeypatch):
    # Protect every real fixture child even if a start/setup assertion fails.
    spawned = []
    real_popen = module.subprocess.Popen

    def tracked_popen(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        spawned.append(child)
        return child

    monkeypatch.setattr(module.subprocess, "Popen", tracked_popen)
    monkeypatch.setattr(module, "PLUGIN_PID_DIR", tmp_path / "state" / "plugins")
    supervisor = ProcessSupervisor()
    plugin = Plugin(
        name="fixture", path=str(tmp_path), execution_mode="external_process",
        manifest={"process_spec": {
            "start_command": [sys.executable, "-c", "import time; time.sleep(60)"],
            "pid_file": "fixture.pid",
        }},
    )
    value = SimpleNamespace(root=tmp_path, supervisor=supervisor, plugin=plugin,
                            pid=module.PLUGIN_PID_DIR / "fixture.pid", spawn=tracked_popen)
    try:
        yield value
    finally:
        for child in spawned:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
            else:
                child.wait(timeout=3)
            for stream in (child.stdout, child.stderr):
                if stream is not None:
                    stream.close()


def fake_spawn(env, monkeypatch, child=None):
    child = child or Child()
    spawn = Mock(return_value=child)
    monkeypatch.setattr(module.subprocess, "Popen", spawn)
    return child, spawn


def test_duplicate_start_keeps_one_owned_child(env, monkeypatch):
    child, spawn = fake_spawn(env, monkeypatch)
    assert env.supervisor.start_external_plugin(env.plugin)
    assert env.supervisor.start_external_plugin(env.plugin)
    spawn.assert_called_once()
    assert env.supervisor._processes["fixture"] is child
    assert env.plugin.pid == child.pid
    assert env.supervisor.stop_external_plugin("fixture")
    assert child.stdout.closed and child.stderr.closed


def test_concurrent_starts_do_not_create_orphan_child(env):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: env.supervisor.start_external_plugin(env.plugin), range(4)))
    assert results == [True] * 4
    child = env.supervisor._processes["fixture"]
    assert env.plugin.pid == child.pid
    assert child.poll() is None
    assert env.pid.read_text() == str(child.pid)
    assert env.supervisor.stop_external_plugin("fixture")
    assert child.poll() is not None


def test_already_exited_owned_handle_is_reaped_without_signal(env, monkeypatch):
    child, _ = fake_spawn(env, monkeypatch)
    assert env.supervisor.start_external_plugin(env.plugin)
    child.alive, child.returncode = False, 0
    assert env.supervisor.stop_external_plugin("fixture")
    child.terminate.assert_not_called()
    child.kill.assert_not_called()
    assert not env.pid.exists()
    assert "fixture" not in env.supervisor._processes


def test_early_exit_is_failure_not_active(env, monkeypatch):
    child, _ = fake_spawn(env, monkeypatch, Child(alive=False))
    assert not env.supervisor.start_external_plugin(env.plugin)
    assert env.plugin.status == PluginStatus.BROKEN
    assert env.plugin.pid is None
    assert "fixture" not in env.supervisor._processes
    child.terminate.assert_not_called()
    assert not env.pid.exists()
    assert child.stdout.closed and child.stderr.closed


def test_real_immediate_exit_is_observed_without_leaking_child(env):
    env.plugin.manifest["process_spec"]["start_command"] = [sys.executable, "-c", "raise SystemExit(2)"]
    assert not env.supervisor.start_external_plugin(env.plugin)
    assert env.plugin.status == PluginStatus.BROKEN
    assert env.plugin.pid is None
    assert not env.pid.exists()
    assert "fixture" not in env.supervisor._processes


@pytest.mark.parametrize("payload", ["malformed", "0", "-1", "9999999999999999999999999"])
def test_unknown_or_malformed_pid_record_is_preserved_and_never_signalled(env, monkeypatch, payload):
    env.pid.parent.mkdir(parents=True)
    env.pid.write_text(payload)
    spawn = Mock()
    kill = Mock(side_effect=AssertionError("Raw PID signalling forbidden"))
    monkeypatch.setattr(module.subprocess, "Popen", spawn)
    monkeypatch.setattr(module.os, "kill", kill)
    assert not env.supervisor.stop_external_plugin("fixture", pid_file=env.pid)
    assert not env.supervisor.start_external_plugin(env.plugin)
    assert env.pid.read_text() == payload
    spawn.assert_not_called()
    kill.assert_not_called()


def test_forged_pid_file_never_signals_independent_fixture_child(env):
    unrelated = env.spawn([sys.executable, "-c", "import time; time.sleep(60)"])
    env.pid.parent.mkdir(parents=True)
    env.pid.write_text(str(unrelated.pid))
    assert not env.supervisor.stop_external_plugin("fixture", pid_file=env.pid)
    assert not env.supervisor.start_external_plugin(env.plugin)
    assert unrelated.poll() is None
    assert env.pid.read_text() == str(unrelated.pid)


def test_pid_record_symlink_blocks_start_and_stop(env, monkeypatch):
    target = env.root / "target.pid"
    target.write_text("12345")
    env.pid.parent.mkdir(parents=True)
    env.pid.symlink_to(target)
    spawn = Mock()
    monkeypatch.setattr(module.subprocess, "Popen", spawn)
    assert not env.supervisor.start_external_plugin(env.plugin)
    assert not env.supervisor.stop_external_plugin("fixture", pid_file=env.pid)
    assert env.pid.is_symlink()
    assert target.read_text() == "12345"
    spawn.assert_not_called()


def test_post_spawn_pid_publication_failure_cleans_up_owned_child(env, monkeypatch):
    child, _ = fake_spawn(env, monkeypatch)
    monkeypatch.setattr(env.supervisor, "_publish_pid", Mock(side_effect=OSError("write failure")))
    assert not env.supervisor.start_external_plugin(env.plugin)
    assert child.poll() is not None
    assert "fixture" not in env.supervisor._processes
    assert env.plugin.pid is None
    child.terminate.assert_called_once()


def test_failed_setup_and_failed_cleanup_retain_owned_handle_for_retry(env, monkeypatch):
    child, spawn = fake_spawn(env, monkeypatch)
    child.terminate.side_effect = PermissionError
    monkeypatch.setattr(env.supervisor, "_publish_pid", Mock(side_effect=OSError("write failure")))
    assert not env.supervisor.start_external_plugin(env.plugin)
    assert env.supervisor._processes["fixture"] is child
    assert env.plugin.pid == child.pid
    assert not env.supervisor.start_external_plugin(env.plugin)
    spawn.assert_called_once()
    child.terminate.side_effect = child._terminate
    assert env.supervisor.stop_external_plugin("fixture")


def test_startup_health_failure_stops_owned_child(env, monkeypatch):
    child, _ = fake_spawn(env, monkeypatch)
    env.plugin.manifest["process_spec"]["health_endpoint"] = "http://127.0.0.1:1/fixture"
    urlopen = Mock(side_effect=OSError("unhealthy"))
    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    assert not env.supervisor.start_external_plugin(env.plugin)
    assert urlopen.call_args.kwargs["timeout"] == 1.5
    assert child.poll() is not None
    assert not env.pid.exists()
    assert "fixture" not in env.supervisor._processes


@pytest.mark.parametrize("failure", ["permission", "timeout", "unconfirmed"])
def test_stop_failure_keeps_handle_pid_record_and_readiness(env, monkeypatch, failure):
    child, _ = fake_spawn(env, monkeypatch)
    assert env.supervisor.start_external_plugin(env.plugin)
    before = env.pid.read_bytes()
    if failure == "permission":
        child.terminate.side_effect = PermissionError
    elif failure == "timeout":
        child.term_works = child.kill_works = False
    else:
        child.term_works = False
        child.wait.side_effect = None
        child.wait.return_value = 0  # claimed wait result but poll still alive
    assert not env.supervisor.stop_external_plugin("fixture", timeout=0.01)
    assert env.supervisor._processes["fixture"] is child
    assert env.supervisor._pid_files["fixture"] == env.pid
    assert env.pid.read_bytes() == before
    assert "fixture" in env.supervisor._ready


def test_ignored_term_escalates_and_waits_for_owned_child(env, monkeypatch):
    child, _ = fake_spawn(env, monkeypatch)
    child.term_works = False
    assert env.supervisor.start_external_plugin(env.plugin)
    assert env.supervisor.stop_external_plugin("fixture", timeout=0.01)
    child.terminate.assert_called_once()
    child.kill.assert_called_once()
    assert child.poll() == -9
    assert not env.pid.exists()


@pytest.mark.parametrize("replacement", ["inode", "content", "symlink"])
def test_stop_preserves_replaced_pid_record(env, monkeypatch, replacement):
    child, _ = fake_spawn(env, monkeypatch)
    assert env.supervisor.start_external_plugin(env.plugin)
    if replacement == "inode":
        other = env.root / "replacement.pid"
        other.write_text(str(child.pid))  # same text, different inode
        other.replace(env.pid)
    elif replacement == "content":
        env.pid.write_text("99999")
    else:
        env.pid.unlink()
        target = env.root / "replacement.pid"
        target.write_text(str(child.pid))
        env.pid.symlink_to(target)
    assert env.supervisor.stop_external_plugin("fixture")
    assert child.poll() is not None
    assert env.pid.exists()
    assert env.pid.is_symlink() == (replacement == "symlink")


def test_explicit_foreign_pid_path_does_not_replace_owned_record_for_cleanup(env, monkeypatch):
    child, _ = fake_spawn(env, monkeypatch)
    assert env.supervisor.start_external_plugin(env.plugin)
    foreign = env.root / "foreign.pid"
    foreign.write_text(str(child.pid))
    assert env.supervisor.stop_external_plugin("fixture", pid_file=foreign)
    assert foreign.exists()
    assert not env.pid.exists()


def test_health_check_never_adopts_unowned_http_service(env, monkeypatch):
    urlopen = Mock()
    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    assert not env.supervisor.check_health("missing", "http://127.0.0.1/fixture")
    urlopen.assert_not_called()


def manager_fixture(env):
    registry = CapabilityRegistry(store_path=str(env.root / "caps.json"))
    manager = PluginManager(plugin_dirs=[str(env.root)], registry=registry)
    manager._plugins["fixture"] = env.plugin
    manager.supervisor = env.supervisor
    return manager, registry


def test_unload_stop_failure_preserves_all_plugin_state(env, monkeypatch):
    manager, registry = manager_fixture(env)
    child, _ = fake_spawn(env, monkeypatch)
    env.plugin.manifest["capabilities"] = [{"name": "fixture.cap"}]
    assert manager.load("fixture")
    module_object = object()
    manager._modules["fixture"] = module_object
    monkeypatch.setitem(sys.modules, "ccos_plugin_fixture", module_object)
    child.terminate.side_effect = PermissionError
    assert not manager.unload("fixture")
    assert env.plugin.status == PluginStatus.ACTIVE
    assert env.plugin.pid == child.pid
    assert env.plugin.capabilities == ["fixture.cap"]
    assert registry.get("fixture.cap") is not None
    assert manager._modules["fixture"] is module_object
    assert sys.modules["ccos_plugin_fixture"] is module_object
    assert env.pid.exists()


def test_repeated_and_concurrent_manager_load_registers_capability_once(env):
    manager, registry = manager_fixture(env)
    env.plugin.manifest["capabilities"] = [{"name": "fixture.cap"}]
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(lambda _: manager.load("fixture"), range(4)))
    assert env.plugin.capabilities == ["fixture.cap"]
    assert registry.get("fixture.cap") is not None
    assert manager.unload("fixture")
    assert env.plugin.status == PluginStatus.INSTALLED
    assert registry.get("fixture.cap") is None


def test_unknown_owner_unload_does_not_unregister_capabilities(env):
    manager, registry = manager_fixture(env)
    env.plugin.status = PluginStatus.ACTIVE
    env.plugin.pid = 12345
    env.plugin.capabilities = ["fixture.cap"]
    registry.register(Capability(name="fixture.cap", description="fixture", implementation="fixture"))
    env.pid.parent.mkdir(parents=True)
    env.pid.write_text("12345")
    assert not manager.unload("fixture")
    assert registry.get("fixture.cap") is not None
    assert env.plugin.pid == 12345
    assert env.plugin.status == PluginStatus.ACTIVE



def test_actual_pid_open_failure_cleans_up_spawned_handle(env, monkeypatch):
    from pathlib import Path

    child, _ = fake_spawn(env, monkeypatch)
    path_open = Path.open

    def fail_pid_open(path, *args, **kwargs):
        if path == env.pid:
            raise PermissionError("fixture PID publication denied")
        return path_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_pid_open)
    assert not env.supervisor.start_external_plugin(env.plugin)
    assert child.poll() is not None
    assert "fixture" not in env.supervisor._processes
    assert child.stdout.closed and child.stderr.closed


def test_post_spawn_record_race_preserves_foreign_publication(env, monkeypatch):
    child, _ = fake_spawn(env, monkeypatch)
    publish = env.supervisor._publish_pid

    def raced_publish(name, path, process):
        path.parent.mkdir(parents=True)
        path.write_text("foreign record")
        publish(name, path, process)

    monkeypatch.setattr(env.supervisor, "_publish_pid", raced_publish)
    assert not env.supervisor.start_external_plugin(env.plugin)
    assert child.poll() is not None
    assert env.pid.read_text() == "foreign record"
    assert "fixture" not in env.supervisor._processes


def test_owned_stop_ignores_pid_record_forged_to_independent_child(env):
    unrelated = env.spawn([sys.executable, "-c", "import time; time.sleep(60)"])
    assert env.supervisor.start_external_plugin(env.plugin)
    own_child = env.supervisor._processes["fixture"]
    env.pid.write_text(str(unrelated.pid))
    assert env.supervisor.stop_external_plugin("fixture")
    assert own_child.poll() is not None
    assert unrelated.poll() is None
    assert env.pid.read_text() == str(unrelated.pid)


def test_duplicate_start_and_stop_poll_failure_preserve_handle(env, monkeypatch):
    child, spawn = fake_spawn(env, monkeypatch)
    assert env.supervisor.start_external_plugin(env.plugin)
    monkeypatch.setattr(child, "poll", Mock(side_effect=OSError("unknown liveness")))
    assert not env.supervisor.start_external_plugin(env.plugin)
    assert not env.supervisor.stop_external_plugin("fixture")
    assert env.supervisor._processes["fixture"] is child
    spawn.assert_called_once()
    child.terminate.assert_not_called()
    assert env.pid.exists()


def test_stop_does_not_block_on_replaced_fifo_record(env, monkeypatch):
    import os

    child, _ = fake_spawn(env, monkeypatch)
    assert env.supervisor.start_external_plugin(env.plugin)
    env.pid.unlink()
    os.mkfifo(env.pid)
    assert env.supervisor.stop_external_plugin("fixture")
    assert child.poll() is not None
    assert env.pid.exists()



def test_explicit_reload_observes_exited_child_marks_broken_and_retries_once(env, monkeypatch):
    manager, registry = manager_fixture(env)
    env.plugin.manifest["capabilities"] = [{"name": "fixture.cap"}]
    old_child, new_child = Child(), Child()
    new_child.pid = 12346
    spawn = Mock(side_effect=[old_child, new_child])
    monkeypatch.setattr(module.subprocess, "Popen", spawn)
    assert manager.load("fixture")
    old_child.alive, old_child.returncode = False, 2

    assert not manager.load("fixture")
    assert env.plugin.status == PluginStatus.BROKEN
    assert registry.get("fixture.cap").status == CapabilityStatus.BROKEN
    assert not registry.has("fixture.cap")
    assert env.supervisor._processes["fixture"] is old_child
    assert env.pid.exists()
    assert env.plugin.pid == old_child.pid
    assert env.plugin.capabilities == ["fixture.cap"]
    old_child.terminate.assert_not_called()

    assert manager.load("fixture")
    assert env.plugin.status == PluginStatus.ACTIVE
    assert registry.get("fixture.cap").status == CapabilityStatus.ACTIVE
    assert env.supervisor._processes["fixture"] is new_child
    assert env.pid.read_text() == str(new_child.pid)
    assert env.plugin.pid == new_child.pid
    assert env.plugin.capabilities == ["fixture.cap"]
    old_child.terminate.assert_not_called()
    assert old_child.stdout.closed and old_child.stderr.closed
    assert spawn.call_count == 2
    assert manager.load("fixture")  # healthy idempotent reload
    assert spawn.call_count == 2
    assert manager.unload("fixture")
    assert new_child.poll() is not None


def test_live_unhealthy_reload_preserves_owned_child_until_retry_cleanup(env, monkeypatch):
    manager, registry = manager_fixture(env)
    env.plugin.manifest["capabilities"] = [{"name": "fixture.cap"}]
    old_child, new_child = Child(), Child()
    new_child.pid = 12346
    spawn = Mock(side_effect=[old_child, new_child])
    monkeypatch.setattr(module.subprocess, "Popen", spawn)
    assert manager.load("fixture")
    env.plugin.manifest["process_spec"]["health_endpoint"] = "http://127.0.0.1:1/fixture"
    urlopen = Mock(side_effect=OSError("unhealthy"))
    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)

    assert not manager.load("fixture")
    assert old_child.poll() is None
    old_child.terminate.assert_not_called()
    assert env.plugin.status == PluginStatus.BROKEN
    assert registry.get("fixture.cap").status == CapabilityStatus.BROKEN
    assert env.supervisor._processes["fixture"] is old_child
    assert env.plugin.pid == old_child.pid
    assert env.pid.read_text() == str(old_child.pid)

    # A failed cleanup cannot turn a broken child into success or start a
    # replacement, even if a later health response might have recovered.
    old_child.terminate.side_effect = PermissionError
    assert not manager.load("fixture")
    assert spawn.call_count == 1
    assert env.plugin.status == PluginStatus.BROKEN
    assert registry.get("fixture.cap").status == CapabilityStatus.BROKEN
    assert env.plugin.capabilities == ["fixture.cap"]
    assert env.supervisor._processes["fixture"] is old_child

    old_child.terminate.side_effect = old_child._terminate
    healthy = Mock()
    healthy.__enter__ = Mock(return_value=Mock(status=200))
    healthy.__exit__ = Mock(return_value=None)
    urlopen.side_effect = None
    urlopen.return_value = healthy
    assert manager.load("fixture")
    assert old_child.poll() is not None
    assert old_child.stdout.closed and old_child.stderr.closed
    assert env.supervisor._processes["fixture"] is new_child
    assert env.plugin.pid == new_child.pid
    assert env.plugin.status == PluginStatus.ACTIVE
    assert registry.get("fixture.cap").status == CapabilityStatus.ACTIVE
    assert env.plugin.capabilities == ["fixture.cap"]
    assert registry.count() == 1
    assert spawn.call_count == 2
    assert manager.unload("fixture")
    assert new_child.poll() is not None
    assert not env.pid.exists()
