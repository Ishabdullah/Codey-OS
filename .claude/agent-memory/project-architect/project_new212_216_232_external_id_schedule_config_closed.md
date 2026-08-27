---
name: project-new212-216-232-external-id-schedule-config-closed
description: NEW-212/216/232 closure (customers/leads external_id + schedule_config table) — SQLite ALTER TABLE ADD COLUMN UNIQUE gotcha and this project's first schema-migration mechanism
metadata:
  type: project
---

2026-08-27, code-complete, code-reviewer-APPROVED (one non-blocking
Warning, spun off as `NEW-248`), committed. Ish approved both pending B2
decisions: (1) add `external_id` to `customers`/`leads`, (2)
`schedule-config.json` destination delegated to project-architect's
judgment ("create best place for it"). Test suite re-verified fresh
before commit: 823 passed, 1 skipped.

**Recurring pattern, now 4th occurrence — worth a standing check:** the
code-reviewer's pass found `get_customer_by_external_id()` gates on
`has_permission(PERM_READ_ALL_CUSTOMERS)` directly, while its sibling
`get_customer(id)` gates on `can_access_customer(id)`'s actual (broader,
row-scoped) access logic. This exact shape — a new lookup method's gate
narrower than its sibling's real scoping rule — has now appeared four
times across this project (`NEW-189`, `NEW-194`, `NEW-214`, `NEW-248`).
Worth checking explicitly, every time a task adds a lookup method
alongside an existing one: does the new gate call/reproduce the
sibling's actual access-scoping function, or does it just check that
*a* permission exists? Not yet formalized as a lint/checklist rule, but
should be treated as one going forward.

**Load-bearing technical finding, applies to any future schema-migration
work:** SQLite's `ALTER TABLE ADD COLUMN` rejects `UNIQUE` as an inline
constraint (`sqlite3.OperationalError: Cannot add a UNIQUE column`).
Verified directly, not assumed. Worked around with a bare `TEXT` column
plus a separate `CREATE UNIQUE INDEX IF NOT EXISTS` — functionally
identical (NULLs stay all-distinct), but the index has to be created
*after* the ALTER on a legacy DB, not inside `_SCHEMA_SQL`'s
`executescript` block, or it fails with "no such column" on any
pre-existing DB file that hadn't already had the column added.

**This project had zero schema-versioning/migration mechanism before
this round** — `database.py`'s `_SCHEMA_SQL` was pure `CREATE TABLE IF
NOT EXISTS`, which only ever helps a brand-new DB file. Added
`DatabaseManager._migrate_schema()`, called after `init_schema()`'s
executescript, which checks `PRAGMA table_info()` before each `ALTER
TABLE ADD COLUMN` so it's idempotent and a no-op on fresh DBs. This is
now the pattern for any future "add a column to an existing table"
change on this project — don't just edit `_SCHEMA_SQL` and assume it's
enough; a real on-device DB already exists at
`~/.codey_restoricon/core.db` and won't pick up new columns from
`CREATE TABLE IF NOT EXISTS` alone.

**Verification method for a schema change against a real device DB
(rule 2/5/12 combined):** copy the live DB file to scratch first, run
one `DatabaseManager()` instantiation against the *copy*, and diff
`PRAGMA table_info()` output before/after — this is cheap (SQLite
schema ops on a 258KB file are instant) and is real evidence, unlike a
synthetic `:memory:` test which never exercises the ALTER branch at all
(a fresh in-memory DB already has every column via CREATE TABLE).

**Design choice, may recur:** `schedule_config` got its own dedicated
singleton table + its own permission pair rather than folding into
`business_profile` or reusing its permissions — reasoning was
"identity/onboarding vs. operational config, different domain owner
(scheduling_service.py vs automation_service.py)," and "one
permission pair per table" was the explicit convention this same B2
round had just established one round earlier for the other five new
tables. If a future settings-shaped JSON file shows up needing a
destination, this reasoning chain (singleton pattern like
`business_profile`, but new table if the domain/owner differs, new
permission pair unless the role matrix is provably identical forever)
is the one to reapply.

See also [[project_phase_b2_schema_expansion]] for the original
five-table B2 round this one continues, and NEW-247 (new finding this
round: the new lookup/config methods have no API route yet — Core-only
scope, deliberate not oversight).
