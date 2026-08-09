---
name: resource-gate-subtask4-release-model-slot-approved
description: TODO.md 7.4 sub-task 4 — daemon-side release_model_slot Unix-socket command — APPROVED
metadata:
  type: project
---

Reviewed `core/daemon.py`'s new `release_model_slot` command (NEW-69
prerequisite, sub-task 4 of 7.4) plus `core/thermal.py`'s new
`is_inference_active()` accessor and `tests/test_daemon_release_model_slot.py`
(13 tests). Verdict: **APPROVED, ready to commit.**

**What was verified directly, not just read:**
- `core/task_executor.py`'s `_execute_task()` really does bracket the
  entire `run_agent()` call with `start_inference()`/`end_inference()` in a
  try/finally — the busy-check premise holds.
- `SWAP_GUARD` (`core/loader_v2.py`) is a plain non-reentrant
  `threading.Lock`; both `ensure_model()` and the new handler use
  non-blocking `acquire()` + decline-as-busy — no deadlock, and concurrent
  same-model_id requests correctly serialize via this guard (second caller
  gets `busy_swap_in_flight`, doesn't double-unload).
- `_handle_client()`'s peer-UID check runs before generic `_handlers.get(cmd)`
  dispatch — `release_model_slot` is registered the same way as
  `ping`/`status`/etc., no auth bypass.
- Fail-closed on thermal-check exception: confirmed by reading the
  `except Exception` branch — returns `RELEASE_OUTCOME_BUSY_TASK`, not
  fail-open.
- `probe_port_health(port)` signature/usage in the confirm-poll matches its
  existing definition and call site.
- **Negative-control tested the test suite itself** (not just read it):
  hand-broke the `finally: SWAP_GUARD.release()` in a scratch copy of
  `core/daemon.py`, re-ran `tests/test_daemon_release_model_slot.py` — the
  autouse fixture's pre-test `assert SWAP_GUARD.acquire(blocking=False)`
  correctly failed and cascaded to 7 errors. Restored the file, re-ran to
  confirm clean 13/13 pass again. This is the technique to reuse when an
  orchestrating session claims "I fixed a test-only bug" — don't just read
  the fixture, break the underlying invariant and watch the fixture catch it.
- Independently confirmed `core.daemon` module has no `SWAP_GUARD` attribute
  (`hasattr` check) — the claimed test-file bug (2 tests referencing
  `daemon_mod.SWAP_GUARD`) was real, and the fix (reference
  `core.loader_v2.SWAP_GUARD` directly) is the correct one, not a
  papered-over false pass.
- Ran the full suite: 466 passed, 1 skipped, 0 failed (128.53s).

**Design notes (not bugs, just recorded for future re-checks):**
- Cooldown (5s) is armed only on a *confirmed* release, checked before
  SWAP_GUARD acquisition — closes both the concurrent-request thrash case
  (serialized by SWAP_GUARD) and the rapid-sequential case (blocked by the
  cooldown timestamp).
- `RELEASE_OUTCOME_BUSY_TASK` is reused for both the real busy-task case and
  the thermal-check-exception fail-closed case (same outcome constant, only
  the message text differs) — cosmetic, not a functional bug, flagged as a
  Suggestion only.

If sub-task 5 (wiring `main.py` to actually call this command) is reviewed
later, re-check: does the CLI handle every RELEASE_OUTCOME_* value
sensibly (especially `cooldown` and `unload_attempted_unconfirmed` — does
it retry, give up, or mislead the user)?
