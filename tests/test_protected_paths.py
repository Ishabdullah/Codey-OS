"""G15e Unit A: pure tests of core.protected_paths (the shared protected-path set).

Everything runs against a disposable tmp_path tree with an explicit fake HOME,
state dir, audit sink, CODE_DIR and PATH. `listdir` / `is_exec` are recording
fakes in the pure rows. Nothing touches the real ~/.codeyOS or the real repo.
"""

import os
from pathlib import Path

import pytest

import core.protected_paths as pp
from core.protected_paths import TIER_DENY, TIER_HIGH


def alias(path) -> str:
    """The /data/user/0 spelling of a /data/data path (device alias)."""
    s = str(path)
    assert s.startswith("/data/data/"), s
    return "/data/user/0/" + s[len("/data/data/"):]


@pytest.fixture
def env(tmp_path, monkeypatch):
    import utils.config as cfg

    home = tmp_path / "home"
    state = tmp_path / "state"
    code = tmp_path / "code"
    audit = tmp_path / "audit" / "ledger.jsonl"
    sysbin = tmp_path / "fakeusr" / "bin"
    for d in (home, state, code, audit.parent, sysbin):
        d.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CODEY_STATE_DIR", str(state))
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(audit))
    monkeypatch.delenv("CODEY_CONFIG_PATH", raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join([str(home / "bin"), str(code), str(sysbin)]))
    monkeypatch.setattr(cfg, "CODEY_STATE_DIR", state)
    monkeypatch.setattr(cfg, "CODEY_DIR", code)

    class E:
        pass

    e = E()
    e.home, e.state, e.code, e.audit, e.sysbin = home, state, code, audit, sysbin
    return e


class Recorder:
    def __init__(self, listings=None, execs=()):
        self.listings = listings or {}
        self.execs = set(execs)
        self.listdir_calls = []
        self.exec_calls = []

    def listdir(self, path):
        self.listdir_calls.append(path)
        if path not in self.listings:
            raise PermissionError(path)
        return list(self.listings[path])

    def is_exec(self, path):
        self.exec_calls.append(path)
        return path in self.execs


def ctx_for(e, rec=None, **kw):
    rec = rec or Recorder()
    kw.setdefault("code_dir", e.code)
    kw.setdefault("workspace_root", e.home)
    kw.setdefault("config_paths", [e.state / "config.json"])
    return pp.build_context(listdir=rec.listdir, is_exec=rec.is_exec, **kw), rec


# --------------------------------------------------------------------------
# canon / fold
# --------------------------------------------------------------------------

def test_canon_folds_alias_both_spellings_and_normalizes():
    assert pp.canon("/data/user/0/com.termux/files/home/x/../y") == "/data/data/com.termux/files/home/y"
    assert pp.canon("/data/data/com.termux/files/home//y/") == "/data/data/com.termux/files/home/y"
    assert pp.canon("/data/user/1/foo") == "/data/user/1/foo"  # only user 0 is a known alias


def test_fold_casefolds_after_canon():
    assert pp.fold("/data/user/0/Com.Termux/.BashRC") == "/data/data/com.termux/.bashrc"


# --------------------------------------------------------------------------
# .git any-component rule
# --------------------------------------------------------------------------

@pytest.mark.parametrize("rel", [
    ".git/config", "a/b/.git/hooks/x", ".GIT/x", "x/.git /y", "x/.git./y", "x/.Git/y",
])
def test_git_component_hits(rel):
    assert pp.has_git_component("/w/" + rel, ("/w",)) is True


@pytest.mark.parametrize("rel", [
    ".github/x", ".gitignore", "foo.git.txt", "a.git/b", "x/gitx/y", ".gitmodules",
])
def test_git_component_non_hits(rel):
    assert pp.has_git_component("/w/" + rel, ("/w",)) is False


def test_git_component_absolute_sibling_repo_outside_bases():
    assert pp.has_git_component("/elsewhere/repo/.git/hooks/pre-commit", ("/w",)) is True


