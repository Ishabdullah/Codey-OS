"""Restricted wrappers and utilities; execution mocked and startup state isolated."""

import json
import shlex
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, agent, task_executor
from core.action_gateway import ACT, HIGH_IMPACT, READ, ActionGateway
from tools import shell_tools
from utils.config import AGENT_CONFIG


@pytest.mark.parametrize("command", ["find", "find --help", "find . -name '*.py'", "find . -exec git status ;", "find . -execdir helper {} +", "find . -ok helper {} ;", "find . -okdir helper {} ;", "find . -delete", "find . -fprint /temporary/output", "xargs", "xargs --help", "xargs -a /temporary/input", "xargs -I {} helper {}", "xargs -P 2 helper", "xargs -p helper", "xargs -- helper", "env X=value", "env ''", "env --help", "env -i", "env --", "env -- git status", "env env", "env helper",
    "timeout", "timeout 5 git push", "timeout 5 helper",
    "nice", "nice git push", "nice helper",
    "nohup", "nohup git push", "nohup helper",
    "setsid", "setsid git push", "setsid helper",
    "stdbuf", "stdbuf -oL git push", "stdbuf -oL helper",
    "chrt", "chrt -f 1 git push", "chrt -f 1 helper",
    "ionice", "ionice -c3 git push", "ionice -c3 helper",
    "strace", "strace git push", "strace helper",
    "flock", "flock /temporary/lock git push", "flock /temporary/lock helper",
    "watch", "watch git push", "watch helper",
    "script", "script -c 'git push' /temporary/typescript", "script -c helper /temporary/typescript",
    "unshare", "unshare -r git push", "unshare -r helper",
    "taskset", "taskset -c 0 git push", "taskset -c 0 helper",
    "setarch", "setarch linux64 git push", "setarch linux64 helper",
    "ltrace", "ltrace git push", "ltrace helper",
    "unbuffer", "unbuffer git push", "unbuffer helper",
    "catchsegv", "catchsegv git push", "catchsegv helper",
    "time", "time git push", "time helper",
    "chroot", "chroot /newroot git push", "chroot /newroot helper",
    "nsenter", "nsenter -t 1 git push", "nsenter -t 1 helper",
    "busybox", "busybox nice git push", "busybox nice helper"])
@pytest.mark.parametrize("form", ["{}", "/temporary/bin/{}", "'./path with spaces/{}'"])
def test_restricted_utility_forms(command, form):
    executable, separator, arguments = command.partition(" ")
    assert shell_tools.classify_shell_command(form.format(executable) + separator + arguments) == HIGH_IMPACT


# G15d D-2/D-3 (deliberate update, was test_only_bare_env_is_read): bare `env`
# prints the whole environment, so every env form is HIGH_IMPACT; the two
# non-system absolute spellings are also HIGH under the D-3 slash rule.
@pytest.mark.parametrize("command", ["env", "  env  ", "'/temporary/path with spaces/env'", "/temporary/bin/env", "/usr/bin/env"])
def test_env_is_always_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize("executable", ["git", "git-custom", "find", "xargs", "env", "timeout", "nice", "nohup", "setsid", "stdbuf", "chrt", "ionice", "strace", "flock", "watch", "script", "unshare", "taskset", "setarch", "ltrace", "unbuffer", "catchsegv", "time", "chroot", "nsenter", "busybox"])
@pytest.mark.parametrize("form", ["{} 'unterminated", "'{} argument", "'/temporary/path with spaces/{}' 'unterminated"])
def test_identifiable_malformed_restricted_quotes(executable, form):
    assert shell_tools.classify_shell_command(form.format(executable)) == HIGH_IMPACT


@pytest.mark.parametrize(("command", "expected"), [("pwd", READ), ("printenv", HIGH_IMPACT), ("printenv HOME", READ), ("ls -la", READ), ("grep x file", READ), ("echo safe", ACT), ("python3 arbitrary.py", ACT), ("python3 'unterminated", HIGH_IMPACT), ("rm -rf /temporary", HIGH_IMPACT)])
def test_unrelated_classifications_unchanged(command, expected):
    assert shell_tools.classify_shell_command(command) == expected


