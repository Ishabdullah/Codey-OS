---
name: admin-delete-buttons-parta-users-cascade-changes-requested
description: Admin-dashboard delete-buttons round Part A (Users + Appointment Types) — round1 CHANGES REQUESTED on users half, round2 APPROVED (archive-then-delete fix-forward, NEW-493/494)
metadata:
  type: project
---

**Round 2 verdict (2026-09-11, staged not committed): APPROVED. Cleared for commit.**

Round 1 (below, preserved) found the users-delete half CHANGES REQUESTED —
CASCADE silently wiped terminal `staff_schedules` history, and a test
falsely claimed to have logged the finding. Ish's decision: archive-then-
delete via a new no-FK `staff_schedules_archive` table, not a rebuild.

## Round 2: what was actually verified (not just read)

- **Migration risk (item 1) — genuinely zero, verified via the actual
  startup path, not just "CREATE TABLE IF NOT EXISTS looks additive."**
  `restoricon_core/api/server.py:154` constructs
  `DatabaseManager(db_path or DEFAULT_DB_PATH)` with default
  `init_schema=True`; `DatabaseManager.init_schema()` unconditionally runs
  `conn.executescript(_SCHEMA_SQL)` (the *entire* schema string, all
  `CREATE TABLE IF NOT EXISTS` statements) on every construction — i.e.
  every server start reruns the whole DDL against the live DB file. A new
  `CREATE TABLE IF NOT EXISTS` table needs no entry in `_migrate_schema()`
  (that mechanism is only for `ALTER TABLE ADD COLUMN` on tables that
  already exist) — it just appears on next boot. Confirmed by reading
  `init_schema()`/`_migrate_schema()` docstrings directly, not inferred.
  **General lesson: never accept "it's additive DDL, no migration risk"
  on an implementer's word — trace to the actual `DatabaseManager(...)`
  construction call in the production entry point (`api/server.py` here)
  and confirm `init_schema` actually runs there.** This is the exact
  shape of the NEW-259 trap (code-complete + approved + still a latent
  prod no-op) generalized to schema instead of a missing kwarg.

- **Invariant (item 3) — repo-wide caller grep, not scoped to
  `restoricon_core/ tests/ tools/ ccos/ core/`.** First pass omitted repo
  root / `pipeline/` / `utils/` / `migrate_aigentik.py`. Rerun with no
  directory list at all (`grep -rn "delete_user(" /data/data/.../Codey-OS
  --include=*.py`) confirmed `auth.py:1138` (def) and `routes.py:643`
  (the only call) are the only two non-test hits anywhere in the repo.
  Always grep from repo root with zero path args for an invariant claim
  like this — a directory-scoped grep can silently miss the one caller
  that falsifies it.

- **Atomicity test is a real rollback proof.** Wraps the *real* sqlite3
  connection (`__enter__`/`__exit__` delegate to the real object, so
  actual transaction semantics run) and raises only on the *second*
  `INSERT INTO staff_schedules_archive` call — two rows created
  specifically so failing on insert #1 can't be confused with "never
  ran." Asserts both: live `staff_schedules` rows still present (cascade
  never reached) AND neither archive row survived (including the
  already-succeeded first insert) — genuine partial-write-then-rollback,
  not a vacuous mock.

- **`api_tokens` behavior-change claim (item 8) — verified against the
  actual FK, not taken on the implementer's word.** `api_tokens.user_id`
  carries `FOREIGN KEY ... ON DELETE CASCADE` — orphaned `api_tokens`
  rows for a nonexistent `user_id` are structurally impossible, so the
  new early-`return False` (skipping the now-dead `DELETE FROM
  api_tokens WHERE user_id = ?` for a missing user) really is externally
  invisible. Confirm this kind of "no functional difference" claim by
  reading the referenced table's own FK, don't just accept the
  docstring's reasoning.

- **NEW-493/494 read directly from `NEW_ISSUES.md`** (not the
  implementer's summary) — NEW-493 correctly marked FIXED with the
  original cascade bug AND the archive-table fix both described; NEW-494
  (subcontractors.user_id dangling FK, no FK at all — confirmed by
  reading the table def directly) is Suspected/informational, explicitly
  not fixed this round, correctly out-of-scoped.

- Tests: `pytest tests/test_restoricon_core/` → 571 passed (exact match to
  brief's claim); `pytest tests/test_user_management.py` → 31 passed
  (exact match). Reran independently, verbatim.

- Appointment-types half: fully re-read this round (not diffed against a
  prior commit — round 1 was itself staged-not-committed, so there's no
  committed baseline to `git diff` against). Matches round-1's approved
  content point-for-point (`scheduling_service.py` delete/precheck,
  both new route branches, UI delete button + precheck flow) and its own
  wiring test still passes. Worded as "re-verified on its own merits,"
  not "confirmed byte-identical," since no baseline commit exists to
  diff against.

## Out-of-scope, logged not fixed (not blocking this verdict)

~24 untracked `file:test_doc_upload_*?mode=memory&cache=shared` files
appear in the repo root as a side effect of running the test suite
(traced to `tests/test_restoricon_core/test_b6_5_document_upload.py`,
unrelated file, not part of this diff) — a SQLite `uri=True` connection
string that's supposed to be an in-memory shared-cache DB
(`file::memory:?cache=shared`) is missing the `:memory:` marker, so
each pytest run writes a real ~600KB file to disk instead. Not part of
this diff's scope; should get its own `NEW-###` (Suspected) next time
that test file is touched.