def test_git_component_base_under_a_git_dir_is_not_denied_wholesale():
    # A workspace that itself lives below a directory named .git.
    assert pp.has_git_component("/r/.git/ws/notes.txt", ("/r/.git/ws",)) is False
    assert pp.has_git_component("/r/.git/ws/sub/.git/config", ("/r/.git/ws",)) is True


def test_git_component_uses_longest_ancestor_base_and_ignores_non_ancestors():
    assert pp.has_git_component("/w/proj/x", ("/w/pro", "/w")) is False
    assert pp.has_git_component("/r/.git/ws/x", ("/r/.git/ws", "/other")) is False


# --------------------------------------------------------------------------
# rule table: positive + neighbouring negative control for every row
# --------------------------------------------------------------------------

def rule_rows(e):
    h, s, c = e.home, e.state, e.code
    return [
        # (path, tier, rule)
        (e.audit, TIER_DENY, "audit-sink"),
        (s / "action_gateway_audit.jsonl", TIER_DENY, "audit-sink"),
        (s / "age.key", TIER_DENY, "state-dir"),
        (s / "sub" / "deep.db", TIER_DENY, "state-dir"),
        (h / ".codeyOS" / "config.json", TIER_DENY, "state-dir"),
        (h / ".bashrc", TIER_DENY, "home-startup"),
        (h / ".profile", TIER_DENY, "home-startup"),
        (h / ".config" / "fish" / "config.fish", TIER_DENY, "home-startup"),
        (h / ".ssh" / "authorized_keys", TIER_DENY, "home-credential"),
        (h / ".npmrc", TIER_DENY, "home-credential"),
        (h / ".docker" / "config.json", TIER_DENY, "home-credential"),
        (h / ".gitconfig", TIER_DENY, "home-git"),
        (h / ".config" / "git" / "config", TIER_DENY, "home-git"),
        (h / ".termux" / "boot" / "start.sh", TIER_DENY, "home-termux"),
        (h / ".shortcuts" / "x", TIER_DENY, "home-termux"),
        (h / "bin" / "ls", TIER_DENY, "path-dedicated"),
        (h / ".local" / "bin" / "x", TIER_DENY, "path-dedicated"),
        (h / "google-cloud-sdk" / "bin" / "x", TIER_DENY, "path-dedicated"),
        (e.sysbin / "tool", TIER_DENY, "path-dedicated"),
        (Path("/data/data/com.termux/files/usr/bin/zz"), TIER_DENY, "path-dedicated"),
        (c / "main.py", TIER_HIGH, "f3-launcher"),
        (c / "codey-metrics", TIER_HIGH, "f3-launcher"),
        (c / "codeyOS", TIER_HIGH, "f3-launcher"),
        (c / "install.sh", TIER_HIGH, "f3-script"),
        (c / "tools" / "setup_skills.sh", TIER_HIGH, "f3-script"),
        (c / "lib" / "anything.txt", TIER_HIGH, "f3-script"),
        (c / "config.json", TIER_HIGH, "f3-config"),
        (c / "ccos" / "plugins" / "a" / "manifest.json", TIER_HIGH, "f3-plugin-data"),
        (c / "ccos" / "plugins" / "a" / "x.pyc", TIER_HIGH, "f3-plugin-data"),
    ]


def neighbour_rows(e):
    h, s, c = e.home, e.state, e.code
    return [
        h / ".ssh2" / "x", h / ".bashrc.backup", h / "proj" / "notes.txt",
        h / ".config" / "other", h / ".config" / "gitx" / "a", h / ".termuxx" / "a",
        h / "binx" / "a", h / "bin2",
        s.parent / "state2" / "x", e.audit.parent / "other.jsonl",
        c / "config.json.example", c / "mainx.py", c / "notes.txt",
        c / "ccos" / "plugins" / "a" / "x.py",   # core .py: is_core_file, not f3-plugin-data
        c / "ccos" / "plugins_extra" / "m.json", c / "x" / "lib" / "a",
        c / "core" / "agent.py",                  # core-py-mirror is shell-only
    ]


