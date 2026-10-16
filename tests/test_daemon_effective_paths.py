"""WP2.1 13c.2a: configured daemon paths and verified read-only clients.

All paths/stores/sockets are disposable; no model or daemon service starts.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import daemon, daemon_config, observability, process_identity


@pytest.fixture
def configured(tmp_path, monkeypatch):
    root = tmp_path / "custom paths"
    config_file = tmp_path / "state" / "config.json"
    config_file.parent.mkdir()
    config_file.write_text(json.dumps({"daemon": {
        "pid_file": str(root / "p"), "socket_file": str(root / "s"), "log_file": str(root / "l"),
    }}))
    config = daemon_config.DaemonConfig(config_file)
    paths = daemon_config.resolve_daemon_paths(config)
    monkeypatch.setattr(daemon_config, "_config", config)
    monkeypatch.setattr(daemon, "_PID_PUBLICATION", None)
    return SimpleNamespace(root=root, config_file=config_file, config=config, paths=paths)


def test_absolute_paths_share_existing_config_parser_without_writes(configured):
    env = configured
    assert env.paths.pid_file == env.root / "p"
    assert env.paths.socket_file == env.root / "s"
    assert env.paths.log_file == env.root / "l"
    assert not env.root.exists()


def test_missing_config_keeps_default_paths_without_mkdir(tmp_path):
    path = tmp_path / "absent" / "config.json"
    config = daemon_config.DaemonConfig(path)
    paths = daemon_config.resolve_daemon_paths(config)
    assert paths == daemon_config.DaemonPaths(
        daemon_config.DAEMON_PID_FILE, daemon_config.DAEMON_SOCKET_FILE, daemon_config.DAEMON_LOG_FILE,
    )
    assert not path.parent.exists()


def test_corrupt_config_preserves_existing_default_fallback(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{")
    assert daemon_config.resolve_daemon_paths(daemon_config.DaemonConfig(path)) == daemon_config.resolve_daemon_paths(
        daemon_config.DaemonConfig(tmp_path / "missing.json")
    )


@pytest.mark.parametrize("method", ["save", "create_default_config"])
def test_config_write_boundary_creates_parent(tmp_path, method):
    path = tmp_path / "missing" / "config.json"
    config = daemon_config.DaemonConfig(path)
    assert not path.parent.exists()
    getattr(config, method)()
    assert json.loads(path.read_text())["daemon"]


def test_import_and_read_inspection_leave_missing_root_absent(tmp_path):
    root = tmp_path / "absent state"
    env = dict(os.environ, CODEY_STATE_DIR=str(root))
    result = subprocess.run([sys.executable, "-c", "from core.daemon_config import resolve_daemon_paths; resolve_daemon_paths()"], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert not root.exists()
    result = subprocess.run([sys.executable, "core/process_identity.py", "inspect", str(root / "daemon.pid"), "codeyOS"], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 1 and result.stdout.strip() == process_identity.DEAD
    assert not root.exists()


def test_main_snapshots_config_paths_before_duplicate_check(configured, monkeypatch):
    events = []
    def check(paths):
        assert paths == configured.paths
        events.append("check")
        return False
    def construct(*, config, paths):
        assert config is configured.config and paths == configured.paths
        events.append("construct")
        return SimpleNamespace(run=lambda: events.append("run"))
    monkeypatch.setattr(daemon, "check_pid_file", check)
    monkeypatch.setattr(daemon, "Daemon", construct)
    daemon.main()
    assert events == ["check", "construct", "run"]


def test_main_blocks_duplicate_before_constructing_daemon(configured, monkeypatch):
    monkeypatch.setattr(daemon, "check_pid_file", lambda paths: paths == configured.paths)
    construct = Mock()
    report = Mock()
    monkeypatch.setattr(daemon, "error", report)
    monkeypatch.setattr(daemon, "Daemon", construct)
    with pytest.raises(SystemExit) as raised:
        daemon.main()
    assert raised.value.code == 1
    construct.assert_not_called()
    assert "running daemon or unsafe/unverifiable process record" in report.call_args.args[0]


def test_self_publication_and_observability_share_custom_pid_and_mtime(configured):
    env = configured
    assert not daemon.check_pid_file()
    daemon.write_pid_file()
    assert env.paths.pid_file.exists()
    assert not daemon.check_pid_file()
    state = observability.State(daemon_paths=env.paths)
    assert state.daemon_pid == os.getpid()
    original = state.state_store.get("daemon_started_at", 0)
    try:
        state.state_store.set("daemon_started_at", 1)
        assert state.uptime == 0
    finally:
        state.state_store.set("daemon_started_at", original)
        assert daemon.remove_pid_file()


@pytest.mark.parametrize("record_kind", ["missing", "legacy_live", "wrong_identity", "symlink"])
def test_unverified_records_never_connect(configured, monkeypatch, record_kind):
    env = configured
    if record_kind != "missing":
        daemon.write_pid_file()
        if record_kind == "legacy_live":
            Path(str(env.paths.pid_file) + ".identity").unlink()
        elif record_kind == "wrong_identity":
            sidecar = Path(str(env.paths.pid_file) + ".identity")
            contents = json.loads(sidecar.read_text())
            contents["uid"] += 1
            sidecar.write_text(json.dumps(contents))
        else:
            original = env.root / "actual"
            env.paths.pid_file.rename(original)
            env.paths.pid_file.symlink_to(original)
    connect = Mock()
    monkeypatch.setattr(daemon.socket, "socket", connect)
    assert daemon.is_daemon_running() is False
    with pytest.raises(ConnectionError, match="identity"):
        daemon.send_command("ping")
    connect.assert_not_called()
    assert observability.State(daemon_paths=env.paths).daemon_pid is None


def test_fresh_process_send_command_uses_custom_socket(configured):
    env = configured
    daemon.write_pid_file()
    # AF_UNIX path limits can be tight under Termux's long pytest root.
    short_socket = env.config_file.parent / "s"
    env.config.set("daemon", "socket_file", value=str(short_socket))
    env.config.save()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(short_socket))
        server.listen(1)
        server.settimeout(5)
        received = []
        def serve():
            conn, _ = server.accept()
            with conn:
                received.append(json.loads(conn.recv(4096)))
                conn.sendall(b'{"status":"ok","message":"fixture"}')
        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        child_env = dict(os.environ, CODEY_STATE_DIR=str(env.config_file.parent))
        result = subprocess.run([sys.executable, "-c", "from core.daemon import send_command; print(send_command('ping')['message'])"], env=child_env, capture_output=True, text=True, timeout=10, check=False)
        worker.join(timeout=5)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "fixture"
        assert received == [{"cmd": "ping", "data": {}}]
    finally:
        server.close()
        short_socket.unlink(missing_ok=True)
        assert daemon.remove_pid_file()


def test_server_snapshots_explicit_socket_path(configured, monkeypatch):
    server = daemon.DaemonServer(Mock(), paths=configured.paths)
    configured.paths.socket_file.parent.mkdir()
    configured.paths.socket_file.write_text("stale fixture")
    asyncio.run(server.stop())
    assert not configured.paths.socket_file.exists()


def test_read_inspection_reports_inaccessible_as_unsafe(tmp_path, monkeypatch):
    monkeypatch.setattr(process_identity.os, "open", Mock(side_effect=PermissionError))
    assert process_identity.inspect_record(tmp_path / "p", "codeyOS").state == process_identity.UNSAFE


def test_read_inspection_does_not_delete_dead_legacy_record(tmp_path, monkeypatch):
    path = tmp_path / "p"
    path.write_text("707070")
    monkeypatch.setattr(process_identity, "process_info", lambda *a, **k: None)
    assert process_identity.inspect_record(path, "codeyOS").state == process_identity.UNSAFE
    assert path.read_text() == "707070"


def test_full_observability_status_resolves_daemon_paths_once(configured, monkeypatch):
    daemon.write_pid_file()
    resolve = Mock(return_value=configured.paths)
    monkeypatch.setattr(observability, "resolve_daemon_paths", resolve)
    state = observability.State()
    status = state.get_full_status()
    resolve.assert_called_once_with()
    assert status["daemon"]["pid"] == os.getpid()
    assert status["daemon"]["uptime_seconds"] == status["health"]["uptime_seconds"]
    assert daemon.remove_pid_file()


@pytest.mark.parametrize("kind,expected", [("absent", False), ("self", True), ("legacy", None), ("malformed", None), ("mismatch", None)])
def test_public_pid_status_is_pure_read_and_distinguishes_unknown(configured, monkeypatch, kind, expected):
    from ccos.plugins.system.daemon_control import daemon_control as plugin

    env = configured
    monkeypatch.setattr(plugin, "resolve_daemon_paths", lambda: env.paths)
    if kind != "absent":
        daemon.write_pid_file()
        sidecar = Path(str(env.paths.pid_file) + ".identity")
        if kind == "legacy":
            sidecar.unlink()
        elif kind == "malformed":
            env.paths.pid_file.write_text("-1")
        elif kind == "mismatch":
            value = json.loads(sidecar.read_text())
            value["uid"] += 1
            sidecar.write_text(json.dumps(value))
        Path(str(env.paths.pid_file) + ".lifecycle.lock").unlink()
    snapshots = {path.name: path.read_bytes() for path in env.root.iterdir()} if env.root.exists() else {}
    forbidden = Mock(side_effect=AssertionError("READ inspection attempted mutation or signal"))
    monkeypatch.setattr(Path, "mkdir", forbidden)
    monkeypatch.setattr(process_identity.os, "kill", forbidden)
    monkeypatch.setattr(process_identity.fcntl, "flock", forbidden)
    result = plugin.daemon_check_pid_file()
    assert result["running"] is expected
    assert result["state"] == (process_identity.UNSAFE if expected is None else process_identity.RUNNING if expected else process_identity.DEAD)
    assert ({path.name: path.read_bytes() for path in env.root.iterdir()} if env.root.exists() else {}) == snapshots
    assert env.root.exists() is (kind != "absent")
    forbidden.assert_not_called()


def test_read_inspection_rejects_pair_changed_between_snapshots(configured, monkeypatch):
    daemon.write_pid_file()
    original = process_identity._read
    calls = 0
    def changing(path, limit):
        nonlocal calls
        calls += 1
        snapshot = original(path, limit)
        if calls == 4:
            return process_identity.Snapshot(snapshot.signature, snapshot.data + b" ")
        return snapshot
    monkeypatch.setattr(process_identity, "_read", changing)
    assert process_identity.inspect_record(configured.paths.pid_file, "codeyOS").state == process_identity.UNSAFE


def test_manifest_symbols_exist_and_normal_dispatch_remains_unclassified(tmp_path, monkeypatch):
    from ccos.core import plugin_manager
    from ccos.core.capability_registry import CapabilityRegistry
    from ccos.plugins.system.daemon_control import daemon_control as plugin
    from core.action_gateway import ActionGateway

    manifest_path = Path(plugin.__file__).with_name("manifest.json")
    manifest = json.loads(manifest_path.read_text())
    names = {cap["name"] for cap in manifest["capabilities"]}
    assert len(names) == 7
    for cap in manifest["capabilities"]:
        module_name, function_name = cap["implementation"].split(":")
        assert module_name == "daemon_control" and callable(getattr(plugin, function_name))
        assert cap["name"] not in plugin_manager.CAPABILITY_AUTHORITY
    gateway = ActionGateway(audit_file=tmp_path / "audit.jsonl")
    monkeypatch.setattr(plugin_manager, "get_action_gateway", lambda: gateway)
    registry = CapabilityRegistry(store_path=str(tmp_path / "capabilities.json"))
    manager = plugin_manager.PluginManager(plugin_dirs=[str(manifest_path.parent.parent.parent)], registry=registry)
    assert manager.load("daemon_control")
    try:
        for name in names:
            with pytest.raises(plugin_manager.CapabilityRefused, match="fail-closed default"):
                manager.call_capability(name)
    finally:
        assert manager.unload("daemon_control")


@pytest.mark.parametrize("public_name,private_name", [("daemon_ping", "_daemon_ping"), ("daemon_status", "_daemon_status"), ("daemon_health", "_daemon_health")])
def test_public_rpc_wrappers_preserve_response_and_exception(monkeypatch, public_name, private_name):
    from ccos.plugins.system.daemon_control import daemon_control as plugin

    response = {"status": "ok", "fixture": object()}
    rpc = Mock(return_value=response)
    monkeypatch.setattr(plugin, private_name, rpc)
    assert getattr(plugin, public_name)() is response
    rpc.assert_called_once_with()
    failure = ConnectionError("fixture unavailable")
    rpc.side_effect = failure
    with pytest.raises(ConnectionError) as raised:
        getattr(plugin, public_name)()
    assert raised.value is failure


@pytest.mark.parametrize("kind", ["absent", "malformed", "legacy_live"])
def test_main_daemon_coordination_is_pure_and_never_connects_unverified(configured, monkeypatch, kind):
    import main

    env = configured
    if kind != "absent":
        env.root.mkdir()
        env.paths.pid_file.write_text("-1" if kind == "malformed" else str(os.getpid()))
    before = {p.name: p.read_bytes() for p in env.root.iterdir()} if env.root.exists() else {}
    connect = Mock(side_effect=AssertionError("unverified daemon must not connect"))
    monkeypatch.setattr(daemon.socket, "socket", connect)
    assert main._daemon_is_running() is False
    after = {p.name: p.read_bytes() for p in env.root.iterdir()} if env.root.exists() else {}
    assert before == after
    assert env.root.exists() is (kind != "absent")
    connect.assert_not_called()


def test_main_daemon_coordination_accepts_verified_identity_and_fixture_socket(configured):
    import main

    daemon.write_pid_file()
    try:
        with tempfile.TemporaryDirectory(prefix="codey-uds-") as directory:
            path = Path(directory) / "s"
            configured.config.set("daemon", "socket_file", value=str(path))
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                server.bind(str(path))
                server.listen(1)
                assert main._daemon_is_running() is True
            finally:
                server.close()
    finally:
        assert daemon.remove_pid_file()


def test_main_gate_does_not_rpc_unverified_daemon(configured, monkeypatch):
    import main
    from core.loader_v2 import LOAD_OUTCOME_GATE_DENIED

    configured.root.mkdir()
    configured.paths.pid_file.write_text("-1")
    rpc = Mock(side_effect=AssertionError("unverified daemon RPC"))
    monkeypatch.setattr(daemon, "send_command", rpc)
    report = Mock()
    monkeypatch.setattr(main, "error", report)
    loader = SimpleNamespace(load_primary=Mock(return_value=False), get_last_ensure_outcome=lambda: LOAD_OUTCOME_GATE_DENIED, get_last_ensure_reason=lambda: "fixture headroom")
    assert main._load_primary_with_gate_recovery(loader) is False
    rpc.assert_not_called()
    loader.load_primary.assert_called_once_with()
    assert "no verified reachable daemon is available" in report.call_args.args[0]
    assert configured.paths.pid_file.read_text() == "-1"


def test_main_shutdown_still_attempts_owned_cleanup_for_unsafe_daemon(configured, monkeypatch):
    import main
    from core import loader_v2

    configured.root.mkdir()
    configured.paths.pid_file.write_text("-1")
    loader = SimpleNamespace(unload=Mock())
    monkeypatch.setattr(loader_v2, "get_loader", lambda: loader)
    monkeypatch.setattr(main, "get_monitor", lambda: SimpleNamespace(stop=Mock()))
    main.shutdown()
    loader.unload.assert_called_once_with()
    assert configured.paths.pid_file.read_text() == "-1"


def test_main_daemon_flag_delegates_once_to_shared_entrypoint(monkeypatch):
    import main

    delegate = Mock()
    monkeypatch.setattr(daemon, "main", delegate)
    monkeypatch.setattr(main.signal, "signal", Mock())
    monkeypatch.setattr(sys, "argv", ["codeyOS", "--daemon"])
    main.main()
    delegate.assert_called_once_with()
