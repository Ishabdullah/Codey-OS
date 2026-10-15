"""WP2.1 group 12b: destructive persistence boundaries use real SQLite."""

import io
import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rich.console import Console

from ccos.core.task_blackboard import TaskBlackboard
from ccos.core.task_context import TaskContext
from core import action_gateway, error_database, preferences, strategy_tracker
from core.action_gateway import ActionGateway
from core.learning import LearningManager
from core.state import StateStore

METHODS = ("preferences", "errors", "strategies", "strategy", "all", "actions", "task")


@pytest.fixture
def env(tmp_path, monkeypatch):
    state = StateStore(tmp_path / "state.db")
    board = TaskBlackboard(str(tmp_path / "board.db"))
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setattr(action_gateway, "get_action_gateway", lambda: ActionGateway(audit))
    for module in (preferences, error_database, strategy_tracker):
        monkeypatch.setattr(module, "get_state_store", lambda: state)
    pref = preferences.PreferenceManager()
    pref._cache = {"test_framework": {"value": "private preference", "confidence": 1}}
    state.set("user_preferences", json.dumps(pref._cache))
    errors = error_database.ErrorDatabase()
    errors.record_error("private type", "private error")
    tracker = strategy_tracker.StrategyTracker()
    tracker.record_attempt("private selected", "private error", True)
    tracker.record_attempt("private retained", "private error", False)
    learning = LearningManager.__new__(LearningManager)
    learning.preferences, learning.error_db, learning.strategy_tracker = pref, errors, tracker
    state.set("private unrelated", "preserved")
    with state._conn:
        state._conn.execute("INSERT INTO episodic_log (timestamp, action) VALUES (0, 'private old')")
        state._conn.execute("INSERT INTO episodic_log (timestamp, action) VALUES (9999999999, 'private future')")
    for task in ("private selected", "private retained"):
        board.create_task(task, "private goal")
        board.set(task, "private key", "private value")
        board.save_checkpoint(TaskContext(task_id=task, step_id="private step", goal="private goal"))
        board.park_escalation(task, "private goal", "private reason")
    value = SimpleNamespace(state=state, board=board, audit=audit, preferences=pref,
                            errors=errors, strategies=tracker, learning=learning)
    yield value
    board.close()
    state.close()


def invoke(env, method, **kwargs):
    calls = {
        "preferences": env.preferences.clear,
        "errors": env.errors.clear,
        "strategies": env.strategies.clear,
        "strategy": lambda **kw: env.strategies.reset_strategy("private selected", **kw),
        "all": env.learning.clear_all,
        "actions": env.state.clear_old_actions,
        "task": lambda **kw: env.board.cleanup_task("private selected", **kw),
    }
    return calls[method](**kwargs)


def audit(env):
    return [json.loads(line) for line in env.audit.read_text().splitlines()]


def snapshot(env):
    return (
        env.state.get_all(), env.state.get_recent_actions(),
        json.dumps(env.preferences._cache, sort_keys=True),
        json.dumps({k: v.to_dict() for k, v in env.errors._cache.items()}, sort_keys=True),
        json.dumps({k: v.to_dict() for k, v in env.strategies._stats.items()}, sort_keys=True),
        [r.to_dict() for r in env.strategies._recent_records],
        [tuple(row) for table in ("task_sessions", "blackboard_entries", "context_checkpoints", "escalation_reviews")
         for row in env.board._conn.execute(f"SELECT * FROM {table}")],
    )


def broken_confirm():
    raise RuntimeError("private callback")


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("kwargs", [
    {}, {"confirm_available": True}, {"confirm": True}, {"confirm": lambda: False},
    {"confirm": broken_confirm}, {"confirm": lambda: 1},
    {"confirm_available": False, "confirm": lambda: True},
])
def test_all_boundaries_refuse_without_explicit_approval(env, method, kwargs):
    before = snapshot(env)
    result = invoke(env, method, **kwargs)
    assert snapshot(env) == before
    if method == "actions":
        assert result == 0
    elif method == "task":
        assert result is False
    else:
        assert result.outcome == "refused"
    record, = audit(env)
    assert record["authority"] == "HIGH_IMPACT"
    assert record["outcome"] == "refused"
    assert "private" not in env.audit.read_text()


