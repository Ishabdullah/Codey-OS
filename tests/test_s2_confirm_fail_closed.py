"""S2-D / NEW-1074: utils.logger.confirm fails closed off-tty and flushes
stale typeahead on a tty. Real pty children are tracked by PID."""

import os
import pty
import select
import signal
import sys
import time
from pathlib import Path

import pytest

import utils.logger as logger

REPO = Path(__file__).resolve().parent.parent


class _Stdin:
    def __init__(self, text="y\ny\n", tty=False):
        import io

        self._io = io.StringIO(text)
        self._tty = tty
        self.reads = 0

    def isatty(self):
        return self._tty

    def readline(self, *a):
        self.reads += 1
        return self._io.readline(*a)

    read = readline


def test_non_tty_with_y_available_is_false_and_unread(monkeypatch):
    fake = _Stdin("y\ny\n")
    monkeypatch.setattr(sys, "stdin", fake)
    assert logger.confirm("go?") is False
    assert fake.reads == 0 and fake._io.tell() == 0


def test_stdin_none_is_false(monkeypatch):
    monkeypatch.setattr(sys, "stdin", None)
    assert logger.confirm("go?") is False


def test_isatty_raising_is_false(monkeypatch):
    class Boom:
        def isatty(self):
            raise ValueError("closed")

    monkeypatch.setattr(sys, "stdin", Boom())
    assert logger.confirm("go?") is False


