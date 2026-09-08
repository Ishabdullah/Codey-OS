---
name: new_issues_cleanup_batch3_role_vs_permission_leak
description: NEW_ISSUES.md ledger closeout batch 3 (crm/scheduling/automation, NEW-238/239/303/306/308/218) — round1 CHANGES REQUESTED, live-reproduced HTTP-reachable notes leak
metadata:
  type: project
---

Batch 3 of the NEW_ISSUES.md project-wide closeout (crm_service.py,
scheduling_service.py, automation_service.py + 3 test files) — round1
CHANGES REQUESTED.

**Critical, live-reproduced:** `update_customer`'s NEW-306 fix switched its
return path from `self.get_customer()` (role-gated, redacts `notes` for
ROLE_CUSTOMER at crm_service.py:168) to a raw `self._row_to_customer(row)`
call (no role param, no redaction at all). The diff's own comment argued
this was safe because "ROLE_CUSTOMER never holds PERM_WRITE_CUSTOMERS" —
checked only against the static `ROLE_PERMISSIONS` table, not the
*effective* permission set `AuthContext.has_permission()` actually
evaluates (`custom_permissions` dict is checked FIRST, before role
fallback — auth.py:634-641). `set_user_permissions()` is an ordinary admin
action that can grant `PERM_WRITE_CUSTOMERS` to a `ROLE_CUSTOMER` user
(the permission is in `PERMISSIONS_CATALOG`, so validation accepts it).
Confirmed HTTP-reachable, not synthetic: `authenticate_token()` (the real
session path) populates `custom_permissions` from the DB, and
`routes.py:655` serializes `update_customer`'s return straight to the JSON
response body. Live negative control (real `set_user_permissions` +
`authenticate_token`-shaped AuthContext + real `update_customer`) printed
the actual secret notes string. Compare: the equivalent NEW-306 fix on
`update_project`'s return path was done correctly — it calls
`_row_to_project(row, actor.role)`, byte-identical to what `get_project`
does — because that redaction logic is role-parameterized. The customer
one wasn't, because `_row_to_customer` has no role param at all; the
implementer used the role-unaware function instead of adding the
equivalent inline `actor.role == ROLE_CUSTOMER` check.

**General pattern to keep checking**: any "safe because role X never has
permission Y" argument must be verified against the actual runtime
`has_permission()` path (which checks `custom_permissions` dict first),
not the static role→permission table alone. Same underlying shape as
[[new233_257_comms_idempotency_role_vs_permission_leak]] and NEW-194 — this
project has a recurring bug class where a redaction/gate is role-keyed but
the actual admission/write-gate is permission-keyed, and a custom-permission
grant decouples them. Always grep `set_user_permissions`/`custom_permissions`
reachability before accepting a "this role never has this permission" claim.

**Two lesser findings, same round:**
- NEW-303's existence-check code in `create_project` (unlike the correctly-
  ordered `update_project` sibling) has no type-check before
  `set(assigned_employees) - found`; a dict element now raises a raw
  `sqlite3.ProgrammingError` that didn't exist pre-diff (previously
  `json.dumps` on the same malformed list would have succeeded silently).
  The implementer's own stated reasoning for reordering `update_project`
  ("don't let a bad element reach the existence check's set()/IN-clause")
  applies identically here and wasn't applied.
- This batch is a "NEW_ISSUES.md ledger closeout" by task framing, but
  `git diff --stat -- NEW_ISSUES.md` was empty — none of NEW-238/239/303/
  306/308/218 were actually marked closed in the ledger. Always check this
  diff scope by default on ledger-closeout tasks (same lesson as
  [[u31_codey_n_ctx_override_changes_requested]] and
  [[resource_gate_new97_plannd_registration_approved]]).

Verified clean in this round: parameterized SQL (no injection), NEW-308
type-check-before-existence-check ordering in `update_project` genuinely
matches the diff's claimed order, NEW-308 field coverage vs
`ALLOWED_PROJECT_UPDATE_FIELDS` is complete (no gap), `_after_project`
unconditionally bound before `return` (no NEW-259-shaped UnboundLocalError),
NEW-218's INSERT param binding genuinely changed from `now,now` to the
object's own timestamp attrs in all three services.