@pytest.mark.parametrize("method", METHODS)
def test_approved_reset_changes_only_its_target(env, method):
    confirm = Mock(return_value=True)
    before = snapshot(env)
    result = invoke(env, method, confirm=confirm)
    confirm.assert_called_once_with()
    if method not in ("actions", "task"):
        assert result.allowed
    if method in ("preferences", "all"):
        assert env.preferences._cache == {}
        assert env.state.get("user_preferences") is None
    else:
        assert snapshot(env)[2] == before[2]
    if method in ("errors", "all"):
        assert env.errors._cache == {}
        assert env.state.get("error_database") is None
    else:
        assert snapshot(env)[3] == before[3]
    if method in ("strategies", "all"):
        assert env.state.get("strategy_tracker") is None
        assert set(env.strategies._stats) == set(env.strategies.BUILTIN_STRATEGIES)
        assert env.strategies._recent_records == []
    elif method == "strategy":
        persisted = json.loads(env.state.get("strategy_tracker"))
        assert env.strategies._stats["private selected"].total_attempts == 0
        assert persisted["private selected"]["total_attempts"] == 0
        assert persisted["private retained"]["total_attempts"] == 1
        assert env.strategies._stats["private retained"].total_attempts == 1
        assert snapshot(env)[5] == before[5]  # ordinary reset retains recent history
    else:
        assert snapshot(env)[4:6] == before[4:6]
    if method == "actions":
        assert result == 1
        assert [row["action"] for row in env.state.get_recent_actions()] == ["private future"]
    else:
        assert snapshot(env)[1] == before[1]
    if method == "task":
        assert result is True
        assert env.board.get_task("private selected") is None
        for table in ("blackboard_entries", "context_checkpoints", "escalation_reviews"):
            assert env.board._conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1
    else:
        assert snapshot(env)[6] == before[6]
    assert env.board.get("private retained", "private key") == "private value"
    assert env.state.get("private unrelated") == "preserved"
    record, = audit(env)
    assert record["outcome"] == "allowed"
    assert record["authority"] == "HIGH_IMPACT"
    assert "private" not in env.audit.read_text()
    if method == "all":
        assert result.detail["completed"] == ["preferences", "errors", "strategies"]


def install_failure(env, method):
    if method == "task":
        conn, table, event, condition = env.board._conn, "task_sessions", "DELETE", "1"
    elif method == "actions":
        conn, table, event, condition = env.state._conn, "episodic_log", "DELETE", "1"
    else:
        key = {"preferences": "user_preferences", "errors": "error_database",
               "strategies": "strategy_tracker", "strategy": "strategy_tracker", "all": "user_preferences"}[method]
        event = "INSERT" if method == "strategy" else "DELETE"
        condition = f"{'NEW' if event == 'INSERT' else 'OLD'}.key = '{key}'"
        conn, table = env.state._conn, "state"
    # FAIL preserves earlier trigger changes until transaction rollback. A
    # subsequent successful write proves these are not accidentally committed.
    with conn:
        conn.execute("CREATE TABLE reset_probe (value TEXT)")
        conn.execute(f"CREATE TRIGGER reject_reset BEFORE {event} ON {table} WHEN {condition} "
                     "BEGIN INSERT INTO reset_probe VALUES ('private rollback marker'); "
                     "SELECT RAISE(FAIL, 'private sql failure'); END")
    return conn


@pytest.mark.parametrize("method", METHODS)
def test_sql_failure_keeps_cache_data_and_rolls_back_before_later_writes(env, method):
    conn = install_failure(env, method)
    before = snapshot(env)
    result = invoke(env, method, confirm=lambda: True)
    assert snapshot(env) == before
    if method == "actions":
        assert result == 0
    elif method == "task":
        assert result is False
    else:
        assert result.outcome == "failed"
    assert not conn.in_transaction
    if method == "task":
        env.board.create_task("later successful write")
    else:
        env.state.set("later successful write", "safe")
    assert conn.execute("SELECT count(*) FROM reset_probe").fetchone()[0] == 0
    record, = audit(env)
    assert record["outcome"] == "failed"
    assert record["reason"] == "Persistence reset failed"
    assert "private" not in env.audit.read_text()


