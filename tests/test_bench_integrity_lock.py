"""G15f Unit B: v2 lock (tasks + evaluator), ledger evidence, run snapshot, compare.

Function-level only, on disposable COPIES. The real agent is never run and the
bench is never executed against a model (null/oracle agents only, as in
tests/test_bench_harness.py)."""
import hashlib
import json
import struct
import shutil
from pathlib import Path

import pytest

from bench import agents, compare, gate, lock, runner
from bench.suite import Task, load_tasks

REPO = Path(__file__).resolve().parent.parent
PRE_SLICE_TASKS_HASH = "90e1f3804d62df38293cd3e4dea4195e1683ad1ef85c9432cea6cdc84e31f72f"
COVERED = ["__init__", "agents", "compare", "gate", "lock", "promote", "runner", "stats", "suite", "verify"]


@pytest.fixture
def copy(tmp_path):
    """Disposable copy of bench/*.py + tasks + a freshly written v2 lock."""
    b = tmp_path / "bench"
    b.mkdir()
    for p in lock.ROOT.glob("*.py"):
        shutil.copy(p, b / p.name)
    shutil.copytree(lock.ROOT / "tasks", b / "tasks",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    lk = b / "suite.lock"
    lock.write_lock(b / "tasks", lk, bench_dir=b)
    return b, lk


# ---- B-T1 hash stability ---------------------------------------------------

def test_suite_hash_algorithm_pinned_on_synthetic_tree(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.txt").write_bytes(b"hi")
    (tmp_path / "b.txt").write_bytes(b"yo")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "z.pyc").write_bytes(b"junk")
    expect = hashlib.sha256(b"a/x.txt\0hi\0b.txt\0yo\0").hexdigest()
    assert lock.suite_hash(tmp_path) == expect


def test_tasks_hash_unchanged_from_pre_slice():
    assert lock.suite_hash() == PRE_SLICE_TASKS_HASH


def test_evaluator_hash_algorithm_pinned(tmp_path):
    (tmp_path / "a.py").write_bytes(b"1")
    (tmp_path / "scorecard.py").write_bytes(b"ignored")
    (tmp_path / "notes.md").write_bytes(b"ignored")
    expect = hashlib.sha256(struct.pack(">Q", 4) + b"a.py" + struct.pack(">Q", 1) + b"1").hexdigest()
    assert lock.evaluator_hash(tmp_path) == expect


def test_evaluator_hash_framing_is_unambiguous(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "f.py").write_bytes(b"X\0g.py\0Y")
    (b / "f.py").write_bytes(b"X"); (b / "g.py").write_bytes(b"Y")
    assert lock.evaluator_hash(a) != lock.evaluator_hash(b)


def test_suite_hash_collision_is_a_pinned_accepted_residual(tmp_path):
    """suite_hash framing is deliberately UNCHANGED (ledger continuity; Ish undecided).
    Do not 'fix' without a decision: it changes every suite_hash and the lock."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    (a / "f.txt").write_bytes(b"X\0g.txt\0Y")
    (b / "f.txt").write_bytes(b"X"); (b / "g.txt").write_bytes(b"Y")
    assert lock.suite_hash(a) == lock.suite_hash(b)


def test_nonutf8_lock_fails_closed_and_runner_raises_runtimeerror(copy, tmp_path, monkeypatch):
    b, lk = copy
    lk.write_bytes(b"tasks:\xff\xfe\n")
    assert lock.read_lock(lk) is None
    assert not lock.verify_lock(b / "tasks", lk, bench_dir=b)
    bad = tmp_path / "bad.lock"
    bad.write_bytes(b"\xff\xfe\x00")
    import functools
    monkeypatch.setattr(runner, "verify_lock", functools.partial(lock.verify_lock, lock=bad))
    with pytest.raises(RuntimeError, match="suite.lock mismatch"):
        runner.run_suite(agents.null_agent, "x", tmp_path / "l.jsonl")


# ---- B-T2 coverage ---------------------------------------------------------

def test_covered_set_is_exactly_expected():
    assert [p.stem for p in lock.evaluator_files()] == COVERED


def test_lock_coverage_every_bench_py_is_covered_or_explicitly_excluded():
    """Fails if a bench/*.py exists that the evaluator hash silently skips."""
    covered = {p.name for p in lock.evaluator_files()}
    for p in lock.ROOT.glob("*.py"):
        assert p.name in covered or p.name in lock.NOT_EVALUATOR, p.name
    assert lock.NOT_EVALUATOR == {"scorecard.py", "power_analysis.py"}


@pytest.mark.parametrize("name", COVERED)
def test_editing_each_covered_file_breaks_lock(copy, name):
    b, lk = copy
    assert lock.verify_lock(b / "tasks", lk, bench_dir=b)
    f = b / f"{name}.py"
    f.write_text(f.read_text() + "\n# x\n")
    assert not lock.verify_lock(b / "tasks", lk, bench_dir=b)


@pytest.mark.parametrize("name", ["scorecard", "power_analysis"])
def test_measurement_modules_not_covered(copy, name):
    b, lk = copy
    f = b / f"{name}.py"
    f.write_text(f.read_text() + "\n# x\n")
    assert lock.verify_lock(b / "tasks", lk, bench_dir=b)


def test_new_bench_py_breaks_lock_fail_closed(copy):
    b, lk = copy
    (b / "zz_new.py").write_text("x = 1\n")
    assert not lock.verify_lock(b / "tasks", lk, bench_dir=b)


def test_task_edit_breaks_lock_and_pycache_does_not(copy):
    b, lk = copy
    (b / "__pycache__").mkdir(exist_ok=True)
    (b / "__pycache__" / "verify.cpython-x.pyc").write_bytes(b"junk")
    (b / "tasks" / "__pycache__").mkdir()
    (b / "tasks" / "__pycache__" / "q.pyc").write_bytes(b"junk")
    assert lock.verify_lock(b / "tasks", lk, bench_dir=b)
    f = next((b / "tasks").rglob("prompt.txt"))
    f.write_text(f.read_text() + "x")
    assert not lock.verify_lock(b / "tasks", lk, bench_dir=b)


# ---- B-T3 format -----------------------------------------------------------

def test_lock_format_v2_and_roundtrip(copy):
    b, lk = copy
    lines = lk.read_text().splitlines()
    assert [l.split(":")[0] for l in lines] == ["tasks", "evaluator"]
    assert lock.read_lock(lk) == {"tasks": lock.suite_hash(b / "tasks"),
                                  "evaluator": lock.evaluator_hash(b)}


def test_malformed_locks_fail_closed(copy):
    b, lk = copy
    t, e = lock.suite_hash(b / "tasks"), lock.evaluator_hash(b)
    for bad in (t + "\n",                                # legacy v1
                f"tasks:{t}\n",                          # missing evaluator line
                f"tasks:{t}\nevaluator:{e}\nextra:1\n",  # extra line
                f"evaluator:{e}\ntasks:{t}\n",           # wrong order
                f"tasks:{t}\nevaluator:{e[:-1]}\n",      # short hex
                f"tasks:{t}\nevaluator:{e.upper()}\n",   # not lowercase hex
                ""):
        lk.write_text(bad)
        assert lock.read_lock(lk) is None
        assert not lock.verify_lock(b / "tasks", lk, bench_dir=b), bad
    assert not lock.verify_lock(b / "tasks", b / "nope.lock", bench_dir=b)
    lk.write_text(f"tasks:{t}\nevaluator:{e}\n")
    assert lock.verify_lock(b / "tasks", lk, bench_dir=b)


def test_self_attestation_is_a_documented_limit(copy):
    """ACCEPTED RESIDUAL (G15f Q2 / spec section 13): a writer who can edit a covered
    file AND call write_lock re-attests it. Detective only, via evaluator_hash in rows."""
    b, lk = copy
    v = b / "verify.py"
    v.write_text(v.read_text() + "\n# tampered\n")
    assert not lock.verify_lock(b / "tasks", lk, bench_dir=b)
    lock.write_lock(b / "tasks", lk, bench_dir=b)
    assert lock.verify_lock(b / "tasks", lk, bench_dir=b)


# ---- real tree -------------------------------------------------------------

def test_real_tree_lock_verifies_and_is_v2():
    assert lock.verify_lock()
    got = lock.read_lock()
    assert got["tasks"] == PRE_SLICE_TASKS_HASH
    assert got["evaluator"] == lock.evaluator_hash()


# ---- B-T4 / B-T5 runner ----------------------------------------------------

def _tasks_copy(tmp_path):
    d = tmp_path / "tasks"
    shutil.copytree(lock.ROOT / "tasks", d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return d


def test_rows_carry_evidence_for_full_default_run(tmp_path):
    rows = runner.run_suite(agents.null_agent, "n", tmp_path / "l.jsonl")
    locked = lock.read_lock()
    assert {r["suite_hash"] for r in rows} == {locked["tasks"]}
    assert {r["evaluator_hash"] for r in rows} == {locked["evaluator"]} == {lock.evaluator_hash()}
    on_disk = [json.loads(l) for l in (tmp_path / "l.jsonl").read_text().splitlines()]
    assert all("evaluator_hash" in r for r in on_disk)


def test_subset_rows_record_subset_hash_and_do_not_compare_with_full(tmp_path):
    ledger = tmp_path / "l.jsonl"
    full = runner.run_suite(agents.oracle_agent, "full", ledger)
    sub = runner.run_suite(agents.oracle_agent, "sub", ledger, tasks=load_tasks()[:1])
    assert sub[0]["suite_hash"] != full[0]["suite_hash"]
    assert sub[0]["suite_hash"] != lock.read_lock()["tasks"]
    assert sub[0]["evaluator_hash"] == full[0]["evaluator_hash"]
    with pytest.raises(ValueError, match="suite versions"):
        compare.compare(full, sub)


def test_custom_tasks_dir_hash_is_that_dirs_hash(tmp_path):
    d = _tasks_copy(tmp_path)
    tasks = load_tasks(d)[:2]
    rows = runner.run_suite(agents.null_agent, "c", tmp_path / "l.jsonl", tasks=tasks)
    # hash of exactly the two task dirs graded (snapshot layout == <id>/...)
    expect = hashlib.sha256()
    for t in tasks:
        for p in sorted(t.dir.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                expect.update((t.id + "/" + p.relative_to(t.dir).as_posix()).encode() + b"\0"
                              + p.read_bytes() + b"\0")
    assert rows[0]["suite_hash"] == expect.hexdigest()


def test_p4_source_rewrite_mid_run_is_not_graded(tmp_path):
    """Agent rewrites the SOURCE hidden test (a path captured before the run) to
    an always-pass test; the snapshot, not the source, is graded -> still False."""
    d = _tasks_copy(tmp_path)
    t = load_tasks(d)[0]
    src_hidden = next((t.dir / "hidden").glob("test_*.py"))

    def evil(task, ws):
        src_hidden.write_text("def test_x():\n    assert True\n")

    rows = runner.run_suite(evil, "evil", tmp_path / "l.jsonl", tasks=[t], require_lock=False)
    assert rows[0]["passed"] is False


def test_p4_snapshot_rewrite_aborts_run_without_rows(tmp_path):
    d = _tasks_copy(tmp_path)
    t = load_tasks(d)[0]
    ledger = tmp_path / "l.jsonl"

    def evil(task, ws):  # `task` points at the snapshot
        next((task.hidden).glob("test_*.py")).write_text("def test_x():\n    assert True\n")

    with pytest.raises(RuntimeError, match="changed during the run"):
        runner.run_suite(evil, "evil", ledger, tasks=[t], require_lock=False)
    assert not ledger.exists()


def test_snapshot_removed_after_run(tmp_path, monkeypatch):
    seen = []
    def spy(task, ws):
        seen.append(task.dir)
    runner.run_suite(spy, "s", tmp_path / "l.jsonl", tasks=load_tasks()[:1])
    assert seen and not seen[0].exists()
    assert seen[0] != load_tasks()[0].dir


def test_runner_refuses_when_evaluator_changed_after_lock_check(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "verify_lock", lambda: True)
    monkeypatch.setattr(runner, "evaluator_hash", lambda: "0" * 64)
    with pytest.raises(RuntimeError, match="evaluator"):
        runner.run_suite(agents.null_agent, "x", tmp_path / "l.jsonl")


def test_runner_refuses_when_tasks_change_between_check_and_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "verify_lock", lambda: True)
    monkeypatch.setattr(runner, "read_lock", lambda: {"tasks": "0" * 64, "evaluator": lock.evaluator_hash()})
    with pytest.raises(RuntimeError, match="between lock check and snapshot"):
        runner.run_suite(agents.null_agent, "x", tmp_path / "l.jsonl")


# ---- B-T6 compare ----------------------------------------------------------

def _rows(label, ev, passed=(True, False, True), **extra):
    out = []
    for i, p in enumerate(passed):
        r = {"label": label, "task": f"t{i}", "rep": 0, "passed": p, "suite_hash": "H"}
        if ev is not None:
            r["evaluator_hash"] = ev
        out.append(r)
    return out


def test_compare_mixed_evaluator_refused():
    with pytest.raises(ValueError, match="evaluator versions"):
        compare.compare(_rows("a", "E1"), _rows("b", "E2"))
    with pytest.raises(ValueError, match="evaluator versions"):
        compare.compare(_rows("a", None), _rows("b", "E1"))


def test_compare_same_or_both_absent_ok():
    assert compare.compare(_rows("a", "E1"), _rows("b", "E1"))["n"] == 3
    assert compare.compare(_rows("a", None), _rows("b", None))["n"] == 3


def test_gate_not_comparable_on_mixed_evaluator_uses_unmodified_gate():
    d = gate.decide(_rows("a", "E1"), _rows("b", "E2"))
    assert d.promote is False
    assert any("not comparable" in r for r in d.reasons)


# ---- B-T9 scorecard anchors ------------------------------------------------

def test_scorecard_anchors_4a_and_4c_preserved():
    """AST-only (the scorecard never runs the bench): runner still imports and calls
    verify_lock (4a, full credit) and gate.decide still carries its conditions (4c)."""
    from bench import scorecard
    repo = scorecard.RepoAst(REPO)
    items = {i["label"][:2]: i for i in scorecard.score_category_4(repo, REPO)}
    assert items["4a"]["points"] == 6.0, items["4a"]
    assert items["4c"]["points"] == 7.0, items["4c"]


# ---- recursive coverage ----------------------------------------------------

def test_subpackage_py_breaks_lock_fail_closed(copy):
    b, lk = copy
    (b / "pkg").mkdir()
    (b / "pkg" / "x.py").write_text("x = 1\n")
    assert not lock.verify_lock(b / "tasks", lk, bench_dir=b)


def test_tasks_py_and_pycache_do_not_affect_evaluator_hash(copy):
    b, lk = copy
    before = lock.evaluator_hash(b)
    f = next((b / "tasks").rglob("*.py"))
    f.write_text(f.read_text() + "\n# x\n")
    (b / "pkg").mkdir()
    (b / "pkg" / "__pycache__").mkdir()
    (b / "pkg" / "__pycache__" / "x.py").write_text("junk")
    assert lock.evaluator_hash(b) == before


def test_all_real_bench_nonpy_files_are_known_data():
    """Non-.py files outside tasks/ are intentionally uncovered; a new kind must be a decision."""
    known = {"README.md", "power_analysis.md", "scorecard.md", "scorecard_history.jsonl",
             "scorecard_manual.json", "suite.lock"}
    found = {p.name for p in lock.ROOT.rglob("*") if p.is_file() and p.suffix != ".py"
             and "tasks" not in p.relative_to(lock.ROOT).parts and "__pycache__" not in p.parts
             and p.suffix != ".pyc"}
    assert found <= known, found - known