def test_every_rule_row_positive(env):
    ctx, _ = ctx_for(env, config_paths=[env.state / "config.json"])
    for path, tier, rule in rule_rows(env):
        hit = pp.first_hit([str(path)], ctx)
        assert hit == pp.Hit(tier, rule), (path, hit)


def test_neighbour_controls_are_not_protected(env):
    ctx, _ = ctx_for(env)
    for path in neighbour_rows(env):
        assert pp.first_hit([str(path)], ctx) is None, path


def test_rule_rows_hit_in_alias_and_case_variants(env):
    ctx, _ = ctx_for(env)
    for path, tier, rule in rule_rows(env):
        if not str(path).startswith("/data/data/"):
            continue
        for variant in (alias(path), str(path).upper()):
            hit = pp.first_hit([variant], ctx)
            assert hit is not None and hit.tier == tier, (variant, hit)
            assert hit.rule == rule, (variant, hit)


def test_alias_spelling_of_home_state_and_code_dirs(env):
    ctx, _ = ctx_for(
        env,
        home=alias(env.home),
        state_dir=alias(env.state),
        code_dir=alias(env.code),
        audit=alias(env.audit),
    )
    for path, tier, rule in rule_rows(env):
        if rule == "path-dedicated" and "sysbin" in str(path):
            continue  # derived from PATH env, not from home/state/code
        hit = pp.first_hit([str(path)], ctx)
        assert hit is not None and hit.tier == tier, (path, hit)


def test_resolved_form_catches_symlink_into_protected(env, tmp_path):
    link = env.home / "proj" / "innocent"
    link.parent.mkdir()
    (env.home / ".bashrc").write_text("x")
    link.symlink_to(env.home / ".bashrc")
    ctx, _ = ctx_for(env)
    # lexical alone is clean, resolved alone is protected
    assert pp.first_hit([str(link)], ctx) is None
    assert pp.first_hit([str(link), str(link.resolve())], ctx).rule == "home-startup"


def test_lexical_form_catches_symlink_planted_at_protected_path(env):
    harmless = env.home / "harmless.txt"
    harmless.write_text("x")
    planted = env.home / ".bashrc"
    planted.symlink_to(harmless)
    ctx, _ = ctx_for(env)
    assert pp.first_hit([str(planted)], ctx).rule == "home-startup"
    # entries are stored in both forms, so the symlink's target is protected too
    assert pp.first_hit([str(harmless)], ctx).rule == "home-startup"


# --------------------------------------------------------------------------
# precedence (4.3a)
# --------------------------------------------------------------------------

def test_f3_launcher_stays_high_when_exec_bit_would_make_path_shadow(env):
    launcher = env.code / "codeyOS"
    rec = Recorder(execs={pp.canon(str(launcher))})
    ctx, _ = ctx_for(env, rec)
    assert pp.first_hit([str(launcher)], ctx) == pp.Hit(TIER_HIGH, "f3-launcher")
    # the very same exec-bit rule makes a non-F3 direct child DENY
    other = env.code / "ls"
    rec.execs.add(pp.canon(str(other)))
    assert pp.first_hit([str(other)], ctx) == pp.Hit(TIER_DENY, "path-shadow")


