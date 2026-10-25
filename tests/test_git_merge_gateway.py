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

from core import action_gateway, git_execution, git_mutation_context, githelper
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


def assert_audit(r, outcome="allowed", reason="command executed", preflight=False, conflicts=False):
    records = [json.loads(line) for line in r.audit.read_text().splitlines()]
    if preflight:
        query = records.pop(0)
        assert isinstance(query.pop("ts"), float)
        assert query == {"authority": "READ", "action": "githelper.is_git_repo", "command": "git metadata query", "outcome": "allowed", "reason": "command executed"}
    if conflicts:
        # The /git merge [CONFLICT] resolution flow now calls the READ-gated
        # detect_conflicts() (WP2.1 slice30, core/git_worktree_context.py),
        # adding one more allowed READ row after the merge's own ACT row.
        query = records.pop()
        assert isinstance(query.pop("ts"), float)
        assert query == {"authority": "READ", "action": "githelper.detect_conflicts", "command": "git worktree query", "outcome": "allowed", "reason": "command executed"}
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
    if case == "nonrepo":
        # core/git_mutation_context.py's discover_worktree preflight rejects
        # a non-repository cwd before any real git invocation (NEW slice31
        # behavior, matching githelper.git_commit's existing short-circuit).
        assert result == "[ERROR] Not a git repository"
    else:
        assert result == f"[ERROR] {(expected.stdout + expected.stderr).strip()}"
    assert snapshot(r) == before
    assert_audit(r, "failed", result)


@pytest.mark.parametrize(
    ("code", "stdout", "stderr", "expected"),
    [(0, " first\n", "second\n", "OK: first\nsecond"), (0, "", "", "OK: Merged successfully."), (1, "CONFLICT in file\n", "failure\n", "[CONFLICT] CONFLICT in file\nfailure"), (1, "out\n", "error\n", "[ERROR] out\nerror")],
)
def test_exact_argv_output_and_audit(repository, monkeypatch, code, stdout, stderr, expected):
    r = repository
    git_bin = git_execution._trusted_git_executable()
    final = SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)
    # core/git_mutation_context.py's isolated_mutation_context runs its own
    # preflight (split/sparse-index checks) and a merge-attribute probe
    # before the real merge; only the final "merge -- target" invocation is
    # the one this test cares about, so every other isolated query gets a
    # benign canned response (NEW slice31 behavior change). "target" does
    # not resolve to a real commit in this mocked repo, so the probe is
    # skipped regardless.
    benign = SimpleNamespace(returncode=0, stderr="", stdout=b"")
    unresolved = SimpleNamespace(returncode=1, stderr="", stdout="")

    def side_effect(argv, **kwargs):
        if argv[1:4] == ["merge", "--", "target"]:
            return final
        if argv[1:3] == ["rev-parse", "--verify"]:
            return unresolved
        return benign

    runner = Mock(side_effect=side_effect)
    monkeypatch.setattr(git_execution.subprocess, "run", runner)
    assert githelper.git_merge("target", str(r.repo)) == expected
    final_args, final_kwargs = runner.call_args_list[-1]
    assert final_args[0] == [git_bin, "merge", "--", "target"]
    assert final_kwargs["capture_output"] is True and final_kwargs["text"] is True
    assert Path(final_kwargs["cwd"]) == r.repo
    assert "env" in final_kwargs
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
    assert_audit(r, preflight=True)


@pytest.mark.parametrize(
    ("answer", "exception", "yolo", "accepted"),
    [("n", None, False, False), ("", None, False, False), ("yes", None, False, True), (None, EOFError(), False, False), (None, KeyboardInterrupt(), False, False), ("y", None, False, True), ("y", None, True, True)],
)
def test_main_real_conflict_resolution_flow(repository, private_main, monkeypatch, answer, exception, yolo, accepted):
    r = repository
    main = private_main
    target = setup_target(r, conflict=True)
    monkeypatch.chdir(r.repo)
    prompt = Mock(return_value=answer, side_effect=exception)
    # NEW-1074 declared flip: conflict prompt uses fail-closed utils.logger.confirm
    # (console.input behind the tty seam); "yes" now approves.
    import utils.logger as _lg

    monkeypatch.setattr(_lg, "_stdin_is_tty", lambda: True)
    monkeypatch.setattr(_lg, "_flush_stdin_typeahead", lambda: None)
    monkeypatch.setattr(_lg.console, "input", prompt)
    history = [{"role": "user", "content": "existing"}]
    resolved_history = [*history, {"role": "assistant", "content": "mock resolution"}]
    agent = Mock(return_value=(True, resolved_history), side_effect=None if accepted else AssertionError("no agent on decline"))
    monkeypatch.setattr(main, "_execute_agent_capability", agent)
    handled, returned = main.handle_command("/git merge target", history, yolo=yolo)
    assert handled is True
    assert history == [{"role": "user", "content": "existing"}]
    prompt.assert_called_once_with("\n\u26a0  Ask Codey to resolve conflicts? \\[y/N]: ")
    main.warning.assert_called_once()
    result = main.warning.call_args.args[0]
    assert result.startswith("[CONFLICT]")
    main.error.assert_not_called()
    main.success.assert_not_called()
    assert_conflict_state(r, target)
    assert_audit(r, "failed", result, preflight=True, conflicts=True)
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


