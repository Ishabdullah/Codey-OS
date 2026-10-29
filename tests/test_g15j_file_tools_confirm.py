"""G15j Unit B: tools.file_tools attaches a stdin human-confirmation callback
to gate_write/gate_append for HIGH_IMPACT targets in confirm_write modes.

All state is disposable (tmp_path workspace + fake CODE_DIR + fake HOME). The
real console / stdin / repo are never used: utils.logger.confirm is a recorder
and file_tools._stdin_is_tty is a seam.
"""

import json
import os
import pty
import select
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

import core.action_gateway as ag
import core.checkpoint as checkpoint_module
import core.filesystem as filesystem_module
import tools.file_tools as file_tools
import tools.patch_tools as patch_tools
from core.filesystem import Filesystem
from utils.config import AGENT_CONFIG

import utils.logger as _logger_mod

_REAL_TTY = file_tools._stdin_is_tty
_REAL_CONFIRM = _logger_mod.confirm
REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def env(tmp_path, monkeypatch):
    import utils.config as cfg
    import utils.logger as logger

    home = tmp_path / "home"
    state = home / ".codeyOS"
    code = tmp_path / "code"
    audit = tmp_path / "audit" / "ledger.jsonl"
    for d in (home, state, code, audit.parent, code / "core"):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEY_STATE_DIR", str(state))
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(audit))
    monkeypatch.delenv("CODEY_CONFIG_PATH", raising=False)
    monkeypatch.setattr(cfg, "CODEY_STATE_DIR", state)
    monkeypatch.setattr(cfg, "CODEY_DIR", code)
    monkeypatch.setattr(filesystem_module, "CODE_DIR", code)
    monkeypatch.setattr(checkpoint_module, "CODE_DIR", code)
    monkeypatch.setattr(filesystem_module, "_snapshot", Mock())
    monkeypatch.chdir(home)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_write", True)
    monkeypatch.setitem(AGENT_CONFIG, "allow_self_modification", False)
    monkeypatch.setattr(file_tools, "_stdin_is_tty", lambda: True)
    ag.reset_action_gateway()

    class E:
        pass

    e = E()
    e.home, e.state, e.code, e.audit = home, state, code, audit
    e.ask = Mock(return_value=True)
    monkeypatch.setattr(logger, "confirm", e.ask)
    e.use = lambda fs: (
        monkeypatch.setattr(file_tools, "_get_fs", lambda: fs),
        monkeypatch.setattr(filesystem_module, "_filesystem", fs),
    )
    e.fs = Filesystem(workspace=code, allow_self_modification=True)
    e.use(e.fs)
    e.rows = lambda: [json.loads(x) for x in audit.read_text().splitlines()] if audit.exists() else []
    yield e
    ag.reset_action_gateway()


def _selfmod(monkeypatch, on=True):
    monkeypatch.setitem(AGENT_CONFIG, "allow_self_modification", on)


@pytest.mark.parametrize("op", ["write", "append"])
def test_approved_declined_and_audit(env, monkeypatch, op):
    fn = file_tools.tool_write_file if op == "write" else file_tools.tool_append_file
    target = env.code / "core" / "zz_new.py"
    # approved
    res = fn(str(target), "x = 1\n")
    assert not res.startswith("[")
    assert target.read_text() == "x = 1\n"
    assert env.ask.call_count == 1
    assert env.rows()[-1]["outcome"] == "allowed"
    # declined
    target.unlink()
    env.ask.reset_mock()
    env.ask.return_value = False
    res = fn(str(target), "x = 1\n")
    assert res.startswith("[BLOCKED] Human confirmation declined")
    assert not target.exists()
    assert env.ask.call_count == 1
    assert env.rows()[-1]["outcome"] == "refused"


@pytest.mark.parametrize("op", ["write", "append"])
@pytest.mark.parametrize("exc", [EOFError(), KeyboardInterrupt(), RuntimeError("secret")])
def test_prompt_exceptions_refuse(env, op, exc):
    fn = file_tools.tool_write_file if op == "write" else file_tools.tool_append_file
    env.ask.side_effect = exc
    target = env.code / "core" / "zz_new.py"
    assert fn(str(target), "x").startswith("[BLOCKED]")
    assert not target.exists()
    assert "secret" not in env.audit.read_text()


@pytest.mark.parametrize("op", ["write", "append"])
def test_non_tty_fails_closed_without_reading(env, monkeypatch, op):
    fn = file_tools.tool_write_file if op == "write" else file_tools.tool_append_file
    monkeypatch.setattr(file_tools, "_stdin_is_tty", lambda: False)
    target = env.code / "core" / "zz_new.py"
    res = fn(str(target), "x")
    assert res.startswith("[BLOCKED] Human confirmation declined")
    env.ask.assert_not_called()  # a piped "y" never gets a chance to approve
    assert not target.exists()


