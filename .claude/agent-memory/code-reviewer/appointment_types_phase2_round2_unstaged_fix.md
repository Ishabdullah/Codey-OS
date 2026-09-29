---
name: appointment-types-phase2-round2-unstaged-fix
description: Coordinator's own "scheduling_hours_json removal" fix on scheduling_service.py was applied to the working tree but never `git add`ed — index still had the vulnerable version
metadata:
  type: project
---

Round 2 re-review (2026-09-11) of appointment_types Phase 2
([[appointment_types_phase2_approved]]). Coordinator claimed to have
removed the raw `scheduling_hours_json` string key from
`_APPOINTMENT_TYPE_UPDATE_FIELDS` in
`restoricon_core/services/scheduling_service.py` directly, and stated
"everything is still staged, not committed."

That claim was false for this specific edit. `git diff --cached --
restoricon_core/services/scheduling_service.py` showed the OLD code
(raw `scheduling_hours_json` key still accepted, `elif key ==
"scheduling_hours_json":` branch still present). `git diff --
restoricon_core/services/scheduling_service.py` (unstaged) showed the
actual removal. `git status --short` showed `MM` for the file — modified
in the index AND modified again in the working tree, i.e. two different
versions layered on top of each other.

**Why this matters:** `git commit` (without `-a`) commits the index, not
the working tree. If committed as-is, the fix that was reviewed and
"confirmed" would silently NOT ship — the raw-JSON-string vulnerability
(a caller could write unparseable JSON into `scheduling_hours_json` and
permanently 500 every future read of that row via
`_row_to_appointment_type`) would land in the commit while
`pytest`/manual verification (which reads the working tree, not the
index) would appear to confirm it was fixed. This is the same failure
shape as [[working_tree_cross_round_bleed]] but even sharper: it's not
stale files from a *different* round bleeding in, it's the *same*
person's own fix landing in the working tree but never staged.

**How to apply:** Whenever a reviewer is told "X was changed directly,
everything is staged," always diff `--cached` AND unstaged separately
per touched file, not just `git status --short`'s M/A letters at a
glance. `MM` (or any letter appearing twice in `git status --short`
porcelain output) means index and working tree disagree — treat it as a
hard stop until whoever made the last edit stages it explicitly
(`git add <path>`, never `-A`), and re-diff `--cached` to confirm the
final content before approving.
