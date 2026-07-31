---
name: round22-new7-scoping
description: NEW-7 Round 22 decided a pre-registered reproducibility re-run before any further prompt iteration; desk-only, no code changed, no live session run
metadata:
  type: project
---

Round 22 (2026-07-31, desk only, no live session, no model load) picked up
`NEW-7` from `WORK_QUEUE.md`. Decision: do a pre-registered, no-code-change
reproducibility re-run (4-bucket failure taxonomy: grounding-failure /
wrong-target / no-`patch_file`-attempt / success; two interleaved fixtures —
`main.py` and a new small few-function file — to separate fixture-complexity
confound from base-model tendency; achievable n~12 licenses a yes/no
reproducibility verdict on `NEW-44`, not a rate estimate) BEFORE writing any
target-function-identification prompt iteration. Full task spec is in
`WORK_QUEUE.md` under the `NEW-7` item, not duplicated here.

**Why:** at n=6, Round 21's 2/6 wrong-function-targeting observation
(`NEW-44`) has a ~6%-71% CI — landing a prompt fix and re-verifying at n=6
again would be unfalsifiable. Advisor's framing: don't collapse "firm up the
signal" and "fix it" into one round; writing the fix first anchors the next
test matrix to the fix's own theory rather than the underlying question.

**How to apply:** when NEW-7 next comes up, check whether the Round 22
live-verifier task (harness pre-registered, code-reviewer-eyed per NEW-45's
double-confirm risk) has actually been run yet before assuming a prompt
iteration is the next step. If it has run, read its result in
`NEW_ISSUES.md`/`PROJECT_LOG.md` first — don't re-derive from this memory,
which is a snapshot of the *decision*, not the outcome. See also
[[project_round21_new7_mixed_result]] if that memory exists, and
[[project_new30_workspace_boundary_correction]] for why fixture-path
validation is a hard pre-run blocker on this project (two prior passes were
invalidated by exactly that mistake).
