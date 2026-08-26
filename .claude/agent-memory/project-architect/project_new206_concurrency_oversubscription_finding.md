---
name: project-new206-concurrency-oversubscription-finding
description: Live concurrency-oversubscription test at n_ctx=8192 found hard all-request failure; escalated to Ish as §8 Q11; corrected scope after reading llama.cpp source
metadata:
  type: project
---

2026-08-26: Phase A1's concurrency test ran live against real `codey-start`
at `CODEY_N_CTX=8192` (not production's 65536 — infeasible wall-clock).
Result: genuine concurrent decoding confirmed (two slots simultaneously via
`/slots`), but when combined prompt demand (8491 tokens) exceeded the
8192-token pool, BOTH in-flight requests failed hard (HTTP 500) after a
~12-minute KV-fragmentation retry cascade — no queuing, no graceful
degradation, no truncation-and-continue. Logged as `NEW-206`, escalated to
Ish as new `CODEY_MASTER_PLAN.md` §8 Q11 (options a-d, none picked
unilaterally) because it bears on §1.4's single-shared-model architecture
assumption.

**Correction made mid-round, important for any follow-up:** the advisor
caught that the first draft over-claimed "pool-size-independent by
construction" as proof the finding generalizes to 65536. Reading the real
allocator (`~/llama.cpp/src/llama-kv-cache.cpp:894-1084`, `find_slot()`)
confirmed the underlying mechanism IS a genuine contiguity/fragmentation
requirement (pool-size-independent in principle) — but the test itself
already had combined demand OVER 100% of the pool before generation even
started, so it cannot separate "trivially fails past total capacity" (true
at any pool size, not a novel finding) from "fails via fragmentation even
UNDER nominal capacity" (the real, more consequential, still-untested
production risk). Also untested: prefill-time failure only — a
during-generation collision (requests that fit at admission, collide
later) is a distinct, unexamined failure surface.

**Why:** this project's rule 12 ("never assume — read the artifact") and
the advisor process both caught the same category of error mid-round:
inferring a mechanism's generality from its structural description rather
than checking whether the specific test actually exercised that
generality. All four docs (NEW_ISSUES.md, CODEY_MASTER_PLAN.md §6.2 row +
Appendix A + §8 Q11, PROJECT_LOG.md) were corrected in the same round to
state the narrower, source-grounded claim instead of the more sweeping one.

**How to apply:** any follow-up 65536 re-run of this test must be
deliberately designed to test UNDER-capacity combined demand (not just a
bigger-pool repeat of the same over-100% scenario) and/or a
during-generation collision, or it will only re-confirm the trivial case
and leave the actual open question — does fragmentation bite realistic
daemon+TUI loads well under 65536 — still unanswered. See [[project_round22_new7_scoping]]-style precedent: pre-register what a test needs to distinguish before running it, not after.
