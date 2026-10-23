"""NEW-894 follow-up: a non-git shell command whose argv references the
workspace's or CODE_DIR's own `.git` directory is escalated to HIGH_IMPACT
(confirm-or-fail-closed), not denied outright: a shell command's argv
token can equally be a write target, a legitimate read source, an
exclusion pattern, or crash-recovery cleanup (`rm .git/index.lock`), so
only core/filesystem.py's single-confirmed-mutation-target path can
safely deny outright -- this generic argv scan cannot.

Every test here uses a tmp_path-based cwd/roots (direct unit tests) or a
monkeypatched shell_tools._config.WORKSPACE_ROOT/CODE_DIR (integration
tests). No test may ever reach the real on-device repository's `.git/`.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway
from core.action_gateway import ACT, HIGH_IMPACT, READ, ActionGateway
from tools import shell_tools
from utils.config import AGENT_CONFIG


# ---------------------------------------------------------------------------
# A. Direct unit tests of _shell_command_targets_git_metadata()
# ---------------------------------------------------------------------------

@pytest.fixture
def roots(tmp_path):
    workspace = tmp_path / "workspace"
    code_dir = tmp_path / "code_dir"
    workspace.mkdir()
    code_dir.mkdir()
    return SimpleNamespace(workspace=workspace, code_dir=code_dir)


@pytest.mark.parametrize("command", [
    "cp content.txt .git/config",
    "tee -a .git/config",
    "sed -i s/a/b/ .git/config",
    "dd if=/dev/null of=.git/config",
    "mv x .git/hooks/pre-commit",
    "chmod +x .git/hooks/pre-commit",
    "ln -s /tmp/evil .git/hooks/pre-commit",
    "install -m755 payload .git/hooks/pre-commit",
    "rm .git/index.lock",
    "sort -o .git/x input.txt",
    "sort --output=.git/x input.txt",
    "uniq input.txt .git/x",
    "tree -o .git/x",
    "file -C -m .git/evil",
])
def test_detects_git_metadata_write_targets(roots, command):
    assert shell_tools._shell_command_targets_git_metadata(
        command, cwd=roots.workspace, roots=(roots.workspace, roots.code_dir)
    )


@pytest.mark.parametrize("command", [
    "./.git/hooks/pre-commit",
    ".git/hooks/pre-commit",
])
def test_detects_git_metadata_target_in_argv0(roots, command):
    """Code-reviewer finding: the scan originally covered only parts[1:],
    missing the case where the command itself (argv[0]) is a path inside
    .git/ -- i.e. directly executing a file planted under .git/hooks --
    exactly the execution-of-.git-resident-code risk this check exists to
    catch. Confirmed via mutation testing that scanning parts (not
    parts[1:]) is what catches this."""
    assert shell_tools._shell_command_targets_git_metadata(
        command, cwd=roots.workspace, roots=(roots.workspace, roots.code_dir)
    )


def test_dd_requires_equals_split_not_naive_whole_token(roots):
    """Pins why the `=`-split exists: the naive whole-token resolution of
    'of=.git/config' (without splitting on '=') would not land under
    either root, so it would NOT match."""
    naive = Path("of=.git/config")
    naive_resolved = (roots.workspace / naive).resolve(strict=False)
    with pytest.raises(ValueError):
        naive_resolved.relative_to(roots.workspace.resolve() / ".git")
    assert shell_tools._shell_command_targets_git_metadata(
        "dd if=/dev/null of=.git/config", cwd=roots.workspace, roots=(roots.workspace, roots.code_dir)
    )


def test_relative_traversal_from_nested_cwd(roots):
    nested_cwd = roots.workspace / "a" / "b"
    nested_cwd.mkdir(parents=True)
    assert shell_tools._shell_command_targets_git_metadata(
        "cp ../../.git/config backup.txt", cwd=nested_cwd, roots=(roots.workspace, roots.code_dir)
    )


def test_distinct_code_dir_root_match(roots):
    """Target lands under the CODE_DIR root specifically, not the
    workspace root, proving both supplied roots are checked."""
    assert shell_tools._shell_command_targets_git_metadata(
        "cp x .git/config", cwd=roots.code_dir, roots=(roots.workspace, roots.code_dir)
    )


def test_symlink_case_a_lexical_match_on_preexisting_symlink(roots):
    """`.git/hooks/pre-commit` pre-exists as a symlink pointing OUTSIDE
    both roots; `rm` of it is still detected via the lexical (unresolved)
    form, without following the symlink."""
    outside = roots.workspace.parent / "elsewhere"
    outside.mkdir()
    hooks = roots.workspace / ".git" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre-commit").symlink_to(outside / "evil")
    assert shell_tools._shell_command_targets_git_metadata(
        "rm .git/hooks/pre-commit", cwd=roots.workspace, roots=(roots.workspace, roots.code_dir)
    )


def test_symlink_loop_at_git_target_is_detected(roots):
    """A self-referential symlink AT the .git-rooted path itself. Verified
    on this device: Path.resolve(strict=False) does NOT raise for this
    case (it returns the lexical path unresolved), so this exercises the
    lexical check, not the resolve()-failure branch -- see
    test_resolve_failure_fails_closed for that branch directly."""
    hooks = roots.workspace / ".git" / "hooks"
    hooks.mkdir(parents=True)
    loop = hooks / "loop"
    loop.symlink_to(loop)
    assert shell_tools._shell_command_targets_git_metadata(
        "rm .git/hooks/loop", cwd=roots.workspace, roots=(roots.workspace, roots.code_dir)
    )


def test_pathological_long_component_is_detected(roots):
    """A path component far longer than typical OS limits. Verified on
    this device: Path.resolve(strict=False) does NOT raise for this case,
    so this exercises the lexical check, not the resolve()-failure branch
    -- see test_resolve_failure_fails_closed for that branch directly."""
    long_name = "x" * 300
    assert shell_tools._shell_command_targets_git_metadata(
        f"cp payload .git/{long_name}", cwd=roots.workspace, roots=(roots.workspace, roots.code_dir)
    )


def test_embedded_nul_does_not_raise_and_is_handled(roots):
    """Verified on this device: Path() does not validate an embedded NUL
    at construction, but Path.resolve(strict=False) raises ValueError
    from the underlying lstat() ('embedded null character in path').
    The lexical check runs first and doesn't match this token (it isn't
    .git-shaped), so this exercises the resolve() ValueError path
    specifically -- it must be caught (not propagate out of shell()/the
    scan) and must fail closed (escalate), not silently return False."""
    assert shell_tools._shell_command_targets_git_metadata(
        "cp x a\x00b", cwd=roots.workspace, roots=(roots.workspace, roots.code_dir)
    )


def test_resolve_failure_fails_closed(roots, monkeypatch):
    """Direct test of the resolve()-failure branch: forces Path.resolve to
    raise, on an otherwise ordinary non-.git command, and asserts the
    function fails closed (returns True) rather than silently treating
    the token as safe."""
    original_resolve = Path.resolve

    def failing_resolve(self, *args, **kwargs):
        if self.name == "b.txt":
            raise OSError("simulated resolve failure")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", failing_resolve)
    assert shell_tools._shell_command_targets_git_metadata(
        "cp a.txt b.txt", cwd=roots.workspace, roots=(roots.workspace, roots.code_dir)
    )


def test_symlink_case_b_resolved_match_through_indirection(roots):
    """A symlink elsewhere points INTO `.git/hooks`; a command targeting
    through that symlink is still detected via the resolved form."""
    git_hooks = roots.workspace / ".git" / "hooks"
    git_hooks.mkdir(parents=True)
    indirection = roots.workspace / "alias_to_hooks"
    indirection.symlink_to(git_hooks)
    assert shell_tools._shell_command_targets_git_metadata(
        "touch alias_to_hooks/pre-commit", cwd=roots.workspace, roots=(roots.workspace, roots.code_dir)
    )


@pytest.mark.parametrize("command", [
    "cat .git/config",
    "grep .git notes.txt",
    "ls .git",
])
def test_read_exemption_preserved(roots, command):
    assert not shell_tools._shell_command_targets_git_metadata(
        command, cwd=roots.workspace, roots=(roots.workspace, roots.code_dir)
    )


def test_git_basename_is_a_no_op(roots):
    assert not shell_tools._shell_command_targets_git_metadata(
        "git --git-dir=.git status", cwd=roots.workspace, roots=(roots.workspace, roots.code_dir)
    )


@pytest.mark.parametrize("command", [
    "cp a.txt b.txt",
    "sort -o out.txt in.txt",
])
def test_no_git_token_not_detected(roots, command):
    assert not shell_tools._shell_command_targets_git_metadata(
        command, cwd=roots.workspace, roots=(roots.workspace, roots.code_dir)
    )


def test_git_shaped_token_outside_both_roots_not_detected(tmp_path, roots):
    outside_cwd = tmp_path / "unrelated"
    outside_cwd.mkdir()
    assert not shell_tools._shell_command_targets_git_metadata(
        "cp x .git/config", cwd=outside_cwd, roots=(roots.workspace, roots.code_dir)
    )


def test_find_is_deliberately_not_exempted(roots):
    """find is already HIGH_IMPACT from classify_shell_command(), so this
    scan returning True for it changes nothing (HIGH_IMPACT -> HIGH_IMPACT).
    This is a deliberate non-exemption, not an oversight -- pinned here so
    a future reader doesn't mistake its absence for a gap."""
    assert shell_tools._shell_command_targets_git_metadata(
        "find . -path './.git' -prune", cwd=roots.workspace, roots=(roots.workspace, roots.code_dir)
    )


