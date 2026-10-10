"""Local commit ambient isolation; temporary child HOME/XDG, never process HOME."""

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, checkpoint, git_execution, githelper
from core.action_gateway import ACT, ActionGateway, GatewayDecision

ALLOWED = {"HOME", "XDG_CONFIG_HOME", "USER", "LOGNAME", "EMAIL", "TZ", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_DATE", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_COMMITTER_DATE"}
OMITTED = ["PATH", "LC_ALL", "LANG", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_COUNT", "GIT_CONFIG_KEY_0", "GIT_CONFIG_VALUE_0", "GIT_CONFIG_PARAMETERS", "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_EXEC_PATH", "GIT_PAGER", "PAGER", "GIT_EDITOR", "EDITOR", "GIT_SSH", "GIT_SSH_COMMAND", "SSH_ASKPASS", "GIT_ASKPASS", "GIT_TRACE", "GIT_TRACE2", "LD_PRELOAD", "LD_LIBRARY_PATH", "BASH_ENV", "ENV", "ARBITRARY_HOOK_SECRET", "TMPDIR"]


def test_builder_exact_allowlist_and_parent_environment_unchanged(tmp_path, monkeypatch):
    for name in ALLOWED - {"HOME", "XDG_CONFIG_HOME"}:
        monkeypatch.setenv(name, f"original-{name}")
    for name in OMITTED:
        monkeypatch.setenv(name, "untrusted ambient value")
    first = tmp_path / "installation/bin/git"
    first.parent.mkdir(parents=True)
    first.touch()
    second = tmp_path / "other/bin/git"
    second.parent.mkdir(parents=True)
    second.touch()
    candidates = (first, first, Path("relative/git"), tmp_path / "missing/git", second)
    monkeypatch.setattr(git_execution, "_git_candidates", lambda: candidates)
    before = dict(os.environ)
    environment = git_execution._local_commit_environment()
    expected = {name: before[name] for name in ALLOWED if name in before}
    expected.update(PATH=os.pathsep.join([str(first.parent), str(tmp_path / "missing"), str(second.parent)]), LC_ALL="C", GIT_CONFIG_NOSYSTEM="1")
    assert environment == expected
    unchanged = dict(os.environ) == before
    assert unchanged


def test_runner_snapshots_once_and_copies_for_every_invocation(monkeypatch):
    source = {"HOME": "literal child home", "USER": "original", "PATH": "/trusted/bin"}
    builder = Mock(return_value=source)
    monkeypatch.setattr(git_execution, "_local_commit_environment", builder)
    received = []
    result = object()

    def run(argv, **kwargs):
        received.append(kwargs["env"])
        if len(received) == 1:
            kwargs["env"]["USER"] = "child mutated copy"
        return result

    monkeypatch.setattr(git_execution, "run_git", run)
    runner = git_execution.local_commit_runner()
    source["USER"] = "builder source changed"
    monkeypatch.setenv("USER", "ambient changed")
    assert runner(["git", "status"], cwd="/temporary", capture_output=True, text=True, check=False, timeout=31) is result
    assert runner(["git", "commit", "-m", "message"]) is result
    builder.assert_called_once_with()
    assert received[1] == {"HOME": "literal child home", "USER": "original", "PATH": "/trusted/bin"}
    assert received[0] is not received[1]


@pytest.mark.parametrize("keyword", ["env", "executable", "shell", "input", "stdin", "stdout", "stderr", "encoding", "preexec_fn", "unknown"])
def test_profile_rejects_forbidden_kwargs_before_selection_or_spawn(monkeypatch, keyword):
    monkeypatch.setattr(git_execution, "_local_commit_environment", dict)
    runner = git_execution.local_commit_runner()
    forbidden = Mock()
    monkeypatch.setattr(git_execution, "_trusted_git_executable", forbidden)
    monkeypatch.setattr(git_execution.subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="Unsupported local commit runner"):
        runner(["git", "status"], **{keyword: "rejected"})
    forbidden.assert_not_called()


@pytest.fixture
def repository(tmp_path, monkeypatch):
    trusted_git = git_execution._trusted_git_executable()
    for name in list(os.environ):
        if name.startswith("GIT_") or name == "EMAIL":
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("GIT_TEMPLATE_DIR", str(empty))
    child_home, child_xdg = tmp_path / "child-home", tmp_path / "child-xdg"
    child_home.mkdir()
    child_xdg.mkdir()
    original = git_execution._local_commit_environment

    def child_environment():
        environment = original()
        environment.update(HOME=str(child_home), XDG_CONFIG_HOME=str(child_xdg))
        return environment

    monkeypatch.setattr(git_execution, "_local_commit_environment", child_environment)
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args, cwd=repo, check=True):
        return subprocess.run([trusted_git, *args], cwd=cwd, capture_output=True, text=True, check=check)

    git("init", "-b", "main")
    for key, value in {"core.hooksPath": str(empty), "commit.gpgsign": "false", "tag.gpgsign": "false", "user.useConfigOnly": "true", "user.name": "Repository Identity", "user.email": "repository@example.invalid"}.items():
        git("config", key, value)
    (repo / "core").mkdir()
    trigger = repo / "core/example.py"
    trigger.write_text("baseline\n")
    git("add", "--", "core/example.py")
    git("commit", "-m", "baseline")
    audit = tmp_path / "audit.jsonl"
    gateway = ActionGateway(audit_file=audit)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: gateway)
    monkeypatch.setattr(checkpoint, "CODE_DIR", repo)
    monkeypatch.setattr(checkpoint, "warning", Mock())
    return SimpleNamespace(repo=repo, trigger=trigger, git=git, home=child_home, xdg=child_xdg, empty=empty, trusted_git=trusted_git, audit=audit, gateway=gateway)


