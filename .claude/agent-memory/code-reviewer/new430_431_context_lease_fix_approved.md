---
name: new430-431-context-lease-fix-approved
description: NEW-430 (context-lease 1800s duration) + NEW-431 (/slots retry + fail-closed) fix — approved, full trace of admission/release/reap paths
metadata:
  type: project
---

Reviewed uncommitted diff: core/resource_gate.py, core/resource_bus.py,
core/inference_hybrid.py, core/plannd.py + 2 modified tests + 1 new test
file (8 tests). APPROVED — 1552 passed / 1 failed (pre-existing,
unrelated) / 1 skipped, full suite (259.76s), re-confirmed via
`git stash`/`git stash pop` bisection against clean main that the 1
failure (`test_api_ai_chat_auth_and_validation`, 429==200) reproduces
identically on unmodified main.

**Key trace points that mattered:**
- NEW-431's fail-closed refusal path in `reserve_context_budget()` sets
  `effective_n_ctx=n_ctx` (the real resolved value), NOT `None` — this is
  load-bearing because `wait_and_reserve_context_budget()`'s early-return
  guard is `if decision.admitted or decision.effective_n_ctx is None:
  return decision`. Setting it to `None` here would silently turn a
  retryable degrade into an immediate hard failure. Verified by reading
  both functions directly, not trusting the comment.
- Per-lease `lease_duration` (resource_bus.py's `acquire_context_lease()`)
  is stored as `expires_at = now + lease_duration` in the DB row itself,
  and `_reap_stale_records_locked()` reads `expires_at` from the row, not
  the module-level `DEFAULT_LEASE_DURATION_SEC` — per-lease overrides are
  genuinely honored on reap, not silently clobbered back to 60s.
- Crash-leak reasoning for the 1800s TTL bump: `_reap_stale_records_locked()`'s
  condition is `(expires_at is not None and now > expires_at) or (pid and
  not _pid_alive(pid))` — the PID-liveness disjunct reaps a dead owner's
  lease immediately regardless of TTL, so raising the TTL from 60s to
  1800s does NOT open a 30-minute leak window on process crash. Only
  matters for a still-alive process that somehow skips its own `finally`
  (not newly possible here — release is wrapped in try/finally on both
  call sites, verified by reading full function bodies not just diff
  hunks, matching the NEW-206 review's established technique).
- The /slots retry (`_fetch_slots_prompt_tokens()`, 2 attempts × 2.0s +
  0.5s gap = ~4.5s) runs entirely BEFORE `acquire_context_lease()` is
  ever called in `reserve_context_budget()` — i.e. outside
  `_LockedState`'s flock, same as the pre-existing meminfo/thermal reads.
  No lock held across the new sleep; no double-release risk.
- Timeout-layering check (this is the one the advisor caught me skipping
  on first pass — I only read `plannd.py`'s diff hunk and called it
  "same pattern, consistent" without reading the full function body the
  first time): confirmed by reading full bodies that (a) both call sites'
  `if not budget_decision.admitted: return` precedes the release
  `try/finally`, so `reservation_id` can't be None there, and (b) a hard
  /slots outage now costs up to ~600s (CONTEXT_QUEUE_TIMEOUT_CAP_SECONDS)
  of blocking admission-wait BEFORE either call site's own HTTP-completion
  timeout (180s at restoricon_core's /api/v1/ai/chat route, 300s at
  inference_hybrid.py) even starts — because that HTTP timeout only wraps
  the post-admission urlopen call, never the admission wait itself. No
  masking: the 600s admission-wait cap and the 180s/300s HTTP timeout are
  sequential, not overlapping windows. `plannd.py::get_plan()` resolves
  the same "primary"/PRIMARY_SERVER_PORT that `compute_outer_plan_timeout()`
  uses to size daemon.py's outer `asyncio.wait_for()`, so outer/inner
  layering stays consistent for that call site too.

**Reusable review technique reinforced:** when a diff touches BOTH call
sites of a shared mechanism (inference_hybrid.py + plannd.py here), don't
approve the second site on "same pattern as the first, diff hunk looks
identical" — read its full function body too. The advisor caught this
gap on this review; it would have been a real blind spot if plannd.py's
`return` had been placed differently relative to its `try/finally`.

Cosmetic-only, non-blocking: the fail-closed refusal hardcodes
`slots_occupied_tokens=0`, which telemetry will read as "pool was full"
for what's actually "couldn't measure the pool" — `reason` string carries
the truth, so not misleading to a human reading logs, just to a naive
telemetry aggregation. Not logged to NEW_ISSUES.md (too minor, flagged
here for whoever touches this telemetry field next).
