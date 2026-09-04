---
name: t8a-daemon-dedup-docstring-overclaim
description: T8a core/daemon.py telemetry review — dedup repeat_count losslessness claim was false, caught by hand-tracing the diff's own test
metadata:
  type: project
---

T8a (telemetry categories B/C/D/G at `core/daemon.py`, 2026-09-04) round 1:
CHANGES REQUESTED for a docstring/test-comment-only defect, not a logic bug.
`Daemon._emit_gate_telemetry_deduped()`'s docstring claimed summing emitted
`repeat_count` values "recovers the true total evaluation count exactly"
("lossless"). This is false: on a dedup-key change, the previous window's
already-accumulated-but-unflushed `repeat_count` is silently discarded
(the implementer's own flagged finding #3). Proven by hand-tracing the
diff's own `test_gate_dedup_transitions` — 6 real calls to the method were
made, but summed emitted `repeat_count` was only 4; the test's own comment
at the time claimed "4 calls ... made in this test so far," which was
simply wrong (miscounted, and didn't name the 2 discarded evaluations).

**Why:** rule 6 (correct the record when a claim doesn't hold up) and this
project's precedent — `NEW-10`'s SIGTERM/REPL mischaracterization and
`b6_2a`'s docstring overclaim were both required-doc-fix-before-approval,
not silently waved through because the underlying logic was otherwise
sound. A docstring asserting "exactly"/"lossless" sitting next to a
findings list that already admits data loss is exactly the kind of
internally-contradictory doc state rule 6 exists to prevent.

**How to apply:** when a diff's own test or its own flagged findings list
contradicts a strong docstring claim ("exactly", "lossless", "always"),
don't just check the logic is correct — check the claim is *also* true.
Hand-trace a representative test by counting real calls vs. what the
assertions/comments claim was counted; a self-consistent-looking test can
still contain a wrong comment that happens not to be asserted on. This is
a cheap, high-yield check (just arithmetic on values already in front of
you) and the advisor tool caught it here after a first pass that verified
the *arithmetic* of the reset-to-0 mechanism (correct) but didn't cross
check it against the *prose claim* around it (false). Do both next time,
don't stop at "the numbers add up internally."

See also [[new10_sigterm_handler_new40_mischaracterization]],
[[b6_2a_audit_details_round2_approved]] for the same pattern in this repo.

**Round 2 (2026-09-04): APPROVED, closed.** Coordinator made a doc-only
fix — both the docstring and the inline reset-branch comment now say
"NOT lossless... lower bound... under-counting by at most one
in-progress window's worth per key transition (bounded, not exact)".
The test comment now says "6 real calls... 2 suppressed 'allowed'
evaluations... discarded, unflushed" and calls the sum a lower bound.
Re-ran both suites independently: `pytest tests/test_daemon_telemetry_t8a.py
tests/test_daemon_dispatch_gate.py -q` → 25 passed. No other diff hunks
changed since round 1 (dispatch-gate `(decision, interactive_active)`
tuple signature, `_deferral_state` cap, etc. all previously reviewed and
still identical). T8a ready to commit.
