"""Finite public gateway: mocked retained workers, no services or OS signals."""

import json
from types import SimpleNamespace

import pytest

from core import action_gateway, process_identity
from core import service_actions as actions


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    audit = tmp_path / 'audit.jsonl'
    monkeypatch.setattr(action_gateway, '_gateway', action_gateway.ActionGateway(audit))
    def records():
        return [json.loads(line) for line in audit.read_text().splitlines()] if audit.exists() else []
    return records


@pytest.mark.parametrize(('values', 'authority'), [
    (['lock-exec', 'all', 'start'], 'ACT'),
    (['lock-exec', 'all', 'restart'], 'ACT'),
    (['lock-exec', 'daemon', 'reload'], 'ACT'),
    (['lock-exec', 'llama-server-8080', 'stop'], 'ACT'),
    (['lock-exec', 'daemon', 'preflight'], 'READ'),
    (['status', 'all'], 'READ'), (['logs', 'daemon'], 'READ'),
    (['config-create'], 'ACT'), (['config-show'], 'READ'),
    (['daemon-status'], 'READ'),
])
def test_finite_operations_one_actual_worker_one_audit(monkeypatch, isolated, values, authority):
    calls = []
    def popen(argv, **options):
        assert isolated() == []
        calls.append((argv, options))
        return SimpleNamespace(wait=lambda: 0)
    monkeypatch.setattr(actions.subprocess, 'Popen', popen)
    assert actions.run_public(values) == 0
    assert calls == [([actions.sys.executable, '-c', actions._WORKER_BOOTSTRAP, str(actions._REPO_ROOT), *values], {'close_fds': True})]
    assert len(isolated()) == 1
    assert isolated()[0]['authority'] == authority
    assert isolated()[0]['outcome'] == 'allowed'


@pytest.mark.parametrize('result', [1, 2, 7, -9])
def test_nonzero_preserves_process_status_and_failed_audit(monkeypatch, isolated, result):
    monkeypatch.setattr(actions.subprocess, 'Popen', lambda *a, **k: SimpleNamespace(wait=lambda: result))
    assert actions.run_public(['lock-exec', 'all', 'restart']) == (128 - result if result < 0 else result)
    assert isolated()[0]['outcome'] == 'failed'
    assert 'Partial effects possible' in isolated()[0]['reason']


@pytest.mark.parametrize('interruption', [KeyboardInterrupt(), SystemExit(77), OSError('sensitive-private-payload')])
def test_interrupted_wait_retains_actual_worker_until_exit(monkeypatch, isolated, interruption):
    calls = []
    def wait():
        calls.append('wait')
        assert isolated() == []
        if len(calls) == 1:
            raise interruption
        return 0
    monkeypatch.setattr(actions.subprocess, 'Popen', lambda *a, **k: SimpleNamespace(wait=wait, poll=lambda: None))
    monkeypatch.setattr(actions.time, 'sleep', lambda _: None)
    assert actions.run_public(['lock-exec', 'all', 'stop']) != 0
    assert calls == ['wait', 'wait']
    assert isolated()[0]['outcome'] == 'failed'
    assert 'sensitive-private-payload' not in json.dumps(isolated())


def test_spawn_error_does_not_leak_arguments_or_exception(monkeypatch, isolated):
    def popen(*a, **k):
        raise OSError('secret path and token')
    monkeypatch.setattr(actions.subprocess, 'Popen', popen)
    assert actions.run_public(['status', 'all']) == 2
    assert isolated()[0]['outcome'] == 'failed'
    assert 'secret' not in json.dumps(isolated())


@pytest.mark.parametrize('values', [[], ['lock-exec', 'all', 'arbitrary'], ['status', 'unknown'], ['config-show', 'payload'], ['-c', 'arbitrary']])
def test_invalid_selectors_cannot_reach_gateway_or_process(monkeypatch, isolated, values):
    def forbidden(*a, **k):
        pytest.fail('invalid selector executed')
    monkeypatch.setattr(actions.subprocess, 'Popen', forbidden)
    with pytest.raises((ValueError, process_identity.UnsafeRecord)):
        actions.run_public(values)
    assert isolated() == []


