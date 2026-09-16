---
name: new492-494-519-staff-schedule-get-and-delete-user-nullout-approved
description: NEW-492 GET-by-id route + NEW-494/NEW-519 delete_user() FK-less null-out — approved, but implementer's "pre-existing, out of scope" framing on a raw-exception leak understated it
metadata:
  type: project
---

Two independent diffs, both APPROVED 2026-09-16 (uncommitted at review time):
1. `SchedulingService.get_staff_schedule()` + `GET /api/v1/staff-schedules/{id}` route (routes.py:1609-1618, scheduling_service.py:1060-1073).
2. Two `UPDATE ... SET ... = NULL` statements added inside `delete_user()`'s existing `with conn:` transaction (auth.py:1207-1214) to null out `subcontractors.user_id` / `appointments.assigned_user_id`, both confirmed FK-less by reading the DDL directly (bare `ALTER TABLE ... ADD COLUMN` with no `REFERENCES`).

**Bug pattern worth remembering: "pre-existing, out of scope" claims about a bug class need re-verification against the NEW code, not just the old code.** The implementer reported a raw-Python-exception-string leak (`int("abc")` → `"invalid literal for int() with base 10: 'abc'"` in a 400 body) as pre-existing on the sibling PATCH/DELETE routes for the same resource, unrelated to this diff. A direct repro against the live `api_server` fixture showed the **new GET route this diff adds reproduces the identical bug** (`int(path.split("/")[-1])` at routes.py:1614, same pattern as PATCH/DELETE) — so one of the three now-affected call sites is new code from this round, not purely inherited. Same class the project already fixed for query params via `_parse_int_query_param` (NEW-505).

**Why:** it would have been easy to accept the implementer's framing and log the finding as 100% pre-existing, which is wrong and would understate scope in the ledger.

**How to apply:** whenever an implementer reports "I found this bug too, but it's pre-existing / out of scope," reproduce it against every code path the *current* diff touches, not just the path they originally noticed it on. If the new code shares the same vulnerable pattern, the ledger entry must say so explicitly — don't let a true-but-incomplete claim get recorded as fully pre-existing.

Related: [[sandbox_http_proxy_urllib_405_env_artifact]] (test suite proxy-var gotcha, still applies — full suite reproduced exactly `1881 passed, 1 skipped` after unsetting proxy vars).

Also worth remembering for FK-less-column sweeps generally: `employees.user_id` looks similar to the two columns fixed here but actually already has a proper `FOREIGN KEY ... ON DELETE SET NULL` in the DDL (database.py:775) — don't assume every `*_user_id`-shaped column needs the same treatment without reading its own DDL line. Conversely, don't assume a two-column sweep is exhaustive either — this round flagged (Suspected, unresolved) several other `*_user_id`/`*_by_id` columns in database.py that weren't individually checked.
