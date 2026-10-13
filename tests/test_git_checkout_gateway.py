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


def assert_audit(r, outcome="allowed", reason="command executed", queries=False):
    records = [json.loads(line) for line in r.audit.read_text().splitlines()]
    if queries:
        for action_name in ("githelper.is_git_repo", "githelper.git_current_branch"):
            query = records.pop(0)
            assert isinstance(query.pop("ts"), float)
            assert query == {"authority": "READ", "action": action_name, "command": "git metadata query", "outcome": "allowed", "reason": "command executed"}
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
        [git_execution._trusted_git_executable(), "checkout", "--no-guess", "missing-ref", "--"], cwd=cwd,
        capture_output=True, text=True, check=False,
    )
    assert expected.returncode != 0
    before = snapshot(r)
    result = githelper.git_checkout("missing-ref", str(cwd))
    if nonrepo:
        # core/git_mutation_context.py's discover_worktree preflight rejects
        # a non-repository cwd before any real git invocation (NEW slice31
        # behavior, matching githelper.git_commit's existing short-circuit).
        assert result == "[ERROR] Not a git repository"
    else:
        assert result == f"[ERROR] {expected.stderr.strip()}"
    assert snapshot(r) == before
    assert_audit(r, "failed", result)


@pytest.mark.parametrize(
    ("stderr", "stdout", "expected"),
    [(" stderr first\n", "stdout ignored", "stderr first"), ("", " stdout\n", "stdout"), ("", "", "Switched to branch 'target'.")],
)
def test_success_output_and_exact_argv(repository, monkeypatch, stderr, stdout, expected):
    r = repository
    git_bin = git_execution._trusted_git_executable()
    final = SimpleNamespace(returncode=0, stderr=stderr, stdout=stdout)
    # core/git_mutation_context.py's isolated_mutation_context runs its own
    # preflight (split/sparse-index checks) and a filter-attribute probe
    # before the real checkout; only the final "checkout --no-guess target
    # --" invocation is the one this test cares about, so every other
    # isolated query gets a benign canned response (NEW slice31 behavior
    # change).
    benign = SimpleNamespace(returncode=0, stderr="", stdout=b"")
    unresolved = SimpleNamespace(returncode=1, stderr="", stdout="")

    def side_effect(argv, **kwargs):
        if argv[1:5] == ["checkout", "--no-guess", "target", "--"]:
            return final
        if argv[1:3] == ["rev-parse", "--verify"]:
            return unresolved
        return benign

    runner = Mock(side_effect=side_effect)
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    assert githelper.git_checkout("target", str(r.repo)) == expected
    final_args, final_kwargs = runner.call_args_list[-1]
    assert final_args[0] == [git_bin, "checkout", "--no-guess", "target", "--"]
    assert final_kwargs["capture_output"] is True and final_kwargs["text"] is True
    assert Path(final_kwargs["cwd"]) == r.repo
    assert "env" in final_kwargs
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
        assert gate.call_count == 3
        assert [call.kwargs["action"] for call in gate.call_args_list] == ["githelper.is_git_repo", "githelper.git_current_branch", "githelper.git_checkout"]
        assert "Switched to branch 'target'" in main.success.call_args.args[0]
        assert r.git("symbolic-ref", "HEAD").stdout.strip() == "refs/heads/target"
        assert_audit(r, queries=True)
    else:
        assert gate.call_count == 2
        assert [call.kwargs["authority"] for call in gate.call_args_list] == ["READ", "READ"]
        main.success.assert_not_called()
        main.info.assert_called_once_with("Checkout cancelled.")
        assert snapshot(r) == before
        assert (r.repo / ".git/index").read_bytes() == index
        ledger = [json.loads(line) for line in r.audit.read_text().splitlines()]
        assert [row["action"] for row in ledger] == ["githelper.is_git_repo", "githelper.git_current_branch"]
        assert all(row["authority"] == "READ" and row["outcome"] == "allowed" for row in ledger)


def test_post_checkout_hook_does_not_fire(repository):
    """WP2.1 slice31 discriminating test: core/git_mutation_context.py forces
    core.hookspath to an empty directory via the highest-precedence
    GIT_CONFIG_COUNT/KEY/VALUE env mechanism. Control case proves the hook
    mechanism itself works (the real repository's own hookspath, restored to
    .git/hooks, fires on an unmediated checkout) before asserting the
    mediated githelper.git_checkout call does not trigger it.
    """
    r = repository
    r.git("branch", "target")
    marker = r.repo / "hook-fired.txt"
    (r.repo / ".git/hooks").mkdir(parents=True, exist_ok=True)
    hook = r.repo / ".git/hooks/post-checkout"
    hook.write_text(f"#!/bin/sh\necho fired >> {marker}\n")
    hook.chmod(0o755)
    r.git("config", "core.hooksPath", ".git/hooks")
    # Control: an unmediated checkout with the real hookspath fires the hook.
    r.git("checkout", "target")
    assert marker.read_text() == "fired\n"
    r.git("checkout", "main")  # also an unmediated checkout; re-fires the hook
    marker.unlink()
    # Mediated: githelper.git_checkout must not trigger the same hook.
    result = githelper.git_checkout("target", str(r.repo))
    assert "Switched to branch 'target'" in result
    assert not marker.exists()


