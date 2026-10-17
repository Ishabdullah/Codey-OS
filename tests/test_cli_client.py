"""13g fixed client unit evidence; every socket/model/config operation is mocked."""

import builtins
import io
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import cli_client, process_identity


@pytest.fixture
def client(monkeypatch, tmp_path):
    # No actual state/config/audit store is imported or opened in this suite.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CODEY_STATE_DIR", str(tmp_path / "state"))
    paths = SimpleNamespace(pid_file=tmp_path / 'pid "\n;file', socket_file=Mock())
    paths.socket_file.__str__ = Mock(return_value=str(tmp_path / 'socket "\n;file'))
    paths.socket_file.is_socket.return_value = True
    config = Mock()
    config.get.return_value = str(tmp_path / "state.db")
    configuration = Mock(return_value=(config, paths))
    monkeypatch.setattr(cli_client, "_configuration", configuration)
    observed = Mock(return_value=SimpleNamespace(state=process_identity.RUNNING))
    monkeypatch.setattr(process_identity, "inspect_record", observed)
    channel = Mock()
    channel.recv.side_effect = [b'{"status":"ok"}', b'']
    factory = Mock(return_value=channel)
    monkeypatch.setattr(cli_client.socket, "socket", factory)
    return SimpleNamespace(paths=paths, channel=channel, factory=factory, observed=observed, configuration=configuration)


def respond(client, value):
    client.channel.recv.side_effect = [json.dumps(value).encode(), b""]


def payload(client):
    return json.loads(client.channel.sendall.call_args.args[0])


@pytest.mark.parametrize("marker", ["--bg", "--background"])
def test_background_prompt_is_literal_and_flags_preserved(client, marker, tmp_path):
    shaped = '"""; __import__("pathlib").Path("owned").touch(); #\n$() `x` \'quoted\''
    assert cli_client.main([marker, "--yolo", shaped, "a b", "", "--ctx", "2048"]) == 0
    assert payload(client) == {"cmd": "command", "data": {"prompt": shaped + " a b  --ctx 2048", "yolo": True}}
    assert not (tmp_path / "owned").exists()
    client.channel.settimeout.assert_called_once_with(30.0)
    client.channel.connect.assert_called_once_with(str(client.paths.socket_file))
    client.observed.assert_called_once_with(client.paths.pid_file, "codeyOS")
    client.channel.close.assert_called_once()


def test_bg_false_yolo_and_empty_prompt(client):
    assert cli_client.main(["--bg"]) == 0
    assert payload(client)["data"] == {"prompt": "", "yolo": False}


@pytest.mark.parametrize("command", ["task", "cancel"])
@pytest.mark.parametrize("value", ["0", "000", "-1", "+1", "1.0", "1+1", "1\n", " 1", "١", "True", '__import__("os").system("x")'])
def test_invalid_task_ids_rejected_before_configuration_or_connection(client, command, value):
    assert cli_client.main([command, value]) == 1
    client.configuration.assert_not_called()
    client.observed.assert_not_called()
    client.factory.assert_not_called()


@pytest.mark.parametrize("command", ["task", "cancel"])
def test_missing_id_never_connects(client, command):
    assert cli_client.main([command]) == 1
    client.factory.assert_not_called()


def test_task_list(client, capsys):
    respond(client, {"status": "ok", "tasks": [{"id": 8, "description": "one\ntwo", "status": "done"}]})
    assert cli_client.main(["task", "list"]) == 0
    assert payload(client) == {"cmd": "task", "data": {"limit": 20}}
    assert "[8] ✓ one two" in capsys.readouterr().out
    client.channel.settimeout.assert_called_once_with(10.0)


def test_positive_task_id_and_display(client, capsys):
    respond(client, {"status": "ok", "task": {"id": 12, "description": "literal", "status": "done", "result": "output", "created_at": 10, "completed_at": 20}})
    assert cli_client.main(["task", "00012"]) == 0
    assert payload(client) == {"cmd": "task", "data": {"id": 12}}
    result = capsys.readouterr().out
    assert "Task 12: literal" in result and "Result: output" in result
    assert "Created:" in result and "Completed:" in result


def test_cancel(client, capsys):
    respond(client, {"status": "ok", "message": "Task 12 cancelled"})
    assert cli_client.main(["cancel", "12"]) == 0
    assert payload(client) == {"cmd": "cancel", "data": {"id": 12}}
    assert "Task 12 cancelled" in capsys.readouterr().out


