---
name: phase7-part2-calendar-view-changes-requested
description: Phase 7 Part 2 (read-only Calendar tab, last admin-dashboard phase) — round1 CHANGES REQUESTED, staff-schedules silent-truncation gap
metadata:
  type: project
---

Reviewed 2026-09-11, staged diff (not committed): `restoricon_core/api/web_surfaces.py`
(Calendar tab, month/week views, filters, detail modal), new test file
`tests/test_restoricon_core/test_web_surfaces_calendar_view.py`.

**Verdict: CHANGES REQUESTED** — one real bug, everything else held up.

## The blocking finding

`loadCalendar()`'s staff-schedules fetch:
```js
fetch('/api/v1/staff-schedules?start=' + startStr + '&end=' + endStr, ...)
```
sends no `limit`. `routes.py`'s GET `/api/v1/staff-schedules` handler (line ~1450)
never reads a `limit` query param at all — only `user_id`/`start`/`end` are
forwarded to `scheduling_service.list_staff_schedules()`, whose default is
`limit=200`. Compare the sibling `/api/v1/appointments` handler two blocks
above (line ~1404), which *does* read `query_params.get("limit", ["50"])`
and forward it — the calendar JS exploits that by passing `&limit=500`. No
equivalent path exists for staff-schedules; the JS literally cannot raise
the cap even if it tried, because the route doesn't wire it through.

Effect: `ORDER BY start_time ASC LIMIT 200` silently drops the *tail*
(later-dated) rows once a month's staff-schedule row count for the
requested range exceeds 200 — e.g. ~10 staff x 22 working days = 220. The
UI has zero indication this happened: no error, no "+N more", nothing.
This is the same silent-data-loss class the task's check #3 explicitly
guards against for the *render* cap (`CAL_MONTH_CELL_ITEM_CAP`) — the
render-layer cap is handled correctly (uncapped in `openCalendarDay`), but
this is an earlier, invisible truncation at the *fetch* layer that the
render-layer fix can't see or compensate for.