# ---------------------------------------------------------------------------
# B. shell()-level integration tests
# ---------------------------------------------------------------------------

@pytest.fixture
def gateway(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    instance = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: instance)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", True)
    return SimpleNamespace(instance=instance, audit=audit)


@pytest.fixture
def isolated_roots(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    code_dir = tmp_path / "code_dir"
    workspace.mkdir()
    code_dir.mkdir()
    monkeypatch.setattr(shell_tools._config, "WORKSPACE_ROOT", workspace)
    monkeypatch.setattr(shell_tools, "CODE_DIR", code_dir)
    monkeypatch.chdir(workspace)
    return SimpleNamespace(workspace=workspace, code_dir=code_dir)


def _audit_rows(gateway):
    return [json.loads(line) for line in gateway.audit.read_text().splitlines()]


@pytest.mark.parametrize("mode", ["no-path", "yolo"])
def test_escalated_command_fails_closed_without_confirm_path(gateway, isolated_roots, monkeypatch, mode):
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", mode != "no-path")
    ask_confirm, warn, runner = Mock(), Mock(), Mock()
    monkeypatch.setattr(shell_tools, "ask_confirm", ask_confirm)
    monkeypatch.setattr(shell_tools, "warning", warn)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = shell_tools.shell("tee -a .git/config", yolo=mode == "yolo")
    assert result.startswith("[BLOCKED]") and "no confirmation path available" in result
    ask_confirm.assert_not_called()
    warn.assert_not_called()
    runner.assert_not_called()
    rows = _audit_rows(gateway)
    assert len(rows) == 1
    assert rows[0]["authority"] == HIGH_IMPACT and rows[0]["outcome"] == "refused"


def test_escalated_command_executes_on_confirmation(gateway, isolated_roots, monkeypatch):
    ask_confirm = Mock(return_value=True)
    warn = Mock()
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="ok\n", stderr=""))
    monkeypatch.setattr(shell_tools, "ask_confirm", ask_confirm)
    monkeypatch.setattr(shell_tools, "warning", warn)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    # `touch` (ACT) not `tee`: G15c default-deny makes `tee` HIGH_IMPACT on its
    # own, so it no longer exercises the ACT -> HIGH metadata escalation.
    result = shell_tools.shell("touch .git/config")
    ask_confirm.assert_called_once()
    runner.assert_called_once()
    assert result == "ok"
    warn.assert_called_once_with(
        "Command targets this repository's own Git metadata directory: `touch .git/config`"
    )
    rows = _audit_rows(gateway)
    assert len(rows) == 1
    assert rows[0]["authority"] == HIGH_IMPACT and rows[0]["outcome"] == "allowed"


