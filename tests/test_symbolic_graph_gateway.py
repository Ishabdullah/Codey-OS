"""WP2.1 group 12a: real SQLite graph boundaries and atomic deletion."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core import action_gateway
from core.action_gateway import ActionGateway
from core.symbolic_graph import GraphOp, GraphOperation, SymbolicGraph

TABLES = ("sg_concepts", "sg_utterances", "sg_relations", "sg_episodes")


@pytest.fixture
def graph_env(tmp_path, monkeypatch):
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: ActionGateway(audit))
    graph = SymbolicGraph(tmp_path / "graph.db")
    return SimpleNamespace(graph=graph, audit=audit)


def rows(env):
    return [json.loads(line) for line in env.audit.read_text().splitlines()]


def counts(graph):
    conn = graph._get_conn()
    try:
        return [conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] for table in TABLES]
    finally:
        conn.close()


def seed(env):
    env.graph.execute(GraphOperation(GraphOp.CAUSE, {"source": "private source", "target": "private target"}))
    conn = env.graph._get_conn()
    try:
        conn.execute("INSERT INTO sg_episodes (observation, created_at) VALUES ('private episode', 1)")
        conn.commit()
    finally:
        conn.close()
    env.graph._load_graph()
    env.graph._nx_graph = object()
    env.audit.write_text("")


@pytest.mark.parametrize("op", list(GraphOp))
def test_operation_authority_and_private_audit(graph_env, op):
    env = graph_env
    args = {"label": "private label", "source": "private source", "target": "private target"}
    result = env.graph.execute(GraphOperation(op, args))
    assert "error" not in result
    record, = rows(env)
    assert record["authority"] == ("READ" if op == GraphOp.QUERY else "ACT")
    assert record["outcome"] == "allowed"
    assert record["command"] == f"symbolic_graph.{op.value}"
    assert "private" not in env.audit.read_text()
    assert counts(env.graph)[0] == (0 if op == GraphOp.QUERY else 1 if op in (GraphOp.OBSERVE, GraphOp.INTEND) else 2)


def test_batch_one_gate_per_operation_including_relation_autocreate(graph_env):
    env = graph_env
    result = env.graph.execute_batch([
        GraphOperation(GraphOp.CAUSE, {"source": "a", "target": "b"}),
        GraphOperation(GraphOp.QUERY, {}),
    ])
    assert len(result) == 2
    assert [row["authority"] for row in rows(env)] == ["ACT", "READ"]
    assert counts(env.graph)[:3] == [2, 2, 1]


@pytest.mark.parametrize("raised", [False, True])
def test_handler_failure_preserves_error_without_audit_leak(graph_env, monkeypatch, raised):
    env = graph_env

    def fail(args):
        if raised:
            raise ValueError("private exception")
        return {"error": "private error dictionary", "extra": 1}

    monkeypatch.setattr(env.graph, "_op_observe", fail)
    expected = {"error": "private exception"} if raised else {"error": "private error dictionary", "extra": 1}
    assert env.graph.execute(GraphOperation(GraphOp.OBSERVE, {})) == expected
    record, = rows(env)
    assert record["outcome"] == "failed"
    assert record["reason"] == "Symbolic graph operation failed"
    assert "private" not in env.audit.read_text()


def throwing_confirmation():
    raise RuntimeError("private callback failure")


@pytest.mark.parametrize("kwargs", [
    {}, {"confirm_available": True}, {"confirm": True},
    {"confirm_available": False, "confirm": lambda: True},
    {"confirm": lambda: False}, {"confirm": throwing_confirmation},
    {"confirm": lambda: 1},
])
def test_clear_refusal_preserves_every_table_and_cache(graph_env, kwargs):
    env = graph_env
    seed(env)
    before = counts(env.graph)
    concepts = env.graph._concepts.copy()
    relations = env.graph._relations.copy()
    nx = env.graph._nx_graph
    assert env.graph.clear(**kwargs).outcome == "refused"
    assert counts(env.graph) == before
    assert env.graph._concepts == concepts
    assert env.graph._relations == relations
    assert env.graph._nx_graph is nx
    record, = rows(env)
    assert record["authority"] == "HIGH_IMPACT"
    assert record["outcome"] == "refused"
    assert "private" not in env.audit.read_text()


def test_approved_clear_deletes_all_tables_and_caches(graph_env):
    env = graph_env
    seed(env)
    confirm = Mock(return_value=True)
    assert env.graph.clear(confirm=confirm).allowed
    confirm.assert_called_once_with()
    assert counts(env.graph) == [0, 0, 0, 0]
    assert env.graph._concepts == {}
    assert env.graph._relations == []
    assert env.graph._nx_graph is None
    record, = rows(env)
    assert record["outcome"] == "allowed"
    assert record["authority"] == "HIGH_IMPACT"


def test_late_delete_failure_rolls_back_all_tables_and_retains_caches(graph_env):
    env = graph_env
    seed(env)
    before = counts(env.graph)
    concepts = env.graph._concepts.copy()
    relations = env.graph._relations.copy()
    nx = env.graph._nx_graph
    conn = env.graph._get_conn()
    try:
        conn.execute("CREATE TRIGGER reject_episode_delete BEFORE DELETE ON sg_episodes "
                     "BEGIN SELECT RAISE(ABORT, 'private trigger failure'); END")
        conn.commit()
    finally:
        conn.close()
    assert env.graph.clear(confirm=lambda: True).outcome == "failed"
    assert counts(env.graph) == before
    assert env.graph._concepts == concepts
    assert env.graph._relations == relations
    assert env.graph._nx_graph is nx
    record, = rows(env)
    assert record["reason"] == "Symbolic graph clear failed"
    assert "private" not in env.audit.read_text()


def test_symbolic_memory_forwards_confirmation_and_outcome(graph_env, monkeypatch):
    from core import symbolic_graph
    from core.memory_v2 import SymbolicMemory

    monkeypatch.setattr(symbolic_graph, "get_symbolic_graph", lambda: graph_env.graph)
    memory = SymbolicMemory()
    seed(graph_env)
    assert memory.clear(confirm_available=True).outcome == "refused"
    assert memory.clear(confirm=lambda: True).allowed
    memory._available = False
    assert memory.clear(confirm=lambda: True) is None


@pytest.mark.parametrize("mode", ["approve", "decline", "headless", "yolo", "daemon", "noninteractive", "prompt_error", "sql_failure"])
def test_cli_clear_reports_only_completed_success(graph_env, monkeypatch, mode):
    import main
    from core import memory_v2

    seed(graph_env)
    symbolic = SimpleNamespace(clear=graph_env.graph.clear)
    monkeypatch.setattr(memory_v2, "memory", SimpleNamespace(symbolic=symbolic))
    monkeypatch.setattr(main.sys.stdin, "isatty", lambda: mode != "headless")
    monkeypatch.delenv("CODEY_DAEMON_MODE", raising=False)
    monkeypatch.delenv("CODEY_NON_INTERACTIVE", raising=False)
    if mode == "daemon":
        monkeypatch.setenv("CODEY_DAEMON_MODE", "1")
    if mode == "noninteractive":
        monkeypatch.setenv("CODEY_NON_INTERACTIVE", "1")
    prompt = Mock(return_value="no" if mode == "decline" else "yes")
    if mode == "prompt_error":
        prompt.side_effect = EOFError
    if mode == "sql_failure":
        conn = graph_env.graph._get_conn()
        try:
            conn.execute("CREATE TRIGGER reject_clear BEFORE DELETE ON sg_episodes "
                         "BEGIN SELECT RAISE(ABORT, 'failure'); END")
            conn.commit()
        finally:
            conn.close()
    monkeypatch.setattr("builtins.input", prompt)
    success = Mock()
    error = Mock()
    monkeypatch.setattr(main, "success", success)
    monkeypatch.setattr(main, "error", error)
    assert main.handle_command("/graph clear", [], yolo=mode == "yolo") == (True, [])
    assert success.call_count == (1 if mode == "approve" else 0)
    assert error.call_count == (0 if mode == "approve" else 1)
    if mode in ("headless", "yolo", "daemon", "noninteractive"):
        prompt.assert_not_called()
    assert counts(graph_env.graph) == ([0, 0, 0, 0] if mode == "approve" else [2, 2, 1, 1])
