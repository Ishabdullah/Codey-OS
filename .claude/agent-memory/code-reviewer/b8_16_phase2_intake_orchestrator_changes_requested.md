---
name: b8-16-phase2-intake-orchestrator-changes-requested
description: B8.16 Phase 2 submit_work_order_intake review — reuse-branch parameter drop broke commission attribution; new bug-pattern class
metadata:
  type: project
---

B8.16 Phase 2 (`CRMService.submit_work_order_intake`, a find-or-create
customer/project orchestrator run under an elevated `intake_system_actor`)
got CHANGES REQUESTED on first review, 2026-09-27.

**New bug pattern for this project: a find-or-create orchestrator applies
a caller-supplied attribution parameter (`salesperson_user_id`) only on
the *create* branch, silently dropping it on the *reuse* branch.** The
existing customer keeps its old `assigned_user_id`; since `create_invoice`
inherits `assigned_user_id` from the customer when none is explicitly
set, every reused-customer intake produced an invoice attributed to the
stale prior owner (or nobody, if unclaimed) instead of the salesperson
named on the intake form — silently wrong commission attribution.
Reproduced live with a standalone script (not the implementer's own
tests): unclaimed existing customer stayed `assigned_user_id=None` after
intake despite `salesperson_user_id` being passed in.

**Why this slipped past the implementer's own 19 tests:** every dedup
test in the new suite (`test_exact_email_match_reuses_customer`, etc.)
asserted `customer_id`/`customer_created` correctness but never checked
`invoice.assigned_user_id` on the *reuse* path — only
`test_assigned_user_id_set_from_salesperson_param_not_actor` checked
attribution, and it only exercises the create branch (no pre-existing
customer). **Lesson: whenever a find-or-create helper has two branches,
grep for which caller-supplied parameters are used on the create branch,
then verify each one is also honored (or explicitly, correctly ignored)
on the reuse branch — do not assume symmetry.**

Also found (Warning, non-blocking): the round-2 portfolio-override
precedence fix's fail-open rationale ("whatever broke this resolution
will almost always break the override block's own identical resolution
too") is factually wrong — the two blocks use separate try/excepts and
separate config reads specifically so they can't share a bug, which means
they also can't be relied on to fail together. A failure isolated to the
precedence block's own try can still let the override block's later,
independent call succeed, recreating the exact double-payout NEW-673 was
meant to prevent, on the error path. Narrow (audit-logged, error-path
only) so non-blocking, but the NEW_ISSUES.md rationale sentence for
NEW-673 needs correcting per rule 6.

Everything else in this round (customer dedup ambiguity logic, NEW-598
non-interaction with the ROLE_ADMIN system actor, create_work_order
narrowing genuinely blocking both roles on a fresh intake project,
audit-trail queryability, commission-widening correctness, gate-1a
no-op proof for 'assessment', NEW-672/674 severity) was traced to source
and verified correct — implementer's disclosure quality on this round
was otherwise high (NEW-672/673/674 all accurately described).

See also: [[b8_15_overpayment_credit_approved]] and the B8.x index in
MEMORY.md for prior CRM/commission review technique notes.
