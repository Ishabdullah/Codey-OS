"""
NEW-164/NEW-165 fix coverage — core/plannd.py's local-backend get_plan().

Covers:
  - compute_planner_timeout()'s formula for known inputs (not just "some
    positive number").
  - core/daemon.py deriving an outer timeout that is confirmed greater
    than plannd's own computed inner timeout for the same inputs (NEW-165
    fix 3 — otherwise raising plannd's inner timeout just relocates the
    premature-cancellation bug one layer up).
  - the new warning-log path actually firing when a thinking-mode request
    comes back with finish_reason == "length" and empty content (the
    silent half of NEW-164 — line ~436's old bare `return None`).

No real llama-server subprocess is spawned — urllib.request.urlopen is
mocked directly (this test file's own pattern; no pre-existing
urlopen-mocking test in tests/ to match against, confirmed via search).
"""
import asyncio
import json
import unittest.mock as mock
from io import BytesIO

import pytest

import core.daemon as daemon_mod
import core.plannd as plannd_mod
import core.resource_gate as rg
from core.plannd import (PLANNER_PROMPT, compute_outer_plan_timeout,
                        compute_planner_timeout, get_plan)
from core.state import StateStore
from core.tokens import estimate_tokens
from utils.config import PLANNER_MAX_TOKENS


def _fake_response(payload: dict):
    """Build a context-manager-compatible fake matching urllib's response object."""
    body = json.dumps(payload).encode("utf-8")
    cm = mock.MagicMock()
    cm.__enter__.return_value = BytesIO(body)
    cm.__exit__.return_value = False
    return cm


@pytest.fixture(autouse=True)
def _admit_context_budget_by_default():
    """
    §8 Q11 fix (2026-08-26): get_plan() now runs a context-budget admission
    check (core/resource_gate.py::wait_and_reserve_context_budget()) before
    its urlopen call. This test file's own synthetic environment has no
    resident primary-model slot registered, so that check would otherwise
    always refuse (n_ctx unresolvable — reserve_context_budget()'s own
    documented fail-closed posture, CLAUDE.md rule 12) and every test below
    would fail on admission before ever reaching the HTTP-mocking/parsing
    behavior these tests actually exercise. Autoused so every test in this
    file gets an always-admitted stub without needing to repeat this patch
    per test — this file is specifically about the timeout/logging
    behavior around the HTTP call, not the admission gate itself (see
    tests/test_context_budget.py for that coverage).
    """
    admitted = rg.ContextBudgetDecision(
        admitted=True,
        reservation_id="test-reservation",
        reserved_tokens=0,
        effective_n_ctx=8192,
        ceiling_tokens=8192,
        slots_occupied_tokens=0,
        other_reserved_tokens=0,
        estimate_source="tokenize",
        reason="admitted",
    )
    with mock.patch("core.resource_gate.wait_and_reserve_context_budget", return_value=admitted), \
         mock.patch("core.resource_gate.release_context_budget", return_value=True):
        yield


# ── compute_planner_timeout() formula ───────────────────────────────────────


def test_compute_planner_timeout_known_inputs():
    # (2425 / 10) + (1024 / 2) + 30 = 242.5 + 512 + 30 = 784.5
    assert compute_planner_timeout(2425, 1024) == 784.5


def test_compute_planner_timeout_scales_with_max_tokens():
    # (2425 / 10) + (2048 / 2) + 30 = 242.5 + 1024 + 30 = 1296.5
    assert compute_planner_timeout(2425, 2048) == 1296.5


def test_compute_planner_timeout_zero_inputs_is_just_margin():
    from utils.config import PLANNER_TIMEOUT_MARGIN_SECONDS

    assert compute_planner_timeout(0, 0) == PLANNER_TIMEOUT_MARGIN_SECONDS


# ── daemon.py's outer timeout vs plannd's inner timeout ─────────────────────


def _server(db_path):
    state = StateStore(db_path=db_path)
    return daemon_mod.DaemonServer(state=state), state


def _expected_inner_timeout(prompt: str) -> float:
    prompt_tokens_estimate = estimate_tokens(PLANNER_PROMPT) + estimate_tokens(prompt)
    return compute_planner_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS)


def _expected_outer_timeout(prompt: str) -> float:
    prompt_tokens_estimate = estimate_tokens(PLANNER_PROMPT) + estimate_tokens(prompt)
    return compute_outer_plan_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS)


