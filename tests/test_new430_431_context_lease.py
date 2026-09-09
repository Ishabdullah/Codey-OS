"""
NEW-430 / NEW-431 fix coverage — both bugs found live-verifying NEW-206's
own context-budget admission gate (core/resource_gate.py,
core/resource_bus.py).

NEW-430: `reserve_context_budget()`'s `acquire_context_lease()` call site
was silently inheriting `resource_bus.py`'s `DEFAULT_LEASE_DURATION_SEC`
(60.0s) instead of the module's own `CONTEXT_RESERVATION_MAX_AGE_SECONDS`
(1800.0s) — a real request running longer than 60s would have its own
still-in-flight reservation reaped out from under it. Also: both real
call sites (`core/inference_hybrid.py`, `core/plannd.py`) release on every
exit path already (correct, unchanged) but stayed silent when
`release_context_budget()` returned `False` — now warned, since with the
TTL now 1800s a `False` here is the load-bearing signal a phantom
long-lived reservation existed.

NEW-431: an unreachable `/slots` endpoint used to make `slots_tokens`
degrade to 0 and proceed as if occupancy were genuinely empty (fail
OPEN) — now `_fetch_slots_prompt_tokens()` retries once, and
`reserve_context_budget()` fails CLOSED (refuses, never calls
`acquire_context_lease()`) if both attempts fail, while still setting
`effective_n_ctx` to the real resolved value (not `None`) so
`wait_and_reserve_context_budget()`'s retry loop treats this as a
retryable degrade, not an immediate hard failure.

All tests use synthetic slot-store state, an injected `fetch_slots_fn` /
`tokenize_fn`, and mocked `urllib.request.urlopen` — matching this
project's established mocking convention (see
tests/test_context_budget.py's own module docstring). No test spawns a
subprocess model server, sleeps real seconds, or depends on this device's
real live state.
"""

import json
import time
import unittest.mock as mock
from io import BytesIO

import core.inference_hybrid as inference_hybrid_mod
import core.plannd as plannd_mod
import core.resource_bus as rb
import core.resource_gate as rg
from core.inference_hybrid import ChatCompletionBackend
from core.plannd import get_plan

GIB = 1024**3


def _seed_resident_slot(tmp_path, model_id="primary", port=8080, n_ctx=8192, pid=None):
    """Mirrors tests/test_context_budget.py's own helper: registers a
    RESIDENT slot with a known n_ctx so resolve_effective_n_ctx() can find
    it, matching what core/loader_v2.py's real spawn path does."""
    import os as _os

    rg.register_slot(
        model_id=model_id,
        cost_bytes=int(1 * GIB),
        pid=pid if pid is not None else _os.getpid(),
        port=port,
        status=rg.SLOT_STATUS_RESIDENT,
        state_dir=tmp_path,
        n_ctx=n_ctx,
    )


def _messages(n_chars=40):
    return [{"role": "user", "content": "a" * n_chars}]


def _fake_json_response(payload):
    """Context-manager-compatible fake matching urllib's response object,
    for both /slots (list payload) and chat-completion (dict payload)
    responses."""
    body = json.dumps(payload).encode("utf-8")
    cm = mock.MagicMock()
    cm.__enter__.return_value = BytesIO(body)
    cm.__exit__.return_value = False
    return cm


# ── NEW-430: lease duration ──────────────────────────────────────────────


def test_reserve_context_budget_uses_context_reservation_max_age_lease_duration(tmp_path):
    _seed_resident_slot(tmp_path, n_ctx=8192)
    fixed_now = 1_700_000_000.0
    with mock.patch("time.time", return_value=fixed_now):
        decision = rg.reserve_context_budget(
            port=8080,
            messages=_messages(),
            max_tokens=0,
            state_dir=tmp_path,
            fetch_slots_fn=lambda: 0,
            tokenize_fn=lambda t: 100,
        )
    assert decision.admitted is True

    with rb._locked_db(tmp_path) as conn:
        row = conn.execute(
            "SELECT granted_at, expires_at FROM resource_leases WHERE lease_id = ?",
            (decision.reservation_id,),
        ).fetchone()
    assert row is not None
    assert row["expires_at"] - row["granted_at"] == rg.CONTEXT_RESERVATION_MAX_AGE_SECONDS
    assert row["expires_at"] - row["granted_at"] != rb.DEFAULT_LEASE_DURATION_SEC


