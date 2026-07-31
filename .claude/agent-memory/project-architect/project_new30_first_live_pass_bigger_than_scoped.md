---
name: project-new30-first-live-pass-bigger-than-scoped
description: NEW-30's first live pass (2026-07-31) found patch_file never fires even in the control case — SUPERSEDED, see [[project-new30-workspace-boundary-correction]]: both this pass and a second one were invalidated by scratch files sitting outside the workspace-access boundary
metadata:
  type: project
---

**SUPERSEDED 2026-07-31 — see [[project-new30-workspace-boundary-correction]].**
The trial outcomes described below were a denied-`read_file` recovery
spiral (`core/filesystem.py`'s `_validate_path()` rejected the scratch
test files, which lived outside `WORKSPACE_ROOT`), not a measurement of
`NEW-30`'s actual read-then-edit behavior. Keeping this file for
history/trial-count reference only — do not cite its conclusions as
current.

The 7B coder system-prompt round's first live pass (7B-only, port 8080,
one load/unload cycle) tested `NEW-30` (contradiction between
`system_prompt.py`'s "Done." instruction and its "emit patch on next turn"
instruction after an Edit-step `read_file`). The predicted symptom did
NOT reproduce, but `patch_file` was ALSO never called in any of 5
completed trials — including a control case with no read-then-edit
ambiguity at all. This means the bug is likely not (only) prompt wording.
[Now known to be invalidated — see the correction above.]

**Why (unconfirmed hypothesis, not established fact):** the
live-verifier suspects `run_agent`'s recursive critique/refine layer
(`core/recursive.py`) may be converting or discarding a correct draft
`patch_file` proposal on this call path, or that `layered_prompt.py`'s
priority-based layer eviction may be dropping the identity layer
carrying the NEW-30 fix from the composed prompt entirely. Neither
mechanism has been confirmed — that's exactly what the desk
investigation is for. (Note: `_execute_task` does pass `no_plan=True`;
that flag alone doesn't establish whether critique/refine runs on this
path — don't assume it does or doesn't without checking `run_agent`'s
own logic.)

**How to apply:** the `system_prompt.py` 6-site fix (code-reviewer
approved, commit held back) should NOT be committed or treated as
resolving NEW-30 until a desk-only investigation (no model load)
confirms which of these two mechanisms (or neither) is the real cause.
New Confirmed findings from the same pass: `NEW-55` (unguarded `input()`
crash at `core/agent.py:1676`, no `EOFError` handling, real daemon-path
crash risk) and `NEW-56` (7B `write_file` to wrong/fabricated paths on
Edit steps, one trial with real content loss). See `NEW_ISSUES.md`'s
corrected `NEW-30` entry and `WORK_QUEUE.md`'s "7B coder system-prompt
round" item for full detail.
