---
name: new507-508-509-subcontractor-delete-approved
description: NEW-507 subcontractor delete+active-ref precheck (rule-4 heavy review), NEW-508 onboard modal, NEW-509 401-handling fixes — all APPROVED
metadata:
  type: project
---

2026-09-15 round, all three findings closed clean on round 1, no changes requested.

**NEW-507** (heaviest scrutiny, rule-4 category — new PERM_WRITE_SUBCONTRACTORS
gate + delete route + dual-category active-reference precheck):
- Permission-ordering claim verified by reading the actual code path, not the
  comment: `POST .../delete` calls `actor.has_permission(PERM_WRITE_SUBCONTRACTORS)`
  and raises `PermissionError` BEFORE either unguarded reference query runs.
  `_query_active_work_orders_for_subcontractor` and
  `_query_active_staff_schedules_for_user` (scheduling_service.py:1025, reused
  from the prior Delete-buttons round, not new this round) both do zero
  permission checks — confirmed by reading their bodies directly.
- RBAC asymmetry claim verified against `restoricon_core/auth.py`'s
  `ROLE_PERMISSIONS` dict directly (not the implementer's grep output): exactly
  4 roles hold `PERM_WRITE_SUBCONTRACTORS` (ADMIN, MANAGER, PROJECT_MANAGER,
  AI_AGENT) and all 4 also hold `PERM_READ_STAFF_SCHEDULES` +
  `PERM_READ_OPERATIONS`. SALES has read-only subcontractors (no write);
  TECHNICIAN has neither.
- Terminal work-order status set `('completed','verified','cancelled')`
  confirmed literal-identical to the one already used at operations_service.py:279
  (QUALITY_INSPECTION guard), and is a proper subset of the 7-value
  `work_orders.status` CHECK constraint in database.py.
- `subcontractors.user_id` confirmed to have zero FK constraint (re-verified
  NEW-494 independently by reading the CREATE TABLE directly); `work_orders
  .assigned_subcontractor_id` confirmed `ON DELETE SET NULL` — bare `DELETE
  FROM subcontractors` is mechanically safe, no archive step needed.
- New dedicated test file (`test_new507_subcontractor_delete.py`, 16 tests,
  all read and all run) includes a genuinely good negative-control test —
  `test_delete_rbac_403_before_any_db_read_no_data_leak` — that proves an
  unprivileged actor gets a bare 403 with no itemized schedule data leaked in
  the body, then separately re-runs as admin to prove the reference check
  still fires for a privileged actor. This is exactly the right shape of test
  for a permission-ordering claim; future rounds with a similar claim should
  ask for this same two-actor pattern if it's missing.

**NEW-508** (onboard modal): payload is a fixed two-key object literal built
manually in JS (`{company_name, primary_trade}`), never a spread of form
state, so the route's unguarded `Subcontractor(**json_body)` (pre-existing,
not touched this round) can't be handed a stray key that 500s.

**NEW-509** (two 401 fixes): `loadSubcontractors()` gained the same
`if (res.status === 401) { logoutUser(); return; }` line already used by
`loadStaffSchedules()`; `loadDocuments()`'s call to the nonexistent `logout()`
was corrected to `logoutUser()`. Grepped all 19 `async function load*`
functions in web_surfaces.py — only these two plus the pre-existing
loadStaffSchedules now have 401 handling; the other ~16 remain untouched,
matching the explicitly out-of-scope note in NEW-509's ledger entry (no scope
creep).

**Colspan/escaping/JS-syntax**: all Subcontractors-tab `colspan="5"` sites
bumped to `"6"` (verified via full-file grep bounded to that tab's line
range), no stray `"5"` left in that tab. New delete button's onclick uses the
same `${escapeHtml(JSON.stringify(x))}` pattern as `deleteUser`/
`deleteAppointmentType` (NEW-496 precedent). `test_web_surfaces_js_syntax.py`
(9 tests) passes — the claimed self-caught `.join('\n\n')` single-backslash
bug (this file's known failure class, NEW-503) is not present in the final
diff; confirmed the file is a plain (non-raw, non-f) triple-quoted Python
string, so `\\n` in source → literal `\n` (JS escape) in output, correct.

Full verification re-run (not trusted from implementer's report):
`tests/test_restoricon_core/ tests/test_user_management.py` → 663 passed;
full `tests/` → 1825 passed, 1 skipped (221s). Both matched the implementer's
claimed numbers exactly.

**Verdict: APPROVED, all three, no round 2 needed.** See also
[[new227_new222_new237_cleanup_approved]] and
[[new489_subcontractors_tab_route_fix_approved]] for the precedent chain this
round builds on (NEW-486 FK gap → NEW-489 route fix → this round's
NEW-507/508/509).
