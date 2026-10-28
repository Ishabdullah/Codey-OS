"""WP2.2 S4 tests for tools/world.py.

Everything lives under tmp_path: the worlds root comes from the
CODEY_WORLDS_ROOT override and the "live" store is a tmp fake with
world.live_db_paths/_passwd_home monkeypatched.  The real ~/.codeyOS and
~/.codeyOS-worlds are never created, touched or deleted, the real
restoricon.db is never opened and no service is started.
"""

import json
import os
import shlex
import socket
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from restoricon_core import world as guard
from tools import world as tw

REPO = str(Path(__file__).resolve().parent.parent)


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    """tmp home with a fake live db, tmp worlds root, guard monkeypatched."""
    home = tmp_path / "home"
    live = home / ".codeyOS" / "restoricon.db"
    live.parent.mkdir(parents=True)
    live.write_bytes(b"FAKE-LIVE-DB")
    root = tmp_path / "worlds"
    monkeypatch.setattr(guard, "live_db_paths", lambda: {str(live)})
    monkeypatch.setattr(guard, "_passwd_home", lambda: str(home))
    monkeypatch.setenv("CODEY_WORLDS_ROOT", str(root))
    monkeypatch.delenv("RESTORICON_DB_PATH", raising=False)

    class C:
        pass

    c = C()
    c.tmp, c.home, c.live, c.root = tmp_path, home, live, root
    return c


@pytest.fixture(autouse=True)
def _real_worlds_dir_untouched():
    """The real ~/.codeyOS-worlds must neither appear nor change (lstat only)."""
    import pwd
    real = os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".codeyOS-worlds")

    def sig():
        try:
            st = os.lstat(real)
        except FileNotFoundError:
            return None
        return (st.st_ino, st.st_mtime_ns)

    before = sig()
    yield
    assert sig() == before, "test touched the real ~/.codeyOS-worlds"


import contextlib
import signal


@contextlib.contextmanager
def alarm(seconds=10):
    """Turn a hang (e.g. blocking open of a FIFO) into a test failure."""
    class Hung(BaseException):  # not an OSError/Exception: code under test must not swallow it
        pass

    def boom(signum, frame):
        raise Hung("operation hung")
    old = signal.signal(signal.SIGALRM, boom)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def _live_sig(live):
    st = os.stat(live)
    return (st.st_ino, st.st_size, st.st_mtime_ns)


def _mk(ctx, name="w1"):
    return tw.cmd_create(name)


def _victim(tmp_path):
    d = tmp_path / "victim"
    d.mkdir()
    s = d / "sentinel.txt"
    s.write_text("keep")
    return d, s


# --------------------------------------------------------------------- names

@pytest.mark.parametrize("name", ["a", "dev-1", "x_y", "0abc", "a" * 40])
def test_name_accepts(name):
    assert tw.validate_name(name) == name


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", "../x", "a/b", "A", "-x", "_x", "a" * 41, "a\x00b", "é", "a\n",
     "production", "live", "default", "restoricon", "codeyos", "worlds", ".hidden", None, 5],
)
def test_name_rejects(name):
    with pytest.raises(tw.WorldRefusal):
        tw.validate_name(name)


# ---------------------------------------------------------------- root safety

def test_root_equals_live_dir_refused(ctx):
    with pytest.raises(tw.WorldRefusal):
        tw.assert_root_safe(str(ctx.live.parent))


def test_root_inside_live_dir_refused(ctx):
    with pytest.raises(tw.WorldRefusal):
        tw.assert_root_safe(str(ctx.live.parent / "worlds"))


def test_root_is_home_refused(ctx):
    with pytest.raises(tw.WorldRefusal):
        tw.assert_root_safe(str(ctx.home))


def test_root_slash_refused(ctx):
    with pytest.raises(tw.WorldRefusal):
        tw.assert_root_safe("/")


def test_root_ancestor_of_live_refused(ctx):
    with pytest.raises(tw.WorldRefusal):
        tw.assert_root_safe(str(ctx.tmp))


def test_root_symlink_refused(ctx):
    safe = ctx.tmp / "safe"
    safe.mkdir(mode=0o700)
    link = ctx.tmp / "link"
    link.symlink_to(safe)
    with pytest.raises(tw.WorldRefusal):
        tw.assert_root_safe(str(link))


def test_root_group_writable_refused(ctx):
    ctx.root.mkdir()
    os.chmod(ctx.root, 0o770)
    with pytest.raises(tw.WorldRefusal):
        tw.assert_root_safe(str(ctx.root))


