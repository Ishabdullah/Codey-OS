---
name: new145_149_155_option_c_approved
description: NEW-145/149/155 chain Option C (context-ceiling kill+respawn upgrade) fix review — approved with 3 warnings
metadata:
  type: project
---

Reviewed 2026-08-27: `core/daemon.py` (`_handle_status()` running_active
+ `daemon_task_in_progress()`), `core/loader_v2.py`
(`_kill_single_pid_term_then_kill()`, `_resolve_resident_pid_and_n_ctx()`/
`_resident_n_ctx_if_smaller()`/`_upgrade_resident_if_safe()`,
`allow_upgrade` flag), NEW_ISSUES.md NEW-256, new test file
`tests/test_new145_149_155_option_c.py`. **APPROVED.**

**Both flagged deviations verified correct against source, not just the
implementer's stated reasoning:**
- Slot-store-first/`/proc`-fallback ordering matches
  `_reconcile_adopted_slot()`'s real code exactly (read side by side).
  NEW-200's `PermissionError`-on-every-caller claim confirmed directly in
  `resolve_port_owner_pid()`'s docstring+implementation.
- `stop()` really does use `os.killpg(os.getpgid(...))` (confirmed by
  direct read) — narrowing to `os.kill()` on the single resolved PID is
  correct, and matches `embed_server.py:_kill_port_occupant()`'s own
  already-reviewed decision (also read directly: that function actually
  uses immediate `os.kill(pid,9)`, no TERM-first escalation — the new
  code's TERM-then-8s-wait-then-KILL shape is closer to `stop()`'s shape,
  scoped to a single PID; docstring's citation of embed_server is only
  for the narrowing decision, not the escalation shape, and is accurate
  on that narrower claim).
- `test_start_allow_upgrade_true_never_uses_killpg` genuinely exercises
  the real kill helper (only `os.kill`/`os.killpg`/`os.getpgid` mocked)
  and asserts `killpg`/`getpgid` never called — read the test body, not
  just the name.

**Asymmetry invariant (point 3) — held up under trace.** `interactive`
in `load_primary()` is a **pre-existing** signal
(`rg.is_interactive_session_active()`, from 7.4b sub-task C, unchanged
by this round) reused as `allow_upgrade=interactive`. Existing test
`test_no_interactive_session_uses_background_n_ctx` was extended to
assert `FakeServerSpawned.last_allow_upgrade is False`; hand-broke it
(`allow_upgrade=True` unconditionally) and confirmed the test fails —
real regression guard, not decorative.

**Known gap (point 4, `is_interactive_session_active()` = "a TUI session
file exists" not "I am mid-request") is real but does NOT create a new
safety hole**, on trace: the actual kill decision is fully gated by
`daemon_task_in_progress()` at kill time, independent of why the caller
believed `allow_upgrade` should be True. A watchdog-triggered
`ensure_model()` cold-load mislabeling itself as "interactive" can at
worst trigger a wasted respawn when nothing is actually busy — it cannot
kill a server that's mid-flight for a real background task, because that
task's row will read "running" regardless of who invoked
`load_primary()`. **Not documented anywhere in this diff or
NEW_ISSUES.md** despite the task's framing implying it should be — this
itself is a rule-8 gap (logged as a finding, not blocking, since the
safety property survives it).

**3 warnings, none blocking:**
1. `core/daemon.py`'s new inline comment claims `_handle_status()`'s
   `running_active` uses "the SAME `task_timeout` threshold
   `_handle_health()` already uses" — **false**, per the diff's own
   NEW-256 entry: `_handle_health()` hardcodes literal `1800`, never
   reads config. The new code itself is correct (verified it really
   calls `self._config.get("tasks", "task_timeout", default=1800)`,
   confirmed via negative control — hardcoding 1800 there does NOT fail
   any test, so the code's correctness rests on direct read, not test
   coverage). Comment should be fixed to say "the same *default value*,
   not the same *mechanism*."
2. **Zero test coverage for the resource-gate slot-release-on-kill path
   (point 8).** `release_slot` is stubbed in the `fake_resource_gate`
   fixture but never asserted-called. Negative control: deleted the
   `rg.release_slot(existing_slot["slot_id"])` call in
   `_upgrade_resident_if_safe()` — full test file still 26/26 green.
   Slot leak would go undetected by this suite. Code itself verified
   correct by direct read.
3. **Zero test coverage that `running_active`'s threshold is actually
   config-sourced vs. a hardcoded duplicate** (the exact NEW-256 bug
   class, in the NEW code). Both `_handle_status()` tests use
   `task_timeout=1800`, indistinguishable from a hardcoded `1800`.
   Negative control confirmed: hardcoding it inline still passes both
   tests.

Live-verification still required (rule 2/7) — unit tests can't observe a
real port-in-use race, a real TERM-then-KILL kill+respawn cycle, or a
real `daemon_task_in_progress()` round-trip against a live daemon
process. Flag for live-verifier: daemon-only harness per the NEW-14
swap-pressure precedent (not a full `codey-start` stack, per rule 2).

**Process note:** mid-review, unrelated concurrent changes to
`restoricon_core/*.py` and `tests/test_restoricon_core/test_services.py`
appeared in the working tree (another session's in-flight work, test
count drifted 855→858 passed between runs). Confirmed via `git diff
--stat` on the specific reviewed files (`core/daemon.py`,
`core/loader_v2.py`) that this drift did not touch anything in scope —
see [[working_tree_cross_round_bleed]]. Always re-check `git diff --stat`
on your specific target files after any full-suite run in this repo,
not just the top-level pass/fail count.
