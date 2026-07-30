---
name: round14-new7-scoping
description: NEW-7 (recursive planner synthesizing whole functions with old_str="") desk-scoped Round 14 — reproduction task designed, not yet run; two key structural findings
metadata:
  type: project
---

Round 14 (2026-07-30) was a desk scoping pass only for `NEW_ISSUES.md`
[NEW-7] — no live session was run, no code changed. Full writeup appended
directly to NEW-7's entry in `NEW_ISSUES.md` (search "Round 14"). Key
points worth remembering without re-reading the whole appendix:

1. **`CODEY_RECURSIVE` env var is a clean existing knob** to force plain
   vs. recursive path (`1`=on, `0`=off, unset=on-for-local-backend) —
   `core/recursive.py:111-118`. No code change needed to isolate the two
   paths across two sessions.
2. **The draft-phase system prompt is identical** between plain and
   recursive paths (`core/agent.py:1402`, built once before the step
   loop) — if the `old_str: ""` bug originates in the draft call itself,
   it should NOT be recursion-specific and should reproduce on the plain
   path too. Recursion's only structural difference is the critique+
   refine loop that runs after the draft.
3. **The critique phase structurally cannot catch this bug class** — its
   system prompt (`prompts/layered_prompt.py:352-382`) deliberately drops
   file/repo context, so the critique model has no ground truth to check
   whether `old_str` actually matches real file content. This is a
   candidate explanation for why recursion's quality gate ("Accepted —
   quality 8/10") didn't self-correct the problem — but doesn't explain
   why the draft was wrong in the first place.
4. **`main.py:396-406` `/clear`** resets conversation history/context
   without reloading the model — use it between same-session test draws
   for consistency checks, matching CLAUDE.md rule 2's batching guidance.
5. Designed reproduction task: 2 sessions (`CODEY_RECURSIVE` unset vs
   `=0`) x 4 prompts each (repeat-for-consistency + 2 different edit
   styles/targets: docstring, error-handling, rename) = 8 draws, capturing
   verbatim tool calls + `git diff` after each turn. Full prompt text and
   exact commands are in the `NEW_ISSUES.md` appendix, not duplicated
   here — reread it there before handing off, since it may drift.

**Why:** NEW-7 was the last remaining item with clear scope from the
original Round 7 punch list, but was explicitly deferred every round
since because it needed multiple live reproductions, not just a fix
attempt. This round's job was purely to make the next live-verification
round's job mechanical (exact prompts, exact toggle, exact things to
capture) rather than open-ended.

**How to apply:** the next round should be a live-verifier (or
implementer, if reproduction and fix get combined later) actually running
the 2-session plan above under RAM discipline (single model load per
session, sequential not concurrent, per [[project_new14_swap_pressure_finding]]
— use the lightest `python3 main.py --no-resume` harness, no daemon
needed). Do not skip straight to a fix — the point of NEW-7's history is
that the fix's actual scope (prompting tweak vs. structural
`recursive_infer()` change vs. base-model limitation) is still unknown
until this reproduction runs.
