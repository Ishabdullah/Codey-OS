"""Isolated broad commits and bounded native merge continuation."""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from core import (
    action_gateway,
    checkpoint,
    git_commit_context,
    git_execution,
    githelper,
)
from core.action_gateway import ACT, GatewayDecision
from tests.test_git_commit_context import marker_script
from tests.test_git_literal_paths import repository as isolated_repository


@pytest.fixture
def repository(tmp_path, monkeypatch):
    yield from isolated_repository.__wrapped__(tmp_path, monkeypatch)


def records(r):
    return [json.loads(line) for line in r.audit.read_text().splitlines()]


def clean_merge(r):
    r.git("checkout", "-b", "incoming")
    r.git("commit", "--allow-empty", "-m", "incoming empty")
    incoming = r.git("rev-parse", "HEAD").stdout.strip()
    r.git("checkout", "main")
    r.git("commit", "--allow-empty", "-m", "main empty")
    before = r.git("rev-parse", "HEAD").stdout.strip()
    r.git("merge", "--no-ff", "--no-commit", "incoming")
    assert r.git("status", "--short").stdout == ""
    return before, incoming


def test_real_helper_clean_pending_merge_commits_two_parents(repository):
    r = repository
    before, incoming = clean_merge(r)
    tree = r.git("rev-parse", "HEAD^{tree}").stdout
    result = githelper.git_commit("complete clean merge", str(r.repo))
    assert result != "Nothing to commit — working tree clean."
    assert not result.startswith("[ERROR]"), result
    assert r.git("rev-parse", "HEAD^{tree}").stdout == tree
    assert r.git("show", "-s", "--format=%P", "HEAD").stdout.strip().split() == [before, incoming]
    assert not (r.repo / ".git/MERGE_HEAD").exists()
    assert len(records(r)) == 1 and records(r)[0]["outcome"] == "allowed"


def invoke(r, *, add_all=True, cwd=None):
    return githelper.git_commit("broad context test", str(cwd or r.repo), add_all=add_all)


def assert_record(r, outcome="allowed"):
    ledger = records(r)
    assert len(ledger) == 1 and ledger[0]["authority"] == "ACT"
    assert ledger[0]["action"] == "githelper.git_commit" and ledger[0]["outcome"] == outcome
    assert ledger[0]["command"] == "local git commit attempt"
    assert not (r.repo / ".git/HEAD.lock").exists()
    assert not list((r.repo / ".git").glob("codey-scoped-*"))
    return ledger[0]


@pytest.mark.parametrize("state", ["attached", "unborn", "detached", "packed", "sha256"])
def test_real_broad_states(repository, tmp_path, state):
    r = repository
    if state == "unborn":
        r.git("checkout", "--orphan", "newborn")
        r.git("rm", "--cached", "-r", ".")
    elif state == "detached":
        r.git("checkout", "--detach")
    elif state == "packed":
        r.git("pack-refs", "--all")
    elif state == "sha256":
        repo = tmp_path / "sha256"
        repo.mkdir()
        r.git("init", "--object-format=sha256", "-b", "main", cwd=repo)
        for key, value in {"user.name": "Test", "user.email": "test@example.invalid", "user.useConfigOnly": "true"}.items():
            r.git("config", key, value, cwd=repo)
        original_git = r.git
        r.git = lambda *args, **kwargs: original_git(*args, cwd=repo, **kwargs)
        r.repo = repo
        (repo / "core").mkdir()
    (r.repo / "core/example.py").write_text("broad version\n")
    assert not invoke(r).startswith("[ERROR]")
    assert r.git("show", "HEAD:core/example.py").stdout == "broad version\n"
    tree = r.git("ls-tree", "-rz", "--name-only", "HEAD").stdout
    assert "codey-scoped-" not in tree and ".git/" not in tree
    assert_record(r)