def test_argv0_git_metadata_target_blocked_with_yolo(gateway, isolated_roots, monkeypatch):
    """Code-reviewer finding: directly executing a path inside .git/ (the
    command itself, not an argument) must be caught and fail closed under
    yolo=True -- this is the execution-of-.git-resident-code scenario the
    whole check exists to prevent, and was missed before the parts[1:] ->
    parts fix."""
    ask_confirm, warn, runner = Mock(), Mock(), Mock()
    monkeypatch.setattr(shell_tools, "ask_confirm", ask_confirm)
    monkeypatch.setattr(shell_tools, "warning", warn)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = shell_tools.shell("./.git/hooks/pre-commit", yolo=True)
    assert result.startswith("[BLOCKED]") and "no confirmation path available" in result
    runner.assert_not_called()
    rows = _audit_rows(gateway)
    assert len(rows) == 1
    assert rows[0]["authority"] == HIGH_IMPACT and rows[0]["outcome"] == "refused"


def test_git_metadata_warning_not_emitted_for_direct_git_control(gateway, isolated_roots, monkeypatch):
    """The escalation-specific warning must only fire when THIS check is
    what triggered HIGH_IMPACT, not for the pre-existing git-basename
    HIGH_IMPACT path."""
    ask_confirm = Mock(return_value=True)
    warn = Mock()
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="clean\n", stderr=""))
    monkeypatch.setattr(shell_tools, "ask_confirm", ask_confirm)
    monkeypatch.setattr(shell_tools, "warning", warn)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    shell_tools.shell("git --git-dir=.git status")
    warn.assert_not_called()


