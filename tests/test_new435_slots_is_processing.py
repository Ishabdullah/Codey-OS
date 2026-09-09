"""
NEW-435 fix coverage — `_fetch_slots_prompt_tokens()` (core/resource_gate.py)
used to sum `n_prompt_tokens` across every `/slots` entry unconditionally.
Source-confirmed against ~/llama.cpp's tools/server/server-context.cpp:
`n_prompt_tokens` is NOT cleared when a slot is released — an idle slot
that has served at least one request keeps reporting that request's token
count indefinitely, until it serves its next one. `is_processing` (present
on every slot) is the field that actually reflects true occupancy, updated
synchronously with no meaningful lag. The fix only counts slots with
`is_processing is True`, and fails closed (counts + warns) on schema drift
(missing/non-bool `is_processing`) rather than silently treating it as
idle.

All tests use synthetic /slots payloads shaped exactly like the real
confirmed live-verify evidence (mirrors this module's own established
mocking convention — see tests/test_new430_431_context_lease.py's own
module docstring). No test spawns a subprocess model server or sleeps
real seconds.
"""

import unittest.mock as mock

import core.resource_gate as rg
from tests.test_new430_431_context_lease import _fake_json_response


def _old_formula_sum(data):
    """The exact pre-fix arithmetic (unconditional n_prompt_tokens sum),
    reproduced inline so tests can prove a given payload genuinely would
    have produced the NEW-435 regression under the old code, not just that
    it passes under the new one."""
    return sum(int(s.get("n_prompt_tokens", 0) or 0) for s in data)


def test_never_served_idle_slot_contributes_zero_no_keyerror():
    payload = [{"id": 0, "n_ctx": 8192, "speculative": False, "is_processing": False}]
    # Not a regression case: the old formula also returned 0 here (via
    # .get("n_prompt_tokens", 0)'s default). This is a KeyError-guard test
    # for the never-served slot, not a proof the fix changed behavior here.
    assert _old_formula_sum(payload) == 0

    with mock.patch.object(rg.urllib.request, "urlopen", return_value=_fake_json_response(payload)):
        result = rg._fetch_slots_prompt_tokens("127.0.0.1", 8080, sleep_fn=lambda s: None)
    assert result == 0


def test_genuinely_idle_slot_with_stale_n_prompt_tokens_is_new435_regression():
    """The actual NEW-435 regression shape: a slot that served a request in
    the past, is now idle, but /slots still reports its last n_prompt_tokens
    (mirrors the real live-verify evidence: id=3, n_ctx=8192, stale 4554)."""
    payload = [
        {
            "id": 3,
            "n_ctx": 8192,
            "speculative": False,
            "is_processing": False,
            "n_prompt_tokens": 4554,
        }
    ]
    # Prove this payload genuinely would have regressed under the OLD
    # formula — not just that the new one passes.
    assert _old_formula_sum(payload) == 4554

    with mock.patch.object(rg.urllib.request, "urlopen", return_value=_fake_json_response(payload)):
        result = rg._fetch_slots_prompt_tokens("127.0.0.1", 8080, sleep_fn=lambda s: None)
    assert result == 0


def test_actively_processing_slot_contributes_full_tokens():
    payload = [{"id": 1, "is_processing": True, "n_prompt_tokens": 4246}]
    with mock.patch.object(rg.urllib.request, "urlopen", return_value=_fake_json_response(payload)):
        result = rg._fetch_slots_prompt_tokens("127.0.0.1", 8080, sleep_fn=lambda s: None)
    assert result == 4246


def test_mixed_pool_counts_only_the_active_slot():
    """Exact real repro shape: one stale-idle slot (would have contributed
    4554 under the old formula) alongside one actively-processing slot
    (4246). Only the active slot's tokens must be counted."""
    payload = [
        {
            "id": 3,
            "n_ctx": 8192,
            "speculative": False,
            "is_processing": False,
            "n_prompt_tokens": 4554,
        },
        {"id": 1, "is_processing": True, "n_prompt_tokens": 4246},
    ]
    assert _old_formula_sum(payload) == 4554 + 4246

    with mock.patch.object(rg.urllib.request, "urlopen", return_value=_fake_json_response(payload)):
        result = rg._fetch_slots_prompt_tokens("127.0.0.1", 8080, sleep_fn=lambda s: None)
    assert result == 4246


def test_schema_drift_missing_is_processing_fails_closed_and_warns():
    payload = [{"id": 5, "n_prompt_tokens": 999}]  # no is_processing key at all
    with mock.patch.object(
        rg.urllib.request, "urlopen", return_value=_fake_json_response(payload)
    ), mock.patch("core.resource_gate.warning") as mock_warning:
        result = rg._fetch_slots_prompt_tokens("127.0.0.1", 8080, sleep_fn=lambda s: None)
    assert result == 999
    assert mock_warning.called
    assert any("is_processing" in str(call.args[0]) for call in mock_warning.call_args_list)


def test_schema_drift_non_bool_is_processing_fails_closed_and_warns():
    payload = [{"id": 6, "is_processing": "idle", "n_prompt_tokens": 111}]
    with mock.patch.object(
        rg.urllib.request, "urlopen", return_value=_fake_json_response(payload)
    ), mock.patch("core.resource_gate.warning") as mock_warning:
        result = rg._fetch_slots_prompt_tokens("127.0.0.1", 8080, sleep_fn=lambda s: None)
    assert result == 111
    assert mock_warning.called


def test_schema_drift_none_is_processing_fails_closed_and_warns():
    payload = [{"id": 7, "is_processing": None, "n_prompt_tokens": 222}]
    with mock.patch.object(
        rg.urllib.request, "urlopen", return_value=_fake_json_response(payload)
    ), mock.patch("core.resource_gate.warning") as mock_warning:
        result = rg._fetch_slots_prompt_tokens("127.0.0.1", 8080, sleep_fn=lambda s: None)
    assert result == 222
    assert mock_warning.called