def test_add_all_from_subcwd_includes_whole_repository(repository):
    r = repository
    (r.repo / "outside.py").write_text("tracked\n")
    r.git("add", "outside.py")
    r.git("commit", "-m", "track outside")
    (r.repo / "outside.py").unlink()
    (r.repo / "new.py").write_text("outside new\n")
    (r.repo / "core/example.py").write_text("inside modified\n")
    assert not invoke(r, cwd=r.repo / "core").startswith("[ERROR]")
    assert r.git("show", "HEAD:new.py").stdout == "outside new\n"
    assert r.git("show", "HEAD:core/example.py").stdout == "inside modified\n"
    assert "outside.py" not in r.git("ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines()
    assert_record(r)


def test_staged_only_preserves_blobs_with_dirty_filtered_files(repository, tmp_path, monkeypatch):
    r = repository
    (r.repo / "core/example.py").write_text("already staged\n")
    r.git("add", "core/example.py")
    staged = r.git("rev-parse", ":core/example.py").stdout
    (r.repo / "core/example.py").write_text("different dirty worktree\n")
    (r.repo / ".gitattributes").write_text("*.secret filter=driver\n")
    (r.repo / "untracked.secret").write_text("leave untracked\n")
    marker, script = marker_script(tmp_path)
    r.git("config", "filter.driver.clean", str(script))
    r.git("config", "filter.driver.required", "true")
    original = git_execution.run_git
    commands = []
    def run(argv, **kwargs):
        commands.append(argv)
        return original(argv, **kwargs)
    with monkeypatch.context() as patches:
        patches.setattr(git_execution, "run_git", run)
        assert not invoke(r, add_all=False).startswith("[ERROR]")
    assert r.git("rev-parse", "HEAD:core/example.py").stdout == staged
    assert (r.repo / "core/example.py").read_text() == "different dirty worktree\n"
    assert (r.repo / "untracked.secret").read_text() == "leave untracked\n"
    assert not marker.exists()
    assert not any("add" in argv or "check-attr" in argv for argv in commands)
    assert_record(r)


def test_only_unstaged_changes_preserve_native_checked_failure(repository):
    r = repository
    old = r.git("rev-parse", "HEAD").stdout
    (r.repo / "core/example.py").write_text("unstaged\n")
    result = invoke(r, add_all=False)
    assert result.startswith("[ERROR]") and result != "Nothing to commit — working tree clean."
    assert r.git("rev-parse", "HEAD").stdout == old
    assert r.git("diff", "--cached", "--name-only").stdout == ""
    assert assert_record(r, "failed")["reason"] == result


@pytest.mark.parametrize("source", ["repository", "home", "xdg", "include"])
def test_broad_positive_identity_and_executable_configs(repository, tmp_path, source):
    r = repository
    env = git_execution._local_commit_environment()
    for key in ("user.name", "user.email"):
        r.git("config", "--unset", key)
    data = '[user]\n name = Broad Identity\n email = broad@example.invalid\n'
    if source == "repository":
        r.git("config", "user.name", "Broad Identity")
        r.git("config", "user.email", "broad@example.invalid")
    else:
        target = Path(env["HOME"]) / ".gitconfig" if source == "home" else Path(env["XDG_CONFIG_HOME"]) / "git/config" if source == "xdg" else r.repo / "identity config"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data)
        if source == "include":
            r.git("config", "include.path", str(target))
    marker, script = marker_script(tmp_path)
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "pre-commit").write_bytes(script.read_bytes())
    (hooks / "pre-commit").chmod(0o755)
    for key, value in {"core.hooksPath": str(hooks), "core.fsmonitor": str(script), "commit.gpgSign": "true", "gpg.program": str(script), "diff.external": str(script), "core.pager": str(script), "filter.unused.clean": str(script)}.items():
        r.git("config", key, value)
    (r.repo / "core/example.py").write_text("positive data\n")
    assert not invoke(r).startswith("[ERROR]")
    assert not marker.exists()
    assert r.git("log", "-1", "--format=%an <%ae>").stdout.strip() == "Broad Identity <broad@example.invalid>"
    assert "gpgsig" not in r.git("cat-file", "commit", "HEAD").stdout
    assert_record(r)


@pytest.mark.parametrize("conversion", ["crlf", "utf16"])
def test_broad_native_conversion(repository, conversion):
    r = repository
    if conversion == "crlf":
        (r.repo / ".gitattributes").write_text("native.txt text eol=crlf\n")
        value, blob = b"native\r\n", b"native\n"
    else:
        (r.repo / ".gitattributes").write_text("native.txt text working-tree-encoding=UTF-16\n")
        value, blob = "native\n".encode("utf-16"), b"native\n"
    (r.repo / "native.txt").write_bytes(value)
    assert not invoke(r).startswith("[ERROR]")
    assert subprocess.run([git_execution._trusted_git_executable(), "show", "HEAD:native.txt"], cwd=r.repo, capture_output=True, check=True).stdout == blob
    assert (r.repo / "native.txt").read_bytes() == value
    assert_record(r)