def commit(r, operation):
    if operation == "broad":
        return githelper.git_commit("profile commit", str(r.repo))
    if operation == "scoped":
        return githelper.git_commit_paths("profile commit", ["core/example.py"], str(r.repo))
    return checkpoint._create_git_commit("profile commit", [str(r.trigger)])


@pytest.mark.parametrize("identity", ["repository", "global", "xdg", "scalar", "email-fallback"])
def test_real_identities_dates_and_home_config_retained(repository, monkeypatch, identity):
    r = repository
    expected_name, expected_email = "Repository Identity", "repository@example.invalid"
    if identity != "repository":
        r.git("config", "--unset", "user.name")
        r.git("config", "--unset", "user.email")
    if identity in {"global", "xdg"}:
        expected_name, expected_email = "Global Identity", "global@example.invalid"
        config = r.home / ".gitconfig" if identity == "global" else r.xdg / "git/config"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(f"[user]\n name = {expected_name}\n email = {expected_email}\n")
    elif identity == "scalar":
        expected_name, expected_email = "Scalar Identity", "scalar@example.invalid"
        for role in ["AUTHOR", "COMMITTER"]:
            monkeypatch.setenv(f"GIT_{role}_NAME", expected_name)
            monkeypatch.setenv(f"GIT_{role}_EMAIL", expected_email)
            monkeypatch.setenv(f"GIT_{role}_DATE", "2001-02-03T04:05:06 +0000")
    elif identity == "email-fallback":
        expected_name, expected_email = "Fallback Identity", "fallback@example.invalid"
        r.git("config", "user.name", expected_name)
        r.git("config", "user.useConfigOnly", "false")
        monkeypatch.setenv("EMAIL", expected_email)
    r.trigger.write_text("new content\n")
    assert not githelper.git_commit_paths("identity", ["core/example.py"], str(r.repo)).startswith("[ERROR]")
    assert r.git("log", "-1", "--format=%an|%ae|%cn|%ce").stdout.strip() == f"{expected_name}|{expected_email}|{expected_name}|{expected_email}"
    if identity == "scalar":
        # 2001-02-03 04:05:06 UTC; avoid equivalent ISO spellings Z/+00:00.
        assert r.git("log", "-1", "--format=%at|%ct").stdout.strip() == "981173106|981173106"


