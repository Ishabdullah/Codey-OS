"""Branch/ref-only checkout in isolated Git; redirect state before collection."""

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
from core.action_gateway import ACT, ActionGateway, GatewayDecision


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

    def git(*args, check=True):
        return subprocess.run([git_execution._trusted_git_executable(), *args], cwd=repo, capture_output=True, text=True, check=check)

    git("init", "-b", "main")
    for key, value in {
        "core.hooksPath": str(empty), "commit.gpgsign": "false", "tag.gpgsign": "false",
        "user.useConfigOnly": "true", "user.name": "Temporary Test",
        "user.email": "test@example.invalid",
    }.items():
        git("config", key, value)
    (repo / "staged.txt").write_text("staged baseline\n")
    (repo / "dirty.txt").write_text("dirty baseline\n")
    git("add", "--", "staged.txt", "dirty.txt")
    git("commit", "-m", "baseline")
    audit = tmp_path / "audit.jsonl"
    gateway = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: gateway)
    return SimpleNamespace(repo=repo, git=git, audit=audit, gateway=gateway)


def snapshot(r):
    return (
        r.git("show-ref").stdout, r.git("symbolic-ref", "HEAD").stdout,
        r.git("ls-files", "--stage").stdout,
        {path.name: path.read_bytes() for path in r.repo.iterdir() if path.is_file()},
    )


def assert_audit(r, outcome="allowed", reason="command executed"):
    records = [json.loads(line) for line in r.audit.read_text().splitlines()]
    assert len(records) == 1
    record = records[0]
    assert isinstance(record.pop("ts"), float)
    assert record == {
        "authority": ACT, "action": "githelper.git_checkout",
        "command": "local git checkout attempt",
        "outcome": outcome, "reason": reason,
    }


@pytest.mark.parametrize("explicit_path", [True, False], ids=["explicit-path", "cwd"])
def test_branch_checkout_preserves_head_index_dirty(repository, tmp_path, monkeypatch, explicit_path):
    r = repository
    r.git("branch", "target")
    (r.repo / "staged.txt").write_text("staged change\n")
    r.git("add", "--", "staged.txt")
    (r.repo / "dirty.txt").write_text("dirty change\n")
    head = r.git("rev-parse", "HEAD").stdout
    entries = r.git("ls-files", "--stage").stdout
    if explicit_path:
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        result = githelper.git_checkout("target", str(r.repo))
        assert list(elsewhere.iterdir()) == []
    else:
        monkeypatch.chdir(r.repo)
        result = githelper.git_checkout("target")
    assert "Switched to branch 'target'" in result
    assert r.git("symbolic-ref", "HEAD").stdout.strip() == "refs/heads/target"
    assert r.git("rev-parse", "HEAD").stdout == head
    assert r.git("ls-files", "--stage").stdout == entries
    assert (r.repo / "staged.txt").read_text() == "staged change\n"
    assert (r.repo / "dirty.txt").read_text() == "dirty change\n"
    assert_audit(r)
    assert "target" not in r.audit.read_text()



def test_clean_checkout_changes_commit_and_tracked_content(repository):
    r = repository
    original = r.git("rev-parse", "HEAD").stdout.strip()
    r.git("checkout", "-b", "divergent")
    (r.repo / "dirty.txt").write_text("divergent committed content\n")
    r.git("add", "--", "dirty.txt")
    r.git("commit", "-m", "divergent content")
    target = r.git("rev-parse", "HEAD").stdout.strip()
    assert target != original
    r.git("checkout", "main")
    assert (r.repo / "dirty.txt").read_text() == "dirty baseline\n"
    result = githelper.git_checkout("divergent", str(r.repo))
    assert result == "Switched to branch 'divergent'"
    assert r.git("symbolic-ref", "HEAD").stdout.strip() == "refs/heads/divergent"
    assert r.git("rev-parse", "HEAD").stdout.strip() == target
    assert r.git("rev-parse", "main").stdout.strip() == original
    assert (r.repo / "dirty.txt").read_text() == "divergent committed content\n"
    assert r.git("status", "--porcelain").stdout == ""
    assert_audit(r)

def test_branch_filename_collision_selects_branch(repository):
    r = repository
    (r.repo / "target").write_text("baseline\n")
    r.git("add", "--", "target")
    r.git("commit", "-m", "add colliding file")
    r.git("branch", "target")
    (r.repo / "target").write_text("dirty collision\n")
    assert "Switched to branch 'target'" in githelper.git_checkout("target", str(r.repo))
    assert r.git("symbolic-ref", "HEAD").stdout.strip() == "refs/heads/target"
    assert (r.repo / "target").read_text() == "dirty collision\n"
    assert_audit(r)


