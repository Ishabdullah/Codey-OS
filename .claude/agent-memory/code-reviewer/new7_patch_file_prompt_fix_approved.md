---
name: new7-patch-file-prompt-fix-approved
description: NEW-7 patch_file old_str grounding prompt fix in system_prompt.py/critique_prompts.py — approved, live-verifier still required
metadata:
  type: project
---

Reviewed the uncommitted NEW-7 fix (prompts/system_prompt.py new "PATCH_FILE —
old_str MUST BE REAL FILE CONTENT" section + critique_prompts.py CRITIQUE_CODE
item 8). All static/mechanical checks passed:

- Escaping: `_SYSTEM_PROMPT_BODY` is a non-raw triple-quoted string; the new
  JSON examples use `\\n`/`\\"` (double backslash) in source, which Python
  collapses to single-backslash `\n`/`\"` at import time — verified via
  `repr(get_system_prompt())` that the rendered prompt text shown to the model
  contains literal backslash-n (not a real newline), i.e. valid-looking JSON
  escapes survive to runtime. This is the exact bug class to check any time a
  prompt string embeds JSON examples inside a Python triple-quoted string —
  single-backslash source would silently produce broken JSON in the actual
  prompt.
- `def shutdown():` in main.py confirmed unique (`grep -c` = 1) even after
  same-session edits to main.py (NEW-10 SIGTERM handler) — worked example
  claim held up.
- tools/patch_tools.py lines 21-22 do reject empty/non-str old_str with an
  error before any write — prompt's behavioral claim to the model is accurate.
- No conflict with same-session Track 1 prompt-audit changes (Edit synonym
  mapping, plain-text-only critique instructions) — both still present,
  untouched.
- New ✗/✓ WRONG/CORRECT worked-example style matches the file's pre-existing
  convention (lines 39-130) — not a new pattern being introduced.
- Full suite: `pytest tests/ -q` → 266 passed (implementer had only run a
  narrower `-k` filter reporting 11 passed — always re-run the full suite,
  narrower filters can hide unrelated regressions).

Key takeaway for future prompt-text reviews: this class of change (prompt
wording only, no process/kill logic) is correctly out of scope for CLAUDE.md
rule 4, but it is NOT fully verifiable by static review + unit tests — the
real effect is on 7B model behavior, so a live-verifier re-run of the
original repro scenario is still required before the issue can be marked
done, even after code-reviewer approval.
