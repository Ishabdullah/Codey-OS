---
name: b8_16_phase3_split_work_order_round2_changes_requested
description: B8.16 Phase 3 split_work_order round 2 — CHANGES REQUESTED again; NEW-679 fix only closed the existence half of the roll-up-double-count Critical, not the compliance half
metadata:
  type: project
---

2026-09-29, round 2 review of [[b8_16_phase3_split_work_order_changes_requested]].
Two of three round-1 findings were fixed correctly and verified genuine
(permission-oracle reorder in `update_work_order`, confirmed via live grep +
read against `get_work_order`'s RBAC narrowing; concurrency guard on the
final parent-zeroing UPDATE, confirmed via delete-guard-clause-and-rerun
showing DID NOT RAISE, then restore). Both real, both closed.

**The Critical was only half-fixed, and the diff-read alone would have
missed it again.** Round 1's finding was "a bad `assigned_subcontractor_id`
on a later split entry leaves earlier children committed and the parent
un-zeroed, permanently doubling `get_project_summary`'s roll-up."
Implementer's NEW-679 fix pre-validates *existence* of every
`assigned_subcontractor_id` before any child is created — but
`split_work_order`'s children-creation loop still calls
`self.dispatch_work_order(child.id, assigned_subcontractor_id, actor)` with
no `override_compliance` argument (default `False`), and
`dispatch_work_order` raises `ValueError` on DNC status, expired COI, or
inactive license for an EXISTING subcontractor — a check that happens
per-entry, mid-loop, exactly like the existence check did before the fix.
Live-reproduced: real subcontractor with `dnc_status=1`, 2-entry split on a
500.0 parent, first entry's child created successfully, second entry's
`dispatch_work_order` call raises on DNC — result: two orphaned children
(500.0 combined) + un-zeroed parent (500.0) = roll-up reads 1000.0. Same
bug class, same money-path consequence, not closed by the round-1 fix.
Root cause: the implementer patched the discriminator named in the finding
("nonexistent id") rather than the actual invariant needed ("every
per-entry `dispatch_work_order` call in this loop must be guaranteed to
succeed before any child is created" — which requires pre-checking BOTH
existence AND compliance, or restructuring to dispatch only after all
children exist).

**The docstring overclaim from round 1 is also still present verbatim** —
"Failing earlier... is visibly recoverable" still never mentions the
roll-up consequence, and NEW-679's "Still open" paragraph names only
"a genuine DB error on the 2nd child's own INSERT" (an unexpected failure)
as the remaining gap, not the deterministic, caller-triggerable compliance
path. Needs its own disclosure, same as NEW-679 was for existence.

Also confirmed stale-but-not-code-broken: `CODEY_MASTER_PLAN.md` and
`PROJECT_LOG.md`'s Phase 3 entries (written after round 1's build, before
round 2's fixes) say "16 new tests"/"1329 passed"/"pending code-reviewer
sign-off" — now 19 tests/1332 passed, and mention none of round 2's three
fixes or NEW-679. Flagged as a hard pre-commit ledger fix per rule 9, but
explicitly NOT bundled into the code verdict — say so plainly so the
coordinator doesn't misroute a pure-docs gap back to the implementer as if
it were a code rejection.

**Technique reinforced:** when a fix closes a named discriminator (id
doesn't exist) inside a loop that calls a *shared, reused* method
(`dispatch_work_order`) with multiple independent failure modes, check
every failure mode that shared method has, not just the one the original
repro happened to trigger. `dispatch_work_order` has three ValueError
paths (not-found, DNC, compliance) plus a fourth via `override_compliance`
not being threaded through at all — a fix that silences one still leaves
the others live in the exact same reachable position. The advisor caught
this by pointing at the specific unguarded call site
(`self.dispatch_work_order(child.id, assigned_subcontractor_id, actor)`,
no `override_compliance=` kwarg) rather than re-deriving it independently
— worth explicitly checking a reused method's full signature/behavior
against what the caller actually threads through, every time a "closes
the gap" claim is made about one specific input shape.

See also [[b8_16_phase3_split_work_order_changes_requested]] (round 1).
