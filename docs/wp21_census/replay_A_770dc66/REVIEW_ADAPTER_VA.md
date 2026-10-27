# V-A adapter independent review — initial checkpoint

CHANGES REQUESTED before runtime/product import approval. Pure-data plan/adapter source only inspected; no product snapshot import, guard installation in target, canary or replay executed. Read full379-line adapter, case-data structure/samples/counts, final ADAPTER_VA report, import graph/receiver ownership inventory and previous guard review. Author notified and repair in progress; do not treat this checkpoint as final corrected-version review.

## Required corrections

1. Literal per-case evidence is discarded. one(row) retains only classifier/attempt-count/verdict/exception-type/template and aliases; actual product output/refusal reason and associated guard event payload/range are absent. Aggregate guard events are written only after ALLcases finish, so interruption loses the exact primitive evidence for already summarized attempts. Preserve bounded verbatim product output/refusal text with explicit truncation/hash if bounded, exception diagnostic, case-to-event indices/payload, rendered-input identity and immutable historical/control mappings incrementally after each case. Inputs/state are fabricated; do not import/read real credentials to supply output. Pending/skipped rows stay explicit, not PASS.

2. Global touch/echo controls test recorder plumbing but do not provide the per-refusal matched control required by closure spec2.0. Supply explicit original/pre-fix control provenance per row or safe same-argv RAWrecorder-only control under the identical installed tripwire (no guard override, no real subprocess output/return). Every PASS must link a control proving expected primitive reach can be recorded, while marker remains absent. Do not claim raw recorder reach proves executable availability or shell semantics.

3. Enforce expected event multiplicity. Current bool(events) accepts repeated subprocess.run attempts with sameargv as a positive-control PASS. Require exact1 for positive/raw controls and residual attempt cases; more than1unexpected primitive attempt must fail/abort with retained evidence. Refusal oracle still fails on ANYevent regardless of output string. Existing no-event non-BLOCKED result correctly stays INCONCLUSIVE.

## Already inspected, satisfactory restricted structure

Guard installs before tools.shell_tools/core.task_executor imports; identity rechecked after imports and each case; unexpected import event or non-subprocess.run effect aborts. Per-event argv hashes must exactly match shlex.split command. No recorder override, saved-real function restoration, actual network/Git/peer/grader/model/canonicalservice allowance. Controller owns exact isolatedPython child with bounded timeout; fixture root/hash manifest/env provenance verified before guarded import, snapshot copies symlink-free into noncefakeHOME/Codey-OS. HOME/state/config/audit/DB/PREFIX/tmp/Git config under ownedroot; helper fixture writes and symlinktargets constrained there; PATHshadow restored after case. Native/captured-alias/FS limitations remain explicitly disclosed.104receivers are not resolved globally: only core.state.sqlite candidate is mapped to lazy constructor in selected diagnostic graph; refresh actual finalfreeze import/path audit before runtime approval.

Pure-data evidence independently executed:
```text
python3 -I -B /data/data/com.termux/files/usr/tmp/wp21_closure_next/replay_va.py --self-test
{"selftest": "PASS_PURE_DATA_ONLY", "legacy_rows": 267, "report_references": 260, "legacy_mapped": 193, "legacy_pending": 74, "unique_data_groups": 266, "new_probes": 8, "product_imports": 0, "product_canaries": 0, "historical_probes": 0}
```
267legacy IDs preserved;193mapped including10RC,74pendingnotrun.260historical references +8new ->266dedupgroups preserving268aliases; NV30invalid and NV32superseded explicitskips. Eight accepted residuals remain attempts REFUSEDbyHARNESS, never successfullyexecuted. V-G14 correctedfakeHOME/CODE_DIR method must remain disclosed and receive finalfrozen-tree oracle evidence. Old42NV/5EV are replayrefs, not newly authored probes;8S2 cases within cap. Inputsource TSV hash independently matches c23a951143df77368bd573b8891782a0a905b2970c0fd2d30728ef9b86102fbd.

Approval metadata is accidental-run protection, not authentication; coordinator must derive supplied filehashmanifest from an actual gitarchive of the claimed frozen40hexrev and record provenance. Source7fe60cc importgraph is diagnostic only and mustrefresh. No final replay permission until repaired adapter independentAPPROVED AND committedfreeze AND explicit coordinator authorization. No repo/index/source changes; only this authorized scratch report written.

## Corrected V-A adapter re-review

APPROVED for the exact corrected adapter/data/guard and limited V-A scope, contingent on coordinator explicit runtime dispatch with frozen770dc6639e4100ea3215fca07d923769a8290078 manifest. Initial CHANGES REQUESTED is superseded, evidence preserved. No product import/canary/replay executed by reviewer.

Independently inspected actual va_review1_fix.diff and corrected target/persistence/oracle helpers. Each case now retains bounded literal fabricated product output plus fullhash/length/truncation, bounded exception diagnostics, rebased command/argv, full alias-specific history/finding metadata, exact product/control event slices and global ranges. Per-case owned-root JSON is written through temp file then replace before summary rewrite; interruption after completion retains prior literal evidence. Unexpected eventshape/integrity/multiplicity is saved before abort. Invalid/superseded rows explicitly persist skip/noattempt/control-notrun.