def test_root_config_json_is_high_with_state_config_present_and_absent(env):
    import utils.config as cfg

    root_cfg = env.code / "config.json"
    state_cfg = env.state / "config.json"
    # real get_config_file_path (not injected): state config absent -> falls
    # back to <CODEY_DIR>/config.json, which the F3 row must keep HIGH.
    assert not state_cfg.exists()
    assert cfg.get_config_file_path() == root_cfg
    ctx = pp.build_context(code_dir=env.code, workspace_root=env.home)
    assert any(e.rule == "config-active" and e.value == pp.fold(str(root_cfg)) for e in ctx.entries)
    assert pp.first_hit([str(root_cfg)], ctx) == pp.Hit(TIER_HIGH, "f3-config")
    state_cfg.write_text("{}")
    root_cfg.write_text("{}")
    ctx = pp.build_context(code_dir=env.code, workspace_root=env.home)
    assert pp.first_hit([str(root_cfg)], ctx) == pp.Hit(TIER_HIGH, "f3-config")
    # the state config itself is DENY (state-dir) either way
    assert pp.first_hit([str(state_cfg)], ctx).tier == TIER_DENY


def test_config_active_alone_denies_when_no_f3_row_matches(env, monkeypatch, tmp_path):
    custom = tmp_path / "elsewhere" / "my_config.json"
    ctx, _ = ctx_for(env, config_paths=[custom])
    assert pp.first_hit([str(custom)], ctx) == pp.Hit(TIER_DENY, "config-active")


def test_config_active_env_set_and_unset_via_real_resolution(env, monkeypatch, tmp_path):
    custom = tmp_path / "elsewhere" / "cfg.json"
    custom.parent.mkdir()
    custom.write_text("{}")
    assert pp.first_hit([str(custom)], pp.build_context(code_dir=env.code)) is None
    monkeypatch.setenv("CODEY_CONFIG_PATH", str(custom))
    assert pp.first_hit([str(custom)], pp.build_context(code_dir=env.code)) == pp.Hit(
        TIER_DENY, "config-active"
    )


def test_deny_beats_high(env):
    ctx, _ = ctx_for(env, state_dir=env.code / "lib")  # state dir inside an F3 subtree
    hit = pp.first_hit([str(env.code / "lib" / "age.key")], ctx)
    assert hit == pp.Hit(TIER_DENY, "state-dir")


def test_skip_rules_parameter(env):
    ctx, _ = ctx_for(env)
    p = str(env.home / "proj" / ".git" / "config")
    assert pp.first_hit([p], ctx).rule == "git-component"
    assert pp.first_hit([p], ctx, skip=frozenset({"git-component"})) is None


# --------------------------------------------------------------------------
# call-time reads (audit sink etc.)
# --------------------------------------------------------------------------

def test_audit_sink_env_set_and_unset_and_default_always_guarded(env, monkeypatch):
    other = env.home / "other_ledger.jsonl"
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(other))
    ctx = pp.build_context(code_dir=env.code)
    assert pp.first_hit([str(other)], ctx).rule == "audit-sink"
    # the production default under the state dir is guarded even with env set
    assert pp.first_hit([str(env.state / "action_gateway_audit.jsonl")], ctx).tier == TIER_DENY
    monkeypatch.delenv("CODEY_ACTION_GATEWAY_AUDIT")
    ctx = pp.build_context(code_dir=env.code)
    assert pp.first_hit([str(env.state / "action_gateway_audit.jsonl")], ctx).tier == TIER_DENY
    assert pp.first_hit([str(other)], ctx) is None


def test_context_reads_home_state_and_path_at_call_time(env, monkeypatch, tmp_path):
    first = pp.build_context(code_dir=env.code)
    new_home = tmp_path / "home2"
    new_home.mkdir()
    monkeypatch.setenv("HOME", str(new_home))
    second = pp.build_context(code_dir=env.code)
    assert pp.first_hit([str(new_home / ".bashrc")], first) is None
    assert pp.first_hit([str(new_home / ".bashrc")], second).rule == "home-startup"


# --------------------------------------------------------------------------
# PATH directories
# --------------------------------------------------------------------------