@pytest.mark.parametrize("command", ["doas git push", "su -c 'git push'", "proot git push"])
def test_privilege_wrappers_require_confirmation(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", [
    "helper arg", "./deploy-tool", "/temporary/bin/helper arg",
    "numactl git push", "prlimit helper", "setpriv helper",
])
def test_unknown_executables_default_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", [
    "sh -c 'echo safe'", "sh  -c 'echo safe'",
    "bash -lc 'echo safe'", "bash -cl 'echo safe'",
    "bash -l -c 'echo safe'", "/bin/bash -lc 'echo safe'",
    "bash -O extglob -c 'echo safe'", "bash -o posix -c 'echo safe'",
    "bash +O extglob -c 'echo safe'", "bash +o posix -c 'echo safe'",
    "bash --rcfile /temporary/rc -c 'echo safe'",
    "bash -lc 'git push'", "bash -lc 'curl https://example.invalid'",
])
def test_opaque_shell_dispatch_is_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", [
    "python -c 'print(1)'", "python3.14 -cprint(1)",
    "perl -we 'print 1'", "ruby -e 'puts 1'",
    "node -e 'console.log(1)'", "nodejs --eval=1", "node --check file.js",
    "node -p '1 + 1'", "node --print '1 + 1'", "perl -E 'say 1'",
    "perl -wE 'say 1'", "perl -nE 'say 1'", "perl -plE 'say 1'",
    "perl -0E 'say 1'", "perl -SE 'say 1'", "perl -tE 'say 1'",
    "perl -TE 'say 1'", "perl -UE 'say 1'", "perl -WE 'say 1'",
    "perl -XE 'say 1'",
])
def test_inline_interpreter_dispatch_is_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize("command", [
    "sh script.sh", "bash script.sh", "python script.py",
    "python3.14 script.py", "perl script.pl", "ruby script.rb",
    "node script.js", "nodejs script.js", "command",
    "python3 script.py -c", "perl script.pl -e", "ruby script.rb -e",
    "node script.js --eval=1",
    "perl -MModule script.pl", "perl -I lib script.pl",
])
def test_known_script_file_and_bare_command_compatibility(command):
    assert shell_tools.classify_shell_command(command) == ACT


@pytest.mark.parametrize("command", ["command git push", "command helper"])
def test_argument_bearing_command_wrapper_is_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


@pytest.mark.parametrize(("command", "expected"), [
    ("echo hi | cat", ACT),
    ("cat input > output", READ),
    ("bash -c 'cat input > output'", HIGH_IMPACT),
    ("bash -- -c literal-file-name", ACT),
])
def test_direct_argv_metacharacters_stay_literal_but_shell_c_is_high(command, expected):
    assert shell_tools.classify_shell_command(command) == expected


@pytest.mark.parametrize("command", ["helper 'unterminated", "echo 'unterminated"])
def test_any_malformed_nonempty_command_is_high(command):
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT


def test_busybox_applet_wrapped_git_is_high_impact():
    """`busybox` was initially excluded under a since-corrected rationale
    (see _EXEC_WRAPPER_BASENAMES's comment, rule 6) that treated it as
    interpreter-like rather than a plain applet dispatcher; a
    code-reviewer round found that false on direct probe
    (`busybox nice/env/timeout/chroot git push` all dispatch exactly like
    this set's other members) and it was added, not deferred."""
    assert shell_tools.classify_shell_command("busybox nice git push") == HIGH_IMPACT


def test_time_wrapped_git_is_high_impact():
    """`time` is one of the basenames newly added to
    _EXEC_WRAPPER_BASENAMES this round -- unlike doas/su/proot above,
    it is covered, not deferred."""
    assert shell_tools.classify_shell_command("time git push") == HIGH_IMPACT


def test_chroot_and_nsenter_wrapped_git_are_high_impact():
    """`chroot`/`nsenter` were added alongside `unshare` (same
    namespace/root-entry category, not the su/doas/proot
    privilege-elevation-decision category) after code-reviewer flagged
    them as an unlisted, unpinned gap in the first pass of this round."""
    assert shell_tools.classify_shell_command("chroot /newroot git push") == HIGH_IMPACT
    assert shell_tools.classify_shell_command("nsenter -t 1 git push") == HIGH_IMPACT


