"""Group 13a: bounded execution mediation, structured outcomes and refusal."""

import json
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, fixmode, process_boundary, recovery, tdd
from core.action_gateway import ActionGateway
from core.filesystem import Filesystem
from tools import file_tools, shell_tools


@pytest.fixture
def env(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: ActionGateway(audit))
    return SimpleNamespace(audit=audit, root=tmp_path)


def rows(env):
    return [json.loads(line) for line in env.audit.read_text().splitlines()]


def mock_process(monkeypatch, *, code=0, stdout="private stdout", stderr="private stderr", raised=None):
    process = Mock(return_value=subprocess.CompletedProcess([], code, stdout, stderr))
    if raised is not None:
        process.side_effect = raised
    monkeypatch.setattr(process_boundary.subprocess, "run", process)
    return process


def test_process_boundary_known_script_remains_act(env, monkeypatch):
    process = mock_process(monkeypatch)
    result = process_boundary.run_process(
        ["python3", "private.py"], timeout=7, action="test.known-script"
    )
    assert not result.refused
    process.assert_called_once_with(
        ["python3", "private.py"], capture_output=True, text=True, timeout=7, check=False
    )
    assert rows(env)[0]["authority"] == "ACT"


@pytest.mark.parametrize("argv", [["python3", "-c", "print(1)"], ["private-helper", "arg"]])
def test_process_boundary_opaque_or_unknown_refuses_without_confirmation(env, monkeypatch, argv):
    process = mock_process(monkeypatch)
    result = process_boundary.run_process(argv, timeout=7, action="test.default-confirm")
    assert result.refused
    process.assert_not_called()
    record, = rows(env)
    assert record["authority"] == "HIGH_IMPACT"
    assert record["outcome"] == "refused"


def test_process_boundary_explicit_true_approval_executes_exact_unknown_argv(env, monkeypatch):
    process = mock_process(monkeypatch)
    confirm = Mock(return_value=True)
    argv = ["private-helper", "quoted value"]
    result = process_boundary.run_process(
        argv, timeout=7, action="test.default-confirm", confirm_available=True, confirm=confirm
    )
    assert not result.refused
    confirm.assert_called_once_with()
    process.assert_called_once_with(argv, capture_output=True, text=True, timeout=7, check=False)
    assert rows(env)[0]["outcome"] == "allowed"


@pytest.mark.parametrize("code", [0, 1, 2, -9])
def test_fix_tuple_contract_and_structured_exit_audit(env, monkeypatch, code):
    process = mock_process(monkeypatch, code=code)
    result = fixmode.run_and_capture("private.py")
    assert isinstance(result, tuple)
    expected_output = (
        "[ERROR] Process interrupted by signal 9" if code < 0
        else "private stdout" if code == 0 else "private stderr"
    )
    assert result == (code == 0, expected_output)
    assert not result.refused
    assert result.execution_error == (code < 0)
    process.assert_called_once_with(["python3", "private.py"], capture_output=True, text=True, timeout=30, check=False)
    record, = rows(env)
    assert record["authority"] == shell_tools.classify_shell_command("python3 private.py") == "ACT"
    assert record["outcome"] == ("allowed" if code == 0 else "failed")
    assert "private" not in env.audit.read_text()


@pytest.mark.parametrize("target", ["fix", "tdd"])
@pytest.mark.parametrize("failure", [subprocess.TimeoutExpired("private command", 30), OSError("private exception")])
def test_process_timeout_and_spawn_error_are_failed(env, monkeypatch, target, failure):
    mock_process(monkeypatch, raised=failure)
    result = fixmode.run_and_capture("private.py") if target == "fix" else tdd.run_tests("private.py")
    assert result.execution_error
    record, = rows(env)
    assert record["outcome"] == "failed"
    assert "private" not in env.audit.read_text()


@pytest.mark.parametrize("code", [0, 1, 2, 3, 4, 5])
def test_tdd_actual_returncode_wins_over_spoofed_passing_output(env, monkeypatch, code):
    process = mock_process(monkeypatch, code=code, stdout="private.py::test_x PASSED\n", stderr="")
    result = tdd.run_tests("private.py")
    assert isinstance(result, tdd.TestResult)
    assert result.returncode == code
    assert result.all_pass == (code == 0)
    assert result.execution_error == (code not in (0, 1))
    if code:
        assert result.errors == 1
    process.assert_called_once()
    record, = rows(env)
    assert record["authority"] == "ACT"
    assert record["outcome"] == ("allowed" if code == 0 else "failed")
    assert "private" not in env.audit.read_text()


