"""G15e Unit A: DENY-tier guard in core.filesystem.Filesystem's five mutation
entry points (write, restore, make_parent_dirs, patch, append).

Stated cwd precondition: file-tool reachability of every home/state/PATH item
requires the protected path to lie inside the workspace (or CODE_DIR with
self-mod). These tests therefore make a fake HOME that IS the workspace
(`Filesystem(workspace=fake_home)`, `monkeypatch.chdir(fake_home)`). The real
~/.codeyOS, ~ and repo are never touched.
"""

import ast
import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

import core.checkpoint as checkpoint_module
import core.filesystem as filesystem_module
from core.filesystem import Filesystem, FilesystemAccessError


@pytest.fixture
def env(tmp_path, monkeypatch):
    import utils.config as cfg

    home = tmp_path / "home"
    state = home / ".codeyOS"
    code = tmp_path / "code"
    audit = home / "audit" / "ledger.jsonl"
    prefix_bin = tmp_path / "fakeusr" / "bin"
    for d in (home, state, code, audit.parent, prefix_bin):
        d.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEY_STATE_DIR", str(state))
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(audit))
    monkeypatch.delenv("CODEY_CONFIG_PATH", raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join([str(home / "bin"), str(code), str(prefix_bin)]))
    monkeypatch.setattr(cfg, "CODEY_STATE_DIR", state)
    monkeypatch.setattr(cfg, "CODEY_DIR", code)
    monkeypatch.setattr(filesystem_module, "CODE_DIR", code)
    monkeypatch.setattr(checkpoint_module, "CODE_DIR", code)
    monkeypatch.chdir(home)
    monkeypatch.setattr(filesystem_module, "_snapshot", Mock())

    class E:
        pass

    e = E()
    e.home, e.state, e.code, e.audit, e.prefix_bin = home, state, code, audit, prefix_bin
    e.fs = Filesystem(workspace=home)
    return e


DENY_TARGETS = [
    (".bashrc", "home-startup"),
    (".profile", "home-startup"),
    (".ssh/authorized_keys", "home-credential"),
    (".npmrc", "home-credential"),
    (".gitconfig", "home-git"),
    (".config/git/config", "home-git"),
    (".termux/boot/start.sh", "home-termux"),
    (".codeyOS/age.key", "state-dir"),
    (".codeyOS/config.json", "state-dir"),
    (".codeyOS/action_gateway_audit.jsonl", "audit-sink"),
    ("audit/ledger.jsonl", "audit-sink"),
    ("bin/ls", "path-dedicated"),
    (".local/bin/tool", "path-dedicated"),
    ("proj/sub/.git/config", "git-component"),
    ("proj/.GIT/config", "git-component"),
]


def _call(fs, op, target):
    if op == "write":
        return fs.write(target, "NEW")
    if op == "append":
        return fs.append(target, "NEW")
    if op == "patch":
        return fs.patch(target, "OLD", "NEW")
    if op == "restore":
        return fs.restore(target, "NEW")
    if op == "make_parent_dirs":
        return fs.make_parent_dirs(target)
    raise AssertionError(op)


OPS = ["write", "append", "patch", "restore", "make_parent_dirs"]


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("rel,rule", DENY_TARGETS)
def test_deny_tier_refused_with_rule_and_no_side_effect(env, monkeypatch, op, rel, rule):
    target = env.home / rel
    existed_parent = target.parent.exists()
    target_existed = target.exists()
    checkpoint = Mock()
    monkeypatch.setattr(env.fs, "_require_checkpoint", checkpoint)
    snapshot = filesystem_module._snapshot
    with pytest.raises(FilesystemAccessError) as ei:
        _call(env.fs, op, str(target))
    msg = str(ei.value)
    assert (rule in msg) or (rule == "git-component" and "Git metadata directory" in msg), msg
    assert target.exists() == target_existed
    assert target.parent.exists() == existed_parent  # nothing created
    checkpoint.assert_not_called()
    snapshot.assert_not_called()


@pytest.mark.parametrize("op", ["write", "append", "patch", "restore"])
def test_deny_tier_unchanged_bytes_for_existing_target(env, op):
    target = env.home / ".bashrc"
    target.write_text("OLD")
    with pytest.raises(FilesystemAccessError, match="protected path"):
        _call(env.fs, op, str(target))
    assert target.read_text() == "OLD"


