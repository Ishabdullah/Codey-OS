"""WP2.2 S3b: DatabaseManager/server/CLI enforcement of the live-store guard.

Every test uses a tmp "live" file with ``world.live_db_paths`` monkeypatched
(or a tmp passwd home); nothing here opens, reads or connects to the real
``~/.codeyOS/restoricon.db``.  No hardlink case is covered: ``os.link`` is
absent on this Termux Python, so the post-open inode check is exercised with
symlink swaps only (hardlink detection is untested on this device).
"""
from __future__ import annotations

import ast
import io
import os
import sqlite3
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

import pytest

from restoricon_core import database as dbmod
from restoricon_core import world
from restoricon_core.api import server as server_mod
from restoricon_core.database import DatabaseManager

REPO = Path(__file__).resolve().parents[1]
REAL_CONNECT = sqlite3.connect


@pytest.fixture
def fake_live(tmp_path, monkeypatch):
    """A real (empty-schema) sqlite file standing in for the live store."""
    live = tmp_path / "home" / ".codeyOS" / "restoricon.db"
    live.parent.mkdir(parents=True)
    c = REAL_CONNECT(str(live))
    c.execute("CREATE TABLE t (x)")
    c.commit()
    c.close()
    monkeypatch.setattr(world, "live_db_paths", lambda: {str(live)})
    return live


@pytest.fixture
def connect_spy(monkeypatch):
    """Record every sqlite3.connect call; delegate to the real one."""
    calls = []

    def spy(database, *a, **k):
        calls.append(database)
        return REAL_CONNECT(database, *a, **k)

    monkeypatch.setattr(dbmod.sqlite3, "connect", spy)
    return calls


@pytest.fixture
def no_connect(monkeypatch):
    """Any sqlite3.connect call fails the test."""
    calls = []

    def boom(database, *a, **k):
        calls.append(database)
        raise AssertionError(f"sqlite3.connect reached for {database!r}")

    monkeypatch.setattr(dbmod.sqlite3, "connect", boom)
    return calls


def _sig(p):
    try:
        st = os.stat(p)
    except FileNotFoundError:
        return None
    return (st.st_ino, st.st_size, st.st_mtime_ns)


# --------------------------------------------------------------- T-NODEFAULT


def test_no_default_constant():
    assert not hasattr(dbmod, "DEFAULT_DB_PATH")
    with pytest.raises(ImportError):
        exec("from restoricon_core.database import DEFAULT_DB_PATH")


def test_bare_manager_without_env_raises(monkeypatch, no_connect):
    monkeypatch.delenv("RESTORICON_DB_PATH", raising=False)
    with pytest.raises(world.WorldConfigError, match="RESTORICON_DB_PATH"):
        DatabaseManager()


def test_env_path_is_used(monkeypatch, tmp_path):
    target = tmp_path / "e" / "env.db"
    monkeypatch.setenv("RESTORICON_DB_PATH", str(target))
    db = DatabaseManager()
    try:
        assert db.db_path == os.path.realpath(str(target))
        assert target.exists()
    finally:
        db.close()


@pytest.mark.parametrize("bad", [Path(""), ".", "a\x00b"])
def test_bad_paths_raise(bad, no_connect):
    with pytest.raises(world.WorldConfigError):
        DatabaseManager(bad)


def test_memory_works_without_env(monkeypatch):
    monkeypatch.delenv("RESTORICON_DB_PATH", raising=False)
    db = DatabaseManager(":memory:")
    assert db.is_memory
    db.close()


# ---------------------------------------------------- T-REFUSE-BEFORE-IO


def _variants(live, tmp_path, monkeypatch):
    link = tmp_path / "link.db"
    link.symlink_to(live)
    return {
        "exact": str(live),
        "wal": str(live) + "-wal",
        "shm": str(live) + "-shm",
        "symlink": str(link),
        "dotdot": str(live.parent / "x" / ".." / live.name),
        "trailing_dot": str(live) + "/.",
    }


