---
name: new325-aigentik-shutdown-telemetry-flush
description: NEW-325 Aigentik telemetry.mjs shutdownTelemetry()/_flushPromise fix review method — approved
metadata:
  type: project
---

Reviewed `~/Codey-Aigentik` diff (telemetry.mjs, index.js, tests/telemetry.test.js) for
NEW-325 (Codey-OS `NEW_ISSUES.md`): wired `Store.shutdown()` into SIGINT/SIGTERM, plus a
scope-extension fix changing `_flush()`'s guard from a boolean `_flushing` flag to an
awaitable `_flushPromise` (the in-flight `_drainQueue()` promise itself), so a second
caller (shutdown's own flush call racing the timer-driven one) awaits the SAME flush
instead of early-returning past it. **APPROVED**, code-complete tier (not live-verified
— no real SIGTERM was sent to a running process).

**Verification method that mattered here (reusable):**
1. Reproduced the negative control myself rather than trusting the implementer's claim:
   `cp`'d telemetry.mjs to scratchpad, hand-reverted `_flush()`/`_flushPromise` back to
   the old boolean `_flushing` guard, ran `npx jest ... -t race` — got the exact failure
   the implementer described (`expect(store._queue.length).toBe(0)` → `Received: 1`).
   Restored from the scratchpad backup afterward. This is the same pattern as
   [[new414_lora_rollback_new91_163_batch_approved]] and several other entries — a git-
   diff read alone would not have caught whether the test genuinely exercises the fixed
   code path vs. passing vacuously either way.
2. Advisor caught something my own read missed: I'd read telemetry.mjs lines 240-400 only
   (Read tool told me ~917 more lines existed, truncated) and treated that as sufficient.
   The diff **renames** a field (`_flushing` → `_flushPromise`) — any surviving reference
   to the old name anywhere in the file/repo would silently evaluate to `undefined`
   (falsy) rather than error, and a vacuous test assertion on the old name would still
   pass. Grepping the WHOLE repo for both old and new names (`grep -rn "_flushing\|
   _flushPromise\|_stopped" telemetry.mjs tests/ index.js`) is the correct check, not a
   scoped Read of the class definition. Zero surviving `_flushing` refs found — clean.
3. Also checked the import binding directly: `index.js` uses
   `import * as telemetry from './telemetry.mjs'` (namespace form), so
   `telemetry.shutdownTelemetry()` at the new call site binds correctly. This matters
   because coverage showed `index.js` lines 1627-1775 (== `shutdown(signal)`, including
   the new call) as **uncovered** by the test suite — the new production call site is
   never actually exercised by `npm test`. That's the exact NEW-259 shape (CLAUDE.md
   "working alongside another agent" section): a mechanism approved on tests-pass alone
   that turned out to be a no-op because the only call site had a wrong binding. Since a
   live SIGTERM couldn't be run this session, checking the import form directly was the
   cheap substitute for the live-verify step that would normally close this gap.

**Two things flagged as Warnings, not blockers:**
- Residual microtask-window race in the new `_flushPromise` guard: if a record is
  enqueued in the narrow gap between `_drainQueue()`'s final `while` check returning
  false and the waiting caller resuming after `await this._flushPromise`, that record
  is NOT redrained by the waiter — same failure mode the OLD boolean guard had in that
  same window. This is a *narrowing*, not a new regression the fix introduced; report it
  that way, don't let it read as a new defect.
- Lengthening the async work inside `index.js`'s `shutdown()` (now awaits
  `telemetry.shutdownTelemetry()` before `process.exit(0)`) marginally widens a
  pre-existing double-SIGINT reentrancy window (`shutdown()` has no re-entrancy guard).
  Checked `stopLlamaServer()` — idempotent (guards on `llamaProcess.killed`). Did not
  chase `gmail.disconnect()`'s idempotency to ground truth; flagged as open, not fixed,
  not blocking — genuinely pre-existing, this diff only marginally lengthens the window.

**Confirmed npm test: 19 suites / 275 tests passing, both before test-file changes and
after restoring the fix following the negative-control revert** — literal output
captured both times, not paraphrased.

Cross-reference: [[new419_420_aigentik_toctou_release_fix_approved]] (same repo, same
session's earlier NEW-413/419/420 work touching this exact `shutdown()` function).