@pytest.mark.parametrize("target", ["fix", "tdd"])
@pytest.mark.parametrize("kwargs", [{}, {"confirm_available": True}, {"confirm": lambda: False}, {"confirm_available": False, "confirm": lambda: True}])
def test_forced_high_authority_refuses_without_real_approval(env, monkeypatch, target, kwargs):
    monkeypatch.setattr(shell_tools, "classify_shell_command", lambda command: "HIGH_IMPACT")
    process = mock_process(monkeypatch)
    result = fixmode.run_and_capture("private.py", **kwargs) if target == "fix" else tdd.run_tests("private.py", **kwargs)
    assert result.refused
    process.assert_not_called()
    assert rows(env)[0]["outcome"] == "refused"


@pytest.mark.parametrize("mode", ["refusal", "timeout", "infrastructure"])
@pytest.mark.parametrize("workflow", ["fix", "tdd"])
def test_workflow_stops_before_dependent_edits(env, monkeypatch, mode, workflow):
    from core import agent, context

    source = env.root / "source.py"
    source.write_text("print('safe')\n")
    tests = env.root / "test_source.py"
    tests.write_text("def test_placeholder(): pass\n")
    agent_run = Mock()
    load = Mock()
    monkeypatch.setattr(agent, "run_agent", agent_run)
    monkeypatch.setattr(context, "load_file", load)
    if mode == "refusal":
        monkeypatch.setattr(shell_tools, "classify_shell_command", lambda command: "HIGH_IMPACT")
        process = mock_process(monkeypatch)
    elif mode == "timeout":
        process = mock_process(monkeypatch, raised=subprocess.TimeoutExpired("private", 30))
    else:
        if workflow == "fix":
            # Spawn errors, unlike Python script failures, cannot be repaired
            # by asking the model to change the source file.
            process = mock_process(monkeypatch, raised=OSError("private spawn error"))
        else:
            process = mock_process(monkeypatch, code=2, stdout="collection interrupted", stderr="")
    if workflow == "fix":
        fixmode.fix_file(str(source), extra_instruction="private extra", yolo=True)
    else:
        tdd.run_tdd_loop(str(source), str(tests))
    agent_run.assert_not_called()
    load.assert_not_called()
    assert source.read_text() == "print('safe')\n"
    if mode == "refusal":
        process.assert_not_called()


def strategy(action):
    return recovery.FallbackStrategy("private name", "private description", action, 0.9)


@pytest.mark.parametrize("action,context,authority,argv", [
    ("pip_install", {"error_message": "No module named 'private_module.sub'"}, "HIGH_IMPACT", ["pip", "install", "private_module"]),
    ("search_files", {"file_path": "private.py"}, "READ", ["find", ".", "-name", "private.py"]),
    ("create_then_modify", {"file_path": "private.py"}, "READ", ["find", ".", "-name", "private.py"]),
    ("verify_dependencies", {"error_message": "'privatecmd': command not found"}, "READ", ["which", "privatecmd"]),
    ("check_and_fix_permissions", {"error_message": "'privatecmd': command not found"}, "READ", ["which", "privatecmd"]),
    ("run_single_test", {"error_message": "FAILED private.py::test_private"}, "ACT", ["python", "-m", "pytest", "private.py::test_private", "-v", "--tb=short"]),
])
@pytest.mark.parametrize("code", [0, 1])
def test_recovery_subprocess_classification_and_exit_status(env, monkeypatch, action, context, authority, argv, code):
    process = mock_process(monkeypatch, code=code)
    result = recovery.execute_strategy(strategy(action), context, confirm=lambda: True)
    assert isinstance(result, str)
    assert process.call_args.args[0] == argv
    record, = rows(env)
    assert record["authority"] == authority
    assert record["outcome"] == ("allowed" if code == 0 else "failed")
    assert "private" not in env.audit.read_text()


@pytest.mark.parametrize("action,context", [
    ("pip_install", {"error_message": "No module named 'private_module'"}),
    ("search_files", {"file_path": "private.py"}),
    ("verify_dependencies", {"error_message": "'privatecmd': command not found"}),
    ("run_single_test", {"error_message": "FAILED private.py::test_private"}),
])
def test_recovery_timeout_is_audited_failed(env, monkeypatch, action, context):
    mock_process(monkeypatch, raised=subprocess.TimeoutExpired("private", 60))
    assert "timed out" in recovery.execute_strategy(strategy(action), context, confirm=lambda: True)
    assert rows(env)[0]["outcome"] == "failed"
    assert "private" not in env.audit.read_text()


