"""Tests for tools/wp21_census.py (WP2.1 group 15, slice G15a).

Unit tests run on synthetic source snippets and tiny temp git repos; nothing
here imports scanned repo code.  The repo-level coverage test at the bottom
scans the HEAD snapshot of this repo (a few seconds; skipped when git or the
register is unavailable, or WP21_CENSUS_SKIP_REPO=1).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from tools import wp21_census as wc

REPO = Path(__file__).resolve().parent.parent
REGISTER = REPO / "docs" / "wp21_census" / "dispositions.tsv"


def scan(src: str, path: str = "m.py"):
    rows, _ = wc.scan_python_source(path, textwrap.dedent(src))
    return rows


def cc(src: str, path: str = "m.py"):
    return [(r.category, r.callee) for r in scan(src, path)]


# --------------------------------------------------------------------------
# Pattern table: one case per category / notable form
# --------------------------------------------------------------------------

@pytest.mark.parametrize("src,expected", [
    # fs_write
    ("open('x', 'w')", [("fs_write", "open")]),
    ("open('x', mode='a')", [("fs_write", "open")]),
    ("open('x', 'r')", []),
    ("open('x')", []),
    ("open('x', m)", [("fs_write", "open")]),                     # dynamic mode
    ("p.write_text('a')", [("fs_write", "*.write_text")]),
    ("p.replace(q)", [("fs_write", "*.replace")]),                # Path.replace
    ("s.replace('a', 'b')", []),                                  # str.replace
    ("import os\nos.remove('x')", [("fs_write", "os.remove")]),
    ("import os as o\no.makedirs('x')", [("fs_write", "os.makedirs")]),   # alias
    ("from shutil import rmtree as rt\nrt('x')", [("fs_write", "shutil.rmtree")]),
    ("import tempfile\ntempfile.mkstemp()", [("fs_write", "tempfile.mkstemp")]),
    ("import zipfile\nzipfile.ZipFile('a', 'w')", [("fs_write", "zipfile.ZipFile")]),
    ("import zipfile\nzipfile.ZipFile('a')", []),
    ("p.open('wb')", [("fs_write", "*.open")]),
    ("p.open('rb')", []),
    # exec_spawn
    ("import subprocess\nsubprocess.run(['ls'])", [("exec_spawn", "subprocess.run")]),
    ("from subprocess import Popen\nPopen(['ls'])", [("exec_spawn", "subprocess.Popen")]),
    ("import os\nos.system('x')", [("exec_spawn", "os.system")]),
    ("import os\nos.execv('a', [])", [("exec_spawn", "os.execv")]),
    # kill
    ("import os\nos.kill(1, 9)", [("kill", "os.kill")]),
    ("import os\nos.killpg(1, 9)", [("kill", "os.killpg")]),
    ("proc.terminate()", [("kill", "*.terminate")]),
    # network
    ("import socket\nsocket.socket()", [("network", "socket.socket")]),
    ("import urllib.request\nurllib.request.urlopen('u')", [("network", "urllib.request.urlopen")]),
    ("import requests\nrequests.get('u')", [("network", "requests.get")]),
    # dyn_code
    ("exec('x')", [("dyn_code", "exec")]),
    ("import re\nre.compile('x')", []),                            # not builtin compile
    ("import importlib\nimportlib.import_module('x')", [("dyn_code", "importlib.import_module")]),
    ("import pickle\npickle.loads(b)", [("dyn_code", "pickle.loads")]),
    ("import os\ngetattr(os, name)(1)", [("dyn_code", "getattr-dynamic")]),
    ("import os\ngetattr(os, 'name')", []),
    # env_mut
    ("import os\nos.environ['A'] = '1'", [("env_mut", "os.environ[]=")]),
    ("import os\nos.environ.update({})", [("env_mut", "os.environ.update")]),
    ("import os\nos.chdir('/')", [("env_mut", "os.chdir")]),
    ("import sys\nsys.path.insert(0, 'x')", [("env_mut", "sys.path.insert")]),
    ("import os\nx = os.environ.get('HOME')", []),                 # plain read: census only
    # credential
    ("import os\nos.environ.get('API_TOKEN')", [("credential", "os.environ.get")]),
    ("import os\nos.getenv('OPENROUTER_API_KEY')", [("credential", "os.getenv")]),
    ("import os\nos.environ['MY_SECRET']", [("credential", "os.environ[]")]),
    ("import getpass\ngetpass.getpass()", [("credential", "getpass.getpass")]),
    ("p = '/home/u/.ssh/id'", [("credential", "const:.ssh")]),
    ("def f():\n    '''about .ssh keys'''\n", []),                  # docstring ignored
    # sqlite
    ("c.execute('INSERT INTO t VALUES (1)')", [("sqlite_write", "*.execute")]),
    ("c.execute('  update t set a=1')", [("sqlite_write", "*.execute")]),
    ("c.execute('SELECT 1')", []),
    ("c.execute(sql)", [("sql_dynamic", "*.execute")]),
    ("c.execute(f'DELETE FROM {t}')", [("sql_dynamic", "*.execute")]),
    ("c.executescript('CREATE TABLE a(b)')", [("sqlite_exec", "*.executescript")]),
    ("c.execute('PRAGMA journal_mode=WAL')", [("sqlite_write", "*.execute")]),
    ("c.execute('PRAGMA table_info(t)')", []),
    ("import sqlite3\nsqlite3.connect('x')", [("sqlite_conn", "sqlite3.connect")]),
])
def test_pattern_table(src, expected):
    assert cc(src) == expected


def test_module_level_sql_constant_resolved_and_detail_verb():
    rows = scan("""
        Q = "DELETE FROM t"
        def f(c):
            c.execute(Q)
    """)
    assert [(r.category, r.detail) for r in rows] == [("sqlite_write", "verb=DELETE")]


def test_credential_argv_in_subprocess():
    rows = scan("import subprocess\nsubprocess.run(['openssl', 'enc'])")
    assert [(r.category, r.callee) for r in rows] == [
        ("exec_spawn", "subprocess.run"), ("credential", "argv:openssl")]


def test_sig0_liveness_probe_flag():
    rows = scan("import os\nos.kill(pid, 0)\nos.kill(pid, 15)")
    assert [r.sig0 for r in rows] == [True, False]


# --------------------------------------------------------------------------
# Row keys
# --------------------------------------------------------------------------

SRC_KEYS = """
import os
class A:
    def m(self):
        os.remove('a')
        os.remove('b')
        def inner():
            os.remove('c')
        return inner
