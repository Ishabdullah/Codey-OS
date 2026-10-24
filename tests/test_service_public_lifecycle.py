"""Public service wiring with fail-closed external-command stubs.

No installed service, backup, tunnel, model, credentials, or network is used.
Identity/spawn CLI stubs only simulate state: their numeric payloads are never
signalled. Actual signal evidence uses separately retained fixture Popen handles.
"""

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import daemon_bootstrap
from core import process_identity as identity

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")

STUB = r'''
import json, os, sys, time
from pathlib import Path
root = Path(os.environ['FIXTURE_REPO'])
sys.path.insert(0, str(root))
base = Path(os.environ['FIXTURE_BASE'])
args = sys.argv[1:]
name = Path(sys.argv[0]).name
trace = base / 'commands.jsonl'
def record(label, **values):
    data = (json.dumps({'label': label, **values}) + '\n').encode()
    fd = os.open(trace, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    try: os.write(fd, data)
    finally: os.close(fd)
def blocked():
    record('BLOCKED', name=name)
    sys.exit(91)
if name == 'bash':
    if args and args[0] == str(root / 'codeyOS') and os.environ.get('FIXTURE_FAKE_TUI') == '1':
        record('TUI', argv=args[1:], cwd=os.getcwd(), codey_dir=os.environ.get('CODEY_DIR'), pythonpath=os.environ.get('PYTHONPATH'), credentials=os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'))
        sys.exit(int(os.environ.get('FIXTURE_TUI_RC', '0')))
    if len(args) > 3 and args[0] == '-c' and args[1] == 'source "$1"; shift; _codey_service_operation "$@"' and args[3] == str(root / 'lib/service_lifecycle.sh'):
        # Test-only Bash retains/reaps simulated coprocess jobs after observing
        # the real private function's result. No service child is ever created.
        args[1] += '; _fixture_rc=$?; for _fixture_fd in 200 210 211 212 213 214 215; do exec {_fixture_fd}>&-; done; printf "%s\\n" "$_fixture_rc" >> "$FIXTURE_RESULTS"; wait; exit "$_fixture_rc"'
        os.execv(os.environ['FIXTURE_BASH'], [os.environ['FIXTURE_BASH'], *args])
    blocked()
if name == 'timeout':
    if args != ['60', 'python3', str(root / 'core/backup_secrets.py')]: blocked()
    record('timeout-secrets-stub')
    os.execv(str(base / 'bin/python3'), [str(base / 'bin/python3'), *args[2:]])
if name != 'python3': blocked()
if len(args) > 1 and args[0] == str(root / 'core/service_lifecycle.py'):
    if args[1] not in ('lock-exec', 'status', 'paths', 'parse-ready', 'usable-daemon', 'logs', 'config-create', 'config-show', 'daemon-status'): blocked()
    if args[1] == 'parse-ready':
        for fd in (200, 210, 211, 212, 213, 214, 215):
            try: os.fstat(fd)
            except OSError: pass
            else: raise RuntimeError('parser inherited lifecycle lock')
    record('adapter:' + args[1])
    from core import service_lifecycle as lifecycle
    from core import service_actions as actions
    actual_popen = actions.subprocess.Popen
    def worker_popen(argv, **kwargs):
        if argv[:4] != [sys.executable, '-c', actions._WORKER_BOOTSTRAP, str(root)]: blocked()
        actions._validate(argv[4:])
        return actual_popen([str(base / 'bin/python3'), *argv[1:]], **kwargs)
    actions.subprocess.Popen = worker_popen
    sys.exit(lifecycle.main(args[1:]))
if len(args) >= 3 and args[:2] == ['-c', __import__('core.service_actions', fromlist=['_WORKER_BOOTSTRAP'])._WORKER_BOOTSTRAP]:
    if args[2] != str(root): blocked()
    from core import service_actions as actions
    from core import service_lifecycle as lifecycle
    actions._validate(args[3:])
    actual_discover = lifecycle.discover_untracked
    allowed = {int(value) for value in os.environ.get('FIXTURE_DISCOVERY_PIDS', '').split(',') if value}
    def discover(*values, **options):
        return [pid for pid in actual_discover(*values, **options) if pid in allowed] if allowed else []
    lifecycle.discover_untracked = discover
    def models():
        record('model-status-stub'); print('Model: fixture disabled')
    actions._show_daemon_models = models
    sys.exit(actions._worker_main(args[3:]))
if len(args) > 1 and args[0] == str(root / 'core/process_identity.py'):
    action = args[1]
    if action not in ('inspect', 'stop', 'signal', 'spawn'): blocked()
    if os.environ.get('FIXTURE_REAL_IDENTITY') == '1' and action != 'spawn':
        from core import process_identity as identity
        def forbidden_signal(*_):
            record('FORBIDDEN_SIGNAL_ATTEMPT')
            raise AssertionError('signal forbidden in malformed identity fixture')
        identity.os.kill = forbidden_signal
        sys.exit(identity.main(args[1:]))
    fd = int(args[args.index('--lock-fd') + 1])
    service = args[args.index('--service') + 1] if action == 'spawn' else args[3]
    pid = args[args.index('--pid-file') + 1] if action == 'spawn' else args[2]
    expected = Path(pid + '.lifecycle.lock').stat()
    actual = os.fstat(fd)
    assert (actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino)
    ledger = base / ('state-' + service)
    failed = os.environ.get('FIXTURE_FAIL_SERVICE') == service
    record('identity:' + action, service=service, pid=pid, fd=fd)
    if action == 'inspect':
        state = ledger.read_text() if ledger.exists() else 'dead'
        print(state.upper(), flush=True)
        sys.exit({'running':0, 'dead':1, 'unsafe':2}[state])
    if action == 'stop':
        if failed:
            print('UNSAFE', flush=True); sys.exit(2)
        ledger.write_text('dead')
        print('DEAD', flush=True); sys.exit(0)
    if action == 'signal':
        assert args[args.index('--signal') + 1] == 'USR1'
        sys.exit(2 if failed else 0)
    # Simulated protocol only. No Popen/os.kill or service executable invocation.
    for other in (200, 210, 211, 212, 213, 214, 215):
        if other == fd: continue
        try: os.fstat(other)
        except OSError: pass
        else: raise RuntimeError('helper inherited unrelated composite lock')
    argv = args[args.index('--') + 1:]
    record('profile', service=service, argv=argv, cwd=args[args.index('--cwd') + 1])
    ready = int(args[args.index('--ready-fd') + 1])
    mode = os.environ.get('FIXTURE_PROTOCOL_MODE') if service == os.environ.get('FIXTURE_PROTOCOL_SERVICE', service) else None
    if mode:
        if mode == 'retained': data = f'retained {os.getpid()} 707070\n'.encode()
        elif mode == 'malformed': data = b'published 707070\nextra\n'
        else: raise AssertionError('unexpected fixture mode')
        os.write(ready, data); os.close(ready)
        deadline = time.monotonic() + 5
        while not (base / 'release').exists() and time.monotonic() < deadline: time.sleep(.01)
        sys.exit(2)
    if failed:
        os.write(ready, b'failed-cleanup-confirmed\n'); os.close(ready); sys.exit(2)
    if os.environ.get('FIXTURE_PAUSE_SPAWN') == service:
        (base / 'spawn-paused').touch()
        deadline = time.monotonic() + 5
        while not (base / 'release').exists() and time.monotonic() < deadline: time.sleep(.01)
    ledger.write_text('running')
    os.write(ready, b'published 707070\n'); os.close(ready); sys.exit(0)
if args == [str(root / 'core/setup_litestream.py')]:
    record('setup-litestream-stub')
    config = Path.home() / '.codeyOS/litestream.yml'
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text('fixture-only')
    sys.exit(0)
if args == [str(root / 'core/backup_secrets.py')]:
    record('backup-secrets-stub')
    sys.exit(0)
if len(args) > 1 and args[:2] == ['-m', 'telemetry.cli']:
    record('metrics-stub', argv=args[2:], cwd=os.getcwd()); sys.exit(17)
if args and args[0] == str(root / 'core/cli_client.py'):
    if args[1:] == ['status'] and os.environ.get('FIXTURE_ALLOW_RPC') == '1':
        record('status-rpc-fixture')
        os.execv(sys.executable, [sys.executable, *args])
    if args[1:] == ['plain prompt'] or args[1:] == ['hello']:
        record('direct-main-stub', argv=args[1:], cwd=os.getcwd()); sys.exit(0)
    blocked()
blocked()
'''


