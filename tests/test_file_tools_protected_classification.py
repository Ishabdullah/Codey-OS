"""G15e Unit A: tools.file_tools.classify_write_action over the shared
protected-path set, and the end-to-end file-tool behaviour (gateway ledger).

Stated cwd precondition: file-tool reachability of every home/state/PATH/F3
item requires the protected path to lie inside the workspace (or CODE_DIR with
self-mod). These tests make a fake HOME that IS the workspace and chdir into
it (or, for the cwd != workspace row, away from it). The real ~/.codeyOS, ~
and repo are never touched.
"""

import json
import os
from unittest.mock import Mock

import pytest

import core.checkpoint as checkpoint_module
import core.filesystem as filesystem_module
import core.protected_paths as pp
import tools.file_tools as file_tools
import tools.patch_tools as patch_tools
from core.action_gateway import ACT, HIGH_IMPACT
from core.filesystem import Filesystem
from tools.file_tools import classify_write_action
from utils.config import AGENT_CONFIG


@pytest.fixture
def env(tmp_path, monkeypatch):
    import utils.config as cfg

    home = tmp_path / "home"
    state = home / ".codeyOS"
    code = tmp_path / "code"
    audit = tmp_path / "audit" / "ledger.jsonl"
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
    monkeypatch.setattr(filesystem_module, "_snapshot", Mock())
    monkeypatch.chdir(home)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_write", False)
    monkeypatch.setitem(AGENT_CONFIG, "allow_self_modification", False)

    class E:
        pass

    e = E()
    e.home, e.state, e.code, e.audit = home, state, code, audit
    e.fs = Filesystem(workspace=home)
    monkeypatch.setattr(file_tools, "_get_fs", lambda: e.fs)
    monkeypatch.setattr(filesystem_module, "_filesystem", e.fs)
    e.rows = lambda: [json.loads(x) for x in audit.read_text().splitlines()] if audit.exists() else []
    return e


F3_ROWS = [
    "main.py", "codey", "codeyOS", "codeydOS", "codey-start", "codey-stop", "codey-metrics",
    "install.sh", "setup.sh", "setup_repo.sh", "lib/service_manager.sh", "lib/x.txt",
    "tools/setup_skills.sh", "config.json", "ccos/plugins/a/manifest.json", "ccos/plugins/README.md",
]
DENY_ROWS = [
    ".bashrc", ".ssh/authorized_keys", ".gitconfig", ".config/git/config", ".termux/boot/start.sh",
    ".codeyOS/age.key", ".codeyOS/config.json", "bin/ls", ".local/bin/tool",
]
CONTROL_ROWS = ["proj/notes.txt", "CODEY.md", ".codeyignore", ".gitignore", ".github/x.yml"]


@pytest.mark.parametrize("rel", F3_ROWS)
def test_f3_entries_classify_high(env, rel):
    assert classify_write_action(str(env.code / rel), workspace=env.home) == HIGH_IMPACT


@pytest.mark.parametrize("rel", DENY_ROWS)
def test_deny_entries_classify_high_defense_in_depth(env, rel):
    assert classify_write_action(str(env.home / rel), workspace=env.home) == HIGH_IMPACT
    assert classify_write_action(rel, workspace=env.home) == HIGH_IMPACT  # relative -> workspace


def test_audit_ledger_classifies_high(env):
    assert classify_write_action(str(env.audit), workspace=env.home) == HIGH_IMPACT


@pytest.mark.parametrize("rel", CONTROL_ROWS)
def test_controls_classify_act(env, rel):
    assert classify_write_action(str(env.home / rel), workspace=env.home) == ACT


def test_git_component_stays_act_so_filesystem_keeps_its_pinned_failed_outcome(env):
    assert classify_write_action(str(env.home / "p" / ".git" / "config"), workspace=env.home) == ACT


def test_f3_launcher_planted_as_symlink_is_judged_by_its_lexical_name(env):
    # lexical form is a launcher, resolved form is an ordinary file
    harmless = env.home / "proj" / "harmless.txt"
    harmless.parent.mkdir()
    harmless.write_text("x")
    (env.code / "main.py").symlink_to(harmless)
    assert classify_write_action(str(env.code / "main.py"), workspace=env.home) == HIGH_IMPACT


def test_malformed_path_stays_act(env):
    assert classify_write_action(str(env.home / "a\0b"), workspace=env.home) == ACT


