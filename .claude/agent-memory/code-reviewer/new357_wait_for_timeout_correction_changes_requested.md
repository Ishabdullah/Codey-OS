---
name: new357-wait-for-timeout-correction-changes-requested
description: NEW-357 wait_for()-timeout __cause__ guard fix in core/daemon.py + core/task_executor.py — round1 CHANGES REQUESTED (docstring overclaim only)
metadata:
  type: project
---

Round1 verdict: CHANGES REQUESTED, doc-only fix needed (mechanism itself sound).

**What was verified true, independently:**
- `asyncio.wait_for()`'s `TimeoutError.__cause__` genuinely is the inner
  `CancelledError` (confirmed live on Python 3.14.6, both directions: real
  wait_for timeout sets `__cause__`, a bare `TimeoutError()` raised from an
  awaited coroutine has `__cause__ is None`).
- Both real dispatch sites in `core/daemon.py` (planner-branch ~L1930,
  direct-branch ~L2064) carry the `isinstance(exc.__cause__,
  asyncio.CancelledError)` guard; the other two `except asyncio.TimeoutError`
  sites in the file (~L303, ~L1833) are unrelated `send_plan_request_async`
  timeouts, correctly untouched.
- Negative-controlled the guard directly: hand-removed the guard at the
  direct-branch site (Edit tool, not git checkout — Bash `cp`/heredoc was
  blocked by the sandbox classifier here, Edit worked fine), reran
  `test_socket_timeout_from_execute_task_does_not_trigger_correction`, it
  failed exactly as expected (correction called once instead of not at
  all), then restored via Edit and reconfirmed `git diff --stat` matched
  pre-probe and the test passed again. Guard is genuinely load-bearing.
- Site 2's `needs_planning` divergence risk (raised by advisor) does NOT
  materialize: `db_task` is the same dict object fetched once via
  `get_next_pending()` and never re-fetched; `clear_needs_planning()` only
  writes to SQLite via raw UPDATE, never mutates the in-memory dict. So
  `db_task.get("needs_planning")` evaluates identically at both the
  `_execute_task()` call and the correction call. Still a style
  inconsistency vs site 1 (which caches into a variable) — Suggestion only.
- Schema (`telemetry/schema/v1.json`) already has `timeout_sec: {type: int}`
  and `terminal_status` enum already has both `"cancelled"`/`"timeout"` —
  no schema change needed, confirmed by dumping the actual JSON.
- `emit_task_timeout_correction()` wraps its whole body in try/except
  Exception, so a telemetry-backend failure inside it cannot propagate to
  `fail_task()`/dispatch outcome — confirmed by code read + a dedicated
  test with the backend mocked to raise.
- Run-stats fields genuinely omitted from the correction's
  `record_task_finished()` call (not re-queried) — confirmed by reading the
  emitted kwargs directly, matches NEW-345's stale-thread-bucket rationale.
- Full suite: 1455 passed, 1 skipped (implementer's claimed baseline,
  independently reproduced).
- 10(b) self-flagged gap (pre-existing `_execute_task()`'s `timeout_sec`
  passed uncoerced vs this fix's `int()`-cast) is real — confirmed by
  reading `core/task_executor.py:472`. Severity: Confirmed but LOW, not a
  write-time blackout — `telemetry/store.py`'s `Store.record()` write path
  has no schema validation call; `schema.validate()` only runs in
  `telemetry/cli.py`'s doctor/rollup consumer path. So a float/string
  `task_timeout` config would silently write a type-violating record, only
  surfacing when someone runs `codey-metrics doctor`, not at emission time.

**The one real defect (blocks approval):** `telemetry/recorders.py`'s new
`record_task_finished()` docstring literally says the dispatch sites
"detect that a `task_finished` record was already emitted with
terminal_status='cancelled'" — nothing detects that. The guard only
inspects `exc.__cause__` on the caller's own `TimeoutError` and *infers*
the inner emission happened; it never reads any actual record. Concretely
wrong when `_execute_task()`'s `_telemetry_active` gate was False (or the
`TELEMETRY_ENABLED` kill switch was off) during the first emission — the
correction still fires unconditionally on the `__cause__` guard alone, so
you can get a **lone** `"timeout"` record with no preceding `"cancelled"`
one, which is exactly the state the docstring claims can't happen. Same
overclaim shape as [[t8a_daemon_dedup_docstring_overclaim]] — required fix
is one sentence: reword to "infers from `exc.__cause__`" not "detects",
and note the second record may be the only record if telemetry was
inactive during `_execute_task()`'s own emission.

See also [[git_checkout_path_wipes_uncommitted_diff]] for why the Edit-tool
negative-control-and-restore pattern (not git checkout/stash) is used here
too — an unreviewed diff was in the working tree the whole time.