This route/service default predates this diff (approved in Phase 7 Part 1,
see [[phase7_part1_subcontractor_link_range_filters_approved]] — the 200
default itself was a reasoned, approved design choice at the time). This
round is the first UI consumer that spans a full date range across
potentially many staff members in a single view, which is exactly the
shape of request the historical default doesn't protect against. Required
fix (implementer's choice of either): (a) forward `limit` through the
staff-schedules route the same way appointments does, and have the
calendar JS pass a generous limit; or (b) if leaving the route as-is,
detect `entries.length === 200` in the JS and surface an explicit
truncation warning in `calLoadErrors` rather than silently rendering a
month that looks complete but isn't. Either way, log a NEW-### finding
per rule 8 since the underlying route gap is broader than just this
calendar view.

## What was checked and held up

- **XSS**: independently grepped the entire calendar region (`Calendar
  (Phase 7 Part 2` through `async function loadDocuments`) for every
  `onclick="..."` — all args are numeric (`${a.id}`, `${s.id}`,
  `${cursor.getFullYear()}` etc.), zero string/name interpolation. No
  NEW-481-pattern matches. All rendered text fields route through
  `escapeHtml()`.
- **Month-nav date-rollover fix**: hand-traced. `calNav()`'s month branch
  builds `new Date(d.getFullYear(), d.getMonth() + delta, 1)` — critically,
  it never reads `d.getDate()`, so the day-of-month component (which is
  what causes `setMonth()` overflow) can't leak into the calculation
  regardless of what day the anchor happens to be on. Aug 31 -> next ->
  Sep 1 -> prev -> Aug 1, confirmed correct in both directions.
- **Month-cell overflow fix**: `CAL_MONTH_CELL_ITEM_CAP = 3` caps only the
  inline month-grid rendering; `openCalendarDay()` applies no slice at all
  when building the day-detail modal — genuinely shows all of that day's
  items, not also capped. (This check is about the *render* cap, distinct
  from the *fetch* cap bug above, which check #3 doesn't cover but is the
  same failure class.) `openCalendarDay`'s signature takes numeric
  year/month/day only.
- **Data fetching**: confirmed via `git diff --cached -- routes.py`
  producing empty output — zero backend route changes in this diff, both
  endpoints (`/api/v1/appointments`, `/api/v1/staff-schedules`) landed in
  Part 1 (`b587da1`) as the memory file records. Real `YYYY-MM-DD` values
  computed from `calGetRange()`, refetched on `calSetView`/`calNav`/
  `calToday` (all call `loadCalendar()`).
- **Color palette**: `calColorForType()` is `Math.abs(parseInt(typeId,10))
  % CAL_TYPE_COLORS.length` — a fixed 8-color array, genuinely
  deterministic, no `Math.random()`.
- **Person/Role filter scope**: `calFilteredAppointments()` only applies
  the type filter, never person/role — appointments are unconditionally
  included regardless of those two filters, matching the "always shown"
  requirement. `calFilteredStaffSchedules()` is the only place person/role
  narrow.
- **RBAC degradation**: grepped the whole file for any existing per-role
  tab-hiding pattern (`role ===`, `hasPermission`, conditional
  `style.display='none'` on nav buttons) — none exists anywhere in this
  file for any of the 14 tabs, confirming the implementer's justification
  for always rendering the Calendar nav entry is accurate, not invented.
  Independently traced the 401 handling concern the advisor raised: all
  three `loadCalendar()` fetches (`users`, `appointments`,
  `staff-schedules`) have `if (res.status === 401) { logoutUser(); return;
  }`, which looked like it could defeat independent degradation if
  permission-denial also returned 401. Read `routes.py`'s router docstring
  (line ~244) and the global exception handler (line ~2193): RBAC denial
  raises `PermissionError` in the service layer, caught centrally and
  turned into **403**, never 401 — 401 is reserved for
  missing/expired-token auth failures (`_authenticate`, `_handle_login`).
  So permission-only denial on either data fetch sets `apptOk`/`staffOk =
  false` and falls through to `renderCalendar()` normally; the two
  fetches do genuinely degrade independently. This was a real risk worth
  checking, not a false alarm to wave off next time — the code just
  happens to be safe here because of how the router centralizes 403.
- **Week view**: time-ordered list per day, explicitly labeled in the UI
  ("Day view is a planned future addition — Month and Week only this
  round" + no hour-grid CSS/markup) — an honest MVP label, not something
  that looks broken.
- Test file matches the project's established convention (see
  `test_web_surfaces_admin_wiring.py` precedent) — coarse string/wiring
  assertions only, explicitly disclaims behavioral coverage, defers to
  live-verifier. Reasonable given no JS test harness in this repo.
- `python3 -m pytest tests/test_restoricon_core/ -q` reran independently:
  **541 passed in 59.23s**, matches claim exactly.

## Minor, non-blocking (worth a follow-up NEW-### note, not blocking this round)

- `openCalendarDay()` does `title.innerText = escapeHtml(dateKey)` —
  double-escaping, since `.innerText` already treats its argument as
  literal text (never interpreted as HTML). Harmless for a `YYYY-MM-DD`
  string with no escapable characters, but inconsistent with
  `openCalendarItem()` two functions down which does plain
  `title.innerText = 'Appointment'` with no `escapeHtml()` wrapper —
  signals some confusion about which sink needs escaping. Low priority.
- `calPopulateTypeFilter()` / `calPopulatePersonFilter()` interpolate
  `${t.id}` / `${u.id}` unescaped into an `<option value="...">`
  attribute. Both are integer PKs from the server (not user-controlled
  strings), so not exploitable today, but it's the one unescaped
  interpolation site in the whole new region and worth tightening for
  consistency if this pattern is ever copied elsewhere with a
  non-numeric id.

## Lesson for future reviews

When a new UI consumer fetches a list endpoint whose service has a
previously-approved default row cap (`LIMIT N`), re-check whether that
cap is actually reachable/overridable from the new caller's route, not
just whether the cap itself is reasonable in isolation — a cap approved
as "well above any realistic single-view need" in one round (Part 1) can
become reachable once a different round's UI (a full month grid across
many staff) is the one hitting it, and if the route doesn't forward a
`limit` param the new caller has no way to defend against it even if it
tries (as the appointments sibling call does with `&limit=500`). Compare
sibling route handlers for the same missing wiring, not just the one
route this diff touches.
