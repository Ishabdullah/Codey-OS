---
name: b8_7d_commission_summary_new546_partial_approved
description: B8.7d get_team_commission_summary + NEW-546 sentinel fix + sales dashboard commission panels — APPROVED round1, with disclosed partial-fix scope and one latent (non-live-reachable) money-bucketing gap
metadata:
  type: project
---

2026-09-22. Reviewed `restoricon_core/api/routes.py`, `restoricon_core/api/web_surfaces.py`,
`restoricon_core/services/commission_service.py` + 6 new tests. APPROVED round1.

**NEW-546 sentinel fix (`_NO_COMMISSION_ACCESS = object()`)**: grepped every real call site of
`_scoped_rep_filter` fresh (`grep -rn "_scoped_rep_filter"`) rather than trusting the diff's own
list — only 2 real call sites exist (`list_commissions`, new `get_team_commission_summary`), both
check `is _NO_COMMISSION_ACCESS` immediately after assignment, before any other use. `get_commission`
doesn't use the helper at all — it inlines an already-fail-closed check. Sentinel handling is complete.

**Disclosed partial-fix scope confirmed accurate**: `CRMService._scoped_assignee_filter`
(crm_service.py:961-975) has the identical fail-open shape (`return actor.user_id` unconditionally,
no `actor.user_id is None` check) — read directly, confirmed unfixed. B8.7d's new code only touches
CRM through pre-existing `list_leads`/`list_tasks`/`get_pipeline_summary` calls, so the disclosure is
complete: **NEW-546 should be logged partially closed** (commission side done, CRM side needs its own
follow-up finding), not closed in full.

**Reversal-nets-to-zero claim**: verified `reverse_commission` writes a NEGATED `commission_amount`
on the reversal row (confirmed by reading the method directly), and same/cross-month netting behaves
exactly as the docstring claims. BUT: advisor caught that this only holds when the *original* row's
status is `'earned'` — `reverse_commission` has no guard restricting it to earned originals, so
reversing a hypothetical `'pending'` original would mis-bucket (`total_earned` goes negative,
`total_pending` stays stuck positive, netting to garbage not $0/$0). Traced every real
`record_commission` call site in the codebase (`grep -rn "record_commission(\|reverse_commission("`)
— both live production call sites (assessment-invoice-paid, HomeCare Phase-2-bonus) hardcode
`status="earned"`, and no route exposes arbitrary status creation — so this gap is **not reachable via
any live path today**, matching the codebase's existing "total_paid always 0.0 today" pattern. Logged
as Warning/non-blocking, not fixed inline (out of scope, not a trivial fix — would mean restricting
`reverse_commission` to earned originals or netting against whichever bucket the original sat in).

**Full-suite flakiness caught live, correctly not misattributed to the diff**: first full-suite run
(2276 passed, 1 skipped, **1 ERROR** in `test_api.py::test_api_new523_staff_schedules_...`, a test
wholly unrelated to commissions/RBAC) looked like a diff-caused regression. Did NOT trust it — passed
standalone and passed the whole `test_restoricon_core/` dir standalone. Re-ran the *exact same* full
suite a second time with no code changes: **2277 passed, 0 errors**, matching the implementer's claim
exactly. Confirmed via a clean `git stash`/full-suite/`stash pop` cycle that the pre-diff baseline is
2271 passed clean. This is the same class as [[test_resource_bus_aging_flaky_under_load]] — a
full-suite-only, non-deterministic test-isolation flake, not a regression. Lesson: when a full-suite
run shows a NEW error the diff doesn't plausibly explain, rerun the identical full suite once before
concluding it's a regression — a single anomalous run is not enough evidence either way.

**Route/JS verification**: `team_commission_rankings` gating independently confirmed via direct route
read (gated on `PERM_READ_TEAM_COMMISSIONS` only, no accidental inheritance from the
`PERM_READ_TEAM_SALES_DATA`-gated `"team"` block). Live-rendered the actual `<script>` block from
`_render_sales_portal()` via Python and ran real `node --check` on it (not the pre-existing syntax
test file) — exit 0.

Full suite final: 2277 passed, 1 skipped, 0 errors (baseline was 2271, +6 exactly as claimed).
