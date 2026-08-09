---
name: resource-gate-subtask2-leak-fix-round2-approved
description: core/resource_gate.py 7.4 sub-task 2 (loader wiring) leak fix — round 2 APPROVED after independent red/green + a sharper negative control that isolates stop() from release_slot()
metadata:
  type: project
---

## Outcome

Round 1 (see [[resource_gate_subtask2_confirm_mark_slot_leak]]) found a live
slot+process leak when `confirm_resident_and_mark_slot()` raises after spawn.
Round 2's fix wraps the whole reserve→spawn→confirm sequence in
`core/loader_v2.py:ModelLoader.load_primary()` and
`core/planner_loader.py:PlannerLoader.load()` in try/finally, gated by a
`loaded_ok` flag set True only on the genuine success return. APPROVED.

## Verification method worth repeating: split-negative-control

My first negative-control attempt disabled the *entire* finally cleanup
block in one edit (`if False and not loaded_ok:`). Both new regression tests
went red — but that only proves *something* in the finally is load-bearing,
not that *each half* is. The finally does two independent things: `stop()`
the spawned process, and `release_slot()`. A single test assertion order
(slot-leak assertion runs before the orphan-process assertion in the source)
means a broken `stop()` alone could hide behind the slot assertion failing
first — the orphan assertion might never even execute.

Fix: disable **only** the `stop()` call (`pass  # self._server.stop()`),
leave `release_slot()` intact, rerun just the two confirm-raises tests.
Correctly discriminated: slot assertions passed, `proc.poll() is not None`
(orphan) assertion failed with a live PID — `pid=16699 is still running`.
This proves the orphan half of the test genuinely depends on the `stop()`
call, not just on the slot-release half.

**Pattern for future rounds**: when a fix bundles two independent cleanup
actions inside one guard (kill a process AND release a resource, close a
file AND update a counter, etc.), and the regression test asserts both
outcomes, do the negative control by disabling **each action separately**,
not by gutting the whole guard in one shot — otherwise an assertion-order
accident can hide a genuinely broken half of the fix.

## Also verified this round (accurate, not blocking)

- `stop()`'s kill logic operates strictly on `self._server.process` (a
  tracked `subprocess.Popen`/pgid), verified by reading `LlamaServer.stop()`
  directly (lines ~387-415) — no CLAUDE.md rule-3 violation introduced.
- `get_pid()`/`is_loaded()` are null-safe against the finally's
  `self._server = None` — no caller (traced `ensure_model()`,
  `_evict_planner_and_confirm_free()`) assumes non-None after a failed
  load; a failed load with the process still alive-but-unreferenced (reuse
  branch mid-exception) is intentionally "not ours to track", not a crash
  risk.
- Reuse-branch `rg.release_slot(slot_id)` inside the try (unguarded) — if it
  raises, propagates to finally, finally's guarded release retries (safe,
  no-op lookup-miss if already released), finally itself never raises
  (wrapped in try/except), original exception still reaches the outer
  handler correctly. Not a defect.
- Full suite: 362 passed, 1 skipped, real output both before and after the
  restore-from-backup round-trip.
- `core/daemon.py`/`main.py` confirmed untouched (`git diff --stat` empty).
- `core/lora_import.py`'s NEW-24 fix (routes secondary-model swap/rollback
  through the real `PlannerLoader` instead of a nonexistent
  `loader.load_secondary()`) is honestly self-documented as still not fixing
  the underlying gap — same root cause as NEW-84 (loaders bind
  `MODEL_PATH`/`PLANNER_MODEL_PATH` at import time, so `cfg.SECONDARY_MODEL_PATH`
  reassignment doesn't actually redirect the load). Link these two together
  if either is revisited.

## Status

Code-complete + unit-verified (including a real spawned `sleep 300`
subprocess standing in for llama-server — RAM-safe, no model loaded). NOT
yet live-verified: `confirm_resident_and_mark_slot()`'s real
`/proc/meminfo` polling has never run against an actual llama-server load
in any of these tests (all drive it through a patched `read_meminfo`).
Needs live-verifier before the round is marked done per CLAUDE.md rule 7.