def test_root_not_directory_refused(ctx):
    ctx.root.write_text("x")
    with pytest.raises(tw.WorldRefusal):
        tw.assert_root_safe(str(ctx.root))


def test_sibling_prefix_accepted(ctx):
    sib = ctx.home / ".codeyOS-worlds"
    assert tw.assert_root_safe(str(sib)) == str(sib)


def test_default_root_is_passwd_home_sibling(ctx, monkeypatch):
    monkeypatch.delenv("CODEY_WORLDS_ROOT")
    assert tw.worlds_root() == str(ctx.home / ".codeyOS-worlds")


def test_relative_env_root_refused(ctx, monkeypatch):
    monkeypatch.setenv("CODEY_WORLDS_ROOT", "relative/dir")
    with pytest.raises(guard.WorldConfigError):
        tw.worlds_root()


def test_missing_marker_refuses_list_destroy_env(ctx):
    ctx.root.mkdir(mode=0o700)
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_list()
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_destroy("w1", True)
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_env("w1")


def test_create_in_nonempty_unmarked_dir_refused(ctx):
    ctx.root.mkdir(mode=0o700)
    (ctx.root / "stuff").write_text("x")
    with pytest.raises(tw.WorldRefusal):
        _mk(ctx)
    assert (ctx.root / "stuff").exists()
    assert not (ctx.root / tw.MARKER).exists()


def test_create_in_empty_existing_dir_writes_marker(ctx):
    ctx.root.mkdir(mode=0o700)
    _mk(ctx)
    assert (ctx.root / tw.MARKER).is_file()


# --------------------------------------------------------------------- create

def test_create_layout_modes_manifest(ctx):
    before = _live_sig(ctx.live)
    r = _mk(ctx)
    wd = Path(r["dir"])
    assert wd == ctx.root / "w1"
    for d in (ctx.root, wd, wd / "state", wd / "state" / "restoricon_documents"):
        assert stat.S_IMODE(d.stat().st_mode) == 0o700, d
    for f in (wd / "world.json", wd / "state" / "restoricon.db", ctx.root / tw.MARKER):
        assert stat.S_IMODE(f.stat().st_mode) == 0o600, f
    man = json.loads((wd / "world.json").read_text())
    assert man["schema"] == 1 and man["name"] == "w1" and man["source"] == "empty"
    assert man["created_by"] == "tools.world" and man["root"] == str(ctx.root)
    assert tw.PORT_LO <= man["port"] <= tw.PORT_HI and man["created_at"]
    db = wd / "state" / "restoricon.db"
    assert guard.is_live_path_strict(db) is False
    conn = sqlite3.connect(str(db))
    tables = [x[0] for x in conn.execute("select name from sqlite_master where type='table'")]
    conn.close()
    assert tables
    # opens cleanly via the guarded manager and closes
    from restoricon_core.database import DatabaseManager
    DatabaseManager(str(db)).close()
    assert _live_sig(ctx.live) == before


def test_create_never_connects_to_live(ctx, monkeypatch):
    seen = []
    real = sqlite3.connect

    def spy(*a, **k):
        seen.append(a[0] if a else k.get("database"))
        return real(*a, **k)

    monkeypatch.setattr(sqlite3, "connect", spy)
    _mk(ctx)
    tw.cmd_list()
    tw.cmd_env("w1")
    assert seen
    for s in seen:
        assert os.path.realpath(str(s)) != os.path.realpath(str(ctx.live))


def test_create_duplicate_refused(ctx):
    _mk(ctx)
    with pytest.raises(tw.WorldRefusal):
        _mk(ctx)


def test_create_dangling_symlink_name_refused(ctx):
    _mk(ctx, "w1")
    (ctx.root / "ghost").symlink_to(ctx.tmp / "nowhere")
    with pytest.raises(tw.WorldRefusal):
        _mk(ctx, "ghost")


def test_two_worlds_distinct_ports(ctx):
    a, b = _mk(ctx, "a"), _mk(ctx, "b")
    assert a["dir"] != b["dir"] and a["port"] != b["port"]


def test_port_skips_bound_and_recorded(ctx):
    ctx.root.mkdir(mode=0o700)
    p = tw.allocate_port(str(ctx.root))
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", p))
        q = tw.allocate_port(str(ctx.root))
        assert q > p
    finally:
        s.close()
    # recorded in another manifest -> skipped even though free
    (ctx.root / "other").mkdir()
    (ctx.root / "other" / "world.json").write_text(json.dumps({"port": p}))
    assert tw.allocate_port(str(ctx.root)) != p


