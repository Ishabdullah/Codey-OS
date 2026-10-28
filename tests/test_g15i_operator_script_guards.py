"""
WP2.1 G15i Unit B: human-presence guards on the two operator entry points,
tools/provision_ai_agent_auth.py::provision (mints/rotates an ai_agent bearer
token) and core/setup_dr_key.py::main (writes the escrow key config and prints
the private half).

Everything here is hermetic: DBs and config live in tmp_path, /dev/tty is never
opened (a pty slave or an OSError-raising opener is injected through each
module's own `_open_tty` seam), `age-keygen` is a recording fake, and the
conftest autouse fixtures point the gateway audit file at a tmp path.

Documented limit (G15i spec 1.2/1.6, accepted residual D-1): this is a guard
on the named entry points, not a boundary. A same-uid wrapper script that
imports the module and patches `_confirm_on_tty` (exactly what the conftest
stand-in does) gets through. What the design does guarantee is that there is
NO importable unguarded twin to call by accident: the mutating body of
`provision()` and of `setup_dr_key.main()` are closures, asserted below.
"""

import ast
import errno
import json
import os
import pty
import select
import signal
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core import setup_dr_key as dr
from core import tty_confirm
from restoricon_core.auth import ROLE_ADMIN, ROLE_AI_AGENT, AuthService
from restoricon_core.database import DatabaseManager
from tools import provision_ai_agent_auth as pa

REPO = Path(__file__).resolve().parent.parent

CANNED_PUB = "age1testpub00000000000000000000000000000000000000000000000000"
OLD_PUB = "age1oldpub000000000000000000000000000000000000000000000000000"
CANNED_PRIV = "AGE-SECRET-KEY-1TESTTESTTESTTESTTESTTESTTESTTESTTESTTESTTESTTEST99"
CANNED_STDOUT = f"# created: 2026-01-01T00:00:00Z\n# public key: {CANNED_PUB}\n{CANNED_PRIV}\n"


class _Pty:
    """A pty standing in for /dev/tty; `master` is the human's side.

    The human answers only AFTER the prompt text appears (the primitive flushes
    pending input before prompting). `stale` is typeahead written first. Echo
    is disabled so the first bytes seen are the prompt itself."""

    def __init__(self, monkeypatch, module, answer: bytes, stale: bytes = b""):
        import termios

        self.master, self.slave = pty.openpty()
        self.opened = 0
        attrs = termios.tcgetattr(self.slave)
        attrs[3] &= ~termios.ECHO
        termios.tcsetattr(self.slave, termios.TCSANOW, attrs)
        if stale:
            os.write(self.master, stale)
        self._answer = answer
        self._seen = b""
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._human, daemon=True)
        self._thread.start()

        def _open():
            self.opened += 1
            return os.dup(self.slave)

        # Put the module's REAL confirm seam back (conftest approves by
        # default) and route its opener to this pty.
        monkeypatch.setattr(module, "_confirm_on_tty", getattr(module._confirm_on_tty, "real", module._confirm_on_tty))
        monkeypatch.setattr(module, "_open_tty", _open)

    def _human(self):
        answered = False
        while not self._stop.is_set():
            if select.select([self.master], [], [], 0.05)[0]:
                try:
                    chunk = os.read(self.master, 4096)
                except OSError:
                    return  # master closed by close(); helper thread ends
                self._seen += chunk
                if not answered and self._answer:
                    os.write(self.master, self._answer)
                    answered = True

    def prompt_seen(self) -> str:
        time.sleep(0.3)  # let the helper thread drain the prompt
        return self._seen.decode(errors="replace")

    def close(self):
        self._stop.set()
        self._thread.join(timeout=5)
        for fd in (self.master, self.slave):
            try:
                os.close(fd)
            except OSError:
                pass  # already closed by an earlier close(); test helper only


@pytest.fixture(autouse=True)
def _alarm():
    # A bug must never hang the suite on a terminal read.
    signal.signal(signal.SIGALRM, lambda *a: (_ for _ in ()).throw(TimeoutError("tty read hung")))
    signal.alarm(60)
    yield
    signal.alarm(0)


