"""
T6 (docs/telemetry_layer_design.md §7) — category-A + category-B telemetry
at core/plannd.py::get_plan()'s local-backend HTTP call site and its
`wait_and_reserve_context_budget()` admission wrapper.

Mirrors tests/test_inference_hybrid_context_budget.py's T5 telemetry
coverage pattern exactly: mocks core.resource_gate.wait_and_reserve_
context_budget()/release_context_budget() directly (never a real
llama-server), mocks urllib.request.urlopen, and — because this file
enables TELEMETRY_ENABLED for its own tests — also mocks
core.resource_gate.is_interactive_session_active() so no test touches the
real ~/.codeyOS/tui-sessions/ directory on disk (T5 round 1's blocker,
CLAUDE.md rule 12 "verify, don't repeat a fixed mistake").

Does not duplicate tests/test_plannd_timeout.py's timeout-formula/warning-
log coverage — this file is telemetry-only.
"""
import json
import unittest.mock as mock
from io import BytesIO

import pytest

import core.plannd as plannd_mod
import core.resource_gate as rg
from core.plannd import get_plan
from telemetry import envelope, recorders, schema


def _fake_response(payload: dict):
    body = json.dumps(payload).encode("utf-8")
    cm = mock.MagicMock()
    cm.__enter__.return_value = BytesIO(body)
    cm.__exit__.return_value = False
    return cm


def _admitted_decision(reservation_id="plannd-test-reservation"):
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


def _refused_decision():
    return rg.ContextBudgetDecision(
        admitted=False,
        reservation_id=None,
        reserved_tokens=100,
        effective_n_ctx=8192,
        ceiling_tokens=6963,
        slots_occupied_tokens=7000,
        other_reserved_tokens=0,
        estimate_source="tokenize",
        reason="combined estimated context would exceed the margin ceiling",
    )


@pytest.fixture(autouse=True)
def _capture_telemetry(monkeypatch):
    """Autouse within this file only — see tests/test_inference_hybrid_
    context_budget.py's identical fixture for the full rationale. Forces
    TELEMETRY_ENABLED True (overriding tests/conftest.py's session-wide
    False default) and mocks is_interactive_session_active() so the
    kill-switch-on path never does a real filesystem scan."""
    captured = []

    def fake_record(rec):
        captured.append(rec)

    monkeypatch.setattr(recorders.store, "record", fake_record)
    monkeypatch.setattr(recorders.store, "get_run_id", lambda: "plannd-telemetry-test")
    monkeypatch.setattr(recorders.store, "TELEMETRY_ENABLED", True)
    monkeypatch.setattr(
        "core.resource_gate.is_interactive_session_active", lambda *a, **k: False
    )
    envelope.reset_seq()
    return captured


def _patch_gate_and_urlopen(monkeypatch, payload, reservation_id="plannd-test-reservation"):
    monkeypatch.setattr(
        "core.resource_gate.wait_and_reserve_context_budget",
        lambda *a, **k: _admitted_decision(reservation_id),
    )
    released = []
    monkeypatch.setattr(
        "core.resource_gate.release_context_budget",
        lambda rid, *a, **k: released.append(rid),
    )
    monkeypatch.setattr(
        plannd_mod.urllib.request, "urlopen", lambda *a, **k: _fake_response(payload)
    )
    return released


