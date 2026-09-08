---
name: new68_inference_retry_and_new413_release_cli_approved
description: NEW-68 core/inference.py bounded DEFERRED-only retry + NEW-413 piece-1 tools/release_model_cli.py — both APPROVED, no findings
metadata:
  type: project
---

Round 2 of the process-lifecycle cleanup series (round 1: [[new414_lora_rollback_new91_163_batch_approved]]). Two items, both **APPROVED**.

**NEW-68 (`core/inference.py:_start_server()`):** added a 3-attempt,
1.5s-sleep bounded retry around `get_loader().ensure_model()`, but ONLY
when `loader.get_last_ensure_outcome() == LOAD_OUTCOME_DEFERRED`; any
other outcome (`GATE_DENIED_HARD`/`ERROR`/`SPAWN_FAILED`/etc.) still
raises immediately with zero wasted retries — read the actual code, not
just the docstring, and confirmed the branch logic does exactly this.

- **The "never runs on an asyncio event loop" claim is real, verified
  independently, not just trusted from the implementer.** Traced every
  cited caller (`core/agent.py`, `main.py`, `core/planner.py`,
  `core/githelper.py`, `core/recursive.py`, `core/orchestrator.py`,
  `core/memory_v2.py`) — all import `infer` from `core.inference_v2`,
  which has **zero** `async def`/`await`/`asyncio` usage in the entire
  file (grepped directly). The only place `core/daemon.py` (the one
  asyncio event-loop process in this codebase) reaches this code is via
  `core/task_executor.py:_execute_task()`'s
  `loop.run_in_executor(None, _run_capability)` worker thread — grepped
  `core/daemon.py` for `inference_v2`/`_start_server` directly: zero
  hits, confirming the daemon never calls this on the loop itself. This
  is the load-bearing safety argument for the whole fix (a blocking
  1.5s×3 sleep on the actual event loop would stall the daemon) and it
  holds.
- **Pre-existing TOCTOU note, not a new bug:** `get_last_ensure_outcome()`
  reads a plain instance attribute set by `ensure_model()` just before
  return, with no lock protecting the gap between one thread's
  `ensure_model()` return and its own `get_last_ensure_outcome()` read —
  a second concurrent caller's `ensure_model()` call in that gap could in
  theory overwrite the outcome before the first thread reads it. Did not
  flag as a new finding: this exact read-right-after-call pattern is
  already established at both `main.py` (`_load_primary_with_gate_recovery`)
  and `core/daemon.py:1041` predating this diff — this fix follows
  existing convention, doesn't introduce a new race class.
- **Disclosure check (item 4 of the review brief) confirmed honest:**
  NEW-68's ledger entry explicitly states the retry "adds up to ~3s ...
  to that same already-over-budget path" against its own prior
  190s-vs-180s severity-correction note, rather than glossing over it.
- New test `tests/test_new68_start_server_retry.py` (3 cases) genuinely
  exercises the real branch logic via `mock_loader.ensure_model.side_effect`
  and asserts exact `call_count` (1 for immediate-raise, 3 for
  exhausted-retries, 3 for succeed-on-3rd) — not vacuous "eventually
  raises" tests.

**NEW-413 piece 1 (`tools/release_model_cli.py`):** thin CLI wrapper
around `core.daemon.send_command("release_model_slot", {"model_id":
"primary"}, timeout=20.0)`, meant to be called by the separate
`~/Codey-Aigentik` repo's own warm-up-failure exit path (not touched
this round).

- Read `_handle_release_model_slot()`'s actual code (not just docstring):
  confirmed it fail-closed declines (`RELEASE_OUTCOME_BUSY_TASK`) both
  when `ThermalManager.is_inference_active()` is true AND when the
  thermal check itself raises, and separately declines
  (`RELEASE_OUTCOME_BUSY_SWAP`) when `SWAP_GUARD` can't be acquired
  non-blocking — the safety claim underpinning "safe to call
  unconditionally from an external process" is real, not just asserted.
  This matches the already-reviewed handler from
  [[resource_gate_subtask4_release_model_slot_approved]] (same handler,
  no changes to it this round).
- Verified the script's exit-code mapping against the FULL
  `RELEASE_OUTCOME_*` set in `core/daemon.py` (8 constants), not just
  the 2 the script explicitly names: `send_command()` itself raises
  `RuntimeError` on any `status == "error"` response, which covers
  `RELEASE_OUTCOME_INVALID_MODEL` and `RELEASE_OUTCOME_ERROR` (both
  return `"status": "error"`) — caught by the script's own `except
  Exception` → exit 1. `RELEASED`/`ALREADY_UNLOADED` → exit 0.
  `BUSY_TASK`/`BUSY_SWAP`/`COOLDOWN`/`UNCONFIRMED` (all `"status": "ok"`)
  fall through the generic else-branch → exit 2. All 8 outcomes land
  somewhere sensible; nothing silently mishandled.
- `tests/test_release_model_cli.py` patches `core.daemon.send_command`
  and calls the real `main()` across success/already-unloaded/busy/
  unreachable-daemon branches. No explicit `RELEASE_OUTCOME_UNCONFIRMED`
  test case, but the busy-decline test already exercises the generic
  "any non-released/already-unloaded ok-status outcome → 2" code path
  the unconfirmed case also hits — noted as a minor coverage gap, not a
  blocker.
- Confirmed `~/Codey-Aigentik` genuinely untouched: `git status
  --short`/`git diff --stat` in that separate repo show zero tracked
  changes (only unrelated untracked cache directories).
- The `sys.path.insert(0, ...)` pattern in the new script is a real,
  independently-verified established convention — cross-checked against
  the existing sibling `tools/ensure_model_cli.py`, which uses the
  identical line for the identical reason (direct invocation from
  Aigentik's `sys.path[0]` being `tools/`, not repo root).

**Live-verified, not just claimed:** ran `python -m pytest tests/ -q`
myself — exact match to the claimed `1517 passed, 1 skipped in
246.29s`. Also ran `python3 tools/release_model_cli.py` as a real
subprocess with no daemon running (there WAS a live orphaned
llama-server already running on this device at review time, RAM
6.9GB used — did not touch it, script only tried a Unix-socket
connect, never spawns/loads anything) — got the claimed "could not
reach daemon" stderr message and exit code 1, real not paraphrased.

No new findings. Both items APPROVED.