def test_context_lease_not_reaped_at_61s_regression(tmp_path):
    """Regression test: under the OLD code (acquire_context_lease() called
    with no explicit lease_duration, silently inheriting
    DEFAULT_LEASE_DURATION_SEC=60.0), this lease would already be expired
    and reaped by t0+61s. Under the fix (lease_duration=
    CONTEXT_RESERVATION_MAX_AGE_SECONDS=1800.0 passed explicitly), it must
    still be ACQUIRED at t0+61s."""
    _seed_resident_slot(tmp_path, n_ctx=8192)
    t0 = 1_700_000_000.0
    with mock.patch("time.time", return_value=t0):
        decision = rg.reserve_context_budget(
            port=8080,
            messages=_messages(),
            max_tokens=0,
            state_dir=tmp_path,
            fetch_slots_fn=lambda: 0,
            tokenize_fn=lambda t: 100,
        )
    assert decision.admitted is True

    with mock.patch("time.time", return_value=t0 + 61.0):
        reaped = rb.reap_stale_records(state_dir=tmp_path)
    assert reaped == 0

    with rb._locked_db(tmp_path) as conn:
        row = conn.execute(
            "SELECT status FROM resource_leases WHERE lease_id = ?",
            (decision.reservation_id,),
        ).fetchone()
    assert row["status"] == rb.ReservationStatus.ACQUIRED.value


# ── NEW-430: silent-release-failure warning ──────────────────────────────


def _admitted_decision(reservation_id="test-reservation"):
    return rg.ContextBudgetDecision(
        admitted=True,
        reservation_id=reservation_id,
        reserved_tokens=100,
        effective_n_ctx=8192,
        ceiling_tokens=6963,
        slots_occupied_tokens=0,
        other_reserved_tokens=0,
        estimate_source="tokenize",
        reason="admitted",
    )


def test_inference_hybrid_warns_when_release_context_budget_returns_false():
    backend = ChatCompletionBackend()
    payload = {
        "choices": [{"message": {"content": "1. step one"}}],
        "usage": {"completion_tokens": 3},
        "timings": {"predicted_n": 3, "predicted_ms": 100},
    }
    with mock.patch(
        "core.resource_gate.wait_and_reserve_context_budget",
        return_value=_admitted_decision("rid-gone"),
    ), mock.patch(
        "core.resource_gate.release_context_budget", return_value=False
    ), mock.patch.object(
        inference_hybrid_mod.urllib.request,
        "urlopen",
        return_value=_fake_json_response(payload),
    ), mock.patch(
        "core.inference_hybrid.warning"
    ) as mock_warning:
        result = backend.infer([{"role": "user", "content": "hi"}], max_tokens=64)

    assert result is not None
    assert mock_warning.called
    assert any(
        "rid-gone" in str(call.args[0]) and "NEW-430" in str(call.args[0])
        for call in mock_warning.call_args_list
    )


def test_plannd_get_plan_warns_when_release_context_budget_returns_false():
    fake_payload = {
        "choices": [{"finish_reason": "stop", "message": {"content": "1. Do the thing"}}],
    }
    with mock.patch(
        "core.resource_gate.wait_and_reserve_context_budget",
        return_value=_admitted_decision("rid-gone-2"),
    ), mock.patch(
        "core.resource_gate.release_context_budget", return_value=False
    ), mock.patch.object(
        plannd_mod.urllib.request, "urlopen", return_value=_fake_json_response(fake_payload)
    ), mock.patch(
        "utils.logger.warning"
    ) as mock_warning:
        result = get_plan("do the thing")

    assert result is not None
    assert mock_warning.called
    assert any(
        "rid-gone-2" in str(call.args[0]) and "NEW-430" in str(call.args[0])
        for call in mock_warning.call_args_list
    )


