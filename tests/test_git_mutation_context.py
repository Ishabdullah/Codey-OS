"""Direct coverage of core/git_mutation_context.py's isolated_mutation_context.

No prior direct unit test of this module exists; coverage so far has come
entirely through the gateway tests (test_git_branch_gateway.py,
test_git_checkout_gateway.py, test_git_merge_gateway.py,
test_checkpoint_rollback_gateway.py). This file isolates the context
manager itself, in particular the admin-dir cleanup-after-success behavior
fixed 2026-10-13 (see that module's docstring and finally block).
"""

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import git_execution, git_mutation_context
from core.git_mutation_context import GitMutationError, isolated_mutation_context


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
        return subprocess.run(
            [git_execution._trusted_git_executable(), *args],
            cwd=repo, capture_output=True, text=True, check=check,
        )

    git("init", "-b", "main")
    for key, value in {
        "core.hooksPath": str(empty), "commit.gpgsign": "false", "tag.gpgsign": "false",
        "user.useConfigOnly": "true", "user.name": "Temporary Test",
        "user.email": "test@example.invalid",
    }.items():
        git("config", key, value)
    (repo / "tracked.txt").write_text("baseline\n")
    git("add", "--", "tracked.txt")
    git("commit", "-m", "baseline")
    return SimpleNamespace(repo=repo, git=git)


def test_success_with_cleanup_failure_is_reported_not_raised(repository, monkeypatch):
    r = repository
    original_rmtree = git_mutation_context.shutil.rmtree
    cleanup_error = OSError("cleanup failed")
    leaked = []

    def rmtree(path, **kwargs):
        if Path(path).name.startswith("codey-mutate-"):
            leaked.append(Path(path))
            raise cleanup_error
        return original_rmtree(path, **kwargs)

    monkeypatch.setattr(git_mutation_context.shutil, "rmtree", rmtree)
    warn = Mock()
    monkeypatch.setattr(git_mutation_context, "warning", warn)

    with isolated_mutation_context(r.repo) as context:
        result = context.run(
            ["git", "checkout", "-b", "new-branch"], cwd=r.repo, capture_output=True, text=True,
        )
        assert result.returncode == 0

    assert context._mutation_cleanup_failed is True
    warn.assert_called_once()
    assert "cleanup" in warn.call_args.args[0].lower()
    assert r.git("rev-parse", "--verify", "new-branch").returncode == 0
    assert r.git("symbolic-ref", "HEAD").stdout.strip() == "refs/heads/new-branch"
    for path in leaked:
        original_rmtree(path)


def test_body_failure_and_cleanup_failure_preserves_original_exception(repository, monkeypatch):
    r = repository
    original_rmtree = git_mutation_context.shutil.rmtree
    cleanup_error = OSError("cleanup also failed")
    body_error = RuntimeError("body failed")
    leaked = []

    def rmtree(path, **kwargs):
        if Path(path).name.startswith("codey-mutate-"):
            leaked.append(Path(path))
            raise cleanup_error
        return original_rmtree(path, **kwargs)

    monkeypatch.setattr(git_mutation_context.shutil, "rmtree", rmtree)

    with pytest.raises(RuntimeError) as caught:
        with isolated_mutation_context(r.repo):
            raise body_error

    assert caught.value is body_error
    assert caught.value._mutation_cleanup_failed is True
    assert caught.value.__notes__
    assert "Git mutation context cleanup also failed" in caught.value.__notes__[0]
    for path in leaked:
        original_rmtree(path)