@pytest.fixture
def harness(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    home, state = tmp_path / "home", tmp_path / "selected state"
    home.mkdir()
    for executable in ("python3", "bash", "timeout", "cloudflared"):
        path = bin_dir / executable
        path.write_text(f"#!{sys.executable}\n" + STUB)
        path.chmod(0o700)
    for executable in ("readlink", "mkdir", "mktemp", "rm", "cat"):
        (bin_dir / executable).symlink_to(shutil.which(executable))
    app = tmp_path / "aigentik app"
    app.mkdir()
    (app / "index.js").write_text("fixture must never execute")
    litestream = home / "go/bin/litestream"
    litestream.parent.mkdir(parents=True)
    litestream.write_text(f"#!{sys.executable}\n" + STUB)
    litestream.chmod(0o700)
    env = dict(os.environ, HOME=str(home), CODEY_STATE_DIR=str(state), CODEY_OS_DIR=str(ROOT), PYTHONPATH=str(ROOT), PATH=str(bin_dir), TMPDIR=str(tmp_path), AIGENTIK_DIR=str(app), CLOUDFLARE_TUNNEL_TOKEN="fixture-secret-never-print", FIXTURE_REPO=str(ROOT), FIXTURE_BASE=str(tmp_path), FIXTURE_BASH=BASH, FIXTURE_RESULTS=str(tmp_path / "results"), CODEY_ACTION_GATEWAY_AUDIT=str(tmp_path / "audit.jsonl"))
    for name in ("GOOGLE_APPLICATION_CREDENTIALS", "CODEY_CONFIG_PATH", "RESTORICON_DB_PATH", "RESTORICON_API_HOST", "RESTORICON_API_PORT"):
        env.pop(name, None)
    item = SimpleNamespace(root=tmp_path, bin=bin_dir, home=home, state=state, app=app, env=env)
    yield item
    (tmp_path / "release").touch()
    assert all(event["label"] != "BLOCKED" for event in events(item)), "unknown external command attempted"


def events(harness):
    trace = harness.root / "commands.jsonl"
    return [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []


def run_command(harness, command, env=None, cwd=None):
    child = subprocess.Popen(command, env=env or harness.env, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        stdout, stderr = child.communicate(timeout=15)
        assert "fixture-secret-never-print" not in stdout + stderr
        return SimpleNamespace(returncode=child.returncode, stdout=stdout, stderr=stderr)
    finally:
        (harness.root / "release").touch()
        if child.poll() is None:
            # Only this actual retained command Popen; simulated helpers have
            # finite waits and Bash retains/reaps its coprocess jobs above.
            try:
                child.wait(timeout=7)
            except subprocess.TimeoutExpired:
                child.terminate()
                try: child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
        child.stdout.close()
        child.stderr.close()


def run_public(harness, entry, *args, env=None):
    return run_command(harness, [BASH, str(ROOT / entry), *args], env=env)


def run_function(harness, function, env=None):
    return run_command(harness, [BASH, "-c", 'source "$1"; "$2"', "fixture", str(ROOT / "lib/service_manager.sh"), function], env=env)


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    pytest.fail("fixture did not reach its expected state")


def configure_daemon(harness):
    harness.state.mkdir(exist_ok=True)
    paths = {name + "_file": str(harness.root / ("custom daemon " + name)) for name in ("pid", "socket", "log")}
    (harness.state / "config.json").write_text(json.dumps({"daemon": paths}))
    return paths


def test_source_is_pure_and_public_status_audits_read_outside_selected_root(harness):
    source = subprocess.run([BASH, "-c", 'source "$1"', "fixture", str(ROOT / "lib/service_manager.sh")], env=harness.env, capture_output=True, text=True, timeout=5, check=False)
    assert source.returncode == 0 and not harness.state.exists()
    result = run_public(harness, "codey", "status")
    assert result.returncode == 0 and "absent-dead" in result.stdout
    # Existing gateway import initializes only the fixed empty schema/checkpoint
    # bootstrap. The audited public read does not create lifecycle/config state.
    assert {path.name for path in harness.state.iterdir()} == {"state.db", "checkpoints"}
    assert list((harness.state / "checkpoints").iterdir()) == []
    with sqlite3.connect(harness.state / "state.db") as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {"state", "task_queue", "episodic_log", "model_state", "project_files", "working_memory", "checkpoints", "sqlite_sequence"}
        for table in tables:
            assert connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] == 0
    audit = [json.loads(line) for line in (harness.root / "audit.jsonl").read_text().splitlines()]
    assert len(audit) == 1 and audit[0]["authority"] == "READ"
    assert not any(event["label"].startswith("identity:") for event in events(harness))


def test_all_six_start_profiles_use_owned_helper_and_stub_every_setup_effect(harness):
    paths = configure_daemon(harness)
    result = run_public(harness, "codey", "start")
    assert result.returncode == 0, result.stderr
    profiles = [event for event in events(harness) if event["label"] == "profile"]
    assert [event["service"] for event in profiles] == ["codeyOS", "restoricon-api", "aigentik", "cloudflared", "litestream", "backup-docs"]
    daemon = profiles[0]
    assert daemon["argv"] == ["python3", str(ROOT / "core/daemon_bootstrap.py"), paths["pid_file"], paths["socket_file"], paths["log_file"]]
    assert profiles[2]["argv"] == ["node", "index.js"] and profiles[2]["cwd"] == str(harness.app)
    # G15h (NEW-1021): the tunnel token is delivered via the helper's env, never argv.
    assert profiles[3]["argv"] == ["cloudflared", "tunnel", "run"]
    assert "fixture-secret-never-print" not in (harness.root / "commands.jsonl").read_text()
    labels = [event["label"] for event in events(harness)]
    assert labels.count("setup-litestream-stub") == labels.count("timeout-secrets-stub") == labels.count("backup-secrets-stub") == 1
    assert "application readiness pending" in result.stdout
    again = run_public(harness, "codey", "start")
    assert again.returncode == 0
    assert len([event for event in events(harness) if event["label"] == "profile"]) == 6
    audit = [json.loads(line) for line in (harness.root / "audit.jsonl").read_text().splitlines()]
    assert len(audit) == 2 and all(row["authority"] == "ACT" and row["outcome"] == "allowed" for row in audit)
    assert all(row["action"] == "service.all.start" for row in audit)


def test_composite_stop_attempts_every_service_and_restart_aborts_failed_stop(harness):
    env = dict(harness.env, FIXTURE_FAIL_SERVICE="aigentik")
    result = run_public(harness, "codey-stop", env=env)
    assert result.returncode != 0 and "Requested services stopped" not in result.stdout
    stopped = [event["service"] for event in events(harness) if event["label"] == "identity:stop"]
    assert stopped == ["backup-docs", "litestream", "cloudflared", "aigentik", "restoricon-api", "codeyOS", "llama-server-8080"]
    result = run_public(harness, "codey", "restart", env=env)
    assert result.returncode != 0
    assert not any(event["label"] == "profile" for event in events(harness))


@pytest.mark.parametrize("entry,args", [("codey", []), ("codey", ["a prompt", "--yolo"]), ("codey", ["start", "prompt"]), ("codey-start", ["hello world"])])
def test_bootstrap_environment_and_original_tui_arguments(harness, entry, args):
    credential = harness.home / ".codeyOS/gcp_credentials.json"
    credential.parent.mkdir()
    credential.write_text("fixture credential contents must never be read")
    env = dict(harness.env, FIXTURE_FAKE_TUI="1", FIXTURE_TUI_RC="23", PYTHONPATH=str(ROOT) + ":existing", GOOGLE_APPLICATION_CREDENTIALS="inherited-credential")
    result = run_public(harness, entry, *args, env=env)
    assert result.returncode == 23, result.stderr
    tui = next(event for event in events(harness) if event["label"] == "TUI")
    assert tui["argv"] == (args[1:] if args and args[0] == "start" else args)
    assert tui["codey_dir"] == str(ROOT) and tui["pythonpath"] == str(ROOT) + ":existing"
    assert tui["credentials"] == str(credential)
    assert "fixture credential contents" not in result.stdout + result.stderr


def test_failed_bootstrap_never_launches_tui(harness):
    result = run_public(harness, "codey-start", env=dict(harness.env, FIXTURE_FAIL_SERVICE="restoricon-api", FIXTURE_FAKE_TUI="1"))
    assert result.returncode != 0
    assert not any(event["label"] == "TUI" for event in events(harness))


@pytest.mark.parametrize("entry,args", [("codey", ["help"]), ("codey-start", []), ("codey-stop", []), ("codeydOS", ["status"]), ("codeyOS", ["hello"]), ("codey-metrics", ["doctor"])])
def test_installed_relative_symlink_chain_with_spaces_resolves_real_root(harness, entry, args):
    links = harness.root / "installed links"
    links.mkdir()
    (links / "target").symlink_to(ROOT / entry)
    (links / entry).symlink_to("target")
    env = dict(harness.env, FIXTURE_FAKE_TUI="1")
    child = run_command(harness, [BASH, str(links / entry), *args], env=env, cwd=harness.root)
    assert child.returncode in (0, 1, 17), child.stderr
    assert "No such file" not in child.stderr and "Cannot resolve" not in child.stderr
    if entry == "codey-start":
        event = next(event for event in events(harness) if event["label"] == "TUI")
        assert event["cwd"] == str(harness.root)
        daemon = next(event for event in events(harness) if event["label"] == "profile" and event["service"] == "codeyOS")
        assert daemon["cwd"] == str(harness.root)
    elif entry == "codeyOS":
        event = next(event for event in events(harness) if event["label"] == "direct-main-stub")
        assert event["cwd"] == str(harness.root)
    if entry == "codey-metrics":
        event = next(event for event in events(harness) if event["label"] == "metrics-stub")
        assert event["cwd"] == str(ROOT) and child.returncode == 17


@pytest.mark.parametrize("values", [[], ["p", "s"], ["p", "s", "l", "extra"], ["", "s", "l"], ["p\0", "s", "l"], ["p" * 4097, "s", "l"], ["relative p", "/custom socket", "/custom log"], ["/p", "rel/s", "/l"], ["/p", "/s", "./l"]])
def test_daemon_bootstrap_rejects_invalid_path_schema_before_import(values, monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "core.daemon", SimpleNamespace(main=lambda **kwargs: calls.append(kwargs)))
    with pytest.raises(ValueError, match="Invalid daemon path snapshot"):
        daemon_bootstrap.main(values)
    assert calls == []


def test_daemon_bootstrap_hands_snapshot_to_shared_guard_without_reselection(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "core.daemon", SimpleNamespace(main=lambda **kwargs: calls.append(kwargs)))
    daemon_bootstrap.main(["/absolute p", "/custom socket", "/custom log"])
    assert [str(value) for value in (calls[0]["paths"].pid_file, calls[0]["paths"].socket_file, calls[0]["paths"].log_file)] == ["/absolute p", "/custom socket", "/custom log"]


@pytest.mark.parametrize("service,function", [("aigentik", "aigentik"), ("litestream", "litestream"), ("backup-docs", "backup_docs")])
def test_discovered_processes_remain_diagnostic_and_are_never_killed(harness, service, function):
    if service == "aigentik":
        (harness.app / "main.py").write_text("import time; time.sleep(60)")
        cwd, argv, executable = harness.app, ["python3", "main.py"], sys.executable
    elif service == "litestream":
        harness.state.mkdir()
        (harness.state / "replicate").write_text("import time; time.sleep(60)")
        cwd, argv, executable = harness.state, ["litestream", "replicate"], sys.executable
    else:
        cwd, argv, executable = ROOT / "core", ["python3", "-c", "import time; time.sleep(60)", "backup_documents.py"], sys.executable
    child = subprocess.Popen(argv, cwd=cwd, executable=executable, env=harness.env)
    try:
        assert child.poll() is None
        env = dict(harness.env, FIXTURE_DISCOVERY_PIDS=str(child.pid))
        status = run_function(harness, "status_" + function, env=env)
        assert "UNTRACKED" in status.stdout and str(child.pid) in status.stdout
        start = run_function(harness, "start_" + function, env=env)
        assert start.returncode != 0 and "diagnostic only" in start.stderr
        stop = run_function(harness, "stop_" + function, env=env)
        assert stop.returncode != 0 and "preserved" in stop.stderr
        assert child.poll() is None
        assert not any(event["label"] == "profile" for event in events(harness))
    finally:
        if child.poll() is None:
            child.terminate()
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)
        else:
            child.wait(timeout=3)


@pytest.mark.parametrize("bad", ["0", "-1", "malformed", "legacy-live", "boot", "start", "uid"])
def test_unsafe_records_refuse_public_start_stop_and_preserve_evidence(harness, bad):
    harness.state.mkdir()
    pid = harness.state / "restoricon-api.pid"
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], env=harness.env)
    try:
        if bad in ("boot", "start", "uid"):
            with identity.LifecycleRecord(pid, "restoricon-api") as record:
                record.publish(child.pid)
            sidecar = Path(str(pid) + ".identity")
            data = json.loads(sidecar.read_text())
            field = {"boot": "boot_id", "start": "start_ticks", "uid": "uid"}[bad]
            data[field] = "wrong-boot" if bad == "boot" else data[field] + 1
            sidecar.write_text(json.dumps(data))
        else:
            pid.write_text(str(child.pid) if bad == "legacy-live" else bad)
        before = {path: path.read_bytes() for path in (pid, Path(str(pid) + ".identity")) if path.exists()}
        env = dict(harness.env, FIXTURE_REAL_IDENTITY="1")
        start = run_function(harness, "start_restoricon", env=env)
        stop = run_function(harness, "stop_restoricon", env=env)
        assert start.returncode == stop.returncode == 2
        assert all(path.read_bytes() == value for path, value in before.items())
        assert not any(event["label"] in ("profile", "FORBIDDEN_SIGNAL_ATTEMPT") for event in events(harness))
        assert child.poll() is None
    finally:
        if child.poll() is None:
            child.terminate()
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)
        else:
            child.wait(timeout=3)


