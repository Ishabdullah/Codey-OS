"""Durable identities: isolated proc records and disposable owned children."""

import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import process_identity as identity

BOOT = "11111111-2222-3333-4444-555555555555"


def proc_entry(root, pid, *, parent=None, start=100, uid=None, state="S", command="fixture"):
    parent = os.getpid() if parent is None else parent
    uid = os.getuid() if uid is None else uid
    directory = root / str(pid)
    directory.mkdir(parents=True, exist_ok=True)
    fields = [state, str(parent)] + ["0"] * 17 + [str(start)]
    (directory / "stat").write_text(f"{pid} ({command}) " + " ".join(fields))
    (directory / "status").write_text(f"Name:\tfixture\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")


@pytest.fixture
def env(tmp_path):
    proc = tmp_path / "proc"
    boot = proc / "sys/kernel/random/boot_id"
    boot.parent.mkdir(parents=True)
    boot.write_text(BOOT + "\n")
    pid = 32123
    proc_entry(proc, pid)
    return SimpleNamespace(root=tmp_path, proc=proc, pid=pid, path=tmp_path / "service.pid")


def locked(env, **kwargs):
    return identity.LifecycleRecord(env.path, "fixture", proc_root=env.proc, **kwargs)


@pytest.mark.parametrize("payload", [b"", b"0", b"1", b"-2", b"+2", b" 2", b"2 ", b"2\t", b"2\n\n", b"True", b"1.5", b"2147483648", b"99999999999999999999999", b"02", b"--1"])
def test_bad_pid_grammar_refused(env, payload):
    env.path.write_bytes(payload)
    with locked(env) as record:
        assert record.inspect().state == identity.UNSAFE
        assert not record.cleanup()
    assert env.path.read_bytes() == payload


@pytest.mark.parametrize("pid", [None, True, False, 0, 1, -2, "32123", 1.5, 2**31])
def test_publication_rejects_invalid_pid_types_and_bounds(env, pid):
    with locked(env) as record, pytest.raises(identity.UnsafeRecord):
        record.publish(pid)
    assert not env.path.exists()


def test_stat_parses_after_final_parenthesis_and_preserves_exact_fields(env):
    proc_entry(env.proc, env.pid, command="spaces ) and (nested) parentheses)", start=987654321)
    details = identity.process_info(env.pid, env.proc)
    assert details["start_ticks"] == 987654321
    assert details["parent_pid"] == os.getpid()
    with locked(env) as record:
        published = record.publish(env.pid)
        assert published.state == identity.RUNNING
        assert record.inspect() == published
        assert set(published.identity) == {"version", "service", "pid", "boot_id", "start_ticks", "uid"}
        assert env.path.read_text() == str(env.pid)
        assert published.identity["start_ticks"] == 987654321


@pytest.mark.parametrize("change", [
    {"version": True}, {"version": 2}, {"service": "other"}, {"pid": True},
    {"pid": 1}, {"pid": 32124}, {"uid": True}, {"uid": -1},
    {"start_ticks": True}, {"start_ticks": -1}, {"start_ticks": 2**64},
    {"boot_id": "malformed"}, {"extra": "forbidden"},
])
def test_bad_identity_fields_preserve_records_and_never_signal(env, monkeypatch, change):
    with locked(env) as record:
        published = record.publish(env.pid)
        altered = {**published.identity, **change}
        record.identity_path.write_text(json.dumps(altered))
        kill = Mock()
        monkeypatch.setattr(identity.os, "kill", kill)
        assert record.inspect().state == identity.UNSAFE
        assert record.signal(signal.SIGUSR1) == identity.UNSAFE
        assert record.stop(0) == identity.UNSAFE
        assert not record.cleanup()
        kill.assert_not_called()
        assert record.identity_path.exists() and env.path.exists()


@pytest.mark.parametrize("contents", [b"{}", b"[]", b"null", b"{", b"x" * 2049])
def test_malformed_or_oversized_identity_is_unsafe(env, contents):
    env.path.write_text(str(env.pid))
    Path(str(env.path) + ".identity").write_bytes(contents)
    with locked(env) as record:
        assert record.inspect().state == identity.UNSAFE
        assert not record.cleanup()


@pytest.mark.parametrize("field", ["version", "service", "pid", "boot_id", "start_ticks", "uid"])
def test_missing_identity_field_is_unsafe(env, field):
    with locked(env) as record:
        published = record.publish(env.pid)
        altered = dict(published.identity)
        del altered[field]
        record.identity_path.write_text(json.dumps(altered))
        assert record.inspect().state == identity.UNSAFE