def test_refusal_cannot_spawn(monkeypatch, isolated):
    monkeypatch.setattr(action_gateway, 'get_action_gateway', lambda: SimpleNamespace(gate_exec=lambda **k: SimpleNamespace(allowed=False, outcome='refused')))
    monkeypatch.setattr(actions.subprocess, 'Popen', lambda *a, **k: pytest.fail('refused operation spawned'))
    assert actions.run_public(['lock-exec', 'all', 'start']) == 2


def test_signal_request_waits_and_restores_original_dispositions(monkeypatch, isolated):
    caught = lambda *_: None
    initial = {actions.signal.SIGINT: caught, actions.signal.SIGTERM: actions.signal.SIG_DFL, actions.signal.SIGHUP: actions.signal.SIG_IGN}
    installed = dict(initial)
    changes = []
    monkeypatch.setattr(actions.signal, 'getsignal', installed.__getitem__)
    def install(number, handler):
        installed[number] = handler
        changes.append((number, handler))
    monkeypatch.setattr(actions.signal, 'signal', install)
    def wait():
        assert isolated() == []
        installed[actions.signal.SIGTERM](actions.signal.SIGTERM, None)
        return 0
    monkeypatch.setattr(actions.subprocess, 'Popen', lambda *a, **k: SimpleNamespace(wait=wait))
    assert actions.run_public(['lock-exec', 'all', 'stop']) == 143
    assert installed == initial
    assert not any(number == actions.signal.SIGHUP for number, _ in changes)
    assert isolated()[0]['outcome'] == 'failed'
    assert 'disposition confirmed' in isolated()[0]['reason']


def test_combined_daemon_status_absence_is_one_failed_read(monkeypatch, isolated):
    from core import service_lifecycle
    displays = []
    monkeypatch.setattr(service_lifecycle, 'status', lambda service: displays.append(service) or 1)
    monkeypatch.setattr(actions, '_show_daemon_models', lambda: displays.append('models'))
    def popen(*args, **kwargs):
        return SimpleNamespace(wait=lambda: actions._worker_main(['daemon-status']))
    monkeypatch.setattr(actions.subprocess, 'Popen', popen)
    assert actions.run_public(['daemon-status']) == 1
    assert displays == ['daemon', 'models']
    assert len(isolated()) == 1
    assert isolated()[0]['authority'] == 'READ'
    assert isolated()[0]['outcome'] == 'failed'


def test_config_display_recursively_redacts_secrets(monkeypatch, tmp_path, capsys):
    from utils import config
    monkeypatch.setattr(config, 'get_config_file_path', lambda: tmp_path / 'config.json')
    monkeypatch.setattr(config, 'get_cloudflare_tunnel_token', lambda: 'token-never-print')
    monkeypatch.setattr(config, 'get_restoricon_api_config', lambda: {'port': 8770})
    monkeypatch.setattr(config, 'get_aigentik_config', lambda: {'port': 8000})
    monkeypatch.setattr(config, 'load_user_config', lambda: {'nested': [{'API_KEY': 'private-key'}], 'secret': 'private-secret', 'normal': 'visible'})
    assert actions._worker_main(['config-show']) == 0
    output = capsys.readouterr().out
    assert 'visible' in output and 'configured' in output and '***redacted***' in output
    assert all(value not in output for value in ('token-never-print', 'private-key', 'private-secret'))


def test_worker_failure_is_static_and_preserves_nonzero(monkeypatch, capsys):
    from core import service_lifecycle
    def failure(*_):
        raise OSError('private path and token')
    monkeypatch.setattr(service_lifecycle, 'status', failure)
    assert actions._worker_main(['status', 'all']) == 2
    assert 'private path' not in capsys.readouterr().err
