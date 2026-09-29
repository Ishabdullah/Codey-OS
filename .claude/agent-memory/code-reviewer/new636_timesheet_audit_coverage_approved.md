---
name: new636-timesheet-audit-coverage-approved
description: NEW-636 timesheet audit trail fix (submit/approve) — APPROVED round1, comment-vs-code verification catch
metadata:
  type: project
---

2026-09-25. `restoricon_core/services/business_ops_service.py`
submit_timesheet/approve_timesheet gained audit.log() calls; APPROVED round1
after full verification (65/65 tests re-run verbatim, precedent claims
checked against source, no new RBAC disclosure).

**Pattern worth repeating**: a drift-guard comment asserted `Timesheet.hourly_rate`
is an independent "job-costing transaction amount," distinct from the
employee's standing compensation rate that `_AUDITABLE_EMPLOYEE_FIELDS`
deliberately excludes. Both of the comment's *cited comparison facts*
checked out true (PO fields do include subtotal/total_amount; Employee
fields do exclude hourly_rate) — but the *conclusion* was false: reading
`submit_timesheet` a few lines above the audited code showed
`ts.hourly_rate` defaults to `emp_row["hourly_rate"]` when not explicitly
supplied, i.e. it commonly *is* the employee's standing rate. Same shape
as the B8.7b finding already in memory (models.py docstring claiming a DB
CHECK constraint database.py's own comment says doesn't exist): a rationale
comment whose individual factual citations are correct but whose overall
claim is contradicted by code a few lines away that nobody re-read. The
advisor caught this after my first pass verified the literal citations and
stopped there — checking a comment's cited facts is not the same as
checking its conclusion; trace the actual data flow the conclusion depends
on.

**Also relevant**: don't stop a role-based disclosure question at "is this
field now readable by role X" — check whether role X already had access to
the same underlying data through an existing, unrelated path. Here
`PERM_READ_AUDIT_LOG` is strictly narrower than `PERM_READ_HR` (only
Admin/Manager have it, and both already have `PERM_READ_HR` too), so the
new audit-log exposure of `hourly_rate` was redundant with an existing read
path, not a new one — that's what kept it a Warning instead of Critical.

Also confirmed: this codebase has two live, real conventions for
status-transition-only audit writes — `action="update"` (receive_purchase_order,
same-file precedent) and `action="status_change"` (crm_service.py,
operations_service.py, scheduling_service.py — more specific, more common
codebase-wide). `action` is unvalidated free text so this doesn't break
anything, but it means "I grepped for the exact precedent and found none"
claims need a broader grep pattern than the most literal one
(`action="approve"` missed the real match, `action="status_change"` would
have found it). See [[verify_grep_precedent_claims]] pattern generally —
a grep that returns zero hits proves the exact string doesn't exist, not
that no relevant precedent exists.