@pytest.fixture
def tty(monkeypatch):
    made = []

    def _make(module, answer: bytes, stale: bytes = b""):
        t = _Pty(monkeypatch, module, answer, stale)
        made.append(t)
        return t

    yield _make
    for t in made:
        t.close()


@pytest.fixture
def no_tty(monkeypatch):
    """Real confirm seam, opener fails like the agent harness (ENXIO)."""
    calls = []

    def _install(module):
        def _open():
            calls.append(module.__name__)
            raise OSError(errno.ENXIO, "No such device or address")

        monkeypatch.setattr(module, "_confirm_on_tty", module._confirm_on_tty.real)
        monkeypatch.setattr(module, "_open_tty", _open)
        return calls

    return _install


def _audit_rows():
    path = Path(os.environ["CODEY_ACTION_GATEWAY_AUDIT"])
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _db_counts(db_path):
    db = DatabaseManager(db_path)
    try:
        conn = db.get_connection()
        users = conn.execute("SELECT COUNT(*) FROM users;").fetchone()[0]
        toks = conn.execute("SELECT COUNT(*) FROM api_tokens;").fetchone()[0]
    finally:
        db.close()
    return users, toks


def _authenticates(db_path, token):
    db = DatabaseManager(db_path)
    try:
        return AuthService(db).authenticate_token(token) is not None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# provision
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("answer", [b"y\n", b"yes\n", b"Y\n"])
def test_provision_approved_mints_and_audits_without_secrets(tty, tmp_path, answer):
    t = tty(pa, answer)
    db_path = str(tmp_path / "core.db")
    token = pa.provision(username="Secret-Agent-Name", db_path=db_path)

    assert isinstance(token, str) and len(token) > 20
    assert t.opened == 1
    assert _authenticates(db_path, token)
    rows = _audit_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["authority"] == "HIGH_IMPACT"
    assert row["action"] == "provision_ai_agent_auth.provision"
    assert row["command"] == "provision ai_agent bearer token"
    assert row["outcome"] == "allowed"
    blob = Path(os.environ["CODEY_ACTION_GATEWAY_AUDIT"]).read_bytes()
    assert token.encode() not in blob
    assert b"Secret-Agent-Name" not in blob and b"secret-agent-name" not in blob
    assert str(tmp_path).encode() not in blob


@pytest.mark.parametrize("answer", [b"n\n", b"\n", b"yep\n", b"no\n", b"\x04"])
def test_provision_declined_changes_nothing(tty, tmp_path, answer):
    tty(pa, answer)
    db_path = tmp_path / "core.db"
    with pytest.raises(pa.ProvisionNotConfirmed) as ei:
        pa.provision(db_path=str(db_path))
    assert "no token was minted" in str(ei.value)
    # The DB file was never even created: no side effect preceded the answer.
    assert not db_path.exists()
    rows = _audit_rows()
    assert len(rows) == 1
    assert rows[0]["outcome"] == "refused"
    assert rows[0]["action"] == "provision_ai_agent_auth.provision"


def test_provision_declined_on_memory_never_constructs_the_db(tty, monkeypatch):
    tty(pa, b"n\n")

    def _boom(*a, **k):
        raise AssertionError("DatabaseManager constructed before consent")

    monkeypatch.setattr(pa, "DatabaseManager", _boom)
    with pytest.raises(pa.ProvisionNotConfirmed):
        pa.provision(db_path=":memory:")


def test_provision_no_tty_enxio_fails_closed_no_db_no_token(no_tty, tmp_path):
    calls = no_tty(pa)
    db_path = tmp_path / "core.db"
    with pytest.raises(pa.ProvisionNotConfirmed) as ei:
        pa.provision(db_path=str(db_path))
    assert calls == [pa.__name__]
    assert "Refused" in str(ei.value)
    assert not db_path.exists()
    assert [r["outcome"] for r in _audit_rows()] == ["refused"]


