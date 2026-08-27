---
name: restoricon-core-new212-216-232-external-id-schedule-config-migration-approved
description: First schema-migration mechanism in this project (_migrate_schema()) + customers/leads external_id + schedule_config table — approved w/ 1 warning
metadata:
  type: project
---

Reviewed 2026-08-27: `restoricon_core/database.py` (new
`DatabaseManager._migrate_schema()` — this project's first-ever
schema-migration mechanism), `external_id TEXT` on `customers`/`leads`
(+ separate `CREATE UNIQUE INDEX`, since SQLite rejects `ALTER TABLE ADD
COLUMN ... UNIQUE`), new `schedule_config` singleton table, RBAC lookup
methods, new permission pair. **Approved**, one non-blocking Warning.

Verified directly, not from the implementer's summary:
- `_migrate_schema()` correctness: runs *after* `init_schema()`'s
  `executescript` (so it sees the table from a legacy DB); gates every
  `ALTER TABLE ADD COLUMN` on a `PRAGMA table_info()` existence check
  first, so a fresh DB (which already has the column via `_SCHEMA_SQL`'s
  `CREATE TABLE`) makes it a true no-op, and a second open of an
  already-migrated legacy DB doesn't raise "duplicate column name" — hand
  re-ran the project's own `test_external_id_migration_adds_column_to_legacy_db`
  logic conceptually and via the real suite; also independently
  constructed the same scenario (open once, reopen with a new
  `DatabaseManager`) and confirmed no error. `init_schema()` (and hence
  `_migrate_schema()`) runs once per `DatabaseManager()` instantiation,
  and `DatabaseManager` is a long-lived singleton per process (API
  server's `__init__`, migration CLI's `main`, never per-request) — so
  this is not a per-connection/per-request performance concern.
- **Real on-device DB genuinely NOT touched**: independently opened
  `~/.codey_restoricon/core.db` (258KB, confirmed real mtime) directly
  with `sqlite3` in Python — no `external_id` column on `customers`/
  `leads`, no `idx_customers_external_id`/`idx_leads_external_id`, no
  `schedule_config` table. The implementer's claim of testing "against a
  copy, not the live file" holds; if they'd actually run the migration
  against the real file, this direct read would have shown it.
- UNIQUE-index NULL semantics: independently confirmed (and the
  project's own new test does too) that SQLite's UNIQUE index treats
  multiple `NULL`s as distinct — two customers with `external_id=NULL`
  insert fine, a real duplicate string raises `IntegrityError`.
- `~/Aigentik-CLI/data/schedule-config.json` read directly (rule 12) —
  field names/defaults/shape (`working_hours` per weekday,
  `default_duration_minutes=30`, `buffer_minutes=15`,
  `booking_window_days=365`, `duration_by_relationship={}`) match
  `ScheduleConfig`/`schedule_config` DDL exactly, byte-for-byte.
- `NEW-247` (no API routes yet) confirmed accurate — grepped
  `restoricon_core/api/routes.py` directly for `external_id`/
  `schedule_config`, zero hits.
- Zero touches to `~/Codey-Aigentik`/`~/Aigentik-CLI` — grepped the full
  diff, all matches are doc/comment references, no actual script/path
  writes.
- `823 passed, 1 skipped` reproduced literally via
  `python -m pytest tests/ -q`, matching the claim exactly.
- NEW-212/NEW-216/NEW-232/NEW-247 ledger entries and
  `CODEY_MASTER_PLAN.md`'s closure note read in full — all consistent
  with the actual diff, no overclaiming, "blocker discharged" vs "task
  built" distinction on NEW-232 correctly preserved.

**Warning found (not blocking):** `get_customer_by_external_id()` gates
on `has_permission(PERM_READ_ALL_CUSTOMERS)` directly, but the sibling
`get_customer(id)` gates on `can_access_customer(id)`, which has a
special case: a `ROLE_CUSTOMER` actor may access **their own** customer
record (`self.customer_id == target_customer_id`) even without
`PERM_READ_ALL_CUSTOMERS`. Reproduced live: a `ROLE_CUSTOMER` actor with
`customer_id` set to their own record's id can call `get_customer(own_id)`
successfully but gets `PermissionError` from
`get_customer_by_external_id(own_ext_id)` even for their own row. Not
live-exploitable today (no API route yet — `NEW-247` — and no evidence
`ROLE_CUSTOMER` would ever call this internal lookup), same "one caller
away" shape as `NEW-189`/`NEW-194`/`NEW-214`. `get_lead_by_external_id()`
has no equivalent issue since there is no single-lead-by-id method with
row-level scoping to diverge from (only `list_leads`, gated the same way
`PERM_READ_LEADS` is used there). Flag for a future `NEW-2xx` before this
lookup gets a real caller — either drop the top-level permission gate
and delegate to `get_customer(row["id"], actor)`'s own check (which
already re-checks correctly), or extend `can_access_customer`-style
logic to the external_id path directly.

**Technique reinforced:** for a schema-migration round specifically,
independently opening the *real* on-device DB file (read-only, via a
separate Python one-liner) rather than trusting "verified against a copy"
is cheap and catches the worst possible outcome (a migration silently
run against production data) directly — don't just read the implementer's
pasted before/after output, reproduce it.
