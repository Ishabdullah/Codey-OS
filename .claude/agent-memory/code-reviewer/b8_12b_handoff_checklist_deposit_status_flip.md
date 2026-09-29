---
name: b8_12b_handoff_checklist_deposit_status_flip
description: B8.12b production handoff checklist — deposit-tagging guard confirmed to flip invoice status to 'paid' and zero balance_due while real balance remains owed, silently vanishing from AR aging/total_ar reports
metadata:
  type: project
---

B8.12b (production_handoff_checklists table + deposit-tagging + completion
guard) — APPROVED round1 (all 6 files + 26 new tests, full suite 2420→2446
matched verbatim, zero regressions). RBAC/idempotency/route-dispatch/
UNIQUE-constraint/escapeHtml-convention/node --check all independently
re-verified clean, not just re-read.

**The one real finding, escalated beyond what the implementer disclosed**:
implementer self-disclosed a "balance_due understated" interaction
(`create_invoice` bakes `deposit_amount` into `balance_due` at creation;
`record_payment`'s `total_paid = deposit_amount + sum(payments)` then
double-counts it if a payment is later recorded for that same deposit).
My first live repro only checked the *number* (understated by exactly
deposit_amount) and nearly stopped there. Advisor caught the real
discriminator: with `amount=10000, deposit_amount=5000`, recording a single
$5000 `payment_type='deposit'` payment (the guard's own designed happy
path) flips `status` to `'paid'` and `balance_due` to `0.0` — confirmed
live — while the customer has only actually paid half. Grepping consumers
confirmed this isn't cosmetic: `finance_service.get_ar_aging` filters
`WHERE status IN ('sent','partially_paid','overdue') AND balance_due > 0`
and `analytics_search_service`'s executive-dashboard `total_ar` sums
`WHERE balance_due > 0` — both silently exclude the invoice's real
remaining balance the moment this bug fires. This is a genuine Critical:
real AR/collections reporting corruption, triggered on essentially every
"happy path" use of the very guard this round ships, not an edge case.

**Why still APPROVED, not CHANGES REQUESTED**: the guard's own access
control (RBAC, idempotency, contract/items conditions) is fully correct;
the corrupted value is a downstream side effect of `record_payment`'s
pre-existing balance formula, which this round explicitly did not touch
and honestly disclosed as out of scope. This matches this project's own
precedent (NEW-575 in [[b8_6a_estimates_contracts_rep_ownership_approved]],
the B8.4b disclosed regression) for approving structurally-sound work with
a disclosed, pre-existing downstream gap — but flagged this one as
Critical/urgent, not routine, because it's now confirmed to corrupt live
financial reporting on the primary intended path, not a rare edge case.

**Reusable lesson (the one to actually remember)**: when a round adds a
*sanctioned workflow* that instructs staff to produce a specific new input
shape (here: "tag this payment `payment_type='deposit'`"), don't just
check whether the new field/mechanism itself is safe — trace what
*pre-existing* downstream formula now unconditionally consumes that new
input on the happy path, and whether flipping a status enum removes rows
from a report's WHERE clause. A latent formula bug that previously fired
only on incidental/inconsistent data entry can become a certainty once a
new round tells everyone to always do the exact thing that triggers it.
Test the boundary case (payment amount that pushes the double-counted
total to zero or negative), not just a mid-range case that only produces
a wrong-but-nonzero number — the zero/negative boundary is where a
`status` enum or a report's `WHERE balance_due > 0` filter silently
changes behavior in a way a "the number is off by X" framing hides.
