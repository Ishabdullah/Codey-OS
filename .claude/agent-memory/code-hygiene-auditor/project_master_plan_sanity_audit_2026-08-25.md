---
name: project-master-plan-sanity-audit-2026-08-25
description: How the 2026-08-25 CODEY_MASTER_PLAN.md-vs-code sanity audit was done, and what it found (mostly clean, one real discrepancy)
metadata:
  type: project
---

Ran a full read-only audit checking CODEY_MASTER_PLAN.md's claims (§4, §5,
§5.1, §6, Appendix A) against the real state of `core/resource_gate.py`,
`utils/config.py`, `core/loader_v2.py`, `codeydOS`, `install.sh`,
`NEW_ISSUES.md`, `PROJECT_LOG.md`, and a real `pytest` run.

**Method that worked well:** grep for the exact constant/function names
the plan cites (`MAX_CONCURRENT_MODEL_BUDGET_BYTES`, `MAX_SWAP_ASSIST_BYTES`,
`get_planner_n_ctx`, `--jinja`/`--reasoning-format`, port-8081 pkill sites)
directly in the code, then diff the literal value/presence against what
the plan states. Also worth doing: `git show <commit> --stat` +ful commit
message for any round the plan cites, and compare the commit message's own
claims (approval status, test counts) against the plan/PROJECT_LOG's claims
for the same round — this is where the one real finding turned up.

**Result: the plan and code matched almost everywhere.** §5.1's constants
(7.00GiB / 6.50GiB, M1-F) are live in `core/resource_gate.py:1594,1759`,
exactly as documented. `utils/config.py`'s `MODEL_PATH`/`PLANNER_MODEL_PATH`,
`QWEN_MMAP`/`QWEN_MLOCK` rename, `n_ctx=65536`, and `get_planner_n_ctx()`'s
removal all check out. `core/loader_v2.py:_spawn_locked()` has `--jinja`
and `--reasoning-format`. `core/planner_loader.py` is genuinely deleted,
`_evict_planner_and_confirm_free()` genuinely gone, port-8081 pkill sites
genuinely gone (only explanatory comments mention 8081 now). `codeydOS`
still has the open 8080-pattern `pkill` sites the plan says are still
open (`NEW-99`/`NEW-103`). `install.sh` matches the Qwen3.5-4B download
URL and post-install text the plan describes; the one `qwen-2.5-coder-7b`
string left in it is `OPENROUTER_MODEL`'s cloud-fallback default, a
genuinely separate, untouched config axis — not stale slop. Test suite:
`tests/` gave 661 passed/1 skipped and `ccos/tests/` gave 68 passed,
matching the plan's most recently cited figures exactly. The 3-tier
dispatch Task A/B commits (`8fe5d07`/`edc9e36`) match Appendix A's
description of them in full, including the deliberately-fenced-out
NEW-175/NEW-173/NEW-178 follow-ons (no missing "Task C" — it's covered).

**One real, Confirmed finding, verified with the discriminating check
(not just absence-of-review-memo inference):** `git show 2eae89f --
CODEY_MASTER_PLAN.md PROJECT_LOG.md` shows this SAME commit adds the
"not code-reviewer-approved... no code-reviewer subagent was available
in this session" language to both tracked docs, while its own commit
message (same commit) asserts "Code-reviewer independently reproduced
all arithmetic against live /proc/meminfo and reran the full test suite
... before approval." One commit simultaneously denies and asserts
review happened — ruled out the "docs are just stale, review happened
later" alternative reading, since there is no later commit to have done
that review in. Confirmed, not Suspected.

**Second Confirmed finding, same pass:** §8 Q8 ("Thinking-mode policy —
when does the model think?") is written as still-open, listing
`classify_tier()` as an option ("gated on the existing complexity
classifier... currently only logs — 7.3 sub-task C"). But `classify_tier()`
was deleted (`NEW-172` Task A, `8fe5d07`) and the real decision shipped
in Task B (`edc9e36`, confirmed live in `core/orchestrator.py` and
`main.py`): tier = medium (non-thinking) if `score.length > 300` else
hard (thinking). §8 Q1 and Q3 both got struck-through "ANSWERED" treatment
when decided; Q8 never did, despite Appendix A/PROJECT_LOG marking the
7.3 sub-task E work DONE. Cosmetic/process-debt, not safety-relevant —
but exactly the "code shows done, plan lists outstanding" case this
audit was asked to look for.

Both handed to project-architect as findings for `NEW_ISSUES.md`, not
fixed (read-only pass).

See [[feedback_doc_discipline_high_dont_force_findings]] for the general
takeaway from this pass.
