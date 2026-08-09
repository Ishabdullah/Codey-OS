---
name: resource-gate-test-arch-override-approved
description: core/resource_gate.py test-only CODEY_TEST_PRIMARY_ARCH/CODEY_TEST_PLANNER_ARCH model-arch override (for live-testing the gate stack with substitute Qwen3-4B/Qwen2.5-0.5B models) — APPROVED
metadata:
  type: project
---

## Outcome

Purely-additive diff to `core/resource_gate.py`/`tests/test_resource_gate.py`
adding two lazily-read env vars that let `_resolve_model_arch()` substitute
`QWEN3_4B_ARCH`/`QWEN25_0_5B_PLANNER_ARCH` for the production 7B/1.5B arch
constants, so Ish can live-test the whole 7.4 gate/loader/daemon/CLI stack
(already 5x approved) with RAM-safe smaller models. **Approved.**

## What was verified directly (not trusted from the report)

- Arithmetic: `28*4*128=14336` (7B) vs `36*8*128=36864` (Qwen3-4B) →
  2.57x, matches the claimed ~2.6x. `estimate_kv_cache_bytes()`'s real
  formula (`n_layers*2*n_kv_heads*head_dim*n_ctx*bytes_per_elem`) matches
  the new tests' own `expected` computation.
- Precedence order (`spec.arch` > env override > `KNOWN_MODEL_ARCHS`) is
  correct by reading `_resolve_model_arch()` directly — `git diff` confirms
  `KNOWN_MODEL_ARCHS`'s own dict literal has zero changes (only additions
  after it).
- **Per-role registry structurally enforced**: `_TEST_ARCH_REGISTRY_BY_ROLE`
  is `Dict[role, Dict[key, ModelArch]]`, and `_resolve_test_arch_override()`
  looks up `role_registry = _TEST_ARCH_REGISTRY_BY_ROLE.get(model_id, {})`
  before the key lookup — a planner-scoped key literally isn't a member of
  the primary role's sub-dict, so cross-role substitution raises `KeyError`
  → `ValueError`, not silent wrong-arch selection. Confirmed via a real test
  (`test_test_arch_override_cross_role_value_rejected`) rather than just
  reading the code.
- **Exception propagation through a flock-holding caller**: `can_admit()`
  calls `estimate_model_load_cost()` (which raises) at line 607, *outside*
  any try/except in `can_admit()` — propagates cleanly. `reserve_slot()`
  calls `can_admit()` *inside* `with _LockedState(...)`; `_LockedState.__exit__`
  only writes state `if exc_type is None`, always unlocks in a `finally`,
  and `return False` (no swallow) — verified by reading `__exit__` directly,
  this is the same lock-cleanup contract sub-task 1's round-2 fix
  established. Confirmed with a real test that reserve_slot() with a bad
  override leaves `list_slots() == []` and a *second* call against the same
  `state_dir` succeeds (proves the flock wasn't left held).
- Unset-env-vars-means-byte-for-byte-unchanged claim: real test
  (`test_test_arch_override_unset_matches_current_default_behavior`) pins
  both `is` identity against `QWEN25_7B_ARCH`/`QWEN25_1_5B_ARCH` and that
  `KNOWN_MODEL_ARCHS`'s dict entries are untouched.
- `NEW-94` (test misnamed `..._resolved_by_path`, actually resolves by
  `model_id`) re-confirmed accurately characterized in `NEW_ISSUES.md`
  (correctly logged, not silently fixed, per CLAUDE.md rule 8) and genuinely
  untouched — the pre-existing test itself has zero diff, new tests were
  only appended after it.
- Full suite: 493 passed, 1 skipped (same known-skip pattern as prior
  rounds), real pytest output captured. `tests/test_resource_gate.py` alone:
  62 passed.

## Pattern worth remembering for this module

When a new failure-injection path (here: a bad env var, raising
`ValueError`) is added to a function that a flock-holding caller invokes
*inside* its critical section (`reserve_slot()` calling `can_admit()` inside
`with _LockedState(...)`), always check `__exit__`'s exception-handling
contract explicitly — don't assume "context managers clean up on exception"
generically. Here it was already correct (established in
[[resource_gate_subtask1_reserved_bytes_toctou_rejected]]'s round 2 fix),
but this is exactly the kind of change that could silently reintroduce a
held-lock bug if `__exit__`'s `if exc_type is None` guard or its `finally`
unlock were ever touched.

## Status

Code-complete + unit-verified with real pytest output. Still needs
live-verifier for the actual on-device substitute-model load test (this
diff only adds the override mechanism; the live model-swap session itself
is the next step, not part of this review).
