---
name: resource-gate-subtask5-main-cli-recovery-approved
description: TODO.md 7.4 sub-task 5 (main.py's four CLI call sites wired to daemon release-slot recovery) — APPROVED, closes all five sub-tasks as code-complete
metadata:
  type: project
---

Reviewed `main.py`'s `_load_primary_with_gate_recovery()` / `_is_unrecovered_gate_denial()`
and all four call sites (`repl()`, `args.init`, `args.tdd`, `args.fix`) plus
`tests/test_main_gate_recovery.py` (16 tests). **Approved.**

**What was verified directly, not trusted from the implementer's report:**
- Single-retry guarantee: the retry path is a direct `return loader.load_primary()`,
  no recursion back into the recovery helper — confirmed by reading the function body,
  not just the report. `FakeLoader` in the test file raises `AssertionError` on an
  unscripted 3rd call, a real negative control (verified this actually fires by reading
  the script-exhaustion branch).
- Cross-checked all 8 `RELEASE_OUTCOME_*` constants against `core/daemon.py` directly
  (`RELEASED`, `ALREADY_UNLOADED`, `BUSY_TASK`, `BUSY_SWAP`, `COOLDOWN`, `INVALID_MODEL`,
  `UNCONFIRMED`, `ERROR`) — main.py's allowlist-inversion (`retry only if RELEASED or
  ALREADY_UNLOADED`) correctly buckets all 8, including the 2 untested by direct
  parametrize (`INVALID_MODEL`, `ERROR`) which both produce `status: "error"` in
  `_handle_release_model_slot()`, so `send_command()` raises `RuntimeError` for them and
  they're actually caught by the `except Exception` path, not the outcome-check path —
  traced this by reading `send_command()`'s `if response.get("status") == "error": raise`.
- `_HARD` short-circuit: confirmed `LOAD_OUTCOME_GATE_DENIED_HARD` never reaches the
  daemon-contact code at all (checked via `!= LOAD_OUTCOME_GATE_DENIED` gate, not
  `in (..., ..._HARD)`).
- `shutdown()`'s "no change needed" claim: verified by reading `load_primary()`'s
  gate-denial return path (line ~643) directly — `self._server`/`self._slot_id` are
  never set before that early return, so `unload()`'s existing `if self._server:` /
  `if self._slot_id:` guards are genuine no-ops on a bailed-out CLI invocation. This
  matters generally for this project: a claim like "existing guard X already handles
  new case Y, no change needed" must be checked by reading the guarded state's actual
  set/unset lifecycle, not just skimming the guard itself.
- Checked the response dict isn't nested under a `"data"` key — `_handle_client()`
  returns `handler(...)`'s dict directly, so `response.get("outcome")` in main.py
  reads the right field. Worth checking on any future daemon-socket-command review;
  an easy wrong-nesting-level bug that wouldn't show up in unit tests using dict fakes.
- Ran the real full suite (`python3 -m pytest -q`): 479 passed, 1 skipped, 3 failed —
  the 3 failures are `tests/test_new19_patch_failed_repeat_escalation.py`'s known
  NEW-39 dirty-tree pattern. Re-confirmed by restoring `main.py` to `HEAD` and re-running
  just that file (5/5 pass clean), then restoring the real diff back (verified via
  `git diff --stat` that nothing was lost).

**Gotcha for next time:** `git stash push -- <specific-path>` can fail
("Entry '<other-file>' not uptodate. Cannot merge.") when an unrelated newly-`git add`-ed
file exists elsewhere in the tree, even though the pathspec doesn't target it. Don't
trust stash-with-pathspec for a clean-diff-only test on this repo — use
`git show HEAD:<file> > <file>`, run the test, then restore from a manual backup copy,
and verify the restore with `git diff --stat` before trusting the result.

**Non-blocking findings (Suggestions, not Warnings):**
- `RELEASE_OUTCOME_BUSY_SWAP` isn't in the test file's decline-parametrize list
  (only `BUSY_TASK`/`COOLDOWN`/`UNCONFIRMED` are) — shares the exact same code path
  (not in the retry-allowlist) as the tested ones, so this is coverage tidiness, not
  a real gap.
- Error message on "retry attempted, retry also gate-denied" says "no recovery was
  possible," which undersells that a recovery WAS attempted and still failed —
  cosmetic, not a correctness bug.
- A successful daemon release + a second gate denial on retry leaves the *daemon's*
  model unloaded and the CLI's own load still failed — net effect is neither process
  has a model resident until the daemon's next watchdog tick reloads it. Acceptable
  side effect of a failed recovery attempt, not a bug, but undocumented in the
  helper's docstring/error message.

**Verdict:** approved for commit. All five sub-tasks of `TODO.md` item 7.4 are now
code-complete; `TODO.md`'s own top-level 7.4 box was already correctly left unchecked
pending code-review + live-verification (CLAUDE.md rule 7) — confirm that language
stays as-is, don't check the box yet. `LIVE_TEST_QUEUE.md` entry for real on-device
model-load testing across the whole gate is still the next step, not this review.