# ── NEW-431: /slots retry + fail-closed fallback ─────────────────────────


def test_fetch_slots_prompt_tokens_fails_twice_returns_none(tmp_path):
    with mock.patch.object(
        rg.urllib.request, "urlopen", side_effect=ConnectionError("simulated /slots failure")
    ):
        sleeps = []
        result = rg._fetch_slots_prompt_tokens("127.0.0.1", 8080, sleep_fn=sleeps.append)
    assert result is None
    # One retry gap between the two attempts, never a sleep after the
    # final (second) attempt.
    assert sleeps == [rg.SLOTS_ENDPOINT_RETRY_GAP_SECONDS]


def test_fetch_slots_prompt_tokens_fails_once_then_succeeds_on_retry():
    call_count = [0]

    def _urlopen(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise ConnectionError("simulated transient /slots failure")
        return _fake_json_response([{"n_prompt_tokens": 4321, "is_processing": True}])

    with mock.patch.object(rg.urllib.request, "urlopen", side_effect=_urlopen):
        sleeps = []
        result = rg._fetch_slots_prompt_tokens("127.0.0.1", 8080, sleep_fn=sleeps.append)
    assert result == 4321
    assert call_count[0] == 2
    assert sleeps == [rg.SLOTS_ENDPOINT_RETRY_GAP_SECONDS]


def test_reserve_context_budget_fails_closed_without_calling_acquire_context_lease(tmp_path):
    _seed_resident_slot(tmp_path, n_ctx=8192)
    with mock.patch("core.resource_bus.acquire_context_lease") as mock_acquire:
        decision = rg.reserve_context_budget(
            port=8080,
            messages=_messages(),
            max_tokens=0,
            state_dir=tmp_path,
            # Simulates _fetch_slots_prompt_tokens() having already
            # exhausted both retries and given up (returns None).
            fetch_slots_fn=lambda: None,
            tokenize_fn=lambda t: 100,
        )
    mock_acquire.assert_not_called()
    assert decision.admitted is False
    assert decision.reservation_id is None
    # Real resolved n_ctx, NOT None -- setting it to None would trip
    # wait_and_reserve_context_budget()'s early-return-on-None-means-
    # hard-fail check and turn a transient blip into an immediate hard
    # failure instead of a bounded wait/retry.
    assert decision.effective_n_ctx == 8192
    assert "NEW-431" in decision.reason
    assert "/slots" in decision.reason


def test_wait_and_reserve_retries_through_degraded_slots_ticks_then_admits(tmp_path):
    """Critical test for the effective_n_ctx=None early-exit trap: with the
    /slots fetch degraded (returning None) on the first two ticks, the
    retry loop must NOT bail out early with admitted=False (which it would
    if effective_n_ctx had been set to None on the degraded refusal) — it
    must keep retrying and admit once the injected fetch starts
    succeeding."""
    _seed_resident_slot(tmp_path, n_ctx=8192)
    remaining = [None, None, 0]

    def _fetch():
        return remaining.pop(0)

    sleep_calls = []
    decision = rg.wait_and_reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=0,
        state_dir=tmp_path,
        fetch_slots_fn=_fetch,
        tokenize_fn=lambda t: 100,
        sleep_fn=sleep_calls.append,
        timeout_seconds=30.0,
    )
    assert decision.admitted is True
    assert decision.timed_out is False
    # Two degraded refusals before the third (successful) tick admits.
    assert len(sleep_calls) == 2
    assert remaining == []