def test_non_tty_never_reaches_console_input(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("console.input must not be called off-tty")

    monkeypatch.setattr(logger.console, "input", boom)
    monkeypatch.setattr(logger, "_stdin_is_tty", lambda: False)
    assert logger.confirm("go?") is False


@pytest.mark.parametrize("answers,expected", [(["y"], True), (["yes"], True), (["n"], False), ([""], False)])
def test_tty_seam_answers(monkeypatch, answers, expected):
    it = iter(answers)
    monkeypatch.setattr(logger, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(logger, "_flush_stdin_typeahead", lambda: None)
    monkeypatch.setattr(logger.console, "input", lambda q: next(it))
    assert logger.confirm("go?") is expected


def test_tty_eof_and_interrupt_false(monkeypatch):
    monkeypatch.setattr(logger, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(logger, "_flush_stdin_typeahead", lambda: None)
    for exc in (EOFError, KeyboardInterrupt):
        def raiser(q, exc=exc):
            raise exc()

        monkeypatch.setattr(logger.console, "input", raiser)
        assert logger.confirm("go?") is False


# --- real pty ---------------------------------------------------------------

_CHILD = (
    "import sys; sys.path.insert(0, %r)\n"
    "import time\n"
    "from utils.logger import confirm\n"
    "if len(sys.argv) > 1 and sys.argv[1] == 'wait':\n"
    "    open(sys.argv[2], 'w').write('ready')\n"
    "    while True:\n"
    "        import os\n"
    "        if os.path.exists(sys.argv[3]): break\n"
    "        time.sleep(0.02)\n"
    "r = confirm('Do it?')\n"
    "sys.stdout.write('\\nRESULT=%%s\\n' %% r); sys.stdout.flush()\n"
) % str(REPO)


def _run_pty(tmp_path, send_before=None, send_after=None, close_after=False, wait_gate=False, child=None, marker=b"[y/N]"):
    script = tmp_path / "child.py"
    script.write_text(child or _CHILD)
    ready, go = tmp_path / "ready", tmp_path / "go"
    argv = [sys.executable, str(script)]
    if wait_gate:
        argv += ["wait", str(ready), str(go)]
    pid, fd = pty.fork()
    if pid == 0:
        os.execv(argv[0], argv)
    out = b""
    try:
        if wait_gate:
            t0 = time.time()
            while not ready.exists() and time.time() - t0 < 20:
                time.sleep(0.02)
            if send_before:
                os.write(fd, send_before)
                time.sleep(0.3)  # let the tty line discipline buffer it
            go.write_text("go")
        sent = False
        t0 = time.time()
        while time.time() - t0 < 20:
            r, _, _ = select.select([fd], [], [], 0.2)
            if r:
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
            if not sent and marker in out and (send_after is not None or close_after):
                time.sleep(0.2)
                if send_after is not None:
                    os.write(fd, send_after)
                if close_after:
                    os.write(fd, b"\x04")
                sent = True
            if b"RESULT=" in out and out.rstrip().endswith((b"True", b"False")):
                break
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            os.waitpid(pid, 0)
        except ChildProcessError:
            pass
        os.close(fd)
    return out.decode("utf-8", "replace")


def test_pty_y_after_prompt_approves_and_shows_hint(tmp_path):
    out = _run_pty(tmp_path, send_after=b"y\n")
    assert "[y/N]" in out and "RESULT=True" in out


def test_pty_y_prebuffered_before_prompt_not_consent(tmp_path):
    out = _run_pty(tmp_path, send_before=b"y\n", wait_gate=True, send_after=b"n\n")
    assert "RESULT=False" in out and "RESULT=True" not in out


def test_pty_prebuffered_y_alone_does_not_approve_then_eof(tmp_path):
    out = _run_pty(tmp_path, send_before=b"y\n", wait_gate=True, close_after=True)
    assert "RESULT=False" in out


def test_pty_n_and_enter_and_eof_false(tmp_path):
    assert "RESULT=False" in _run_pty(tmp_path, send_after=b"n\n")
    assert "RESULT=False" in _run_pty(tmp_path, send_after=b"\n")
    assert "RESULT=False" in _run_pty(tmp_path, close_after=True)


def test_file_tools_seam_delegates_to_logger_and_both_patch_points_work(monkeypatch):
    import tools.file_tools as ft

    monkeypatch.setattr(logger, "_stdin_is_tty", lambda: True)
    assert ft._stdin_is_tty() is True  # logger patch is effective via the wrapper
    monkeypatch.setattr(logger, "_stdin_is_tty", lambda: False)
    assert ft._stdin_is_tty() is False
    monkeypatch.setattr(ft, "_stdin_is_tty", lambda: True)  # file_tools patch point
    assert ft._stdin_is_tty() is True


_GATE = (
    "import sys, os, time\n"
    "if len(sys.argv) > 1 and sys.argv[1] == 'wait':\n"
    "    open(sys.argv[2], 'w').write('ready')\n"
    "    while not os.path.exists(sys.argv[3]):\n"
    "        time.sleep(0.02)\n"
)

_PEER_CHILD = (
    "import sys; sys.path.insert(0, %r)\n" % str(REPO) + _GATE +
    "from unittest.mock import patch\n"
    "from core.peer_cli import PEER_REGISTRY, PeerCLIManager\n"
    "qwen = next(c for c in PEER_REGISTRY if c.name == 'qwen')\n"
    "with patch.object(PeerCLIManager, 'available', return_value=[qwen]):\n"
    "    r = PeerCLIManager().confirm(qwen, 'code', 'do a thing')\n"
    "sys.stdout.write('\\nRESULT=%s\\n' % (r,)); sys.stdout.flush()\n"
)

_COMMIT_CHILD = (
    "import sys, os, subprocess, importlib.util; sys.path.insert(0, %r)\n" % str(REPO) + _GATE +
    "from types import ModuleType\n"
    "from unittest.mock import Mock\n"
    "import core\n"
    "for name, attrs in {'context': {}, 'dashboard_data': {'get_render_text': Mock()},\n"
    "    'inference_v2': {'was_last_streamed': Mock()}, 'loader_v2': {'get_loader': Mock()},\n"
    "    'sysmon': {'get_monitor': Mock()}}.items():\n"
    "    m = ModuleType('core.' + name); m.__dict__.update(attrs)\n"
    "    sys.modules['core.' + name] = m; setattr(core, name, m)\n"
    "spec = importlib.util.spec_from_file_location('_s2_main', %r)\n" % str(REPO / "main.py") +
    "main = importlib.util.module_from_spec(spec); sys.modules['_s2_main'] = main; spec.loader.exec_module(main)\n"
    "from core import githelper\n"
    "githelper.generate_commit_message = lambda d, h: 'suggested msg'\n"
    "main.handle_command('/git commit', [])\n"
    "subj = subprocess.run(['git', 'log', '-1', '--format=%s'], capture_output=True, text=True).stdout.strip()\n"
    "sys.stdout.write('\\nRESULT=SUBJECT:%s\\n' % subj); sys.stdout.flush()\n"
)


def test_pty_peer_prebuffered_y_not_consent(tmp_path):
    """NEW-1074: real pty; a stale y typed before the peer prompt is flushed."""
    out = _run_pty(tmp_path, send_before=b"y\n", wait_gate=True, send_after=b"n\n", child=_PEER_CHILD, marker=b"\xe2\x86\x92")
    assert "RESULT=(False, None)" in out, out


def test_pty_peer_y_after_prompt_approves(tmp_path):
    out = _run_pty(tmp_path, send_after=b"y\n", child=_PEER_CHILD, marker=b"\xe2\x86\x92")
    assert "RESULT=(True, None)" in out, out


def _commit_env(tmp_path, monkeypatch):
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=repo, check=True)
    (repo / "one.txt").write_text("one\n")
    subprocess.run(["git", "add", "one.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo, check=True)
    (repo / "one.txt").write_text("one changed\n")
    home = tmp_path / "home"
    (home / ".codeyOS").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEY_STATE_DIR", str(home / ".codeyOS"))
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.chdir(repo)
    return repo


def _head(repo):
    import subprocess

    return subprocess.run(["git", "log", "-1", "--format=%s"], cwd=repo, capture_output=True, text=True).stdout.strip()


def test_pty_commit_prebuffered_enter_not_accepted(tmp_path, monkeypatch):
    """NEW-1074: a stale Enter before the /git commit accept prompt is flushed
    and cannot accept the suggested message."""
    repo = _commit_env(tmp_path, monkeypatch)
    out = _run_pty(tmp_path, send_before=b"\n", wait_gate=True, send_after=b"typed msg\n", child=_COMMIT_CHILD, marker=b"Press Enter")
    assert "RESULT=SUBJECT:typed msg" in out, out
    assert _head(repo) == "typed msg"


def test_pty_commit_enter_after_prompt_accepts(tmp_path, monkeypatch):
    repo = _commit_env(tmp_path, monkeypatch)
    out = _run_pty(tmp_path, send_after=b"\n", child=_COMMIT_CHILD, marker=b"Press Enter")
    assert "RESULT=SUBJECT:suggested msg" in out, out


def test_pty_commit_prebuffered_enter_then_eof_no_commit(tmp_path, monkeypatch):
    repo = _commit_env(tmp_path, monkeypatch)
    out = _run_pty(tmp_path, send_before=b"\n", wait_gate=True, close_after=True, child=_COMMIT_CHILD, marker=b"Press Enter")
    assert "RESULT=SUBJECT:base" in out, out
