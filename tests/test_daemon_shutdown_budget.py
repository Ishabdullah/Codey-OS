"""NEW-967 fixed profile and fake-clock stop checks; no live service signals."""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import process_identity as identity

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")
KEYS = ("codeyOS", "restoricon-api", "aigentik", "litestream", "cloudflared", "backup-docs", "llama-server-8080")


@pytest.fixture
def clock_record(tmp_path, monkeypatch):
    """Every numeric PID is synthetic and all kernel signaling is replaced."""
    proc = tmp_path / "proc"
    boot = proc / "sys/kernel/random/boot_id"
    boot.parent.mkdir(parents=True)
    boot.write_text("11111111-2222-3333-4444-555555555555\n")
    pid = 32123
    entry = proc / str(pid)
    entry.mkdir()
    fields = ["S", str(os.getpid())] + ["0"] * 17 + ["100"]
    (entry / "stat").write_text(f"{pid} (fixture) " + " ".join(fields))
    uid = os.getuid()
    (entry / "status").write_text(f"Uid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
    record = identity.LifecycleRecord(tmp_path / "daemon.pid", "codeyOS", proc_root=proc).__enter__()
    expected = record.publish(pid)
    clock = SimpleNamespace(ticks=0, signals=[], samples={}, death=None, after_kill=False, inspections=[], recheck_start=0)
    def now():
        return clock.ticks / 1_000_000_000
    def sleep(delay):
        assert 0 < delay <= .05
        clock.ticks += max(1, round(delay * 1_000_000_000))
        for mark in (5, 8, 26, 45, 90):
            if now() >= mark and mark not in clock.samples:
                clock.samples[mark] = list(clock.signals)
        if clock.death is not None and now() >= clock.death and (not clock.after_kill or any(value == signal.SIGKILL for _, value in clock.signals)):
            shutil.rmtree(entry, ignore_errors=True)
    def signal_spy(selected_pid, requested):
        assert selected_pid == pid
        # Actual signal() must read identity twice immediately before its kill.
        assert len(clock.inspections) - clock.recheck_start >= 2
        assert clock.inspections[-2:] == [now(), now()]
        clock.signals.append((now(), requested))
    real_info = identity.process_info
    def info(*args, **kwargs):
        clock.inspections.append(now())
        return real_info(*args, **kwargs)
    real_signal = record.signal
    def audited_signal(requested, expected=None):
        clock.recheck_start = len(clock.inspections)
        return real_signal(requested, expected=expected)
    monkeypatch.setattr(record, "signal", audited_signal)
    monkeypatch.setattr(identity, "time", SimpleNamespace(monotonic=now, sleep=sleep))
    monkeypatch.setattr(identity, "process_info", info)
    monkeypatch.setattr(identity.os, "kill", signal_spy)
    forbidden = []
    for name in ("killpg", "getpgid"):
        guard = Mock(side_effect=AssertionError("synthetic PID cannot reach OS"))
        monkeypatch.setattr(identity.os, name, guard)
        forbidden.append(guard)
    spawn = Mock(side_effect=AssertionError("no subprocess in fake-clock cases"))
    monkeypatch.setattr(subprocess, "Popen", spawn)
    forbidden.append(spawn)
    yield SimpleNamespace(record=record, expected=expected, clock=clock, now=now)
    record.__exit__(None, None, None)
    for guard in forbidden:
        guard.assert_not_called()


@pytest.mark.parametrize("cleanup_seconds", [5, 8, 26])
def test_daemon_normal_cleanup_grace_never_escalates_at_prior_thresholds(clock_record, cleanup_seconds):
    env = clock_record
    env.clock.death = cleanup_seconds
    assert env.record.stop(timeout=45) == identity.DEAD
    assert env.clock.signals == [(0, signal.SIGTERM)]
    assert env.now() == pytest.approx(cleanup_seconds)
    assert not env.record.path.exists() and not env.record.identity_path.exists()


def test_daemon_kill_only_at45_and_final_confirmation_keeps_full45_budget(clock_record):
    env = clock_record
    before = (env.record.path.read_bytes(), env.record.identity_path.read_bytes())
    assert env.record.stop(timeout=45) == identity.UNSAFE
    assert env.clock.signals == [(0, signal.SIGTERM), (45, signal.SIGKILL)]
    assert env.now() == pytest.approx(90)
    for threshold in (5, 8, 26, 45):
        assert env.clock.samples[threshold] == [(0, signal.SIGTERM)]
    assert (env.record.path.read_bytes(), env.record.identity_path.read_bytes()) == before


@pytest.mark.parametrize("kill_confirmation_seconds", [44, 45])
def test_exit_at_end_of_second_daemon_phase_is_confirmed(clock_record, kill_confirmation_seconds):
    env = clock_record
    env.clock.after_kill = True
    env.clock.death = 45 + kill_confirmation_seconds
    assert env.record.stop(timeout=45) == identity.DEAD
    assert env.clock.signals == [(0, signal.SIGTERM), (45, signal.SIGKILL)]
    assert env.now() == pytest.approx(45 + kill_confirmation_seconds)
    assert not env.record.path.exists() and not env.record.identity_path.exists()


def test_generic_stop_default_remains_five_per_phase(clock_record):
    env = clock_record
    assert env.record.stop() == identity.UNSAFE
    assert env.clock.signals == [(0, signal.SIGTERM), (5, signal.SIGKILL)]
    assert env.now() == pytest.approx(10)


def test_identity_replacement_immediately_before_escalation_is_preserved(clock_record, monkeypatch):
    env = clock_record
    real_signal = env.record.signal
    replacement = env.record.path.with_name("replacement.pid")
    observed = []
    def replace_before_kill(requested, expected=None):
        observed.append((requested, expected))
        if requested == signal.SIGKILL:
            replacement.write_bytes(env.record.path.read_bytes())
            replacement.replace(env.record.path)  # same contents, different inode
        return real_signal(requested, expected=expected)
    monkeypatch.setattr(env.record, "signal", replace_before_kill)
    original_inode = env.record.path.stat().st_ino
    original_identity = env.record.identity_path.read_bytes()
    assert env.record.stop(timeout=45) == identity.UNSAFE
    assert env.now() == pytest.approx(45)
    assert env.clock.signals == [(0, signal.SIGTERM)]
    assert [request for request, _ in observed] == [signal.SIGTERM, signal.SIGKILL]
    assert all(expected == env.expected for _, expected in observed)
    assert env.record.path.stat().st_ino != original_inode
    assert env.record.path.read_text() == str(env.expected.identity["pid"])
    assert env.record.identity_path.read_bytes() == original_identity


def test_unsafe_initial_identity_has_no_signal_or_cleanup(clock_record):
    env = clock_record
    env.record.identity_path.write_text("unsafe evidence")
    before = (env.record.path.read_bytes(), env.record.identity_path.read_bytes())
    assert env.record.stop(timeout=45) == identity.UNSAFE
    assert env.clock.signals == [] and env.now() == 0
    assert (env.record.path.read_bytes(), env.record.identity_path.read_bytes()) == before


def test_fixed_profile_trace_only_canonical_daemon_receives45(tmp_path):
    trace = tmp_path / "trace.jsonl"
    executable = tmp_path / "python3"
    executable.write_text(f"#!{sys.executable}\n" + '''import json,os,sys
from pathlib import Path
args=sys.argv[1:]
assert args[0]==os.environ['FIXTURE_IDENTITY'] and args[1]=='stop'
with Path(os.environ['FIXTURE_TRACE']).open('a') as stream: stream.write(json.dumps(args)+'\\n')
''')
    executable.chmod(0o700)
    script = 'source "$1"; shift; for key in "$@"; do _codey_locked_identity 200 stop "$key" fixture.pid || exit $?; done'
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), CODEY_STATE_DIR=str(tmp_path / "state"), CODEY_OS_DIR=str(ROOT), PATH=str(tmp_path), FIXTURE_IDENTITY=str(ROOT / "core/process_identity.py"), FIXTURE_TRACE=str(trace), CODEY_STOP_TIMEOUT="0", STOP_TIMEOUT="0")
    result = subprocess.run([BASH, "-c", script, "fixture", str(ROOT / "lib/service_lifecycle.sh"), *KEYS], env=env, capture_output=True, text=True, timeout=5, check=False)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in trace.read_text().splitlines()]
    assert len(calls) == len(KEYS)
    for key, args in zip(KEYS, calls):
        assert args == [str(ROOT / "core/process_identity.py"), "stop", "fixture.pid", key, "--timeout", "45" if key == "codeyOS" else "5", "--lock-fd", "200"]


