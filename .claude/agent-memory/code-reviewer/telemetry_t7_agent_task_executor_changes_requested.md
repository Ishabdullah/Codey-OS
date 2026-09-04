---
name: telemetry-t7-agent-task-executor-changes-requested
description: T7 category-E task-outcome telemetry (core/agent.py + core/task_executor.py) — round1 CHANGES REQUESTED, two false-value bugs + one false invariant comment
metadata:
  type: project
---

Round1 verdict: CHANGES REQUESTED. Design-scope-gap claim (superseded_by_plan
structurally unreachable from task_executor.py/agent.py alone, real caller sites in
core/daemon.py:1273/:1361 pass only a bare prompt string, record_task_started/finished
require non-optional task_id/task_type/needs_planning) verified true by independently
reading core/daemon.py and telemetry/recorders.py — the "inert until T8" disposition
itself is sound. Full suite 1388 passed/1 skipped, targeted suite 141 passed, both
verbatim-matched the task's expected counts.

**Three real findings, all in the honest-null/passivity space this layer's whole premise
rests on** (found via advisor call, then independently re-verified rather than accepted
on faith — see [[telemetry_t3_round3_release_budget_arg_order_litter]] for the same
verify-the-mechanism-yourself discipline):

1. `core/task_executor.py`'s new `except asyncio.CancelledError` branch unconditionally
   labels `terminal_status="timeout"`, on the theory that the only source of
   CancelledError is `daemon.py`'s `asyncio.wait_for(..., timeout=...)`. Traced this is
   false: `daemon.py`'s `run()` catches `KeyboardInterrupt` around `asyncio.run(self._main_loop())`
   — on a real SIGINT, `asyncio.run()`'s own internal shutdown cancels all still-pending
   tasks (including the suspended `_main_loop` task) as cleanup before re-raising,
   delivering a genuine CancelledError unrelated to any wait_for timeout. The design's
   own §2.E enum has a distinct `cancelled` value for this. SIGTERM itself is NOT this
   risk (`_handle_sigterm` just sets `self.running = False`, checked at loop top, no
   mid-await cancellation) — the KeyboardInterrupt/asyncio.run() cleanup path is the
   real one.

2. Module comment in `core/agent.py` claims "at most one run_agent() call is ever in
   flight" (justifying a plain module-level dict instead of thread-local state). False
   on the exact path #1 touches: `run_in_executor`'s worker thread is NOT killed when
   the awaiting `wait_for` cancels/times out — Python's documented behavior. The
   orphaned thread keeps running `run_agent()` to completion and can still mutate
   `_LAST_RUN_STATS`/`_run_agent_call_seq` after the NEXT task's `_execute_task` has
   already reset those globals for itself, corrupting the new task's stats. The `_seq`
   guard only detects "run_agent never started," not "two runs interleaved" — doesn't
   catch this. Currently non-exploitable (T7 is production-inert, no caller passes
   task_id yet) but the comment itself is false and T8 will trust it when wiring real
   call sites in.

3. `escalation_outcome`'s closed enum has no code for `[redirect]:` (human typed a
   redirect, no peer CLI ran) — implementer bucketed it under `peer_cli` as "closest
   fit." Judged this a wrong value, not an honest null — same shape as `NEW-341`.
   `escalate_or_park()` "running to completion" is a property of the call, not the
   outcome category being recorded.

**Why:** the advisor call caught all three on the FIRST pass, before I'd finished my own
trace — but each one was independently re-verifiable rather than something to take on
faith: #1 by reading daemon.py's SIGTERM handler + KeyboardInterrupt catch + asyncio.run
shutdown semantics; #2 by reasoning through documented run_in_executor/Future.cancel()
behavior; #3 by re-reading the actual call semantics of escalate_or_park(). All three
held up under independent verification — none were advisor overreach.

**How to apply:** on any future telemetry sub-task with an exception-mapping branch
(CancelledError, TimeoutError, etc. -> a status enum value), don't accept "the only
caller of this path is X" at face value — trace the process's OTHER paths into that same
except clause (signal handlers, asyncio.run()'s own cleanup machinery) before trusting a
1:1 mapping. Same for "at most one X in flight" invariant comments guarding shared
mutable state — check whether the mechanism used to enforce single-flight (awaiting
sequentially) actually survives cancellation/timeout of the underlying work, not just
the awaiting coroutine.