@pytest.mark.parametrize("operation", ["broad", "scoped", "checkpoint"])
def test_redirect_config_hook_trace_and_fake_path_removed(repository, tmp_path, monkeypatch, operation):
    r = repository
    second = tmp_path / "second-repo"
    second.mkdir()
    r.git("init", "-b", "main", cwd=second)
    r.git("config", "user.name", "Second Identity", cwd=second)
    r.git("config", "user.email", "second@example.invalid", cwd=second)
    (second / "protected").write_text("protected bytes\n")
    r.git("add", "--", "protected", cwd=second)
    r.git("-c", "commit.gpgsign=false", "commit", "-m", "second baseline", cwd=second)
    head = r.git("rev-parse", "HEAD", cwd=second).stdout
    index = (second / ".git/index").read_bytes()
    marker = tmp_path / "untrusted-marker"
    hooks = tmp_path / "injected-hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nPath({str(marker)!r}).write_text('hook ran')\n")
    hook.chmod(0o755)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake = fake_bin / "git"
    fake.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nPath({str(marker)!r}).write_text('fake git ran')\nraise SystemExit(99)\n")
    fake.chmod(0o755)
    trace = tmp_path / "trace"
    redirects = {"GIT_DIR": str(second / ".git"), "GIT_WORK_TREE": str(second), "GIT_INDEX_FILE": str(second / ".git/index"), "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.hooksPath", "GIT_CONFIG_VALUE_0": str(hooks), "GIT_TRACE": str(trace), "GIT_EXEC_PATH": str(fake_bin), "PATH": str(fake_bin), "ARBITRARY_HOOK_SECRET": "private", "LD_PRELOAD": "/nonexistent/preload"}
    for name, value in redirects.items():
        monkeypatch.setenv(name, value)
    r.trigger.write_text("intended change\n")
    original_run = subprocess.run
    children = []

    def run(argv, **kwargs):
        children.append(kwargs["env"])
        return original_run(argv, **kwargs)

    with monkeypatch.context() as calls:
        calls.setattr(git_execution.subprocess, "run", run)
        result = commit(r, operation)
    assert result is not None and not result.startswith("[ERROR]")
    assert len(children) >= 4
    contextual = {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"} if operation != "broad" else set()
    assert all(not (set(redirects) - {"PATH"} - contextual) & child.keys() for child in children)
    if contextual:
        assert all(Path(child["GIT_DIR"]).parent == r.repo / ".git" for child in children)
        assert all(child["GIT_WORK_TREE"] == str(r.repo) and child["GIT_INDEX_FILE"] == str(r.repo / ".git/index") for child in children)
        assert all(child["GIT_OBJECT_DIRECTORY"] == str(r.repo / ".git/objects") and "GIT_COMMON_DIR" not in child for child in children)
    assert all(child["LC_ALL"] == "C" and child["GIT_CONFIG_NOSYSTEM"] == "1" and child["HOME"] == str(r.home) for child in children)
    assert len({id(child) for child in children}) == len(children)
    assert not marker.exists() and not trace.exists()
    # Inspect the second repository with a clean child environment, never the
    # injected parent redirects. HOME/XDG are disposable child values only.
    clean = git_execution._local_commit_environment()
    assert subprocess.run([r.trusted_git, "rev-parse", "HEAD"], cwd=second, env=clean, capture_output=True, text=True, check=True).stdout == head
    assert (second / ".git/index").read_bytes() == index
    assert (second / "protected").read_text() == "protected bytes\n"
    assert subprocess.run([r.trusted_git, "show", "HEAD:core/example.py"], cwd=r.repo, env=clean, capture_output=True, text=True, check=True).stdout == "intended change\n"
    rows = [json.loads(line) for line in r.audit.read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["outcome"] == "allowed"


@pytest.mark.parametrize("scoped", [False, True])
def test_helper_refusal_does_not_construct_environment(repository, monkeypatch, scoped):
    r = repository
    gate = Mock(return_value=GatewayDecision(ACT, "refused", "test policy"))
    monkeypatch.setattr(r.gateway, "gate_exec", gate)
    factory = Mock(side_effect=AssertionError("refusal must not construct runner"))
    monkeypatch.setattr(githelper, "local_commit_runner", factory)
    monkeypatch.setattr(githelper, "isolated_scoped_commit_context", factory)
    result = githelper.git_commit_paths("unused", [], str(r.repo)) if scoped else githelper.git_commit("unused", str(r.repo))
    assert result == "[ERROR] Local git commit refused: test policy"
    factory.assert_not_called()
    assert not r.audit.exists()


def test_checkpoint_context_is_inside_gate_after_inprocess_discovery(repository, monkeypatch):
    r = repository
    order = []
    original_context = checkpoint.isolated_scoped_commit_context
    original_discover = checkpoint.discover_worktree
    original_gate = r.gateway.gate_exec

    def discover(cwd):
        order.append("discover")
        return original_discover(cwd)

    @contextmanager
    def context(cwd, paths):
        order.append("context")
        with original_context(cwd, paths) as run:
            def runner(argv, **kwargs):
                order.append(argv[2] if argv[1] == "--literal-pathspecs" else argv[1])
                return run(argv, **kwargs)
            yield runner

    def gate(**kwargs):
        order.append("gate")
        return original_gate(**kwargs)

    monkeypatch.setattr(checkpoint, "discover_worktree", discover)
    monkeypatch.setattr(checkpoint, "isolated_scoped_commit_context", context)
    monkeypatch.setattr(r.gateway, "gate_exec", gate)
    r.trigger.write_text("change\n")
    assert checkpoint._create_git_commit("ordering", [str(r.trigger)])
    assert order == ["discover", "gate", "context", "add", "diff", "commit", "rev-parse"]


def test_all_missing_candidates_still_build_nonempty_path_without_filesystem_probes(tmp_path, monkeypatch):
    candidates = (tmp_path / "missing-one/git", tmp_path / "missing-two/git")
    monkeypatch.setattr(git_execution, "_git_candidates", lambda: candidates)
    forbidden = Mock(side_effect=AssertionError("profile construction must not probe the filesystem"))
    monkeypatch.setattr(Path, "exists", forbidden)
    monkeypatch.setattr(Path, "stat", forbidden)
    monkeypatch.setattr(Path, "lstat", forbidden)
    monkeypatch.setattr(git_execution.os, "access", forbidden)
    monkeypatch.setattr(git_execution, "_trusted_git_executable", forbidden)
    monkeypatch.setattr(git_execution.subprocess, "run", forbidden)
    environment = git_execution._local_commit_environment()
    assert environment["PATH"] == os.pathsep.join(str(candidate.parent) for candidate in candidates)
    assert os.get_exec_path(environment) == [str(candidate.parent) for candidate in candidates]
    assert "" not in os.get_exec_path(environment) and "." not in os.get_exec_path(environment)
    forbidden.assert_not_called()


def test_no_absolute_candidate_parents_reject_profile_before_selection_or_spawn(monkeypatch):
    monkeypatch.setattr(git_execution, "_git_candidates", lambda: (Path("relative/git"),))
    forbidden = Mock(side_effect=AssertionError("invalid profile must not probe or execute"))
    monkeypatch.setattr(Path, "exists", forbidden)
    monkeypatch.setattr(Path, "stat", forbidden)
    monkeypatch.setattr(Path, "lstat", forbidden)
    monkeypatch.setattr(git_execution.os, "access", forbidden)
    monkeypatch.setattr(git_execution, "_trusted_git_executable", forbidden)
    monkeypatch.setattr(git_execution.subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="No absolute Git installation directories"):
        git_execution.local_commit_runner()
    forbidden.assert_not_called()
