---
name: phase7-part1-subcontractor-link-range-filters-approved
description: Phase 7 Part 1 (subcontractors.user_id link + list_appointments/list_staff_schedules date-range filters) — approved round1
metadata:
  type: project
---

Reviewed 2026-09-11, staged diff (not committed): `restoricon_core/database.py`,
`models.py`, `services/crm_service.py`, `services/audit_service.py`,
`services/scheduling_service.py`, `api/routes.py`, `api/web_surfaces.py`,
new test file, `NEW_ISSUES.md` (NEW-489).

**Verdict: APPROVED.**

What was checked and held up:
- `subcontractors.user_id` bare-INTEGER migration matches the
  `appointments.appointment_type_id` precedent exactly (both `_SCHEMA_SQL`
  and `_migrate_schema()` tuple). Migration test used a real on-disk legacy
  DB (not `:memory:`, which always gets the column via CREATE TABLE and
  can never exercise the ALTER TABLE branch) — correct test design, worth
  reusing as the pattern for any future additive-column test.
- INSERT column list / VALUES placeholder count / params tuple in
  `create_subcontractor` hand-counted at 48/48/48 — lockstep confirmed,
  no repeat of the prior-round `upsert_*` mismatch class of bug.
- `_AUDITABLE_SUBCONTRACTOR_FIELDS` includes `user_id` (audit-diff visibility).
- `update_subcontractor`'s blanket `if value is None: raise ValueError`
  loop runs before any per-field logic, so it genuinely fires for
  `user_id` too — not just claimed, traced in the actual code path. Test
  (`test_subcontractor_update_user_id_rejects_none`) asserts this directly.
- Range filters (`list_appointments`/`list_staff_schedules`): inclusive
  BETWEEN both bounds, one-sided `>=`/`<=`, `substr(start_time,1,10)`
  verified safe against real stored formats — `appointments.start_time`
  is nullable (schema-confirmed, so the NULL-exclusion claim is real, not
  hypothetical) and `staff_schedules.start_time` is `NOT NULL` (also
  schema-confirmed), matching the code comments exactly.
- `list_staff_schedules`'s new `ORDER BY start_time ASC LIMIT 200` default
  is a genuine, reasoned behavior change (roster vs "most recent N" feed)
  with only one caller in the whole codebase (`routes.py`), no Aigentik
  JS caller — verified via grep, no silent breakage.
- NEW-489 (subcontractors admin tab was already dead before this round —
  `loadSubcontractors()` fetches `/api/v1/operations/subcontractors`,
  which doesn't exist; real route is `/api/v1/subcontractors`; row-render
  reads `sc.specialty`/`sc.rating`, neither a real `Subcontractor` field)
  — independently verified via grep of `routes.py` and `models.py`. Fully
  accurate, not overclaimed. This round's new "Linked User" column is
  honestly disclosed as equally inert until NEW-489 is fixed separately —
  good practice, don't let this kind of honest disclosure get flagged as
  a problem in future reviews of the same author's work.
- 528 passed, `python3 -m pytest tests/test_restoricon_core/ -q` reran
  independently, matches claim exactly.

Minor non-blocking note for future rounds: `routes.py`'s `start`/`end`
query-param parsing does `query_params.get("start", [None])[0]` — an
explicitly-empty `?start=` (not absent) yields `""` rather than `None`,
which reaches `substr(...) >= ''` (always-true, harmless but not exactly
"one-sided/absent" semantics). Not exercised by any test, didn't block
approval since it's a harmless no-op, but worth tightening (`or None`)
if a future round touches this code.
