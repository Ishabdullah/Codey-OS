"""NEW-956: fake owned children, conservative accounting and caller propagation.

Every OS signal and subprocess spawn is guarded in these unit tests. Actual
process verification is a separate fixture-owned live-verifier step.
"""

import asyncio
import signal
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import daemon
from core import loader_v2 as lv
from core import resource_gate as rg


class Child:
    pid = 606060

    def __init__(self):
        self.alive = True
        self.code = None
        self.term_works = True
        self.kill_works = True
        self.terminate = Mock(side_effect=self._term)
        self.kill = Mock(side_effect=self._kill)
        self.wait = Mock(side_effect=self._wait)

    def poll(self):
        return None if self.alive else self.code

    def _term(self):
        if self.term_works:
            self.alive, self.code = False, -15

    def _kill(self):
        if self.kill_works:
            self.alive, self.code = False, -9

    def _wait(self, timeout):
        if self.alive:
            raise subprocess.TimeoutExpired("fake child", timeout)
        return self.code


@pytest.fixture(autouse=True)
def guarded_os(monkeypatch):
    """No synthetic PID in this module can reach a real kernel signal."""
    kill = Mock()
    group = Mock()
    monkeypatch.setattr(lv.os, "kill", kill)
    monkeypatch.setattr(lv.os, "killpg", group)
    monkeypatch.setattr(lv.os, "getpgid", Mock(return_value=Child.pid))
    monkeypatch.setattr(lv.subprocess, "Popen", Mock(side_effect=AssertionError("No real subprocess in unit fixtures")))
    return SimpleNamespace(kill=kill, group=group)


@pytest.fixture
def owned_server():
    server = lv.LlamaServer(Path("/fake/model.gguf"), port=29877)
    server.process = Child()
    server._started = True
    server._STOP_TIMEOUT_S = 0.01
    return server


@pytest.mark.parametrize("failure", ["term", "kill", "final_wait", "unconfirmed_wait"])
def test_failed_stop_keeps_owned_handle_until_retry(owned_server, failure):
    child = owned_server.process
    if failure == "term":
        child.terminate.side_effect = PermissionError
    elif failure == "kill":
        child.term_works = False
        child.kill.side_effect = PermissionError
    elif failure == "final_wait":
        child.term_works = child.kill_works = False
    else:
        child.term_works = False
        child.wait.side_effect = None
        child.wait.return_value = 0
    assert owned_server.stop() is False
    assert owned_server.process is child
    assert owned_server._cleanup_pending
    assert not owned_server._started
    child.terminate.side_effect = child._term
    child.wait.side_effect = child._wait
    child.term_works = True
    assert owned_server.stop() is True
    assert child.poll() is not None
    assert owned_server.process is None
    assert not owned_server._cleanup_pending


@pytest.mark.parametrize("force", [False, True])
def test_successful_stop_waits_and_reaps(owned_server, force):
    child = owned_server.process
    child.term_works = not force
    assert owned_server.stop() is True
    child.terminate.assert_called_once()
    assert child.kill.call_count == int(force)
    assert child.wait.call_count == (2 if force else 1)
    assert child.poll() is not None
    assert owned_server.process is None


def test_exited_child_is_reaped_without_signaling(owned_server, guarded_os):
    child = owned_server.process
    child.alive, child.code = False, 2
    assert owned_server.stop() is True
    child.wait.assert_called_once()
    child.terminate.assert_not_called()
    child.kill.assert_not_called()
    guarded_os.kill.assert_not_called()
    guarded_os.group.assert_not_called()


def test_expected_session_group_only_while_anchored(owned_server, guarded_os):
    child = owned_server.process
    owned_server._owned_session_pid = child.pid
    guarded_os.group.side_effect = lambda group, sig: child._term()
    assert owned_server.stop() is True
    guarded_os.group.assert_called_once_with(child.pid, signal.SIGTERM)
    child.terminate.assert_not_called()


