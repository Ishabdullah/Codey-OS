"""Branch/ref-only merge using isolated Git; redirect config before collection."""

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
    monkeypatch.setenv("GIT_MERGE_AUTOEDIT", "no")
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
        "authority": ACT, "action": "githelper.git_merge",
        "command": "local git merge attempt",
        "outcome": outcome, "reason": reason,
    }


def setup_target(r, *, diverged=False, conflict=False):
    r.git("checkout", "-b", "target")
    (r.repo / "dirty.txt").write_text("target content\n")
    r.git("add", "--", "dirty.txt")
    r.git("commit", "-m", "target change")
    target = r.git("rev-parse", "HEAD").stdout.strip()
    r.git("checkout", "main")
    if diverged or conflict:
        filename = "dirty.txt" if conflict else "staged.txt"
        (r.repo / filename).write_text("main content\n")
        r.git("add", "--", filename)
        r.git("commit", "-m", "main change")
    return target


@pytest.mark.parametrize("explicit_path", [True, False], ids=["explicit-path", "cwd"])
def test_fast_forward_changes_head_and_content(repository, tmp_path, monkeypatch, explicit_path):
    r = repository
    target = setup_target(r)
    old_head = r.git("rev-parse", "HEAD").stdout.strip()
    assert target != old_head
    if explicit_path:
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        result = githelper.git_merge("target", str(r.repo))
        assert list(elsewhere.iterdir()) == []
    else:
        monkeypatch.chdir(r.repo)
        result = githelper.git_merge("target")
    assert result.startswith("OK:") and "Fast-forward" in result
    assert r.git("rev-parse", "HEAD").stdout.strip() == target
    assert r.git("symbolic-ref", "HEAD").stdout.strip() == "refs/heads/main"
    assert (r.repo / "dirty.txt").read_text() == "target content\n"
    assert r.git("status", "--porcelain").stdout == ""
    assert_audit(r)


def test_non_fast_forward_creates_two_parent_merge(repository):
    r = repository
    target = setup_target(r, diverged=True)
    original = r.git("rev-parse", "HEAD").stdout.strip()
    result = githelper.git_merge("target", str(r.repo))
    assert result.startswith("OK:")
    head = r.git("rev-parse", "HEAD").stdout.strip()
    assert head not in (original, target)
    assert r.git("show", "-s", "--format=%P", "HEAD").stdout.strip().split() == [original, target]
    assert (r.repo / "dirty.txt").read_text() == "target content\n"
    assert (r.repo / "staged.txt").read_text() == "main content\n"
    assert r.git("status", "--porcelain").stdout == ""
    assert not (r.repo / ".git/MERGE_HEAD").exists()
    assert_audit(r)


def test_up_to_date_preserves_history(repository):
    r = repository
    before = snapshot(r)
    result = githelper.git_merge("main", str(r.repo))
    assert result == "OK: Already up to date."
    assert snapshot(r) == before
    assert_audit(r)


@pytest.mark.parametrize("kind", ["hash", "ref", "previous"])
def test_hash_ref_previous_target(repository, kind):
    r = repository
    target = setup_target(r)
    name = target if kind == "hash" else "refs/heads/target" if kind == "ref" else "-"
    assert githelper.git_merge(name, str(r.repo)).startswith("OK:")
    assert r.git("rev-parse", "HEAD").stdout.strip() == target
    assert (r.repo / "dirty.txt").read_text() == "target content\n"
    assert_audit(r)


def assert_conflict_state(r, target):
    assert (r.repo / ".git/MERGE_HEAD").read_text().strip() == target
    text = (r.repo / "dirty.txt").read_text()
    assert "<<<<<<< HEAD" in text and "=======" in text and ">>>>>>> target" in text
    assert "main content" in text and "target content" in text
    entries = r.git("ls-files", "--unmerged").stdout.splitlines()
    assert len(entries) == 3
    assert [line.split()[2] for line in entries] == ["1", "2", "3"]
    assert all(line.endswith("\tdirty.txt") for line in entries)


def test_real_conflict_returns_conflict_and_failed_audit(repository):
    r = repository
    target = setup_target(r, conflict=True)
    original = r.git("rev-parse", "HEAD").stdout.strip()
    result = githelper.git_merge("target", str(r.repo))
    assert result.startswith("[CONFLICT]")
    assert r.git("rev-parse", "HEAD").stdout.strip() == original
    assert_conflict_state(r, target)
    assert_audit(r, "failed", result)


