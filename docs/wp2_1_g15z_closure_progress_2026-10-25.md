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

## Committed source freeze and classification checkpoints

The exact 21-path prefreeze tranche was independently APPROVED, committed as `770dc6639e4100ea3215fca07d923769a8290078` (`770dc66`) and pushed. HEAD and origin/main were verified equal afterward. The earlier not-committed/not-frozen statements above describe the precommit checkpoint; production source is now frozen at this revision. No final closure/gate/residual signature is claimed.

A full git-archive snapshot (1,267 regular files) and SHA256 manifest are retained in scratch `frozen_source_770dc66/`, `frozen_source_manifest.json` and `FREEZE.md`. Two independent `--source head --rev HEAD --check --seed` census runs at this revision produced byte-identical scan, shell_scan, manifest_scan, cli_flags and env_names TSVs. Each exited 1 with 1,467 rows, 1,433 UNKNOWN, 28 NO_DISPOSITION and 38 coverage failures (10 stale keys +28 unregistered keys), no warnings. Register remains unchanged pending classification/merge, so reproducibility does not imply coverage success.

Frozen ownership: C1 355 rows, C2 304, C3 159, C4 153, C5 179, C6 181, C7 136 (1,467 total across 179 disjoint files). Ownership manifests preserve exact keys and sorted-key hashes.

- **C3:** author /root, independently APPROVED after review correction of one real package-install row initially mislabeled as a regex false positive. Final 159 exact dispositions: 65 OPERATOR_BOOTSTRAP, 27 OPERATOR_SCRIPT_RUNNABLE, 54 FALSE_POSITIVE, 13 BOOKKEEPING. Reviewer independently audited all 159; independent random sample 40 had 0/40 initial differences. Expanded initial differences and resolved conventions remain recorded. Named F3 execution restrictions and copied/imported F2 ceiling are explicit, with no whole-file safety exemption. Scratch `REVIEW_C3.md` and `classification_units/C3_reviewed_dispositions.tsv`.
- **C7:** author /root/implementer, independently APPROVED under the sampling policy. All 136 exact keys and 31 source hashes match; random 34 plus mandatory cases gave 37 unique required reviews, expanded to 58 individually audited rows. Initial 3/34 differences (8.8235%) were preserved; two semantic interpretations were resolved by the coordinator after source inspection, and one invalid reviewer enum was normalized. Only the 58 individually audited rows carry reviewer signatures; the other 78 retain author-only fields under the unit-level sampled approval. Five UNMEDIATED rows and both helper GATED rows were included in mandatory review. Scratch `REVIEW_C7.md`, `classification_units/C7_REPORT.md` and `C7_reviewed_dispositions.tsv`.

These two approved units cover 295 boundary dispositions; they have not yet been merged into the canonical register. C1 is in progress; C2/C4/C6 are pending; C5 has partial source/caller preparation only. No classification from a mutable worktree is substituted for the frozen inventory.

## First adapted V-A runtime attempt

The repaired adapter was independently approved before execution, with full frozen snapshot hash verification and unchanged hashes for all 16 reviewed import-graph files. The first run stopped during product imports, before any product canaries or historical probes: checkpoint imports Python stdlib `uuid`, which calls `platform.system()` -> Android `android_ver()` -> `ctypes.CDLL("libc.so")`; the recorder raised `ReplayBlocked: ctypes.CDLL`. This is a safe harness/import preflight stop, not a product bypass or successful replay. Literal traceback: scratch `replay_guard_runs/va-d29x8ot6/controller.stderr`.

The initial adapter did not persist the event list on this import exception; that evidence-retention gap is explicitly retained. A narrow bootstrap repair preloads only vetted, source-hash-pinned platform/uuid dependencies before installing the guard and adds typed import-stop event persistence. The actual device has no optional `_uuid` extension; the repair refuses one if present. Product-time ctypes calls remain blocked. Pure/bootstrap tests passed, but the changed adapter requires new independent review before retry. No historical V-A success is inferred from the planning/selftest output.

## Continuation checkpoint — 2026-10-26

