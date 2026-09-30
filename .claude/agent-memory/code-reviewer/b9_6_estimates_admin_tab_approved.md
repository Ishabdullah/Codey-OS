---
name: b9_6_estimates_admin_tab_approved
description: B9.6 admin Estimates tab (list/filter, detail, version-diff, audit timeline) — APPROVED round 1; total_cents ungating verified safe via full role×permission matrix, not just field-precedent
metadata:
  type: project
---

B9.6 (`restoricon_core/services/estimate_service.py` new `list_versions()`/
`get_version_lines()`/`_gate_version_cost_fields()` + changed
`_attach_cost_fields()`, `models.py` new `EstimateHeader.total_cents`,
two new `/versions` routes, admin "Estimates" tab in `web_surfaces.py`,
18 new tests, 2026-09-30) — APPROVED on round 1, no changes requested.

**The one check that could have flipped the verdict, and the technique
for it:** the implementer's claim "`total_cents` is safe to expose
unconditionally, it's sell price not margin" is true only for a viewer
who doesn't also know a cost input for that estimate. Field-level
precedent-matching (`EstimateVersion.total_cents`/
`EstimateLineItem.line_total_cents` already ungated) is NECESSARY but
NOT SUFFICIENT — it doesn't prove the audience is safe. The
sufficient check is the **role × permission set-difference**: which
roles pass `_can_view_estimate()` (i.e. `PERM_READ_ESTIMATES`/
`PERM_READ_OWN_ESTIMATES`/`PERM_READ_ALL_ESTIMATES`) while lacking
`PERM_READ_ESTIMATE_COSTS`? Read every `ROLE_PERMISSIONS[ROLE_X]` block
directly (`restoricon_core/auth.py`) rather than trusting the method
name. In this codebase today: ADMIN/MANAGER/SALES/PROJECT_MANAGER/
AI_AGENT all grant both permissions together (never one without the
other); ROLE_CUSTOMER grants only `PERM_READ_OWN_ESTIMATES` (no COSTS);
ROLE_TECHNICIAN/ROLE_SUBCONTRACTOR hold neither, so they can't reach
`_can_view_estimate()`'s True branch via the default role grants at
all. The difference is customers-only — genuinely safe, since a
customer's own sell price is exactly what the customer is charged.
This same technique (grep `ROLE_PERMISSIONS`, read every block, take
the set difference) is the generalizable move any time a shared-helper
change relaxes one gate while keeping another — don't stop at "this
field has a same-shape precedent," check who newly sees it.

**Other things verified directly, not on the implementer's word:**
- IDOR guard on `get_version_lines()`: resolves version_id -> estimate_id
  -> `_can_view_estimate()` BEFORE any data returned; confirmed in code
  and via `test_get_version_lines_is_not_an_idor`.
- `_gate_version_cost_fields()`'s 7-field null list matches exactly
  `EstimateVersion`'s real cost-revealing columns (4 component costs +
  cost_total_cents + gross_profit_cents + gross_margin_bp); sell-side
  fields including `subtotal_sell_cents` stay visible. Minor
  imprecision (not a bug, a Warning-level docstring nit): the docstring
  claims this "mirrors" the line-level gate, but `_LINE_COST_INTERNAL_FIELDS`
  actually DOES gate `sell_total_cents` at the line level while
  `_gate_version_cost_fields()` leaves the analogous `subtotal_sell_cents`
  visible at the version level — asymmetric, doesn't leak cost (sell-side
  aggregates alone don't reveal cost), but don't cite this docstring's
  "same as" claim as precedent for a future field without rechecking.
- Diff route: no server-side diff exists (disclosed as NEW-724); JS
  `estimateAdminRunDiff()` fetches both versions' `/lines` independently
  and renders side by side with zero `_cents +/-/* ` arithmetic anywhere
  in the function body (grepped the literal function text between its
  own `async function` markers).
- XSS: every dynamic value in `estimateAdminLoadAudit()` (timestamp,
  action, entity_type/id, actor_id/role, change_summary, every
  changed_fields/snapshot key AND value) is wrapped in `escapeHtml()`
  before reaching `innerHTML`, confirmed by reading the literal function
  body, not the diff's own comments. `signature_data` is filtered out of
  both `changed_fields` and `snapshot` by exact key match before
  rendering (`!== 'signature_data'`), never reaches the DOM in any form.
  Traced the real data path: `record_decision()` writes
  `build_audit_details(after=result.to_dict())` with no `before`, which
  (per `build_audit_details`'s diffing logic) puts EVERY key of
  `EstimateDecision.to_dict()` — including `signature_data`,
  `signer_name`, `comment` — into `changed_fields` as `{old: None, new:
  value}`; confirmed `EstimateDecision`'s real field name is exactly
  `signature_data` (matches the JS filter's literal string). The new
  test `test_decision_comment_and_signer_name_surface_in_audit_timeline_via_details`
  round-trips an actual `<img src=x onerror=alert(1)>` comment through
  `record_decision()` into a real queried audit row and asserts it lands
  in `changed_fields.comment.new` verbatim (unescaped in the DB, which is
  correct — escaping belongs at render time only) — this plus the static
  JS trace closes the XSS item without needing a live HTTP repro.
- RBAC on new routes: no route-level permission decorator (consistent
  with every other `/api/v1/estimator/estimates/...` route in this file
  since B9.3) — gating is entirely inside `list_versions()`/
  `get_version_lines()` via `_can_view_estimate()`.
- `list_versions()`'s 404-for-missing-estimate / `PermissionError`-for-
  not-viewable split is not a new existence-oracle risk: `get()` already
  has the exact same split (`row is None -> return None` then
  `_can_view_estimate() is False -> raise PermissionError`), pre-existing
  convention on this same authenticated surface.
- NEW-723/NEW-724: both genuinely disclosed-by-design (not silently
  shipped), IDs 723/724 unique and non-colliding with any prior entry
  (checked via grep across the whole ledger, given this project's prior
  NEW-544 double-allocation incident).
- Full suite: 1471 passed, matches implementer's claim exactly, verbatim
  (`python -m pytest tests/test_restoricon_core/ -q`, proxy env vars
  unset, 214s). Also spot-checked no prior B9.2/B9.3 test asserted
  `header.total_cents is None` for a cost-restricted actor (would have
  been a silent regression-in-what-the-test-tests even if it still
  passed for a different reason) — grepped `total_cents` across the
  whole test dir and confirmed no such assertion existed before this
  round.

Files staged for commit: `NEW_ISSUES.md`, `restoricon_core/api/routes.py`,
`restoricon_core/api/web_surfaces.py`, `restoricon_core/models.py`,
`restoricon_core/services/estimate_service.py`,
`tests/test_restoricon_core/test_b9_6_estimates_admin_tab.py`.
