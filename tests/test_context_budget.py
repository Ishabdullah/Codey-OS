"""
Tests for the §8 Q11 / NEW-206 context-budget admission fix in
core/resource_gate.py — the (c) primary-defense admission check
(`reserve_context_budget()`) plus the (b) serialization-queue backstop
(`wait_and_reserve_context_budget()`) Ish confirmed together as the fix
direction for NEW-206 (the real shared llama-server failing every
in-flight request hard when concurrent requests oversubscribe its
kv_unified=true shared KV pool).

All tests use synthetic slot-store state, an injected `fetch_slots_fn`
(never a real HTTP call to a live server), and an injected `tokenize_fn`
(never a real `/tokenize` HTTP call) — matching this project's own
established mocking convention (tests/test_resource_gate.py's module
docstring, tests/test_loader_resource_gate.py's `monkeypatch.setattr`
pattern). No test spawns a subprocess model server or depends on this
device's real live state.
"""

import time


import core.resource_gate as rg

GIB = 1024**3


def _seed_resident_slot(tmp_path, model_id="primary", port=8080, n_ctx=8192, pid=None):
    """Register a RESIDENT slot with a known n_ctx so
    resolve_effective_n_ctx() can find it — mirrors what
    core/loader_v2.py's real spawn path does via reserve_slot()/
    register_slot()."""
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


# ── resolve_effective_n_ctx() ────────────────────────────────────────────────


def test_resolve_effective_n_ctx_from_resident_slot(tmp_path):
    _seed_resident_slot(tmp_path, n_ctx=8192)
    assert rg.resolve_effective_n_ctx("primary", 8080, state_dir=tmp_path) == 8192


def test_resolve_effective_n_ctx_none_when_nothing_registered(tmp_path):
    # No slot registered and no real /proc/net/tcp occupant on this test
    # host for port 8080 (or, on a real device, this device's own
    # documented /proc/net/tcp PermissionError, NEW-200) — either way,
    # resolves to None, not a guessed config default.
    assert rg.resolve_effective_n_ctx("primary", 8080, state_dir=tmp_path) is None


def test_resolve_effective_n_ctx_ignores_slot_with_no_n_ctx_field(tmp_path):
    import os as _os

    rg.register_slot(
        model_id="primary",
        cost_bytes=int(1 * GIB),
        pid=_os.getpid(),
        port=8080,
        status=rg.SLOT_STATUS_RESIDENT,
        state_dir=tmp_path,
        # n_ctx omitted -> None, matching a legacy pre-NEW-149 slot record
    )
    assert rg.resolve_effective_n_ctx("primary", 8080, state_dir=tmp_path) is None


# ── estimate_prompt_tokens() ──────────────────────────────────────────────────


def test_estimate_prompt_tokens_prefers_tokenize_endpoint():
    messages = [{"role": "user", "content": "hello world"}]
    tokens, source = rg.estimate_prompt_tokens(
        "127.0.0.1", 8080, messages, tokenize_fn=lambda text: 42
    )
    assert (tokens, source) == (42, "tokenize")


def test_estimate_prompt_tokens_falls_back_to_padded_heuristic_when_tokenize_fails():
    messages = [{"role": "user", "content": "x" * 400}]  # ~100 tokens at len//4
    tokens, source = rg.estimate_prompt_tokens(
        "127.0.0.1", 8080, messages, tokenize_fn=lambda text: None
    )
    assert source == "heuristic"
    # estimate_messages_tokens() heuristic: 400//4 + 1*4 = 104, padded by
    # CONTEXT_HEURISTIC_FALLBACK_PADDING_FACTOR (1.35) -> 140.
    from core.tokens import estimate_messages_tokens

    raw = estimate_messages_tokens(messages)
    assert tokens == int(raw * rg.CONTEXT_HEURISTIC_FALLBACK_PADDING_FACTOR)
    assert tokens > raw  # the padding must widen the estimate, never shrink it


# ── compute_context_queue_timeout_seconds() ──────────────────────────────────


def test_compute_context_queue_timeout_is_formula_based_not_flat():
    small = rg.compute_context_queue_timeout_seconds(n_ctx=2048, max_tokens=256)
    large = rg.compute_context_queue_timeout_seconds(n_ctx=16384, max_tokens=2048)
    assert small < large  # must actually scale with n_ctx/max_tokens


def test_compute_context_queue_timeout_capped_at_production_n_ctx():
    # Production's real n_ctx=65536 would give ~110 minutes uncapped —
    # must be capped, not returned raw (see CONTEXT_QUEUE_TIMEOUT_CAP_SECONDS's
    # own comment for why an uncapped value would blow through both real
    # call sites' enclosing timeouts).
    timeout = rg.compute_context_queue_timeout_seconds(n_ctx=65536, max_tokens=2048)
    assert timeout == rg.CONTEXT_QUEUE_TIMEOUT_CAP_SECONDS


# ── reserve_context_budget() ─────────────────────────────────────────────────