def test_filter_driver_rejected_for_changed_path(repository):
    """WP2.1 slice31 discriminating test: core/git_mutation_context.py probes
    exactly the paths that will change on this checkout for a `filter`
    attribute and rejects if any is set (verified experimentally which path
    set is actually smudged; see that module's docstring)."""
    r = repository
    r.git("checkout", "-b", "filtered-branch")
    (r.repo / ".gitattributes").write_text("dirty.txt filter=marker\n")
    (r.repo / "dirty.txt").write_text("filtered content\n")
    r.git("add", "--", ".gitattributes", "dirty.txt")
    r.git("commit", "-m", "attach filter attribute")
    r.git("checkout", "main")
    before = snapshot(r)
    result = githelper.git_checkout("filtered-branch", str(r.repo))
    assert result == "[ERROR] Selected Git filter drivers are unsupported"
    assert snapshot(r) == before


def test_dwim_remote_tracking_checkout_filter_rejected(repository, tmp_path):
    """WP2.1 slice31 regression test for the code-reviewer-found DWIM bypass:
    resolve_target()'s strict `rev-parse --verify <name>^{commit}` probe and
    the real `git checkout <name> --` command used to resolve names
    differently. A name with no local branch but a same-named
    remote-tracking ref (here synthesized directly via `update-ref` plus a
    fake `remote add`, with no network involved) is unresolvable by the
    strict probe -- so the filter-driver probe above is skipped -- but used
    to still succeed via Git's branch-name DWIM (auto-creating a local
    tracking branch from the remote-tracking ref), smudging content through
    a configured filter driver with no rejection check having run at all.
    Control case proves the DWIM mechanism and the filter driver both
    actually fire on an unmediated checkout before asserting the mediated
    githelper.git_checkout call is rejected and the driver never runs
    (closed by running the real checkout with --no-guess; see
    core/git_mutation_context.py's docstring).
    """
    r = repository
    r.git("checkout", "-b", "feature-src")
    (r.repo / ".gitattributes").write_text("dirty.txt filter=marker\n")
    (r.repo / "dirty.txt").write_text("filtered content\n")
    r.git("add", "--", ".gitattributes", "dirty.txt")
    r.git("commit", "-m", "attach filter attribute")
    feature_sha = r.git("rev-parse", "feature-src").stdout.strip()
    r.git("checkout", "main")
    r.git("branch", "-D", "feature-src")
    r.git("remote", "add", "origin", "https://example.invalid/unused.git")
    r.git("update-ref", "refs/remotes/origin/feature", feature_sha)
    marker = tmp_path / "filter-fired.txt"
    r.git("config", "filter.marker.smudge", f"sh -c 'touch {marker}; cat'")
    r.git("config", "filter.marker.clean", "cat")
    # Control: resolve_target()'s strict probe cannot resolve 'feature' by
    # itself (no local branch of that name) -- the exact condition under
    # which the filter probe above is skipped.
    probe = r.git("rev-parse", "--verify", "--quiet", "feature^{commit}", check=False)
    assert probe.returncode != 0
    # Control: an unmediated DWIM checkout succeeds and fires the driver.
    control = r.git("checkout", "feature")
    assert control.returncode == 0
    assert marker.exists()
    marker.unlink()
    r.git("checkout", "main")
    r.git("branch", "-D", "feature")
    before = snapshot(r)
    # Mediated: githelper.git_checkout must not take the DWIM path at all.
    result = githelper.git_checkout("feature", str(r.repo))
    assert result == "[ERROR] fatal: invalid reference: feature"
    assert not marker.exists()
    assert snapshot(r) == before
    # Assert the mechanism directly, not only git's (possibly-reworded)
    # error text: no local 'feature' branch exists -- DWIM never ran.
    local_branch = r.git("rev-parse", "--verify", "--quiet", "refs/heads/feature", check=False)
    assert local_branch.returncode != 0
    assert_audit(r, "failed", result)


def test_active_merge_state_rejected(repository):
    """WP2.1 slice31: checkout must reject while a merge is mid-flight
    (deliberately the opposite of core/git_worktree_context.py's tolerant
    worktree-READ case; see core/git_mutation_context.py's docstring)."""
    r = repository
    r.git("branch", "target")
    r.git("checkout", "-b", "other")
    (r.repo / "dirty.txt").write_text("other content\n")
    r.git("add", "--", "dirty.txt")
    r.git("commit", "-m", "other change")
    r.git("checkout", "main")
    (r.repo / "dirty.txt").write_text("main content\n")
    r.git("add", "--", "dirty.txt")
    r.git("commit", "-m", "main change")
    r.git("merge", "--", "other", check=False)
    assert (r.repo / ".git/MERGE_HEAD").exists()
    before = snapshot(r)
    result = githelper.git_checkout("target", str(r.repo))
    assert result == "[ERROR] Active Git operations are unsupported"
    assert snapshot(r) == before
