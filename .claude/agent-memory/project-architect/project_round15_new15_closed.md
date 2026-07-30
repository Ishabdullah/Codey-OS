---
name: project-round15-new15-closed
description: Round 15 (NEW-15) write_file corruption guardrail closed out in docs (commit 7599a65)
metadata:
  type: project
---

Round 15 (NEW-15) is closed out: code complete, code-reviewer approved with
direct live-behavioral verification of the guardrail logic (reviewer wrote
and ran a throwaway script exercising `tool_write_file()` against the real
running code, and explicitly judged an on-device model session unnecessary
for this class of change), full unit test coverage added (4 new tests in
`tests/test_file_tools.py`, full suite 258 passed). Fix commit `7756581`;
docs-closeout commit `7599a65` (PROJECT_LOG.md, PROJECT_PLAN.md,
NEW_ISSUES.md).

**Why:** NEW-15 was the most severe finding from [[project_round14_new7_results]]
(the write_file whole-file-reconstruction escalation after a failed
patch_file call) — this round fixed it narrowly, via a syntax-check
guardrail in `tools/file_tools.py`'s `tool_write_file()` plus reworded
`[PATCH_FAILED]` guidance in `tools/patch_tools.py`.

**How to apply:** NEW-16, NEW-17, NEW-18 (logged in the same Round 14
investigation) remain open and UNSCOPED — do not assume they were touched
by this fix. NEW-7 itself (the underlying planner behavior) also remains
open — Round 14's b3/b4 reproduction draws were never run. If asked to
continue this investigation thread, the next open items are: NEW-7's
remaining draws, or scoping a fix for NEW-16/17/18, or NEW-9 (deprioritized),
or the two NEW-12 deferred items (cross-process port lock, planner
auto-launcher).