def test_filename_only_never_restores_dirty_file(repository):
    r = repository
    (r.repo / "dirty.txt").write_text("must survive\n")
    before = snapshot(r)
    result = githelper.git_checkout("dirty.txt", str(r.repo))
    assert result.startswith("[ERROR]")
    assert snapshot(r) == before
    assert (r.repo / "dirty.txt").read_text() == "must survive\n"
    assert_audit(r, "failed", result)


def test_hash_checkout_detaches_head(repository):
    r = repository
    head = r.git("rev-parse", "HEAD").stdout.strip()
    result = githelper.git_checkout(head, str(r.repo))
    assert not result.startswith("[ERROR]")
    assert r.git("symbolic-ref", "HEAD", check=False).returncode != 0
    assert r.git("rev-parse", "HEAD").stdout.strip() == head
    assert_audit(r)
    assert head not in r.audit.read_text()


@pytest.mark.parametrize("previous", [True, False])
def test_previous_branch_target(repository, previous):
    r = repository
    if previous:
        r.git("checkout", "-b", "target")
        result = githelper.git_checkout("-", str(r.repo))
        assert "Switched to branch 'main'" in result
        assert r.git("symbolic-ref", "HEAD").stdout.strip() == "refs/heads/main"
        assert_audit(r)
    else:
        before = snapshot(r)
        result = githelper.git_checkout("-", str(r.repo))
        assert result.startswith("[ERROR]")
        assert snapshot(r) == before
        assert_audit(r, "failed", result)


@pytest.mark.parametrize("name", ["--force", "-f", "--", "--detach", "-b"])
def test_options_rejected_before_gateway_or_subprocess(repository, monkeypatch, name):
    r = repository
    (r.repo / "dirty.txt").write_text("must survive\n")
    before = snapshot(r)
    index = (r.repo / ".git/index").read_bytes()
    gate = Mock(side_effect=AssertionError("no gateway for options"))
    monkeypatch.setattr(r.gateway, "gate_exec", gate)
    with monkeypatch.context() as calls:
        runner = Mock(side_effect=AssertionError("no Git for options"))
        calls.setattr(git_execution.subprocess, "run", runner)
        assert githelper.git_checkout(name, str(r.repo)) == f"[ERROR] Checkout options are not supported: '{name}'"
        runner.assert_not_called()
    gate.assert_not_called()
    assert snapshot(r) == before
    assert (r.repo / ".git/index").read_bytes() == index
    assert not r.audit.exists()


def test_dirty_switch_protection(repository):
    r = repository
    r.git("checkout", "-b", "divergent")
    (r.repo / "dirty.txt").write_text("other branch content\n")
    r.git("add", "--", "dirty.txt")
    r.git("commit", "-m", "different branch content")
    r.git("checkout", "main")
    (r.repo / "dirty.txt").write_text("uncommitted content\n")
    before = snapshot(r)
    result = githelper.git_checkout("divergent", str(r.repo))
    assert result.startswith("[ERROR]")
    assert "would be overwritten by checkout" in result
    assert snapshot(r) == before
    assert_audit(r, "failed", result)


@pytest.mark.parametrize("nonrepo", [False, True])
def test_missing_ref_or_nonrepo_exact_failure(repository, tmp_path, nonrepo):
    r = repository
    cwd = r.repo
    if nonrepo:
        cwd = tmp_path / "nonrepo"
        cwd.mkdir()
    expected = subprocess.run(
        [git_execution._trusted_git_executable(), "checkout", "missing-ref", "--"], cwd=cwd,
        capture_output=True, text=True, check=False,
    )
    assert expected.returncode != 0
    before = snapshot(r)
    result = githelper.git_checkout("missing-ref", str(cwd))
    assert result == f"[ERROR] {expected.stderr.strip()}"
    assert snapshot(r) == before
    assert_audit(r, "failed", result)


@pytest.mark.parametrize(
    ("stderr", "stdout", "expected"),
    [(" stderr first\n", "stdout ignored", "stderr first"), ("", " stdout\n", "stdout"), ("", "", "Switched to branch 'target'.")],
)
def test_success_output_and_exact_argv(repository, monkeypatch, stderr, stdout, expected):
    r = repository
    runner = Mock(return_value=SimpleNamespace(returncode=0, stderr=stderr, stdout=stdout))
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    assert githelper.git_checkout("target", str(r.repo)) == expected
    runner.assert_called_once_with([git_execution._trusted_git_executable(), "checkout", "target", "--"], capture_output=True, text=True, cwd=str(r.repo))
    assert_audit(r)


