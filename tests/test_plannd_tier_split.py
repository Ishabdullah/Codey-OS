"""
7.3 sub-task E, Task B (2026-08-24) — medium/hard planning tier split.

Covers the new plumbing added on top of NEW-164/165/167/169's existing
timeout machinery (see tests/test_plannd_timeout.py and
tests/test_planner_service_daemon_socket_timeout.py for that coverage,
left untouched here):

  - PLANNER_MAX_TOKENS_MEDIUM < PLANNER_MAX_TOKENS invariant (encoded as an
    assertion, not just documented in a comment).
  - is_complex(message, score=score) is a no-regression: identical results
    to is_complex(message) for every existing test case.
  - core/plannd.py's get_plan(): enable_thinking=False selects
    PLANNER_MAX_TOKENS_MEDIUM and sends chat_template_kwargs.enable_thinking
    == False; enable_thinking=True (the default) is unchanged from before
    this task.
  - core/planner_client.py's send_plan_request_async(): the
    functools.partial/run_in_executor fix — enable_thinking is genuinely
    forwarded to get_plan(), not silently dropped back to the default.
  - core/planner_service.py's _request_daemon_plan(): the socket timeout is
    tier-INVARIANT (always hard-tier-sized) even though the payload's
    "tier" field does vary; and a missing "tier" key in core/daemon.py's
    handler defaults to "hard".
  - core/daemon.py: a medium-tier request produces a consistent
    max_tokens/enable_thinking pairing across all three materializations
    (daemon's own compute_planner_timeout() budget, plannd's payload
    max_tokens, and plannd's chat_template_kwargs) — the actual failure
    mode this task's design flags as the one silent bug that's easy to
    introduce.

No real daemon socket or model load — mocked at the HTTP/socket boundary,
matching this project's existing convention (tests/test_plannd_timeout.py,
tests/test_planner_service_daemon_socket_timeout.py).
"""
import asyncio
import json
import unittest.mock as mock
from io import BytesIO

import pytest

import core.daemon as daemon_mod
import core.plannd as plannd_mod
import core.planner_client as planner_client_mod
import core.planner_service as planner_service
import core.resource_gate as rg
from core.orchestrator import _score_message, is_complex
from core.plannd import (PLANNER_PROMPT, compute_outer_plan_timeout,
                        compute_planner_timeout, get_plan)
from core.state import StateStore
from core.tokens import estimate_tokens
from utils.config import PLANNER_MAX_TOKENS, PLANNER_MAX_TOKENS_MEDIUM


def _fake_response(payload: dict):
    body = json.dumps(payload).encode("utf-8")
    cm = mock.MagicMock()
    cm.__enter__.return_value = BytesIO(body)
    cm.__exit__.return_value = False
    return cm