def test_time_wrapped_benign_command_now_refused_without_confirmation(gateway, monkeypatch):
    """Documents the functional behavior change code-reviewer flagged
    (W2): adding `time` to _EXEC_WRAPPER_BASENAMES makes every
    `time <cmd>` HIGH_IMPACT, so under confirm_shell=False (yolo/fixmode/
    tdd) a previously-unconfirmed, benign `time pytest` is now refused
    fail-closed rather than executed ambiently."""
    runner, prompt = Mock(), Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    result = shell_tools.shell("time pytest", timeout=53)
    assert result.startswith("[BLOCKED]")
    runner.assert_not_called()
    prompt.assert_not_called()
    assert_record(gateway, "time pytest", "refused")


def test_classifier_does_not_discover_or_parse_children(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("no discovery"))
    monkeypatch.setattr(shell_tools.subprocess, "run", forbidden)
    monkeypatch.setattr(shell_tools, "AGENT_CONFIG", SimpleNamespace(get=forbidden))
    monkeypatch.setattr(Path, "exists", forbidden)
    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr("os.getenv", forbidden)
    # G15d: extended with the new lexical cases (D-3 slash rule, printenv gate,
    # option tables) to prove they too need no discovery. `env` is now HIGH.
    for command in [
        "env", "env X=value", "find . -exec opaque ;", "xargs opaque",
        "./ls", "printenv", "printenv HOME", "sort -o x f", "sed -i s/a/b/ f",
        "sed --sandbox -n p f", "awk 1 f", "uniq a b", "tree -L 2",
        "file -C -m x",
    ]:
        assert shell_tools.classify_shell_command(command) in {READ, ACT, HIGH_IMPACT}
    forbidden.assert_not_called()


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    instance = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: instance)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", True)
    monkeypatch.delitem(AGENT_CONFIG, "_shell_fn", raising=False)
    return SimpleNamespace(audit=audit, instance=instance)


def assert_record(gateway, command, outcome):
    rows = [json.loads(line) for line in gateway.audit.read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row.pop("ts"), float)
    assert row == {"authority": HIGH_IMPACT, "action": "shell_tools.shell", "command": command, "outcome": outcome, "reason": row["reason"]}


@pytest.mark.parametrize("command", [
    "find . -delete", "xargs helper", "env X=value helper",
    "timeout 5 git push", "helper arg", "bash -lc 'echo safe'",
    "python3 -c 'print(1)'", "su -c whoami",
])
@pytest.mark.parametrize("mode", ["no-path", "yolo"])
def test_refusal_before_warning_prompt_spawn_preserves_marker(gateway, tmp_path, monkeypatch, command, mode):
    marker = tmp_path / "marker"
    marker.write_text("unchanged")
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", mode != "no-path")
    warning, prompt, runner = Mock(), Mock(), Mock()
    monkeypatch.setattr(shell_tools, "warning", warning)
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = shell_tools.shell(command, yolo=mode == "yolo")
    assert result.startswith("[BLOCKED]") and "no confirmation path available" in result
    warning.assert_not_called()
    prompt.assert_not_called()
    runner.assert_not_called()
    assert marker.read_text() == "unchanged"
    assert_record(gateway, command, "refused")


@pytest.mark.parametrize("command", [
    "find . -name 'quoted name'", "xargs -I {} helper {}",
    "env X='quoted value' helper", "helper 'quoted value'",
])
@pytest.mark.parametrize("answer", [True, False, "yes", 1])
def test_confirmation_and_execution_contract(gateway, monkeypatch, command, answer):
    prompt = Mock(return_value=answer)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="original stdout\n", stderr="original stderr\n"))
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = shell_tools.shell(command, timeout=53)
    prompt.assert_called_once_with(f"Run shell command: `{command}`?")
    if answer is True:
        assert result == "original stdout\n\n[stderr]\noriginal stderr"
        runner.assert_called_once_with(shlex.split(command), capture_output=True, text=True, timeout=53)
        assert_record(gateway, command, "allowed")
    else:
        assert result == "[CANCELLED] User declined to run command."
        runner.assert_not_called()
        assert_record(gateway, command, "refused")