def test_create_rollback_removes_only_half_made_world(ctx, monkeypatch):
    _mk(ctx, "keepme")
    keep_sig = sorted(os.listdir(ctx.root / "keepme"))

    def boom(db):
        raise RuntimeError("seed failed")

    monkeypatch.setattr(tw, "_seed_empty", boom)
    with pytest.raises(RuntimeError):
        _mk(ctx, "half")
    assert not (ctx.root / "half").exists()
    assert (ctx.root / tw.MARKER).is_file()
    assert sorted(os.listdir(ctx.root / "keepme")) == keep_sig
    assert (ctx.live).read_bytes() == b"FAKE-LIVE-DB"


def test_create_refuses_when_world_db_classifies_live(ctx, monkeypatch):
    monkeypatch.setattr(guard, "is_live_path_strict", lambda p: True)
    with pytest.raises(tw.WorldRefusal):
        _mk(ctx)
    assert not (ctx.root / "w1").exists()


def test_create_classification_error_aborts(ctx, monkeypatch):
    def err(p):
        raise guard.WorldConfigError("cannot classify")

    monkeypatch.setattr(guard, "is_live_path_strict", err)
    with pytest.raises(guard.WorldConfigError):
        _mk(ctx)
    assert not (ctx.root / "w1").exists()


# ------------------------------------------------------------------ list / env

def test_list_ok_and_broken(ctx):
    _mk(ctx, "good")
    _mk(ctx, "bad")
    (ctx.root / "bad" / "world.json").write_text("garbage")
    (ctx.root / "Not_A_Name").mkdir()
    (ctx.root / "lnk").symlink_to(ctx.tmp)
    rows = {r["name"]: r for r in tw.cmd_list()}
    assert set(rows) == {"good", "bad"}
    assert rows["good"]["state"] == "ok" and rows["bad"]["state"] == "broken"


def test_env_exact_set_and_roundtrip(ctx, monkeypatch):
    weird = ctx.tmp / "wo'r ld s"
    monkeypatch.setenv("CODEY_WORLDS_ROOT", str(weird))
    _mk(ctx)
    lines = tw.cmd_env("w1")
    exports = [ln for ln in lines if not ln.startswith("#")]
    d = {}
    for ln in exports:
        k, v = shlex.split(ln)[1].split("=", 1)
        d[k] = v
    assert set(d) == {
        "CODEY_STATE_DIR", "RESTORICON_DB_PATH", "RESTORICON_DOC_STORE_PATH",
        "CODEY_ACTION_GATEWAY_AUDIT", "RESTORICON_API_HOST", "RESTORICON_API_PORT",
        "RESTORICON_WORLD_NAME",
    }
    wd = os.path.realpath(str(weird / "w1"))
    assert d["CODEY_STATE_DIR"] == wd + "/state"
    assert d["RESTORICON_DB_PATH"] == wd + "/state/restoricon.db"
    assert d["RESTORICON_API_HOST"] == "127.0.0.1"
    blob = "\n".join(lines).lower()
    assert "production" not in blob and "--world" not in blob and "token" not in blob
    # utils.config honours the three explicit-env keys
    for k, v in d.items():
        monkeypatch.setenv(k, v)
    import utils.config as uc
    cfg = uc.get_restoricon_api_config({})
    assert cfg["db_path"] == os.path.realpath(d["RESTORICON_DB_PATH"])
    assert cfg["port"] == int(d["RESTORICON_API_PORT"])
    assert uc.get_restoricon_doc_store_path({}) == os.path.realpath(d["RESTORICON_DOC_STORE_PATH"])


def test_env_refuses_unknown_and_live_classification(ctx, monkeypatch):
    _mk(ctx)
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_env("nope")
    monkeypatch.setattr(guard, "is_live_path_strict", lambda p: True)
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_env("w1")


# -------------------------------------------------------------------- destroy

def test_destroy_without_yes_deletes_nothing(ctx):
    _mk(ctx)
    r = tw.cmd_destroy("w1", False)
    assert r["deleted"] is False and r["entries"] > 0
    assert (ctx.root / "w1" / "world.json").exists()
    assert tw.main(["destroy", "w1"]) == 2
    assert (ctx.root / "w1").exists()


