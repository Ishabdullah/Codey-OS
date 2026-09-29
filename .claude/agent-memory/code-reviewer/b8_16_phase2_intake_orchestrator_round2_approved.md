---
name: b8-16-phase2-intake-orchestrator-round2-approved
description: B8.16 Phase 2 submit_work_order_intake round-2 re-review — salesperson_user_id fix confirmed genuine, APPROVED
metadata:
  type: project
---

Round 2 of [[b8_16_phase2_intake_orchestrator_changes_requested]] — APPROVED
2026-09-27 (still uncommitted at review time; commit pending coordinator).

The fix moved the `Invoice(...)` construction to AFTER the create/reuse
customer branches converge on one `customer_id`, with
`assigned_user_id=salesperson_user_id` set unconditionally there — not
"also added to the reuse branch" but structurally a single construction
site, which is a stronger fix than patching each branch separately (no
future branch can reintroduce the asymmetry by accident). Confirmed
`create_invoice`'s inherit-from-customer fallback (`if
invoice.assigned_user_id is None`) is bypassed only because a non-None
value is always supplied here — every other caller passing `None` is
unaffected.

Verification technique worth repeating: the regression test for "reused
customer, different prior rep" used a `prior_rep` actor distinct from the
intake's `sales` actor and asserted `invoice.assigned_user_id !=
prior_rep.user_id` in addition to `== sales.user_id` — this is what rules
out a coincidental-match false pass (invoice value only "looks right"
because it happens to equal the customer's stale value). When reviewing
attribution-parameter tests, check for this three-way discriminator
(new value present, old value absent, old value still intact elsewhere)
rather than a single equality assertion.

Also confirmed here: a "corrected the rationale, did NOT change the
behavior" claim (NEW-673's fail-open comment/doc correction) is only
verifiable by diffing the actual `except` block's control flow, not by
reading the corrected prose — the prose can be perfectly accurate while
a reviewer still needs the code diff to confirm nothing else moved.
Confirmed clean here: `skip_flat_for_portfolio_override = False` in the
except block was untouched.

Full suite: 1313 passed (ran directly, verbatim, matched implementer's
claim). See also [[b8_15_overpayment_credit_approved]] for the B8.x
review-technique index.
