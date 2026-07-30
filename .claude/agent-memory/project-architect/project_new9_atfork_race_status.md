---
name: project-new9-atfork-race-status
description: NEW-9 (llama-server orphan on SIGINT during model load, atfork/fork race) — two consecutive fix attempts live-verified incomplete as of 2026-07-30
metadata:
  type: project
---

NEW-9 (`NEW_ISSUES.md`) — a residual, intermittent atfork/fork-window
race in `core/loader_v2.py` that lets `SIGINT` during model load orphan
`llama-server` by having CPython's atfork machinery silently swallow
the `KeyboardInterrupt` before it reaches the caller's
`try/except (KeyboardInterrupt, SystemExit)` guard — has had **two
consecutive fix attempts, both approved by code-reviewer, both shown by
live-verifier to be incomplete**:

- Round 9 (commit `1a1c0b7`): masked only the `Popen()` call itself.
  Live-verified 3/16 (~19%) still orphaned — mask was placed too late,
  missing ~70 lines of unguarded setup before it.
- Round 10 (commit `2aaabb1`): widened the mask to cover from the
  `"Starting llama-server..."` log line through `Popen()`. Live-verified
  20/22 clean, but still 2/22 (~9%) failed, both at the earliest
  possible SIGINT timing (delay=0.0s) — with `KeyboardInterrupt` still
  observed inside `logging._afterFork` even while
  `pthread_sigmask(SIG_BLOCK)` was active for the entire widened region.
  This suggests the remaining failure mode is not simply "window too
  narrow" but something deeper — possibly Termux/Android-specific
  signal-delivery behavior, or a CPython atfork-callback quirk not
  fully governed by `pthread_sigmask` here.

**Why this matters:** the pattern of "widen the masked window further"
has diminishing but nonzero returns and does not appear to be
converging to zero through mask-widening alone. Per CLAUDE.md's
escalation rules, both rounds were brought to Ish directly rather than
scoping a next attempt unilaterally — this is now the second
consecutive escalation on the same bug.

**How to apply:** if a third NEW-9 fix attempt is scoped, do not default
to "widen the mask again" without new diagnostic information (e.g.
confirming whether this is Termux-specific, or finding an
interrupt-safe mechanism that doesn't depend on `KeyboardInterrupt`
propagating through the fork window at all — see fix-direction notes
already logged in `NEW_ISSUES.md` [NEW-9]). See
[[project_punch_list_closed_round7]] for the broader punch-list state
this bug emerged from.