@pytest.mark.parametrize("hazard", ["filter", "embedded", "gitlink"])
def test_add_all_hazards_outside_subcwd_fail_before_stage(repository, tmp_path, hazard):
    r = repository
    before = (r.repo / ".git/index").read_bytes()
    marker, script = marker_script(tmp_path)
    if hazard == "filter":
        (r.repo / ".gitattributes").write_text("outside filter=driver\n")
        (r.repo / "outside").write_text("hazard\n")
        r.git("config", "filter.driver.clean", str(script))
    else:
        embedded = r.repo / "outside"
        embedded.mkdir()
        r.git("init", "-b", "main", cwd=embedded)
        if hazard == "gitlink":
            hash_value = r.git("rev-parse", "HEAD").stdout.strip()
            r.git("update-index", "--add", "--cacheinfo", "160000", hash_value, "outside")
            before = (r.repo / ".git/index").read_bytes()
    result = invoke(r, cwd=r.repo / "core")
    assert result.startswith("[ERROR]")
    assert (r.repo / ".git/index").read_bytes() == before and not marker.exists()
    assert_record(r, "failed")


def conflict(r):
    r.git("checkout", "-b", "incoming")
    (r.repo / "core/example.py").write_text("incoming\n")
    r.git("add", "-A")
    r.git("commit", "-m", "incoming")
    incoming = r.git("rev-parse", "HEAD").stdout.strip()
    r.git("checkout", "main")
    (r.repo / "core/example.py").write_text("main\n")
    r.git("add", "-A")
    r.git("commit", "-m", "main")
    before = r.git("rev-parse", "HEAD").stdout.strip()
    assert r.git("merge", "incoming", check=False).returncode != 0
    return before, incoming


@pytest.mark.parametrize("add_all", [False, True])
def test_real_resolved_conflict_has_two_parents_and_cleans_metadata(repository, add_all):
    r = repository
    before, incoming = conflict(r)
    original = (r.repo / ".git/ORIG_HEAD").read_bytes()
    (r.repo / "core/example.py").write_text("resolution\n")
    if not add_all:
        r.git("add", "core/example.py")
    assert not invoke(r, add_all=add_all).startswith("[ERROR]")
    assert r.git("show", "-s", "--format=%P", "HEAD").stdout.strip().split() == [before, incoming]
    assert r.git("show", "HEAD:core/example.py").stdout == "resolution\n"
    assert (r.repo / ".git/ORIG_HEAD").read_bytes() == original
    for name in ("MERGE_HEAD", "MERGE_MSG", "MERGE_MODE", "AUTO_MERGE"):
        assert not (r.repo / ".git" / name).exists()
    assert_record(r)


def test_unresolved_staged_only_retains_native_pending_state(repository):
    r = repository
    old, _ = conflict(r)
    metadata = {p.name: p.read_bytes() for p in (r.repo / ".git").glob("MERGE_*")}
    result = invoke(r, add_all=False)
    assert result.startswith("[ERROR]")
    assert r.git("rev-parse", "HEAD").stdout.strip() == old
    assert {p.name: p.read_bytes() for p in (r.repo / ".git").glob("MERGE_*")} == metadata
    assert_record(r, "failed")


def test_real_squash_keeps_one_parent_and_removes_message(repository):
    r = repository
    r.git("checkout", "-b", "incoming")
    (r.repo / "extra").write_text("squash content\n")
    r.git("add", "-A")
    r.git("commit", "-m", "incoming")
    r.git("checkout", "main")
    old = r.git("rev-parse", "HEAD").stdout.strip()
    r.git("merge", "--squash", "incoming")
    assert (r.repo / ".git/SQUASH_MSG").exists()
    assert not invoke(r).startswith("[ERROR]")
    assert r.git("show", "-s", "--format=%P", "HEAD").stdout.strip() == old
    assert not (r.repo / ".git/SQUASH_MSG").exists()
    assert_record(r)


