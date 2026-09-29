---
name: b8_16_phase3_split_work_order_changes_requested
description: B8.16 Phase 3 (split_work_order, SPLIT status, work_orders CHECK migration) — round 1 CHANGES REQUESTED, real roll-up double-count found live
metadata:
  type: project
---

2026-09-29. `OperationsService.split_work_order` + `WorkOrderStatus.SPLIT` +
`_migrate_work_orders_status_constraint()` (full-table-rebuild CHECK
migration, mirrors `_migrate_users_role_constraint()`). Migration procedure,
legacy-DB-with-data test, partition logic, `parent_work_order_id` round-trip,
RBAC grants, `Invoice` billing isolation, and NEW-676/677/678 ledger entries
were all independently re-verified and are genuine — diff-read alone would
have approved this.

**What diff-read missed, advisor caught, then I live-reproduced:**
1. **(Critical/blocking) Roll-up double-count is reachable in ONE request,
   no race needed.** `split_work_order` validates trade/indices/partition/
   sum-tolerance up front but never validates `assigned_subcontractor_id`
   existence before the children-creation loop. If `splits[1]` names a
   bogus subcontractor id, `dispatch_work_order` raises after child 0 is
   already committed and BEFORE the parent is zeroed (by design — children
   first, parent zeroed last, to keep failure "recoverable"). Result: 2
   orphaned children + an un-zeroed parent, all with real `total_cost` —
   `get_project_summary`'s unfiltered sum roll-up permanently doubles
   (500 -> 1000 in my repro). The docstring frames this failure mode as
   benign/recoverable and never mentions the roll-up consequence — a
   money-path docstring overclaim, same class as B8.7a/NEW-625. Fix:
   validate every `assigned_subcontractor_id` exists (`SELECT 1 FROM
   subcontractors WHERE id=?`) in the pre-write validation block, before
   any child is created. DNC/compliance rejections inside
   `dispatch_work_order` still aren't fully pre-validated by this fix —
   docstring needs to say so and this needs a real `NEW-###` (not folded
   into NEW-675's generic no-transaction disclosure, which doesn't name a
   concrete wrong-dollar consequence).
2. **(Warning) New SPLIT immutability guard in `update_work_order` runs
   BEFORE the `ROLE_TECHNICIAN`/`ROLE_SUBCONTRACTOR` ownership-narrowing
   branches**, not after. Live-repro: a technician assigned to zero
   projects can pass an arbitrary split parent's id and gets
   `ValueError("...has been split...")` instead of the `PermissionError`
   they got pre-round — a genuine new existence+status oracle (NEW-568
   "undisclosed 404/behavior regression" shape). Fix is a reorder, not a
   rewrite: move both SPLIT checks after the role-narrowing blocks.
3. **(Warning) Final parent UPDATE has no `AND status = 'draft'` /
   rowcount check** — two concurrent `split_work_order` calls on the same
   DRAFT parent can both pass validation and both zero it, permanently
   doubling children against one parent. Low probability (single admin,
   no UI button yet) but cheap to close given this project's history with
   double-admission races (B8.12b, NEW-631/632, etc).

**Technique reinforced:** the advisor caught this by tracing the actual
failure path through `dispatch_work_order`'s validation order (existence
check happens inside the loop, not before it) rather than trusting the
docstring's own "children first is recoverable" reasoning — which was true
for the *parent* but silently false for the *roll-up*. A live repro (not
just code-reading) confirmed it in under 5 minutes. Also reinforces
`[[frontend_search_must_include_py_files]]`-style lesson: always trace one
level past the function under review into what it calls (here,
`dispatch_work_order`'s own validation order) rather than trusting the
caller's docstring characterization of what that callee can do.

See also [[b8_16_phase2_intake_orchestrator_round2_approved]] (same file,
prior phase, also caught a real money-attribution bug + commission
double-payout risk on first pass).