@pytest.mark.parametrize("init_schema", [True, False])
@pytest.mark.parametrize(
    "kind", ["exact", "wal", "shm", "symlink", "dotdot", "trailing_dot", "relative"]
)
def test_live_refused_before_any_io(kind, init_schema, fake_live, tmp_path, monkeypatch, no_connect):
    made = []
    real_mkdir = Path.mkdir

    def spy_mkdir(self, *a, **k):
        made.append(str(self))
        return real_mkdir(self, *a, **k)

    monkeypatch.setattr(Path, "mkdir", spy_mkdir)
    if kind == "relative":
        monkeypatch.chdir(fake_live.parent)
        path = fake_live.name
    else:
        path = _variants(fake_live, tmp_path, monkeypatch)[kind]
    with pytest.raises(world.LiveStoreRefused):
        DatabaseManager(path, init_schema=init_schema)
    assert no_connect == []
    assert made == []


def test_refusal_does_not_create_missing_parent(tmp_path, monkeypatch, no_connect):
    live = tmp_path / "nolive" / "sub" / "restoricon.db"
    monkeypatch.setattr(world, "live_db_paths", lambda: {str(live)})
    with pytest.raises(world.LiveStoreRefused):
        DatabaseManager(live)
    assert not live.parent.exists()
    assert not (tmp_path / "nolive").exists()


# ------------------------------------------------------------ T-PRODUCTION


def test_production_opens_live_with_one_audit_line(fake_live, capsys):
    db = DatabaseManager(fake_live, production=True)
    try:
        assert db.db_path == os.path.realpath(str(fake_live))
        db.get_connection()
    finally:
        db.close()
    err = capsys.readouterr().err
    assert err.count("[restoricon world] PRODUCTION open of live store:") == 1


def test_production_on_nonlive_is_silent(fake_live, tmp_path, capsys):
    db = DatabaseManager(tmp_path / "w" / "dev.db", production=True)
    db.close()
    assert capsys.readouterr().err == ""


# ------------------------------------------------------------ T-FILE-URI


@pytest.mark.parametrize("uri", ["file:/tmp/x.db", "FILE:/tmp/x.db", "File:x.db?mode=ro"])
def test_file_uri_rejected(uri, no_connect):
    with pytest.raises(world.WorldConfigError, match="file:"):
        DatabaseManager(uri)
    assert no_connect == []


# ------------------------------------------------------- T-W1-MESSAGES


def _cfg_home(tmp_path, monkeypatch, content: bytes):
    home = tmp_path / "pwhome"
    (home / ".codeyOS").mkdir(parents=True)
    cfg = home / ".codeyOS" / "config.json"
    cfg.write_bytes(content)
    monkeypatch.setattr(world, "_passwd_home", lambda: str(home))
    return cfg


BAD_CONFIGS = {
    "garbage": b"{not json",
    "empty": b"",
    "non_dict": b"[1, 2]",
    "oversized": b" " * (world._MAX_CONFIG_BYTES + 5),
}


@pytest.mark.parametrize("name", sorted(BAD_CONFIGS))
@pytest.mark.parametrize("production", [False, True])
def test_bad_config_surfaces_own_message(name, production, tmp_path, monkeypatch, no_connect):
    cfg = _cfg_home(tmp_path, monkeypatch, BAD_CONFIGS[name])
    target = tmp_path / "never" / "dev.db"
    with pytest.raises(world.WorldConfigError) as ei:
        DatabaseManager(target, production=production)
    msg = str(ei.value)
    assert str(cfg) in msg
    assert "refusing to open live" not in msg
    assert not target.parent.exists()


@pytest.mark.parametrize("name", ["garbage", "empty"])
def test_bad_config_through_clis_and_server(name, tmp_path, monkeypatch, capsys, no_connect):
    from restoricon_core import backfill_wo_351695937 as bf
    from restoricon_core import migrate_aigentik as mg

    cfg = _cfg_home(tmp_path, monkeypatch, BAD_CONFIGS[name])
    target = str(tmp_path / "never" / "dev.db")
    assert mg.main(["--db-path", target]) == 2
    assert str(cfg) in capsys.readouterr().err
    assert bf.main(["--db-path", target]) == 2
    assert str(cfg) in capsys.readouterr().err
    assert server_mod.main(["--db", target, "--port", "0"]) == 2
    cap = capsys.readouterr()
    assert str(cfg) in cap.err
    assert "Server Live" not in cap.out
    assert not (tmp_path / "never").exists()


