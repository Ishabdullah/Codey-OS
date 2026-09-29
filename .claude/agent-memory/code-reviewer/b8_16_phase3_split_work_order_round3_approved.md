---
name: b8_16_phase3_split_work_order_round3_approved
description: B8.16 Phase 3 split_work_order round 3 — APPROVED (final); compliance-path fix genuine, but ledger docs mischaracterized the disclosed residual
metadata:
  type: project
---

2026-09-29, round 3 (final) review of [[b8_16_phase3_split_work_order_round2_changes_requested]].

**Code verdict: APPROVED.** The compliance-pre-check fix is genuine and closes
the second half of the roll-up-double-count Critical. Verified directly:
- Read `_check_subcontractor_compliance` (new shared helper) and confirmed
  `dispatch_work_order`'s inline DNC/COI/license blocks were replaced with a
  call to it, not just wrapped — same wording, same `override_compliance`
  semantics. Ran `-k dispatch` (11 tests incl. override/bypass-flag edge
  cases) — all pass, extraction didn't change behavior.
- `split_work_order`'s new pre-check loop calls existence-check THEN
  `_check_subcontractor_compliance(..., override_compliance=False,
  error_prefix=...)` for every `assigned_subcontractor_id`, before any
  child is created.
- **Did the revert-and-confirm-discrimination check myself** (not just
  trusted the implementer's claim): commented out the compliance call only
  (kept round 2's existence check), reran
  `test_split_rejects_dnc_subcontractor_before_any_child_created` — it
  failed on `assert [wo.id for wo in work_orders] == [parent.id]` (got
  `[1,2,3]`), i.e. genuinely fails on the post-condition, not on the
  `pytest.raises` itself. Restored the fix, reran — 20/20 pass.
- Full suite: 1333 passed (`tests/test_restoricon_core/`, proxy vars
  unset), matches both the implementer's claim and PROJECT_LOG.md's stated
  count exactly.
- Checked the *other* reused callee in the loop too, per round 2's own
  "check every failure mode of a reused method" lesson —
  `create_work_order` is called before `dispatch_work_order` for every
  entry. Its only raise conditions (empty title/trade, PermissionError for
  TECHNICIAN/SUBCONTRACTOR roles) are all already foreclosed by
  `split_work_order`'s own upstream checks (trade non-empty-checked in the
  partition loop; title derived from the parent's own already-valid title;
  PERM_DISPATCH_WORK_ORDERS holders are never TECHNICIAN/SUBCONTRACTOR).
  No third Critical hiding in `create_work_order`.

**Doc-only issues found, NOT bundled into the code verdict** (same routing
as round 2's stale-ledger flag — say so plainly so the coordinator doesn't
misroute this back to the implementer as a failed code review):
1. **The three ledgers contradict each other on the disclosed residual.**
   `NEW_ISSUES.md`'s `NEW-679` entry names TWO residuals and says the
   second (a T0/T1 race: pre-check reads subcontractor compliance once
   up front, `dispatch_work_order`'s own re-read inside the loop happens
   later, so a subcontractor flipped to DNC or whose COI expires in that
   window is still reachable) "IS still subcontractor-validation-shaped."
   But `PROJECT_LOG.md` and `CODEY_MASTER_PLAN.md` both compress this to
   a single residual described as "a genuine mid-loop DB error, unrelated
   to subcontractor validation" — which both omits the T0/T1 race
   entirely and mischaracterizes it. Attributing it to `NEW-675` rather
   than minting a new id is a defensible call (same root cause: no
   wrapping transaction) — the problem is the *description*, not the
   attribution.
2. **Round 2's docstring finding was never actually fixed.** `split_
   work_order`'s "Ordering" docstring paragraph still reads "Failing
   earlier... is visibly recoverable" with no mention of the roll-up
   double-count, even in the now-narrowed residual (T0/T1) case an
   operator could actually still hit. Round 2's own review note said this
   "needs its own disclosure, same as NEW-679 was for existence" — still
   open in round 3.

**Technique confirmed again:** trace one level into every reused callee in
a validation-then-write loop, not just the one the original finding named.
Also: when a finding's residual gets folded into an existing NEW-### rather
than minted fresh, diff all three ledger docs against each other, not just
each one individually — a doc can be internally consistent and still
contradict a sibling doc describing the same finding.

**Staging list for this three-round diff (exact paths, no `git add -A`):**
```
CODEY_MASTER_PLAN.md
NEW_ISSUES.md
PROJECT_LOG.md
restoricon_core/api/routes.py
restoricon_core/database.py
restoricon_core/models.py
restoricon_core/services/audit_service.py
restoricon_core/services/operations_service.py
tests/test_restoricon_core/test_b8_16_phase3_split_work_order.py   (new)
```
`.claude/agent-memory/code-reviewer/*` files are the code-reviewer's own
memory artifacts, not part of the B8.16 diff — stage/commit those
separately at the coordinator's discretion.

See also [[b8_16_phase3_split_work_order_changes_requested]] (round 1),
[[b8_16_phase3_split_work_order_round2_changes_requested]] (round 2).
