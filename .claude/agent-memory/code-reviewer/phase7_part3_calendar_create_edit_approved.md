---
name: phase7-part3-calendar-create-edit-approved
description: Phase 7 Part 3 (Calendar create/edit) round2 fix — StaffSchedule.id default — APPROVED, clears the entire admin-dashboard program
metadata:
  type: project
---

Follow-up to a round1 CRITICAL blocker (not in this reviewer's own memory —
no round1 memory file existed when this round started; treat that as a gap,
not as evidence round1 didn't happen): `StaffSchedule.id: Optional[int]` had
no default, so `StaffSchedule(**json_body)` in `routes.py`'s POST
`/api/v1/staff-schedules` 500'd on every real browser payload, since neither
`submitStaffSchedule()` nor Part 3's new `submitSchedForm()` ever send an
`id` key.

Round2 fix verified against `git diff --cached` (models.py + web_surfaces.py
+ 2 test files + NEW_ISSUES.md, all staged):
- `models.py`: `id: Optional[int] = None` moved after the 6 non-default
  fields, before `created_at`/`updated_at` (already defaulted) — valid
  dataclass field ordering, confirmed by import + `dataclasses.fields()`.
  No other field's order/meaning changed.
- `scheduling_service.py`'s `create_staff_schedule` INSERT column list
  independently re-verified to omit `id`, with `schedule.id =
  cursor.lastrowid` set after — passing `id=None` in is genuinely harmless.
- Repo-wide `StaffSchedule(` grep (Codey-OS + Codey-Aigentik + restoricon)
  re-run independently: only 2 real construction sites
  (`routes.py:1464 StaffSchedule(**json_body)`, and keyword-arg test
  fixtures) — zero positional constructions anywhere, confirmed not just
  trusted from implementer's claim.
- New test `test_route_staff_schedules_create_without_id_field` reproduces
  the *exact* no-`id`-key payload shape from both JS call sites (not the
  weaker `"id": None` shape used elsewhere in the test file, which happens
  to route around the bug). **Negative-controlled**: `git stash push --
  models.py` → test gives `500 == 201` (genuine repro of the pre-fix bug,
  not a vacuous assertion) → `git stash pop` → 201.
- `NEW-491` (bundled PATCH-no-404 + DELETE-false-success from round1,
  intentionally not fixed this round) cross-checked line-for-line against
  `update_staff_schedule`/`delete_staff_schedule` — accurate, and its
  Impact line already correctly names the *new* Calendar modal wiring
  (this diff's `openEditSchedModal`/`removeScheduleFromCalendar`) as a live
  reachable caller of both unguarded PATCH/DELETE paths, not just the
  pre-existing Staff Schedules tab.
- Full 357-line `web_surfaces.py` diff read in full (not just the
  incremental fix) since no round1 memory existed to lean on: all new
  `onclick` handlers pass only numeric ids (NEW-481 pattern avoided), all
  fetch error paths show the real server message inline (no silent
  swallow, no `alert()`-only UX), and the two subtlest design choices both
  independently verified correct by reading the *called* service methods
  rather than trusting the JS comments describing them:
  - `submitApptForm`'s edit path omits `status` from the payload — verified
    `update_appointment()` in `scheduling_service.py` only builds SET
    clauses for keys actually present in the `updates` dict (genuine
    partial-SET, not a defaulting writer) — so omitting `status` really
    does leave it untouched, exactly as the JS comment at diff lines
    231-242 claims.
  - `calPopulateApptTypeSelect` silently no-ops if `selectedId` isn't in
    `window.currentAppointmentTypes` (a plausible risk for an appointment
    pointing at a deactivated type) — verified the fetch populating that
    cache uses `?include_inactive=true` (web_surfaces.py ~3249), so this
    risk doesn't materialize.
- `pytest tests/test_restoricon_core/ -q` → 556 passed, matches claim.

**Reviewer self-error caught by advisor, corrected before verdict:** my own
`git stash push -- models.py` / `git stash pop` (without `--index`) used
during negative-control testing silently downgraded `models.py` from
staged to unstaged in the working tree — `git status --short` showed
` M` instead of the original `M `. Re-ran `git add restoricon_core/models.py`
and confirmed identical diff content before approving. **Lesson: `git
stash push -- <path>` / `git stash pop` without `--index` does not
preserve staged/unstaged state — always diff the restored file's status
against the pre-stash snapshot before trusting it, or use `git stash push
--keep-index` / `--index` on pop, or just copy+restore the file content
manually instead of stashing when the file is staged.**

**Verdict: APPROVED.** Clears Phase 7 Part 3 and the entire multi-week
admin-dashboard program for final commit.
