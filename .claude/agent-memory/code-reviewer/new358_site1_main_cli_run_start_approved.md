---
name: new358-site1-main-cli-run-start-approved
description: T10 commit 3 / NEW-358 Site 1 — main.py CLI-flag _record_cli_telemetry_run_start() approved; doctor lone-run_start semantics
metadata:
  type: project
---

T10 commit 3 commit A (main.py `_record_cli_telemetry_run_start()` for --init/--tdd/--fix/--import-lora) — APPROVED 2026-09-10.

**Why:** closes NEW-358 Site 1 (CLI flags recorded under generic codey-os.loader emitter).

**How to apply / reusable facts verified:**
- `telemetry/recorders.record_run_start()` order: `_emit()` -> `write_run_provenance()` -> `mark_run_start_recorded()` (unconditional, line ~835, before `schedule_cold_model_digests`). Raise before mark => flag unset => loader `_ensure_run_start_fallback()` claims + emits => at worst ONE duplicate run_start (accepted design; doctor flags `duplicate_run_start_runs` non-fatally per NEW-330).
- `telemetry/cli.py` doctor: `run_ids_with_events` is populated from EVERY record with a run_id INCLUDING the run_start itself (line ~614). So `orphan_runs = run_ids_with_events - run_ids_with_run_start` is empty for a lone run_start => a bare run_start with no amended/run_end is NOT a hard violation. CLI branches that return early after the telemetry call (missing test file, declined overwrite) are fine.
- helper is first statement in each branch, before get_loader()/import. import-lora: 3x load_primary each hit fallback, all no-op after flag set. Verified.
- Tests (8) genuine: ordering via `parent.mock_calls` index comparison with attach_mock; real-store single-emit + claim-semantics tests; negative --finetune asserts `prepare_finetune_data` called_once (non-vacuous).
- Full suite 1592 passed / 1 skipped (241s), matches implementer.

Commit B (docs): OK. v1.json->v2.json edits accurate (Aigentik T10 commit 2 already done a71e4d1). Remaining v1.json: line 729 (JS import example, already flagged by implementer), line 1108 (T0 rollout-plan historical row — genuine history, leave). envelope.py/provenance.py/test_telemetry_schema.py changes are docstring-only, no behavior change.
