"""Mock-only owned embedding lifecycle: no model, process, port or live store."""
import builtins
import io
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock

import pytest

from core import embed_server as es


class Child:
    pid = 987654

    def __init__(self, waits=(), exited=False):
        self.returncode = 0 if exited else None
        self.waits = list(waits)
        self.events = []
        self.terminate_error = None
        self.kill_error = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.events.append("TERM")
        if self.terminate_error:
            raise self.terminate_error

    def kill(self):
        self.events.append("KILL")
        if self.kill_error:
            raise self.kill_error

    def wait(self, timeout):
        self.events.append("wait")
        if self.waits:
            outcome = self.waits.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
        self.returncode = 0
        return 0


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(es, "CODEY_STATE_DIR", tmp_path / "state")
    def forbidden(*args, **kwargs):
        raise AssertionError("unmocked external lifecycle effect")
    for name in ("kill", "killpg", "getpgid"):
        monkeypatch.setattr(es.os, name, forbidden)
    monkeypatch.setattr(es.subprocess, "Popen", forbidden)
    monkeypatch.setattr(es.urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(es.EmbedServer, "_check_health", Mock(return_value=False))
    monkeypatch.setattr(es.EmbedServer, "_port_is_bound", Mock(return_value=False))
    monkeypatch.setattr(es.EmbedServer, "_find_port_occupant_pid", forbidden)
    monkeypatch.setattr(es.EmbedServer, "_kill_port_occupant", forbidden)
    monkeypatch.setattr(es.rg, "register_slot", Mock(return_value="own-slot"))
    monkeypatch.setattr(es.rg, "release_slot", Mock(return_value=True))
    monkeypatch.setattr(es.rg, "find_resident_slot", Mock(return_value=None))
    for name in ("reserve_slot", "can_admit", "list_slots"):
        monkeypatch.setattr(es.rg, name, forbidden)
    monkeypatch.setattr(es.time, "sleep", lambda seconds: None)
    for name in ("info", "warning", "success", "error"):
        monkeypatch.setattr(es, name, Mock())
    monkeypatch.setattr(es, "_embed_server", None)
    model = tmp_path / "fake-model"
    model.write_bytes(b"fixture")
    binary = tmp_path / "fake-binary"
    binary.touch()
    monkeypatch.setattr(es, "LLAMA_SERVER_BIN", str(binary))
    obj = es.EmbedServer()
    obj.model_path = model
    yield obj
    # Every Child is a Python fake. No numeric PID reaches OS dependencies.


def own(server, child):
    server.process = child
    server._slot_id = "owned-slot"
    server._started = True
    return child


@pytest.mark.parametrize("force", [False, True])
def test_term_or_kill_confirms_final_reap_before_slot_release(server, force):
    child = own(server, Child([subprocess.TimeoutExpired("fake", 5)] if force else []))
    es.rg.release_slot.side_effect = lambda slot: child.events.append("release")
    assert server.stop() is None
    assert child.events == (["TERM", "wait", "KILL", "wait", "release"] if force else ["TERM", "wait", "release"])
    assert server.process is None
    assert server._slot_id is None
    assert not server.cleanup_pending


@pytest.mark.parametrize("failure", ["term", "kill", "wait", "final-wait", "poll"])
def test_uncertainty_retains_handle_slot_and_singleton_then_retry(server, monkeypatch, failure):
    timeout = subprocess.TimeoutExpired("fixture", 5)
    child = own(server, Child([timeout] if failure in ("kill", "final-wait") else []))
    if failure == "term":
        child.terminate_error = PermissionError("fake")
    elif failure == "kill":
        child.kill_error = PermissionError("fake")
    elif failure == "wait":
        child.waits = [PermissionError("fake")]
    elif failure == "final-wait":
        child.waits.append(timeout)
    else:
        monkeypatch.setattr(child, "poll", Mock(side_effect=PermissionError("fake")))
    monkeypatch.setattr(es, "_embed_server", server)
    with pytest.raises(es.EmbedTeardownError):
        es.stop_embed_server()
    assert es.get_embed_server() is server
    assert server.process is child
    assert server._slot_id == "owned-slot"
    assert server.cleanup_pending
    es.rg.release_slot.assert_not_called()
    assert not any(call.args == ("Embed server stopped",) for call in es.info.call_args_list)
    child.terminate_error = child.kill_error = None
    child.waits.clear()
    if failure == "poll":
        monkeypatch.setattr(child, "poll", lambda: child.returncode)
    es.stop_embed_server()
    assert es._embed_server is None
    assert child.returncode == 0


def test_stop_interrupt_retains_ownership(server):
    child = own(server, Child([KeyboardInterrupt()]))
    with pytest.raises(KeyboardInterrupt):
        server.stop()
    assert server.process is child
    assert server.cleanup_pending
    es.rg.release_slot.assert_not_called()


def test_owned_group_only_while_live_child_anchors_original_session(server, monkeypatch):
    child = own(server, Child())
    server._owned_session_pid = child.pid
    group = Mock(return_value=child.pid)
    signal = Mock()
    monkeypatch.setattr(es.os, "getpgid", group)
    monkeypatch.setattr(es.os, "killpg", signal)
    server.stop()
    signal.assert_called_once_with(child.pid, es.signal.SIGTERM)
    assert child.events == ["wait"]


def test_changed_group_uses_only_retained_child_handle(server, monkeypatch):
    child = own(server, Child())
    server._owned_session_pid = child.pid
    monkeypatch.setattr(es.os, "getpgid", Mock(return_value=123))
    server.stop()
    assert child.events == ["TERM", "wait"]


def test_dead_handle_reaped_and_slot_released_before_healthy_adoption(server):
    child = own(server, Child(exited=True))
    es.EmbedServer._port_is_bound.return_value = True
    es.EmbedServer._check_health.return_value = True
    es.rg.find_resident_slot.return_value = {"slot_id": "borrowed"}
    assert server.start() is True
    assert child.events == ["wait"]
    assert server.process is None
    es.rg.release_slot.assert_called_once_with("owned-slot")
    assert server._slot_id is None


def test_unhealthy_owned_cleanup_failure_refuses_spawn_adoption_or_foreign_killer(server):
    child = own(server, Child())
    child.terminate_error = PermissionError("fake")
    assert server.start() is False
    assert server.process is child
    assert server.cleanup_pending
    es.EmbedServer._port_is_bound.assert_not_called()


def launch(server, monkeypatch, child, healthy=True):
    def spawn(*args, **kwargs):
        child.log_stream = kwargs["stdout"]
        return child
    popen = Mock(side_effect=spawn)
    monkeypatch.setattr(es.subprocess, "Popen", popen)
    # Fake child left its initial group; only its mocked handle methods run.
    monkeypatch.setattr(es.os, "getpgid", Mock(return_value=child.pid + 1))
    es.EmbedServer._check_health.return_value = healthy
    return popen


@pytest.mark.parametrize("mode", ["early-exit", "timeout", "health-exception", "interrupt", "postspawn-log"])
def test_failed_start_closes_log_and_cleans_actual_handle(server, monkeypatch, mode):
    child = Child(exited=mode == "early-exit")
    launch(server, monkeypatch, child, healthy=False)
    if mode == "health-exception":
        es.EmbedServer._check_health.side_effect = RuntimeError("fake")
    elif mode == "interrupt":
        es.EmbedServer._check_health.side_effect = KeyboardInterrupt()
    elif mode == "postspawn-log":
        es.info.side_effect = lambda text: (_ for _ in ()).throw(RuntimeError("fake")) if "PID:" in text else None
    if mode == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            server.start()
    else:
        assert server.start() is False
    assert child.log_stream.closed
    assert child.returncode == 0
    assert server.process is None


def test_failed_start_retains_cleanup_and_never_overwrites(server, monkeypatch):
    child = Child()
    child.terminate_error = PermissionError("fake")
    popen = launch(server, monkeypatch, child, healthy=False)
    assert server.start() is False
    assert child.log_stream.closed
    assert server.process is child
    assert server.cleanup_pending
    assert server.start() is False
    popen.assert_called_once()


def test_registration_failure_is_nonfatal_and_never_admits(server, monkeypatch):
    child = Child()
    launch(server, monkeypatch, child)
    es.rg.register_slot.side_effect = OSError("fake store failure")
    assert server.start() is True
    assert server.process is child
    assert not server.cleanup_pending
    assert server._slot_id is None
    assert child.log_stream.closed


def test_slot_release_error_retains_id_after_reap_then_retry_absent(server):
    child = own(server, Child())
    es.rg.release_slot.side_effect = OSError("fake")
    with pytest.raises(es.EmbedTeardownError, match="slot release"):
        server.stop()
    assert child.returncode == 0
    assert server.process is None
    assert server._slot_id == "owned-slot"
    assert server.cleanup_pending
    es.rg.release_slot.side_effect = None
    es.rg.release_slot.return_value = False
    server.stop()
    assert server._slot_id is None
    assert not server.cleanup_pending


@pytest.mark.parametrize("borrowed", [False, True])
def test_adoption_detaches_only_self_registered_observation(server, monkeypatch, borrowed):
    es.EmbedServer._port_is_bound.return_value = True
    es.EmbedServer._check_health.return_value = True
    es.rg.find_resident_slot.return_value = {"slot_id": "foreign-slot"} if borrowed else None
    monkeypatch.setattr(server, "_find_port_occupant_pid", Mock(return_value=123456))
    assert server.start() is True
    assert server.process is None
    server.stop()
    if borrowed:
        es.rg.release_slot.assert_not_called()
        es.rg.register_slot.assert_not_called()
    else:
        es.rg.release_slot.assert_called_once_with("own-slot")


def test_parent_log_closed_when_popen_raises(server, monkeypatch):
    captured = []
    def failing(*args, **kwargs):
        captured.append(kwargs["stdout"])
        raise OSError("fake spawn")
    monkeypatch.setattr(es.subprocess, "Popen", failing)
    assert server.start() is False
    assert captured[0].closed
    assert server.process is None


def test_log_write_failure_closes_without_spawn(server, monkeypatch):
    class BadLog(io.StringIO):
        def write(self, value):
            raise OSError("fake log")
    stream = BadLog()
    original_open = builtins.open
    monkeypatch.setattr(builtins, "open", lambda path, *a, **kw: stream if str(path).endswith("embed-server.log") else original_open(path, *a, **kw))
    assert server.start() is False
    assert stream.closed


def test_singleton_creation_and_stop_are_serialized(server, monkeypatch):
    created = Mock(return_value=server)
    monkeypatch.setattr(es, "EmbedServer", created)
    with ThreadPoolExecutor(4) as executor:
        instances = list(executor.map(lambda _: es.get_embed_server(), range(8)))
    assert all(instance is server for instance in instances)
    created.assert_called_once()


def test_instance_start_waits_for_stop_before_considering_replacement(server, monkeypatch):
    entered, release = Event(), Event()
    child = own(server, Child())
    original_wait = child.wait
    def wait(timeout):
        entered.set()
        assert release.wait(3)
        return original_wait(timeout)
    monkeypatch.setattr(child, "wait", wait)
    es.EmbedServer._port_is_bound.return_value = True
    es.EmbedServer._check_health.return_value = True
    es.rg.find_resident_slot.return_value = {"slot_id": "foreign"}
    with ThreadPoolExecutor(2) as executor:
        stopping = executor.submit(server.stop)
        assert entered.wait(3)
        starting = executor.submit(server.start)
        try:
            assert not starting.done()
        finally:
            release.set()
        stopping.result(3)
        assert starting.result(3) is True
    assert child.events == ["TERM", "wait"]


@pytest.mark.parametrize("failure", ["lookup", "group-signal"])
def test_group_lookup_or_signal_failure_retains_owned_cleanup(server, monkeypatch, failure):
    child = own(server, Child())
    server._owned_session_pid = child.pid
    monkeypatch.setattr(es.os, "getpgid", Mock(side_effect=PermissionError("fake")) if failure == "lookup" else Mock(return_value=child.pid))
    monkeypatch.setattr(es.os, "killpg", Mock(side_effect=PermissionError("fake")))
    with pytest.raises(es.EmbedTeardownError):
        server.stop()
    assert server.process is child
    assert server._slot_id == "owned-slot"
    assert server.cleanup_pending
    es.rg.release_slot.assert_not_called()


def test_postspawn_log_close_exception_still_cleans_owned_child(server, monkeypatch):
    class BadClose(io.StringIO):
        def close(self):
            super().close()
            raise OSError("fake close")
    stream = BadClose()
    original_open = builtins.open
    monkeypatch.setattr(builtins, "open", lambda path, *a, **kw: stream if str(path).endswith("embed-server.log") else original_open(path, *a, **kw))
    child = Child()
    launch(server, monkeypatch, child)
    assert server.start() is False
    assert stream.closed
    assert child.returncode == 0
    assert server.process is None


def test_success_log_exception_does_not_abort_healthy_owned_child(server, monkeypatch):
    child = Child()
    launch(server, monkeypatch, child)
    es.success.side_effect = RuntimeError("fake logging failure")
    assert server.start() is True
    assert child.returncode is None
    assert server.process is child
    assert server._slot_id == "own-slot"
    assert server.cleanup_pending is False


def test_global_start_waits_for_global_stop_before_new_singleton(server, monkeypatch):
    child = own(server, Child())
    monkeypatch.setattr(es, "_embed_server", server)
    entered, release = Event(), Event()
    wait = child.wait

    def paused_wait(timeout):
        entered.set()
        assert release.wait(3)
        return wait(timeout)

    monkeypatch.setattr(child, "wait", paused_wait)
    next_server = Mock()
    next_server.start.return_value = True
    factory = Mock(return_value=next_server)
    monkeypatch.setattr(es, "EmbedServer", factory)
    with ThreadPoolExecutor(2) as executor:
        stopping = executor.submit(es.stop_embed_server)
        assert entered.wait(3)
        starting = executor.submit(es.start_embed_server)
        try:
            factory.assert_not_called()
            assert not starting.done()
        finally:
            release.set()
        stopping.result(3)
        assert starting.result(3) is True
    factory.assert_called_once()
    assert es._embed_server is next_server
    assert child.returncode == 0


def primary_ready(monkeypatch):
    from core import loader_v2

    loader = Mock()
    loader.ensure_model.return_value = True
    monkeypatch.setattr(loader_v2, "get_loader", lambda: loader)
    return loader


@pytest.mark.parametrize("healthy", [False, True])
def test_inference_preserves_foreign_health_only_contract(server, monkeypatch, healthy):
    from core import inference

    primary_ready(monkeypatch)
    monkeypatch.setattr(es, "get_embed_server", lambda: server)
    es.EmbedServer._check_health.return_value = healthy
    start = Mock(return_value=False)
    monkeypatch.setattr(server, "start", start)
    assert server.cleanup_pending is False
    assert inference._start_server() is None
    assert start.call_count == (0 if healthy else 1)


def test_inference_healthy_but_pending_child_retries_cleanup_without_replacement(server, monkeypatch):
    from core import inference

    primary_ready(monkeypatch)
    child = own(server, Child())
    child.terminate_error = PermissionError("fake cleanup refusal")
    server._cleanup_pending = True
    es.EmbedServer._check_health.return_value = True
    monkeypatch.setattr(es, "get_embed_server", lambda: server)
    assert server.cleanup_pending is True
    assert inference._start_server() is None
    assert child.events == ["TERM"]
    assert server.process is child
    assert server.cleanup_pending is True
    assert server._slot_id == "owned-slot"
    es.rg.release_slot.assert_not_called()
    es.EmbedServer._port_is_bound.assert_not_called()


def test_inference_optional_embed_cleanup_error_preserves_fallback(server, monkeypatch):
    from core import inference

    primary_ready(monkeypatch)
    server._cleanup_pending = True
    monkeypatch.setattr(es, "get_embed_server", lambda: server)
    monkeypatch.setattr(server, "start", Mock(side_effect=es.EmbedTeardownError("fake")))
    assert inference._start_server() is None
    assert server.cleanup_pending is True


def test_inference_embed_interrupt_is_not_swallowed(server, monkeypatch):
    from core import inference

    primary_ready(monkeypatch)
    server._cleanup_pending = True
    monkeypatch.setattr(es, "get_embed_server", lambda: server)
    monkeypatch.setattr(server, "start", Mock(side_effect=KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        inference._start_server()


def closed_rich_diagnostics(monkeypatch):
    from rich.console import Console

    from utils import logger

    stream = io.StringIO()
    console = Console(file=stream, force_terminal=False)
    stream.close()
    monkeypatch.setattr(logger, "console", console)
    monkeypatch.setattr(logger, "_file_logger", None)
    monkeypatch.setattr(logger, "_current_log_level", 0)
    for name in ("info", "warning", "success", "error"):
        monkeypatch.setattr(es, name, getattr(logger, name))
    # Establish that this is a genuinely broken Rich sink, not a no-op mock.
    with pytest.raises(ValueError, match="closed"):
        logger.info("closed sink control")


def test_closed_rich_console_cannot_turn_confirmed_stop_into_failure(server, monkeypatch):
    closed_rich_diagnostics(monkeypatch)
    child = own(server, Child())
    monkeypatch.setattr(es, "_embed_server", server)
    assert es.stop_embed_server() is None
    assert child.returncode == 0
    assert server.process is None
    assert server._slot_id is None
    assert server.cleanup_pending is False
    assert es._embed_server is None


def test_closed_rich_console_preserves_original_start_interrupt_after_reap(server, monkeypatch):
    closed_rich_diagnostics(monkeypatch)
    child = Child()
    launch(server, monkeypatch, child, healthy=False)
    original = KeyboardInterrupt("original startup interrupt")
    es.EmbedServer._check_health.side_effect = original
    with pytest.raises(KeyboardInterrupt) as caught:
        server.start()
    assert caught.value is original
    assert child.returncode == 0
    assert server.process is None
    assert server.cleanup_pending is False
    assert child.log_stream.closed


def test_closed_rich_console_preserves_ordinary_failed_start_result(server, monkeypatch):
    closed_rich_diagnostics(monkeypatch)
    child = Child()
    launch(server, monkeypatch, child, healthy=False)
    es.EmbedServer._check_health.side_effect = RuntimeError("original startup failure")
    assert server.start() is False
    assert child.returncode == 0
    assert server.process is None
    assert server.cleanup_pending is False
    assert child.log_stream.closed


def test_closed_rich_console_cannot_abort_healthy_start(server, monkeypatch):
    closed_rich_diagnostics(monkeypatch)
    child = Child()
    launch(server, monkeypatch, child)
    assert server.start() is True
    assert server.process is child
    assert server._slot_id == "own-slot"
    assert server.cleanup_pending is False


def test_original_start_interrupt_survives_second_cleanup_interrupt(server, monkeypatch):
    child = Child(waits=[SystemExit("secondary cleanup interruption")])
    launch(server, monkeypatch, child, healthy=False)
    original = KeyboardInterrupt("original startup interruption")
    es.EmbedServer._check_health.side_effect = original
    with pytest.raises(KeyboardInterrupt) as caught:
        server.start()
    assert caught.value is original
    assert server.process is child
    assert server.cleanup_pending is True
    assert child.log_stream.closed


@pytest.fixture
def daemon_harness(server, monkeypatch, tmp_path):
    import _socket
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from utils import config

    # Import-time fixed state bootstrap is redirected; no StateStore is built.
    monkeypatch.setattr(config, "CODEY_STATE_DIR", tmp_path / "daemon-state")
    monkeypatch.setattr(config, "STATE_DB_FILE", tmp_path / "daemon-state" / "state.db")
    from core import daemon as daemon_module

    # Asyncio creates only its private wakeup socketpair. Existing socket FDs
    # may be wrapped; creating any test network/listening socket stays forbidden.
    socket_type = _socket.socket

    def wakeup_socket_only(family=-1, type=-1, proto=-1, fileno=None):
        if family == socket.AF_UNIX and fileno is not None:
            # _socket.socket is sufficient for the event loop's wakeup pair.
            return socket_type(family, type, proto, fileno=fileno)
        raise AssertionError("daemon fixture attempted a network socket")

    monkeypatch.setattr(socket, "socket", wakeup_socket_only)
    daemon = daemon_module.Daemon.__new__(daemon_module.Daemon)
    daemon.state = Mock()
    daemon.server = Mock()
    daemon.server.server = None
    daemon.server.start = AsyncMock()
    daemon.server.stop = AsyncMock()
    daemon.background = Mock()
    daemon.file_watch = Mock()
    daemon.running = False
    daemon._reload_requested = False
    daemon._process_planner_tasks = AsyncMock()
    daemon._emit_gate_telemetry_deduped = Mock()
    daemon._record_daemon_telemetry_device_sample = Mock()
    daemon._observe_interactive_state = Mock()
    daemon._watchdog_check_model = Mock(side_effect=lambda: setattr(daemon, "running", False))
    for name in ("_record_daemon_telemetry_run_start", "_record_daemon_telemetry_writer_stopped", "remove_pid_file"):
        monkeypatch.setattr(daemon_module, name, Mock())
    monkeypatch.setattr(daemon_module, "info", Mock())
    monkeypatch.setattr(daemon_module, "warning", Mock())
    monkeypatch.setattr(config, "is_remote_backend", lambda: False)
    monkeypatch.setattr(es.rg, "sample_cpu_percent", Mock(return_value=None))
    monkeypatch.setattr(es.rg, "sample_temperature_c", Mock(return_value=None))
    monkeypatch.setattr(es.rg, "is_interactive_session_active", Mock(return_value=False))
    monkeypatch.setattr(es.rg, "should_trip_shutdown", Mock(return_value=SimpleNamespace(should_trip=False, reason="fixture")))
    primary_ready(monkeypatch)
    startup = Mock(return_value=True)
    actual_stop = es.stop_embed_server
    shutdown = Mock()
    monkeypatch.setattr(es, "start_embed_server", startup)
    monkeypatch.setattr(es, "stop_embed_server", shutdown)
    monkeypatch.setattr(es, "get_embed_server", lambda: server)
    monkeypatch.setattr(server, "is_running", Mock(return_value=True))
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    return SimpleNamespace(daemon=daemon, module=daemon_module, startup=startup, shutdown=shutdown, actual_stop=actual_stop)


def run_daemon(harness):
    import asyncio

    asyncio.run(harness.daemon._main_loop())


@pytest.mark.parametrize("pending", [False, True])
def test_daemon_startup_reports_actual_unavailable_or_pending(server, daemon_harness, pending):
    harness = daemon_harness
    server._cleanup_pending = pending
    harness.startup.return_value = False
    run_daemon(harness)
    warnings = " ".join(call.args[0] for call in harness.module.warning.call_args_list)
    infos = " ".join(call.args[0] for call in harness.module.info.call_args_list)
    assert ("startup cleanup pending" in warnings) is pending
    assert ("server unavailable" in warnings) is not pending
    assert "Embed server ready" not in infos


@pytest.mark.parametrize("recovered", [False, True])
def test_daemon_watchdog_retries_live_pending_child_and_reports_result(server, daemon_harness, recovered):
    harness = daemon_harness
    harness.daemon.running = True
    calls = []

    def start():
        calls.append(1)
        if len(calls) == 1:
            return True
        server._cleanup_pending = not recovered
        return recovered

    def watchdog_tick():
        server._cleanup_pending = True
        harness.daemon.running = False

    harness.startup.side_effect = start
    harness.daemon._watchdog_check_model.side_effect = watchdog_tick
    run_daemon(harness)
    assert len(calls) == 2
    server.is_running.assert_not_called()
    warnings = " ".join(call.args[0] for call in harness.module.warning.call_args_list)
    infos = " ".join(call.args[0] for call in harness.module.info.call_args_list)
    assert ("watchdog cleanup pending" in warnings) is not recovered
    assert ("ready after watchdog recovery" in infos) is recovered


def test_daemon_watchdog_failed_recovery_never_claims_restart(server, daemon_harness):
    harness = daemon_harness
    harness.daemon.running = True
    harness.startup.side_effect = [True, False]
    server.is_running.return_value = False
    run_daemon(harness)
    warnings = " ".join(call.args[0] for call in harness.module.warning.call_args_list)
    infos = " ".join(call.args[0] for call in harness.module.info.call_args_list)
    assert "watchdog recovery unavailable" in warnings
    assert "ready after watchdog recovery" not in infos
    assert harness.startup.call_count == 2


def test_daemon_shutdown_runs_owned_stop_in_executor_and_releases_after_reap(server, daemon_harness, monkeypatch):
    from threading import get_ident

    harness = daemon_harness
    child = own(server, Child())
    monkeypatch.setattr(es, "_embed_server", server)
    main_thread = get_ident()
    waited_from = []
    wait = child.wait

    def observed_wait(timeout):
        waited_from.append(get_ident())
        return wait(timeout)

    monkeypatch.setattr(child, "wait", observed_wait)
    monkeypatch.setattr(es, "stop_embed_server", harness.actual_stop)
    run_daemon(harness)
    assert waited_from and all(identity != main_thread for identity in waited_from)
    assert child.returncode == 0
    assert es._embed_server is None
    harness.daemon.server.stop.assert_awaited_once()


def test_daemon_shutdown_failure_logs_and_retains_owned_singleton(server, daemon_harness, monkeypatch):
    harness = daemon_harness
    child = own(server, Child())
    child.terminate_error = PermissionError("fake teardown refusal")
    monkeypatch.setattr(es, "_embed_server", server)
    monkeypatch.setattr(es, "stop_embed_server", harness.actual_stop)
    run_daemon(harness)
    assert es._embed_server is server
    assert server.process is child
    assert server._slot_id == "owned-slot"
    assert server.cleanup_pending is True
    warnings = " ".join(call.args[0] for call in harness.module.warning.call_args_list)
    assert "Owned embed cleanup during shutdown failed" in warnings
    assert "not durable after daemon exit" in warnings
    harness.daemon.server.stop.assert_awaited_once()


def test_daemon_closed_warning_sink_cannot_abort_remaining_shutdown(server, daemon_harness, monkeypatch):
    from utils import logger

    harness = daemon_harness
    closed_rich_diagnostics(monkeypatch)
    monkeypatch.setattr(harness.module, "warning", logger.warning)
    child = own(server, Child())
    child.terminate_error = PermissionError("fake")
    monkeypatch.setattr(es, "_embed_server", server)
    monkeypatch.setattr(es, "stop_embed_server", harness.actual_stop)
    run_daemon(harness)
    assert es._embed_server is server
    assert server.process is child
    assert server.cleanup_pending is True
    harness.daemon.server.stop.assert_awaited_once()
    harness.module.remove_pid_file.assert_called_once()


def test_primary_unload_failure_with_closed_sink_still_reaps_embed_and_finishes_cleanup(server, daemon_harness, monkeypatch):
    from threading import get_ident

    from core.loader_v2 import get_loader
    from utils import logger

    harness = daemon_harness
    closed_rich_diagnostics(monkeypatch)
    monkeypatch.setattr(harness.module, "warning", logger.warning)
    loader = get_loader()
    loader.unload.side_effect = RuntimeError("injected primary unload failure")
    child = own(server, Child())
    monkeypatch.setattr(es, "_embed_server", server)
    monkeypatch.setattr(es, "stop_embed_server", harness.actual_stop)
    main_thread = get_ident()
    waited_from = []
    wait = child.wait

    def observed_wait(timeout):
        waited_from.append(get_ident())
        return wait(timeout)

    monkeypatch.setattr(child, "wait", observed_wait)
    run_daemon(harness)
    loader.unload.assert_called_once()
    assert waited_from and all(identity != main_thread for identity in waited_from)
    assert child.returncode == 0
    assert server.process is None
    assert server._slot_id is None
    assert server.cleanup_pending is False
    assert es._embed_server is None
    es.rg.release_slot.assert_called_once_with("owned-slot")
    harness.daemon.server.stop.assert_awaited_once()
    harness.module.remove_pid_file.assert_called_once()


def test_inference_stop_between_health_snapshot_and_start_uses_current_singleton(server, monkeypatch):
    from core import inference

    primary_ready(monkeypatch)
    child = own(server, Child())
    monkeypatch.setattr(es, "_embed_server", server)
    current = es.EmbedServer()
    current.start = Mock(return_value=True)
    factory = Mock(return_value=current)
    monkeypatch.setattr(es, "EmbedServer", factory)
    stale_start = Mock(side_effect=AssertionError("stale singleton must not restart"))
    monkeypatch.setattr(server, "start", stale_start)

    def health_snapshot_then_stop():
        es.stop_embed_server()
        assert es._embed_server is None
        return False

    monkeypatch.setattr(server, "is_healthy", health_snapshot_then_stop)
    assert inference._start_server() is None
    assert child.returncode == 0
    stale_start.assert_not_called()
    factory.assert_called_once()
    current.start.assert_called_once_with()
    assert es._embed_server is current
