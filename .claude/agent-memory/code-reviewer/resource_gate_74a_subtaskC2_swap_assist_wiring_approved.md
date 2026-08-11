---
name: resource-gate-74a-subtaskC2-swap-assist-wiring-approved
description: TODO.md 7.4a sub-task C2 (swap-assisted admission wired into can_admit()) — APPROVED first pass, no round 2 needed
metadata:
  type: project
---

C2 (`core/resource_gate.py`/`tests/test_resource_gate.py`, swap-assisted
secondary admission check) passed review on its first round — unusual for
this item (sub-tasks A/B/C1 each needed 2-3 rounds; see
[[resource_gate_74a_subtasksABC1_crash_ghost_slot_rejected]] and its
follow-ups).

**What made it solid:**
- The swap-assist branch lives entirely inside the `if required > headroom:`
  block, which is reached only after `hard_reject` (line ~1503) and
  `budget_ceiling_exceeded` (line ~1519) have already `return`ed — so C1's
  "swap-assist must never override C1's ceiling" invariant is structurally
  enforced by control flow, not just asserted in a docstring. Verified by
  reading the literal line order, not trusting the comment.
- `compute_swap_assisted_headroom_bytes()` uses `meminfo.get("SwapFree", 0)`
  / `.get("SwapTotal", 0)` — fails safe (0 swap headroom, denial preserved)
  on a meminfo dict missing swap keys, rather than raising `KeyError` on the
  gate's own denial path. Worth checking explicitly any time a helper that
  used to be untested-but-harmless (per B's "NOT called by can_admit() yet"
  status) gets wired into a live decision path for the first time.
- `MAX_SWAP_ASSIST_BYTES = 768MiB` cross-checked directly against TODO.md's
  "Ish's decisions"/"Scoping call" block — matches verbatim, including the
  `min(768MiB, 8.4GiB) = 768MiB` NEW-21 fixture derivation. The pinning test
  (`test_compute_swap_assisted_headroom_new21_fixture_pre_registered_case`)
  actually asserts `== 768 * MIB`, not a placeholder.
- Only 2 real callers of `can_admit()` exist in the whole tree —
  `reserve_slot()` (inherits on-by-default swap-assist, correct per Ish's
  decision) and `would_model_fit()` (explicitly passes
  `enable_swap_assist=False`, matching TODO.md's pre-declared routing
  default). Enumerated via `grep -rn "can_admit(" core tools utils ccos
  main.py` — a daemon.py comment mentions `can_admit()` but has no actual
  call. This full-caller-enumeration step is what actually bounds a rule-4
  "changes whether a model process gets spawned" claim; don't stop at
  tracing the two callers you already expect.
- `_resolve_swap_assist_enabled_default()` only accepts `"1"`/`"0"`/unset,
  raises `ValueError` on anything else (deliberately not a bare `!= "0"`
  truthiness check — a typo like `"false"` must fail loudly, not silently
  keep the feature enabled in the wrong direction).
- Two genuinely real, correctly-scoped-out findings were flagged by the
  implementer and independently re-verified before logging as NEW-135/136:
  (1) `compute_swap_assisted_headroom_bytes()` has no `reserved_bytes`-style
  param unlike `compute_headroom_bytes()` — two concurrent swap-assisted
  admissions can each independently claim the same 768MiB against the same
  live SwapFree; (2) `admitted_via_swap` isn't persisted into
  `register_slot()`/`list_slots()`'s schema, so a later reader can't tell
  which resident slots got there via swap.
- 705 passed, 1 skipped, 68 warnings, 130s — matched the implementer's claim
  verbatim on a literal re-run.
- `git diff --cached --stat` confirmed only `core/resource_gate.py` and
  `tests/test_resource_gate.py` touched; the diff's only removed lines are
  docstring/comment updates plus a hardcoded `2.0` → named
  `SLMK_FLOOR_GATE_MULTIPLIER` swap — no functional change to C1's
  already-approved logic.

**Non-blocking notes carried into the write-up:**
- TODO.md/WORK_QUEUE.md/PROJECT_PLAN.md/PROJECT_LOG.md are untouched by
  this diff (rule 9 closeout still owed as a follow-up commit) — this is
  fine because, unlike the stale-status pattern that blocked
  [[resource_gate_phase4_1_subtaskC_dispatch_gate_changes_requested]] and
  [[resource_gate_phase4_1_subtaskD_shutdown_tripwire_changes_requested]],
  no contradictory doc text ships *inside this same diff* — the docs
  simply aren't part of it yet.
- `docs/configuration.md`'s env var table doesn't list the new
  `CODEY_SWAP_ASSIST_ADMISSION` — but it also doesn't list
  `CODEY_N_CTX` (U.31, already approved/shipped) or
  `CODEY_TEST_PRIMARY_ARCH`, so this is a pre-existing gap, not a
  regression unique to C2. Logged as a Suggestion, not a Warning.

Lesson for future rounds on this item (D and E remain): the advisor's
3-check pass here (raw meminfo indexing safety on a newly-wired-in helper;
full caller enumeration, not just the 2 expected call sites; literal read
of the "pre-registered" test cited by a constant's own comment) is a good
template to reapply to D/E without re-deriving it from scratch.
