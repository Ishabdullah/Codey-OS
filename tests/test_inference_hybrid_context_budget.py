"""
§8 Q11 / NEW-206 fix coverage — core/inference_hybrid.py::
ChatCompletionBackend.infer()'s context-budget admission wiring (the other
of the two live call sites this fix wires, alongside
core/plannd.py::get_plan() — see tests/test_plannd_timeout.py's/
tests/test_plannd_tier_split.py's matching fixture for that side, and
tests/test_context_budget.py for the resource_gate admission logic itself).

Mocks core.resource_gate.wait_and_reserve_context_budget()/
release_context_budget() directly (this module's own established pattern —
see tests/test_plannd_timeout.py) rather than spawning a real llama-server;
urllib.request.urlopen is also mocked so no real HTTP call is made.
"""
import dataclasses
import json
import unittest.mock as mock
from io import BytesIO

import pytest

import core.resource_gate as rg
from core.inference_hybrid import ChatCompletionBackend
from telemetry import envelope, recorders, schema


def _fake_response(payload: dict):
    body = json.dumps(payload).encode("utf-8")
    cm = mock.MagicMock()
    cm.__enter__.return_value = BytesIO(body)
    cm.__exit__.return_value = False
    return cm


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


def _refused_decision(timed_out=False):
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
        timed_out=timed_out,
    )


def _chat_payload(text="1. step one"):
    return {
        "choices": [{"message": {"content": text}}],
        "usage": {"completion_tokens": 3},
        "timings": {"predicted_n": 3, "predicted_ms": 100},
    }


def test_infer_calls_wait_and_reserve_before_urlopen_and_releases_after():
    backend = ChatCompletionBackend()
    calls = []

    def _fake_wait(*args, **kwargs):
        calls.append("reserve")
        return _admitted_decision("rid-1")

    def _fake_release(reservation_id, *args, **kwargs):
        calls.append(f"release:{reservation_id}")
        return True

    with mock.patch(
        "core.resource_gate.wait_and_reserve_context_budget", side_effect=_fake_wait
    ), mock.patch(
        "core.resource_gate.release_context_budget", side_effect=_fake_release
    ), mock.patch.object(
        __import__("core.inference_hybrid", fromlist=["urllib"]).urllib.request,
        "urlopen",
        return_value=_fake_response(_chat_payload()),
    ):
        result = backend.infer([{"role": "user", "content": "hi"}], max_tokens=64)

    assert result is not None
    assert calls == ["reserve", "release:rid-1"]


def test_infer_returns_none_and_never_calls_urlopen_when_admission_refused():
    backend = ChatCompletionBackend()

    with mock.patch(
        "core.resource_gate.wait_and_reserve_context_budget", return_value=_refused_decision()
    ), mock.patch(
        "core.resource_gate.release_context_budget"
    ) as mock_release, mock.patch.object(
        __import__("core.inference_hybrid", fromlist=["urllib"]).urllib.request,
        "urlopen",
    ) as mock_urlopen:
        result = backend.infer([{"role": "user", "content": "hi"}], max_tokens=64)

    assert result is None
    mock_urlopen.assert_not_called()
    # No reservation was admitted, so nothing to release.
    mock_release.assert_not_called()


def test_infer_returns_none_on_queue_timeout():
    backend = ChatCompletionBackend()

    with mock.patch(
        "core.resource_gate.wait_and_reserve_context_budget",
        return_value=_refused_decision(timed_out=True),
    ), mock.patch.object(
        __import__("core.inference_hybrid", fromlist=["urllib"]).urllib.request,
        "urlopen",
    ) as mock_urlopen:
        result = backend.infer([{"role": "user", "content": "hi"}], max_tokens=64)

    assert result is None
    mock_urlopen.assert_not_called()


