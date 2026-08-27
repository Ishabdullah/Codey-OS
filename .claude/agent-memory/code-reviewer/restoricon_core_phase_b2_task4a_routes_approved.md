---
name: restoricon_core_phase_b2_task4a_routes_approved
description: Phase B2 task 4a (17 new HTTP routes for subcontractors/appointments/automation_rules/business_profile/do_not_contact) — approved, 2 non-blocking Warnings
metadata:
  type: project
---

Reviewed 2026-08-27: `restoricon_core/api/routes.py` (+152), `api/server.py`
(+9), `tests/test_restoricon_core/test_api.py` (+285, 6 new test functions).
CODEY_MASTER_PLAN.md §6.4 task 4a. **Approved.**

Verified directly (not from implementer's summary):
- All 17 routes match the spec's route table (line ~2471-2487) one-for-one:
  same path, same service call, same param mapping, same falsy/error-return
  convention (404 vs 400 vs bare-bool). No PUT/DELETE introduced, no
  by-external-id GET routes, no get-rule-by-id route (closes NEW-219 as
  "correctly absent," not silently added).
- All 17 target service methods (`crm_service.py`/`scheduling_service.py`/
  `automation_service.py`) gate on `actor.has_permission(...)` before any DB
  touch — checked every one by hand across all three files.
- **Read-but-not-write role probe (the check that actually matters for this
  diff, beyond the all-permissions-denied technician test already in the
  suite):** `auth.py`'s matrix has `sales`/`project_manager` holding read
  but not write on some of the 10 new perms. Hand-built a live `sales` user
  against a real running `RestoriconAPIServer`, POSTed to
  `/api/v1/subcontractors` and `/api/v1/automation-rules` with *complete*
  bodies — both correctly returned 403 via the global `PermissionError`
  handler, not a 500. This is the sharper test than the bundled
  all-five-denied technician test, which only proves the empty-permission
  case works and can't distinguish "no route calls has_permission" from
  "permission gate present but read/write split broken."
- `server.py`: `SchedulingService`/`AutomationService` constructed with the
  same `self.db`/`self.audit_service` instances as `CRMService` — no second
  disconnected `DatabaseManager`. `APIRouter(` still has exactly one
  construction site repo-wide (independently re-grepped).
- NEW-220 (DNC ambiguity): tested and documented as unresolved-on-purpose
  (`not-an-email-or-phone` -> `blocked: False` on check, `400` on add) —
  not silently "fixed" beyond the round's scope.
- NEW-221 pattern (`Model(**json_body)` -> TypeError -> 500 on bad body):
  the 3 new call sites (Subcontractor/Appointment/AutomationRule/
  BusinessProfile construction) are byte-identical in shape to the 8
  pre-existing ones (Customer/Lead/Opportunity/etc.) — no new instance of
  the bug, just the same pre-existing pattern reused.
- 838 passed, 1 skipped, reproduced myself; not fabricated.

**Warnings (non-blocking):**
1. Test-count baseline confusion across three sources: task prompt claimed
   "770 passed," `CODEY_MASTER_PLAN.md` §6.4's task-4a spec claimed a "764"
   baseline recorded the same day, but this diff's own delta is exactly
   +6 tests (verified via `--collect-only`: HEAD's `test_api.py` had 2 tests,
   now has 8). Neither 764 nor 770 + 6 gets anywhere near the actual 838 —
   meaning HEAD (before this diff) was already ~832, not 764/770. This is
   drift from *other* same-day commits (concurrency/lease-registry work
   landing between when the 764 figure was recorded and when this diff was
   authored), not a fabrication inside this diff. Still: whoever writes the
   PROJECT_LOG entry for this round must use the real delta (832 -> 838),
   not the stale 764/770 figures — same doc-accuracy class as u31/NEW-212/
   NEW-218's "plausible but not re-derived" numbers.
2. `path.startswith("/api/v1/subcontractors/") and method == "GET"` will
   also match a mistaken `GET /api/v1/subcontractors/{id}/qualification`
   (or any appointment/rule sibling) and try `int("qualification")`, which
   raises `ValueError` -> 400 (not a 500, not a stack leak) rather than a
   clean 404. Not introduced by this diff — it's inherent to the
   `startswith`-based routing style already used throughout the file for
   every other resource with an action-suffix route — so it's a
   pre-existing shape, not a new defect. Logged as a Suggestion, not
   required to fix.

**Technique reinforced:** when a permission matrix has roles with
read-without-write (or vice versa) for a permission pair the new routes
gate on, the standard "one hostile role, all denied" negative test is not
sufficient to prove the write gate specifically works — build a live probe
with a role that has read but not write and hit the POST/action route with
a *complete* body (so a TypeError from bad-body construction can't produce
a false-positive 403).
