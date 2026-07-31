---
name: project-new30-workspace-boundary-correction
description: both live passes in the 7B coder system-prompt round (2026-07-31) were invalidated because scratch test files sat outside core/filesystem.py's workspace-access boundary; NEW-60 opened, NEW-30/NEW-56/NEW-49/NEW-57 corrected
metadata:
  type: project
---

Two live-verifier passes tested `NEW-30`'s `prompts/system_prompt.py`
fix (still uncommitted, code-reviewer approved) using hand-crafted
scratch test files placed under `/data/data/com.termux/files/usr/tmp/
claude-10247/.../scratchpad/...`. A third session discovered
`core/filesystem.py:79-127`'s `_validate_path()` restricts all
`read_file`/`write_file`/`patch_file` calls to `WORKSPACE_ROOT`/
`CODE_DIR` (both `/data/data/com.termux/files/home/Codey-OS` on this
device) — entirely outside the `/usr/tmp` scratch tree used in both
passes. Every `read_file` in both passes therefore returned `[ERROR]
Access denied`, not real content; everything measured downstream (wrong
paths, dropped content, blocked shell, premature "Done.") was the
model's post-denial recovery behavior, not a measurement of `NEW-30`/
`NEW-56`'s actual target questions.

**Corrected status:** `NEW-30` — genuinely untested this session (one
bounded surviving signal: correct turn-1 `read_file` targeting before
denial, in 2 of 3 first-pass case-1 trials). `NEW-56` — downgraded;
behavior real, cause reattributed to the new `NEW-60`, not confirmed as
a normal-conditions `patch_file`-avoidance bug. `NEW-55` (the unguarded
`input()`/`EOFError` crash) — kept Confirmed, unaffected, provenance
note only. `NEW-49` — unchanged, still Suspected. `NEW-57` — unchanged,
held-pending condition restated as fully open again. New finding
`NEW-60` (Confirmed) — a denied `read_file` sends the 7B agent into an
unbounded, unrecoverable failure spiral; this is the actual mechanism
that produced both contaminated passes, and it's real and
production-reachable independent of `NEW-30`/`NEW-56`.

**Why:** rule 6 (correct the record when a re-investigation shows an
earlier finding was overclaimed) plus a live-verifier catching its own
prior sessions' contamination.

**How to apply — the durable lesson:** before trusting any live pass's
result, verify the test fixture's file paths actually resolve inside
`WORKSPACE_ROOT` (or `CODE_DIR` with self-mod enabled) — check with
`Filesystem()._validate_path()` or an equivalent direct call, not by
assumption. A denied read looks exactly like a model behavior failure
(wrong paths, dropped content, give-up responses) unless you check the
access boundary first. Any future live-pass driver for this kind of
test should assert the initial `read_file` actually succeeded (no
`[ERROR]` prefix) before treating the rest of the trial as valid data —
see `WORK_QUEUE.md`'s "7B coder system-prompt round" entry for the
concrete next-pass recommendation (scratch files in a gitignored
in-repo subdirectory, plus this precondition check).
