---
name: d3-sales-portal-periodic-refresh-approved
description: D3 closeout — 12s setInterval auto-refresh added to sales portal loadDashboard(), reviewed and approved 2026-09-17
metadata:
  type: project
---

APPROVED 2026-09-17 (uncommitted at review time — coordinator to commit).
`restoricon_core/api/web_surfaces.py` `_render_sales_portal()`'s
`loadDashboard()` gained a `redirectOnIndeterminate = true` param, an
in-flight guard (`dashboardRefreshInFlight`), a distinction between
confirmed-401 (always redirects) vs. network-blip/ambiguous response
(redirects only when `redirectOnIndeterminate`), and
`setInterval(() => loadDashboard(false), 12000)`.

**Why:** Ish declined the full SSE push layer in
`docs/realtime_push_design.md` — "10-15 seconds is good enough" — so this
is the cheap alternative. Scope discipline confirmed: `git diff --stat`
touched exactly 2 files (`web_surfaces.py` +
`test_sales_portal_leads_opportunities.py`); `docs/realtime_push_design.md`
and `_render_staff_portal_base` untouched.

**Verification method that worked well here** (reusable for future
web_surfaces.py JS reviews, see also
[[web_surfaces_join_backslash_n_regression_approved]] and
[[new470_staff_portal_fstring_escape_approved]] for the brace-escaping bug
class):
- Render the actual surface in Python (`_render_sales_portal()`), slice
  out the `<script>...</script>` block, write it to a scratch file, and
  run `node --check` on it — catches f-string brace-doubling bugs
  (`{{`/`}}` → `{`/`}`) that string-level `in html` test assertions can
  miss if the assertion string itself has the same bug as the source.
  **Mandatory extra step (caught by advisor, not by first pass):** a
  `node --check` exit-0 only proves *some* JS was valid — confirm the
  sliced block actually contains the changed lines (e.g. grep/`in`-check
  the scratch file for 2-3 of the new tokens) before trusting the
  syntax-check result. A slice that silently grabbed the wrong
  `<script>` block, or truncated before the new code, would still exit 0
  and prove nothing.
- Cross-check each new test's literal asserted string against the
  *actual* rendered output via a one-off Python snippet (`"..." in html`),
  not just trusting the diff looks plausible.
- `grep`/`find` bare commands are broken in this Termux shell (loads
  `-G`/`-S` as if they were library args) — use `Read`, `git diff
  --stat`, or Python `in` checks instead. [[project_termux_grep_find_alias_broken]]

**Guard/race verified correct:** `try { ... } finally { dashboardRefreshInFlight
= false; }` wraps the *entire* function body including all internal
per-fetch try/catch blocks and every early `return` (token missing, 401,
!user) — JS `return` inside `try` still runs `finally` before returning,
so the guard cannot wedge permanently. Self-flagged race (interval tick
mid-flight when `claimLead`/`claimOpportunity` fires its own unawaited
`loadDashboard()`) is real but self-healing (no-ops once, catches up
next ~12s tick) — worth a NEW_ISSUES.md entry (see below) rather than
silently dropped.

**Full suite confirmed**: `1945 passed, 1 skipped in 301.29s` after
unsetting `HTTP_PROXY`/`http_proxy`/`HTTPS_PROXY`/`https_proxy` (matches
[[sandbox_http_proxy_urllib_405_env_artifact]] workaround — still correct
as of 2026-09-17).

A new NEW_ISSUES.md entry (id TBD by coordinator, do not guess the
number here) is owed for the interval-tick vs. claim-reload race in the
in-flight guard — low severity, self-healing, not fixed this round.
Implementer explicitly deferred logging it to the coordinator; confirm
in a later review that it actually got logged, not silently dropped.
