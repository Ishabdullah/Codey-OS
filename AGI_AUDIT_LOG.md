# Codey-OS AGI Audit — Work Log

Reverse-chronological. Companion to `AGI_AUDIT_PLAN.md`. Statuses follow CLAUDE.md rule 7: **code-complete** vs **live-verified**.

## 2026-09-30 — Phase 4: code-complete (4.1, 4.3); 4.2 withdrawn (rule 6)

- 4.1: `_fix_memory_hint()` in `core/agent.py`, appended to the generic auto-retry "Error:" message only when `CODEY_USE_FIX_MEMORY=1` (default OFF, fail-open). Enable only after a gate-approved bench A/B. CONCERN: `suggest_fix` can return generic template fixes, not only history-learned ones.
- 4.3: `core/trajectory.py::record_teacher_trace` (table `teacher_traces`, output capped 20000 chars), called from `tool_peer_delegate` (both paths). Flag `CODEY_TRAJECTORY=1`, fail-open, unlabeled until an external verifier passes it (`label_teacher`, `verified_teacher_traces`).
- **4.2 withdrawn (correction of the audit plan, rule 6):** the plan said `rollback_to_backup` "deletes its own backup". Re-read (`core/lora_import.py:451-520`): it restores the backup over the ORIGINAL path (derived from the backup's name) and only then `unlink`s the backup, i.e. it consumes the backup after a successful restore. That is intended behavior, not data loss; a failed copy raises before the unlink. Residual risk: if the reload after restore fails, no backup remains, but the original file is already restored. Not a defect I can justify changing in lifecycle code, so **no change made**.
- Tests: `tests/test_fix_memory_hint.py` (4), two more in `tests/test_trajectory.py`. Full suite 2091 passed, 0 failed.
- Not live-verified; no reviewer subagent available (no approval claimed). Nothing changes runtime behavior while the flags are unset.

## 2026-09-30 — Phase 3 fine-tune tooling: code-complete

- Source checked (rule 12): Unsloth Qwen3.5 fine-tuning guide (unsloth.ai/docs/models/qwen3.5/fine-tune) says 16-bit LoRA on `Qwen/Qwen3.5-4B`, QLoRA 4-bit not recommended, transformers v5 required, ~10GB VRAM. Read via a summarizing fetch, not the raw page.
- 3.1: new `4b` notebook variant (valid multi-cell nbformat 4, every code cell parses, chat-template formatting on real tool-call transcripts, 10% held-out split, bf16/fp16 auto). Legacy 1.5b/7b (Qwen2.5) kept, marked legacy. Fixed a real bug: legacy notebook source lines lacked line endings (whole notebook was one line).
- 3.2: `DatasetCurator.curate_verified()` reads only externally-labeled passing trajectories; `curate_examples(verified_only=True)`; reading never creates the DB.
- 3.3: `--ft-model` choices `4b|7b|1.5b|both`, default `4b`; instructions use `--lora-merge`, no bogus `--model`, and require a gate decision before adopting an adapter.
- Tests: `tests/test_finetune_phase3.py` (7). Full suite 2085 passed, 0 failed.
- UNVERIFIED (needs Ish/Colab): notebook actually runs; LoRA `target_modules` names fit Qwen3.5's hybrid layers; llama.cpp can convert/apply a Qwen3.5 LoRA. Until verified, treat fine-tuning as an experiment, never an adoption path. No data exists yet: enable `CODEY_TRAJECTORY=1`, run the bench, label episodes.

## 2026-09-30 — Phase 2.3/2.4 promotion gate, switch, honest optimizer: code-complete

- `bench/gate.py`: champion/challenger decision (same suite hash, >=30 pairs, McNemar exact p<0.05, bootstrap CI lower bound >0, zero regressions). `no_evaluator()` always refuses. `bench/promote.py` CLI appends every decision to `bench/experiments.jsonl`. Measured A/A false-accept rate over 300 simulated pairs of an identical 70% agent: <=5% asserted (test).
- `ccos/core/self_improve.py`: `CODEY_SELF_IMPROVE=off|shadow|on`, default off. Checked in `CapabilityOptimizer.optimize`, `AutoImprovementLoop.after_task`, `GoalEngine.analyze_and_generate/inject_into_planner`, `SkillRecombiner.analyze_and_generate` (shadow = generate+sandbox-test, no registration).
- 2.4: `compare_and_upgrade` deploys only with an approving `GateDecision` AND mode `on`; fake `+5` removed (new_score = old_score). `optimize()` passes `no_evaluator()` because no capability-level benchmark exists yet, so the optimizer cannot deploy anything today. That is deliberate and honest: activation of capability self-modification is blocked on building evaluators, not on a flag.
- Tests: `test_improvement_loop` updated (no-gate = not improved, no version registered; approved = deployed); `ccos/tests/conftest.py` sets mode `on` for legacy tests (marker `si_default` opts out); new `tests/test_promotion_gate.py` (10) incl. runtime-core-does-not-import-self-improvement. Suites: 1964 + 114 = 2078 passed, 0 failed.
- CONCERN: `ccos/demo_*.py` and script-mode `python ccos/tests/test_x.py` runs now need `CODEY_SELF_IMPROVE=on` to exercise these modules. Not changed; note for Ish.
- Not live-verified; no reviewer subagent available (no approval claimed). Nothing here runs in the live agent path.

## 2026-09-30 — Phase 2.2 trajectory store: code-complete

`core/trajectory.py` (SQLite, `~/.codeyOS/trajectories.db`, override `CODEY_TRAJECTORY_DB`) + wrappers appended at the bottom of `core/agent.py` (`functools.wraps`, default OFF via `CODEY_TRAJECTORY=1`, fail-open, nested run_agent calls = one episode, crashes recorded and re-raised). Labels come only from external verifiers (`label_tag`/`label_episode`); `verified_episodes()` returns only labeled rows. `bench/runner.py` labels episodes via `traj_db`. Full suite: 1954 (tests/) + 114 (ccos/tests) = 2068 passed, 0 failed (was 2052; +16 new).
Limits: rule 4 reviewer not available (no reviewer claim); this touches the live `run_agent` path but is a pass-through with the flag off. Not live-verified on device; args/results truncated but NOT secret-scrubbed (noted in module docstring; do not export the DB off-device unreviewed).

## 2026-09-30 — Phase 2.1 bench harness: code-complete

New `bench/` (not imported by runtime): 8 seed tasks with hidden tests + reference solutions, sha256 `suite.lock`, temp-workspace grader, null/oracle/codey-cli agents, append-only JSONL runner, McNemar-exact + bootstrap-CI compare. `tests/test_bench_harness.py`: 8 passed (null=0/8, oracle=8/8, tamper detection, agent-written test can't shadow hidden test, crash recorded as failure, A/A p=1.0, McNemar values hand-checked). One test expectation of mine was wrong (McNemar(2,9)=0.0654, not <0.05); the code was right, test corrected.
Limits: 8 tasks is too few to detect small gains; real-agent runs need the device (`make_codey_cli_agent`), not yet live-verified; the `main.py` one-shot flags are from reading source, unrun.

## 2026-09-30 — Rule 1 superseded by direct instruction; real tag confirmed

- Ish (in-session, direct): approved building and activating the self-improvement code, overriding the old "permanently gated off" rule with a new rule: build Codey-OS as close to AGI as achievable, goal score 100, in logical order. Recorded in `CLAUDE.md` rule 1 and `CODEY_MASTER_PLAN.md` §2 rule 1 / §6.11 P.1. Activation is conditional on the promotion gate (see plan ground rule 3).
- Ish pushed tag `rollback/2026-09-30-pre-agi-audit-fixes` -> `91ee3c1` to GitHub himself. Rollback is now a real tag plus the branch.
- Build order: 2.1 bench harness -> 2.2 trajectory store -> 2.3/2.4 gate + switch + honest optimizer -> Phase 3 -> Phase 4 -> gated activation -> honest re-score.

## 2026-09-30 — Phase 1 (tests and docs only): code-complete

**Result:** full suite 2043 passed / 9 failed / 70 warnings -> **2052 passed / 0 failed / 0 warnings**. No runtime logic changed.

| Item | Change | Files |
|---|---|---|
| 1.1 | `ccos/tests/conftest.py` hook: returning False now fails; True/None no longer warns. Probe test (removed after) confirmed False fails, True/None pass. The `return True` lines stay because each file's standalone `main()` counts them | `ccos/tests/conftest.py` (new) |
| 1.2 | Hermetic loader/swap tests: placeholder `llama-server` path (`tests/conftest.py`) and sparse ~2.74GB placeholder model file (`tests/test_loader_resource_gate.py`), each used ONLY when the real file is missing, so device behavior is unchanged | `tests/conftest.py`, `tests/test_loader_resource_gate.py` |
| 1.3 | Root cause: `codey` script shebang is `#!/data/data/com.termux/files/usr/bin/bash`, absent off-device, so direct exec fails before the script runs. Test now falls back to system bash when the shebang path is missing (script verified to run correctly under plain bash) | `tests/test_service_manager_config.py` |
| 1.4 | Docstring/text corrections: `error_database.py` ("genuinely smarter" -> write-side only), `agent.py` symbolic pipeline comment/docstring (coder also sees the original request), `lora_import.py` instructions (nonexistent `core/finetune_merge.py`; wrong `--model` flag -> `--lora-model`) | `core/error_database.py`, `core/agent.py`, `core/lora_import.py` |

**Deferred to later phases (found while doing Phase 1):**
- `core/finetune_prep.py::print_instructions` (~line 655) has the same wrong `--model` flag and passes `1.5b`/`7b`. Belongs to Phase 3.3.
- Optimizer test asserting `improved` for a no-op: Phase 2.4 (rule-1 module, needs Ish's explicit confirmation).

**Verification limits (rule 7):** test-verified in a Linux sandbox only; not run on the S24 Ultra. Docstring-only edits compile-checked (`py_compile`) and diff-reviewed. No code-reviewer subagent was available to this session, so no reviewer approval is claimed; Phase 1 touches no process/model-lifecycle logic. New findings: `NEW-729`..`NEW-733` (renumbered at merge time from `NEW-546`..`NEW-550`; see `PROJECT_LOG.md`'s merge entry).

## 2026-09-30 — Setup: audit, rollback point, branch, plan

- Source-level AGI alignment audit completed (score 18/100). Key findings: no capability evaluator; CCOS optimizer's "improvement" is a functional no-op with a fabricated `+5` score; fine-tune data export reads a state key nothing writes (0 examples from 40 realistic logged actions, reproduced); Colab notebook targets Qwen2.5-7B/1.5B while the deployed model is Qwen3.5-4B; 69 CCOS tests end in `return True` (initially misreported as "cannot fail"; corrected below, they do assert); 9 tests fail in a sandbox lacking `llama-server` (8 loader/swap tests, cause `llama-server not found`; 1 in `test_service_manager_config`, cause unknown).
- **Rollback point created:** branch `rollback/2026-09-30-pre-agi-audit-fixes` @ `91ee3c1` (current `main`), pushed to GitHub. Tag push was blocked by the session proxy (HTTP 403), so it is a branch. Local tag of the same name exists only in the session clone, not on GitHub.
- **Work branch:** `codey-os-agi` cut from `main` @ `91ee3c1`. (Requested name "Codey-OS AGI" contains a space, which git does not allow.)
- **Other branches reviewed, left untouched by Ish's decision:**
  - `feat/estimator-phase3-schema` — 3 commits ahead, 0 behind. Rebuilds the production `estimates` table; its own log requires device-side migration verification before merge. Not merged.
  - `feat/termux-api-agent-tools` — 12 commits ahead, 351 behind. Pure additions, but plugin auto-discovery would expose ~60 phone actions (SMS, calls, mic, camera, contacts) to the agent; not reviewed under rule 4. Not merged, not deleted.
- Baseline full test run recorded below once complete.

### Baseline (main @ 91ee3c1, before any change)
`pytest tests ccos/tests` (two backup tests needing `google-cloud-storage` excluded), Linux cloud sandbox with no llama.cpp and no model file: **2043 passed, 9 failed, 70 warnings (336 s)**. The 9: 3 in `test_loader_resource_gate` (model file missing), and `test_lora_import_swap_sync` (1), `test_new84_stale_model_path` (3), `test_new91_new163_rollback_preserves_finetune` (1) (all `llama-server not found`), `test_service_manager_config::test_codey_script_cli_help_and_config` (Termux shebang path absent).

### Correction (rule 6), 2026-09-30
The audit report first said 69 CCOS tests "cannot fail" because they return a bool. Checked directly: the 7 files contain 32-59 `assert` statements each and no `return False`. The `return True` only produces a pytest warning. The claim was overstated and has been withdrawn; the report and plan item 1.1 are corrected. What remains true: `test_improvement_loop.py` asserts that a no-op optimization counts as `improved`.