def test_provision_declined_rerun_does_not_revoke_the_deployed_token(tty, monkeypatch, tmp_path):
    db_path = str(tmp_path / "core.db")
    deployed = pa.provision(db_path=db_path)  # conftest stand-in approves
    assert _authenticates(db_path, deployed)

    tty(pa, b"n\n")
    with pytest.raises(pa.ProvisionNotConfirmed):
        pa.provision(db_path=db_path)
    assert _authenticates(db_path, deployed)  # revoke did NOT happen pre-consent
    users, toks = _db_counts(db_path)
    assert (users, toks) == (1, 1)


def test_provision_approved_rerun_revokes_old_and_issues_new(tty, tmp_path):
    db_path = str(tmp_path / "core.db")
    old = pa.provision(db_path=db_path)
    tty(pa, b"y\n")
    new = pa.provision(db_path=db_path)
    assert new != old
    assert not _authenticates(db_path, old)
    assert _authenticates(db_path, new)


def test_provision_stale_typeahead_does_not_approve(tty, tmp_path):
    tty(pa, b"n\n", stale=b"y\n")
    db_path = tmp_path / "core.db"
    with pytest.raises(pa.ProvisionNotConfirmed):
        pa.provision(db_path=str(db_path))
    assert not db_path.exists()


def test_provision_wrong_role_user_raises_value_error_and_audits_static_failure(tty, tmp_path):
    db_path = str(tmp_path / "core.db")
    db = DatabaseManager(db_path)
    try:
        AuthService(db).create_user(
            username="role-clash-user", plain_password="x" * 20, full_name="Admin Person",
            email="a@local.invalid", role=ROLE_ADMIN,
        )
    finally:
        db.close()
    tty(pa, b"y\n")
    with pytest.raises(ValueError, match="role-clash-user"):
        pa.provision(username="role-clash-user", db_path=db_path)
    rows = _audit_rows()
    assert [r["outcome"] for r in rows] == ["failed"]
    assert rows[0]["reason"] == "provision failed"
    assert b"role-clash-user" not in Path(os.environ["CODEY_ACTION_GATEWAY_AUDIT"]).read_bytes()


def test_provision_gateway_failed_without_captured_exception_is_clean(monkeypatch, tmp_path):
    from core.action_gateway import OUTCOME_FAILED, GatewayDecision

    class _FakeGateway:
        def gate_exec(self, **kw):
            return GatewayDecision(authority="HIGH_IMPACT", outcome=OUTCOME_FAILED, reason="audit boom")

    monkeypatch.setattr("core.action_gateway.get_action_gateway", lambda: _FakeGateway())
    db_path = tmp_path / "core.db"
    with pytest.raises(RuntimeError, match="^provision failed$"):
        pa.provision(db_path=str(db_path))
    assert not db_path.exists()  # thunk never ran
    assert _audit_rows() == []


def test_refusal_message_and_prog_name_the_module_invocation(no_tty, monkeypatch, tmp_path, capsys):
    no_tty(pa)
    monkeypatch.setattr(sys, "argv", ["prov", "--db-path", str(tmp_path / "c.db")])
    assert pa.main() == 2
    assert "python3 -m tools.provision_ai_agent_auth" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        monkeypatch.setattr(sys, "argv", ["prov", "--help"])
        pa.main()
    assert "python3 -m tools.provision_ai_agent_auth" in capsys.readouterr().out


def test_provision_bad_custom_permissions_raise_before_any_prompt(no_tty, tmp_path):
    calls = no_tty(pa)
    with pytest.raises(ValueError):
        pa.provision(db_path=str(tmp_path / "core.db"), custom_permissions={"no:such_permission": False})
    assert calls == []  # the opener was never called
    assert _audit_rows() == []


