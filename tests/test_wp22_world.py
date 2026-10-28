"""WP2.2 S1 tests for restoricon_core.world.

All fixtures live under tmp_path; ``live_db_paths`` is monkeypatched to a tmp
"live" file.  The real ~/.codeyOS/restoricon.db is never opened (the NEW-455
equivalence test only computes path strings).
"""

import json
import os
import pwd
from pathlib import Path

import pytest

from restoricon_core import world


@pytest.fixture
def fake_live(tmp_path, monkeypatch):
    live = tmp_path / "home" / ".codeyOS" / "restoricon.db"
    live.parent.mkdir(parents=True)
    live.write_bytes(b"not a real db")
    monkeypatch.setattr(world, "live_db_paths", lambda: {str(live)})
    return live


def test_exact_live_path_is_live(fake_live):
    assert world.is_live_path(fake_live)
    assert world.is_live_path(str(fake_live))


def test_other_path_not_live(fake_live, tmp_path):
    other = tmp_path / "world" / "restoricon.db"
    other.parent.mkdir()
    other.write_bytes(b"x")
    assert not world.is_live_path(other)


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_sidecar_suffixes_are_live(fake_live, suffix):
    assert world.is_live_path(str(fake_live) + suffix)


def test_symlink_to_live_is_live(fake_live, tmp_path):
    link = tmp_path / "innocent.db"
    link.symlink_to(fake_live)
    assert world.is_live_path(link)


def test_symlink_to_live_wal_is_live(fake_live, tmp_path):
    link = tmp_path / "innocent.db-wal"
    link.symlink_to(str(fake_live) + "-wal")  # dangling is fine
    assert world.is_live_path(link)


@pytest.mark.skipif(not hasattr(os, "link"), reason="os.link absent on this python")
def test_hardlink_to_live_is_live(fake_live, tmp_path):
    hl = tmp_path / "hard.db"
    os.link(fake_live, hl)
    assert world.is_live_path(hl)


def test_samefile_branch_coverage_only(fake_live, tmp_path, monkeypatch):
    """Branch coverage ONLY (samefile is stubbed): proves the branch is reached,
    not that real inode aliasing is detected; the real hardlink test is skipped
    where os.link is absent."""
    alias = tmp_path / "alias.db"
    alias.write_bytes(b"y")
    monkeypatch.setattr(
        world.os.path, "samefile", lambda a, b: os.fspath(b) == str(fake_live)
    )
    assert world.is_live_path(alias)


def test_nonexistent_path_under_live_dir_not_live(fake_live):
    assert not world.is_live_path(fake_live.parent / "other.db")


def test_memory_passes(fake_live):
    assert not world.is_live_path(":memory:")
    world.assert_world_allows(":memory:")


