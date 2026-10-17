"""NEW969: synthetic proc and resource stores; no process or network effects."""
import os
import signal
from types import SimpleNamespace

import pytest

from core import loader_v2 as loader
from core import process_identity as identity
from core import resource_gate as rg


@pytest.fixture
def fake(tmp_path, monkeypatch):
    def forbidden(*a, **k):
        pytest.fail('real process/network effect forbidden')
    monkeypatch.setattr(loader.os, 'kill', forbidden)
    monkeypatch.setattr(loader.os, 'killpg', forbidden)
    monkeypatch.setattr(loader.os, 'getpgid', forbidden)
    monkeypatch.setattr(loader.subprocess, 'Popen', forbidden)
    monkeypatch.setattr(loader.urllib.request, 'urlopen', forbidden)
    root = tmp_path / 'proc'
    boot = root / 'sys/kernel/random/boot_id'
    boot.parent.mkdir(parents=True)
    boot.write_text('11111111-2222-3333-4444-555555555555')
    pid = 32123
    directory = root / str(pid)
    directory.mkdir()
    executable, model = tmp_path / 'llama-server', tmp_path / 'primary.gguf'
    executable.touch(); model.touch()
    (directory / 'exe').symlink_to(executable)
    (directory / 'cwd').symlink_to(tmp_path)
    def proc(*, start=100, uid=None, state='S'):
        uid = os.getuid() if uid is None else uid
        fields = [state, str(os.getpid())] + ['0'] * 17 + [str(start)]
        (directory / 'stat').write_text(f'{pid} (fixture ) command) ' + ' '.join(fields))
        (directory / 'status').write_text(f'Uid:\t{uid}\t{uid}\t{uid}\t{uid}\n')
    def argv(values=None):
        values = values or [str(executable), '-m', str(model), '--port', '8080', '-c', '16384']
        (directory / 'cmdline').write_bytes(b'\0'.join(os.fsencode(value) for value in values) + b'\0')
    proc(); argv()
    monkeypatch.setattr(loader, 'LLAMA_SERVER_BIN', executable)
    actual_info = identity.process_info
    # Every production read, including default-/proc callers, is redirected
    # before helper invocation. No placeholder PID can reach the live proc tree.
    monkeypatch.setattr(identity, 'process_info', lambda candidate, *_: actual_info(candidate, root))
    actual_capture = loader._capture_foreign_primary
    monkeypatch.setattr(loader, '_capture_foreign_primary', lambda *a, **k: actual_capture(*a, **{**k, 'proc_root': root}))
    calls = []
    monkeypatch.setattr(loader.os, 'kill', lambda candidate, requested: calls.append((candidate, requested)))
    clock = [0.0]
    monkeypatch.setattr(loader.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(loader.time, 'sleep', lambda duration: clock.__setitem__(0, clock[0] + duration))
    item = SimpleNamespace(root=root, directory=directory, pid=pid, executable=executable, model=model, proc=proc, argv=argv, calls=calls, clock=clock)
    item.capture = lambda: loader._capture_foreign_primary(pid, model, 8080, lambda: (pid, 16384), 65536)
    return item


@pytest.mark.parametrize('pid', [True, False, 0, 1, -1, 2**31, '32123'])
def test_invalid_candidate_never_signalled(fake, pid):
    assert loader._capture_foreign_primary(pid, fake.model, 8080, lambda: (pid, 1), 65536) is None
    assert loader._kill_single_pid_term_then_kill(pid).outcome == 'unsafe'
    assert fake.calls == []


@pytest.mark.parametrize('bad', ['exe', 'model', 'port', 'duplicate-model', 'missing-port', 'foreign-uid', 'identity-missing', 'malformed'])
def test_stale_slot_cannot_bless_unrelated_current_process(fake, bad):
    values = [str(fake.executable), '-m', str(fake.model), '--port', '8080']
    if bad == 'exe':
        (fake.directory / 'exe').unlink(); (fake.directory / 'exe').symlink_to(fake.model)
    elif bad == 'model': values[2] = str(fake.executable)
    elif bad == 'port': values[-1] = '8081'
    elif bad == 'duplicate-model': values += ['--model=' + str(fake.model)]
    elif bad == 'missing-port': values = values[:3]
    elif bad == 'foreign-uid': fake.proc(uid=os.getuid() + 1)
    elif bad == 'identity-missing': (fake.directory / 'stat').unlink()
    elif bad == 'malformed': values[-1] = '+8080'
    fake.argv(values)
    assert fake.capture() is None
    assert fake.calls == []


def test_capture_brackets_fresh_context_and_identity(fake):
    def resolve():
        fake.proc(start=101)
        return fake.pid, 16384
    assert loader._capture_foreign_primary(fake.pid, fake.model, 8080, resolve, 65536) is None
    assert fake.calls == []


@pytest.mark.parametrize('fresh', [(32123, 65536), (32123, None), (54321, 16384)])
def test_fresh_eligible_context_required(fake, fresh):
    assert loader._capture_foreign_primary(fake.pid, fake.model, 8080, lambda: fresh, 65536) is None


@pytest.mark.parametrize('change', ['exit', 'zombie', 'replacement', 'permission', 'timeout'])
def test_identity_checked_after_term_before_any_escalation(fake, monkeypatch, change):
    expected = fake.capture()
    def kill(pid, requested):
        fake.calls.append((pid, requested))
        if requested == signal.SIGTERM:
            if change == 'exit':
                (fake.directory / 'stat').unlink()
                # A proc directory remaining without stat is uncertain, not absent.
                (fake.directory / 'status').unlink(); (fake.directory / 'exe').unlink()
                (fake.directory / 'cwd').unlink(); (fake.directory / 'cmdline').unlink(); fake.directory.rmdir()
            elif change == 'zombie': fake.proc(state='Z')
            elif change == 'replacement': fake.proc(start=101)
            elif change == 'permission':
                monkeypatch.setattr(identity, 'process_info', lambda *_: (_ for _ in ()).throw(PermissionError()))
    monkeypatch.setattr(loader.os, 'kill', kill)
    result = loader._kill_single_pid_term_then_kill(fake.pid, wait_s=.4, expected=expected)
    assert result.attempted
    assert result.outcome == ('exited' if change in ('exit', 'zombie') else 'unconfirmed')
    assert [requested for _, requested in fake.calls] == ([signal.SIGTERM, signal.SIGKILL] if change == 'timeout' else [signal.SIGTERM])
    assert fake.clock[0] <= .8 + .0001


def test_replacement_before_term_never_signalled(fake):
    expected = fake.capture(); fake.proc(start=101)
    result = loader._kill_single_pid_term_then_kill(fake.pid, expected=expected)
    assert result.outcome == 'unsafe' and not result.attempted and result.replaced
    assert fake.calls == []


def test_escalation_confirms_original_exit(fake, monkeypatch):
    expected = fake.capture()
    def kill(pid, requested):
        fake.calls.append((pid, requested))
        if requested == signal.SIGKILL: fake.proc(state='Z')
    monkeypatch.setattr(loader.os, 'kill', kill)
    result = loader._kill_single_pid_term_then_kill(fake.pid, wait_s=.4, expected=expected)
    assert result.outcome == 'exited'
    assert fake.calls == [(fake.pid, signal.SIGTERM), (fake.pid, signal.SIGKILL)]


@pytest.mark.parametrize('change', [None, 'pid', 'slot_id', 'model_id', 'port', 'n_ctx', 'missing'])
def test_conditional_release_compares_entire_original_under_one_lock(tmp_path, change):
    original = {'slot_id': 'original', 'pid': 32123, 'model_id': 'primary', 'port': 8080, 'n_ctx': 16384}
    current = dict(original)
    if change and change != 'missing': current[change] = 'replacement'
    with rg._LockedState(tmp_path) as slots:
        slots[:] = [] if change == 'missing' else [current]
    assert rg.release_slot_if_unchanged(original, tmp_path) is (change is None)
    with rg._LockedState(tmp_path) as slots:
        assert slots == ([] if change in (None, 'missing') else [current])


@pytest.mark.parametrize('failure', ['unsafe', 'unconfirmed', 'replaced', 'release-false', 'release-error', 'busy-port', 'success'])
def test_upgrade_caller_retains_accounting_on_uncertainty(fake, monkeypatch, failure):
    from core import daemon
    monkeypatch.setattr(daemon, 'daemon_task_in_progress', lambda: False)
    server = loader.LlamaServer(fake.model, port=8080, n_ctx=65536, allow_upgrade=True)
    monkeypatch.setattr(server, '_resolve_resident_pid_and_n_ctx', lambda: (fake.pid, 16384))
    original = {'slot_id': 'old', 'pid': fake.pid, 'model_id': 'primary', 'port': 8080, 'n_ctx': 16384}
    monkeypatch.setattr(rg, 'find_resident_slot', lambda **_: dict(original))
    released = []
    def release(row, **_):
        released.append(row)
        if failure == 'release-error': raise OSError('fixture')
        return failure != 'release-false'
    monkeypatch.setattr(rg, 'release_slot_if_unchanged', release)
    def stop(*a, **k):
        if failure == 'unsafe': return loader.ForeignStopOutcome('unsafe')
        if failure == 'unconfirmed': return loader.ForeignStopOutcome('unconfirmed', True)
        if failure == 'replaced':
            fake.proc(start=101)
            return loader.ForeignStopOutcome('exited', True, True)
        fake.proc(state='Z')
        return loader.ForeignStopOutcome('exited', True)
    monkeypatch.setattr(loader, '_kill_single_pid_term_then_kill', stop)
    monkeypatch.setattr(server, '_is_port_in_use', lambda: failure == 'busy-port')
    time_values = iter([0., 0., 11.])
    monkeypatch.setattr(loader.time, 'time', lambda: next(time_values, 11.))
    result = server._upgrade_resident_if_safe(16384)
    expected = loader._UPGRADE_NOT_SAFE if failure == 'unsafe' else loader._UPGRADE_KILLED if failure == 'success' else loader._UPGRADE_PORT_STUCK
    assert result == expected
    assert released == ([original] if failure in ('success', 'release-false', 'release-error') else [])


@pytest.mark.parametrize('kind', ['boot', 'uid', 'start'])
def test_each_signal_is_bound_to_immutable_generation(fake, kind):
    expected = fake.capture()
    assert expected is not None
    if kind == 'boot':
        (fake.root / 'sys/kernel/random/boot_id').write_text('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
    elif kind == 'uid': fake.proc(uid=os.getuid() + 1)
    else: fake.proc(start=101)
    result = loader._kill_single_pid_term_then_kill(fake.pid, expected=expected)
    assert result.outcome == 'unsafe' and fake.calls == []


def test_actual_start_does_not_spawn_or_release_after_unconfirmed_foreign_stop(fake, monkeypatch):
    from core import daemon
    monkeypatch.setattr(daemon, 'daemon_task_in_progress', lambda: False)
    monkeypatch.setattr(loader, 'CODEY_STATE_DIR', fake.root.parent / 'isolated-state')
    server = loader.LlamaServer(fake.model, port=8080, n_ctx=65536, allow_upgrade=True)
    monkeypatch.setattr(server, '_resolve_resident_pid_and_n_ctx', lambda: (fake.pid, 16384))
    monkeypatch.setattr(server, '_is_port_in_use', lambda: True)
    monkeypatch.setattr(server, '_check_health', lambda: True)
    row = {'slot_id': 'old', 'pid': fake.pid, 'model_id': 'primary', 'port': 8080, 'n_ctx': 16384}
    monkeypatch.setattr(rg, 'find_resident_slot', lambda **_: dict(row))
    monkeypatch.setattr(rg, 'release_slot_if_unchanged', lambda *_, **__: pytest.fail('uncertain exit released accounting'))
    assert server.start() is False
    assert server.process is None and not server._started
    assert fake.calls == [(fake.pid, signal.SIGTERM), (fake.pid, signal.SIGKILL)]


@pytest.mark.parametrize('requested', [True, -1, float('inf'), float('nan')])
def test_bad_wait_budget_is_refused_before_any_signal(fake, requested):
    expected = fake.capture()
    assert loader._kill_single_pid_term_then_kill(fake.pid, requested, expected=expected).outcome == 'unsafe'
    assert fake.calls == []


def test_conditional_release_preserves_same_numeric_different_type_row(tmp_path):
    original = {'slot_id': 'original', 'pid': 32123, 'model_id': 'primary', 'port': 8080, 'cost': 1}
    replacement = {**original, 'cost': True}
    with rg._LockedState(tmp_path) as slots:
        slots[:] = [replacement]
    assert rg.release_slot_if_unchanged(original, tmp_path) is False
    with rg._LockedState(tmp_path) as slots:
        assert slots == [replacement]


def test_replacement_in_final_term_poll_never_receives_kill(fake, monkeypatch):
    expected = fake.capture()
    states = iter(['running', 'running', 'replaced'])
    monkeypatch.setattr(loader, '_foreign_state', lambda *_: next(states))
    result = loader._kill_single_pid_term_then_kill(fake.pid, wait_s=0, expected=expected)
    assert result.outcome == 'unconfirmed' and result.replaced
    assert fake.calls == [(fake.pid, signal.SIGTERM)]


@pytest.mark.parametrize('problem', [PermissionError, ProcessLookupError])
def test_signal_error_is_not_exit_confirmation(fake, monkeypatch, problem):
    expected = fake.capture()
    def kill(*args):
        fake.calls.append(args)
        raise problem()
    monkeypatch.setattr(loader.os, 'kill', kill)
    result = loader._kill_single_pid_term_then_kill(fake.pid, wait_s=0, expected=expected)
    assert result.outcome == 'unconfirmed' and result.attempted
    assert len(fake.calls) == (1 if problem is PermissionError else 2)


def test_accounting_write_failure_preserves_original_row(tmp_path, monkeypatch):
    original = {'slot_id': 'old', 'pid': 32123, 'model_id': 'primary', 'port': 8080}
    with rg._LockedState(tmp_path) as slots:
        slots[:] = [original]
    # Failure at the atomic persistence layer must not masquerade as release.
    def fail(*_):
        raise OSError('injected state write failure')
    with monkeypatch.context() as patch:
        patch.setattr(rg, '_write_state_locked', fail)
        with pytest.raises(OSError):
            rg.release_slot_if_unchanged(original, tmp_path)
    with rg._LockedState(tmp_path) as slots:
        assert slots == [original]


def _seed_row(tmp_path, pid):
    original = {'slot_id': 'old', 'pid': pid, 'model_id': 'primary', 'port': 8080, 'n_ctx': 16384}
    with rg._LockedState(tmp_path) as slots:
        slots[:] = [original]
    return original


def _rows(tmp_path):
    with rg._LockedState(tmp_path) as slots:
        return list(slots)


def _dead_proc(fake):
    fake.proc(state='Z')


@pytest.mark.parametrize('change', ['replaced', 'unsafe'])
def test_identity_change_while_lock_held_preserves_row(fake, tmp_path, monkeypatch, change):
    expected = fake.capture()
    state = tmp_path / 'state'
    original = _seed_row(state, fake.pid)
    held = []
    def confirm():
        # Runs inside _LockedState: mutate the fake proc tree as a contended
        # lock delaying the check across PID reuse would.
        held.append(True)
        if change == 'replaced':
            fake.proc(start=101)
        else:
            fake.proc(uid=os.getuid() + 1)
            monkeypatch.setattr(identity, 'process_info', lambda *_: (_ for _ in ()).throw(PermissionError()))
        return loader._foreign_state(expected) == 'dead'
    assert rg.release_slot_if_unchanged(original, state, confirm_dead=confirm) is False
    assert held == [True] and _rows(state) == [original]


@pytest.mark.parametrize('change', ['replaced', 'unsafe'])
def test_loader_refuses_respawn_when_identity_changes_under_lock(fake, tmp_path, monkeypatch, change):
    from core import daemon
    monkeypatch.setattr(daemon, 'daemon_task_in_progress', lambda: False)
    state = tmp_path / 'state'
    original = _seed_row(state, fake.pid)
    server = loader.LlamaServer(fake.model, port=8080, n_ctx=65536, allow_upgrade=True)
    monkeypatch.setattr(server, '_resolve_resident_pid_and_n_ctx', lambda: (fake.pid, 16384))
    monkeypatch.setattr(server, '_is_port_in_use', lambda: False)
    monkeypatch.setattr(rg, 'find_resident_slot', lambda **_: dict(original))
    real_release = rg.release_slot_if_unchanged
    monkeypatch.setattr(rg, 'release_slot_if_unchanged', lambda row, **k: real_release(row, state, **k))
    calls = [0]
    real_state = loader._foreign_state
    def flaky_state(expected, *a):
        # Pre-lock check sees dead; the in-lock re-check sees the change.
        calls[0] += 1
        if calls[0] <= 1:
            return 'dead'
        if change == 'replaced':
            fake.proc(start=101)
        else:
            monkeypatch.setattr(identity, 'process_info', lambda *_: (_ for _ in ()).throw(PermissionError()))
        return real_state(expected, *a)
    monkeypatch.setattr(loader, '_foreign_state', flaky_state)
    def stop(pid, *a, **k):
        _dead_proc(fake)
        return loader.ForeignStopOutcome('exited', True)
    monkeypatch.setattr(loader, '_kill_single_pid_term_then_kill', stop)
    assert server._upgrade_resident_if_safe(16384) == loader._UPGRADE_PORT_STUCK
    assert _rows(state) == [original]


def test_dead_under_lock_removes_row(fake, tmp_path):
    expected = fake.capture()
    state = tmp_path / 'state'
    original = _seed_row(state, fake.pid)
    _dead_proc(fake)
    assert rg.release_slot_if_unchanged(original, state, confirm_dead=lambda: loader._foreign_state(expected) == 'dead') is True
    assert _rows(state) == []


@pytest.mark.parametrize('result', ['raise', None, 1, 'dead'])
def test_confirm_dead_error_or_non_true_preserves_row(tmp_path, result):
    state = tmp_path / 'state'
    original = _seed_row(state, 32123)
    def confirm():
        if result == 'raise':
            raise OSError('fixture')
        return result
    assert rg.release_slot_if_unchanged(original, state, confirm_dead=confirm) is False
    assert _rows(state) == [original]