def top():
    f = lambda: os.remove('d')
    return f
os.remove('e')
"""


def test_row_keys_qualname_callee_ordinal():
    keys = [r.key for r in scan(SRC_KEYS)]
    assert keys == [
        "m.py::A.m::os.remove::1",
        "m.py::A.m::os.remove::2",
        "m.py::A.m.<locals>.inner::os.remove::1",
        "m.py::top.<locals>.<lambda>::os.remove::1",
        "m.py::<module>::os.remove::1",
    ]


def test_row_keys_stable_under_line_shifts_but_lines_differ():
    a = scan(SRC_KEYS)
    b = scan("# comment\n\n\n" + SRC_KEYS.replace("import os", "import os\n\n# pad"))
    assert [r.key for r in a] == [r.key for r in b]
    assert [r.line for r in a] != [r.line for r in b]


def test_no_line_numbers_in_keys():
    for r in scan(SRC_KEYS):
        assert r.key.count("::") == 3
        assert r.key.endswith(f"::{r.ordinal}")


# --------------------------------------------------------------------------
# Lexical gate / helper rule
# --------------------------------------------------------------------------

def test_lambda_thunk_inside_gate_exec_is_lexgate():
    rows = scan("""
        import subprocess
        def f(gw):
            gw.gate_exec(authority='ACT', action='a', command='c',
                         confirm_available=False,
                         execute=lambda: subprocess.run(['x']))
    """)
    assert [(r.callee, r.lexgate) for r in rows] == [("subprocess.run", "lambda:gate_exec")]
    d = wc.mechanical_disposition(rows[0])
    assert d["cls"] == "GATED" and d["mediator"] == "lexical:gate_exec"


def test_confirm_callback_is_not_a_mediated_thunk():
    rows = scan("""
        import os
        def f(gw):
            gw.gate_exec(authority='ACT', action='a', command='c',
                         confirm_available=True, execute=run,
                         confirm=lambda: os.write(1, b'?'))
    """)
    assert [r.lexgate for r in rows] == [""]
    assert wc.mechanical_disposition(rows[0]) is None


def test_gate_write_args_are_not_thunks():
    rows = scan("""
        import os
        def f(gw):
            gw.gate_write(authority='ACT', action='a', path='p',
                          content=lambda: os.remove('x'), confirm_available=False)
    """)
    assert rows[0].lexgate == ""


def _scan_files(files):
    src = wc.Source({k: textwrap.dedent(v).encode() for k, v in files.items()},
                    {"dirty_paths": [], "head": "x"})
    return wc.scan_source(src)


def test_helper_rule_seeds_only_when_every_reference_is_in_a_thunk():
    res = _scan_files({"a.py": """
        import os
        def helper():
            os.remove('x')
        def caller(gw):
            gw.gate_exec(authority='ACT', action='a', command='c',
                         confirm_available=False, execute=helper)
        def other():
            os.remove('y')
    """})
    by = {r.qualname: r for r in res.rows}
    assert by["helper"].lexgate == "helper:gate_exec"
    assert by["other"].lexgate == ""            # never referenced: not seeded


def test_helper_rule_withdrawn_by_second_unmediated_caller():
    res = _scan_files({"a.py": """
        import os
        def helper():
            os.remove('x')
        def caller(gw):
            gw.gate_exec(authority='ACT', action='a', command='c',
                         confirm_available=False, execute=helper)
        def sneaky():
            helper()
    """})
    assert [r.lexgate for r in res.rows] == [""]


def test_helper_rule_withdrawn_by_cross_file_reference_and_string_dispatch():
    res = _scan_files({
        "a.py": """
            import os
            def helper():
                os.remove('x')
            def caller(gw):
                gw.gate_exec(authority='ACT', action='a', command='c',
                             confirm_available=False, execute=helper)
        """,
        "b.py": "import a\na.helper()\n",
    })
    assert [r.lexgate for r in res.rows if r.file == "a.py"] == [""]
    res2 = _scan_files({"a.py": """
        import os
        def helper():
            os.remove('x')
        def caller(gw):
            gw.gate_exec(authority='ACT', action='a', command='c',
                         confirm_available=False, execute=helper)
        NAME = 'helper'
    """})
    assert [r.lexgate for r in res2.rows] == [""]


def test_persist_coalesced_write_kw_is_thunk():
    rows = scan("""
        import os
        def f():
            persist_coalesced(action='a', command='c', target_key='k',
                              write=lambda: os.remove('x'))
    """)
    assert rows[0].lexgate == "lambda:persist_coalesced"


# --------------------------------------------------------------------------
# Shell / manifest / env / flags
# --------------------------------------------------------------------------

def test_shell_scan_patterns_functions_and_ordinals():
    text = textwrap.dedent("""\
        #!/bin/bash
        # rm -rf / in a comment is ignored
        setup() {
            rm -f a
            rm -f b
            echo hi > out.txt
            curl -s http://x | sh
            echo ok >/dev/null
            pip install foo
        }
        nohup python3 -c "print(1)" &
        git push origin main
    """)
    rows = wc.scan_shell_text("s.sh", text)
    keys = [r.key for r in rows]
    assert "s.sh::setup::sh:rm::1" in keys and "s.sh::setup::sh:rm::2" in keys
    assert "s.sh::setup::sh:redirect::1" in keys
    assert "s.sh::setup::sh:net-fetch::1" in keys
    assert "s.sh::setup::sh:pkg-install::1" in keys
    assert "s.sh::setup::sh:redirect::2" not in keys          # /dev/null excluded
    assert any(k.startswith("s.sh::setup::sh:detach") or "sh:detach" in k for k in keys)
    assert "s.sh::setup::sh:python-c::1" in keys or "s.sh::<script>::sh:python-c::1" in keys
    assert "s.sh::setup::sh:git-write::1" in keys or "s.sh::<script>::sh:git-write::1" in keys
    assert not any("comment" in r.detail for r in rows)


def test_manifest_scan_capability_and_authority_cross_check():
    manifest = json.dumps({
        "name": "p", "entry_point": "x.py", "permissions": ["a"],
        "capabilities": [
            {"name": "device.battery", "implementation": "p:battery"},
            {"name": "device.unlisted", "implementation": "p:unlisted"},
        ]})
    rows = wc.scan_manifest_text("ccos/plugins/p/manifest.json", manifest, {"device.battery"})
    by = {r.qualname: r for r in rows if r.callee == "manifest:capability"}
    assert "authority_listed=True" in by["$/p/device.battery"].detail
    assert "authority_listed=False" in by["$/p/device.unlisted"].detail
    assert any(r.callee == "manifest:permissions" for r in rows)
    assert any(r.callee == "manifest:entry_point" for r in rows)
    bad = wc.scan_manifest_text("m.json", "{not json", set())
    assert bad[0].callee == "manifest:parse-error"


def test_env_census_and_flag_census():
    res = _scan_files({"a.py": """
        import os, argparse, sys
        os.environ.get('CODEY_LINTER')
        os.getenv('ALLOW_SELF_MOD')
        os.environ['CODEY_STATE_DIR']
        os.environ.get(name)
        p = argparse.ArgumentParser()
        p.add_argument('--daemon')
        if '--yolo' in sys.argv:
            pass
    """})
    env = {e["name"]: e["class"] for e in res.env_rows}
    assert env["CODEY_LINTER"] == "executable-selector"
    assert env["ALLOW_SELF_MOD"] == "authority-modifier"
    assert env["CODEY_STATE_DIR"] == "path-redirect"
    assert env["<dynamic>"] == "mode-toggle"
    flags = {f["flag"] for f in res.flag_rows}
    assert {"--daemon", "--yolo"} <= flags


def test_want_path_scope_rules():
    assert wc.want_path("core/x.py")
    assert wc.want_path("ccos/plugins/a/test.py")          # runnable plugin test.py scanned
    assert wc.want_path("tools/demo_x.py")
    assert not wc.want_path("tests/test_x.py")
    assert not wc.want_path("ccos/tests/test_x.py")
    assert not wc.want_path("core/test_helper.py")
    assert not wc.want_path("conftest.py")
    assert not wc.want_path("docs/a.py")
    assert wc.want_path("install.sh") and wc.want_path("lib/x.sh")
    assert wc.want_path("codeyOS") and not wc.want_path("README.md")
    assert wc.want_path("ccos/plugins/a/manifest.json")
    assert not wc.want_path("other/manifest.json")
    assert wc.want_path(".github/workflows/tests.yml")


def test_parse_only_never_executes_scanned_code(tmp_path):
    marker = tmp_path / "marker"
    src = f"open({str(marker)!r}, 'w').write('x')\nraise SystemExit(3)\n"
    rows, _ = wc.scan_python_source("evil.py", src)
    assert [r.callee for r in rows] == ["open"] and not marker.exists()


# --------------------------------------------------------------------------
# Snapshot mechanics (tiny temp git repo)
# --------------------------------------------------------------------------

def _git(cwd, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({"HOME": str(cwd), "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    return subprocess.run(["git", "-C", str(cwd), *args], check=True, env=env,
                          capture_output=True, text=True).stdout


@pytest.fixture
def tiny_repo(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git not available")
    repo = tmp_path / "repo"
    (repo / "core").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "core" / "a.py").write_text("import os\nos.remove('x')\n")
    (repo / "core" / "b.py").write_text("import os\nos.remove('y')\n")
    (repo / "tests" / "test_a.py").write_text("import os\nos.remove('z')\n")
    (repo / "run.sh").write_text("#!/bin/sh\nrm -f a\n")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _repo_state(repo):
    status = _git(repo, "status", "--porcelain")
    idx = hashlib.sha256((repo / ".git" / "index").read_bytes()).hexdigest()
    head = _git(repo, "rev-parse", "HEAD")
    return status, idx, head


def test_snapshot_reads_head_not_working_tree_and_records_dirty(tiny_repo):
    head = _git(tiny_repo, "rev-parse", "HEAD").strip()
    (tiny_repo / "core" / "a.py").write_text("import os\nos.remove('x')\nos.remove('dirty')\n")
    (tiny_repo / "core" / "new_untracked.py").write_text("import os\nos.remove('u')\n")
    before = _repo_state(tiny_repo)
    res = wc.run(str(tiny_repo))
    assert _repo_state(tiny_repo) == before                      # read-only on the repo
    assert res.meta["head"] == head
    assert set(res.meta["dirty_paths"]) == {"core/a.py", "core/new_untracked.py"}
    files = {r.file for r in res.rows}
    assert files == {"core/a.py", "core/b.py", "run.sh"}         # tests/ excluded, untracked absent
    a_rows = [r for r in res.rows if r.file == "core/a.py"]
    assert len(a_rows) == 1 and a_rows[0].dirty is True          # HEAD content, flagged dirty
    assert res.file_hashes["core/a.py"] == hashlib.sha256(
        b"import os\nos.remove('x')\n").hexdigest()
    assert "tests/test_a.py" not in res.file_hashes


def test_scan_tsv_bytes_identical_with_tree_dirty_or_clean(tiny_repo, tmp_path):
    wc.main(["--repo", str(tiny_repo), "--out", str(tmp_path / "clean")])
    (tiny_repo / "core" / "a.py").write_text("import os\nos.remove('dirty')\n")
    (tiny_repo / "core" / "x.py").write_text("x = 1\n")
    wc.main(["--repo", str(tiny_repo), "--out", str(tmp_path / "dirty")])
    for name in ("scan.tsv", "shell_scan.tsv", "manifest_scan.tsv", "env_names.tsv",
                 "cli_flags.tsv"):
        assert (tmp_path / "clean" / name).read_bytes() == (tmp_path / "dirty" / name).read_bytes()
    assert json.loads((tmp_path / "clean" / "run_meta.json").read_text())["dirty_paths"] == []
    assert "core/a.py" in json.loads((tmp_path / "dirty" / "run_meta.json").read_text())["dirty_paths"]


def test_snapshot_rev_and_bad_rev(tiny_repo):
    res = wc.run(str(tiny_repo), "HEAD")
    assert res.meta["pattern_set_sha256"] == wc.pattern_set_hash()
    with pytest.raises(RuntimeError):
        wc.run(str(tiny_repo), "no-such-rev")


def test_worktree_source_reads_files_in_place(tiny_repo):
    (tiny_repo / "core" / "a.py").write_text("import os\nos.remove('x')\nos.remove('w')\n")
    res = wc.run(str(tiny_repo), source="worktree")
    a = [r for r in res.rows if r.file == "core/a.py"]
    assert len(a) == 2 and all(r.dirty for r in a)


def test_cli_writes_only_to_out_and_leaves_repo_unchanged(tiny_repo, tmp_path, capsys):
    before = _repo_state(tiny_repo)
    tree_before = sorted(p.relative_to(tiny_repo).as_posix()
                         for p in tiny_repo.rglob("*") if ".git/" not in p.as_posix())
    out = tmp_path / "out"
    rc = wc.main(["--repo", str(tiny_repo), "--out", str(out), "--seed"])
    assert rc == 0
    assert _repo_state(tiny_repo) == before
    assert sorted(p.relative_to(tiny_repo).as_posix()
                  for p in tiny_repo.rglob("*") if ".git/" not in p.as_posix()) == tree_before
    assert {p.name for p in out.iterdir()} >= {
        "scan.tsv", "shell_scan.tsv", "manifest_scan.tsv", "env_names.tsv",
        "cli_flags.tsv", "run_meta.json", "summary.json", "dispositions.seed.tsv"}
    meta = json.loads((out / "run_meta.json").read_text())
    assert meta["head"] and "file_sha256" in meta and "tool_version" in meta


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------

def test_deterministic_output_independent_of_file_order(tmp_path):
    files = {"z.py": "import os\nos.remove('1')\n", "a.py": "import os\nos.remove('2')\n",
             "m/b.py": "import os\nos.remove('3')\n", "s.sh": "rm a\n"}
    s1 = wc.Source({k: v.encode() for k, v in files.items()}, {"dirty_paths": [], "head": "h"})
    s2 = wc.Source({k: files[k].encode() for k in reversed(list(files))},
                   {"dirty_paths": [], "head": "h"})
    r1, r2 = wc.scan_source(s1), wc.scan_source(s2)
    wc.write_outputs(str(tmp_path / "o1"), r1, wc.seed_register_rows(r1, "h"), None)
    wc.write_outputs(str(tmp_path / "o2"), r2, wc.seed_register_rows(r2, "h"), None)
    for name in ("scan.tsv", "shell_scan.tsv", "env_names.tsv", "dispositions.seed.tsv",
                 "run_meta.json", "summary.json"):
        assert (tmp_path / "o1" / name).read_bytes() == (tmp_path / "o2" / name).read_bytes()
    keys = [r.key for r in r1.rows]
    assert keys == sorted(keys, key=lambda k: (k.split("::")[0], k.split("::")[1],
                                               k.split("::")[2], int(k.split("::")[3])))


# --------------------------------------------------------------------------
# Taxonomy + coverage behavior
# --------------------------------------------------------------------------

def test_taxonomy_is_eleven_dispositions_plus_unknown():
    assert len(wc.CLASSES) == 12 and wc.CLASSES[-1] == "UNKNOWN"
    assert len(set(wc.CLASSES)) == 12
    assert {"GATED", "NATIVE_AUTHORITY", "BOOKKEEPING", "OPERATOR_BOOTSTRAP",
            "LOOPBACK_IPC", "READ_NOEFFECT", "DORMANT", "OPERATOR_SCRIPT_RUNNABLE",
            "EXCLUDED_SIBLING", "FALSE_POSITIVE", "UNMEDIATED"} <= set(wc.CLASSES)


def reg(key, cls="FALSE_POSITIVE", **kw):
    d = {c: "" for c in wc.REGISTER_COLUMNS}
    d.update(key=key, evidence="because" if cls != "UNKNOWN" else "", **kw)
    d["class"] = cls
    return d


SCAN_FILES = {
    "core/a.py": "import os\nos.remove('x')\nos.remove('y')\n",
    "restoricon_core/s.py": "def w(c):\n    c.execute('INSERT INTO t VALUES (1)')\n",
}


def _cov_scan(files=None, dirty=()):
    f = files or SCAN_FILES
    return wc.scan_source(wc.Source({k: v.encode() for k, v in f.items()},
                                    {"dirty_paths": list(dirty), "head": "h"}))


FULL_REG = [
    reg("core/a.py::<module>::os.remove::1"),
    reg("core/a.py::<module>::os.remove::2"),
    reg("restoricon_core/s.py::w::sqlite_write", "NATIVE_AUTHORITY", count="1"),
]


def codes(cov):
    return sorted({c for c, _ in cov.failures}), sorted({c for c, _ in cov.warnings})


def test_coverage_passes_when_every_row_has_a_disposition():
    cov = wc.evaluate_coverage(_cov_scan(), FULL_REG)
    assert cov.ok and cov.stats["scan_rows"] == 3


def test_coverage_fails_on_new_unregistered_row():
    scan_ = _cov_scan({**SCAN_FILES, "core/a.py": SCAN_FILES["core/a.py"] + "os.remove('z')\n"})
    assert codes(wc.evaluate_coverage(scan_, FULL_REG))[0] == ["unregistered-row"]


def test_coverage_warns_not_fails_for_foreign_dirty_paths():
    scan_ = _cov_scan({**SCAN_FILES, "core/a.py": SCAN_FILES["core/a.py"] + "os.remove('z')\n"},
                      dirty=["core/a.py"])
    cov = wc.evaluate_coverage(scan_, FULL_REG, dirty_paths=["core/a.py"])
    assert cov.ok and codes(cov)[1] == ["unregistered-row"]


def test_coverage_fails_on_stale_register_row_and_warns_when_file_absent():
    stale = FULL_REG + [reg("core/gone.py::f::os.remove::1")]
    assert codes(wc.evaluate_coverage(_cov_scan(), stale))[0] == ["stale-row"]
    cov = wc.evaluate_coverage(_cov_scan(), stale, present_files={"core/a.py"})
    assert cov.ok and codes(cov)[1] == ["stale-row"]


def test_qualname_level_count_mismatch_fails():
    s = _cov_scan({**SCAN_FILES, "restoricon_core/s.py":
                   "def w(c):\n    c.execute('INSERT INTO t VALUES (1)')\n"
                   "    c.execute('DELETE FROM t')\n"})
    assert codes(wc.evaluate_coverage(s, FULL_REG))[0] == ["qualname-count-mismatch"]


def test_restoricon_rows_not_gated_when_disabled():
    only_core = [d for d in FULL_REG if d["key"].startswith("core/")]
    cov = wc.evaluate_coverage(_cov_scan(), only_core, gate_restoricon=False)
    assert cov.ok and codes(cov)[1] == ["unregistered-row"]
    assert not wc.evaluate_coverage(_cov_scan(), only_core).ok


def test_unmediated_requires_finding_and_severity():
    r = [reg("core/a.py::<module>::os.remove::1", "UNMEDIATED"), FULL_REG[1], FULL_REG[2]]
    assert "unmediated-needs-finding-severity" in codes(wc.evaluate_coverage(_cov_scan(), r))[0]
    r[0].update(finding="NEW-1006", severity="HIGH", reach="prod-confirmless")
    assert wc.evaluate_coverage(_cov_scan(), r).ok


def test_gated_mediator_must_be_gate_and_match_scan():
    r = [reg("core/a.py::<module>::os.remove::1", "GATED", mediator="my_wrapper"),
         FULL_REG[1], FULL_REG[2]]
    assert "gated-mediator-not-gate" in codes(wc.evaluate_coverage(_cov_scan(), r))[0]
    r[0]["mediator"] = "lexical:gate_exec"          # real gate name but scan shows no lexical evidence
    assert "gated-lexical-claim-not-in-scan" in codes(wc.evaluate_coverage(_cov_scan(), r))[0]
    r[0]["mediator"] = "gate_exec"                  # explicit named mediator with evidence: accepted
    assert wc.evaluate_coverage(_cov_scan(), r).ok


def test_unknown_allowed_by_default_but_fails_in_strict_mode():
    r = [reg("core/a.py::<module>::os.remove::1", "UNKNOWN"), FULL_REG[1], FULL_REG[2]]
    cov = wc.evaluate_coverage(_cov_scan(), r)
    assert cov.ok and cov.stats["unknown_rows"] == 1
    assert codes(wc.evaluate_coverage(_cov_scan(), r, require_no_unknown=True))[0] == [
        "unknown-remains"]


def test_bad_class_reach_duplicate_and_missing_evidence():
    bad = [reg("core/a.py::<module>::os.remove::1", "NOPE"),
           reg("core/a.py::<module>::os.remove::2", reach="weird"),
           reg("core/a.py::<module>::os.remove::2"),
           reg("restoricon_core/s.py::w::sqlite_write", "NATIVE_AUTHORITY", count="1")]
    bad[3]["evidence"] = ""
    c = codes(wc.evaluate_coverage(_cov_scan(), bad))[0]
    assert {"bad-class", "bad-reach", "duplicate-key", "missing-evidence"} <= set(c)


def test_register_roundtrip_and_merge_preserves_existing_dispositions():
    seed = wc.seed_register_rows(_cov_scan(), "h")
    assert [d["key"] for d in seed] == sorted(d["key"] for d in seed)
    assert all(d["class"] == "UNKNOWN" for d in seed)
    assert any(d["key"] == "restoricon_core/s.py::w::sqlite_write" and d["count"] == "1"
               for d in seed)                            # restoricon rows at qualname/count level
    existing = [reg("core/a.py::<module>::os.remove::1", "FALSE_POSITIVE")]
    merged = wc.merge_seed(existing, seed)
    got = {d["key"]: d["class"] for d in merged}
    assert got["core/a.py::<module>::os.remove::1"] == "FALSE_POSITIVE"
    assert len(merged) == len(seed)
    text = wc.render_register(merged)
    assert wc.parse_register(text) == [{c: d.get(c, "") for c in wc.REGISTER_COLUMNS}
                                       for d in merged]


# --------------------------------------------------------------------------
# W1: attribute calls on a from-imported NAME receiver
# --------------------------------------------------------------------------

@pytest.mark.parametrize("call,expected", [
    ("N.parent.mkdir(parents=True, exist_ok=True)", ("fs_write", "*.mkdir")),
    ("N.write_text('x')", ("fs_write", "*.write_text")),
    ("N.unlink()", ("fs_write", "*.unlink")),
    ("N.open('w')", ("fs_write", "*.open")),
    ("N.kill()", ("kill", "*.kill")),
    ("N.rename(other)", ("fs_write", "*.rename")),
])
def test_from_imported_name_receiver_yields_exactly_one_row(call, expected):
    src = "from utils.config import NOTES_FILE as N\n" + call + "\n"
    assert cc(src) == [expected]


@pytest.mark.parametrize("call", [
    "N.open('r')", "N.append(1)", "N.sort()", "N.read_text()", "N.replace('a', 'b')",
    "N.parent.exists()", "N.items()",
])
def test_from_imported_name_receiver_non_effects_are_not_rows(call):
    assert cc("from utils.config import N\n" + call + "\n") == []


@pytest.mark.parametrize("src,expected", [
    ("import os\nos.remove(x)", [("fs_write", "os.remove")]),
    ("import shutil\nshutil.copy2(a, b)", [("fs_write", "shutil.copy2")]),
    ("import subprocess\nsubprocess.run(['ls'])", [("exec_spawn", "subprocess.run")]),
    ("from os import remove\nremove(x)", [("fs_write", "os.remove")]),   # bare Name call
    ("from os import path\npath.replace(q)", []),   # stdlib from-import: module, not a value
    ("from google.cloud import storage\nstorage.Client()", [("network", "google.cloud.storage.Client")]),
    ("from requests import get\nget.post(u)", [("network", "requests.get.post")]),  # known prefix kept
    ("from signal import SIGTERM\nSIGTERM.kill()", []),   # stdlib root: left alone
])
def test_from_import_receiver_fix_does_not_double_count_or_relabel(src, expected):
    assert cc(src) == expected


def test_w1_reviewer_probe_four_calls_four_rows():
    src = """
    from utils.config import NOTES_FILE as N
    def f():
        N.parent.mkdir()
        N.write_text('x')
        N.unlink()
        N.open('w')
    """
    assert cc(src) == [("fs_write", "*.mkdir"), ("fs_write", "*.write_text"),
                       ("fs_write", "*.unlink"), ("fs_write", "*.open")]


def test_parse_failure_in_production_boundary_file_fails_coverage():
    scan_ = _cov_scan({**SCAN_FILES, "core/new_boundary.py": "def f(:\n"})
    assert scan_.parse_failures
    cov = wc.evaluate_coverage(scan_, FULL_REG)
    assert not cov.ok and codes(cov)[0] == ["parse-failure"]


def test_parse_failure_in_registered_file_is_not_silently_stale_only():
    scan_ = _cov_scan({**SCAN_FILES, "core/a.py": "import os\nos.remove(\n"})
    cov = wc.evaluate_coverage(scan_, FULL_REG)
    assert not cov.ok and "parse-failure" in codes(cov)[0]


def test_parse_failure_in_foreign_dirty_path_only_warns():
    scan_ = _cov_scan({**SCAN_FILES, "core/new_boundary.py": "def f(:\n"},
                      dirty=["core/new_boundary.py"])
    cov = wc.evaluate_coverage(scan_, FULL_REG, dirty_paths=["core/new_boundary.py"])
    assert cov.ok and codes(cov)[1] == ["parse-failure"]


def test_excluded_path_with_syntax_error_is_never_scanned():
    # tests/** is out of scope (want_path), so it can neither fail nor warn.
    assert not wc.want_path("tests/test_broken.py")
    cov = wc.evaluate_coverage(_cov_scan(), FULL_REG)
    assert cov.ok and not cov.warnings


# --------------------------------------------------------------------------
# Repo-level coverage gate (HEAD snapshot of this repo)
# --------------------------------------------------------------------------

def _repo_gate_available():
    return (os.environ.get("WP21_CENSUS_SKIP_REPO") != "1" and shutil.which("git")
            and REGISTER.exists() and (REPO / ".git").exists())


@pytest.mark.skipif(not _repo_gate_available(),
                    reason="git/register unavailable or WP21_CENSUS_SKIP_REPO=1")
def test_repo_head_snapshot_is_covered_by_register():
    """Every boundary row at HEAD must have a register entry (BLOCKING by default).

    Fails on any unregistered or stale row, parse failure, or business
    (restoricon_core) coverage gap.  UNKNOWN is still a valid disposition here;
    zero-UNKNOWN is the separate opt-in closure test (``WP21_CENSUS_STRICT=1``).
    ``WP21_CENSUS_SOURCE=worktree`` is an optional diagnostic mode.  There is no
    warn-only switch: the register is fully dispositioned, so a gap is a real
    unreviewed boundary.
    """
    source = os.environ.get("WP21_CENSUS_SOURCE", "head")
    res = wc.run(str(REPO), "HEAD", source=source)
    register = wc.parse_register(REGISTER.read_text(encoding="utf-8"))
    dirty = res.meta["dirty_paths"] if source == "worktree" else []
    cov = wc.evaluate_coverage(res, register, dirty_paths=dirty,
                               present_files=set(res.file_hashes))
    assert cov.ok, "\n".join(f"{c}: {d}" for c, d in cov.failures[:40])


@pytest.mark.skipif(os.environ.get("WP21_CENSUS_STRICT") != "1" or not _repo_gate_available(),
                    reason="closure check: set WP21_CENSUS_STRICT=1 (UNKNOWN rows must be zero)")
def test_repo_head_snapshot_has_no_unknown_rows():
    res = wc.run(str(REPO), "HEAD")
    register = wc.parse_register(REGISTER.read_text(encoding="utf-8"))
    cov = wc.evaluate_coverage(res, register, present_files=set(res.file_hashes),
                               require_no_unknown=True)
    assert cov.ok, "\n".join(f"{c}: {d}" for c, d in cov.failures[:40])


# --------------------------------------------------------------------------
# Blocking-contract proof: the real repo-level test function against tiny
# disposable git repos (module REPO/REGISTER pointed at the fixture; gate and
# strict env vars absent).  No recursive pytest, no product imports.
# --------------------------------------------------------------------------

def _run_repo_gate(monkeypatch, repo, rows):
    """Call test_repo_head_snapshot_is_covered_by_register against ``repo`` and a
    register built from ``rows``; return None on pass or the AssertionError text."""
    mod = globals()
    register = repo.parent / "dispositions.tsv"
    register.write_text(wc.render_register(rows), encoding="utf-8")
    for var in ("WP21_CENSUS_GATE", "WP21_CENSUS_STRICT", "WP21_CENSUS_SOURCE",
                "WP21_CENSUS_SKIP_REPO"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setitem(mod, "REPO", repo)
    monkeypatch.setitem(mod, "REGISTER", register)
    try:
        test_repo_head_snapshot_is_covered_by_register()
    except AssertionError as e:
        return str(e)
    return None


@pytest.fixture
def gate_repo(tiny_repo, tmp_path, monkeypatch):
    # Isolated HOME/proxies; tiny_repo already builds an isolated git repo.
    monkeypatch.setenv("HOME", str(tmp_path))
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
        monkeypatch.delenv(var, raising=False)
    (tiny_repo / "restoricon_core").mkdir()
    (tiny_repo / "restoricon_core" / "s.py").write_text(SCAN_FILES["restoricon_core/s.py"])
    _git(tiny_repo, "add", ".")
    _git(tiny_repo, "commit", "-q", "-m", "biz")
    res = wc.run(str(tiny_repo), "HEAD")
    seed = wc.seed_register_rows(res, "h")
    return tiny_repo, _disp(seed)


def _disp(seed, have=()):
    """Seed rows -> explicit dispositions (business rows must be NATIVE_AUTHORITY)."""
    return [dict(d, **{"class": "NATIVE_AUTHORITY" if d["key"].startswith("restoricon_core/")
                       else "FALSE_POSITIVE", "evidence": "because"})
            for d in seed if d["key"] not in have]


def _commit_file(repo, rel, text):
    (repo / rel).write_text(text)
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", "add " + rel)


def test_default_gate_passes_with_complete_register(gate_repo, monkeypatch):
    repo, full = gate_repo
    assert _run_repo_gate(monkeypatch, repo, full) is None


def test_default_gate_fails_on_undispositioned_boundary_then_passes_when_registered(
        gate_repo, monkeypatch):
    repo, full = gate_repo
    _commit_file(repo, "core/c.py", "import os\nos.remove('new')\n")
    msg = _run_repo_gate(monkeypatch, repo, full)
    assert msg and "unregistered-row" in msg and "core/c.py" in msg
    res = wc.run(str(repo), "HEAD")
    have = {d["key"] for d in full}
    extra = _disp(wc.seed_register_rows(res, "h"), have)
    assert extra and _run_repo_gate(monkeypatch, repo, full + extra) is None


def test_default_gate_fails_on_undispositioned_business_boundary(gate_repo, monkeypatch):
    repo, full = gate_repo
    _commit_file(repo, "restoricon_core/t.py",
                 "def w2(c):\n    c.execute('DELETE FROM t')\n")
    msg = _run_repo_gate(monkeypatch, repo, full)
    assert msg and "restoricon_core/t.py" in msg


def test_default_gate_fails_on_business_qualname_count_mismatch(gate_repo, monkeypatch):
    repo, full = gate_repo
    _commit_file(repo, "restoricon_core/s.py",
                 SCAN_FILES["restoricon_core/s.py"] + "    c.execute('DELETE FROM t')\n")
    msg = _run_repo_gate(monkeypatch, repo, full)
    assert msg and "qualname-count-mismatch" in msg


def test_default_gate_fails_on_stale_register_row(gate_repo, monkeypatch):
    repo, full = gate_repo
    # File still present at HEAD but the registered ordinal no longer exists.
    stale = full + [reg("core/a.py::<module>::os.remove::2")]
    msg = _run_repo_gate(monkeypatch, repo, stale)
    assert msg and "stale-row" in msg
    # A row for a file absent from HEAD is only a warning (matches evaluate_coverage).
    gone = full + [reg("core/gone.py::f::os.remove::1")]
    assert _run_repo_gate(monkeypatch, repo, gone) is None


def test_default_gate_ignores_dirty_worktree_and_allows_unknown(gate_repo, monkeypatch):
    repo, full = gate_repo
    (repo / "core" / "a.py").write_text("import os\nos.remove('x')\nos.remove('dirty')\n")
    (repo / "core" / "untracked.py").write_text("import os\nos.remove('u')\n")
    assert _run_repo_gate(monkeypatch, repo, full) is None      # HEAD snapshot only
    unknown = [dict(d, **{"class": "UNKNOWN", "evidence": ""}) if i == 0 else d
               for i, d in enumerate(full)]
    assert _run_repo_gate(monkeypatch, repo, unknown) is None   # strict stays opt-in


def test_default_gate_fails_on_parse_failure_in_head_boundary_file(gate_repo, monkeypatch):
    repo, full = gate_repo
    _commit_file(repo, "core/broken.py", "def f(:\n")
    msg = _run_repo_gate(monkeypatch, repo, full)
    assert msg and "parse-failure" in msg


def test_default_gate_mediator_sensitivity(gate_repo, monkeypatch):
    repo, full = gate_repo
    key = next(d["key"] for d in full if d["key"].startswith("core/a.py"))

    def with_gated(mediator):
        return [dict(d, **{"class": "GATED", "mediator": mediator}) if d["key"] == key else d
                for d in full]

    assert "gated-mediator-not-gate" in _run_repo_gate(monkeypatch, repo, with_gated("my_wrapper"))
    assert "gated-lexical-claim-not-in-scan" in _run_repo_gate(
        monkeypatch, repo, with_gated("lexical:gate_exec"))
    assert _run_repo_gate(monkeypatch, repo, with_gated("gate_exec")) is None
