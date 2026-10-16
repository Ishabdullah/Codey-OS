"""Disposable owned helper/child fixtures; no installed service or model runs.

The helper harness retains every actual Popen out of band through finally.
The parent retains its actual helper Popen. Only those handles are signalled.
"""

import json
import os
import select
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from core import process_identity as identity

HARNESS = r'''
import json, os, signal, sys, threading, time
from pathlib import Path
from core import process_identity as identity
pid_file, log_file, completion, scenario = sys.argv[1:5]
lock_fd, ready_fd, control_fd = map(int, sys.argv[5:8])
owned = []
real_popen = identity.subprocess.Popen
real_reap = identity.OwnedLaunch._reap_owned
real_write = identity.LifecycleRecord._atomic_write
writes = 0
allow_cleanup = False
backstop_requested = False
spawn_in_progress = False
rc = None

def cleanup_children():
    for child in tuple(owned):
        if child.poll() is None:
            child.terminate()
            try: child.wait(timeout=.3)
            except identity.subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2)
        else:
            child.wait(timeout=2)

def write_completion():
    temporary = Path(completion + '.' + str(threading.get_ident()) + '.tmp')
    temporary.write_text(json.dumps({'rc': rc, 'children': len(owned), 'returncodes': [p.returncode for p in owned], 'backstop': backstop_requested}))
    temporary.replace(completion)

def request_backstop(*_):
    global backstop_requested
    backstop_requested = True  # no Popen call or lock acquisition in signal context

def cleanup_worker():
    while True:
        time.sleep(.02)
        if not backstop_requested or spawn_in_progress:
            continue
        try:
            cleanup_children()
            write_completion()
        except BaseException:
            continue  # retain actual handles and retry; never exit unreaped
        os._exit(2)  # test-only exit only after all retained children are reaped

signal.signal(signal.SIGUSR2, request_backstop)
threading.Thread(target=cleanup_worker, daemon=True).start()

def spawn(*args, **kwargs):
    global spawn_in_progress
    spawn_in_progress = True
    try:
        child = real_popen(*args, **kwargs)
        owned.append(child)
        return child
    finally:
        spawn_in_progress = False
identity.subprocess.Popen = spawn

def wait_child_ready():
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if Path(log_file).exists() and Path(log_file).read_bytes().strip():
            return
        time.sleep(.01)
    raise RuntimeError('fixture child did not initialize')

def write(self, target, data, expected):
    global writes
    writes += 1
    if scenario in ('write1', 'guardian', 'term_ignore', 'eof_guardian') and writes == 1 or scenario == 'write2' and writes == 2:
        wait_child_ready()
        raise OSError('fixture publication failure')
    return real_write(self, target, data, expected)
identity.LifecycleRecord._atomic_write = write

if scenario in ('guardian', 'eof_guardian'):
    os.set_blocking(control_fd, False)
    def reap(self):
        global allow_cleanup
        try:
            allow_cleanup = allow_cleanup or bool(os.read(control_fd, 1))
        except BlockingIOError:
            pass
        return real_reap(self) if allow_cleanup else False
    identity.OwnedLaunch._reap_owned = reap
if scenario == 'eof_guardian':
    def report(self, outcome):
        if not self.ready_attempted:
            self.ready_attempted = True
            os.close(self.ready_fd)
            self.ready_fd = None
        return False
    identity.OwnedLaunch._report = report
if scenario == 'replacement':
    publish = identity.LifecycleRecord.publish
    def replaced(self, pid, **kwargs):
        observed = publish(self, pid, **kwargs)
        replacement = self.path.with_name('replacement')
        replacement.write_bytes(b'707070')
        replacement.replace(self.path)
        return observed
    identity.LifecycleRecord.publish = replaced

code = ''' + 'r"""' + r'''
import json, os, signal, sys, threading, time
fds = [int(value) for value in sys.argv[1].split(',')]
leaked = []
for fd in fds:
    try: os.fstat(fd); leaked.append(fd)
    except OSError: pass
if sys.argv[2] == 'term_ignore': signal.signal(signal.SIGTERM, signal.SIG_IGN)
print(json.dumps({'hup_ignored': signal.getsignal(signal.SIGHUP) == signal.SIG_IGN, 'leaked': leaked}), flush=True)
time.sleep(60)
''' + '"""' + r'''
try:
    rc = identity.main(['spawn', '--pid-file', pid_file, '--service', 'fixture', '--lock-fd', str(lock_fd), '--ready-fd', str(ready_fd), '--log-file', log_file, '--startup-delay', '.05', '--timeout', '.1', '--', sys.executable, '-u', '-c', code, ','.join(map(str, (lock_fd, ready_fd, control_fd))), scenario, 'private-argv-marker'])
    if rc == 0:
        if scenario == 'cleanup_timeout':
            while True: time.sleep(1)  # forced normal-cleanup timeout, worker owns backstop
        else:
            os.read(control_fd, 1)  # fixture retains successful child's handle until cleanup
finally:
    cleanup_children()
    write_completion()
'''