def test_provision_prompt_shows_db_consequence_stdout_and_escapes_user_text(tty, tmp_path):
    t = tty(pa, b"n\n")
    nasty = "evil\x1b[31m\nname"
    db_path = str(tmp_path / "core.db")
    with pytest.raises(pa.ProvisionNotConfirmed):
        pa.provision(username=nasty, db_path=db_path)
    seen = t.prompt_seen()
    assert db_path in seen
    assert "REVOKED" in seen
    assert "printed on stdout" in seen
    assert "NOT a terminal" in seen or "a terminal" in seen
    assert "\x1b" not in seen  # raw escape never reaches the terminal
    assert "\\x1b[31m\\nname" in seen  # shown ascii-escaped (!a)
    assert "Proceed? [y/N]:" in seen


def test_provision_prompt_uses_env_db_path_without_opening_it(tty, monkeypatch):
    t = tty(pa, b"n\n")

    def _boom(*a, **k):
        raise AssertionError("DatabaseManager constructed before consent")

    monkeypatch.setattr(pa, "DatabaseManager", _boom)
    with pytest.raises(pa.ProvisionNotConfirmed):
        pa.provision()
    assert ascii(os.environ["RESTORICON_DB_PATH"]) in t.prompt_seen()


def test_main_declined_returns_2_with_empty_stdout(tty, monkeypatch, tmp_path, capsys):
    tty(pa, b"n\n")
    monkeypatch.setattr(sys, "argv", ["prov", "--db-path", str(tmp_path / "core.db")])
    assert pa.main() == 2
    out = capsys.readouterr()
    assert out.out == ""
    assert "Refused" in out.err


def test_main_no_tty_returns_2(no_tty, monkeypatch, tmp_path, capsys):
    no_tty(pa)
    db_path = tmp_path / "core.db"
    monkeypatch.setattr(sys, "argv", ["prov", "--db-path", str(db_path)])
    assert pa.main() == 2
    assert capsys.readouterr().out == ""
    assert not db_path.exists()


def test_main_approved_prints_exactly_the_token(tty, monkeypatch, tmp_path, capsys):
    tty(pa, b"y\n")
    db_path = str(tmp_path / "core.db")
    monkeypatch.setattr(sys, "argv", ["prov", "--db-path", db_path])
    assert pa.main() == 0
    out = capsys.readouterr().out
    assert out.endswith("\n") and out.count("\n") == 1
    assert _authenticates(db_path, out.strip())


def test_provision_audit_labels_are_static_literals():
    tree = ast.parse((REPO / "tools" / "provision_ai_agent_auth.py").read_text())
    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "gate_human_action"
    ]
    assert len(calls) == 1
    a0, a1 = calls[0].args[0], calls[0].args[1]
    assert isinstance(a0, ast.Constant) and a0.value == "provision_ai_agent_auth.provision"
    assert isinstance(a1, ast.Constant) and a1.value == "provision ai_agent bearer token"


def test_no_importable_unguarded_twin_of_provision_or_dr_keygen():
    # The mutating bodies are closures. No module-level function may create a
    # token (provision) or write the key config (setup_dr_key). A wrapper
    # script that PATCHES the module's seam is the documented limit.
    for name, obj in vars(pa).items():
        code = getattr(obj, "__code__", None)
        if code is not None and obj.__module__ == pa.__name__:
            assert "create_token" not in code.co_names, name
            assert "create_user" not in code.co_names, name
    for name, obj in vars(dr).items():
        code = getattr(obj, "__code__", None)
        if code is not None and obj.__module__ == dr.__name__ and name != "main":
            assert "dump" not in code.co_names, name
    assert not hasattr(pa, "_provision_impl")


def test_wrapper_that_patches_the_seam_is_the_documented_limit(monkeypatch, tmp_path):
    """Limit, recorded on purpose: a same-uid wrapper that patches
    `_confirm_on_tty` is not stopped (D-1/R1). Only the casual caller is."""
    monkeypatch.setattr(pa, "_confirm_on_tty", lambda prompt: True)
    assert pa.provision(db_path=str(tmp_path / "core.db"))