def test_isatty_raising_fails_closed(env, monkeypatch):
    class Boom:
        def isatty(self):
            raise ValueError("closed")

    monkeypatch.setattr(sys, "stdin", Boom())
    assert _REAL_TTY() is False
    monkeypatch.setattr(sys, "stdin", None)
    assert _REAL_TTY() is False


def test_callback_real_logger_default_no_and_only_yes(env, monkeypatch):
    """Drive the real utils.logger.confirm with scripted console input."""
    import utils.logger as logger

    answers = iter(["", "no", "YES"])
    monkeypatch.setattr(logger.console, "input", Mock(side_effect=lambda q: next(answers)))
    monkeypatch.setattr(logger, "confirm", _REAL_CONFIRM)
    # NEW-1074 declared flip: the real confirm now fails closed off-tty, so
    # scripted console input needs the logger tty seam (not a prod backdoor).
    monkeypatch.setattr(logger, "_stdin_is_tty", lambda: True)
    cb = file_tools._high_write_confirm("Write to", "p", "c")
    assert cb() is False  # empty -> default No
    assert cb() is False  # "no"
    assert cb() is True  # "YES"
    monkeypatch.setattr(logger.console, "input", Mock(side_effect=EOFError))
    assert cb() is False


@pytest.mark.parametrize("op", ["write", "append"])
def test_deny_and_out_of_workspace_refused_without_prompt(env, monkeypatch, op):
    fn = file_tools.tool_write_file if op == "write" else file_tools.tool_append_file
    fs = Filesystem(workspace=env.home, allow_self_modification=True)
    env.use(fs)
    _selfmod(monkeypatch)
    # DENY tier
    r = fn(str(env.home / ".bashrc"), "x")
    assert r.startswith("[ERROR] Access denied"), r
    r = fn(str(env.home / ".ssh" / "authorized_keys"), "x")
    assert r.startswith("[ERROR] Access denied"), r
    assert not (env.home / ".ssh").exists()
    # out of workspace / CODE_DIR
    outside = env.home.parent / "elsewhere" / "core" / "x.py"
    r = fn(str(outside), "x")
    assert r.startswith("[ERROR]"), r
    assert not outside.exists()
    env.ask.assert_not_called()
    assert [x["outcome"] for x in env.rows()] == ["failed"] * 3


@pytest.mark.parametrize("op", ["write", "append"])
def test_act_target_never_prompts(env, monkeypatch, op):
    fn = file_tools.tool_write_file if op == "write" else file_tools.tool_append_file
    fs = Filesystem(workspace=env.home)
    env.use(fs)
    r = fn(str(env.home / "notes.txt"), "hello")
    assert not r.startswith("[")
    env.ask.assert_not_called()


def test_overwrite_prompts_once_not_twice(env):
    target = env.code / "core" / "zz_old.py"
    target.write_text("a = 1\n" * 40)
    r = file_tools.tool_write_file(str(target), "a = 2\n" * 40)
    assert not r.startswith("[")
    assert env.ask.call_count == 1
    assert env.ask.call_args[0][0].startswith("Overwrite")
    # declined legacy prompt never reaches the gateway
    env.ask.reset_mock()
    env.ask.return_value = False
    rows_before = len(env.rows())
    assert file_tools.tool_write_file(str(target), "a = 3\n" * 40).startswith("[CANCELLED]")
    assert env.ask.call_count == 1
    assert len(env.rows()) == rows_before


def test_write_protected_overwrite_not_double_prompted(env, monkeypatch):
    # WRITE_PROTECTED name that is also HIGH (inside CODE_DIR core/): CLAUDE.md
    # is ACT, so use a HIGH-and-protected-name target: requirements.txt under
    # a core-file root is not classified HIGH; prove the flag via a spy instead.
    seen = {}

    class Spy:
        def gate_write(self, **kw):
            seen.update(kw)
            return ag.GatewayDecision(authority=kw["authority"], outcome=ag.OUTCOME_ALLOWED, reason="", detail={})

    monkeypatch.setattr(file_tools, "get_action_gateway", lambda: Spy())
    monkeypatch.setattr(file_tools, "classify_write_action", lambda *a, **k: ag.HIGH_IMPACT)
    (env.code / "README.md").write_text("old")
    file_tools.tool_write_file(str(env.code / "README.md"), "new")
    assert env.ask.call_count == 1
    assert "confirm" not in seen  # consent already obtained -> no callback