@pytest.mark.parametrize("state", ["autostash", "rerere-file", "rerere-cache", "multi-head", "mode", "mixed", "orphan", "symlink", "large-message", "large-squash", "large-head", "large-mode", "invalid-auto", "cherry", "revert", "rebase", "sequencer"])
def test_unsupported_metadata_fails_before_add(repository, state):
    r = repository
    clean_merge(r)
    real = r.repo / ".git"
    old = r.git("rev-parse", "HEAD").stdout
    index = (real / "index").read_bytes()
    incoming = (real / "MERGE_HEAD").read_bytes()
    if state == "autostash":
        (real / "MERGE_AUTOSTASH").write_bytes(incoming)
    elif state == "rerere-file":
        (real / "MERGE_RR").write_bytes(b"")
    elif state == "rerere-cache":
        (real / "rr-cache").mkdir()
    elif state == "multi-head":
        (real / "MERGE_HEAD").write_bytes(incoming * 2)
    elif state == "mode":
        (real / "MERGE_MODE").write_text("unsupported")
    elif state == "mixed":
        (real / "SQUASH_MSG").write_text("mixed")
    elif state == "orphan":
        (real / "MERGE_HEAD").unlink()
    elif state == "symlink":
        (real / "MERGE_MSG").unlink()
        (real / "MERGE_MSG").symlink_to(real / "MERGE_HEAD")
    elif state.startswith("large-"):
        name = {"large-message": "MERGE_MSG", "large-squash": "SQUASH_MSG", "large-head": "MERGE_HEAD", "large-mode": "MERGE_MODE"}[state]
        if state == "large-squash":
            for merge_name in ("MERGE_HEAD", "MERGE_MSG", "MERGE_MODE"):
                (real / merge_name).unlink()
        (real / name).write_bytes(b"x" * (1024 * 1024 + 1 if name.endswith("MSG") else 257))
    elif state == "invalid-auto":
        (real / "AUTO_MERGE").write_text("malformed")
    else:
        (real / {"cherry": "CHERRY_PICK_HEAD", "revert": "REVERT_HEAD", "rebase": "rebase-merge", "sequencer": "sequencer"}[state]).mkdir()
    result = invoke(r)
    assert result.startswith("[ERROR]")
    assert r.git("rev-parse", "HEAD").stdout == old and (real / "index").read_bytes() == index
    assert_record(r, "failed")


@pytest.mark.parametrize("consumer", ["scoped", "checkpoint"])
def test_active_merge_still_unsupported_for_scoped_consumers(repository, consumer):
    r = repository
    clean_merge(r)
    before = (r.repo / ".git/index").read_bytes()
    result = githelper.git_commit_paths("scoped", ["core/example.py"], str(r.repo)) if consumer == "scoped" else checkpoint._create_git_commit("scoped", ["core/example.py"])
    assert result is None if consumer == "checkpoint" else result.startswith("[ERROR]")
    assert (r.repo / ".git/index").read_bytes() == before
    assert records(r)[0]["outcome"] == "failed"


def test_refusal_constructs_nothing(repository, monkeypatch):
    r = repository
    forbidden = Mock(side_effect=AssertionError("must not construct"))
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: SimpleNamespace(gate_exec=Mock(return_value=GatewayDecision(ACT, "refused", "policy"))))
    monkeypatch.setattr(githelper, "isolated_broad_commit_context", forbidden)
    monkeypatch.setattr(git_execution, "run_git", forbidden)
    assert invoke(r) == "[ERROR] Local git commit refused: policy"
    forbidden.assert_not_called()
    assert not r.audit.exists()


def test_mocked_commit_success_cannot_delete_pending_state(repository, monkeypatch):
    r = repository
    clean_merge(r)
    original = git_execution.run_git
    before = (r.repo / ".git/MERGE_HEAD").read_bytes()
    def run(argv, **kwargs):
        if argv[:3] == ["git", "commit", "-m"]:
            return subprocess.CompletedProcess(argv, 0, "mock success", "")
        return original(argv, **kwargs)
    monkeypatch.setattr(git_execution, "run_git", run)
    assert "no verified HEAD transition" in invoke(r)
    assert (r.repo / ".git/MERGE_HEAD").read_bytes() == before
    assert_record(r, "failed")