@pytest.mark.parametrize("name", ["--abort", "--squash", "--ff-only", "--", "-m"])
def test_options_cannot_modify_existing_conflict(repository, monkeypatch, name):
    r = repository
    target = setup_target(r, conflict=True)
    failure = r.git("merge", "--", "target", check=False)
    assert failure.returncode != 0
    assert_conflict_state(r, target)
    before = snapshot(r)
    index = (r.repo / ".git/index").read_bytes()
    merge_head = (r.repo / ".git/MERGE_HEAD").read_bytes()
    gate = Mock(side_effect=AssertionError("no gateway for options"))
    monkeypatch.setattr(r.gateway, "gate_exec", gate)
    with monkeypatch.context() as calls:
        runner = Mock(side_effect=AssertionError("no subprocess for options"))
        calls.setattr(git_execution.subprocess, "run", runner)
        assert githelper.git_merge(name, str(r.repo)) == f"[ERROR] Merge options are not supported: '{name}'"
        runner.assert_not_called()
    gate.assert_not_called()
    assert snapshot(r) == before
    assert (r.repo / ".git/index").read_bytes() == index
    assert (r.repo / ".git/MERGE_HEAD").read_bytes() == merge_head
    assert not r.audit.exists()


@pytest.mark.parametrize("case", ["missing", "nonrepo", "dirty"])
def test_real_merge_failures(repository, tmp_path, case):
    r = repository
    name = "missing-ref"
    cwd = r.repo
    if case == "nonrepo":
        cwd = tmp_path / "nonrepo"
        cwd.mkdir()
    elif case == "dirty":
        setup_target(r)
        (r.repo / "dirty.txt").write_text("uncommitted content\n")
        name = "target"
    expected = subprocess.run([git_execution._trusted_git_executable(), "merge", "--", name], cwd=cwd, capture_output=True, text=True, check=False)
    assert expected.returncode != 0
    before = snapshot(r)
    result = githelper.git_merge(name, str(cwd))
    assert result == f"[ERROR] {(expected.stdout + expected.stderr).strip()}"
    assert snapshot(r) == before
    assert_audit(r, "failed", result)


@pytest.mark.parametrize(
    ("code", "stdout", "stderr", "expected"),
    [(0, " first\n", "second\n", "OK: first\nsecond"), (0, "", "", "OK: Merged successfully."), (1, "CONFLICT in file\n", "failure\n", "[CONFLICT] CONFLICT in file\nfailure"), (1, "out\n", "error\n", "[ERROR] out\nerror")],
)
def test_exact_argv_output_and_audit(repository, monkeypatch, code, stdout, stderr, expected):
    r = repository
    runner = Mock(return_value=SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr))
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    assert githelper.git_merge("target", str(r.repo)) == expected
    runner.assert_called_once_with([git_execution._trusted_git_executable(), "merge", "--", "target"], capture_output=True, text=True, cwd=str(r.repo))
    assert_audit(r, "failed" if code else "allowed", expected if code else "command executed")


def test_refusal_never_executes(repository, monkeypatch):
    r = repository
    before = snapshot(r)
    index = (r.repo / ".git/index").read_bytes()
    gate = Mock(return_value=GatewayDecision(ACT, "refused", "test policy"))
    monkeypatch.setattr(r.gateway, "gate_exec", gate)
    with monkeypatch.context() as calls:
        runner = Mock(side_effect=AssertionError("no execution"))
        calls.setattr(git_execution.subprocess, "run", runner)
        assert githelper.git_merge("target", str(r.repo)) == "[ERROR] Local git merge refused: test policy"
        runner.assert_not_called()
    gate.assert_called_once()
    assert gate.call_args.kwargs["authority"] == ACT
    assert gate.call_args.kwargs["action"] == "githelper.git_merge"
    assert gate.call_args.kwargs["command"] == "local git merge attempt"
    assert gate.call_args.kwargs["confirm_available"] is False
    assert snapshot(r) == before
    assert (r.repo / ".git/index").read_bytes() == index
    assert not r.audit.exists()