# ------------------------------------------------------ T-RESOLVED-PATH


def test_connect_receives_classified_realpath(tmp_path, connect_spy):
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    (tmp_path / "linkdir").symlink_to(real_dir)
    path = tmp_path / "linkdir" / "sub" / ".." / "d.db"
    db = DatabaseManager(path)
    try:
        expected = os.path.realpath(str(path))
        assert expected == str(real_dir.resolve() / "d.db")
        assert connect_spy and connect_spy[0] == expected
    finally:
        db.close()


# -------------------------------------------------- T-POSTOPEN-SWAP (W3)


def _swapping_connect(monkeypatch, leaf, target, counter=None):
    """sqlite3.connect wrapper: right before delegating, repoint ``leaf`` at
    ``target`` (the checked path now opens the live store)."""
    def swap(database, *a, **k):
        if os.path.realpath(database) == os.path.realpath(leaf) or counter is None:
            tmp_link = str(leaf) + ".swap"
            os.symlink(str(target), tmp_link)
            os.replace(tmp_link, str(leaf))
        return REAL_CONNECT(database, *a, **k)

    monkeypatch.setattr(dbmod.sqlite3, "connect", swap)


def test_postopen_swap_refused_before_any_write(fake_live, tmp_path, monkeypatch):
    # Hold the live DB in WAL mode with a second connection so -wal/-shm exist.
    holder = REAL_CONNECT(str(fake_live))
    holder.execute("PRAGMA journal_mode=WAL")
    holder.execute("INSERT INTO t VALUES (1)")
    holder.commit()
    try:
        family = [str(fake_live) + s for s in ("", "-wal", "-shm")]
        before = [_sig(p) for p in family]
        leaf = tmp_path / "dev" / "dev.db"
        db = DatabaseManager(leaf, init_schema=False)  # opens nothing yet
        leaf.write_bytes(b"")  # leaf exists, non-live at guard time
        _swapping_connect(monkeypatch, leaf, fake_live)

        with pytest.raises(world.LiveStoreRefused):
            db.get_connection()
        assert getattr(dbmod._local, f"conn_{db.db_path}", None) is None
        assert [_sig(p) for p in family] == before
        assert os.path.islink(leaf)  # swapped, never written through
    finally:
        holder.close()


def test_postopen_swap_retry_rechecks(fake_live, tmp_path, monkeypatch):
    """A refused connection is not cached, so a retry runs the check again.
    No second live connection is held here: while one is, SQLite's unix VFS
    keeps the closed connection's fd in the shared inode's unused list and
    reuses it, which the fd diff cannot see (documented residual in
    world.assert_opened_not_live; production and dev are separate processes)."""
    leaf = tmp_path / "dev" / "dev.db"
    db = DatabaseManager(leaf, init_schema=False)
    leaf.write_bytes(b"")
    _swapping_connect(monkeypatch, leaf, fake_live)
    for _ in range(3):
        with pytest.raises(world.LiveStoreRefused):
            db.get_connection()
        assert getattr(dbmod._local, f"conn_{db.db_path}", None) is None


def test_postopen_swap_second_thread_refused(fake_live, tmp_path, monkeypatch):
    leaf = tmp_path / "dev" / "dev.db"
    db = DatabaseManager(leaf)  # first connection (this thread) is fine
    try:
        results = {}

        def worker():
            try:
                db.get_connection()
                results["ok"] = True
            except BaseException as exc:  # noqa: BLE001 - recorded, asserted below
                results["exc"] = exc

        # swap the leaf to the live store right before the worker's connect
        _swapping_connect(monkeypatch, leaf, fake_live)
        t = threading.Thread(target=worker)
        t.start()
        t.join(10)
        assert not t.is_alive()
        assert isinstance(results.get("exc"), world.LiveStoreRefused), results
    finally:
        monkeypatch.undo()
        db.close()