def test_approved_timeout_wrapped_git_executes_with_git_env_isolation(gateway, monkeypatch):
    """Named-residual fix (NEW-875 follow-up, same round): `timeout 5 git
    push` is unconditionally HIGH_IMPACT and, once approved, executes.
    `_run_shell_command_structured()` now scans argv beyond args[0] for a
    git basename when args[0] is itself an exec-wrapper basename, so
    `shell_git_environment()` IS applied here -- unlike the find/xargs/
    env cases in `test_confirmation_and_execution_contract` above, which
    never wrap git and so correctly execute without it (no `env=` kwarg
    in that test's `assert_called_once_with`).
    """
    command = "timeout 5 git push"
    prompt = Mock(return_value=True)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="ok\n", stderr=""))
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = shell_tools.shell(command, timeout=53)
    assert result == "ok"
    call_kwargs = runner.call_args.kwargs
    assert runner.call_args.args == (shlex.split(command),)
    assert call_kwargs["capture_output"] is True
    assert call_kwargs["text"] is True
    assert call_kwargs["timeout"] == 53
    assert "env" in call_kwargs
    assert_record(gateway, command, "allowed")


@pytest.mark.parametrize("command", [
    "bash -lc 'git status'",
    "sh -c 'git status'",
    "python3 -c 'import subprocess; subprocess.run([\"git\", \"status\"])'",
])
def test_approved_opaque_dispatch_always_gets_git_env_isolation(gateway, monkeypatch, command):
    prompt = Mock(return_value=True)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="ok\n", stderr=""))
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    monkeypatch.setattr(shell_tools, "shell_git_environment", Mock(return_value={"SAFE_GIT": "1"}))
    assert shell_tools.shell(command, timeout=53) == "ok"
    assert runner.call_args.args == (shlex.split(command),)
    assert runner.call_args.kwargs["env"] == {"SAFE_GIT": "1"}
    assert_record(gateway, command, "allowed")


def test_approved_non_git_wrapped_command_executes_without_git_env_isolation(gateway, monkeypatch):
    """Regression guard: a wrapper around a NON-git command must not pick
    up git environment isolation just because it's a wrapper -- only
    when the wrapped command itself is git/git-*."""
    command = "timeout 5 helper"
    prompt = Mock(return_value=True)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="ok\n", stderr=""))
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = shell_tools.shell(command, timeout=53)
    assert result == "ok"
    runner.assert_called_once_with(shlex.split(command), capture_output=True, text=True, timeout=53)
    assert_record(gateway, command, "allowed")


@pytest.mark.parametrize("command", [
    "flock /temporary/lock -c 'git push'",
    "watch 'git push'",
    "script -c 'git push' /temporary/typescript",
    "watch \"git push 'unterminated\"",
])
def test_approved_quoted_single_string_wrapped_git_gets_isolation(gateway, monkeypatch, command):
    """Fix for the residual bug found during WP2.1 group 1 closeout
    scoping: a `-c`/single-string wrapper dispatch shape hands the
    wrapped git command to the wrapper as ONE already-quoted argv token
    (e.g. `'git push'`), so a plain Path(token).name check on args[1:]
    never matches it (`Path('git push').name == 'git push'`, not
    `'git'`). These commands already classify HIGH_IMPACT (confirmation
    required either way), but without this fix executed with no git-env
    isolation (hooks/gpgsign/fsmonitor not neutralized). The last case
    has malformed quoting inside the single-string token itself (its own
    shlex.split() raises ValueError), pinning _argv_token_hits_git()'s
    whitespace-.split() fallback -- without that fallback (an earlier,
    narrower version of the fix that returned False on ValueError
    instead) this specific case stays un-isolated even after the main
    fix. Discriminating: asserts the exact env object the mocked
    shell_git_environment() returns is what's passed through, not just
    that some `env` kwarg is present.
    """
    sentinel = {"SENTINEL": "1"}
    prompt = Mock(return_value=True)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="ok\n", stderr=""))
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    monkeypatch.setattr(shell_tools, "shell_git_environment", lambda: sentinel)
    result = shell_tools.shell(command, timeout=53)
    assert result == "ok"
    call_kwargs = runner.call_args.kwargs
    assert runner.call_args.args == (shlex.split(command),)
    assert call_kwargs["env"] is sentinel
    assert_record(gateway, command, "allowed")