def test_changed_process_group_does_not_gain_group_signal_authority(owned_server, guarded_os, monkeypatch):
    child = owned_server.process
    owned_server._owned_session_pid = child.pid
    monkeypatch.setattr(lv.os, "getpgid", Mock(return_value=99999))
    assert owned_server.stop() is True
    guarded_os.group.assert_not_called()
    child.terminate.assert_called_once()


def test_pending_start_retry_does_not_overwrite_live_handle(owned_server, monkeypatch):
    child = owned_server.process
    child.terminate.side_effect = PermissionError
    assert owned_server.stop() is False
    spawn = Mock(side_effect=AssertionError("Must not spawn replacement"))
    monkeypatch.setattr(owned_server, "_spawn_locked", spawn)
    assert owned_server.start() is False
    assert owned_server.process is child
    spawn.assert_not_called()


def test_interruption_preserves_owned_server_state(owned_server):
    child = owned_server.process
    child.wait.side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        owned_server.stop()
    assert owned_server.process is child
    assert owned_server._cleanup_pending


@pytest.fixture
def loader_env(tmp_path, monkeypatch):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"fake, never loaded")
    binary = tmp_path / "fake-llama"
    binary.write_text("not executed")
    monkeypatch.setattr(lv.cfg, "MODEL_PATH", model)
    monkeypatch.setattr(lv, "LLAMA_SERVER_BIN", binary)
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)
    monkeypatch.setattr(lv, "_ensure_run_start_fallback", Mock())
    monkeypatch.setattr(lv, "_emit_gate_telemetry", Mock())
    monkeypatch.setattr(lv, "_emit_argv_provenance", Mock())
    monkeypatch.setattr(rg, "is_interactive_session_active", lambda: True)
    monkeypatch.setattr(rg, "read_meminfo", lambda: {"MemAvailable": 10**10, "MemTotal": 10**10})
    decision = SimpleNamespace(admitted=True, estimated_cost_bytes=1024)
    reserve = Mock(return_value=(decision, "slot-fixture"))
    release = Mock(return_value=True)
    bind = Mock(return_value=True)
    confirm = Mock()
    monkeypatch.setattr(rg, "reserve_slot", reserve)
    monkeypatch.setattr(rg, "release_slot", release)
    monkeypatch.setattr(rg, "bind_pending_slot_pid", bind)
    monkeypatch.setattr(lv, "confirm_resident_and_mark_slot", confirm)
    child = Child()
    options = SimpleNamespace(started=True, adopted=False, interrupt=False)
    created = []
    base_server = lv.LlamaServer

    class FixtureServer(base_server):
        def start(self):
            if options.adopted:
                self._started = True
                return True
            self.process = child
            self._cleanup_pending = True
            self._on_spawn(child)
            if options.interrupt:
                raise KeyboardInterrupt
            self._started = options.started
            self._cleanup_pending = not options.started
            return options.started

    def server_factory(*args, **kwargs):
        server = FixtureServer(*args, **kwargs)
        created.append(server)
        return server

    monkeypatch.setattr(lv, "LlamaServer", server_factory)
    loader = lv.ModelLoader()
    monkeypatch.setattr(loader, "_reconcile_adopted_slot", Mock())
    return SimpleNamespace(loader=loader, child=child, reserve=reserve, release=release,
                           bind=bind, confirm=confirm, options=options, created=created)


def test_unload_failure_retains_slot_server_pid_and_blocks_new_reservation(loader_env):
    env = loader_env
    assert env.loader.load_primary()
    server = env.loader._server
    env.child.terminate.side_effect = PermissionError
    with pytest.raises(lv.ModelTeardownError):
        env.loader.unload()
    assert env.loader._server is server
    assert env.loader._slot_id == "slot-fixture"
    assert env.loader.get_pid() == env.child.pid
    assert env.loader.is_cleanup_pending()
    assert env.loader.get_status()["cleanup_pending"]
    assert not env.loader.is_loaded()
    env.release.assert_not_called()
    assert env.loader.load_primary() is False
    assert env.loader.ensure_model() is False
    assert len(env.created) == env.reserve.call_count == 1
    env.child.terminate.side_effect = env.child._term
    env.loader.unload()
    assert env.loader._server is None and env.loader._slot_id is None
    env.release.assert_called_once_with("slot-fixture")


