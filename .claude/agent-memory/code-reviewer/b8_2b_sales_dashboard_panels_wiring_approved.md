---
name: b8_2b_sales_dashboard_panels_wiring_approved
description: B8.2b wiring GET /api/v1/sales/dashboard into _render_sales_portal() (6 new panels + NEW-552 banner fix) — APPROVED 2026-09-17
metadata:
  type: project
---

APPROVED 2026-09-17. `restoricon_core/api/web_surfaces.py` `_render_sales_portal()`
gained 6 new panels (Appointments today/upcoming, New-Leads badge,
Follow-ups, Pipeline Summary, Commissions, manager-only Team Snapshot) fed
by one new `fetch('/api/v1/sales/dashboard?days=7')` inside the existing
`loadDashboard()`, plus the NEW-552 fix (viewer-scope banner now derives
solely from `data.scope === 'team'`, old `custom_permissions` check fully
removed, fail-closed default `'My Own'`).

**What full verification looked like here** (reusable checklist for future
`web_surfaces.py` dashboard-wiring rounds):
- `node --check` on the actual current rendered `<script>` block (not
  implementer's claim) — exit 0. Confirmed the slice actually contained
  new tokens (`newLeadsBadge`, `teamSummaryStrip`, `'team' in data`)
  before trusting the syntax-check result (per
  [[d3_sales_portal_periodic_refresh_approved]]'s mandatory-extra-step
  lesson).
- Diffed every JS field read (`a.start_time/title/status`,
  `t.title/due_date/priority/status`, `c.source_type/commission_amount/
  earned_at/status`, `pl.stage_order/stages[st].count|total_value|
  weighted_value/win_rate`, `ts.total_leads/hot_leads/.../win_rate_percent`)
  against the real `Appointment.to_dict()`, `Task.to_dict()`,
  `CommissionLedgerEntry.to_dict()` (all bare `asdict(self)`),
  `CRMService.get_pipeline_summary()`, and
  `AnalyticsSearchService.get_executive_dashboard()` return shapes read
  directly from source — **this is the check advisor flagged as missing
  and it's the exact bug class this file has been burned by before
  (NEW-538: unverified GET-response-shape assumption)**. All matched
  exactly; implementer's `win_rate` unit-mismatch disclosure (per-stage
  has no win_rate, top-level pipeline.win_rate is 0-1, team.sales.
  win_rate_percent is already ×100) was independently verified correct
  against the real source, not just accepted as stated.
- Checked `escapeHtml`'s impl: `(unsafe || '').toString()...` — null-safe,
  so unguarded fields like `a.title`/`t.priority`/`c.source_type` cannot
  throw and silently kill the whole dashboard try-block. Ruled out
  advisor's second concern empirically, not by assumption.
- Two live negative controls (edit `web_surfaces.py` in place from a
  scratchpad backup, run the specific test, restore, re-diff to confirm
  restoration): (1) reverted NEW-552's banner fix back to the old
  `custom_permissions` check -> `test_sales_portal_viewer_scope_banner_is_
  display_only` failed exactly as expected; (2) changed the team-block
  gate from `'team' in data` to `data.scope === 'team'` ->
  `test_sales_portal_team_block_gated_on_key_presence` failed exactly as
  expected. Both confirmed non-vacuous.
- Confirmed byte-identical scaffolding claim by grepping the diff's own
  `+`/`-` lines for `dashboardRefreshInFlight`, `redirectOnIndeterminate`,
  `claimLead`, `claimOpportunity`, `window.onload`, `setInterval` — zero
  hits, all unchanged context only.
- Confirmed the 3 untouched pre-existing fetches
  (`/api/v1/leads`, `/api/v1/opportunities`,
  `/api/v1/staff-schedules?user_id=...`) are still present unparameterized/
  unswapped via direct regex search on the post-diff file.
- Confirmed NEW-555 (`.badge`/`.badge-info` undefined in
  `_get_common_styles()`) is genuinely pre-existing, not introduced by
  this diff: rendered the pre-diff (`git show HEAD:...`) file and found
  the same undefined classes already in use (schedule/leads/opportunities
  rows) before B8.2b touched anything.
- Full suite reproduced exactly: `2095 passed, 1 skipped, 69 warnings in
  293.43s` (proxy vars unset, `python -m pytest -q` from repo root) —
  matches implementer's claim verbatim. Note: repo-root `pytest -q`
  already collects everything under `tests/`, so a separate
  `pytest -q tests/` run is redundant, not a second real check.

**Process note:** the coordinator's own background-task tooling stalled
the first `pytest -q` run mid-suite (progress log froze at 54% with the
spawned process later gone from `ps aux`, no summary line) — this looks
like an artifact of the sandbox's backgrounding/timeout mechanism moving
a long job to background and then losing it, not a code issue. Re-running
via explicit `nohup ... & disown` plus a `kill -0 $PID` polling loop
completed cleanly. Don't trust a truncated progress log with no final
summary line as a suite result, even if it shows no failures so far —
rerun until a literal "N passed" line exists.