Production source remains frozen at pushed `770dc66`. No additional production change or full-suite rerun is claimed. C1's 355 exact manifest dispositions are independently APPROVED: independent random sample 89 had 0/89 initial disagreements; expanded mandatory review covered all 355, all 97 source/caller hashes matched. All 35 READ capabilities and their 70 paired declaration/implementation rows were traced through their real effects, including sampler threads, SQLite initialization and fixed process reads. All 332 native helper rows, six unenforced metadata rows and 17 activation entries were reviewed. The report discloses that author READ notes were encountered during initial inventory; it does not claim a blind experiment. Existing missing exports remain NEW-864/NEW-985, not repaired or silently treated as functional.

C1+C3+C7 now provide **650 approved unit dispositions of 1,467**. The register is still unchanged; these approvals do not imply zero UNKNOWN in the canonical register. C2 (business) and C4 (lifecycle/inference) are being authored; C5 has 131 draft rows from 22 reviewed source files, with 48 rows/seven source files still pending; C6 has not started. No new production fix is hidden in classification.

### Approved adapted V-A result and factual correction

The second exact reviewed adapter run completed on frozen `770dc66` under nonce `replay_guard_runs/va-ybv196pf`. Independent result audit reconciled **269 case files, 267 matched controls, 301 recorded events and all 1,267 source hashes**, then APPROVED the corrected result. Three product canaries passed, including expected product refusal and recorded/refused ACT attempts; the fabricated effect marker stayed absent.

The 266 data groups represent 268 references with two exact duplicate aliases, comprising 264 runnable groups and two explicitly unrun cases (NV30 invalid expectation; NV32 superseded by EV01). Data-only results:

```text
233 product refusals
20 positive-control primitive attempts recorded and refused by the harness
8 accepted-residual attempts recorded and refused by the harness
2 clean-sample attempts recorded and refused by the harness
1 stricter product refusal
2 invalid/superseded cases not run
0 FAIL; 0 INCONCLUSIVE
```

Every runnable data case and product canary has a same-rebased-argv recorder-only matched control. This proves recorder reach/refusal, not executable availability or actual command success. The 299 subprocess records comprise 267 raw matched controls and 32 product attempts, all refused; one invalid-PID signal-0 canary and one Requests-import socket-bind attempt were also refused. The original 267-row inventory retains 193 mapped IDs and 74 unselected/pending-oracle IDs; no claim all original inventory rows were replayed. Eight new S2 casefold probes are included. Other B/C units and S1b are still pending.

**Rule-6 correction:** the earlier receiver statement that StateStore was never constructed was false. Importing checkpoint calls its module-level schema extension, which creates StateStore's fresh SQLite schema/WAL under the nonce's prevalidated CODEY_STATE_DIR. SQLite/file writes were not intercepted; this owned, source-constant bootstrap is an actual permitted filesystem effect. The source-reconciled selected closure has 18 modules, including lazy export_hygiene/trajectory imports; it is not a saved runtime module trace or a global dynamic proof. Of 104 receiver candidates, StateStore's connect is reachable during this bootstrap, trajectory's connect is not called by masking, and 102 remain outside this selected closure. Original false claims are preserved in `.before_R1` artifacts. The main DB mtime after completion is consistent with WAL finalization, whose timing cause is not proven. No coordinator post-run product import or DB seed occurred.

Independent review approved these factual corrections without changing the adapter or repeating the probes. Evidence: `VA_REPLAY_RESULT.md`, `VA_OWNERSHIP_R1.md`, `VA_FROZEN_RUNTIME_CLOSURE.json`, `REVIEW_VA_RESULT.md`, retained per-case JSON and original first-attempt traceback. These results establish the stated recording-fixture tier; no attended terminal, real model/bench, credential, service or live business DB claim is made.


## Classification continuation — author completion, mandatory fresh redo and scope findings

C2 authoring is complete: 304 exact keys/21 files, 77 source/caller/test/context hashes stable, no UNKNOWN or reviewer signatures. C5 authoring is complete: 179 exact keys/29 full source files read, all source hashes stable and 53 caller/test hashes retained. Its counts are 84 GATED, 45 BOOKKEEPING, 23 OPERATOR_SCRIPT_RUNNABLE, nine OPERATOR_BOOTSTRAP, nine FALSE_POSITIVE, six DORMANT, two LOOPBACK_IPC and one READ_NOEFFECT. These remain author candidates pending independent review, not approved additions to the 650-row total.

C4 independent review is CHANGES REQUESTED by procedure: initial seed 77020261028 random 39 had 10 differing initial classes (25.641%). Some are taxonomy/reviewer trace errors and some require author correction; the rate remains recorded. The plan requires a fresh classifier to redo all 153 rows. Original-author R2 reread/refinements are preserved as context, explicitly not a substitute for fresh classification or approval. No signed C4 register is emitted. C4 fresh authoring is in progress.