def test_dedicated_vs_mixed_path_dirs_and_nonexistent_codey_v4(env):
    custom_bin = env.home / "tools" / "bin"
    mixed = env.home / "somewhere"
    ctx, rec = ctx_for(
        env,
        path_env=os.pathsep.join([str(custom_bin), str(mixed), "relative/dir", "", str(env.sysbin)]),
        rec=None,
    )
    assert pp.first_hit([str(custom_bin / "deep" / "x")], ctx) == pp.Hit(TIER_DENY, "path-dedicated")
    # mixed: ordinary child and nested file are fine, no discovery happened
    assert pp.first_hit([str(mixed / "notes.txt")], ctx) is None
    assert pp.first_hit([str(mixed / "sub" / "ls")], ctx) is None
    # relative / empty PATH entries are ignored
    assert pp.first_hit([str(env.home / "relative" / "dir" / "x")], ctx) is None
    # ~/Codey-v4 does not exist yet is still a mixed dir: an exec child is the plant
    v4 = env.home / "Codey-v4" / "plant"
    assert not v4.parent.exists()
    rec.execs.add(pp.canon(str(v4)))
    assert pp.first_hit([str(v4)], ctx) == pp.Hit(TIER_DENY, "path-shadow")


def test_shadow_names_never_listed_unless_direct_child_of_mixed_dir(env):
    rec = Recorder(listings={str(env.sysbin): ["ls", "cp"]})
    ctx, _ = ctx_for(env, rec)
    assert rec.listdir_calls == [] and rec.exec_calls == []  # build_context does no discovery
    for p in (env.home / "proj" / "x", env.code / "sub" / "ls", env.state.parent / "ls"):
        pp.first_hit([str(p)], ctx)
    assert rec.listdir_calls == []


def test_shadow_names_listed_once_per_context_and_name_collision_denies(env):
    rec = Recorder(listings={str(env.sysbin): ["ls", "Cp"], str(env.home / "bin"): ["tool"]})
    ctx, _ = ctx_for(env, rec)
    assert pp.first_hit([str(env.code / "ls")], ctx) == pp.Hit(TIER_DENY, "path-shadow")
    assert pp.first_hit([str(env.code / "CP")], ctx) == pp.Hit(TIER_DENY, "path-shadow")
    assert pp.first_hit([str(env.code / "tool")], ctx).rule == "path-shadow"
    assert pp.first_hit([str(env.code / "notes.txt")], ctx) is None
    assert pp.first_hit([str(env.code / "build")], ctx) is None
    # each directory listed at most once per Context, unreadable ones swallowed
    assert len(rec.listdir_calls) == len(set(rec.listdir_calls))
    assert str(env.sysbin) in rec.listdir_calls


def test_mixed_dir_own_listing_is_excluded_and_other_mixed_dirs_need_exec_files(env):
    other_mixed = env.home / "othermixed"
    rec = Recorder(
        listings={str(env.code): ["onlyhere"], str(other_mixed): ["adir", "runme"]},
        execs={str(other_mixed / "runme")},
    )
    ctx, _ = ctx_for(env, rec, path_env=os.pathsep.join([str(env.code), str(other_mixed)]))
    assert pp.first_hit([str(env.code / "onlyhere")], ctx) is None  # own names excluded
    assert pp.first_hit([str(env.code / "runme")], ctx).rule == "path-shadow"  # executable elsewhere
    assert pp.first_hit([str(env.code / "adir")], ctx) is None  # a directory is not a command


def test_default_is_exec_requires_regular_file_with_exec_bit(tmp_path):
    f = tmp_path / "f"
    f.write_text("x")
    f.chmod(0o600)
    assert pp._default_is_exec(str(f)) is False
    f.chmod(0o700)
    assert pp._default_is_exec(str(f)) is True
    d = tmp_path / "d"
    d.mkdir()
    assert pp._default_is_exec(str(d)) is False  # directories carry x bits
    assert pp._default_is_exec(str(tmp_path / "missing")) is False


# --------------------------------------------------------------------------
# shell-only row, ancestors, empty Ish-gated data
# --------------------------------------------------------------------------