def test_main_conflict_prompt_piped_y_non_tty_declined(repository, private_main, monkeypatch):
    """NEW-1074: a piped 'y' cannot approve the conflict-resolution agent run."""
    import io

    import utils.logger as _lg

    r = repository
    main = private_main
    setup_target(r, conflict=True)
    monkeypatch.chdir(r.repo)

    class Piped(io.StringIO):
        reads = 0

        def isatty(self):
            return False

        def readline(self, *a):
            Piped.reads += 1
            return super().readline(*a)

    monkeypatch.setattr(sys, "stdin", Piped("y\ny\n"))
    monkeypatch.setattr("builtins.input", Mock(side_effect=AssertionError("bare input() used")))
    monkeypatch.setattr(_lg.console, "input", Mock(side_effect=AssertionError("prompt reached off-tty")))
    agent = Mock(side_effect=AssertionError("no agent on decline"))
    monkeypatch.setattr(main, "_execute_agent_capability", agent)
    handled, _ = main.handle_command("/git merge target", [], yolo=False)
    assert handled is True and Piped.reads == 0
    agent.assert_not_called()


def test_post_merge_hook_does_not_fire(repository):
    """WP2.1 slice31 discriminating test: core/git_mutation_context.py forces
    core.hookspath to an empty directory via the highest-precedence
    GIT_CONFIG_COUNT/KEY/VALUE env mechanism. Control case proves the hook
    mechanism itself works (the real repository's own hookspath, restored to
    .git/hooks, fires on an unmediated non-ff merge) before asserting the
    mediated githelper.git_merge call does not trigger it.
    """
    r = repository
    marker = r.repo / "hook-fired.txt"
    (r.repo / ".git/hooks").mkdir(parents=True, exist_ok=True)
    hook = r.repo / ".git/hooks/post-merge"
    hook.write_text(f"#!/bin/sh\necho fired >> {marker}\n")
    hook.chmod(0o755)
    r.git("config", "core.hooksPath", ".git/hooks")
    pre_merge_main = r.git("rev-parse", "HEAD").stdout.strip()
    setup_target(r, diverged=True)
    # Control: an unmediated merge with the real hookspath fires the hook.
    r.git("merge", "--", "target")
    assert marker.read_text() == "fired\n"
    marker.unlink()
    r.git("reset", "--hard", pre_merge_main)
    r.git("branch", "-D", "target")
    # Mediated: githelper.git_merge must not trigger the same hook.
    setup_target(r, diverged=True)
    result = githelper.git_merge("target", str(r.repo))
    assert result.startswith("OK:")
    assert not marker.exists()


def test_merge_driver_rejected_for_changed_path(repository):
    """WP2.1 slice31 discriminating test (no existing precedent in this
    project): core/git_mutation_context.py probes the union of paths that
    differ between HEAD and the incoming target for a `merge` attribute and
    rejects if any is set -- verified experimentally this is a safe
    conservative superset of the paths that actually invoke a configured
    driver; see that module's docstring.

    The `.gitattributes` commit is made on the CURRENT (main) side only,
    strictly after the branches diverge, so the incoming `target` branch
    never has the attribute in its own history. This discriminates the
    "current HEAD visibility is what matters" claim from a weaker,
    non-discriminating version of this test (code-reviewer finding during
    this slice's review) where the attribute was committed before
    divergence and therefore present on both sides -- that version could
    not tell apart "current side matters" from "either side matters".
    """
    r = repository
    r.git("checkout", "-b", "target")
    (r.repo / "dirty.txt").write_text("target content\n")
    r.git("add", "--", "dirty.txt")
    r.git("commit", "-m", "target change")
    r.git("checkout", "main")
    (r.repo / "dirty.txt").write_text("main content\n")
    r.git("add", "--", "dirty.txt")
    r.git("commit", "-m", "main change")
    # Attribute added to current HEAD only, after divergence; "target" never
    # has this file in its history.
    (r.repo / ".gitattributes").write_text("dirty.txt merge=custom\n")
    r.git("add", "--", ".gitattributes")
    r.git("commit", "-m", "add merge attribute to current side only")
    before = snapshot(r)
    result = githelper.git_merge("target", str(r.repo))
    assert result == "[ERROR] Selected Git merge drivers are unsupported"
    assert snapshot(r) == before


