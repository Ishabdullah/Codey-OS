---
name: git-checkout-path-wipes-uncommitted-diff
description: never use `git checkout -- <file>` to undo a reviewer's own temporary edit on a file that already has uncommitted implementer changes
metadata:
  type: feedback
---

`git checkout -- <path>` restores a file to HEAD (the committed index),
discarding *all* uncommitted changes to that file — not just the
reviewer's own just-made temporary edit. If the file under review has
an unstaged, uncommitted implementer diff (the normal case: "nothing
committed yet, review the working tree"), running `git checkout --` on
it after a negative-control tweak (e.g. temporarily removing a guard or
flipping an ORDER BY direction to prove a test is load-bearing) wipes
the entire implementer diff, not just the tweak.

Hit live during [[restoricon_core_phase_b2_task4_find_subcontractor_new246_approved]]:
removed the empty-query guard in `crm_service.py` to prove
`test_find_subcontractor_empty_string_query_returns_none_not_first_row`
was load-bearing, then ran `git checkout -- restoricon_core/services/crm_service.py`
to "restore" it — this deleted the entire uncommitted `find_subcontractor()`
method (78 lines), not just the one-line guard removal, since the whole
method was itself uncommitted. Caught immediately via `git diff --stat`
showing 0 changes when 78 were expected, and recovered by reconstructing
the method verbatim from the diff text already captured earlier in the
same review — no data was actually lost, but it was a self-inflicted
near-miss during the review itself.

**Why:** `git checkout -- <path>` operates against the index/HEAD, with
no concept of "just this hunk" — it does not know or care which part of
the working-tree diff was the reviewer's own scratch edit versus the
implementer's real, not-yet-committed work.

**How to apply:** Before making any negative-control edit (temporarily
removing a guard, flipping a constant, deleting a line) to a file that
already carries an uncommitted diff, `cp` the current on-disk file to
the scratchpad directory first. Restore from that backup copy after the
test, never via `git checkout -- <path>` or `git stash` on that path
(see [[resource_gate_subtask5_main_cli_recovery_approved]] for the
prior instance of `git stash push -- path` being unreliable for the
same class of reason). After restoring, always re-run `git diff --stat`
on the file and confirm the line count matches the original diff
`--stat` exactly before trusting the restore.

**Repeat hit (2026-09-23, B8.7c/B8.9a round-2 re-review):** did the
negative-control edit correctly this time (a Python `str.replace` patch
on `_resolved_signed_at`, not `sed`), but then reverted it via
`git checkout -- restoricon_core/services/crm_service.py` anyway,
instead of just writing back the pre-patch text — wiped the entire
411-line uncommitted implementer diff on that file a second time, same
mechanism, despite this exact memory existing. Recovered because a full
`git diff` of the file had already been captured to a tool-results file
earlier in the same review session and could be re-applied with
`git apply <saved-diff-file>` — this only worked because the diff had
incidentally been saved before the mistake; do not rely on that being
available. **Concrete rule going forward: never run `git checkout --
<path>` or `git restore <path>` on any file that has an uncommitted
diff you did not create yourself in this turn, for any reason,
including "restoring my own scratch edit."** The only safe restore
paths are (a) reversing your own patch by reapplying its inverse text
directly, or (b) `git apply` of a diff file you saved with `git diff >
file` *before* the scratch edit. Save that diff file preemptively, every
time, before any negative-control edit — treat it as mandatory setup,
not optional.