@pytest.mark.parametrize("failure", ["start", "confirm", "bind_false", "bind_error", "interrupt", "logging"])
def test_failed_load_retains_owned_cleanup_and_reservation(loader_env, monkeypatch, failure):
    env = loader_env
    env.child.terminate.side_effect = PermissionError
    if failure == "start":
        env.options.started = False
    elif failure == "confirm":
        env.confirm.side_effect = OSError("confirmation failed")
    elif failure == "bind_false":
        env.bind.return_value = False
    elif failure == "bind_error":
        env.bind.side_effect = OSError("binding failed")
    elif failure == "interrupt":
        env.options.interrupt = True
    else:
        monkeypatch.setattr(lv, "success", Mock(side_effect=OSError("closed output")))
    if failure == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            env.loader.load_primary()
    else:
        assert env.loader.load_primary() is False
    assert env.loader._server.process is env.child
    assert env.loader._slot_id == "slot-fixture"
    assert not env.loader.is_loaded()
    assert env.loader.is_cleanup_pending()
    assert env.loader.get_pid() == env.child.pid
    assert env.loader.get_status()["pending_child_bound"] == (failure not in ("bind_false", "bind_error"))
    env.release.assert_not_called()
    assert env.loader.load_primary() is False
    assert env.reserve.call_count == 1


@pytest.mark.parametrize("failure", [False, True])
def test_release_absent_is_success_but_io_failure_retains_slot(loader_env, failure):
    env = loader_env
    assert env.loader.load_primary()
    if failure:
        env.release.side_effect = OSError("accounting write failed")
        with pytest.raises(lv.ModelTeardownError):
            env.loader.unload()
        assert env.child.poll() is not None
        assert env.loader.get_pid() is None
        assert env.loader._slot_id == "slot-fixture"
        assert env.loader.is_cleanup_pending()
        assert env.loader.load_primary() is False
        assert env.reserve.call_count == 1
        env.release.side_effect = None
    env.release.return_value = False  # safely already absent under its lock
    env.loader.unload()
    assert env.loader._slot_id is None
    assert env.loader._server is None
    assert not env.loader.is_cleanup_pending()


def test_healthy_direct_load_is_idempotent(loader_env):
    env = loader_env
    assert env.loader.load_primary()
    assert env.loader.load_primary()
    assert env.reserve.call_count == 1
    assert len(env.created) == 1
    assert env.loader.get_pid() == env.child.pid


def test_adopted_reference_drops_only_our_reservation_without_stop(loader_env):
    env = loader_env
    env.options.adopted = True
    assert env.loader.load_primary()
    server = env.loader._server
    server.stop = Mock(side_effect=AssertionError("Adopted process must not be stopped"))
    assert env.loader._slot_id is None
    env.bind.assert_not_called()
    env.loader.unload()
    server.stop.assert_not_called()
    env.release.assert_called_once_with("slot-fixture")


def test_thermal_restart_retains_recommendation_when_teardown_fails(loader_env, monkeypatch):
    from core import thermal

    env = loader_env
    assert env.loader.load_primary()
    env.child.terminate.side_effect = PermissionError
    manager = SimpleNamespace(restart_recommended=True, current_threads=2)
    monkeypatch.setattr(thermal, "get_thermal_manager", lambda: manager)
    assert env.loader.ensure_model() is False
    assert manager.restart_recommended
    assert env.reserve.call_count == 1
    assert env.loader.get_pid() == env.child.pid


def test_reset_loader_preserves_singleton_on_teardown_failure(loader_env, monkeypatch):
    env = loader_env
    assert env.loader.load_primary()
    env.child.terminate.side_effect = PermissionError
    monkeypatch.setattr(lv, "_loader", env.loader)
    with pytest.raises(lv.ModelTeardownError):
        lv.reset_loader()
    assert lv._loader is env.loader
    assert env.loader.get_pid() == env.child.pid


