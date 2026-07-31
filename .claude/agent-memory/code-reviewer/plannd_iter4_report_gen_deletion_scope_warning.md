---
name: plannd-iter4-report-gen-deletion-scope-warning
description: plannd.py PLANNER_PROMPT iteration 4 (report_gen.py leak example deletion) — approved end state with Warning, deletion-only claim unverifiable
metadata:
  type: project
---

Fourth uncommitted touch of `PLANNER_PROMPT` in `core/plannd.py` this session
(NEW-46/NEW-47/NEW-28 line). None of the four iterations this session were
committed — `git log --oneline -5 -- core/plannd.py` still points at
`702b0d5` (rename sweep). So `git diff -- core/plannd.py` against HEAD is
**cumulative across all four iterations**, not an isolated view of the
latest edit. Content added in an earlier iteration and deleted in a later
one cancels out and shows as nothing in the diff — its absence is NOT
evidence a deletion never happened, and its presence as `+` is NOT evidence
it's new (see [[plannd_new46_47_28_prompt_fix_approved]] — the `_TOOL_VERBS`
regex `edit` addition showed as `+` in this same diff despite being
iteration-1 content already approved).

**How to apply:** when reviewing a "just this one incremental change since
last approval" claim on a file with no commit between iterations, first
confirm with `git log -- <file>` that a commit boundary actually exists at
the point being claimed. If it doesn't, treat the diff as cumulative and
say so explicitly in the verdict rather than certifying "deletion-only" or
"addition-only" claims you can't actually isolate.

**Content warning (not blocking):** the specific leaking example described
as removed (a create+delegate prompt paired with fabricated
`3. Run: python report_gen.py data.json`) is absent from history/diff,
consistent with clean removal. But a *different* Rule-9 ✗/✓ example at
lines ~120-122 still contains the exact filename and clause from the
live-failing prompt (`ask claude to review report_gen.py for bugs`),
verbatim, in both the wrong and correct lines. If leakage is lexical
(matching example text) rather than semantic, this could still cause
partial reproduction on the exact targeted prompt. Flag this specifically
for live-verifier rather than assuming the deletion fully closes the loop.

Verdict: approved the net end-state diff (coherent, no broken text/rules),
Warning on the remaining report_gen.py string, explicit note that
deletion-only-ness could not be verified from available git history, and
rule-7 reminder that this is code-complete only pending live-verifier.
