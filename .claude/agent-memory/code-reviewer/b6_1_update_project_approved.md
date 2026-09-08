---
name: b6-1-update-project-approved
description: B6.1 CRMService.update_project + POST /projects/{id}/update + two-perm reassignment model — APPROVED
metadata:
  type: project
---

Rule-4 RBAC review, B6.1. **APPROVED.** 271 tests pass (full scope re-run), 28 new.

Verified:
- `_actor_may_reassign_project_staff(actor, row)` has NO `actor.role` branch — pure
  permission keying (ANY-perm bypass, else scoped-perm requires `pm_id == actor.user_id`).
  NEW-194 shape avoided. `has_permission` honors custom `false` override (custom over role).
- Role matrix confirmed live: admin/manager both perms; project_manager scoped only;
  sales/technician/customer/ai_agent none. ai_agent lacks PERM_WRITE_PROJECTS so it's
  blocked at the base gate, not just the reassignment gate.
- All 22 ALLOWED_PROJECT_UPDATE_FIELDS map to real `projects` columns; stage/status/
  customer_id/id/timestamps correctly excluded. No schema migration, no new deps (sqlite3 stdlib).
- Raw `SELECT *` pre-update read (not get_project); row is sqlite3.Row (row_factory set),
  `row[col]` string indexing works. PRAGMA foreign_keys=ON per-connection (db.py:898) so
  bad project_manager_id FK → IntegrityError → ValueError → route 400. `with conn:` rolls back.
- Route: no collision (GET-one needs no-slash-after-prefix; operations/finance/portal
  distinct prefixes). Global handlers map PermissionError→403, ValueError→400.
- Negative-control test present and effective: sales user w/ custom scoped perm reassigns
  own-managed project (would fail if code checked role=="project_manager"). Audit nested
  changed_fields shape asserted; unchanged-value-not-logged asserted; ANY=false fallback asserted.

Non-blocking (coordinator should log per rule 8):
- `return self.get_project(project_id, actor)` after commit can raise PermissionError to a
  write-capable/read-refused actor *after* the write landed — same shape as update_customer,
  existing convention.
- True (customer-unmasked) financials written into audit `details.changed_fields` — acceptable,
  audit read is admin/manager gated.
- `updated_at` bumps on pure no-op update.
