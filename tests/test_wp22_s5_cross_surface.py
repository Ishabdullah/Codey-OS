"""WP2.2 S5: cross-surface closure of the live-store guard.

One rig, one claim per surface: in a NON-production configuration the live
Restoricon store is refused by (1) the Python DatabaseManager (bare and with a
live path), (2) the three operator CLIs and the server main(), (3) the file
tools and (4) the shell tool; a world session (env exported from
tools.world) opens its OWN world DB but still not live; only production=True
opens live.  "Live" is a tmp fixture reached by monkeypatching
world.live_db_paths/_passwd_home; the real ~/.codeyOS, ~/.codeyOS-worlds and
restoricon.db are never opened.  Opaque script execution (python3 -c ...) is
an accepted residual (G15b-19) and is deliberately not asserted here.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import core.checkpoint as checkpoint_module
import core.filesystem as filesystem_module
import core.protected_paths as pp
from core import action_gateway
from core.action_gateway import HIGH_IMPACT, ActionGateway, reset_action_gateway
from core.filesystem import Filesystem, FilesystemAccessError
from restoricon_core import database as dbmod
from restoricon_core import world as guard
from restoricon_core.api import server as server_mod
from restoricon_core.database import DatabaseManager
from tools import file_tools, patch_tools, shell_tools
from tools import world as wtool
from utils.config import AGENT_CONFIG

REAL_CONNECT = sqlite3.connect
SUFFIXES = ["", "-wal", "-shm"]


def _sig(p):
    try:
        st = os.stat(p)
    except FileNotFoundError:
        return None
    return (st.st_ino, st.st_size, st.st_mtime_ns)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    """tmp home with a real tiny sqlite 'live' store + -wal/-shm placeholders."""
    import utils.config as cfg

    home = tmp_path / "home"
    state = home / ".codeyOS"
    code = tmp_path / "code"
    audit = tmp_path / "audit" / "ledger.jsonl"
    for d in (state, code, audit.parent):
        d.mkdir(parents=True)
    live = state / "restoricon.db"
    c = REAL_CONNECT(str(live))
    c.execute("CREATE TABLE t (x)")
    c.execute("INSERT INTO t VALUES ('LIVE-SENTINEL')")
    c.commit()
    c.close()
    (state / "restoricon.db-wal").write_bytes(b"FAKE-WAL")
    (state / "restoricon.db-shm").write_bytes(b"FAKE-SHM")
    live_s = str(live)

    monkeypatch.setattr(guard, "live_db_paths", lambda: {live_s})
    monkeypatch.setattr(guard, "_passwd_home", lambda: str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEY_STATE_DIR", str(state))
    monkeypatch.setenv("RESTORICON_DB_PATH", str(tmp_path / "devdb" / "dev.db"))
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(audit))
    monkeypatch.setenv("CODEY_WORLDS_ROOT", str(tmp_path / "worlds"))
    monkeypatch.delenv("CODEY_CONFIG_PATH", raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join([str(home / "bin"), str(code)]))
    monkeypatch.setattr(cfg, "CODEY_STATE_DIR", state)
    monkeypatch.setattr(cfg, "WORKSPACE_ROOT", home)
    monkeypatch.setattr(cfg, "CODEY_DIR", code)
    monkeypatch.setattr(filesystem_module, "CODE_DIR", code)
    monkeypatch.setattr(checkpoint_module, "CODE_DIR", code)
    monkeypatch.setattr(shell_tools, "CODE_DIR", code)
    monkeypatch.setattr(shell_tools._config, "CODEY_STATE_DIR", state)
    monkeypatch.setattr(shell_tools._config, "WORKSPACE_ROOT", home)
    monkeypatch.setattr(shell_tools, "_command_shadows_system_binary", lambda command: False)
    monkeypatch.chdir(home)
    snap = Mock()
    monkeypatch.setattr(filesystem_module, "_snapshot", snap)
    monkeypatch.setattr(patch_tools, "snapshot", snap)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_write", False)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    monkeypatch.setitem(AGENT_CONFIG, "allow_self_modification", False)
    monkeypatch.delitem(AGENT_CONFIG, "_shell_fn", raising=False)
    reset_action_gateway()
    fs = Filesystem(workspace=tmp_path)
    monkeypatch.setattr(filesystem_module, "get_filesystem", lambda *a, **k: fs)
    monkeypatch.setattr(file_tools, "_fs", fs)
    monkeypatch.setattr(file_tools, "_fs_allow_self_mod", False)
    gw = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: gw)
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: gw)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="ok", stderr=""))
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    monkeypatch.setattr(shell_tools, "ask_confirm", Mock(return_value=True))

    r = SimpleNamespace(
        tmp=tmp_path, home=home, state=state, live=live, live_s=live_s, audit=audit,
        fs=fs, runner=runner, expect_unchanged=True,
        family=[live_s + s for s in SUFFIXES],
    )
    before = [_sig(p) for p in r.family]
    yield r
    # Every non-production case must leave the live fixture byte-for-byte alone.
    if r.expect_unchanged:
        assert [_sig(p) for p in r.family] == before
        assert live.read_bytes()[:15] == b"SQLite format 3"
    reset_action_gateway()


@pytest.fixture
def no_connect(monkeypatch):
    calls = []

    def boom(database, *a, **k):
        calls.append(database)
        raise AssertionError(f"sqlite3.connect reached for {database!r}")

    monkeypatch.setattr(dbmod.sqlite3, "connect", boom)
    return calls


def _refused_row(rig):
    row = json.loads(rig.audit.read_text().splitlines()[-1])
    assert row["authority"] == HIGH_IMPACT and row["outcome"] == "refused", row


# ------------------------------------------------------ 1. Python surface


@pytest.mark.parametrize("suffix", SUFFIXES)
@pytest.mark.parametrize("init_schema", [True, False])
def test_database_manager_with_live_path_refused(rig, no_connect, suffix, init_schema):
    with pytest.raises(guard.LiveStoreRefused):
        DatabaseManager(rig.live_s + suffix, init_schema=init_schema)
    assert no_connect == []


def test_bare_database_manager_without_env_refused(rig, monkeypatch, no_connect):
    monkeypatch.delenv("RESTORICON_DB_PATH")
    with pytest.raises(guard.WorldConfigError, match="RESTORICON_DB_PATH"):
        DatabaseManager()
    assert no_connect == []


@pytest.mark.parametrize("suffix", SUFFIXES)
def test_bare_database_manager_with_env_at_live_refused(rig, monkeypatch, no_connect, suffix):
    monkeypatch.setenv("RESTORICON_DB_PATH", rig.live_s + suffix)
    with pytest.raises(guard.LiveStoreRefused):
        DatabaseManager()
    assert no_connect == []


def test_control_non_live_env_path_opens(rig, monkeypatch):
    """Control: a non-live env path opens fine, so the refusals above are the
    guard and not a broken environment."""
    db = DatabaseManager()
    try:
        assert Path(db.db_path).name == "dev.db"
    finally:
        db.close()


# --------------------------------------- 2. operator CLIs and server main()


@pytest.fixture(params=["migrate", "backfill"])
def cli(request):
    from restoricon_core import backfill_wo_351695937 as bf
    from restoricon_core import migrate_aigentik as mg

    return {"migrate": mg, "backfill": bf}[request.param]


@pytest.mark.parametrize("suffix", SUFFIXES)
def test_cli_refuses_live_without_world_production(rig, cli, no_connect, capsys, suffix):
    assert cli.main(["--db-path", rig.live_s + suffix]) == 2
    assert "live Restoricon store" in capsys.readouterr().err
    assert no_connect == []


def test_cli_refuses_live_via_env(rig, cli, monkeypatch, no_connect, capsys):
    monkeypatch.setenv("RESTORICON_DB_PATH", rig.live_s)
    assert cli.main([]) == 2
    assert "live Restoricon store" in capsys.readouterr().err
    assert no_connect == []


def test_cli_no_db_no_env_refused(rig, cli, monkeypatch, capsys):
    monkeypatch.delenv("RESTORICON_DB_PATH")
    assert cli.main([]) == 2
    assert "RESTORICON_DB_PATH" in capsys.readouterr().err


@pytest.mark.parametrize("suffix", SUFFIXES)
def test_provision_cli_refuses_live(rig, monkeypatch, capsys, no_connect, suffix):
    from tools import provision_ai_agent_auth as pa

    boom = Mock(side_effect=AssertionError("gate/tty reached"))
    monkeypatch.setattr(pa, "_gate_provision", boom)
    monkeypatch.setattr(pa, "_open_tty", boom)
    monkeypatch.setattr(sys, "argv", ["prov", "--db-path", rig.live_s + suffix])
    assert pa.main() == 2
    cap = capsys.readouterr()
    assert cap.out == "" and "live Restoricon store" in cap.err
    boom.assert_not_called()
    assert no_connect == []


@pytest.mark.parametrize("suffix", SUFFIXES)
def test_server_main_refuses_live_before_banner_or_bind(rig, monkeypatch, capsys, no_connect, suffix):
    bound = []
    monkeypatch.setattr(server_mod, "ThreadingHTTPServer", lambda *a, **k: bound.append(a))
    assert server_mod.main(["--db", rig.live_s + suffix, "--port", "0"]) == 2
    cap = capsys.readouterr()
    assert "refusing to start" in cap.err and "live Restoricon store" in cap.err
    assert "Server Live" not in cap.out
    assert bound == [] and no_connect == []


def test_server_constructor_refuses_live(rig, no_connect):
    with pytest.raises(guard.LiveStoreRefused):
        server_mod.RestoriconAPIServer(db_path=rig.live_s, port=0)
    assert no_connect == []


# ------------------------------------------------------------ 3. file tools


@pytest.mark.parametrize("suffix", SUFFIXES)
def test_file_read_of_live_denied_without_leak(rig, suffix):
    p = rig.live_s + suffix
    with pytest.raises(FilesystemAccessError, match="credential"):
        rig.fs.read(p)
    out = file_tools.tool_read_file(p)
    assert out.startswith("[ERROR] Access denied"), out
    assert "LIVE-SENTINEL" not in out and "FAKE-WAL" not in out


@pytest.mark.parametrize("suffix", SUFFIXES)
def test_file_write_and_patch_of_live_do_not_modify(rig, suffix):
    p = rig.live_s + suffix
    before = Path(p).read_bytes()
    w = file_tools.tool_write_file(p, "OVERWRITTEN")
    assert w.startswith(("[BLOCKED]", "[ERROR]")), w
    pt = patch_tools.tool_patch_file(p, "LIVE", "X")
    assert pt.startswith(("[BLOCKED]", "[ERROR]")), pt
    assert "LIVE-SENTINEL" not in pt
    assert Path(p).read_bytes() == before


# --------------------------------------------------------------- 4. shell


@pytest.mark.parametrize("suffix", SUFFIXES)
def test_shell_cat_of_live_refused(rig, suffix):
    result = shell_tools.shell(f"cat {rig.live_s}{suffix}")
    assert result.startswith("[BLOCKED]"), result
    rig.runner.assert_not_called()
    _refused_row(rig)


@pytest.mark.parametrize("command", [
    "sqlite3 {live} .tables", "sqlite3 {live} 'select * from t'",
    "grep -a LIVE {live}", "cp {live} /tmp/x", "strings {live}",
])
def test_shell_other_readers_of_live_do_not_run(rig, command):
    """Other readers/copiers of the live DB are blocked before subprocess.run
    (credential-path scan or HIGH_IMPACT classification; either is a refusal)."""
    result = shell_tools.shell(command.format(live=rig.live_s))
    assert result.startswith("[BLOCKED]"), (command, result)
    rig.runner.assert_not_called()


# ------------------------------------------------- 5. world session pair


def _enter_world_session(rig, monkeypatch, name="s5"):
    """Create a tmp world and apply its exported env to this process."""
    import utils.config as cfg

    info = wtool.cmd_create(name)
    exports = {}
    for line in wtool.cmd_env(name):
        if line.startswith("export "):
            k, _, v = line[len("export "):].partition("=")
            exports[k] = v.strip("'")
    for k, v in exports.items():
        monkeypatch.setenv(k, v)
    state = Path(exports["CODEY_STATE_DIR"])
    monkeypatch.setattr(cfg, "CODEY_STATE_DIR", state)
    monkeypatch.setattr(shell_tools._config, "CODEY_STATE_DIR", state)
    return SimpleNamespace(info=info, state=state, db=exports["RESTORICON_DB_PATH"])


def test_world_session_opens_own_db_but_not_live(rig, monkeypatch):
    w = _enter_world_session(rig, monkeypatch)
    assert os.path.realpath(w.db) != os.path.realpath(rig.live_s)
    assert not guard.is_live_path_strict(w.db)
    # bare constructor resolves through the world env: its OWN db
    db = DatabaseManager()
    try:
        assert db.db_path == os.path.realpath(w.db)
        db.get_connection().execute("SELECT 1")
    finally:
        db.close()
    # same session, live path and live-via-env: refused
    with pytest.raises(guard.LiveStoreRefused):
        DatabaseManager(rig.live_s)
    monkeypatch.setenv("RESTORICON_DB_PATH", rig.live_s)
    with pytest.raises(guard.LiveStoreRefused):
        DatabaseManager()


def test_world_session_protects_world_db_and_still_live_on_file_and_shell(rig, monkeypatch):
    w = _enter_world_session(rig, monkeypatch)
    # T-PROT inside the session: the world's restoricon.db* is a credential file
    assert pp.credential_read_hit([w.db], home=rig.home) == "credential-file"
    assert pp.credential_read_hit([w.db + "-wal"], home=rig.home) == "credential-file"
    # live is still protected (HOME/.codeyOS stays a root next to the world state)
    assert pp.credential_read_hit([rig.live_s], home=rig.home) == "credential-file"
    for p in (w.db, rig.live_s):
        with pytest.raises(FilesystemAccessError, match="credential"):
            rig.fs.read(p)
        result = shell_tools.shell(f"cat {p}")
        assert result.startswith("[BLOCKED]"), (p, result)
    rig.runner.assert_not_called()


def test_world_db_is_ordinary_outside_a_world_session(rig, monkeypatch):
    """Without the world env the world state dir is not a protected root, so
    the pattern does not match its DB (documented in docs/worlds.md)."""
    info = wtool.cmd_create("s5out")
    db = os.path.join(info["dir"], "state", "restoricon.db")
    assert pp.credential_read_hit([db], home=rig.home) is None
    assert pp.credential_read_hit([rig.live_s], home=rig.home) == "credential-file"
    assert not guard.is_live_path_strict(db)


# ------------------------------------------------- 6. production control


def test_only_production_true_opens_live(rig, capsys):
    rig.expect_unchanged = False  # a real production open may touch the fixture
    # the same call without production is refused ...
    with pytest.raises(guard.LiveStoreRefused):
        DatabaseManager(rig.live_s, init_schema=False)
    # ... and with it, it opens and announces itself once on stderr
    db = DatabaseManager(rig.live_s, init_schema=False, production=True)
    try:
        assert db.db_path == os.path.realpath(rig.live_s)
        row = db.get_connection().execute("SELECT x FROM t").fetchone()
        assert row[0] == "LIVE-SENTINEL"
    finally:
        db.close()
    assert capsys.readouterr().err.count("PRODUCTION open of live store") == 1


def test_env_var_cannot_grant_production(rig, monkeypatch, no_connect):
    for k in ("RESTORICON_WORLD", "RESTORICON_WORLD_NAME", "RESTORICON_PRODUCTION", "CODEY_WORLD"):
        monkeypatch.setenv(k, "production")
    with pytest.raises(guard.LiveStoreRefused):
        DatabaseManager(rig.live_s)
    assert no_connect == []
