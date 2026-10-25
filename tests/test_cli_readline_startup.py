"""Optional REPL readline setup; AST isolation avoids CLI/model startup."""

import ast
import builtins
import errno
import io
import os
import pty
import select
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


REPO = Path(__file__).resolve().parents[1]
SOURCE = (REPO / "main.py").read_text()
TREE = ast.parse(SOURCE)
HELPER = next(n for n in TREE.body if isinstance(n, ast.FunctionDef)
              and n.name == "_enable_interactive_readline")
HELPER_SOURCE = ast.get_source_segment(SOURCE, HELPER)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("RESTORICON_DB_PATH", str(tmp_path / "restoricon.db"))
    for name in list(os.environ):
        if name.lower().endswith("_proxy") or name in (
                "CODEY_DAEMON_MODE", "CODEY_NON_INTERACTIVE"):
            monkeypatch.delenv(name)


@pytest.fixture
def helper():
    namespace = {"os": os, "sys": sys}
    exec(compile(ast.Module(body=[HELPER], type_ignores=[]), "main.py", "exec"), namespace)
    return namespace[HELPER.name]


def _readline_import_spy(monkeypatch, *, missing=False):
    original = builtins.__import__
    imported = []

    def importer(name, *args, **kwargs):
        if name == "readline":
            imported.append(name)
            if missing:
                raise ImportError("readline unavailable")
            return SimpleNamespace()  # no actual editor enabled in pytest
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", importer)
    return imported


def test_tty_enables_optional_import(helper, monkeypatch):
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    imported = _readline_import_spy(monkeypatch)
    assert helper() is True
    assert imported == ["readline"]


@pytest.mark.parametrize("mode", ["off-tty", "one-shot", "daemon", "non-interactive"])
def test_unattended_modes_do_not_import(helper, monkeypatch, mode):
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: mode != "off-tty"))
    if mode == "daemon":
        monkeypatch.setenv("CODEY_DAEMON_MODE", "1")
    if mode == "non-interactive":
        monkeypatch.setenv("CODEY_NON_INTERACTIVE", "1")
    imported = _readline_import_spy(monkeypatch)
    assert helper(one_shot=mode == "one-shot") is False
    assert imported == []


@pytest.mark.parametrize("stream", [None, io.StringIO("piped\n")])
def test_missing_or_piped_stdin_skips(helper, monkeypatch, stream):
    monkeypatch.setattr(sys, "stdin", stream)
    imported = _readline_import_spy(monkeypatch)
    assert helper() is False
    assert imported == []


def test_closed_stdin_skips(helper, monkeypatch):
    stream = io.StringIO()
    stream.close()
    monkeypatch.setattr(sys, "stdin", stream)
    imported = _readline_import_spy(monkeypatch)
    assert helper() is False
    assert imported == []


def test_importerror_retains_ordinary_input(helper, monkeypatch):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", Tty("ordinary\n"))
    imported = _readline_import_spy(monkeypatch, missing=True)
    assert helper() is False
    assert input() == "ordinary"
    assert imported == ["readline"]


@pytest.mark.parametrize("one_shot", [False, True])
def test_actual_repl_hook_runs_before_banner_monitor_or_model(helper, monkeypatch, one_shot):
    """Execute the real entry statements, stopping at the banner, before any startup."""
    node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "repl")
    banner_index = next(i for i, n in enumerate(node.body)
                        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                        and ast.unparse(n.value.func) == "console.print")
    entry = ast.FunctionDef(name="entry", args=node.args,
                           body=node.body[:banner_index + 1], decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[entry], type_ignores=[]))
    events = []

    def enable(**kwargs):
        events.append(("readline", kwargs))
        return helper(**kwargs)

    def banner(*args):
        events.append(("banner", {}))

    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    imported = _readline_import_spy(monkeypatch)
    namespace = {"_enable_interactive_readline": enable, "BANNER": "test",
                 "console": SimpleNamespace(print=banner)}
    exec(compile(module, "main.py", "exec"), namespace)
    namespace["entry"](one_shot=one_shot)
    assert events == [("readline", {"one_shot": one_shot}), ("banner", {})]
    assert imported == ([] if one_shot else ["readline"])