def test_plan_claimed_task_outer_timeout_matches_formula():
    """
    NEW-165 fix 3 / NEW-260: exercises the real core/daemon.py call site (not a
    re-derivation in the test) — patches asyncio.wait_for as seen from
    core.daemon's own namespace and asserts the actual `timeout` kwarg
    Daemon._plan_claimed_task passed equals
    compute_outer_plan_timeout(...), and that this is strictly
    greater than plannd's own inner timeout for the same inputs.

    _plan_claimed_task's body never touches `self`, so it's called
    directly on the class (self=None) rather than constructing a full
    Daemon() — which would require standing up config/state/planner/
    background-manager machinery unrelated to this method.
    """
    prompt = "do the thing"
    captured = {}

    async def _fake_wait_for(coro, timeout=None):
        coro.close()
        captured["timeout"] = timeout
        return None

    with mock.patch("core.daemon.asyncio.wait_for", side_effect=_fake_wait_for):
        asyncio.run(daemon_mod.Daemon._plan_claimed_task(None, prompt))

    inner_timeout = _expected_inner_timeout(prompt)
    expected_outer = _expected_outer_timeout(prompt)

    assert captured["timeout"] == expected_outer
    assert captured["timeout"] > inner_timeout


def test_handle_command_plan_only_outer_timeout_matches_formula(tmp_path):
    """Same coverage as above, for _handle_command's plan_only=True RPC
    path — the second call site this fix changed."""
    server, _ = _server(tmp_path / "state.db")
    prompt = "do the thing"
    captured = {}

    async def _fake_wait_for(coro, timeout=None):
        coro.close()
        captured["timeout"] = timeout
        return None

    with mock.patch("core.daemon.asyncio.wait_for", side_effect=_fake_wait_for):
        asyncio.run(server._handle_command({"prompt": prompt, "plan_only": True}))

    inner_timeout = _expected_inner_timeout(prompt)
    expected_outer = _expected_outer_timeout(prompt)

    assert captured["timeout"] == expected_outer
    assert captured["timeout"] > inner_timeout


# ── get_plan()'s local-backend branch: empty-content/length warning ────────


def test_get_plan_logs_warning_on_empty_content_after_length():
    fake_payload = {
        "choices": [
            {
                "finish_reason": "length",
                "message": {
                    "content": "",
                    "reasoning_content": "x" * 4632,
                },
            }
        ],
        "usage": {"completion_tokens": 1024, "prompt_tokens": 2425},
    }

    with mock.patch.object(
        plannd_mod.urllib.request, "urlopen", return_value=_fake_response(fake_payload)
    ) as mock_urlopen, mock.patch("utils.logger.warning") as mock_warning:
        result = get_plan("do the thing")

    assert result is None
    assert mock_warning.called
    logged_msg = mock_warning.call_args[0][0]
    assert "finish_reason=length" in logged_msg
    assert "max_tokens=" in logged_msg
    assert "reasoning_content_len=4632" in logged_msg

    # NEW-165: confirm get_plan() actually wires the computed timeout into
    # urlopen() — not just that the formula function itself is correct in
    # isolation (the earlier version of this test left this line
    # unasserted, meaning a regression to `timeout=60` would pass silently).
    expected_prompt_tokens = estimate_tokens(PLANNER_PROMPT) + estimate_tokens("do the thing")
    expected_timeout = compute_planner_timeout(expected_prompt_tokens, PLANNER_MAX_TOKENS)
    assert mock_urlopen.call_args.kwargs["timeout"] == expected_timeout


def test_get_plan_no_warning_when_content_present():
    fake_payload = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": "1. Do the thing\n2. Verify it"},
            }
        ],
    }

    with mock.patch.object(
        plannd_mod.urllib.request, "urlopen", return_value=_fake_response(fake_payload)
    ), mock.patch("utils.logger.warning") as mock_warning:
        result = get_plan("do the thing")

    assert result is not None
    assert not mock_warning.called


def test_get_plan_exception_path_routes_through_logger_not_print():
    """NEW-165: the bare `print(...)` on the except path never reached the
    daemon log — this is why NEW-165 read as 'silent' even though
    something was technically printed. Confirm it now goes through
    utils.logger.warning() instead."""
    with mock.patch.object(
        plannd_mod.urllib.request, "urlopen", side_effect=OSError("timed out")
    ), mock.patch("utils.logger.warning") as mock_warning, mock.patch(
        "builtins.print"
    ) as mock_print:
        result = get_plan("do the thing")

    assert result is None
    assert mock_warning.called
    assert "get_plan error" in mock_warning.call_args[0][0]
    mock_print.assert_not_called()