def test_status_uses_health_and_configured_database(client, capsys):
    respond(client, {"status": "ok", "pid": 7, "tasks": {"pending": 2, "stuck": [3, 4]}})
    assert cli_client.main(["status"]) == 0
    assert payload(client) == {"cmd": "health", "data": {}}
    client.channel.settimeout.assert_called_once_with(5.0)
    text = capsys.readouterr().out
    assert "Codey-OS Daemon Status" in text and "3, 4" in text
    assert "State Database:" in text


@pytest.mark.parametrize("args", [["status"], ["task", "list"], ["task", "1"], ["cancel", "1"], ["--bg", "hello"]])
@pytest.mark.parametrize("response", [b"", b"{", b"\xff", b"[]", b"null", b"{}", b'{"status":"error","message":"refused"}'])
def test_bad_response_fails_all_rpc_branches(client, args, response):
    client.channel.recv.side_effect = [response, b""]
    assert cli_client.main(args) == 1
    client.channel.close.assert_called_once()


@pytest.mark.parametrize("args", [["status"], ["task", "list"], ["cancel", "1"], ["--bg", "hello"]])
@pytest.mark.parametrize("failure", [TimeoutError(), OSError("refused")])
def test_connection_failure_nonzero(client, args, failure):
    client.channel.connect.side_effect = failure
    assert cli_client.main(args) == 1
    client.channel.close.assert_called_once()


@pytest.mark.parametrize("state", [process_identity.DEAD, process_identity.UNSAFE])
def test_unverified_daemon_never_connects_or_imports_main(client, state, monkeypatch):
    client.observed.return_value.state = state
    direct = Mock(side_effect=AssertionError("must not fall through"))
    monkeypatch.setattr(cli_client, "_direct", direct)
    assert cli_client.main(["--bg", "hello"]) == 1
    client.factory.assert_not_called()
    direct.assert_not_called()


def test_missing_socket_never_connects(client):
    client.paths.socket_file.is_socket.return_value = False
    assert cli_client.main(["status"]) == 1
    client.factory.assert_not_called()


def test_socket_cleanup_failure_does_not_mask_rpc_error(client):
    client.channel.connect.side_effect = OSError("refused")
    client.channel.close.side_effect = OSError("cleanup failed")
    assert cli_client.main(["--bg", "literal"]) == 1


def test_socket_cleanup_failure_does_not_change_success(client):
    client.channel.close.side_effect = OSError("cleanup failed")
    assert cli_client.main(["cancel", "1"]) == 0


@pytest.mark.parametrize("args", [[], ["--daemon"], ["--ctx", "2048", '"\n;literal'], ["--yolo", "hello"]])
@pytest.mark.parametrize("outcome", [None, 7, SystemExit(7), KeyboardInterrupt()])
def test_direct_preserves_argv_streams_and_exit(client, monkeypatch, args, outcome):
    original_argv = ["original-client", "old"]
    monkeypatch.setattr(sys, "argv", original_argv)
    streams = (io.StringIO("input"), io.StringIO(), io.StringIO())
    for name, stream in zip(("stdin", "stdout", "stderr"), streams):
        monkeypatch.setattr(sys, name, stream)
    def run():
        assert sys.argv == ["original-client", *args]
        assert (sys.stdin, sys.stdout, sys.stderr) == streams
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome
    monkeypatch.setitem(sys.modules, "main", SimpleNamespace(main=run))
    if isinstance(outcome, BaseException):
        with pytest.raises(type(outcome)) as caught:
            cli_client.main(args)
        assert caught.value is outcome
    else:
        assert cli_client.main(args) == outcome
    assert sys.argv is original_argv
    client.configuration.assert_not_called()
    client.factory.assert_not_called()


def test_rpc_never_imports_main_daemon_or_inference(client, monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name == "main" or name.startswith(("core.daemon", "core.inference", "core.loader", "torch")):
            raise AssertionError("Forbidden heavy client import: " + name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    for args in (["status"], ["task", "list"], ["cancel", "1"], ["--bg", "hello"]):
        respond(client, {"status": "ok"})
        assert cli_client.main(args) == 0


def test_configuration_uses_one_existing_snapshot(monkeypatch):
    config = object()
    paths = object()
    get = Mock(return_value=config)
    resolve = Mock(return_value=paths)
    monkeypatch.setitem(sys.modules, "core.daemon_config", SimpleNamespace(get_config=get, resolve_daemon_paths=resolve))
    assert cli_client._configuration() == (config, paths)
    get.assert_called_once_with()
    resolve.assert_called_once_with(config)
