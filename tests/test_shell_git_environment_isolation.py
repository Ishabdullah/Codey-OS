"""NEW-893: generic shell-tool git env isolation (core.git_execution.shell_git_environment).

Unit tests pin shell_git_environment()'s exact behavior (ambient
preservation + forced-override injection). Real-subprocess tests run
through shell_tools.shell() end to end -- never a bare r.git() call for
the "mediated" side -- so these prove shell()'s actual wiring applies the
isolation, not just that the isolation mechanism works in isolation.
"""

import os
import shlex
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, git_execution
from core.action_gateway import ActionGateway
from tools import shell_tools
from utils.config import AGENT_CONFIG

# ---------------------------------------------------------------------------
# Unit tests on shell_git_environment() directly
# ---------------------------------------------------------------------------

def test_ambient_vars_survive(monkeypatch):
    monkeypatch.setenv("MY_UNRELATED_VAR", "survives")
    env = git_execution.shell_git_environment()
    assert env["MY_UNRELATED_VAR"] == "survives"


def test_preexisting_git_config_block_and_parameters_removed(monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "some.key")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "val")
    monkeypatch.setenv("GIT_CONFIG_PARAMETERS", "'secret'")
    env = git_execution.shell_git_environment()
    assert "GIT_CONFIG_PARAMETERS" not in env
    assert env["GIT_CONFIG_COUNT"] == str(len(git_execution._SHELL_GIT_FORCED_OVERRIDES))
    forced = {
        env[f"GIT_CONFIG_KEY_{i}"]: env[f"GIT_CONFIG_VALUE_{i}"]
        for i in range(len(git_execution._SHELL_GIT_FORCED_OVERRIDES))
    }
    assert forced == {
        "core.hookspath": "/dev/null",
        "core.fsmonitor": "false",
        "commit.gpgsign": "false",
        "tag.gpgsign": "false",
        "push.gpgSign": "false",
        "submodule.recurse": "false",
        "gc.auto": "0",
        "maintenance.auto": "false",
    }
    # The stale slot-0 pair planted above must not survive anywhere else
    # in the result under a higher index either.
    all_keys = [env[f"GIT_CONFIG_KEY_{i}"] for i in range(len(git_execution._SHELL_GIT_FORCED_OVERRIDES))]
    assert "some.key" not in all_keys


# ---------------------------------------------------------------------------
# Real-subprocess discriminating tests, through shell_tools.shell()
# ---------------------------------------------------------------------------

@pytest.fixture
def gateway(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    instance = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: instance)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", True)
    monkeypatch.delitem(AGENT_CONFIG, "_shell_fn", raising=False)
    monkeypatch.setattr(shell_tools, "ask_confirm", Mock(return_value=True))
    return SimpleNamespace(instance=instance, audit=audit)


def _write_marker_hook(hooks_dir, name, marker):
    script = hooks_dir / name
    script.write_text(f"#!/bin/sh\necho {name} >> {marker}\ncat >/dev/null\n")
    script.chmod(0o755)
    return script


@pytest.fixture
def repository(tmp_path, monkeypatch):
    for name in list(os.environ):
        if name.startswith("GIT_") or name == "EMAIL":
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    empty = tmp_path / "empty-config"
    empty.mkdir()
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(empty))
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args, cwd=repo, check=True):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)

    git("init", "-b", "main")
    for key, value in {
        "core.hooksPath": str(empty), "commit.gpgsign": "false", "tag.gpgsign": "false",
        "user.useConfigOnly": "true", "user.name": "Temporary Test",
        "user.email": "test@example.invalid",
    }.items():
        git("config", key, value)
    (repo / "content.txt").write_text("local content\n")
    git("add", "--", "content.txt")
    git("commit", "-m", "baseline")
    monkeypatch.chdir(repo)
    return SimpleNamespace(repo=repo, git=git, empty=empty)


