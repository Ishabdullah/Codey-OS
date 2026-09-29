---
name: new613-ar-reconciliation-split-commit-approved
description: NEW-613 AR offset reconciliation (get_ar_net_totals/get_project_ar_net) — APPROVED, cross-agent commit-collision review pattern
metadata:
  type: project
---

NEW-613 (fix two AR aggregates missing the B8.8b-2 financing offset:
get_executive_dashboard's total_ar KPI, and transition_project_stage's
CLOSED-stage gate) — APPROVED round1, 2026-09-25.

**Cross-agent commit-collision review shape**: half the logical change
(operations_service.py's constructor DI + CLOSED-gate rewrite) landed
already-committed inside dd244d5, a commit whose message/review only
covered an unrelated RBAC round (NEW-630/642/647). The NEW-613 hunk
inside that commit had never been reviewed. Reviewed both halves
together as one logical change (`git show <sha> -- <file>` for the
committed half + `git diff` for the rest) rather than treating the
committed half as already-approved just because it shipped in an
approved-looking commit. Watch for this shape again — a genuinely
reviewed commit can still smuggle in an unrelated, unreviewed hunk when
two agents' working trees collide.

**Bisect-broken commit, confirmed via `git worktree add`**: dd244d5 in
isolation (`git worktree add <path> dd244d5`) fails
`test_project_lifecycle_full_canonical_progression` with
`AttributeError: 'FinanceService' object has no attribute
'get_project_ar_net'` — that method didn't exist yet at that commit,
only in the uncommitted NEW-613 working-tree changes at the time. The
commit's own "2531 passed" claim was true-in-local-tree, false-for-the-
commit-in-isolation. Recorded as a documented gap, not fixed by
rewriting history (rule: never amend/rebase without explicit ask) —
the round's commit message calling this out explicitly is the right
remediation, not silent correction.

**Advisor caught two things I hadn't checked**, both resolved clean on
investigation, worth the pattern for next money-code round:
1. CLOSED-gate's invoice filter changed shape (`balance_due > 0 AND
   status NOT IN ('void','paid')` → `status != 'void'` inside the new
   shared helper) — looked like a widened blast radius. Resolved: grep
   confirmed `balance_due = max(0.0, amount - total_paid)` — balance_due
   can never go negative in this codebase, and `status='paid'` only ever
   gets set by the same formula that zeroes balance_due, so the two
   filters are behaviorally equivalent on any row reachable through the
   real write path. (A directly-constructed `Invoice(status="paid",
   balance_due=999)` passed to `create_invoice` is a pre-existing,
   already-known gap-class — see B8.3/B8.5b/NEW-631/632 fixture-masks-
   reality memories — and the new code is *more* correct on it, not less.)
2. `_financing_offset_for_project_unlinked` (NULL-invoice_id financing
   rows) is newly reachable from a state-mutating action
   (transition_project_stage) where before it only fed a read-only
   report (get_project_pnl). The arithmetic itself was already proven
   correct by B8.8b-2's original review; what's new is the reachability,
   and it's untested at this specific call site (every NEW-613 test uses
   `invoice_id=inv.id`-linked records only). Logged as a Warning, not a
   blocker — matches the project's [[b8_8b2_financing_ar_offset_approved]]
   precedent of documented-but-inert-until-now NULL-invoice_id gaps.

Full suite: 2425 passed, 1 skipped, ran to completion (no hang, no
resource_bus flake this run) — matched implementer's claim verbatim.
Pure-refactor proof (`git diff --stat` on both pre-existing test files
empty) verified directly, not trusted.