def test_nonexistent_precheck_mismatch_gets_one_prompt(env, monkeypatch):
    # cwd != workspace: file_exists (computed against cwd) is False even though
    # the target exists in the workspace -> exactly one HIGH prompt.
    target = env.code / "core" / "zz_exist.py"
    target.write_text("old\n")
    monkeypatch.chdir(env.home)
    file_tools.tool_write_file("core/zz_exist.py", "new\n")
    assert env.ask.call_count == 1
    assert "core" in env.ask.call_args[0][0]


def test_allow_self_mod_still_prompts(env, monkeypatch):
    _selfmod(monkeypatch, True)
    r = file_tools.tool_write_file(str(env.code / "core" / "a.py"), "x")
    assert not r.startswith("[")
    assert env.ask.call_count == 1
    env.ask.return_value = False
    assert file_tools.tool_append_file(str(env.code / "core" / "a.py"), "y").startswith("[BLOCKED]")


@pytest.mark.parametrize("selfmod,expect_written", [(False, False), (True, True)])
@pytest.mark.parametrize("op", ["write", "append"])
def test_confirm_less_modes_unchanged(env, monkeypatch, op, selfmod, expect_written):
    fn = file_tools.tool_write_file if op == "write" else file_tools.tool_append_file
    monkeypatch.setitem(AGENT_CONFIG, "confirm_write", False)
    _selfmod(monkeypatch, selfmod)
    seen = {}
    real = ag.get_action_gateway()
    orig = real.gate_write if op == "write" else real.gate_append

    def spy(**kw):
        seen.update(kw)
        return orig(**kw)

    monkeypatch.setattr(real, "gate_write" if op == "write" else "gate_append", spy)
    target = env.code / "core" / "zz_new.py"
    r = fn(str(target), "x")
    assert "confirm" not in seen
    env.ask.assert_not_called()
    assert target.exists() is expect_written
    if not expect_written:
        assert r.startswith("[BLOCKED]") and "confirm" in r.lower()


def test_gateway_kwarg_only_when_warranted(env, monkeypatch):
    seen = []
    real = ag.get_action_gateway()
    orig = real.gate_write

    def spy(**kw):
        seen.append(set(kw))
        return orig(**kw)

    monkeypatch.setattr(real, "gate_write", spy)
    file_tools.tool_write_file(str(env.code / "core" / "n.py"), "x")  # HIGH
    env.use(Filesystem(workspace=env.home))
    file_tools.tool_write_file(str(env.home / "act.txt"), "x")  # ACT
    assert "confirm" in seen[0] and "confirm" not in seen[1]


def test_patch_tool_unchanged_one_prompt_no_confirm_kwarg(env, monkeypatch):
    _selfmod(monkeypatch)
    target = env.code / "core" / "p.py"
    target.write_text("def f():\n    return 1\n")
    seen = {}
    real = ag.get_action_gateway()
    orig = real.gate_write

    def spy(**kw):
        seen.update(kw)
        return orig(**kw)

    monkeypatch.setattr(real, "gate_write", spy)
    monkeypatch.setattr(patch_tools, "get_filesystem", lambda **kw: env.fs, raising=False)
    monkeypatch.setattr(patch_tools, "ask_confirm", env.ask)
    r = patch_tools.tool_patch_file(str(target), "return 1", "return 2")
    assert env.ask.call_count == 1 and env.ask.call_args[0][0] == "Apply patch?", r
    assert "confirm" not in seen, r


def test_prompt_text_escaped_and_capped(env):
    nasty = "co[red]re/[/x]\n\x1b[31mevil\x07" + "A" * 600 + ".py"
    cb = file_tools._high_write_confirm("Write to", nasty, "body")
    cb()
    q = env.ask.call_args[0][0]
    assert "\x1b" not in q and "\x07" not in q
    assert "\n" not in q
    assert "\\x1b" in q and "\\n" in q
    assert "\\[red]" in q  # rich markup escaped
    assert len(q) < 600
    assert "HIGH_IMPACT" in q and "4 bytes" in q
    from rich.text import Text
    from rich.markup import render

    render(q)  # must not raise MarkupError


# --------------------------------------------------------------------------
# real pty.fork live check (disposable workspace + HOME; child is our own)
# --------------------------------------------------------------------------
CHILD = r"""
import os, sys
sys.path.insert(0, {repo!r})
os.chdir({ws!r})
from utils.config import AGENT_CONFIG
AGENT_CONFIG["confirm_write"] = True
AGENT_CONFIG["allow_self_modification"] = True
import core.filesystem as fsm
import core.checkpoint as ck
from pathlib import Path
fsm.CODE_DIR = Path({ws!r}); ck.CODE_DIR = Path({ws!r})
fsm._require_checkpoint = lambda *a, **k: None
import tools.file_tools as ft
fsm._snapshot = lambda *a, **k: None
print("RESULT:" + ft.tool_write_file({target!r}, "x = 1\n"), flush=True)
"""


