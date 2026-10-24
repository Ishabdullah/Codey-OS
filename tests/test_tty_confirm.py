"""core/tty_confirm.py (WP2.1 G15i-A): the shared /dev/tty human-confirmation
primitive extracted from core/lora_import.py (NEW-977).

Two harnesses: a fake opener backed by a pty pair (fine-grained control), and
a real pty.fork child whose controlling terminal is /dev/tty (exercises the
real open_tty). Everything is stdlib; no model, no Restoricon state."""

import ast
import errno
import os
import pty
import select
import subprocess
import sys
import termios
import threading
import time
from pathlib import Path

import pytest

from core import tty_confirm as tc
import core.lora_import as _li

# conftest autouse-patches lora_import._confirm_on_tty; keep the real one.
_REAL_LORA_CONFIRM = _li._confirm_on_tty

REPO = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# fake-opener harness
# --------------------------------------------------------------------------
class FakeTty:
    """pty pair standing in for /dev/tty. ECHO is off so the master only sees
    what the primitive itself wrote. The human answers only AFTER the prompt
    appears (the primitive flushes pending input first); `stale` is typeahead
    written before any prompt."""

    def __init__(self, answer=b"", stale=b""):
        self.master, self.slave = pty.openpty()
        attrs = termios.tcgetattr(self.slave)
        attrs[3] &= ~termios.ECHO
        termios.tcsetattr(self.slave, termios.TCSANOW, attrs)
        if stale:
            os.write(self.master, stale)
        self.answer, self.seen = answer, b""
        self.opened, self.fds = 0, []
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._human, daemon=True)
        self._t.start()

    def opener(self):
        self.opened += 1
        fd = os.dup(self.slave)
        self.fds.append(fd)
        return fd

    def _human(self):
        answered = False
        while not self._stop.is_set():
            if select.select([self.master], [], [], 0.05)[0]:
                try:
                    chunk = os.read(self.master, 4096)
                except OSError:
                    return
                self.seen += chunk
                if not answered and self.answer:
                    os.write(self.master, self.answer)
                    answered = True

    def drained(self):
        time.sleep(0.3)
        return self.seen

    def close(self):
        self._stop.set()
        self._t.join(timeout=5)
        for fd in (self.master, self.slave):
            try:
                os.close(fd)
            except OSError:
                pass  # already closed by the test; helper teardown only


@pytest.fixture
def fake():
    made = []

    def _make(answer=b"", stale=b""):
        t = FakeTty(answer, stale)
        made.append(t)
        return t

    yield _make
    for t in made:
        t.close()


def _fd_closed(fd):
    try:
        os.fstat(fd)
    except OSError as e:
        return e.errno == errno.EBADF
    return False


@pytest.mark.parametrize("ans", [b"y\n", b"yes\n", b"Y\n", b"YES\n", b"  yes  \n", b"Yes\n"])
def test_accepts_y_and_yes(fake, ans):
    t = fake(ans)
    assert tc.confirm_on_tty("Proceed? ", open_tty=t.opener) is True


@pytest.mark.parametrize(
    "ans", [b"\n", b"n\n", b"no\n", b"N\n", b"maybe\n", b"yes please\n", b"yy\n", b"ye\n", b"1\n", b"true\n", b"ok\n", b" \n"]
)
def test_refuses_everything_else(fake, ans):
    t = fake(ans)
    assert tc.confirm_on_tty("Proceed? ", open_tty=t.opener) is False


def test_prompt_is_written_and_nothing_else_no_echo(fake, capfd):
    t = fake(b"y\n")
    prompt = "Mint token for 'alice'. Proceed? [y/N]: "
    assert tc.confirm_on_tty(prompt, open_tty=t.opener) is True
    assert t.drained() == prompt.encode()  # exactly the prompt, no echo of the answer
    out = capfd.readouterr()
    assert out.out == "" and out.err == ""  # nothing leaks to stdout/stderr


def test_secret_in_answer_is_not_re_emitted(fake):
    t = fake(b"hunter2-SECRET\n")
    assert tc.confirm_on_tty("? ", open_tty=t.opener) is False
    assert b"hunter2" not in t.drained()


def test_stale_yes_is_flushed_and_cannot_approve(fake):
    t = fake(b"n\n", stale=b"y\n")
    assert tc.confirm_on_tty("? ", open_tty=t.opener) is False


def test_stale_yes_with_eof_answer_does_not_approve(fake):
    t = fake(b"\x04", stale=b"y\n")  # Ctrl-D (VEOF) at line start -> read() == b""
    with pytest.raises(EOFError):
        tc.confirm_on_tty("? ", open_tty=t.opener)


def test_fresh_yes_after_prompt_approves_despite_stale(fake):
    t = fake(b"yes\n", stale=b"n\nn\n")
    assert tc.confirm_on_tty("? ", open_tty=t.opener) is True


def test_eof_raises_eoferror(fake):
    t = fake(b"\x04")
    with pytest.raises(EOFError):
        tc.confirm_on_tty("? ", open_tty=t.opener)


