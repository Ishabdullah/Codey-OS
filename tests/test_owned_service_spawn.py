"""Owned-spawn mechanics: synthetic handles never reach real OS signals."""

import os
import signal
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import process_identity as identity


class Child:
    pid = 606060

    def __init__(self):
        self.alive = True
        self.term_works = True
        self.kill_works = True
        self.terminate = Mock(side_effect=self._terminate)
        self.kill = Mock(side_effect=self._kill)
        self.wait = Mock(side_effect=self._wait)

    def poll(self):
        return None if self.alive else -15

    def _terminate(self):
        if self.term_works:
            self.alive = False

    def _kill(self):
        if self.kill_works:
            self.alive = False

    def _wait(self, timeout):
        if self.alive:
            raise subprocess.TimeoutExpired("fixture", timeout)
        return -15


@pytest.fixture
def launch_env(tmp_path, monkeypatch):
    child = Child()
    record = Mock(inherited_fd=None)
    publication = identity.Inspection(identity.RUNNING, {"pid": child.pid})
    record.inspect.side_effect = [identity.Inspection(identity.DEAD), publication]
    record.cleanup.return_value = True
    record.publish.return_value = publication
    read_fd, ready_fd = os.pipe()
    # Every synthetic process uses fully mocked Popen methods and raw signals.
    raw_signal = Mock(side_effect=AssertionError("synthetic PID reached OS signal"))
    monkeypatch.setattr(identity.os, "kill", raw_signal)
    monkeypatch.setattr(identity.os, "killpg", raw_signal)
    popen = Mock(return_value=child)
    monkeypatch.setattr(identity.subprocess, "Popen", popen)
    launch = identity.OwnedLaunch(record, ["fixture", "secret-marker"], log_file=tmp_path / "child.log", ready_fd=ready_fd, startup_delay=0, timeout=0)
    try:
        yield SimpleNamespace(launch=launch, record=record, child=child, read_fd=read_fd, popen=popen, publication=publication, raw_signal=raw_signal)
    finally:
        os.close(read_fd)
        if launch.ready_fd is not None:
            os.close(launch.ready_fd)
        raw_signal.assert_not_called()


def ready(env):
    return identity.parse_spawn_ready(os.read(env.read_fd, 128))


def test_success_publishes_then_reports_without_signalling_child(launch_env):
    env = launch_env
    assert env.launch.run() == 0
    assert ready(env) == identity.SpawnReady("published", child_pid=env.child.pid)
    env.record.publish.assert_called_once_with(env.child.pid)
    env.child.terminate.assert_not_called()
    assert env.launch.child is env.child
    kwargs = env.popen.call_args.kwargs
    assert kwargs["close_fds"] is True and "pass_fds" not in kwargs and "shell" not in kwargs
    assert kwargs["stdin"] == subprocess.DEVNULL and kwargs["stderr"] == subprocess.STDOUT
    assert os.read(env.read_fd, 1) == b""


@pytest.mark.parametrize("state", [identity.RUNNING, identity.UNSAFE])
def test_existing_evidence_blocks_before_spawn(launch_env, state):
    env = launch_env
    env.record.inspect.side_effect = None
    env.record.inspect.return_value = identity.Inspection(state)
    assert env.launch.run() == 2
    assert ready(env).outcome == "failed-cleanup-confirmed"
    env.popen.assert_not_called()
    env.record.publish.assert_not_called()


@pytest.mark.parametrize("failure", ["popen", "publication", "identity_check", "close_log", "interrupt", "early_exit"])
def test_postspawn_failures_confirm_owned_cleanup(launch_env, monkeypatch, failure):
    env = launch_env
    if failure == "popen":
        env.popen.side_effect = OSError("secret-marker")
    elif failure == "publication":
        env.record.publish.side_effect = OSError("secret-marker")
    elif failure == "identity_check":
        env.record.inspect.side_effect = [identity.Inspection(identity.DEAD), identity.Inspection(identity.UNSAFE)]
    elif failure == "interrupt":
        env.record.publish.side_effect = KeyboardInterrupt
    elif failure == "early_exit":
        env.child.alive = False
    else:
        log = Mock()
        log.__enter__ = Mock(return_value=log)
        log.__exit__ = Mock(side_effect=OSError("secret-marker"))
        monkeypatch.setattr("builtins.open", Mock(return_value=log))
    assert env.launch.run() == 2
    assert ready(env).outcome == "failed-cleanup-confirmed"
    if failure != "popen":
        assert not env.child.alive and env.child.wait.called


