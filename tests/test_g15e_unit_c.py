"""G15e Unit C: Ish-accepted protected-set rows (bench/**, D-7, C-1..C-3) and the
read side (Q7): Filesystem.read credential denial and patch_file's
validate-before-read / snapshot-after-protection ordering.

Stated cwd precondition: file-tool reachability of every home item requires the
protected path to lie inside the workspace (or CODE_DIR with self-mod). These
tests therefore make a fake HOME that IS the workspace
(`Filesystem(workspace=fake_home)`, `monkeypatch.chdir(fake_home)`). Recording
fakes / disposable dirs only; the real ~/.codeyOS, ~ and repo are never
touched, no process is spawned, no model is loaded.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import core.checkpoint as checkpoint_module
import core.filesystem as filesystem_module
import core.protected_paths as pp
from core.action_gateway import reset_action_gateway
from core.filesystem import Filesystem, FilesystemAccessError
from tools import file_tools, patch_tools, shell_tools
from tools.file_tools import ACT, HIGH_IMPACT, classify_write_action
from utils.config import AGENT_CONFIG


@pytest.fixture
def env(tmp_path, monkeypatch):
    import utils.config as cfg

    home = tmp_path / "home"
    state = home / ".codeyOS"
    code = tmp_path / "code"
    outside = tmp_path / "outside"
    audit = tmp_path / "audit" / "ledger.jsonl"
    for d in (home, state, code, outside, audit.parent):
        d.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEY_STATE_DIR", str(state))
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(audit))
    monkeypatch.delenv("CODEY_CONFIG_PATH", raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join([str(home / "bin"), str(code)]))
    monkeypatch.setattr(cfg, "CODEY_STATE_DIR", state)
    monkeypatch.setattr(cfg, "WORKSPACE_ROOT", home)
    monkeypatch.setattr(cfg, "CODEY_DIR", code)
    monkeypatch.setattr(filesystem_module, "CODE_DIR", code)
    monkeypatch.setattr(checkpoint_module, "CODE_DIR", code)
    monkeypatch.chdir(home)
    snap = Mock()
    monkeypatch.setattr(filesystem_module, "_snapshot", snap)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_write", False)
    monkeypatch.setitem(AGENT_CONFIG, "allow_self_modification", False)
    reset_action_gateway()
    fs = Filesystem(workspace=home)
    monkeypatch.setattr(filesystem_module, "get_filesystem", lambda *a, **k: fs)
    # tools.file_tools caches its own instance; pin it to this workspace.
    monkeypatch.setattr(file_tools, "_fs", fs)
    monkeypatch.setattr(file_tools, "_fs_allow_self_mod", False)
    yield SimpleNamespace(home=home, state=state, code=code, outside=outside,
                          audit=audit, fs=fs, snap=snap)
    reset_action_gateway()


# --------------------------------------------------------------------------
# C1: bench-evaluator and D-7 classification (every suffix, file tools)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rel", [
    "bench/suite.lock", "bench/scorecard_manual.json", "bench/tasks/t01/task.yaml",
    "bench/tasks/t01/hidden/test_x.py", "ccos/core/anything.md", "ccos/core/plugin_manager.py",
    "restoricon_core/authority.py", "restoricon_core/authority_rules.py",
    ".claude/settings.json", ".qwen/settings.json",
])
def test_classify_high_for_unit_c_repo_rows(env, rel):
    assert classify_write_action(str(env.code / rel), workspace=env.home) == HIGH_IMPACT


@pytest.mark.parametrize("rel", [
    "benchmark/x.json", "bench.json", "x/bench/a.json", "ccos/data/x.json", "restoricon_core/routes.py",
    "restoricon_core/authority/x.py", "telemetry/store.py", "pipeline/run.py",
    "codey_estimator/__init__.py",
])
def test_classify_act_for_neighbours_and_queued_d7_files(env, rel):
    assert classify_write_action(str(env.code / rel), workspace=env.home) == ACT


def test_unit_c_repo_rows_are_not_denied_by_filesystem_and_selfmod_unlocks(env, monkeypatch):
    """HIGH tier is classification, not a Filesystem refusal: --allow-self-mod
    keeps working (Ish 2026-10-08), unlike the DENY rows."""
    fs = Filesystem(workspace=env.home, allow_self_modification=True)
    monkeypatch.setattr(Filesystem, "_require_checkpoint", lambda self, p: None)
    target = env.code / "bench" / "suite.lock"
    fs.write(str(target), "x")
    assert target.read_text() == "x"


def test_unit_c_repo_rows_blocked_confirmless_without_selfmod_audited(env):
    target = env.code / "bench" / "suite.lock"
    out = file_tools.tool_write_file(str(target), "x")
    assert out.startswith("[BLOCKED]"), out
    assert not target.exists()
    rows = [json.loads(l) for l in env.audit.read_text().splitlines()]
    assert rows and rows[-1]["outcome"] == "refused"


# --------------------------------------------------------------------------
# C1-C3 DENY rows reach Filesystem in every mode (self-mod does not unlock)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rel,rule", [
    (".claude.json", "peer-agent-config"), (".claude/settings.json", "peer-agent-config"),
    (".qwen/settings.json", "peer-agent-config"), (".codex/config.toml", "peer-agent-config"),
    (".gemini/settings.json", "peer-agent-config"), (".config/opencode/c.json", "peer-agent-config"),
    (".config/mimocode/c.json", "peer-agent-config"), (".codey_sessions/p.json", "peer-agent-config"),
    ("venv/lib/python3.14/site-packages/evil.pth", "site-startup"),
    ("venv/lib/python3.14/site-packages/sitecustomize.py", "site-startup"),
    (".local/lib/python3.14/site-packages/usercustomize.py", "site-startup"),
])
@pytest.mark.parametrize("op", ["write", "append"])
def test_deny_rows_refused_even_with_self_mod(env, rel, rule, op):
    target = env.home / rel
    fs = Filesystem(workspace=env.home, allow_self_modification=True)
    with pytest.raises(FilesystemAccessError, match=rule):
        getattr(fs, op)(str(target), "X")
    assert not target.exists()
    # a denied call has no side effect: no parent directory was created either
    assert target.parent == env.home or not target.parent.exists()


@pytest.mark.parametrize("rel", [
    "CODEY.md", ".codeyignore", "notes.txt", "proj/.claude/x.md", "venv/lib/python3.14/site-packages/pkg/mod.py",
    "claude.json",
])
def test_operator_and_ordinary_workspace_paths_stay_writable(env, rel):
    env.fs.write(str(env.home / rel), "ok")
    assert (env.home / rel).read_text() == "ok"


def test_prefix_etc_denied_when_reachable(env, monkeypatch):
    """$PREFIX/etc is outside the workspace normally; with PREFIX pointing at a
    workspace dir the DENY row is what stops the write."""
    monkeypatch.setenv("PREFIX", str(env.home / "usr"))
    with pytest.raises(FilesystemAccessError, match="prefix-etc"):
        env.fs.write(str(env.home / "usr" / "etc" / "profile"), "X")
    env.fs.write(str(env.home / "usr" / "share" / "x"), "ok")


# --------------------------------------------------------------------------
# C3 (Q7b): Filesystem.read credential denial
# --------------------------------------------------------------------------

CRED_FILES = [
    ".ssh/id_rsa", ".ssh/config", ".netrc", ".git-credentials", ".gnupg/pubring.kbx",
    ".aws/credentials", ".npmrc", ".bash_history", ".config/gh/hosts.yml",
    ".codeyOS/age.key", ".codeyOS/config.json", ".codeyOS/gcp_credentials.json",
    ".codeyOS/aigentik_internal_token", ".codeyOS/ccos_crm_read_token",
    ".codeyOS/secrets.age", ".codeyOS/restoricon.db", ".codeyOS/restoricon.db-wal",
]


@pytest.mark.parametrize("rel", CRED_FILES)
def test_read_denies_credential_files(env, rel):
    f = env.home / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("TOPSECRET-FAKE")
    with pytest.raises(FilesystemAccessError, match="credential"):
        env.fs.read(str(f))
    out = file_tools.tool_read_file(rel)
    assert out.startswith("[ERROR] Access denied"), out
    assert "TOPSECRET-FAKE" not in out


def test_read_denies_credential_via_alias_case_and_symlink(env):
    f = env.home / ".ssh" / "id_rsa"
    f.parent.mkdir()
    f.write_text("TOPSECRET-FAKE")
    (env.home / "innocent.txt").symlink_to(f)
    with pytest.raises(FilesystemAccessError, match="credential"):
        env.fs.read("innocent.txt")  # resolved form
    with pytest.raises(FilesystemAccessError, match="credential"):
        env.fs.read(str(env.home / ".SSH" / "ID_RSA"))  # casefold (absent file still denied first)
    s = str(f)
    if s.startswith("/data/data/"):
        with pytest.raises(FilesystemAccessError):
            env.fs.read("/data/user/0/" + s[len("/data/data/"):])


def test_read_allows_ordinary_files_and_neighbours(env):
    for rel in ("notes.txt", ".ssh2/x", ".netrc.example", ".codeyOS/notes.json",
                ".codeyOS/state.db", "proj/.env.example", "proj/server.key", "id_rsa_pub_notes.md"):
        f = env.home / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("ok-" + rel)
        assert env.fs.read(str(f)) == "ok-" + rel, rel


def test_proc_secret_rule_is_pid_scoped():
    assert pp.credential_read_hit(["/proc/self/environ"]) == "proc-secret"
    assert pp.credential_read_hit(["/proc/1234/cmdline"]) == "proc-secret"
    assert pp.credential_read_hit(["/proc/thread-self/mem"]) == "proc-secret"
    assert pp.credential_read_hit(["/proc/cpuinfo"]) is None
    assert pp.credential_read_hit(["/proc/self"]) is None


def test_read_guard_fails_closed_when_check_errors(env, monkeypatch):
    f = env.home / "plain.txt"
    f.write_text("hello")

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(filesystem_module, "credential_read_hit", boom)
    with pytest.raises(FilesystemAccessError, match="credential guard"):
        env.fs.read(str(f))


def test_operator_writers_and_readers_do_not_use_the_guarded_filesystem():
    """Operator/daemon paths read and write the state dir with plain IO and must
    never route through Filesystem (so the credential-read and DENY guards
    cannot break `codeydOS config`, the DR-key tools or the dashboard)."""
    import ast

    root = Path(__file__).resolve().parent.parent
    forbidden = {"core.filesystem", "tools.file_tools", "tools.patch_tools", "core.protected_paths"}
    for rel in ("core/daemon_config.py", "core/service_lifecycle.py", "core/service_actions.py",
                "core/setup_dr_key.py", "core/backup_secrets.py"):
        tree = ast.parse((root / rel).read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            assert not (set(names) & forbidden), (rel, names)


# --------------------------------------------------------------------------
# C3 (Q7a): patch_file validates before reading; snapshot after protection
# --------------------------------------------------------------------------

def test_patch_nonmatching_old_str_does_not_echo_file_outside_workspace(env):
    secret = env.outside / "secret.txt"
    secret.write_text("TOPSECRET-FAKE")
    res = patch_tools.tool_patch_file(str(secret), "NOPE", "x")
    assert res.startswith("[ERROR] Access denied"), res
    assert "TOPSECRET-FAKE" not in res and "Current file content" not in res
    assert secret.read_text() == "TOPSECRET-FAKE"


@pytest.mark.parametrize("rel", [".ssh/id_rsa", ".codeyOS/age.key", ".netrc"])
def test_patch_nonmatching_old_str_does_not_echo_credential_inside_workspace(env, rel):
    f = env.home / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("AGE-SECRET-KEY-FAKE")
    res = patch_tools.tool_patch_file(rel, "NOPE", "x")
    assert res.startswith("[ERROR] Access denied"), res
    assert "AGE-SECRET-KEY-FAKE" not in res
    assert f.read_text() == "AGE-SECRET-KEY-FAKE"


def test_patch_missing_and_outside_give_same_refusal_class(env):
    """No existence oracle: a missing file outside the workspace is refused the
    same way as an existing one."""
    a = patch_tools.tool_patch_file(str(env.outside / "missing.txt"), "a", "b")
    (env.outside / "present.txt").write_text("z")
    b = patch_tools.tool_patch_file(str(env.outside / "present.txt"), "a", "b")
    assert a.startswith("[ERROR] Access denied") and b.startswith("[ERROR] Access denied")


def test_patch_ordinary_workspace_file_still_works_and_failed_patch_still_echoes(env):
    f = env.home / "notes.txt"
    f.write_text("alpha beta\n")
    miss = patch_tools.tool_patch_file("notes.txt", "gamma", "x")
    assert miss.startswith("[PATCH_FAILED]") and "alpha beta" in miss
    ok = patch_tools.tool_patch_file("notes.txt", "alpha", "ALPHA")
    assert ok.startswith("Patched"), ok
    assert f.read_text() == "ALPHA beta\n"
    # Exactly one snapshot (Filesystem.write's); patch_tools no longer takes its own.
    # Note: this fixture no longer mocks patch_tools.snapshot, so it cannot see a
    # reintroduced duplicate; tests/test_wp24_patch_undo.py guards that.
    assert env.snap.call_count == 1


def test_patch_nul_in_path_refused_cleanly(env):
    res = patch_tools.tool_patch_file("a\x00b", "x", "y")
    assert res.startswith("[ERROR]"), res


@pytest.mark.parametrize("rel", [".bashrc", ".claude/settings.json", ".gitconfig",
                                 "proj/.git/config", ".codeyOS/state.db"])
def test_patch_deny_target_is_not_snapshotted_and_is_audited(env, rel):
    f = env.home / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("OLD line\n")
    env.snap.reset_mock()
    res = patch_tools.tool_patch_file(rel, "OLD", "NEW")
    assert res.startswith("[BLOCKED]") or res.startswith("[ERROR]"), res
    assert f.read_text() == "OLD line\n"
    env.snap.assert_not_called()
    rows = [json.loads(l) for l in env.audit.read_text().splitlines()]
    assert rows and rows[-1]["action"] == "patch_tools.tool_patch_file"


def test_patch_snapshot_happens_after_protection_check(env, monkeypatch):
    f = env.home / "notes.txt"
    f.write_text("OLD\n")
    order = []
    real = Filesystem._validate_for_mutation

    def spy(self, raw):
        order.append("check")
        return real(self, raw)

    monkeypatch.setattr(Filesystem, "_validate_for_mutation", spy)
    env.snap.side_effect = lambda *a, **k: order.append("snapshot")
    patch_tools.tool_patch_file("notes.txt", "OLD", "NEW")
    assert order.index("check") < order.index("snapshot")


# --------------------------------------------------------------------------
# Shell scan sees the new rows (Unit B surface, data-only extension)
# --------------------------------------------------------------------------

@pytest.fixture
def world(env, monkeypatch):
    monkeypatch.setattr(shell_tools, "CODE_DIR", env.code)
    return env


def _scan(w, cmd):
    ctx = pp.build_context(
        code_dir=w.code, workspace_root=w.home, home=w.home, state_dir=w.state,
        audit=w.audit, config_paths=[w.state / "config.json"],
        path_env=os.pathsep.join([str(w.home / "bin"), str(w.code)]),
        listdir=lambda p: [], is_exec=lambda p: False,
    )
    return shell_tools._shell_command_targets_protected_path(
        cmd, cwd=w.home, home=w.home, ctx=ctx)


@pytest.mark.parametrize("base", ["cp x", "mv x", "touch", "mkdir", "rm", "ln -s x", "chmod +x"])
@pytest.mark.parametrize("rel,rule", [
    ("code:bench/suite.lock", "bench-evaluator"), ("code:ccos/core/plugin_manager.py", "d7-authority"),
    ("code:restoricon_core/authority.py", "d7-authority"), ("code:.claude/settings.json", "peer-agent-repo"),
    ("home:.claude.json", "peer-agent-config"), ("home:.codey_sessions/p.json", "peer-agent-config"),
    ("home:.config/opencode/c.json", "peer-agent-config"),
    ("home:v/lib/site-packages/a.pth", "site-startup"),
])
def test_shell_scan_flags_mutators_on_unit_c_rows(world, base, rel, rule):
    where, _, r = rel.partition(":")
    root = world.code if where == "code" else world.home
    assert _scan(world, f"{base} {root / r}") == rule


def test_shell_scan_runner_exempt_and_reads_for_unit_c_rows(world):
    b = world.code / "bench" / "verify.py"
    assert _scan(world, f"python3 {b}") is None  # runner-exempt (script-file ceiling)
    assert _scan(world, f"pytest {world.code / 'ccos' / 'core' / 'tests'}") is None
    assert _scan(world, f"cat {world.code / 'bench' / 'suite.lock'}") is None
    assert _scan(world, f"grep -r x {world.home / '.claude.json'}") is None
    assert _scan(world, f"python3 {world.home / 'v/lib/site-packages/a.pth'}") == "site-startup"


def test_shell_scan_prefix_etc(world):
    assert _scan(world, f"cp x {pp.DEFAULT_PREFIX}/etc/profile") == "prefix-etc"
    assert _scan(world, f"cat {pp.DEFAULT_PREFIX}/etc/profile") is None


def test_read_denies_lexical_credential_name_even_if_symlink_target_is_harmless(env):
    """Both forms are compared: a symlink AT a credential path is judged by its
    own name as well as by its target (mutation: resolved-only comparison)."""
    harmless = env.home / "harmless.txt"
    harmless.write_text("hello")
    (env.home / ".ssh").mkdir()
    (env.home / ".ssh" / "id_rsa").symlink_to(harmless)
    with pytest.raises(FilesystemAccessError, match="credential"):
        env.fs.read(".ssh/id_rsa")


def test_credential_entries_are_compared_in_resolved_form_when_home_is_a_symlink(tmp_path):
    """HOME given through a symlink while the candidate uses the real path must hit (mutation: lexical-only entries)."""
    real = tmp_path / "real_home"
    (real / ".ssh").mkdir(parents=True)
    link = tmp_path / "link_home"
    link.symlink_to(real)
    assert pp.credential_read_hit([str(real / ".ssh" / "id_rsa")], home=link, state_dirs=[]) == "credential-file"
    assert pp.credential_read_hit([str(real / "notes.txt")], home=link, state_dirs=[]) is None
