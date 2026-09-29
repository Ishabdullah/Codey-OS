---
name: new710_estimates_assigned_user_id_rename_bug
description: Merge of main into feat/estimator-phase3-schema — real bug found+fixed in _migrate_estimates_table_v2's legacy-rename logic, full merge independently re-verified and APPROVED
metadata:
  type: project
---

Merge of `main` (~30 commits, incl. the whole B8.16 work-order intake
pipeline) into `feat/estimator-phase3-schema` (B9.1 schema + B9.2
EstimateService, previously reviewed in isolation —
[[b9_1_estimator_schema_rbac_approved]], [[b9_2_round2_branch_divergence_approved]]).

**The headline bug, confirmed genuinely real and genuinely fixed:**
`_migrate_estimates_table_v2()` originally carried
`_LEGACY_COLUMN_RENAMES = {"assigned_user_id": "assigned_to_user_id"}`,
written and grep-verified against this branch ALONE ("nothing reads
`estimates.assigned_user_id`"). That grep was true in isolation and false
the moment `main`'s independent B8.12a rep-ownership work merged in:
`CRMService.create_estimate`/`get_estimate`/`list_estimates`
(`restoricon_core/services/crm_service.py`) read/write
`estimates.assigned_user_id` directly as a real, separate, actively-used
column (the estimate's owning rep) — unrelated to this branch's own
`assigned_to_user_id` (Codey-Estimator's created-by/reassignment concept).
Had the rename shipped, every `create_estimate` call post-migration would
have crashed with "no such column: assigned_user_id".

**Fix verified via full independent re-derivation, not trust of the
implementer's own diff/docstring:**
1. Read the merged `_migrate_estimates_table_v2()` in full —
   `_LEGACY_COLUMN_RENAMES` genuinely gone, `new_cols` keeps both
   `assigned_user_id` and `assigned_to_user_id` as permanent separate
   columns, docstring has an honest dated correction explaining exactly
   why the old logic was wrong.
2. Diffed the `estimates`/`users` DDL pairs (`_SCHEMA_SQL` vs. their
   full-rebuild-migration twin constants) programmatically — byte-identical
   apart from the table-name/`IF NOT EXISTS` opener, as this project's
   standing convention requires.
3. **Live-reproduced the exact crash path**: built a from-scratch legacy
   SQLite file matching real prod's actual current shape (B8.16 `users`
   columns incl. `subcontractor_id`/`territory_id`/`terminated_at`, old
   pre-B9.1 `estimates` shape with real `assigned_user_id` data, `1100.0`
   total etc.), ran it through the real merged `DatabaseManager()`,
   confirmed `assigned_user_id` data survived the rebuild intact, then
   called the real `CRMService.create_estimate`/`get_estimate`/
   `list_estimates` against the migrated DB — all succeeded. This is the
   strongest form of verification available for a migration claim and
   should be the default technique for any "this rename/rebuild is safe"
   claim in this project (see also [[d2_sales_manager_role_users_table_rebuild_approved]]'s
   crash-injection technique — same family).
4. `_migrate_users_role_constraint()`'s `new_cols` set confirmed to include
   all 4 required additions (`requires_estimate_approval`, `territory_id`,
   `terminated_at`, `subcontractor_id`).
5. `auth.py`'s `ROLE_PERMISSIONS[ROLE_SALES_MANAGER]` merge independently
   diffed against both branches' pre-merge commits (`main` HEAD vs.
   `ef04dab`) — merged set is a genuine, lossless union of both sides.
6. `NEW_ISSUES.md` id-collision fix (`NEW-544` kept on main's finding,
   estimator branch's colliding one renumbered to `NEW-709`) confirmed via
   `grep -oE "### \[NEW-[0-9]+\]" | sort | uniq -c` — every remaining
   duplicate id (`NEW-57`, `NEW-30`, `NEW-56`, `NEW-55`, `NEW-49`,
   `NEW-287`, `NEW-227`, `NEW-226`, `NEW-222`, `NEW-18`, `NEW-126`,
   `NEW-700`) was cross-checked against `main` and the branch's pre-merge
   commit and found to be PRE-EXISTING on at least one side already — the
   merge introduced zero new collisions.
7. `CODEY_MASTER_PLAN.md` decision-log items 13 (main's 2026-09-23 D6
   entry) / 14 (branch's 2026-09-27 B9.2+ scoping pass) both present,
   correctly ordered, not duplicated.
8. `PROJECT_LOG.md`: no leftover `<<<<<<<`/`=======`/`>>>>>>>` markers
   anywhere in any of the 7 conflict-resolved files; top-of-file entries
   spot-checked for correct reverse-chronological interleave of both
   branches' 2026-09-2x rounds.
9. Full `tests/test_restoricon_core/` suite (HTTP_PROXY/HTTPS_PROXY
   unset — see [[sandbox_http_proxy_urllib_405_env_artifact]]): **1377
   passed**, matching the implementer's claimed count exactly.

**One real gap found, non-blocking, logged not fixed:** `PROJECT_LOG.md`
has no entry at all for the B9.2 EstimateService round (`ef04dab`) — a
rule-9 violation that predates this merge (git log confirms `ef04dab`
never touched `PROJECT_LOG.md`). The merge doesn't make this worse, but
it's a real ledger gap the coordinator should close.

**Verdict: APPROVED.** This is the strongest-verified migration review in
this project's history to date — every one of the task's 10 checklist
items was independently re-derived (not re-read), including a from-scratch
live crash repro of the exact bug that made this merge notable. Flag for
the coordinator: this confirms [[b9_2_round2_branch_divergence_approved]]'s
recommendation was followed correctly — do not treat this as "safe to
`codey start`" without also running a live-verifier pass against a DB
COPY exercising the *full* `init_schema()` chain; that step is still
separate from and after this merge-commit review.