def test_daemon_release_does_not_report_not_loaded_while_cleanup_pending(loader_env, monkeypatch):
    env = loader_env
    assert env.loader.load_primary()
    env.child.terminate.side_effect = PermissionError
    with pytest.raises(lv.ModelTeardownError):
        env.loader.unload()
    probe = Mock(return_value=False)
    monkeypatch.setattr(lv, "probe_port_health", probe)
    with pytest.raises(lv.ModelTeardownError):
        daemon.DaemonServer._release_model_slot_sync(env.loader, 29877)
    probe.assert_not_called()


def test_main_shutdown_never_falls_back_to_stale_numeric_pid(loader_env, monkeypatch, guarded_os):
    import main

    env = loader_env
    assert env.loader.load_primary()
    env.child.terminate.side_effect = PermissionError
    monkeypatch.setattr(lv, "get_loader", lambda: env.loader)
    monkeypatch.setattr(main, "_daemon_is_running", lambda: False)
    monkeypatch.setattr(main, "get_monitor", lambda: SimpleNamespace(stop=Mock()))
    warning = Mock()
    monkeypatch.setattr(main, "warning", warning)
    main.shutdown()
    guarded_os.group.assert_not_called()
    guarded_os.kill.assert_not_called()
    warning.assert_called_once()
    assert env.loader.get_pid() == env.child.pid
    assert env.loader.is_cleanup_pending()


@pytest.mark.parametrize("variant", ["primary", "secondary"])
def test_lora_swap_restores_cfg_and_does_not_reload_after_failed_teardown(tmp_path, monkeypatch, variant):
    from core import lora_import

    original, planner = tmp_path / "base.gguf", tmp_path / "planner.gguf"
    replacement = tmp_path / "fine.gguf"
    replacement.write_bytes(b"candidate")
    monkeypatch.setattr(lora_import.cfg, "MODEL_PATH", original)
    monkeypatch.setattr(lora_import.cfg, "PLANNER_MODEL_PATH", planner)
    loader = SimpleNamespace(unload=Mock(side_effect=lv.ModelTeardownError("pending")), load_primary=Mock())
    monkeypatch.setattr(lv, "get_loader", lambda: loader)
    ok, message = lora_import.swap_to_finetuned_model(str(replacement), variant)
    assert not ok and "teardown" in message.lower()
    assert lora_import.cfg.MODEL_PATH == original
    assert lora_import.cfg.PLANNER_MODEL_PATH == planner
    loader.load_primary.assert_not_called()


def test_backup_rollback_teardown_precedes_every_artifact_or_cfg_mutation(tmp_path, monkeypatch):
    from core import lora_import

    backup = tmp_path / "base.backup.gguf"
    target = tmp_path / "base.gguf"
    fine = tmp_path / "fine.gguf"
    backup.write_bytes(b"backup bytes")
    target.write_bytes(b"target bytes")
    monkeypatch.setattr(lora_import.cfg, "MODEL_PATH", fine)
    monkeypatch.setattr(lora_import.cfg, "PLANNER_MODEL_PATH", fine)
    loader = SimpleNamespace(unload=Mock(side_effect=lv.ModelTeardownError("pending")), load_primary=Mock())
    monkeypatch.setattr(lv, "get_loader", lambda: loader)
    ok, message = lora_import.rollback_to_backup(str(backup), "primary")
    assert not ok and "pending" in message
    assert backup.read_bytes() == b"backup bytes"
    assert target.read_bytes() == b"target bytes"
    assert lora_import.cfg.MODEL_PATH == fine and lora_import.cfg.PLANNER_MODEL_PATH == fine
    loader.load_primary.assert_not_called()