def test_get_plan_success_path_unchanged_with_telemetry_enabled(monkeypatch):
    """Passivity check (not a telemetry-content check -- see
    test_get_plan_telemetry_records_have_expected_fields below for that):
    with TELEMETRY_ENABLED True and the admission gate admitted, get_plan()
    still returns the correct parsed steps and still releases the exact
    reservation_id it was admitted with -- telemetry emission must not
    perturb either of get_plan()'s pre-existing return-value or
    release-call contracts."""
    payload = {
        "id": "chatcmpl-plannd-1",
        "system_fingerprint": "b1234-abcdef0",
        "choices": [
            {
                "message": {"content": "1. Do the thing\n2. Verify it"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 12},
        "timings": {
            "cache_n": 20,
            "prompt_n": 50,
            "prompt_ms": 120.0,
            "prompt_per_token_ms": 2.4,
            "prompt_per_second": 416.7,
            "predicted_n": 12,
            "predicted_ms": 200.0,
            "predicted_per_token_ms": 16.7,
            "predicted_per_second": 60.0,
        },
    }
    released = _patch_gate_and_urlopen(monkeypatch, payload)

    result = get_plan("do the thing", enable_thinking=True)

    assert result == ["Do the thing", "Verify it"]
    assert released == ["plannd-test-reservation"]


def test_get_plan_telemetry_records_have_expected_fields(monkeypatch, _capture_telemetry):
    payload = {
        "id": "chatcmpl-plannd-2",
        "system_fingerprint": "b1234-abcdef0",
        "choices": [
            {
                "message": {"content": "1. Do the thing"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 6},
        "timings": {
            "cache_n": 20,
            "prompt_n": 50,
            "prompt_ms": 120.0,
            "prompt_per_token_ms": 2.4,
            "prompt_per_second": 416.7,
            "predicted_n": 6,
            "predicted_ms": 100.0,
            "predicted_per_token_ms": 16.7,
            "predicted_per_second": 60.0,
        },
    }
    _patch_gate_and_urlopen(monkeypatch, payload)

    result = get_plan("do the thing", enable_thinking=True)
    assert result == ["Do the thing"]

    categories = {rec["category"] for rec in _capture_telemetry}
    assert categories == {"inference", "gate"}

    gate_records = [r for r in _capture_telemetry if r["category"] == "gate"]
    assert len(gate_records) == 1
    gate_record = gate_records[0]
    assert gate_record["emitter"] == "codey-os.daemon"
    assert gate_record["event_type"] == "reserve_context_budget"
    assert gate_record["body"]["call_site"] == "plannd.get_plan"
    assert gate_record["body"]["decision"]["admitted"] is True
    assert gate_record["body"]["wait_ms"] >= 0.0
    assert schema.validate(gate_record) == []

    inf_records = [r for r in _capture_telemetry if r["category"] == "inference"]
    assert len(inf_records) == 1
    inf_record = inf_records[0]
    assert inf_record["emitter"] == "codey-os.daemon"
    assert inf_record["event_type"] == "completion"
    body = inf_record["body"]
    assert body["role"] == "planner"
    assert body["thinking_mode"] is True
    assert body["backend"] == "local"
    assert body["stream"] is False
    assert body["prompt_tokens"] == 50
    assert body["completion_tokens"] == 6
    assert body["cached_prompt_tokens"] == 20
    assert body["prefix_cache_hit"] is True
    assert body["prefill_tps"] == 416.7
    assert body["generation_tps"] == 60.0
    assert body["finish_reason"] == "stop"
    assert body["server_request_id"] == "chatcmpl-plannd-2"
    assert body["server_fingerprint"] == "b1234-abcdef0"
    assert body["queue_wait_ms"] >= 0.0
    assert body["n_ctx"] == 8192  # _admitted_decision()'s effective_n_ctx
    assert body["interactive"] is False
    # No streaming path exists for this call site at all -- always null.
    assert inf_record["nulls"]["body.ttft_ms"] == "server_timings_absent"
    assert inf_record["nulls"]["body.model_sha256"] == "model_sha256_not_computed"
    # Unlike T5's inference_hybrid.py call sites, role/thinking_mode ARE
    # known here -- must NOT be in nulls.
    assert "body.role" not in inf_record["nulls"]
    assert "body.thinking_mode" not in inf_record["nulls"]
    assert schema.validate(inf_record) == []


def test_get_plan_telemetry_cached_prompt_tokens_pruned_when_cache_n_absent(monkeypatch, _capture_telemetry):
    """NEW-344 (Confirmed/latent, not yet fixed): pins CURRENT behavior,
    not the intended/correct behavior -- see NEW_ISSUES.md's "Fix
    direction" for this entry, which calls for adding explicit `nulls`
    handling here. Today, when `timings` is present but lacks a `cache_n`
    key (distinct from test_get_plan_telemetry_falls_back_to_usage_when_
    timings_absent's case, where timings is missing entirely),
    core/plannd.py's `if timings:` branch sets `cached_prompt_tokens =
    timings.get("cache_n")` to None without recording a matching `nulls`
    reason (unlike the fully-timings-absent branch, which does add one).
    `telemetry/recorders.py`'s `_emit()` then silently prunes any body
    field that is None with no matching `nulls` entry -- so
    `cached_prompt_tokens`/`prefix_cache_hit` come back missing from
    `body` entirely rather than present as an honest null, which is
    exactly the "invisible-omission" gap NEW-344 describes. This test
    exists to catch a regression in *this* pruning behavior changing
    unexpectedly; it must be updated (not just re-pinned) once NEW-344 is
    actually fixed to instead assert an honest null with a `nulls`
    reason."""
    payload = {
        "choices": [{"message": {"content": "1. Do the thing"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 50, "completion_tokens": 6},
        "timings": {
            "prompt_n": 50,
            "prompt_ms": 120.0,
            "prompt_per_token_ms": 2.4,
            "prompt_per_second": 416.7,
            "predicted_n": 6,
            "predicted_ms": 100.0,
            "predicted_per_token_ms": 16.7,
            "predicted_per_second": 60.0,
        },
    }
    _patch_gate_and_urlopen(monkeypatch, payload)

    result = get_plan("do the thing", enable_thinking=True)
    assert result == ["Do the thing"]

    inf_record = [r for r in _capture_telemetry if r["category"] == "inference"][0]
    body = inf_record["body"]
    assert "cached_prompt_tokens" not in body
    assert "prefix_cache_hit" not in body
    assert "body.cached_prompt_tokens" not in inf_record["nulls"]
    assert "body.prefix_cache_hit" not in inf_record["nulls"]
    assert body["prefill_tps"] == 416.7
    assert body["generation_tps"] == 60.0
    assert schema.validate(inf_record) == []


def test_get_plan_telemetry_thinking_mode_reflects_enable_thinking_false(monkeypatch, _capture_telemetry):
    payload = {
        "choices": [{"message": {"content": "1. Do the thing"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3},
    }
    _patch_gate_and_urlopen(monkeypatch, payload)

    result = get_plan("do the thing", enable_thinking=False)
    assert result == ["Do the thing"]

    inf_record = [r for r in _capture_telemetry if r["category"] == "inference"][0]
    assert inf_record["body"]["thinking_mode"] is False


def test_get_plan_telemetry_falls_back_to_usage_when_timings_absent(monkeypatch, _capture_telemetry):
    payload = {
        "choices": [{"message": {"content": "1. Do the thing"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 8},
    }
    _patch_gate_and_urlopen(monkeypatch, payload)

    result = get_plan("do the thing")
    assert result == ["Do the thing"]

    inf_record = [r for r in _capture_telemetry if r["category"] == "inference"][0]
    body = inf_record["body"]
    assert body["prompt_tokens"] == 20
    assert body["completion_tokens"] == 8
    nulls = inf_record["nulls"]
    for field in (
        "prefill_tps", "generation_tps", "prefill_ms", "generation_ms",
        "prompt_per_token_ms", "predicted_per_token_ms", "cached_prompt_tokens",
        "prefix_cache_hit",
    ):
        assert body[field] is None, f"{field} should be null, got {body.get(field)!r}"
        assert nulls[f"body.{field}"] == "server_timings_absent"
    assert schema.validate(inf_record) == []


def test_get_plan_telemetry_honest_null_when_timings_and_usage_both_absent(monkeypatch, _capture_telemetry):
    payload = {"choices": [{"message": {"content": "1. Do the thing"}, "finish_reason": "stop"}]}
    _patch_gate_and_urlopen(monkeypatch, payload)

    result = get_plan("do the thing")
    assert result == ["Do the thing"]

    inf_record = [r for r in _capture_telemetry if r["category"] == "inference"][0]
    assert inf_record["nulls"]["body.prompt_tokens"] == "server_usage_absent"
    assert inf_record["nulls"]["body.completion_tokens"] == "server_usage_absent"
    assert schema.validate(inf_record) == []


def test_get_plan_telemetry_emitted_even_when_content_empty_after_length(monkeypatch, _capture_telemetry):
    """NEW-164 diagnostic case: finish_reason=length with empty content
    still returns None from get_plan(), but the completion DID happen and
    the response body was fully consumed -- the category-A record must
    still be emitted so the evidence (finish_reason, token counts) isn't
    silently lost, matching this function's own placement decision (see
    core/plannd.py's inline comment at the emission call site)."""
    payload = {
        "choices": [
            {
                "finish_reason": "length",
                "message": {"content": "", "reasoning_content": "x" * 100},
            }
        ],
        "usage": {"completion_tokens": 1024, "prompt_tokens": 50},
    }
    _patch_gate_and_urlopen(monkeypatch, payload)

    result = get_plan("do the thing")
    assert result is None

    inf_records = [r for r in _capture_telemetry if r["category"] == "inference"]
    assert len(inf_records) == 1
    assert inf_records[0]["body"]["finish_reason"] == "length"
    assert inf_records[0]["body"]["completion_tokens"] == 1024


def test_get_plan_no_telemetry_when_disabled(monkeypatch, _capture_telemetry):
    """Kill switch: checked first, before any other telemetry work --
    with TELEMETRY_ENABLED False, neither category-A nor category-B
    records are ever built, and get_plan() itself still works."""
    monkeypatch.setattr(recorders.store, "TELEMETRY_ENABLED", False)
    payload = {
        "choices": [{"message": {"content": "1. Do the thing"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        "timings": {"predicted_n": 3, "predicted_ms": 30.0},
    }
    _patch_gate_and_urlopen(monkeypatch, payload)

    result = get_plan("do the thing")

    assert result == ["Do the thing"]
    assert _capture_telemetry == []


def test_get_plan_emits_gate_denial_record_when_admission_refused(monkeypatch, _capture_telemetry):
    """Design §2.B: 'Denials are recorded exactly as fully as
    admissions.' Also confirms urlopen is never reached and no
    category-A record is emitted -- no HTTP response exists to describe."""
    monkeypatch.setattr(
        "core.resource_gate.wait_and_reserve_context_budget",
        lambda *a, **k: _refused_decision(),
    )
    mock_release = mock.MagicMock()
    monkeypatch.setattr("core.resource_gate.release_context_budget", mock_release)
    mock_urlopen = mock.MagicMock()
    monkeypatch.setattr(plannd_mod.urllib.request, "urlopen", mock_urlopen)

    result = get_plan("do the thing")

    assert result is None
    mock_release.assert_not_called()
    mock_urlopen.assert_not_called()
    assert len(_capture_telemetry) == 1
    gate_record = _capture_telemetry[0]
    assert gate_record["category"] == "gate"
    assert gate_record["event_type"] == "reserve_context_budget"
    assert gate_record["body"]["decision"]["admitted"] is False
    assert gate_record["body"]["reason"] == _refused_decision().reason
