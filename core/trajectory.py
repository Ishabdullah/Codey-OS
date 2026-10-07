"""Trajectory store (AGI audit 2.2). DEFAULT OFF: enabled only by CODEY_TRAJECTORY=1.

Records each top-level run_agent episode and its tool calls to a local SQLite
file. Labels (pass/fail) come ONLY from external verifiers via label_*();
the agent's own opinion of its success is never stored as a label (see the
audit: self-judged success is not a training signal).

Fail-open: every hook swallows its own exceptions; a broken store must never
change agent behavior. Data is local only and contains prompts/code/tool
output -- treat the DB as private. Concern: args/results are truncated, not
scrubbed of secrets; do not export the DB off-device without review.
"""
import functools
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

_MAX_ARGS = 2000
_MAX_RESULT = 1000
_local = threading.local()
_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, tag TEXT, prompt TEXT, final TEXT,
  n_tools INTEGER, secs REAL, crashed INTEGER DEFAULT 0,
  verifier TEXT, passed INTEGER);
CREATE TABLE IF NOT EXISTS tool_calls(
  episode_id INTEGER, seq INTEGER, name TEXT, args TEXT, result TEXT, is_error INTEGER, secs REAL);
CREATE TABLE IF NOT EXISTS teacher_traces(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, peer TEXT, task TEXT, output TEXT,
  verifier TEXT, passed INTEGER);
CREATE INDEX IF NOT EXISTS ix_ep_tag ON episodes(tag);
CREATE INDEX IF NOT EXISTS ix_tc_ep ON tool_calls(episode_id);
"""


def enabled() -> bool:
    return os.environ.get("CODEY_TRAJECTORY", "0") == "1"


def db_path() -> Path:
    p = os.environ.get("CODEY_TRAJECTORY_DB")
    if p:
        return Path(p)
    from utils.config import CODEY_STATE_DIR
    return Path(CODEY_STATE_DIR) / "trajectories.db"


def _connect(path=None):
    path = Path(path) if path else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=5)
    con.executescript(_SCHEMA)
    return con


def _trunc(x, n):
    s = x if isinstance(x, str) else json.dumps(x, default=str)
    return s if len(s) <= n else s[:n] + "...[truncated]"


def _save_episode(ep, path=None):
    with _lock:
        con = _connect(path)
        try:
            cur = con.execute(
                "INSERT INTO episodes(ts,tag,prompt,final,n_tools,secs,crashed) VALUES(?,?,?,?,?,?,?)",
                (ep["ts"], ep["tag"], ep["prompt"], ep["final"], len(ep["calls"]), ep["secs"], ep["crashed"]))
            eid = cur.lastrowid
            con.executemany("INSERT INTO tool_calls VALUES(?,?,?,?,?,?,?)",
                            [(eid, i) + c for i, c in enumerate(ep["calls"])])
            con.commit()
            return eid
        finally:
            con.close()


def label_episode(episode_id, verifier: str, passed: bool, path=None):
    """Attach an EXTERNAL verifier's verdict (pytest, bench grader, script exit code)."""
    with _lock:
        con = _connect(path)
        try:
            con.execute("UPDATE episodes SET verifier=?, passed=? WHERE id=?",
                        (verifier, int(bool(passed)), episode_id))
            con.commit()
        finally:
            con.close()


def label_tag(tag: str, verifier: str, passed: bool, since_ts: float = 0.0, path=None) -> int:
    """Label all unlabeled episodes with `tag` recorded at/after since_ts. Returns rows labeled."""
    with _lock:
        con = _connect(path)
        try:
            cur = con.execute(
                "UPDATE episodes SET verifier=?, passed=? WHERE tag=? AND ts>=? AND verifier IS NULL",
                (verifier, int(bool(passed)), tag, since_ts))
            con.commit()
            return cur.rowcount
        finally:
            con.close()


# WP0.5 (CODEY_OS_MASTER_BLUEPRINT.md §21, NEW-761, Critical). A single
# `verified_episodes()` (removed) fed BOTH fine-tune export and anything
# wanting to inspect eval results, with no tag partition -- its own
# docstring called itself "the only eligible fine-tune/eval data",
# conflating training and evaluation sources in one function. The
# documented Phase 3 workflow (AGI_AUDIT_LOG.md) and bench/runner.py's own
# labeling step (tag=f"bench:{task.id}") meant the 8 frozen benchmark
# tasks could be fed straight into the fine-tune corpus, then the
# promotion gate would grade candidates on those same 8 tasks --
# evaluation leakage, scores moving up for the wrong reason. Split into
# two accessors below so the conflation can't be expressed: a
# `tag LIKE 'bench:%'` episode is now structurally ineligible for
# training, full stop, not dependent on every future caller remembering
# to filter it out.
EVAL_TAG_PREFIX = "bench:"


