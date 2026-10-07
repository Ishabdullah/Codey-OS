---
name: wp1_3_round2_merge_on_device_fix_approved
description: WP1.3 round 2 — the merge_on_device=True early-return audit gap from round 1 (NEW-811-class, 3rd site) fixed and verified — APPROVED
metadata:
  type: project
---

Follow-up to [[wp1_3_model_registry_lora_gate_changes_requested]]. The one
blocking gap from round 1 — `core/lora_import.py`'s `merge_on_device=True`
branch, `if not success: return results` after `merge_lora_with_llama_cpp()`
fails, with zero `record_adoption_attempt()` call and zero test coverage —
was fixed exactly as it should be: the `record_adoption_attempt(...,
adopted=False, ...)` call added immediately before that `return`, inside
the `if not success:` block, mutually exclusive with the success path's own
(separate) `record_adoption_attempt(..., adopted=swap_success, ...)` call
further down. No double-call, nothing fired on the success path.

New test `test_merge_on_device_failure_is_recorded` is the first in the
file to exercise `merge_on_device=True` at all: monkeypatches
`merge_lora_with_llama_cpp` to fail AND monkeypatches
`swap_to_finetuned_model` to raise if reached — proving the merge-failure
path stops before any swap. Asserts exactly one registry row,
`adopted=False`, `gate_promote=1`, `operator_override=False`.

Verified: 29/29 tests pass (up from 28 — exactly the one new test, no
regressions), real `~/.codeyOS/state.db` has no `model_adoptions` table
before or after (queried directly both times).

Lesson confirmed again: for this `import_lora_adapter()`-shaped function
(gate → validate → backup → [merge|expect-gguf] → swap, each stage with
its own early return), a correctness check for "is the audit call in the
right place" reduces to: is it inside the same `if <failure>:` block as
the `return`, not after it (which would be unreachable) — and does the
success path's own call sit in a mutually-exclusive branch. Fast,
mechanical check once you know the pattern.

The two Warning-level items from round 1 (`prune_adoptions()` /
`get_latest_adopted()` having zero production callers, and the
hardcoded 100-row window) were not touched by this diff and remain open
— should still get a NEW-### entry before this registry is wired into
an automated promotion path, per the round-1 memory.
