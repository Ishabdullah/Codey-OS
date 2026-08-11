---
name: resource_gate_74a_subtaskF_swap_cap_recalibration_stale_status
description: 7.4a sub-task F (MAX_SWAP_ASSIST_BYTES 768MiB->10GiB + DISPATCH_MAX_SWAP_ASSIST_BYTES decoupling) — round1 CHANGES REQUESTED on stale TODO.md header, round2 APPROVED after doc-only fix
metadata:
  type: project
---

Sub-task F (raise `MAX_SWAP_ASSIST_BYTES` in `core/resource_gate.py` to
10GiB per Ish's 2026-08-11 direction, decouple a new
`DISPATCH_MAX_SWAP_ASSIST_BYTES` constant at the old 768MiB for
`can_dispatch_task()` so the autonomous dispatch loop's early-warning
gap isn't collapsed) went through two review rounds.

**Round 1 — CHANGES REQUESTED, doc only.** All substantive work checked
out clean: constants correct, `can_admit()`/`can_dispatch_task()` call
sites correctly split, negative control (hand-reverting the split to
confirm the two `can_dispatch_task()` cap-enforcement tests would
actually flip) confirmed load-bearing, an NEW-21-shaped concurrent-
admission consequence independently re-derived and logged as `NEW-140`,
full suite 729 passed/1 skipped pasted verbatim. Blocked ONLY because
`TODO.md`'s sub-task F header still read "...NOT YET IMPLEMENTED" in
the same diff that implements it — the recurring
stale-status-ships-with-its-own-code pattern this project has hit
repeatedly (see [[resource_gate_phase4_1_subtaskC_dispatch_gate_changes_requested]],
[[resource_gate_phase4_1_subtaskD_shutdown_tripwire_changes_requested]]).

**Round 2 — APPROVED.** Header corrected to: "Implemented and
code-reviewer-approved (one round, after a stale-status line in this
entry was caught and fixed — see below); uncommitted as of this
writing, pending the required live-verification pass...". Verified via
file mtimes (not just re-reading the diff) that `core/resource_gate.py`
and `tests/test_resource_gate.py` postdated round-1 review by nothing —
`TODO.md`'s mtime was strictly later than both, confirming only the doc
changed between rounds, so no code re-verification was needed. Skimmed
the full F section end-to-end (not just the header) for other leftover
stale-status phrasing — none found; a project-wide grep for "NOT YET
IMPLEMENTED"/"not started" also came back empty.

**Reusable technique**: when a task claims "only file X changed since
last review, don't re-verify the rest," don't just trust the claim —
`stat -c '%Y %n'` the files in question and confirm the doc file's
mtime is strictly the most recent. Cheap, fast, and catches silent
scope creep back into already-approved code without a full re-diff.

**Why this keeps recurring**: sub-task write-ups in this project are
drafted with forward-looking status language ("scoped by
project-architect... NOT YET IMPLEMENTED") that then isn't updated in
the same edit that lands the implementation. Treat any TODO.md/
WORK_QUEUE.md status line touched by an in-scope diff as a required
check item on every review pass, not just once per item.