def _query_episodes(path, only_passed, tag_sql_filter):
    if not Path(path or db_path()).exists():
        return []  # reading must not create the DB
    con = _connect(path)
    try:
        q = f"SELECT id,prompt,final,verifier,passed FROM episodes WHERE verifier IS NOT NULL {tag_sql_filter}"
        if only_passed:
            q += " AND passed=1"
        out = []
        for eid, prompt, final, ver, ok in con.execute(q):
            calls = con.execute(
                "SELECT name,args,result,is_error FROM tool_calls WHERE episode_id=? ORDER BY seq", (eid,)).fetchall()
            out.append({"id": eid, "prompt": prompt, "final": final, "verifier": ver,
                        "passed": bool(ok), "calls": calls})
        return out
    finally:
        con.close()


def verified_training_episodes(path=None, only_passed=True):
    """Episodes with an external verdict, eligible for fine-tune export.
    Structurally excludes any episode tagged by the frozen benchmark
    (tag LIKE 'bench:%') -- those are evaluation data and may never be
    trained on, regardless of what labeled them or why."""
    return _query_episodes(path, only_passed, f"AND (tag IS NULL OR tag NOT LIKE '{EVAL_TAG_PREFIX}%')")


def verified_eval_episodes(path=None, only_passed=True):
    """Episodes with an external verdict, tagged by the frozen benchmark
    (tag LIKE 'bench:%') -- for inspecting/auditing eval results. Never
    feed this into fine-tune export; use verified_training_episodes()."""
    return _query_episodes(path, only_passed, f"AND tag LIKE '{EVAL_TAG_PREFIX}%'")


def record_teacher_trace(peer: str, task: str, output: str, path=None):
    """AGI audit 4.3: keep a stronger peer CLI's answer as a candidate distillation example.
    No-op unless CODEY_TRAJECTORY=1; fail-open. UNLABELED: a peer's output is not
    ground truth until an external verifier passes it (label_teacher)."""
    if not enabled():
        return None
    try:
        with _lock:
            con = _connect(path)
            try:
                cur = con.execute(
                    "INSERT INTO teacher_traces(ts,peer,task,output) VALUES(?,?,?,?)",
                    (time.time(), str(peer), _trunc(task, 4000), _trunc(output, 20000)))
                con.commit()
                return cur.lastrowid
            finally:
                con.close()
    except Exception:
        return None


def label_teacher(trace_id: int, verifier: str, passed: bool, path=None):
    with _lock:
        con = _connect(path)
        try:
            con.execute("UPDATE teacher_traces SET verifier=?, passed=? WHERE id=?",
                        (verifier, int(bool(passed)), trace_id))
            con.commit()
        finally:
            con.close()


def verified_teacher_traces(path=None):
    if not Path(path or db_path()).exists():
        return []
    con = _connect(path)
    try:
        return con.execute("SELECT id,peer,task,output,verifier FROM teacher_traces "
                           "WHERE verifier IS NOT NULL AND passed=1").fetchall()
    finally:
        con.close()


def instrument_run_agent(fn):
    """Wrap run_agent. Only the OUTERMOST call on a thread is an episode."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not enabled() or getattr(_local, "ep", None) is not None:
            return fn(*args, **kwargs)
        try:
            prompt = args[0] if args else kwargs.get("user_message", "")
            _local.ep = {"ts": time.time(), "tag": os.environ.get("CODEY_TRAJECTORY_TAG", ""),
                         "prompt": _trunc(prompt, 4000), "calls": [], "final": "", "crashed": 0, "secs": 0.0}
        except Exception:
            _local.ep = None
            return fn(*args, **kwargs)
        ep = _local.ep
        try:
            result = fn(*args, **kwargs)
            try:
                ep["final"] = _trunc(result[0] if isinstance(result, tuple) else result, 2000)
            except Exception:
                pass
            return result
        except BaseException:
            ep["crashed"] = 1
            raise
        finally:
            _local.ep = None
            try:
                ep["secs"] = round(time.time() - ep["ts"], 3)
                _save_episode(ep)
            except Exception:
                pass  # fail open
    return wrapper


def instrument_execute_tool(fn):
    """Wrap execute_tool; appends to the current episode if one is open."""
    @functools.wraps(fn)
    def wrapper(tool_dict, *a, **k):
        ep = getattr(_local, "ep", None)
        if ep is None:
            return fn(tool_dict, *a, **k)
        t0 = time.time()
        res = fn(tool_dict, *a, **k)
        try:
            name = tool_dict.get("name", "") if isinstance(tool_dict, dict) else ""
            args = tool_dict.get("args", {}) if isinstance(tool_dict, dict) else {}
            rs = res if isinstance(res, str) else str(res)
            ep["calls"].append((name, _trunc(args, _MAX_ARGS), _trunc(rs, _MAX_RESULT),
                                int(rs.startswith("[ERROR]")), round(time.time() - t0, 3)))
        except Exception:
            pass
        return res
    return wrapper