def _messages(n_chars=40):
    return [{"role": "user", "content": "a" * n_chars}]


def test_reserve_context_budget_refuses_when_n_ctx_unresolvable(tmp_path):
    decision = rg.reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=256,
        state_dir=tmp_path,
        fetch_slots_fn=lambda: 0,
        tokenize_fn=lambda t: 10,
    )
    assert decision.admitted is False
    assert decision.reservation_id is None
    assert decision.effective_n_ctx is None
    assert decision.estimate_source == "none"
    assert "n_ctx" in decision.reason


def test_reserve_context_budget_admits_and_registers_when_room(tmp_path):
    _seed_resident_slot(tmp_path, n_ctx=8192)
    decision = rg.reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=256,
        state_dir=tmp_path,
        fetch_slots_fn=lambda: 0,
        tokenize_fn=lambda t: 100,
    )
    assert decision.admitted is True
    assert decision.reservation_id is not None
    assert decision.reserved_tokens == 100 + 256
    assert decision.effective_n_ctx == 8192
    assert decision.ceiling_tokens == int(8192 * (1 - rg.CONTEXT_BUDGET_SAFETY_MARGIN_FRACTION))
    assert decision.estimate_source == "tokenize"


def test_reserve_context_budget_refuses_when_slots_signal_alone_exceeds_margin(tmp_path):
    _seed_resident_slot(tmp_path, n_ctx=8192)
    # ceiling = 8192 * 0.85 = 6963.2 -> int 6963. A live /slots occupant
    # already claiming 7000 tokens must refuse any further admission,
    # regardless of how small the new request's own estimate is.
    decision = rg.reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=10,
        state_dir=tmp_path,
        fetch_slots_fn=lambda: 7000,
        tokenize_fn=lambda t: 5,
    )
    assert decision.admitted is False
    assert decision.slots_occupied_tokens == 7000
    assert "exceed" in decision.reason


def test_reserve_context_budget_second_call_sees_first_reservation(tmp_path):
    # This is reserve_slot()'s own TOCTOU-closing guarantee, replayed for
    # the context-budget ledger: a second call must see the first call's
    # still-live reservation via the store itself, not require the caller
    # to separately track/pass it.
    _seed_resident_slot(tmp_path, n_ctx=8192)
    # ceiling = 6963. First reservation: 3500 tokens -> admitted (3500 <= 6963).
    first = rg.reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=0,
        state_dir=tmp_path,
        fetch_slots_fn=lambda: 0,
        tokenize_fn=lambda t: 3500,
    )
    assert first.admitted is True

    # Second reservation: another 3500 tokens. Combined with the first
    # still-live reservation (3500) that's 7000 > 6963 -> refused.
    second = rg.reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=0,
        state_dir=tmp_path,
        fetch_slots_fn=lambda: 0,
        tokenize_fn=lambda t: 3500,
    )
    assert second.admitted is False
    assert second.other_reserved_tokens == 3500


def test_reserve_context_budget_fails_closed_when_slots_unreachable(tmp_path):
    # NEW-431: /slots unreachable must fail CLOSED (refuse, no lease
    # acquired) — the old behavior (degrade slots_tokens to 0 and admit
    # anyway) reopened NEW-206's own over-admission window, since the
    # local reservation ledger alone cannot see occupancy from requests
    # that bypassed it.
    _seed_resident_slot(tmp_path, n_ctx=8192)

    def _raise_slots():
        raise ConnectionError("simulated /slots failure")

    decision = rg.reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=0,
        state_dir=tmp_path,
        fetch_slots_fn=_raise_slots,
        tokenize_fn=lambda t: 100,
    )
    assert decision.admitted is False
    assert decision.reservation_id is None
    assert decision.effective_n_ctx == 8192  # real n_ctx, NOT None (NEW-431)
    assert "NEW-431" in decision.reason
    assert "/slots" in decision.reason


def test_reserve_context_budget_reaps_expired_reservation(tmp_path):
    _seed_resident_slot(tmp_path, n_ctx=8192)
    # Seed a stale reservation directly in the context-budget store, older
    # than CONTEXT_RESERVATION_MAX_AGE_SECONDS, under a still-alive PID (so
    # only the age-based reap, not the pid-liveness reap, is what drops it).
    import os as _os

    with rg._LockedState(
        tmp_path,
        state_filename=rg._CONTEXT_STATE_FILENAME,
        lock_filename=rg._CONTEXT_LOCK_FILENAME,
    ) as records:
        records.append(
            {
                "reservation_id": "stale",
                "port": 8080,
                "pid": _os.getpid(),
                "reserved_tokens": 5000,
                "prompt_tokens": 5000,
                "max_tokens": 0,
                "estimate_source": "heuristic",
                "created_at": time.time() - rg.CONTEXT_RESERVATION_MAX_AGE_SECONDS - 60,
            }
        )

    # Without reaping, 5000 (stale) + 3000 (this request) = 8000 > 6963
    # ceiling -> would refuse. With reaping, the stale entry is dropped
    # first and this request is admitted.
    decision = rg.reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=0,
        state_dir=tmp_path,
        fetch_slots_fn=lambda: 0,
        tokenize_fn=lambda t: 3000,
    )
    assert decision.admitted is True
    assert decision.other_reserved_tokens == 0