def test_commit_pre_commit_hook_control_fires_mediated_does_not(repository, gateway, tmp_path, monkeypatch):
    r = repository
    hooks_dir = tmp_path / "marker-hooks"
    hooks_dir.mkdir()
    marker = tmp_path / "hook-fired.txt"
    _write_marker_hook(hooks_dir, "pre-commit", marker)
    r.git("config", "core.hooksPath", str(hooks_dir))
    (r.repo / "content.txt").write_text("more content\n")
    r.git("add", "--", "content.txt")

    # Control: force the pre-fix (fully ambient) behavior through the real
    # shell() code path, scoped to this block only.
    before = r.git("rev-parse", "HEAD").stdout
    with monkeypatch.context() as ctl:
        ctl.setattr(shell_tools, "shell_git_environment", lambda: os.environ.copy())
        shell_tools.shell("git commit -m control", timeout=19)
    assert marker.exists()
    after_control = r.git("rev-parse", "HEAD").stdout
    assert after_control != before

    # Mediated: real wiring (no override in scope), a fresh real commit.
    marker.unlink()
    (r.repo / "content.txt").write_text("even more content\n")
    r.git("add", "--", "content.txt")
    before2 = r.git("rev-parse", "HEAD").stdout
    shell_tools.shell("git commit -m mediated", timeout=19)
    assert not marker.exists()
    after2 = r.git("rev-parse", "HEAD").stdout
    assert after2 != before2  # the commit still landed; isolation didn't silently fail it


def test_status_fsmonitor_control_fires_mediated_does_not(repository, gateway, tmp_path, monkeypatch):
    r = repository
    marker = tmp_path / "fsmonitor-fired.txt"
    fsm = tmp_path / "fsm.sh"
    fsm.write_text(f"#!/bin/sh\necho fired >> {marker}\nprintf 'builtin:1\\n\\x00'\n")
    fsm.chmod(0o755)
    r.git("config", "core.fsmonitor", str(fsm))

    # Control: force pre-fix ambient behavior, scoped to this block only.
    with monkeypatch.context() as ctl:
        ctl.setattr(shell_tools, "shell_git_environment", lambda: os.environ.copy())
        shell_tools.shell("git status", timeout=19)
    assert marker.exists()

    # Mediated: real wiring (no override in scope). Assert the status call
    # itself still completed normally, not just that the marker is absent --
    # a broken/erroring mediated call would also leave the marker untouched.
    marker.unlink()
    result = shell_tools.shell("git status", timeout=19)
    assert not marker.exists()
    assert "[ERROR]" not in result
    assert "working tree clean" in result


def test_commit_gpgsign_config_control_fires_mediated_does_not(repository, gateway, tmp_path, monkeypatch):
    """Config-driven commit.gpgsign=true (NOT an explicit -S flag).

    Verified empirically (2026-10-13, disposable repo) that an explicit
    `git commit -S` bypasses commit.gpgsign entirely -- Git documents -S
    as countermanding the config variable, not consulting it -- so a
    mediated commit.gpgsign=false override has no effect on a command
    that passes -S directly. The override is only observable when
    signing is config-driven (no -S/-no-gpg-sign on the command line).
    """
    r = repository
    marker = tmp_path / "gpg-fired.txt"
    fake_gpg = tmp_path / "fake-gpg.sh"
    fake_gpg.write_text(
        f"#!/bin/sh\necho fired >> {marker}\n"
        f"echo '-----BEGIN PGP SIGNATURE-----'\necho fake-signature\necho '-----END PGP SIGNATURE-----'\n"
    )
    fake_gpg.chmod(0o755)
    r.git("config", "gpg.program", str(fake_gpg))
    r.git("config", "user.signingKey", "dummy")
    r.git("config", "commit.gpgsign", "true")

    # Control: force pre-fix ambient behavior, scoped to this block only --
    # commit.gpgsign=true from repo config actually invokes the fake gpg
    # (and fails to "sign").
    with monkeypatch.context() as ctl:
        ctl.setattr(shell_tools, "shell_git_environment", lambda: os.environ.copy())
        shell_tools.shell("git commit --allow-empty -m control-sig", timeout=19)
    assert marker.exists()

    # Mediated: real wiring forces commit.gpgsign=false, so the fake gpg
    # never fires and the commit succeeds without a signature attempt.
    marker.unlink()
    before = r.git("rev-parse", "HEAD").stdout
    shell_tools.shell("git commit --allow-empty -m mediated-sig", timeout=19)
    assert not marker.exists()
    after = r.git("rev-parse", "HEAD").stdout
    assert after != before


