"""Real native handlers/SQLite/gateway with model and network effects forbidden."""
import asyncio
import json
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture
def boundary(tmp_path, monkeypatch):
    import _socket
    import os
    import subprocess
    import urllib.request

    from utils import config

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CODEY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CODEY_ACTION_GATEWAY_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(config, "CODEY_STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(config, "STATE_DB_FILE", tmp_path / "state" / "state.db")
    from core import daemon, planner_client, planner_service
    from core.action_gateway import ActionGateway
    from core.state import StateStore

    def forbidden(*args, **kwargs):
        raise AssertionError("native unit fixture attempted an external effect")

    def wakeup_only(family=-1, type=-1, proto=-1, fileno=None):
        if family == socket.AF_UNIX and fileno is not None:
            return _socket.socket(family, type, proto, fileno=fileno)
        return forbidden()

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    for name in ("kill", "killpg", "getpgid"):
        monkeypatch.setattr(os, name, forbidden)
    monkeypatch.setattr(socket, "socket", wakeup_only)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(daemon, "get_config", lambda: SimpleNamespace(get=lambda *a, **kw: 1800))
    audit = tmp_path / "audit.jsonl"
    gateway = ActionGateway(audit_file=audit)
    monkeypatch.setattr(daemon, "get_action_gateway", lambda: gateway)
    for name in ("info", "warning", "error"):
        monkeypatch.setattr(daemon, name, Mock())
    monkeypatch.setattr(planner_service, "info", Mock())
    planner = AsyncMock(return_value=None)
    monkeypatch.setattr(planner_client, "send_plan_request_async", planner)
    state = StateStore(db_path=tmp_path / "queue.db")
    server = daemon.DaemonServer(state, paths=SimpleNamespace())
    result = SimpleNamespace(server=server, state=state, audit=audit, gateway=gateway, module=daemon, planner=planner, oracle=planner_service)
    try:
        yield result
    finally:
        state.close()


def run(coroutine):
    return asyncio.run(coroutine)


def rows(boundary):
    return [json.loads(line) for line in boundary.audit.read_text().splitlines()] if boundary.audit.exists() else []


@pytest.mark.parametrize("no_plan,yolo", [(False, False), (True, False), (True, True)])
def test_operator_command_commits_inside_actual_act_callback(boundary, monkeypatch, no_plan, yolo):
    b = boundary
    audited_after_mutation = []
    audit = b.gateway._audit

    def observed_audit(**fields):
        if fields["action"] == "daemon.command":
            audited_after_mutation.append(len(b.state.get_all_tasks()))
        audit(**fields)

    monkeypatch.setattr(b.gateway, "_audit", observed_audit)
    response = run(b.server._handle_command({"prompt": "PRIVATE_CUSTOMER_PROMPT", "no_plan": no_plan, "yolo": yolo}))
    assert response["status"] == "ok"
    task = b.state.get_task(response["task_id"])
    assert task["description"] == "PRIVATE_CUSTOMER_PROMPT"
    assert task["needs_planning"] == (0 if no_plan else 1)
    assert audited_after_mutation == [1]
    assert [(row["authority"], row["action"], row["outcome"]) for row in rows(b)] == [("ACT", "daemon.command", "allowed")]
    assert "PRIVATE_CUSTOMER_PROMPT" not in b.audit.read_text()
    b.planner.assert_not_awaited()


@pytest.mark.parametrize("prompt", ["", None, 123])
def test_invalid_command_has_failed_disposition_and_never_enqueues(boundary, prompt):
    b = boundary
    assert run(b.server._handle_command({"prompt": prompt}))["status"] == "error"
    assert b.state.get_all_tasks() == []
    assert [row["outcome"] for row in rows(b)] == ["failed"]


@pytest.mark.parametrize("outcome", [
    ["step one", "step two"], ["one step"], [], None, "malformed",
    TimeoutError("PRIVATE_PLANNER_ERROR"),
    ConnectionRefusedError("PRIVATE_PLANNER_ERROR"),
    RuntimeError("PRIVATE_PLANNER_ERROR"),
])
def test_every_planning_only_outcome_never_enqueues(boundary, monkeypatch, outcome):
    b = boundary
    if isinstance(outcome, Exception):
        b.planner.side_effect = outcome
    else:
        b.planner.return_value = outcome
    added = Mock(wraps=b.state.add_task)
    monkeypatch.setattr(b.state, "add_task", added)
    response = run(b.server._handle_command({"prompt": "PRIVATE_PROMPT", "plan_only": True}))
    assert response["status"] == "ok"
    assert response["task_ids"] == []
    assert "task_id" not in response
    assert response["plan"] == (outcome if isinstance(outcome, list) else [])
    assert b.state.get_all_tasks() == []
    assert b.state.get_recent_actions() == []
    added.assert_not_called()
    assert rows(b) == []
    assert "PRIVATE" not in repr(b.module.warning.call_args_list)


def test_planning_only_no_plan_skips_planner_and_queue(boundary):
    b = boundary
    response = run(b.server._handle_command({"prompt": "x", "plan_only": True, "no_plan": True}))
    assert response["task_ids"] == [] and response["plan"] == []
    b.planner.assert_not_awaited()
    assert b.state.get_all_tasks() == []


def test_planning_only_medium_preserves_planner_tier(boundary):
    b = boundary
    run(b.server._handle_command({"prompt": "x", "plan_only": True, "tier": "medium"}))
    b.planner.assert_awaited_once_with("x", enable_thinking=False)
    assert b.state.get_all_tasks() == []


@pytest.mark.parametrize("steps,expected", [(["a", "b"], ["a", "b"]), (["a"], None), ([], None), (None, None)])
def test_real_oracle_client_returns_short_plan_fallback_without_hidden_task(boundary, monkeypatch, steps, expected):
    b = boundary
    b.planner.return_value = steps
    monkeypatch.setattr(b.module, "is_daemon_running", lambda: True)
    sent = []

    def transport(command, data, timeout):
        assert command == "command"
        assert data["plan_only"] is True
        sent.append(data)
        return run(b.server._handle_command(data))

    monkeypatch.setattr(b.module, "send_command", transport)
    assert b.oracle._request_daemon_plan("PRIVATE_ORACLE_PROMPT") == expected
    assert len(sent) == 1
    assert b.state.get_all_tasks() == []


def test_enqueue_database_error_preserved_privately_but_static_in_audit(boundary, monkeypatch):
    b = boundary
    monkeypatch.setattr(b.state, "add_task", Mock(side_effect=RuntimeError("PRIVATE_DATABASE_ERROR")))
    response = run(b.server._handle_command({"prompt": "PRIVATE_PROMPT"}))
    assert response == {"status": "error", "message": "PRIVATE_DATABASE_ERROR"}
    assert rows(b)[0]["outcome"] == "failed"
    assert rows(b)[0]["reason"] == "Daemon operation failed"
    assert "PRIVATE" not in b.audit.read_text()
    assert b.state.get_all_tasks() == []


@pytest.mark.parametrize("operation", ["command", "cancel"])
def test_post_commit_episodic_failure_preserves_success_and_allowed_audit(boundary, monkeypatch, operation):
    b = boundary
    if operation == "cancel":
        task_id = b.state.add_task("private")
        data = {"id": task_id}
    else:
        data = {"prompt": "private"}
    monkeypatch.setattr(b.state, "log_action", Mock(side_effect=RuntimeError("PRIVATE_EPISODIC_ERROR")))
    response = run(getattr(b.server, f"_handle_{operation}")(data))
    assert response["status"] == "ok"
    assert "committed" in response["warning"]
    assert len(b.state.get_all_tasks()) == 1
    if operation == "cancel":
        assert b.state.get(f"task_cancelled_{task_id}") == "1"
    assert rows(b)[0]["outcome"] == "allowed"
    assert "PRIVATE" not in b.audit.read_text()
    assert "PRIVATE" not in repr(b.module.warning.call_args_list)


@pytest.mark.parametrize("kind", ["pending", "running", "done", "missing", "no-id", "database-error"])
def test_cancellation_actual_outcomes_and_failures_are_audited(boundary, monkeypatch, kind):
    b = boundary
    task_id = b.state.add_task("private")
    if kind == "running":
        b.state.start_task(task_id)
    elif kind == "done":
        b.state.complete_task(task_id)
    data = {"id": 99999 if kind == "missing" else task_id}
    if kind == "no-id":
        data = {}
    if kind == "database-error":
        data = {"id": "PRIVATE_ID"}
        monkeypatch.setattr(b.state, "cancel_task", Mock(side_effect=RuntimeError("PRIVATE_CANCEL_ERROR")))
    response = run(b.server._handle_cancel(data))
    succeeds = kind in ("pending", "running")
    assert response["status"] == ("ok" if succeeds else "error")
    assert rows(b)[0]["authority"] == "ACT"
    assert rows(b)[0]["outcome"] == ("allowed" if succeeds else "failed")
    assert "PRIVATE" not in b.audit.read_text()


@pytest.mark.parametrize("operation", ["ping", "status", "health", "task"])
def test_known_read_handlers_audit_actual_response(boundary, operation):
    b = boundary
    response = run(getattr(b.server, f"_handle_{operation}")({}))
    assert response["status"] == "ok"
    assert [(row["authority"], row["action"], row["outcome"]) for row in rows(b)] == [("READ", f"daemon.{operation}", "allowed")]
    assert b.state.get_all_tasks() == []


def test_read_status_error_is_failed_and_private_task_id_never_audited(boundary):
    b = boundary
    response = run(b.server._handle_task({"id": "PRIVATE_TASK_ID"}))
    assert response["status"] == "error"
    assert "PRIVATE_TASK_ID" in response["message"]
    assert rows(b)[0]["outcome"] == "failed"
    assert "PRIVATE" not in b.audit.read_text()


def test_post_commit_bookkeeping_and_closed_warning_sink_never_invites_enqueue_retry(boundary, monkeypatch):
    import io

    from rich.console import Console

    from utils import logger

    b = boundary
    sink = io.StringIO()
    console = Console(file=sink)
    sink.close()
    monkeypatch.setattr(logger, "console", console)
    monkeypatch.setattr(logger, "_current_log_level", 0)
    monkeypatch.setattr(logger, "_file_logger", None)
    monkeypatch.setattr(b.module, "warning", logger.warning)
    monkeypatch.setattr(b.state, "log_action", Mock(side_effect=RuntimeError("PRIVATE_LOG_ERROR")))
    with pytest.raises(ValueError):
        logger.warning("closed sink control")
    response = run(b.server._handle_command({"prompt": "PRIVATE_PROMPT"}))
    assert response["status"] == "ok"
    assert response["task_id"] == b.state.get_all_tasks()[0]["id"]
    assert len(b.state.get_all_tasks()) == 1
    assert response["warning"] == "Task operation committed; episodic logging failed"
    assert rows(b)[0]["outcome"] == "allowed"
    assert "PRIVATE" not in b.audit.read_text()


@pytest.fixture
def release_boundary(boundary, monkeypatch):
    from threading import Lock

    from core import loader_v2, thermal

    b = boundary
    loader = SimpleNamespace(is_loaded=Mock(return_value=True), is_cleanup_pending=Mock(return_value=False), unload=Mock(return_value=None))
    guard = Lock()
    probe = Mock(return_value=False)
    idle = SimpleNamespace(is_inference_active=Mock(return_value=False))
    monkeypatch.setattr(loader_v2, "get_loader", lambda: loader)
    monkeypatch.setattr(loader_v2, "SWAP_GUARD", guard)
    monkeypatch.setattr(loader_v2, "probe_port_health", probe)
    monkeypatch.setattr(thermal, "get_thermal_manager", lambda: idle)
    return SimpleNamespace(b=b, loader=loader, guard=guard, probe=probe, thermal=idle, loader_module=loader_v2)


@pytest.mark.parametrize("outcome", ["none-success", "false", "exception", "pending", "already-unloaded", "unconfirmed"])
def test_release_callback_actual_outcomes_have_one_truthful_static_audit(release_boundary, monkeypatch, outcome):
    from threading import get_ident

    r = release_boundary
    b = r.b
    if outcome == "false":
        r.loader.unload.return_value = False
    elif outcome == "exception":
        r.loader.unload.side_effect = RuntimeError("PRIVATE_MODEL_ERROR")
    elif outcome == "pending":
        r.loader.is_cleanup_pending.side_effect = [False, True]
    elif outcome == "already-unloaded":
        r.loader.is_loaded.return_value = False
    elif outcome == "unconfirmed":
        r.probe.return_value = True
        monkeypatch.setattr(b.module, "RELEASE_CONFIRM_TIMEOUT_S", 0)
    worker_threads = []
    main_thread = get_ident()
    gate = b.gateway.gate_exec

    def observe_gate(**kwargs):
        worker_threads.append(get_ident())
        assert r.guard.locked()
        return gate(**kwargs)

    monkeypatch.setattr(b.gateway, "gate_exec", observe_gate)
    response = run(b.server._handle_release_model_slot({"model_id": "primary"}))
    assert worker_threads and all(identity != main_thread for identity in worker_threads)
    assert not r.guard.locked()
    assert len(rows(b)) == 1
    assert rows(b)[0]["authority"] == "ACT"
    assert rows(b)[0]["action"] == "daemon.release_model_slot"
    assert "PRIVATE" not in b.audit.read_text()
    if outcome == "none-success":
        assert response["released"] is True
        assert rows(b)[0]["outcome"] == "allowed"
        assert "primary" in b.server._release_slot_last_release
    elif outcome == "already-unloaded":
        assert response["outcome"] == b.module.RELEASE_OUTCOME_ALREADY_UNLOADED
        r.loader.unload.assert_not_called()
        assert rows(b)[0]["outcome"] == "allowed"
    elif outcome == "unconfirmed":
        assert response["outcome"] == b.module.RELEASE_OUTCOME_UNCONFIRMED
        assert response["released"] is False
        assert rows(b)[0]["outcome"] == "failed"
    else:
        assert response["status"] == "error" and response["released"] is False
        assert rows(b)[0]["outcome"] == "failed"
        assert b.server._release_slot_last_release == {}
        r.probe.assert_not_called()


@pytest.mark.parametrize("kind", ["invalid", "busy-task", "busy-swap", "cooldown", "idle-error"])
def test_release_preflight_has_single_disposition_without_unload(release_boundary, monkeypatch, kind):
    r = release_boundary
    b = r.b
    data = {"model_id": "PRIVATE_INVALID_MODEL" if kind == "invalid" else "primary"}
    if kind == "busy-task":
        r.thermal.is_inference_active.return_value = True
    elif kind == "busy-swap":
        r.guard.acquire()
    elif kind == "cooldown":
        b.server._release_slot_last_release["primary"] = b.module.time.monotonic()
    elif kind == "idle-error":
        r.thermal.is_inference_active.side_effect = RuntimeError("PRIVATE_IDLE_ERROR")
    try:
        response = run(b.server._handle_release_model_slot(data))
    finally:
        if kind == "busy-swap":
            r.guard.release()
    assert response["released"] is False
    assert len(rows(b)) == 1
    assert rows(b)[0]["authority"] == "ACT"
    assert rows(b)[0]["outcome"] == ("failed" if kind == "invalid" else "allowed")
    r.loader.unload.assert_not_called()
    assert "PRIVATE" not in b.audit.read_text()
    assert "PRIVATE" not in repr(b.module.warning.call_args_list)


@pytest.mark.parametrize("preflight", [False, True])
def test_release_injected_denial_never_unloads_and_returns_error(release_boundary, monkeypatch, preflight):
    from core.action_gateway import ACT, ActionGateway

    r = release_boundary
    b = r.b

    if preflight:
        r.thermal.is_inference_active.return_value = True

    class DeniedGateway(ActionGateway):
        def gate_exec(self, **kwargs):
            return self.refuse_exec(authority=ACT, action=kwargs["action"], command=kwargs["command"], reason="Injected refusal")

    monkeypatch.setattr(b.module, "get_action_gateway", lambda: DeniedGateway(audit_file=b.audit))
    response = run(b.server._handle_release_model_slot({"model_id": "primary"}))
    assert response["status"] == "error" and response["released"] is False
    r.loader.unload.assert_not_called()
    assert rows(b)[0]["outcome"] == "refused"
    assert not r.guard.locked()
    assert b.server._release_slot_last_release == {}


def test_release_adopted_loader_drops_only_reference_and_never_signals(release_boundary, monkeypatch):
    r = release_boundary
    b = r.b
    loader = r.loader_module.ModelLoader()
    adopted = SimpleNamespace(process=None, stop=Mock(side_effect=AssertionError("foreign stop forbidden")))
    loader._server = adopted
    loader._loaded = True
    monkeypatch.setattr(r.loader_module, "get_loader", lambda: loader)
    # Foreign server can remain alive; no death/owned-reap claim from adoption.
    r.probe.return_value = True
    monkeypatch.setattr(b.module, "RELEASE_CONFIRM_TIMEOUT_S", 0)
    response = run(b.server._handle_release_model_slot({"model_id": "primary"}))
    assert loader._server is None
    adopted.stop.assert_not_called()
    assert response["released"] is False
    assert response["outcome"] == b.module.RELEASE_OUTCOME_UNCONFIRMED
    assert len(rows(b)) == 1


def test_cancelled_release_request_keeps_guard_until_actual_worker_finishes(release_boundary):
    from threading import Event

    r = release_boundary
    b = r.b
    entered, release = Event(), Event()

    def unload():
        entered.set()
        assert release.wait(3)

    r.loader.unload.side_effect = unload

    async def exercise():
        task = asyncio.create_task(b.server._handle_release_model_slot({"model_id": "primary"}))
        try:
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            await asyncio.sleep(0)
            assert r.guard.locked()
            assert not task.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    run(exercise())
    assert not r.guard.locked()
    assert r.loader.unload.call_count == 1
    assert len(rows(b)) == 1 and rows(b)[0]["outcome"] == "allowed"
    assert "primary" in b.server._release_slot_last_release


def test_confirmed_release_survives_closed_rich_sink_and_arms_only_its_cooldown(release_boundary, monkeypatch):
    import io

    from rich.console import Console

    from utils import logger

    r = release_boundary
    b = r.b
    sink = io.StringIO()
    console = Console(file=sink)
    sink.close()
    monkeypatch.setattr(logger, "console", console)
    monkeypatch.setattr(logger, "_current_log_level", 0)
    monkeypatch.setattr(logger, "_file_logger", None)
    monkeypatch.setattr(b.module, "info", logger.info)
    with pytest.raises(ValueError):
        logger.info("broken sink control")
    response = run(b.server._handle_release_model_slot({"model_id": "primary"}))
    assert response["released"] is True
    assert list(b.server._release_slot_last_release) == ["primary"]
    assert len(rows(b)) == 1 and rows(b)[0]["outcome"] == "allowed"
    assert r.loader.unload.call_count == 1


def test_release_retries_pending_cleanup_even_when_loader_reports_not_loaded(release_boundary):
    r = release_boundary
    r.loader.is_loaded.return_value = False
    r.loader.is_cleanup_pending.side_effect = [True, False]
    response = run(r.b.server._handle_release_model_slot({"model_id": "primary"}))
    assert response["released"] is True
    r.loader.unload.assert_called_once()
    assert len(rows(r.b)) == 1


@pytest.mark.parametrize("data", [None, [], "PRIVATE_INVALID_DATA"])
@pytest.mark.parametrize("operation", ["command", "release_model_slot"])
def test_malformed_native_mutation_payload_is_a_failed_static_disposition(boundary, data, operation):
    b = boundary
    response = run(getattr(b.server, f"_handle_{operation}")(data))
    assert response["status"] == "error"
    if operation == "release_model_slot":
        assert response["released"] is False
    assert len(rows(b)) == 1
    assert rows(b)[0]["authority"] == "ACT"
    assert rows(b)[0]["outcome"] == "failed"
    assert b.state.get_all_tasks() == []
    assert "PRIVATE" not in b.audit.read_text()