def test_destroy_success_leaves_root_marker_sibling(ctx):
    _mk(ctx, "a")
    _mk(ctx, "b")
    before = _live_sig(ctx.live)
    r = tw.cmd_destroy("a", True)
    assert r["deleted"] and not (ctx.root / "a").exists()
    assert (ctx.root / "b" / "world.json").exists()
    assert (ctx.root / tw.MARKER).exists() and ctx.root.is_dir()
    assert _live_sig(ctx.live) == before


def test_destroy_last_world_keeps_root_and_marker(ctx):
    _mk(ctx, "a")
    tw.cmd_destroy("a", True)
    assert ctx.root.is_dir() and (ctx.root / tw.MARKER).exists()


@pytest.mark.parametrize(
    "name", ["..", ".", "../victim", "/tmp", "a/../..", "a\n", "production", ""]
)
def test_destroy_name_traversal(ctx, name):
    _mk(ctx)
    vd, vs = _victim(ctx.tmp)
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_destroy(name, True)
    assert vs.read_text() == "keep" and (ctx.root / "w1").exists()


def test_destroy_symlinked_world_dir(ctx):
    _mk(ctx)
    vd, vs = _victim(ctx.tmp)
    (vd / "world.json").write_text("{}")
    (ctx.root / "evil").symlink_to(vd)
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_destroy("evil", True)
    assert vs.exists() and (vd / "world.json").exists()


def test_destroy_symlink_inside_world_unlinked_not_followed(ctx):
    _mk(ctx)
    vd, vs = _victim(ctx.tmp)
    outside_file = ctx.tmp / "outfile"
    outside_file.write_text("keep2")
    os.symlink(vd, ctx.root / "w1" / "state" / "linkdir")
    os.symlink(outside_file, ctx.root / "w1" / "state" / "linkfile")
    os.symlink(ctx.home / ".codeyOS", ctx.root / "w1" / "linklive")
    tw.cmd_destroy("w1", True)
    assert not (ctx.root / "w1").exists()
    assert vs.read_text() == "keep" and outside_file.read_text() == "keep2"
    assert ctx.live.read_bytes() == b"FAKE-LIVE-DB"


@pytest.mark.parametrize("mode", ["missing", "symlink", "garbage", "name", "root", "creator", "schema"])
def test_destroy_bad_manifest(ctx, mode):
    _mk(ctx)
    vd, vs = _victim(ctx.tmp)
    mp = ctx.root / "w1" / "world.json"
    man = json.loads(mp.read_text())
    if mode == "missing":
        mp.unlink()
    elif mode == "symlink":
        real = vd / "m.json"
        real.write_text(json.dumps(man))
        mp.unlink()
        mp.symlink_to(real)
    elif mode == "garbage":
        mp.write_text("{{{")
    else:
        key = {"name": "name", "root": "root", "creator": "created_by", "schema": "schema"}[mode]
        man[key] = "other" if mode != "schema" else 2
        mp.write_text(json.dumps(man))
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_destroy("w1", True)
    assert (ctx.root / "w1").exists() and vs.exists()


def test_destroy_dir_that_is_not_a_world(ctx):
    _mk(ctx)
    (ctx.root / "plain").mkdir()
    (ctx.root / "plain" / "f").write_text("x")
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_destroy("plain", True)
    assert (ctx.root / "plain" / "f").exists()


def test_destroy_hostile_root_without_marker(ctx, monkeypatch):
    evil = ctx.tmp / "ordinary"
    (evil / "evil").mkdir(parents=True)
    os.chmod(evil, 0o700)
    (evil / "evil" / "world.json").write_text(
        json.dumps({"schema": 1, "name": "evil", "created_by": "tools.world",
                    "root": str(evil), "port": 18800})
    )
    monkeypatch.setenv("CODEY_WORLDS_ROOT", str(evil))
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_destroy("evil", True)
    assert (evil / "evil" / "world.json").exists()


@pytest.mark.parametrize("target", ["live_dir", "home", "slash"])
def test_destroy_hostile_roots_refused(ctx, monkeypatch, target):
    path = {"live_dir": str(ctx.live.parent), "home": str(ctx.home), "slash": "/"}[target]
    monkeypatch.setenv("CODEY_WORLDS_ROOT", path)
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_destroy("w1", True)
    assert ctx.live.read_bytes() == b"FAKE-LIVE-DB"


def test_destroy_target_overlapping_live_refused(ctx, monkeypatch):
    _mk(ctx)
    monkeypatch.setattr(guard, "live_db_paths", lambda: {str(ctx.root / "w1" / "state" / "restoricon.db")})
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_destroy("w1", True)
    assert (ctx.root / "w1").exists()


