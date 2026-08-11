---
name: resource-gate-74a-subtaskC1-round2-fake-pid-regression
description: TODO.md 7.4a sub-task C1 NEW-81 fix round 2 — core fix correct, but broke a pre-existing test via a hardcoded fake PID; verified-claim mismatch caught by literal suite re-run
metadata:
  type: project
---

Round 2 review of [[resource_gate_74a_subtasksABC1_crash_ghost_slot_rejected]]'s
required fix (attach real spawned-subprocess PID to a slot at
`mark_resident()` time, so `reserve_slot()`'s existing dead-PID reap filter
can clear a crashed model's ghost slot before the new
`MAX_CONCURRENT_MODEL_BUDGET_BYTES` ceiling sums it).

**Core fix verified correct**, re-derived by hand, not by trusting the
implementer's stash-revert description: `reserve_slot()`'s reap filter
(`core/resource_gate.py` ~line 2177) runs inside the same lock, before
`_sum_committed_bytes()`, on the already-reaped list — a crashed model's
now-correctly-PID-tagged slot really is dropped before the ceiling check.
PID propagation (`loader_v2.load_primary()` /
`planner_loader.PlannerLoader.load()` → `confirm_resident_and_mark_slot(pid=...)`
→ `resource_gate.mark_resident(slot_id, pid=...)`) only fires in the
genuinely-spawned branch, never the "reused an existing server" branch
(which releases its own reservation and never calls `mark_resident()` —
no new ghost). The implementer's correction of my round-1 "`pid=None`"
description (real behavior: `reserve_slot()`/`register_slot()` both do
`if pid is None: pid = os.getpid()`, never a literal `None`) is accurate,
confirmed by direct read. New regression test
`test_load_primary_crash_then_reload_not_denied_by_ghost_slot_new81` is
genuine — two real `sleep 300` subprocesses, a real ~4.68GB on-disk model
file (confirmed present on this device), a real `os.killpg(SIGKILL)`
crash simulation, assertions against the real state store. NEW-134
(narrower residual gap: PENDING-window leak before `mark_resident(pid=...)`
ever runs) is an accurate, correctly-scoped finding, not overstated.

**Blocking finding this round — a real, unmocked, PRE-EXISTING test now
fails, and the implementer's "623 passed, 1 skipped" claim does not match
an actual re-run.** Live suite run:
`1 failed, 690 passed, 1 skipped` —
`tests/test_loader_resource_gate.py::test_real_gate_reserve_confirm_release_end_to_end`
FAILED. Isolated by stashing this round's diff and re-running that one
test alone: passes pre-diff, fails post-diff — a genuine regression
introduced by this round, not a flaky/pre-existing failure. Root cause:
`FakeServerSpawned` (this test file's own fixture, predates this round)
hardcodes `self.process = MagicMock(pid=12345)`. Before this fix,
`mark_resident()` never touched `pid`, so the fake value was cosmetic.
After this fix, `load_primary()` forwards
`pid=self._server.process.pid=12345` into `mark_resident()`, rebinding
the slot's `pid` to a PID that is not an actually-running process on this
device. This particular test is the ONLY one in the file that calls the
real (unmocked) `resource_gate.list_slots()` (default `reap_dead=True`)
after loading — so its next call reaps the slot it just marked resident,
`_pid_alive(12345)` being `False`, and `assert len(slots) == 1` fails.
Every other test using `FakeServerSpawned` in that file mocks
`resource_gate` functions directly, so they never hit real PID-liveness
reaping and stayed green — that's why only this one test broke and it's
easy to miss without a literal, full, live re-run.

**Lesson for future reviews of this module**: whenever a fix makes a
previously-cosmetic mocked field (like a fake `.process.pid`) suddenly
load-bearing (here: actually consumed by real PID-liveness reaping),
check every existing test fixture across the touched files that uses a
hardcoded/fake value for that same field — a mock that was harmless
before the change can silently start failing a real (not fully-mocked)
downstream assertion elsewhere in the same file, and this project's own
"verified: N passed" claims have now twice (see
[[resource_gate_74a_subtasksABC1_crash_ghost_slot_rejected]] and this
entry) needed a literal re-run to catch a mismatch — always re-run the
FULL suite yourself and diff the exact pass/fail counts against what's
claimed, never accept a summary.

**Required fix, not applied by me (implementer's job)**: give
`FakeServerSpawned` a real, currently-alive PID (e.g. `os.getpid()`, or a
throwaway spawned subprocess matching this same file's
`RealSpawnLlamaServer`/`_fake_server_with_pid` precedent) instead of the
hardcoded `12345`, so `test_real_gate_reserve_confirm_release_end_to_end`
keeps proving the real wiring works. Then re-run the full suite and paste
literal output.
