"""G15h Unit A (NEW-1021): the tunnel token never appears in any argv."""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import process_identity as identity
from core import service_lifecycle as lifecycle
from utils import config as ucfg

CANARY = "FAKE-G15H-UNIT-CANARY-0123456789abcdef"
SELECTED = SimpleNamespace(pid_file=Path("/nonexistent/x.pid"))


class Child:
    pid = 707070

    def poll(self):
        return None

    terminate = kill = wait = Mock()


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("CLOUDFLARE_TUNNEL_TOKEN", "CLOUDFLARED_TOKEN", "TUNNEL_TOKEN"):
        monkeypatch.delenv(name, raising=False)


# --- start_profile -------------------------------------------------------

def test_profile_argv_has_no_token(monkeypatch, clean_env):
    monkeypatch.setattr(ucfg, "get_cloudflare_tunnel_token", lambda *a, **k: CANARY)
    monkeypatch.setattr("shutil.which", lambda name: "/bin/" + name)
    cwd, missing, argv = lifecycle.start_profile("cloudflared", SELECTED)
    assert argv == ["cloudflared", "tunnel", "run"] and missing is False
    assert CANARY not in repr((cwd, missing, argv))


def test_profile_no_token_and_no_binary(monkeypatch, clean_env):
    monkeypatch.setattr("shutil.which", lambda name: "/bin/" + name)
    monkeypatch.setattr(ucfg, "get_cloudflare_tunnel_token", lambda *a, **k: None)
    assert lifecycle.start_profile("cloudflared", SELECTED)[1:] == (True, [])
    getter = Mock(return_value=CANARY)
    monkeypatch.setattr(ucfg, "get_cloudflare_tunnel_token", getter)
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert lifecycle.start_profile("cloudflared", SELECTED)[1:] == (True, [])
    getter.assert_not_called()


# --- selector table --------------------------------------------------------

def test_selector_table_is_exactly_cloudflared():
    assert identity._SERVICE_SECRET_ENV == {"cloudflared": "TUNNEL_TOKEN"}
    assert identity._service_env_provider("cloudflared") is not None
    for service in ("codeyOS", "restoricon-api", "aigentik", "litestream", "backup-docs", "llama-server-8080", "TUNNEL_TOKEN=x", "", "unknown"):
        assert identity._service_env_provider(service) is None


def test_provider_builds_env_copy(monkeypatch, clean_env):
    monkeypatch.setattr(ucfg, "get_cloudflare_tunnel_token", lambda *a, **k: CANARY)
    monkeypatch.setenv("CLOUDFLARE_TUNNEL_TOKEN", "other-source")
    monkeypatch.setenv("CLOUDFLARED_TOKEN", "other-source-2")
    monkeypatch.setenv("KEEP_ME", "yes")
    before = dict(os.environ)
    env = identity._service_env_provider("cloudflared")()
    assert env["TUNNEL_TOKEN"] == CANARY and env["KEEP_ME"] == "yes"
    assert "CLOUDFLARE_TUNNEL_TOKEN" not in env and "CLOUDFLARED_TOKEN" not in env
    assert dict(os.environ) == before and "TUNNEL_TOKEN" not in os.environ


def test_provider_ignores_argv_entirely(monkeypatch, clean_env):
    monkeypatch.setattr(ucfg, "get_cloudflare_tunnel_token", lambda *a, **k: CANARY)
    monkeypatch.setattr(sys, "argv", ["process_identity.py", "spawn", "--", "x", "INJECTED_ENV=1", "TUNNEL_TOKEN=evil"])
    env = identity._service_env_provider("cloudflared")()
    assert "INJECTED_ENV" not in env and env["TUNNEL_TOKEN"] == CANARY


def test_provider_unavailable_fixed_text(monkeypatch, clean_env):
    monkeypatch.setattr(ucfg, "get_cloudflare_tunnel_token", lambda *a, **k: None)
    with pytest.raises(identity.UnsafeRecord) as caught:
        identity._service_env_provider("cloudflared")()
    assert str(caught.value) == "Service credential unavailable"


# --- OwnedLaunch -----------------------------------------------------------

