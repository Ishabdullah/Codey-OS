---
name: sales_dashboard_independent_permission_gates_changes_requested
description: B8.2a GET /api/v1/sales/dashboard route — round1 CHANGES REQUESTED, round2 APPROVED (clears rule-4)
metadata:
  type: project
---

**Round 1 (2026-09-17):** CHANGES REQUESTED. New route in
`restoricon_core/api/routes.py` (`/api/v1/sales/dashboard`) aggregates
appointments/leads/tasks/pipeline (self-scoped/route-scoped on
`PERM_READ_TEAM_SALES_DATA`) plus a `commissions` block from
`CommissionService.list_commissions`, which internally scopes on a
**different**, independently-grantable permission,
`PERM_READ_TEAM_COMMISSIONS`. Every built-in role pairs the two, but
`custom_permissions` (the `NEW-533` mechanism) can grant one without the
other, so the route's single top-level `"scope"` field (reflecting only
`PERM_READ_TEAM_SALES_DATA`) could say `"rep"` while a `commissions_only`
actor silently saw every rep's commission ledger — a mislabeled response
and real money-data leak relative to what the label implied. Also found:
route's inline comment promised a `NEW_ISSUES.md` entry for the
appointments strict-assignment divergence from `list_leads`/`list_tasks`'s
unclaimed-pool rule, that didn't exist yet.

**Round 2 (2026-09-17): APPROVED, clears rule-4's gate.** Verified live,
not just read:
- `has_team_commissions = actor.has_permission(PERM_READ_TEAM_COMMISSIONS)`
  is computed with zero coupling to `PERM_READ_TEAM_SALES_DATA`; new
  sibling field `"commissions_scope": "team"|"own"` is independent of
  `"scope"`. `commission_service.py` diff is empty (`git diff --stat`
  confirmed) — `CommissionService.list_commissions`'s own scoping,
  already approved in B8.1, genuinely untouched.
- New test `test_commissions_scope_independent_of_sales_data_scope`
  constructs an actor with `custom_permissions={PERM_READ_TEAM_COMMISSIONS:
  True}` only (no `PERM_READ_TEAM_SALES_DATA`), asserts `"scope"=="rep"`
  AND `"commissions_scope"=="team"` AND both rep A's and rep B's
  commission IDs are present in the response body — not a status-flag
  check. **Negative control**: swapped the route's `has_team_commissions`
  source to `PERM_READ_TEAM_SALES_DATA` (same bug round 1 flagged), test
  failed exactly as expected (`'own' != 'team'`), confirmed non-vacuous,
  reverted (diff restored to the pre-control 131-insertion state, `git
  diff --stat` checked).
- No new independently-grantable-permission composition gaps introduced
  this round — diff only adds the one route block + two imports + one DI
  wiring change (`server.py`), no new service calls beyond
  `CommissionService`.
- `NEW-551` entry read directly in `NEW_ISSUES.md`: accurately describes
  the appointments strict-`assigned_user_id` divergence from
  `list_leads`/`list_tasks`'s unclaimed-pool rule, rated
  Suspected/informational (not overclaimed as a bug), matches round-1's
  own assessment that this is a defensible spec-driven tradeoff.
- Full suite: `python -m pytest -q` with the proxy env vars set gave 59
  false failures — this is the known
  [[sandbox_http_proxy_urllib_405_env_artifact]] artifact (confirmed via
  `env | grep -i proxy` showing `HTTP_PROXY`/`HTTPS_PROXY` set). Re-ran
  with `unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY`: **2089
  passed, 1 skipped in 251.20s** — matches the implementer's claimed
  number exactly, verified myself, not trusted from the summary.
- Round-1's 6 "verified clean" items (pagination-loop correctness,
  `"team"` key absence vs `{}`, route-level gate ordering, `user_id is
  None` guard, `CommissionService` DI wiring signature match, route
  dispatch order) are all present byte-for-byte unchanged in this round's
  diff — confirmed via diff review, no re-verification needed.

**Reusable pattern, reinforced:** when a fix adds a second,
independently-grantable permission gate alongside an existing one, don't
just read the new boolean — (1) confirm zero coupling to the old gate by
reading the exact expression, (2) confirm the new test asserts on
response *contents* (IDs present), not just a status string, (3) run a
live negative control on the new gate specifically, not just the
pre-existing ones.