def test_relative_path_is_checked_against_workspace_not_cwd(env, monkeypatch, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    with pytest.raises(FilesystemAccessError, match="home-startup"):
        env.fs.write(".bashrc", "x")


@pytest.mark.parametrize(
    "rel",
    ["proj/notes.txt", "CODEY.md", ".codeyignore", ".github/workflows/x.yml", ".gitignore", "proj/.gitignore"],
)
def test_controls_are_writable(env, rel):
    target = env.home / rel
    assert "Written" in env.fs.write(str(target), "ok")
    assert target.read_text() == "ok"
    assert "Appended" in env.fs.append(str(target), "!")


def test_f3_entries_are_not_denied_by_filesystem(env):
    # HIGH tier is classification (tools.file_tools), not a Filesystem denial.
    fs = Filesystem(workspace=env.code, allow_self_modification=True)
    for rel in ("main.py", "codeyOS", "install.sh", "config.json", "lib/a.sh", "ccos/plugins/p/manifest.json"):
        fs.write(str(env.code / rel), "x")
        assert (env.code / rel).read_text() == "x"


def test_allow_self_modification_never_unlocks_deny_tier(env):
    fs = Filesystem(workspace=env.home, allow_self_modification=True)
    with pytest.raises(FilesystemAccessError, match="protected path"):
        fs.write(str(env.home / ".ssh" / "authorized_keys"), "x")
    with pytest.raises(FilesystemAccessError, match="protected path"):
        fs.write(str(env.home / "bin" / "ls"), "x")


def test_alias_spelling_of_workspace_and_reverse(env, tmp_path):
    s = str(env.home)
    assert s.startswith("/data/data/")
    alias_home = "/data/user/0/" + s[len("/data/data/"):]
    # canonical-spelling target with alias-spelling workspace
    # (the alias-spelling workspace is outside the resolved boundary check, so
    # also exercise the reverse: alias target against the canonical workspace)
    with pytest.raises(FilesystemAccessError):
        Filesystem(workspace=Path(alias_home)).write(str(env.home / ".bashrc"), "x")
    with pytest.raises(FilesystemAccessError):
        env.fs.write(alias_home + "/.bashrc", "x")
    assert not (env.home / ".bashrc").exists()


def test_workspace_symlink_redirecting_into_protected_path(env):
    (env.home / ".bashrc").write_text("OLD")
    ws = env.home / "proj"
    ws.mkdir()
    (ws / "innocent").symlink_to(env.home / ".bashrc")
    with pytest.raises(FilesystemAccessError, match="home-startup"):
        env.fs.write(str(ws / "innocent"), "x")
    assert (env.home / ".bashrc").read_text() == "OLD"


def test_symlink_planted_at_protected_path_pointing_to_harmless_file(env):
    harmless = env.home / "proj" / "harmless.txt"
    harmless.parent.mkdir()
    harmless.write_text("OLD")
    (env.home / ".bashrc").symlink_to(harmless)
    with pytest.raises(FilesystemAccessError, match="protected path"):
        env.fs.write(str(env.home / ".bashrc"), "x")
    assert harmless.read_text() == "OLD"


def test_symlinked_dot_git_dir_is_judged_by_its_lexical_name(env):
    # `.git` is a symlink to a directory that has no `.git` component: only
    # the lexical form carries the component, the resolved form is clean.
    target_dir = env.home / "elsewhere"
    target_dir.mkdir()
    proj = env.home / "proj"
    proj.mkdir()
    (proj / ".git").symlink_to(target_dir)
    with pytest.raises(FilesystemAccessError, match="Git metadata directory"):
        env.fs.write(str(proj / ".git" / "config"), "x")
    assert not (target_dir / "config").exists()


def test_git_sibling_repo_via_code_dir_absolute_path(env):
    fs = Filesystem(workspace=env.home, allow_self_modification=True)
    sibling = env.code / "vendor" / "repo" / ".git" / "hooks" / "pre-commit"
    with pytest.raises(FilesystemAccessError, match="Git metadata directory"):
        fs.write(str(sibling), "#!/bin/sh")
    assert not sibling.exists()


def test_workspace_under_a_git_dir_is_not_denied_wholesale(tmp_path, monkeypatch, env):
    ws = tmp_path / ".git" / "ws"
    ws.mkdir(parents=True)
    fs = Filesystem(workspace=ws)
    assert "Written" in fs.write(str(ws / "notes.txt"), "ok")
    with pytest.raises(FilesystemAccessError, match="Git metadata directory"):
        fs.write(str(ws / "sub" / ".git" / "config"), "x")


def test_make_parent_dirs_checks_the_parent_too(env):
    # target itself is not protected, its PARENT is a shadow-named child of the
    # mixed repo-root PATH dir (a plant that mkdir would create).
    fs = Filesystem(workspace=env.code)
    (env.prefix_bin / "ls").write_text("x")
    target = env.code / "ls" / "inner.txt"
    assert "Written" in fs.write(str(target), "ok")  # write alone only checks the target
    import shutil
    shutil.rmtree(env.code / "ls")
    with pytest.raises(FilesystemAccessError, match="path-shadow"):
        fs.make_parent_dirs(str(target))
    assert not (env.code / "ls").exists()


def test_audit_ledger_guarded_and_gateway_can_still_append(env):
    from core.action_gateway import _append_audit

    env.audit.write_text("".join(json.dumps({"n": i}) + "\n" for i in range(9)))
    before = env.audit.read_bytes()
    for op in ("write", "append", "patch"):
        with pytest.raises(FilesystemAccessError, match="audit-sink"):
            _call(env.fs, op, str(env.audit))
    assert env.audit.read_bytes() == before
    _append_audit({"n": 9})
    assert len(env.audit.read_text().splitlines()) == 10


def test_audit_default_path_guarded_when_env_override_unset(env, monkeypatch):
    monkeypatch.delenv("CODEY_ACTION_GATEWAY_AUDIT")
    with pytest.raises(FilesystemAccessError):
        env.fs.write(str(env.state / "action_gateway_audit.jsonl"), "x")
    # the env-override ledger is no longer special once unset
    assert "Written" in env.fs.write(str(env.audit), "x")


def test_operator_owned_daemon_config_path_still_writes(env):
    from core.daemon_config import DaemonConfig

    cfg_path = env.state / "config.json"
    with pytest.raises(FilesystemAccessError):
        env.fs.write(str(cfg_path), "{}")
    dc = DaemonConfig(config_file=cfg_path)
    dc.create_default_config()
    assert cfg_path.exists()
    dc.save()
    assert cfg_path.exists()
    with pytest.raises(FilesystemAccessError):
        env.fs.write(str(cfg_path), "{}")


def test_operator_modules_do_not_import_the_file_tool_layer():
    root = Path(__file__).resolve().parent.parent
    banned = {"core.protected_paths", "core.filesystem", "tools.file_tools", "tools.shell_tools"}
    for rel in (
        "core/daemon_config.py", "core/service_lifecycle.py", "core/service_actions.py",
        "core/setup_dr_key.py", "core/backup_secrets.py",
    ):
        tree = ast.parse((root / rel).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {node.module or ""} | {f"{node.module}.{a.name}" for a in node.names}
            else:
                continue
            assert not (names & banned), (rel, names & banned)


def test_f3_symlink_to_active_config_stays_denied_with_allow_self_mod(env, monkeypatch):
    cfg = env.home / "mycfg.json"
    cfg.write_text("ORIG")
    monkeypatch.setenv("CODEY_CONFIG_PATH", str(cfg))
    (env.code / "lib").mkdir()
    link = env.code / "lib" / "innocent.sh"
    link.symlink_to(cfg)
    fs = Filesystem(workspace=env.home, allow_self_modification=True)
    for op in ("write", "append", "patch", "restore"):
        with pytest.raises(FilesystemAccessError, match="config-active"):
            _call(fs, op, str(link))
    assert cfg.read_text() == "ORIG"


def test_f3_symlink_to_exec_in_repo_root_stays_denied_with_allow_self_mod(env):
    runme = env.code / "runme"
    runme.write_text("ORIG")
    runme.chmod(0o700)
    (env.code / "main.py").symlink_to(runme)
    fs = Filesystem(workspace=env.home, allow_self_modification=True)
    with pytest.raises(FilesystemAccessError, match="path-shadow"):
        fs.write(str(env.code / "main.py"), "PWNED")
    assert runme.read_text() == "ORIG"


def test_codey_config_path_nondefault_file_refused(env, monkeypatch):
    cfg = env.home / "elsewhere" / "my_config.json"
    cfg.parent.mkdir()
    cfg.write_text("ORIG")
    monkeypatch.setenv("CODEY_CONFIG_PATH", str(cfg))
    with pytest.raises(FilesystemAccessError, match="config-active"):
        env.fs.write(str(cfg), "x")
    assert cfg.read_text() == "ORIG"