@pytest.mark.parametrize("command", [
    "flock /temporary/lock -c 'helper push'",
    "watch 'helper push'",
])
def test_approved_quoted_single_string_wrapped_non_git_gets_no_isolation(gateway, monkeypatch, command):
    """Negative companion to the fix above: a single-string wrapped
    command that does NOT contain a git/git-* basename among its
    sub-tokens must not pick up env isolation -- guards against the new
    shlex-split-the-token path over-applying beyond actual git
    basenames."""
    prompt = Mock(return_value=True)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="ok\n", stderr=""))
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = shell_tools.shell(command, timeout=53)
    assert result == "ok"
    runner.assert_called_once_with(shlex.split(command), capture_output=True, text=True, timeout=53)
    assert_record(gateway, command, "allowed")


@pytest.mark.parametrize("command", ["find . -name '*.py'", "env helper", "xargs helper"])
@pytest.mark.parametrize("caller", ["agent", "daemon"])
def test_agent_and_daemon_refuse_utilities(gateway, monkeypatch, command, caller):
    runner, prompt = Mock(), Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    if caller == "agent":
        result = agent.TOOLS["shell"]({"command": command})
    else:
        executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
        result = executor._daemon_shell(command)
    assert result.startswith("[BLOCKED]")
    runner.assert_not_called()
    prompt.assert_not_called()
    if caller == "daemon" and command.startswith("xargs"):
        assert result == "[BLOCKED] Daemon mode will not run 'xargs helper' without explicit authorization. Add the command prefix to _DAEMON_ALLOWED_PREFIXES in core/task_executor.py to enable it."
        row = json.loads(gateway.audit.read_text())
        assert row["authority"] == HIGH_IMPACT and row["action"] == "task_executor.daemon_shell" and row["outcome"] == "refused"
        assert len(gateway.audit.read_text().splitlines()) == 1
    else:
        assert_record(gateway, command, "refused")


# G15d D-2 (deliberate update, was test_daemon_bare_env_remains_read): the
# daemon admits the `env` prefix but shell() now classifies every env form
# HIGH_IMPACT, so it is refused with no spawn. The refusal row is written by
# shell() (action shell_tools.shell), not by _daemon_shell's prefix check.
def test_daemon_env_is_always_refused(gateway, monkeypatch):
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="temporary environment", stderr=""))
    prompt = Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert executor._daemon_shell("env").startswith("[BLOCKED]")
    runner.assert_not_called()
    prompt.assert_not_called()
    rows = [json.loads(line) for line in gateway.audit.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["authority"] == HIGH_IMPACT and rows[0]["outcome"] == "refused"
    assert rows[0]["action"] == "shell_tools.shell"


@pytest.mark.parametrize("command", ["find .", "env helper", "xargs helper"])
def test_execute_tool_refusal_has_no_episodic_success(gateway, monkeypatch, command):
    import core.memory_v2 as memory_module

    log = Mock()
    monkeypatch.setattr(memory_module.memory, "log_action", log)
    monkeypatch.setattr(agent, "_get_learning", Mock(return_value=Mock()))
    monkeypatch.setattr(agent, "show_shell", Mock())
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    runner = Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    result = agent.execute_tool({"name": "shell", "args": {"command": command}})
    assert result.startswith("[BLOCKED]")
    log.assert_not_called()
    runner.assert_not_called()
    assert_record(gateway, command, "refused")


def test_sink_failure_preserves_refusal(gateway, tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("unchanged")
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: ActionGateway(audit_file=blocker / "audit.jsonl"))
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", False)
    runner = Mock()
    monkeypatch.setattr(shell_tools.subprocess, "run", runner)
    assert shell_tools.shell("env helper").startswith("[BLOCKED]")
    runner.assert_not_called()
    assert blocker.read_text() == "unchanged"
