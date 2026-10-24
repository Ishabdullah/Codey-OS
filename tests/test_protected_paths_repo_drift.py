"""G15e Unit A: read-only drift guards over the REAL repository tree.

No writes. Fails when a new launcher/script/plugin data file is added that the
F3 rows of core.protected_paths would not cover, or when the shell-only
core-py-mirror row drifts from core.checkpoint.is_core_file.
"""

import os
import subprocess
from pathlib import Path

import core.checkpoint as checkpoint
import core.protected_paths as pp

REPO = Path(__file__).resolve().parent.parent


def _ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return pp.build_context(code_dir=REPO, home=tmp_path / "home", state_dir=tmp_path / "state",
                            audit=tmp_path / "audit.jsonl", config_paths=[], path_env="")


def _covered_f3(path, ctx):
    hit = pp.first_hit([str(path)], ctx)
    return hit is not None and hit.rule.startswith("f3-")


def _tracked():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout
    return [REPO / p for p in out.decode().split("\0") if p]


def test_root_level_launchers_and_scripts_are_covered(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch)
    uncovered = []
    for p in REPO.iterdir():
        if not p.is_file() or p.is_symlink() or p.suffix == ".py" and p.name != "main.py":
            continue
        try:
            with open(p, "rb") as f:
                shebang = f.read(2) == b"#!"
        except OSError:
            continue
        if (shebang or os.access(p, os.X_OK)) and not _covered_f3(p, ctx):
            uncovered.append(p.name)
    assert uncovered == []


def test_root_level_python_with_shebang_or_exec_is_covered_or_core(tmp_path, monkeypatch):
    # .py files at the root are not under the core roots; report any that are
    # executable/shebang and not an F3 row (a finding, not a silent pass).
    ctx = _ctx(tmp_path, monkeypatch)
    loose = []
    for p in REPO.glob("*.py"):
        with open(p, "rb") as f:
            shebang = f.read(2) == b"#!"
        if (shebang or os.access(p, os.X_OK)) and not _covered_f3(p, ctx):
            loose.append(p.name)
    assert loose == [], f"root-level executable .py files not covered by F3: {loose}"


def test_every_lib_file_is_covered(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch)
    lib = [p for p in _tracked() if p.relative_to(REPO).parts[0] == "lib"]
    assert lib
    assert [p for p in lib if not _covered_f3(p, ctx)] == []


def test_every_non_py_plugin_file_is_covered_including_untracked_pyc(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch)
    plugins = REPO / "ccos" / "plugins"
    files = [p for p in plugins.rglob("*") if p.is_file() and p.suffix != ".py"]
    assert files
    assert [p for p in files if not _covered_f3(p, ctx)] == []


def test_every_tracked_sh_file_is_covered(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch)
    sh = [p for p in _tracked() if p.suffix == ".sh"]
    assert sh
    assert [p for p in sh if not _covered_f3(p, ctx)] == []


def test_core_py_mirror_agrees_with_is_core_file(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch)
    corpus = [p for p in _tracked() if p.suffix == ".py"]
    assert len(corpus) > 50
    for p in corpus:
        # All hits, not first_hit's single one: since G15e Unit C a core .py
        # under bench/ or ccos/core also carries bench-evaluator / d7-authority.
        mirror = any(
            h.rule == "core-py-mirror"
            for h in pp._matches(str(p), ctx, shell=True)
        )
        assert mirror == checkpoint.is_core_file(str(p)), p


def test_unit_c_every_tracked_bench_ccos_core_and_authority_file_is_high(tmp_path, monkeypatch):
    """G15e Unit C drift guard: every tracked file under bench/ (any suffix),
    ccos/core/ and restoricon_core/authority*.py is covered by a HIGH row, so a
    new evaluator or authority file cannot be added unprotected."""
    ctx = _ctx(tmp_path, monkeypatch)
    wanted = [
        p for p in _tracked()
        if p.relative_to(REPO).parts[0] == "bench"
        or p.relative_to(REPO).as_posix().startswith("ccos/core/")
        or (p.parent.name == "restoricon_core" and p.name.startswith("authority") and p.suffix == ".py")
    ]
    assert len(wanted) > 10
    missing = []
    for p in wanted:
        hit = pp.first_hit([str(p)], ctx)
        if hit is None or hit.tier != pp.TIER_HIGH:
            missing.append(p)
    assert missing == []