@pytest.mark.parametrize("failure_step,completed", [
    ("preferences", []), ("errors", ["preferences"]),
    ("strategies", ["preferences", "errors"]),
])
def test_aggregate_partial_progress_is_truthful_and_confirms_once(env, failure_step, completed):
    install_failure(env, failure_step)
    before = snapshot(env)
    confirm = Mock(return_value=True)
    result = env.learning.clear_all(confirm=confirm)
    confirm.assert_called_once_with()
    assert result.outcome == "failed"
    assert result.detail["completed"] == completed
    assert (env.state.get("user_preferences") is None) == ("preferences" in completed)
    assert (env.state.get("error_database") is None) == ("errors" in completed)
    assert env.state.get("strategy_tracker") == before[0]["strategy_tracker"]
    assert snapshot(env)[4:6] == before[4:6]
    record, = audit(env)
    assert record["action"] == "learning.clear_all"
    assert record["outcome"] == "failed"
    assert "private" not in env.audit.read_text()


@pytest.mark.parametrize("invalid", [True, False, -1, 1.5, "24", None, float("nan"), float("inf")])
def test_retention_validation_precedes_deletion(env, invalid):
    before = snapshot(env)
    confirm = Mock(return_value=True)
    with pytest.raises(ValueError, match="non-negative integer"):
        env.state.clear_old_actions(invalid, confirm=confirm)
    assert snapshot(env) == before
    confirm.assert_not_called()
    assert not env.audit.exists()


def test_zero_retention_is_valid_and_missing_targets_keep_bool_contract(env):
    assert env.state.clear_old_actions(0, confirm=lambda: True) == 1
    assert env.board.cleanup_task("missing", confirm=lambda: True) is False
    assert env.strategies.reset_strategy("missing", confirm=lambda: True).allowed


@pytest.mark.parametrize("method", METHODS)
def test_reset_does_not_commit_or_rollback_preexisting_transaction(env, method):
    conn = env.board._conn if method == "task" else env.state._conn
    conn.execute("CREATE TABLE pending_recording (value TEXT)")
    conn.commit()
    conn.execute("INSERT INTO pending_recording VALUES ('unrelated pending data')")
    before = snapshot(env)
    result = invoke(env, method, confirm=lambda: True)
    assert snapshot(env) == before
    assert conn.in_transaction
    assert conn.execute("SELECT count(*) FROM pending_recording").fetchone()[0] == 1
    if method == "actions":
        assert result == 0
    elif method == "task":
        assert result is False
    else:
        assert result.outcome == "failed"
    assert audit(env)[0]["outcome"] == "failed"
    conn.rollback()
    assert conn.execute("SELECT count(*) FROM pending_recording").fetchone()[0] == 0


@pytest.fixture
def closed_logging_output(monkeypatch):
    from utils import logger

    stream = io.StringIO()
    console = Console(file=stream, force_terminal=False)
    stream.close()
    monkeypatch.setattr(logger, "console", console)
    monkeypatch.setattr(logger, "_current_log_level", logging.INFO)
    # Verify the real logger path raises, rather than mocking info itself.
    with pytest.raises(ValueError, match="closed file"):
        logger.info("closed output probe")


@pytest.mark.parametrize("method", METHODS)
def test_closed_rich_output_cannot_misreport_completed_reset(env, closed_logging_output, method):
    result = invoke(env, method, confirm=lambda: True)
    if method == "actions":
        assert result == 1
        assert [row["action"] for row in env.state.get_recent_actions()] == ["private future"]
    elif method == "task":
        assert result is True
        assert env.board.get_task("private selected") is None
    else:
        assert result.allowed
    if method in ("preferences", "all"):
        assert env.state.get("user_preferences") is None
        assert env.preferences._cache == {}
    if method in ("errors", "all"):
        assert env.state.get("error_database") is None
        assert env.errors._cache == {}
    if method in ("strategies", "all"):
        assert env.state.get("strategy_tracker") is None
        assert env.strategies._recent_records == []
    if method == "strategy":
        assert env.strategies._stats["private selected"].total_attempts == 0
        assert json.loads(env.state.get("strategy_tracker"))["private selected"]["total_attempts"] == 0
    if method == "all":
        assert result.detail["completed"] == ["preferences", "errors", "strategies"]
    record, = audit(env)
    assert record["outcome"] == "allowed"


def test_closed_rich_output_keeps_aggregate_partial_progress_truthful(env, closed_logging_output):
    install_failure(env, "errors")
    result = env.learning.clear_all(confirm=lambda: True)
    assert result.outcome == "failed"
    assert result.detail["completed"] == ["preferences"]
    assert env.state.get("user_preferences") is None
    assert env.preferences._cache == {}
    assert env.state.get("error_database") is not None
    assert env.errors._cache
    assert env.state.get("strategy_tracker") is not None
    record, = audit(env)
    assert record["outcome"] == "failed"
