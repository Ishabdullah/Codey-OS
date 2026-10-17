"""NEW-86/14d: synthetic proc root; every process/network/model effect forbidden."""
import os
import signal
import socket
from types import SimpleNamespace

import pytest

from core import embed_server as es
from core import loader_v2 as loader
from core import process_identity as identity

PORT = 18999


@pytest.fixture
def fake(tmp_path, monkeypatch):
    def forbidden(*a, **k):
        pytest.fail("real process/network effect forbidden")

    for name in ("killpg", "getpgid"):
        monkeypatch.setattr(os, name, forbidden)
    monkeypatch.setattr(es.subprocess, "Popen", forbidden)
    monkeypatch.setattr(es.subprocess, "run", forbidden)
    monkeypatch.setattr(es.urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    root = tmp_path / "proc"
    boot = root / "sys/kernel/random/boot_id"
    boot.parent.mkdir(parents=True)
    boot.write_text("11111111-2222-3333-4444-555555555555")
    pid = 32123
    directory = root / str(pid)
    directory.mkdir()
    executable, model = tmp_path / "llama-server", tmp_path / "embed.gguf"
    executable.touch()
    model.touch()
    (directory / "exe").symlink_to(executable)
    (directory / "cwd").symlink_to(tmp_path)

    def proc(*, start=100, uid=None, state="S"):
        uid = os.getuid() if uid is None else uid
        fields = [state, str(os.getpid())] + ["0"] * 17 + [str(start)]
        (directory / "stat").write_text(f"{pid} (fixture ) cmd) " + " ".join(fields))
        (directory / "status").write_text(f"Uid:\t{uid}\t{uid}\t{uid}\t{uid}\n")

    def argv(values=None):
        values = values or [str(executable), "-m", str(model), "--port", str(PORT), "--embedding"]
        (directory / "cmdline").write_bytes(b"\0".join(os.fsencode(v) for v in values) + b"\0")

    proc()
    argv()
    monkeypatch.setattr(es, "LLAMA_SERVER_BIN", executable)
    monkeypatch.setattr(es.EmbedServer, "_PROC_ROOT", root)
    actual_info = identity.process_info
    monkeypatch.setattr(identity, "process_info", lambda candidate, *_: actual_info(candidate, root))
    calls = []
    monkeypatch.setattr(os, "kill", lambda candidate, requested: calls.append((candidate, requested)))
    clock = [0.0]
    monkeypatch.setattr(loader.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(loader.time, "sleep", lambda d: clock.__setitem__(0, clock[0] + d))
    srv = es.EmbedServer()
    srv.model_path = model
    srv.port = PORT
    bound = [True]
    srv._find_port_occupant_pid = lambda: pid
    srv._port_is_bound = lambda: bound[0]
    return SimpleNamespace(srv=srv, root=root, directory=directory, pid=pid, executable=executable,
                           model=model, proc=proc, argv=argv, calls=calls, clock=clock, bound=bound)


def test_exact_identity_term_then_exit_clears_port(fake, monkeypatch):
    def kill(pid, sig):
        fake.calls.append((pid, sig))
        fake.bound[0] = False
        (fake.directory / "stat").unlink()
        (fake.directory / "status").unlink()
        (fake.directory / "exe").unlink()
        (fake.directory / "cwd").unlink()
        (fake.directory / "cmdline").unlink()
        fake.directory.rmdir()
    monkeypatch.setattr(os, "kill", kill)
    assert fake.srv._kill_port_occupant() is True
    assert fake.calls == [(fake.pid, signal.SIGTERM)]


def test_term_ignored_then_kill_after_revalidation(fake):
    assert fake.srv._kill_port_occupant() is False  # port stays bound; truthful
    assert [s for _, s in fake.calls] == [signal.SIGTERM, signal.SIGKILL]
    assert {p for p, _ in fake.calls} == {fake.pid}


def test_replacement_after_term_never_gets_kill(fake, monkeypatch):
    def kill(pid, sig):
        fake.calls.append((pid, sig))
        fake.proc(start=101)
    monkeypatch.setattr(os, "kill", kill)
    assert fake.srv._kill_port_occupant() is False
    assert [s for _, s in fake.calls] == [signal.SIGTERM]


def test_replacement_between_capture_and_term_not_signalled(fake, monkeypatch):
    real = fake.srv._capture_embed_occupant

    def capture(pid):
        result = real(pid)
        fake.proc(start=101)
        return result
    fake.srv._capture_embed_occupant = capture
    assert fake.srv._kill_port_occupant() is False
    assert fake.calls == []


@pytest.mark.parametrize("bad", ["exe", "model", "port", "extra-model", "no-port", "uid", "zombie",
                                 "no-stat", "malformed-port", "relative-wrong-model"])
def test_unrelated_or_unprovable_occupant_refused_zero_signals(fake, bad):
    values = [str(fake.executable), "-m", str(fake.model), "--port", str(PORT)]
    if bad == "exe":
        (fake.directory / "exe").unlink()
        (fake.directory / "exe").symlink_to(fake.model)
    elif bad == "model":
        values[2] = str(fake.executable)
    elif bad == "port":
        values[-1] = "8082"
    elif bad == "extra-model":
        values += ["--model=" + str(fake.model)]
    elif bad == "no-port":
        values = values[:3]
    elif bad == "uid":
        fake.proc(uid=os.getuid() + 1)
    elif bad == "zombie":
        fake.proc(state="Z")
    elif bad == "no-stat":
        (fake.directory / "stat").unlink()
    elif bad == "malformed-port":
        values[-1] = "+" + str(PORT)
    elif bad == "relative-wrong-model":
        values[2] = "other.gguf"
    fake.argv(values)
    assert fake.srv._kill_port_occupant() is False
    assert fake.calls == []


def test_unknown_pid_refused(fake):
    fake.srv._find_port_occupant_pid = lambda: None
    assert fake.srv._kill_port_occupant() is False
    assert fake.calls == []


def test_portscan_pid_changes_between_lookups_refused(fake):
    seq = iter([fake.pid, 99999])
    fake.srv._find_port_occupant_pid = lambda: next(seq)
    assert fake.srv._kill_port_occupant() is False
    assert fake.calls == []


def test_refused_occupant_that_vanishes_reports_port_free(fake):
    fake.argv([str(fake.executable), "-m", "/nope", "--port", str(PORT)])
    fake.bound[0] = False
    assert fake.srv._kill_port_occupant() is True
    assert fake.calls == []
