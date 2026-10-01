"""Trajectory store (AGI audit 2.2): default off, fail-open, verifier-only labels."""
import inspect
import json
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


def test_episode_fields_stored_full(db, monkeypatch):
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")

    def big(msg, history):
        tj.instrument_execute_tool(lambda d: "x" * 5000)({"name": "n", "args": {"a": "y" * 5000}})
        return "z" * 5000, history
    tj.instrument_run_agent(big)("p" * 5000, [])
    con = sqlite3.connect(db)
    a, r = con.execute("select args,result from tool_calls").fetchone()
    assert a == json.dumps({"a": "y" * 5000}) and r == "x" * 5000
    prompt, final = con.execute("select prompt,final from episodes").fetchone()
    assert prompt == "p" * 5000 and final == "z" * 5000
    for v in (a, r, prompt, final):
        assert "...[truncated]" not in v


def test_oversize_field_replaced_by_marker(db, monkeypatch):
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")
    monkeypatch.setattr(tj, "_MAX_FIELD_CHARS", 100)

    def big(msg, history):
        tj.instrument_execute_tool(lambda d: "x" * 100)({"name": "n", "args": {"a": "y" * 200}})
        tj.instrument_execute_tool(lambda d: "x" * 101)({"name": "n", "args": {}})
        return "done", history
    tj.instrument_run_agent(big)("p", [])
    rows = sqlite3.connect(db).execute("select args,result from tool_calls order by seq").fetchall()
    assert rows[0][0].startswith(tj.OVERSIZE_MARKER_PREFIX)
    assert rows[0][1] == "x" * 100
    assert rows[1][1] == "[[codey-trajectory:omitted-oversize chars=101]]"


def test_recording_fail_open_when_bounding_raises(db, monkeypatch):
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")

    def boom(x):
        raise RuntimeError("boom")
    monkeypatch.setattr(tj, "_bounded", boom)
    assert tj.instrument_run_agent(_fake_agent)("hi", []) == ("done", [])


def test_tool_wrapper_fail_open_when_bounding_raises(db, monkeypatch):
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")
    seen = []

    def agent(msg, history):
        seen.append(tj.instrument_execute_tool(lambda d: "ok")({"name": "n", "args": {}}))
        return "done", history

    def boom(x):
        raise RuntimeError("boom")
    # _bounded works for the episode (prompt/final) but raises for tool calls
    real = tj._bounded
    monkeypatch.setattr(tj, "_bounded", lambda x: boom(x) if x == {} or x == "ok" else real(x))
    assert tj.instrument_run_agent(agent)("hi", []) == ("done", [])
    assert seen == ["ok"]  # tool result unaffected
    assert sqlite3.connect(db).execute("select n_tools from episodes").fetchone()[0] == 0


def test_fail_open_when_save_episode_raises(db, monkeypatch):
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")

    def boom(ep, path=None):
        raise RuntimeError("save failed")
    monkeypatch.setattr(tj, "_save_episode", boom)
    assert tj.instrument_run_agent(_fake_agent)("hi", []) == ("done", [])


def test_episode_budget_marks_rest_as_oversize(db, monkeypatch):
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")
    monkeypatch.setattr(tj, "_MAX_EPISODE_CHARS", 250)

    def agent(msg, history):
        tj.instrument_execute_tool(lambda d: "x" * 100)({"name": "n", "args": {}})
        tj.instrument_execute_tool(lambda d: "y" * 100)({"name": "n", "args": {}})
        tj.instrument_execute_tool(lambda d: "z")({"name": "n", "args": {}})
        return "done", history
    tj.instrument_run_agent(agent)("p" * 100, [])
    con = sqlite3.connect(db)
    rows = con.execute("select args,result from tool_calls order by seq").fetchall()
    assert rows[0] == ("{}", "x" * 100)  # 100 + 2 + 100 = 202 <= 250
    assert rows[1][0] == "{}"  # 204 fits
    assert rows[1][1] == "[[codey-trajectory:omitted-oversize chars=100]]"  # 304 > 250
    assert rows[2][0].startswith(tj.OVERSIZE_MARKER_PREFIX)  # later small fields also replaced
    assert rows[2][1] == "[[codey-trajectory:omitted-oversize chars=1]]"
    assert con.execute("select final from episodes").fetchone()[0] == "[[codey-trajectory:omitted-oversize chars=4]]"


def test_next_episode_records_normally_after_budget_blown(db, monkeypatch):
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")
    monkeypatch.setattr(tj, "_MAX_EPISODE_CHARS", 50)

    def big(msg, history):
        return "z" * 100, history
    tj.instrument_run_agent(big)("p", [])
    tj.instrument_run_agent(_fake_agent)("hi", [])
    rows = sqlite3.connect(db).execute("select prompt,final from episodes order by id").fetchall()
    assert rows[0][1].startswith(tj.OVERSIZE_MARKER_PREFIX)
    assert rows[1] == ("hi", "done")


def test_agent_module_wrapped_and_signature_preserved(monkeypatch):
    monkeypatch.delenv("CODEY_TRAJECTORY", raising=False)
    import core.agent as ag
    assert hasattr(ag.run_agent, "__wrapped__") and hasattr(ag.execute_tool, "__wrapped__")
    params = list(inspect.signature(ag.run_agent).parameters)
    assert params[:3] == ["user_message", "history", "yolo"]
    assert "_in_subtask" in params


def test_teacher_traces_flag_gated_and_verified_only(db, monkeypatch):
    monkeypatch.delenv("CODEY_TRAJECTORY", raising=False)
    assert tj.record_teacher_trace("claude", "t", "out") is None and not db.exists()
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")
    tid = tj.record_teacher_trace("claude", "t", "x" * 30000)
    assert tid and tj.verified_teacher_traces() == []  # unlabeled -> ineligible
    tj.label_teacher(tid, "pytest", True)
    rows = tj.verified_teacher_traces()
    assert len(rows) == 1 and len(rows[0][3]) < 20100 and rows[0][3].endswith("...[truncated]")


def test_teacher_capture_fail_open(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEY_TRAJECTORY", "1")
    monkeypatch.setenv("CODEY_TRAJECTORY_DB", str(tmp_path))  # unopenable
    import core.agent as ag
    ag._record_teacher("claude", "t", "o")  # must not raise
