# WP2.1 G15z closure progress — 2026-10-25

Status: IN PROGRESS, not a closure statement. Starting HEAD `7fe60cc` is pushed, with the 99-path S0-S2 commit `84c7bfd` recorded. Historical handoff/takeover reports remain evidence for their dates. Existing `.claude/` changes and the untracked original handoff are preserved.

## Decisions approved by Ish

Ish answered “go with what you recommend for all the questions i approve”, then explicitly “yes take all the recommended actions for the questions you asked”. The approved recommendations are:

- Enable optional standard-library readline at interactive REPL entry, with no persistent history handling, key rebinding or new signal handler; keep unattended/one-shot behavior.
- Make dashboard activation load only `thermal_monitor`, rather than every plugin.
- Retain the canonical `private_agent` and `aigentik` CCOS adapter definitions, explicitly disabled until repaired. No live PID cleanup or real integration launch is authorized by this change.
- D-6: keep plugin manifests HIGH. D-7: keep `ccos/core` and `restoricon_core/authority*.py` HIGH. D-8: confirm remaining HIGH ratings for G15b-07, G15b-31 and G15b-35; G15b-37 was already confirmed.
- Z-1: after full classification, make coverage checks blocking by default; require strict zero-UNKNOWN at closure; keep business-boundary rows subject to coverage.
- Apply the specific `CLAUDE.md` correction acknowledging WP0.5 landed, preserving the NEW-761 guard and Ish-attended benchmark requirements. This specific file edit was explicitly authorized.

These answers do not sign an unseen final residual list or definition of done. Final residual/DoD sign-off, live-check scheduling or explicit deferrals, group-14 evidence tiers and the next package remain pending.

## Current execution

- Prefreeze micro-slice A: optional readline helper at actual REPL entry plus regression tests; code complete and independent reviewer APPROVED. Implementer 16 focused +34 existing tests passed; reviewer independently 50 passed and confirmed actual readline-enabled PTY Ctrl-C and stale-typeahead controls. This is disposable PTY evidence, not Ish's attended Termux terminal.
- Authorized `CLAUDE.md` correction is applied and independently reviewed. Coordinator trajectory guard run: `19 passed in 0.97s`.
- Micro-slice B: thermal-only dashboard activation is code complete + independent reviewer APPROVED; 7 dashboard tests and 2 existing TUI idle/SIGTERM tests passed in both implementation and independent review. Successful activation is cached; failed activation retries without loading unrelated plugins.
- Micro-slice C: strict manifest `enabled` policy and retained disabled adapters are code complete + independently reviewer APPROVED. Implementer focused run: 343 passed in 6.07s. Independent broad run: 342 passed /1 known NEW-1090 timing-sensitive failure; that test passed its isolated rerun. Additional independent controls verified observed-disable/re-enable ownership and direct execution refusal. Existing live/in-flight owner identity is preserved, with no automatic stop or PID cleanup; new work is refused and explicit unload/restart remains the cleanup path. Ordinary deliberate False discovery is visible metadata, not an attempted-action audit; malformed declarations and explicit load/start/dispatch/execute refusals are audited.
- All three prefreeze source slices are reviewed. The fresh bounded recursive tests/ run completed with 9,294 passed /10 recorded baseline failures /2 skipped /19 subtests passed across 32 chunks; all 14 reviewed source/test/manifest hashes remain unchanged. Guarded CCOS completed (details below); final documentation review is APPROVED for the exact 21-path commit. Source is NOT yet committed/frozen; no final classification or final replay claim.

## Diagnostic census before freeze

Command: `python3 -I tools/wp21_census.py --repo . --rev HEAD --source head --register docs/wp21_census/dispositions.tsv --check --seed --out /data/data/com.termux/files/usr/tmp/wp21_closure_next/census_pre_freeze`

At `7fe60cc`, exit 1; register unchanged. Literal coverage summary:

```json
{"failures": 38, "register_entries": 1337, "scan_rows": 1467, "unknown_rows": 1433, "warnings": 0}
```

Row classes: UNKNOWN 1,433; NO_DISPOSITION 28; READ_NOEFFECT 5; GATED 1. This is a diagnostic on the committed starting code, not the pending prefreeze slices, and not evidence that unknown rows are safe. Final counts must be regenerated after freeze.

## Replay preparation and evidence

Scratch root: `/data/data/com.termux/files/usr/tmp/wp21_closure_next/`. `ARCHITECT.md`, `IMPLEMENT_A.md`, `REVIEW_A.md`, `trajectory_guard.log`, `decisions.json` and `census_pre_freeze/` retain scope and literal evidence. `PRE_FLIGHT.md` is a completed static recorder audit, with no harness/canary execution. It locates historical runtime scripts and supplies per-unit repair and harmless-canary plans. The classification ownership skeleton assigns 1,467 keys across 179 files with classification fields deliberately blank until freeze. No retained hunter script is executed before recorder coverage and a discriminating canary are approved. Some historical harnesses lack complete recorders, import before patching or deliberately restore real primitives; replay must adapt those outside the repository and refresh the final committed snapshot.

Remaining sequence: guarded CCOS and documentation checks; commit/freeze; regenerate census; classify all C1-C7 rows; independent review; replay affected probes and PTY checks; strict/coverage gate; final residual/DoD review; closure documentation and Ish sign-off. Real token/tunnel, real bench/model cycle, real escrow DR key and attended-terminal checks stay Ish-only. Disabled adapters are unavailable integrations, not live-verified integrations.

