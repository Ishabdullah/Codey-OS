"""Private mechanisms only; no installed service/setup/backup/cloud action runs.

Every external interpreter dispatch is fail-closed allowlisted. HOME/state are
throwaway. Bash owns/reaps its simulated helper jobs; Python retains Bash Popen.
"""

import json
import os
import select
import shutil
import stat
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import process_identity as identity

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "core/service_lifecycle.py"
LIBRARY = ROOT / "lib/service_lifecycle.sh"

WRAPPER = r'''
import os, sys, time
from pathlib import Path
args = sys.argv[1:]
root = Path(os.environ['FIXTURE_REPO'])
trace = Path(os.environ['FIXTURE_TRACE'])
allowed = False
label = 'blocked'
if args and args[0] == str(root / 'core/process_identity.py') and len(args) > 1:
    allowed = args[1] in ('inspect', 'stop', 'signal', 'spawn')
    label = 'identity:' + args[1]
elif args and args[0] == str(root / 'core/service_lifecycle.py') and len(args) > 1:
    allowed = args[1] == 'parse-ready'
    label = 'readiness'
with trace.open('a') as stream: stream.write(label + '\n')
if not allowed: sys.exit(91)
if os.environ.get('FIXTURE_REQUIRE_LOCK') == '1' and label != 'readiness':
    fd = 200
    expected = Path(os.environ['FIXTURE_PID'] + '.lifecycle.lock').stat()
    actual = os.fstat(fd)
    assert (actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino)
if label == 'readiness':
    try: os.fstat(200)
    except OSError: pass
    else: raise RuntimeError('unrelated lifecycle FD leaked into parser')
if os.environ.get('FIXTURE_CLOSED_FD'):
    try: os.fstat(int(os.environ['FIXTURE_CLOSED_FD']))
    except OSError: pass
    else: raise RuntimeError('unrelated inherited FD survived adapter')
mode = os.environ.get('FIXTURE_PROTOCOL')
if label == 'identity:spawn' and mode:
    from core import process_identity as identity
    lock_fd = int(args[args.index('--lock-fd') + 1])
    ready_fd = int(args[args.index('--ready-fd') + 1])
    pid_file = args[args.index('--pid-file') + 1]
    service = args[args.index('--service') + 1]
    with identity.LifecycleRecord(pid_file, service, lock_fd=lock_fd):
        if mode == 'published': data = b'published 707070\n'
        elif mode == 'failed': data = b'failed-cleanup-confirmed\n'
        elif mode in ('retained', 'delayed-retained'): data = f'retained {os.getpid()} 707070\n'.encode()
        elif mode == 'wrong-guardian': data = b'retained 707071 707070\n'
        elif mode == 'malformed': data = b'not-valid\n'
        elif mode in ('trailing', 'trailing-success'): data = b'published 707070\ntrailing-junk\n'
        elif mode in ('eof', 'crash'): data = b''
        else: raise RuntimeError('unknown fixture protocol')
        if mode == 'delayed-retained':
            delay = time.monotonic() + 10.5
            while not Path(os.environ['FIXTURE_RELEASE']).exists() and time.monotonic() < delay:
                time.sleep(.01)
        if data: os.write(ready_fd, data)
        os.close(ready_fd)
        if mode in ('retained', 'delayed-retained', 'malformed', 'eof', 'wrong-guardian', 'trailing'):
            deadline = time.monotonic() + 5
            while not Path(os.environ['FIXTURE_RELEASE']).exists() and time.monotonic() < deadline:
                time.sleep(.01)
        sys.exit(0 if mode in ('published', 'trailing-success') else (3 if mode == 'crash' else 2))
os.execv(sys.executable, [sys.executable, *args])
'''


