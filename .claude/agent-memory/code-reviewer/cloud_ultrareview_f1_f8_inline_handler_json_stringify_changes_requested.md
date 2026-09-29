---
name: cloud-ultrareview-f1-f8-inline-handler-json-stringify-changes-requested
description: 2026-09-15 cloud-ultrareview fix round (F1 NEW-481 inline-handler quoting, F2 NEW-491, F3 migrate profile carry-over, F4 user_id PATCH, F5/F6 UI, F8 INSERT..SELECT archive) — r1 CHANGES REQUESTED on stale test comments only, r2 APPROVED
metadata:
  type: project
---

Round: 7 fixes from a cloud ultrareview of the admin-dashboard program,
reviewed as an unstaged working-tree diff (HEAD 0f7ae8f). **Verdict:
CHANGES REQUESTED, comment-only** — every code change verified correct;
blocked because `tests/test_restoricon_core/test_web_surfaces_admin_wiring.py`
kept the pre-fix rationale ("Raw ${u.username} (not escapeHtml'd)...
escaping here would break the button") stacked above the new assertion
that asserts the opposite, and the appointment-type test's ONLY comment
still says "Raw ${t.name}". A future reader could "fix" the security fix
back out. Same stale-as-current pattern as [[t8a_daemon_dedup_docstring_overclaim]].

## What I verified (not taken from the brief)

- **F1 mechanism** (`${escapeHtml(JSON.stringify(v))}` inside a
  double-quoted `onclick`): ran my own node round-trip on 19 extra edge
  cases (backslash+quote, `&quot;`/`&amp;quot;` literals, U+2028, lone
  surrogate, `${...}`, backticks, NUL, CRLF, `</td>`, emoji) with a
  single-pass entity decoder — all round-trip, zero raw `"` leaks. It
  holds because escapeHtml escapes `&` first so the attribute decodes to
  exactly the JSON literal, and JSON is a JS-literal subset. **Load-bearing
  dependency: `JSON.stringify(undefined)` -> escapeHtml -> empty ->
  `fn(7, )` SyntaxError.** Safe only because `users.username` and
  `appointment_types.name` are both `NOT NULL` (checked DDL). If this
  pattern is reused on a nullable column, it breaks.
- Sweep test allow-list checked at the binding sites: `${day}` iterates the
  `BIZ_HOURS_DAYS` literal; `${p.id}` comes from `/api/v1/permissions/catalog`
  (auth.py's fixed catalog). No single-quoted `on*='` attributes exist in
  web_surfaces.py, so the `on\w+="` regex isn't blind to any handler.
- Negative control for the sweep done via scratchpad `cp` + `sed` revert of
  one site, then `cp` back — md5 identical before/after, no git stash.
- **F1 scope**: `<td>${u.username}</td>` etc. in `loadUsersList` are still
  raw — a crafted username still XSSes the admin row via the cell. F1 closes
  the handler sink only; NEW-481's cell sites must stay open in the ledger.
- F2: `StaffSchedule` defines no `__bool__`/`__len__`, so `if not updated`
  is a None check. Repo-wide grep: only routes.py calls both service methods.
- F3: `ROLE_AI_AGENT` holds `read:business_profile` (auth.py:428);
  `get_business_profile()` returns None on no row -> profile keeps
  dataclass None defaults (same as pre-fix). `map_profile` never sets the
  three Core-only fields, so the carry-over is the only source.
- F4: `/api/v1/users` (no filter) returns active AND inactive users with no
  limit, and user deletion archives+cascades schedules, so the Calendar
  edit modal's Person select always contains the current assignee — the
  new `user_id` existence check cannot mis-reassign to the first option.
- F6 is inert in prod: `loadSubcontractors()` still fetches the
  nonexistent `/api/v1/operations/subcontractors` (NEW-489 unfixed), so the
  Linked User input never renders. Correct in shape, unreachable today.
- F8: 10-column INSERT..SELECT mapping hand-checked against the archive
  DDL; rollback test now fails on `DELETE FROM users` after the single
  archive INSERT wrote 2 rows (`cursor.rowcount == 2` asserted) — genuine
  partial-write-then-rollback.
- F7 skip agreed: ISO-string SQL window comparison could silently exclude
  overlapping rows on format drift -> cap fails open. Perf nit vs safety.
- `pytest tests/test_restoricon_core/ tests/test_user_management.py -q`
  -> 639 passed in 62.00s (matches claim).

## Adjacent findings handed back for NEW_ISSUES.md

- Reassignment invite goes only to `after.user_id`; old assignee gets no
  ICS cancellation (pre-existing for delete too; now more visible).
- `test_doc_upload_*` junk files: 15 -> 18 after one suite run.

## Lesson

When a diff flips a test assertion to its opposite, read the comment block
ABOVE the assertion in the full file, not just the diff hunk — `git diff`
context lines showed the stale rationale but it's easy to skim past as
"unchanged." Stale rationale above a security-fix assertion is a
regression vector, not cosmetics.

## Round 2 (same session): APPROVED

Stale comments replaced; only the wiring test file changed (per-file diff stats for the other 9 files byte-identical to round 1). 36 passed on the two affected test files. One non-blocking warning: the new comment forward-cites `NEW-496`, which did not yet exist in NEW_ISSUES.md at approval time — coordinator told to reconcile the id when writing the ledger.