def test_core_py_mirror_is_shell_only(env):
    ctx, _ = ctx_for(env)
    p = str(env.code / "core" / "agent.py")
    assert pp.first_hit([p], ctx) is None
    assert pp.first_hit([p], ctx, shell=True) == pp.Hit(TIER_HIGH, "core-py-mirror")
    assert pp.first_hit([str(env.code / "core" / "notes.md")], ctx, shell=True) is None


def test_ancestor_hit_rows(env):
    ctx, _ = ctx_for(env)
    for anc in (env.home, env.home / ".config", env.code, env.home.parent, "/"):
        assert pp.ancestor_hit([str(anc)], ctx) is not None, anc
    assert pp.ancestor_hit([str(env.home / "proj")], ctx) is None
    assert pp.ancestor_hit([str(env.home / ".ssh2")], ctx) is None
    # a DENY descendant wins over a HIGH one
    assert pp.ancestor_hit([str(env.code)], ctx).tier in (TIER_HIGH, TIER_DENY)
    assert pp.ancestor_hit([str(env.home / ".config")], ctx).tier == TIER_DENY


# --- Unit C: Ish-accepted data rows (decisions 2026-10-23/24) --------------

def test_unit_c_data_tuples_pinned():
    """Declared flip of the Unit A 'empty tuples' pin. Widening any of these is
    a reviewed edit; the three queued D-7 files must stay OUT."""
    assert pp.BENCH_EVALUATOR_SUBTREES == ("bench",)
    assert pp.D7_HIGH_ENTRIES == ("ccos/core", "restoricon_core/authority*.py")
    for queued in ("telemetry/store.py", "pipeline/run.py", "codey_estimator/__init__.py"):
        assert queued not in pp.D7_HIGH_ENTRIES
    assert not hasattr(pp, "CANDIDATE_SUBTREES")


@pytest.mark.parametrize("rel,rule", [
    ("bench/suite.lock", "bench-evaluator"), ("bench/scorecard_manual.json", "bench-evaluator"),
    ("bench/tasks/t01/hidden/test_x.py", "bench-evaluator"), ("bench", "bench-evaluator"),
    ("ccos/core/plugin_manager.py", "d7-authority"), ("ccos/core/memory/x.md", "d7-authority"),
    ("restoricon_core/authority.py", "d7-authority"),
    ("restoricon_core/authority_policy.py", "d7-authority"),
    (".claude/settings.json", "peer-agent-repo"), (".qwen/settings.json", "peer-agent-repo"),
])
def test_unit_c_repo_rows_are_high(env, rel, rule):
    ctx, _ = ctx_for(env)
    for shell in (False, True):
        assert pp.first_hit([str(env.code / rel)], ctx, shell=shell) == pp.Hit(TIER_HIGH, rule), rel


@pytest.mark.parametrize("rel", [
    "benchmark/x.json", "bench.json", "x/bench/a.json", "ccos/data/x.py", "ccos/tests/t.py",
    "ccos/x.py", "ccos/plugins_extra/x.py", "restoricon_core/other.py", "restoricon_core/authority/x.py",
    "restoricon_core/xauthority.py", "restoricon_core/authority.txt", "telemetry/store.py",
    "pipeline/run.py", "codey_estimator/__init__.py", ".claudex/x", "src/.claude/x",
])
def test_unit_c_repo_neighbours_not_flagged(env, rel):
    ctx, _ = ctx_for(env)
    assert pp.first_hit([str(env.code / rel)], ctx, shell=True) is None, rel


def test_unit_c_bench_and_d7_are_runner_exempt_and_tier_high(env):
    ctx, _ = ctx_for(env)
    by_rule = {e.rule: e for e in ctx.entries if e.rule in ("bench-evaluator", "d7-authority")}
    assert set(by_rule) == {"bench-evaluator", "d7-authority"}
    assert all(e.tier == TIER_HIGH and e.runner_exempt for e in ctx.entries
               if e.rule in by_rule)


