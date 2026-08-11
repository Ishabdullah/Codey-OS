---
name: resource-gate-74a-subtaskC1-round3-fixture-pid-fix-approved
description: TODO.md 7.4a sub-task C1 NEW-81 fix round 3 (test-fixture-only) — APPROVED, closes the round-2 regression
metadata:
  type: project
---

Round 3 (final) review of [[resource_gate_74a_subtaskC1_round2_fake_pid_regression]]'s
required fix. Scope this round: `tests/test_loader_resource_gate.py` only —
`FakeServerSpawned.process` changed from `MagicMock(pid=12345)` (dead,
arbitrary) to `MagicMock(pid=os.getpid())` (real, alive for the test's
whole lifetime), plus docstring updates.

**No commit boundary exists for this whole 7.4a chain** (rounds 1/2/3 are
all still one uncommitted working tree, same gap as
[[plannd_iter4_report_gen_deletion_scope_warning]]) — `git diff --stat`
against HEAD shows all of core/resource_gate.py, loader_v2.py,
planner_loader.py, tests/test_resource_gate.py too, none of which moved
this round. Confirmed scope two ways: (1) mtime — the test file's mtime
was ~13 min newer than every other touched file, all four "old" files
landing within 4 microseconds of each other (consistent with a stash/pop
during round-2 isolation, not a bulk rewrite this round); (2) re-read the
actual content of `reserve_slot()`'s reap-then-sum ordering (still at
~line 2176-2192, unchanged from round 2's description) and
`load_primary()`'s pid-forwarding branch (still forwards
`pid=self._server.process.pid` only in the spawned branch, releases and
never marks resident in the reuse branch) — matches round 2's approved
description verbatim. Advisor correctly flagged that mtime alone doesn't
prove content identity; the content re-read closed that gap.

Verified independently (not just accepted the implementer's claim):
- Every other `pid=12345/54321/42` fixture instance across the test suite
  (`test_resource_gate.py:670`, `test_new12_launcher_lock_and_swap.py:41`,
  `test_new84_stale_model_path.py:43`) genuinely doesn't hit the live-reap
  path — first uses `reap_dead=False` explicitly, other two mock
  `rg.mark_resident` directly.
- The docstring's *universal* claim ("every current caller of
  FakeServerSpawned except the e2e test is unaffected") checked against
  all 8 call sites by line number, not just the one named example
  (`test_ensure_model_eviction_failed_sets_outcome`) — all 7 non-e2e sites
  either mock `mark_resident` directly or (eviction_failed specifically)
  never reach it, confirmed by reading `ensure_model()`'s actual control
  flow (`EVICTION_FAILED` returns before `load_primary()`/`mark_resident()`
  is ever reached).
- NEW-134 (cited in this round's context) is actually present in
  `NEW_ISSUES.md` (grepped, found at its own numbered entry) — not just
  claimed.
- Disclosed limitation ("os.getpid() can't distinguish rebind-from-child
  vs left-at-caller-default") is real and correctly scoped: the e2e test
  doesn't assert on `pid` at all, and the distinct rebinding assertion
  (`slots[0]["pid"] == real_pid`, a genuinely different, independently
  alive PID) lives in `test_load_primary_crash_then_reload_not_denied_by_ghost_slot_new81`
  via its own `_fake_server_with_pid()` factory — not an unaddressed gap.
- Full suite re-run live: `691 passed, 1 skipped, 68 warnings in 107.91s`
  — matches implementer's claim exactly, zero failures.

**APPROVED. This closes the 3-round chain for 7.4a sub-task C1 (NEW-81
ghost-slot fix).** Next step is live-verifier, then commit.

**Lesson reinforced**: mtime clustering (multiple files sharing a
microsecond-identical timestamp) is a signal of stash/restore, not
evidence of "untouched" by itself — always re-read the specific lines a
prior round's approval depended on (line numbers, control-flow branches)
to confirm content identity, not just file metadata.