def test_destroy_refuses_live_pid_throwaway_child(ctx, monkeypatch):
    _mk(ctx)
    calls = []
    real_kill = os.kill

    def rec(pid, sig):
        calls.append(sig)
        return real_kill(pid, sig)

    monkeypatch.setattr(os, "kill", rec)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        (ctx.root / "w1" / "state" / "x.pid").write_text(str(child.pid))
        with pytest.raises(tw.WorldRefusal, match="in use"):
            tw.cmd_destroy("w1", True)
        assert (ctx.root / "w1").exists()
        assert calls and set(calls) == {0}
    finally:
        child.terminate()  # our own spawned PID only
        child.wait(timeout=10)


def test_destroy_dead_pid_file_allows(ctx):
    _mk(ctx)
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait(timeout=10)
    (ctx.root / "w1" / "state" / "x.pid").write_text(str(child.pid))
    assert tw.cmd_destroy("w1", True)["deleted"]


def test_destroy_refuses_listening_port(ctx):
    r = _mk(ctx)
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", r["port"]))
        s.listen(1)
        with pytest.raises(tw.WorldRefusal, match="in use"):
            tw.cmd_destroy("w1", True)
    finally:
        s.close()
    assert (ctx.root / "w1").exists()


def test_destroy_fifo_refuses_and_deletes_nothing(ctx):
    _mk(ctx)
    os.mkfifo(ctx.root / "w1" / "state" / "pipe")
    with pytest.raises(tw.WorldRefusal, match="special"):
        tw.cmd_destroy("w1", True)
    assert (ctx.root / "w1" / "world.json").exists()
    assert (ctx.root / "w1" / "state" / "restoricon.db").exists()


def test_destroy_deep_nesting_refused(ctx):
    _mk(ctx)
    d = ctx.root / "w1" / "state"
    for _ in range(tw.MAX_DEPTH + 2):
        d = d / "d"
        d.mkdir()
    with pytest.raises(tw.WorldRefusal, match="nesting"):
        tw.cmd_destroy("w1", True)
    assert (ctx.root / "w1" / "world.json").exists()


def test_destroy_nested_regular_tree(ctx):
    _mk(ctx)
    d = ctx.root / "w1" / "state" / "restoricon_documents" / "a" / "b"
    d.mkdir(parents=True)
    (d / "f").write_text("x")
    assert tw.cmd_destroy("w1", True)["deleted"]
    assert not (ctx.root / "w1").exists()


# ------------------------------------------- review round: TOCTOU / binding

def _swap_world_for_plain(ctx, name="w1"):
    """Move the real world aside and put a plain non-world dir with a sentinel in its place."""
    aside = ctx.root / (name + "_aside")
    os.rename(ctx.root / name, aside)
    (ctx.root / name).mkdir()
    sent = ctx.root / name / "sentinel.txt"
    sent.write_text("keep")
    return aside, sent


def test_destroy_swap_at_in_use_point_survives(ctx, monkeypatch):
    _mk(ctx)
    real = tw._in_use
    state = {}

    def hooked(fd, port):
        state["aside"], state["sent"] = _swap_world_for_plain(ctx)
        return real(fd, port)

    monkeypatch.setattr(tw, "_in_use", hooked)
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_destroy("w1", True)
    assert state["sent"].read_text() == "keep"
    assert (state["aside"] / "world.json").exists()  # nothing deleted at all


def test_forged_sibling_manifest_survives(ctx):
    _mk(ctx, "w1")
    r = _mk(ctx, "w2")
    forged = ctx.root / "forged"
    forged.mkdir()
    (forged / "sentinel.txt").write_text("keep")
    man = json.loads((ctx.root / "w1" / "world.json").read_text())
    man["name"] = "forged"
    (forged / "world.json").write_text(json.dumps(man))  # carries w1's dev/ino
    with pytest.raises(tw.WorldRefusal, match="not bound"):
        tw.cmd_destroy("forged", True)
    del man["dev"], man["ino"]
    (forged / "world.json").write_text(json.dumps(man))
    with pytest.raises(tw.WorldRefusal, match="not bound"):
        tw.cmd_destroy("forged", True)
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_env("forged")
    assert (forged / "sentinel.txt").read_text() == "keep"
    assert [x["state"] for x in tw.cmd_list() if x["name"] == "forged"] == ["broken"]


