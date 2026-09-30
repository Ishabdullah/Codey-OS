# Codey-OS AGI Audit — Project Plan

**Branch:** `codey-os-agi` (requested name "Codey-OS AGI"; git branch names cannot contain spaces)
**Base:** `main` @ `91ee3c1`
**Rollback point:** branch `rollback/2026-09-30-pre-agi-audit-fixes` @ `91ee3c1` (frozen; do not commit to it).
Restore: `git checkout main && git reset --hard origin/rollback/2026-09-30-pre-agi-audit-fixes`.
A tag push was blocked by the session proxy (HTTP 403); **Ish pushed the real tag himself from Termux on 2026-09-30 (confirmed `[new tag]` on GitHub)**. Command used:
`git tag rollback/2026-09-30-pre-agi-audit-fixes 91ee3c1 && git push origin rollback/2026-09-30-pre-agi-audit-fixes`.
**Source of work:** the 2026-09-30 source-level AGI alignment audit (score 18/100). Findings are cited by section in that report; each item below names its evidence file.
**Companion file:** `AGI_AUDIT_LOG.md` (dated record of every change, test result, and decision).

## Ground rules (from CLAUDE.md, restated for this work)

1. Business safety first. `restoricon_core/`, daemon lifecycle, `core/resource_gate.py` are not modified, except where a phase explicitly says so.
2. Every behavior change is **default off** behind a flag, and new code on live paths **fails open** (an exception in new code never changes agent behavior).
3. **Superseded 2026-09-30 by Ish's direct in-session instruction:** the self-improvement mechanisms (`goal_engine`, `auto_improvement_loop`, `capability_optimizer`, `skill_recombiner`) may be built out and activated, but ONLY behind the promotion gate (frozen bench, champion/challenger, paired stats, evaluator outside agent write scope) and a `CODEY_SELF_IMPROVE` switch that defaults off until the gate exists and passes its A/A test. Recorded as CLAUDE.md rule 1.
4. Anything touching process/model lifecycle (Phase 4 rollback fix) needs the mandatory code-reviewer pass (rule 4) and is **code-complete, not live-verified** until Ish runs it on the device (rule 7). RAM discipline (rule 2): no live model loads from this work.
5. No new dependencies unless added to `install.sh` in the same change (rule 11).
6. New findings outside a task's scope go to `NEW_ISSUES.md` (rule 8), not silently fixed.
7. Full test suite before and after each phase. Any new failure blocks the phase.
8. `feat/estimator-phase3-schema` and `feat/termux-api-agent-tools` are **untouched** by Ish's decision (2026-09-30). This work does not merge or delete them.
9. Nothing merges to `main` without Ish's approval. Work stays on `codey-os-agi`.

## Phases

### Phase 1 — Tests and docs only (no runtime code changes)
| ID | Item | Evidence | Done when |
|---|---|---|---|
| 1.1 | Make CCOS test return values meaningful | 69 `PytestReturnNotNoneWarning`s across 7 files in `ccos/tests/`. **Correction:** these tests DO assert (32-59 each). Deleting the `return True` lines would break each file's standalone runner, so a `ccos/tests/conftest.py` hook is used instead: a returned False now fails. The optimizer-test criterion fix moved to 2.4 (touches a rule-1 module) | Zero warnings; returning False fails (probe-verified) |
| 1.2 | Make the loader/swap tests hermetic | 8 failures with `llama-server not found` in `test_loader_resource_gate`, `test_lora_import_swap_sync`, `test_new84_stale_model_path`, `test_new91_new163_rollback_preserves_finetune` | Pass with no llama.cpp installed; still exercise the same logic |
| 1.3 | Investigate `test_service_manager_config::test_codey_script_cli_help_and_config` | 1 failure, cause unknown | Root cause recorded; fixed if test-only, else logged |
| 1.4 | Correct misleading docs | `error_database.py` docstring ("genuinely smarter"), `symbolic_graph`/`_run_symbolic_pipeline` "sees ONLY the graph", `lora_import.py` reference to non-existent `core/finetune_merge.py`, optimizer docstrings | Docstrings state what the code does |

### Phase 2 — Additive tooling
| ID | Item | Notes |
|---|---|---|
| 2.1 | `bench/` harness: frozen tasks, verifiers, runner, results ledger | New directory. Not imported by runtime. Agent cannot write to it in normal operation |
| 2.2 | Trajectory store | New SQLite table/module; hook in `core/agent.py` guarded by flag `CODEY_TRAJECTORY=1`, default **off**, wrapped in try/except |
| 2.3 | Explicit kill switch for CCOS self-improvement | `CODEY_ALLOW_SELF_IMPROVE` default off, checked inside `AutoImprovementLoop.after_task`, `CapabilityOptimizer.optimize`, goal engine, recombiner entry points. Plus a test asserting no runtime module imports them |
| 2.4 | Stop the optimizer from reporting fake improvements | Remove the `+5` score, mark no-op headers as `improved=False` until a real evaluator exists. Dormant code, no runtime effect |

### Phase 3 — Fine-tune tooling (manual CLI path only)
| ID | Item | Notes |
|---|---|---|
| 3.1 | Retarget notebook generation to the deployed model | Verify Unsloth support for the model before claiming it works |
| 3.2 | Fix the data path | `DatasetCurator` reads the trajectory store, not the nonexistent `episodic_log` key; only verifier-graded outcomes eligible |
| 3.3 | Fix stale instructions and CLI choices | `--ft-model` choices, missing `finetune_merge.py` reference |

### Phase 4 — Behavior changes (default off, measured)
| ID | Item | Notes |
|---|---|---|
| 4.1 | Wire error DB / strategy tracker read-side into the retry path | Flag `CODEY_USE_FIX_MEMORY`, default off. Enabled only after `bench/` shows benefit |
| 4.2 | Fix `rollback_to_backup` deleting its own backup | Lifecycle-tier: reviewer required; not live-verified until Ish runs `LIVE_TEST_QUEUE.md` steps |
| 4.3 | Capture peer-escalation transcripts as teacher traces | Into the trajectory store, flag-gated |

## Out of scope (deliberately not built)
Evolutionary search, neural world model, activating goal engine / skill recombiner, on-device training, more CCOS rule-based "agents", expanding the symbolic graph before an A/B shows benefit.

## Risk register
| Risk | Mitigation |
|---|---|
| Converting return-bool tests exposes real failures in dormant code | Log each in `NEW_ISSUES.md`; fix only if trivial and test-side, otherwise mark expected-failure with reason |
| Hook in `agent.py` slows or breaks the live loop | Flag default off; try/except; benchmark overhead; reviewer pass |
| Merge conflicts with `feat/estimator-phase3-schema` in shared log files | Main record lives in new files; only small appends to shared logs |
| Cannot verify on the phone | Live checks go to Ish via `LIVE_TEST_QUEUE.md`; statuses say "code-complete", never "verified" |
| Bench results not comparable across hardware | Pin GGUF hash, sampler settings, suite version in the ledger |

## Status
| Phase | Status |
|---|---|
| Rollback point + branch | Done 2026-09-30 |
| Plan + log | Done 2026-09-30 |
| Phase 1 | Code-complete 2026-09-30 (test-verified in sandbox; not live-verified on device) |
| Phase 2 | Code-complete 2026-09-30: 2.1 bench, 2.2 trajectory, 2.3 switch+gate, 2.4 honest optimizer (sandbox-verified; bench not yet run with the real model) |
| Phase 3 | Code-complete 2026-09-30 (Colab/llama.cpp steps unverified) |
| Phase 4 | Not started |