def test_real_audit_ledger_untouched_by_a_provision_call(tmp_path):
    from utils.config import CODEY_STATE_DIR

    real = Path(CODEY_STATE_DIR) / "action_gateway_audit.jsonl"
    before = (real.stat().st_size, real.stat().st_mtime_ns) if real.exists() else None
    pa.provision(db_path=":memory:")
    after = (real.stat().st_size, real.stat().st_mtime_ns) if real.exists() else None
    assert before == after
    assert len(_audit_rows()) == 1  # it went to the isolated per-test file


def test_conftest_isolates_the_gateway_audit_path_by_default():
    from core.action_gateway import audit_path

    p = str(audit_path())
    assert "gateway_audit_isolated" in p


# ---------------------------------------------------------------------------
# setup_dr_key
# ---------------------------------------------------------------------------


@pytest.fixture
def cfg_file(tmp_path, monkeypatch):
    path = tmp_path.resolve() / "config.json"
    path.write_text(json.dumps({"restoricon": {"db_path": "/keep/me.db"}, "toplevel": 7}), encoding="utf-8")
    monkeypatch.setenv("CODEY_CONFIG_PATH", str(path))
    return path


@pytest.fixture
def keygen(monkeypatch):
    m = MagicMock()
    m.return_value.stdout = CANNED_STDOUT
    monkeypatch.setattr(dr.subprocess, "run", m)
    return m


def _run_dr(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["setup_dr_key", *args])
    return dr.main()


def test_dr_approved_first_generation_unchanged_behaviour(tty, cfg_file, keygen, monkeypatch, capsys, tmp_path):
    tty(dr, b"y\n")
    assert _run_dr(monkeypatch) == 0
    data = json.loads(cfg_file.read_text())
    assert data["restoricon"]["dr_recipient_pubkey"] == CANNED_PUB
    assert data["restoricon"]["db_path"] == "/keep/me.db" and data["toplevel"] == 7
    assert CANNED_PRIV in capsys.readouterr().out
    keygen.assert_called_once()
    for p in tmp_path.resolve().rglob("*"):
        if p.is_file():
            assert CANNED_PRIV.encode() not in p.read_bytes(), p
    assert _audit_rows() == []  # option A: no audit row for the DR key


@pytest.mark.parametrize("answer", [b"n\n", b"\n", b"yep\n", b"\x04"])
@pytest.mark.parametrize("force_args", [(), ("--force",)])
def test_dr_declined_leaves_config_untouched_and_keygen_unrun(
    tty, cfg_file, keygen, monkeypatch, capsys, answer, force_args
):
    if force_args:
        cfg = json.loads(cfg_file.read_text())
        cfg["restoricon"]["dr_recipient_pubkey"] = OLD_PUB
        cfg_file.write_text(json.dumps(cfg))
    before = cfg_file.read_bytes()
    tty(dr, answer)
    assert _run_dr(monkeypatch, *force_args) == 1
    assert cfg_file.read_bytes() == before
    keygen.assert_not_called()
    out = capsys.readouterr()
    assert CANNED_PRIV not in out.out and CANNED_PRIV not in out.err
    assert "Refused" in out.err


def test_dr_no_tty_fails_closed(no_tty, cfg_file, keygen, monkeypatch, capsys):
    calls = no_tty(dr)
    before = cfg_file.read_bytes()
    assert _run_dr(monkeypatch) == 1
    assert calls == [dr.__name__]
    assert cfg_file.read_bytes() == before
    keygen.assert_not_called()
    assert "Run it directly in a terminal" in capsys.readouterr().err


def test_dr_stdout_not_a_terminal_refused_even_if_human_would_approve(
    cfg_file, keygen, monkeypatch, capsys
):
    opened = []
    monkeypatch.setattr(dr, "_stdout_is_terminal", lambda: False)
    monkeypatch.setattr(dr, "_open_tty", lambda: opened.append(1))
    monkeypatch.setattr(dr, "_confirm_on_tty", lambda prompt: opened.append(prompt) or True)
    before = cfg_file.read_bytes()
    assert _run_dr(monkeypatch) == 1
    assert opened == []  # never even asked
    assert cfg_file.read_bytes() == before
    keygen.assert_not_called()
    out = capsys.readouterr()
    assert out.out == "" and "stdout is not a terminal" in out.err