def test_production_on_nonlive_path_still_checked_for_swap(fake_live, tmp_path, monkeypatch, capsys):
    """production=True only skips the post-open check for an AUTHORIZED live
    open; a non-live path swapped to the live store after the guard is refused."""
    leaf = tmp_path / "dev" / "dev.db"
    db = DatabaseManager(leaf, init_schema=False, production=True)
    assert db._live_authorized is False
    leaf.write_bytes(b"")
    _swapping_connect(monkeypatch, leaf, fake_live)
    with pytest.raises(world.LiveStoreRefused):
        db.get_connection()
    assert getattr(dbmod._local, f"conn_{db.db_path}", None) is None


def test_authorized_live_open_flag_and_audit_line(fake_live, capsys):
    db = DatabaseManager(fake_live, production=True)
    try:
        assert db._live_authorized is True
        assert db.get_connection() is not None
    finally:
        db.close()
    assert capsys.readouterr().err.count("PRODUCTION open of live store") == 1


def test_postopen_check_skipped_for_production_and_memory(fake_live, monkeypatch):
    called = []
    monkeypatch.setattr(world, "snapshot_fd_inodes", lambda: called.append(1) or {})
    DatabaseManager(":memory:").get_connection()
    DatabaseManager(fake_live, production=True).get_connection()
    assert called == []


def test_proc_fd_unreadable_fails_closed(tmp_path, monkeypatch):
    db = DatabaseManager(tmp_path / "d.db", init_schema=False)
    real_listdir = os.listdir

    def fake_listdir(p="."):
        if str(p) == "/proc/self/fd":
            raise OSError("no /proc")
        return real_listdir(p)

    monkeypatch.setattr(world.os, "listdir", fake_listdir)
    with pytest.raises(world.WorldConfigError, match="/proc/self/fd"):
        db.get_connection()


def test_no_per_manager_fd_state_retained(tmp_path):
    db = DatabaseManager(tmp_path / "d.db")
    try:
        assert not any("fd" in k or "inode" in k or "snapshot" in k for k in vars(db))
    finally:
        db.close()


# ----------------------------------------------- T-MAIN / T-SERVER-E2E


def test_main_passes_production_kwarg(tmp_path, monkeypatch, capsys):
    seen = []

    class Stub:
        def __init__(self, **kw):
            seen.append(kw)

        def start(self, background=False):
            return None

    monkeypatch.setattr(server_mod, "RestoriconAPIServer", Stub)
    db = str(tmp_path / "x.db")
    assert server_mod.main(["--db", db, "--world", "production"]) == 0
    assert server_mod.main(["--db", db]) == 0
    assert seen[0]["production"] is True and seen[0]["db_path"] == db
    assert seen[1]["production"] is False and seen[1]["db_path"] == db
    assert "Server Live" in capsys.readouterr().out


def test_main_keyboard_interrupt_returns_zero_and_stops(tmp_path, monkeypatch, capsys):
    stopped = []

    class Stub:
        def __init__(self, **kw):
            pass

        def start(self, background=False):
            raise KeyboardInterrupt

        def stop(self):
            stopped.append(1)

    monkeypatch.setattr(server_mod, "RestoriconAPIServer", Stub)
    assert server_mod.main(["--db", str(tmp_path / "x.db")]) == 0
    assert stopped == [1]


def test_main_refusal_returns_2_before_banner_or_bind(fake_live, monkeypatch, capsys, no_connect):
    bound = []

    def spy_httpd(*a, **k):
        bound.append(a)
        raise AssertionError("port bound")

    monkeypatch.setattr(server_mod, "ThreadingHTTPServer", spy_httpd)
    rc = server_mod.main(["--db", str(fake_live), "--port", "0"])
    cap = capsys.readouterr()
    assert rc == 2
    assert "refusing to start" in cap.err and "live Restoricon store" in cap.err
    assert "Server Live" not in cap.out and cap.out == ""
    assert bound == []


