---
name: new587-proposal-unscoped-customer-approved
description: NEW-587 fix (proposal route uses _get_customer_unscoped instead of actor-narrowed get_customer) — APPROVED, one undisclosed-but-currently-benign permission bypass found
metadata:
  type: project
---

2026-09-22, commit not yet made (reviewed pre-commit). Fix for NEW-587: the
B8.6c proposal route (`GET /api/v1/estimates/<id>/proposal`) called
`get_customer(estimate.customer_id, actor)` after already calling
`get_estimate(est_id, actor)` — two *independent* rep-ownership narrowing
checks on the same actor, so a rep who legitimately owned the estimate but
whose customer got reassigned to someone else (via NEW-568's own admin
reassign feature) got a spurious 404. Fix: new `CRMService._get_customer_unscoped(customer_id)`
(no actor, no narrowing at all) used only at that one route call site, on the
premise that `get_estimate`'s own narrowing already answered "can this actor
see this record."

Verified directly (not just diff-read):
- Exactly one `_row_to_customer` staticmethod exists (grep across whole file,
  not just diff hunks) — implementer's own admitted near-miss (accidental
  duplicate definition shadowing) did NOT make it into the final diff.
- `get_customer`'s refactor to call `_row_to_customer` is field-for-field
  identical to the deleted hand-rolled constructor (all 19 fields incl.
  `notes=row["notes"]` unconditionally, `ROLE_CUSTOMER` clearing done
  separately after the call) — no silent notes/tags/custom_fields regression.
- `get_estimate` (crm_service.py ~3065) genuinely has NO unclaimed-pool
  (assigned_user_id IS NULL) carve-out, confirmed by reading the source, unlike
  `get_customer` which does have one (`row["assigned_user_id"] is not None and
  != actor.user_id` — NULL passes through). So get_estimate is strictly at
  least as strict on the ownership axis.
- `_get_customer_unscoped` has exactly one call site (`routes.py:1228`),
  confirmed by grep across `restoricon_core/` + `tests/`.
- `render_estimate_proposal` (web_surfaces.py) never reads `customer.notes` at
  all — the unconditional notes-clearing in the new helper is defense-in-depth,
  not load-bearing, and is still correctly implemented.
- Differential live repro (not just the new test's own assertions per the
  B8.5b lesson): added a scratch assertion inline in the test file, ran it,
  then reverted via `cp` from a pre-edit backup — confirmed
  `crm.get_customer(cust.id, actor_sales)` really is `None` post-reassignment
  (proving the pre-fix bug is real) while `_get_customer_unscoped` returns the
  row. Restored the test file to the implementer's original diff afterward
  (`git diff --stat` matched exactly, 53 insertions, before and after).
- Full suite reproduced verbatim: `2205 passed, 1 skipped, 69 warnings in
  260.75s` — matches the implementer's claim exactly. Note: this run did NOT
  hang despite [[full_suite_pytest_hang]]-style prior notes; ran to completion
  in background this time. Scoped `tests/test_restoricon_core/` also passed
  clean (893 passed) as a faster first check.

**One real finding, non-blocking (Warning, not logged as a new NEW-### since
harmless today):** `get_customer` has TWO gates — `can_access_customer(customer_id)`
(raises `PermissionError` unless `ROLE_CUSTOMER` identity match or actor has
`PERM_READ_ALL_CUSTOMERS`) AND the NEW-568 `assigned_user_id` narrowing.
`_get_customer_unscoped` bypasses *both*, not just the narrowing — the
docstring/comments only discuss bypassing the ownership narrowing, not the
top-level permission gate. Checked empirically (printed `ROLE_PERMISSIONS`):
every role that can reach `get_estimate` successfully today either already
has `PERM_READ_ALL_CUSTOMERS` (admin/manager/sales/sales_manager/project_manager/
ai_agent) or is `ROLE_CUSTOMER` accessing their own already-scoped estimate's
customer (identity match, not permission-based) — so no role can exploit this
bypass today. But it's an *undisclosed* equivalence, not an enforced one: a
future role granted `PERM_READ_ESTIMATES`/`PERM_READ_OWN_ESTIMATES` without
`PERM_READ_ALL_CUSTOMERS` would silently get full customer PII via this route
with nothing catching it. Recommend for next touch: either add a comment
in `_get_customer_unscoped`'s docstring naming the permission-gate bypass
explicitly (not just the ownership narrowing), or add a role-matrix test
asserting "any role with estimate-read also has PERM_READ_ALL_CUSTOMERS."

Minor Suggestion: `routes.py` reaching a `_`-prefixed method
(`self.crm._get_customer_unscoped`) across the route/service boundary is a
mild style break from the rest of the codebase's public-API-only cross-module
calls. Not worth blocking on.

**Verdict: APPROVED.**
