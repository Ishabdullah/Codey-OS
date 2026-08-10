---
name: resource_gate_phase4_1_subtaskD_shutdown_tripwire_changes_requested
description: Phase 4.1 sub-task D (autonomous shutdown tripwire) round 1 review — CHANGES REQUESTED; sparse-history false-trip is a kill-path Critical, found only by hand-tracing the walk-backward loop for a sample-count gap, not by reading the fraction check alone
metadata:
  type: project
---

Round 1 of Phase 4.1 sub-task D (`should_trip_shutdown()` / `_sustained_trailing_run()`
in core/resource_gate.py, watchdog wiring in core/daemon.py, retirement of the
socket `shutdown` handler + `daemon_shutdown()` helper) — CHANGES REQUESTED,
three findings:

1. **Critical, kill-path**: `_sustained_trailing_run()`'s min-fraction guard
   checks the fraction of *present* samples above threshold within a span, but
   never checks sample count/density. A history with just 2 samples 25 minutes
   apart (`[(now-1500, 95.0), (now, 95.0)]`) passes both the span check
   (1500s >= 1200s) and the fraction check (1.0 >= 0.8) and fires
   `_trigger_shutdown()`. This is reachable in production: `sample_temperature_c()`
   appends nothing on a None/failed read (documented sentinel contract), so a
   run of failed thermal reads / an Android doze window / a stalled event loop
   produces exactly this sparse history, and the next hot sample after the gap
   trips the daemon. It's the exact failure mode the spec named ("a
   freshly-started daemon with only a couple of hot ticks must not trivially
   satisfy this") reached via a route the implementer's own tests didn't cover
   (all their synthetic histories are contiguous 30s-spaced samples). Fix needs
   a minimum sample-count/density requirement in the qualifying window, not
   just a fraction-of-present-samples check.
   Verified live: `python -c "import core.resource_gate as rg, time; now=time.time();
   print(rg.should_trip_shutdown(temp_history=[(now-1500,95.0),(now,95.0)],
   cpu_history=[]))"` → `should_trip=True`.

2. **Blocking, doc-currency (3rd occurrence of this exact pattern)**: TODO.md's
   sub-task D entry still says "BLOCKED on a decision from Ish, not
   implementer-resolvable" and describes the CPU-signal question as
   undecided — in the SAME diff/working tree where the code fully implements
   Ish's already-recorded 2026-08-10 decision (option 3), and where
   WORK_QUEUE.md's parallel entry WAS correctly updated with "Decided by Ish,
   2026-08-10: option 3...". Same round, same author, inconsistent between the
   two docs that are supposed to mirror each other in ordering (per CLAUDE.md's
   "TODO.md is what to check off, WORK_QUEUE.md is the reasoning" split — they
   still need to agree on current status). Matches prior CHANGES REQUESTED
   precedent on sub-task A ("stale TODO.md 'zero implementation' line shipping
   alongside its own code") and sub-task C ("stale TODO/WORK_QUEUE 'not
   started' text shipping alongside its own implementation") — see
   [[resource_gate_phase5a_subtaskA_cpu_sentinel_changes_requested]] and
   [[resource_gate_phase4_1_subtaskC_dispatch_gate_changes_requested]].
   Lesson: "project-architect updates docs after approval" is NOT an excuse to
   let a *newly-written-this-round* doc line contradict the very code it sits
   beside — that's different from merely-stale leftover text from a prior
   round. Check whether the stale text predates this diff or was authored IN
   this diff; if authored in this diff, it's a same-round internal
   inconsistency, not a deferred-to-project-architect update.

3. **Blocking, rule 8 (3rd occurrence)**: two out-of-scope findings the
   implementer flagged in their own summary (stale "not wired into
   core/daemon.py yet" module docstring in resource_gate.py; stale "7 handlers
   total"/`daemon_shutdown()`-as-existing-handler docstring in
   daemon_control.py) were never actually written to NEW_ISSUES.md — confirmed
   via `git diff --stat -- NEW_ISSUES.md` showing zero changes to that file.
   Same pattern as [[u31_codey_n_ctx_override_changes_requested]] and
   [[resource_gate_new97_plannd_registration_approved]]'s reviewer note —
   always check `git diff --stat -- NEW_ISSUES.md` independently, never trust
   "I logged this" in a chat summary.

Non-blocking items that DID check out on independent trace/repro (worth
reusing the technique, not the conclusion, next time):
- `_trigger_shutdown()`'s `self.server.server.close()` vs. `finally:`'s
  `await self.server.stop()` double-close reasoning is sound by inspection
  (`asyncio.Server.close()` cancels `_serving_forever_fut`, is idempotent;
  `wait_closed()` on an already-closing server returns once closed, no
  traceback) — and the diff's own docs correctly flag this as still needing
  live confirmation rather than assuming it silently.
- `shutdown_callback`/`_shutdown_callback`: zero repo-wide references after
  removal (real grep, not trusted).
- `daemon_shutdown()`: zero real callers, one docstring-only mention in
  daemon_control.py — matches implementer's claim exactly.
- Socket `{"cmd": "shutdown"}` fallback: independently traced
  `_handle_client()`'s real dispatch code (core/daemon.py:581-585,
  `handler = self._handlers.get(cmd); ... else: {"status": "error", "message":
  f"Unknown command: {cmd}"}`) rather than trusting the test, which
  hand-builds its own expected-response dict instead of driving the real
  dispatcher (flagged as a Suggestion: weak/self-fulfilling test, not a
  blocker on its own).
- Config validation (`CODEY_SHUTDOWN_TRIP_AFTER_SEC`/`CODEY_SHUTDOWN_CPU_PCT`)
  fails loudly with a clear message on bad input — verified by reading
  `_thermal_int_env_override()` directly.
- 514 passed, 1 skipped — matches implementer's claimed count exactly (own
  run: `pytest tests/ -q --ignore=tests/test_new19_patch_failed_repeat_escalation.py`).

**New gotcha this round surfaced, separate from the 3 blockers above**: even
after the sparse-history fix lands, live-verification of THIS sub-task may
still be structurally hard — the two new env overrides
(`CODEY_SHUTDOWN_TRIP_AFTER_SEC`, `CODEY_SHUTDOWN_CPU_PCT`) don't touch
`THERMAL_CONFIG["temp_critical"]` (still fixed at 90°C, no env override
exists — confirmed via grep, only one `temp_critical` line in utils/config.py).
Shortening the duration override alone doesn't make live-verification
reachable without either a genuinely-hot device or a `CODEY_TEMP_CRITICAL`-
style override; flag this explicitly to the implementer/project-architect
before signing off on "ready for live-verification" wording, don't let it
slide as assumed-fine.