@pytest.mark.parametrize("failure", ["verify", "output", "unlink", "rmtree", "changed", "replaced", "absent"])
def test_real_commit_later_failure_is_honest_and_snapshot_guarded(repository, monkeypatch, failure):
    r = repository
    old, incoming = clean_merge(r)
    real = r.repo / ".git"
    snapshots = {name: (real / name).read_bytes() for name in ("MERGE_HEAD", "MERGE_MSG", "MERGE_MODE")}
    original_run, original_unlink, original_remove = git_execution.run_git, Path.unlink, shutil.rmtree
    exception = OSError("original later error")
    leaked = []
    def run(argv, **kwargs):
        if failure == "verify" and argv[:4] == ["git", "show", "-s", "--format=%P"]:
            raise exception
        result = original_run(argv, **kwargs)
        if argv[:3] == ["git", "commit", "-m"]:
            if failure == "output":
                raise exception
            if failure == "changed":
                (real / "MERGE_MODE").write_text("changed")
            if failure == "replaced":
                (real / "MERGE_MODE").unlink()
                (real / "MERGE_MODE").write_bytes(snapshots["MERGE_MODE"])
            if failure == "absent":
                (real / "SQUASH_MSG").write_text("appeared")
        return result
    def unlink(path, *args, **kwargs):
        if failure == "unlink" and path == real / "MERGE_HEAD":
            raise exception
        return original_unlink(path, *args, **kwargs)
    def remove(path, **kwargs):
        if failure == "rmtree" and Path(path).name.startswith("codey-scoped-"):
            leaked.append(path)
            raise exception
        return original_remove(path, **kwargs)
    try:
        with monkeypatch.context() as patches:
            patches.setattr(git_execution, "run_git", run)
            patches.setattr(Path, "unlink", unlink)
            patches.setattr(git_commit_context.shutil, "rmtree", remove)
            if failure in ("verify", "output", "unlink", "rmtree"):
                with pytest.raises(OSError) as caught:
                    invoke(r)
                assert caught.value is exception
            else:
                assert invoke(r).startswith("[ERROR]")
        assert r.git("show", "-s", "--format=%P", "HEAD").stdout.strip().split() == [old, incoming]
        if failure in ("verify", "changed", "replaced", "absent", "unlink"):
            assert (real / "MERGE_HEAD").read_bytes() == snapshots["MERGE_HEAD"]
            assert (real / "MERGE_MSG").read_bytes() == snapshots["MERGE_MSG"]
        assert records(r)[0]["outcome"] == "failed"
    finally:
        for path in leaked:
            original_remove(path)
    assert not (real / "HEAD.lock").exists()


@pytest.mark.parametrize("operation", ["add", "commit"])
@pytest.mark.parametrize("cleanup_kind", [None, "policy", "os"])
def test_broad_checked_error_and_cleanup_accounting(repository, monkeypatch, operation, cleanup_kind):
    r = repository
    (r.repo / "core/example.py").write_text("changed\n")
    original_run, original_remove = git_execution.run_git, shutil.rmtree
    leaked = []
    def run(argv, **kwargs):
        if argv[1] == operation:
            return subprocess.CompletedProcess(argv, 1, "", "original diagnostic\n")
        return original_run(argv, **kwargs)
    def remove(path, **kwargs):
        if cleanup_kind and Path(path).name.startswith("codey-scoped-"):
            leaked.append(path)
            raise (OSError if cleanup_kind == "os" else git_commit_context.ScopedCommitError)("private cleanup")
        return original_remove(path, **kwargs)
    try:
        with monkeypatch.context() as patches:
            patches.setattr(git_execution, "run_git", run)
            patches.setattr(git_commit_context.shutil, "rmtree", remove)
            result = invoke(r)
        expected = "[ERROR] git add failed: original diagnostic\n" if operation == "add" else "[ERROR] original diagnostic"
        if cleanup_kind:
            expected += "; scoped Git context cleanup or publication also failed"
        assert result == expected and records(r)[0]["reason"] == expected
    finally:
        for path in leaked:
            original_remove(path)
    assert_record(r, "failed")


