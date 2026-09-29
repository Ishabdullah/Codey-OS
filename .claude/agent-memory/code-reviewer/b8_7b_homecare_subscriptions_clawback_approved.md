---
name: b8-7b-homecare-subscriptions-clawback-approved
description: B8.7b HomeCare enrollment/Phase-2-bonus/90-day-clawback + mid-round $179→$119 reprice correction — APPROVED round 1
metadata:
  type: project
---

2026-09-22, B8.7b (HomeCare `homecare_subscriptions` table, `sign_contract`
second try/except enrollment trigger, `cancel_homecare_subscription` +
lazy 90-day clawback via existing `reverse_commission`) plus a mid-round
Ish-directed reprice ($179→$119 Basic) with a scoped corrective
`_migrate_schema()` UPDATE — **APPROVED round 1**, no round 2 needed.

**Why round 1 cleared cleanly**: every claim in the implementer's report
was independently re-derived, not trusted:
- Reprice number checked against the actual `home-care.html` marketing
  page, not just internal consistency.
- On-device DB claim ("commission_plan_config doesn't exist yet")
  checked by literally listing tables on both `~/.codeyOS/restoricon.db`
  and its `.bak`, not accepted from the report.
- Migration idempotency proven with a live 3-open repro (179→119 on
  reopen 1, `updated_at` provably untouched on reopen 2) — the same
  technique as [[d2_sales_manager_role_users_table_rebuild_approved]].
- The IntegrityError-string-match branch for the *composite* partial
  unique index (`source_type, source_id`) had zero test coverage in the
  new file — advisor caught this, and the raw SQLite error text was
  reproduced live twice (direct INSERT + through the real
  `record_commission()` service call) before trusting it matched the
  code's `in exc_text` check.

**Bug pattern worth remembering**: a docstring/comment can confidently
assert something about a DDL that the DDL right next to it contradicts.
`models.py`'s `HomecareSubscription` docstring claimed "the DB does have
[a CHECK constraint on status] this round since the table is new -- see
database.py" — but `database.py`'s own comment on the same table
explicitly says status has NO CHECK constraint, and the DDL confirms it.
Two files, one true, one false, both narrating the same table. Doc-only
(Warning, not blocking) since the two legal values are enforced at the
only two Python write sites, but exactly the class of unverified
artifact-claim rule 12 exists to catch — grep both the model docstring
AND the raw DDL comment when a new table shows up in the same diff,
don't assume they agree with each other just because they're adjacent.

**Reusable technique**: when a report claims "error text X triggers
branch Y" and no test exercises it, don't accept the claim from a
narrower test (e.g. a single-column UNIQUE) as covering a *different*
constraint (a multi-column partial UNIQUE) — reproduce the specific
constraint's raw `str(exc)` live. SQLite's message format for
`UNIQUE(source_type, source_id) WHERE ...` partial index is
`"UNIQUE constraint failed: table.col1, table.col2"` — confirmed, no
index name, consistent with the single-column case already documented in
[[b8_7a_commission_trigger_round2_approved]].

Advisor caught the two things a diff-only read would have missed:
(1) the untested composite-index error-string branch, (2) telling me to
actually grep for the partial unique index's predicate rather than trust
the comment claiming it covers `subscription_upsell`.