def test_dr_real_stdout_check_under_capture_is_not_a_terminal(monkeypatch, capsys):
    # The un-stubbed seam: under pytest capture stdout is not a tty.
    monkeypatch.undo()  # drop conftest stand-ins for this one check
    assert dr._stdout_is_terminal() is False


def test_dr_already_configured_no_force_never_prompts(no_tty, cfg_file, keygen, monkeypatch, capsys):
    cfg = json.loads(cfg_file.read_text())
    cfg["restoricon"]["dr_recipient_pubkey"] = OLD_PUB
    cfg_file.write_text(json.dumps(cfg))
    calls = no_tty(dr)
    monkeypatch.setattr(dr, "_stdout_is_terminal", lambda: False)  # not even consulted
    assert _run_dr(monkeypatch) == 1
    assert calls == []
    keygen.assert_not_called()
    assert "already configured" in capsys.readouterr().out


def test_dr_force_declined_keeps_old_key_approved_replaces_it_and_prompt_names_old(
    tty, cfg_file, keygen, monkeypatch
):
    cfg = json.loads(cfg_file.read_text())
    cfg["restoricon"]["dr_recipient_pubkey"] = OLD_PUB
    cfg_file.write_text(json.dumps(cfg))

    t = tty(dr, b"n\n")
    assert _run_dr(monkeypatch, "--force") == 1
    assert json.loads(cfg_file.read_text())["restoricon"]["dr_recipient_pubkey"] == OLD_PUB
    seen = t.prompt_seen()
    assert OLD_PUB in seen and "REPLACES" in seen and "PRIVATE key" in seen
    assert ascii(str(cfg_file)) in seen

    t2 = tty(dr, b"y\n")
    assert _run_dr(monkeypatch, "--force") == 0
    assert json.loads(cfg_file.read_text())["restoricon"]["dr_recipient_pubkey"] == CANNED_PUB
    assert t2.opened == 1


def test_dr_stale_typeahead_does_not_approve(tty, cfg_file, keygen, monkeypatch):
    tty(dr, b"n\n", stale=b"y\n")
    before = cfg_file.read_bytes()
    assert _run_dr(monkeypatch) == 1
    assert cfg_file.read_bytes() == before
    keygen.assert_not_called()


def test_dr_prompt_escapes_the_config_path(tty, tmp_path, keygen, monkeypatch):
    nasty = tmp_path.resolve() / "cfg\x1b[31m\nx.json"
    nasty.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CODEY_CONFIG_PATH", str(nasty))
    t = tty(dr, b"n\n")
    assert _run_dr(monkeypatch) == 1
    seen = t.prompt_seen()
    assert "\x1b" not in seen and "\\x1b[31m\\nx.json" in seen


_BANNED = {
    "core.filesystem", "core.protected_paths", "tools.file_tools", "tools.patch_tools", "tools.shell_tools",
}


@pytest.mark.parametrize("rel", ["core/setup_dr_key.py", "core/tty_confirm.py"])
def test_operator_guard_modules_do_not_import_the_file_tool_layer(rel):
    tree = ast.parse((REPO / rel).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names = {mod} | {f"{mod}.{a.name}" for a in node.names}
        else:
            continue
        assert not (names & _BANNED), (rel, names)


def test_tty_confirm_primitive_is_what_both_modules_use():
    # The seams delegate to the shared primitive (no private copy of the
    # y/yes / tcflush logic in either operator script).
    for mod in (pa, dr):
        src = (REPO / ("tools/provision_ai_agent_auth.py" if mod is pa else "core/setup_dr_key.py")).read_text()
        assert "tty_confirm.confirm_on_tty" in src and "termios" not in src
    assert tty_confirm.TTY_PATH == "/dev/tty"