def test_manifest_records_dev_ino(ctx):
    r = _mk(ctx)
    man = json.loads((ctx.root / "w1" / "world.json").read_text())
    st = os.stat(ctx.root / "w1")
    assert (man["dev"], man["ino"]) == (st.st_dev, st.st_ino)


def test_strict_rmtree_rejects_wrong_identity(ctx):
    _mk(ctx)
    st = os.stat(ctx.root / "w1")
    with pytest.raises(tw.WorldRefusal):
        tw._strict_rmtree(str(ctx.root), "w1", (st.st_dev, st.st_ino + 12345))
    assert (ctx.root / "w1" / "world.json").exists()


def test_strict_rmtree_rejects_fd_of_other_dir(ctx):
    """The fd's own identity must match `expected` even when the name binds fine."""
    _mk(ctx, "w1")
    _mk(ctx, "w2")
    st1 = os.stat(ctx.root / "w1")
    other = os.open(ctx.root / "w2", os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(tw.WorldRefusal):
            tw._strict_rmtree(str(ctx.root), "w1", (st1.st_dev, st1.st_ino), fd=other)
    finally:
        os.close(other)
    assert (ctx.root / "w1" / "world.json").exists() and (ctx.root / "w2" / "world.json").exists()


# --------------------------------------------------------------- FIFO hangs

def test_fifo_pid_file_does_not_hang(ctx):
    _mk(ctx)
    os.mkfifo(ctx.root / "w1" / "state" / "x.pid")
    with alarm():
        with pytest.raises(tw.WorldRefusal):  # refused as a special file, not hung
            tw.cmd_destroy("w1", True)
    assert (ctx.root / "w1" / "world.json").exists()


def test_fifo_sibling_manifest_does_not_hang(ctx):
    _mk(ctx)
    (ctx.root / "sib").mkdir()
    os.mkfifo(ctx.root / "sib" / "world.json")
    with alarm():
        tw.allocate_port(str(ctx.root))
        rows = {r["name"]: r["state"] for r in tw.cmd_list()}
        _mk(ctx, "w2")
        with pytest.raises(tw.WorldRefusal):
            tw.cmd_destroy("sib", True)
    assert rows["sib"] == "broken"
    assert (ctx.root / "sib").exists()


def test_fifo_manifest_in_world_does_not_hang(ctx):
    _mk(ctx)
    os.unlink(ctx.root / "w1" / "world.json")
    os.mkfifo(ctx.root / "w1" / "world.json")
    with alarm():
        with pytest.raises(tw.WorldRefusal):
            tw.cmd_destroy("w1", True)


# ----------------------------------------------------------- pid range check

@pytest.mark.parametrize("pidtext", ["0", "-1", "1099511627776", "99999999999999999999"])
def test_pid_out_of_range_never_signalled(ctx, monkeypatch, pidtext):
    _mk(ctx)
    calls = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: calls.append((pid, sig)))
    (ctx.root / "w1" / "state" / "x.pid").write_text(pidtext)
    assert tw.cmd_destroy("w1", True)["deleted"]
    assert all(pid > 0 for pid, _ in calls) and calls == []


def test_pid_overflowerror_from_kill_is_skipped(ctx, monkeypatch):
    _mk(ctx)

    def kill(pid, sig):
        raise OverflowError("too big")

    monkeypatch.setattr(os, "kill", kill)
    (ctx.root / "w1" / "state" / "x.pid").write_text("12345")
    assert tw.cmd_destroy("w1", True)["deleted"]


# ------------------------------------------------------- partial deletion

def test_mid_delete_failure_reports_partial_exit_1(ctx, monkeypatch, capsys):
    _mk(ctx)
    real_walk = tw._walk
    planted = []

    def hooked(dir_fd, dev, depth, delete, rel=""):
        if delete and not planted:
            planted.append(1)
            os.mkfifo(ctx.root / "w1" / "state" / "late")
        return real_walk(dir_fd, dev, depth, delete, rel)

    monkeypatch.setattr(tw, "_walk", hooked)
    assert tw.main(["destroy", "w1", "--yes"]) == 1
    assert "PARTIALLY DELETED" in capsys.readouterr().err


def test_mid_delete_oserror_reports_partial(ctx, monkeypatch):
    _mk(ctx)
    real = os.unlink

    def bad(path, *a, **k):
        if k.get("dir_fd") is not None:
            raise PermissionError("boom")
        return real(path, *a, **k)

    monkeypatch.setattr(os, "unlink", bad)
    with pytest.raises(tw.PartialDelete, match="PARTIALLY DELETED"):
        tw.cmd_destroy("w1", True)


