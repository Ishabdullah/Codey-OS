---
name: plannd-new46-47-28-iter3-onestep-delegation-approved
description: core/plannd.py PLANNER_PROMPT iteration 3 (one-step peer-CLI delegation truncation + Create-side example fabrication fixes) — approved with a non-blocking contamination warning
metadata:
  type: project
---

Reviewed 2026-07-31, third iteration of the same PLANNER_PROMPT string this
session (see [[plannd_new46_47_28_prompt_fix_approved]] for iter 1). Iter 3
added a STEP TEMPLATES peer-CLI line + Rule 9 update making full-verbatim-copy
explicit for sole-step delegations, a new non-contaminated one-step worked
example (gemini/sync_utils.py), and made the Create STEP TEMPLATE's
`accepts <input>` conditional (only list what the user actually named) while
stripping fabricated `n`/`20` specifics from the fibonacci example. Approved.

**Bug pattern worth remembering: "avoid contaminating the next test" fixes
can be undermined elsewhere in the SAME diff.** The implementer deliberately
built a new, non-contaminated one-step delegation example (different CLI
name/filename/clause) specifically so a future live-verifier pass wouldn't
be testing a string already baked into the prompt as "correct." But the same
diff separately added a NEW Rule 9 violation example reusing the exact
still-failing string ("ask claude to review report_gen.py for bugs"),
presented standalone (no multi-step framing) — structurally identical to the
live-test's actual failing case. This doesn't break the *planned* next test
(which correctly uses the new gemini string) but permanently forecloses ever
cleanly re-testing the *original* failing case, contradicting the stated
design goal in a different section of the same prompt.

**Why this matters**: when reviewing a prompt-string fix that includes an
explicit "we added X so the next test isn't contaminated" claim, don't just
check the one place X was added — grep the whole prompt for every literal
substring of the known-failing case (filename, CLI name, trailing clause).
Multi-iteration prompt files accumulate examples across rounds; a later
round can reintroduce a string a previous round tried to keep clean, in an
unrelated rule/section.

**How to apply**: if PLANNER_PROMPT is touched again, `grep -n` (full path,
not bare `grep` — see [[project_termux_grep_find_alias_broken]]) the whole
string for any literal phrase from a previously-identified live-test failure
before approving, not just the diff hunk claiming to add a fresh example.