@pytest.mark.parametrize("failure", ["finish", "output", "publication"])
def test_detached_native_commit_survives_later_failure(repository, monkeypatch, failure):
    r = repository
    r.git("checkout", "--detach")
    old = r.git("rev-parse", "HEAD").stdout.strip()
    (r.repo / "core/example.py").write_text("detached new bytes\n")
    original_run = git_execution.run_git
    original_finish = git_commit_context._Context.finish_metadata
    exception = OSError("detached later error")
    def run(argv, **kwargs):
        result = original_run(argv, **kwargs)
        if failure == "output" and argv[:3] == ["git", "commit", "-m"]:
            raise exception
        return result
    def finish(context):
        original_finish(context)
        if failure == "finish":
            raise exception
    def replace(*args, **kwargs):
        raise exception
    monkeypatch.setattr(git_execution, "run_git", run)
    monkeypatch.setattr(git_commit_context._Context, "finish_metadata", finish)
    if failure == "publication":
        monkeypatch.setattr(git_commit_context.os, "replace", replace)
    with pytest.raises(OSError) as caught:
        invoke(r)
    assert caught.value is exception
    if failure == "publication":
        assert r.git("rev-parse", "HEAD").stdout.strip() == old
        assert r.git("diff", "--cached", "--name-only").stdout.strip() == "core/example.py"
    else:
        assert r.git("rev-parse", "HEAD^").stdout.strip() == old
        assert r.git("show", "HEAD:core/example.py").stdout == "detached new bytes\n"
    assert_record(r, "failed")


def test_actual_head_change_retains_all_pending_metadata(repository, monkeypatch):
    r = repository
    clean_merge(r)
    real = r.repo / ".git"
    snapshots = {name: (real / name).read_bytes() for name in ("MERGE_HEAD", "MERGE_MSG", "MERGE_MODE")}
    original = git_execution.run_git
    def run(argv, **kwargs):
        result = original(argv, **kwargs)
        if argv[:3] == ["git", "commit", "-m"]:
            (real / "HEAD").write_text("ref: refs/heads/replaced\n")
        return result
    monkeypatch.setattr(git_execution, "run_git", run)
    assert "Actual Git HEAD changed" in invoke(r)
    assert {name: (real / name).read_bytes() for name in snapshots} == snapshots
    assert (real / "HEAD").read_text() == "ref: refs/heads/replaced\n"
    assert_record(r, "failed")


def test_uppercase_incoming_oid_preserves_native_merge(repository):
    r = repository
    old, incoming = clean_merge(r)
    (r.repo / ".git/MERGE_HEAD").write_text(incoming.upper() + "\n")
    assert r.git("cat-file", "-t", incoming.upper()).stdout.strip() == "commit"
    assert not invoke(r).startswith("[ERROR]")
    assert r.git("show", "-s", "--format=%P", "HEAD").stdout.strip().split() == [old, incoming]
    assert_record(r)


@pytest.mark.parametrize("argv", [["git", "commit", "--amend", "-m", "bad"], ["git", "add", "-A", "--", "."], ["git", "status", "--porcelain"], ["git", "rev-parse", "HEAD"], ["git", "commit", "-m", "good", "--", "file"]])
def test_broad_runner_rejects_nonbusiness_argv(repository, monkeypatch, argv):
    r = repository
    with git_commit_context.isolated_broad_commit_context(str(r.repo)) as context:
        forbidden = Mock(side_effect=AssertionError("business command must not spawn"))
        monkeypatch.setattr(context, "_run", forbidden)
        with pytest.raises(ValueError):
            context.run(argv, cwd=str(r.repo), capture_output=True, text=True)
        forbidden.assert_not_called()


def test_staged_only_runner_rejects_add_and_cwd_override(repository, monkeypatch):
    r = repository
    with git_commit_context.isolated_broad_commit_context(str(r.repo), add_all=False) as context:
        forbidden = Mock(side_effect=AssertionError("must not spawn"))
        monkeypatch.setattr(context, "_run", forbidden)
        for argv, kwargs in ((["git", "add", "-A"], {}), (["git", "status", "--short"], {"cwd": "/"}), (["git", "status", "--short"], {"env": {}})):
            with pytest.raises(ValueError):
                context.run(argv, **kwargs)
        forbidden.assert_not_called()