def test_backup_rollback_does_not_claim_success_after_failed_reload(tmp_path, monkeypatch):
    from core import lora_import

    backup = tmp_path / "base.backup.gguf"
    backup.write_bytes(b"backup bytes")
    loader = SimpleNamespace(unload=Mock(), load_primary=Mock(return_value=False))
    monkeypatch.setattr(lv, "get_loader", lambda: loader)
    monkeypatch.setattr(lora_import.cfg, "MODEL_PATH", tmp_path / "fine.gguf")
    monkeypatch.setattr(lora_import.cfg, "PLANNER_MODEL_PATH", tmp_path / "fine.gguf")
    ok, message = lora_import.rollback_to_backup(str(backup), "primary")
    assert not ok and "reload failed" in message


def test_concurrent_direct_loads_reserve_and_spawn_once(loader_env):
    env = loader_env
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(pool.map(lambda _: env.loader.load_primary(), range(4)))
    assert env.reserve.call_count == len(env.created) == 1


def test_on_spawn_binding_precedes_identity_and_health(tmp_path, monkeypatch):
    from core import process_identity

    events = []
    server = lv.LlamaServer(tmp_path / "fake.gguf", port=29877)
    child = Child()
    server._on_spawn = lambda process: events.append("bind")
    server.stop = Mock(return_value=False)  # synthetic PID teardown is guarded
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)
    monkeypatch.setattr(lv.subprocess, "Popen", Mock(side_effect=lambda *a, **k: (events.append("spawn"), child)[1]))
    monkeypatch.setattr(lv.subprocess, "run", Mock(return_value=SimpleNamespace(stdout="fixture", stderr="")))
    monkeypatch.setattr(lv.time, "sleep", Mock())
    publication = Mock()
    publication.__enter__ = Mock(return_value=SimpleNamespace(publish=lambda pid: events.append("publish")))
    publication.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(process_identity, "LifecycleRecord", Mock(return_value=publication))
    monkeypatch.setattr(server, "_check_health", lambda: (events.append("health"), True)[1])
    assert server._spawn_locked()
    assert events[:4] == ["spawn", "bind", "publish", "health"]


@pytest.mark.parametrize("reap_site", ["list", "reserve"])
@pytest.mark.parametrize("kind,retained", [("owned_pending", True), ("dead_child", False), ("resident_marker", False), ("unmarked_pending", False)])
def test_pending_child_reapers_preserve_only_permission_ambiguous_owned_pending(tmp_path, monkeypatch, reap_site, kind, retained):
    state_dir = tmp_path / "state"
    slot_id = rg.register_slot("fixture", 2048, pid=88888, port=29877, state_dir=state_dir)
    if kind != "unmarked_pending":
        assert rg.bind_pending_slot_pid(slot_id, 707070, state_dir=state_dir)
    if kind == "resident_marker":
        with rg._LockedState(state_dir) as slots:
            slots[0]["status"] = rg.SLOT_STATUS_RESIDENT
    def liveness(pid, sig):
        assert sig == 0  # never send a real signal in this fixture
        if kind == "dead_child":
            raise ProcessLookupError
        raise PermissionError
    monkeypatch.setattr(rg.os, "kill", liveness)
    probe = Mock(return_value=False)
    monkeypatch.setattr(lv, "probe_port_health", probe)
    if reap_site == "list":
        rg.list_slots(state_dir=state_dir)
    else:
        monkeypatch.setattr(rg, "can_admit", Mock(return_value=SimpleNamespace(admitted=False)))
        rg.reserve_slot(SimpleNamespace(), meminfo={}, read_temp_fn=lambda: 30, state_dir=state_dir)
    slots = rg.list_slots(state_dir=state_dir, reap_dead=False)
    assert bool(slots) is retained
    if retained:
        assert slots[0]["pid"] == 707070
        assert slots[0]["cost_bytes"] == 2048
        assert slots[0]["status"] == rg.SLOT_STATUS_PENDING
        assert rg.total_reserved_bytes(state_dir=state_dir) == 2048
        probe.assert_not_called()


