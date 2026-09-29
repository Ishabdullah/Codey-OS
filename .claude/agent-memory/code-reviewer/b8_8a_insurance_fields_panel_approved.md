---
name: b8-8a-insurance-fields-panel-approved
description: B8.8a insurance/claim UI panel + 2 new Project columns — APPROVED round1
metadata:
  type: project
---

2026-09-23: B8.8a (expose 6 pre-existing + 2 new Project insurance/claim
fields in sales-portal UI) reviewed and APPROVED round1, no round 2 needed.

All 8 claims in the task brief verified true against the actual diff/code,
not just the implementer's summary:
- INSERT placeholder count: 31 columns / 31 `?` / 31 values tuple entries,
  counted programmatically, matched exactly.
- `_PROJECT_NUMERIC_FIELDS` addition genuinely necessary (real NEW-308
  type-check guard) and both new fields added correctly, no typo.
- `deductible` really is unmasked for ROLE_CUSTOMER in `_row_to_project`
  today (no `and not is_customer` guard on it, unlike estimated_cost/
  actual_cost/profit/notes which do have that guard) — confirmed by
  reading the function directly. New fields follow the same unmasked
  pattern, consistent with precedent, not a new leak.
- The new panel lives in `_render_sales_portal()`, routed only via
  `/sales` in routes.py — a staff-shell page (unauthenticated HTML shell,
  same as every other portal in this codebase; the real gate is the
  server-side `PERM_WRITE_PROJECTS` check on the API route, matching this
  project's existing convention for all portal pages). Not reachable
  meaningfully by a ROLE_CUSTOMER actor since the customer portal is a
  wholly separate render function/route (`/portal` -> `render_portal_surface`).
- `insurance_claim_status` confirmed to exist only on `Opportunity`
  dataclass, not `Project` — exclusion claim is accurate, not a
  half-finished UX gap.
- update_project's blanket None-guard (pre-existing, lines ~2805-2809)
  does apply generically to the two new fields too — this is pre-existing
  generic behavior the new fields inherit automatically, not something
  introduced or avoidable by this diff.
- Live-extracted the actual `<script>` block from a real
  `_render_sales_portal()` call and ran `node --check` on it directly
  (didn't trust the implementer's claimed run) — passed. Confirmed the
  `${{...}}` doubled-brace convention collapsed correctly to single
  `${...}` in the rendered JS (NEW-538 regression class).
- `test_auditable_project_fields_matches_dataclass` in
  test_b6_2b2_audit_details.py is a real drift guard
  (`_AUDITABLE_PROJECT_FIELDS == frozenset(f.name for f in dc_fields(Project))`)
  that would have caught a missing field — confirmed by reading it, not
  just trusting the name.
- All 8 new tests read directly, each exercises a real code path
  (create/update round-trip with distinct values per field to catch
  column-ordering swaps, default-None, numeric type-check rejection
  parametrized x2, audit-diff assertion, RBAC PermissionError, route
  200). No mocking of the thing under test.
- Full suite: 2285 passed, 1 skipped, 69 warnings in 335.78s — matched
  implementer's claimed 2277->2285 (+8) exactly, no hang this run.
- No install.sh/requirements.txt change needed or missing (no new deps).

Nothing to escalate to NEW_ISSUES.md from this round — first B8.8a
sub-round to clear on round1 with zero findings.
