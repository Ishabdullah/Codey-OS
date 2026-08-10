"""
core/daemon.py's `DaemonServer._handle_command()` — TODO.md 4.1 sub-task C
(WORK_QUEUE.md Track 3 item 2, NEW-112).

Covers only the `plan_only` falsy path this sub-task changed (the
`plan_only=True` RPC path is unchanged and already implicitly covered by
existing production use — no test file previously existed for it, and
this sub-task's spec explicitly requires it be left behaviorally
untouched, not newly tested here).

No real llama-server/plannd subprocess is spawned — `self.state` is a real
tmp-path-backed StateStore (so row contents are asserted for real), and
`self.planner`/`send_plan_request_async` are never reached on this path
(plan_only falsy returns before either is touched).
"""
import asyncio

import core.daemon as daemon_mod
from core.state import StateStore


def _server(db_path):
    state = StateStore(db_path=db_path)
    return daemon_mod.DaemonServer(state=state), state


def _run(coro):
    return asyncio.run(coro)


def test_plan_only_false_enqueues_raw_task_with_needs_planning(tmp_path):
    server, state = _server(tmp_path / "state.db")
    resp = _run(server._handle_command({"prompt": "do the thing"}))

    assert resp == {"status": "ok", "message": "Task queued", "task_id": resp["task_id"]}
    task = state.get_task(resp["task_id"])
    assert task["description"] == "do the thing"
    assert task["status"] == "pending"
    assert task["needs_planning"] == 1


def test_plan_only_false_with_no_plan_true_does_not_set_needs_planning(tmp_path):
    # no_plan=True means "do not plan this at all" — it must not be
    # silently inverted into "plan it later on the pull side" just because
    # the synchronous enqueue-time planning call moved off this code path.
    server, state = _server(tmp_path / "state.db")
    resp = _run(server._handle_command({"prompt": "do the thing", "no_plan": True}))

    task = state.get_task(resp["task_id"])
    assert task["needs_planning"] == 0


def test_no_prompt_is_error(tmp_path):
    server, _ = _server(tmp_path / "state.db")
    resp = _run(server._handle_command({}))
    assert resp["status"] == "error"
