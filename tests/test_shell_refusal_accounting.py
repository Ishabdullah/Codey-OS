"""Shell UI/daemon refusal accounting; redirect all state before collection."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, agent, task_executor
from core.action_gateway import ACT, HIGH_IMPACT, READ, ActionGateway
from tools import shell_tools
from utils.config import AGENT_CONFIG

DECLINED = "Human confirmation declined; command not attempted."
INTERRUPTED = "Human confirmation unavailable or interrupted; command not attempted."
FAILED = "Human confirmation unavailable due to callback failure; command not attempted."
CANCELLED = "[CANCELLED] User declined to run command."


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    instance = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: instance)
    monkeypatch.setattr(shell_tools, "get_action_gateway", lambda: instance)
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", True)
    return SimpleNamespace(instance=instance, audit=audit)


def record(gateway, *, authority, action, command, outcome, reason):
    rows = [json.loads(line) for line in gateway.audit.read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert isinstance(row.pop("ts"), float)
    assert row == {
        "authority": authority, "action": action, "command": command,
        "outcome": outcome, "reason": reason,
    }


@pytest.mark.parametrize("authority", [READ, ACT, HIGH_IMPACT])
def test_refuse_exec_shape(gateway, authority):
    decision = gateway.instance.refuse_exec(
        authority=authority, action="test.refusal", command="attempt", reason="existing UI rejection",
    )
    assert decision.outcome == "refused" and not decision.allowed
    assert decision.detail == {"action": "test.refusal", "command": "attempt"}
    record(gateway, authority=authority, action="test.refusal", command="attempt", outcome="refused", reason="existing UI rejection")


def test_refuse_exec_unknown_authority(gateway):
    with pytest.raises(ValueError, match="Unknown authority class"):
        gateway.instance.refuse_exec(authority="unknown", action="test", command="attempt", reason="denied")
    assert not gateway.audit.exists()


@pytest.mark.parametrize("sink", ["parent", "open"])
def test_refuse_exec_sink_failure_preserves_refusal(gateway, tmp_path, monkeypatch, sink):
    if sink == "parent":
        blocker = tmp_path / "blocker"
        blocker.write_text("blocker")
        instance = ActionGateway(audit_file=blocker / "audit.jsonl")
    else:
        instance = gateway.instance
        monkeypatch.setattr("builtins.open", Mock(side_effect=OSError("sink failed")))
    decision = instance.refuse_exec(authority=ACT, action="test", command="attempt", reason="denied")
    assert decision.outcome == "refused" and decision.reason == "denied"


@pytest.mark.parametrize("command", ["pwd", "echo safe", "git reset --hard HEAD"])
@pytest.mark.parametrize("answer", [False, "yes", None, 1])
def test_decline_is_one_refusal_not_execution(gateway, monkeypatch, command, answer):
    prompt = Mock(return_value=answer)
    execute = Mock(side_effect=AssertionError("decline cannot execute"))
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools, "_run_shell_command_structured", execute)
    monkeypatch.setattr(shell_tools, "warning", Mock())
    assert shell_tools.shell(command) == CANCELLED
    prompt.assert_called_once_with(f"Run shell command: `{command}`?")
    execute.assert_not_called()
    record(gateway, authority=shell_tools.classify_shell_command(command), action="shell_tools.shell", command=command, outcome="refused", reason=DECLINED)


@pytest.mark.parametrize("command", ["pwd", "echo safe", "cp source target", "git reset --hard HEAD"])
def test_approval_once_and_execution_only_thunk(gateway, monkeypatch, command):
    order = []
    original_gate = gateway.instance.gate_exec

    def gate(**kwargs):
        order.append("gate")
        return original_gate(**kwargs)

    monkeypatch.setattr(gateway.instance, "gate_exec", gate)
    monkeypatch.setattr(shell_tools, "ask_confirm", lambda prompt: order.append("prompt") or True)
    monkeypatch.setattr(shell_tools, "warning", lambda message: order.append("warning"))

    def execute(actual, timeout):
        assert actual == command and timeout == 23
        order.append("execute")
        return shell_tools._ShellExecResult("original result", "ok")

    monkeypatch.setattr(shell_tools, "_run_shell_command_structured", execute)
    assert shell_tools.shell(command, timeout=23) == "original result"
    if shell_tools.classify_shell_command(command) == HIGH_IMPACT:
        assert order == ["gate", "warning", "prompt", "execute"]
    elif shell_tools.is_dangerous(command):
        assert order == ["warning", "prompt", "gate", "execute"]
    else:
        assert order == ["prompt", "gate", "execute"]
    record(gateway, authority=shell_tools.classify_shell_command(command), action="shell_tools.shell", command=command, outcome="allowed", reason="command executed")


@pytest.mark.parametrize("command", ["pwd", "echo safe", "git reset --hard HEAD"])
@pytest.mark.parametrize("exception", [EOFError(), KeyboardInterrupt(), RuntimeError("private prompt exception")])
def test_prompt_errors_are_static_refusals(gateway, monkeypatch, command, exception):
    prompt = Mock(side_effect=exception)
    execute = Mock(side_effect=AssertionError("prompt failure cannot execute"))
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools, "_run_shell_command_structured", execute)
    monkeypatch.setattr(shell_tools, "warning", Mock())
    reason = INTERRUPTED if isinstance(exception, (EOFError, KeyboardInterrupt)) else FAILED
    assert shell_tools.shell(command) == f"[BLOCKED] {reason}"
    prompt.assert_called_once()
    execute.assert_not_called()
    record(gateway, authority=shell_tools.classify_shell_command(command), action="shell_tools.shell", command=command, outcome="refused", reason=reason)
    assert "private prompt exception" not in gateway.audit.read_text()


@pytest.mark.parametrize("yolo", [False, True])
def test_high_impact_without_path_refuses_before_warning(gateway, monkeypatch, yolo):
    # False config or YOLO independently remove the confirmation path.
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", yolo)
    warning = Mock()
    prompt = Mock()
    execute = Mock()
    monkeypatch.setattr(shell_tools, "warning", warning)
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools, "_run_shell_command_structured", execute)
    command = "git reset --hard HEAD"
    result = shell_tools.shell(command, yolo=yolo)
    assert result.startswith("[BLOCKED]") and "no confirmation path available" in result
    warning.assert_not_called()
    prompt.assert_not_called()
    execute.assert_not_called()
    record(gateway, authority=HIGH_IMPACT, action="shell_tools.shell", command=command, outcome="refused", reason=result.removeprefix("[BLOCKED] "))


@pytest.mark.parametrize(
    ("command", "config", "yolo", "prompted", "warned"),
    [("cp source target", False, False, True, True), ("echo safe", False, False, False, False), ("pwd", True, True, False, False), ("cp source target", True, True, False, True)],
)
def test_existing_read_act_prompt_choices(gateway, monkeypatch, command, config, yolo, prompted, warned):
    monkeypatch.setitem(AGENT_CONFIG, "confirm_shell", config)
    prompt = Mock(return_value=True)
    warning = Mock()
    execute = Mock(return_value=shell_tools._ShellExecResult("original output", "ok"))
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools, "warning", warning)
    monkeypatch.setattr(shell_tools, "_run_shell_command_structured", execute)
    assert shell_tools.shell(command, yolo=yolo, timeout=37) == "original output"
    assert prompt.call_count == int(prompted)
    assert warning.call_count == int(warned)
    execute.assert_called_once_with(command, 37)
    record(gateway, authority=shell_tools.classify_shell_command(command), action="shell_tools.shell", command=command, outcome="allowed", reason="command executed")


@pytest.mark.parametrize("command", ["", "  "])
def test_empty_command_stays_without_attempt(gateway, monkeypatch, command):
    prompt = Mock()
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    assert shell_tools.shell(command) == "[ERROR] Empty command"
    prompt.assert_not_called()
    assert not gateway.audit.exists()


def test_real_pwd_in_temporary_cwd(gateway, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shell_tools, "ask_confirm", Mock(return_value=True))
    assert shell_tools.shell("pwd", timeout=5) == str(tmp_path.resolve())
    record(gateway, authority=READ, action="shell_tools.shell", command="pwd", outcome="allowed", reason="command executed")


@pytest.mark.parametrize(
    ("command", "reason", "output", "warning"),
    [
        ("python", "Daemon Python/pip command pattern is not permitted.", "[BLOCKED] Daemon mode will not run 'python'. Only 'python script.py' and 'pip install package' are allowed.", "Daemon: blocked Python/pip command: python"),
        ("python -c secret", "Daemon Python/pip command contains a prohibited flag.", "[BLOCKED] Flag '-c' is not allowed in daemon mode.", "Daemon: blocked dangerous flag '-c' in: python -c secret"),
        ("git reset --hard HEAD", "Daemon command prefix is not permitted without explicit authorization.", "[BLOCKED] Daemon mode will not run 'git reset --hard HEAD' without explicit authorization. Add the command prefix to _DAEMON_ALLOWED_PREFIXES in core/task_executor.py to enable it.", "Daemon: blocked shell command: git reset --hard HEAD"),
        ("git push", "Daemon command prefix is not permitted without explicit authorization.", "[BLOCKED] Daemon mode will not run 'git push' without explicit authorization. Add the command prefix to _DAEMON_ALLOWED_PREFIXES in core/task_executor.py to enable it.", "Daemon: blocked shell command: git push"),
    ],
)
def test_each_daemon_refusal_one_audit_no_shell(gateway, monkeypatch, command, reason, output, warning):
    runner = Mock(side_effect=AssertionError("daemon denial must not call shell"))
    warnings = Mock()
    monkeypatch.setattr(shell_tools, "shell", runner)
    monkeypatch.setattr(task_executor, "warning", warnings)
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    assert executor._daemon_shell(command) == output
    runner.assert_not_called()
    warnings.assert_called_once_with(warning)
    record(gateway, authority=shell_tools.classify_shell_command(command), action="task_executor.daemon_shell", command=command, outcome="refused", reason=reason)


def test_accepted_daemon_delegates_once_single_shell_audit(gateway, monkeypatch):
    real_shell = shell_tools.shell
    delegate = Mock(wraps=real_shell)
    execute = Mock(return_value=shell_tools._ShellExecResult("original output", "ok"))
    monkeypatch.setattr(shell_tools, "shell", delegate)
    monkeypatch.setattr(shell_tools, "_run_shell_command_structured", execute)
    monkeypatch.setattr(shell_tools, "ask_confirm", Mock(side_effect=AssertionError("YOLO must not prompt")))
    executor = task_executor.TaskExecutor.__new__(task_executor.TaskExecutor)
    command = "  pwd  "
    assert executor._daemon_shell(command) == "original output"
    delegate.assert_called_once_with(command, yolo=True)
    execute.assert_called_once_with(command, 1800)
    record(gateway, authority=READ, action="shell_tools.shell", command=command, outcome="allowed", reason="command executed")


@pytest.mark.parametrize("approved", [False, True])
def test_execute_tool_cancelled_is_not_episodic_success(gateway, monkeypatch, approved):
    import core.memory_v2 as memory_module

    log = Mock()
    monkeypatch.setattr(memory_module.memory, "log_action", log)
    learning = Mock()
    monkeypatch.setattr(agent, "_get_learning", lambda: learning)
    display = Mock()
    monkeypatch.setattr(agent, "show_shell", display)
    monkeypatch.setitem(agent.TOOLS, "shell", lambda args: shell_tools.shell(args["command"]))
    monkeypatch.setattr(shell_tools, "ask_confirm", Mock(return_value=approved))
    monkeypatch.setattr(shell_tools, "_run_shell_command_structured", Mock(return_value=shell_tools._ShellExecResult("original output", "ok")))
    command = "pwd"
    result = agent.execute_tool({"name": "shell", "args": {"command": command}})
    assert result == ("original output" if approved else CANCELLED)
    display.assert_called_once_with(command, result, error=False)
    assert agent.is_error(CANCELLED, "shell") is False
    learning.record_error.assert_not_called()
    if approved:
        log.assert_called_once_with("shell", "original output")
    else:
        log.assert_not_called()
    record(gateway, authority=READ, action="shell_tools.shell", command=command, outcome="allowed" if approved else "refused", reason="command executed" if approved else DECLINED)


# ── NEW-874: shell execution-error fidelity ─────────────────────────────────


def test_real_nonzero_exit_is_exit_marked_and_audited_failed(gateway):
    command = "false"
    assert shell_tools.shell(command, yolo=True, timeout=5) == "[EXIT 1] (no output)"
    record(gateway, authority=shell_tools.classify_shell_command(command), action="shell_tools.shell", command=command, outcome="failed", reason="command exited with status 1")


def test_real_nonzero_exit_stderr_reaches_caller_not_ledger(gateway, tmp_path):
    # The sentinel lives in the *script's* stderr output, not in the
    # command text itself (the command text is legitimately audited —
    # that's the existing, unrelated "command" field) -- so this isolates
    # the leak check to exactly what NEW-874 changes: command OUTPUT must
    # stay out of the ledger, only the bounded reason string goes there.
    sentinel = "SENTINEL_NEW874_STDERR_ONLY"
    script = tmp_path / "fail.sh"
    script.write_text(f"#!/bin/sh\necho {sentinel} 1>&2\nexit 7\n")
    script.chmod(0o755)
    command = str(script)
    result = shell_tools.shell(command, yolo=True, timeout=5)
    assert result.startswith("[EXIT 7]")
    assert sentinel in result
    assert sentinel not in gateway.audit.read_text()
    record(gateway, authority=shell_tools.classify_shell_command(command), action="shell_tools.shell", command=command, outcome="failed", reason="command exited with status 7")


def test_real_missing_binary_unchanged_message_no_doubled_prefix(gateway):
    command = "definitely_not_a_real_binary_new874"
    result = shell_tools.shell(command, yolo=True, timeout=5)
    assert result == f"[ERROR] Command not found: {command}"
    record(gateway, authority=shell_tools.classify_shell_command(command), action="shell_tools.shell", command=command, outcome="failed", reason="command executable not found")


def test_real_timeout_unchanged_message(gateway):
    command = "sleep 5"
    result = shell_tools.shell(command, yolo=True, timeout=1)
    assert result == "[ERROR] Command timed out after 1s"
    record(gateway, authority=shell_tools.classify_shell_command(command), action="shell_tools.shell", command=command, outcome="failed", reason="command execution timed out")


def test_unexpected_exception_reason_bounded_no_leak(gateway, monkeypatch):
    sentinel_message = "SENTINEL_NEW874_OSERROR_TEXT"
    monkeypatch.setattr(
        shell_tools.subprocess, "run", Mock(side_effect=OSError(sentinel_message))
    )
    command = "echo irrelevant"
    result = shell_tools.shell(command, yolo=True, timeout=5)
    assert result == f"[ERROR] {sentinel_message}"
    ledger_text = gateway.audit.read_text()
    assert sentinel_message not in ledger_text
    record(gateway, authority=shell_tools.classify_shell_command(command), action="shell_tools.shell", command=command, outcome="failed", reason="command execution raised an unexpected exception")


# ── NEW-874 follow-up: classification must come from the structured
# side channel, never from sniffing the returned text. A real success
# (returncode == 0) whose own stdout happens to start with one of our
# own markers must NOT be reclassified as a failure. These reproduce the
# code-reviewer's exact probe lines (spoof-exit-ok / spoof-error-ok /
# spoof-timeout-ok / spoof-not-found-ok) against real subprocess runs,
# not mocks -- the whole point is that classification is now derived
# from subprocess.run()'s actual returncode, not from this text.
@pytest.mark.parametrize(
    "spoofed_text",
    [
        "[ERROR] hi",
        "[EXIT 1] fake",
        "[ERROR] Command timed out after 5s",
        "[ERROR] Command not found: nope",
    ],
)
def test_successful_command_with_spoofed_marker_stdout_is_not_misclassified(gateway, spoofed_text):
    command = f"echo '{spoofed_text}'"
    result = shell_tools.shell(command, yolo=True, timeout=5)
    assert result == spoofed_text
    record(gateway, authority=shell_tools.classify_shell_command(command), action="shell_tools.shell", command=command, outcome="allowed", reason="command executed")


def test_successful_command_with_huge_digit_lookalike_stdout_stays_bounded(gateway, tmp_path):
    # Bug 2 regression: the prior string-sniffing version sliced an
    # unbounded digit run out of stdout into the audit `reason` field.
    # The structured helper never parses stdout at all for classification,
    # so this is bounded by construction -- but kept as an explicit
    # regression test per the reviewer's ask rather than relying on that
    # being "obviously" true.
    payload = "[EXIT " + ("9" * 100_000) + "] not a real marker"
    huge_file = tmp_path / "huge.txt"
    huge_file.write_text(payload)
    command = f"cat {huge_file}"
    result = shell_tools.shell(command, yolo=True, timeout=5)
    assert result == payload
    ledger_text = gateway.audit.read_text()
    assert len(ledger_text) < 1000
    record(gateway, authority=shell_tools.classify_shell_command(command), action="shell_tools.shell", command=command, outcome="allowed", reason="command executed")


def test_negative_exit_status_from_signal_kill_is_recognized(gateway, tmp_path):
    script = tmp_path / "selfkill.sh"
    script.write_text("#!/bin/sh\nkill -9 $$\n")
    script.chmod(0o755)
    command = str(script)
    result = shell_tools.shell(command, yolo=True, timeout=5)
    assert result.startswith("[EXIT -9]")
    record(gateway, authority=shell_tools.classify_shell_command(command), action="shell_tools.shell", command=command, outcome="failed", reason="command exited with status -9")


def test_high_impact_approved_exit_failure_is_failed_not_refused(gateway, monkeypatch):
    monkeypatch.setattr(shell_tools, "ask_confirm", Mock(return_value=True))
    monkeypatch.setattr(shell_tools, "warning", Mock())
    monkeypatch.setattr(
        shell_tools, "_run_shell_command_structured",
        Mock(return_value=shell_tools._ShellExecResult("[EXIT 1] original output", "exit", 1)),
    )
    command = "git reset --hard HEAD"
    assert shell_tools.classify_shell_command(command) == HIGH_IMPACT
    result = shell_tools.shell(command)
    assert result == "[EXIT 1] original output"
    record(gateway, authority=HIGH_IMPACT, action="shell_tools.shell", command=command, outcome="failed", reason="command exited with status 1")


def test_structured_empty_args_has_its_own_kind_not_lumped_with_error():
    # shlex.split() reducing a non-blank command to zero tokens is not
    # reachable through shell()'s own public entry point (it already
    # short-circuits any blank/whitespace-only command before reaching
    # _run_shell_command_structured()), but the structured helper is
    # exercised directly here since its "empty" kind must stay distinct
    # from "error" (code-reviewer W3, NEW-874 round 3) — a blank command
    # is not an "unexpected exception".
    result = shell_tools._run_shell_command_structured("", timeout=5)
    assert result.kind == "empty"
    assert result.text == "[ERROR] Empty command"


def test_execute_tool_shell_exit_failure_known_gap_slips_into_episodic_memory(gateway, monkeypatch):
    """NEW-874 closed the audit-ledger fidelity gap (see
    test_high_impact_approved_exit_failure_is_failed_not_refused and the
    real-exit tests above: a nonzero shell exit is now truthfully audited
    outcome="failed"). It did NOT close the episodic-memory/display-layer
    gap this test pins: execute_tool() still logs a nonzero-exit shell
    result into episodic memory as if it succeeded, and is_error()/
    show_shell() still display it as a non-error. A round-2 attempt at
    closing this by matching result.startswith("[EXIT ") in execute_tool()
    was reverted on code-reviewer feedback — that is the same unsound
    text-sniffing class the audit-ledger fix exists to eliminate (a real
    success whose own stdout starts with "[EXIT " would be wrongly
    excluded). A real fix needs shell_tools._ShellExecResult's structured
    kind/code threaded out through TOOLS["shell"]/execute_tool, which is
    its own separate, logged NEW_ISSUES item. This test pins the current,
    known gap so it isn't silently reintroduced via a text-sniffing
    shortcut.
    """
    import core.memory_v2 as memory_module

    log = Mock()
    monkeypatch.setattr(memory_module.memory, "log_action", log)
    learning = Mock()
    monkeypatch.setattr(agent, "_get_learning", lambda: learning)
    display = Mock()
    monkeypatch.setattr(agent, "show_shell", display)
    monkeypatch.setitem(agent.TOOLS, "shell", lambda args: shell_tools.shell(args["command"]))
    monkeypatch.setattr(shell_tools, "ask_confirm", Mock(return_value=True))
    monkeypatch.setattr(
        shell_tools, "_run_shell_command_structured",
        Mock(return_value=shell_tools._ShellExecResult("[EXIT 1] boom", "exit", 1)),
    )
    command = "pwd"
    result = agent.execute_tool({"name": "shell", "args": {"command": command}})
    assert result == "[EXIT 1] boom"
    display.assert_called_once_with(command, result, error=False)
    assert agent.is_error(result, "shell") is False
    log.assert_called_once_with("shell", result[:100])
    record(gateway, authority=READ, action="shell_tools.shell", command=command, outcome="failed", reason="command exited with status 1")