def test_infer_releases_reservation_even_when_http_call_fails():
    backend = ChatCompletionBackend()
    released = []

    with mock.patch(
        "core.resource_gate.wait_and_reserve_context_budget",
        return_value=_admitted_decision("rid-err"),
    ), mock.patch(
        "core.resource_gate.release_context_budget", side_effect=lambda rid, *a, **k: released.append(rid)
    ), mock.patch.object(
        __import__("core.inference_hybrid", fromlist=["urllib"]).urllib.request,
        "urlopen",
        side_effect=OSError("connection reset"),
    ):
        result = backend.infer([{"role": "user", "content": "hi"}], max_tokens=64)

    assert result is None
    assert released == ["rid-err"]


def test_infer_fails_closed_when_admission_check_itself_raises():
    backend = ChatCompletionBackend()

    with mock.patch(
        "core.resource_gate.wait_and_reserve_context_budget",
        side_effect=RuntimeError("resource_gate broke"),
    ), mock.patch.object(
        __import__("core.inference_hybrid", fromlist=["urllib"]).urllib.request,
        "urlopen",
    ) as mock_urlopen:
        result = backend.infer([{"role": "user", "content": "hi"}], max_tokens=64)

    assert result is None
    mock_urlopen.assert_not_called()


# ── T5 (docs/telemetry_layer_design.md §7): category-A + category-B ────────
# telemetry emitted by ChatCompletionBackend.infer(). Mocks
# telemetry.recorders.store.record() directly to a capture list (the same
# pattern tests/test_telemetry_recorders.py already established) rather
# than polling real JSONL files -- deterministic, no writer thread, no
# filesystem. The admission gate is mocked via
# core.resource_gate.wait_and_reserve_context_budget()/
# release_context_budget() (this file's own established pattern above),
# never exercising the real gate against live device RAM state.


@pytest.fixture(autouse=True)
def _capture_telemetry(monkeypatch):
    """Autouse within this file only: captures every record() call and
    forces TELEMETRY_ENABLED True by default, overriding
    tests/conftest.py's session-wide default of False (matching
    tests/test_telemetry_recorders.py's `_capture_store` fixture). The one
    test that needs the kill switch OFF (`test_infer_no_telemetry_when_disabled`)
    overrides it back to False itself."""
    captured = []

    def fake_record(rec):
        captured.append(rec)

    monkeypatch.setattr(recorders.store, "record", fake_record)
    monkeypatch.setattr(recorders.store, "get_run_id", lambda: "infhybridtest01")
    monkeypatch.setattr(recorders.store, "TELEMETRY_ENABLED", True)
    # With telemetry genuinely enabled, inference_hybrid.py's emission path
    # locally imports and calls the real is_interactive_session_active(),
    # which does filesystem work against ~/.codeyOS/tui-sessions/. Patch the
    # module attribute (not an already-bound reference) so the local import
    # picks up the mock instead of touching real device state.
    monkeypatch.setattr(
        "core.resource_gate.is_interactive_session_active", lambda *a, **k: False
    )
    envelope.reset_seq()
    return captured


def _sse_lines(*objs):
    """Builds the raw byte lines _infer_streaming() iterates over, plus
    the terminating [DONE] line."""
    lines = [f"data: {json.dumps(o)}\n".encode("utf-8") for o in objs]
    lines.append(b"data: [DONE]\n")
    return lines


class _FakeSSEResponse:
    """Minimal stand-in for urllib's streaming response object.
    `_infer_streaming()` only iterates it and calls `.close()` --
    `.fp._sock.settimeout()/.close()` are both already wrapped in
    try/except Exception at the real call site, so omitting `.fp`
    entirely exercises that existing fallback path rather than needing a
    real socket."""

    def __init__(self, lines):
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)

    def close(self):
        pass


def _patch_urlopen_and_gate(monkeypatch, response_factory, reservation_id="t5-reservation"):
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
        __import__("core.inference_hybrid", fromlist=["urllib"]).urllib.request,
        "urlopen",
        response_factory,
    )
    return released


