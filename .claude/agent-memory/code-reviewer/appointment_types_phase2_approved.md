---
name: appointment-types-phase2-approved
description: Final scheduling round Phase 2 — appointment_types table/model/service/routes + appointments.appointment_type_id; APPROVED w/ warnings r1
metadata:
  type: project
---

Phase 2 of final scheduling round (2026-09-11, staged not committed at review). Adds `appointment_types` table (multi-row, AUTOINCREMENT id, seeded Emergency/Standard estimate/Consultation @ max_concurrent 1) + bare-INTEGER `appointments.appointment_type_id` (service-type axis, SEPARATE from the untouched `appointment_type` call/in_person modality column). Data foundation for Phase 4 booking-concurrency enforcement.

**Verdict: APPROVED, no blockers.** Migration traced independently and holds:
- legacy path: ALTER runs, seed skipped on sqlite_master guard, executescript creates table, seed fires on 2nd _migrate_schema pass
- fresh path: existing_columns empty -> ALTER skipped, DDL creates column, seed on pass 2
- re-open: COUNT==3 -> no-op. Test `test_migration_creates_table_and_seeds_defaults_once` genuinely proves it (db.close() between two DatabaseManager on same tmp file, asserts count stays 3).
- INSERT placeholders 23/23/23 aligned, appointment_type_id in matching slot. equipment.current_project_id bare-INTEGER precedent real (database.py:1021). Route collision ruled out (`appointment-types` never matches `== "/api/v1/appointments"` / `startswith("/api/v1/appointments/")`). int() on bad path id -> ValueError -> 400 via handler at routes.py:2188. submit_public_booking 12-col explicit list safe (new col NULL). 474 passed.

**Warnings handed back (non-blocking):**
- `update_appointment_type` omits `fields=` in build_audit_details while its sibling `update_appointment` passes `fields=_AUDITABLE_APPOINTMENT_FIELDS` 5 lines away — convention break vs the b6.2b canonicalized-55-sites pattern. Harmless today (all 8 AppointmentType fields benign, both sides same builder).
- `max_concurrent` / `name` have no CHECK / non-empty / UNIQUE guard; table is always CREATE TABLE (never ALTER) so constraints WERE available. `max_concurrent=-5` and blank/dup names accepted via POST. This is the table Phase 4 concurrency reads.
- update route silently no-ops on unknown/typo'd keys (`max_concurent` -> 200, no change) while create route 400s on unknown keys — asymmetry inside one diff, same class as silent-no-op patch bug. Suggested fix: ignore {id,created_at,updated_at}, 400 on rest.
- RBAC: reuses PERM_*_SCHEDULE_CONFIG, so ROLE_AI_AGENT can create/rename/deactivate business service types (test_route_round_trip proves the grant). Defensible but confirm intended vs new PERM_*_APPOINTMENT_TYPES (project has 2 logged role-vs-permission leaks).

**Rule-8 / NEW_ISSUES.md items:** (a) submit_public_booking still stuffs `service_type` into notes/title text, not wired to appointment_type_id now that the table exists; (b) COUNT(*)==0 seed guard resurrects 3 defaults if a future delete endpoint empties the table (latent, no delete path today).
