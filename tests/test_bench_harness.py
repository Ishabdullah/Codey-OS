"""Self-checks for bench/: the evaluator must itself be trustworthy (AGI audit 2.1)."""
import shutil

import pytest

from bench import agents, compare, lock, runner, stats
from bench.suite import load_tasks
from bench.verify import grade


def test_null_scores_zero_and_oracle_scores_all(tmp_path):
    ledger = tmp_path / "l.jsonl"
    n = runner.run_suite(agents.null_agent, "null", ledger)
    o = runner.run_suite(agents.oracle_agent, "oracle", ledger)
    assert len(n) == len(load_tasks()) >= 8
    assert not any(r["passed"] for r in n), "a task is solved by doing nothing"
    assert all(r["passed"] for r in o), [r["task"] for r in o if not r["passed"]]


def test_lock_matches_and_detects_tamper(tmp_path):
    assert lock.verify_lock()
    tdir = tmp_path / "tasks"
    shutil.copytree(lock.ROOT / "tasks", tdir)
    lk = tmp_path / "suite.lock"
    lock.write_lock(tdir, lk)
    assert lock.verify_lock(tdir, lk)
    f = next(tdir.rglob("prompt.txt"))
    f.write_text(f.read_text() + "x")
    assert not lock.verify_lock(tdir, lk)


def test_runner_refuses_tampered_suite(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "verify_lock", lambda: False)
    with pytest.raises(RuntimeError):
        runner.run_suite(agents.null_agent, "x", tmp_path / "l.jsonl")


def test_agent_cannot_pass_by_writing_own_tests(tmp_path):
    t = load_tasks()[0]
    ws = tmp_path / "ws"
    shutil.copytree(t.starter, ws)
    (ws / f"test_{t.id}.py").write_text("def test_x():\n    assert True\n")  # same name as hidden
    assert grade(t, ws) is False  # hidden test overwrites it


def test_crashing_agent_recorded_as_failure(tmp_path):
    def boom(task, ws):
        raise RuntimeError("x")
    rows = runner.run_suite(boom, "boom", tmp_path / "l.jsonl", tasks=load_tasks()[:1])
    assert rows[0]["passed"] is False and "RuntimeError" in rows[0]["error"]


def test_mcnemar_known_values():
    assert stats.mcnemar_exact(0, 0) == 1.0
    assert stats.mcnemar_exact(5, 5) == 1.0
    assert abs(stats.mcnemar_exact(0, 8) - 2 / 256) < 1e-12
    assert abs(stats.mcnemar_exact(2, 9) - 2 * 67 / 2048) < 1e-12  # hand-computed
    assert stats.mcnemar_exact(1, 9) < 0.05


def test_compare_and_suite_mismatch(tmp_path):
    ledger = tmp_path / "l.jsonl"
    runner.run_suite(agents.null_agent, "a", ledger)
    runner.run_suite(agents.oracle_agent, "b", ledger)
    r = compare.compare(compare.load(ledger, "a"), compare.load(ledger, "b"))
    assert r["base_only"] == 0 and r["cand_only"] == r["n"] and r["ci95"][0] > 0
    bad = compare.load(ledger, "b")
    bad[0] = dict(bad[0], suite_hash="different")
    with pytest.raises(ValueError):
        compare.compare(compare.load(ledger, "a"), bad)


def test_aa_identical_agents_never_significant(tmp_path):
    ledger = tmp_path / "l.jsonl"
    runner.run_suite(agents.oracle_agent, "a1", ledger)
    runner.run_suite(agents.oracle_agent, "a2", ledger)
    r = compare.compare(compare.load(ledger, "a1"), compare.load(ledger, "a2"))
    assert r["p_value"] == 1.0


def _tmp_task(tmp_path):
    from bench.suite import Task
    t = load_tasks()[0]
    tdir = tmp_path / "tasks" / t.id
    shutil.copytree(t.dir, tdir)
    return Task(t.id, tdir)


def test_grade_tolerates_junk_subdirs_in_hidden(tmp_path):
    # Before the fix, copy2 on a hidden/ subdir raised IsADirectoryError, which grade()
    # swallowed -> False even for the reference solution. Now cache dirs are ignored.
    t = _tmp_task(tmp_path)
    (t.hidden / "__pycache__").mkdir()
    (t.hidden / "__pycache__" / "junk.cpython-311.pyc").write_bytes(b"x")
    (t.hidden / ".pytest_cache").mkdir()
    ws = tmp_path / "ws"
    shutil.copytree(t.reference, ws)
    assert grade(t, ws) is True


def test_grade_copies_hidden_data_subdirs(tmp_path):
    t = _tmp_task(tmp_path)
    (t.hidden / "data").mkdir()
    (t.hidden / "data" / "input.txt").write_text("ok")
    test_file = next(t.hidden.glob("test_*.py"))
    with test_file.open("a") as fh:
        fh.write("\n\ndef test_hidden_data_present():\n"
                 "    from pathlib import Path\n"
                 "    assert (Path(__file__).parent / 'data' / 'input.txt').read_text() == 'ok'\n")
    ws = tmp_path / "ws"
    shutil.copytree(t.reference, ws)
    assert grade(t, ws) is True