def test_merge_driver_not_consulted_for_incoming_only_attribute(repository, tmp_path):
    """WP2.1 slice31 discriminating control test for the risk case the
    code-reviewer identified: a `merge` attribute defined ONLY on the
    incoming branch, added strictly after divergence, with a real content
    conflict on the same path on both sides. core/git_mutation_context.py's
    merge probe deliberately omits `--source` and therefore cannot see this
    attribute (it only reads the current worktree/index); this is safe only
    if real Git's merge-driver dispatch also never consults the incoming
    side for this attribute.

    Control case proves the driver mechanism itself works (an unmediated
    merge that DOES have the attribute visible on the current side invokes
    the configured driver) before asserting that a real unmediated merge
    with the SAME conflicting content but the attribute ONLY on the
    incoming side does NOT invoke the driver -- confirmed experimentally
    against the real git binary in this environment (2026-10-13, disposable
    repo, git 2.56.0): the merge instead falls back to an ordinary content
    conflict. The mediated githelper.git_merge call is then confirmed to
    reach the same [CONFLICT] outcome (not rejected), matching real Git's
    behavior for this exact case rather than falsely rejecting a merge the
    unmediated command would complete.
    """
    r = repository
    marker = tmp_path / "merge-driver-fired.txt"

    def configure_driver():
        r.git("config", "merge.marker.name", "test driver")
        r.git("config", "merge.marker.driver", f"sh -c 'touch {marker}; exit 1'")

    # Control: attribute visible on the CURRENT side invokes the driver on
    # an unmediated merge.
    configure_driver()
    r.git("checkout", "-b", "control-target")
    (r.repo / "dirty.txt").write_text("control target content\n")
    r.git("add", "--", "dirty.txt")
    r.git("commit", "-m", "control target change")
    r.git("checkout", "main")
    (r.repo / "dirty.txt").write_text("control main content\n")
    r.git("add", "--", "dirty.txt")
    r.git("commit", "-m", "control main change")
    (r.repo / ".gitattributes").write_text("dirty.txt merge=marker\n")
    r.git("add", "--", ".gitattributes")
    r.git("commit", "-m", "control: attribute on current side")
    r.git("merge", "control-target", check=False)
    assert marker.exists()
    marker.unlink()
    r.git("merge", "--abort")
    r.git("branch", "-D", "control-target")
    (r.repo / ".gitattributes").unlink()
    r.git("add", "--", ".gitattributes")
    r.git("commit", "-m", "remove attribute from current side")

    # Risk case: attribute defined ONLY on the incoming side, after
    # divergence, with a real content conflict on both sides.
    r.git("checkout", "-b", "target")
    (r.repo / "dirty.txt").write_text("target content\n")
    r.git("add", "--", "dirty.txt")
    r.git("commit", "-m", "target change")
    (r.repo / ".gitattributes").write_text("dirty.txt merge=marker\n")
    r.git("add", "--", ".gitattributes")
    r.git("commit", "-m", "incoming-only merge attribute, after divergence")
    r.git("checkout", "main")
    (r.repo / "dirty.txt").write_text("main content\n")
    r.git("add", "--", "dirty.txt")
    r.git("commit", "-m", "main change")
    # Unmediated control: the real merge does not invoke the driver.
    unmediated = r.git("merge", "target", check=False)
    assert "CONFLICT" in unmediated.stdout.upper() + unmediated.stderr.upper()
    assert not marker.exists()
    r.git("merge", "--abort")
    # Mediated: githelper.git_merge reaches the same [CONFLICT] outcome,
    # not a rejection -- the probe correctly cannot see (and real Git does
    # not consult) the incoming-only attribute. The preceding control
    # sequence used r.git(...) directly (bypassing the gateway), so the
    # audit ledger only has this one record, same as
    # test_real_conflict_returns_conflict_and_failed_audit above.
    result = githelper.git_merge("target", str(r.repo))
    assert result.startswith("[CONFLICT]")
    assert not marker.exists()
    assert_audit(r, "failed", result)


def test_success_survives_admin_dir_cleanup_failure(repository, monkeypatch):
    """2026-10-13 fix: a successful merge must not be reported as failed
    (nor raise) merely because the admin-dir cleanup afterward fails."""
    r = repository
    target = setup_target(r, diverged=True)
    original_rmtree = git_mutation_context.shutil.rmtree
    leaked = []

    def rmtree(path, **kwargs):
        if Path(path).name.startswith("codey-mutate-"):
            leaked.append(Path(path))
            raise OSError("cleanup failed")
        return original_rmtree(path, **kwargs)

    monkeypatch.setattr(git_mutation_context.shutil, "rmtree", rmtree)
    result = githelper.git_merge("target", str(r.repo))
    assert result.startswith("OK:")
    assert result.endswith("; Git mutation context cleanup also failed")
    assert r.git("merge-base", "--is-ancestor", target, "HEAD").returncode == 0
    assert_audit(r)
    for path in leaked:
        original_rmtree(path)


def test_active_merge_state_rejected(repository):
    """WP2.1 slice31: a second merge must reject while a merge is already
    mid-flight (deliberately the opposite of core/git_worktree_context.py's
    tolerant worktree-READ case; see core/git_mutation_context.py's
    docstring)."""
    r = repository
    setup_target(r, conflict=True)
    r.git("merge", "--", "target", check=False)
    assert (r.repo / ".git/MERGE_HEAD").exists()
    before = snapshot(r)
    result = githelper.git_merge("target", str(r.repo))
    assert result == "[ERROR] Active Git operations are unsupported"
    assert snapshot(r) == before