def test_ignored_term_escalates_and_reaps(launch_env):
    env = launch_env
    env.record.publish.side_effect = OSError
    env.child.term_works = False
    assert env.launch.run() == 2
    assert ready(env).outcome == "failed-cleanup-confirmed"
    env.child.terminate.assert_called_once_with()
    env.child.kill.assert_called_once_with()
    assert env.child.wait.call_count == 2


@pytest.mark.parametrize("failure", ["term", "kill", "wait", "interruption"])
def test_guardian_retains_same_handle_and_lock_until_retry_reaps(launch_env, monkeypatch, failure):
    env = launch_env
    env.record.publish.side_effect = OSError
    env.child.term_works = False
    env.child.kill_works = False
    if failure == "term":
        env.child.terminate.side_effect = PermissionError
    elif failure == "kill":
        env.child.kill.side_effect = PermissionError
    elif failure == "interruption":
        env.child.wait.side_effect = KeyboardInterrupt
    observed = []
    def retry(_):
        # Release the fake child before anything fallible. Production guardian
        # correctly catches interruption/assertion errors and keeps ownership.
        env.child.alive = False
        env.child.wait.side_effect = env.child._wait
        observed.append(ready(env))
    monkeypatch.setattr(identity.time, "sleep", retry)
    assert env.launch.run() == 2
    assert observed == [identity.SpawnReady("retained", child_pid=env.child.pid, guardian_pid=os.getpid())]
    assert not env.child.alive
    assert env.launch.child is env.child and env.launch.ready_fd is None


def test_broken_readiness_converges_on_cleanup_without_second_message(launch_env):
    env = launch_env
    os.close(env.read_fd)
    env.read_fd = os.dup(0)  # fixture teardown owns a valid replacement descriptor
    assert env.launch.run() == 2
    assert not env.child.alive and env.child.wait.called
    assert env.launch.ready_attempted and env.launch.ready_fd is None


def test_signal_requests_ignore_hup_and_route_term_to_cleanup(launch_env):
    env = launch_env
    originals = {sig: signal.getsignal(sig) for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT, signal.SIGQUIT)}
    with env.launch._signal_requests():
        assert signal.getsignal(signal.SIGHUP) == signal.SIG_IGN
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        assert env.launch.interrupted
    assert all(signal.getsignal(sig) == handler for sig, handler in originals.items())


@pytest.mark.parametrize("data", [b"", b"published 0\n", b"published -1\n", b"published 2", b"published 2\nextra", b"published 2147483648\n", b"retained 3 3\n", b"retained 3 4 5\n", b"failed-cleanup-confirmed extra\n", b"x" * 97])
def test_readiness_rejects_malformed_and_eof(data):
    with pytest.raises(identity.UnsafeRecord):
        identity.parse_spawn_ready(data)


@pytest.mark.parametrize("value", [True, -1, float("inf"), float("nan"), 31])
def test_cleanup_timing_is_finite_bounded(value):
    with pytest.raises(identity.UnsafeRecord):
        identity._bounded_seconds(value, 30)


