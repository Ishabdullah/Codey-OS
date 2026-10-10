"""Copied metadata READ contracts; all Git/state effects are disposable."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway, checkpoint, git_execution, git_query_context, githelper
from core.action_gateway import READ, ActionGateway, GatewayDecision
from core.git_query_context import GitQueryError
from tests.test_git_literal_paths import repository as isolated_repository


@pytest.fixture
def repository(tmp_path, monkeypatch):
    parent = tmp_path / "query-admin"
    parent.mkdir()
    monkeypatch.setattr(git_query_context, "_temporary_candidates", lambda: (parent,))
    yield from isolated_repository.__wrapped__(tmp_path, monkeypatch)
    assert list(parent.iterdir()) == []


def records(r):
    return [json.loads(line) for line in r.audit.read_text().splitlines()]


def snapshot(r):
    result = {}
    for path in [r.repo, *r.repo.rglob("*")]:
        st = path.lstat()
        result[str(path.relative_to(r.repo))] = (st.st_dev, st.st_ino, st.st_mode, path.read_bytes() if path.is_file() and not path.is_symlink() else None)
    return result


QUERIES = [githelper.is_git_repo, githelper.git_current_branch, githelper.git_log, githelper.git_branches, githelper.git_commit_log_messages]


@pytest.mark.parametrize("state", ["attached", "unborn", "detached", "packed", "sha256", "subcwd", "active", "split", "sparse-config"])
def test_metadata_states_read_without_repository_changes(repository, tmp_path, state):
    r = repository
    cwd = r.repo
    if state in ("unborn", "sha256"):
        cwd = tmp_path / state
        cwd.mkdir()
        r.git("init", "-b", "fresh", *(["--object-format=sha256"] if state == "sha256" else []), cwd=cwd)
        if state == "sha256":
            r.git("config", "user.name", "Temp", cwd=cwd)
            r.git("config", "user.email", "temp@example.invalid", cwd=cwd)
            r.git("commit", "--allow-empty", "-m", "secret subject", cwd=cwd)
        r.repo = cwd
    elif state == "detached":
        r.git("checkout", "--detach")
    elif state == "packed":
        r.git("update-ref", "refs/remotes/origin/topic", r.git("rev-parse", "HEAD").stdout.strip())
        r.git("pack-refs", "--all")
    elif state == "subcwd":
        cwd = r.repo / "core"
    elif state == "active":
        (r.repo / ".git/MERGE_HEAD").write_text("operation data not queried")
        (r.repo / ".git/CHERRY_PICK_HEAD").write_text("operation data not queried")
    elif state == "split":
        r.git("update-index", "--split-index")
    elif state == "sparse-config":
        r.git("config", "core.sparseCheckout", "true")
    before = snapshot(r)
    values = [query(path=str(cwd)) for query in QUERIES]
    assert values[0] is True
    assert values[1] == ("fresh" if state == "unborn" else "HEAD" if state == "detached" else "fresh" if state == "sha256" else "main")
    if state == "unborn":
        assert values[2:] == ["No commits yet.", "No branches found.", []]
        assert not (cwd / ".git/index").exists() and not (cwd / ".git/logs").exists()
    else:
        assert "secret subject" in values[2] if state == "sha256" else "baseline" in values[2]
        assert values[4] == (["secret subject"] if state == "sha256" else ["baseline"])
        if state == "packed":
            assert "origin/topic" in values[3]
    assert snapshot(r) == before
    ledger = records(r)
    assert len(ledger) == 5 and all(row["authority"] == READ and row["outcome"] == "allowed" for row in ledger)
    assert all(row["command"] == "git metadata query" for row in ledger)
    assert "secret subject" not in r.audit.read_text()


@pytest.mark.parametrize("query", [githelper.git_log, githelper.git_commit_log_messages])
@pytest.mark.parametrize("count", [0, -1, True, "--all", None, 1.5])
def test_history_count_validation(repository, query, count):
    r = repository
    if count == 0 and not isinstance(count, bool):
        assert query(count, path=str(r.repo)) == ("No commits yet." if query is githelper.git_log else [])
        outcome = "allowed"
    else:
        with pytest.raises(GitQueryError):
            query(count, path=str(r.repo))
        outcome = "failed"
    assert records(r)[0]["outcome"] == outcome


@pytest.mark.parametrize("query", [githelper.is_git_repo, githelper.git_log, githelper.git_commit_log_messages])
def test_actual_missing_head_object_is_failure_not_empty(repository, query):
    r = repository
    oid = r.git("rev-parse", "HEAD").stdout.strip()
    (r.repo / ".git/objects" / oid[:2] / oid[2:]).unlink()
    assert r.git("log", "-5", "--oneline", check=False).returncode == 128
    before = snapshot(r)
    with pytest.raises(GitQueryError):
        query(path=str(r.repo))
    assert snapshot(r) == before
    ledger = records(r)
    assert len(ledger) == 1 and ledger[0]["outcome"] == "failed"
    assert oid not in r.audit.read_text() and "bad object" not in r.audit.read_text()


@pytest.mark.parametrize("state", ["missing-cwd", "nonrepo", "bad-head", "large-head", "dangling-ref", "include", "includeIf", "unknown-extension", "v0-extension", "custom", "bare", "gitfile", "linked", "symlink-ref", "directory-ref", "bad-config", "graft-symlink"])
def test_invalid_metadata_is_explicit(repository, tmp_path, state):
    r = repository
    cwd = r.repo
    real = r.repo / ".git"
    if state in ("missing-cwd", "nonrepo"):
        cwd = tmp_path / state
        if state == "nonrepo":
            cwd.mkdir()
    elif state == "bad-head":
        (real / "HEAD").write_text("invalid head")
    elif state == "large-head":
        (real / "HEAD").write_bytes(b"x" * 4097)
    elif state == "dangling-ref":
        (real / "refs/heads/main").write_text("0" * 40 + "\n")
    elif state in ("include", "includeIf"):
        r.git("config", "include.path" if state == "include" else "includeIf.gitdir:secret.path", str(tmp_path / "secret-config"))
    elif state == "unknown-extension":
        r.git("config", "core.repositoryFormatVersion", "1")
        r.git("config", "extensions.unknown", "secretvalue")
    elif state == "v0-extension":
        r.git("config", "extensions.objectFormat", "sha256")
    elif state == "custom":
        r.git("config", "core.worktree", str(tmp_path))
    elif state == "bare":
        cwd = tmp_path / "bare"
        r.git("init", "--bare", str(cwd))
    elif state == "gitfile":
        shutil.rmtree(real)
        real.write_text("gitdir: arbitrary")
    elif state == "linked":
        (real / "commondir").write_text("arbitrary")
    elif state == "symlink-ref":
        (real / "refs/heads/main").unlink()
        (real / "refs/heads/main").symlink_to(real / "HEAD")
    elif state == "directory-ref":
        (real / "refs/heads/main").unlink()
        (real / "refs/heads/main").mkdir()
    elif state == "bad-config":
        (real / "config").write_text("[malformed")
    else:
        (real / "info").mkdir(exist_ok=True)
        (real / "info/grafts").symlink_to(real / "HEAD")
    if state == "nonrepo":
        assert githelper.is_git_repo(str(cwd)) is False
        assert records(r)[0]["outcome"] == "allowed"
    else:
        with pytest.raises(FileNotFoundError if state == "missing-cwd" else GitQueryError):
            githelper.is_git_repo(str(cwd))
        assert records(r)[0]["outcome"] == "failed"
        assert "secretvalue" not in r.audit.read_text() and "secret-config" not in r.audit.read_text()


@pytest.mark.parametrize("rc", [1, 2, 128])
def test_show_ref_missing_is_distinguished_from_failure(repository, monkeypatch, rc):
    r = repository
    original = git_execution.run_git
    def run(argv, **kwargs):
        if argv[1:3] == ["show-ref", "--exists"]:
            return subprocess.CompletedProcess(argv, rc, "", "secret stderr")
        return original(argv, **kwargs)
    monkeypatch.setattr(git_execution, "run_git", run)
    if rc == 2:
        assert githelper.git_log(path=str(r.repo)) == "No commits yet."
        assert records(r)[0]["outcome"] == "allowed"
    else:
        with pytest.raises(GitQueryError):
            githelper.git_log(path=str(r.repo))
        assert records(r)[0]["outcome"] == "failed"
    assert "secret stderr" not in r.audit.read_text()


def test_marker_configuration_and_environment_are_not_activated(repository, tmp_path, monkeypatch):
    r = repository
    marker = tmp_path / "marker"
    script = tmp_path / "helper"
    script.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n")
    script.chmod(0o755)
    for key in ("core.pager", "core.editor", "core.fsmonitor", "filter.driver.clean", "diff.external", "diff.driver.textconv", "gpg.program", "core.sshCommand", "alias.log", "maintenance.strategy"):
        r.git("config", key, str(script))
    global_config = tmp_path / "global config"
    global_config.write_text(f'[include]\n path = {script}\n[pager]\n log = {script}\n')
    for key, value in {"GIT_CONFIG_GLOBAL": str(global_config), "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.pager", "GIT_CONFIG_VALUE_0": str(script), "GIT_CONFIG_PARAMETERS": "secret", "GIT_DIR": str(tmp_path / "other"), "GIT_INDEX_FILE": str(tmp_path / "other-index"), "GIT_EXEC_PATH": str(tmp_path), "PATH": str(tmp_path), "TMPDIR": str(r.repo), "LD_PRELOAD": "secret", "PYTHONPATH": "secret"}.items():
        monkeypatch.setenv(key, value)
    original, children = git_execution.run_git, []
    def run(argv, **kwargs):
        children.append((argv, kwargs))
        return original(argv, **kwargs)
    before, parent = snapshot(r), dict(os.environ)
    with monkeypatch.context() as calls:
        calls.setattr(git_execution, "run_git", run)
        assert githelper.git_log(path=str(r.repo))
    assert snapshot(r) == before and dict(os.environ) == parent and not marker.exists()
    allowed = {"PATH", "LC_ALL", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_GLOBAL", "GIT_DIR", "GIT_WORK_TREE", "GIT_OBJECT_DIRECTORY", "GIT_INDEX_FILE", "GIT_OPTIONAL_LOCKS", "GIT_NO_LAZY_FETCH", "GIT_TERMINAL_PROMPT", "GIT_ATTR_NOSYSTEM"}
    assert children and all(set(kwargs["env"]) == allowed and kwargs["timeout"] == 15 for _, kwargs in children)
    assert all(kwargs["env"]["GIT_CONFIG_GLOBAL"] == os.devnull for _, kwargs in children)
    assert len({id(kwargs["env"]) for _, kwargs in children}) == len(children)


@pytest.mark.parametrize("kind", ["selection", "spawn", "timeout"])
def test_unexpected_identity_and_static_audit(repository, monkeypatch, kind):
    r = repository
    failure = subprocess.TimeoutExpired("secret command", 15) if kind == "timeout" else OSError("secret exception")
    monkeypatch.setattr(git_execution, "_trusted_git_executable" if kind == "selection" else "run_git", Mock(side_effect=failure))
    with pytest.raises(type(failure)) as caught:
        githelper.git_log(path=str(r.repo))
    assert caught.value is failure
    assert records(r)[0]["outcome"] == "failed" and "secret" not in r.audit.read_text()


@pytest.mark.parametrize("body_error", [False, True])
def test_cleanup_error_preserves_identity_and_audits_extra_failure(repository, monkeypatch, body_error):
    r = repository
    original = shutil.rmtree
    cleanup = OSError("secret cleanup")
    body = OSError("secret body")
    leaked = []
    def remove(path, **kwargs):
        leaked.append(path)
        raise cleanup
    try:
        with monkeypatch.context() as changes:
            changes.setattr(git_query_context.shutil, "rmtree", remove)
            if body_error:
                changes.setattr(git_query_context._Metadata, "query", Mock(side_effect=body))
            with pytest.raises(OSError) as caught:
                githelper.git_log(path=str(r.repo))
            assert caught.value is (body if body_error else cleanup)
        ledger = records(r)
        assert ledger[0]["outcome"] == "failed" and "secret" not in r.audit.read_text()
        if body_error:
            assert "cleanup also failed" in ledger[0]["reason"]
    finally:
        for path in leaked:
            original(path)


def test_refusal_has_no_context_or_selection(repository, monkeypatch):
    r = repository
    forbidden = Mock(side_effect=AssertionError("no query construction"))
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: SimpleNamespace(gate_exec=Mock(return_value=GatewayDecision(READ, "refused", "synthetic"))))
    monkeypatch.setattr(git_query_context, "_metadata_context", forbidden)
    monkeypatch.setattr(git_execution, "run_git", forbidden)
    with pytest.raises(GitQueryError):
        githelper.git_log(path=str(r.repo))
    forbidden.assert_not_called()
    assert not r.audit.exists()


@pytest.mark.parametrize("failure", [False, True])
def test_blocked_audit_cannot_change_success_or_error(repository, tmp_path, monkeypatch, failure):
    r = repository
    blocker = tmp_path / "blocked"
    blocker.write_text("blocked")
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: ActionGateway(audit_file=blocker / "audit"))
    if failure:
        error = OSError("original identity")
        monkeypatch.setattr(git_execution, "run_git", Mock(side_effect=error))
        with pytest.raises(OSError) as caught:
            githelper.is_git_repo(str(r.repo))
        assert caught.value is error
    else:
        assert githelper.is_git_repo(str(r.repo)) is True
    assert blocker.read_text() == "blocked"


@pytest.mark.parametrize("files", [None, []])
def test_no_path_checkpoint_read_hash_and_real_backup_row(repository, files):
    r = repository
    before = snapshot(r)
    expected = r.git("rev-parse", "HEAD").stdout.strip()
    assert checkpoint._create_git_commit("secret reason", files) == expected
    assert snapshot(r) == before
    assert records(r)[0]["authority"] == READ and records(r)[0]["command"] == "checkpoint Git HEAD query"
    r.audit.unlink()
    identifier = checkpoint.create_checkpoint("metadata integration", files)
    assert r.state.get_checkpoint(identifier)["git_commit_hash"] == expected
    assert (r.backups / identifier / "core/example.py").read_bytes() == (r.repo / "core/example.py").read_bytes()
    assert len(records(r)) == 1 and records(r)[0]["authority"] == READ


def test_no_path_failure_keeps_backup_and_null_row(repository):
    r = repository
    oid = r.git("rev-parse", "HEAD").stdout.strip()
    (r.repo / ".git/objects" / oid[:2] / oid[2:]).unlink()
    identifier = checkpoint.create_checkpoint("metadata failure", [])
    assert r.state.get_checkpoint(identifier)["git_commit_hash"] is None
    assert (r.backups / identifier / "core/example.py").read_text() == "baseline core\n"
    assert records(r)[0]["outcome"] == "failed"
    checkpoint.warning.assert_called_with("Checkpoint: Git metadata query failed")


@pytest.mark.parametrize("bare", [False, True])
def test_native_valueless_boolean_protocol(repository, bare):
    r = repository
    with (r.repo / ".git/config").open("a") as out:
        out.write("\n[core]\n bare\n" if bare else "\n[unrelated]\n boolean\n")
    if bare:
        with pytest.raises(GitQueryError):
            githelper.is_git_repo(str(r.repo))
        assert records(r)[0]["outcome"] == "failed"
    else:
        assert githelper.is_git_repo(str(r.repo)) is True
        assert records(r)[0]["outcome"] == "allowed"


@pytest.mark.parametrize("fallback", [False, True])
def test_fixed_temp_symlink_into_worktree_never_creates_admin_there(repository, tmp_path, monkeypatch, fallback):
    r = repository
    candidate = tmp_path / "fixed-symlink"
    candidate.symlink_to(r.repo, target_is_directory=True)
    safe = tmp_path / "safe-temp"
    safe.mkdir()
    monkeypatch.setattr(git_query_context, "_temporary_candidates", lambda: (candidate, safe) if fallback else (candidate,))
    before = snapshot(r)
    if fallback:
        assert githelper.is_git_repo(str(r.repo)) is True
    else:
        with pytest.raises(GitQueryError):
            githelper.is_git_repo(str(r.repo))
    assert snapshot(r) == before and list(safe.iterdir()) == []


def test_copied_grafts_remain_history_data(repository):
    r = repository
    old = r.git("rev-parse", "HEAD").stdout.strip()
    r.git("commit", "--allow-empty", "-m", "new subject")
    current = r.git("rev-parse", "HEAD").stdout.strip()
    info = r.repo / ".git/info"
    info.mkdir(exist_ok=True)
    (info / "grafts").write_text(current + "\n")
    before = snapshot(r)
    assert githelper.git_commit_log_messages(path=str(r.repo)) == ["new subject"]
    assert old not in githelper.git_log(path=str(r.repo))
    assert snapshot(r) == before


@pytest.mark.parametrize("command", ["rev-parse", "log", "branch", "config"])
def test_checked_query_failure_never_returns_success(repository, monkeypatch, command):
    r = repository
    original = git_execution.run_git
    def run(argv, **kwargs):
        if argv[1] == command:
            return subprocess.CompletedProcess(argv, 1, "", "secret stderr path")
        return original(argv, **kwargs)
    monkeypatch.setattr(git_execution, "run_git", run)
    query = githelper.git_branches if command == "branch" else githelper.git_log
    with pytest.raises(GitQueryError):
        query(path=str(r.repo))
    assert records(r)[0]["outcome"] == "failed" and "secret" not in r.audit.read_text()


def test_import_is_inert(repository, monkeypatch):
    forbidden = Mock(side_effect=AssertionError("import must be pure"))
    monkeypatch.setattr(git_execution, "run_git", forbidden)
    monkeypatch.setattr(git_query_context, "discover_worktree", forbidden)
    monkeypatch.setattr(git_query_context.tempfile, "mkdtemp", forbidden)
    spec = importlib.util.spec_from_file_location("_metadata_import_test", Path(git_query_context.__file__))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    forbidden.assert_not_called()


@pytest.fixture
def private_main(monkeypatch):
    import core
    source = Path(__file__).resolve().parents[1] / "main.py"
    with monkeypatch.context() as imports:
        imports.setattr(sys, "path", list(sys.path))
        for name, attrs in {"context": {}, "dashboard_data": {"get_render_text": Mock()}, "inference_v2": {"was_last_streamed": Mock()}, "loader_v2": {"get_loader": Mock()}, "sysmon": {"get_monitor": Mock()}}.items():
            stub = ModuleType(f"core.{name}")
            stub.__dict__.update(attrs)
            imports.setitem(sys.modules, f"core.{name}", stub)
            imports.setattr(core, name, stub, raising=False)
        spec = importlib.util.spec_from_file_location("_metadata_main", source)
        main = importlib.util.module_from_spec(spec)
        imports.setitem(sys.modules, spec.name, main)
        spec.loader.exec_module(main)
    monkeypatch.setattr(main, "error", Mock())
    return main


@pytest.mark.parametrize("subcommand", ["log", "branches"])
def test_private_main_real_read_output_and_history(repository, private_main, monkeypatch, subcommand):
    r = repository
    monkeypatch.chdir(r.repo)
    history = [{"role": "user", "content": "existing"}]
    assert private_main.handle_command("/git " + subcommand, history) == (True, history)
    assert [row["authority"] for row in records(r)] == [READ, READ]
    assert [row["outcome"] for row in records(r)] == ["allowed", "allowed"]
    private_main.error.assert_not_called()


@pytest.mark.parametrize("failure", ["preflight", "branch", "history", "log", "branches"])
def test_private_main_query_failure_aborts_dependent_work(repository, private_main, monkeypatch, failure):
    r = repository
    monkeypatch.chdir(r.repo)
    function = {"preflight": "is_git_repo", "branch": "git_current_branch", "history": "git_commit_log_messages", "log": "git_log", "branches": "git_branches"}[failure]
    monkeypatch.setattr(githelper, function, Mock(side_effect=OSError("secret error")))
    forbidden = Mock(side_effect=AssertionError("no dependent work"))
    for name in ("git_commit", "git_checkout", "git_push", "generate_commit_message"):
        monkeypatch.setattr(githelper, name, forbidden)
    monkeypatch.setattr(githelper, "git_diff_for_commit", Mock(return_value="native diff stub"))
    monkeypatch.setattr(private_main, "input", forbidden, raising=False)
    history = [{"role": "user", "content": "existing"}]
    command = {"preflight": "/git push", "branch": "/git checkout main", "history": "/git commit", "log": "/git log", "branches": "/git branches"}[failure]
    handled, returned = private_main.handle_command(command, history)
    assert handled is True and returned is history
    assert history == [{"role": "user", "content": "existing"}]
    forbidden.assert_not_called()
    private_main.error.assert_called_once_with("Git metadata query failed.")


def test_agent_repo_failure_prevents_status_confirmation_commit(repository, monkeypatch):
    from core import agent
    from utils import logger
    r = repository
    monkeypatch.chdir(r.repo)
    monkeypatch.setattr(githelper, "is_git_repo", Mock(side_effect=OSError("secret error")))
    forbidden = Mock(side_effect=AssertionError("no dependent work"))
    monkeypatch.setattr(githelper, "git_status_paths", forbidden)
    monkeypatch.setattr(githelper, "git_commit_paths", forbidden)
    monkeypatch.setattr(logger, "confirm", forbidden)
    error = Mock()
    monkeypatch.setattr(logger, "error", error)
    agent.check_git_and_offer_commit("write", ["write_file"], ["core/example.py"])
    forbidden.assert_not_called()
    error.assert_called_once_with("Git metadata query failed.")


@pytest.mark.parametrize("empty", ["unborn", "nonrepo"])
def test_no_path_checkpoint_genuine_absence_is_allowed_read(repository, tmp_path, monkeypatch, empty):
    r = repository
    cwd = tmp_path / "empty-query-cwd"
    cwd.mkdir()
    if empty == "unborn":
        r.git("init", "-b", "main", cwd=cwd)
    monkeypatch.setattr(checkpoint, "CODE_DIR", cwd)
    assert checkpoint._create_git_commit("not a mutation", []) is None
    assert len(records(r)) == 1 and records(r)[0]["authority"] == READ and records(r)[0]["outcome"] == "allowed"


@pytest.mark.parametrize("query", QUERIES)
def test_refused_default_path_does_not_getcwd(repository, monkeypatch, query):
    r = repository
    forbidden = Mock(side_effect=AssertionError("no default cwd lookup"))
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: SimpleNamespace(gate_exec=Mock(return_value=GatewayDecision(READ, "refused", "synthetic"))))
    with monkeypatch.context() as cwd:
        cwd.setattr(git_query_context.os, "getcwd", forbidden)
        with pytest.raises(GitQueryError):
            query()
    forbidden.assert_not_called()
    assert not r.audit.exists()


def test_default_cwd_error_identity_has_failed_read(repository, monkeypatch):
    r = repository
    failure = OSError("secret cwd failure")
    with monkeypatch.context() as cwd:
        cwd.setattr(git_query_context.os, "getcwd", Mock(side_effect=failure))
        with pytest.raises(OSError) as caught:
            githelper.git_log()
        assert caught.value is failure
    assert records(r)[0]["outcome"] == "failed" and "secret" not in r.audit.read_text()


@pytest.mark.parametrize("name", ["commondir", "gitdir"])
def test_broken_linked_marker_is_still_unsupported(repository, name):
    r = repository
    (r.repo / ".git" / name).symlink_to(r.repo / "missing marker destination")
    with pytest.raises(GitQueryError, match="Linked Git metadata"):
        githelper.is_git_repo(str(r.repo))
    assert records(r)[0]["outcome"] == "failed"


@pytest.mark.parametrize("output", ["core.bare\nfalse", "nonsense\0", "core.bare\nfalse\0\0", None])
def test_malformed_config_protocol_has_static_failed_read(repository, monkeypatch, output):
    r = repository
    original = git_execution.run_git
    def run(argv, **kwargs):
        if argv[1] == "config":
            return subprocess.CompletedProcess(argv, 0, output, "secret stderr")
        return original(argv, **kwargs)
    monkeypatch.setattr(git_execution, "run_git", run)
    with pytest.raises(GitQueryError):
        githelper.is_git_repo(str(r.repo))
    assert records(r)[0]["outcome"] == "failed" and "secret" not in r.audit.read_text()


def test_private_runner_rejects_nonmetadata_argv_before_selection(repository, monkeypatch):
    r = repository
    def query(context, operation, n):
        forbidden = Mock(side_effect=AssertionError("invalid argv must not select Git"))
        with monkeypatch.context() as execution:
            execution.setattr(git_execution, "_trusted_git_executable", forbidden)
            for argv in (["git", "checkout", "main"], ["git", "status", "--short"], ["git", "log", "--all", "--oneline"], ["git", "log", "-5", "-p"], ["git", "config", "--global", "--list"], ["git", "cat-file", "-t", "--evil"], ["git", "show-ref", "--exists", "--evil"]):
                with pytest.raises(GitQueryError):
                    context._run(argv)
        forbidden.assert_not_called()
        return "guarded"
    monkeypatch.setattr(git_query_context._Metadata, "query", query)
    assert githelper.git_log(path=str(r.repo)) == "guarded"
    assert records(r)[0]["outcome"] == "allowed"
