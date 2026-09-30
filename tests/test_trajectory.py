"""Trajectory store (AGI audit 2.2): default off, fail-open, verifier-only labels."""
import inspect
import sqlite3

import pytest

from core import trajectory as tj


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "t.db"
    monkeypatch.setenv("CODEY_TRAJECTORY_DB", str(p))
    return p


def _fake_agent(msg, history, yolo=False):
    tj_tool(lambda d: "ok")({"name": "read_file", "args": {"path": "a"}})
    tj_tool(lambda d: "[ERROR] boom")({"name": "shell", "args": {"cmd": "x"}})
    return "done", history


def tj_tool(f):
    return tj.instrument_execute_tool(f)


def test_default_off_writes_nothing(db, monkeypatch):
    monkeypatch.delenv("CODEY_TRAJECTORY", raising=False)
    w = tj.instrument_run_agent(_fake_agent)
    assert w("hi", []) == ("done", [])
    assert not db.exists()


def test_records_episode_and_tools(db, monkeypatch):
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")
    monkeypatch.setenv("CODEY_TRAJECTORY_TAG", "tagA")
    tj.instrument_run_agent(_fake_agent)("do it", [])
    con = sqlite3.connect(db)
    ep = con.execute("select tag,prompt,final,n_tools,verifier,passed from episodes").fetchall()
    assert ep == [("tagA", "do it", "done", 2, None, None)]
    errs = [r[0] for r in con.execute("select is_error from tool_calls order by seq")]
    assert errs == [0, 1]


def test_nested_calls_are_one_episode(db, monkeypatch):
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")
    holder = {}

    def inner(msg, history):
        return "in", history

    def outer(msg, history):
        return holder["w"]("sub", history)
    holder["w"] = tj.instrument_run_agent(inner)
    tj.instrument_run_agent(outer)("top", [])
    # inner wrapper is a different function object but shares thread-local: only ONE row
    assert sqlite3.connect(db).execute("select count(*) from episodes").fetchone()[0] == 1


def test_crash_recorded_and_reraised(db, monkeypatch):
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")

    def bad(msg, history):
        raise ValueError("x")
    with pytest.raises(ValueError):
        tj.instrument_run_agent(bad)("p", [])
    assert sqlite3.connect(db).execute("select crashed from episodes").fetchone()[0] == 1


def test_fail_open_when_store_broken(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")
    monkeypatch.setenv("CODEY_TRAJECTORY_DB", str(tmp_path))  # a directory: sqlite cannot open it
    assert tj.instrument_run_agent(_fake_agent)("hi", []) == ("done", [])


def test_only_verifier_labels_feed_training_view(db, monkeypatch):
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")
    monkeypatch.setenv("CODEY_TRAJECTORY_TAG", "T")
    w = tj.instrument_run_agent(_fake_agent)
    w("a", []); w("b", [])
    assert tj.verified_episodes() == []  # unlabeled -> not eligible
    assert tj.label_tag("T", "pytest", True) == 2
    assert tj.label_tag("T", "pytest", False) == 0  # already labeled; no overwrite
    assert len(tj.verified_episodes()) == 2
    tj.label_episode(1, "pytest", False)
    assert len(tj.verified_episodes()) == 1
    assert len(tj.verified_episodes(only_passed=False)) == 2


def test_truncation(db, monkeypatch):
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")

    def big(msg, history):
        tj.instrument_execute_tool(lambda d: "x" * 5000)({"name": "n", "args": {"a": "y" * 5000}})
        return "z" * 5000, history
    tj.instrument_run_agent(big)("p", [])
    con = sqlite3.connect(db)
    a, r = con.execute("select args,result from tool_calls").fetchone()
    assert len(a) < 2100 and len(r) < 1100
    assert len(con.execute("select final from episodes").fetchone()[0]) < 2100


def test_agent_module_wrapped_and_signature_preserved(monkeypatch):
    monkeypatch.delenv("CODEY_TRAJECTORY", raising=False)
    import core.agent as ag
    assert hasattr(ag.run_agent, "__wrapped__") and hasattr(ag.execute_tool, "__wrapped__")
    params = list(inspect.signature(ag.run_agent).parameters)
    assert params[:3] == ["user_message", "history", "yolo"]
    assert "_in_subtask" in params