def test_swap_after_delete_pass_final_rmdir_not_redirected(ctx, monkeypatch):
    """An empty plain dir swapped in under the name must not be rmdir'd."""
    _mk(ctx)
    real_walk = tw._walk
    top = []

    def hooked(dir_fd, dev, depth, delete, rel=""):
        n = real_walk(dir_fd, dev, depth, delete, rel)
        if delete and depth == 1 and not top:
            top.append(1)
            os.rename(ctx.root / "w1", ctx.root / "w1_aside")
            (ctx.root / "w1").mkdir()  # empty: a bare rmdir(name) would succeed
        return n

    monkeypatch.setattr(tw, "_walk", hooked)
    with pytest.raises(tw.PartialDelete):
        tw.cmd_destroy("w1", True)
    assert (ctx.root / "w1").is_dir()


# ------------------------------------------------------ _walk mutant killers

def _make_sub(ctx):
    _mk(ctx)
    sub = ctx.root / "w1" / "state" / "restoricon_documents" / "sub"
    sub.mkdir()
    (sub / "f").write_text("x")
    return sub


def test_walk_subdir_identity_swap_refused(ctx, monkeypatch):
    sub = _make_sub(ctx)
    real_open = os.open
    done = []

    def hooked(path, flags, *a, **k):
        if path == "sub" and k.get("dir_fd") is not None and not done:
            done.append(1)
            os.rename(sub, sub.parent / "sub_old")
            sub.mkdir()  # a different real directory, same name
        return real_open(path, flags, *a, **k)

    monkeypatch.setattr(os, "open", hooked)
    with pytest.raises(tw.WorldRefusal, match="changed during the walk"):
        tw.cmd_destroy("w1", True)
    assert (sub.parent / "sub_old" / "f").exists()


def test_walk_subdir_symlink_swap_refused_by_nofollow(ctx, monkeypatch, tmp_path):
    sub = _make_sub(ctx)
    vd, vs = _victim(tmp_path)
    real_open = os.open
    done = []

    def hooked(path, flags, *a, **k):
        if path == "sub" and k.get("dir_fd") is not None and not done:
            done.append(1)
            os.rename(sub, sub.parent / "sub_old")
            sub.symlink_to(vd)
        return real_open(path, flags, *a, **k)

    monkeypatch.setattr(os, "open", hooked)
    with pytest.raises(tw.WorldRefusal, match="cannot open"):
        tw.cmd_destroy("w1", True)
    assert vs.read_text() == "keep"


def test_walk_cross_device_refused(ctx, monkeypatch):
    _make_sub(ctx)
    real_stat = os.stat

    def hooked(path, *a, **k):
        st = real_stat(path, *a, **k)
        if path == "sub" and k.get("dir_fd") is not None and stat.S_ISDIR(st.st_mode):
            lst = list(st)
            lst[2] = st.st_dev + 1
            return os.stat_result(lst)
        return st

    monkeypatch.setattr(os, "stat", hooked)
    with pytest.raises(tw.WorldRefusal, match="different filesystem"):
        tw.cmd_destroy("w1", True)
    monkeypatch.undo()
    assert (ctx.root / "w1" / "world.json").exists()


# ----------------------------------------------- review round 2 additions

def test_known_gap_stat_forged_sibling_manifest_is_deletable(ctx):
    """KNOWN GAP (pinned on purpose): a same-uid writer that stats a sibling dir
    and writes a matching world.json gets it deleted.  The dev/ino binding only
    stops copied/stale manifests; a forger could rm the dir directly anyway
    (NEW-1069).  If a future hardening makes this refuse, flip this test."""
    _mk(ctx, "w1")
    forged = ctx.root / "forged"
    forged.mkdir()
    (forged / "sentinel.txt").write_text("gone")
    st = os.stat(forged)
    man = json.loads((ctx.root / "w1" / "world.json").read_text())
    man.update(name="forged", dev=st.st_dev, ino=st.st_ino)
    (forged / "world.json").write_text(json.dumps(man))
    assert tw.cmd_destroy("forged", True)["deleted"] is True
    assert not forged.exists()
    assert (ctx.root / "w1" / "world.json").exists()


DEEP = '{"a":' + "[" * 60000  # under the 64 KiB cap, recurses the JSON parser


