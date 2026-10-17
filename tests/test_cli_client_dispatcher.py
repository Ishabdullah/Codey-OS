"""Actual public dispatcher in disposable copied repos with mocked RPC transport.

Every subprocess runs only the real shell/client and fixed fixture modules. No
model, installed service, actual socket, cloud command, or real HOME is used.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash")

CONFIG = '''
import json, os
from pathlib import Path
from types import SimpleNamespace
class Config:
    def get(self, *keys): return str(Path(os.environ['FIXTURE_STATE']) / 'custom db')
def get_config(): return Config()
def resolve_daemon_paths(config):
    data = json.loads(os.environ['FIXTURE_PATHS'])
    return SimpleNamespace(**{key: Path(value) for key, value in data.items()})
'''
IDENTITY = '''
import os
from types import SimpleNamespace
RUNNING, DEAD, UNSAFE = 'RUNNING', 'DEAD', 'UNSAFE'
def inspect_record(path, service):
    assert service == 'codeyOS'
    return SimpleNamespace(state=os.environ.get('FIXTURE_IDENTITY', RUNNING))
'''
MAIN = '''
import json, os, signal, sys
from pathlib import Path
def main():
    Path(os.environ['FIXTURE_DIRECT_TRACE']).write_text(json.dumps({
        'argv': sys.argv[1:], 'stdin': sys.stdin.read(), 'cwd': os.getcwd()}))
    print('foreground stdout', flush=True)
    print('foreground stderr', file=sys.stderr, flush=True)
    outcome = os.environ.get('FIXTURE_OUTCOME', 'return7')
    if outcome == 'return7': return 7
    if outcome == 'exit7': raise SystemExit(7)
    if outcome == 'interrupt': raise KeyboardInterrupt()
    if outcome == 'term': os.kill(os.getpid(), signal.SIGTERM)
    if outcome == 'exception': raise RuntimeError('fixture foreground error')
    return None
'''
TRANSPORT = '''
import builtins, json, os, socket, sys
from pathlib import Path
_real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith(('core.daemon', 'core.inference', 'core.loader', 'torch')) and name != 'core.daemon_config':
        raise AssertionError('model/daemon import in client: ' + name)
    if name == 'main' and os.environ.get('FIXTURE_DIRECT') != '1':
        raise AssertionError('main imported in RPC branch')
    return _real_import(name, *args, **kwargs)
builtins.__import__ = guarded
class Channel:
    def __init__(self): self.sent = False
    def settimeout(self, value): self.timeout = value
    def connect(self, path):
        assert path == json.loads(os.environ['FIXTURE_PATHS'])['socket_file']
        Path(os.environ['FIXTURE_CONNECT_TRACE']).write_text(path)
        if os.environ.get('FIXTURE_SOCKET_ERROR') == 'timeout': raise TimeoutError('fixture timeout')
        if os.environ.get('FIXTURE_SOCKET_ERROR') == 'refused': raise OSError('fixture refused')
    def sendall(self, data):
        Path(os.environ['FIXTURE_RPC_TRACE']).write_bytes(data)
    def recv(self, size):
        if self.sent: return b''
        self.sent = True
        return os.environ.get('FIXTURE_RESPONSE', '{"status":"ok"}').encode()
    def close(self):
        if os.environ.get('FIXTURE_CLOSE_ERROR') == '1': raise OSError('fixture cleanup')
def channel(family, kind):
    assert family == socket.AF_UNIX and kind == socket.SOCK_STREAM
    return Channel()
socket.socket = channel
# Only copied fixture paths use this override. The fake UNIX socket is a Path,
# with connect assertions in Channel; no socket or state file is created.
Path.is_socket = lambda self: True
'''


@pytest.fixture
def dispatcher(tmp_path):
    # Quotes/newlines/metacharacters in the actual executing source paths cannot
    # enter generated Python: these are real wrapper/client copies, not strings
    # interpolated into a Python program by production code.
    repo = tmp_path / 'repo "\n; $(literal)'
    (repo / "core").mkdir(parents=True)
    shutil.copy2(ROOT / "codeyOS", repo / "codeyOS")
    shutil.copy2(ROOT / "core/cli_client.py", repo / "core/cli_client.py")
    (repo / "core/__init__.py").write_text("")
    (repo / "core/daemon_config.py").write_text(CONFIG)
    (repo / "core/process_identity.py").write_text(IDENTITY)
    (repo / "main.py").write_text(MAIN)
    (repo / "sitecustomize.py").write_text(TRANSPORT)
    home = tmp_path / "home"
    state = tmp_path / 'state "\n; literal'
    paths = {key: str(state / name) for key, name in (("pid_file", 'pid "\n'), ("socket_file", "socket ';$()"), ("log_file", "log `literal`"))}
    env = dict(os.environ, HOME=str(home), CODEY_STATE_DIR=str(state), PYTHONPATH=str(repo),
               FIXTURE_STATE=str(state), FIXTURE_PATHS=json.dumps(paths),
               FIXTURE_DIRECT_TRACE=str(tmp_path / "direct.json"), FIXTURE_RPC_TRACE=str(tmp_path / "rpc.json"),
               FIXTURE_CONNECT_TRACE=str(tmp_path / "connect.txt"))
    # Avoid carrying Python instrumentation into the isolated child.
    env.pop("PYTHONSTARTUP", None)
    return SimpleNamespace(repo=repo, root=tmp_path, state=state, home=home, env=env)


def dispatch(fixture, arguments, **updates):
    return subprocess.run([BASH, str(fixture.repo / "codeyOS"), *arguments],
                          cwd=fixture.root, env=dict(fixture.env, **updates), input="foreground input\n",
                          text=True, capture_output=True, timeout=10, check=False)


@pytest.mark.parametrize("marker", ["--bg", "--background"])
def test_public_background_literal_prompt_and_paths(dispatcher, marker):
    shaped = '"""; __import__("pathlib").Path("owned").touch(); #\n$() `x` \'literal\''
    result = dispatch(dispatcher, [marker, "--yolo", shaped, "a b", ""])
    assert result.returncode == 0, result.stderr
    assert json.loads((dispatcher.root / "rpc.json").read_text()) == {
        "cmd": "command", "data": {"prompt": shaped + " a b ", "yolo": True}}
    assert not (dispatcher.root / "owned").exists()
    assert not dispatcher.home.exists() and not dispatcher.state.exists()
    assert not (dispatcher.root / "direct.json").exists()


