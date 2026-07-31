---
name: system_prompt_new30_top_table_gap
description: NEW-30 read-then-patch fix in prompts/system_prompt.py — RESOLVED, all 6 sites now consistent (top table gap closed)
metadata:
  type: project
---

RESOLVED. Follow-up review confirmed prompt-engineer added the missing
read-first caveat to the file's very first WORD->TOOL table (line 33-34):

  "Patch:", "Update", or "Edit" →  Output: <tool>{"name": "patch_file", ...}</tool>
    If you have not read that file yet, your FIRST turn is read_file.

Verified via `git diff -- prompts/system_prompt.py` (still uncommitted,
cumulative with the prior 5-site fix — nothing from that round had landed
yet) and independent grep for both mapping tables ("ABSOLUTE, NO EXCEPTIONS"
at line 29, "no exceptions, no substitutions, no creativity" at line 198) —
confirmed these are the only two WORD->TOOL tables in the file, and both now
carry the same read-first qualifier with consistent wording ("your FIRST
turn is read_file" / "patch_file is your second turn").

All 6 sites (29-38, 138-141, 146-155, 165-167, 197-204, 256-262) verified
internally consistent. Approved as code-complete; still pending
live-verifier's test matrix (7B model behavior can't be confirmed by static
prompt review alone — same caveat as [new7_patch_file_prompt_fix_approved]).

**Lesson reinforced**: the "grep the whole file for duplicate tables, not
just the diff hunk" check from the original finding paid off again here —
confirming there are exactly 2 tables (not assuming) is what let this
close cleanly instead of re-opening a new gap.

See also [plannd_new46_47_28_prompt_fix_approved] and
[plannd_new46_47_28_iter3_onestep_delegation_approved].
