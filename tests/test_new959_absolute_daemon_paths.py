"""NEW-959 S1: daemon paths must be absolute; relative values are refused.

Disposable HOME/state/cwd under tmp_path. Every process-spawn, signal, exec and
lifecycle-record entry point is patched to raise BEFORE the unit under test
runs, and refusal tests assert nothing was created in the cwd or state root.
No model, no network, no synthetic PID.
"""

import builtins
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import main as main_mod
from core import cli_client, daemon, daemon_bootstrap, daemon_config, service_actions
from core import process_identity as identity
from core import service_lifecycle as mechanics
from core.daemon_config import (
    DaemonConfig,
    DaemonPathError,
    DaemonPaths,
    resolve_daemon_paths,
)

ROOT = Path(__file__).resolve().parents[1]
KEYS = ("pid_file", "socket_file", "log_file")


def _forbidden(*_args, **_kwargs):
    raise AssertionError("must not be reached on refusal")


def tree(path):
    return sorted(str(item.relative_to(path)) for item in path.rglob("*"))


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    home, state, cwd = tmp_path / "home", tmp_path / "state", tmp_path / "cwd"
    home.mkdir()
    state.mkdir()
    cwd.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEY_STATE_DIR", str(state))
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(daemon_config, "CODEY_STATE_DIR", state)
    monkeypatch.setattr(daemon_config, "_config", None)
    monkeypatch.chdir(cwd)
    yield SimpleNamespace(tmp=tmp_path, home=home, state=state, cwd=cwd)
    monkeypatch.setattr(daemon_config, "_config", None)


@pytest.fixture
def guard(monkeypatch):
    """Install raising stand-ins for every effect before the call under test."""
    monkeypatch.setattr(subprocess, "Popen", _forbidden)
    monkeypatch.setattr(signal, "pthread_kill", _forbidden)
    for name in ("kill", "killpg", "getpgid", "execv", "execve", "execvp", "execvpe"):
        monkeypatch.setattr(os, name, _forbidden)
    monkeypatch.setattr(identity, "OwnedLaunch", _forbidden)
    monkeypatch.setattr(identity, "inspect_record", _forbidden)
    for name in ("__enter__", "signal", "stop"):
        monkeypatch.setattr(identity.LifecycleRecord, name, _forbidden)


def make_config(env, monkeypatch, values, install=True):
    """Write config.json with daemon values and (optionally) make it the global config."""
    path = env.state / "config.json"
    path.write_text(json.dumps({"daemon": values}))
    config = DaemonConfig(path)
    if install:
        monkeypatch.setattr(daemon_config, "_config", config)
    return config


RELATIVE_CONFIG = {"pid_file": "rel.pid", "socket_file": "rel.sock", "log_file": "rel.log"}


# ---- resolver matrix -------------------------------------------------------

@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("value", ["rel.x", "./x", "a/b", "$HOME/x", "", "x" * 10, "~nosuchuser_zz9/x"])
def test_relative_string_values_refused_naming_key(env, monkeypatch, key, value):
    config = make_config(env, monkeypatch, {key: value}, install=False)
    with pytest.raises(DaemonPathError) as caught:
        resolve_daemon_paths(config)
    message = str(caught.value)
    assert f"daemon.{key}" in message and "absolute" in message and str(env.state / "config.json") in message
    assert "tools will not scan for" in message
    assert "set the key to the absolute location it was started in before stopping it" in message
    assert "Set CODEY_STATE_DIR" not in message
    if value == "~nosuchuser_zz9/x":
        assert repr(value) in message
        assert "<unresolvable:" not in message


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("value", [None, 5, [], {"a": 1}, True])
def test_non_string_values_refused_without_type_errors(env, monkeypatch, key, value):
    config = make_config(env, monkeypatch, {key: value}, install=False)
    with pytest.raises(DaemonPathError):
        resolve_daemon_paths(config)


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("value", ["/a\0b", "/" + "x" * 4096])
def test_nul_and_oversized_values_refused(env, monkeypatch, key, value):
    config = make_config(env, monkeypatch, {key: value}, install=False)
    with pytest.raises(DaemonPathError):
        resolve_daemon_paths(config)


