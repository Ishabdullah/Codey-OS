---
name: new135-136-swap-claim-race-approved
description: NEW-135/NEW-136 swap-claim double-admission race fix (core/resource_gate.py, commits 3513661+f7511bb) — APPROVED, closes the mandatory rule-4 gap these were committed without
metadata:
  type: project
---

Both commits reviewed post-hoc (committed without a code-reviewer pass
first, explicitly flagged by the implementing session as a rule-4 gap).
Verdict: **APPROVED**, closing that gap.

**What made this solid:**
- `reserved_swap_bytes` accounting inside `reserve_slot()` sits in the
  exact same locked block as the pre-existing RAM-side
  `reserved`/`committed` sums — read-check-write fully covered, not a
  partial-lock reintroduction of the race.
- New `swap_bytes_claimed` field uses the same PENDING-only filter as the
  already-approved RAM-side `reserved_bytes` pattern
  (`total_reserved_bytes()`), so there's no separate "clear on release"
  step needed — a RESIDENT or removed slot simply stops being summed.
  This is the kind of thing that looks like a leak risk on first read
  (see [[resource_gate_74a_subtaskC2_swap_assist_wiring_approved]]'s
  own flagged-but-then-fixed version of this same gap) but isn't, once
  you check the filter the summing function actually uses.
- Only 2 real callers of `can_admit()` exist (`reserve_slot()`,
  `would_model_fit_decision()`) — same full-caller-enumeration result as
  C2's review. `would_model_fit_decision()` forces
  `enable_swap_assist=False` by default so its branch never executes;
  `can_dispatch_task()`'s separate swap-assist consumer is honestly
  disclosed as NOT fixed (registers no slot, nothing to sum against) in
  both the code docstring and NEW_ISSUES.md — not hidden.
- The advisor-review follow-up (`f7511bb`) added exactly the test the
  advisor asked for: a wiring test that pre-loads a PENDING slot's claim
  via `register_slot()` with no hand-fed parameter. I independently
  reproduced the "fails if the wiring line is deleted" claim myself
  (hand-removed `reserved_swap_bytes=reserved_swap` from
  `reserve_slot()`'s `can_admit()` call, reran the single test, got
  `assert True is False` exactly as predicted, restored the file, `diff`
  confirmed clean restoration) — the standard technique from
  [[new12_swap_lock_sequential_swap_rejected]], still worth applying
  every time a "we added a regression test that proves the fix is wired
  in" claim shows up.
- `669 passed, 1 skipped` reproduced via a literal `python3 -m pytest
  tests/ -q` run, matching the commit message exactly.
- Docs (`NEW_ISSUES.md`, `CODEY_MASTER_PLAN.md`) cross-checked against
  the diff and found accurate — no overclaim, residual gaps stated
  plainly, both entries correctly flagged themselves as pending this
  exact rule-4 pass before this review.

**Non-blocking note carried forward:** `MAX_SWAP_ASSIST_BYTES` is
correctly untouched (still 6.50GiB per M1-F) — the fix only changes how
concurrent PENDING claims are accounted against that fixed cap, not the
cap's value. Don't confuse it with `MAX_CONCURRENT_MODEL_BUDGET_BYTES`
(7.00GiB) — a different constant on a different axis (concurrent-model
RAM budget vs. swap-assist ceiling), a mixup the review task prompt
itself made.
