"""WP2.1 group 14a / NEW-951: recursive classification of Codey-core files.

Pure classification tests against a temporary CODE_DIR; nothing here loads
a model, kills a process, or touches the network. create_checkpoint is
never called (the filesystem's _require_checkpoint is replaced with a
recorder).
"""

from pathlib import Path

import pytest

from core import checkpoint, filesystem
from core.filesystem import Filesystem, FilesystemAccessError
from tools.file_tools import ACT, HIGH_IMPACT, classify_write_action

REAL_CODE_DIR = checkpoint.CODE_DIR
ROOTS = ("core", "tools", "utils", "prompts")
EXT_ROOTS = ("ccos/plugins", "bench")  # slice 14a-ext (Ish fork 1)
BACKUP_PATTERNS = ["core/*.py", "tools/*.py", "utils/*.py", "prompts/*.py"]


@pytest.fixture
def code_dir(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(checkpoint, "CODE_DIR", root)
    monkeypatch.setattr(filesystem, "CODE_DIR", root)
    return root


def _old_is_core_file(file_path: str, code_dir: Path) -> bool:
    """Verbatim pre-14a algorithm, for before/after comparison."""
    path = Path(file_path).resolve()
    for pattern in checkpoint.CORE_PATTERNS:
        base_dir = code_dir / pattern.split("/")[0]
        try:
            path.relative_to(base_dir)
        except ValueError:
            continue
        if path.match(pattern):
            return True
    return False


@pytest.mark.parametrize("root", ROOTS)
@pytest.mark.parametrize("rel", ["x.py", "a/x.py", "a/b/c/x.py"])
def test_py_at_any_depth_under_each_root_is_core_high(code_dir, root, rel):
    target = code_dir / root / rel
    assert checkpoint.is_core_file(str(target)) is True
    assert classify_write_action(str(target)) == HIGH_IMPACT


@pytest.mark.parametrize(
    "rel",
    [
        "core/a/notes.md",
        "core/a/data.json",
        "tests/sub/test_x.py",
        "corex/a/b.py",
        "coreish.py",
        "x/core/a.py",
    ],
)
def test_non_core_nested_path_unaffected(code_dir, rel):
    target = code_dir / rel
    assert checkpoint.is_core_file(str(target)) is False
    assert classify_write_action(str(target)) == ACT


# Declared G15e Unit C flip (D-7, Ish 2026-10-24): `ccos/core/x.py` moved from
# the ACT list above to HIGH (d7-authority); still not a core file.
def test_ccos_core_is_high_but_not_core_file(code_dir):
    target = code_dir / "ccos/core/x.py"
    assert checkpoint.is_core_file(str(target)) is False
    assert classify_write_action(str(target)) == HIGH_IMPACT


# Declared G15e flip (Ish F3, 2026-10-23): these were ACT; they are still NOT
# core files (is_core_file False, no checkpoint) but now classify HIGH_IMPACT
# through core.protected_paths.
@pytest.mark.parametrize("rel", ["tools/x/y.sh", "main.py"])
def test_f3_paths_are_high_but_not_core(code_dir, rel):
    target = code_dir / rel
    assert checkpoint.is_core_file(str(target)) is False
    assert classify_write_action(str(target)) == HIGH_IMPACT


def test_outside_code_dir_is_not_core(code_dir, tmp_path):
    assert checkpoint.is_core_file(str(tmp_path / "other" / "core" / "a.py")) is False


def test_dotdot_traversal_resolves_before_classification(code_dir):
    inside = code_dir / "core" / "a" / ".." / "b" / "x.py"
    assert checkpoint.is_core_file(str(inside)) is True
    escaped = code_dir / "core" / ".." / "docs" / "x.py"
    assert checkpoint.is_core_file(str(escaped)) is False


def test_symlink_to_nested_core_dir_resolves_to_core(code_dir, tmp_path):
    (code_dir / "core" / "a").mkdir(parents=True)
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "link").symlink_to(code_dir / "core" / "a")
    assert checkpoint.is_core_file(str(ws / "link" / "x.py")) is True


def test_nul_byte_falls_back_to_act(code_dir):
    assert classify_write_action(str(code_dir / "core" / "a" / "x\0.py")) == ACT


def test_classification_roots_separate_from_backup_constant():
    assert checkpoint.CORE_CLASSIFICATION_ROOTS == ROOTS + EXT_ROOTS
    assert checkpoint.CORE_CLASSIFICATION_ROOTS is not checkpoint.CORE_PATTERNS
    # Backup constant value unchanged.
    assert checkpoint.CORE_PATTERNS == BACKUP_PATTERNS