@pytest.fixture
def launch_env(tmp_path, monkeypatch):
    child = Child()
    record = Mock(inherited_fd=None)
    publication = identity.Inspection(identity.RUNNING, {"pid": child.pid})
    record.inspect.side_effect = [identity.Inspection(identity.DEAD), publication]
    record.cleanup.return_value = True
    record.publish.return_value = publication
    read_fd, ready_fd = os.pipe()
    popen = Mock(return_value=child)
    monkeypatch.setattr(identity.subprocess, "Popen", popen)
    monkeypatch.setattr(identity.os, "kill", Mock(side_effect=AssertionError("signal")))

    def make(**kwargs):
        return identity.OwnedLaunch(record, ["cloudflared", "tunnel", "run", "TUNNEL_TOKEN=notenv"], log_file=tmp_path / "c.log", ready_fd=ready_fd, startup_delay=0, timeout=0, **kwargs)

    yield SimpleNamespace(make=make, record=record, popen=popen, read_fd=read_fd, ready_fd=ready_fd, tmp=tmp_path)
    os.close(read_fd)
    try:
        os.close(ready_fd)
    except OSError:
        pass


def test_launch_passes_env_only_with_provider(launch_env):
    env = {"PATH": "/x", "TUNNEL_TOKEN": CANARY}
    assert launch_env.make(env_provider=lambda: env).run() == 0
    kwargs = launch_env.popen.call_args.kwargs
    assert kwargs["env"] is env
    assert CANARY not in repr(launch_env.popen.call_args.args)
    # An argv element that looks like an assignment stays plain argv.
    assert "TUNNEL_TOKEN=notenv" in launch_env.popen.call_args.args[0]


def test_launch_without_provider_has_no_env_kwarg(launch_env):
    assert launch_env.make().run() == 0
    assert "env" not in launch_env.popen.call_args.kwargs


def test_provider_failure_never_spawns(launch_env):
    def boom():
        raise identity.UnsafeRecord("Service credential unavailable")
    launch = launch_env.make(env_provider=boom)
    assert launch.run() == 2
    launch_env.popen.assert_not_called()
    launch_env.record.publish.assert_not_called()
    data = os.read(launch_env.read_fd, 128)
    assert identity.parse_spawn_ready(data).outcome == "failed-cleanup-confirmed"
    assert CANARY.encode() not in data


def test_provider_not_called_when_evidence_blocks(launch_env):
    launch_env.record.inspect.side_effect = None
    launch_env.record.inspect.return_value = identity.Inspection(identity.RUNNING)
    provider = Mock(return_value={})
    assert launch_env.make(env_provider=provider).run() == 2
    provider.assert_not_called()
    launch_env.popen.assert_not_called()


# --- _spawn_main selector ----------------------------------------------------

@pytest.mark.parametrize("service,expect", [("cloudflared", True), ("litestream", False), ("aigentik", False), ("codeyOS", False), ("nope", False)])
def test_spawn_main_installs_provider_by_service_only(tmp_path, monkeypatch, service, expect):
    seen = {}

    class Fake:
        handed_off = False

        def __init__(self, record, argv, **kwargs):
            seen["argv"], seen["provider"] = argv, kwargs.get("env_provider")

        def run(self):
            return 0

    class Rec:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(identity, "OwnedLaunch", Fake)
    monkeypatch.setattr(identity, "LifecycleRecord", Rec)
    monkeypatch.setattr(identity, "_ready_pipe", lambda fd, lock: fd)
    argv = ["--pid-file", "/p", "--service", service, "--lock-fd", "200", "--ready-fd", "1", "--log-file", "/l", "--", "x", "TUNNEL_TOKEN=evil"]
    assert identity._spawn_main(argv) == 0
    assert (seen["provider"] is not None) is expect
    assert seen["argv"] == ["x", "TUNNEL_TOKEN=evil"]


class _Odd(Exception):
    pass


@pytest.mark.parametrize("exc", [
    RuntimeError(CANARY), OSError(CANARY), _Odd(CANARY),
    subprocess.CalledProcessError(1, ["age", "-d", "-i", "/k/" + CANARY, "/x/" + CANARY], output=CANARY, stderr=CANARY),
    subprocess.TimeoutExpired(["age", CANARY], 10),
])
def test_non_unsaferecord_provider_error_fails_closed_silently(launch_env, monkeypatch, clean_env, capfd, exc):
    """Any decrypt/getter error (not only UnsafeRecord) ends as a clean pre-spawn failure with no echo."""
    def getter(*a, **k):
        raise exc
    monkeypatch.setattr(ucfg, "get_cloudflare_tunnel_token", getter)
    launch = launch_env.make(env_provider=identity._service_env_provider("cloudflared"))
    assert launch.run() == 2
    launch_env.popen.assert_not_called()
    launch_env.record.publish.assert_not_called()
    assert not (launch_env.tmp / "c.log").exists()  # log never opened
    data = os.read(launch_env.read_fd, 128)
    assert identity.parse_spawn_ready(data).outcome == "failed-cleanup-confirmed"
    out, err = capfd.readouterr()
    assert out == "" and err == ""
    assert CANARY not in out + err + data.decode() and "Traceback" not in out + err
