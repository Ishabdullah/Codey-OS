---
name: new172-dead-code-deletion-task-a-doc-status-gap
description: NEW-172 Task A (delete dead get_plan/classify_tier) — code CHANGES REQUESTED on doc-status grounds only, not code correctness
metadata:
  type: project
---

Reviewed 2026-08-24: deletion of `core/planner_service.py:get_plan()` and
`core/model_tiers.py:classify_tier()` (dead since M1-D collapsed the
planner onto the primary model), plus their test files/classes.

**The deletion itself is clean and fully verified — every implementer
claim independently re-checked, all correct:**
- Re-grepped `get_plan`/`classify_tier`/`planner_service` myself (broader,
  unqualified patterns, not just the implementer's exact qualified names)
  — zero live callers of the deleted functions anywhere outside
  docs/archive and comments/docstrings. Note there are multiple unrelated
  `get_plan()` functions in this codebase (`core/plannd.py`,
  `core/planner.py`, the deleted `core/planner_service.py` one) — grep by
  bare name alone is not enough, had to confirm caller graph per-module.
- `_request_daemon_plan()` (the real live function in the same file)
  untouched; its own test file
  (`tests/test_planner_service_daemon_socket_timeout.py`) passes 3/3.
- `core/model_tiers.py` diffed line-by-line: only `classify_tier()`
  removed, `MODEL_TIERS`/`ModelTierEntry`/`get_tier()`/`tiers_for_role()`
  byte-identical.
- Deleted-test-file boundary exact: 8 tests in the deleted whole file
  (`tests/test_planner_service_classify_tier.py`) + 6 tests in the two
  deleted classes (`TestClassifyTier`, `TestClassifyTierFullChainIntegration`
  in `tests/test_model_tiers.py`) = 14, matching 658 (pre-round baseline,
  reverified myself via `git stash push -u`) - 14 = 644 exactly.
- Docstring corrections (main.py's `_try_daemon_plan()`, planner_service.py
  module docstring) checked against what the surviving code actually does —
  accurate.
- `tests/test_orchestration.py:167`'s stale `classify_tier()` comment
  correctly identified as a comment (not a call) and correctly logged as
  NEW-176 rather than silently fixed or silently left unlogged.
- Test-infra fragility triage confirmed by A/B: `pytest tests/` with
  main.py dirty gave 641 passed/1 skipped/3 failed
  (`tests/test_new19_patch_failed_repeat_escalation.py`, pre-existing,
  traced to `core/agent.py:check_git_and_offer_commit()` + pytest stdin
  capture); `git stash push -- main.py` then re-running gave 644 passed/1
  skipped. Standard move for this project's recurring dirty-main.py test
  coupling — see also `resource_gate_phase5a_subtaskA_cpu_sentinel_...`
  memory for the original discovery of this coupling.
- `ccos/tests/` unaffected: 68 passed.

**BLOCKED — not on the code, on the round's own tracking-doc accuracy
(rule 9), the single most repeated rejection reason in this project's
history (Phase 5a subtask A, Phase 4.1 C/D x2, M1-A, U.31-adjacent — this
is now another occurrence).** Both new `PROJECT_LOG.md` entries added in
this exact diff ("2026-08-24 (latest) — ... reconciled into one
implementer-ready two-task brief" and the "halted" entry beneath it)
explicitly say "**Status: scoping/reconciliation only, no code changed**"
and describe Task A in future tense — "ready to hand to implementer," "no
further scoping needed" — while the code deletion performing Task A is
**already present and complete in this same diff**
(`core/planner_service.py`, `core/model_tiers.py`, `main.py`,
`tests/test_model_tiers.py`, deleted
`tests/test_planner_service_classify_tier.py`). `CODEY_MASTER_PLAN.md`'s
own Appendix A / roadmap-table edits in this diff have the identical
gap — no line anywhere states Task A is code-complete, tested, or
pending code-reviewer sign-off; §4 current-state section wasn't touched
at all. Fix: add a round-closing PROJECT_LOG entry (or amend the
existing one before commit) stating Task A was actually implemented,
with the real test-count arithmetic (658 → 644, 14 deleted), and update
Appendix A to reflect Task A as done rather than "hand to implementer."
Task B remains correctly out of scope and untouched.

**Lesson for future reviews:** an untracked draft memory file
(apparently written by a prior, session-limit-interrupted attempt at
this exact review) was sitting in `.claude/agent-memory/code-reviewer/`
before this review began, containing a pre-written "APPROVED, no
findings" conclusion. Per instructions this was correctly NOT trusted as
evidence — everything was re-verified from scratch — and the
independent re-verification actually surfaced this doc-status gap that
the stale draft had missed entirely. Don't let a memory file (even one
that looks like your own prior work) substitute for redoing the
diff/test verification.
