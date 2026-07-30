---
name: project-phase3-closed
description: Phase 3 (unified entry points) fully closed 2026-07-30; NEW-22 only partially resolved despite gui/start.sh deletion
metadata:
  type: project
---

Phase 3 ("Unified entry points + retire old fragmented ones") is marked
COMPLETE in PROJECT_PLAN.md as of docs commit `0c6c7d7` (code commit
`63ab3df`, 2026-07-30). Three decisions from Ish closed it out:
`gui/start.sh` and `ccos_main.py` deleted outright; `main.py` documented
as-is as the advanced/direct-invocation interface, no code change.
`core/kernel.py` confirmed to never have existed in this repo (v4 was
never part of Codey-OS's lineage).

**Why this matters for future rounds:** NEW-22 was only **resolved in
part**. Deleting `gui/start.sh` closed the checklist item (it retired
`gui/start.sh` as user-facing surface) and fixed `README.md`'s
misdescription, but the underlying duplication NEW-22 was really about —
`codey-start` and `codeyOS` each independently reimplementing the same
GUI-launch/PID-file/trap-kill logic — was untouched by that commit and
remains open, unscoped, in `NEW_ISSUES.md`. Don't assume "the checklist
item is checked" means "the finding is fully resolved" — check the NEW_
ISSUES.md entry's own status line, not just the PROJECT_PLAN checkbox.

**How to apply:** if a future round touches `codey-start` or `codeyOS`'s
GUI-launch logic, check NEW-22's residual-duplication note first. Also
carried forward, non-blocking: Sub-step A's `sleep 0.5` orphan-pgrep race
fix (never live-tested), `docs/architecture.md`'s missing CCOS-layer
content, `docs/commands.md`'s incompleteness, NEW-24 (stale codey3/codeyd3
naming in the spec doc, Suspected), NEW-25 (codeyOS --daemon `\$@`
quoting bug forwarding a literal string instead of real args, Confirmed,
needs code-reviewer approval per project rule 4 since it's
process-lifecycle-adjacent).

See [feedback_verification_wording_precision] for the general discipline
this closeout followed (distinguishing "checklist item done" from
"underlying finding fully resolved").
