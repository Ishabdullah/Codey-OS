---
name: phase-b2-task2-migrate-aigentik-extension-closed
description: migrate_aigentik.py extended to customers.json/schedule-config.json, code-complete + code-reviewer-approved + committed 2026-08-27; not yet run with --apply; reviewer self-disclosed an unintended live-DB schema-migration side effect
metadata:
  type: project
---

Extended `restoricon_core/migrate_aigentik.py` (already closed for
`subcontractors`/`appointments`/`automation_rules`/`profile`, see
[[project_phase_b2_task2_migrate_aigentik_closed]]) to also cover
`customers.json` -> `Customer` and `schedule-config.json` ->
`ScheduleConfig`. Code-complete, code-reviewer-approved, committed
2026-08-27. Full suite `829 passed, 1 skipped`.

**Why:** only 8 of customers.json's ~46 fields map cleanly onto
`Customer` columns; everything else (insurance/claim fields especially —
relevant since Restoricon is a restoration business) goes into
`custom_fields["aigentik_raw"]` rather than being dropped or forced into
a column. This produced three follow-on findings, none fixed this round:
`NEW-252` (insurance/claim data opaque, worth a real schema decision),
`NEW-253` (lead-shaped rows in customers.json never reach `leads`),
`NEW-254` (`create_customer()` duplicates the full raw blob into the
permanent, append-only `audit_log` table — inert today, a real concern
once real insurance/claim data flows through).

**Notable process finding — `NEW-255`:** while independently verifying
this round's prior schema work (the `NEW-212`/`NEW-216`/`NEW-232`
closure), the code-reviewer's stated intent was a throwaway DB copy, but
they instantiated `DatabaseManager` directly against the real
`~/.codey_restoricon/core.db`, which auto-ran the schema migration and
added the `schedule_config` TABLE to the live file (258048 -> 270336
bytes). No data rows were written; table creation is idempotent (would
have happened on the next real daemon start anyway). Logged plainly per
rule 5/6, not treated as a data-safety incident but not swept under the
rug either.

**How to apply:** `--apply` against real data was deliberately NOT run
this round — pending a DB backup
(`cp ~/.codey_restoricon/core.db ~/.codey_restoricon/core.db.pre-b2-migration-backup-<timestamp>`)
that Ish/the coordinator runs immediately before the real `--apply`
invocation. Real on-device DB independently confirmed still at 0 rows in
`customers`/`leads`/`schedule_config` as of this round's close, so
`--apply` will be a clean 3-insert + 1-upsert with no dedup risk.

**Cross-round hazard avoided:** a separate, concurrent, not-yet-reviewed
implementer round was modifying `core/daemon.py`/`core/loader_v2.py`
(the `NEW-145`/`NEW-149`/`NEW-155` context-ceiling fix) in the same
working tree during this round's commit. Staged and committed only the
exact files this round touched (never `git add -A`/`git commit -a`) —
see [[feedback_stage_files_by_scope_not_by_dirty_tree]].
