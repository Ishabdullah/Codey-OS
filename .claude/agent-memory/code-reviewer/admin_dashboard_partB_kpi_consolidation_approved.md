---
name: admin-dashboard-partB-kpi-consolidation-approved
description: Admin Dashboard round Part B — Calendar/Booking Config/Business Profile folded into Executive Overview tab, 3 standalone tabs removed — APPROVED
metadata:
  type: project
---

Staged (not committed) diff in `restoricon_core/api/web_surfaces.py` + 2 test
files. Large HTML/JS move (310 changed lines in one file). Reviewed by direct
structural inspection of `git show :restoricon_core/api/web_surfaces.py`
(staged content), not just the diff hunks — necessary because a move this
size makes diff-hunk-only review miss nesting/order bugs.

**Verified facts:**
- `grep -c 'id="tab-profile"\|tab-schedule\|tab-calendar"'` → 0 each; wrapper
  divs genuinely deleted, not renamed/emptied.
- Content ids (`profName`, `schedDuration`, `apptTypesTableBody`, `calGrid`,
  `calRangeLabel`, modal ids) each occur exactly once in the full rendered
  file — no duplication, no loss.
- Moved content sits as flat `erp-card`/`card-header-line` divs directly
  inside `tab-kpis`, not re-wrapped in any inner `class="tab-pane"` div (which
  would have permanently hidden it via the CSS gate even with tab-kpis
  active) — read the actual lines, not inferred from the diff.
- Physical order confirmed via id-offset comparison: KPI → Calendar →
  Booking Config → Business Profile → tab-users, matching the requested
  order exactly.
- Nav button count: grep `<button class="erp-tab-btn` → 15 before, 12 after;
  confirms the implementer's corrected comment (not the original "11
  assumed" scoping guess) was right.
- Zero live `switchErpTab('profile'|'schedule'|'calendar')` call sites
  remain anywhere in the file (would have been a silent no-op stray call).
- `<div>`/`</div>` count for the whole file: 400/400, balanced.
- `loadCalendar()`'s claimed internal fallback fetch
  (`if (!window.currentAppointmentTypes || !window.currentAppointmentTypes.length) { ...fetch... }`)
  verified to genuinely exist at the exact line — the `await loadCalendar()`
  ordering fix was defensive-but-harmless, not strictly required to prevent
  a race. Implementer's own characterization of their fix was accurate here
  (contrast with other rounds where "verified" claims didn't hold up).
- `git diff --cached -- routes.py services/ database.py models.py auth.py`
  → empty; genuinely a pure front-end move, no backend change.
- New/changed tests in both test files are non-vacuous: assert absence of
  old ids/onclick strings AND presence + relative ordering of new ones
  within the `tab-kpis`..`tab-users` HTML slice (`html.find(...)` offset
  comparisons), not just substring presence.
- `pytest tests/test_restoricon_core/ -q` → 576 passed in 140.45s (verbatim,
  background-task output read directly).

**Verdict: APPROVED.**

## Lesson

For a pure-HTML-restructure round (move, not edit), `git show :path` of the
full staged file plus targeted `grep -c` id-uniqueness checks and
id-offset-based ordering checks catch the two failure modes diff hunks alone
would miss: (1) a moved block still nested inside a surviving
`tab-pane`-classed wrapper (permanently hidden by CSS despite the outer tab
being active), and (2) silent duplication/loss that a line-based diff can
hide when both add and remove hunks touch near-identical text.
