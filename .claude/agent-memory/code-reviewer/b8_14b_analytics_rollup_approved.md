---
name: b8-14b-analytics-rollup-approved
description: B8.14b tiered sales analytics rollup (rep/manager/executive) — APPROVED round1, zero blocking findings
metadata:
  type: project
---

B8.14b (`AnalyticsSearchService.get_sales_analytics_rollup`, `GET
/api/v1/sales/analytics-rollup`, sales-portal panel) — APPROVED round1,
2026-09-25.

Verification performed (not just diff-read):
- Traced `_scoped_assignee_filter` (keys on `PERM_READ_TEAM_SALES_DATA`)
  and `_scoped_rep_filter` (keys on `PERM_READ_TEAM_COMMISSIONS`)
  independently to confirm the manager-tier OR-composition
  (`PERM_READ_TEAM_SALES_DATA` or `PERM_READ_TEAM_COMMISSIONS`) can't
  leak unfiltered pipeline data to a commissions-only holder — each axis
  gates independently on its own permission, confirmed by reading both
  helpers, not assumed from the docstring.
- Read `get_executive_dashboard`'s full return shape to confirm
  `"financial"` is the only AR/revenue-derived key the `.pop()` needs to
  strip (`marketing.total_marketing_spend` survives but is spend, not
  AR/revenue — outside the spec's exclusion, disclosed not silently
  judged).
- Confirmed both `get_pipeline_summary` and `get_team_commission_summary`
  are read-only (no `self.audit.log()` calls in either), making the
  lazy-default `AuditService(db)` constructor path genuinely inert.
- Confirmed constructor backward-compat: 9 existing
  `AnalyticsSearchService(db)` positional-only call sites (tests) still
  work since the new `crm_service`/`commission_service` params default
  to `None` → same lazy-construction as before.
- advisor caught a real gap in my own check: I'd read
  `get_pipeline_summary` up to line 1987 but never confirmed the actual
  `win_rate`/`active_weighted_value` key names/scale the renderer reads.
  Same fixture-masks-reality shape as B8.3/B8.5b/NEW-631-632 — a wrong
  field name or scale (e.g. 0-1 fraction rendered as `*100` when the
  method actually returns a 0-100 percent) would silently render `$0`/
  `0%` or a 100x-wrong number, no error. Read the actual return
  statement: `win_rate = round(won_count/closed_total, 4)` (0.0-1.0
  fraction) and `active_weighted_value` both exist and match the
  renderer's assumptions exactly. **Lesson: when a task brief cites a
  specific line-range read, verify the return statement was actually
  inside that range — a partial read of a long method is an easy way to
  miss the one line that matters.**
- Live-ran all 11 new tests directly (not trusted from implementer
  report) — all passed, including the PermissionError→403 no-leak tests.
- `node --check` on the real rendered `<script>` block confirmed no JS
  syntax error from the new panel/functions.
- Full suite: `2469 passed, 1 skipped, 69 warnings in 488.85s` — matches
  implementer's claim verbatim and is exactly +11 over B8.13a's 2458
  baseline (the new test file). Ambient proxy env vars
  (`HTTP_PROXY`/etc, `127.0.0.1:45583`) confirmed present in this sandbox
  per [[sandbox_http_proxy_urllib_405_env_artifact]] — always unset
  before trusting a failure count, not needed here since this round used
  no urllib loopback calls but the artifact is real and recurring.

Two Suggestions filed, not blocking:
- `_ROLLUP_RECONCILIATION_NOTE` is worded to describe the "unclaimed-pool
  leniency" divergence, but is returned unconditionally on both rep AND
  manager tiers — for a manager-tier actor who genuinely holds
  `PERM_READ_TEAM_SALES_DATA`, the note describes a condition that isn't
  true for them (no unclaimed-pool narrowing applies to their own
  pipeline read at all).
- `tier: "manager"` for an actor holding only `PERM_READ_TEAM_COMMISSIONS`
  (not `PERM_READ_TEAM_SALES_DATA`) is accurate about commission breadth
  but the pipeline data underneath is still self-scoped — the UI badge
  reads "Manager view" over a mix of team-wide + self-scoped data. No
  leak, just an imprecise label.

Both are real precedent for this project's pattern: composite gates on
two independent permissions tend to produce a coarse tier label that
doesn't precisely describe either underlying dataset's actual breadth.
Same shape as [[b8_7d_commission_summary_new546_partial_approved]]'s
reconciliation-quirk disclosure.