def test_pending_binding_preserves_cost_and_residency_clears_marker(tmp_path):
    slot_id = rg.register_slot("fixture", 2048, pid=88888, state_dir=tmp_path)
    assert rg.bind_pending_slot_pid(slot_id, 707070, state_dir=tmp_path)
    assert rg.mark_resident(slot_id, state_dir=tmp_path, pid=707070)
    row = rg.list_slots(state_dir=tmp_path, reap_dead=False)[0]
    assert row["cost_bytes"] == 2048 and row["status"] == rg.SLOT_STATUS_RESIDENT
    assert "owned_pending_child" not in row
    assert not rg.bind_pending_slot_pid(slot_id, 707070, state_dir=tmp_path)
    assert not rg.bind_pending_slot_pid("missing", 707070, state_dir=tmp_path)


@pytest.mark.parametrize("pid", [True, False, 0, 1, -1, 2**31, 3.0])
def test_pending_binding_rejects_invalid_pid(tmp_path, pid):
    with pytest.raises(ValueError):
        rg.bind_pending_slot_pid("missing", pid, state_dir=tmp_path)


def test_async_release_error_does_not_arm_cooldown(loader_env, monkeypatch):
    from core import thermal

    env = loader_env
    assert env.loader.load_primary()
    env.child.terminate.side_effect = PermissionError
    with pytest.raises(lv.ModelTeardownError):
        env.loader.unload()
    monkeypatch.setattr(lv, "get_loader", lambda: env.loader)
    monkeypatch.setattr(thermal, "get_thermal_manager", lambda: SimpleNamespace(is_inference_active=lambda: False))
    server = object.__new__(daemon.DaemonServer)
    server._release_slot_last_release = {}
    result = asyncio.run(server._handle_release_model_slot({"model_id": "primary"}))
    assert result["status"] == "error" and result["released"] is False
    assert server._release_slot_last_release == {}
    assert env.loader.is_cleanup_pending()


def test_concrete_spawn_interruption_keeps_handle_before_publication(tmp_path, monkeypatch):
    from core import process_identity

    child = Child()
    server = lv.LlamaServer(tmp_path / "fake.gguf", port=29877)
    server._on_spawn = Mock(side_effect=KeyboardInterrupt)
    server.stop = Mock(return_value=False)  # synthetic PID teardown is guarded
    monkeypatch.setattr(lv, "CODEY_STATE_DIR", tmp_path)
    monkeypatch.setattr(lv.subprocess, "Popen", Mock(return_value=child))
    monkeypatch.setattr(lv.subprocess, "run", Mock(return_value=SimpleNamespace(stdout="fixture", stderr="")))
    publication = Mock()
    monkeypatch.setattr(process_identity, "LifecycleRecord", publication)
    with pytest.raises(KeyboardInterrupt):
        server._spawn_locked()
    assert server.process is child and server._cleanup_pending
    assert server._owned_session_pid == child.pid
    publication.assert_not_called()
    server.stop.assert_not_called()


@pytest.mark.parametrize("variant", ["primary", "secondary"])
@pytest.mark.parametrize("interruption_type", [KeyboardInterrupt, SystemExit])
def test_lora_teardown_interruption_restores_cfg_before_propagating(tmp_path, monkeypatch, variant, interruption_type):
    from core import lora_import

    original, planner = tmp_path / "base.gguf", tmp_path / "planner.gguf"
    replacement = tmp_path / "fine.gguf"
    replacement.write_bytes(b"candidate")
    monkeypatch.setattr(lora_import.cfg, "MODEL_PATH", original)
    monkeypatch.setattr(lora_import.cfg, "PLANNER_MODEL_PATH", planner)
    interruption = interruption_type("interrupted teardown")
    loader = SimpleNamespace(unload=Mock(side_effect=interruption), load_primary=Mock())
    monkeypatch.setattr(lv, "get_loader", lambda: loader)
    with pytest.raises(interruption_type) as raised:
        lora_import.swap_to_finetuned_model(str(replacement), variant)
    assert raised.value is interruption
    assert lora_import.cfg.MODEL_PATH == original
    assert lora_import.cfg.PLANNER_MODEL_PATH == planner
    loader.load_primary.assert_not_called()