def test_closed_tty_never_approves():
    master, slave = pty.openpty()
    os.close(master)  # hangup: the human side is gone
    try:
        with pytest.raises((EOFError, OSError)):
            tc.confirm_on_tty("? ", open_tty=lambda: os.dup(slave))
    finally:
        os.close(slave)


@pytest.mark.parametrize("kind", ["pipe", "devnull", "file"])
def test_non_tty_fd_refused_fail_closed(kind, tmp_path):
    if kind == "pipe":
        r, w = os.pipe()
        os.write(w, b"y\n")  # a would-be "yes" must not be consumed
        opener = lambda: os.dup(r)
    elif kind == "devnull":
        opener = lambda: os.open(os.devnull, os.O_RDWR)
    else:
        f = tmp_path / "ans"
        f.write_bytes(b"y\n")
        opener = lambda: os.open(f, os.O_RDWR)
    got = []

    def op():
        fd = opener()
        got.append(fd)
        return fd

    with pytest.raises(OSError):  # tcflush -> ENOTTY, converted to OSError
        tc.confirm_on_tty("? ", open_tty=op)
    assert _fd_closed(got[0])


def test_flush_failure_fails_closed_and_prompt_not_written(fake, monkeypatch):
    t = fake(b"y\n")

    def boom(fd, queue):
        raise termios.error(25, "not a tty")

    monkeypatch.setattr(termios, "tcflush", boom)
    with pytest.raises(OSError):
        tc.confirm_on_tty("? ", open_tty=t.opener)
    assert t.drained() == b""


def test_termios_unavailable_fails_closed(fake, monkeypatch):
    t = fake(b"y\n")
    monkeypatch.setitem(sys.modules, "termios", None)  # makes `import termios` raise ImportError
    with pytest.raises(OSError):
        tc.confirm_on_tty("? ", open_tty=t.opener)
    assert t.drained() == b""
    assert _fd_closed(t.fds[0])


def test_opener_failure_propagates():
    def nope():
        raise OSError(errno.ENXIO, "no ctty")

    with pytest.raises(OSError):
        tc.confirm_on_tty("? ", open_tty=nope)


def test_fd_closed_on_every_outcome(fake):
    for ans in (b"y\n", b"n\n"):
        t = fake(ans)
        tc.confirm_on_tty("? ", open_tty=t.opener)
        assert _fd_closed(t.fds[0])
    t = fake(b"\x04")
    with pytest.raises(EOFError):
        tc.confirm_on_tty("? ", open_tty=t.opener)
    assert _fd_closed(t.fds[0])


def test_overlong_answer_is_bounded_and_refused(fake):
    t = fake(b"y" * 4000 + b"\n")
    assert tc.confirm_on_tty("? ", open_tty=t.opener) is False
    t = fake(b" " * 300 + b"y\n")  # the 256-byte cap cuts before the y; unbounded read would say yes
    # 256 bytes read without a newline: not exactly y/yes -> refused. (A canonical
    # tty line is limited by the kernel's line buffer anyway.)
    assert tc.confirm_on_tty("? ", open_tty=t.opener) is False


# ---- prompt text -----------------------------------------------------------
def test_prompt_escaped_by_caller_has_no_control_chars_on_tty(fake):
    evil = "x\x1b[2J\x1b]0;pwn\x07\r\nProceed? [y/N]: y\n"
    prompt = f"[HIGH IMPACT] path: {evil!a}\nProceed? [y/N]: "
    t = fake(b"n\n")
    assert tc.confirm_on_tty(prompt, open_tty=t.opener) is False
    seen = t.drained()
    seen = seen.replace(b"\r\n", b"\n")  # the tty maps the prompt's own LF to CRLF (ONLCR)
    assert b"\x1b" not in seen and b"\x07" not in seen and b"\r" not in seen
    assert seen.count(b"\n") == 1  # only the prompt's own newline, none injected
    assert b"\\x1b" in seen


def test_prompt_is_not_format_interpreted(fake):
    t = fake(b"n\n")
    p = "100%s {0} {x} %(a)s [bold]red[/bold] <b>x</b> "
    tc.confirm_on_tty(p, open_tty=t.opener)
    assert t.drained() == p.encode()


def test_unencodable_prompt_does_not_crash(fake):
    t = fake(b"n\n")
    assert tc.confirm_on_tty("bad \ud800 surrogate ", open_tty=t.opener) is False
    assert b"bad " in t.drained()