def test_refusal_never_executes(repository, monkeypatch):
    r = repository
    before = snapshot(r)
    index = (r.repo / ".git/index").read_bytes()
    gate = Mock(return_value=GatewayDecision(ACT, "refused", "test policy"))
    monkeypatch.setattr(r.gateway, "gate_exec", gate)
    with monkeypatch.context() as calls:
        runner = Mock(side_effect=AssertionError("no Git on refusal"))
        calls.setattr(git_execution.subprocess, "run", runner)
        assert githelper.git_checkout("target", str(r.repo)) == "[ERROR] Local git checkout refused: test policy"
        runner.assert_not_called()
    gate.assert_called_once()
    assert gate.call_args.kwargs["authority"] == ACT
    assert gate.call_args.kwargs["action"] == "githelper.git_checkout"
    assert gate.call_args.kwargs["command"] == "local git checkout attempt"
    assert gate.call_args.kwargs["confirm_available"] is False
    assert snapshot(r) == before
    assert (r.repo / ".git/index").read_bytes() == index
    assert not r.audit.exists()


def test_subprocess_exception_identity(repository, monkeypatch):
    r = repository
    original = OSError("original subprocess error")
    runner = Mock(side_effect=original)
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    with pytest.raises(OSError) as caught:
        githelper.git_checkout("target", str(r.repo))
    assert caught.value is original
    runner.assert_called_once()
    assert_audit(r, "failed", str(original))


def test_blocked_audit_preserves_checkout(repository, tmp_path, monkeypatch):
    r = repository
    r.git("branch", "target")
    blocker = tmp_path / "blocker"
    blocker.write_text("blocker")
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: ActionGateway(audit_file=blocker / "audit.jsonl"))
    assert "Switched to branch 'target'" in githelper.git_checkout("target", str(r.repo))
    assert r.git("symbolic-ref", "HEAD").stdout.strip() == "refs/heads/target"
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
        spec = importlib.util.spec_from_file_location("_checkout_test_main", source)
        main = importlib.util.module_from_spec(spec)
        imports.setitem(sys.modules, spec.name, main)
        spec.loader.exec_module(main)
    for name in ("success", "error", "info"):
        monkeypatch.setattr(main, name, Mock())
    monkeypatch.setattr(main, "_execute_agent_capability", Mock(side_effect=AssertionError("no agent loop")))
    monkeypatch.setattr(githelper, "generate_commit_message", Mock(side_effect=AssertionError("no inference")))
    return main


@pytest.mark.parametrize(
    ("answer", "exception", "yolo", "allowed"),
    [("y", None, False, True), ("y", None, True, True), ("n", None, False, False), ("yes", None, False, False), ("", None, False, False), ("n", None, True, False), (None, EOFError(), False, False), (None, KeyboardInterrupt(), False, False)],
)
def test_main_existing_prompt_and_history(repository, private_main, monkeypatch, answer, exception, yolo, allowed):
    r = repository
    main = private_main
    r.git("branch", "target")
    monkeypatch.chdir(r.repo)
    before = snapshot(r)
    index = (r.repo / ".git/index").read_bytes()
    prompt = Mock(return_value=answer, side_effect=exception)
    monkeypatch.setattr("builtins.input", prompt)
    gate = Mock(wraps=r.gateway.gate_exec)
    monkeypatch.setattr(r.gateway, "gate_exec", gate)
    history = [{"role": "user", "content": "existing"}]
    handled, returned = main.handle_command("/git checkout target", history, yolo=yolo)
    assert handled is True and returned is history
    assert history == [{"role": "user", "content": "existing"}]
    prompt.assert_called_once_with("Confirm? [y/N] ")
    main.error.assert_not_called()
    if allowed:
        gate.assert_called_once()
        assert "Switched to branch 'target'" in main.success.call_args.args[0]
        assert r.git("symbolic-ref", "HEAD").stdout.strip() == "refs/heads/target"
        assert_audit(r)
    else:
        gate.assert_not_called()
        main.success.assert_not_called()
        main.info.assert_called_once_with("Checkout cancelled.")
        assert snapshot(r) == before
        assert (r.repo / ".git/index").read_bytes() == index
        assert not r.audit.exists()
