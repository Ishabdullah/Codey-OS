---
name: new187-swap-dispatch-fail-closed-round2-approved
description: NEW-187 can_dispatch_task() read-failure direction fix + docstring wording correction, confirmatory round 2 — APPROVED
metadata:
  type: project
---

Round 1 (same-day, 2026-08-26) rejected NEW-187's `can_dispatch_task()`
fix for two reasons: (1) the read-failure except-branch substituted
`reserved_swap_for_dispatch = 0` on an unreadable ledger — the MORE
permissive reading, backwards for an admission gate, inconsistent with
the sibling `CODEY_SWAP_ASSIST_ADMISSION` handler and `reserve_slot()`'s
own fail-closed read of the same ledger; (2) the docstring/NEW_ISSUES.md
claimed `can_dispatch_task()` "reads the ledger, never writes to it" —
false, since `total_reserved_swap_bytes()` defaults to
`list_slots(reap_dead=True)`, which mutates the shared slot store under
lock when reaping dead PIDs.

Round 2 fix verified correct by direct read (not just docstring claims):
- except-branch now sets `swap_assist_enabled = False` (matches sibling
  handler exactly), never substitutes a permissive `0`.
- Control flow uses TWO separate `if swap_assist_enabled:` blocks — one
  gates the try/except read (assigns `reserved_swap_for_dispatch` only on
  success), the second (gating the actual
  `compute_swap_assisted_headroom_bytes()` call that reads the variable)
  is only reachable if the flag is still `True`, i.e. the read succeeded.
  No dead/unreachable reference, no NameError path — confirmed by
  grepping both use sites (lines ~2576 assign, ~2596 use) and reading the
  surrounding structure directly, not trusting the docstring's claim.
- Test renamed to
  `test_can_dispatch_task_new187_reserved_swap_read_failure_fails_closed`,
  asserts `allowed is False` / `dispatched_via_swap is False` on an
  injected `OSError`; monkeypatches `rg.total_reserved_swap_bytes`, which
  the module-level call site resolves via `globals()` at call time, so
  the patch is effective (same-module global-function-call monkeypatch
  pattern, works here).
- Docstring and NEW_ISSUES.md `NEW-187` entry both corrected to "never
  registers a durable claim, though its reaping side-effect does mutate
  the shared store" — verified by reading both, not just the summary.
- Real test runs pasted: `tests/test_resource_gate.py` → 200 passed;
  full suite (`--ignore=tests/test_restoricon_core`) → 671 passed, 1
  skipped, matching the count both NEW_ISSUES.md and
  CODEY_MASTER_PLAN.md claim.
- CODEY_MASTER_PLAN.md's status trail is accurate and non-overclaiming:
  explicitly says "code-complete... a follow-up confirmatory pass is
  still needed" at the point this review started — did not prematurely
  mark itself approved before an independent pass actually happened.

Verdict: APPROVED. Closes NEW-187's own review chain. Does NOT close
7.4a as a whole — NEW-140's remaining model-independent content and
NEW-188's live-verification gap are untouched by this fix and explicitly
called out as still-open in the same doc section; don't conflate the
two when this memory is recalled later.