# --------------------------------------------------------------------------
# real /dev/tty via pty.fork
# --------------------------------------------------------------------------
def _run_child(driver, *, stale=b"", timeout=15):
    """Fork a child whose controlling terminal is a fresh pty and let it call
    the REAL tc.confirm_on_tty("PROMPT> "). `driver(master)` plays the human
    after the prompt has appeared. Returns (exit_code, bytes_seen)."""
    sync_r, sync_w = os.pipe()
    pid, master = pty.fork()
    if pid == 0:  # child
        code = 99
        try:
            os.close(sync_w)
            attrs = termios.tcgetattr(0)
            attrs[3] &= ~termios.ECHO
            termios.tcsetattr(0, termios.TCSANOW, attrs)
            os.read(sync_r, 1)  # wait until the parent queued stale input
            try:
                code = 0 if tc.confirm_on_tty("PROMPT> ") else 1
            except EOFError:
                code = 2
            except OSError:
                code = 3
        finally:
            os._exit(code)
    os.close(sync_r)
    seen = b""
    try:
        if stale:
            os.write(master, stale)
        os.write(sync_w, b"g")
        deadline = time.time() + timeout
        answered = False
        while time.time() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                seen += chunk
                if not answered and b"PROMPT> " in seen:
                    driver(master)
                    answered = True
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                return os.waitstatus_to_exitcode(status), seen
        # master hung up (child exited) or deadline passed: reap the child.
        end = time.time() + 5
        while time.time() < end:
            done, status = os.waitpid(pid, os.WNOHANG)
            if done:
                return os.waitstatus_to_exitcode(status), seen
            time.sleep(0.05)
        os.kill(pid, 9)  # our own forked child only
        os.waitpid(pid, 0)
        raise AssertionError("child timed out; seen=%r" % seen)
    finally:
        os.close(master)
        os.close(sync_w)


@pytest.mark.parametrize(
    "ans,code",
    [(b"y\n", 0), (b"yes\n", 0), (b"Yes\n", 0), (b"\n", 1), (b"n\n", 1), (b"no\n", 1), (b"sure\n", 1), (b"\x04", 2)],
)
def test_real_dev_tty_answers(ans, code):
    got, seen = _run_child(lambda m: os.write(m, ans))
    assert got == code
    assert b"PROMPT> " in seen


def test_real_dev_tty_stale_input_flushed():
    got, _ = _run_child(lambda m: os.write(m, b"n\n"), stale=b"y\n")
    assert got == 1
    got, _ = _run_child(lambda m: os.write(m, b"\x04"), stale=b"yes\n")
    assert got == 2  # EOF, NOT consumed stale "yes"


def test_no_controlling_terminal_fails_closed_enxio():
    """A detached session has no ctty: the real open_tty() must raise OSError
    (ENXIO), which is what makes every unattended path refuse."""
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "from core import tty_confirm as tc\n"
        "try:\n    tc.confirm_on_tty('x')\n"
        "except OSError as e:\n    print('OSERR', e.errno)\n"
        "else:\n    print('NO ERROR')\n" % str(REPO)
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        start_new_session=True,  # setsid: drops the controlling terminal
        timeout=30,
    )
    assert r.stdout.startswith("OSERR"), (r.stdout, r.stderr)


# --------------------------------------------------------------------------
# gate_human_action + module hygiene
# --------------------------------------------------------------------------
class _Gw:
    def __init__(self):
        self.kw = None

    def gate_exec(self, **kw):
        self.kw = kw
        return "sentinel"


def test_gate_human_action_wires_high_impact(monkeypatch):
    import core.action_gateway as ag

    gw = _Gw()
    monkeypatch.setattr(ag, "get_action_gateway", lambda: gw)
    calls = []
    monkeypatch.setattr(tc, "confirm_on_tty", lambda p, open_tty=None: calls.append((p, open_tty)) or True)
    marker = lambda: 7
    res = tc.gate_human_action("act", "cmd", "PROMPT", lambda: 1, open_tty=marker)
    assert res == "sentinel"
    assert gw.kw["authority"] == ag.HIGH_IMPACT
    assert (gw.kw["action"], gw.kw["command"], gw.kw["confirm_available"]) == ("act", "cmd", True)
    assert gw.kw["confirm"]() is True and calls == [("PROMPT", marker)]


def test_gate_human_action_explicit_confirm_wins(monkeypatch):
    import core.action_gateway as ag

    gw = _Gw()
    monkeypatch.setattr(ag, "get_action_gateway", lambda: gw)
    monkeypatch.setattr(tc, "confirm_on_tty", lambda *a, **k: pytest.fail("must not prompt"))
    tc.gate_human_action("a", "c", "P", lambda: 1, confirm=lambda: False)
    assert gw.kw["confirm"]() is False


def test_module_is_stdlib_only_at_import_time():
    tree = ast.parse((REPO / "core" / "tty_confirm.py").read_text())
    top = []
    for n in tree.body:
        if isinstance(n, ast.Import):
            top += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            top.append(n.module)
    assert top == ["os"]
    src = (REPO / "core" / "tty_confirm.py").read_text()
    for bad in ("core.filesystem", "core.protected_paths", "tools."):
        assert bad not in src


def test_lora_import_delegates_to_shared_primitive(monkeypatch):
    li = _li
    seen = {}
    monkeypatch.setattr(tc, "confirm_on_tty", lambda p, open_tty=None: seen.update(p=p, o=open_tty) or True)
    assert _REAL_LORA_CONFIRM("Q") is True
    assert seen["p"] == "Q" and seen["o"] is li._open_tty