def test_message_truncates_and_escapes_offending_value(env, monkeypatch):
    config = make_config(env, monkeypatch, {"pid_file": "rel\n" + "y" * 500}, install=False)
    with pytest.raises(DaemonPathError) as caught:
        resolve_daemon_paths(config)
    assert "\n" not in str(caught.value).split(" (")[0] and "y" * 200 not in str(caught.value)


def test_tilde_expands_under_disposable_home_and_is_accepted(env, monkeypatch):
    config = make_config(env, monkeypatch, {"pid_file": "~/x/p", "socket_file": "~/s", "log_file": "~/l"}, install=False)
    paths = resolve_daemon_paths(config)
    assert paths.pid_file == env.home / "x/p" and paths.log_file == env.home / "l"
    assert not (env.home / "x").exists()


def test_absolute_spaces_and_dotdot_are_accepted_verbatim(env, monkeypatch):
    values = {"pid_file": str(env.tmp / "a b" / "p"), "socket_file": "/a/../b/s", "log_file": str(env.tmp / "l  l")}
    paths = resolve_daemon_paths(make_config(env, monkeypatch, values, install=False))
    assert [str(paths.pid_file), str(paths.socket_file), str(paths.log_file)] == [values["pid_file"], "/a/../b/s", values["log_file"]]


@pytest.mark.parametrize("root", ["relstate", "~/x", "./s", "~"])
def test_relative_state_dir_refused_even_with_absolute_config_values(env, monkeypatch, root):
    values = {key: str(env.tmp / key) for key in KEYS}
    config = make_config(env, monkeypatch, values, install=False)
    monkeypatch.setattr(daemon_config, "CODEY_STATE_DIR", Path(root))
    with pytest.raises(DaemonPathError, match="CODEY_STATE_DIR") as caught:
        resolve_daemon_paths(config)
    message = str(caught.value)
    assert "Set CODEY_STATE_DIR to an absolute directory" in message
    assert "will not scan for or stop a daemon started under a relative root" in message
    assert f"got {str(Path(root))!r}" in message
    assert "daemon.CODEY_STATE_DIR" not in message and "set the key to" not in message


