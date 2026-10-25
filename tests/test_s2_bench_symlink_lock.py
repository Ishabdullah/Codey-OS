"""S2 unit C (VC2-N01): any symlink under bench/ fails the lock closed.

Disposable COPIES only; the real tree is never mutated and no bench run occurs."""
import os
import shutil
from pathlib import Path

import pytest

from bench import lock


@pytest.fixture
def copy(tmp_path):
    b = tmp_path / "bench"
    b.mkdir()
    for p in lock.ROOT.glob("*.py"):
        shutil.copy(p, b / p.name)
    shutil.copytree(lock.ROOT / "tasks", b / "tasks",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    lk = b / "suite.lock"
    lock.write_lock(b / "tasks", lk, bench_dir=b)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "evil.py").write_text("x = 1\n")
    return b, lk, outside


def _verify(b, lk):
    return lock.verify_lock(b / "tasks", lk, bench_dir=b)


def _mk_dirlink(b, outside):
    (b / "linkdir").symlink_to(outside, target_is_directory=True)


def _mk_filelink(b, outside):
    (b / "evil_link.py").symlink_to(outside / "evil.py")


def _mk_dangling(b, outside):
    (b / "dangling.py").symlink_to(outside / "nope.py")


def _mk_tasks_link(b, outside):
    (b / "tasks" / "tlink").symlink_to(outside, target_is_directory=True)


def _mk_nested(b, outside):
    (b / "sub" / "deep").mkdir(parents=True)
    (b / "sub" / "deep" / "l.py").symlink_to(outside / "evil.py")


def _mk_pycache(b, outside):
    (b / "__pycache__").mkdir(exist_ok=True)
    (b / "__pycache__" / "x.pyc").symlink_to(outside / "evil.py")


def _mk_tasks_filelink(b, outside):
    f = next(p for p in (b / "tasks").rglob("*") if p.is_file() and p.suffix != ".pyc")
    f2 = f.with_name("linked_" + f.name)
    f2.symlink_to(f)


MAKERS = [_mk_dirlink, _mk_filelink, _mk_dangling, _mk_tasks_link, _mk_nested,
          _mk_pycache, _mk_tasks_filelink]


@pytest.mark.parametrize("mk", MAKERS, ids=lambda f: f.__name__)
def test_symlink_breaks_verify_and_blocks_write(copy, mk):
    b, lk, outside = copy
    assert _verify(b, lk) is True
    mk(b, outside)
    assert _verify(b, lk) is False
    before = lk.read_text()
    with pytest.raises(RuntimeError, match="symlink"):
        lock.write_lock(b / "tasks", lk, bench_dir=b)
    assert lk.read_text() == before


@pytest.mark.parametrize("mk", MAKERS, ids=lambda f: f.__name__)
def test_removing_symlink_restores(copy, mk):
    b, lk, outside = copy
    mk(b, outside)
    for p in lock.find_symlinks(b):
        p.unlink()
    assert _verify(b, lk) is True


def test_linked_dir_module_was_unhashed_without_the_guard(copy):
    """Documents the original hole: the linked .py is not in evaluator_files."""
    b, lk, outside = copy
    _mk_dirlink(b, outside)
    assert not any("evil.py" in str(p) for p in lock.evaluator_files(b))


def test_no_symlink_tree_unaffected(copy):
    b, lk, _ = copy
    assert lock.find_symlinks(b, b / "tasks") == []
    assert _verify(b, lk) is True
    assert lock.write_lock(b / "tasks", lk, bench_dir=b) == lock.suite_hash(b / "tasks")
    assert _verify(b, lk) is True


def test_real_tree_has_no_symlinks_and_verifies():
    assert lock.find_symlinks(lock.ROOT) == []
    assert lock.verify_lock() is True
