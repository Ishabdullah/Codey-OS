"""Linter output parsing: ruff prints cwd-relative paths; parse structurally, fail visible."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from core import linter
from core.linter import LintIssue, _parse_colon_format

RUFF = "/data/data/com.termux/files/usr/bin/ruff"
needs_ruff = pytest.mark.skipif(not os.path.exists(RUFF), reason="real ruff not installed")
SRC = "import os\n"
TAIL = ["check", "--no-cache", "--output-format=concise", "--"]


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.delenv("CODEY_LINTER", raising=False)
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
        monkeypatch.delenv(k, raising=False)


def _old_parse(output, filepath):
    """Verbatim copy of the pre-fix (HEAD 3981457) _parse_colon_format."""
    issues = []
    fname = Path(filepath).name
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Found") or line.startswith("All checks"):
            continue
        for prefix in (filepath + ":", fname + ":"):
            if line.startswith(prefix):
                line = line[len(prefix) :]
                break
        parts = line.split(":", 2)
        if len(parts) >= 3:
            try:
                lineno = int(parts[0])
                col = int(parts[1]) if parts[1].strip().isdigit() else 0
                rest = parts[2].strip()
                space = rest.find(" ")
                code = rest[:space].strip() if space > 0 else rest
                msg = rest[space + 1 :].strip() if space > 0 else ""
                if not code:
                    continue
                issues.append(LintIssue(filepath, lineno, col, code, msg, "error"))
            except (ValueError, IndexError):
                continue
    return issues


def _raw_codes(filepath, cwd):
    out = subprocess.run(
        [RUFF, "check", "--no-cache", "--output-format=concise", "--", filepath],
        capture_output=True, text=True, cwd=cwd,
    )
    return sorted(
        ln.split(": ", 1)[1].split()[0] for ln in out.stdout.splitlines() if ": " in ln and "Found" not in ln
    )


def _run(filepath, cwd, monkeypatch):
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(linter, "_ruff_argv", lambda p: [RUFF, *TAIL, p])
    issues, name = linter.run_linter(filepath)
    assert name == "ruff"
    return sorted(i.code for i in issues)


@needs_ruff
@pytest.mark.parametrize(
    "case",
    ["cwd_project_abs", "cwd_file_dir", "cwd_unrelated", "relative_arg", "nested", "spaces", "dash_x"],
)
def test_real_ruff_matches_raw(case, tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    sub = proj / "pkg" / "inner"
    sub.mkdir(parents=True)
    other = tmp_path / "elsewhere"
    other.mkdir()
    name = {"spaces": "my file.py", "dash_x": "-x.py"}.get(case, "t.py")
    d = sub if case == "nested" else proj
    f = d / name
    f.write_text(SRC)
    arg, cwd = str(f), proj
    if case == "cwd_file_dir":
        cwd = d
    elif case == "cwd_unrelated":
        cwd = other
    elif case == "relative_arg":
        arg = os.path.relpath(f, proj)
        if name.startswith("-"):
            arg = "./" + arg
    elif case == "dash_x":
        arg = str(f)
    expected = _raw_codes(arg, cwd)
    assert expected, "fixture must produce violations in raw ruff"
    assert _run(arg, cwd, monkeypatch) == expected
    # all_linters path too
    results = dict(linter.run_all_linters(arg))
    assert sorted(i.code for i in results["ruff"]) == expected


@needs_ruff
def test_old_parser_fails_cwd_ancestor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    proj = tmp_path / "proj"
    proj.mkdir()
    f = proj / "t.py"
    f.write_text(SRC)
    out = subprocess.run(
        [RUFF, "check", "--no-cache", "--output-format=concise", "--", str(f)],
        capture_output=True, text=True, cwd=tmp_path,
    ).stdout
    assert out.startswith("proj/t.py:")
    assert _old_parse(out, str(f)) == []  # the bug
    assert [i.code for i in _parse_colon_format(out, str(f))] == ["F401"]  # the fix


@pytest.mark.parametrize("shown", ["{abs}", "t.py", "./t.py", "{rel}", "sub/../t.py"])
def test_parser_path_forms(shown, tmp_path, monkeypatch):
    f = tmp_path / "t.py"
    f.write_text(SRC)
    monkeypatch.chdir(tmp_path)
    p = shown.format(abs=str(f), rel=os.path.relpath(f, tmp_path))
    out = f"{p}:1:8: F401 [*] `os` imported but unused\n{p}:1:1: I001 [*] x y\nFound 2 errors.\n[*] 2 fixable with `--fix`.\n"
    got = _parse_colon_format(out, str(f))
    assert [(i.line, i.col, i.code, i.severity) for i in got] == [(1, 8, "F401", "error"), (1, 1, "I001", "warning")]


def test_parser_colon_in_path(tmp_path, monkeypatch):
    d = tmp_path / "a:1:2"
    d.mkdir()
    f = d / "t.py"
    f.write_text(SRC)
    monkeypatch.chdir(tmp_path)
    got = _parse_colon_format("a:1:2/t.py:3:4: E501 long line\n", str(f))
    assert [(i.line, i.col, i.code) for i in got] == [(3, 4, "E501")]


def test_clean_outputs_are_empty(tmp_path):
    f = tmp_path / "t.py"
    f.write_text("x = 1\n")
    assert _parse_colon_format("All checks passed!\n", str(f)) == []
    assert _parse_colon_format("", str(f)) == []
    assert _parse_colon_format("warning: deprecated option\nAll checks passed!\n", str(f)) == []


def test_unparseable_violations_not_clean(tmp_path, monkeypatch):
    f = tmp_path / "t.py"
    f.write_text(SRC)
    monkeypatch.chdir(tmp_path)
    for out in (
        "somewhere/else.py:1:1: F401 x\nFound 1 error.\n",
        "Found 3 errors.\n",
        "error: Failed to parse ruff.toml\n",
    ):
        got = _parse_colon_format(out, str(f))
        assert len(got) == 1 and got[0].code == "LINT-PARSE" and got[0].severity == "error"
        assert "LINT-PARSE" in linter.format_issues(got)


@pytest.mark.parametrize(
    "code,sev",
    [
        ("F401", "error"), ("E501", "error"), ("I001", "warning"), ("W291", "warning"),
        ("C901", "warning"), ("N801", "warning"), ("UP006", "warning"), ("B007", "warning"),
        ("E999", "error"), ("invalid-syntax:", "error"), ("syntax-error", "error"),
        ("unused-import", "error"), ("undefined-name", "error"),
        ("unsorted-imports", "warning"), ("trailing-whitespace", "warning"),
        ("complex-structure", "warning"),
        ("break-outside-loop", "error"), ("lambda-assignment", "error"),
        ("none-comparison", "error"), ("io-error", "error"),
        ("raise-not-implemented", "error"),
        ("missing-f-string-syntax", "warning"),
    ],
)
def test_severity_table(code, sev, tmp_path, monkeypatch):
    f = tmp_path / "t.py"
    f.write_text(SRC)
    monkeypatch.chdir(tmp_path)
    got = _parse_colon_format(f"t.py:1:1: {code} msg here\n", str(f))
    assert len(got) == 1 and got[0].severity == sev
    assert got[0].code == code.rstrip(":")


def test_real_ruff_syntax_error_is_error(tmp_path, monkeypatch):
    if not shutil.which("ruff"):
        pytest.skip("ruff not installed")
    f = tmp_path / "bad.py"
    f.write_text("def f(:\n    pass\n")
    monkeypatch.chdir(tmp_path)
    issues, used = linter.run_linter(str(f))
    assert used == "ruff"
    errs = [i for i in issues if i.severity == "error"]
    assert errs and all(not i.code.endswith(":") for i in issues)
    assert any("syntax" in i.code.lower() for i in errs)
    assert "[LINTER]" in linter.format_issues(errs)


def test_error_rule_names_match_ruff_dump():
    """Drift pin: the literal must equal ruff's E/F rule names (+ 'invalid-syntax')."""
    ruff = shutil.which("ruff")
    if not ruff:
        pytest.skip("ruff not installed")
    proc = subprocess.run(
        [ruff, "rule", "--all", "--output-format", "json"],
        capture_output=True, text=True, timeout=60,
    )
    if proc.returncode != 0:
        pytest.skip(f"ruff rule --all unavailable: {proc.stderr[:200]}")
    rules = json.loads(proc.stdout)
    expected = {r["name"] for r in rules if r["code"] and re.match(r"^[EF]\d", r["code"])}
    expected.add("invalid-syntax")  # code-less parse error: emitted, absent from the dump
    assert linter._ERROR_RULE_NAMES == expected, (
        "core/linter.py _ERROR_RULE_NAMES drifted from the installed ruff; regenerate it "
        "from `ruff rule --all --output-format json` (E/F-code names + invalid-syntax). "
        f"missing={sorted(expected - linter._ERROR_RULE_NAMES)} "
        f"stale={sorted(linter._ERROR_RULE_NAMES - expected)}"
    )
