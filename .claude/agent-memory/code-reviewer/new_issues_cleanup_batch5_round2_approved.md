---
name: new_issues_cleanup_batch5_round2_approved
description: Batch 5 (prompt/planner) round 2 — NEW-31 NEED_DOCS regression fixed, APPROVED
metadata:
  type: project
---

Round 2 of [[new_issues_cleanup_batch5_prompt_planner_need_docs_regression]].
Verdict: **APPROVED**.

Round-1's single blocking finding (CRITIQUE_TOOL/CRITIQUE_PLAN silently
dropped the NEED_DOCS targeted-retrieval trigger that CRITIQUE_CODE had,
contradicting the module docstring's "all three templates" claim) is
closed correctly:

- `prompts/critique_prompts.py`: both `CRITIQUE_TOOL` and `CRITIQUE_PLAN`
  now carry a `NEED_DOCS: <topic>` line. Not a lazy copy-paste —
  `CRITIQUE_TOOL`'s line is byte-identical to `CRITIQUE_CODE`'s (fine,
  same phrasing fits), `CRITIQUE_PLAN`'s is reworded to "unsure about any
  API or library **a step relies on**" — reads naturally for plan review
  context.
- `core/recursive.py`'s `extract_doc_needs()` (line 248) is a plain
  `re.findall(r"NEED_DOCS:\s*(.+?)(?:\n|$)", critique, re.IGNORECASE)` —
  template-agnostic, confirmed the new lines will actually fire.
- `task_type=task_type` threading through `recursive_infer()` ->
  `build_recursive_prompt()` -> `_build_critique_prompt()` ->
  `select_critique_prompt()` was unchanged this round (already verified
  round 1); `git diff --stat` on `core/agent.py`, `core/orchestrator.py`,
  `core/plannd.py`, `prompts/layered_prompt.py`, `prompts/system_prompt.py`,
  `utils/config.py` showed **zero new hunks** — only `critique_prompts.py`,
  `recursive.py` (the `task_type=task_type` line + a stale "7B" comment
  fix), and `NEW_ISSUES.md` changed this round. Confirms the coordinator's
  direct fix didn't quietly touch anything outside the flagged gap.
- NEW-31's ledger entry rewritten accurately: states Resolved, describes
  the wiring, and explicitly narrates the round-1-caught regression and
  its fix — not overclaiming, correctly credits the review round.
- Test suite independently re-run (not trusted from the coordinator's
  claim): `1500 passed, 1 skipped in 231.79s` — matches verbatim.

Process note: this is a clean example of a targeted round-2 fix — narrow
diff, only touches what the finding named, doesn't ride other changes in
under the same commit. Good pattern to expect/require on other CR->fix
loops in this project.
