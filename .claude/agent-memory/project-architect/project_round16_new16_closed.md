---
name: project_round16_new16_closed
description: Round 16 (NEW-16) show_patch/show_file_write display-honesty fix closed; NEW-19 opened
metadata:
  type: project
---

Round 16 (NEW-16) is closed as code complete, code-reviewer approved, no
live model session (docs commit `1b16bdf`, fix commit `99d922f`).

**Fix:** `core/agent.py`'s `show_patch()`/`show_file_write()` call sites
now thread `error=is_error(result, name)` through to `core/display.py`,
which renders a red-bordered "PATCH FAILED"/"WRITE FAILED" panel instead
of the previous unconditional success-styled panel. Bundled the
identical bug in both functions rather than splitting into two rounds.
`show_patch()`'s call site also got a narrow inline check for
`tools/patch_tools.py`'s `[PATCH_FAILED]` prefix — deliberately NOT via
widening the shared `is_error()`, since that function by design excludes
`[PATCH_FAILED]` from retry/escalation so the model sees untruncated
file content to reconstruct edits.

**Why no live session:** code-reviewer assessed this class of change
(pure display-layer styling, no process-lifecycle/network/GUI surface)
as fully exhaustible via direct `execute_tool()`-level testing, which it
performed itself (325 passed, 1 pre-existing unrelated failure).

**Spun off [NEW-19] (Suspected, new):** whether `[PATCH_FAILED]`'s
bypass of retry/escalation logic is correct as designed, and whether it
needs its own distinct transcript marker (NEW-2's `[EDIT NOT APPLIED]`
wording is inaccurate for this case — it asserts retries/escalation were
exhausted, which is false for `[PATCH_FAILED]`). Needs its own scoping
pass in NEW-2/NEW-15 territory.

**Why:** keeps the docs (`PROJECT_LOG.md`, `PROJECT_PLAN.md`,
`NEW_ISSUES.md`) accurate about which verification tier this round
actually reached — "code complete, code-reviewer approved," not "live
verified" (CLAUDE.md rule 7).

**How to apply:** Remaining open items after this round: NEW-7
(partially characterized, 2/8 draws outstanding), NEW-9 (deprioritized,
escalated to Ish twice), NEW-17/18 (logged, unscoped), NEW-19 (new),
plus two earlier-deferred NEW-12 items (cross-process port lock,
planner auto-launcher). See [feedback_verification_wording_precision].