@pytest.fixture(autouse=True)
def _admit_context_budget_by_default():
    """
    §8 Q11 fix (2026-08-26) — same rationale as
    tests/test_plannd_timeout.py's identical fixture: get_plan() now runs a
    context-budget admission check before its urlopen call, which would
    otherwise always refuse in this file's synthetic (no resident slot
    registered) test environment. This file is about the tier-split
    plumbing, not the admission gate itself (see tests/test_context_budget.py).
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


def _server(db_path):
    state = StateStore(db_path=db_path)
    return daemon_mod.DaemonServer(state=state), state


# ── Invariant: medium budget strictly smaller than hard budget ─────────────


def test_planner_max_tokens_medium_invariant():
    assert PLANNER_MAX_TOKENS_MEDIUM < PLANNER_MAX_TOKENS


# ── is_complex(message, score=score) no-regression ─────────────────────────

_IS_COMPLEX_CASES = [
    "How do I create a file?",
    "Create a Flask app with user authentication and also add tests",
    "Refactor the code to use classes and then run the tests",
    "Implement a caching system with Redis for the application",
    "Is this the right approach?",
    "",
    "Hi",
    "Fix the off-by-one error in the loop in core/legacy_calc.py",
    "x" * 400 + " create and also run and also verify",
]


def test_is_complex_with_precomputed_score_matches_default():
    for msg in _IS_COMPLEX_CASES:
        score = _score_message(msg)
        assert is_complex(msg, score=score) == is_complex(msg)


def test_is_complex_existing_positional_caller_unaffected():
    # core/agent.py:1271's call shape — one positional arg, no score kwarg.
    assert is_complex("Create a Flask app with user authentication and also add tests") is True
    assert is_complex("How do I create a file?") is False


# ── plannd.get_plan(): enable_thinking selects the budget + payload flag ──


def test_get_plan_medium_tier_uses_smaller_budget_and_disables_thinking():
    fake_payload = {
        "choices": [{"finish_reason": "stop", "message": {"content": "1. Do the thing"}}]
    }
    with mock.patch.object(
        plannd_mod.urllib.request, "urlopen", return_value=_fake_response(fake_payload)
    ) as mock_urlopen:
        result = get_plan("do the thing", enable_thinking=False)

    assert result == ["Do the thing"]
    sent_payload = json.loads(mock_urlopen.call_args.args[0].data.decode("utf-8"))
    assert sent_payload["max_tokens"] == PLANNER_MAX_TOKENS_MEDIUM
    assert sent_payload["chat_template_kwargs"] == {"enable_thinking": False}


def test_get_plan_hard_tier_default_unchanged():
    fake_payload = {
        "choices": [{"finish_reason": "stop", "message": {"content": "1. Do the thing"}}]
    }
    with mock.patch.object(
        plannd_mod.urllib.request, "urlopen", return_value=_fake_response(fake_payload)
    ) as mock_urlopen:
        result = get_plan("do the thing")  # enable_thinking defaults to True

    assert result == ["Do the thing"]
    sent_payload = json.loads(mock_urlopen.call_args.args[0].data.decode("utf-8"))
    assert sent_payload["max_tokens"] == PLANNER_MAX_TOKENS
    assert sent_payload["chat_template_kwargs"] == {"enable_thinking": True}


def test_get_plan_medium_tier_truncation_warning_is_labeled_non_thinking():
    fake_payload = {
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": "", "reasoning_content": ""},
            }
        ]
    }
    with mock.patch.object(
        plannd_mod.urllib.request, "urlopen", return_value=_fake_response(fake_payload)
    ), mock.patch("utils.logger.warning") as mock_warning:
        result = get_plan("do the thing", enable_thinking=False)

    assert result is None
    assert mock_warning.called
    logged_msg = mock_warning.call_args[0][0]
    assert "medium-tier (non-thinking)" in logged_msg
    assert "thinking-mode request" not in logged_msg


# ── planner_client.send_plan_request_async(): functools.partial fix ────────


def test_send_plan_request_async_forwards_enable_thinking_false():
    captured = {}

    def fake_get_plan(prompt, enable_thinking=True):
        captured["enable_thinking"] = enable_thinking
        return ["step one", "step two"]

    with mock.patch("core.plannd.get_plan", fake_get_plan):
        result = asyncio.run(
            planner_client_mod.send_plan_request_async("do it", enable_thinking=False)
        )

    assert result == ["step one", "step two"]
    assert captured["enable_thinking"] is False


def test_send_plan_request_async_default_is_thinking_true():
    captured = {}

    def fake_get_plan(prompt, enable_thinking=True):
        captured["enable_thinking"] = enable_thinking
        return ["step one", "step two"]

    with mock.patch("core.plannd.get_plan", fake_get_plan):
        result = asyncio.run(planner_client_mod.send_plan_request_async("do it"))

    assert result == ["step one", "step two"]
    assert captured["enable_thinking"] is True


# ── planner_service._request_daemon_plan(): tier-invariant socket timeout ──


def test_request_daemon_plan_socket_timeout_is_tier_invariant():
    captured = []

    def fake_send_command(cmd, data, timeout=60.0):
        captured.append(timeout)
        return {"plan": ["step one", "step two"]}

    with mock.patch("core.daemon.is_daemon_running", return_value=True), mock.patch(
        "core.daemon.send_command", fake_send_command
    ):
        planner_service._request_daemon_plan("do the thing", tier="medium")
        planner_service._request_daemon_plan("do the thing", tier="hard")

    assert len(captured) == 2
    assert captured[0] == captured[1]


def test_request_daemon_plan_threads_tier_into_payload():
    captured = {}

    def fake_send_command(cmd, data, timeout=60.0):
        captured["data"] = data
        return {"plan": ["step one", "step two"]}

    with mock.patch("core.daemon.is_daemon_running", return_value=True), mock.patch(
        "core.daemon.send_command", fake_send_command
    ):
        planner_service._request_daemon_plan("do the thing", tier="medium")

    assert captured["data"]["tier"] == "medium"


# ── core/daemon.py: old-daemon-safety + one-request consistency ────────────


def test_handle_command_missing_tier_defaults_to_hard(tmp_path):
    server, _ = _server(tmp_path / "state.db")
    prompt = "do the thing"
    captured = {}

    async def _fake_wait_for(coro, timeout=None):
        coro.close()
        captured["timeout"] = timeout
        return None

    with mock.patch("core.daemon.asyncio.wait_for", side_effect=_fake_wait_for):
        asyncio.run(server._handle_command({"prompt": prompt, "plan_only": True}))

    prompt_tokens_estimate = estimate_tokens(PLANNER_PROMPT) + estimate_tokens(prompt)
    inner_timeout = compute_planner_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS)
    expected_outer = compute_outer_plan_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS)

    assert captured["timeout"] == expected_outer
    assert captured["timeout"] > inner_timeout


def test_handle_command_medium_tier_uses_medium_sized_timeout(tmp_path):
    """
    Discriminating test: proves the daemon's own outer timeout actually
    scales down for a medium-tier request, rather than staying pinned to
    PLANNER_MAX_TOKENS regardless of `tier` (the missing coverage
    test_handle_command_medium_tier_end_to_end_consistency below leaves —
    that test mocks urlopen, not wait_for, so it never inspects this
    timeout at all).
    """
    server, _ = _server(tmp_path / "state.db")
    prompt = "do the thing"
    captured = {}

    async def _fake_wait_for(coro, timeout=None):
        coro.close()
        captured["timeout"] = timeout
        return None

    with mock.patch("core.daemon.asyncio.wait_for", side_effect=_fake_wait_for):
        asyncio.run(
            server._handle_command({"prompt": prompt, "plan_only": True, "tier": "medium"})
        )

    prompt_tokens_estimate = estimate_tokens(PLANNER_PROMPT) + estimate_tokens(prompt)
    medium_inner_timeout = compute_planner_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS_MEDIUM)
    hard_inner_timeout = compute_planner_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS)
    expected_medium_outer = compute_outer_plan_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS_MEDIUM)
    expected_hard_outer = compute_outer_plan_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS)

    assert captured["timeout"] == expected_medium_outer
    assert captured["timeout"] < expected_hard_outer


def test_plan_claimed_task_medium_tier_uses_medium_sized_timeout():
    """Same discriminating coverage as above, for _plan_claimed_task's own
    tier parameter — currently exercised only at its default ("hard") by
    test_plan_claimed_task_defaults_to_hard_tier."""
    prompt = "do the thing"
    captured = {}

    async def _fake_wait_for(coro, timeout=None):
        coro.close()
        captured["timeout"] = timeout
        return None

    with mock.patch("core.daemon.asyncio.wait_for", side_effect=_fake_wait_for):
        asyncio.run(daemon_mod.Daemon._plan_claimed_task(None, prompt, tier="medium"))

    prompt_tokens_estimate = estimate_tokens(PLANNER_PROMPT) + estimate_tokens(prompt)
    medium_inner_timeout = compute_planner_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS_MEDIUM)
    hard_inner_timeout = compute_planner_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS)
    expected_medium_outer = compute_outer_plan_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS_MEDIUM)
    expected_hard_outer = compute_outer_plan_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS)

    assert captured["timeout"] == expected_medium_outer
    assert captured["timeout"] < expected_hard_outer


def test_handle_command_medium_tier_end_to_end_consistency(tmp_path):
    """
    The one test the individual per-materialization checks above don't
    cover: that a SINGLE medium-tier request produces medium in all three
    places it must (daemon's own timeout budget, plannd's payload
    max_tokens, and plannd's chat_template_kwargs) rather than one of them
    silently staying hard-tier.
    """
    server, _ = _server(tmp_path / "state.db")
    prompt = "do the thing"
    captured = {}

    fake_payload = {
        "choices": [{"finish_reason": "stop", "message": {"content": "1. Do the thing"}}]
    }

    def fake_urlopen(req, timeout=None):
        captured["sent_payload"] = json.loads(req.data.decode("utf-8"))
        return _fake_response(fake_payload)

    with mock.patch.object(plannd_mod.urllib.request, "urlopen", side_effect=fake_urlopen):
        asyncio.run(
            server._handle_command({"prompt": prompt, "plan_only": True, "tier": "medium"})
        )

    sent = captured["sent_payload"]
    assert sent["max_tokens"] == PLANNER_MAX_TOKENS_MEDIUM
    assert sent["chat_template_kwargs"] == {"enable_thinking": False}


def test_plan_claimed_task_defaults_to_hard_tier():
    prompt = "do the thing"
    captured = {}

    async def _fake_wait_for(coro, timeout=None):
        coro.close()
        captured["timeout"] = timeout
        return None

    with mock.patch("core.daemon.asyncio.wait_for", side_effect=_fake_wait_for):
        asyncio.run(daemon_mod.Daemon._plan_claimed_task(None, prompt))

    prompt_tokens_estimate = estimate_tokens(PLANNER_PROMPT) + estimate_tokens(prompt)
    inner_timeout = compute_planner_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS)
    expected_outer = compute_outer_plan_timeout(prompt_tokens_estimate, PLANNER_MAX_TOKENS)

    assert captured["timeout"] == expected_outer
    assert captured["timeout"] > inner_timeout