@pytest.mark.parametrize("command", ["task", "cancel"])
@pytest.mark.parametrize("identifier", ["0", "-1", "1+1", '1};__import__("os").system("x");#', "1\n", "١"])
def test_public_bad_id_rejected_without_connect(dispatcher, command, identifier):
    result = dispatch(dispatcher, [command, identifier])
    assert result.returncode == 1 and "positive decimal" in result.stderr
    assert not (dispatcher.root / "connect.txt").exists()
    assert not (dispatcher.root / "direct.json").exists()


@pytest.mark.parametrize(("arguments", "response", "expected"), [
    (["status"], {"status": "ok", "tasks": {}}, {"cmd": "health", "data": {}}),
    (["task", "list"], {"status": "ok", "tasks": []}, {"cmd": "task", "data": {"limit": 20}}),
    (["task", "003"], {"status": "ok", "task": {"id": 3, "description": "literal", "status": "done"}}, {"cmd": "task", "data": {"id": 3}}),
    (["cancel", "3"], {"status": "ok", "message": "cancelled"}, {"cmd": "cancel", "data": {"id": 3}}),
])
def test_public_rpc_branches_without_main(dispatcher, arguments, response, expected):
    result = dispatch(dispatcher, arguments, FIXTURE_RESPONSE=json.dumps(response))
    assert result.returncode == 0, result.stderr
    assert json.loads((dispatcher.root / "rpc.json").read_text()) == expected
    assert not (dispatcher.root / "direct.json").exists()


@pytest.mark.parametrize("arguments", [["status"], ["task", "list"], ["cancel", "3"], ["--bg", "prompt"]])
@pytest.mark.parametrize("failure", ["error", "empty", "invalid", "timeout", "refused"])
def test_public_rpc_failures_stay_nonzero(dispatcher, arguments, failure):
    updates = {"FIXTURE_CLOSE_ERROR": "1"}
    if failure in ("timeout", "refused"):
        updates["FIXTURE_SOCKET_ERROR"] = failure
    else:
        updates["FIXTURE_RESPONSE"] = {"error": '{"status":"error","message":"refused"}', "empty": "", "invalid": "{"}[failure]
    result = dispatch(dispatcher, arguments, **updates)
    assert result.returncode == 1 and "[ERROR]" in result.stderr
    assert not (dispatcher.root / "direct.json").exists()
    assert not dispatcher.state.exists()


@pytest.mark.parametrize("state", ["DEAD", "UNSAFE"])
def test_public_rpc_identity_refuses_without_fallback(dispatcher, state):
    result = dispatch(dispatcher, ["--bg", "hello"], FIXTURE_IDENTITY=state)
    assert result.returncode == 1
    assert not (dispatcher.root / "connect.txt").exists()
    assert not (dispatcher.root / "direct.json").exists()


@pytest.mark.parametrize("arguments", [["--daemon"], ["--ctx", "2048", '"\n;prompt'], []])
@pytest.mark.parametrize("outcome", ["return7", "exit7", "interrupt", "term", "exception", "none"])
def test_public_direct_exact_argv_streams_and_status(dispatcher, arguments, outcome):
    updates = {"FIXTURE_DIRECT": "1", "FIXTURE_OUTCOME": outcome}
    result = dispatch(dispatcher, arguments, **updates)
    baseline = subprocess.run([sys.executable, "-c", "import main,sys;sys.exit(main.main())", *arguments],
                              cwd=dispatcher.root, env=dict(dispatcher.env, **updates), input="foreground input\n",
                              text=True, capture_output=True, timeout=10, check=False)
    assert result.returncode == baseline.returncode
    assert result.returncode == {"return7": 7, "exit7": 7, "interrupt": -2, "term": -15, "exception": 1, "none": 0}[outcome]
    assert result.stdout == baseline.stdout == "foreground stdout\n"
    assert "foreground stderr\n" in result.stderr
    trace = json.loads((dispatcher.root / "direct.json").read_text())
    assert trace == {"argv": arguments, "stdin": "foreground input\n", "cwd": str(dispatcher.root)}
    assert not (dispatcher.root / "connect.txt").exists()
    assert not dispatcher.home.exists() and not dispatcher.state.exists()


def test_public_symlink_resolves_actual_fixed_client(dispatcher):
    link = dispatcher.root / 'client " link'
    link.symlink_to(dispatcher.repo / "codeyOS")
    result = subprocess.run([BASH, str(link), "--daemon"], cwd=dispatcher.root,
                            env=dict(dispatcher.env, FIXTURE_DIRECT="1"), input="literal", text=True,
                            capture_output=True, timeout=10, check=False)
    assert result.returncode == 7
    assert json.loads((dispatcher.root / "direct.json").read_text())["argv"] == ["--daemon"]
