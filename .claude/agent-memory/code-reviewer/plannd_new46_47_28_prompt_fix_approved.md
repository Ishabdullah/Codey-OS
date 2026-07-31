---
name: plannd-new46-47-28-prompt-fix-approved
description: core/plannd.py PLANNER_PROMPT rewrite (NEW-46/47) + filter_tool_steps edit-regex fix (NEW-28) — approved; surfaced a new daemon.py step-1-enrichment risk
metadata:
  type: project
---

Reviewed 2026-07-31: prompt-engineer's PLANNER_PROMPT rewrite (adds CREATE vs
EDIT precedence section, gates Run/Verify behind explicit user request,
allows 1-step plans) + implementer's one-line `edit` addition to
`_TOOL_VERBS` regex in `filter_tool_steps()`. Both verified directly
(module import, live regex/function calls, `tests/` gives literal
`266 passed`, full repo `334 passed`) and approved.

**New finding surfaced during review, not yet fixed**: `core/daemon.py`
lines ~156-203 unconditionally enriches *step 1 of any ≥2-step plan* with
"Write the COMPLETE file with ALL features described above. Do not skip
any requirement." — hardcoded Create semantics regardless of whether step
1 actually says `Edit`. Before this prompt fix, genuine multi-step
`Edit + Verify`/`Edit + Run` plans were rare (NEW-46/47 caused the model
to fabricate unrelated plans or add spurious steps instead). This prompt
fix makes real Edit-first multi-step plans common — which means this
daemon.py code now gets exercised in a case where it force-feeds
Create/full-rewrite instructions onto an Edit step. Single-step Edit-only
plans are safe (they hit the `len(steps) > 1` False branch and skip this
code entirely); the risk is specifically 2+-step plans starting with Edit.

**Why**: this is the same data-loss shape NEW-46 targeted (full-file
overwrite instructions reaching an Edit task) but via the daemon
consumer rather than model hallucination — worth tracking as its own
NEW_ISSUES.md entry (Suspected, code-read not live-tested) rather than
assuming the prompt fix alone closes the risk class.

**How to apply**: if `core/daemon.py`'s plan-enrichment block (search
"Write the COMPLETE file") is touched in a future round, check it
branches on the step's own verb (Create vs Edit) rather than assuming
position 0 == Create. Don't approve a fix to that block without a live
test that an Edit-first ≥2-step plan doesn't get overwrite-style
enrichment.
