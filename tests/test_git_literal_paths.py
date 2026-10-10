"""Literal scoped pathnames in disposable Git; state isolated before collection."""

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, checkpoint, git_execution, githelper
from core.action_gateway import ActionGateway
from core.state import StateStore

MODE_KEYS = {"GIT_LITERAL_PATHSPECS", "GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS", "GIT_ICASE_PATHSPECS"}


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
    home, xdg = tmp_path / "child-home", tmp_path / "child-xdg"
    home.mkdir()
    xdg.mkdir()
    original_environment = git_execution._local_commit_environment

    def environment():
        child = original_environment()
        child.update(HOME=str(home), XDG_CONFIG_HOME=str(xdg))
        return child

    monkeypatch.setattr(git_execution, "_local_commit_environment", environment)
    # Public status keeps its ambient profile. Replace HOME/XDG only in the
    # child forwarding seam, never in os.environ or production query behavior.
    original_run = githelper.run_git

    def public_run(argv, **kwargs):
        child = dict(kwargs["env"])
        child.update(HOME=str(home), XDG_CONFIG_HOME=str(xdg))
        return original_run(argv, **{**kwargs, "env": child})

    monkeypatch.setattr(githelper, "run_git", public_run)
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args, cwd=repo, check=True):
        return subprocess.run([trusted_git, *args], cwd=cwd, capture_output=True, text=True, check=check)

    git("init", "-b", "main")
    for key, value in {"core.hooksPath": str(empty), "commit.gpgsign": "false", "tag.gpgsign": "false", "user.useConfigOnly": "true", "user.name": "Temporary Test", "user.email": "test@example.invalid"}.items():
        git("config", key, value)
    (repo / "core").mkdir()
    (repo / "core/example.py").write_text("baseline core\n")
    (repo / "unrelated.txt").write_text("baseline unrelated\n")
    git("add", "-A")
    git("commit", "-m", "baseline")
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: ActionGateway(audit_file=audit))
    state = StateStore(db_path=tmp_path / "state.db")
    monkeypatch.setattr(checkpoint, "CODE_DIR", repo)
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "backups")
    monkeypatch.setattr(checkpoint, "get_state_store", lambda: state)
    monkeypatch.setattr(checkpoint, "warning", Mock())
    yield SimpleNamespace(repo=repo, git=git, audit=audit, state=state, backups=tmp_path / "backups")
    state.close()


def files(r, names):
    for name in names:
        file = r.repo / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("baseline target\n")
    r.git("add", "-A")
    r.git("commit", "-m", "file baseline")


def invoke(r, paths, operation="helper", cwd=None):
    if operation == "checkpoint":
        assert cwd is None
        return checkpoint._create_git_commit("literal paths", paths)
    return githelper.git_commit_paths("literal paths", paths, str(cwd or r.repo))


def names(r, *args):
    return {name for name in r.git(*args).stdout.split("\0") if name}