def _pty_run(tmp_path, answer, *, tty=True, timeout=30):
    ws = tmp_path / "ws"
    (ws / "core").mkdir(parents=True)
    home = tmp_path / "h"
    home.mkdir()
    target = str(ws / "core" / "zz_live.py")
    script = tmp_path / "child.py"
    script.write_text(CHILD.format(repo=str(REPO), ws=str(ws), target=target))
    env = {
        k: v for k, v in os.environ.items() if k.lower() not in ("http_proxy", "https_proxy")
    }
    env.update(
        HOME=str(home),
        CODEY_STATE_DIR=str(home / ".codeyOS"),
        CODEY_ACTION_GATEWAY_AUDIT=str(tmp_path / "audit.jsonl"),
        CODEY_CONFIG_PATH=str(tmp_path / "nocfg.json"),
    )
    argv = [sys.executable, str(script)]
    seen = b""
    if not tty:
        out = subprocess.run(
            argv, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout, cwd=str(ws)
        )
        return out.stdout.decode(errors="replace"), Path(target)
    pid, master = pty.fork()
    if pid == 0:
        try:
            os.execve(argv[0], argv, env)
        finally:
            os._exit(127)
    try:
        deadline = time.time() + timeout
        answered = False
        while time.time() < deadline:
            if select.select([master], [], [], 0.2)[0]:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                seen += chunk
                if not answered and b"HIGH_IMPACT)" in seen:
                    os.write(master, answer)
                    answered = True
            done, _ = os.waitpid(pid, os.WNOHANG)
            if done:
                pid = None
                break
        # drain
        try:
            while select.select([master], [], [], 0.2)[0]:
                chunk = os.read(master, 4096)
                if not chunk:
                    break
                seen += chunk
        except OSError:
            pass
    finally:
        if pid:
            os.kill(pid, 9)  # our own forked child only
            os.waitpid(pid, 0)
        os.close(master)
    return seen.decode(errors="replace"), Path(target)


@pytest.mark.parametrize("answer,written", [(b"y\n", True), (b"\n", False), (b"n\n", False)])
def test_live_pty_prompt(tmp_path, answer, written):
    out, target = _pty_run(tmp_path, answer)
    assert "HIGH_IMPACT)" in out, out
    assert "HIGH_IMPACT" in out, out
    assert target.exists() is written, out
    if written:
        assert "RESULT:Written" in out or "RESULT:" in out
    else:
        assert "RESULT:[BLOCKED] Human confirmation declined" in out, out


def test_live_no_tty_refuses(tmp_path):
    out, target = _pty_run(tmp_path, b"", tty=False)
    assert "RESULT:[BLOCKED] Human confirmation declined" in out, out
    assert "HIGH_IMPACT" not in out
    assert not target.exists()


def test_long_path_tail_visible(env):
    for tail in ("/.bashrc", "/authorized_keys"):
        nasty = "/ws/" + "benign/" * 90 + tail.lstrip("/")
        assert len(nasty) > 600
        file_tools._high_write_confirm("Write to", nasty, "b")()
        q = env.ask.call_args[0][0]
        assert tail.lstrip("/") in q and q.count("...") == 1


def test_logger_confirm_prompt_shows_yn_hint(monkeypatch):
    import io

    import utils.logger as logger
    from rich.console import Console

    buf = io.StringIO()
    c = Console(file=buf, force_terminal=False, highlight=False, width=200)
    seen = {}

    def fake_input(prompt=""):
        # same console.input rendering path, input source faked
        c.print(prompt, end="")
        return "n"

    monkeypatch.setattr(logger, "console", c)
    monkeypatch.setattr(c, "input", fake_input)
    # NEW-1074 declared flip: logger.confirm needs a tty to prompt at all.
    monkeypatch.setattr(logger, "_stdin_is_tty", lambda: True)
    assert _REAL_CONFIRM("Write to x?") is False
    assert "[y/N]" in buf.getvalue()
    # path markup from the file-tool prompt stays literal, not interpreted
    buf.truncate(0)
    cb = file_tools._high_write_confirm("Write to", "a[red]b", "c")
    monkeypatch.setattr(file_tools, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(logger, "confirm", _REAL_CONFIRM)
    cb()
    assert "a[red]b" in buf.getvalue() and "[y/N]" in buf.getvalue()