# ── release_context_budget() ─────────────────────────────────────────────────


def test_release_context_budget_removes_reservation(tmp_path):
    _seed_resident_slot(tmp_path, n_ctx=8192)
    decision = rg.reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=0,
        state_dir=tmp_path,
        fetch_slots_fn=lambda: 0,
        tokenize_fn=lambda t: 100,
    )
    assert rg.release_context_budget(decision.reservation_id, state_dir=tmp_path) is True

    # A second, otherwise-identical request that would have been refused
    # by the first's still-live reservation must now be admitted.
    second = rg.reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=0,
        state_dir=tmp_path,
        fetch_slots_fn=lambda: 0,
        tokenize_fn=lambda t: 100,
    )
    assert second.other_reserved_tokens == 0
    assert second.admitted is True


def test_release_context_budget_unknown_id_returns_false(tmp_path):
    assert rg.release_context_budget("does-not-exist", state_dir=tmp_path) is False


# ── wait_and_reserve_context_budget() ────────────────────────────────────────


def test_wait_and_reserve_admits_immediately_when_room_no_sleep_called(tmp_path):
    _seed_resident_slot(tmp_path, n_ctx=8192)
    sleep_calls = []
    decision = rg.wait_and_reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=0,
        state_dir=tmp_path,
        fetch_slots_fn=lambda: 0,
        tokenize_fn=lambda t: 100,
        sleep_fn=sleep_calls.append,
    )
    assert decision.admitted is True
    assert sleep_calls == []  # fast path never sleeps


def test_wait_and_reserve_retries_until_occupant_releases(tmp_path):
    _seed_resident_slot(tmp_path, n_ctx=8192)
    # Occupant reservation blocks a fresh 3000-token request (ceiling 6963,
    # occupant reserves 5000 -> 5000+3000=8000 > 6963). Release it after the
    # second sleep tick to prove the retry loop actually re-checks and
    # succeeds without waiting for the real timeout.
    occupant = rg.reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=0,
        state_dir=tmp_path,
        fetch_slots_fn=lambda: 0,
        tokenize_fn=lambda t: 5000,
    )
    assert occupant.admitted is True

    sleep_calls = []

    def _sleep(seconds):
        sleep_calls.append(seconds)
        if len(sleep_calls) == 2:
            rg.release_context_budget(occupant.reservation_id, state_dir=tmp_path)

    decision = rg.wait_and_reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=0,
        state_dir=tmp_path,
        fetch_slots_fn=lambda: 0,
        tokenize_fn=lambda t: 3000,
        sleep_fn=_sleep,
        timeout_seconds=30.0,
    )
    assert decision.admitted is True
    assert decision.timed_out is False
    assert len(sleep_calls) == 2


def test_wait_and_reserve_times_out_and_reports_timed_out_flag(tmp_path):
    _seed_resident_slot(tmp_path, n_ctx=8192)
    # Occupant never releases -> every retry refuses -> must time out
    # cleanly (not hang, not raise) once the injected fake clock crosses
    # the deadline.
    occupant = rg.reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=0,
        state_dir=tmp_path,
        fetch_slots_fn=lambda: 0,
        tokenize_fn=lambda t: 5000,
    )
    assert occupant.admitted is True

    fake_now = [time.time()]
    import unittest.mock as _mock

    def _sleep(seconds):
        fake_now[0] += seconds

    with _mock.patch("time.time", side_effect=lambda: fake_now[0]):
        decision = rg.wait_and_reserve_context_budget(
            port=8080,
            messages=_messages(),
            max_tokens=0,
            state_dir=tmp_path,
            fetch_slots_fn=lambda: 0,
            tokenize_fn=lambda t: 3000,
            sleep_fn=_sleep,
            timeout_seconds=5.0,
            poll_interval_seconds=2.0,
        )
    assert decision.admitted is False
    assert decision.timed_out is True
    assert decision.reservation_id is None
    assert "timed out" in decision.reason


def test_wait_and_reserve_returns_immediately_when_n_ctx_unresolvable(tmp_path):
    # No slot registered -> n_ctx unresolvable -> must not enter a retry
    # loop that can never succeed; returns the first refusal immediately.
    sleep_calls = []
    decision = rg.wait_and_reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=0,
        state_dir=tmp_path,
        fetch_slots_fn=lambda: 0,
        tokenize_fn=lambda t: 100,
        sleep_fn=sleep_calls.append,
    )
    assert decision.admitted is False
    assert decision.timed_out is False  # not a queue timeout — never retried
    assert sleep_calls == []
