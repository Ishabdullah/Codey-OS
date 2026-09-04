---
name: telemetry-t3-prefix-cache-hit-round2-flaky-test-rejected
description: T3 prefix_cache_hit one-liner fix verified correct, but round2 REJECTED on 4 new tests that nondeterministically hit real unmocked resource_gate admission
metadata:
  type: project
---

Follow-up review of `restoricon_core/api/routes.py`'s `_emit_ai_chat_telemetry` (T3,
`docs/telemetry_layer_design.md`). Round1 blocker (prefix_cache_hit silently omitted, not
honest-nulled, in the timings-absent branch) — the one-line fix is correct: negative-control
verified myself (hand-removed `"prefix_cache_hit"` from the nulls-tuple, reran the specific
test, got the exact predicted `KeyError: 'prefix_cache_hit'`; restored, green again).

**Round2 REJECTED anyway** — not on the fix itself, on a new defect the fix's own test file
introduced. `tests/test_restoricon_core/test_api.py`'s `-k
test_api_ai_chat_...` file passes standalone (20/20), but `pytest tests/ -q` (full suite) came
back **1321 passed / 4 failed / 1 skipped**, and all 4 failures were the 4 NEW T3 tests
(`test_api_ai_chat_emits_category_a_telemetry_on_success`,
`_falls_back_to_usage_when_timings_absent`, `_honest_null_when_timings_and_usage_both_absent`,
`_no_telemetry_written_when_disabled`) — every one failing with `assert 429 == 200`, i.e. the
real `wait_and_reserve_context_budget()` admission gate refusing the request. This directly
contradicts the implementer's claimed "1323 passed / 2 pre-existing unrelated failures / 1
skipped."

**Root cause (traced, not guessed):** `grep resource_gate
tests/test_restoricon_core/test_api.py` returns zero hits — none of the ai/chat tests in this
file mock or override `state_dir`. The pre-existing 10b finding (`test_api_ai_chat_auth_and_validation`
patches `urllib.request.urlopen` *unconditionally*, so `make_request()`'s own client-side call
is intercepted too and the server handler body never actually runs) is why NO prior test in
this file ever really drove `wait_and_reserve_context_budget()`. The 4 new T3 tests use a
path-conditional `mock_urlopen` (only intercepts `/v1/chat/completions`, passes everything
else to the real `urlopen`) — making them the FIRST tests in the repo to exercise the real,
unmocked admission gate, whose default `state_dir` is `CODEY_STATE_DIR = ~/.codeyOS` (the
actual production state directory) and which polls a nonexistent llama-server on
`127.0.0.1:8080` (visible in stdout: "resource_gate: /slots poll failed ... degrading:
timed out"). Under full-suite load/real system RAM pressure, admission is refused
nondeterministically. One of the 4 flaky tests is the sole regression guard for THIS ROUND'S
OWN blocker (`_falls_back_to_usage_when_timings_absent`) — a nondeterministic acceptance test
for the very thing being reviewed is not an acceptance test.

**Also discovered:** the "2 pre-existing unrelated `test_loader_resource_gate.py` failures"
boilerplate carried forward from T0 through T2's approvals is ITSELF flaky, not a stable
baseline — my full run came back with `test_loader_resource_gate.py` green and the 4 new
tests red instead; totals reconcile exactly (1319+2 baseline -> 1321 passed this run, +4 new
failures = same 1326 total). Correct the record (rule 6): stop copying "2 pre-existing
failures" forward as a fixed fact: it's actually flaky too, and should be reworded in
PROJECT_LOG/NEW_ISSUES.

**Item 4 (sibling `cache_n` gap) nuance:** confirmed via `~/llama.cpp/tools/server/server-task.h`
+ `server-task.cpp` that `result_timings::to_json()` puts `cache_n` in the unconditional base
JSON object (unlike `draft_n`/`draft_n_accepted`, gated on `> 0`) -- so the MISSING-KEY form of
this gap is genuinely latent/unreachable, confirming the implementer's claim. BUT the struct
declares `int32_t cache_n = -1` as its default, and `telemetry/schema/v1.json` line 60 declares
`cached_prompt_tokens` as `{"type": "int", "nullable": true}` with no minimum/range check -- so
if `cache_n` is ever left at its -1 default (uninitialized edge case), it flows through as
`cached_prompt_tokens = -1`, a wrong VALUE that passes schema validation silently, not a missing
key. Correct NEW_ISSUES.md wording: "the missing-key form is unreachable; the -1 sentinel form
is not (and is not caught by schema validation)." Non-blocking, but should be logged with this
more precise framing rather than a blanket "latent/unreachable."

**Fix required for round3:** the 4 new tests need to stub the admission gate directly --
`monkeypatch.setattr` on the `core.resource_gate.wait_and_reserve_context_budget` symbol the
route imports (it's a local `from core.resource_gate import (...)` inside the route method, so
patch at `core.resource_gate.wait_and_reserve_context_budget`), returning an admitted
`ContextBudgetDecision` with a real `effective_n_ctx` (the telemetry body asserts consume
`n_ctx`, so a bare `Mock()` would poison the record with a non-serializable value). Requirement
for re-review: all 4 tests green in a FULL `pytest tests/ -q` run, pasted verbatim, not just
the file in isolation.

**Why:** this is the same bug shape as [[resource_gate_74a_subtaskC1_round2_fake_pid_regression]]
-- a claimed test count that doesn't match a literal re-run, caught only by actually running the
full suite myself rather than trusting the isolated-file pass. It also reinforces
[[termux_signal_delivery_unreliable_in_sandbox]]-adjacent lesson: real device resource state
(RAM, real ~/.codeyOS files) leaking into test runs produces silent, hard-to-reproduce
false-positives when tests are only run in isolation.

**How to apply:** for ANY new test that hits `/api/v1/ai/chat` (or any route going through
`wait_and_reserve_context_budget`/`reserve_context_budget`), check it mocks/stubs the gate or
passes an isolated `state_dir` -- don't assume path-conditional `mock_urlopen` is sufficient
isolation on its own. Always run the FULL suite (not just the changed file) before accepting a
"tests pass" claim on anything touching `restoricon_core/api/routes.py`'s ai/chat handler,
since that's the one endpoint in this file with a real unmocked resource-gate dependency.
