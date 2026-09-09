---
name: new435-slots-is-processing-fix-approved
description: NEW-435 _fetch_slots_prompt_tokens() is_processing gating fix — approved, with a downstream-consumer check pattern worth reusing
metadata:
  type: project
---

`core/resource_gate.py::_fetch_slots_prompt_tokens()` fix (2026-09-09):
llama.cpp's real `/slots` `n_prompt_tokens` is NOT cleared when a slot goes
idle — server-context.cpp's `to_json()` sets it from `task ? task : task_prev`,
so an idle slot keeps reporting its last-served request's token count
indefinitely. Fix now only counts a slot when `is_processing is True`
(identity check against real bool, not truthy check), and fails closed
(counts + warns) when `is_processing` is missing/non-bool. Verified against
`~/llama.cpp/tools/server/server-context.cpp` line 632-640: `is_processing`
is unconditionally emitted on every slot in every `to_json()` call — not
conditional on `ptask`, unlike `n_prompt_tokens` which is. APPROVED.

**Why this review needed a second pass:** the advisor caught that my first
pass verified the fail-closed branch and the fix's internal logic but never
traced what the *caller* (`reserve_context_budget()`) does with the changed
return contract. This function's docstring changed from "never returns 0 for
a non-empty pool" to "0 is now the normal case" — a classic place for a
downstream `if not slots_tokens:` falsy-check to silently break (0 and None
becoming indistinguishable, turning a genuinely-idle pool into a refused
admission). Had to grep `slots_tokens` through the whole caller and confirm
every check downstream (`if slots_tokens is None:`, all `ContextBudgetDecision`
construction sites) uses `is None`, not truthiness. It did — real bug pattern,
false alarm this time, but worth checking every time a function's "0 vs None
vs missing" contract changes: **grep every use site of the return value, not
just the function itself.**

**Also worth reusing:** verifying an "X is confirmed against upstream source
Y" claim in a docstring by actually reading upstream source Y (not trusting
the docstring's citation) caught nothing wrong here, but is cheap and is
exactly CLAUDE.md rule 12's "read the artifact, not family resemblance" in
practice — this project has category-error precedent (Qwen3.5-4B) for
skipping this. `~/llama.cpp` is checked out locally as a working directory
for this kind of check.

**Minor, non-blocking finding:** `tests/test_new430_431_context_lease.py`'s
pre-existing `test_fetch_slots_prompt_tokens_fails_once_then_succeeds_on_retry`
uses payload `[{"n_prompt_tokens": 4321}]` with no `is_processing` key. Post
NEW-435-fix, this now passes through the schema-drift fail-closed branch
(counts anyway + warns) rather than the normal-processing branch it was
originally written to exercise — it still asserts the same value (4321) so
it stays green, but it's silently testing a different code path than its
name/intent describes, and emits a warning on every run. Should add
`"is_processing": True` to that payload. Flagged, not blocking.

See also [[resource_gate_new430_431_context_lease_fix_approved]] (referenced
in MEMORY.md index but the file wasn't present under that exact name at time
of this review — check index line for the actual filename).