def test_server_no_db_no_env_refused(monkeypatch):
    monkeypatch.delenv("RESTORICON_DB_PATH", raising=False)
    with pytest.raises(world.WorldConfigError):
        server_mod.RestoriconAPIServer(port=0)


def test_server_e2e(fake_live, monkeypatch):
    with pytest.raises(world.LiveStoreRefused):
        server_mod.RestoriconAPIServer(db_path=str(fake_live), port=0)
    srv = server_mod.RestoriconAPIServer(db_path=str(fake_live), port=0, production=True)
    try:
        srv.start(background=True)
        port = srv.httpd.server_address[1]
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/quote", timeout=10) as resp:
            assert resp.status == 200
    finally:
        srv.stop()


# ------------------------------------------------------------------ T-CLI


@pytest.fixture(params=["migrate", "backfill"])
def cli(request):
    from restoricon_core import backfill_wo_351695937 as bf
    from restoricon_core import migrate_aigentik as mg

    return {"migrate": mg, "backfill": bf}[request.param]


def test_cli_no_db_no_env_exit_2(cli, monkeypatch, capsys):
    monkeypatch.delenv("RESTORICON_DB_PATH", raising=False)
    assert cli.main([]) == 2
    assert "RESTORICON_DB_PATH" in capsys.readouterr().err


def test_cli_live_requires_world_production(cli, fake_live, monkeypatch, capsys, no_connect):
    assert cli.main(["--db-path", str(fake_live)]) == 2
    err = capsys.readouterr().err
    assert "live Restoricon store" in err
    assert no_connect == []


def test_cli_live_with_world_production_constructs(cli, fake_live, monkeypatch, capsys, connect_spy):
    """Real DatabaseManager (dry run, init_schema False): the guard passes and
    prints the production line; the runner is stubbed so nothing connects."""
    runner = "run_migration" if cli.__name__.endswith("migrate_aigentik") else "run_backfill"
    seen = []
    monkeypatch.setattr(cli, runner, lambda *a, **k: seen.append(a[0] if runner == "run_backfill" else a[1]) or {})
    monkeypatch.setattr(cli, "print_report", lambda *a, **k: None)
    assert cli.main(["--db-path", str(fake_live), "--world", "production"]) == 0
    assert len(seen) == 1 and seen[0].production is True
    assert seen[0].db_path == os.path.realpath(str(fake_live))
    assert capsys.readouterr().err.count("PRODUCTION open of live store") == 1
    assert connect_spy == []


def test_cli_tmp_path_dry_run_unchanged(cli, tmp_path, monkeypatch):
    seen = {}

    class FakeDB:
        def __init__(self, path, init_schema=True, *, production=False):
            seen.update(path=path, init_schema=init_schema, production=production)

    runner = "run_migration" if cli.__name__.endswith("migrate_aigentik") else "run_backfill"
    monkeypatch.setattr(cli, "DatabaseManager", FakeDB)
    monkeypatch.setattr(cli, runner, lambda *a, **k: {})
    monkeypatch.setattr(cli, "print_report", lambda *a, **k: None)
    p = str(tmp_path / "d.db")
    assert cli.main(["--db-path", p]) == 0
    assert seen == {"path": p, "init_schema": False, "production": False}


def test_provision_refusal_before_gate_and_tty(fake_live, monkeypatch, capsys):
    from tools import provision_ai_agent_auth as pa

    def boom(*a, **k):
        raise AssertionError("gate/tty reached")

    monkeypatch.setattr(pa, "_gate_provision", boom)
    monkeypatch.setattr(pa, "_open_tty", boom)
    monkeypatch.setattr(pa, "DatabaseManager", boom)
    with pytest.raises(world.LiveStoreRefused):
        pa.provision(db_path=str(fake_live))
    monkeypatch.setattr(sys, "argv", ["prov", "--db-path", str(fake_live)])
    assert pa.main() == 2
    cap = capsys.readouterr()
    assert cap.out == ""
    assert "live Restoricon store" in cap.err