def test_context_build_failure_fails_closed_to_high(env, monkeypatch):
    def boom(**kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(pp, "build_context", boom)
    assert classify_write_action(str(env.home / "proj" / "x.txt"), workspace=env.home) == HIGH_IMPACT


def test_relative_path_uses_workspace_not_process_cwd(env, monkeypatch, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert classify_write_action(".bashrc", workspace=env.home) == HIGH_IMPACT
    assert classify_write_action(".bashrc", workspace=elsewhere) == ACT  # same name, other workspace
    # agrees with what Filesystem would actually target
    from core.filesystem import FilesystemAccessError

    with pytest.raises(FilesystemAccessError):
        env.fs.write(".bashrc", "x")


def test_is_core_file_and_core_patterns_not_widened(env, monkeypatch):
    assert checkpoint_module.CORE_PATTERNS == ["core/*.py", "tools/*.py", "utils/*.py", "prompts/*.py"]
    for rel in ("main.py", "lib/a.sh", "install.sh", "config.json", "ccos/plugins/a/manifest.json", "tools/x.sh"):
        assert checkpoint_module.is_core_file(str(env.code / rel)) is False, rel
    fs = Filesystem(workspace=env.home, allow_self_modification=True)
    checkpoint = Mock()
    monkeypatch.setattr(fs, "_require_checkpoint", checkpoint)
    fs.write(str(env.code / "main.py"), "x")
    checkpoint.assert_not_called()


# ---- end to end through the real tools and the gateway ledger -----------------

def test_confirmless_no_selfmod_f3_blocked_and_audited(env, monkeypatch):
    monkeypatch.setattr(filesystem_module, "CODE_DIR", env.code)
    fs = Filesystem(workspace=env.code)
    monkeypatch.setattr(file_tools, "_get_fs", lambda: fs)
    target = env.code / "main.py"
    result = file_tools.tool_write_file(str(target), "x")
    assert result.startswith("[BLOCKED]")
    assert not target.exists()
    rows = env.rows()
    assert len(rows) == 1 and rows[0]["outcome"] == "refused" and rows[0]["authority"] == "HIGH_IMPACT"


@pytest.mark.parametrize("tool", ["write", "append"])
def test_confirmless_deny_blocked(env, tool):
    target = env.home / ".bashrc"
    fn = file_tools.tool_write_file if tool == "write" else file_tools.tool_append_file
    assert fn(str(target), "x").startswith("[BLOCKED]")
    assert not target.exists()


def test_selfmod_confirmless_f3_allowed_deny_still_refused(env, monkeypatch):
    monkeypatch.setitem(AGENT_CONFIG, "allow_self_modification", True)
    fs = Filesystem(workspace=env.code, allow_self_modification=True)
    monkeypatch.setattr(file_tools, "_get_fs", lambda: fs)
    monkeypatch.setattr(fs, "_require_checkpoint", Mock())
    ok = file_tools.tool_write_file(str(env.code / "codeyOS"), "#!/bin/sh\n")
    assert not ok.startswith("[BLOCKED]") and not ok.startswith("[ERROR]"), ok
    assert (env.code / "codeyOS").read_text() == "#!/bin/sh\n"
    # DENY target (a home file reached through a home-workspace Filesystem)
    fs2 = Filesystem(workspace=env.home, allow_self_modification=True)
    monkeypatch.setattr(file_tools, "_get_fs", lambda: fs2)
    res = file_tools.tool_write_file(str(env.home / ".bashrc"), "x")
    assert res.startswith("[ERROR] Access denied") and "protected path" in res, res
    assert not (env.home / ".bashrc").exists()
    assert env.rows()[-1]["outcome"] == "failed"


def test_repl_f3_new_file_and_append_prompt_deny_refused(env, monkeypatch):
    # NEW-1027 / G15j (flipped from "unprompted"): in the REPL (confirm_write
    # True, a tty) a HIGH new-file write or append now prompts once each; the
    # overwrite of the existing file adds only the legacy "Overwrite?" prompt
    # (no double prompt). DENY is still refused with no prompt.
    monkeypatch.setitem(AGENT_CONFIG, "confirm_write", True)
    monkeypatch.setitem(AGENT_CONFIG, "allow_self_modification", True)
    monkeypatch.setattr(file_tools, "_stdin_is_tty", lambda: True)
    fs = Filesystem(workspace=env.code, allow_self_modification=True)
    monkeypatch.setattr(file_tools, "_get_fs", lambda: fs)
    ask = Mock(return_value=True)
    import utils.logger as logger

    monkeypatch.setattr(logger, "confirm", ask)
    new = env.code / "install.sh"
    assert "Written" in file_tools.tool_write_file(str(new), "x")
    assert ask.call_count == 1
    assert "Appended" in file_tools.tool_append_file(str(new), "y")
    assert ask.call_count == 2
    # overwriting an EXISTING file hits only the ordinary confirm_write prompt
    file_tools.tool_write_file(str(new), "z")
    assert ask.call_count == 3
    ask.reset_mock()
    fs2 = Filesystem(workspace=env.home, allow_self_modification=True)
    monkeypatch.setattr(file_tools, "_get_fs", lambda: fs2)
    assert file_tools.tool_append_file(str(env.home / ".ssh" / "authorized_keys"), "k").startswith("[ERROR]")
    assert not (env.home / ".ssh").exists()
    ask.assert_not_called()


def test_patch_tool_uses_filesystem_workspace_and_denies(env, monkeypatch):
    target = env.home / ".bashrc"
    target.write_text("OLD line\n")
    monkeypatch.setattr(patch_tools, "get_filesystem", lambda **kw: env.fs, raising=False)
    import core.filesystem as fsmod

    monkeypatch.setattr(fsmod, "get_filesystem", lambda *a, **k: env.fs)
    res = patch_tools.tool_patch_file(str(target), "OLD", "NEW")
    assert res.startswith("[BLOCKED]") or res.startswith("[ERROR]"), res
    assert target.read_text() == "OLD line\n"


# ---- reviewer C1 / W1: per-form override and workspace= at tool level ---------

def test_tool_write_symlink_to_active_config_refused_with_self_mod_cwd_not_workspace(env, monkeypatch, tmp_path):
    cfg = env.home / "mycfg.json"
    cfg.write_text("ORIG")
    monkeypatch.setenv("CODEY_CONFIG_PATH", str(cfg))
    (env.code / "lib").mkdir()
    (env.code / "lib" / "innocent.sh").symlink_to(cfg)
    monkeypatch.setitem(AGENT_CONFIG, "allow_self_modification", True)
    fs = Filesystem(workspace=env.home, allow_self_modification=True)
    monkeypatch.setattr(file_tools, "_get_fs", lambda: fs)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    res = file_tools.tool_write_file(str(env.code / "lib" / "innocent.sh"), "PWNED")
    assert res.startswith("[ERROR] Access denied") and "config-active" in res, res
    assert cfg.read_text() == "ORIG"
    res = file_tools.tool_append_file(str(env.code / "lib" / "innocent.sh"), "PWNED")
    assert res.startswith("[ERROR] Access denied"), res
    assert cfg.read_text() == "ORIG"


@pytest.mark.parametrize("tool", ["write", "append", "patch"])
def test_tools_classify_relative_path_against_workspace_not_cwd(env, monkeypatch, tmp_path, tool):
    # confirm-less, no self-mod: a HIGH classification is a [BLOCKED] refusal; a
    # mis-classified ACT would reach Filesystem and come back as [ERROR] Access denied.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (env.home / ".bashrc").write_text("OLD line\n")
    (elsewhere / ".bashrc").write_text("OLD line\n")
    monkeypatch.chdir(elsewhere)
    import core.filesystem as fsmod

    monkeypatch.setattr(fsmod, "get_filesystem", lambda *a, **k: env.fs)
    if tool == "write":
        res = file_tools.tool_write_file(".bashrc", "x")
    elif tool == "append":
        res = file_tools.tool_append_file(".bashrc", "x")
    else:
        # patch_tools keeps an existing cwd-relative path relative, so the
        # classifier alone decides which directory it means (workspace=).
        res = patch_tools.tool_patch_file(".bashrc", "OLD", "NEW")
        # Declared G15e Unit C flip (Q7a): patch_file now validates the path it
        # will READ (the cwd-relative file) before reading, and that file lies
        # outside the workspace, so it is refused earlier than the classifier
        # ([ERROR] Access denied, nothing read or echoed) instead of [BLOCKED].
        assert res.startswith("[ERROR] Access denied"), res
        assert "OLD line" not in res
        assert (env.home / ".bashrc").read_text() == "OLD line\n"
        assert (elsewhere / ".bashrc").read_text() == "OLD line\n"
        return
    assert res.startswith("[BLOCKED]"), res
    assert (env.home / ".bashrc").read_text() == "OLD line\n"