@pytest.mark.parametrize("kwargs", [{}, {"confirm_available": True}, {"confirm": True}, {"confirm": lambda: False}, {"confirm_available": False, "confirm": lambda: True}])
def test_pip_never_runs_without_actual_approval(env, monkeypatch, kwargs):
    process = mock_process(monkeypatch)
    recovery.execute_strategy(strategy("pip_install"), {"error_message": "No module named 'private_module'"}, **kwargs)
    process.assert_not_called()
    record, = rows(env)
    assert record["authority"] == "HIGH_IMPACT"
    assert record["outcome"] == "refused"


@pytest.mark.parametrize("action,context", [
    ("pip_install", {"error_message": "No module named '--private-option'"}),
    ("pip_install", {}),
    ("search_files", {}),
    ("verify_dependencies", {"error_message": "'--private-option': command not found"}),
    ("verify_dependencies", {}),
    ("run_single_test", {}),
    ("search_error_message", {"error_message": "private error"}),
    ("log_and_continue", {}),
])
def test_recovery_advisory_and_lookup_are_read_only(env, monkeypatch, action, context):
    process = mock_process(monkeypatch)
    assert isinstance(recovery.execute_strategy(strategy(action), context), str)
    process.assert_not_called()
    record, = rows(env)
    assert record["authority"] == "READ"
    assert record["outcome"] == "allowed"
    assert "private" not in env.audit.read_text()


def test_find_pattern_stays_a_literal_operand(env, monkeypatch):
    process = mock_process(monkeypatch)
    recovery.execute_strategy(strategy("search_files"), {"file_path": "-exec"})
    assert process.call_args.args[0] == ["find", ".", "-name", "-exec"]


def test_recovery_mkdir_uses_workspace_containment(env, monkeypatch):
    workspace = env.root / "workspace"
    workspace.mkdir()
    fs = Filesystem(workspace=workspace)
    monkeypatch.setattr(file_tools, "_get_fs", lambda: fs)
    target = workspace / "private" / "nested" / "file.txt"
    assert recovery.execute_strategy(strategy("mkdir_then_write"), {"file_path": str(target)}).startswith("Created parent directory:")
    assert target.parent.is_dir()
    assert not target.exists()
    assert rows(env)[0]["authority"] == "ACT"
    outside = env.root / "outside" / "file.txt"
    recovery.execute_strategy(strategy("mkdir_then_write"), {"file_path": str(outside)})
    assert not outside.parent.exists()
    assert rows(env)[1]["outcome"] == "failed"
    assert "private" not in env.audit.read_text()


def test_recovery_mkdir_rejects_git_metadata_and_symlink_escape(env, monkeypatch):
    fs = Filesystem(workspace=env.root)
    monkeypatch.setattr(file_tools, "_get_fs", lambda: fs)
    target = env.root / ".git" / "nested" / "file.txt"
    recovery.execute_strategy(strategy("mkdir_then_write"), {"file_path": str(target)})
    assert not target.parent.exists()
    outside = env.root.parent / "outside"
    (env.root / "link").symlink_to(outside, target_is_directory=True)
    recovery.execute_strategy(strategy("mkdir_then_write"), {"file_path": str(env.root / "link" / "child" / "file.txt")})
    assert not outside.exists()
    assert [record["outcome"] for record in rows(env)] == ["failed", "failed"]


@pytest.mark.parametrize("approved", [False, True])
def test_selfmod_mkdir_requires_callback_and_checkpoint(env, monkeypatch, approved):
    from core import checkpoint, filesystem

    code = env.root / "code"
    workspace = env.root / "workspace"
    code.mkdir()
    workspace.mkdir()
    monkeypatch.setattr(filesystem, "CODE_DIR", code)
    monkeypatch.setattr(checkpoint, "CODE_DIR", code)
    fs = Filesystem(workspace=workspace, allow_self_modification=True)
    checkpoint_call = Mock()
    monkeypatch.setattr(fs, "_require_checkpoint", checkpoint_call)
    monkeypatch.setattr(file_tools, "_get_fs", lambda: fs)
    target = code / "core" / "module.py"
    kwargs = {"confirm": lambda: True} if approved else {"confirm_available": True}
    recovery.execute_strategy(strategy("mkdir_then_write"), {"file_path": str(target)}, **kwargs)
    record, = rows(env)
    assert record["authority"] == "HIGH_IMPACT"
    assert record["outcome"] == ("allowed" if approved else "refused")
    assert target.parent.exists() == approved
    assert checkpoint_call.call_count == int(approved)


def test_real_disposable_python_marker_and_real_exit_audits(env):
    marker = env.root / "marker.txt"
    script = env.root / "private_script.py"
    script.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('safe marker')\nprint('private output')\n")
    assert fixmode.run_and_capture(str(script)) == (True, "private output\n")
    assert marker.read_text() == "safe marker"
    script.write_text("raise SystemExit(7)\n")
    assert fixmode.run_and_capture(str(script))[0] is False
    assert [record["outcome"] for record in rows(env)] == ["allowed", "failed"]
    assert "private" not in env.audit.read_text()