def test_cli_daemon_returns_before_repl_hook():
    """Pin the real routing boundary without running main() or daemon startup."""
    node = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    daemon = next(n for n in node.body if isinstance(n, ast.If)
                  and ast.unparse(n.test) == "args.daemon")
    assert isinstance(daemon.body[-1], ast.Return)
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id in ("repl", HELPER.name) for n in ast.walk(daemon))
    repl_call = next(n for n in ast.walk(node) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name) and n.func.id == "repl")
    assert daemon.end_lineno < repl_call.lineno


def _pty_prompt(tmp_path, answer):
    """Fresh Python, real controlling tty; send exactly one post-prompt input."""
    script = "import os, sys\n" + HELPER_SOURCE + "\n" + """
assert _enable_interactive_readline() is True
try:
    answer = input('PROMPT> ')
except KeyboardInterrupt:
    print('CANCELLED', flush=True)
else:
    print('ANSWER=' + answer, flush=True)
"""
    pid, fd = pty.fork()
    if pid == 0:
        os.execve(sys.executable, [sys.executable, "-S", "-c", script], dict(os.environ))
    output = b""
    sent = False
    reaped = False
    status = None
    sent_at = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if select.select([fd], [], [], 0.05)[0]:
                try:
                    chunk = os.read(fd, 4096)
                except OSError as exc:
                    if exc.errno != errno.EIO:
                        raise
                    break
                if not chunk:
                    break
                output += chunk
            if not sent and b"PROMPT> " in output:
                os.write(fd, answer)
                sent_at = time.monotonic()
                sent = True
                deadline = sent_at + 3
            if b"CANCELLED" in output or b"ANSWER=" in output:
                break
        elapsed = None if sent_at is None else time.monotonic() - sent_at
        # A successful prompt must exit by itself, without another key or signal.
        until = time.monotonic() + 2
        while time.monotonic() < until:
            found, status = os.waitpid(pid, os.WNOHANG)
            if found:
                reaped = True
                break
            time.sleep(0.01)
        assert sent, output.decode(errors="replace")
        assert reaped and os.waitstatus_to_exitcode(status) == 0, output.decode(errors="replace")
        return output.decode(errors="replace"), elapsed
    finally:
        if not reaped:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # the owned child already exited
            os.waitpid(pid, 0)
        os.close(fd)


def test_real_pty_ctrl_c_cancels_without_another_key(tmp_path):
    output, elapsed = _pty_prompt(tmp_path, b"\x03")
    assert "CANCELLED" in output
    assert "ANSWER=" not in output
    assert elapsed < 3


def test_real_pty_positive_input_still_works(tmp_path):
    output, _ = _pty_prompt(tmp_path, b"hello\n")
    assert "ANSWER=hello" in output
    assert "CANCELLED" not in output


def test_piped_y_stays_unread_and_refused_after_setup(helper, monkeypatch):
    from utils import logger

    stream = io.StringIO("y\n")
    monkeypatch.setattr(sys, "stdin", stream)
    imported = _readline_import_spy(monkeypatch)
    prompt = Mock(side_effect=AssertionError("must not ask off-tty"))
    monkeypatch.setattr(logger.console, "input", prompt)
    assert helper() is False
    assert logger.confirm("Approve?") is False
    assert imported == []
    assert stream.tell() == 0
    prompt.assert_not_called()


def test_subprocess_piped_y_refusal(tmp_path):
    script = ("import os, sys\n" + HELPER_SOURCE + "\n"
              "sys.path.insert(0, " + repr(str(REPO)) + ")\n"
              "from utils.logger import confirm\n"
              "assert _enable_interactive_readline() is False\n"
              "assert confirm('Approve?') is False\n"
              "assert sys.stdin.readline() == 'y\\n'\n"
              "print('REFUSED_UNREAD')\n")
    result = subprocess.run([sys.executable, "-c", script], input="y\n",
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "REFUSED_UNREAD" in result.stdout
