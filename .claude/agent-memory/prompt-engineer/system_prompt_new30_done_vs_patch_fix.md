---
name: system-prompt-new30-done-vs-patch-fix
description: NEW-30 fix in prompts/system_prompt.py — resolved "Done."-vs-patch_file conflict on unread-file Edit steps; also confirms NEW-53's real cross-file mechanism
metadata:
  type: project
---

2026-07-31 round: fixed `NEW-30` (corrected framing) in
`prompts/system_prompt.py` — the contradiction was NOT the original
"exactly one tool call" framing (a two-call exception for unread-file Edit
steps already existed incidentally from the `NEW-7` fix, commit `0026565`).
The live contradiction was that the model has **two instructions for what to
do immediately after a successful `read_file` on an unread-file Edit step**:
`:143-146`/`:156` (old line numbers) said "respond with 'Done.', never call
extra tools after success"; `:216-219` said "your ONE call is read_file, emit
the patch on your NEXT turn." Both applied to the same model turn — a small
model could resolve this either way non-deterministically, meaning an Edit
step could silently never get patched while still reporting "Done."

**Fix: made the "Done."/no-extra-tools rule explicitly conditional, at every
site that stated it, using identical wording.** Advisor caught that patching
only one site (the main `AFTER THE TOOL RUNS` block) would leave the bug
"relocated, not resolved" — there were actually **four** independent firing
sites restating some form of "you're done / one call only," and missing any
one of them leaves the small model a path back to the bug:
1. `:143-146` (now with EXCEPTION clause under "Respond with exactly: Done.")
2. `:156` ("Never call extra tools... after a step succeeds" — added UNLESS clause)
3. `:216-219` (the original read-then-patch section — added explicit "you are
   NOT done, do NOT say Done." reinforcement)
4. `:138` (EXECUTION RULES' "every step requires exactly one tool call" —
   advisor caught this on a *second* pass; missed on the first. Qualified as
   "one tool call per turn" + EXCEPTION cross-ref)
5. `:197` (STEP WORD → TOOL table's "Patch/Update/Edit → patch_file ONLY, no
   exceptions" — advisor caught this on a *third* pass, distinct from all the
   above: this table + the "READ THE FIRST WORD" instruction at :26-27 governs
   **turn 1** behavior — a 7B seeing "Edit config.py" could emit `patch_file`
   immediately with an invented `old_str`, bypassing the whole turn-2 fix.
   Concretely relevant because `NEW-7` (turn-1 old_str fabrication) was
   live-tested and came back "mixed effect, stays open" — i.e. turn-1
   patch-without-reading is a known-still-live failure mode, not
   hypothetical. Added a cross-reference: "If you have not read that file
   yet, your FIRST turn is read_file... patch_file is your second turn.")

**Also added:** a negative-case example distinguishing Edit steps (two-turn:
read_file then patch_file, no "Done." in between) from Read:/Review steps
(one-turn: read_file then "Done.", no patch_file) — without this, the model
could over-generalize "read_file succeeded → call patch_file next" to plain
Read steps, which is the over-verification failure mode this prompt already
fights elsewhere. Examples use the file's existing house style (literal
`<tool>{...}</tool>` blocks, `✓`/`✗` markers, `Problem:` labels) — an initial
draft used prose-described turns instead of literal tool-call blocks and
advisor flagged it as inconsistent with every other example gallery in the
file.

**Net size:** `get_system_prompt()` grew from ~12,464 to ~12,872 chars.
`layered_prompt.py`'s draft/refine `identity` layer is priority 0,
`required=True` — never evicted regardless of size — so this doesn't risk
eviction of the identity block itself, though it does mean the `files` layer
(priority 4, evicts first) has less budget headroom, and that layer is
literally the alternative to calling read_file in the unread-file exception.
Not a reason to revert, just a note that further prose growth in this prompt
should be traded off against that budget, per this project's general
small-model-context-budget discipline (see `layered_prompt.py` priority map).

**NEW-53 (append_file/note_forget unreachable) — confirmed the deeper
mechanism, left unfixed as scoped:** grepped `core/plannd.py`'s
`_TOOL_VERBS` regex (`~line 209`) — it has no `append`/`forget`/`save`/
`remember`/`note` alternative. This means even if `system_prompt.py`'s
word→tool mapping gained trigger rows for these two tools, a
planner-emitted step literally starting `"Append ..."` or `"Forget ..."`
would be **silently dropped by `filter_tool_steps()` before ever reaching
the 7B model** (unless it happened to be one of the first two steps, kept
unconditionally as a fallback). So a system_prompt.py-only fix would be dead
text — this is a cross-file gap requiring a `plannd.py` code change, same
class of issue as `NEW-28` (see [[planner-prompt-create-vs-edit-rewrite]]).
Left unfixed per task scope; reported the concrete mechanism instead of just
"gap confirmed."

**Still open:** live-verifier round next (already scoped in `WORK_QUEUE.md`'s
"7B coder system-prompt round") — hand-craft `daemon.py`-style enriched
step strings and call `TaskExecutor()._execute_task()` with only the 7B
loaded, test both the anchor unread-file Edit case and a control case
(file already in context). Also test NEW-49 (Edit-first plan through
daemon's step-0 "write the COMPLETE file" enrichment) in the same load
cycle. Do not mark NEW-30 closed until that pass confirms the fix
empirically — code-complete is not live-verified (project rule 7).

See [[patch-file-old-str-grounding-fix]] for the related NEW-7 turn-1
old_str-fabrication history that motivates why the `:197` cross-reference
matters (that failure mode is documented as still partially live).
