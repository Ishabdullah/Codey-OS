"""
NEW-434 fix coverage — `wait_and_reserve_context_budget()`'s retry loop
used to call `reserve_context_budget()` on every tick, and each call
independently re-invoked `estimate_prompt_tokens()` (a fresh `/tokenize`
HTTP POST) for the same, unchanged `messages` payload. Fixed by computing
the estimate ONCE per wait (`(tokens, source)` pair) and threading it
through every `reserve_context_budget()` call in that wait via the new
`precomputed_estimate` keyword-only parameter — both call sites inside
`wait_and_reserve_context_budget()` (the initial call and the retry
loop's call), matching the exact shape NEW-259 was about (a param
threaded into one call site but silently missed on the other).

All tests use synthetic slot-store state and injected `fetch_slots_fn` /
`tokenize_fn` (never a real HTTP call) — matching this project's own
established mocking convention (tests/test_context_budget.py's module
docstring). No test spawns a subprocess model server or sleeps real
seconds (`sleep_fn=lambda _: None`).
"""

import core.resource_gate as rg
import core.tokens as tokens_mod

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
    return [{"role": "user", "content": "x" * n_chars}]


def _refuse_then_admit_fetch_slots_fn(calls_list, admit_on_call=3):
    """Returns an over-ceiling `/slots` figure (forcing a refusal via
    acquire_context_lease's own combined-demand check) for every call
    before `admit_on_call`, then 0 (plenty of room) from `admit_on_call`
    onward — used to force >=2 retries inside one
    wait_and_reserve_context_budget() call without any real sleeping."""

    def _fetch_slots_fn():
        calls_list.append(1)
        if len(calls_list) < admit_on_call:
            return 7000  # n_ctx=8192, ceiling=6963 -> alone exceeds it
        return 0

    return _fetch_slots_fn


def test_wait_and_reserve_tokenizes_exactly_once_across_retries(tmp_path):
    """Primary regression test (NEW-434): force >=3 total
    reserve_context_budget() invocations inside one wait (1 initial + 2
    retries) via a fetch_slots_fn that refuses the first two calls, and
    assert the tokenize stub is called exactly once — proving the
    memoized estimate, not a fresh /tokenize call, backs every retry.
    Also asserts the final decision.estimate_source matches what that
    single tokenize call produced, proving the memoized (tokens, source)
    PAIR (not just the int) survived to the admission record."""
    _seed_resident_slot(tmp_path, n_ctx=8192)

    slots_calls = []
    fetch_slots_fn = _refuse_then_admit_fetch_slots_fn(slots_calls, admit_on_call=3)

    tokenize_calls = []

    def tokenize_fn(text):
        tokenize_calls.append(text)
        return 100

    decision = rg.wait_and_reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=0,
        state_dir=tmp_path,
        fetch_slots_fn=fetch_slots_fn,
        tokenize_fn=tokenize_fn,
        sleep_fn=lambda _: None,
        timeout_seconds=30.0,
    )

    assert decision.admitted is True
    # 1 initial reserve_context_budget() call + 2 retries = 3 total.
    assert len(slots_calls) == 3
    # The critical NEW-434 assertion: exactly one /tokenize call across
    # all 3 reserve_context_budget() invocations in this one wait -- if
    # either call site (initial or retry-loop) failed to pass
    # precomputed_estimate, this would be 3, not 1.
    assert len(tokenize_calls) == 1
    assert decision.estimate_source == "tokenize"
    assert decision.reserved_tokens == 100  # prompt_tokens(100) + max_tokens(0)


def test_wait_and_reserve_heuristic_pinned_across_retries(tmp_path, monkeypatch):
    """Heuristic-pinning case: tokenize_fn returns None (forcing the
    heuristic fallback) on the one precomputation. Asserts the underlying
    heuristic computation (core.tokens.estimate_messages_tokens) is
    exercised exactly once across the whole wait despite multiple
    retries, and the final decision.estimate_source == "heuristic" even
    after retries."""
    _seed_resident_slot(tmp_path, n_ctx=8192)

    slots_calls = []
    fetch_slots_fn = _refuse_then_admit_fetch_slots_fn(slots_calls, admit_on_call=3)

    heuristic_calls = []
    original_estimate = tokens_mod.estimate_messages_tokens

    def counting_estimate(messages):
        heuristic_calls.append(1)
        return original_estimate(messages)

    monkeypatch.setattr(tokens_mod, "estimate_messages_tokens", counting_estimate)

    decision = rg.wait_and_reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=0,
        state_dir=tmp_path,
        fetch_slots_fn=fetch_slots_fn,
        tokenize_fn=lambda t: None,  # forces heuristic fallback
        sleep_fn=lambda _: None,
        timeout_seconds=30.0,
    )

    assert decision.admitted is True
    assert len(slots_calls) == 3
    # The critical NEW-434 assertion for the heuristic path: exactly one
    # heuristic computation across all 3 reserve_context_budget() calls in
    # this wait.
    assert len(heuristic_calls) == 1
    assert decision.estimate_source == "heuristic"


def test_wait_and_reserve_n_ctx_unresolvable_never_calls_tokenize(tmp_path):
    """No slot registered -> n_ctx unresolvable -> the precompute step
    must not fire at all (matching the pre-existing "refuse immediately"
    path's own estimate_source="none" contract, which never called
    /tokenize either)."""
    tokenize_calls = []

    decision = rg.wait_and_reserve_context_budget(
        port=8080,
        messages=_messages(),
        max_tokens=0,
        state_dir=tmp_path,
        fetch_slots_fn=lambda: 0,
        tokenize_fn=lambda t: tokenize_calls.append(1) or 100,
        sleep_fn=lambda _: None,
    )

    assert decision.admitted is False
    assert decision.estimate_source == "none"
    assert tokenize_calls == []
