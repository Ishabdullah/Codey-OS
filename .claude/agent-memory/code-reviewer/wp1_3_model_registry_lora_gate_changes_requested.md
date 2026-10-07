---
name: wp1_3_model_registry_lora_gate_changes_requested
description: WP1.3 model_registry.py + lora_import.py gate/registry/rollback round — CHANGES REQUESTED, third NEW-811-class gap found in merge_on_device branch
metadata:
  type: project
---

WP1.3 (CODEY_OS_MASTER_BLUEPRINT.md §21, CLAUDE.md rule 1's 4th element):
`core/model_registry.py` (new) + `import_lora_adapter()` gate consultation +
`rollback_adoption()`. The operator-override design (Ish caught the first
draft fabricating `gate_promote=1` for `--lora-force-adopt`) was fixed
correctly in the version reviewed: `gate_decision` is never rewritten,
`operator_override` is a fully independent stored column, all 6 (not 7)
`record_adoption_attempt()` call sites forward it. Verified live: 28/28
tests pass, real `~/.codeyOS/state.db` has no `model_adoptions` table
before or after the run (test isolation fixture confirmed sound).

**Real bug found (blocks commit):** the task description said NEW-811
fixed "two early-return audit-completeness" gaps (validate_lora_adapter
failure, no-GGUF-found). Reading the whole function end-to-end (not just
the diff hunks) found a **third, unfixed site of the identical bug
class**: `core/lora_import.py`'s `merge_on_device=True` branch, the
`if not success: results["error"] = msg; return results` right after
`merge_lora_with_llama_cpp()` (~line 717-719, pre-existing line, NOT
touched by this diff). Gate passed, validate passed, backup created —
real work happened — but a failed on-device merge returns with zero
registry row, same audit gap NEW-811 just closed two lines away. Also:
this whole branch is untested — the new test file only exercises
`merge_on_device=False` (pre-merged GGUF path); the `if not success:`
branch and the swap-success path within `merge_on_device=True` have zero
test coverage.

Lesson for next time: when a diff claims "the two early-return gaps were
fixed," don't just check those two — read the whole function for every
`return` and diff each one against the fix pattern. The merge_on_device
branch is easy to skip because it's gated behind a flag the tests never
exercise, and the diff's own hunks don't show it changing, which makes it
look reviewed when it wasn't touched.

Also flagged (Warning, not blocking): `prune_adoptions()` and
`get_latest_adopted()` have zero production callers anywhere in the repo
(grepped) — the registry table will grow unbounded in practice since
nothing calls prune, and get_latest_adopted's hardcoded `.get_model_adoptions(100)`
window would silently lose a live row that's 100+ rows old once something
eventually does call it. Not a regression (dead code path, module's own
docstring admits WP1.3 has no production caller yet), but should get a
NEW-### entry per rule 8 so it's not forgotten before this registry is
ever wired into an automated promotion path.

See also [[new754_760_llama_server_load_mode_migration_approved]] for the
"read full --help dump not grep" lesson — same shape here: read the full
function body, not the diff hunks, to find all exit points.