def test_escalated_command_cancelled_on_decline(gateway, isolated_roots, monkeypatch):
    ask_confirm = Mock(return_value=False)
    runner = Mock()
    monkeypatch.setattr(shell_tools, "ask_confirm", ask_confirm)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = shell_tools.shell("tee -a .git/config")
    assert result == "[CANCELLED] User declined to run command."
    runner.assert_not_called()
    rows = _audit_rows(gateway)
    assert len(rows) == 1
    assert rows[0]["authority"] == HIGH_IMPACT and rows[0]["outcome"] == "refused"


def test_control_ordinary_act_command_unchanged(gateway, isolated_roots, monkeypatch):
    ask_confirm = Mock(return_value=True)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="done\n", stderr=""))
    monkeypatch.setattr(shell_tools, "ask_confirm", ask_confirm)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    (isolated_roots.workspace / "a.txt").write_text("x")
    result = shell_tools.shell("cp a.txt b.txt")
    ask_confirm.assert_called_once()
    runner.assert_called_once()
    assert result == "done"
    rows = _audit_rows(gateway)
    assert rows[0]["authority"] == ACT and rows[0]["outcome"] == "allowed"


def test_control_read_command_on_git_config_unchanged(gateway, isolated_roots, monkeypatch):
    """READ-authority commands already go through the UI confirm prompt
    when AGENT_CONFIG['confirm_shell'] is True (pre-existing behavior,
    unrelated to this change) -- what must stay unchanged here is the
    authority classification (READ, not escalated to HIGH_IMPACT) and the
    gateway's fail-open-on-confirm semantics for READ."""
    ask_confirm = Mock(return_value=True)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="[core]\n", stderr=""))
    monkeypatch.setattr(shell_tools, "ask_confirm", ask_confirm)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    git_dir = isolated_roots.workspace / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]\n")
    result = shell_tools.shell("cat .git/config")
    ask_confirm.assert_called_once()
    runner.assert_called_once()
    assert result == "[core]"
    rows = _audit_rows(gateway)
    assert rows[0]["authority"] == READ and rows[0]["outcome"] == "allowed"


def test_control_read_command_executes_without_confirm_when_confirm_shell_false(gateway, isolated_roots, monkeypatch):
    """The property escalation would actually break: with confirm_shell
    False, a plain READ command executes directly with no confirm prompt
    -- if `cat .git/config` were wrongly escalated to HIGH_IMPACT, this
    would instead return `[BLOCKED] ... no confirmation path available`."""
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    ask_confirm = Mock()
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="[core]\n", stderr=""))
    monkeypatch.setattr(shell_tools, "ask_confirm", ask_confirm)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    git_dir = isolated_roots.workspace / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]\n")
    result = shell_tools.shell("cat .git/config")
    assert result == "[core]"
    ask_confirm.assert_not_called()
    runner.assert_called_once()
    rows = _audit_rows(gateway)
    assert rows[0]["authority"] == READ and rows[0]["outcome"] == "allowed"


def test_control_direct_git_basename_path_unaffected(gateway, isolated_roots, monkeypatch):
    """Proves the new check didn't double-handle or short-circuit the
    EXISTING git-basename HIGH_IMPACT path differently."""
    ask_confirm = Mock(return_value=True)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="clean\n", stderr=""))
    monkeypatch.setattr(shell_tools, "ask_confirm", ask_confirm)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = shell_tools.shell("git --git-dir=.git status")
    ask_confirm.assert_called_once()
    runner.assert_called_once()
    assert result == "clean"
    rows = _audit_rows(gateway)
    assert rows[0]["authority"] == HIGH_IMPACT and rows[0]["outcome"] == "allowed"


def test_daemon_passthrough_unaffected(gateway, isolated_roots, monkeypatch):
    from core import task_executor

    ask_confirm = Mock()
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="[core]\n", stderr=""))
    monkeypatch.setattr(shell_tools, "ask_confirm", ask_confirm)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    git_dir = isolated_roots.workspace / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("[core]\n")
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    result = executor._daemon_shell("cat .git/config")
    ask_confirm.assert_not_called()
    assert result == "[core]"
