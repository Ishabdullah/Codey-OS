"""WP2.2 S0: the test session must never reach the live Restoricon store.

root conftest.py redirects RESTORICON_DB_PATH to a temp file at collection.
These checks only os.stat() the live ~/.codeyOS/restoricon.db (+ -wal/-shm);
they never open, read, copy or connect to it. They are skip-safe when the
live files do not exist (CI). The live home is taken from the passwd entry,
not $HOME, so a test that monkeypatches HOME cannot rebase "live".
"""
import os
import pwd
from pathlib import Path

import pytest


def _live_db() -> Path:
    return Path(pwd.getpwuid(os.getuid()).pw_dir) / ".codeyOS" / "restoricon.db"


def _stat_sig(path: Path):
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return None
    return (st.st_ino, st.st_size, st.st_mtime_ns)


def _live_family():
    live = _live_db()
    return [Path(str(live) + sfx) for sfx in ("", "-wal", "-shm", "-journal")]


def test_default_db_path_is_not_the_live_store():
    from restoricon_core.database import DEFAULT_DB_PATH

    resolved = Path(DEFAULT_DB_PATH).expanduser().resolve()
    live = _live_db().resolve()
    live_dir = live.parent
    assert resolved != live
    assert live_dir not in resolved.parents, (
        f"DEFAULT_DB_PATH {resolved} is under the live state dir {live_dir}"
    )
    if live.exists():
        assert not os.path.samefile(resolved.parent, live_dir)
        if resolved.exists():
            assert not os.path.samefile(resolved, live)


def test_session_env_redirect_is_not_live():
    env = os.environ.get("RESTORICON_DB_PATH")
    assert env, "root conftest.py must set RESTORICON_DB_PATH"
    resolved = Path(env).expanduser().resolve()
    assert resolved != _live_db().resolve()
    assert _live_db().resolve().parent not in resolved.parents


def test_bare_database_manager_leaves_live_store_untouched():
    family = _live_family()
    if not any(p.exists() for p in family):
        pytest.skip("no live Restoricon store on this machine")
    before = {str(p): _stat_sig(p) for p in family}

    import restoricon_core.database as dbmod

    db = dbmod.DatabaseManager()  # resolves to the redirected temp default
    try:
        assert Path(dbmod.DEFAULT_DB_PATH).expanduser().resolve() != _live_db().resolve()
        assert Path(dbmod.DEFAULT_DB_PATH).exists()
    finally:
        close = getattr(db, "close", None)
        if callable(close):
            close()

    after = {str(p): _stat_sig(p) for p in family}
    assert after == before
