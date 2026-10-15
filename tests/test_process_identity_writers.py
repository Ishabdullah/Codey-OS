"""Daemon self-publication and loader-owned child wiring, never model loads."""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from core import daemon, loader_v2, process_identity


@pytest.fixture
def daemon_path(tmp_path, monkeypatch):
    path = tmp_path / "codeyOS.pid"
    monkeypatch.setattr(daemon, "PID_FILE", path)
    monkeypatch.setattr(daemon, "_PID_PUBLICATION", None)
    return path


def test_daemon_self_prewrite_then_publication_and_shutdown(daemon_path):
    daemon_path.write_text(str(os.getpid()) + "\n")
    assert daemon.check_pid_file() is False
    daemon.write_pid_file()
    sidecar = Path(str(daemon_path) + ".identity")
    record = json.loads(sidecar.read_text())
    assert record["pid"] == os.getpid()
    assert record["service"] == "codeyOS"
    assert daemon.check_pid_file() is False
    assert daemon.remove_pid_file() is True
    assert not daemon_path.exists() and not sidecar.exists()


def test_daemon_does_not_override_inconsistent_self_identity(daemon_path):
    daemon.write_pid_file()
    sidecar = Path(str(daemon_path) + ".identity")
    altered = json.loads(sidecar.read_text())
    altered["uid"] += 1
    sidecar.write_text(json.dumps(altered))
    assert daemon.check_pid_file() is True
    assert daemon.remove_pid_file() is False
    assert daemon_path.exists() and sidecar.exists()


def test_daemon_shutdown_preserves_replaced_record(daemon_path):
    daemon.write_pid_file()
    replacement = daemon_path.parent / "replacement.pid"
    replacement.write_bytes(daemon_path.read_bytes())
    replacement.replace(daemon_path)
    assert daemon.remove_pid_file() is False
    assert daemon_path.exists()
    assert Path(str(daemon_path) + ".identity").exists()


def test_daemon_shutdown_does_not_deadlock_shell_stopper_lock(daemon_path):
    daemon.write_pid_file()
    with process_identity.LifecycleRecord(daemon_path, "codeyOS"):
        assert daemon.remove_pid_file() is False
        assert daemon_path.exists()
    assert daemon.remove_pid_file() is True


def test_daemon_rejects_malformed_pid_and_preserves_evidence(daemon_path):
    daemon_path.write_text("-1")
    assert daemon.check_pid_file() is True
    with pytest.raises(process_identity.UnsafeRecord):
        daemon.write_pid_file()
    assert daemon_path.read_text() == "-1"


@pytest.fixture
def child():
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    try:
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        else:
            process.wait(timeout=2)


def test_daemon_refuses_legacy_live_other_process(daemon_path, child):
    daemon_path.write_text(str(child.pid))
    assert daemon.check_pid_file() is True
    with pytest.raises(process_identity.UnsafeRecord):
        daemon.write_pid_file()
    assert child.poll() is None
    assert daemon_path.read_text() == str(child.pid)


def prepare_loader(tmp_path, monkeypatch, child):
    # Popen returns a fixture-owned ordinary Python sleeper. Neither a model
    # process nor the real binary/version probe is executed by this test.
    monkeypatch.setattr(loader_v2, "CODEY_STATE_DIR", tmp_path)
    monkeypatch.setattr(loader_v2.subprocess, "Popen", Mock(return_value=child))
    monkeypatch.setattr(loader_v2.subprocess, "run", Mock(return_value=Mock(stdout="fixture", stderr="")))
    monkeypatch.setattr(loader_v2.time, "sleep", Mock())
    server = loader_v2.LlamaServer(tmp_path / "fake.gguf", port=29876)
    monkeypatch.setattr(server, "_check_health", Mock(return_value=True))
    return server


def test_loader_publishes_actual_owned_child_and_cleans_only_confirmed_exit(tmp_path, monkeypatch, child):
    server = prepare_loader(tmp_path, monkeypatch, child)
    assert server._spawn_locked() is True
    path = tmp_path / "llama-server-29876.pid"
    sidecar = Path(str(path) + ".identity")
    assert json.loads(sidecar.read_text())["pid"] == child.pid
    assert server._pid_publication[0] == path
    assert server.stop() is True
    assert child.poll() is not None
    assert not path.exists() and not sidecar.exists()


def test_loader_stop_preserves_replaced_publication(tmp_path, monkeypatch, child):
    server = prepare_loader(tmp_path, monkeypatch, child)
    assert server._spawn_locked() is True
    path = tmp_path / "llama-server-29876.pid"
    replacement = tmp_path / "replacement.pid"
    replacement.write_bytes(path.read_bytes())
    replacement.replace(path)
    assert server.stop() is True
    assert child.poll() is not None
    assert path.exists() and Path(str(path) + ".identity").exists()


def test_loader_publication_failure_is_degraded_without_triggering_teardown(tmp_path, monkeypatch, child):
    server = prepare_loader(tmp_path, monkeypatch, child)
    path = tmp_path / "llama-server-29876.pid"
    path.write_text("malformed evidence")
    stop = Mock(wraps=server.stop)
    warning = Mock()
    monkeypatch.setattr(server, "stop", stop)
    monkeypatch.setattr(loader_v2, "warning", warning)
    assert server._spawn_locked() is True  # existing health-ready semantics
    assert server._started
    assert server.process is child and child.poll() is None
    assert server._pid_publication is None
    assert server._identity_publication_failed
    stop.assert_not_called()
    warning.assert_called_once_with("llama-server identity publication unavailable; owned child retained")
    assert path.read_text() == "malformed evidence"
    with process_identity.LifecycleRecord(path, "llama-server-29876") as record:
        assert record.inspect().state == process_identity.UNSAFE
    # child fixture's exact-handle finally cleanup owns termination.


def test_synthetic_loader_pid_fixtures_guard_publication_and_teardown():
    """A fake child PID must never reach a real teardown after writer failure."""
    test_root = Path(__file__).parent
    guarded = 0
    for filename in (
        "test_loader_v2_load_mode.py", "test_loader_v2_telemetry.py",
        "test_new145_149_155_option_c.py",
    ):
        for node in ast.walk(ast.parse((test_root / filename).read_text())):
            if not isinstance(node, ast.With):
                continue
            expressions = [item.context_expr for item in node.items]
            fake_spawn = any(
                isinstance(expr, ast.Call) and expr.args
                and isinstance(expr.args[0], ast.Constant) and expr.args[0].value == "subprocess.Popen"
                and any(key.arg == "return_value" and isinstance(key.value, ast.Name) and key.value.id == "fake_process" for key in expr.keywords)
                for expr in expressions
            )
            if not fake_spawn:
                continue
            writer = any(
                isinstance(expr, ast.Call) and expr.args and isinstance(expr.args[0], ast.Constant)
                and expr.args[0].value == "core.process_identity.LifecycleRecord"
                for expr in expressions
            )
            stop = any(
                isinstance(expr, ast.Call) and len(expr.args) >= 2
                and ast.unparse(expr.args[0]) == "lv.LlamaServer"
                and isinstance(expr.args[1], ast.Constant) and expr.args[1].value == "stop"
                and any(key.arg == "return_value" and isinstance(key.value, ast.Constant) and key.value.value is False for key in expr.keywords)
                for expr in expressions
            )
            assert writer and stop, (filename, node.lineno)
            guarded += 1
    assert guarded >= 8