@pytest.mark.parametrize("special", ["symlink", "fifo", "contended"])
def test_last_composite_lock_failure_prevents_every_service_effect(harness, special):
    harness.state.mkdir()
    pid = harness.state / "llama-server-8080.pid"
    lock = Path(str(pid) + ".lifecycle.lock")
    owned_lock = None
    target = harness.root / "unchanged"
    target.write_text("untouched")
    if special == "symlink":
        lock.symlink_to(target)
    elif special == "fifo":
        os.mkfifo(lock)
    else:
        owned_lock = identity.LifecycleRecord(pid, "llama-server-8080").__enter__()
    try:
        result = run_public(harness, "codey", "start")
        assert result.returncode == 2
        assert target.read_text() == "untouched"
        assert not any(event["label"].startswith("identity:") or event["label"].endswith("-stub") for event in events(harness))
    finally:
        if owned_lock is not None:
            owned_lock.__exit__(None, None, None)


def test_concurrent_composite_start_stop_cannot_interleave_effects(harness):
    outcomes = []
    failures = []
    env = dict(harness.env, FIXTURE_PAUSE_SPAWN="codeyOS")
    def first_start():
        try: outcomes.append(run_public(harness, "codey", "start", env=env))
        except BaseException as exc: failures.append(exc)  # noqa: BLE001 - convey thread failure to the test
    thread = threading.Thread(target=first_start)
    thread.start()
    try:
        wait_until(lambda: (harness.root / "spawn-paused").exists())
        competing = run_public(harness, "codey-stop")
        assert competing.returncode == 2
        assert not any(event["label"] == "identity:stop" and event["service"] != "llama-server-8080" for event in events(harness))
    finally:
        (harness.root / "release").touch()
        thread.join(timeout=15)
    assert not thread.is_alive() and not failures and outcomes[0].returncode == 0
    assert len([event for event in events(harness) if event["label"] == "profile"]) == 6


