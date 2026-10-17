"""WP2.1 slice 14c: linter ACT envelope, ruff cache/option isolation, flake8/mypy skipped."""
import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from core import linter

REAL_RUFF = "/data/data/com.termux/files/usr/bin/ruff"


@pytest.fixture
def audit(tmp_path, monkeypatch):
    path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(path))
    monkeypatch.delenv("CODEY_LINTER", raising=False)
    return path


def rows(path):
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines()]


@pytest.fixture
def fake_run(monkeypatch, audit):
    """Forbid network; record subprocess.run argv; pretend all tools are installed."""
    import socket
    import urllib.request

    def forbidden(*a, **k):
        pytest.fail("network forbidden")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    calls = []

    def run(argv, **kw):
        calls.append(list(argv))
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(linter.subprocess, "run", run)
    monkeypatch.setattr(linter.shutil, "which", lambda t: "/fake/" + t)
    return calls


def test_run_linter_ruff_argv_and_audit(tmp_path, fake_run, audit):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    issues, name = linter.run_linter(str(f))
    assert name == "ruff" and issues == []
    assert fake_run == [
        ["ruff", "check", "--no-cache", "--output-format=concise", "--", str(f)]
    ]
    r = rows(audit)
    assert len(r) == 1
    assert (r[0]["action"], r[0]["command"], r[0]["authority"]) == (
        "linter.ruff", "linter.ruff", "ACT")
    assert str(tmp_path) not in json.dumps(r)


def test_flake8_and_mypy_never_executed(tmp_path, fake_run, audit, monkeypatch):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    linter.run_all_linters(str(f))
    monkeypatch.setenv("CODEY_LINTER", "flake8")
    _issues, name = linter.run_linter(str(f))
    assert name == "none"  # falls to ast fallback, clean file
    monkeypatch.delenv("CODEY_LINTER")
    linter.run_linter(str(f))
    assert all(c[0] == "ruff" for c in fake_run)
    assert linter.skipped_linters() == ["flake8", "mypy"]


def test_dash_filename_after_double_dash(tmp_path, fake_run, monkeypatch):
    (tmp_path / "-x.py").write_text("x = 1\n")
    monkeypatch.chdir(tmp_path)
    linter.run_linter("-x.py")
    linter.run_all_linters("-x.py")
    for argv in fake_run:
        i = argv.index("--")
        assert argv[i + 1:] == ["-x.py"]
        assert all(not a.startswith("-x") for a in argv[:i])


@pytest.mark.parametrize("kind", ["missing", "dir", "nul"])
def test_non_regular_file_refused_no_subprocess(tmp_path, fake_run, audit, kind):
    target = {"missing": tmp_path / "no.py", "dir": tmp_path / "d.py"}.get(kind)
    if kind == "dir":
        target.mkdir()
    path = str(target) if target else str(tmp_path / "a\x00.py")
    assert linter.run_linter(path) == ([], "none")
    assert linter.run_all_linters(path) == []
    assert fake_run == [] and rows(audit) == []


def test_fifo_not_linted_or_read(tmp_path, fake_run):
    import os
    fifo = tmp_path / "f.py"
    os.mkfifo(fifo)
    assert linter.run_linter(str(fifo)) == ([], "none")  # must not block on read
    assert linter.run_all_linters(str(fifo)) == []
    assert fake_run == []


@pytest.mark.parametrize("exc", [subprocess.TimeoutExpired("ruff", 20), FileNotFoundError("x"), OSError("y")])
def test_tool_failure_degrades_with_static_audit(tmp_path, monkeypatch, audit, exc):
    f = tmp_path / "secret_name.py"
    f.write_text("import os\n")
    monkeypatch.setattr(linter.shutil, "which", lambda t: "/fake/" + t)

    def boom(argv, **kw):
        raise exc

    monkeypatch.setattr(linter.subprocess, "run", boom)
    issues, name = linter.run_linter(str(f))
    assert name == "none" and issues == []  # no raise, ast fallback on clean file
    assert linter.run_all_linters(str(f))[0][0] == "syntax"
    r = rows(audit)
    assert r and all(x["outcome"] == "failed" and x["reason"] == "linter unavailable" for x in r)
    assert "secret_name" not in json.dumps(r)


def test_syntax_error_fallback_still_reported(tmp_path, monkeypatch, audit):
    f = tmp_path / "bad.py"
    f.write_text("def (:\n")
    monkeypatch.setattr(linter.shutil, "which", lambda t: None)
    issues, name = linter.run_linter(str(f))
    assert name == "ast" and issues[0].code == "SyntaxError"


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not on PATH")
def test_real_ruff_no_cache_dash_name_and_config(tmp_path, audit, monkeypatch):
    monkeypatch.setenv("PATH", "/data/data/com.termux/files/usr/bin:/usr/bin:/bin")
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "ruff.toml").write_text('[lint]\nselect = ["F"]\n')
    (proj / "-x.py").write_text("import os\n")
    monkeypatch.chdir(proj)
    issues, name = linter.run_linter("-x.py")
    assert name == "ruff"
    assert [i.code for i in issues] == ["F401"]
    assert not (proj / ".ruff_cache").exists()
    res = linter.run_all_linters("-x.py")
    assert dict(res)["ruff"][0].code == "F401"
    assert not list(tmp_path.rglob(".ruff_cache"))
    # Workspace config still honored: select only E => F401 not reported.
    (proj / "ruff.toml").write_text('[lint]\nselect = ["E"]\n')
    issues, _ = linter.run_linter("-x.py")
    assert issues == []
    assert len(rows(audit)) == 3
