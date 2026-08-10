---
name: resource_gate_phase4_1_subtaskC_dispatch_gate_changes_requested
description: Phase 4.1 sub-task C (daemon dispatch gate, needs_planning pull-side planning) — code APPROVED via negative control, blocked on doc-drift + missing NEW_ISSUES entries
metadata:
  type: project
---

Reviewed `core/daemon.py`/`core/resource_gate.py`/`core/state.py`'s Phase
4.1 sub-task C: `can_dispatch_task()` gate consulted before
`try_claim_task()` in both `_process_planner_tasks()` branches, plus
`needs_planning` pull-side planning replacing `_handle_command`'s old
synchronous enqueue-time planning call.

**Code verdict: sound.** Claim-order fix independently proven by
hand-reverting the guard order in a scratch copy and rerunning
`tests/test_daemon_dispatch_gate.py` — the regression tests failed
exactly as expected (`'running' == 'pending'` assertion), confirming
real negative-control coverage, not a tautological test. `no_plan`
inversion genuinely fixed (verified against a real StateStore, not
mocked). `plan_only=True` path is byte-for-byte unchanged (diffed the
whole function). 496 passed, 1 skipped — up from 474/1, my own verbatim
run.

**Blocked on process, not code — CHANGES REQUESTED:**
1. Two of three implementer-flagged judgment calls were never logged to
   NEW_ISSUES.md despite rule 8: (a) `self.server.planner = self.planner`
   (daemon.py:684) is now dead code — confirmed via grep that
   `_handle_command` no longer touches `self.planner` after this diff,
   and nothing else reads `server.planner`; (b) a *new* crash window this
   diff introduces: between `planner.add_tasks(enriched)` committing N
   rows and `complete_task()` retiring the raw row, a crash leaves the
   raw row `running`+`needs_planning=1` forever — grepped `core/
   recovery.py` and confirmed there is NO stale-`running` reaper anywhere
   in this codebase (`_handle_health` only *reports* stuck tasks, never
   reaps them). Before this sub-task no such intermediate persisted row
   existed (planning was a synchronous RPC, not a claimed queue row), so
   this is new, not a restatement.
2. `TODO.md`/`WORK_QUEUE.md` still say sub-task C is "not started" /
   "no code changed" in the SAME diff that fully implements it with
   passing tests — the inverse of the usual stale-doc bug
   ([[resource_gate_phase5a_subtaskA_cpu_sentinel_changes_requested]]'s
   "zero implementation shipping alongside its own code"), same root
   cause: doc updates lag the actual working-tree state. Always run
   `git diff -- TODO.md WORK_QUEUE.md` and sanity-check the prose against
   what the rest of the diff actually contains, not just check the files
   changed.

**New technique note:** advisor caught that I'd only *grepped* the two
`result=t.get("result")` call sites the task brief asked about, not
opened them — "found via grep" is not the same as "traced and
resolved." Both turned out inert (one is DB rehydration gated to PENDING
status only, one is an unrelated subsystem reading its own JSON file),
but that had to be confirmed by reading, not inferred from a grep hit
count.