def test_duplicate_json_fields_are_rejected(env):
    with locked(env) as record:
        published = record.publish(env.pid)
        data = json.dumps(published.identity)
        record.identity_path.write_text(data[:-1] + ', "pid": 32123}')
        assert record.inspect().state == identity.UNSAFE


@pytest.mark.parametrize("changed", ["boot", "start", "uid"])
def test_live_identity_mismatch_is_unsafe_not_a_pid_to_signal(env, monkeypatch, changed):
    with locked(env) as record:
        record.publish(env.pid)
        if changed == "boot":
            (env.proc / "sys/kernel/random/boot_id").write_text("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        else:
            proc_entry(env.proc, env.pid, start=101 if changed == "start" else 100,
                       uid=os.getuid() + 1 if changed == "uid" else os.getuid())
        kill = Mock()
        monkeypatch.setattr(identity.os, "kill", kill)
        assert record.inspect().state == identity.UNSAFE
        assert record.signal(signal.SIGTERM) == identity.UNSAFE
        assert record.stop(0) == identity.UNSAFE
        kill.assert_not_called()
        assert env.path.exists()


@pytest.mark.parametrize("which", ["pid", "identity", "lock"])
def test_symlink_records_or_lock_are_rejected(env, which):
    target = env.root / "foreign"
    target.write_text("preserve")
    if which == "lock":
        Path(str(env.path) + ".lifecycle.lock").symlink_to(target)
        with pytest.raises(identity.UnsafeRecord), locked(env):
            pass
    else:
        with locked(env) as record:
            record.publish(env.pid)
            path = env.path if which == "pid" else record.identity_path
            path.unlink()
            path.symlink_to(target)
            assert record.inspect().state == identity.UNSAFE
            assert not record.cleanup()
    assert target.read_text() == "preserve"


def test_pid_fifo_is_rejected_without_blocking(env):
    os.mkfifo(env.path)
    with locked(env) as record:
        assert record.inspect().state == identity.UNSAFE
        assert not record.cleanup()


def test_missing_and_inaccessible_proc_identity_fail_closed(env, monkeypatch):
    with locked(env) as record:
        record.publish(env.pid)
        stat_path = env.proc / str(env.pid) / "stat"
        read = Path.read_text

        def denied(path, *args, **kwargs):
            if path == stat_path:
                raise PermissionError("fixture proc denied")
            return read(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", denied)
        assert record.inspect().state == identity.UNSAFE
        assert not record.cleanup()


def test_legacy_live_pid_is_unsafe_but_confirmed_dead_legacy_can_retire(env):
    env.path.write_text(str(env.pid) + "\n")
    with locked(env) as record:
        assert record.inspect().state == identity.UNSAFE
        assert not record.cleanup()
        shutil.rmtree(env.proc / str(env.pid))
        observed = record.inspect()
        assert observed.state == identity.DEAD and observed.legacy
        assert record.cleanup(observed)
        assert not env.path.exists()
        assert record.inspect().state == identity.DEAD


@pytest.mark.parametrize("state", ["Z", "X"])
def test_original_zombie_or_exited_process_is_stopped_without_signal(env, monkeypatch, state):
    with locked(env) as record:
        published = record.publish(env.pid)
        proc_entry(env.proc, env.pid, state=state)
        kill = Mock()
        monkeypatch.setattr(identity.os, "kill", kill)
        assert record.inspect().state == identity.DEAD
        assert record.cleanup(published)
        kill.assert_not_called()
        assert not env.path.exists() and not record.identity_path.exists()


@pytest.mark.parametrize("replacement", ["pid", "identity"])
def test_cleanup_preserves_replaced_records_even_with_identical_content(env, replacement):
    with locked(env) as record:
        published = record.publish(env.pid)
        shutil.rmtree(env.proc / str(env.pid))
        target = env.path if replacement == "pid" else record.identity_path
        other = env.root / "replacement"
        other.write_bytes(target.read_bytes())
        other.replace(target)
        assert not record.cleanup(published)
        assert env.path.exists() and record.identity_path.exists()


def test_publication_refuses_unknown_process_parent_or_live_foreign_record(env):
    proc_entry(env.proc, env.pid, parent=999)
    with locked(env) as record, pytest.raises(identity.UnsafeRecord):
        record.publish(env.pid)
    proc_entry(env.proc, env.pid)
    with locked(env) as record:
        record.publish(env.pid)
        proc_entry(env.proc, env.pid + 1)
        with pytest.raises(identity.UnsafeRecord):
            record.publish(env.pid + 1)
        assert record.inspect().identity["pid"] == env.pid


def test_signal_revalidates_records_and_keeps_real_reload_signal(env, monkeypatch):
    with locked(env) as record:
        record.publish(env.pid)
        kill = Mock()
        monkeypatch.setattr(identity.os, "kill", kill)
        assert record.signal(signal.SIGUSR1) == identity.RUNNING
        kill.assert_called_once_with(env.pid, signal.SIGUSR1)
        before = record.inspect()
        calls = 0
        inspect = record.inspect

        def race():
            nonlocal calls
            calls += 1
            if calls == 2:
                record.identity_path.write_text("{}")
            return inspect()

        monkeypatch.setattr(record, "inspect", race)
        assert record.signal(signal.SIGTERM, expected=before) == identity.UNSAFE
        assert kill.call_count == 1


def test_stop_rechecks_original_identity_before_escalation(env, monkeypatch):
    with locked(env) as record:
        published = record.publish(env.pid)
        real_signal = record.signal
        kill = Mock()
        monkeypatch.setattr(identity.os, "kill", kill)
        another = {**published.identity, "start_ticks": 101}

        def signal_then_replace(number, expected=None):
            if number == signal.SIGKILL:
                proc_entry(env.proc, env.pid, start=101)
                record.identity_path.write_text(json.dumps(another))
            return real_signal(number, expected)

        monkeypatch.setattr(record, "signal", signal_then_replace)
        assert record.stop(timeout=0) == identity.UNSAFE
        kill.assert_called_once_with(env.pid, signal.SIGTERM)
        assert env.path.exists() and record.identity_path.exists()


def test_signal_permission_failure_preserves_identity(env, monkeypatch):
    with locked(env) as record:
        published = record.publish(env.pid)
        monkeypatch.setattr(identity.os, "kill", Mock(side_effect=PermissionError))
        assert record.stop(0) == identity.UNSAFE
        assert record.inspect() == published


def test_validated_inherited_lock_keeps_outer_lock_held(env):
    with locked(env) as outer:
        with locked(env, lock_fd=outer.fd) as adopted:
            assert adopted.inspect().state == identity.DEAD
        contender = os.open(outer.lock_path, os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(contender)


def test_inherited_fd_cannot_skip_a_different_or_conflicting_lock(env):
    with locked(env) as outer:
        unrelated = os.open(env.root / "unrelated", os.O_RDWR | os.O_CREAT, 0o600)
        conflict = os.open(outer.lock_path, os.O_RDWR)
        try:
            for descriptor in (unrelated, conflict):
                with pytest.raises(identity.UnsafeRecord), locked(env, lock_fd=descriptor):
                    pass
        finally:
            os.close(unrelated)
            os.close(conflict)


def test_lock_replacement_invalidates_context(env):
    with locked(env) as record:
        replacement = env.root / "replacement.lock"
        replacement.write_text("")
        replacement.replace(record.lock_path)
        assert record.inspect().state == identity.UNSAFE
        with pytest.raises(identity.UnsafeRecord):
            record.publish(env.pid)


@pytest.fixture
def child_factory():
    children = []

    def spawn(code="import time; time.sleep(60)"):
        child = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        children.append(child)
        return child

    try:
        yield spawn
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=2)
            else:
                child.wait(timeout=2)


def test_real_owned_child_publication_stop_and_unrelated_child_survives(tmp_path, child_factory):
    owned, unrelated = child_factory(), child_factory()
    path = tmp_path / "child.pid"
    with identity.LifecycleRecord(path, "fixture") as record:
        publication = record.publish(owned.pid)
        assert publication.state == identity.RUNNING
        assert record.stop(0.5) == identity.DEAD
        owned.wait(timeout=2)
        assert unrelated.poll() is None
        assert not path.exists() and not record.identity_path.exists()


def test_cli_sibling_child_publication_and_cross_process_stop(tmp_path, child_factory):
    child = child_factory()
    path = tmp_path / "child.pid"
    command = [sys.executable, identity.__file__]
    published = subprocess.run(command + ["record", str(path), "fixture", "--pid", str(child.pid)], capture_output=True, text=True, check=False)
    assert (published.returncode, published.stdout.strip()) == (0, identity.RUNNING)
    stopped = subprocess.run(command + ["stop", str(path), "fixture", "--timeout", "0.5"], capture_output=True, text=True, check=False)
    assert (stopped.returncode, stopped.stdout.strip()) == (0, identity.DEAD)
    child.wait(timeout=2)


def test_cli_refuses_publishing_its_parent_process(tmp_path):
    completed = subprocess.run(
        [sys.executable, identity.__file__, "record", str(tmp_path / "parent.pid"), "fixture", "--pid", str(os.getpid())],
        capture_output=True, text=True, check=False,
    )
    assert (completed.returncode, completed.stdout.strip()) == (2, identity.UNSAFE)


@pytest.mark.parametrize("descriptor", [True, -1, 2**100, "3"])
def test_invalid_inherited_lock_descriptor_cannot_bypass_lock(env, descriptor):
    with pytest.raises(identity.UnsafeRecord), locked(env, lock_fd=descriptor):
        pass


def test_partial_publication_failure_remains_unverifiable(env, monkeypatch):
    replace = identity.os.replace

    def fail_sidecar(source, target):
        if str(target).endswith(".identity"):
            raise PermissionError("fixture sidecar publication denied")
        return replace(source, target)

    with locked(env) as record:
        monkeypatch.setattr(identity.os, "replace", fail_sidecar)
        with pytest.raises(PermissionError):
            record.publish(env.pid)
        assert env.path.read_text() == str(env.pid)
        assert record.inspect().state == identity.UNSAFE
        assert not record.cleanup()
    assert list(env.root.glob(".identity-*")) == []


def test_nonblocking_shutdown_lock_attempt_preserves_held_lock(env):
    with locked(env) as outer:
        with pytest.raises(identity.UnsafeRecord), locked(env, blocking=False):
            pass
        assert outer.inspect().state == identity.DEAD


def test_signal_stops_if_identity_process_changes_during_revalidation(env, monkeypatch):
    with locked(env) as record:
        record.publish(env.pid)
        inspect = record.inspect
        calls = 0
        kill = Mock()
        monkeypatch.setattr(identity.os, "kill", kill)

        def race():
            nonlocal calls
            calls += 1
            if calls == 2:
                proc_entry(env.proc, env.pid, start=101)
            return inspect()

        monkeypatch.setattr(record, "inspect", race)
        assert record.signal(signal.SIGUSR1) == identity.UNSAFE
        kill.assert_not_called()


def test_helper_import_does_not_import_model_state_or_config(tmp_path):
    code = (
        "import importlib.util,sys; "
        f"s=importlib.util.spec_from_file_location('isolated_identity',{identity.__file__!r}); "
        "m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m); "
        "assert not any(n in sys.modules for n in ('utils.config','core.state','core.loader_v2','core.daemon'));print('stdlib-only')"
    )
    completed = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=False, cwd=tmp_path)
    assert (completed.returncode, completed.stdout.strip()) == (0, "stdlib-only")



def test_boolean_signal_never_authorizes_hup(env, monkeypatch):
    with locked(env) as record:
        record.publish(env.pid)
        kill = Mock()
        monkeypatch.setattr(identity.os, "kill", kill)
        assert record.signal(True) == identity.UNSAFE
        assert record.signal(False) == identity.UNSAFE
        kill.assert_not_called()


@pytest.mark.parametrize("argument", [" 32123", "+32123", "32123 ", "2147483648", "True"])
def test_cli_pid_argument_cannot_coerce_malformed_values(env, argument):
    with pytest.raises(SystemExit) as failure:
        identity.main(["record", str(env.path), "fixture", "--pid", argument])
    assert failure.value.code == 2
    assert not env.path.exists()


@pytest.mark.parametrize("requested_value", [1.0, "1", None])
def test_signal_requires_an_actual_integer_signal(env, monkeypatch, requested_value):
    with locked(env) as record:
        record.publish(env.pid)
        kill = Mock()
        monkeypatch.setattr(identity.os, "kill", kill)
        assert record.signal(requested_value) == identity.UNSAFE
        kill.assert_not_called()


def test_stop_escalates_only_verified_original_then_cleans_confirmed_exit(env, monkeypatch):
    with locked(env) as record:
        record.publish(env.pid)

        def ignore_term_then_exit(pid, requested_signal):
            assert pid == env.pid
            if requested_signal == signal.SIGKILL:
                proc_entry(env.proc, env.pid, state="Z")

        kill = Mock(side_effect=ignore_term_then_exit)
        monkeypatch.setattr(identity.os, "kill", kill)
        assert record.stop(timeout=0) == identity.DEAD
        assert [call.args for call in kill.call_args_list] == [
            (env.pid, signal.SIGTERM), (env.pid, signal.SIGKILL),
        ]
        assert not env.path.exists() and not record.identity_path.exists()