def test_non_git_command_unaffected(gateway, monkeypatch, tmp_path):
    # Delete any ambient GIT_CONFIG_* first: if every command (not just
    # git) were getting the mediated git env, GIT_CONFIG_COUNT/KEY_0 would
    # also show up in the child's environment here, masking the bug this
    # test is meant to catch.
    #
    # G15d D-2 (deliberate update): `shell("env")` is now HIGH_IMPACT and
    # refused, so the probe is an ACT python script file that writes its own
    # os.environ to a file the test reads, run through the real runner.
    for name in list(os.environ):
        if name.startswith("GIT_CONFIG_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("MY_SHELL_MARKER_VAR", "present-in-env-output")
    out = tmp_path / "env_dump.txt"
    script = tmp_path / "dump_env.py"
    script.write_text(
        "import os\n"
        f"open({str(out)!r}, 'w').write('\\n'.join(f'{{k}}={{v}}' for k, v in os.environ.items()))\n"
    )
    shell_tools.shell(f"python3 {script}", yolo=True)
    result = out.read_text()
    assert "MY_SHELL_MARKER_VAR=present-in-env-output" in result
    assert "GIT_CONFIG_COUNT" not in result
    assert "GIT_CONFIG_KEY_0" not in result


def test_explicit_commit_gpg_sign_flag_bypasses_mediation(repository, gateway, tmp_path):
    """Pins the documented residual: an explicit `-S`/`--gpg-sign` on the
    command line bypasses commit.gpgsign (and therefore this function's
    commit.gpgsign=false override) entirely. Mediated here means the real
    shell_git_environment() wiring, not the control override -- the point
    is that mediation alone cannot stop this, by design (see the
    docstring's residual list)."""
    r = repository
    marker = tmp_path / "gpg-s-fired.txt"
    fake_gpg = tmp_path / "fake-gpg.sh"
    fake_gpg.write_text(
        f"#!/bin/sh\necho fired >> {marker}\n"
        f"echo '-----BEGIN PGP SIGNATURE-----'\necho fake-signature\necho '-----END PGP SIGNATURE-----'\n"
    )
    fake_gpg.chmod(0o755)
    r.git("config", "gpg.program", str(fake_gpg))
    r.git("config", "user.signingKey", "dummy")
    # Deliberately leave commit.gpgsign unset/false in repo config -- the
    # explicit -S flag on the command line is what requests signing here,
    # not the config variable this function overrides.
    shell_tools.shell("git commit -S --allow-empty -m explicit-sign", timeout=19)
    assert marker.exists()


# ---------------------------------------------------------------------------
# Named-residual regression tests
# ---------------------------------------------------------------------------

def test_named_residual_command_line_c_override_still_bypasses(repository, gateway, tmp_path):
    """Pins the documented, accepted gap: `git -c core.hooksPath=...` on
    the command line defeats the env-based override. This is a regression
    test for the gap itself, not an unnoticed failure -- if a future
    change accidentally closes (or reopens differently) this gap, this
    test should be updated deliberately, not silently left failing.
    """
    r = repository
    hooks_dir = tmp_path / "marker-hooks"
    hooks_dir.mkdir()
    marker = tmp_path / "hook-fired.txt"
    _write_marker_hook(hooks_dir, "pre-commit", marker)
    # Plant core.hooksPath via repo config FIRST and confirm mediation
    # blocks it with no -c clause -- otherwise this test would also pass
    # if mediation were broken entirely (never isolating anything).
    r.git("config", "core.hooksPath", str(hooks_dir))
    (r.repo / "content.txt").write_text("plain mediated change\n")
    r.git("add", "--", "content.txt")
    shell_tools.shell("git commit -m plain-mediated", timeout=19)
    assert not marker.exists()

    # Now the command-line -c clause supplies the same hooksPath directly.
    (r.repo / "content.txt").write_text("residual change\n")
    r.git("add", "--", "content.txt")
    command = f"git -c core.hooksPath={shlex.quote(str(hooks_dir))} commit -m residual"
    result = shell_tools.shell(command, timeout=19)
    assert marker.exists()
    assert result