def test_deeply_nested_manifest_is_unreadable_not_crash(ctx):
    _mk(ctx, "w1")
    _mk(ctx, "deep")
    assert len(DEEP) < tw._MAX_JSON
    (ctx.root / "deep" / "world.json").write_text(DEEP)
    rows = {r["name"]: r["state"] for r in tw.cmd_list()}
    assert rows == {"w1": "ok", "deep": "broken"}
    tw.allocate_port(str(ctx.root))
    _mk(ctx, "w2")  # create scans sibling manifests for ports
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_env("deep")
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_destroy("deep", True)
    assert (ctx.root / "deep").exists()
    assert tw.main(["list"]) == 0 and tw.main(["destroy", "deep", "--yes"]) == 2


def test_deeply_nested_marker_refused_cleanly(ctx):
    _mk(ctx)
    (ctx.root / tw.MARKER).write_text(DEEP)
    with pytest.raises(tw.WorldRefusal):
        tw.cmd_list()


def test_open_world_nofollow_swap_refused(ctx, monkeypatch, tmp_path):
    _mk(ctx)
    vd, vs = _victim(tmp_path)
    wd = str(ctx.root / "w1")
    real_open = os.open
    done = []

    def hooked(path, flags, *a, **k):
        if path == wd and k.get("dir_fd") is None and not done:
            done.append(1)
            os.rename(wd, wd + "_aside")
            os.symlink(vd, wd)
        return real_open(path, flags, *a, **k)

    monkeypatch.setattr(os, "open", hooked)
    with pytest.raises(tw.WorldRefusal, match="cannot open"):
        tw.cmd_destroy("w1", True)
    assert vs.read_text() == "keep"
    assert (ctx.root / "w1_aside" / "world.json").exists()


def _nfds():
    return len(os.listdir("/proc/self/fd"))


def test_no_fd_leaks(ctx):
    _mk(ctx, "a")
    _mk(ctx, "b")
    _mk(ctx, "c")
    os.mkfifo(ctx.root / "b" / "state" / "pipe")
    (ctx.root / "plain").mkdir()
    ops = [
        lambda: tw.cmd_list(),
        lambda: tw.cmd_env("a"),
        lambda: tw.cmd_destroy("a", False),
        lambda: tw.cmd_destroy("b", True),      # refusal: special file
        lambda: tw.cmd_destroy("plain", True),  # refusal: not a world
        lambda: tw.cmd_env("plain"),            # refusal
        lambda: tw.cmd_destroy("a", True),      # success
    ]
    for op in ops:
        before = _nfds()
        try:
            op()
        except tw.WorldRefusal:
            pass
        assert _nfds() == before


def test_special_file_message_names_relative_path(ctx):
    _mk(ctx)
    os.mkfifo(ctx.root / "w1" / "state" / "restoricon_documents" / "pipe")
    with pytest.raises(tw.WorldRefusal) as ei:
        tw.cmd_destroy("w1", True)
    msg = str(ei.value)
    assert "state/restoricon_documents/pipe" in msg and "manually" in msg
    assert (ctx.root / "w1" / "world.json").exists()


# ---------------------------------------------------------------------- CLI

def test_cli_exit_codes(ctx, capsys):
    assert tw.main(["create", "w1"]) == 0
    assert tw.main(["create", "w1"]) == 2
    assert tw.main(["create", "../x"]) == 2
    assert tw.main(["list", "--json"]) == 0
    assert tw.main(["env", "w1"]) == 0
    assert tw.main(["destroy", "production", "--yes"]) == 2
    assert tw.main(["destroy", "w1", "--yes"]) == 0
    err = capsys.readouterr().err
    assert "refused:" in err


# ------------------------------------------------------------------- T-PROT

def test_tprot_world_db_protected_only_in_world_session(ctx):
    from core import protected_paths as pp
    r = _mk(ctx)
    db = os.path.join(r["dir"], "state", "restoricon.db")
    state = os.path.join(r["dir"], "state")
    assert pp.credential_read_hit([db], home=str(ctx.home), state_dirs=[Path(state)]) == "credential-file"
    assert pp.credential_read_hit([db], home=str(ctx.home), state_dirs=[ctx.tmp / "other"]) is None


# ------------------------------------------------------------ import hygiene

def test_import_hygiene_subprocess():
    code = (
        "import sys; sys.path.insert(0, %r); import tools.world; "
        "bad = [m for m in sys.modules if m == 'utils.config' or m == 'core' or m.startswith('core.')]; "
        "print(bad); sys.exit(1 if bad else 0)" % REPO
    )
    env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
    r = subprocess.run([sys.executable, "-I", "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
