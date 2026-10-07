---
name: wp0_5_trajectory_eval_leak_approved_teacher_traces_gap
description: WP0.5 NEW-761 eval-leak fix (verified_training_episodes/verified_eval_episodes split) — APPROVED; found adjacent out-of-scope teacher_traces channel with no tag column at all
metadata:
  type: project
---

Reviewed 2026-10-07: `core/trajectory.py`'s `verified_episodes()` (old, no
tag filter, fed both fine-tune export and eval inspection off one function)
split into `verified_training_episodes()` (`tag IS NULL OR tag NOT LIKE
'bench:%'`) and `verified_eval_episodes()` (the complement). `finetune_prep.py`
switched to the training accessor. Verified by hand: the two predicates are
exact, non-overlapping complements for every tag value including `NULL` and
the literal string `"bench:"` (SQLite `LIKE`'s `%` matches zero-or-more, so
`"bench:"` itself matches `'bench:%'` and correctly routes to eval, not
training). `EVAL_TAG_PREFIX = "bench:"` is a module-level constant
interpolated via f-string into two hardcoded call sites only — not
attacker-controlled, and contains no LIKE metacharacters (`%`/`_`) or quotes,
so the injection/widening risk advisor asked about doesn't apply today (would
need noting if `EVAL_TAG_PREFIX` is ever edited to contain `_`). Grepped
`FROM episodes` repo-wide (`command grep`, not the broken Termux `grep`
alias — see [[new422_423_finetune_import_and_scan_fallback_default_mismatch]])
to confirm no other raw-SQL path reads `episodes.verifier`/`passed` and
bypasses both new accessors — clean. `bench/runner.py`'s
`label_tag(f"bench:{t.id}", ...)` tag format can't break the `LIKE
'bench:%'` match regardless of `t.id` content since `%` is a suffix
wildcard — the pattern match is on the literal prefix, not on what follows.
28/28 tests passed (`tests/test_trajectory.py`,
`tests/test_finetune_phase3.py`, `tests/test_bench_harness.py`), after
clearing stale `bench/tasks/*/hidden/__pycache__` per `NEW-791`'s documented
artifact. `AGI_AUDIT_LOG.md` edit confirmed purely additive (new top entry
only; `git diff` showed zero `-` content lines, only the diff header's `---`).

**Real gap found, logged as follow-up not blocking:** `teacher_traces` table
(`record_teacher_trace`/`verified_teacher_traces`, fed from
`tool_peer_delegate` in `core/agent.py`) has **no `tag` column at all** —
structurally un-taggable, so a peer-delegation call made during a bench run
would be indistinguishable from legitimate training data if anything ever
curated teacher traces into fine-tune export. Checked: `core/finetune_prep.py`
currently has no `teacher`-related code at all (`command grep -n teacher
core/finetune_prep.py` → empty), so this channel is inert today and genuinely
out of WP0.5's literal scope (blueprint §21 WP0.5 names only
`core/trajectory.py:108-114`, `core/finetune_prep.py:127-130`,
`bench/runner.py:32-35` — episodes table only). Confirmed by reading
`CODEY_OS_MASTER_BLUEPRINT.md` lines 2205-2220 directly rather than trusting
the task description's paraphrase or the new `AGI_AUDIT_LOG.md` entry's own
claim about what the acceptance criterion is — both turned out accurate, but
checking the primary source is what the advisor correctly pushed back on
before I'd done it.

**Test-coverage nit (Warning, not blocking):** the new end-to-end test
(`test_finetune_prep_curate_verified_excludes_bench_tagged_episodes`) only
asserts `curate_verified() == []` for a DB containing a single bench-tagged
episode — this alone can't distinguish "the filter worked" from "the call is
broken and always returns nothing" (the `reserve_slot()`-missing-`port=`
shape from `NEW-259`). Mitigated here only by a *separate* file's *existing*
positive test (`tests/test_finetune_phase3.py::
test_curate_verified_uses_only_externally_labeled_passes`) proving
`curate_verified()` does return real rows for ordinary labeled data — but no
single test proves both in one DB (one bench episode + one non-bench episode
in the same `curate_verified()` call, asserting exactly the non-bench one
comes out). Recommend that mixed-episode test as the stronger version of the
blueprint's stated acceptance criterion if this file is touched again.

Verdict: **APPROVED**. Teacher-traces gap and the test-coverage nit do not
block — both out of this work package's literal, blueprint-stated scope —
but must be logged to `NEW_ISSUES.md` per rule 8, not silently dropped.
`NEW_ISSUES.md`/`PROJECT_LOG.md` updates are the coordinator's step 5, not
part of this diff; flagged so the coordinator doesn't skip it. Tree also
carries unrelated modified/untracked files (10 memory files, `MEMORY.md`) —
coordinator must stage the 5 exact WP0.5 paths, never `git add -A`, per
working-tree-bleed precedent ([[working_tree_cross_round_bleed]]).
