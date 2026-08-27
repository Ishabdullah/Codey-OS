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
import json
import unittest.mock as mock
from io import BytesIO

import core.resource_gate as rg
from core.inference_hybrid import ChatCompletionBackend


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
