---
name: resource-gate-subtask2-confirm-mark-slot-leak
description: core/resource_gate.py 7.4 sub-task 2 (loader wiring) — round 1 CHANGES REQUESTED, live-reproduced slot+process leak when confirm_resident_and_mark_slot() raises
metadata:
  type: project
---

## Finding: NEW-82's predicted failure mode, live-reproduced with real call sites

Sub-task 1 logged `NEW-82`: PENDING slot reservations have no TTL, and a
caller that reserves then fails to release on a failed load leaks the
reservation forever — explicitly assigned to sub-task 2/3 as "the actual
call-and-release pattern gets written" there.

Sub-task 2 wires `core/loader_v2.py:ModelLoader.load_primary()` and
`core/planner_loader.py:PlannerLoader.load()` onto `reserve_slot()` /
`confirm_resident_and_mark_slot()` / `release_slot()`, but only releases on
the two *explicit* failure branches it checks (`server.start()` returns
False; the "reused, didn't spawn" branch). It does NOT wrap
`confirm_resident_and_mark_slot()` (or the whole post-spawn sequence) in a
try/finally. If that call raises (`rg.mark_resident()`'s `_LockedState` does
a blocking `flock()` + atomic `os.replace()` write, both of which can raise
under fd exhaustion/disk pressure — realistic on this RAM-constrained
device, not a hypothetical), the outer `except Exception` in
`load_primary()`/`load()` swallows it and returns False, but by then:

- the server is already spawned and running (`self._server.is_running()` ==
  True)
- `self._slot_id` was never set (assigned only *after* the confirm call
  returns without raising), so `unload()`'s cleanup never fires
- nothing releases the reservation

Live-reproduced (not static analysis) by monkeypatching `rg.mark_resident`
to raise inside a call to `loader.load_primary()`:

```
load_primary() returned: False
loader._loaded: False
loader._slot_id: None
loader._server is not None (still holds a live process handle): True
loader._server.is_running(): True
released slots: []
```

Compounding factor: `reserve_slot()` is called with no `pid=` override at
either call site, so the slot's `pid` defaults to the *caller's own* PID
(the daemon process), not the spawned llama-server subprocess's PID — this
is `NEW-81` (also logged sub-task 1, deferred). PID-liveness reaping in
`list_slots()`/`reserve_slot()` therefore never reclaims this leaked slot as
long as the daemon lives, permanently double-counting it against
`total_reserved_bytes()` and eventually causing the gate to falsely deny all
future loads even with real headroom.

`tests/test_loader_resource_gate.py`'s 15 new tests cover happy-path,
spawn-failure, and reuse-path — none exercise `mark_resident()` /
`confirm_resident_and_mark_slot()` raising, so this gap shipped untested.

## Pattern to check for in future rounds of this module

**A reserve-then-confirm sequence where only the caller's own explicitly-
checked failure branches release the reservation, not a try/finally around
the whole sequence.** Any "reserve a resource, do work, confirm/register"
pattern in this codebase needs the release to be structurally guaranteed
(try/finally or equivalent) covering *every* exception the "do work"/
"confirm" step can raise — not just the specific failure modes the
implementer thought to check for. This is the same root pattern as
[[resource_gate_subtask1_reserved_bytes_toctou_rejected]]'s lesson (record
needs a lifecycle field / atomic critical section) one level up: here the
atomicity gap is at the *caller* level (loader), not inside
`resource_gate.py` itself, which is exactly why sub-task 1's own review
correctly couldn't have caught it (module had zero live callers then).

## Also verified this round (accurate, not blocking)

- Reuse-path logic (`self._server.process is None` → release, don't mark
  resident) is correct — verified by reading `LlamaServer.start()` directly,
  all three reuse branches leave `self.process` None, only `_spawn_locked()`
  sets it.
- `tests/test_new12_launcher_lock_and_swap.py`'s 21-line diff is additive
  only (one autouse fixture patching gate calls to deterministic stand-ins)
  — no existing assertion loosened, confirmed by reading the full diff not
  just the stat, per the [[plannd_new46_47_28_iter3_onestep_delegation_approved]]
  lesson (always check whether a fix is undermined elsewhere in the same
  diff, and whether a modified pre-existing test file hides a loosened
  assertion).
- NEW-83 (`embed_server.py:253`, bare `pkill -9 llama-server`, real CLAUDE.md
  rule-3 violation) confirmed pre-existing and NOT made more reachable by
  this sub-task: `_kill_port_occupant()` runs before the health check/new
  `register_slot()` call in `start()`'s control flow.
- NEW-84 (loaders never re-read `cfg.MODEL_PATH`/`cfg.PLANNER_MODEL_PATH`
  after import) confirmed by grep. Extra consequence found and worth adding
  to the entry: `resource_gate.py`'s own `KNOWN_MODEL_ARCHS` dict is also
  keyed on these same import-time path strings, so even a future re-read fix
  would still miss the arch lookup post-swap, silently dropping the KV-cache
  cost term to 0 — an admission-safety (cost underestimate → over-admission)
  angle, not just "wrong weights loaded."