@pytest.mark.parametrize("rel", [
    ".claude.json", ".claude.json.backup", ".claude/settings.json", ".claude", ".qwen/settings.json",
    ".codex/config.toml", ".gemini/settings.json", ".config/opencode/x.json",
    ".config/mimocode/x", ".codey_sessions/proj.json", ".CLAUDE/x",
])
def test_unit_c3_peer_agent_home_is_deny(env, rel):
    ctx, _ = ctx_for(env)
    assert pp.first_hit([str(env.home / rel)], ctx) == pp.Hit(TIER_DENY, "peer-agent-config"), rel


@pytest.mark.parametrize("rel", [
    "claude.json", "notes/.claude/x", ".config/other/x", ".config/opencodex/x", "CODEY.md",
    ".codeyignore", "proj/.claude/x", ".qwenx/x",
])
def test_unit_c3_home_neighbours_and_operator_files_stay_writable(env, rel):
    ctx, _ = ctx_for(env)
    assert pp.first_hit([str(env.home / rel)], ctx) is None, rel


def test_unit_c1_prefix_etc_default_and_env_prefix(env, monkeypatch):
    alt = env.home.parent / "altprefix"
    monkeypatch.setenv("PREFIX", str(alt))
    ctx, _ = ctx_for(env)
    for root in (pp.DEFAULT_PREFIX, str(alt)):
        assert pp.first_hit([root + "/etc/profile"], ctx) == pp.Hit(TIER_DENY, "prefix-etc")
        assert pp.first_hit([root + "/etc/profile.d/x.sh"], ctx) == pp.Hit(TIER_DENY, "prefix-etc")
        assert pp.first_hit([root + "/etcx/profile"], ctx) is None
        assert pp.first_hit([root + "/share/x"], ctx) is None
    # alias spelling of the default prefix
    assert pp.first_hit([alias(pp.DEFAULT_PREFIX + "/etc/bash.bashrc")], ctx) == pp.Hit(TIER_DENY, "prefix-etc")


@pytest.mark.parametrize("path", [
    "/v/lib/python3.14/site-packages/evil.pth", "/v/site-packages/sitecustomize.py",
    "/v/site-packages/usercustomize.py", "/v/site-packages/SiteCustomize.PY",
    "/v/site-packages/sitecustomize.cpython-314.so", "/v/dist-packages/x.pth",
    "/v/site-packages/sitecustomize/__init__.py",
])
def test_unit_c2_site_startup_files_deny(env, path):
    ctx, _ = ctx_for(env)
    assert pp.first_hit([path], ctx) == pp.Hit(TIER_DENY, "site-startup"), path


@pytest.mark.parametrize("path", [
    "/v/site-packages/requests/x.py", "/v/site-packages/pkg/evil.pth",
    "/v/site-packages/sitecustomizer.py", "/v/lib/evil.pth", "/v/sitecustomize.py",
    "/v/site-packages", "/v/site-packagesx/a.pth",
])
def test_unit_c2_site_startup_neighbours_not_flagged(env, path):
    ctx, _ = ctx_for(env)
    assert pp.first_hit([path], ctx) is None, path


def test_f3_launcher_set_includes_codey_metrics_and_all_listed(env):
    assert {"main.py", "codey", "codeyos", "codeydos", "codey-start", "codey-stop", "codey-metrics"} == set(
        pp.F3_LAUNCHERS
    )


# --------------------------------------------------------------------------
# classifier invariant (P2): classify_shell_command never touches this module
# --------------------------------------------------------------------------

