---
name: new206-q11-context-budget-reservation-lifetime-double-count
description: NEW-206/§8 Q11 context-budget admission fix — core mechanism approved, but reservation held for full call duration double-counts against /slots' real signal, undermining the fix's own concurrency goal; not logged to NEW_ISSUES.md
metadata:
  type: project
---

Reviewed uncommitted diff for NEW-206/§8 Q11 (concurrency-oversubscription
fix): `core/resource_gate.py` (new context-budget ledger:
`reserve_context_budget()`/`release_context_budget()`/
`wait_and_reserve_context_budget()`/`resolve_effective_n_ctx()`/
`estimate_prompt_tokens()`), wired into `core/inference_hybrid.py::infer()`
and `core/plannd.py::get_plan()`, plus `core/daemon.py` timeout-layering
(`compute_outer_plan_timeout()`).

**Verified clean:** fail-closed n_ctx resolution (every return path
checked — no permissive fallback), flock never held across `sleep()` in
`wait_and_reserve_context_budget()`, `release_context_budget()` called on
every exit path of both call sites (including exception/early-return
paths — verified by reading full function bodies, not just the diff
hunks), outer/inner timeout layering still strictly ordered after adding
`CONTEXT_QUEUE_TIMEOUT_CAP_SECONDS`, no duplicated hardcoded copies of the
0.15/600.0 constants, test suite literally re-run and matched claim
(716 passed, 1 skipped), `CODEY_MASTER_PLAN.md` honestly states
"MANDATORY RULE-4 CODE-REVIEWER PASS NOT YET RUN, NOT LIVE-VERIFIED" (no
overclaim).

**Real gap found, safe-direction (over-conservative), not logged to
NEW_ISSUES.md:** the context-budget reservation is held for the ENTIRE
in-flight call duration (released only in a `finally` after the HTTP
response fully returns — `core/inference_hybrid.py` infer()'s finally,
`core/plannd.py` get_plan()'s finally, `release_context_budget()` at
resource_gate.py:4463), not just the pre-send TOCTOU gap. But the
server's own `/slots` endpoint (`_fetch_slots_prompt_tokens()`,
polled fresh on every admission check) reflects that SAME request's real
occupancy for the whole time it's actually being processed by the server
— confirmed by `release_context_budget()`'s own docstring
(resource_gate.py:4470+), which explicitly says "the server has already
been sending/processing it the whole time" as its reasoning for why
release-on-return is safe going forward. That means for the full duration
of any admitted call, its own footprint is counted against the ceiling
TWICE — once via the local reservation record, once via /slots' live
occupancy — silently roughly halving the achievable concurrent capacity
vs. what the design's own stated goal ("(c) admission control with (b) as
a queue backstop specifically to preserve concurrency, not crude
serialization") implies. The section's header comment
(resource_gate.py:~3945-3950) frames the ledger as existing "only to
close the TOCTOU window... not to track occupancy for a request's entire
lifetime" — but the actual release timing contradicts that framing; it
DOES track for the entire lifetime.

Not a safety bug (fails toward under-admission, not over-admission — the
safe direction for what NEW-206 was about), and not something to block a
commit outright over. But per CLAUDE.md rule 8 ("anything found outside a
task's scope... gets logged to NEW_ISSUES.md... not silently fixed or
dropped") this needed a ledger entry and didn't get one in this diff —
flag this as the reason for CHANGES REQUESTED if this pattern recurs:
check whether a "release on completion" reservation design was evaluated
against what the real-time authoritative signal (/slots) ALREADY reports
during that same window, not just at the pre-send instant.

**Reusable review technique:** when a design doc claims a lock/reservation
is only used to close a narrow race window ("TOCTOU gap"), check the
ACTUAL release trigger against that claim literally — a reservation
released only at full-completion is a lifetime-long hold, not a
narrow-window one, regardless of how the surrounding comments frame it.