def test_retained_guardian_keeps_only_selected_composite_service_lock(harness):
    outcomes, failures = [], []
    env = dict(harness.env, FIXTURE_PROTOCOL_MODE="retained", FIXTURE_PROTOCOL_SERVICE="restoricon-api")
    def launch():
        try: outcomes.append(run_public(harness, "codey", "start", env=env))
        except BaseException as exc: failures.append(exc)  # noqa: BLE001 - convey thread failure to the test
    thread = threading.Thread(target=launch)
    thread.start()
    try:
        def result_ready():
            path = harness.root / "results"
            return path.exists() and path.read_bytes() == b"2\n"
        wait_until(result_ready)
        with pytest.raises(identity.UnsafeRecord), identity.LifecycleRecord(harness.state / "restoricon-api.pid", "restoricon-api", blocking=False):
            pytest.fail("retained guardian released its selected lock")
        # The earlier daemon and model locks are not inherited by guardian210.
        with identity.LifecycleRecord(harness.state / "codeyOS.pid", "codeyOS", blocking=False):
            pass
        with identity.LifecycleRecord(harness.state / "llama-server-8080.pid", "llama-server-8080", blocking=False):
            pass
    finally:
        (harness.root / "release").touch()
        thread.join(timeout=10)
    assert not thread.is_alive() and not failures and outcomes[0].returncode == 2