C6 authoring halted before dispositions when an unchecked absolute capability name was found selecting optimizer generation writes outside staging before any deployment gate. Independent static assessment confirms the defect and reconciles 50 source/context hashes. No main/daemon/API lifecycle caller was established; current default off and demo-only wiring limit exposure. Coordinator records NEW-1096 LOW/dormant, OPEN/QUEUE, with conditional HIGH code-overwrite impact and mandatory reassessment before production wiring or shadow/on activation. This is not residual acceptance or a claim the later deploy gate protects generation. NEW-1095 separately records the confirmed missing subprocess binding in two conditional alternate peer runners, LOW/QUEUE. No fixes or runtime exploitation were performed. Full findings and limits are in NEW_ISSUES.md and scratch REVIEW_C6_BLOCKER.md.

All ten stale canonical register keys have proposed individual current-key mappings in scratch stale_register_adjudication.json, supported by actual moved helper/callback source. The canonical register remains unchanged, with original entries preserved. Manual reconciliation needs independent review and complete current-unit approvals before merge. Source freeze, full test results and adapted V-A evidence remain unchanged. Usage-limited agents wrote their reports/checkpoints before interruption; continuation reuses those artifacts.


## Current continuation — 1,107 approved classifications; remaining redos and bounded B1 run

Source is still frozen/pushed at `770dc66`. Approved units now total **1,107/1,467**: C1 355, C2 304, C3 159, fresh C4 153 and C7 136. C2's full304 were individually audited; C4's85 reviewed rows are signed and68 remain author-only under sampled unit approval. Combined five-unit individual signatures961, unsigned146; unit approval is not a claim all1,107 were independently reclassified. Raw author/reviewer/history packets are copied to `docs/wp21_census/review_770dc66/`; approved V-A records to `docs/wp21_census/replay_A_770dc66/`. These new publication directories and documentation are uncommitted and still require package review. Raw trailing empty TSV cells and literal stdout whitespace are preserved intentionally.

C5 original initial11/45 differences(24.4444%) required a fresh179-row redo; the architect's full fresh candidate then differed8/45(17.7778%), requiring a third fresh classifier. These include reviewer caller assumptions and taxonomy differences, not19 proven product bugs. Implementer is authoring that third source-first map. C6 author181/43files completed with116 frozen source/context hashes; independent initial13/46 differences(28.2609%) require a fresh181-row redo, now assigned to the architect. Nine C6 differences concern the explicit spec convention that demo/plugin-test SCRIPT includes bootstrap rows; three concern generated staging, one dormant missing containment. Conventions are clarified before redo; initial rates are retained literally. NEW-1097 records unused Sandbox workspace-name containment LOW/dormant/QUEUE, not residual acceptance. No new production change or established active HIGH exposure.

A separate independently approved B1 bridge adapter ran once under owned `b1-_rr31qb3`: child0,16 selected historical references,15PASS_OWNED_FIXTURE plus N17PASS_SELECTED_SUBCASE_HISTORICAL_PARTIAL. Its omitted absent-file patch/existing-file comparison remain pending. Sixteen raw ordinary-mirror controls succeeded; they do not reproduce exact paths/symlinks/inodes/source bytes/absence. Actual ordinary write/append/read and file-I/O canary succeeded. Historical cases made zero primitive attempts and zero stdin reads; two total guard events were refused Requests-import socket.bind and the explicit refused subprocess canary. Owned SQLite schema/WAL bootstrap was allowed, state.db53248bytes; file I/O is not globally intercepted. Full sourcecopy unchanged. This is author-observed, **independent result audit pending**, not complete B1/B2, realTTY/live integration or closure.

Canonical register remains unchanged:1,433UNKNOWN/38coveragefailures; ten stale-key mappings await independent review, C5/C6 await approval, default gate remains unflipped. The census parser uses literal tab splitting, unlike quoted CSV TSV unit packets: final merge must decode packet CSV then use the frozen canonical renderer and check roundtrip; byte concatenation is invalid. Remaining B/C/S1b replay, default-gate/test verification, finding/residual/manual-tier reconciliation, documentation/package review and final concrete Ish sign-offs remain open.
