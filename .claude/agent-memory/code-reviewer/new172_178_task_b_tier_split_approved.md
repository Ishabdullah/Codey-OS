---
name: new172-178-task-b-tier-split-approved
description: 7.3 sub-task E Task B (medium/hard planning tier split) — APPROVED; verified score.length>300 boundary is an explicit prior Ish-approved design line, not a silent implementer choice
metadata:
  type: project
---

Reviewed 2026-08-24: Task B threads a `tier`/`enable_thinking` value through
`main.py` -> `core/planner_service.py` -> `core/daemon.py` socket RPC ->
`core/planner_client.py` -> `core/plannd.py`'s HTTP request. Closes
[[new172_dead_code_deletion_task_a_approved]]'s Task A/B split.

**Verified clean, all independently re-checked (not trusted from the
implementer's report):**
- Timeout asymmetry, the single load-bearing invariant here: confirmed by
  reading the actual code (not just comments) that
  `core/planner_service.py:_request_daemon_plan()`'s client-side socket
  timeout is computed from `PLANNER_MAX_TOKENS` unconditionally (tier
  variable never touches that computation), while `core/daemon.py`'s two
  internal `compute_planner_timeout()` call sites (`_handle_command`'s
  `plan_only=True` branch and `_plan_claimed_task`) both correctly key off
  `max_tokens_for_this_request`, which does branch on tier. This is a
  deliberate asymmetry (outer client timeout must survive an old-daemon
  binary that ignores `tier` and always runs hard-tier server-side); both
  directions are asserted by real discriminating tests in
  `tests/test_plannd_tier_split.py`, not just "some timeout was computed."
- `core/planner_client.py:send_plan_request_async()`'s `functools.partial`
  fix: real, confirmed via a fake `get_plan` capturing the actual
  `enable_thinking` kwarg it received (not just "a plan came back").
  `run_in_executor` only forwards positional args, so this was a genuine
  silent-mislabeling trap if left unfixed.
- `core/plannd.py:get_plan()`: `max_tokens` and
  `chat_template_kwargs.enable_thinking` are derived adjacently
  (`max_tokens = PLANNER_MAX_TOKENS_MEDIUM if not enable_thinking else
  PLANNER_MAX_TOKENS`, then `"enable_thinking": enable_thinking` a few
  lines below) — genuinely colocated, can't drift independently. NEW-164's
  truncation-warning message correctly branches on `enable_thinking` for
  distinguishable logs. NEW-168's separate truncation-heuristic bug
  confirmed untouched (fenced to NEW-173).
- `NEW-178` (new finding, `_plan_claimed_task`'s tier param can't carry a
  real value — no tier column in the tasks table) is honestly reported,
  not silently faked. Verified its bounding claim myself: grepped
  `_plan_claimed_task`'s only call site (`core/daemon.py:1264`, from
  `_process_planner_tasks()`), which does call it with no `tier` arg
  (defaults to hard) — matches NEW-178's description exactly. Independently
  re-verified NEW-112's "zero live callers" claim for this whole pull-side
  path too (grepped for the daemon socket `"command"` handler's callers)
  rather than trusting it transitively — holds.
- Full regression, ran myself both ways: `pytest tests/` with `main.py`
  dirty (this task's own diff) → literal `3 failed, 656 passed, 1 skipped`
  (the pre-existing NEW-177 dirty-main.py test-fragility, unrelated
  content). Stashed `main.py` (`git show HEAD:main.py > main.py`, restored
  after) → `659 passed, 1 skipped` exactly matching 644 baseline + 15 new
  tests in `tests/test_plannd_tier_split.py` (counted `^def test_` myself).
  `ccos/tests/`: 68 passed, unchanged.
- Repo-wide `is_complex(` grep: confirmed no positional-second-arg caller
  exists anywhere that could accidentally bind to the new `score=`
  parameter — every call site is single-positional-arg.

**Advisor raised a real concern that resolved clean on inspection — worth
the pattern for future reviews:** `score.length` is `len(message)`,
character count (`core/orchestrator.py:242`), so `tier = "medium" if
score.length > 300 else "hard"` means most real coding prompts (>300
chars, a couple sentences) land in medium/non-thinking — a much bigger
behavioral shift than "additive, backward-compatible" first suggests. This
was NOT a silent implementer choice: `CODEY_MASTER_PLAN.md` Appendix A's
7.3 sub-task E entry (read the FULL entry, not just the first 2 grep
lines — the "Reconciled 2026-08-24 (Ish approved building all three tiers
in one push)" paragraph a few lines below the header) states this exact
boundary, verbatim, as the scoped design signed off by Ish. Lesson: when a
threshold's *consequences* look surprising, check whether the threshold
was independently pre-approved in the plan doc before treating it as the
implementer's judgment call to second-guess — read the cited doc section
in full, not just enough to find the right heading.

**Non-blocking findings, to log/flag but not gate this commit:**
1. No test directly asserts on `main.py`'s own tier-decision line
   (`tier = "medium" if score.length > 300 else "hard"`) — all 15 new
   tests take `tier`/`enable_thinking` as an input, none exercise the
   decision itself. Low risk since it's a one-line, spec-verbatim match;
   worth a follow-up test.
2. The `main.py` "Planning tier: ..." info log fires whenever `no_plan` is
   False, even if the daemon isn't running (`_request_daemon_plan` returns
   `None` at `is_daemon_running()` before any planning happens) — same
   log-noise-on-a-plan-that-never-happens shape the `no_plan` guard was
   written to prevent, just not the exact case that guard covers. Cosmetic.
3. `CODEY_MASTER_PLAN.md` line ~1500 (Phase-summary table row, not
   Appendix A) still describes `classify_tier()`/
   `planner_service.get_plan()` as live-but-unreachable — stale against
   HEAD since Task A deleted that code in `8fe5d07`, independent of this
   diff. Flag for project-architect's doc-closeout pass, not this review's
   concern (tracking-doc updates are project-architect's job per
   CLAUDE.md's workflow section, not code-reviewer's to block on — same
   judgment call validated in [[new172_dead_code_deletion_task_a_approved]]
   territory but distinguishable: there the stale text shipped *inside*
   the diff being reviewed, here it's untouched and outside it).

**Verdict: APPROVED.** Not rule-4 category (additive payload field
threaded through an existing RPC handler, no start/stop/PID/kill/lock
logic touched) — agreed with the task's own classification. Ready to
commit pending live-verifier confirmation per this project's standard
code-complete-vs-live-verified split (rule 7).
