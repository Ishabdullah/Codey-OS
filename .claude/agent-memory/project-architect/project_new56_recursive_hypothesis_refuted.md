---
name: new56-recursive-hypothesis-refuted
description: NEW-30/NEW-56's "recursive critique/refine ate the draft's patch_file" hypothesis was refuted by desk investigation 2026-07-31; true mechanism still unestablished — NOTE, NEW-56 itself was separately downgraded 2026-07-31, see [[project-new30-workspace-boundary-correction]]
metadata:
  type: project
---

**Note added 2026-07-31 (does not change this file's own conclusion):**
this desk investigation's refutation of the recursive-critique
hypothesis still stands unchanged. But the underlying `NEW-56` trials it
was refuting a cause for are now understood, per
[[project-new30-workspace-boundary-correction]], to be a
denied-`read_file` recovery spiral, not genuine patch-vs-write
decisions. This file correctly ruled out one wrong mechanism; it never
established the real one, and neither has anything since.

The anchor hypothesis for `NEW-30`/`NEW-56` (7B coder producing wrong-path
`write_file` instead of `patch_file` on Edit steps) was that
`core/recursive.py`'s critique/refine layer discarded a correct draft
`patch_file` proposal. A 2026-07-31 desk investigation refuted this for
the specific trials observed: `core/agent.py:1489`'s `_use_recursive`
only fires on the agent loop's first turn (`step==1`), but the bad
`write_file` calls happened on turn 5 and turn 2 — both ran plain
`infer()` with full history, not recursion. Separately, `recursive.py`'s
refine phase is unreachable at all unless `classify_breadth_need()`
returns `"deep"` (`max_depth=2`); a normal single-file Edit message
classifies `"standard"` (`max_depth=1`), under which the `cycle >=
max_depth` break fires before refine's code ever runs.

Two real-but-latent bugs were found and logged anyway (`NEW-58` refine
has no `prior_draft` path if ever reached, `NEW-59` critique
double-truncates the draft preview and can split a `patch_file` JSON
mid-string) — worth fixing as hardening, explicitly not claimed to fix
NEW-56. A third candidate (`NEW-57`, a `read_file`/`core.context`
context-surfacing gap) was initially over-framed as a `write_file` vs.
`read_file` asymmetry and had to be downgraded to Suspected after
checking that `core/memory_v2.py`'s store (what `write_file` populates)
and `core.context`'s store (what the layered prompt's "files" block
reads) are actually separate systems — neither branch populates the
layered-prompt context today, so there's no asymmetry to fix by
"mirroring."

**Why:** the advisor caught two things I'd have shipped wrong on first
pass: (1) I verified the citations I was told to verify but not the gate
that decided whether the whole mechanism was even reachable
(`step==1`, `max_depth`) — that check reversed the entire scope; (2) I
rated NEW-57 Confirmed on an "asymmetry" claim without checking both
branches used the same store.

**How to apply:** when scoping a fix against a hypothesis handed down
from another round, check the *reachability gates* (turn counters,
depth caps, feature flags) before checking whether the mechanism's
internals are buggy — a buggy-but-unreachable code path can't explain an
observed symptom. Also: when a "why doesn't X do what Y does" framing
appears, verify X and Y actually write to the same store before rating
it Confirmed; don't assume symmetry from function-name similarity. Next
step (not yet done): attribution logging in `agent.py`/`recursive.py` so
the next live pass can tell which code path produced which tool call —
see `WORK_QUEUE.md`'s "7B coder system-prompt round" entry, sub-task 1.
