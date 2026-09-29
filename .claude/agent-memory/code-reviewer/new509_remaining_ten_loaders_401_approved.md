---
name: new509-remaining-ten-loaders-401-approved
description: NEW-509 finishing round (10 of 11 remaining load* functions get 401 handling) — approved, loadDashboard exclusion independently verified correct
metadata:
  type: project
---

2026-09-15, second NEW-509 round (first round covered `loadSubcontractors`/
`loadDocuments` only, see [[new507_508_509_subcontractor_delete_approved]]).
This round added `if (<res>.status === 401) { logoutUser(); return; }`
immediately after each fetch in the remaining 10 admin-dashboard `load*`
functions (`loadKPIs`, `loadEquipment`, `loadFinance`, `loadComms`,
`loadBizOps`, `loadCrmList`, `loadUsersList`, `loadDeletedUserHistory`,
`loadAuditLogs`, `loadAppointmentTypes`), deliberately excluding
`loadDashboard`.

**The `loadDashboard` exclusion is real and correct** — independently
verified, not just trusted: `loadDashboard()` lives inside
`_render_staff_portal_base()` (line ~4864), a *different* rendered surface
from `render_admin_surface()` (~1671-4863). `_get_common_script()` (where
`logoutUser` is defined) is called inside `render_admin_surface` (line 2724)
but never inside `_render_staff_portal_base`. That surface's own Sign Out
button already uses `window.location.href='/admin/login'`, not `logoutUser`.
Adding `logoutUser()` there would throw a live `ReferenceError` — same bug
class as the `loadDocuments` `logout()`-typo bug NEW-509 fixed once already.
**Lesson: this file has multiple independently-rendered surfaces sharing a
similar naming convention (`load*` functions, `render_*`/`_render_*_base`
functions) — never assume a function belongs to the surface you're scanning
just because it's nearby in the file or shares a name pattern with functions
in that surface. Always check which `render_*`/`_render_*_base` function's
line range a given `async function` actually falls inside, and separately
confirm `_get_common_script()` is actually invoked within that same range,
before assuming a shared helper (like `logoutUser`) is in scope.**

Other checks worth repeating in future rounds on this file:
- Multi-fetch functions in a single try block (`loadFinance`, `loadBizOps`)
  or split across two try/catch blocks (`loadCrmList`) each need their own
  response-variable check right after their own fetch — verify each
  inserted check's variable name matches the fetch immediately above it,
  not a variable from a different fetch in the same function.
- For a count-based test (`region.count(check) == N`), do a live
  negative-control spot check by reverting exactly one of N insertion
  points and confirming the test fails on that specific assertion, not
  just on a full-function revert — this proves the test would catch a
  *partial* fix, which is the actual failure mode this bug class produces.
- `test_web_surfaces_js_syntax.py` should be rerun on every `web_surfaces.py`
  diff regardless of how small — this file has a real history of the
  Python-string-escaping-breaks-the-whole-`<script>`-block bug class
  (NEW-503, see [[web_surfaces_join_backslash_n_regression_approved]]).

**Ledger gap flagged (not blocking, but required before round close):**
`NEW_ISSUES.md`'s `[NEW-509]` entry still described the pre-this-round state
(11 remaining, including `loadDashboard`) at review time — needs updating to
reflect 10/11 fixed, plus a new `NEW-###` logged for the `loadDashboard`
staff-portal 401 gap per rule 8 (found during this task, correctly not
silently folded into this round's fix idiom since it needs a different one).

Full suite: `tests/test_restoricon_core/ tests/test_user_management.py` →
664 passed (663 + 1 new test), matching implementer's claim exactly.

**Verdict: APPROVED**, code + test. See also
[[new489_subcontractors_tab_route_fix_approved]] and
[[new507_508_509_subcontractor_delete_approved]] for the round chain.
