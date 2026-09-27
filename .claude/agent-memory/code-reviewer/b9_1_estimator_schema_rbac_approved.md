# Phase B9.1 Codey-Estimator schema/migration/RBAC — APPROVED (2026-09-27)

Rule-4 review (schema/RBAC). Full independent verification, not trust-the-summary:

- **Byte-identity claim** (`_ESTIMATES_TABLE_V2_SQL` vs `_SCHEMA_SQL`'s `estimates`
  block): re-verified programmatically myself (normalize only the
  `CREATE TABLE IF NOT EXISTS estimates (` vs `CREATE TABLE estimates (` opener) —
  genuinely byte-identical. Same pattern that drifted before
  (`_USERS_TABLE_WIDENED_ROLE_SQL`) did NOT drift here.
- **`_migrate_estimates_table_v2()`**: traced side-by-side against
  `_migrate_users_role_constraint()` (the precedent it claims to follow) line
  by line — idempotency gate (`PRAGMA table_info` check) genuinely precedes
  every destructive statement; `PRAGMA foreign_keys` OFF/ON genuinely outside
  `with conn:`; `BEGIN IMMEDIATE` genuinely wraps steps 3-6; `sqlite_sequence`
  restore is plain `DELETE`+`INSERT`, not `INSERT OR REPLACE`; `PRAGMA
  foreign_key_check` result is actually checked and raises. All matched.
- **`new_cols` fix in `_migrate_users_role_constraint`**: confirmed it's a
  single, narrow addition (`requires_estimate_approval`) — the column is
  added by an earlier ADD-COLUMN migration in the SAME `_migrate_schema()`
  call before this rebuild runs, so without the fix the guard would have
  been a false-positive "incompatible schema" abort on every legacy DB from
  now on. Fix does not loosen the check for any other unknown column.
- **CHECK-on-ADD-COLUMN**: independently reproduced myself (this sandbox is
  also SQLite 3.45.1, not the device's 3.53.4) against a real
  `DatabaseManager`-built legacy-shaped DB, real `ALTER TABLE ADD COLUMN ...
  CHECK`, and an actual failing INSERT *and* UPDATE with an out-of-range
  value post-ALTER. Feature (CHECK constraints on ADD COLUMN) has been
  stable since SQLite 3.25 (2018) — very low residual risk 3.53.4 differs;
  correctly left to the live-verification checklist rather than asserted as
  certain.
- **RBAC**: verified programmatically (not by eyeballing) that
  `ROLE_AI_AGENT`'s set has zero overlap with
  `{PERM_SEND_ESTIMATES, PERM_APPROVE_ESTIMATES, PERM_REASSIGN_ESTIMATES,
  PERM_MANAGE_PRICE_BOOK}`, and that `ROLE_SALES_MANAGER`'s new derived set
  is exactly `ROLE_SALES | {existing perm} | {3 new perms}` with nothing
  dropped. Matched every one of the 8 roles against the spec table by
  locating each hunk's containing role block via pre-diff line numbers
  (not just "looks about right").
- **`PERMISSIONS_CATALOG` block name**: it's genuinely `"estimates_contracts"`,
  not `"estimates"` (the implementer's flag was correct) — but the six new
  entries landed in that same correct block, right next to
  `PERM_READ_ESTIMATES`/`PERM_WRITE_ESTIMATES`/`PERM_READ_OWN_ESTIMATES`.
- **Test suite**: ran fresh myself, 748 passed / 1 failed. Independently
  confirmed the failure (`test_document_streaming_upload`, missing
  `python_multipart` module) is pre-existing and unrelated by `git stash`
  + re-running that one test against the pre-diff tree — identical failure.
- **Scope**: `git diff --stat` touched only `database.py`, `auth.py`,
  `test_auth.py`, plus the two ledger docs and the new spec doc — no
  service/API/UI/pricing files.

**New pattern worth remembering**: this project's docs
(`codey_estimator_schema.md`, `CODEY_MASTER_PLAN.md`) were written claiming
"code-reviewer approved" *before* the actual review ran. Treat that as an
unverified claim, same as an implementer's "tests pass" — it happened to
turn out true this time, but don't let a doc's own self-description
substitute for actually doing the review.