def test_private_daemon_restart_waits_for_stop_before_replacement_start(tmp_path):
    trace, release = tmp_path / "steps", tmp_path / "release"
    helper = tmp_path / "python3"
    helper.write_text(f"#!{sys.executable}\n" + '''import os,time
from pathlib import Path
release=Path(os.environ['FIXTURE_RELEASE'])
deadline=time.monotonic()+3
while not release.exists() and time.monotonic()<deadline: time.sleep(.01)
if not release.exists(): raise RuntimeError('fixture release missing')
''')
    helper.chmod(0o700)
    script = '''source "$1"
_codey_service_one() {
    printf '%s %s\\n' "$1" "$2" >> "$FIXTURE_TRACE"
    if [ "$1" = daemon ] && [ "$2" = stop ]; then python3; fi
}
_codey_service_operation daemon restart 2 200 daemon codeyOS p l s . 0 0 '' 0 210 llama-server-8080 llama-server-8080 mp ml '' . 0 0 '' 0
'''
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), CODEY_STATE_DIR=str(tmp_path / "state"), CODEY_OS_DIR=str(ROOT), PATH=str(tmp_path), FIXTURE_TRACE=str(trace), FIXTURE_RELEASE=str(release))
    child = subprocess.Popen([BASH, "-c", script, "fixture", str(ROOT / "lib/service_lifecycle.sh")], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if trace.exists() and trace.read_text() == "daemon stop\n":
                break
            time.sleep(.01)
        assert trace.read_text() == "daemon stop\n" and child.poll() is None
        release.touch()
        stdout, stderr = child.communicate(timeout=5)
        assert child.returncode == 0, stdout + stderr
        assert trace.read_text().splitlines() == ["daemon stop", "llama-server-8080 stop", "daemon start"]
    finally:
        # The only helper is synchronous and finite; release it before waiting
        # so assertion failure cannot strand an owned job. No service is spawned.
        release.touch()
        child.wait(timeout=5)
        child.stdout.close()
        child.stderr.close()
