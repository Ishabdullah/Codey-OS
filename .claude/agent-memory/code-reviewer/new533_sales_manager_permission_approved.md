---
name: new533-sales-manager-permission-approved
description: NEW-533 sales-manager PERM_READ_TEAM_SALES_DATA narrowing round — APPROVED, real server-side enforcement verified by tracing route bypass attempts
metadata:
  type: project
---

2026-09-16. NEW-533 fix (`restoricon_core/auth.py`, `crm_service.py`,
`web_surfaces.py`) — new `PERM_READ_TEAM_SALES_DATA` permission narrows
`list_leads`/`list_opportunities`/`list_tasks`/`get_lead`/`get_opportunity`/
`get_task` to own-assignee + unclaimed-pool (`assigned_user_id IS NULL`)
unless the actor holds the permission. APPROVED after independent
verification, not just reading the diff.

**What made this verifiable, not just plausible:** traced the actual API
route handlers (`restoricon_core/api/routes.py`) for `GET /api/v1/leads`
etc. and confirmed a direct API call with `?assigned_user_id=<other>`
cannot bypass the narrowing — the route passes the *requested* id through
to the service, but `CRMService._scoped_assignee_filter` ignores the
request and forces `actor.user_id` for non-privileged actors. This is the
right thing to check: a narrowing that's only enforced in the route-param
parsing (not the service layer) would be trivially bypassable by calling
the API directly instead of using the rendered portal JS.

**Audit after-image fix (re-derivation of the NEW-306 pattern) verified
correct by tracing, not just trusting the comment:** `update_lead/
update_opportunity/update_task` used to re-read via `self.get_lead(id,
actor)` to build the audit `after` image. Once `get_lead` gained the
narrowing check, that re-read would return `None` for a narrowed actor
reassigning `assigned_user_id` AWAY from themselves (they no longer "own"
it post-reassignment) — silently recording a false `after=None` /
cleared-field audit entry for the exact event being audited. Fixed by
building the after-image from the already-updated in-memory object
instead of re-reading through the permission gate. Confirmed via a
dedicated test (`test_reassign_away_from_self_still_records_audit_after_image`)
that actually asserts on `changed_fields['assigned_user_id']` from a real
audit-log query, not a mock.

**New pattern for this codebase:** any read-gate added to a `get_X`
method that's *also* reused internally for an after-image re-read in
`update_X` can silently corrupt the audit trail for the exact actors/
events the new gate is narrowing — check every internal caller of a
`get_X` whenever `get_X` itself gains actor-dependent filtering, not just
external API callers.

**Minor disclosed quirk, judged non-blocking:** the sales-portal's
"Viewing: Whole Team"/"Viewing: My Own" banner reads
`user.custom_permissions['read:team_sales_data']` client-side, but
admin/manager/ai_agent get the permission via **role default**, not
`custom_permissions` (confirmed via `/api/v1/auth/me` returning
`user.to_dict()`, which only exposes `custom_permissions`, not merged
effective permissions). So if an admin/manager navigates directly to
`/sales` (route has no role gate, `GET /sales` serves the page to anyone
with a valid token — confirmed in `routes.py`), the banner mislabels
"My Own" while the underlying `/api/v1/leads` fetch actually returns the
whole team. Cosmetic only — comment explicitly says "never an
access-control point" and no downstream logic branches on it. Real
enforcement is 100% server-side and correct. Worth a one-line fix
someday (check role-default permission too) but not worth blocking this
round over.

See also [[new515_516_allowlist_and_warning_log_approved]] for the
project's general pattern of trusting-but-verifying implementer safety
claims via direct tracing rather than re-reading the comment.