def test_inherited_credentials_and_pythonpath_are_preserved_without_default_file(harness):
    env = dict(harness.env, FIXTURE_FAKE_TUI="1", PYTHONPATH="existing", GOOGLE_APPLICATION_CREDENTIALS="configured-other-path")
    result = run_public(harness, "codey-start", env=env)
    assert result.returncode == 0
    tui = next(event for event in events(harness) if event["label"] == "TUI")
    assert tui["pythonpath"] == str(ROOT) + ":existing" and tui["credentials"] == "configured-other-path"


def test_optional_absence_is_success_without_setup_or_spawn_attempt(harness):
    (harness.app / "index.js").unlink()
    (harness.home / "go/bin/litestream").unlink()
    (harness.bin / "cloudflared").unlink()
    result = run_public(harness, "codey", "start")
    assert result.returncode == 0, result.stderr
    assert [event["service"] for event in events(harness) if event["label"] == "profile"] == ["codeyOS", "restoricon-api", "backup-docs"]
    assert not any(event["label"] in ("setup-litestream-stub", "backup-secrets-stub") for event in events(harness))
    assert result.stdout.count("optional service unavailable/not configured") == 3


def test_malformed_composite_ready_keeps_complete_operation_locked_until_helper_exit(harness):
    outcomes, failures = [], []
    env = dict(harness.env, FIXTURE_PROTOCOL_MODE="malformed", FIXTURE_PROTOCOL_SERVICE="restoricon-api")
    def launch():
        try: outcomes.append(run_public(harness, "codey", "start", env=env))
        except BaseException as exc: failures.append(exc)  # noqa: BLE001 - convey thread failure to the test
    thread = threading.Thread(target=launch)
    thread.start()
    try:
        wait_until(lambda: any(event["label"] == "profile" and event["service"] == "restoricon-api" for event in events(harness)))
        time.sleep(.1)
        assert not (harness.root / "results").exists()
        with pytest.raises(identity.UnsafeRecord), identity.LifecycleRecord(harness.state / "codeyOS.pid", "codeyOS", blocking=False):
            pytest.fail("malformed protocol released outer composite lock early")
    finally:
        (harness.root / "release").touch()
        thread.join(timeout=10)
    assert not thread.is_alive() and not failures and outcomes[0].returncode == 2
    assert "service identity requires inspection" in outcomes[0].stderr
    assert len([event for event in events(harness) if event["label"] == "profile"]) == 2