Replay bootstrap checkpoint: independent reviewer approved only its harmless bootstrap selftests (5 scenarios, 102 symbols patched, 85 fabricated primitive calls refused/recorded, marker absent). No product/historical replay is authorized by that result. A V-A adapter is in preparation outside the repository; per-unit adapter review, refreshed frozen snapshot and canary controls are still required.

## Final candidate recursive regression evidence

Command driver: `/data/data/com.termux/files/usr/tmp/wp21_closure_next/final_tests/run.sh`; recursive file inventory, literal logs and failure details are retained beside it. Disposable HOME/state/audit/DB; proxies removed; no model run. All 32 chunks completed. The 10 failed node IDs match the takeover baseline: four planner/coder context tests, the canonical daemon shutdown-budget trace, three NEW-84 model-path tests, the rollback-preserves-finetune test, and orphaned-thread task telemetry. This is not an all-green suite. The 14 reviewed source/test/manifest hashes matched their pre-run values afterward.

```text
chunk 1 rc=1 :: 4 failed, 138 passed in 9.38s
chunk 2 rc=0 :: 32 passed in 20.95s
chunk 3 rc=0 :: 15 passed in 86.01s (0:01:26)
chunk 4 rc=0 :: 201 passed, 4 warnings in 122.43s (0:02:02)
chunk 5 rc=0 :: 333 passed in 89.11s (0:01:29)
chunk 6 rc=1 :: 1 failed, 225 passed in 24.80s
chunk 7 rc=0 :: 469 passed in 26.98s
chunk 8 rc=0 :: 534 passed in 57.54s
chunk 9 rc=0 :: 85 passed in 135.21s (0:02:15)
chunk 10 rc=0 :: 38 passed in 29.48s
chunk 11 rc=0 :: 98 passed in 115.48s (0:01:55)
chunk 12 rc=0 :: 331 passed in 239.00s (0:03:59)
chunk 13 rc=0 :: 158 passed in 5.58s
chunk 14 rc=0 :: 9 passed in 91.16s (0:01:31)
chunk 15 rc=0 :: 187 passed in 42.69s
chunk 16 rc=0 :: 138 passed in 7.33s
chunk 17 rc=1 :: 4 failed, 56 passed, 1 skipped in 4.31s
chunk 18 rc=0 :: 369 passed in 13.85s
chunk 19 rc=0 :: 331 passed in 14.11s
chunk 20 rc=0 :: 484 passed in 38.10s
chunk 21 rc=0 :: 342 passed in 110.94s (0:01:50)
chunk 22 rc=0 :: 111 passed in 16.51s
chunk 23 rc=0 :: 193 passed in 30.43s
chunk 24 rc=0 :: 147 passed in 12.23s
chunk 25 rc=0 :: 217 passed in 22.55s
chunk 26 rc=0 :: 219 passed in 45.70s
chunk 27 rc=0 :: 204 passed in 36.63s
chunk 28 rc=0 :: 256 passed in 16.54s
chunk 29 rc=0 :: 264 passed in 151.23s (0:02:31)
chunk 30 rc=0 :: 2155 passed in 48.33s
chunk 31 rc=1 :: 1 failed, 627 passed, 19 subtests passed in 23.97s
chunk 32 rc=0 :: 328 passed, 1 skipped, 1 warning in 77.43s (0:01:17)
DONE
```

Current-scope Ruff remains non-green: 190 diagnostics across 12 Python files; those existing HEAD files have 179 baseline diagnostics. Counts are scope-specific, not comparable to the previous tranche's 344. No broad style cleanup was included. Mypy is unavailable (NEW-984).

## Guarded CCOS regression

An independently approved bootstrap/controller created an exact-owned disposable source snapshot and HOME outside system TMP, overlaid only the 21 candidate paths, and checked the 14 source hashes. All state, configuration, audit, DB, Git configuration and temporary paths were disposable; proxies were absent. Narrow tripwires prohibited canonical private_agent/aigentik process/HTTP attempts while allowing owned fixture children. No canonical integration or attended-live claim.

```text
python3 -m pytest -q -p no:cacheprovider -p wp21_closure_ccos_guard ccos/tests ccos/plugins/coding/agent/test.py
FAILED ccos/tests/test_multi_domain.py::test_orchestrator_multi_domain_deliberation_and_execution
FAILED ccos/tests/test_process_supervisor_ownership.py::test_real_immediate_exit_is_observed_without_leaking_child
2 failed, 183 passed, 1 warning in 30.51s
pytest_exit 1 guard_refusals 0
```

The multi-domain failure remains NEW-805: `No loaded plugin implements 'crm.get_customer'`. The immediate-exit failure is the known NEW-1090 timing-sensitive case; the same guarded snapshot/environment isolated control passed:

```text
python3 -m pytest -q -p no:cacheprovider -p wp21_closure_ccos_guard ccos/tests/test_process_supervisor_ownership.py::test_real_immediate_exit_is_observed_without_leaking_child
1 passed in 0.52s
exit 0; guard_refusals 0
```

No exclusions/deselections. The updated plugin-manager discovery test now passes with 19 definitions, two intentionally disabled and 17 enabled; canonical service attempts were zero. Raw run is not all green. `ccos_regression.log`, `ccos_immediate_exit_control.log`, `ccos_command.json`, `ccos_exit.json`, `ccos_guard.jsonl`, `REVIEW_CCOS_GUARD.md` and the exact snapshot root are retained under scratch. Fixture-only evidence does not verify unavailable external integrations. Full recursive and guarded CCOS checks are complete for this candidate; commit/freeze and remaining closure stages are still pending.