@pytest.fixture
def sandbox(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "bash").symlink_to(shutil.which("bash"))
    python = bin_dir / "python3"
    python.write_text(f"#!{sys.executable}\n" + WRAPPER)
    python.chmod(0o700)
    home, state_root = tmp_path / "home", tmp_path / "state"
    home.mkdir()
    trace = tmp_path / "commands.txt"
    release = tmp_path / "release"
    pid_file = state_root / "restoricon-api.pid"
    env = dict(os.environ, HOME=str(home), CODEY_STATE_DIR=str(state_root), PATH=str(bin_dir), PYTHONPATH=str(ROOT), FIXTURE_REPO=str(ROOT), FIXTURE_TRACE=str(trace), FIXTURE_RELEASE=str(release), FIXTURE_PID=str(pid_file))
    env.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    yield SimpleNamespace(root=tmp_path, env=env, state=state_root, trace=trace, release=release, pid=pid_file, bin=bin_dir)
    if trace.exists():
        assert "blocked" not in trace.read_text(), "unexpected external command escaped allowlist"


def run_adapter(env, *args, pass_fds=()):
    return subprocess.run([sys.executable, str(ADAPTER), *args], env=env, pass_fds=pass_fds, capture_output=True, text=True, timeout=5, check=False)


def test_source_and_module_import_create_no_state_root(sandbox):
    source = subprocess.run([str(sandbox.bin / "bash"), "-c", 'source "$1"', "fixture", str(LIBRARY)], env=sandbox.env, capture_output=True, text=True, timeout=5, check=False)
    assert source.returncode == 0, source.stderr
    imported = subprocess.run([sys.executable, "-c", "import core.service_lifecycle"], env=sandbox.env, capture_output=True, text=True, timeout=5, check=False)
    assert imported.returncode == 0, imported.stderr
    assert not sandbox.state.exists() and not sandbox.trace.exists()


def test_regular_lock_content_is_untouched_and_only_selected_fd_survives(sandbox):
    sandbox.state.mkdir()
    lock_path = Path(str(sandbox.pid) + ".lifecycle.lock")
    lock_path.write_bytes(b"existing lock content")
    read_fd, write_fd = os.pipe()
    env = dict(sandbox.env, FIXTURE_REQUIRE_LOCK="1", FIXTURE_CLOSED_FD=str(read_fd))
    try:
        result = run_adapter(env, "lock-exec", "restoricon", "preflight", pass_fds=(read_fd,))
    finally:
        os.close(read_fd)
        os.close(write_fd)
    assert result.returncode == 1 and result.stdout.strip() == identity.DEAD, result.stderr
    assert lock_path.read_bytes() == b"existing lock content"
    assert sandbox.trace.read_text().splitlines() == ["identity:inspect"]


@pytest.mark.parametrize("kind", ["symlink", "fifo", "directory"])
def test_unsafe_lock_rejected_without_side_effect_or_interpreter(sandbox, kind):
    sandbox.state.mkdir()
    lock_path = Path(str(sandbox.pid) + ".lifecycle.lock")
    target = sandbox.root / "untouched"
    target.write_bytes(b"unchanged")
    if kind == "symlink":
        lock_path.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(lock_path)
    else:
        lock_path.mkdir()
    started = time.monotonic()
    result = run_adapter(sandbox.env, "lock-exec", "restoricon", "preflight")
    assert result.returncode == 2 and time.monotonic() - started < 3
    assert target.read_bytes() == b"unchanged" and not sandbox.trace.exists()
    if kind == "fifo":
        assert stat.S_ISFIFO(lock_path.lstat().st_mode)


def test_contended_lock_fails_without_mechanics(sandbox):
    with identity.LifecycleRecord(sandbox.pid, "restoricon-api"):
        result = run_adapter(sandbox.env, "lock-exec", "restoricon", "stop")
    assert result.returncode == 2 and not sandbox.trace.exists()


@pytest.mark.parametrize("args", [("lock-exec", "unknown", "stop"), ("lock-exec", "daemon", "--internal"), ("lock-exec", "restoricon", "reload"), ("lock-exec", "daemon", "secret-command")])
def test_finite_operations_reject_arbitrary_dispatch_before_root_creation(sandbox, args):
    result = run_adapter(sandbox.env, *args)
    assert result.returncode == 2
    assert "secret-command" not in result.stderr
    assert not sandbox.state.exists() and not sandbox.trace.exists()