def test_message_growth_after_stat_is_bounded_before_stage(repository, monkeypatch):
    r = repository
    clean_merge(r)
    message = r.repo / ".git/MERGE_MSG"
    original_open = Path.open
    observed = []
    def opened(path, *args, **kwargs):
        if path == message and args == ("rb",):
            with original_open(path, "wb") as out:
                out.write(b"x" * (1024 * 1024 + 20))
            stream = original_open(path, *args, **kwargs)
            class Stream:
                def __enter__(self):
                    return self
                def read(self, limit):
                    observed.append(limit)
                    return stream.read(limit)
                def __exit__(self, *exc):
                    stream.close()
            return Stream()
        return original_open(path, *args, **kwargs)
    before = (r.repo / ".git/index").read_bytes()
    monkeypatch.setattr(Path, "open", opened)
    assert "exceeds supported size" in invoke(r)
    assert observed == [1024 * 1024 + 1]
    assert (r.repo / ".git/index").read_bytes() == before
    assert_record(r, "failed")


def test_private_main_resolution_then_explicit_commit(repository, monkeypatch):
    import core
    r = repository
    source = Path(__file__).resolve().parents[1] / "main.py"
    with monkeypatch.context() as imports:
        imports.setattr(sys, "path", list(sys.path))
        for name, attrs in {"context": {}, "dashboard_data": {"get_render_text": Mock()}, "inference_v2": {"was_last_streamed": Mock()}, "loader_v2": {"get_loader": Mock()}, "sysmon": {"get_monitor": Mock()}}.items():
            stub = ModuleType(f"core.{name}")
            stub.__dict__.update(attrs)
            imports.setitem(sys.modules, f"core.{name}", stub)
            imports.setattr(core, name, stub, raising=False)
        spec = importlib.util.spec_from_file_location("_broad_commit_main", source)
        main = importlib.util.module_from_spec(spec)
        imports.setitem(sys.modules, spec.name, main)
        spec.loader.exec_module(main)
    r.git("checkout", "-b", "incoming")
    (r.repo / "core/example.py").write_text("incoming\n")
    r.git("add", "-A")
    r.git("commit", "-m", "incoming")
    incoming = r.git("rev-parse", "HEAD").stdout.strip()
    r.git("checkout", "main")
    (r.repo / "core/example.py").write_text("main\n")
    r.git("add", "-A")
    r.git("commit", "-m", "main")
    old = r.git("rev-parse", "HEAD").stdout.strip()
    monkeypatch.chdir(r.repo)
    monkeypatch.setattr(githelper, "run_git", git_execution.run_git)
    monkeypatch.setattr(main, "input", Mock(return_value="y"), raising=False)
    def resolve(prompt, history, **kwargs):
        assert "merge conflicts" in prompt
        (r.repo / "core/example.py").write_text("resolved without inference\n")
        return "resolved", history
    resolver = Mock(side_effect=resolve)
    monkeypatch.setattr(main, "_execute_agent_capability", resolver)
    monkeypatch.setattr(githelper, "generate_commit_message", Mock(side_effect=AssertionError("no generation")))
    history = [{"role": "user", "content": "existing"}]
    assert main.handle_command("/git merge incoming", history) == (True, history)
    resolver.assert_called_once()
    assert main.handle_command("/git commit explicit resolution", history) == (True, history)
    assert r.git("show", "-s", "--format=%P", "HEAD").stdout.strip().split() == [old, incoming]
    assert r.git("show", "HEAD:core/example.py").stdout == "resolved without inference\n"
    assert [record["outcome"] for record in records(r)] == ["failed", "allowed"]


@pytest.mark.parametrize("name", ["MERGE_HEAD", "MERGE_MSG", "MERGE_MODE", "AUTO_MERGE", "SQUASH_MSG"])
def test_nonregular_operation_metadata_rejected(repository, name):
    r = repository
    clean_merge(r)
    path = r.repo / ".git" / name
    if path.exists():
        path.unlink()
    path.mkdir()
    before = (r.repo / ".git/index").read_bytes()
    assert "Unsupported Git metadata file" in invoke(r)
    assert (r.repo / ".git/index").read_bytes() == before
    assert_record(r, "failed")


