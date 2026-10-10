"""Real disposable Git effects/configuration, with startup state isolation."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from core import checkpoint, git_commit_context, git_execution, githelper
from core.action_gateway import ACT, GatewayDecision
from tests.test_git_literal_paths import repository as isolated_repository


@pytest.fixture
def repository(tmp_path, monkeypatch):
    yield from isolated_repository.__wrapped__(tmp_path, monkeypatch)


def head(r):
    return (r.repo / ".git/HEAD").read_bytes()


def ledger(r):
    records = [json.loads(line) for line in r.audit.read_text().splitlines()]
    assert len(records) == 1 and records[0]["authority"] == "ACT"
    return records[0]


def clean(r):
    assert not (r.repo / ".git/HEAD.lock").exists()
    assert not list((r.repo / ".git").glob("codey-scoped-*"))


def commit(r, paths=None, checkpoint_commit=False):
    paths = ["core/example.py"] if paths is None else paths
    if checkpoint_commit:
        return checkpoint._create_git_commit("context test", paths)
    return githelper.git_commit_paths("context test", paths, str(r.repo))


def marker_script(tmp_path):
    marker = tmp_path / "unexpected-effect"
    script = tmp_path / "marker-helper"
    script.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nPath({str(marker)!r}).write_text('unexpected')\nraise SystemExit(91)\n")
    script.chmod(0o755)
    return marker, script


@pytest.mark.parametrize("state", ["attached", "unborn", "detached", "packed", "sha256"])
def test_real_states_index_refs_logs_and_no_admin_tree(repository, tmp_path, monkeypatch, state):
    r = repository
    if state == "sha256":
        repo = tmp_path / "sha256"
        repo.mkdir()
        r.git("init", "--object-format=sha256", "-b", "main", cwd=repo)
        for key, value in {"user.name": "Test", "user.email": "test@example.invalid", "user.useConfigOnly": "true"}.items():
            r.git("config", key, value, cwd=repo)
        (repo / "core").mkdir()
        (repo / "core/example.py").write_text("initial\n")
        r.repo = repo
        monkeypatch.setattr(checkpoint, "CODE_DIR", repo)
    elif state == "unborn":
        r.git("checkout", "--orphan", "newborn")
        r.git("rm", "--cached", "-r", ".")
    elif state == "detached":
        r.git("checkout", "--detach")
    elif state == "packed":
        r.git("pack-refs", "--all")
    (r.repo / "core/example.py").write_text("new bytes\n")
    (r.repo / "unrelated.txt").write_text("unrelated staging\n")
    r.git("add", "--", "unrelated.txt", cwd=r.repo)
    result = commit(r)
    assert not result.startswith("[ERROR]")
    git = lambda *args: r.git(*args, cwd=r.repo)
    assert git("show", "HEAD:core/example.py").stdout == "new bytes\n"
    assert git("diff", "--cached", "--name-only").stdout.strip() == "unrelated.txt"
    tree = git("ls-tree", "-rz", "--name-only", "HEAD").stdout.split("\0")
    assert all("codey-scoped" not in name and ".git" not in name for name in tree)
    assert (r.repo / ".git/logs/HEAD").is_file()
    assert git("rev-parse", "--show-object-format").stdout.strip() == ("sha256" if state == "sha256" else "sha1")
    if state == "detached":
        assert not head(r).startswith(b"ref: ")
    clean(r)
    assert ledger(r)["outcome"] == "allowed"


@pytest.mark.parametrize("source", ["repository", "home", "xdg", "include"])
def test_identity_data_and_unconditional_include(repository, source):
    r = repository
    environment = git_execution._local_commit_environment()
    if source != "repository":
        r.git("config", "--unset", "user.name")
        r.git("config", "--unset", "user.email")
    data = '[user]\n name = "Quoted Identity"\n email = quoted@example.invalid\n'
    if source == "repository":
        r.git("config", "user.name", "Quoted Identity")
        r.git("config", "user.email", "quoted@example.invalid")
    elif source == "home":
        (Path(environment["HOME"]) / ".gitconfig").write_text(data)
    elif source == "xdg":
        file = Path(environment["XDG_CONFIG_HOME"]) / "git/config"
        file.parent.mkdir(parents=True)
        file.write_text(data)
    else:
        file = r.repo / "included data"
        file.write_text(data)
        r.git("config", "include.path", str(file))
    (r.repo / "core/example.py").write_text("new identity content\n")
    assert not commit(r).startswith("[ERROR]")
    assert r.git("log", "-1", "--format=%an|%ae").stdout.strip() == "Quoted Identity|quoted@example.invalid"
    clean(r)


@pytest.mark.parametrize("source", ["repository", "home"])
def test_executable_config_never_runs(repository, tmp_path, source):
    r = repository
    marker, script = marker_script(tmp_path)
    hooks = tmp_path / "evil-hooks"
    hooks.mkdir()
    shutil.copyfile(script, hooks / "pre-commit")
    (hooks / "pre-commit").chmod(0o755)
    settings = {"core.hooksPath": str(hooks), "core.fsmonitor": str(script), "commit.gpgsign": "true", "gpg.program": str(script), "diff.external": str(script), "diff.evil.command": str(script), "diff.evil.textconv": str(script), "maintenance.auto": "true", "gc.auto": "1", "filter.unused.clean": str(script)}
    if source == "repository":
        for key, value in settings.items():
            r.git("config", key, value)
    else:
        file = Path(git_execution._local_commit_environment()["HOME"]) / ".gitconfig"
        for key, value in settings.items():
            r.git("config", "--file", str(file), key, value)
    (r.repo / ".gitattributes").write_text("core/example.py diff=evil\n")
    (r.repo / "core/example.py").write_text("unsigned useful commit\n")
    assert not commit(r).startswith("[ERROR]")
    assert not marker.exists()
    # Inspection is builtin log/show, not status/diff using malicious config.
    assert r.git("show", "HEAD:core/example.py").stdout == "unsigned useful commit\n"
    assert "gpgsig" not in r.git("cat-file", "-p", "HEAD").stdout
    clean(r)
    assert ledger(r)["outcome"] == "allowed"


@pytest.mark.parametrize("source", ["working", "info", "global", "macro", "index"])
def test_effective_filters_reject_before_stage_and_no_marker(repository, tmp_path, source):
    r = repository
    marker, script = marker_script(tmp_path)
    attributes = "core/example.py filter=evil\n"
    if source in ("working", "macro", "index"):
        if source == "macro":
            attributes = "[attr]unsafe filter=evil\ncore/example.py unsafe\n"
        file = r.repo / ".gitattributes"
        file.write_text(attributes)
        if source == "index":
            r.git("add", "--", ".gitattributes")
            file.unlink()
    elif source == "info":
        (r.repo / ".git/info").mkdir(exist_ok=True)
        (r.repo / ".git/info/attributes").write_text(attributes)
    else:
        file = Path(git_execution._local_commit_environment()["XDG_CONFIG_HOME"]) / "git/attributes"
        file.parent.mkdir(parents=True)
        file.write_text(attributes)
    # Configure execution only after fixture Git staging; native refresh may run filters.
    r.git("config", "filter.evil.clean", str(script))
    assert not marker.exists()
    (r.repo / "core/example.py").write_text("rejected bytes\n")
    before_head, index = head(r), (r.repo / ".git/index").read_bytes()
    assert commit(r) == "[ERROR] Selected Git filter drivers are unsupported"
    assert head(r) == before_head and (r.repo / ".git/index").read_bytes() == index
    assert not marker.exists()
    clean(r)
    record = ledger(r)
    assert record["outcome"] == "failed" and str(script) not in json.dumps(record)


@pytest.mark.parametrize("conversion", ["crlf", "utf16", "ident"])
def test_native_conversion_bytes(repository, conversion):
    r = repository
    target = r.repo / "core/example.py"
    if conversion == "crlf":
        attribute, raw, blob = "text eol=lf", b"native\r\n", "native\n"
    elif conversion == "utf16":
        attribute, raw, blob = "text working-tree-encoding=UTF-16 eol=lf", "native\n".encode("utf-16"), "native\n"
    else:
        attribute, raw, blob = "ident", b"$Id: old value $\n", "$Id$\n"
    (r.repo / ".gitattributes").write_text("core/example.py " + attribute + "\n")
    target.write_bytes(raw)
    assert not commit(r).startswith("[ERROR]")
    assert r.git("show", "HEAD:core/example.py").stdout == blob
    assert target.read_bytes() == raw


@pytest.mark.parametrize("state", ["gitfile", "gitsymlink", "merge", "rebase", "extension", "sparse", "split", "index-symlink", "embedded", "gitlink"])
def test_unsupported_before_stage_and_cleanup(repository, state, tmp_path):
    r = repository
    real = r.repo / ".git"
    if state == "gitfile":
        real.rename(r.repo / "actual-admin")
        real.write_text("gitdir: actual-admin\n")
        real = r.repo / "actual-admin"
    elif state == "gitsymlink":
        real.rename(r.repo / "actual-admin")
        real.symlink_to(r.repo / "actual-admin", target_is_directory=True)
    elif state in ("merge", "rebase"):
        entry = real / ("MERGE_HEAD" if state == "merge" else "rebase-merge")
        entry.write_text("active") if state == "merge" else entry.mkdir()
    elif state == "extension":
        r.git("config", "extensions.unreviewed", "true")
    elif state == "sparse":
        r.git("sparse-checkout", "init", "--cone", "--sparse-index")
    elif state == "split":
        r.git("update-index", "--split-index")
    elif state == "index-symlink":
        index = real / "index"
        index.rename(real / "other-index")
        index.symlink_to(real / "other-index")
    elif state == "embedded":
        embedded = r.repo / "core/embedded"
        embedded.mkdir()
        r.git("init", cwd=embedded)
    else:
        value = r.git("rev-parse", "HEAD").stdout.strip()
        r.git("update-index", "--add", "--cacheinfo", f"160000,{value},core/submodule")
    before_head = (real / "HEAD").read_bytes()
    index = (real / "index").read_bytes()
    result = commit(r, ["core"])
    assert result.startswith("[ERROR]")
    assert (real / "HEAD").read_bytes() == before_head and (real / "index").read_bytes() == index
    clean(r)
    assert ledger(r)["outcome"] == "failed"


@pytest.mark.parametrize("configuration", ["conditional", "malformed"])
def test_bad_config_private_values_not_in_audit(repository, configuration):
    r = repository
    environment = git_execution._local_commit_environment()
    file = Path(environment["HOME"]) / ".gitconfig"
    file.write_text('[includeIf "gitdir:/private/secret/"]\n path = /private/secret/value\n' if configuration == "conditional" else "[malformed secret\n")
    index = (r.repo / ".git/index").read_bytes()
    assert commit(r).startswith("[ERROR]")
    assert (r.repo / ".git/index").read_bytes() == index
    assert "secret" not in json.dumps(ledger(r)) and str(file) not in json.dumps(ledger(r))
    clean(r)


def test_existing_lock_preserved(repository):
    r = repository
    lock = r.repo / ".git/HEAD.lock"
    lock.write_text("other owner's lock")
    index = (r.repo / ".git/index").read_bytes()
    assert commit(r) == "[ERROR] Git HEAD is already locked"
    assert lock.read_text() == "other owner's lock" and (r.repo / ".git/index").read_bytes() == index
    assert not list((r.repo / ".git").glob("codey-scoped-*"))
    assert ledger(r)["outcome"] == "failed"


def test_detached_commit_published_after_final_hash_failure(repository, monkeypatch):
    r = repository
    r.git("checkout", "--detach")
    before = head(r)
    (r.repo / "core/example.py").write_text("new detached content\n")
    original = git_execution.run_git

    def run(argv, **kwargs):
        if argv == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(argv, 1, "", "final hash failure")
        return original(argv, **kwargs)

    monkeypatch.setattr(git_execution, "run_git", run)
    assert commit(r, checkpoint_commit=True) is None
    assert head(r) != before
    assert r.git("show", "HEAD:core/example.py").stdout == "new detached content\n"
    clean(r)
    assert ledger(r)["outcome"] == "failed"


@pytest.mark.parametrize("stage", ["operation", "publication", "cleanup", "both"])
def test_failures_preserve_original_and_truthful_audit(repository, monkeypatch, stage):
    r = repository
    r.git("checkout", "--detach")
    before = head(r)
    (r.repo / "core/example.py").write_text("new detached bytes\n")
    operation = OSError("original operation failure")
    cleanup = OSError("cleanup failure")
    original_run = git_execution.run_git
    original_remove = shutil.rmtree
    original_replace = os.replace
    leaked = []

    def run(argv, **kwargs):
        if stage in ("operation", "both") and "add" in argv:
            raise operation
        return original_run(argv, **kwargs)

    def remove(path, **kwargs):
        if stage in ("cleanup", "both") and Path(path).name.startswith("codey-scoped-"):
            leaked.append(Path(path))
            raise cleanup
        return original_remove(path, **kwargs)

    def replace(source, destination):
        if stage == "publication" and Path(destination) == r.repo / ".git/HEAD":
            raise cleanup
        return original_replace(source, destination)

    with monkeypatch.context() as calls:
        calls.setattr(git_execution, "run_git", run)
        calls.setattr(git_commit_context.shutil, "rmtree", remove)
        calls.setattr(git_commit_context.os, "replace", replace)
        with pytest.raises(OSError) as caught:
            commit(r)
    assert caught.value is (operation if stage in ("operation", "both") else cleanup)
    assert ledger(r)["outcome"] == "failed"
    if stage == "both":
        assert "cleanup or publication also failed" in ledger(r)["reason"]
        assert caught.value.__notes__
    if stage in ("operation", "both", "publication"):
        assert head(r) == before
    else:
        assert head(r) != before
    assert not (r.repo / ".git/HEAD.lock").exists()
    for path in leaked:
        original_remove(path)
    clean(r)


@pytest.mark.parametrize("consumer", ["helper", "checkpoint"])
def test_refusal_no_context_lock_or_git(repository, monkeypatch, consumer):
    r = repository
    gate = Mock(return_value=GatewayDecision(ACT, "refused", "test policy"))
    # Shared fixture returns gateway on demand; replace factory with one fixed double.
    monkeypatch.setattr("core.action_gateway.get_action_gateway", lambda: type("Gate", (), {"gate_exec": staticmethod(gate)})())
    forbidden = Mock(side_effect=AssertionError("refusal cannot construct or spawn"))
    before = head(r), (r.repo / ".git/index").read_bytes()
    with monkeypatch.context() as calls:
        calls.setattr(githelper, "isolated_scoped_commit_context", forbidden)
        calls.setattr(checkpoint, "isolated_scoped_commit_context", forbidden)
        calls.setattr(git_execution, "run_git", forbidden)
        result = commit(r, checkpoint_commit=consumer == "checkpoint")
    assert result is None if consumer == "checkpoint" else result == "[ERROR] Local git commit refused: test policy"
    forbidden.assert_not_called()
    assert (head(r), (r.repo / ".git/index").read_bytes()) == before
    clean(r)


@pytest.mark.parametrize("failure", ["filter", "config", "active"])
def test_checkpoint_failure_retains_backup_sqlite_null(repository, failure):
    r = repository
    if failure == "filter":
        (r.repo / ".gitattributes").write_text("core/example.py filter=unavailable\n")
    elif failure == "config":
        (Path(git_execution._local_commit_environment()["HOME"]) / ".gitconfig").write_text("[broken\n")
    else:
        (r.repo / ".git/MERGE_HEAD").write_text("active")
    target = r.repo / "core/example.py"
    target.write_text("backup bytes retained\n")
    checkpoint_id = checkpoint.create_checkpoint("failed context", [str(target)])
    assert r.state.get_checkpoint(checkpoint_id)["git_commit_hash"] is None
    assert (r.backups / checkpoint_id / "core/example.py").read_text() == "backup bytes retained\n"
    assert ledger(r)["outcome"] == "failed"
    clean(r)


@pytest.mark.parametrize("unsafe", ["filter", "embedded"])
def test_subdir_candidate_paths_and_attributes(repository, unsafe):
    r = repository
    if unsafe == "filter":
        (r.repo / ".gitattributes").write_text("core/example.py filter=unsupported\n")
        paths = ["example.py"]
    else:
        directory = r.repo / "core/embedded"
        directory.mkdir()
        r.git("init", cwd=directory)
        paths = ["embedded"]
    index = (r.repo / ".git/index").read_bytes()
    result = githelper.git_commit_paths("subdir", paths, str(r.repo / "core"))
    assert result.startswith("[ERROR]") and "unsupported" in result.lower()
    assert (r.repo / ".git/index").read_bytes() == index
    clean(r)


def test_snapshot_fresh_env_and_override_rejection(repository, monkeypatch):
    r = repository
    original_run = git_execution.run_git
    children = []

    def run(argv, **kwargs):
        assert "CHILD_ONLY_MUTATION" not in kwargs["env"]
        children.append(kwargs["env"])
        result = original_run(argv, **kwargs)
        kwargs["env"]["CHILD_ONLY_MUTATION"] = "must not persist"
        return result

    parent = dict(os.environ)
    with monkeypatch.context() as calls:
        calls.setattr(git_execution, "run_git", run)
        with git_commit_context.isolated_scoped_commit_context(str(r.repo), ["core/example.py"]) as runner:
            count = len(children)
            for kwargs in ({"env": {}}, {"executable": "/untrusted"}, {"shell": True}, {"input": "arbitrary"}):
                with pytest.raises(ValueError):
                    runner(["git", "status"], **kwargs)
            assert len(children) == count
            runner(["git", "status", "--short"], cwd=str(r.repo), capture_output=True, text=True)
    assert len({id(child) for child in children}) == len(children)
    assert all(child["GIT_CONFIG_GLOBAL"] == os.devnull and "GIT_COMMON_DIR" not in child for child in children)
    assert all(child["GIT_INDEX_FILE"] == str(r.repo / ".git/index") for child in children)
    assert dict(os.environ) == parent
    clean(r)


@pytest.mark.parametrize("extension", ["objectformat", "refstorage"])
def test_version_zero_extensions_fail_without_storage_reinterpretation(repository, extension):
    r = repository
    r.git("config", "extensions." + extension, "sha256" if extension == "objectformat" else "files")
    index, before = (r.repo / ".git/index").read_bytes(), head(r)
    assert commit(r) == "[ERROR] Git extensions require repository format version one"
    assert head(r) == before and (r.repo / ".git/index").read_bytes() == index
    assert ledger(r)["outcome"] == "failed"
    clean(r)


@pytest.mark.parametrize("source", ["relative", "tilde"])
def test_configured_attribute_data_paths(repository, source):
    r = repository
    if source == "relative":
        file = r.repo / "data attributes"
        value = "data attributes"
    else:
        file = Path(git_execution._local_commit_environment()["HOME"]) / "data attributes"
        value = "~/data attributes"
    file.write_text("core/example.py text eol=lf\n")
    r.git("config", "core.attributesFile", value)
    (r.repo / "core/example.py").write_bytes(b"native config data\r\n")
    assert not commit(r).startswith("[ERROR]")
    assert r.git("show", "HEAD:core/example.py").stdout == "native config data\n"


@pytest.mark.parametrize("state", ["custom", "nonfiles", "nonregular-index"])
def test_other_unsupported_layout_data(repository, state):
    r = repository
    if state == "custom":
        r.git("config", "core.worktree", str(r.repo))
    elif state == "nonfiles":
        r.git("config", "core.repositoryFormatVersion", "1")
        r.git("config", "extensions.refStorage", "reftable")
    else:
        (r.repo / ".git/index").rename(r.repo / ".git/saved-index")
        (r.repo / ".git/index").mkdir()
    before = head(r)
    assert commit(r).startswith("[ERROR]")
    assert head(r) == before and ledger(r)["outcome"] == "failed"
    clean(r)


@pytest.mark.parametrize("layout", ["bare", "linked"])
def test_bare_and_linked_worktree_rejection(repository, tmp_path, layout):
    r = repository
    other = tmp_path / "other"
    if layout == "bare":
        other.mkdir()
        r.git("init", "--bare", cwd=other)
        original = (other / "HEAD").read_bytes()
    else:
        r.git("worktree", "add", "-b", "linked", str(other))
        original = (other / ".git").read_bytes()
    result = githelper.git_commit_paths("unsupported", ["core/example.py"], str(other))
    assert result == "[ERROR] Unsupported Git worktree layout"
    assert (other / ("HEAD" if layout == "bare" else ".git")).read_bytes() == original
    assert ledger(r)["outcome"] == "failed"
    clean(r)


def test_local_object_alternates_and_shallow_data(repository, tmp_path):
    r = repository
    baseline = r.git("rev-parse", "HEAD").stdout.strip()
    objects = r.repo / ".git/objects"
    alternate = tmp_path / "alternate-objects"
    shutil.copytree(objects, alternate)
    for child in objects.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    (objects / "info").mkdir()
    (objects / "info/alternates").write_text(str(alternate) + "\n")
    (r.repo / ".git/shallow").write_text(baseline + "\n")
    (r.repo / "core/example.py").write_text("alternate useful bytes\n")
    assert not commit(r).startswith("[ERROR]")
    assert r.git("show", "HEAD:core/example.py").stdout == "alternate useful bytes\n"
    assert r.git("rev-parse", "HEAD^").stdout.strip() == baseline
    assert (r.repo / ".git/shallow").read_text() == baseline + "\n"
    clean(r)


def test_owned_lock_cleanup_does_not_remove_replacement(repository, monkeypatch):
    r = repository
    lock = r.repo / ".git/HEAD.lock"
    original = git_execution.run_git

    def run(argv, **kwargs):
        if "add" in argv:
            # Deliberate path replacement tests ownership; no general race safety claim.
            replacement = lock.with_name("other-lock")
            replacement.write_text("another owner")
            os.replace(replacement, lock)
            raise OSError("operation interrupted")
        return original(argv, **kwargs)

    monkeypatch.setattr(git_execution, "run_git", run)
    with pytest.raises(OSError, match="operation interrupted"):
        commit(r)
    assert lock.read_text() == "another owner"
    assert "cleanup or publication also failed" in ledger(r)["reason"]
    assert not list((r.repo / ".git").glob("codey-scoped-*"))
    lock.unlink()


@pytest.mark.parametrize("operation", ["ls-files", "check-attr", "status"])
def test_internal_query_failure_never_false_clean(repository, monkeypatch, operation):
    r = repository
    original = git_execution.run_git
    before = head(r), (r.repo / ".git/index").read_bytes()
    (r.repo / "core/example.py").write_text("change before query error\n")

    def run(argv, **kwargs):
        if operation in argv:
            return subprocess.CompletedProcess(argv, 2, "", "private diagnostic must not leak")
        return original(argv, **kwargs)

    monkeypatch.setattr(git_execution, "run_git", run)
    result = commit(r)
    assert result.startswith("[ERROR] Isolated Git")
    assert ledger(r)["outcome"] == "failed" and "private diagnostic" not in ledger(r)["reason"]
    assert head(r) == before[0]
    if operation != "status":
        assert (r.repo / ".git/index").read_bytes() == before[1]
    else:
        assert r.git("diff", "--cached", "--name-only").stdout.strip() == "core/example.py"
    clean(r)


def test_head_snapshot_after_own_lock_acquisition(repository, monkeypatch):
    r = repository
    baseline = r.git("rev-parse", "HEAD").stdout.strip()
    (r.repo / "core/example.py").write_text("new snapshot bytes\n")
    lock = r.repo / ".git/HEAD.lock"
    original_open = os.open
    transitions = []

    def acquire(path, flags, *args, **kwargs):
        if Path(path) == lock:
            # Simulate a completed cooperating transition immediately before locking.
            (r.repo / ".git/HEAD").write_text(baseline + "\n")
            transitions.append("detached before acquire")
        return original_open(path, flags, *args, **kwargs)

    with monkeypatch.context() as calls:
        calls.setattr(git_commit_context.os, "open", acquire)
        assert not commit(r).startswith("[ERROR]")
    assert transitions == ["detached before acquire"]
    assert not head(r).startswith(b"ref: ") and head(r).strip() != baseline.encode()
    assert r.git("show", "HEAD:core/example.py").stdout == "new snapshot bytes\n"
    clean(r)
    assert ledger(r)["outcome"] == "allowed"


def test_first_head_read_failure_preserves_exception_and_cleans_own_lock(repository, monkeypatch):
    r = repository
    original = Path.read_bytes
    failure = OSError("HEAD read failed")

    def read(path):
        if path == r.repo / ".git/HEAD":
            assert (r.repo / ".git/HEAD.lock").exists()
            raise failure
        return original(path)

    with monkeypatch.context() as calls:
        calls.setattr(Path, "read_bytes", read)
        with pytest.raises(OSError) as caught:
            commit(r)
    assert caught.value is failure and not getattr(failure, "_scoped_cleanup_failed", False)
    assert ledger(r)["reason"] == "HEAD read failed"
    clean(r)


@pytest.mark.parametrize("consumer", ["helper", "checkpoint"])
def test_short_head_write_never_publishes_truncated_hash(repository, monkeypatch, consumer):
    r = repository
    r.git("checkout", "--detach")
    before = head(r)
    (r.repo / "core/example.py").write_text("commit before incomplete publication\n")
    original = os.write

    def short_write(fd, content):
        return original(fd, content[:5])

    with monkeypatch.context() as calls:
        calls.setattr(git_commit_context.os, "write", short_write)
        result = commit(r, checkpoint_commit=consumer == "checkpoint")
    assert result is None if consumer == "checkpoint" else result == "[ERROR] Detached Git HEAD publication was incomplete"
    assert head(r) == before
    assert r.git("rev-parse", "HEAD").stdout.strip().encode() == before.strip()
    assert ledger(r)["outcome"] == "failed"
    clean(r)


@pytest.mark.parametrize("source", ["working", "info", "global"])
@pytest.mark.parametrize("attribute", ["filter=unset", "filter=unspecified", "filter=set", "filter=ordinary", "filter=", "-filter"])
def test_ambiguous_filter_values_fail_closed(repository, tmp_path, source, attribute):
    r = repository
    marker, script = marker_script(tmp_path)
    if source == "working":
        file = r.repo / ".gitattributes"
    elif source == "info":
        file = r.repo / ".git/info/attributes"
    else:
        file = Path(git_execution._local_commit_environment()["XDG_CONFIG_HOME"]) / "git/attributes"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("core/example.py " + attribute + "\n")
    for driver in ("unset", "unspecified", "set", "ordinary"):
        r.git("config", "filter." + driver + ".clean", str(script))
    (r.repo / "core/example.py").write_text("rejected ambiguous content\n")
    before = head(r), (r.repo / ".git/index").read_bytes()
    assert commit(r) == "[ERROR] Selected Git filter drivers are unsupported"
    assert (head(r), (r.repo / ".git/index").read_bytes()) == before
    assert not marker.exists() and ledger(r)["outcome"] == "failed"
    clean(r)


@pytest.mark.parametrize("attribute", ["absent", "!filter"])
def test_absent_reset_attributes_allow_unused_drivers(repository, tmp_path, attribute):
    r = repository
    marker, script = marker_script(tmp_path)
    if attribute != "absent":
        (r.repo / ".gitattributes").write_text("core/example.py " + attribute + "\n")
    for driver in ("unset", "unspecified", "ordinary"):
        r.git("config", "filter." + driver + ".clean", str(script))
    (r.repo / "core/example.py").write_text("native absent-reset bytes\n")
    assert not commit(r).startswith("[ERROR]")
    assert r.git("show", "HEAD:core/example.py").stdout == "native absent-reset bytes\n"
    assert not marker.exists() and ledger(r)["outcome"] == "allowed"
    clean(r)


def test_checkpoint_explicit_filter_disable_conservatively_refuses(repository):
    r = repository
    (r.repo / ".gitattributes").write_text("core/example.py -filter\n")
    before = head(r), (r.repo / ".git/index").read_bytes()
    assert commit(r, checkpoint_commit=True) is None
    assert (head(r), (r.repo / ".git/index").read_bytes()) == before
    assert ledger(r)["outcome"] == "failed"
    assert "Selected Git filter drivers are unsupported" in checkpoint.warning.call_args.args[0]
    clean(r)


@pytest.mark.parametrize("output", ["unterminated", "core/example.py\0filter\0", "other-private-path\0filter\0private-value\0"])
def test_malformed_attribute_protocol_fails_before_stage(repository, monkeypatch, output):
    r = repository
    original = git_execution.run_git
    before = head(r), (r.repo / ".git/index").read_bytes()

    def run(argv, **kwargs):
        if "check-attr" in argv:
            return subprocess.CompletedProcess(argv, 0, output.encode(), b"")
        return original(argv, **kwargs)

    monkeypatch.setattr(git_execution, "run_git", run)
    assert commit(r) == "[ERROR] Isolated Git attribute query is malformed"
    assert (head(r), (r.repo / ".git/index").read_bytes()) == before
    record = ledger(r)
    assert record["outcome"] == "failed" and "private" not in json.dumps(record)
    clean(r)


@pytest.mark.parametrize("raw_name", [b"literal-\xff.py", b"line\nname.py"])
def test_real_byte_and_newline_names_from_subcwd(repository, raw_name):
    r = repository
    directory = r.repo / "core"
    relative = os.fsdecode(raw_name)
    target = directory / relative
    target.write_text("literal native pathname bytes\n")
    (directory / "neighbor.py").write_text("neighbor dirty bytes\n")
    result = githelper.git_commit_paths("literal pathname", [relative], str(directory))
    assert not result.startswith("[ERROR]")
    native = subprocess.run([git_execution._trusted_git_executable(), "ls-tree", "-rz", "--name-only", "HEAD"], cwd=r.repo, capture_output=True, check=True)
    assert b"core/" + raw_name in native.stdout.split(b"\0")
    assert b"core/neighbor.py" not in native.stdout.split(b"\0")
    blob = subprocess.run([git_execution._trusted_git_executable(), b"show", b"HEAD:core/" + raw_name], cwd=r.repo, capture_output=True, check=True)
    assert blob.stdout == b"literal native pathname bytes\n"
    assert target.read_text() == "literal native pathname bytes\n"
    assert (directory / "neighbor.py").read_text() == "neighbor dirty bytes\n"
    assert ledger(r)["outcome"] == "allowed"
    clean(r)


def test_ordinary_subcwd_head_and_objects_are_not_bare(repository):
    r = repository
    subdir = r.repo / "ordinary-subdir"
    subdir.mkdir()
    (subdir / "HEAD").write_text("unrelated ordinary file\n")
    (subdir / "objects").mkdir()
    (subdir / "selected.py").write_text("selected bytes\n")
    assert Path(r.git("rev-parse", "--show-toplevel", cwd=subdir).stdout.strip()) == r.repo
    original = r.git("rev-parse", "HEAD").stdout.strip()
    result = githelper.git_commit_paths("ordinary subcwd", ["selected.py"], str(subdir))
    assert not result.startswith("[ERROR]"), result
    assert r.git("rev-parse", "HEAD^").stdout.strip() == original
    assert r.git("show", "HEAD:ordinary-subdir/selected.py").stdout == "selected bytes\n"
    assert r.git("status", "--porcelain").stdout.strip() == "?? ordinary-subdir/HEAD"
    assert ledger(r)["outcome"] == "allowed"
    clean(r)


@pytest.mark.parametrize("operation", ["add", "commit"])
@pytest.mark.parametrize("cleanup_kind", [None, "policy", "os"])
def test_checked_git_failure_retains_diagnostic_through_cleanup(repository, monkeypatch, operation, cleanup_kind):
    r = repository
    (r.repo / "core/example.py").write_text("changed for checked failure\n")
    original_head = r.git("rev-parse", "HEAD").stdout.strip()
    original_run, original_remove = git_execution.run_git, shutil.rmtree
    leaked = []
    diagnostic = "ORIGINAL_CHECKED_ERROR\n"
    expected = "[ERROR] git add failed: " + diagnostic if operation == "add" else "[ERROR] " + diagnostic.strip()

    def run(argv, **kwargs):
        if operation in argv:
            return subprocess.CompletedProcess(argv, 1, "", diagnostic)
        return original_run(argv, **kwargs)

    def remove(path, **kwargs):
        if cleanup_kind and Path(path).name.startswith("codey-scoped-"):
            leaked.append(path)
            error = git_commit_context.ScopedCommitError if cleanup_kind == "policy" else OSError
            raise error("PRIVATE_CLEANUP_DIAGNOSTIC")
        return original_remove(path, **kwargs)

    try:
        with monkeypatch.context() as patches:
            patches.setattr(git_execution, "run_git", run)
            patches.setattr(git_commit_context.shutil, "rmtree", remove)
            result = commit(r)
        extra = "; scoped Git context cleanup or publication also failed" if cleanup_kind else ""
        assert result == expected + extra
        record = ledger(r)
        assert record["outcome"] == "failed" and record["reason"] == result
        assert "PRIVATE_CLEANUP_DIAGNOSTIC" not in result
        assert r.git("rev-parse", "HEAD").stdout.strip() == original_head
        staged = r.git("diff", "--cached", "--name-only").stdout.strip()
        assert staged == ("core/example.py" if operation == "commit" else "")
        assert not (r.repo / ".git/HEAD.lock").exists()
    finally:
        for path in leaked:
            original_remove(path)
    clean(r)