def read_ready(fd, timeout=5):
    deadline = time.monotonic() + timeout
    data = b""
    while len(data) <= 96:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            raise AssertionError("owned helper did not close its bounded readiness pipe")
        chunk = os.read(fd, 97 - len(data))
        if not chunk:
            return data
        data += chunk
    raise AssertionError("oversized readiness")


# Unexpected unconfirmed cleanup retains references/FDs for investigation.
# Tests must never silently close the last tracking state for a live helper.
_RETAINED_FIXTURES = []


@contextmanager
def fixture_launch(tmp_path, scenario="success", *, broken_pipe=False, normal_wait=10):
    script = tmp_path / "helper.py"
    script.write_text(HARNESS)
    pid_file, log_file, completion = (tmp_path / name for name in ("fixture.pid", "child.log", "done.json"))
    outer = identity.LifecycleRecord(pid_file, "fixture").__enter__()
    ready_r, ready_w = os.pipe()
    control_r, control_w = os.pipe()
    helper = None
    try:
        helper = subprocess.Popen(
            [sys.executable, str(script), str(pid_file), str(log_file), str(completion), scenario, str(outer.fd), str(ready_w), str(control_r)],
            pass_fds=(outer.fd, ready_w, control_r), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]), CODEY_STATE_DIR=str(tmp_path / "state")),
        )
        os.close(ready_w)
        ready_w = None
        os.close(control_r)
        control_r = None
        if broken_pipe:
            os.close(ready_r)
            ready_r = None
            data = None
        else:
            data = read_ready(ready_r)
        yield SimpleFixture(helper, data, outer, control_w, pid_file, log_file, completion)
    finally:
        original_failure = sys.exc_info()[1]
        cleanup_confirmed = helper is None
        try:
            try:
                os.write(control_w, b"x")  # normal retained owned-handle cleanup
            except BrokenPipeError:
                pass
            if helper is not None:
                try:
                    helper.wait(timeout=normal_wait)
                except subprocess.TimeoutExpired:
                    # The actual retained helper Popen is the only target.
                    # Its signal handler merely requests cleanup from a separate
                    # worker that retains/reaps actual child Popen handles.
                    helper.send_signal(signal.SIGUSR2)
                    helper.wait(timeout=10)
                stdout, stderr = helper.communicate(timeout=1)
                assert completion.exists(), (stdout, stderr)
                done = json.loads(completion.read_text())
                assert done["children"] <= 1
                assert all(code is not None for code in done["returncodes"])
                cleanup_confirmed = True
                assert b"private-argv-marker" not in stdout + stderr
        except BaseException:
            if original_failure is None:
                raise
            original_failure.add_note("Owned fixture cleanup validation also failed" if cleanup_confirmed else "Owned fixture cleanup also failed; unconfirmed handles/FDs remain retained")
        finally:
            if cleanup_confirmed:
                if helper is not None:
                    helper.stdout.close()
                    helper.stderr.close()
                for fd in (ready_r, ready_w, control_r, control_w):
                    if fd is not None:
                        os.close(fd)
                # Closing, never LOCK_UN, preserves any inherited lock owner.
                if outer.fd is not None:
                    os.close(outer.fd)
                    outer.fd = None
            else:
                _RETAINED_FIXTURES.append((helper, outer, ready_r, ready_w, control_r, control_w))


class SimpleFixture:
    def __init__(self, helper, data, outer, control_w, pid_file, log_file, completion):
        self.helper, self.data, self.outer, self.control_w = helper, data, outer, control_w
        self.pid_file, self.log_file, self.completion = pid_file, log_file, completion


