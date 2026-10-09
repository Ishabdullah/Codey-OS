"""Push mediation with isolated local Git only; bootstrap state before collection."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, git_execution, githelper
from core.action_gateway import HIGH_IMPACT, ActionGateway


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    instance = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: instance)
    return SimpleNamespace(instance=instance, audit=audit)


def record(gateway):
    records = [json.loads(line) for line in gateway.audit.read_text().splitlines()]
    assert len(records) == 1
    row = records[0]
    assert isinstance(row.pop("ts"), float)
    assert row["authority"] == HIGH_IMPACT
    assert row["action"] == "githelper.git_push"
    assert row["command"] == "git push attempt"
    assert set(row) == {"authority", "action", "command", "outcome", "reason"}
    return row


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
        return subprocess.run([git_execution._trusted_git_executable(), *args], cwd=cwd, capture_output=True, text=True, check=check)

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
    return SimpleNamespace(repo=repo, git=git, empty=empty)


def test_real_local_push_decline_then_approve(repository, gateway, tmp_path):
    r = repository
    remote = tmp_path / "local.git"
    r.git("init", "--bare", str(remote))
    r.git("config", "core.hooksPath", str(r.empty), cwd=remote)
    r.git("remote", "add", "origin", str(remote))
    r.git("config", "branch.main.remote", "origin")
    r.git("config", "branch.main.merge", "refs/heads/main")
    assert githelper.git_push(str(r.repo), confirm=lambda: False).startswith("[ERROR] Git push refused:")
    assert r.git("show-ref", cwd=remote, check=False).returncode == 1
    assert record(gateway)["outcome"] == "refused"
    gateway.audit.unlink()
    confirm = Mock(return_value=True)
    assert githelper.git_push(str(r.repo), confirm=confirm) == "Pushed successfully."
    confirm.assert_called_once_with()
    assert r.git("rev-parse", "refs/heads/main", cwd=remote).stdout == r.git("rev-parse", "HEAD").stdout
    assert (remote / "refs/heads/main").exists()
    assert record(gateway)["outcome"] == "allowed"
    assert str(remote) not in gateway.audit.read_text()
    assert "local content" not in gateway.audit.read_text()


def test_real_no_destination_preserves_failure(repository, gateway, monkeypatch):
    r = repository
    expected = r.git("push", check=False)
    assert expected.returncode != 0
    monkeypatch.chdir(r.repo)
    result = githelper.git_push(confirm=lambda: True)
    assert result == f"[ERROR] {expected.stderr.strip()}"
    assert record(gateway)["reason"] == result
    assert record(gateway)["outcome"] == "failed"


@pytest.mark.parametrize("stdout", ["  pushed output\n", ""])
def test_exact_push_argv_result(gateway, monkeypatch, stdout):
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout=stdout, stderr="private stderr"))
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    assert githelper.git_push("/temporary/repo", confirm=lambda: True) == (stdout.strip() or "Pushed successfully.")
    runner.assert_called_once_with([git_execution._trusted_git_executable(), "push"], capture_output=True, text=True, cwd="/temporary/repo")
    assert record(gateway)["outcome"] == "allowed"
    assert "private stderr" not in gateway.audit.read_text()


def test_no_callback_never_executes(gateway, monkeypatch):
    runner = Mock(side_effect=AssertionError("no execution"))
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    assert githelper.git_push().startswith("[ERROR] Git push refused:")
    runner.assert_not_called()
    assert "no confirmation path available" in record(gateway)["reason"]


def test_original_exception_is_preserved(gateway, monkeypatch):
    original = OSError("original subprocess error")
    runner = Mock(side_effect=original)
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    with pytest.raises(OSError) as caught:
        githelper.git_push(confirm=lambda: True)
    assert caught.value is original
    runner.assert_called_once()
    assert record(gateway)["outcome"] == "failed"
    assert record(gateway)["reason"] == str(original)


def test_push_survives_blocked_audit(gateway, monkeypatch, tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("blocker")
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: ActionGateway(audit_file=blocker / "audit.jsonl"))
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    assert githelper.git_push(confirm=lambda: True) == "Pushed successfully."
    runner.assert_called_once()
    assert blocker.read_text() == "blocker"


@pytest.fixture
def private_main(monkeypatch):
    import core

    source = Path(__file__).resolve().parents[1] / "main.py"
    with monkeypatch.context() as imports:
        imports.setattr(sys, "path", list(sys.path))
        for name, attrs in {
            "context": {}, "dashboard_data": {"get_render_text": Mock()},
            "inference_v2": {"was_last_streamed": Mock()},
            "loader_v2": {"get_loader": Mock()}, "sysmon": {"get_monitor": Mock()},
        }.items():
            stub = ModuleType(f"core.{name}")
            stub.__dict__.update(attrs)
            imports.setitem(sys.modules, f"core.{name}", stub)
            imports.setattr(core, name, stub, raising=False)
        spec = importlib.util.spec_from_file_location("_push_test_main", source)
        main = importlib.util.module_from_spec(spec)
        imports.setitem(sys.modules, spec.name, main)
        spec.loader.exec_module(main)
    monkeypatch.setattr(main, "success", Mock())
    monkeypatch.setattr(main, "error", Mock())
    monkeypatch.setattr(main, "_execute_agent_capability", Mock(side_effect=AssertionError("no agent loop")))
    monkeypatch.setattr(githelper, "generate_commit_message", Mock(side_effect=AssertionError("no inference")))
    monkeypatch.setattr(githelper, "is_git_repo", Mock(return_value=True))
    return main


@pytest.mark.parametrize(
    ("answer", "exception", "tty", "yolo", "flag", "allowed", "prompted"),
    [
        ("y", None, True, False, None, True, True),
        (" YES ", None, True, False, None, True, True),
        ("no", None, True, False, None, False, True),
        ("", None, True, False, None, False, True),
        ("yeah", None, True, False, None, False, True),
        ("y", None, False, False, None, False, False),
        ("y", None, True, True, None, False, False),
        ("y", None, True, False, "CODEY_DAEMON_MODE", False, False),
        ("y", None, True, False, "CODEY_NON_INTERACTIVE", False, False),
        ("y", EOFError(), True, False, None, False, True),
        ("y", KeyboardInterrupt(), True, False, None, False, True),
        ("y", RuntimeError("private callback failure"), True, False, None, False, True),
        ("y", None, OSError("stdin unavailable"), False, None, False, False),
    ],
)
def test_main_push_confirmation(private_main, gateway, monkeypatch, answer, exception, tty, yolo, flag, allowed, prompted):
    main = private_main
    for name in ("CODEY_DAEMON_MODE", "CODEY_NON_INTERACTIVE"):
        monkeypatch.delenv(name, raising=False)
    if flag:
        monkeypatch.setenv(flag, "1")
    stdin = SimpleNamespace(isatty=Mock(side_effect=tty if isinstance(tty, Exception) else None, return_value=tty))
    monkeypatch.setattr(sys, "stdin", stdin)
    prompt = Mock(return_value=answer, side_effect=exception)
    monkeypatch.setattr("builtins.input", prompt)
    runner = Mock(return_value=SimpleNamespace(returncode=0, stdout="", stderr=""))
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    history = [{"role": "user", "content": "existing"}]
    handled, returned = main.handle_command("/git push", history, yolo=yolo)
    assert handled is True
    assert returned is history
    assert history == [{"role": "user", "content": "existing"}]
    assert prompt.call_count == int(prompted)
    if prompted:
        prompt.assert_called_once_with("Publish this repository's commits to its configured remote? [y/N]: ")
    assert runner.call_count == int(allowed)
    if allowed:
        runner.assert_called_once_with([git_execution._trusted_git_executable(), "push"], capture_output=True, text=True, cwd=os.getcwd())
        main.success.assert_called_once_with("Pushed successfully.")
        main.error.assert_not_called()
    else:
        main.success.assert_not_called()
        assert main.error.call_args.args[0].startswith("[ERROR] Git push refused:")
    assert record(gateway)["outcome"] == ("allowed" if allowed else "refused")
    assert "private callback failure" not in gateway.audit.read_text()


@pytest.mark.parametrize("failed", [False, True])
def test_main_result_with_blocked_audit(private_main, gateway, monkeypatch, tmp_path, failed):
    main = private_main
    for name in ("CODEY_DAEMON_MODE", "CODEY_NON_INTERACTIVE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    prompt = Mock(return_value="yes")
    monkeypatch.setattr("builtins.input", prompt)
    blocker = tmp_path / "audit-parent"
    blocker.write_text("blocker")
    monkeypatch.setattr(
        action_gateway, "get_action_gateway",
        lambda: ActionGateway(audit_file=blocker / "audit.jsonl"),
    )
    runner = Mock(return_value=SimpleNamespace(
        returncode=1 if failed else 0, stdout="", stderr="  original Git failure\n",
    ))
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    history = []
    handled, returned = main.handle_command("/git push", history)
    assert handled is True and returned is history and history == []
    prompt.assert_called_once()
    runner.assert_called_once_with([git_execution._trusted_git_executable(), "push"], capture_output=True, text=True, cwd=os.getcwd())
    if failed:
        main.error.assert_called_once_with("[ERROR] original Git failure")
        main.success.assert_not_called()
    else:
        main.success.assert_called_once_with("Pushed successfully.")
        main.error.assert_not_called()
    assert blocker.read_text() == "blocker"
