---
name: resource-gate-74a-subtaskD-consistency-pass-approved
description: TODO.md 7.4a sub-task D (would_model_fit_decision, can_dispatch_task swap-aware floor, confirm_resident_and_mark_slot docstring note) — APPROVED first pass
metadata:
  type: project
---

D (`core/resource_gate.py`/`core/loader_v2.py`/`tests/test_resource_gate.py`/
`NEW_ISSUES.md`) passed review on its first round — third sub-task in the
7.4a chain to do so after C2 (see
[[resource_gate_74a_subtaskC2_swap_assist_wiring_approved]]).

**What made it solid:**
- D1 (`would_model_fit_decision()` as a new sibling, `would_model_fit()`
  kept as a thin `.admitted` wrapper) genuinely avoids the always-truthy-
  `GateDecision` footgun — verified by reading the actual wrapper code, not
  just the docstring's claim. Confirmed via `grep` that `would_model_fit()`
  has zero live callers anywhere outside `resource_gate.py`/tests (its
  intended consumer, `core/model_tiers.py`, hasn't landed the call yet) —
  so "no caller silently broken" is currently vacuously true, not just
  structurally safe.
- D2's swap-assist branch in `can_dispatch_task()` is nested strictly
  inside the existing `if snapshot.ram_headroom_bytes < DISPATCH_MIN_HEADROOM_BYTES:`
  block, which itself sits after the interactive/thermal/battery `return`s
  — verified by reading the literal line order (interactive → thermal →
  battery → RAM(+swap)), matching C2's own "swap-assist can only override
  its own check" structural guarantee for `can_admit()`.
- The `ValueError`-swallowing divergence in `can_dispatch_task()` (catches
  `_resolve_swap_assist_enabled_default()`'s malformed-env-var raise,
  `can_admit()` does not) was independently verified as justified, not just
  asserted: (1) `core/daemon.py`'s `_process_planner_tasks()` calls
  `_check_dispatch_gate()` → `can_dispatch_task()` at both call sites
  (~1171, ~1219) with no surrounding try/except; (2) the main loop's
  `while self.running:` block (~938) has only a bare `try/finally`, no
  `except` — an uncaught `ValueError` here really would propagate through
  the `finally:` (which unloads the 7B model server) and kill the daemon's
  run coroutine, exactly as claimed. (3) Critically, the fallback direction
  (`swap_assist_enabled = False` on parse failure) is itself the SAFE
  direction — identical to the pre-D2 RAM-only behavior — so this
  divergence can only ever make autonomous dispatch more conservative on a
  malformed config, never more permissive; it's logged at `warning()`, not
  silent. This is a materially different, and defensible, tradeoff from
  `can_admit()`'s explicit-single-load callers (`reserve_slot()`, called
  from `loader_v2.py`/`planner_loader.py` load paths a human/explicit
  action triggers and can see the resulting error), not an inconsistency.
- D3 is genuinely docstring-only — `git diff` shows the only change inside
  `confirm_resident_and_mark_slot()` is an added docstring paragraph; no
  code below it touched.
- New tests are substantive, not tautological: D1's tests separately prove
  hard_reject-vs-headroom-no and budget-ceiling-no-vs-headroom-no
  distinguishability, plus a swap-assisted-yes-vs-RAM-comfortable-yes case
  that checks `admitted_via_swap` stays `False` even with the opt-in flag
  on when RAM alone already passes. D2's tests mirror C2's own rigor:
  exact-byte boundary pairs, a "can't buy arbitrary headroom" capped-still-
  refuses case, an SLMK-floor-gated case that asserts the underlying
  mechanism (not just the decision) returns exactly 0, and three separate
  "swap-assist never overrides interactive/thermal/battery" tests.
- `git diff --stat` (unqualified) confirmed the change is exactly the 4
  claimed files; `git status --short` at review time showed a clean tree
  otherwise (other files visible in the session's opening `gitStatus`
  snapshot — TODO.md, WORK_QUEUE.md, core/orchestrator.py, etc. — had
  already been committed separately by the time of this review; see
  [[working_tree_cross_round_bleed]] for why this needs re-checking each
  time, not assumed from a stale snapshot).
- Full suite: `724 passed, 1 skipped, 68 warnings in 129.60s` — matched the
  implementer's claim verbatim on a literal re-run.
  `tests/test_resource_gate.py` alone: `184 passed in 1.00s`, also matched.

**NEW-135/NEW-136 scoping call — judged defensible:**
TODO.md has a real internal discrepancy: C2's own write-up (line ~1006-1007)
says both findings are "in scope for sub-task D's consistency pass," but
D's own detailed enumerated sub-item list (lines ~1036-1089, the actual
D1/D2/D3 spec) never mentions either finding by name — it only covers
`would_model_fit()`, `can_dispatch_task()`, and
`confirm_resident_and_mark_slot()`. Given the more specific/detailed text
doesn't list them, and both findings were already logged and explicitly
deferred once (during C2, for the same "would require changing sub-task
B's own function signature" reason), declining to fix them here — while
documenting NEW-135's widened blast radius (a second independent consumer
of the uncapped 768MiB cap) in `can_dispatch_task()`'s own docstring — is
consistent, not scope-creeping avoidance. Neither finding is severity-
raising enough to force an unscheduled fix: NEW-135 is a soft race that
self-corrects once real RSS settles, not a crash/correctness bug; NEW-136
is a diagnostics gap (slot record doesn't say how a slot got admitted),
not a functional one.

**Reusable technique for future D/E rounds:** when a task's own scope note
elsewhere in TODO.md says "X is in scope for round N," always cross-check
round N's own *detailed* enumerated sub-item list, not just the forward-
reference — the two can genuinely disagree, and the detailed list is the
better signal of actual mandate.
