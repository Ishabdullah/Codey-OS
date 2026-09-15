---
name: new487-assigned-user-id-appointment-approved
description: NEW-487 assigned_user_id column on Appointment (schema + service validation + audit + calendar UI) — APPROVED after resolving a 34-test full-suite scare that was actually a sandbox proxy artifact
metadata:
  type: project
---

Full NEW-487 diff (`restoricon_core/database.py`, `models.py`,
`services/scheduling_service.py`, `services/audit_service.py`,
`api/web_surfaces.py`, plus 3 test files) — APPROVED 2026-09-15.

Verified directly, not from implementer's summary:
- Migration: bare `INTEGER` column (no FK), matches `appointment_type_id`
  precedent exactly; `_migrate_schema()` tuple entry present; legacy-DB
  test (`test_appointments_assigned_user_id_migration_adds_column_to_legacy_db`)
  actually exercises a pre-existing DB file + a second `DatabaseManager()`
  open for idempotency — ran it standalone, passes.
- INSERT column list/placeholders/params: counted by hand, 24/24/24,
  `assigned_user_id` at position 13 in all three — no positional drift.
- `create_appointment`/`update_appointment` both validate
  `assigned_user_id` against `SELECT 1 FROM users WHERE id = ?` when
  non-None; `None` (unassign) skips the check cleanly — confirmed via
  `test_assigned_user_id_round_trips_and_is_audited`'s explicit
  None-update case and two dedicated "unknown id raises" tests.
- `ALLOWED_UPDATE_FIELDS` and `_AUDITABLE_APPOINTMENT_FIELDS` both updated
  — this is the exact "forgot the allow-list" bug class ([[new498...]]
  precedent per task brief); a real audit-diff test proves
  `changed_fields["assigned_user_id"]["new"]` appears, not just "other
  audit tests still pass."
- `upsert_appointment` has no separate write path — delegates to
  create/update, so validation isn't bypassable through that route.
- Web UI: null-safety ternary is at the `openCalendarItem` call site, not
  inside `calUserName()` (confirmed by reading `calUserName` — unchanged,
  still assumes non-null, other callers pass non-nullable `s.user_id`).
  `calFilteredAppointments()` genuinely filters by `assigned_user_id` now
  (not just a caption relabel) — confirmed by reading the function body
  and a test that great regex-slices the function and asserts both
  `calFilterPerson` and `a.assigned_user_id` appear inside it.
- Routes: no route-level allow-list exists for appointments; `Appointment(**json_body)`
  picks up the new dataclass field automatically, confirmed by reading
  routes.py directly.

The only real scare this round was the test-suite discrepancy — see
[[sandbox_http_proxy_urllib_405_env_artifact]]. Fully resolved: same 34
failures with and without the diff, root-caused to ambient
HTTP_PROXY/HTTPS_PROXY env vars in this sandbox breaking urllib.request
loopback calls specifically. With those unset, full suite is 683 passed /
0 failed with the diff applied.
