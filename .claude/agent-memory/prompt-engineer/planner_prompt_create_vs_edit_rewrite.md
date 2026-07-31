---
name: planner-prompt-create-vs-edit-rewrite
description: NEW-46/47/28-driven rewrite of core/plannd.py PLANNER_PROMPT (Create-vs-Edit lexical gate, Run/Verify gate) — what changed, why, and what's still open
metadata:
  type: project
---

2026-07-31 round: `core/plannd.py`'s `PLANNER_PROMPT` rewritten to fix two
live-confirmed 1.5B planner (port 8081) failure modes found by live-verifier
(`NEW_ISSUES.md` NEW-46, NEW-47), plus reduce exposure to a separate code bug
(NEW-28).

**NEW-46 (3-vs-3 discriminating test, most severe):** natural-phrasing
edit-only requests ("Fix the off-by-one error in the loop in
`core/legacy_calc.py`") caused the model to fabricate an unrelated
Create→Edit→Run→Verify plan with step content copied **verbatim** from
`PLANNER_PROMPT`'s own few-shot examples (fibonacci/docstring/tally.json
text that never appeared in the user's message). Identical task phrased as
the literal "Edit `<file>`: `<change>`" template worked correctly 3/3. Root
cause: the model pattern-matches the template surface form, not the
underlying task category — an existing natural-phrasing edit example
(`core/voice.py` docstring) was already present pre-rewrite and did NOT
generalize, so **adding another edit-only few-shot example was ruled out as
the fix** (advisor caught this — that lever was already pulled).

**Fix applied:** a new "CRITICAL RULE: CREATE vs EDIT — CHECK THIS FIRST"
section, placed *before* the FILENAMES section, using the same structural
pattern that's empirically confirmed working for filename fidelity
(ALL-CAPS divider, imperative bullets, explicit VIOLATIONS gallery) — not
another example, a **lexical trigger-word list**: fix, bug, error,
off-by-one, wrong, broken, change, modify, update, correct, debug, refactor,
rename, replace → forces Edit, forbids Create. Also added an explicit rule
that step content must come only from the user's own words, never from the
prompt's own examples, and a VIOLATIONS entry using the literal observed
failure as the wrong example.

**NEW-47 (n=1, Rule 8 already existed but wasn't followed):** model appended
an unrequested `Run:` step for "create a file, then ask claude to review
it." Fix: converted Rule 8 and the Run/Verify rules from abstract ("never
invent capabilities") to a concrete **gate** — Run only if user said
run/execute/test, Verify only if user said check/verify/confirm, otherwise
plan ends after the last Create/Edit step. Added the real observed
transcript as a VIOLATIONS example.

**NEW-28 (code bug, NOT fixed by this prompt rewrite — explicitly flagged
as needing a companion code change):** `filter_tool_steps()`'s `_TOOL_VERBS`
regex (`core/plannd.py` ~line 130-134) has no `edit` alternative. Traced
mechanism: for a `[Create, Edit, Run]` plan, the Run step survives via both
`_TOOL_VERBS` and the separate `Run:` regex, making `len(kept) > 1` true, so
the `steps[:2]` fallback (which would otherwise rescue the dropped Edit step)
never fires — meaning the *more complete* the plan, the more likely the Edit
step silently vanishes. The Run/Verify gate added for NEW-47 narrows
exposure only in the specific case where killing an unrequested trailing Run
step drops a `[Create, Edit]` plan to `len(kept)==1`, letting the fallback
rescue Edit by accident — it does NOT fix `[Create, Edit, Edit]` or any plan
still containing a legitimate Run step after Edit. **Recommend as a separate
implementer task: add `edit` to `_TOOL_VERBS` in `core/plannd.py`.** Do not
report NEW-28 as closed by this rewrite.

**Also removed:** the duplicated fibonacci Create+Run demonstration (there
were two near-identical copies — a "CORRECT PATTERN" block and a separate
"EXAMPLE" block) and the `core/voice.py` docstring example (identified by
NEW-46 as a leak source), replaced with the `core/legacy_calc.py` edit-only
example. This paid for most of the new section's length; net prompt grew
~24% (4962 -> 6157 chars) rather than compounding on top of the original.

**Verified (no model load, per task constraint):** `python3 -c "from
core.plannd import PLANNER_PROMPT; print(len(PLANNER_PROMPT))"` — import
succeeds, renders correctly, confirmed no other file references
`PLANNER_PROMPT` by substring (grepped repo-wide) so no test/other module
depends on exact old wording. `orchestrator.py`'s separate `PLAN_PROMPT`
(NEW-29) was explicitly NOT touched — out of scope per task, flagged as a
standing recommendation to unify or document the divergence, not acted on.

**Still open:** live-verifier re-test needed against the real 1.5B model
(port 8081) re-running the exact NEW-46 discriminating prompt pair (natural
vs. templated "off-by-one" phrasing) and the NEW-47 prompt ("create a file,
then ask claude to review it"), plus the NEW-28 `[Create, Edit, Run]` repro
prompt to confirm the Edit step still drops without the code fix (expected —
this documents that the code fix is still required, not a regression). See
[[patch-file-old-str-grounding-fix]] for this project's general pattern of
code-complete vs. live-verified prompt fixes.

---

**2026-07-31 round 2 — live-verifier caught a real regression from round 1's
rewrite, fixed same day:** controlled A/B (identical prompt, only
`PLANNER_PROMPT` text differed, pre-fix text pulled read-only via `git show
HEAD:core/plannd.py`) showed round 1's opening line change ("as few as the
request actually needs") plus the new Run/Verify gates caused **repeated-Run
under-generation**: "run it three times" produced only 1 `Run:` step in 4/4
trials (pre-fix: 3/3 correct). Root cause per advisor: a global minimization
directive in the prompt's first sentence beats a buried Rule 5 exception on a
1.5B model, and there was no explicit counting/arithmetic mapping (word →
number of steps) comparable to this project's existing word→tool table
pattern.

**Fix applied (additive, did not touch Rules 3/4/8's "never add on your own"
gates — confirmed by advisor not to weaken NEW-47's fix):**
- Reworded opening line from "as few as needed" to "include every action the
  user asked for — no more, no fewer" + an explicit repeat-count clause.
- Rule 3 (Run) gained a literal counting rule: "twice" → 2 Run steps, "three
  times" → 3 Run steps, attached specifically to run/execute/test — plus an
  explicit anti-trigger clause distinguishing a repeat count from a number
  describing an expected Verify *outcome* (e.g. "wrote 3 rows to out.csv" is
  NOT 3 Run steps).
- Rule 5 reordered to lead with the repetition exception instead of the
  "no repeats" default.
- Added an under-generation VIOLATION/✓ pair in the CREATE-vs-EDIT block
  (mirrors the existing over-generation NEW-47 example) and gave the NEW-47
  violation its own ✓ counterpart (previously only had a ✗).
- Added a new worked example (`ping_check.py`, "run it twice") teaching the
  counting rule end-to-end.
- Fixed Rule 9 (peer-CLI delegation) to explicitly forbid dropping trailing
  clauses like "for bugs" — flagged (not separately verified for provenance)
  as dropped in 6/7 trials.

**Important process lesson — advisor caught two rounds of prompt-contamination
in its own suggestions, both fixed before handoff:** (1) advisor's first
suggested worked example used the *exact* filename/domain/count
(`dice_roller.py`, "run it three times") as the live-verifier's actual test
prompt — would have let the model copy the example instead of generalizing
the rule, making a future pass uninterpretable. Changed to a bland
`ping_check.py`/"twice" example with a different count. (2) advisor's second
suggested anti-trigger example ("verify it printed exactly 10 lines") was
near-verbatim the wording of the must-not-regress `counter.py` test case and
stated its correct answer outright — same failure one level down. Changed to
a bland `report.py`/"3 rows to out.csv" example. **General lesson for future
prompt-engineer rounds: when a live-verifier report includes the literal
test-prompt wording, any new example added in response must deliberately use
different filenames/domains/counts than that wording, or the next
verification round measures memorization, not generalization — check this
explicitly, don't assume the advisor's own suggested wording is safe by
default.**

**NEW-47 status: not claimed fixed.** The observed 3/7 vs 4/7 divergence
across back-to-back identical calls at temp=0.2 is sampling noise — n=7
cannot distinguish a 43% from a 25% true rate. Added a stronger ✓/✗ pair for
the exact failure pattern (Create + peer-CLI-delegation, no Run/Verify
requested); this may reduce the rate but cannot be verified as having done so
without another live-verifier pass, and if it stays nonzero afterward that is
likely a small-model non-determinism floor, not a wording problem still worth
chasing. A real fix, if wanted, is filter-side (post-hoc detection of
unrequested Run steps in `filter_tool_steps`) — out of scope for prompt
edits, flagged for project-architect to log per CLAUDE.md rule 8.

**NEW-28 support reasoned from text only (no live test performed this
round):** Rule 2 (Edit) untouched; Rule 5's reordering only affects repeated
*identical* actions, so it does not affect a `[Create, Edit, Run]` plan; the
new opening line argues for emitting the Edit step (not against). Still
needs live-verifier confirmation, not claimed as verified.

---

**2026-07-31 round 3 — single-step peer-CLI trailing-clause drop (4/4 live),
diagnosed and fixed differently than the obvious lever:** live-verifier found
Rule 9 (copy peer-CLI instructions verbatim, added round 2) works when the
delegation is step 2+ of a multi-step plan but fails deterministically when
it's the ONLY step in the plan — "Ask claude to review report_gen.py for
bugs" as a standalone request drops "for bugs" every time, even though the
exact correct string is already present verbatim inside Rule 9's own ✓
example. Advisor flagged that "add another example with the right string" is
the same already-ruled-out lever from NEW-46 (model had the literal right
answer in-context and still failed) — so the fix could not be another
example alone.

**Root cause identified by advisor, not by re-reading Rule 9 harder:**
STEP TEMPLATES (the always-read structural block used for filename fidelity)
lists Create / Edit / Run / Run pytest / Verify but has **no peer-CLI
delegation entry**. When delegation is step 2+, step 1 already matched a
template and the model is in copy-mode; when delegation is the *only* step,
there's no template to shape it, so the model normalizes/shortens it. This
mirrors why the FILENAMES fix worked in round 1 — a structural rule in the
always-read block beats another example, because the model consults the
template block when deciding step *shape*, not when it's already copying
content.

**Fix applied (targeted, 3 pieces):**
1. Added a peer-CLI line to STEP TEMPLATES: `Ask <cli> to <the user's
   instruction copied word-for-word, including every trailing clause>` with
   an explicit note that this template applies even as the ONLY step.
2. Made Rule 9 position-explicit: added a sentence that the rule applies
   identically whether delegation is step 1 of a one-step plan or step 2+ of
   a longer plan.
3. Added one new worked example — a genuine one-step numbered delegation
   plan (`legacy_calc.py`'s single-step Edit example existed but was Edit,
   not delegation — no single-step delegation precedent existed before this).
   Deliberately used a different surface shape than the live-test prompt
   (`"Ask gemini to summarize sync_utils.py and list its public functions"`
   vs. the test's `"review X for bugs"`) per this project's own
   anti-contamination lesson from round 2 — a `review X for Y` shape would
   have let a future pass measure surface-pattern matching instead of
   generalization. **Flag to live-verifier: also test a fresh single-step
   delegation prompt with an unseen filename/clause, since the original
   failing prompt is character-identical to a string already inside
   PLANNER_PROMPT (a future pass on that exact string would be
   uninterpretable, though the current failure result is still valid — it
   failed despite having the answer in-context, which is more diagnostic,
   not less).**

**Opportunistic Create-side fix (lower priority per task, done since it cost
no separate scope):** advisor identified the Fibonacci Create-side
copying wasn't the example being copied wholesale — it was the STEP
TEMPLATES line itself mandating `accepts <input>` unconditionally
(`Create <file>: accepts <input>, <feature1>, ...`), so the model was
*following the template*, not leaking the example. Fixed by making the
template's inputs conditional (`<only the features/inputs/outputs the user
actually named — never add a feature, parameter, or format the user did not
mention>`) and removed the fibonacci example's own fabricated `accepts n` /
`python fibonacci.py 20` argument (the example itself modeled the bug — the
user's message never mentioned a parameter or a CLI arg). This is the higher-
yield half of that finding per advisor; no restructuring of the example
beyond removing the fabricated parts.

**Not touched this round:** NEW-28 (`_TOOL_VERBS` missing `edit` — still a
code-side fix, not a prompt fix), Rules 1-8, the tally.json/ping_check
examples (already confirmed working, per task's do-not-regress list).