Every runnable case invokes ONLY installed subprocess.run tripwire with same rebased argv, requires ReplayBlocked/exact1matching event/absentmarker, then invokes product under unchanged tripwires. No real return/function restoration or recorder override. This is a recorder reach control, not executable availability/semantics proof. Productevent>1is failure/abort; anyexpectedrefusal eventfails even when output saysBLOCKED; noevent/nonBLOCKED remainsinconclusive. ACTpositivecases requireoneevent. Product canaryACT/HIGH/daemon controls precede originals and abort on any failure. Historicalresidual attempts remain harness-refused, never falselyexecuted.

Independent pure-data selftest again exit0:
```text
{"selftest": "PASS_PURE_DATA_ONLY", "legacy_rows": 267, "report_references": 260, "legacy_mapped": 193, "legacy_pending": 74, "unique_data_groups": 266, "new_probes": 8, "product_imports": 0, "product_canaries": 0, "historical_probes": 0}
```
Reviewed actualhashes:
replay_va.py02d3a7b95ab54b3fb7b79081963c66484710ed6dcb2402147952b08b98cc5cb8
replay_va_cases.json8efc61fb08e65b9e7c688e6120645d190de34ff4331ac6e50ddee1362f5aa583
replay_guard.pyf68aa877fa92d0fc979c807d3fe7ce0e0d85d9d02075fce2c6bd61ecf0c36995

FREEZE.md now records actualcommitted770dc66. Before runtime, coordinator must bind approvalmetadata to these exacthashes/fullrev and actualarchive filehashmanifest, refresh source provenance/selected importgraph at frozenHEAD, and retain finaloutputs. Existing diagnostic receiverinventory is NOT a universalresolution of104candidates; no arbitrarynative/FS sandbox is claimed. Guard-before-import, fresh minimalenv nonce roots, productfileprovenance, no external/realchild/realnetwork exceptions and only expectedsubprocess.run events remain mandatory. Parentcontroller alone owns exactPythonchild with timeout; no canonicalservice/model/bench/grader/Git execution permitted. No sourcechanges afterfreeze without renewedclassification/replay review.

Coverage remains193mappedoriginalIDs plus historicaldefensive/controlrefs,74legacyoriginals pendingnotrun,266dedupgroups including2explicit skipped,8newcases. Do not report complete267original execution or allPASSfromexit0. Later output must distinguish productrefusal, attemptedprimitive refusedbyharness, residualnotobserved, skips/inconclusive/failures. This approval permits coordinator to dispatch this exact bounded adapter after metadata/preflight; it does not authorize other Vunits or S1b, alterpolicy, signresiduals/DoD or closeWP2.1.


APPROVED — narrow V-A Android stdlib bootstrap repair

Exact reviewed replay_va.py SHA256 a644d8d176a13ad793b446500d9acbde1f921c12384c3e378271f2a85b551f32. Prior source copy matches earlier approved02d3a7b95ab54b3fb7b79081963c66484710ed6dcb2402147952b08b98cc5cb8; data8efc61fb08e65b9e7c688e6120645d190de34ff4331ac6e50ddee1362f5aa583 and guardf68aa877fa92d0fc979c807d3fe7ce0e0d85d9d02075fce2c6bd61ecf0c36995 unchanged. Independent AST parse and incremental diff inspection completed.

Read BOOTSTRAP_VA.md and actual driver, adapter, local stdlib source. platform/uuid actual hashes match pins. uuid module import calls platform.system; current Android os.uname branch leads platform.android_ver -> local CDLL(libc.so).__system_property_get, reading fixed OS properties. That handle/function stays local to android_ver; subsequent calls import current patched CDLL. No subprocess/getnode/uuid1 or product execution is introduced by preload. Optional _uuid is refused before import and checked after import, avoiding captured native UUID helpers. Stdlib origins and contents must match exact reviewed paths/hashes; unexpected runtime/native extension fails closed. Preloaded product check precedes bootstrap and guard install still precedes every product import. No original primitive is restored or recorder weakened.

Import try/except now covers product imports, guard-integrity/event, module-origin and runtime-root checks. save_import_stop persists typed failure, bootstrap IDs, capabilities and full existing events via own-root write before rethrow without assert_integrity-first save. No arbitrary exception __str__ invoked. Persistence remains best effort under filesystem failure, explicitly disclosed. Filesystem/native guard limits remain unchanged and no broad sandbox claim follows.

Independent harmless bootstrap selftest executed with python -I -B selftest_va_bootstrap.py. Exit0. Owned disposable root replay_guard_runs/va-bootstrap-test-3cxnlw2g retained, controller.stdout/stderr evidence there. Literal result: PASS_STDLIB_AND_GUARD_ONLY, ctypes_attempts_refused2, failed_import_evidence_savedtrue, product_imports0, product_canaries0, historical_probes0. Driver hash98036ead139f29c3e51316cff8c61cdede9921f7bfa310d8ff6d4f697d70742e verified. Negative wronghash refused; cached imports generated no event; fabricated CDLL and actual platform.android_ver both hit patched CDLL; custom error string never evaluated and typed event evidence persisted. No product replay/canary run by reviewer.

APPROVED for this exact adapter hash under prior frozen770dc66 snapshot/controller/nonce/root/provenance and intact-guard conditions. Coordinator alone authorizes retry. This approves neither a successful replay result nor unresolved74 historical oracles,104 receiver completeness, residual acceptance, live behavior or WP2.1 closure. Changed stdlib/runtime/hash/native extension requires renewed review.