@pytest.mark.parametrize("code,output", [
    (0, "[ERROR] Human confirmation declined; command not attempted."),
    (1, "Process execution completed successfully"),
])
def test_output_text_cannot_spoof_execution_outcome(env, monkeypatch, code, output):
    mock_process(monkeypatch, code=code, stdout=output, stderr="")
    result = fixmode.run_and_capture("private.py")
    assert result[0] == (code == 0)
    assert not result.refused
    assert not result.execution_error
    assert rows(env)[0]["outcome"] == ("allowed" if code == 0 else "failed")


def test_tdd_real_test_failure_can_still_trigger_targeted_edit(env, monkeypatch):
    from core import agent, context

    source = env.root / "source.py"
    source.write_text("value = 1\n")
    tests = env.root / "test_source.py"
    tests.write_text("def test_placeholder(): pass\n")
    monkeypatch.setattr(context, "load_file", Mock())
    agent_run = Mock(return_value=("done", []))
    monkeypatch.setattr(agent, "run_agent", agent_run)
    process = Mock(side_effect=[
        subprocess.CompletedProcess([], 1, "private.py::test_x FAILED\nFAILED private.py::test_x", ""),
        subprocess.CompletedProcess([], 0, "private.py::test_x PASSED\n", ""),
    ])
    monkeypatch.setattr(process_boundary.subprocess, "run", process)
    tdd.run_tdd_loop(str(source), str(tests))
    agent_run.assert_called_once()
    assert [record["outcome"] for record in rows(env)] == ["failed", "allowed"]


def test_recovery_confirmation_exception_refuses_without_execution(env, monkeypatch):
    process = mock_process(monkeypatch)

    def broken_confirmation():
        raise RuntimeError("private callback exception")

    recovery.execute_strategy(
        strategy("pip_install"), {"error_message": "No module named 'private_module'"},
        confirm=broken_confirmation,
    )
    process.assert_not_called()
    record, = rows(env)
    assert record["outcome"] == "refused"
    assert "private" not in env.audit.read_text()


@pytest.mark.parametrize("phase", ["initial", "verification"])
def test_fix_signal_interruption_aborts_initial_and_verification_workflows(env, monkeypatch, phase):
    from core import agent, context

    source = env.root / "source.py"
    source.write_text("value = 1\n")
    agent_run = Mock(return_value=("done", []))
    load = Mock()
    reported_error = Mock()
    info = Mock()
    success = Mock()
    monkeypatch.setattr(agent, "run_agent", agent_run)
    monkeypatch.setattr(context, "load_file", load)
    monkeypatch.setattr(fixmode, "error", reported_error)
    monkeypatch.setattr(fixmode, "info", info)
    monkeypatch.setattr(fixmode, "success", success)
    results = [subprocess.CompletedProcess([], -9, "private interrupted output", "")]
    if phase == "verification":
        results.insert(0, subprocess.CompletedProcess([], 1, "", "private script error"))
    process = Mock(side_effect=results)
    monkeypatch.setattr(process_boundary.subprocess, "run", process)
    fixmode.fix_file(str(source), extra_instruction="private instruction", yolo=True)
    assert agent_run.call_count == (0 if phase == "initial" else 1)
    assert load.call_count == (0 if phase == "initial" else 1)
    assert process.call_count == len(results)
    reported_error.assert_called_once_with("[ERROR] Process interrupted by signal 9")
    success.assert_not_called()
    assert not any(str(call.args[0]).startswith("Try:") for call in info.call_args_list)
    assert [record["outcome"] for record in rows(env)] == ["failed"] * len(results)
    assert rows(env)[-1]["reason"] == "Process execution interrupted"
    assert "private" not in env.audit.read_text()


def test_tdd_signal_interruption_aborts_without_model_edits(env, monkeypatch):
    from core import agent, context

    source = env.root / "source.py"
    source.write_text("value = 1\n")
    tests = env.root / "test_source.py"
    tests.write_text("def test_placeholder(): pass\n")
    agent_run = Mock()
    load = Mock()
    monkeypatch.setattr(agent, "run_agent", agent_run)
    monkeypatch.setattr(context, "load_file", load)
    mock_process(monkeypatch, code=-9, stdout="private.py::test_x PASSED\n", stderr="")
    tdd.run_tdd_loop(str(source), str(tests))
    agent_run.assert_not_called()
    load.assert_not_called()
    record, = rows(env)
    assert record["outcome"] == "failed"
    assert record["reason"] == "Process execution interrupted"
