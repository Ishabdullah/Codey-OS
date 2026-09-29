---
name: phase7-part2-calendar-view-round2-approved
description: Phase 7 Part 2 (Calendar view) round2 — NEW-490 staff-schedules truncation fix — APPROVED, clears for commit
metadata:
  type: project
---

Follow-up to [[phase7_part2_calendar_view_changes_requested]]. Round1 blocked on
silent staff-schedules truncation (route ignored `limit` query param entirely).
Round2 fix verified directly against `git diff --cached` (still staged, not
committed):

- `routes.py` GET `/api/v1/staff-schedules`: now reads
  `limit = int(query_params.get("limit", ["200"])[0])` and forwards it,
  mirroring the appointments sibling route exactly, default preserved at 200.
- `web_surfaces.py` `loadCalendar()`: fetches with `&limit=500`
  (`CAL_STAFF_FETCH_LIMIT`) AND separately checks
  `schedules.length === CAL_STAFF_FETCH_LIMIT` to surface a truncation warning
  in `calLoadErrors` — correctly implemented as belt-and-braces (raised cap
  alone would leave the same class of bug reachable at >500 rows).
- New test `test_route_staff_schedules_limit_query_param_caps_response`
  (in the Phase 7 Part 1 test file) proves `?limit=5` actually caps to 5 rows
  and no-`limit` still works (7/7 rows, route default).
- New JS wiring tests in `test_web_surfaces_calendar_view.py` assert exact-match
  strings (`CAL_STAFF_FETCH_LIMIT = 500`, the literal fetch URL concat,
  `staffTruncated`, `schedules.length === CAL_STAFF_FETCH_LIMIT`) — not vacuous,
  each string only appears if the specific fix landed.
- NEW-490 logged with correct rule-7 tier split: route half "unit-tested and
  passing"; JS truncation-warning half "code-complete... not yet live-verified
  in a browser," explicitly deferred to live-verifier.
- Rest of `web_surfaces.py` diff is purely additive (zero removed lines besides
  diff header) — no scope creep alongside the fix.
- `pytest tests/test_restoricon_core/ -q` → 544 passed (541 baseline + 3 new),
  matches claim exactly.

**Verdict: APPROVED.** Clears Phase 7 Part 2 for commit.

## Lesson

When a round1 CR finding gets fixed and re-submitted still-staged (no intermediate
commit), you can't `git diff` round1-vs-round2 directly — instead spot-check that
the file's overall diff has zero *removed* lines outside the fix region (a quick
`grep -c "^-"` sanity check) to catch scope creep, then verify the specific fix
blocks line-by-line against the round1 finding's required behavior.