def test_successful_publication_closes_service_fds_and_preserves_nohup(tmp_path):
    with fixture_launch(tmp_path) as env:
        result = identity.parse_spawn_ready(env.data)
        assert result.outcome == "published"
        assert identity.inspect_record(env.pid_file, "fixture").identity["pid"] == result.child_pid
        deadline = time.monotonic() + 3
        while not env.log_file.read_text().strip() and time.monotonic() < deadline:
            time.sleep(.01)
        child = json.loads(env.log_file.read_text().strip())
        assert child == {"hup_ignored": True, "leaked": []}
        assert env.helper.poll() is None  # fixture retains its actual child's Popen


@pytest.mark.parametrize("scenario", ["write1", "write2", "term_ignore", "replacement"])
def test_failed_publication_reaps_only_its_real_owned_child(tmp_path, scenario):
    with fixture_launch(tmp_path, scenario) as env:
        assert identity.parse_spawn_ready(env.data).outcome == "failed-cleanup-confirmed"
        env.helper.wait(timeout=5)
        done = json.loads(env.completion.read_text())
        assert done["rc"] == 2 and done["children"] == 1
        assert done["returncodes"][0] is not None
        if scenario == "term_ignore":
            assert done["returncodes"] == [-9]
        if scenario == "replacement":
            assert env.pid_file.read_bytes() == b"707070"


def test_retained_guardian_holds_same_lock_and_ignores_cleanup_interrupt_until_reaped(tmp_path):
    with fixture_launch(tmp_path, "guardian") as env:
        result = identity.parse_spawn_ready(env.data)
        assert result.outcome == "retained" and result.guardian_pid == env.helper.pid
        os.close(env.outer.fd)
        env.outer.fd = None
        with pytest.raises(identity.UnsafeRecord), identity.LifecycleRecord(env.pid_file, "fixture", blocking=False):
            pytest.fail("guardian lock unexpectedly available")
        env.helper.terminate()  # exact fixture-owned Popen; request, not bare PID kill
        time.sleep(.1)
        assert env.helper.poll() is None
        os.write(env.control_w, b"x")
        env.helper.wait(timeout=5)
        with identity.LifecycleRecord(env.pid_file, "fixture", blocking=False):
            pass


def test_broken_pipe_failure_reaps_before_helper_exit(tmp_path):
    with fixture_launch(tmp_path, broken_pipe=True) as env:
        env.helper.wait(timeout=5)
        done = json.loads(env.completion.read_text())
        assert done["rc"] == 2 and done["returncodes"][0] is not None


def test_eof_while_guardian_live_keeps_outer_lock_until_owned_job_finishes(tmp_path):
    with fixture_launch(tmp_path, "eof_guardian") as env:
        assert env.data == b"" and env.helper.poll() is None
        with pytest.raises(identity.UnsafeRecord), identity.LifecycleRecord(env.pid_file, "fixture", blocking=False):
            pytest.fail("outer lock released after malformed/EOF readiness")
        os.write(env.control_w, b"x")
        env.helper.wait(timeout=5)  # wait actual helper job, no PID signal or fallback spawn
        assert json.loads(env.completion.read_text())["children"] == 1


@pytest.mark.parametrize("original_failure", [False, True])
def test_fixture_cleanup_timeout_backstop_reaps_handles_and_preserves_failure(tmp_path, original_failure):
    if original_failure:
        with pytest.raises(AssertionError, match="original fixture failure"), fixture_launch(tmp_path, "cleanup_timeout", normal_wait=.02):
            raise AssertionError("original fixture failure")
    else:
        with fixture_launch(tmp_path, "cleanup_timeout", normal_wait=.02):
            pass
    done = json.loads((tmp_path / "done.json").read_text())
    assert done["backstop"] is True
    assert done["children"] == 1 and all(code is not None for code in done["returncodes"])
    assert not _RETAINED_FIXTURES


def test_fixture_backstop_signal_handler_only_sets_request():
    import ast

    handler = next(node for node in ast.parse(HARNESS).body if isinstance(node, ast.FunctionDef) and node.name == "request_backstop")
    assert not any(isinstance(node, ast.Call) for node in ast.walk(handler))
