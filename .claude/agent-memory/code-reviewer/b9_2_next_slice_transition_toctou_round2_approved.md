---
name: b9_2_next_slice_transition_toctou_round2_approved
description: B9.2 next slice round 2 (2026-09-29) — transition() TOCTOU/CAS fix — APPROVED, full independent verification
metadata:
  type: project
---

Round 2 of [[b9_2_next_slice_transition_toctou_changes_requested]]. Verdict:
**APPROVED**. The Critical (unguarded pre-read + no-CAS blind UPDATE in
`transition()`) is genuinely fixed: `BEGIN IMMEDIATE` now precedes the
`SELECT`, every permission/action lookup runs against the freshly-read row,
and the final UPDATE carries `AND workflow_status = ?` + raises on
`rowcount == 0`. Verified by reading the live code directly, not the
implementer's description.

Two things worth remembering for next time:

1. **A "your repro pair is actually legal" pushback should be checked
   against the real lookup table, not accepted on prose alone.** The
   implementer's claim that `SENT->CANCELLED` is a legal transition (so my
   round-1 repro pair wasn't a rejection case) was correct — confirmed by
   grepping `_ACTOR_DRIVEN_TRANSITIONS` directly for both `("SENT",
   "CANCELLED")` (present) and `("SENT", "INTERNAL_REVIEW")` (absent). Don't
   let a plausible-sounding scope correction stand without grepping the
   actual dict/table it claims about.

2. **A connection-proxy race-simulation test needs to be traced by hand,
   not just run.** `test_transition_stale_pre_read_no_longer_clobbers_state_changed_before_lock`
   intercepts `execute()` on the literal `"BEGIN IMMEDIATE"` string to
   inject a competing transition at that exact point. Whether this actually
   discriminates old-vs-new code depends entirely on *where* the read
   sits relative to that interception point in each version — worth
   reasoning through explicitly (old code: SELECT before any BEGIN
   IMMEDIATE, so the injected race is invisible to it and it blindly
   clobbers; new code: SELECT after BEGIN IMMEDIATE, so it observes the
   injected commit and correctly raises). A green test alone doesn't
   prove this discrimination — trace the ordering.

Full suite: 1402 passed, 0 failed, 0 deselected (literal output captured,
matches implementer's claim exactly this time — contrast with round 1
where the claimed count didn't reproduce).

See [[b9_2_next_slice_transition_toctou_changes_requested]] for the
original Critical finding and the other Warnings (all resolved or
correctly disclosed-not-fixed this round: NEW-713/714/715).
