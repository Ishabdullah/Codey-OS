---
name: new358-run-start-fallback-claim-vs-recorded-conflation
description: loader_v2.py NEW-358 run_start fallback — eager CAS latches a flag named for the outcome before the outcome is known, so a swallowed exception permanently consumes the claim
metadata:
  type: project
---

Round 1: NEW-358 fix (`_ensure_run_start_fallback()` in `core/loader_v2.py`,
`store.claim_run_start()`/`mark_run_start_recorded()` in
`telemetry/store.py`). Verdict: CHANGES REQUESTED, doc/code-scoped only
— nothing else in the diff blocked.

**Bug pattern (new, distinct from the plain docstring-overclaim class
already logged in [[telemetry_t9_loader_argv_provenance_scope_gap]] /
[[t8a_daemon_dedup_docstring_overclaim]] /
[[new345_thread_identity_run_stats_round2_second_overclaim]]):** an
atomic test-and-set (`claim_run_start()`) sets the flag `True` the
moment the *attempt* is claimed, not when the underlying work actually
succeeds. `_ensure_run_start_fallback()` claims, then calls
`recorders.record_run_start()`, which can raise (its
`build_run_start_body()` step does uncaught git/getprop subprocess work)
before ever reaching `store.mark_run_start_recorded()`. The outer
`except Exception` swallows the failure (correctly, per this project's
"telemetry must never block a real load" convention) but never
unclaims — so a *second* `load_primary()` call in the same process
(reload/retry) silently skips the fallback forever, permanently
reintroducing the exact orphaned-`run_start_amended` shape NEW-358 was
built to close, for that one process.

Live-reproduced directly (not just read): mocked `record_run_start` to
raise once, called `_ensure_run_start_fallback()` twice — second call
never re-attempted; `store._run_start_recorded` stuck `True` after the
first, failed attempt.

**Round 2 (2026-09-04): CLOSED, APPROVED.** Coordinator chose option (a)
— added `store.unclaim_run_start()`, called from
`_ensure_run_start_fallback()`'s except block, gated on a local
`claimed` flag set only after `claim_run_start()` itself returned
`True` (so a claim that never happened — e.g. `TELEMETRY_ENABLED` False,
or claim denied — is never wrongly unclaimed), and the unclaim call
itself wrapped in its own `try/except: pass` so a failure inside
`unclaim_run_start()` can't defeat the outer except block. Verified
directly:
- `telemetry/store.py::unclaim_run_start()` resets the flag under
  `_run_start_lock`; its docstring **honestly discloses**, rather than
  hides, the one theoretical gap (a second thread's genuinely successful
  concurrent `record_run_start()` in the narrow claim-to-failure window
  could be wrongly unclaimed too) and argues it's accepted/bounded
  because (a) this isn't a real multithreaded call pattern today and (b)
  `codey-metrics doctor`'s `duplicate_run_start_runs` already covers the
  resulting duplicate-record shape. This is the *correct* shape of
  disclosure this project's docstrings have repeatedly gotten wrong
  before — noting the real residual gap instead of asserting a stronger
  guarantee than the code provides.
- All three previously-flagged overclaiming docstrings
  (`_emit_argv_provenance()`, `_ensure_run_start_fallback()`,
  `claim_run_start()`) were corrected — confirmed by reading each in
  full, not just grepping for the old flagged phrase.
- `recorders.record_run_start()` calls `store.mark_run_start_recorded()`
  strictly *after* `store.write_run_provenance(record)`, itself strictly
  after `build_run_start_body()` (the git/getprop subprocess work) —
  confirmed by reading the full function body, so any exception in body
  construction really does propagate before the mark, matching the
  round-2 docstrings' claims.
- Negative-controlled the fix directly: hand-removed the
  `store.unclaim_run_start()` call from `_ensure_run_start_fallback()`'s
  except block and reran
  `test_ensure_run_start_fallback_unclaims_on_failure_so_next_call_retries`
  — it failed exactly as expected (second `_ensure_run_start_fallback()`
  call never reached `record_run_start` a second time), confirming the
  new test is load-bearing, not decorative. Restored the file afterward
  and confirmed `git diff --stat core/loader_v2.py` matched the
  pre-negative-control state (121 insertions/5 deletions).
- `tests/test_loader_v2_telemetry.py`'s new retry test genuinely
  exercises the real claim/unclaim state machine: it captures
  `_real_claim_run_start`/`_real_unclaim_run_start` at module-collection
  time (before the file's autouse `_capture_telemetry` fixture pins
  `claim_run_start` to `lambda: False`), then `monkeypatch.setattr`s
  those real functions back in for just that test, plus
  `store.reset_for_tests()` to clear prior state. It asserts a `flaky()`
  record_run_start counter reaches `2` — i.e. the *second*
  `_ensure_run_start_fallback()` call actually re-invokes
  `record_run_start`, not just that the internal flag value changed.
  Sound pattern, reusable for future "override an autouse fixture's pin
  for one test" needs.
- `pytest tests/test_loader_v2_telemetry.py tests/test_telemetry_store.py
  tests/test_telemetry_t2_run_start.py -q` → 43 passed (verbatim,
  reproduced independently). `pytest tests/ -q` → 1433 passed, 1 skipped
  (verbatim, reproduced independently — matches coordinator's claim
  exactly).
- Diff scope confirmed limited to `core/loader_v2.py`,
  `telemetry/recorders.py`, `telemetry/store.py`, and the three test
  files — no ledger docs (`NEW_ISSUES.md`/`CODEY_MASTER_PLAN.md`/
  `PROJECT_LOG.md`) touched in this round's diff (`git diff --stat`
  against those paths was empty), consistent with the coordinator not
  yet having done the ledger-update pass.

**How to apply:** any time a review sees a boolean/CAS flag set
*before* the operation it gestures at has actually completed
(claim-then-attempt, rather than attempt-then-mark), check what happens
on the exception path specifically — read the except block, don't just
confirm the happy path is tested. When a fix adds an "unclaim on
failure" pattern, verify three things: (1) the unclaim is gated on a
local "did I actually claim" flag, not called unconditionally in the
except block; (2) the unclaim call itself can't raise out of the outer
except; (3) hand-remove the unclaim and confirm the fix's own new test
actually fails — a passing test after the fix proves nothing if it would
also have passed against the old, broken code.
</content>