def test_classify_shell_command_is_independent_of_protected_paths(env, monkeypatch):
    from tools import shell_tools

    corpus = [
        "ls", "cat main.py", "cp a b", "rm -rf x", "python3 main.py", "git status",
        "ln -s /usr/bin/git ls", "touch ~/.bashrc", "echo hi > ~/.bashrc", "sed -n p f",
        "grep -r x ~/.ssh", "pytest tests", "mkdir -p ~/.termux/boot", "chmod +x install.sh",
    ]
    before = [shell_tools.classify_shell_command(c) for c in corpus]

    def boom(*a, **k):
        raise AssertionError("classifier consulted core.protected_paths")

    for name in ("first_hit", "ancestor_hit", "build_context", "has_git_component", "shadow_names"):
        monkeypatch.setattr(pp, name, boom)
    monkeypatch.setattr(Path, "resolve", boom)
    monkeypatch.setattr(os, "listdir", boom)
    after = [shell_tools.classify_shell_command(c) for c in corpus]
    assert after == before


def test_shell_tools_reexports_lifted_constants_by_identity():
    from tools import shell_tools as st

    assert st._SYSTEM_BIN_DIRS is pp.SYSTEM_BIN_DIRS
    assert st._CRED_HOME_ENTRIES is pp.CRED_HOME_ENTRIES
    assert st._CRED_STATE_ENTRIES is pp.CRED_STATE_ENTRIES
    assert st._CRED_STATE_PATTERNS is pp.CRED_STATE_PATTERNS
    assert st._CRED_BASENAME_PATTERNS is pp.CRED_BASENAME_PATTERNS
    assert st._CRED_PATH_ALIASES is pp.CRED_PATH_ALIASES
    assert st._cred_canon is pp.canon


# --------------------------------------------------------------------------
# F3 override is PER FORM (reviewer C1): a symlink whose lexical spelling is an
# F3 row and whose resolved spelling is config-active / path-shadow must stay DENY
# --------------------------------------------------------------------------

def test_f3_override_does_not_cross_forms_config_active(env, monkeypatch):
    cfg = env.home / "mycfg.json"
    cfg.write_text("{}")
    monkeypatch.setenv("CODEY_CONFIG_PATH", str(cfg))
    (env.code / "lib").mkdir()
    link = env.code / "lib" / "innocent.sh"
    link.symlink_to(cfg)
    ctx = pp.build_context(code_dir=env.code, workspace_root=env.home)
    assert pp.first_hit([str(link)], ctx) == pp.Hit(TIER_HIGH, "f3-script")  # lexical alone
    assert pp.first_hit([str(link), str(link.resolve())], ctx) == pp.Hit(TIER_DENY, "config-active")


def test_f3_override_does_not_cross_forms_path_shadow(env):
    runme = env.code / "runme"
    runme.write_text("#!/bin/sh\n")
    runme.chmod(0o700)
    link = env.code / "main.py"
    link.symlink_to(runme)
    ctx = pp.build_context(code_dir=env.code, workspace_root=env.home)
    assert pp.first_hit([str(link)], ctx) == pp.Hit(TIER_HIGH, "f3-launcher")
    assert pp.first_hit([str(link), str(link.resolve())], ctx) == pp.Hit(TIER_DENY, "path-shadow")


def test_codey_config_path_nondefault_file_is_denied_not_just_via_default_resolution(env, monkeypatch, tmp_path):
    # Kills "drop the CODEY_CONFIG_PATH entry": the injected-config_paths=None
    # path must contribute BOTH get_config_file_path() and the env value
    # (here the env value is an unresolved ~-free spelling through a symlink dir).
    real = tmp_path / "realdir"
    real.mkdir()
    (tmp_path / "linkdir").symlink_to(real)
    cfg = tmp_path / "linkdir" / "c.json"
    monkeypatch.setenv("CODEY_CONFIG_PATH", str(cfg))
    # make get_config_file_path() NOT return the env path, isolating the env entry
    import utils.config as uc

    monkeypatch.setattr(uc, "get_config_file_path", lambda: env.code / "other_default.json")
    ctx = pp.build_context(code_dir=env.code)
    assert pp.first_hit([str(cfg)], ctx) == pp.Hit(TIER_DENY, "config-active")