def test_infer_blocking_emits_category_a_and_category_b_telemetry(monkeypatch, _capture_telemetry):
    payload = {
        "id": "chatcmpl-xyz",
        "system_fingerprint": "b1234-abcdef0",
        "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4},
        "timings": {
            "cache_n": 6,
            "prompt_n": 10,
            "prompt_ms": 40.0,
            "prompt_per_token_ms": 4.0,
            "prompt_per_second": 250.0,
            "predicted_n": 4,
            "predicted_ms": 80.0,
            "predicted_per_token_ms": 20.0,
            "predicted_per_second": 50.0,
        },
    }
    _patch_urlopen_and_gate(monkeypatch, lambda *a, **k: _fake_response(payload))

    backend = ChatCompletionBackend()
    result = backend.infer([{"role": "user", "content": "hi"}], max_tokens=64, stream=False)

    assert result is not None
    text, tokens, tps = result
    assert text == "hello"

    categories = {rec["category"] for rec in _capture_telemetry}
    assert categories == {"inference", "gate"}

    gate_records = [r for r in _capture_telemetry if r["category"] == "gate"]
    assert len(gate_records) == 1
    gate_record = gate_records[0]
    assert gate_record["event_type"] == "reserve_context_budget"
    assert gate_record["body"]["call_site"] == "inference_hybrid.infer"
    assert gate_record["body"]["decision"] == dataclasses.asdict(_admitted_decision("t5-reservation"))
    assert gate_record["body"]["wait_ms"] >= 0.0
    assert schema.validate(gate_record) == []

    inf_records = [r for r in _capture_telemetry if r["category"] == "inference"]
    assert len(inf_records) == 1
    inf_record = inf_records[0]
    assert inf_record["event_type"] == "completion"
    body = inf_record["body"]
    assert body["backend"] == "local"
    assert body["stream"] is False
    assert body["prompt_tokens"] == 10
    assert body["completion_tokens"] == 4
    assert body["cached_prompt_tokens"] == 6
    assert body["prefix_cache_hit"] is True
    assert body["prefill_tps"] == 250.0
    assert body["generation_tps"] == 50.0
    assert body["finish_reason"] == "stop"
    assert body["server_request_id"] == "chatcmpl-xyz"
    assert body["server_fingerprint"] == "b1234-abcdef0"
    assert body["queue_wait_ms"] >= 0.0
    assert body["n_ctx"] == 8192  # _admitted_decision()'s effective_n_ctx
    # Blocking path: no first-token boundary exists at all (design §5.1) --
    # never faked from wall-clock elapsed time.
    assert inf_record["nulls"]["body.ttft_ms"] == "server_timings_absent"
    assert inf_record["nulls"]["body.role"] == "call_site_not_yet_tagged"
    assert inf_record["nulls"]["body.thinking_mode"] == "call_site_not_yet_tagged"
    assert inf_record["nulls"]["body.model_sha256"] == "model_sha256_not_computed"
    assert schema.validate(inf_record) == []


def test_infer_streaming_captures_real_ttft_ms(monkeypatch, _capture_telemetry):
    final_chunk = {
        "id": "chatcmpl-stream-1",
        "system_fingerprint": "b1234-abcdef0",
        "choices": [{"delta": {}, "finish_reason": "stop"}],
        "timings": {
            "cache_n": 0,
            "prompt_n": 8,
            "prompt_ms": 30.0,
            "prompt_per_token_ms": 3.75,
            "prompt_per_second": 266.7,
            "predicted_n": 2,
            "predicted_ms": 40.0,
            "predicted_per_token_ms": 20.0,
            "predicted_per_second": 50.0,
        },
    }
    lines = _sse_lines(
        {"choices": [{"delta": {"content": "Hi"}}]},
        {"choices": [{"delta": {"content": "!"}}]},
        final_chunk,
    )
    _patch_urlopen_and_gate(monkeypatch, lambda *a, **k: _FakeSSEResponse(lines))

    backend = ChatCompletionBackend()
    # on_first_token deliberately omitted (None) -- ttft_ms capture must
    # not depend on a caller-supplied callback (T5, design §5.1).
    result = backend.infer([{"role": "user", "content": "hi"}], max_tokens=64, stream=True)

    assert result is not None
    text, tokens, tps = result
    assert text == "Hi!"

    inf_records = [r for r in _capture_telemetry if r["category"] == "inference"]
    assert len(inf_records) == 1
    body = inf_records[0]["body"]
    assert body["stream"] is True
    assert body["ttft_ms"] is not None
    assert body["ttft_ms"] >= 0.0
    assert "body.ttft_ms" not in inf_records[0]["nulls"]
    assert body["finish_reason"] == "stop"
    assert body["server_request_id"] == "chatcmpl-stream-1"
    assert body["prompt_tokens"] == 8
    assert body["completion_tokens"] == 2
    assert schema.validate(inf_records[0]) == []