def test_cli_does_not_echo_secret_arguments(capsys):
    assert identity.main(["spawn", "--not-an-option", "secret-marker"]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "secret-marker" not in captured.err


def test_cli_rejects_non_pipe_readiness_before_spawn(tmp_path, monkeypatch):
    popen = Mock(side_effect=AssertionError("must not spawn"))
    monkeypatch.setattr(identity.subprocess, "Popen", popen)
    with open(tmp_path / "not-a-pipe", "wb") as stream:
        assert identity.main(["spawn", "--pid-file", str(tmp_path / "p"), "--service", "fixture", "--lock-fd", "200", "--ready-fd", str(stream.fileno()), "--log-file", str(tmp_path / "l"), "--", "fixture"]) == 2
    popen.assert_not_called()


@pytest.mark.parametrize("failing_write", [1, 2])
def test_actual_record_write_failure_preserves_partial_evidence_and_reaps(launch_env, tmp_path, monkeypatch, failing_write):
    env = launch_env
    info = {"pid": env.child.pid, "boot_id": "00000000-0000-0000-0000-000000000001", "start_ticks": 10, "uid": os.getuid(), "parent_pid": os.getpid(), "state": "S"}
    monkeypatch.setattr(identity, "process_info", lambda *a, **k: info if env.child.alive else None)
    with identity.LifecycleRecord(tmp_path / "actual.pid", "fixture") as record:
        env.launch.record = record
        original = record._atomic_write
        count = 0
        def write(target, data, expected):
            nonlocal count
            count += 1
            if count == failing_write:
                raise OSError("secret-marker")
            return original(target, data, expected)
        monkeypatch.setattr(record, "_atomic_write", write)
        assert env.launch.run() == 2
        assert ready(env).outcome == "failed-cleanup-confirmed"
        assert not env.child.alive
        assert record.path.exists() is (failing_write == 2)
        assert not record.identity_path.exists()


def test_replaced_publication_is_not_erased_during_child_cleanup(launch_env):
    env = launch_env
    env.record.inspect.side_effect = [identity.Inspection(identity.DEAD), identity.Inspection(identity.UNSAFE)]
    env.record.cleanup.side_effect = [True, False]
    assert env.launch.run() == 2
    assert ready(env).outcome == "failed-cleanup-confirmed"
    assert env.record.cleanup.call_args.args == (env.publication,)
    assert not env.child.alive


def test_log_open_failure_does_not_spawn_or_echo_payload(launch_env, monkeypatch, capsys):
    env = launch_env
    monkeypatch.setattr("builtins.open", Mock(side_effect=OSError("secret-marker")))
    assert env.launch.run() == 2
    assert ready(env).outcome == "failed-cleanup-confirmed"
    env.popen.assert_not_called()
    assert "secret-marker" not in str(capsys.readouterr())


def test_handoff_remains_committed_after_signal_context_restore_exception(launch_env, tmp_path, monkeypatch):
    from contextlib import contextmanager

    env = launch_env
    @contextmanager
    def restore_failure(self):
        try:
            yield
        finally:
            raise KeyboardInterrupt
    monkeypatch.setattr(identity.OwnedLaunch, "_signal_requests", restore_failure)
    manager = Mock()
    manager.__enter__ = Mock(return_value=env.record)
    manager.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(identity, "LifecycleRecord", Mock(return_value=manager))
    read_fd, ready_fd = os.pipe()
    try:
        assert identity.main(["spawn", "--pid-file", str(tmp_path / "p"), "--service", "fixture", "--lock-fd", "200", "--ready-fd", str(ready_fd), "--log-file", str(tmp_path / "l"), "--startup-delay", "0", "--", "fixture"]) == 0
        assert identity.parse_spawn_ready(os.read(read_fd, 128)).outcome == "published"
        assert env.child.alive
        env.child.terminate.assert_not_called()
    finally:
        os.close(read_fd)


def test_unconfirmed_dead_record_cleanup_blocks_spawn(launch_env):
    env = launch_env
    env.record.cleanup.return_value = False
    assert env.launch.run() == 2
    assert ready(env).outcome == "failed-cleanup-confirmed"
    env.popen.assert_not_called()


@pytest.mark.parametrize("field,value", [("argv", "fixture"), ("log_file", 1), ("cwd", True)])
def test_spawn_inputs_cannot_treat_paths_as_descriptors_or_text_as_argv(launch_env, field, value):
    env = launch_env
    values = {"argv": ["fixture"], "log_file": "fixture.log", "cwd": None}
    values[field] = value
    with pytest.raises(identity.UnsafeRecord):
        identity.OwnedLaunch(env.record, values.pop("argv"), ready_fd=env.launch.ready_fd, **values)
    env.popen.assert_not_called()