@contextmanager
def protocol_shell(sandbox, mode, disposition="unchanged"):
    outer = identity.LifecycleRecord(sandbox.pid, "fixture").__enter__()
    marker = sandbox.root / "operation-result"
    script = r'''
source "$1"
case "$6" in
    caught)
        trap $'printf \'%s\\n\' "caller\'s quoted handler" >> "$FIXTURE_SIGNAL_MARKER"\n:' INT TERM HUP
        ;;
    ignored) trap '' INT TERM HUP ;;
    default) trap - INT TERM HUP ;;
esac
trap -p INT TERM HUP > "$7"
_codey_spawn_owned 200 fixture "$2" "$3" "$4" fixture-command 'private-token' 'a b; no-shell'
result=$?
trap -p INT TERM HUP > "$8"
case "$6" in
    caught|ignored)
        # Signals target this shell itself, never a protocol/service PID.
        kill -s INT "$BASHPID"
        kill -s TERM "$BASHPID"
        kill -s HUP "$BASHPID"
        ;;
esac
printf '%s\n' "$result" > "$5"
exec 200>&-
wait
exit "$result"
'''
    # This fake helper never spawns a service and no protocol PID is signalled.
    # Bash retains/reaps the actual helper job; Python retains/reaps Bash.
    env = dict(sandbox.env, FIXTURE_PROTOCOL=mode, FIXTURE_REQUIRE_LOCK="1", FIXTURE_SIGNAL_MARKER=str(sandbox.root / "signal-marker"))
    shell = None
    try:
        bootstrap = "import os,sys; source=int(sys.argv[1]); os.dup2(source,200,inheritable=True); os.close(source) if source!=200 else None; os.execv(sys.argv[2],sys.argv[2:])"
        shell = subprocess.Popen([sys.executable, "-c", bootstrap, str(outer.fd), str(sandbox.bin / "bash"), "-c", script, "fixture", str(LIBRARY), str(sandbox.pid), str(sandbox.root / "child.log"), str(sandbox.root), str(marker), disposition, str(sandbox.root / "traps-before"), str(sandbox.root / "traps-after")], env=env, pass_fds=(outer.fd,), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Parent closes its description without LOCK_UN, leaving the actual
        # shell/helper descriptions to govern the complete test operation.
        os.close(outer.fd)
        outer.fd = None
        yield SimpleNamespace(shell=shell, marker=marker)
    finally:
        sandbox.release.touch()
        if shell is not None:
            shell.wait(timeout=10)
            stdout, stderr = shell.communicate(timeout=1)
            shell.stdout.close()
            shell.stderr.close()
            assert b"private-token" not in stdout + stderr
        if outer.fd is not None:
            os.close(outer.fd)
            outer.fd = None


def await_marker(marker, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with marker.open("rb") as stream:
                data = stream.read(3)
        except FileNotFoundError:
            data = b""
        if data in (b"0\n", b"2\n"):
            return int(data)
        assert b"\n" not in data and len(data) <= 1, "invalid private operation result"
        # Redirection creates the file before printf writes its complete frame.
        time.sleep(.01)
    pytest.fail("private parent did not write a complete operation result")


@pytest.mark.parametrize("mode,expected", [("published", 0), ("failed", 2)])
def test_rapid_helper_completion_keeps_saved_job_and_pipe(sandbox, mode, expected):
    for attempt in range(5):
        marker = sandbox.root / "operation-result"
        marker.unlink(missing_ok=True)
        with protocol_shell(sandbox, mode) as env:
            assert await_marker(env.marker) == expected
            env.shell.wait(timeout=5)
            assert env.shell.returncode == expected


def test_retained_guardian_excludes_contender_after_outer_function_returns(sandbox):
    with protocol_shell(sandbox, "retained") as env:
        assert await_marker(env.marker) == 2
        with pytest.raises(identity.UnsafeRecord), identity.LifecycleRecord(sandbox.pid, "fixture", blocking=False):
            pytest.fail("guardian's inherited lock was unlocked")
    with identity.LifecycleRecord(sandbox.pid, "fixture", blocking=False):
        pass


@pytest.mark.parametrize("mode", ["malformed", "eof", "wrong-guardian", "trailing"])
def test_invalid_protocol_keeps_outer_lock_and_waits_actual_job(sandbox, mode):
    with protocol_shell(sandbox, mode) as env:
        time.sleep(.1)
        assert not env.marker.exists() and env.shell.poll() is None
        with pytest.raises(identity.UnsafeRecord), identity.LifecycleRecord(sandbox.pid, "fixture", blocking=False):
            pytest.fail("outer lock released before helper cleanup resolution")
        sandbox.release.touch()
        assert await_marker(env.marker) == 2


def private_path_data(env, field="all", encoding="json"):
    read_fd, write_fd = os.pipe()
    helper = None
    try:
        helper = subprocess.Popen([sys.executable, str(ADAPTER), "paths", "--field", field, "--encoding", encoding, "--data-fd", str(write_fd)], env=env, pass_fds=(write_fd,), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.close(write_fd)
        write_fd = None
        assert select.select([read_fd], [], [], 5)[0]
        data = os.read(read_fd, 4097)
        helper.wait(timeout=5)
        stdout, stderr = helper.communicate(timeout=1)
        assert stdout == b""
        return helper.returncode, data, stderr
    finally:
        if helper is not None:
            helper.wait(timeout=5)
            helper.stdout.close()
            helper.stderr.close()
        os.close(read_fd)
        if write_fd is not None:
            os.close(write_fd)


def test_finite_path_data_preserves_custom_spaces_and_selected_snapshot(sandbox):
    sandbox.state.mkdir()
    selected = {"pid_file": str(sandbox.root / "custom p"), "socket_file": str(sandbox.root / "custom s"), "log_file": str(sandbox.root / "custom l")}
    (sandbox.state / "config.json").write_text(json.dumps({"daemon": selected}))
    rc, data, stderr = private_path_data(sandbox.env)
    assert rc == 0 and not stderr
    assert json.loads(data) == {key: selected[key + "_file"] for key in ("pid", "socket", "log")}
    rc, data, _ = private_path_data(sandbox.env, "socket", "nul")
    assert rc == 0 and data == selected["socket_file"].encode() + b"\0"


def test_malformed_config_warning_cannot_corrupt_private_path_channel(sandbox):
    sandbox.state.mkdir()
    (sandbox.state / "config.json").write_text("{")
    rc, data, stderr = private_path_data(sandbox.env)
    assert rc == 0 and b"Could not load config" in stderr
    assert json.loads(data) == {"pid": str(sandbox.state / "codeyOS.pid"), "socket": str(sandbox.state / "codeyOS.sock"), "log": str(sandbox.state / "codeyOS.log")}


def test_missing_config_path_resolution_does_not_create_root(sandbox):
    rc, data, _ = private_path_data(sandbox.env)
    assert rc == 0 and json.loads(data)["pid"] == str(sandbox.state / "codeyOS.pid")
    assert not sandbox.state.exists()


def test_relative_custom_paths_are_not_reinterpreted_pending_product_choice(sandbox):
    sandbox.state.mkdir()
    (sandbox.state / "config.json").write_text(json.dumps({"daemon": {"pid_file": "custom.pid", "socket_file": "custom.sock", "log_file": "custom.log"}}))
    rc, data, _ = private_path_data(sandbox.env)
    assert rc == 0 and json.loads(data) == {"pid": "custom.pid", "socket": "custom.sock", "log": "custom.log"}


def test_delayed_valid_retained_result_survives_default_cleanup_budget(sandbox):
    with protocol_shell(sandbox, "delayed-retained") as env:
        assert await_marker(env.marker, timeout=15) == 2
        with pytest.raises(identity.UnsafeRecord), identity.LifecycleRecord(sandbox.pid, "fixture", blocking=False):
            pytest.fail("normal delayed retained result fell into timeout cleanup")


@pytest.mark.parametrize("mode", ["trailing-success", "crash"])
def test_broken_protocol_helper_exit_does_not_claim_service_cleanup(sandbox, mode):
    with protocol_shell(sandbox, mode) as env:
        assert await_marker(env.marker) == 2
        stdout, stderr = env.shell.communicate(timeout=5)
        assert b"service identity requires inspection" in stderr
        assert b"cleanup resolved" not in stderr
        assert stdout == b""
    assert sandbox.trace.read_text().splitlines().count("identity:spawn") == 1


def test_adapter_reload_and_stop_verified_disposable_owned_child(sandbox):
    """Only this retained fixture handle is ever eligible for real signals."""
    sandbox.state.mkdir()
    pid_file = sandbox.root / "custom daemon.pid"
    ready = sandbox.root / "child-ready"
    reloaded = sandbox.root / "usr1-marker"
    selected = {"pid_file": str(pid_file), "socket_file": str(sandbox.root / "unused.sock"), "log_file": str(sandbox.root / "unused.log")}
    (sandbox.state / "config.json").write_text(json.dumps({"daemon": selected}))
    code = "import signal,sys,time; from pathlib import Path; signal.signal(signal.SIGUSR1, lambda *_: Path(sys.argv[2]).write_text('USR1\\n')); Path(sys.argv[1]).write_text('ready'); time.sleep(60)"
    child = subprocess.Popen([sys.executable, "-c", code, str(ready), str(reloaded)], env=sandbox.env)
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(.01)
        assert ready.exists() and child.poll() is None
        with identity.LifecycleRecord(pid_file, "codeyOS") as record:
            assert record.publish(child.pid).state == identity.RUNNING
        env = dict(sandbox.env, FIXTURE_REQUIRE_LOCK="1", FIXTURE_PID=str(pid_file))
        result = run_adapter(env, "lock-exec", "daemon", "reload")
        assert result.returncode == 0, result.stderr
        deadline = time.monotonic() + 5
        signal_frame = b""
        while time.monotonic() < deadline:
            try:
                signal_frame = reloaded.read_bytes()
            except FileNotFoundError:
                signal_frame = b""
            if signal_frame == b"USR1\n":
                break
            time.sleep(.01)
        assert signal_frame == b"USR1\n" and child.poll() is None
        result = run_adapter(env, "lock-exec", "daemon", "stop")
        assert result.returncode == 0 and result.stdout.strip() == identity.DEAD, result.stderr
        child.wait(timeout=5)
        assert not pid_file.exists() and not Path(str(pid_file) + ".identity").exists()
        assert sandbox.trace.read_text().splitlines() == ["identity:signal", "identity:stop"]
    finally:
        # Actual Popen ownership, no PID extracted from records or output.
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        else:
            child.wait(timeout=5)


def test_early_fixture_assertion_releases_delayed_helper_and_preserves_error(sandbox):
    actual_shell = None
    started = time.monotonic()
    with pytest.raises(AssertionError, match="original fixture failure"), protocol_shell(sandbox, "delayed-retained") as env:
        actual_shell = env.shell
        raise AssertionError("original fixture failure")
    assert actual_shell is not None and actual_shell.poll() is not None
    assert time.monotonic() - started < 5
    with identity.LifecycleRecord(sandbox.pid, "fixture", blocking=False):
        pass


@pytest.mark.parametrize("mode", ["published", "failed", "retained", "malformed"])
@pytest.mark.parametrize("disposition", ["caught", "ignored", "default"])
def test_private_spawn_restores_exact_caller_signal_dispositions(sandbox, mode, disposition):
    with protocol_shell(sandbox, mode, disposition) as env:
        if mode == "malformed":
            sandbox.release.touch()  # resolve simulated helper before assertions
        assert await_marker(env.marker) == (0 if mode == "published" else 2)
        before = (sandbox.root / "traps-before").read_text()
        after = (sandbox.root / "traps-after").read_text()
        assert before == after
        marker = sandbox.root / "signal-marker"
        if disposition == "caught":
            assert "quoted handler" in before and "\n:" in before
            assert marker.read_text().splitlines() == ["caller's quoted handler"] * 3
        else:
            assert not marker.exists()


@pytest.mark.parametrize("initial", [b"", b"2"])
def test_operation_observer_waits_for_complete_frame(tmp_path, monkeypatch, initial):
    marker = tmp_path / "operation-result"
    marker.write_bytes(initial)
    waits = []

    def finish_write(_delay):
        waits.append(initial)
        marker.write_bytes(b"2\n")

    monkeypatch.setattr(time, "sleep", finish_write)
    assert await_marker(marker) == 2
    assert waits == [initial]


@pytest.mark.parametrize("invalid", [b" 2\n", b"2\njunk", b"1\n", b"02\n"])
def test_operation_observer_rejects_invalid_complete_frames(tmp_path, invalid):
    marker = tmp_path / "operation-result"
    marker.write_bytes(invalid)
    with pytest.raises(AssertionError, match="invalid private operation result"):
        await_marker(marker)