def test_relative_codey_state_dir_env_refused_in_fresh_process_without_creating_dirs(env):
    # Resolver only; this child imports no service, daemon or model code.
    code = f"import sys; sys.path.insert(0, {str(ROOT)!r})\nfrom core.daemon_config import resolve_daemon_paths\nresolve_daemon_paths()"
    child_env = dict(os.environ, CODEY_STATE_DIR="relstate")
    before = tree(env.cwd)
    result = subprocess.run([sys.executable, "-I", "-c", code], cwd=env.cwd, env=child_env, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode != 0 and "DaemonPathError" in result.stderr and "CODEY_STATE_DIR" in result.stderr
    assert tree(env.cwd) == before == []


def test_daemon_paths_dataclass_validates_directly(env):
    DaemonPaths(Path("/a"), Path("/b"), Path("/c"))
    for bad in (Path("rel"), Path(""), "relstr", None):
        for slot in range(3):
            values = [Path("/a"), Path("/b"), Path("/c")]
            values[slot] = bad
            with pytest.raises(DaemonPathError):
                DaemonPaths(*values)


def test_create_default_config_refuses_relative_root_and_writes_nothing(env, monkeypatch):
    monkeypatch.setattr(daemon_config, "CODEY_STATE_DIR", Path("relstate"))
    config = DaemonConfig(env.cwd / "relstate" / "config.json")
    with pytest.raises(DaemonPathError):
        config.create_default_config()
    assert tree(env.cwd) == []


def test_create_default_config_refuses_existing_relative_config_unchanged(env, monkeypatch):
    config = make_config(env, monkeypatch, RELATIVE_CONFIG, install=False)
    before = config.config_file.read_bytes()
    with pytest.raises(DaemonPathError, match="daemon.pid_file.*absolute"):
        config.create_default_config()
    assert config.config_file.read_bytes() == before
    assert tree(env.state) == ["config.json"]


# ---- cross-cwd -------------------------------------------------------------

def test_two_cwds_resolve_identical_records_for_absolute_config(env, monkeypatch):
    values = {key: str(env.tmp / "abs" / key) for key in KEYS}
    make_config(env, monkeypatch, values)
    other = env.tmp / "other"
    other.mkdir()
    first = (resolve_daemon_paths(), mechanics.service_paths("daemon"))
    monkeypatch.chdir(other)
    second = (resolve_daemon_paths(), mechanics.service_paths("daemon"))
    assert first == second and first[1].pid_file == env.tmp / "abs" / "pid_file"


# ---- daemon consumers ------------------------------------------------------

def test_daemon_main_exits_2_before_any_side_effect(env, monkeypatch, guard):
    make_config(env, monkeypatch, RELATIVE_CONFIG)
    messages = []
    monkeypatch.setattr(daemon, "check_pid_file", _forbidden)
    monkeypatch.setattr(daemon, "Daemon", _forbidden)
    monkeypatch.setattr(daemon, "error", messages.append)
    before = (tree(env.cwd), tree(env.state))
    with pytest.raises(SystemExit) as caught:
        daemon.main()
    assert caught.value.code == 2
    assert len(messages) == 1 and "daemon.pid_file" in messages[0] and "absolute" in messages[0]
    assert (tree(env.cwd), tree(env.state)) == before


def test_check_pid_file_stays_fail_closed_on_refusal(env, monkeypatch, guard):
    def refuse():
        raise DaemonPathError("refused")
    monkeypatch.setattr(daemon, "resolve_daemon_paths", refuse)
    assert daemon.check_pid_file() is True


def test_is_daemon_running_and_send_command_propagate_refusal(env, monkeypatch, guard):
    import socket
    monkeypatch.setattr(socket, "socket", _forbidden)
    make_config(env, monkeypatch, RELATIVE_CONFIG)
    with pytest.raises(DaemonPathError):
        daemon.is_daemon_running()
    with pytest.raises(DaemonPathError):
        daemon.send_command("ping")


def test_cli_client_prints_error_rc1_without_socket_or_inspect(env, monkeypatch, guard, capsys):
    import socket
    monkeypatch.setattr(socket, "socket", _forbidden)
    make_config(env, monkeypatch, RELATIVE_CONFIG)
    assert cli_client.main(["status"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("[ERROR] ") and "daemon.pid_file" in err


# ---- bootstrap -------------------------------------------------------------

def test_bootstrap_refuses_relative_before_importing_core_daemon(monkeypatch):
    monkeypatch.delitem(sys.modules, "core.daemon", raising=False)
    imported = []
    real_import = builtins.__import__

    def watching(name, *args, **kwargs):
        if name in ("core.daemon", "core.daemon_config"):
            imported.append(name)
            raise AssertionError("imported before the absoluteness check")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", watching)
    for values in (["rel", "/s", "/l"], ["/p", "rel", "/l"], ["/p", "/s", "rel"]):
        with pytest.raises(ValueError, match="Invalid daemon path snapshot"):
            daemon_bootstrap.main(values)
    assert imported == []
    assert "core.daemon" not in sys.modules or sys.modules["core.daemon"] is not None


# ---- service lifecycle -----------------------------------------------------

def refused_text(error):
    return str(error.value)


@pytest.mark.parametrize("service,operation", [
    ("daemon", "start"), ("daemon", "stop"), ("daemon", "restart"), ("daemon", "reload"), ("daemon", "preflight"),
    ("all", "start"), ("all", "stop"), ("all", "restart"),
])
def test_lock_exec_refuses_every_operation_before_any_effect(env, monkeypatch, guard, service, operation):
    make_config(env, monkeypatch, RELATIVE_CONFIG)
    before = (tree(env.cwd), tree(env.state))
    with pytest.raises(mechanics.ServicePathRefused) as caught:
        mechanics.lock_exec(service, operation)
    assert "daemon.pid_file" in refused_text(caught)
    assert (tree(env.cwd), tree(env.state)) == before
    assert not list(env.state.glob("*.lifecycle.lock")) and not list(env.cwd.glob("*"))


def test_stop_refused_under_invalid_config_even_with_an_existing_record(env, monkeypatch, guard):
    absolute_record = env.tmp / "kept" / "codeyOS.pid"
    absolute_record.parent.mkdir()
    absolute_record.write_text("{}")
    snapshot = absolute_record.read_bytes()
    make_config(env, monkeypatch, RELATIVE_CONFIG)
    with pytest.raises(mechanics.ServicePathRefused):
        mechanics.lock_exec("daemon", "stop")
    assert absolute_record.read_bytes() == snapshot and tree(env.tmp / "kept") == ["codeyOS.pid"]


@pytest.mark.parametrize("values", [["lock-exec", "all", "stop"], ["lock-exec", "daemon", "start"], ["status", "daemon"], ["logs", "daemon"], ["daemon-status"]])
def test_worker_prints_refusal_message_and_returns_2(env, monkeypatch, guard, capsys, values):
    make_config(env, monkeypatch, RELATIVE_CONFIG)
    assert service_actions._worker_main(values) == 2
    captured = capsys.readouterr()
    assert "daemon.pid_file" in captured.err and "absolute" in captured.err
    assert "unavailable or unsafe" not in captured.err and captured.out == ""
    assert tree(env.cwd) == []


def test_config_create_worker_prints_relative_config_refusal_only(env, monkeypatch, guard, capsys):
    config = make_config(env, monkeypatch, RELATIVE_CONFIG)
    before = config.config_file.read_bytes()
    assert service_actions._worker_main(["config-create"]) == 2
    captured = capsys.readouterr()
    assert "daemon.pid_file" in captured.err and "absolute" in captured.err
    assert "Default config created" not in captured.out + captured.err
    assert "unavailable or unsafe" not in captured.err
    assert config.config_file.read_bytes() == before


def test_config_create_worker_prints_relative_state_root_refusal_only(env, monkeypatch, guard, capsys):
    monkeypatch.setattr(daemon_config, "CODEY_STATE_DIR", Path("relstate"))
    monkeypatch.setattr(daemon_config, "_config", DaemonConfig(Path("relstate/config.json")))
    assert service_actions._worker_main(["config-create"]) == 2
    captured = capsys.readouterr()
    assert "CODEY_STATE_DIR" in captured.err and "absolute" in captured.err
    assert "Default config created" not in captured.out + captured.err
    assert "unavailable or unsafe" not in captured.err
    assert tree(env.cwd) == []


@pytest.mark.parametrize("values", [["status", "daemon"], ["config-create"]])
def test_worker_keeps_fixed_text_for_other_failures(env, monkeypatch, capsys, values):
    if values[0] == "config-create":
        monkeypatch.setattr(daemon_config, "create_default_config", lambda: (_ for _ in ()).throw(RuntimeError("secret detail")))
    else:
        monkeypatch.setattr(mechanics, "status", lambda service: (_ for _ in ()).throw(RuntimeError("secret detail")))
    assert service_actions._worker_main(values) == 2
    err = capsys.readouterr().err
    assert "secret detail" not in err and "unavailable or unsafe" in err


def fake_inspect(*_args, **_kwargs):
    return SimpleNamespace(state=identity.DEAD, identity={})


def test_status_all_shows_refusal_line_and_continues(env, monkeypatch, capsys):
    make_config(env, monkeypatch, RELATIVE_CONFIG)
    monkeypatch.setattr(identity, "inspect_record", fake_inspect)
    monkeypatch.setattr(mechanics, "start_profile", lambda name, selected: (str(env.cwd), True, []))
    assert mechanics.status("all") == 2
    out = capsys.readouterr().out
    assert "  daemon: REFUSED (" in out and "daemon.pid_file" in out
    for name in ("restoricon", "aigentik", "cloudflared", "litestream", "backup-docs"):
        assert f"  {name}: {identity.DEAD}" in out
    assert tree(env.cwd) == []


def test_logs_all_shows_refusal_line_and_continues(env, monkeypatch, capsys):
    make_config(env, monkeypatch, RELATIVE_CONFIG)
    assert mechanics.show_logs("all") == 2
    out = capsys.readouterr().out
    assert "daemon: REFUSED (" in out
    for name in ("restoricon", "aigentik", "cloudflared", "litestream", "backup-docs"):
        assert f"No log found for {name}" in out
    with pytest.raises(mechanics.ServicePathRefused):
        mechanics.show_logs("daemon")


def test_single_service_status_refuses(env, monkeypatch, guard):
    make_config(env, monkeypatch, RELATIVE_CONFIG)
    with pytest.raises(mechanics.ServicePathRefused):
        mechanics.status("daemon")


def test_path_data_refuses_before_writing_to_pipe(env, monkeypatch, guard):
    make_config(env, monkeypatch, RELATIVE_CONFIG)
    read_fd, write_fd = os.pipe()
    try:
        monkeypatch.setattr(identity, "_ready_pipe", _forbidden)
        with pytest.raises(mechanics.ServicePathRefused):
            mechanics.path_data("all", "json", write_fd)
        os.close(write_fd)
        write_fd = None
        assert os.read(read_fd, 10) == b""
    finally:
        os.close(read_fd)
        if write_fd is not None:
            os.close(write_fd)


def test_main_prints_message_on_stderr_rc2_for_paths(env, monkeypatch, guard, capsys):
    make_config(env, monkeypatch, RELATIVE_CONFIG)
    read_fd, write_fd = os.pipe()
    try:
        assert mechanics.main(["paths", "--data-fd", str(write_fd)]) == 2
    finally:
        os.close(read_fd)
        os.close(write_fd)
    assert "daemon.pid_file" in capsys.readouterr().err


@pytest.mark.parametrize("arguments", [("rel.pid", "/s"), ("/p", "rel.sock")])
def test_usable_daemon_rejects_relative_argument(env, monkeypatch, guard, arguments):
    assert mechanics.main(["usable-daemon", *arguments]) == 2


def test_usable_daemon_accepts_absolute_arguments_to_inspection(env, monkeypatch):
    monkeypatch.setattr(identity, "inspect_record", fake_inspect)
    assert mechanics.usable_daemon(str(env.tmp / "p"), str(env.tmp / "s")) == 1


# ---- main.py ---------------------------------------------------------------

def test_daemon_is_running_logs_refusal_and_stays_false(env, monkeypatch, guard):
    warnings = []
    monkeypatch.setattr(main_mod, "warning", warnings.append)
    make_config(env, monkeypatch, RELATIVE_CONFIG)
    assert main_mod._daemon_is_running() is False
    assert len(warnings) == 1 and "daemon.pid_file" in warnings[0]


def test_daemon_is_running_generic_failure_is_silent_false(monkeypatch):
    warnings = []
    monkeypatch.setattr(main_mod, "warning", warnings.append)
    monkeypatch.setattr(daemon, "is_daemon_running", lambda: (_ for _ in ()).throw(OSError("x")))
    assert main_mod._daemon_is_running() is False and warnings == []


def test_shutdown_still_unloads_once_when_path_refused(env, monkeypatch, guard):
    from core import loader_v2
    calls = []
    loader = SimpleNamespace(unload=lambda: calls.append("unload"))
    monkeypatch.setattr(main_mod, "get_monitor", lambda: SimpleNamespace(stop=lambda: None))
    monkeypatch.setattr(main_mod, "warning", lambda *_: None)
    monkeypatch.setattr(loader_v2, "get_loader", lambda: loader)
    make_config(env, monkeypatch, RELATIVE_CONFIG)
    main_mod.shutdown()
    assert calls == ["unload"]


def test_main_status_prints_message_exit_2(env, monkeypatch, guard, capsys):
    import signal as signal_module

    from core import observability
    make_config(env, monkeypatch, RELATIVE_CONFIG)
    monkeypatch.setattr(signal_module, "signal", lambda *_: None)
    monkeypatch.setattr(sys, "argv", ["main.py", "--status"])

    def refuse():
        raise DaemonPathError("Daemon path daemon.pid_file must be absolute; refused")
    monkeypatch.setattr(observability, "status", refuse)
    with pytest.raises(SystemExit) as caught:
        main_mod.main()
    assert caught.value.code == 2
    captured = capsys.readouterr()
    assert "must be absolute" in captured.err and "Traceback" not in captured.err + captured.out


# ---- S3 non-daemon lifecycle paths -----------------------------------------

NON_DAEMON_SERVICES = (
    "restoricon",
    "aigentik",
    "litestream",
    "cloudflared",
    "backup-docs",
    "llama-server-8080",
)
MUTATING_OPERATIONS = tuple(
    (service, operation)
    for service in NON_DAEMON_SERVICES[:-1]
    for operation in ("start", "stop", "restart", "preflight")
) + (("llama-server-8080", "stop"),)


@pytest.mark.parametrize("service", NON_DAEMON_SERVICES)
@pytest.mark.parametrize("root", ["rel", "./state", "~/state", "$HOME/state"])
def test_non_daemon_service_paths_refuse_relative_state_root(
    env, monkeypatch, service, root
):
    monkeypatch.setenv("CODEY_STATE_DIR", root)
    with pytest.raises(mechanics.ServicePathRefused) as caught:
        mechanics.service_paths(service)
    message = str(caught.value)
    assert "CODEY_STATE_DIR" in message
    assert "absolute" in message
    assert repr(str(Path(root)))[:120] in message


def test_non_daemon_refusal_message_is_one_line_escaped_and_truncated(
    env, monkeypatch
):
    root = "relative\n" + "x" * 300
    monkeypatch.setenv("CODEY_STATE_DIR", root)
    with pytest.raises(mechanics.ServicePathRefused) as caught:
        mechanics.service_paths("restoricon")
    message = str(caught.value)
    assert "\n" not in message
    assert repr(str(Path(root)))[:120] in message
    assert "x" * 200 not in message


@pytest.mark.parametrize("service,operation", MUTATING_OPERATIONS)
def test_non_daemon_operations_refuse_before_effects(
    env, monkeypatch, guard, service, operation
):
    monkeypatch.setenv("CODEY_STATE_DIR", "relative state")
    monkeypatch.setattr(mechanics, "start_profile", _forbidden)
    before = (tree(env.cwd), tree(env.home))
    with pytest.raises(mechanics.ServicePathRefused):
        mechanics.lock_exec(service, operation)
    assert (tree(env.cwd), tree(env.home)) == before == ([], [])
    assert not list(env.cwd.glob("*.lifecycle.lock"))
    assert not (env.cwd / "relative state").exists()


@pytest.mark.parametrize("service", NON_DAEMON_SERVICES)
def test_non_daemon_status_refuses_before_identity_read(
    env, monkeypatch, guard, service
):
    monkeypatch.setenv("CODEY_STATE_DIR", "relative-state")
    with pytest.raises(mechanics.ServicePathRefused):
        mechanics.status(service)


@pytest.mark.parametrize("service", NON_DAEMON_SERVICES)
def test_non_daemon_logs_refuse_before_file_open(
    env, monkeypatch, service
):
    monkeypatch.setenv("CODEY_STATE_DIR", "relative-state")
    monkeypatch.setattr(Path, "open", _forbidden)
    with pytest.raises(mechanics.ServicePathRefused):
        mechanics.show_logs(service)


@pytest.mark.parametrize(
    "service,operation",
    [(service, "start") for service in NON_DAEMON_SERVICES[:-1]]
    + [("llama-server-8080", "stop")],
)
def test_non_daemon_worker_prints_only_actionable_refusal(
    env, monkeypatch, guard, capsys, service, operation
):
    monkeypatch.setenv("CODEY_STATE_DIR", "relative-state")
    monkeypatch.setattr(mechanics, "start_profile", _forbidden)
    assert service_actions._worker_main(["lock-exec", service, operation]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "CODEY_STATE_DIR" in captured.err and "absolute" in captured.err
    assert "unavailable or unsafe" not in captured.err


@pytest.mark.parametrize("reader", [mechanics.status, mechanics.show_logs])
def test_non_daemon_composite_reports_all_refusals_without_effects(
    env, monkeypatch, guard, capsys, reader
):
    monkeypatch.setenv("CODEY_STATE_DIR", "relative-state")
    monkeypatch.setattr(daemon_config, "CODEY_STATE_DIR", Path("relative-state"))
    monkeypatch.setattr(mechanics, "start_profile", _forbidden)
    before = (tree(env.cwd), tree(env.home))
    assert reader("all") == 2
    output = capsys.readouterr().out
    for service in mechanics._START_ORDER:
        assert f"{service}: REFUSED (" in output
    assert "llama-server-8080" not in output
    assert (tree(env.cwd), tree(env.home)) == before == ([], [])


def test_non_daemon_all_mutation_refuses_before_any_effect(
    env, monkeypatch, guard
):
    make_config(
        env,
        monkeypatch,
        {key: str(env.state / f"daemon-{key}") for key in KEYS},
    )
    monkeypatch.setenv("CODEY_STATE_DIR", "relative-state")
    monkeypatch.setattr(mechanics, "start_profile", _forbidden)
    visited = []
    real_service_paths = mechanics.service_paths

    def recording_service_paths(service):
        visited.append(service)
        return real_service_paths(service)

    monkeypatch.setattr(mechanics, "service_paths", recording_service_paths)
    before = (tree(env.cwd), tree(env.home))
    with pytest.raises(mechanics.ServicePathRefused, match="CODEY_STATE_DIR"):
        mechanics.lock_exec("all", "start")
    assert visited == ["daemon", "restoricon"]
    assert (tree(env.cwd), tree(env.home)) == before == ([], [])


def test_non_daemon_absolute_spaces_and_dotdot_are_retained_verbatim(
    env, monkeypatch
):
    root = str(env.tmp / "state with spaces" / ".." / "selected state")
    monkeypatch.setenv("CODEY_STATE_DIR", root)
    for service in NON_DAEMON_SERVICES:
        selected = mechanics.service_paths(service)
        assert str(selected.pid_file.parent) == root
        assert str(selected.log_file.parent) == root


def test_litestream_profile_uses_selected_snapshot_after_environment_change(
    env, monkeypatch
):
    selected = mechanics.service_paths("litestream")
    monkeypatch.setenv("CODEY_STATE_DIR", "later-relative-root")
    cwd, _missing, _argv = mechanics.start_profile("litestream", selected)
    assert cwd == str(selected.pid_file.parent) == str(env.state)


@pytest.mark.parametrize("value", [None, ""])
@pytest.mark.parametrize("service", NON_DAEMON_SERVICES)
def test_non_daemon_unset_or_empty_state_root_uses_home_fallback(
    env, monkeypatch, service, value
):
    if value is None:
        monkeypatch.delenv("CODEY_STATE_DIR", raising=False)
    else:
        monkeypatch.setenv("CODEY_STATE_DIR", value)
    selected = mechanics.service_paths(service)
    assert selected.pid_file.parent == env.home / ".codeyOS"
    assert selected.log_file.parent == env.home / ".codeyOS"


def test_s3_does_not_change_relative_aigentik_dir_or_restoricon_db(
    env, monkeypatch
):
    relative_aigentik = Path("relative-aigentik")
    relative_db = Path("relative-restoricon.db")
    config = SimpleNamespace(
        get_aigentik_config=lambda: {"dir": str(relative_aigentik)},
        get_restoricon_api_config=lambda: {
            "host": "127.0.0.1",
            "port": 8000,
            "db_path": relative_db,
        },
    )
    monkeypatch.setattr(mechanics, "_config_helpers", lambda: config)

    aigentik = mechanics.service_paths("aigentik")
    cwd, missing, argv = mechanics.start_profile("aigentik", aigentik)
    assert cwd == str(relative_aigentik) and missing is True and argv == []

    restoricon = mechanics.service_paths("restoricon")
    _cwd, missing, argv = mechanics.start_profile("restoricon", restoricon)
    assert missing is False
    assert argv[argv.index("--db") + 1] == str(relative_db)


def _restoricon_argv(monkeypatch, db_path):
    config = SimpleNamespace(
        get_restoricon_api_config=lambda: {"host": "127.0.0.1", "port": 8000, "db_path": db_path},
    )
    monkeypatch.setattr(mechanics, "_config_helpers", lambda: config)
    _cwd, missing, argv = mechanics.start_profile("restoricon", mechanics.service_paths("restoricon"))
    assert missing is False
    return argv


def test_wp22_s2_world_flag_iff_db_path_is_live(env, monkeypatch):
    from restoricon_core import world

    live = env.tmp / "fake-live" / "restoricon.db"
    live.parent.mkdir()
    monkeypatch.setattr(world, "live_db_paths", lambda: {str(live)})
    argv = _restoricon_argv(monkeypatch, live)
    assert argv[-2:] == ["--world", "production"]
    assert argv[argv.index("--db") + 1] == str(live)
    other = _restoricon_argv(monkeypatch, env.tmp / "world-copy.db")
    assert "--world" not in other and "production" not in other


def test_wp22_s2_undeterminable_live_set_omits_flag(env, monkeypatch):
    from restoricon_core import world

    def _boom():
        raise world.WorldConfigError("bad config")

    monkeypatch.setattr(world, "live_db_paths", _boom)
    assert "--world" not in _restoricon_argv(monkeypatch, env.tmp / "x.db")


def test_wp22_s2_server_world_arg_parsing(capsys):
    from restoricon_core.api.server import build_arg_parser

    parser = build_arg_parser()
    assert parser.parse_args([]).world is None
    assert parser.parse_args(["--world", "production"]).world == "production"
    for bad in ("dev", "Production", ""):
        with pytest.raises(SystemExit):
            parser.parse_args(["--world", bad])
    capsys.readouterr()


def test_wp22_s3a_nul_db_path_cannot_grant_flag(env, monkeypatch):
    from restoricon_core import world

    monkeypatch.setattr(world, "live_db_paths", lambda: {str(env.tmp / "fake-live.db")})
    assert world.is_live_path("a\x00b") is True  # the old grant path
    argv = _restoricon_argv(monkeypatch, "a\x00b")  # must not raise ValueError
    assert "--world" not in argv and "production" not in argv


@pytest.mark.parametrize("content", ["{not json", "", "[]"])
def test_wp22_s3a_garbage_config_json_omits_flag(env, monkeypatch, content):
    from restoricon_core import world

    pwhome = env.tmp / "pwhome"
    (pwhome / ".codeyOS").mkdir(parents=True)
    (pwhome / ".codeyOS" / "config.json").write_text(content)
    monkeypatch.setattr(world, "_passwd_home", lambda: str(pwhome))
    for target in (env.tmp / "x.db", pwhome / ".codeyOS" / "restoricon.db"):
        argv = _restoricon_argv(monkeypatch, target)
        assert "--world" not in argv and "production" not in argv


def test_wp22_s3a_empty_db_path_omits_flag_and_live_adds_it_last(env, monkeypatch):
    from restoricon_core import world

    live = env.tmp / "fake-live.db"
    monkeypatch.setattr(world, "live_db_paths", lambda: {str(live)})
    assert "--world" not in _restoricon_argv(monkeypatch, "")
    argv = _restoricon_argv(monkeypatch, str(live) + "-wal")
    assert argv[-2:] == ["--world", "production"]
    assert argv.count("--world") == 1


@pytest.mark.parametrize("code,delay", [
    ("import sys, time; time.sleep(0.4); sys.exit(2)", 3.0),  # alive at publish
    ("import sys; sys.exit(2)", 3.0),  # may exit before publication verifies
])
def test_wp22_s3a_child_exiting_2_is_reported_failed_and_leaves_no_live_record(tmp_path, code, delay):
    """Real owned spawn (real Popen, real LifecycleRecord) of a throwaway
    ``python3 -c`` child that exits 2, standing in for a restoricon server
    that refuses to start after S3b.  No real service is started.

    Pins: run() returns 2, readiness is failed-cleanup-confirmed (not
    published/retained), the child was spawned exactly once (no restart), and
    afterwards the record state is DEAD ("absent-dead", what ``status``
    prints, rc 1), never RUNNING.  If the child was alive when published the
    pid/identity files are removed.  Known race (process_identity.py:603 vs
    :358): a child that dies before publish() verifies leaves a DEAD pid +
    identity pair behind (publication stays None, so _cleanup_record at :563
    skips); the next launch removes it via run():589.  The test asserts that
    leftover is DEAD and cleanable, not that it is absent.
    """
    pid_file = tmp_path / "state" / "restoricon.pid"
    log_file = tmp_path / "state" / "restoricon.log"
    pid_file.parent.mkdir()
    read_fd, write_fd = os.pipe()
    spawned = []
    real_popen = subprocess.Popen

    def _counting_popen(*a, **k):
        spawned.append(a[0])
        return real_popen(*a, **k)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(identity.subprocess, "Popen", _counting_popen)
    launch = None
    try:
        with identity.LifecycleRecord(pid_file, "restoricon") as record:
            launch = identity.OwnedLaunch(
                record, ["python3", "-c", code],
                log_file=log_file, ready_fd=write_fd, startup_delay=delay, timeout=5.0,
            )
            assert launch.run() == 2
            outcome = identity.parse_spawn_ready(os.read(read_fd, 128))
            state_after = record.inspect().state
            leftover = pid_file.exists()
            if leftover:
                assert record.cleanup(record.inspect()) is True  # next launch's path
    finally:
        monkey.undo()
        os.close(read_fd)
        if launch is not None and launch.ready_fd is not None:
            os.close(launch.ready_fd)
    assert outcome.outcome == "failed-cleanup-confirmed"
    assert len(spawned) == 1
    assert launch.child.poll() == 2
    assert state_after == identity.DEAD
    if "sleep" in code:
        assert leftover is False  # published, then cleaned up on failure
    assert not pid_file.exists() and not Path(str(pid_file) + ".identity").exists()
    assert identity.inspect_record(pid_file, "restoricon").state == identity.DEAD
