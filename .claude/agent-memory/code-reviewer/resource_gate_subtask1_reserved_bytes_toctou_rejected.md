---
name: resource-gate-subtask1-reserved-bytes-toctou-rejected
description: core/resource_gate.py sub-task 1 (7.4) — REJECTED round 1 for a docstring/behavior contract mismatch on reserved_bytes plus a real TOCTOU across 3 separate flock acquisitions; round 2 fix APPROVED after independent verification
metadata:
  type: project
---

## Round 2 (fix) — APPROVED

Implementer added `status` (SLOT_STATUS_PENDING/RESIDENT) per slot,
`total_reserved_bytes()` now filters to PENDING only (docstring updated to
match, and matches `compute_headroom_bytes()`'s contract), and collapsed the
3-call sequence into one `reserve_slot()` that holds a single `_LockedState`
flock across reap → compute-reserved → `can_admit()` → append-and-write.
Verified directly, not from the report:

- Read the full current `core/resource_gate.py` by hand and confirmed
  `reserve_slot()`'s critical section is genuinely one `with
  _LockedState(...)` block with no gap between check and write. Live
  meminfo/thermal reads are captured *before* the lock (documented
  rationale: blocking flock with no timeout, must not stall other
  processes on a slow sysfs read) and passed in as fixed values — this is
  fine because those are independent external signals, not part of the
  locked state, so no new race is introduced by reading them outside the
  lock.
- Ran the concurrency test (`test_reserve_slot_concurrent_does_not_over_admit`,
  12-thread `threading.Barrier`-synchronized race against a fixed budget
  that allows exactly 2 admissions) 6x myself — stable, always exactly 2.
- **Independently proved the negative-control test is real, not vacuous**:
  monkeypatched `rg.reserve_slot` to the old unsafe 3-lock-acquisition
  pattern and re-ran the *real* regression test function directly (not the
  negative-control test — the actual `test_reserve_slot_concurrent_does_not_over_admit`)
  against it. Result: 12/12 over-admitted (expected 2), test correctly
  failed. This is the standard to hold future "negative control" claims to
  in this project — don't just read the negative-control test's own
  assertion, actually swap the implementation under the *real* test and
  watch it go red.
- Full suite: 331/331 passed (up from the pre-fix 321; resource_gate.py's
  own file went 41→51 tests, consistent with the claimed 9 new tests, off
  by one from a pre-existing count drift, not worth chasing).
- NEW-80/81/82 (lock-fd leak on flock() failure, no pid-rebinding at
  PENDING→RESIDENT, no TTL on abandoned PENDING reservations) all
  correctly logged as deferred: module still has zero live callers
  (sub-tasks 2-5 wire it in), so none of these are reachable bugs yet —
  correctly NOT used to block sub-task 1 sign-off.
- `TODO.md`/`PROJECT_LOG.md` diffs checked for overclaiming per rule 7:
  correctly marked "code-complete," explicitly NOT claimed
  "live-verified," with the exact justification (no process-lifecycle
  risk in this sub-task, module unwired) rather than a bare label swap.
- `core/thermal.py`'s new `get_current_temp_c()` wrapper (both instance and
  module-level) is a minimal, side-effect-free addition matching
  resource_gate.py's docstring claims about it.

## Round 1 (original rejection) — kept for the bug-pattern lesson

7.4's resource gate (`core/resource_gate.py`, standalone, not wired into any
running path yet — sub-tasks 2-5 migrate `daemon.py`/`loader_v2.py`/
`planner_loader.py`/`main.py` onto it) was well-built and well-documented:
NEW-21's real incident numbers used correctly as a regression test fixture
(not softened), self-corrections (MemFree→MemAvailable, 0.85→0.60 ceiling
fraction) genuinely documented in-code as provisional, not just claimed in
the report, 321/321 full suite pass verified myself, scope clean
(`core/lora_import.py` correctly untouched, NEW-24's "two sites not one"
correction verified by grep). Still rejected on two findings in the
cross-process residency store.

### The bug pattern (worth checking for elsewhere)

**A "reserved/in-flight" accounting mechanism whose docstring says one thing
and whose implementation does another, because the underlying data record
has no lifecycle field to distinguish the two states it's meant to
disambiguate.**

`compute_headroom_bytes()`'s docstring defines `reserved_bytes` as covering
ONLY slots "concurrently being admitted/loaded but haven't yet shown up in
a fresh /proc/meminfo read" (i.e., in-flight only). `total_reserved_bytes()`
originally summed `cost_bytes` over EVERY live slot regardless of lifecycle
state — the same self-referential-guard bug class as the project's known
PID-file self-race bug, just in memory-accounting form. **Check for this
pattern specifically whenever a module tracks "things I've already
claimed/reserved" and later re-reads a live external signal that might
already reflect those claims — the record needs a lifecycle/state field, or
the two numbers get double-counted.**

### The TOCTOU (secondary finding, same root cause/fix)

`total_reserved_bytes()` → `can_admit()` → `register_slot()` were three
separate flock acquisitions, not one atomic critical section. **Correct fix
for both findings at once** (what round 2 actually did): add a
`state: "pending" | "resident"` field to the slot record, have
`total_reserved_bytes()` take an explicit state filter (or default-filter),
add a promotion function for pending→resident, and collapse the sequence
into one atomic reserve-and-register call that reads/computes/appends under
a single held flock.

### Also worth re-checking in future rounds of this module

A code comment claiming a safety margin is "comfortable" should be checked
by hand-computing the module's own formula, not accepted at face value —
found the `DEVICE_CEILING_USABLE_FRACTION=0.60` comment's "comfortably
admits the 7B model" claim was actually a ~1.8% (~117MiB) margin. Correct
instance of rule 6 even though nothing was technically "verified" wrong
before — it was just asserted without the arithmetic being shown.

See also [[new12_swap_lock_sequential_swap_rejected]] (same "prove a
regression test actually red/green-cycles the fix" discipline this round 2
review applied by hand-reverting to the unsafe pattern and re-running the
real test).