@pytest.mark.parametrize("invalid", ["0" * 40, "blob"])
def test_merge_head_must_name_existing_local_commit(repository, invalid):
    r = repository
    clean_merge(r)
    if invalid == "blob":
        invalid = r.git("rev-parse", "HEAD:core/example.py").stdout.strip()
    (r.repo / ".git/MERGE_HEAD").write_text(invalid + "\n")
    before = (r.repo / ".git/index").read_bytes()
    assert invoke(r).startswith("[ERROR]")
    assert (r.repo / ".git/index").read_bytes() == before
    assert_record(r, "failed")


def test_exact_message_cap_supported(repository):
    r = repository
    clean_merge(r)
    (r.repo / ".git/MERGE_MSG").write_bytes(b"x" * (1024 * 1024))
    assert not invoke(r).startswith("[ERROR]")
    assert_record(r)


@pytest.mark.parametrize("stage_gitlink", [False, True])
def test_staged_only_gitlink_change_cannot_hide_behind_ignore_all(repository, stage_gitlink):
    r = repository
    pointer = r.git("rev-parse", "HEAD").stdout.strip()
    r.git("update-index", "--add", "--cacheinfo", "160000", pointer, "submodule")
    if not stage_gitlink:
        r.git("commit", "-m", "baseline gitlink")
    (r.repo / "core/example.py").write_text("staged ordinary data\n")
    r.git("add", "core/example.py")
    r.git("config", "diff.ignoreSubmodules", "all")
    before = (r.repo / ".git/index").read_bytes()
    result = invoke(r, add_all=False)
    if stage_gitlink:
        assert "Selected Git submodules" in result
        assert (r.repo / ".git/index").read_bytes() == before
        assert_record(r, "failed")
    else:
        assert not result.startswith("[ERROR]"), result
        assert r.git("show", "HEAD:core/example.py").stdout == "staged ordinary data\n"
        assert_record(r)


def test_existing_head_lock_is_preserved(repository):
    r = repository
    lock = r.repo / ".git/HEAD.lock"
    lock.write_bytes(b"other owner")
    before = (r.repo / ".git/index").read_bytes()
    assert "already locked" in invoke(r)
    assert lock.read_bytes() == b"other owner"
    assert (r.repo / ".git/index").read_bytes() == before
    assert records(r)[0]["outcome"] == "failed"


def test_replaced_owned_lock_retains_pending_metadata(repository, monkeypatch):
    r = repository
    clean_merge(r)
    real = r.repo / ".git"
    before = (real / "MERGE_HEAD").read_bytes()
    original = git_execution.run_git
    def run(argv, **kwargs):
        result = original(argv, **kwargs)
        if argv[:3] == ["git", "commit", "-m"]:
            replacement = real / "foreign-lock"
            replacement.write_bytes(b"foreign owner")
            replacement.replace(real / "HEAD.lock")
        return result
    monkeypatch.setattr(git_execution, "run_git", run)
    assert "Owned Git HEAD lock was replaced" in invoke(r)
    assert (real / "HEAD.lock").read_bytes() == b"foreign owner"
    assert (real / "MERGE_HEAD").read_bytes() == before
    assert records(r)[0]["outcome"] == "failed"


def test_detached_merge_publication_continues_after_metadata_unlink_error(repository, monkeypatch):
    r = repository
    old, incoming = clean_merge(r)
    real = r.repo / ".git"
    (real / "HEAD").write_text(old + "\n")
    pending = (real / "MERGE_HEAD").read_bytes()
    original = Path.unlink
    failure = OSError("merge metadata unlink failed")
    def unlink(path, *args, **kwargs):
        if path == real / "MERGE_HEAD":
            raise failure
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(OSError) as caught:
        invoke(r)
    assert caught.value is failure
    assert r.git("show", "-s", "--format=%P", "HEAD").stdout.strip().split() == [old, incoming]
    assert (real / "MERGE_HEAD").read_bytes() == pending
    assert_record(r, "failed")


@pytest.mark.parametrize("padding", [" ", "\n"])
def test_merge_oid_rejects_whitespace_beyond_single_terminator(repository, padding):
    r = repository
    _, incoming = clean_merge(r)
    (r.repo / ".git/MERGE_HEAD").write_text(padding + incoming + "\n")
    before = (r.repo / ".git/index").read_bytes()
    assert "one full incoming commit" in invoke(r)
    assert (r.repo / ".git/index").read_bytes() == before
    assert_record(r, "failed")