def test_provision_no_db_no_env_exit_2(monkeypatch, capsys):
    from tools import provision_ai_agent_auth as pa

    monkeypatch.delenv("RESTORICON_DB_PATH", raising=False)
    monkeypatch.setattr(pa, "_gate_provision", lambda *a, **k: pytest.fail("gate"))
    monkeypatch.setattr(sys, "argv", ["prov"])
    assert pa.main() == 2
    cap = capsys.readouterr()
    assert cap.out == "" and "RESTORICON_DB_PATH" in cap.err


def test_provision_bad_config_surfaces_message(tmp_path, monkeypatch, capsys):
    from tools import provision_ai_agent_auth as pa

    cfg = _cfg_home(tmp_path, monkeypatch, b"{not json")
    monkeypatch.setattr(pa, "_gate_provision", lambda *a, **k: pytest.fail("gate"))
    monkeypatch.setattr(sys, "argv", ["prov", "--db-path", str(tmp_path / "d.db")])
    assert pa.main() == 2
    assert str(cfg) in capsys.readouterr().err


# ------------------------------------------------------------------ T-AST


def _tracked_py():
    out = subprocess.run(
        ["/data/data/com.termux/files/usr/bin/git", "ls-files", "*.py"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.split()
    return [p for p in out if (REPO / p).exists()]


def _is_test_path(p):
    parts = Path(p).parts
    return "tests" in parts or Path(p).name.startswith("test_") or Path(p).name == "conftest.py"


_GUARDED = ("DatabaseManager", "RestoriconAPIServer")


def _guarded_names(tree):
    """Local names bound to the guarded classes: plain, aliased
    (``DatabaseManager as DM``) and module-qualified attribute access."""
    aliases = set(_GUARDED)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name in _GUARDED:
                    aliases.add(a.asname or a.name)
        elif isinstance(node, ast.Assign) and isinstance(node.value, (ast.Name, ast.Attribute)):
            v = node.value
            vname = v.id if isinstance(v, ast.Name) else v.attr
            if vname in aliases:
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        aliases.add(t.id)
    return aliases


def test_ast_default_db_path_gone_and_caller_allowlist():
    callers = {}
    for rel in _tracked_py():
        if _is_test_path(rel):
            continue
        try:
            tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        aliases = _guarded_names(tree)
        for node in ast.walk(tree):
            ident = None
            if isinstance(node, ast.Name):
                ident = node.id
            elif isinstance(node, ast.Attribute):
                ident = node.attr
            elif isinstance(node, ast.alias):
                ident = node.name
            if ident == "DEFAULT_DB_PATH":
                pytest.fail(f"DEFAULT_DB_PATH referenced in {rel}:{node.lineno}")
            if isinstance(node, ast.Call):
                f = node.func
                name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
                if name in aliases:
                    prod = [k for k in node.keywords if k.arg == "production"]
                    callers.setdefault(rel, []).append((node.lineno, prod))
    assert set(callers) == {
        "restoricon_core/api/server.py",
        "restoricon_core/migrate_aigentik.py",
        "restoricon_core/backfill_wo_351695937.py",
        "tools/provision_ai_agent_auth.py",
        "tools/world.py",
    }, sorted(callers)
    for rel, sites in callers.items():
        for lineno, prod in sites:
            assert prod, f"{rel}:{lineno} constructs without production="
            val = prod[0].value
            assert not (isinstance(val, ast.Constant) and val.value is True), (
                f"{rel}:{lineno} hardcodes production=True"
            )


def test_ast_helper_catches_aliases_and_qualified_calls():
    tree = ast.parse(
        "from restoricon_core.database import DatabaseManager as DM\n"
        "import restoricon_core.database as database\n"
        "X = database.DatabaseManager\n"
        "DM(p); database.DatabaseManager(p); X(p)\n"
    )
    assert {"DM", "X", "DatabaseManager"} <= _guarded_names(tree)


# --------------------------------------------------- T-IMPORT-HYGIENE


def test_database_import_does_not_pull_core_or_utils_config():
    code = (
        "import sys, restoricon_core.database;"
        "bad=[m for m in sys.modules if m=='utils.config' or m=='core' or m.startswith('core.')];"
        "print(bad); sys.exit(1 if bad else 0)"
    )
    env = dict(os.environ)
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
