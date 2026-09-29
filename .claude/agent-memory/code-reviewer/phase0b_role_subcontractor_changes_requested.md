---
name: phase0b-role-subcontractor-changes-requested
description: Phase 0b/B8.16 ROLE_SUBCONTRACTOR rollout (auth.py/database.py/operations_service.py) — CHANGES REQUESTED, two live-reproduced Critical permission escapes
metadata:
  type: project
---

Reviewed a stitched-together (two-concurrent-agent-sessions) diff adding a
real `ROLE_SUBCONTRACTOR` role (NEW-641). The CHECK-constraint migration
collision fix (idempotency gate switched from a bare `'sales_manager'`
substring to a quoted `'subcontractor'` role literal, because the same
migration's own `ADD COLUMN subcontractor_id` rewrites
`sqlite_master.sql` and would otherwise false-positive the gate forever)
was correct, well-tested, and verified genuinely non-vacuous by
temporarily reverting the gate to a bare substring check and watching the
new regression test fail with the exact predicted `IntegrityError` before
restoring the real fix. `1290 passed` reproduced verbatim.

Two real, live-reproduced Critical bugs found beyond the diff's own test
suite (see [[b8_14a_new550_executive_dashboard_and_gate_approved]] for the
same discriminator applied here — "does the write mutate the exact column
the narrowing keys on"):

1. **`OperationsService.update_work_order`'s `ROLE_SUBCONTRACTOR` branch
   checks ownership against the CURRENT DB row before the write, but the
   `UPDATE` statement itself still writes `assigned_subcontractor_id`
   straight from the caller-supplied model** — so a subcontractor who owns
   a work order can reassign it to a *different* subcontractor's id in the
   same call, handing the other subcontractor full read/write access to
   it. Live-reproduced end to end (sub A creates+owns WO, sets
   `assigned_subcontractor_id=B`, `update_work_order` succeeds, sub B then
   reads the hijacked WO). This is exactly `PERM_DISPATCH_WORK_ORDERS`
   behavior, which the role's own permission grant explicitly excludes.
   The contrast with the file's own `ROLE_TECHNICIAN` precedent is the
   tell: that branch's docstring says "The `UPDATE` below never writes
   `project_id`" — the scoping column is made immutable in the update
   path by construction. The new `ROLE_SUBCONTRACTOR` branch has no such
   protection. None of the new test file's own update-path tests attempt
   this (they only spoof the field on a WO the actor never owned, which
   trips the *other*, unrelated pre-check branch). Fix: after reading the
   current row, reject when
   `work_order.assigned_subcontractor_id != row["assigned_subcontractor_id"]`
   for a `ROLE_SUBCONTRACTOR` actor, before any write.

2. **`ROLE_PERMISSIONS[ROLE_SUBCONTRACTOR]` grants `PERM_READ_COMPLIANCE`
   with a comment claiming it's scoped to "their own license/
   insurance-on-file status"** — but `BusinessOpsService.list_compliance_items`
   (reachable via `GET /api/v1/compliance/items`) has zero entity-level
   narrowing; any actor holding the permission gets every compliance item
   in the system (any entity_type/entity_id) by omitting the optional
   filter params. Granting this permission to an external subcontractor
   party is a genuine company-wide compliance-data leak (other
   subcontractors'/staff's licenses, insurance, expirations), not the
   narrow self-scoped read the justifying comment describes. No narrowing
   helper for compliance was added anywhere in this diff.

Also verified false: the `ROLE_PERMISSIONS[ROLE_SUBCONTRACTOR]` comment
claims a `get_project()` `PERM_READ_OPERATIONS` over-grant is "logged...
see NEW_ISSUES.md" — grepped `NEW_ISSUES.md` for any 2026-09-27 entry
matching this and found none, and separately confirmed the claim itself
is inaccurate: `get_project()`/`list_projects()` gate on
`PERM_READ_ALL_PROJECTS`/`PERM_READ_OWN_SOLD_PROJECTS`/
`PERM_READ_ASSIGNED_PROJECTS`/`PERM_READ_OWN_PROJECTS` only, none of which
`ROLE_SUBCONTRACTOR` holds — `PERM_READ_OPERATIONS` isn't even checked
there, so the described over-grant doesn't exist at that call site. A
comment overclaiming both "this is logged" (rule 8) and a security fact
that isn't true on inspection — same failure class as the NEW-625 false
comment noted in [[new617_627_contract_signed_at_resolution_approved]].

Warning-level, also live-confirmed: `get_active_work_orders_for_subcontractor`
has no `ROLE_SUBCONTRACTOR` branch at all (only `ROLE_TECHNICIAN` is
narrowed there, per NEW-646's 2026-09-25 fix, predating this role's
existence) — a subcontractor actor can pass any other subcontractor's id
and see their active work orders unfiltered. And `create_work_order`'s
`ROLE_SUBCONTRACTOR` branch has no project-membership check analogous to
`ROLE_TECHNICIAN`'s `_actor_assigned_to_project` — a subcontractor can
inject a work order into any `project_id` in the system as long as they
self-assign it.

Technique note: when a role-permission grant comment says a
call site's over-grant is "not narrowed, logged separately," always grep
the actual call site's gate AND grep `NEW_ISSUES.md` for the claimed
entry — both can be false independently, and this round both were.
