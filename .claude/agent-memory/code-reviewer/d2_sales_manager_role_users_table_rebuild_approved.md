---
name: d2_sales_manager_role_users_table_rebuild_approved
description: D2 ROLE_SALES_MANAGER users-table CHECK-constraint rebuild migration — APPROVED after independent SQLite empirical repro of every claim
metadata:
  type: project
---

2026-09-16, restoricon_core. Reviewed the D2 change (real `ROLE_SALES_MANAGER`
role on top of the NEW-533 permission mechanism) adding
`_migrate_users_role_constraint()` to `database.py` — a full SQLite
table-rebuild of `users` (13 FK-dependent children, 2 with
`ON DELETE CASCADE`) since SQLite can't `ALTER TABLE ... ADD CHECK`.
**APPROVED.** All load-bearing empirical claims in the implementer's
docstring were independently reproduced against this project's real
SQLite (3.53.4) and real `DatabaseManager`, not taken on trust:

- **`PRAGMA legacy_alter_table` nuance the implementer's docstring
  overclaimed slightly**: it does NOT have "no effect regardless of the
  pragma" universally — with `foreign_keys=OFF`, `legacy_alter_table=ON`
  DOES stop `ALTER TABLE ... RENAME` from rewriting children's FK DDL
  text. It only fails to protect you when `foreign_keys=ON` — which is
  exactly this project's real connection config
  (`database.py` line ~1063, every connection). So the practical
  conclusion (the rename-first design is dangerous, avoid it) is correct
  and confirmed disaster-scenario-empirically (a real cascade wipe of
  `api_tokens` under the project's actual `foreign_keys=ON` config), but
  the docstring's "regardless of the pragma" phrasing is imprecise. Flag
  as a Suggestion, not a blocker, next time this docstring is touched.
- `BEGIN IMMEDIATE` atomicity claim: verified myself via a real injected
  mid-rebuild crash (subclassed `sqlite3.Connection.execute` via a
  `factory=` connect hook — `sqlite3.Connection.execute` itself is
  immutable/can't be monkeypatched directly, monkeypatch `sqlite3.connect`
  instead). Confirmed zero leftover temp table and the original `users`
  table fully intact after the crash, and a clean subsequent reopen
  recovers and completes the migration. Note: the shipped test
  `test_users_role_migration_recovers_from_stale_leftover_temp_table`
  does NOT itself inject a real crash — it only pre-seeds a stale leftover
  table and checks recovery from that. My own repro was stronger evidence
  than what shipped; worth suggesting (non-blocking) a real
  injected-crash test be added for future confidence.
- `sqlite_sequence` `INSERT OR REPLACE` non-dedupe claim (no
  UNIQUE/PK on `name`) — verified directly, produces a duplicate row
  instead of replacing.
- Idempotency, cascade-still-fires-after-rebuild, permission-derivation
  correctness (`ROLE_PERMISSIONS[ROLE_SALES_MANAGER] =
  ROLE_PERMISSIONS[ROLE_SALES] | {...}`, not a literal dup), the exactly-3
  `web_surfaces.py` sites, and `routes.py:2001`'s `PERM_READ_ALL_CUSTOMERS`
  OR-fallback covering the new role without an edit — all traced/verified
  directly, all held up.
- Full suite reproduced myself: `1924 passed, 1 skipped in 313.08s`,
  matching the implementer's claim exactly.

**General technique worth reusing**: to inject a mid-transaction crash
into SQLite-backed code for atomicity testing in Python, you cannot
monkeypatch `sqlite3.Connection.execute` (immutable C type) — instead
monkeypatch `sqlite3.connect` to pass `factory=SubclassWithOverriddenExecute`.
Also: `DatabaseManager.get_connection()` caches connections in
`threading.local` keyed by `db_path` string — a crash-testing script that
reopens the same path in the same process must `delattr` the cached
thread-local attr first or the second "clean" open silently reuses the
poisoned connection object from the crashed attempt.

See also [[verify_never_assume]] pattern — this is the class of review
CLAUDE.md rule 12 and rule 4 exist for, and it held up under real testing
this time.