def test_subprocess_exception_identity(repository, monkeypatch):
    r = repository
    original = OSError("original subprocess failure")
    runner = Mock(side_effect=original)
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    with pytest.raises(OSError) as caught:
        githelper.git_merge("target", str(r.repo))
    assert caught.value is original
    runner.assert_called_once()
    assert_audit(r, "failed", str(original))


def test_blocked_audit_preserves_merge(repository, tmp_path, monkeypatch):
    r = repository
    target = setup_target(r)
    blocker = tmp_path / "blocker"
    blocker.write_text("blocker")
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: ActionGateway(audit_file=blocker / "audit.jsonl"))
    assert githelper.git_merge("target", str(r.repo)).startswith("OK:")
    assert r.git("rev-parse", "HEAD").stdout.strip() == target
    assert (r.repo / "dirty.txt").read_text() == "target content\n"
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
        spec = importlib.util.spec_from_file_location("_merge_test_main", source)
        main = importlib.util.module_from_spec(spec)
        imports.setitem(sys.modules, spec.name, main)
        spec.loader.exec_module(main)
    for name in ("success", "error", "info", "warning"):
        monkeypatch.setattr(main, name, Mock())
    monkeypatch.setattr(main, "_execute_agent_capability", Mock(side_effect=AssertionError("no agent loop")))
    monkeypatch.setattr(githelper, "generate_commit_message", Mock(side_effect=AssertionError("no inference")))
    return main


def test_main_clean_merge_no_new_prompt(repository, private_main, monkeypatch):
    r = repository
    main = private_main
    target = setup_target(r)
    monkeypatch.chdir(r.repo)
    prompt = Mock(side_effect=AssertionError("clean merge must not prompt"))
    monkeypatch.setattr("builtins.input", prompt)
    history = [{"role": "user", "content": "existing"}]
    handled, returned = main.handle_command("/git merge target", history)
    assert handled is True and returned is history
    assert history == [{"role": "user", "content": "existing"}]
    prompt.assert_not_called()
    main._execute_agent_capability.assert_not_called()
    main.success.assert_called_once()
    main.error.assert_not_called()
    main.warning.assert_not_called()
    assert r.git("rev-parse", "HEAD").stdout.strip() == target
    assert_audit(r)


@pytest.mark.parametrize(
    ("answer", "exception", "yolo", "accepted"),
    [("n", None, False, False), ("", None, False, False), ("yes", None, False, False), (None, EOFError(), False, False), (None, KeyboardInterrupt(), False, False), ("y", None, False, True), ("y", None, True, True)],
)
def test_main_real_conflict_resolution_flow(repository, private_main, monkeypatch, answer, exception, yolo, accepted):
    r = repository
    main = private_main
    target = setup_target(r, conflict=True)
    monkeypatch.chdir(r.repo)
    prompt = Mock(return_value=answer, side_effect=exception)
    monkeypatch.setattr("builtins.input", prompt)
    history = [{"role": "user", "content": "existing"}]
    resolved_history = [*history, {"role": "assistant", "content": "mock resolution"}]
    agent = Mock(return_value=(True, resolved_history), side_effect=None if accepted else AssertionError("no agent on decline"))
    monkeypatch.setattr(main, "_execute_agent_capability", agent)
    handled, returned = main.handle_command("/git merge target", history, yolo=yolo)
    assert handled is True
    assert history == [{"role": "user", "content": "existing"}]
    prompt.assert_called_once_with("\nAsk Codey to resolve conflicts? [y/N] ")
    main.warning.assert_called_once()
    result = main.warning.call_args.args[0]
    assert result.startswith("[CONFLICT]")
    main.error.assert_not_called()
    main.success.assert_not_called()
    assert_conflict_state(r, target)
    assert_audit(r, "failed", result)
    if accepted:
        agent.assert_called_once()
        arguments = agent.call_args
        assert arguments.args[1] is history
        assert arguments.kwargs == {"yolo": yolo}
        context = arguments.args[0]
        assert "merge conflicts after merging branch 'target'" in context
        assert "File: dirty.txt" in context
        assert "OURS (HEAD):\nmain content" in context
        assert "THEIRS (target):\ntarget content" in context
        assert "(1 conflict block(s))" in context
        assert returned is resolved_history
    else:
        agent.assert_not_called()
        assert returned is history
