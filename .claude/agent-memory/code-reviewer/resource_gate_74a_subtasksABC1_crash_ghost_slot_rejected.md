---
name: resource-gate-74a-subtasksABC1-crash-ghost-slot-rejected
description: TODO.md 7.4a sub-tasks A/B/C1 (zram signal, swap-headroom fn, cumulative budget ceiling) reviewed — CHANGES REQUESTED, C1 activates a dormant crash-recovery bug into a self-inflicted permanent-looking admission denial
metadata:
  type: project
---

Reviewed `core/resource_gate.py` + `tests/test_resource_gate.py` diff for
TODO.md 7.4a sub-tasks A (zram signal sourcing), B
(`compute_swap_assisted_headroom_bytes()`, pure/unwired), C1
(`MAX_CONCURRENT_MODEL_BUDGET_BYTES` cumulative-budget ceiling in
`can_admit()`/`reserve_slot()`).

**Everything independently verified clean**: `MAX_CONCURRENT_MODEL_BUDGET_BYTES`
arithmetic (`int(8.90*1024**3)` = 9,556,302,233, margin 47,901,426 bytes
over the 9,508,400,807-byte raw sum — recomputed by hand, matches);
check-order in `can_admit()` (hard_reject → budget-ceiling → thermal →
headroom, read directly, matches docstring); `reserve_slot()`'s
`_sum_committed_bytes(slots)` computed INSIDE the existing
`_LockedState` block on the already-held slots list (no nested lock, no
TOCTOU reopening); `compute_device_ceiling_bytes()` completely untouched
(grepped the diff, confirmed); `GateDecision`/`ResourceSnapshot` new
fields all keyword-defaulted, every construction site uses kwargs, zero
breakage risk; `hard_reject`/`LOAD_OUTCOME_GATE_DENIED_HARD` consumers
across main.py/daemon.py/loader_v2.py grepped — the new check's
`hard_reject=False` correctly routes to the existing retryable path, no
special-casing anywhere breaks; full suite run live, `619 passed, 1
skipped` — literal match to the implementer's claim; scope clean (`git
diff --stat` — only resource_gate.py/tests + docs, no model_tiers.py/
planner_service.py bleed).

**Blocking finding (Critical) — C1 activates a dormant crash-recovery
bug into a self-inflicted, effectively-permanent admission denial,
exactly the self-race bug class CLAUDE.md rule 4 exists to catch:**

Traced with the advisor's prompt ("does any re-reserve path count its
own existing slot?"). Confirmed by direct code read, not inferred:

1. `core/loader_v2.py:629` (`ModelLoader.load_primary()`) calls
   `rg.reserve_slot(spec)` with **no `pid=` argument** — the primary
   model's slot is registered with `pid=None` and NEVER updated
   afterward (`mark_resident()` at `core/resource_gate.py:2226` only
   flips `status`, never touches `pid`). Same gap in
   `core/planner_loader.py:90` for the planner's slot.
2. `reserve_slot()`'s own reap filter
   (`core/resource_gate.py:2177`): `s.get("pid") is None or
   _pid_alive(s["pid"])` — a slot with `pid=None` is **always kept**,
   regardless of whether the process behind it is alive or dead. So the
   primary/planner's own slot is *never* reaped by PID-liveness, ever.
3. `core/loader_v2.py:800-830` (`ensure_model()`): the only path that
   calls `unload()` (which releases the slot) before re-loading is the
   explicit thermal-restart branch. If the server crashes on its own
   (OOM-killed, segfault, etc. — `is_running()` now False), the
   `if self._loaded and self._server and self._server.is_running():`
   guard is simply False and execution falls straight through to
   `self._evict_planner_and_confirm_free()` → `self.load_primary()`
   with **no intervening `unload()`/`release_slot()` call**. The old
   RESIDENT slot (pid=None, per #1/#2, un-reapable) is still sitting in
   the state store when the new `reserve_slot()` call runs.

**Consequence, before vs. after this diff**: pre-C1, `RESIDENT` slots
were invisible to every admission check (`total_reserved_bytes()`/
`can_admit()`'s `reserved_bytes` are PENDING-only) — this crash-orphan
gap was latent, harmless dead weight. **This diff's `_sum_committed_bytes()`
deliberately sums PENDING+RESIDENT together** (by design, per TODO.md's
own C1 spec — that part is correct and necessary for the ceiling's
purpose). The side effect: a single primary-model crash now leaves a
~6.83GiB ghost RESIDENT slot that (a) can never be reaped by PID
liveness and (b) is never released by the crash-recovery reload path —
so the very next `load_primary()` retry sums ghost(6.83GiB) +
candidate(6.83GiB) = 13.66GiB > the 9.56GiB ceiling and is denied with
`budget_ceiling_exceeded=True`. Unlike a `hard_reject`, this reports as
"recoverable," but nothing in the crash-retry loop ever actually
releases the ghost slot — every subsequent crash adds another one,
making the model permanently unloadable on this device without a
manual/external state-store cleanup. This is the same self-referential-
guard bug shape CLAUDE.md rule 4 names by example (a daemon reading its
own preemptively-written PID as evidence of a duplicate).

**Required fix, not applied by me (implementer's job)**: at minimum,
`load_primary()`/planner's loader must pass the real spawned PID into
`reserve_slot()`/attach it to the slot before/at `mark_resident()` time,
so the reap-dead filter can actually detect and drop a crashed process's
stale slot; and/or `ensure_model()`'s cold-load fallthrough must release
any slot this loader still holds (`self._slot_id`) before re-reserving,
mirroring the thermal-restart branch's explicit `unload()` call. Needs
its own test that simulates a crash (server dead, `self._slot_id` still
set, no explicit `unload()` call) followed by a reload attempt, and
asserts the reload is NOT wrongly denied by the budget ceiling.

**Secondary finding (Warning, required NEW_ISSUES.md log before commit,
not blocking on its own)**: ghost **PENDING** slots (registered before
spawn, also `pid=None` at that point) have the same never-reaped
property — pre-C1 this only skewed a live-`MemAvailable`-relative
`reserved_bytes` (self-healing as `MemAvailable` recovers); post-C1 it
permanently burns a slice of the *fixed* budget ceiling too. Related to,
but a sharper amplification of, the existing "new crash-window w/ no
reaper" finding already logged from Phase 4.1 sub-task C — cross-
reference, don't duplicate, but the C1-specific consequence (fixed
ceiling vs. a live/self-healing signal) is new and must get its own
NEW_ISSUES entry.

**Not blocking, correctly triaged**: embed `-c 2048` vs. the 32768
premise in C1's own derivation comment (disclosed inline at the point it
matters, doesn't move the computed byte value either way — no false
"logged to NEW_ISSUES" claim was made, unlike the two prior u31-style
rejections in this project's history); pre-existing thermal-before-
headroom docstring numbering mismatch (unchanged by this diff); missing
PROJECT_LOG.md round entry for this diff (expected — project-architect
updates tracking docs after code-review approval, per this project's
documented pipeline).

**Lesson for future reviews of this module**: whenever a new admission
check starts counting `SLOT_STATUS_RESIDENT` slots (not just PENDING)
against anything, the crash-recovery path (not the graceful
unload()-then-reload path) is the one to trace end-to-end — graceful
paths in this codebase are consistently written correctly (unload()
always releases), but nothing in `core/loader_v2.py`/`core/planner_loader.py`
currently attaches a real PID to a slot at `reserve_slot()` time, so
PID-based reaping is silently a no-op for the two models that actually
go through `reserve_slot()` (primary, planner) — this was harmless
before any RESIDENT-inclusive check existed, and stops being harmless
the moment one does.
