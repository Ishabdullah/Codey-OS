---
name: b8_4b_project_property_id_approved
description: B8.4b Project.property_id wiring + sales-portal property history panel — APPROVED w/ 2 Warnings
metadata:
  type: project
---

2026-09-17. Reviewed uncommitted diff wiring `projects.property_id` (B8.1
column, previously dead) into `Project`/`CRMService`/routes, plus a
per-property "History" panel in the sales portal Customer 360 modal.
APPROVED, 2 Warnings (neither blocking).

What I verified independently, not just read:
- **Live-reproduced the pre-fix 500** by temporarily deleting
  `create_project`'s new `property_id` existence check and re-running the
  new route test: got a real `sqlite3.IntegrityError` -> uncaught -> 500
  (`{'error': 'Internal server error: FOREIGN KEY constraint failed'}`),
  confirming the bug was real before restoring the file from a scratchpad
  backup.
- Confirmed the existence check runs before the `INSERT`/`with conn:`
  block (not after), so the ValueError genuinely pre-empts the FK
  violation rather than racing it.
- Confirmed the fresh-DB-FK vs migrated-DB-no-FK asymmetry claim directly
  in `database.py` (`_SCHEMA_SQL` has a real FK; the migration tuple is a
  bare `ALTER TABLE ... ADD COLUMN` with no FK, matching implementer's
  claim). The Python-level check is unconditional either way, so the
  claim that this makes the asymmetry "moot for this bug class" holds —
  **but** the docstring's "instead of leaking an uncaught IntegrityError
  as a 500" only describes the fresh-DB case; on a migrated FK-less DB the
  pre-fix failure mode would have been a silent orphan write, not a 500.
  Flagged as a documentation-precision Warning, not a blocker.
- Confirmed `_AUDITABLE_PROJECT_FIELDS`'s `property_id` addition was
  actually required by a pre-existing drift-guard test
  (`test_auditable_project_fields_matches_dataclass`,
  `tests/test_restoricon_core/test_b6_2b2_audit_details.py:326`) that
  asserts the frozenset equals `dataclasses.fields(Project)` — not
  invented scope creep.
- **advisor caught a gap my first pass missed**: never exercised
  `list_projects`'s new `property_id` filter under a restricted role
  (only `ROLE_ADMIN` in the new test file). Live-reproduced with a
  `ROLE_TECHNICIAN` actor, one project assigned to them and one not, both
  on the same property, `list_projects(tech, property_id=prop.id)` →
  correctly returned only the assigned one. No SQL error either, because
  the base query is `"SELECT * FROM projects WHERE 1=1"` — every branch
  can safely append `AND property_id = ?` regardless of which role-branch
  ran first. Lesson: when a new optional filter kwarg is appended to an
  existing role-scoped query builder, don't just trust "the diff mirrors
  an existing pattern" — check the *base* WHERE clause structure directly,
  and test the filter combined with at least one non-privileged role, not
  just the admin path the new tests defaulted to.
- **The "mirrors `project_manager_id`'s [type-check]" claim in the diff
  comment is false, live-verified**: `project_manager_id`'s update_project
  check is bare `not isinstance(x, int)` with no bool guard, so
  `update_project(id, {"project_manager_id": True})` silently succeeds
  and writes `1` (bools are `int` subclasses in Python). The new
  `property_id` check explicitly adds `isinstance(x, bool) or not
  isinstance(x, int)`, so `property_id=True` correctly raises
  `ValueError`. The new code is *stricter*, not a mirror — harmless
  (over-validation, not under-validation) but the record should say
  "stricter than" not "mirrors." Recommend logging the
  `project_manager_id` bool-acceptance gap as a new `NEW-###` per rule 8
  (found outside this round's scope, real, not fixed here) rather than
  leaving it undisclosed.
- `node --check` on the actual extracted `<script>` from a live
  `_render_sales_portal()` call (not string-shape assertions): clean.
- Full suite, proxy vars unset: `2137 passed, 1 skipped, 0 failed` —
  cleanly 8 more than the prior `b8_4a` baseline of 2129 (the 8 new
  `test_b8_4b_project_property_id.py` tests), zero flaky failures this
  run. `git diff --stat -- core/resource_bus.py tests/test_resource_bus.py`
  empty, confirming that file is genuinely untouched by this diff.
- Traced `togglePropertyHistory`/`renderPropertiesPanel` A->B->A manually:
  toggle-closed only fires on a same-id repeat click, so the claimed
  stale-toggle fix is real and the reset points (`renderPropertiesPanel`
  top, `closeCustomer360Modal`) match what's claimed.
- Renamed test
  `test_customer_360_property_panel_has_project_history_but_not_documents`
  is a legitimate scope-tracking update: asserts the new
  `/api/v1/projects?property_id=` fetch is present and the still-descoped
  `/api/v1/documents?property_id=` is absent — not a weakened assertion.

Warning (non-blocking) not previously in this file: `togglePropertyHistory`
has no staleness re-check after its `await fetch`/`await res.json()` — if
a user clicks property A's History then rapidly clicks property B's
before A's fetch resolves, and A's response lands after B's, A's data
renders into the panel while `currentPropertyHistoryId` says B. Single
shared `#propertyHistoryArea`, on-click only, low practical severity, but
worth an `if (currentPropertyHistoryId !== propertyId) return;` guard
right after each `await` if this panel gets revisited.

New pattern for future reviews of this file: when a JS toggle/fetch
function claims to fix a staleness bug, don't just trace the synchronous
open/close branches — check whether there's a re-verification *after* each
`await` too, since that's a separate race from the one usually described.