def test_codeydos_config_creates_only_selected_disposable_config(harness):
    assert not harness.state.exists()
    result = run_public(harness, "codeydOS", "config")
    assert result.returncode == 0, result.stderr
    assert json.loads((harness.state / "config.json").read_text())["daemon"]["pid_file"] == str(harness.state / "codeyOS.pid")
    audit = [json.loads(line) for line in (harness.root / "audit.jsonl").read_text().splitlines()]
    assert len(audit) == 1 and audit[0]["authority"] == "ACT" and audit[0]["outcome"] == "allowed"
    assert not any(event["label"].startswith("identity:") for event in events(harness))


def test_codeydos_config_refuses_existing_relative_daemon_paths_unchanged(harness):
    harness.state.mkdir()
    config = harness.state / "config.json"
    config.write_text(json.dumps({"daemon": {"pid_file": "relative.pid"}}))
    before = config.read_bytes()

    result = run_public(harness, "codeydOS", "config")

    assert result.returncode == 2
    assert "daemon.pid_file" in result.stderr and "absolute" in result.stderr
    assert "Default config created" not in result.stdout + result.stderr
    assert config.read_bytes() == before
    assert not any(
        event["label"].startswith("identity:")
        or event["label"] == "profile"
        or event["label"].endswith("-stub")
        for event in events(harness)
    )
    assert not list(harness.state.glob("*.pid"))
    assert not list(harness.state.glob("*.lifecycle.lock"))
    audit = [json.loads(line) for line in (harness.root / "audit.jsonl").read_text().splitlines()]
    assert len(audit) == 1
    assert audit[0]["action"] == "service.config-create"
    assert audit[0]["authority"] == "ACT" and audit[0]["outcome"] == "failed"


