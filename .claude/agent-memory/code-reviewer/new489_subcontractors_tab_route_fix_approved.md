---
name: new489-subcontractors-tab-route-fix-approved
description: NEW-489 admin dashboard Subcontractors tab dead-route + fake-field fix — approved, all claims independently verified
metadata:
  type: project
---

Reviewed and APPROVED (2026-09-15). `loadSubcontractors()` in
`restoricon_core/api/web_surfaces.py` switched from the nonexistent
`/api/v1/operations/subcontractors` (a real but unrelated
`/api/v1/operations/subcontractors/match` route exists nearby — don't
confuse the two when grepping) to `/api/v1/subcontractors?limit=500`,
and from fake fields (`specialty`/`status`/`rating`) to real
`Subcontractor` model fields (`company_name`/`primary_trade`/
`qualification_status`/`license_status`).

What was independently verified, not just trusted from the implementer's
report:
- `license_status` and `primary_trade` genuinely exist on `Subcontractor`
  (models.py) and are `Optional[str] = None` — i.e. genuinely nullable in
  the common case. Checked `escapeHtml`'s actual definition:
  `(unsafe || '').toString()...` — `null`/`undefined` coerce to `''`
  before escaping, so nullable fields render blank, not the literal
  string `"null"`. This matters because [[cloud_ultrareview_f1_f8_inline_handler_json_stringify_changes_requested]]
  logged a real bug in this exact family (interpolation only safe because
  columns were NOT NULL) — here the columns are nullable but the specific
  `escapeHtml` implementation used already guards it. Always check the
  guard mechanism directly instead of assuming NOT-NULL-shaped safety.
- `tbody` hoisted above the `try` — confirmed `document.getElementById`
  cannot throw, so pre- and post-fix behavior in the `catch` path is
  identical; the hoist is a correctness no-op, not a fix in itself.
- colspan=5 consistent across truncation-banner/no-records/error rows
  and matches the 5 real `<th>` headers.
- Negative-assertion tests were checked assertion-by-assertion (not just
  "whole function fails on revert", since pytest stops at first failing
  assert and the first assert in the inline-handler test is a *positive*
  one) — evaluated each `not in region` string against both the fixed
  HTML (all False, correct) and confirmed the full-function revert test
  fails pre-fix. Do this per-assertion check whenever a test bundles a
  positive assertion before a negative one the implementer specifically
  flagged as previously-passing-for-the-wrong-reason.
- Route (`/api/v1/subcontractors` GET, routes.py ~line 1325), limit
  bounds (`_parse_int_query_param` max 1000, 500 requested is within
  range), and response shape (`{"subcontractors": [...]}` via bare
  `asdict()`) all confirmed in routes.py, not assumed from the JS side.
- Scope: diff is exactly 2 hunks in web_surfaces.py (headers +
  `loadSubcontractors` body); `saveSubcontractorUserId`, the onboarding
  stub, and `/upsert` are unchanged context, not touched.
- Full suite: 643 passed verbatim
  (`python3 -m pytest tests/test_restoricon_core/ tests/test_user_management.py -q`).

See also [[appointment_types_phase6_aigentik_calendar_alignment_approved]]
and [[phase7_part1_subcontractor_link_range_filters_approved]] for the
broader Subcontractor-tab work this closes out.
