---
name: wp1_2_dev_v2_trajectory_full_fidelity_approved
description: WP1.2 manual reconciliation of stranded codey-os-dev-v2 branch (trajectory full-fidelity recording, export_hygiene module, bench/verify.py copytree fix) — APPROVED, one undisclosed gap found
metadata:
  type: project
---

Reviewed 2026-10-07. A real `git merge` of `codey-os-dev-v2` into `main` was
never attempted (too much divergence — blueprint/census didn't exist on
dev-v2); the coordinator instead read dev-v2's diff against its merge-base
and hand-reconciled the equivalent changes onto current `main`. Verdict:
**APPROVED** — code is correct, tests are real and pass, branch deletion is
reasonable — but one undisclosed gap must be logged before/at the ledger
update step.

**What I verified directly (not from the implementer's description):**
- `core/trajectory.py`: WP0.5's `verified_training_episodes()`/`verified_eval_episodes()`
  (eval-leak split, `NEW-761`) and this round's full-fidelity recording
  (`_bounded`/`_budgeted` replacing `_MAX_ARGS=2000`/`_MAX_RESULT=1000`) don't
  collide — confirmed by reading the whole file, not just the diff hunks.
  `ep["chars"]=0` is initialized before any `_budgeted()` call touches it.
  `grep -rn "_MAX_ARGS\|_MAX_RESULT\b"` returns nothing — fully removed.
- `core/finetune_prep.py`: `_write_jsonl`'s atomic temp-file write sets
  `tmp = None` before the `try`, so `NamedTemporaryFile(...)` raising before
  entering the `with` body can't cause an `UnboundLocalError` in the
  `except` cleanup. `export_dataset`'s local `sanitize_examples` import
  matches this file's existing convention (ALL `core.trajectory`-adjacent
  imports in this file are local, not module-level — not a circular-import
  workaround, just house style). `examples` is rebound to the sanitized
  list and used consistently for every downstream `_write_jsonl` call and
  returned count — no caller logs a stale pre-sanitize count (checked both
  call sites: `main.py:2112`, `ccos/plugins/coding/finetune/test.py:99`).
  Neither call site wraps `prepare_finetune_data`/`export_dataset` in a
  bare `except`, so `sanitize_examples`'s "fail closed" claim actually
  holds — an exception there crashes the CLI command rather than silently
  skipping hygiene.
- `core/export_hygiene.py` / `tests/test_export_hygiene.py`: byte-identical
  port confirmed via `diff <(git show codey-os-dev-v2:<path>) <path>`
  (exit 0 both files). Timed 9 adversarial regex constructions (2MB
  payloads, repeated-keyword near-misses) against `yaml_secret_assignment`,
  `quoted_token_assignment`, `mysql_password_flag`, `env_secret_assignment`,
  `quoted_secret_assignment`, `aws_secret_access_key` — all sub-0.25s, no
  catastrophic backtracking. Confirmed `sanitize_examples` never mutates
  its input (deepcopy-compare + `kept is ex` check).
- `bench/verify.py`: `copytree(..., dirs_exist_ok=True, ignore=...)`
  correctly supersedes the old `iterdir()`+`copy2` loop (which couldn't
  have handled a hidden/ subdirectory at all — `copy2` on a dir raises).
- Ran `pytest tests/test_trajectory.py tests/test_finetune_phase3.py
  tests/test_finetune.py tests/test_export_hygiene.py
  tests/test_bench_harness.py tests/test_bench_power_analysis.py -q`
  myself: **177 passed in 53.74s**, verbatim.
- `git diff --stat $(git merge-base main codey-os-dev-v2) codey-os-dev-v2`
  enumerated — every code/test file dev-v2 touched (`bench/verify.py`,
  `core/export_hygiene.py`, `core/finetune_prep.py`, `core/trajectory.py`,
  3 test files) is reconciled onto `main`. The only un-ported files are
  dev-v2's own stale planning docs (`docs/plans/S0.1b_SPEC.md`,
  `CODEY_OS_AGENT_HANDOFF.md`, `STAGE0_EXECUTION_PLAN.md`) and its own
  `NEW_ISSUES.md`/`PROJECT_LOG.md`/`CODEY_MASTER_PLAN.md` edits — all
  superseded by current `main`'s blueprint/ledgers, not lost content:
  reading `S0.1b_SPEC.md` directly shows dev-v2's full planned scope was
  items 1-6b (teacher-trace full fidelity, `curate_teacher`, shared
  `sessions.py` redaction, `CODEY_FULL_TOOL_RESULTS`); only item 3's module
  (export_hygiene) and part of item 6b-adjacent work (episode full fidelity)
  actually landed this round — the rest is explicitly tracked as open
  findings (`NEW-800`, `NEW-801`, `NEW-803`), not silently dropped.
- Renumbering precedent (`NEW-754`..`763` dev-v2 → `NEW-799`..`808` main)
  cross-checked against the cited prior case: `NEW_ISSUES.md:19914` really
  does say `NEW-546`..`551` → `NEW-729`..`734` for the same collision
  reason. Precedent is real, not invented.

**Gap found (not blocking, but must be logged per rule 8 before the ledger
update lands):** `record_teacher_trace()` in `core/trajectory.py` still
calls `_trunc(task, 4000)`/`_trunc(output, 20000)` — teacher traces are
NOT full-fidelity, only `episodes` got that treatment this round (the
module docstring's "episode fields are stored at full fidelity" claim is
scoped correctly and not literally false, but easy to misread as blanket).
Worse: `core/finetune_prep.py::curate_verified`'s new legacy-marker skip
(`field.endswith(LEGACY_TRUNC_MARKER)` ⇒ "pre-full-fidelity data, skip")
is only true for the `episodes` table. If a future `curate_teacher()`
(exactly `NEW-803`'s proposed fix direction) reuses that same skip
convention, every long teacher trace recorded from now on would still hit
`_trunc` and get permanently misclassified as "legacy" — a correctness
trap for not-yet-written code, worth its own line (or an addition to
`NEW-803`) so whoever implements `curate_teacher` doesn't walk into it.
This was confirmed via `tests/test_trajectory.py`'s own strengthened
assertion: `rows[0][3].endswith("...[truncated]")` for a trace recorded
*today*, after this round's "full fidelity" work landed.

See also [[wp0_5_trajectory_eval_leak_approved_teacher_traces_gap]] (the
earlier, related finding that `teacher_traces` has no `tag` column either
— same table, different gap, both still open).