def test_public_client_requires_identity_and_uses_one_custom_socket_snapshot(harness):
    paths = configure_daemon(harness)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], env=harness.env)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stop = threading.Event()
    received, failures = [], []
    worker = None
    try:
        with tempfile.TemporaryDirectory(prefix="wp21-b3-uds-") as directory:
            address = str(Path(directory) / "s")
            paths["socket_file"] = address
            (harness.state / "config.json").write_text(json.dumps({"daemon": paths}))
            pid = Path(paths["pid_file"])
            with identity.LifecycleRecord(pid, "codeyOS") as record:
                record.publish(child.pid)
            server.bind(address)
            server.listen(1)
            server.settimeout(.1)
            def serve():
                while not stop.is_set():
                    try: connection, _ = server.accept()
                    except TimeoutError: continue
                    except OSError: return
                    try:
                        with connection:
                            connection.settimeout(3)
                            received.append(json.loads(connection.recv(4096)))
                            connection.sendall(b'{"status":"ok","pid":123,"tasks":{}}')
                    except BaseException as exc: failures.append(exc)  # noqa: BLE001 - convey thread failure to test
            worker = threading.Thread(target=serve)
            worker.start()
            env = dict(harness.env, FIXTURE_ALLOW_RPC="1")
            valid = run_public(harness, "codeyOS", "status", env=env)
            assert valid.returncode == 0 and "Daemon Status" in valid.stdout, valid.stderr
            assert received == [{"cmd": "health", "data": {}}]
            sidecar = Path(str(pid) + ".identity")
            sidecar.unlink()  # live legacy PID must never authorize a connection
            before = pid.read_bytes()
            refused = run_public(harness, "codeyOS", "status", env=env)
            assert refused.returncode != 0 and "unsafe/unverifiable" in refused.stderr
            assert received == [{"cmd": "health", "data": {}}] and pid.read_bytes() == before
            direct = run_public(harness, "codeyOS", "plain prompt", env=env)
            assert direct.returncode == 0
            assert any(event["label"] == "direct-main-stub" for event in events(harness))
            assert len(received) == 1
    finally:
        stop.set()
        server.close()
        if worker is not None:
            worker.join(timeout=3)
        if child.poll() is None:
            child.terminate()
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=3)
        else:
            child.wait(timeout=3)
        if worker is not None:
            assert not worker.is_alive() and not failures


@pytest.mark.parametrize("entry", ["codey", "codey-start", "codey-stop", "codeyOS", "codeydOS", "codey-metrics"])
def test_root_resolution_failure_never_falls_back_to_caller_directory(harness, entry):
    readlink = harness.bin / "readlink"
    readlink.unlink()
    readlink.write_text(f"#!{sys.executable}\nimport sys; sys.exit(1)\n")
    readlink.chmod(0o700)
    result = run_public(harness, entry)
    assert result.returncode == 2 and "Cannot resolve installed" in result.stderr
    assert events(harness) == [] and not harness.state.exists()