def test_home_monkeypatch_does_not_rebase_live(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    pw_home = pwd.getpwuid(os.getuid()).pw_dir
    expected = os.path.join(pw_home, ".codeyOS", "restoricon.db")
    assert expected in world.live_db_paths()
    assert os.path.join(str(tmp_path), ".codeyOS", "restoricon.db") not in (
        world.live_db_paths()
    )


def test_config_json_declared_path_included(tmp_path, monkeypatch):
    home = tmp_path / "pwhome"
    (home / ".codeyOS").mkdir(parents=True)
    declared = tmp_path / "elsewhere" / "prod.db"
    (home / ".codeyOS" / "config.json").write_text(
        json.dumps({"restoricon": {"db_path": str(declared)}})
    )
    monkeypatch.setattr(world, "_passwd_home", lambda: str(home))
    paths = world.live_db_paths()
    assert str(home / ".codeyOS" / "restoricon.db") in paths
    assert str(declared) in paths
    assert world.is_live_path(declared)


def test_config_json_tilde_uses_passwd_home(tmp_path, monkeypatch):
    home = tmp_path / "pwhome"
    (home / ".codeyOS").mkdir(parents=True)
    (home / ".codeyOS" / "config.json").write_text(
        json.dumps({"restoricon": {"db_path": "~/x/prod.db"}})
    )
    monkeypatch.setenv("HOME", str(tmp_path / "other"))
    monkeypatch.setattr(world, "_passwd_home", lambda: str(home))
    assert str(home / "x" / "prod.db") in world.live_db_paths()


def _home_with_config(tmp_path, monkeypatch, content):
    home = tmp_path / "pwhome"
    (home / ".codeyOS").mkdir(parents=True)
    if content is not None:
        (home / ".codeyOS" / "config.json").write_text(content)
    monkeypatch.setattr(world, "_passwd_home", lambda: str(home))
    return home


def test_config_json_absent_has_default_only(tmp_path, monkeypatch):
    home = _home_with_config(tmp_path, monkeypatch, None)
    assert world.live_db_paths() == {str(home / ".codeyOS" / "restoricon.db")}


@pytest.mark.parametrize(
    "content", ['{"restoricon": {"db_path": null}}', '{"restoricon": {"db_path": ""}}',
                '{"restoricon": null}', "{}"]
)
def test_config_json_unset_db_path_has_default_only(tmp_path, monkeypatch, content):
    home = _home_with_config(tmp_path, monkeypatch, content)
    assert world.live_db_paths() == {str(home / ".codeyOS" / "restoricon.db")}


@pytest.mark.parametrize(
    "content", ["{not json", '{"restoricon":{"db_path":"/a/b.db"}} trailing', "[]",
                '{"restoricon": 3}', '{"restoricon": {"db_path": 5}}', "",
                '{"restoricon": {"db_path": "~nosuchuser_zz9/x.db"}}']
)
def test_config_json_garbage_fails_closed(tmp_path, monkeypatch, content):
    _home_with_config(tmp_path, monkeypatch, content)
    with pytest.raises(world.WorldConfigError):
        world.live_db_paths()
    assert world.is_live_path(tmp_path / "w.db") is True


def test_config_json_oversize_fails_closed(tmp_path, monkeypatch):
    _home_with_config(tmp_path, monkeypatch, " " * (world._MAX_CONFIG_BYTES + 10))
    with pytest.raises(world.WorldConfigError):
        world.live_db_paths()


def test_config_json_unreadable_fails_closed(tmp_path, monkeypatch):
    home = _home_with_config(tmp_path, monkeypatch, None)
    (home / ".codeyOS" / "config.json").mkdir()  # a directory, not a file
    with pytest.raises(world.WorldConfigError):
        world.live_db_paths()


def test_config_relative_path_cwd_and_codeyos_both_live(tmp_path, monkeypatch):
    home = _home_with_config(
        tmp_path, monkeypatch, '{"restoricon": {"db_path": "prod.db"}}'
    )
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    assert world.is_live_path(cwd / "prod.db")
    assert world.is_live_path(home / ".codeyOS" / "prod.db")


def test_config_tilde_alone_and_home_variants(tmp_path, monkeypatch):
    home = _home_with_config(
        tmp_path, monkeypatch, '{"restoricon": {"db_path": "~"}}'
    )
    env_home = tmp_path / "envhome"
    monkeypatch.setenv("HOME", str(env_home))
    paths = world.live_db_paths()
    assert str(env_home) in paths and str(home) in paths


def test_config_tilde_user_resolved_or_closed(tmp_path, monkeypatch):
    _home_with_config(
        tmp_path, monkeypatch, '{"restoricon": {"db_path": "~someuser/prod.db"}}'
    )
    monkeypatch.setattr(
        world.os.path, "expanduser",
        lambda p: "/home/someuser/prod.db" if p.startswith("~someuser") else p,
    )
    assert world.is_live_path("/home/someuser/prod.db")


@pytest.mark.parametrize(
    "form", ["file:{p}", "file:{p}?mode=ro", "file://{p}", "file://localhost{p}?x=1",
             "FILE:{p}#frag", "file:{p}-wal?mode=rw"]
)
def test_file_uri_forms_of_live_are_live(fake_live, form):
    assert world.is_live_path(form.format(p=fake_live))


def test_file_uri_percent_encoded_is_live(fake_live):
    enc = str(fake_live).replace("restoricon", "restorico%6E")
    assert world.is_live_path("file:" + enc)


def test_file_uri_non_live_and_memory(fake_live, tmp_path):
    assert not world.is_live_path(f"file:{tmp_path}/w.db?mode=ro")
    assert not world.is_live_path("file::memory:")
    assert not world.is_live_path("file::memory:?cache=shared")


@pytest.mark.parametrize("bad", ["file:", "file://evilhost/x.db", "file:?mode=ro"])
def test_file_uri_unparseable_fails_closed(fake_live, bad):
    assert world.is_live_path(bad) is True


def test_stacked_suffixes_are_live(fake_live):
    assert world.is_live_path(str(fake_live) + "-wal-journal")
    assert world.is_live_path(str(fake_live) + "-shm-wal")


def test_passwd_failure_raises_config_error(monkeypatch):
    def boom(_uid):
        raise KeyError("no such uid")

    monkeypatch.setattr(world.pwd, "getpwuid", boom)
    with pytest.raises(world.WorldConfigError):
        world.live_db_paths()


def test_resolution_error_fails_closed(monkeypatch, tmp_path):
    def boom():
        raise world.WorldConfigError("cannot tell")

    monkeypatch.setattr(world, "live_db_paths", boom)
    assert world.is_live_path(tmp_path / "anything.db") is True
    with pytest.raises(world.LiveStoreRefused):
        world.assert_world_allows(tmp_path / "anything.db")


def test_realpath_error_fails_closed(fake_live, tmp_path, monkeypatch):
    def boom(_p):
        raise OSError("loop")

    monkeypatch.setattr(world.os.path, "realpath", boom)
    assert world.is_live_path(tmp_path / "x.db") is True


def test_empty_and_bad_type_fail_closed(fake_live):
    assert world.is_live_path("") is True
    assert world.is_live_path(None) is True


def test_resolve_db_path_explicit_beats_env(monkeypatch):
    monkeypatch.setenv("RESTORICON_DB_PATH", "/env/db")
    assert world.resolve_db_path("/explicit/db") == "/explicit/db"


def test_resolve_db_path_env(monkeypatch):
    monkeypatch.setenv("RESTORICON_DB_PATH", "/env/db")
    assert world.resolve_db_path() == "/env/db"


@pytest.mark.parametrize("val", [None, ""])
def test_resolve_db_path_no_default(monkeypatch, val):
    if val is None:
        monkeypatch.delenv("RESTORICON_DB_PATH", raising=False)
    else:
        monkeypatch.setenv("RESTORICON_DB_PATH", val)
    with pytest.raises(world.WorldConfigError, match="RESTORICON_DB_PATH"):
        world.resolve_db_path()


def test_assert_refuses_live_without_production(fake_live):
    with pytest.raises(world.LiveStoreRefused):
        world.assert_world_allows(fake_live)
    with pytest.raises(world.LiveStoreRefused):
        world.assert_world_allows(str(fake_live) + "-wal")


def test_assert_production_allows_and_audits(fake_live, capsys):
    world.assert_world_allows(fake_live, production=True)
    assert "PRODUCTION" in capsys.readouterr().err


def test_assert_allows_non_live_silently(fake_live, tmp_path, capsys):
    world.assert_world_allows(tmp_path / "w.db")
    assert capsys.readouterr().err == ""


def test_exceptions_are_distinct_types():
    assert not issubclass(world.LiveStoreRefused, world.WorldConfigError)
    assert not issubclass(world.WorldConfigError, world.LiveStoreRefused)


def test_world_module_does_not_import_config_or_core():
    import subprocess
    import sys

    code = (
        "import sys, restoricon_core.world;"
        "bad=[m for m in sys.modules if m=='utils.config' or m=='core' "
        "or m.startswith('core.')];"
        "print(bad); sys.exit(1 if bad else 0)"
    )
    root = Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, "-c", code], cwd=root,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_live_default_equals_api_config_default(monkeypatch):
    """NEW-455 equivalence (moved from S0): shipped fallback == live path."""
    import utils.config as uc

    pw_home = pwd.getpwuid(os.getuid()).pw_dir
    monkeypatch.delenv("RESTORICON_DB_PATH", raising=False)
    monkeypatch.setenv("CODEY_STATE_DIR", os.path.join(pw_home, ".codeyOS"))
    monkeypatch.setattr(uc, "CODEY_STATE_DIR", Path(pw_home) / ".codeyOS")
    api_db = uc.get_restoricon_api_config({})["db_path"]
    default_live = os.path.realpath(
        os.path.join(pw_home, ".codeyOS", "restoricon.db")
    )
    assert api_db == default_live
    assert any(os.path.realpath(p) == api_db for p in world.live_db_paths())


def test_assert_empty_refused_even_in_production(fake_live, capsys):
    for bad in ("", None):
        with pytest.raises(world.LiveStoreRefused):
            world.assert_world_allows(bad, production=True)
    assert "PRODUCTION" not in capsys.readouterr().err


def test_resolve_db_path_rejects_bytes(monkeypatch):
    monkeypatch.setenv("RESTORICON_DB_PATH", "/env/db")
    with pytest.raises(world.WorldConfigError):
        world.resolve_db_path(b"/x/y.db")
