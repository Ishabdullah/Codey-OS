---
name: new549_global_search_rep_scoping_approved
description: NEW-549 AnalyticsSearchService.global_search leads/opportunities rep-ownership narrowing fix — APPROVED, clears rule-4 gate
metadata:
  type: project
---

Reviewed 2026-09-17. `restoricon_core/services/analytics_search_service.py`
`global_search`'s leads/opportunities branches were leaking every rep's rows
to any `PERM_GLOBAL_SEARCH` holder without `PERM_READ_TEAM_SALES_DATA`. Fix
adds the same `AND (assigned_user_id = ? OR assigned_user_id IS NULL)`
narrowing `CRMService.list_leads`/`list_opportunities` already apply via
`_scoped_assignee_filter` (crm_service.py:826-870, 1308-1341).

Verification performed (not just diff read):
- Confirmed the "matches CRM's unclaimed-pool visibility" claim against
  crm_service.py:863-870/1334-1341 directly — real and true for the common
  case.
- **Correction to the implementer's claim**: it does NOT match CRM exactly
  at one edge — CRM's shape is `if effective_uid is not None: <apply filter>`,
  so a narrowed actor with `user_id=None` gets **zero filtering** in
  `list_leads`/`list_opportunities` (fail-open, same shape as the NEW-546
  pattern and the b8.1 `_scoped_rep_filter` finding). This fix's new code
  applies the filter unconditionally and binds `None` — live SQLite repro
  confirmed `assigned_user_id = NULL OR assigned_user_id IS NULL` returns
  only NULL-assignee (unclaimed) rows, not zero rows and not all rows. That
  is *stricter/safer* than CRM's own behavior, not an exact match — worth
  correcting the record on (rule 6) even though it doesn't block.
- Ran the role→permission matrix in `restoricon_core/auth.py` myself rather
  than trusting the two roles the new tests cover (ROLE_SALES,
  ROLE_SALES_MANAGER). Roles holding `PERM_GLOBAL_SEARCH` but NOT
  `PERM_READ_TEAM_SALES_DATA` (i.e. newly narrowed by this diff):
  `ROLE_SALES` and `ROLE_PROJECT_MANAGER`. `ROLE_AI_AGENT` (Aigentik's
  integration identity) DOES hold `PERM_READ_TEAM_SALES_DATA` (auth.py:481)
  so it is unaffected — no comms-limb regression, contrary to a plausible
  worry. `ROLE_PROJECT_MANAGER`'s global search is now silently narrowed
  too (no test coverage for that role) — same leak class, correct
  direction, just undisclosed/untested surface. Not blocking, worth a
  one-line note in the round's ledger entry.
- Proved the new `rep_scoped` test is non-vacuous by stashing just the
  service-file diff and re-running it against pre-fix code: failed with
  2 leaked rows vs expected 1, confirmed real assertion, then restored the
  stash cleanly.
- SQL built via static string fragments only (`l_query +=`/`opp_query +=`
  add hardcoded clause text, never interpolate `like_pattern` or any request
  value) — all real values go through bound params lists. No injection
  surface.
- Confirmed diff touches only the leads/opportunities blocks; `ROLE_CUSTOMER`
  branch and all other 10 entity types (customers/projects/estimates/
  contracts/invoices/work_orders/subcontractors/vendors/employees/
  compliance) and `get_executive_dashboard` (NEW-550, logged not fixed)
  are byte-for-byte untouched — confirmed by direct read of the full file,
  not description.
- Full suite: reran myself, `2080 passed, 1 skipped in 252.08s (exit 0)` —
  differs from implementer's claimed `1966 passed, 1 skipped` (likely a
  narrower collection root on their end, e.g. skipping `ccos/tests/`); zero
  failures either way so not a blocker, but the raw number should never be
  restated as verified without reproducing it (rule 5) — this is the same
  gap flagged in [[new512_staff_portal_dashboard_401_fix]].

New pattern worth carrying: **when a fix claims to "match" an existing
scoping helper's behavior, don't just confirm the common-case line range —
walk the helper's `if x is not None:`-style guard for its None/edge-case
branch too, and check whether the new code reproduces that same edge
behavior or (as here) actually diverges from it while still being safe.**
Also: **before approving a permission-gated narrowing fix, enumerate the
full role→permission delta yourself from the auth module** rather than
trusting the two roles the new tests happen to cover — the implementer here
tested ROLE_SALES and ROLE_SALES_MANAGER but the diff silently also
re-scopes ROLE_PROJECT_MANAGER, and only checking auth.py directly caught
that ROLE_AI_AGENT was not accidentally regressed.
