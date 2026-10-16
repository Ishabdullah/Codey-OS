"""Post-reap metadata locking only: fake proc tree and fully guarded signals.

No Popen is created, no model is loaded, and synthetic PIDs never reach OS
signals. The contention uses actual temporary SQLite-free filesystem/flock.
"""

import os
import shutil
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import loader_v2 as loader
from core import process_identity as identity


@pytest.fixture
def guarded(tmp_path, monkeypatch):
    forbidden = []
    for name in ("kill", "killpg", "getpgid"):
        mock = Mock(side_effect=AssertionError("OS process operation forbidden for synthetic fixture"))
        monkeypatch.setattr(loader.os, name, mock)
        forbidden.append(mock)
    popen = Mock(side_effect=AssertionError("model spawn forbidden"))
    monkeypatch.setattr(loader.subprocess, "Popen", popen)
    forbidden.append(popen)
    proc_root = tmp_path / "proc"
    boot = proc_root / "sys/kernel/random/boot_id"
    boot.parent.mkdir(parents=True)
    boot.write_text("11111111-2222-3333-4444-555555555555\n")
    pid = 32123
    entry = proc_root / str(pid)
    entry.mkdir()
    fields = ["S", str(os.getpid())] + ["0"] * 17 + ["100"]
    (entry / "stat").write_text(f"{pid} (fixture) " + " ".join(fields))
    uid = os.getuid()
    (entry / "status").write_text(f"Uid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
    path = tmp_path / "model.pid"
    real_record = identity.LifecycleRecord
    with real_record(path, "llama-server-8080", proc_root=proc_root) as record:
        expected = record.publish(pid)
    calls = []
    def record_factory(selected_path, service, **kwargs):
        calls.append(kwargs)
        return real_record(selected_path, service, proc_root=proc_root, **kwargs)
    monkeypatch.setattr(identity, "LifecycleRecord", record_factory)
    server = loader.LlamaServer(tmp_path / "nonexistent-model.gguf", port=8080)
    child = Mock(pid=pid)
    child.poll.return_value = 0
    child.wait.return_value = 0
    child.terminate.side_effect = AssertionError("signal to fake process forbidden")
    child.kill.side_effect = AssertionError("signal to fake process forbidden")
    server.process = child
    server._started = True
    server._pid_publication = (path, expected)
    yield SimpleNamespace(path=path, server=server, child=child, expected=expected, calls=calls, proc=proc_root, entry=entry, real_record=real_record)
    for mock in forbidden:
        mock.assert_not_called()
    child.terminate.assert_not_called()
    child.kill.assert_not_called()


def test_confirmed_reap_does_not_wait_on_real_contended_metadata_lock(guarded):
    env = guarded
    shutil.rmtree(env.entry)  # fake proc tree now truthfully reports dead
    sidecar = Path(str(env.path) + ".identity")
    before = (env.path.read_bytes(), sidecar.read_bytes())
    results, failures = [], []
    def stop():
        try: results.append(env.server.stop())
        except BaseException as exc: failures.append(exc)  # noqa: BLE001 - convey thread failure to test
    thread = threading.Thread(target=stop)
    with env.real_record(env.path, "llama-server-8080", proc_root=env.proc):
        thread.start()
        thread.join(timeout=.5)
        resolved_while_held = not thread.is_alive()
        preserved = (env.path.read_bytes(), sidecar.read_bytes()) == before
    # A regression using blocking flock is released before assertions, so the
    # test can fail promptly without leaving a blocked thread or fake child.
    thread.join(timeout=3)
    assert not thread.is_alive() and not failures
    assert resolved_while_held and preserved and results == [True]
    assert env.calls == [{"blocking": False}]
    assert env.server.process is None and env.server._pid_publication is None
    env.child.wait.assert_called_once()
    assert (env.path.read_bytes(), sidecar.read_bytes()) == before
    with env.real_record(env.path, "llama-server-8080", proc_root=env.proc) as owner:
        assert owner.cleanup(env.expected)
    assert not env.path.exists() and not sidecar.exists()


def test_uncontended_matching_dead_publication_is_cleaned(guarded):
    env = guarded
    shutil.rmtree(env.entry)
    assert env.server.stop() is True
    assert env.calls == [{"blocking": False}]
    assert not env.path.exists() and not Path(str(env.path) + ".identity").exists()


def test_replaced_metadata_survives_confirmed_owned_reap(guarded):
    env = guarded
    shutil.rmtree(env.entry)
    env.path.write_bytes(b"replacement evidence")
    sidecar = Path(str(env.path) + ".identity")
    before = sidecar.read_bytes()
    assert env.server.stop() is True
    assert env.path.read_bytes() == b"replacement evidence" and sidecar.read_bytes() == before


def test_uncertain_reap_never_enters_metadata_and_keeps_slot_ownership(guarded, monkeypatch):
    env = guarded
    env.child.poll.return_value = None
    env.child.wait.side_effect = subprocess.TimeoutExpired("fixture", .01)
    monkeypatch.setattr(env.server, "_signal_owned", Mock())  # all signal operations stay mocked
    assert env.server.stop() is False
    assert env.calls == [] and env.server.process is env.child
    assert env.server._pid_publication == (env.path, env.expected)
    assert env.server._cleanup_pending
    model = loader.ModelLoader()
    model._server = env.server
    model._slot_id = "fixture-retained-cost"
    model._loaded = True
    release = Mock(side_effect=AssertionError("uncertain child must retain admission cost"))
    monkeypatch.setattr(model, "_release_own_slot", release)
    with pytest.raises(loader.ModelTeardownError):
        model.unload()
    release.assert_not_called()
    assert model._server is env.server and model._slot_id == "fixture-retained-cost"
    assert model.is_cleanup_pending() and env.calls == []