def audit(r, operation, outcome="allowed"):
    rows = [json.loads(line) for line in r.audit.read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert row["authority"] == "ACT" and row["outcome"] == outcome
    assert row["action"] == ("githelper.git_commit_paths" if operation == "helper" else "checkpoint.create_git_commit")
    assert set(row) == {"ts", "authority", "action", "command", "outcome", "reason"}


def test_prior_wildcard_stage_overscope_then_literal_helper_commit(repository):
    r = repository
    files(r, ["*.py", "neighbor.py"])
    (r.repo / "*.py").write_text("literal change\n")
    (r.repo / "neighbor.py").write_text("neighbor dirty\n")
    # Reproduce the old argv only in this disposable repository.
    r.git("add", "--", "*.py")
    assert names(r, "diff", "--cached", "--name-only", "-z") == {"*.py", "neighbor.py"}
    r.git("reset", "--mixed", "HEAD")
    assert not invoke(r, ["*.py"]).startswith("[ERROR]")
    assert r.git("show", "HEAD:*.py").stdout == "literal change\n"
    assert r.git("show", "HEAD:neighbor.py").stdout == "baseline target\n"
    assert (r.repo / "neighbor.py").read_text() == "neighbor dirty\n"
    audit(r, "helper")


@pytest.mark.parametrize(("literal", "neighbor"), [("*", "neighbor"), ("?", "a"), ("[abc]", "a"), (":(glob)*.py", "neighbor.py"), (":(top)*.py", "neighbor.py"), (":", "neighbor"), ("--filename", "neighbor")])
@pytest.mark.parametrize("operation", ["helper", "checkpoint"])
def test_special_filenames_commit_only_literal_and_preserve_unrelated_index(repository, literal, neighbor, operation):
    r = repository
    files(r, [literal, neighbor])
    (r.repo / literal).write_text("literal changed\n")
    (r.repo / neighbor).write_text("tempting dirty neighbor\n")
    (r.repo / "unrelated.txt").write_text("unrelated staged\n")
    r.git("add", "--", "unrelated.txt")
    result = invoke(r, [literal], operation)
    assert result is not None and not result.startswith("[ERROR]")
    assert names(r, "ls-tree", "-rz", "--name-only", "HEAD") == {literal, neighbor, "core/example.py", "unrelated.txt"}
    assert r.git("show", f"HEAD:{literal}").stdout == "literal changed\n"
    assert r.git("show", f"HEAD:{neighbor}").stdout == "baseline target\n"
    assert names(r, "diff", "--cached", "--name-only", "-z") == {"unrelated.txt"}
    audit(r, operation)


@pytest.mark.parametrize("form", ["root-relative", "subdir-cwd", "absolute"])
def test_literal_path_forms_are_not_rewritten(repository, form):
    r = repository
    files(r, ["sub/literal*.py", "sub/neighbor.py"])
    (r.repo / "sub/literal*.py").write_text("changed\n")
    (r.repo / "sub/neighbor.py").write_text("neighbor dirty\n")
    operand = "literal*.py" if form == "subdir-cwd" else str(r.repo / "sub/literal*.py") if form == "absolute" else "sub/literal*.py"
    cwd = r.repo / "sub" if form == "subdir-cwd" else r.repo
    assert not invoke(r, [operand], cwd=cwd).startswith("[ERROR]")
    assert r.git("show", "HEAD:sub/literal*.py").stdout == "changed\n"
    assert r.git("show", "HEAD:sub/neighbor.py").stdout == "baseline target\n"
    audit(r, "helper")


@pytest.mark.parametrize("operation", ["helper", "checkpoint"])
@pytest.mark.parametrize("operand", ["*.py", ":(glob)*.py"])
def test_nonexistent_literal_does_not_stage_matching_neighbors(repository, operand, operation):
    r = repository
    files(r, ["neighbor.py"])
    (r.repo / "neighbor.py").write_text("neighbor dirty\n")
    head = r.git("rev-parse", "HEAD").stdout
    index = r.git("ls-files", "--stage").stdout
    result = invoke(r, [operand], operation)
    assert result is None if operation == "checkpoint" else result.startswith("[ERROR] git add failed:")
    assert r.git("rev-parse", "HEAD").stdout == head
    assert r.git("ls-files", "--stage").stdout == index
    audit(r, operation, "failed")


@pytest.mark.parametrize("operation", ["helper", "checkpoint"])
def test_deleted_tracked_literal_commits_deletion_without_neighbor(repository, operation):
    r = repository
    files(r, ["*.py", "neighbor.py"])
    (r.repo / "*.py").unlink()
    (r.repo / "neighbor.py").write_text("neighbor dirty\n")
    result = invoke(r, ["*.py"], operation)
    assert result is not None and not result.startswith("[ERROR]")
    assert "*.py" not in names(r, "ls-tree", "-rz", "--name-only", "HEAD")
    assert r.git("show", "HEAD:neighbor.py").stdout == "baseline target\n"
    audit(r, operation)


@pytest.mark.parametrize("directory", ["*", "ordinary", "."])
def test_directories_intentionally_select_subtrees(repository, directory):
    r = repository
    child = "ordinary/child" if directory == "." else f"{directory}/child"
    files(r, [child, "neighbor/child"])
    (r.repo / child).write_text("subtree change\n")
    (r.repo / "neighbor/child").write_text("neighbor change\n")
    assert not invoke(r, [directory]).startswith("[ERROR]")
    assert r.git("show", f"HEAD:{child}").stdout == "subtree change\n"
    assert r.git("show", "HEAD:neighbor/child").stdout == ("neighbor change\n" if directory == "." else "baseline target\n")
    audit(r, "helper")


def test_absolute_outside_path_keeps_git_error(repository, tmp_path):
    r = repository
    outside = tmp_path / "outside.py"
    outside.write_text("protected\n")
    head = r.git("rev-parse", "HEAD").stdout
    result = invoke(r, [str(outside)])
    assert result.startswith("[ERROR] git add failed:") and "outside repository" in result
    assert r.git("rev-parse", "HEAD").stdout == head and outside.read_text() == "protected\n"
    audit(r, "helper", "failed")


@pytest.mark.parametrize("mode", sorted(MODE_KEYS))
def test_public_status_is_literal_under_each_ambient_mode(repository, monkeypatch, mode):
    r = repository
    files(r, ["Case*.py", "caseNeighbor.py"])
    (r.repo / "Case*.py").write_text("literal dirty\n")
    (r.repo / "caseNeighbor.py").write_text("neighbor dirty\n")
    monkeypatch.setenv(mode, "1")
    result = githelper.git_status_paths(["Case*.py"], str(r.repo))
    assert "Case*.py" in result and "caseNeighbor.py" not in result
    assert os.environ[mode] == "1" and not r.audit.exists()


def test_public_status_empty_list_retains_unrestricted_status(repository):
    r = repository
    (r.repo / "core/example.py").write_text("changed\n")
    (r.repo / "unrelated.txt").write_text("changed\n")
    result = githelper.git_status_paths([], str(r.repo))
    assert "core/example.py" in result and "unrelated.txt" in result
    assert not r.audit.exists()


def test_public_status_removes_exactly_four_env_keys_and_preserves_operands(monkeypatch):
    for key in MODE_KEYS:
        monkeypatch.setenv(key, "1")
    monkeypatch.setenv("PRESERVE_QUERY_SENTINEL", "unchanged")
    before = dict(os.environ)
    runner = Mock(return_value=SimpleNamespace(stdout="original status\n"))
    monkeypatch.setattr(githelper, "run_git", runner)
    operands = ["*.py", ":(glob)*", b"raw?bytes"]
    assert githelper.git_status_paths(operands, "/temporary cwd") == "original status"
    argv = runner.call_args.args[0]
    assert argv == ["git", "--literal-pathspecs", "status", "--short", "--", *operands]
    assert runner.call_args.kwargs.keys() == {"env", "capture_output", "text", "cwd"}
    child = runner.call_args.kwargs["env"]
    assert child is not os.environ and not child.keys() & MODE_KEYS
    preserved = child == {key: value for key, value in before.items() if key not in MODE_KEYS}
    unchanged = dict(os.environ) == before
    assert preserved and unchanged
    assert runner.call_args.kwargs["cwd"] == "/temporary cwd"


@pytest.mark.parametrize("operation", ["scoped", "broad", "checkpoint"])
def test_exact_scoped_flags_and_unchanged_broad_queries(monkeypatch, tmp_path, operation):
    operands = ["*.py", ":(glob)*", b"raw?bytes"]
    before = list(operands)
    responses = [SimpleNamespace(returncode=0, stdout=".git", stderr=""), SimpleNamespace(returncode=0, stdout="", stderr=""), SimpleNamespace(returncode=1 if operation == "checkpoint" else 0, stdout="M target", stderr=""), SimpleNamespace(returncode=0, stdout="original result", stderr="")]
    if operation == "checkpoint":
        responses.append(SimpleNamespace(returncode=0, stdout="saved hash\n", stderr=""))
    runner = Mock(side_effect=responses)
    monkeypatch.setattr(githelper, "local_commit_runner", Mock(return_value=runner))
    monkeypatch.setattr(checkpoint, "local_commit_runner", Mock(return_value=runner))
    monkeypatch.setattr(checkpoint, "CODE_DIR", Path("/temporary cwd"))
    audit_file = tmp_path / "audit.jsonl"
    instance = ActionGateway(audit_file=audit_file)
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: instance)
    forbidden = Mock(side_effect=AssertionError("no operand existence/normalization probes"))
    with monkeypatch.context() as probes:
        probes.setattr(Path, "exists", forbidden)
        probes.setattr(Path, "resolve", forbidden)
        if operation == "checkpoint":
            result = checkpoint._create_git_commit("message", operands)
            wanted = "saved hash"
            expected = [["git", "rev-parse", "--git-dir"], ["git", "--literal-pathspecs", "add", "--", *operands], ["git", "--literal-pathspecs", "diff", "--cached", "--quiet", "--", *operands], ["git", "--literal-pathspecs", "commit", "-m", "Codey checkpoint: message", "--", *operands], ["git", "rev-parse", "HEAD"]]
        elif operation == "scoped":
            result = githelper.git_commit_paths("message", operands, "/temporary cwd")
            wanted = "original result"
            expected = [["git", "rev-parse", "--git-dir"], ["git", "--literal-pathspecs", "add", "--", *operands], ["git", "--literal-pathspecs", "status", "--short", "--", *operands], ["git", "--literal-pathspecs", "commit", "-m", "message", "--", *operands]]
        else:
            result = githelper.git_commit("message", "/temporary cwd")
            wanted = "original result"
            expected = [["git", "rev-parse", "--git-dir"], ["git", "add", "-A"], ["git", "status", "--short"], ["git", "commit", "-m", "message"]]
    assert result == wanted
    assert [call.args[0] for call in runner.call_args_list] == expected
    assert operands == before
    forbidden.assert_not_called()
    records = [json.loads(line) for line in audit_file.read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["authority"] == "ACT" and records[0]["outcome"] == "allowed"


def test_create_checkpoint_literal_wildcard_backup_sqlite_hash(repository):
    r = repository
    files(r, ["core/*.py", "core/neighbor.py"])
    (r.repo / "core/*.py").write_text("wildcard backup bytes\n")
    (r.repo / "core/neighbor.py").write_text("neighbor dirty\n")
    checkpoint_id = checkpoint.create_checkpoint("literal integration", [str(r.repo / "core/*.py")])
    row = r.state.get_checkpoint(checkpoint_id)
    assert row["git_commit_hash"] == r.git("rev-parse", "HEAD").stdout.strip()
    assert (r.backups / checkpoint_id / "core/*.py").read_text() == "wildcard backup bytes\n"
    assert r.git("show", "HEAD:core/*.py").stdout == "wildcard backup bytes\n"
    assert r.git("show", "HEAD:core/neighbor.py").stdout == "baseline target\n"
    assert json.loads(row["files_modified"]) == [str(r.repo / "core/*.py")]
    audit(r, "checkpoint")
