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
    monkeypatch.setattr(shell_tools, "_execute_shell_command", execute)
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
        return "original result"

    monkeypatch.setattr(shell_tools, "_execute_shell_command", execute)
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
    monkeypatch.setattr(shell_tools, "_execute_shell_command", execute)
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
    monkeypatch.setattr(shell_tools, "_execute_shell_command", execute)
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
    execute = Mock(return_value="original output")
    monkeypatch.setattr(shell_tools, "ask_confirm", prompt)
    monkeypatch.setattr(shell_tools, "warning", warning)
    monkeypatch.setattr(shell_tools, "_execute_shell_command", execute)
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
    execute = Mock(return_value="original output")
    monkeypatch.setattr(shell_tools, "shell", delegate)
    monkeypatch.setattr(shell_tools, "_execute_shell_command", execute)
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
    monkeypatch.setattr(shell_tools, "_execute_shell_command", Mock(return_value="original output"))
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