def test_widening_classification_does_not_change_backup_scope(code_dir, monkeypatch):
    monkeypatch.setattr(
        checkpoint, "CORE_CLASSIFICATION_ROOTS", ROOTS + ("scripts",)
    )
    assert checkpoint.is_core_file(str(code_dir / "scripts" / "gate.py")) is True
    assert checkpoint.CORE_PATTERNS == BACKUP_PATTERNS


def test_create_checkpoint_backup_still_recursive_over_backup_constant(
    code_dir, tmp_path, monkeypatch
):
    for rel in ("core/a.py", "core/sub/b.py", "tools/x/y.py", "bench/z.py"):
        p = code_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x = 1\n")
    backup_root = tmp_path / "ckpt"
    backup_root.mkdir()
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", backup_root)
    monkeypatch.setattr(checkpoint, "_create_git_commit", lambda *a, **k: None)

    class _State:
        def execute(self, *a, **k):
            return None

    monkeypatch.setattr(checkpoint, "get_state_store", lambda: _State())
    cid = checkpoint.create_checkpoint("t")
    saved = {
        str(p.relative_to(backup_root / cid))
        for p in (backup_root / cid).rglob("*.py")
    }
    assert saved == {"core/a.py", "core/sub/b.py", "tools/x/y.py"}


@pytest.fixture
def fs_factory(code_dir, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        Filesystem, "_require_checkpoint", lambda self, path: calls.append(path)
    )
    ws = tmp_path / "ws"
    ws.mkdir()

    def make(allow):
        return Filesystem(workspace=ws, allow_self_modification=allow)

    return make, calls


def test_allow_self_modification_gate_preserved_for_nested_core(fs_factory, code_dir):
    make, calls = fs_factory
    target = code_dir / "core" / "sub" / "x.py"
    with pytest.raises(FilesystemAccessError, match="outside workspace"):
        make(False).write(str(target), "x = 1\n")
    assert not target.exists()
    assert calls == []


def test_nested_core_write_triggers_checkpoint_enforcement(fs_factory, code_dir):
    make, calls = fs_factory
    target = code_dir / "core" / "sub" / "x.py"
    make(True).write(str(target), "x = 1\n")
    assert target.read_text() == "x = 1\n"
    assert calls == [target.resolve()]


def test_non_core_nested_write_skips_checkpoint(fs_factory, code_dir):
    make, calls = fs_factory
    target = code_dir / "core" / "sub" / "notes.md"
    make(True).write(str(target), "hi")
    assert calls == []


def test_real_tree_has_no_nested_py_under_roots():
    """Spec F1: zero nested .py under the four roots today, so the
    recursive fix reclassifies nothing. If this fails, a nested file was
    added and its (new) HIGH classification is intended -- update here."""
    nested = []
    for root in ROOTS:
        base = REAL_CODE_DIR / root
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            if p.parent != base:
                nested.append(str(p.relative_to(REAL_CODE_DIR)))
    assert nested == []


def test_real_tree_classification_changes_only_for_ext_roots_py():
    """14a-ext: versus the pre-14a algorithm, the ONLY real-tree files whose
    classification changes are *.py under ccos/plugins/** and bench/**
    (ACT -> HIGH). Every other file is unchanged."""
    files = [
        p
        for p in REAL_CODE_DIR.rglob("*")
        if p.is_file()
        and ".git" not in p.relative_to(REAL_CODE_DIR).parts
        and "__pycache__" not in p.parts
        and p.relative_to(REAL_CODE_DIR).parts[0]
        not in ("node_modules", ".venv", "venv")
    ]
    assert files, "expected a non-empty repo tree"
    changed = {
        str(p.relative_to(REAL_CODE_DIR))
        for p in files
        if checkpoint.is_core_file(str(p)) != _old_is_core_file(str(p), REAL_CODE_DIR)
    }
    expected = {
        str(p.relative_to(REAL_CODE_DIR))
        for p in files
        if p.suffix == ".py"
        and p.relative_to(REAL_CODE_DIR).parts[:2] == ("ccos", "plugins")
        or (p.suffix == ".py" and p.relative_to(REAL_CODE_DIR).parts[0] == "bench")
    }
    assert changed == expected
    # Sanity: non-vacuous, and every change is old-ACT -> new-HIGH.
    assert "ccos/plugins/_pathutil.py" in changed
    assert "bench/gate.py" in changed
    assert "bench/tasks/t01_slugify/starter/slug.py" in changed
    for rel in changed:
        assert not _old_is_core_file(str(REAL_CODE_DIR / rel), REAL_CODE_DIR)
        assert classify_write_action(str(REAL_CODE_DIR / rel)) == HIGH_IMPACT
    assert checkpoint.is_core_file(str(REAL_CODE_DIR / "core" / "checkpoint.py"))
    assert not checkpoint.is_core_file(str(REAL_CODE_DIR / "main.py"))