def test_infer_telemetry_falls_back_to_usage_when_timings_absent(monkeypatch, _capture_telemetry):
    payload = {
        "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 8},
    }
    _patch_urlopen_and_gate(monkeypatch, lambda *a, **k: _fake_response(payload))

    backend = ChatCompletionBackend()
    result = backend.infer([{"role": "user", "content": "hi"}], max_tokens=64, stream=False)
    assert result is not None

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


def test_infer_telemetry_honest_null_when_timings_and_usage_both_absent(monkeypatch, _capture_telemetry):
    payload = {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}
    _patch_urlopen_and_gate(monkeypatch, lambda *a, **k: _fake_response(payload))

    backend = ChatCompletionBackend()
    result = backend.infer([{"role": "user", "content": "hi"}], max_tokens=64, stream=False)
    assert result is not None

    inf_record = [r for r in _capture_telemetry if r["category"] == "inference"][0]
    assert inf_record["nulls"]["body.prompt_tokens"] == "server_usage_absent"
    assert inf_record["nulls"]["body.completion_tokens"] == "server_usage_absent"
    assert schema.validate(inf_record) == []


def test_infer_no_telemetry_when_disabled(monkeypatch, _capture_telemetry):
    """Kill switch (design §5.3): checked first, before any other work --
    with TELEMETRY_ENABLED False, neither category-A nor category-B
    records are ever built."""
    monkeypatch.setattr(recorders.store, "TELEMETRY_ENABLED", False)
    payload = {
        "choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        "timings": {"predicted_n": 1, "predicted_ms": 10.0},
    }
    _patch_urlopen_and_gate(monkeypatch, lambda *a, **k: _fake_response(payload))

    backend = ChatCompletionBackend()
    result = backend.infer([{"role": "user", "content": "hi"}], max_tokens=64, stream=False)

    assert result is not None
    assert _capture_telemetry == []


def test_infer_emits_gate_denial_record_when_admission_refused(monkeypatch, _capture_telemetry):
    """Design §2.B: 'Denials are recorded exactly as fully as
    admissions.'"""
    monkeypatch.setattr(
        "core.resource_gate.wait_and_reserve_context_budget",
        lambda *a, **k: _refused_decision(),
    )
    mock_release = mock.MagicMock()
    monkeypatch.setattr("core.resource_gate.release_context_budget", mock_release)
    mock_urlopen = mock.MagicMock()
    monkeypatch.setattr(
        __import__("core.inference_hybrid", fromlist=["urllib"]).urllib.request,
        "urlopen",
        mock_urlopen,
    )

    backend = ChatCompletionBackend()
    result = backend.infer([{"role": "user", "content": "hi"}], max_tokens=64)

    assert result is None
    mock_release.assert_not_called()
    mock_urlopen.assert_not_called()
    assert len(_capture_telemetry) == 1
    gate_record = _capture_telemetry[0]
    assert gate_record["category"] == "gate"
    assert gate_record["event_type"] == "reserve_context_budget"
    assert gate_record["body"]["decision"]["admitted"] is False
    assert gate_record["body"]["reason"] == _refused_decision().reason
    assert schema.validate(gate_record) == []
