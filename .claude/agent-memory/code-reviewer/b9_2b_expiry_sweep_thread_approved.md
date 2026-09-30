---
name: b9_2b_expiry_sweep_thread_approved
description: B9.2b estimate expiry-sweep daemon thread (restoricon_core/api/expiry_sweep.py) — Rule-4 review, APPROVED after full-suite OOM triage
metadata:
  type: project
---

Phase B9.2b (2026-09-30): adds `EstimateExpirySweepThread` (in-process daemon
thread inside `RestoriconAPIServer`) + `EstimateService.sweep_expired()`
(`SENT`/`VIEWED` → `EXPIRED` once `expires_at` passed). Rule-4 mandatory
review (process-lifecycle). Verdict: **APPROVED**.

**What held up on independent verification** (all traced against real code,
not the implementer's docstring claims):
- `EstimateExpirySweepThread` genuinely uses `threading.Event.wait(interval)`
  (interruptible), `stop()` sets event + bounded `join(timeout=5.0)`, tracked
  by reference (`self.expiry_sweep_thread`) and joined, never killed by name
  — rule-3 compliant.
- `sweep_expired()`'s per-row `try/except Exception: continue` genuinely
  isolates one bad row from the rest of the batch, and the thread's own
  `_loop()` has a second, tick-level `try/except` around the whole
  `sweep_expired()` call — two independent layers, both real (test:
  `test_sweep_one_bad_row_does_not_abort_the_rest_of_the_batch`,
  `test_thread_loop_survives_sweep_expired_raising`).
- The mid-round atomicity fix (status-UPDATE + `audit.log()` sharing one
  `with conn:` block) is real and correct — but *not* for the reason the
  docstring implies. Python's `sqlite3` has **no true nested transactions**
  via `with conn:` — it's one flat transaction per connection until a
  `commit()`/`rollback()` fires. `audit.log()` opens its OWN internal
  `with conn:` on the SAME thread-local connection; its `__exit__` is what
  actually commits (success) or rolls back (exception) the UPDATE+INSERT
  *together*, since they're still one uncommitted transaction at that point.
  The outer `with conn:` in `sweep_expired()` then does a redundant
  commit-of-nothing. End result matches the claimed behavior (audit failure
  → status change also rolled back), but the mechanism is "sqlite3 has no
  real transaction nesting, so it works by accident of flat-transaction
  semantics," not "nested `with` blocks give real atomicity." **Always trace
  this exact way when a diff claims atomicity via nested `with conn:` in
  this codebase** — check whether the callee also opens its own `with conn:`
  on the same thread-local connection object, and reason about sqlite3's
  actual commit/rollback timing rather than trusting the nesting intuition.
- CAS guard (`WHERE id = ? AND workflow_status = ?` + rowcount check)
  present and matches `transition()`'s/`record_share_link_view()`'s own
  precedent.
- `actor=None` → `actor_role='system'`/`actor_type='agent'` confirmed against
  `AuditService.log()`'s real code (lines ~304-305), matches
  `record_share_link_view()`'s only other precedent.
- Candidate SQL scope (`workflow_status IN ('SENT','VIEWED') AND expires_at
  IS NOT NULL AND expires_at < ?`) verified correct; tests parametrize all 9
  OTHER statuses individually (not just spot-checking two), confirming none
  are touched even with a past `expires_at`, and a separate test confirms
  null/future `expires_at` is excluded.
- Thread-local connection + shared-cache `:memory:` URI mode
  (`file:restoricon_mem_N?mode=memory&cache=shared`) confirmed directly in
  `database.py` `DatabaseManager.__init__`/`get_connection()` — the sweep
  thread and HTTP-handler threads do see consistent state despite separate
  connection objects, for both `:memory:` (test) and file-backed (prod) DBs.
- **The implementer's disclosed "no B7 backup thread precedent" correction
  is accurate** — confirmed by reading `core/backup_documents.py` (a
  `--daemon`/`time.sleep(interval)` CLI loop) and `lib/service_manager.sh`
  (`start_backup_docs()`/`stop_backup_docs()`, PID-file-managed, `nohup`'d
  as a *separate OS process*). `codey_estimator_service.md` §9 item 3's "B7
  backup thread" framing is factually wrong — B7 backup has never been an
  in-process Python thread. Logged as a doc-accuracy finding (rule 6), not a
  code blocker.

**The full-suite `tests/` OOM investigation (the one open item worth
recording a pattern for)**: implementer could not get a clean full-suite run
and flagged it explicitly rather than papering over it (good — matches rule
5). I reproduced: with the diff applied, a full `tests/` run crashed twice
in this session — once `OSError: [Errno 12] Out of memory` inside pytest's
OWN `cleanup_dead_symlinks` teardown (i.e., after all tests had already
run), once `Fatal Python error: Aborted` inside `database.py:2075
init_schema` (a `:memory:` DB construction inside `test_user_management.py`,
the LAST file in collection order, ~2680 tests into the run). A `git stash
-u` → clean baseline run (diff removed) passed cleanly once: `2679 passed, 1
skipped in 440.17s`. `database.py` is 100% untouched by this diff
(`git diff --stat` confirms 0 lines), and the crash both times happened in
code/files this diff never touches, at the very tail of an already very
long (2698-test, ~7-8min) run, on a device already running two live
`llama-server` processes in the background the whole session (confirmed via
`ps aux`) — textbook rule-2 RAM-constrained-device exhaustion, not a diff
regression. Scoped `tests/test_restoricon_core/` (1498 tests, matches
implementer's claim exactly) passed clean twice independently (once by me,
matching the implementer's own two claimed clean runs).

**Pattern for future full-suite-OOM triage**: (1) always `git diff --stat`
the crash-site file to confirm the diff genuinely never touches it before
calling it "unrelated." (2) Compare where in collection order the crash
falls (`pytest --collect-only -q`) against where the diff's own new test
file sits — if the crash site is nowhere near the diff's own tests, that's
real evidence, not circumstantial reasoning. (3) A crash whose EXACT FAILURE
MODE changes between identical repeated runs (OSError-at-teardown vs.
Fatal-Abort-at-unrelated-init_schema-call) is itself evidence of
non-deterministic environmental OOM rather than a deterministic logic bug
in the diff — a real regression would tend to fail the same way every time.
(4) Still don't call it "fully verified" — call it what it is: the diff
could not be given a 100%-clean full-suite run on this device in this
session, the scoped suite is clean, and the crash pattern points strongly
away from the diff. That's the honest rule-5 statement, not a paraphrase to
"tests pass."

See also [[b9_2_estimate_service_changes_requested]] (prior B9.2 round,
found an unlogged Critical via advisor-directed empirical repro — this round
had no equivalent hidden bug; the implementer's own self-caught atomicity
fix already closed the analogous gap here).
