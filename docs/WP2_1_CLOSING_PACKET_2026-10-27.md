# WP2.1 closing packet, 2026-10-27

**Status: READY FOR ISH'S SIGN-OFF. WP2.1 IS NOT CLOSED.** Nothing in this
packet records closure. Closure is Ish's call (spec 4.3, Z-7); the DoD
statement below is a draft with the closing HEAD left blank until the reviewed
closeout is committed.

Frozen production source: `770dc6639e4100ea3215fca07d923769a8290078`
(`770dc66`), committed and pushed; local HEAD and `origin/main` were equal when
this packet was assembled and no commit exists after it. Production source has
not changed since the freeze. Everything in section 1 marked "uncommitted" lives
only in the working tree.

Authoring note: this packet was assembled by the project-architect agent from
the scratch directory `/data/data/com.termux/files/usr/tmp/wp21_closure_next/`
(outside the repo, volatile) and from the working-tree ledgers. Durable copies
of the evidence it cites are in `docs/wp21_census/closing_770dc66/`
(README + `SHA256SUMS`). Nothing was run to produce it except read-only hash and
count computations (section 9). Tier words follow `CLAUDE.md` rule 7 and are
never collapsed: **code-complete**, **reviewer-approved**, **live-verified**
are three different things.

## 1. What is DONE, with literal evidence tiers

| # | item | what exists | tier |
| --- | --- | --- | --- |
| 1 | Source freeze | `770dc66` pushed; 21-path prefreeze tranche APPROVED before commit | code-complete + reviewer-approved, committed; not live-verified |
| 2 | Census register, 1,467 exact keys | `docs/wp21_census/dispositions.tsv` in the working tree, SHA256 `5279004783c2c3dc37208f061d76c97fdb1ec558d5eabbcd27dc61f1a8d0de7d`; 0 UNKNOWN; merge of 7 unit packets, 10 stale keys re-mapped, canonical register edited only by installing this file (the original, SHA256 `f405a6715247c0781abb3232b836d9417fb15d1c46a18b741a7820672a6dcf3f`, is preserved at `770dc66` and in `docs/wp21_census/review_770dc66/`) | **uncommitted**; mechanical `--check --strict` result 0 failures / 0 UNKNOWN / 0 warnings (`merged_candidate/census_check_strict_output.txt`); classification content reviewer-approved per unit as below, with the caveats in section 2 |
| 3 | Default-blocking coverage gate | `tests/test_wp21_census.py` working-tree change: warn-only branch and `WP21_CENSUS_GATE` removed, five disposable-repo proofs added (complete register passes; undispositioned boundary, business boundary, business qualname-count mismatch, stale row fail) | **code-complete + reviewer-approved (reported), uncommitted, not live-verified.** Two independent code-reviewer rounds: round 1 CHANGES REQUESTED (code sound; operator docs not yet updated), round 2 APPROVED. **The reviewer kept no file**: `closing_770dc66/GATE_AND_DOCS_REVIEW_RECORD.md` is the coordinator's transcription of the in-session reports, not a reviewer artifact. Round 1 reviewer re-ran the tests (candidate register default `123 passed, 1 skipped`, STRICT=1 `124 passed`; gate reverted to warn-only -> 6 failed; business gate default False -> 2 failed). Gate run: `census_strict` 124 passed. See the diff-match statement below this table |
| 4 | Operator docs (`docs/security.md`, `docs/commands.md`, `docs/architecture.md`) | working-tree edits correcting authority, confirmation, network and test claims | **code-complete (docs) + reviewer-approved (reported), uncommitted.** Reviewed in the same two rounds (round 1 found them not yet updated, which the gate scope requires in the same change; round 2 APPROVED: docs hunks accurate, no current-tense warn-only/opt-in claim remains). Same caveat: the approval is recorded only by the coordinator's transcription |
| 5 | `CLAUDE.md` rule 8 revision (fix-when-related / log-with-trigger, Ish 2026-10-27) | edited in the working tree | uncommitted; Ish's own edit authority |
| 6 | V-A recorder-only replay at `770dc66` | run `va-ybv196pf`: 269 case files = 266 data groups + 3 canaries; 264 runnable, 2 unrun; 233 product refusals, 20 positive attempts refused by the recorder, 8 accepted-residual attempts refused, 2 clean attempts refused, 1 stricter refusal; 267 matched raw controls; 301 events; 0 FAIL, 0 INCONCLUSIVE. Adapter `a644d8d176a13ad793b446500d9acbde1f921c12384c3e378271f2a85b551f32`, guard `f68aa877fa92d0fc979c807d3fe7ce0e0d85d9d02075fce2c6bd61ecf0c36995` | reviewer-approved (`REVIEW_VA_RESULT.md`, final R1 re-review). **Recorder-only: every primitive attempt was recorded and refused, nothing executed.** Evidence copy `docs/wp21_census/replay_A_770dc66/` (uncommitted). Not live-verified |
| 7 | B1 selected bridge | see the verbatim citable wording below | owned-fixture replay on fabricated fixtures; independent audit verdict CHANGES_REQUESTED on author wording only (raw evidence consistent, no escape found); **the citable wording (`B1_CITABLE_WORDING.md`, `280e7687...`) was revised after that audit and has NOT been re-audited** (the audit JSON carries its own proposed wording; the revised file is the coordinator's); not live-verified; not full coverage |
| 8 | 49-item G15b reconciliation | `G15B_49_RECONCILIATION_FINAL.tsv` SHA256 `5c0f82d4c4ad7146faef1b8b33bc12d04c42e43e004de79cff6a840025e90e29`: 28 CLOSED_CODE_REVIEW / 3 ACCEPTED_RESIDUAL / 12 PARTIAL / 6 OPEN; severity 32 HIGH / 10 MEDIUM / 7 LOW | see section 2, "approval chain": re-review returned CHANGES_REQUESTED on a predecessor file; the fixes were applied afterwards and mechanically re-checked, not re-approved |
| 9 | Frozen-source test verification | raw `summary.txt`: **9,299 passed / 13 failed / 2 skipped / 19 subtests**; effective after the foreground rerun of chunk 29 (264 passed): **9,303 passed / 9 failed / 2 skipped / 19 subtests**; guarded CCOS 1 failed / 184 passed (NEW-805 `test_multi_domain` failed; NEW-1090 passed this run); census strict 124 passed; zero guard refusals | measured on the working tree (frozen source + uncommitted test/register changes); recursive 32-chunk runner, not a single full-suite run |
| 10 | Census determinism | three frozen runs: the 6 TSV inventories plus `summary.json` are byte-identical across runs 1, 2 and 3 (cli_flags, dispositions.seed, env_names, manifest_scan, scan, shell_scan). "Five inventories" in the brief excludes `dispositions.seed.tsv`; all six match | measured; run 1/2 had no SHA256SUMS, the generated sums are in `closing_770dc66/census_frozen/` |
| 11 | Ledger/document reconciliation | NEW-1023/1044/1026 corrections, stale-header updates, trigger tags, LIVE_TEST_QUEUE entries, blueprint status | documentation, uncommitted, written this pass |

**Does the final diff equal what was reviewed? What can and cannot be verified.** Verified: the current working-tree files are byte-identical to the copies in the gate-run snapshot (`final_tests_gate/ccos_verify/snapshot/`, used for the guarded CCOS run): `tests/test_wp21_census.py` SHA256 `ff95fbcdeaf88e1e6a0e3f7610111603a27b047c4f5858c8aa82534a1f806134` (file mtime 09:23:30), `docs/security.md` `1d6c7bea6990b6d889fa1c7314557a7a73301d45a4e55a8d4f4a9a1dbd154517` (09:29:42), `docs/commands.md` `133455401125833fad497a1bf4e845d214478e58d79a2423157f537463d3d839` and `docs/architecture.md` `e07fbd0f371110a98d342f6d307d05479f00a8dc10dcd0748cddbec1b170f99b` (both 2026-10-26 08:40). `commands.md` and `architecture.md` also match the earlier operator-docs candidate hash manifest; `security.md` does not (it was edited after that manifest, at 09:29:42, which is consistent with the coordinator's account that the implementer edited the docs before round 2 and nothing after). Not verifiable: the exact bytes the reviewer saw in round 2, because no reviewer file or hash was kept; I rely on the coordinator's statement that nothing changed after round 2 and on the mtimes being earlier than the gate-run summary (09:48:04).

### B1 citable wording (verbatim from `B1_CITABLE_WORDING.md`, SHA256 `280e7687fa3ede29e1c7793681b4b0f8ec28044c70d6ae56c8a9198d4c8d1b2d`)

MAY CITE: "B1 selected bridge: 16 mapped historical references re-executed once on fabricated owned fixtures, under reviewed adapter 4030bdfa4da8ec99c6194c4631a4afc18d36d9d579865cb0bac0250b3569c9b9 and data 10ea68c558bb5cf60fe9cbe884164c4badcc60cd6eff61773d6ddf8bd3432e0c, against frozen 770dc66 (1267-file manifest). 15 selected operations passed their oracles; N17 passed only a read-only partial subcase. Process and network primitives were recorded and refused: 2 events (a loopback IPv6 bind inside urllib3 import, and an explicit subprocess canary). No real TTY, live state, or real credentials." Tier: owned-fixture replay; not live-verified; not full coverage.

MAY NOT CITE: "16 completed / 16 PASS"; all historical rows / all of B1 or B2 / the 272-row ledger; "child exit 0" as retained evidence (only the completion marker `out/b1-complete.json` is retained); "no network attempts"; protected-path coverage for HM-01/03/08/11 (they hit the HIGH no-confirmation gate first); "refused before read" for FT12; N17 as covering the no-existence-oracle claim; "committed copies"; live-verified / real-TTY-verified / WP2.1 closure; coverage of final HEAD.

Housekeeping the auditor requires: a stray `frozen_source_770dc66/tools/__pycache__/wp21_census.cpython-314.pyc` (mtime 2026-10-27 09:18, not in the manifest) must be removed or documented before any later replay. It is documented here; it was not removed by this pass (scratch is outside scope).

### Classification units, with the rates retained

Rates are retained literally; they include taxonomy and reviewer-assumption differences, not only proven author bugs.

| unit | rows | state | individually signed (`reviewed_by` in the register) | retained rates |
| --- | ---: | --- | ---: | --- |
| C1 manifests | 355 | APPROVED | 355 | random 0/89; all 355 audited, 0 differences. Reviewer saw author notes during inventory: not claimed blind |
| C2 business | 304 | APPROVED | 304 | initial 3/76 (3.9474%) |
| C3 shell | 159 | APPROVED | 159 | disagreement list preserved in `C3_REVIEW_DISAGREEMENTS.json` |
| C4 lifecycle/inference | 153 | fresh classifier APPROVED | 85 (68 author-only under sampled approval) | **original 10/39 = 25.6410% (failed threshold, fresh redo)**; fresh 3/39 = 7.6923% |
| C5 state/tools/peers | 179 | third fresh author, review **round 4 APPROVED** (JSON labels itself "round 3 (final)" but carries `round: 4`; cite round 4) | **0 in the register**; 112 rows individually signed in the review JSON only | **original 11/45 = 24.4444%; second 8/45 = 17.7778%** (each forced a fresh classifier); third author: round 1 3/45 random (reach) + 6 mandatory, round 2 0/45 + 2 out-of-sample, round 3 0, round 4 0/45 + 0 mandatory |
| C6 CCOS | 181 | fresh author, review APPROVED with warnings | **0 in the register**; 87 rows reviewed in the review JSON only | **original 13/46 = 28.2609%**; fresh 0/46, **NON-BLIND (author and old labels were open to the reviewer), so 0/46 is a literal count, not an agreement statistic** |
| C7 tools/pipeline/bench | 136 | APPROVED | 58 (78 author-only under sampled approval) | raw 3/34 = 8.8235% (semantic 2/34 = 5.8824%) |

`reviewed_by` populated in the installed register: 355 + 304 + 159 + 85 + 58 = **961** rows. The other 506 rows are author-only (unsigned under sampled unit approvals, or C5/C6 rows whose reviews live in their review JSONs). Unit approval is not a claim that every row was independently reclassified.

C6 hash chain: the review approved `b2aa8b12e8af1a1a9fcc1fe0ea3ea7a1f1b840f7554e1fdd02fac43fb0e84703`. The installed packet is `d61a5afb88cec10c6462f25670d228648981b361e1d4cb7abeac7f55395857ff`, a text-only reseal of 3 rows (evidence for `sandbox.py` `run_command`/`run_python`, termux extended `_run`; plus a NEW-1099 finding cross-reference) made after reviewer warnings W1/W2. The changelog (`C6_FRESH_RESEAL_CHANGELOG.json`) lists class, key, reach and severity unchanged. The resealed file was validated by the author's scripts only; no reviewer re-read it.

C5 hash chain: reviewed and installed packet `7bbfdaf657ce0b823c523890b83e982c483a6db58d3462f780b3c80915e3cfd8` (pre-round-2 copy `8c24d6bb084d764e42b9f18e1c4bce139451328d4d911300926e4d8d4cb94176`). C5 helper GATED rows (84), the UNMEDIATED rows (2) and the four `setup_dr_key` rows were all individually signed in round 4.

Stale-key reconciliation (10 keys): `stale_reconciliation_REVIEW.json` (SHA256 `f6f704e43fb5af286d8fd169e58580d693f071aa5406fa433a57a5bce605a6a6`) has no top-level verdict; each of the 10 mappings is marked APPROVED and the review lists 3 `required_changes_before_approval` (setup_dr_key reason text; `adjudicated_by` identity; explicit `first_seen_rev` for successors). The adjudication file (`b5134f0b54f1950d03cd77344ee3585d9961e0257b457d11b09e333c87644dbd`, 09:16) was edited after the review (09:14) and carries the corrections; **no second review of the corrected file exists**. `stale_key_movements_PENDING_REVIEW.json` still says `PENDING_REVIEW` on every entry. The 10 successor keys carry `first_seen_rev = 770dc66` (checked by `independent_checks_output.txt`).

## 2. What is NOT claimed

- **Not closed.** No closure, no live verification of WP2.1 as a whole.
- **Replay expansion is DEFERRED by Ish (2026-10-27, coordinator brief; no earlier ledger entry existed, the entry is made in `PROJECT_LOG.md` by this pass).** Not done: the B1 HIGH matrix (31 original HIGH append cases; 13 ACT/residual cases excluded; architecture scope never started, no adapter exists), final-HEAD S1b, the remaining B / C1 / C2 / C3 replays. V-A covers 193 legacy IDs mapped to its cases; **74 of 267 original IDs are unselected**; the 272-row historical B ledger has 16 selected and 256 unselected rows. No claim of full historical replay.
- **V-A is recorder-only.** It proves classification and refusal on the replayed argv, not execution semantics, and it permitted owned SQLite bootstrap writes (state.db 53,248 bytes). It is not a filesystem or native sandbox.
- **Live-verified only on disposable fixtures where a row says so** (G15b-12, G15b-25). No attended Termux terminal check, no real cloudflared token run, no real bench run, no real aigentik/private_agent spawn, no real escrow key, no peer-binary run. Those are the Z-5 schedule (section 6).
- **NEW-1101 (accepted limitation, Ish option 2).** The scanner constant `DYN_EXACT` has no `exec_module`/`load_module`; the scanner and frozen inventory were not extended. 15 supplementary rows (`supplementary_dispositions.tsv`, SHA256 `50fa9ba0cac5cb324daed87bb48a33c7019d9b0dea631a064cee82a9661b3e2a`; 2 production sites + 13 `ccos/plugins/**/test.py` sites; reviewed in rounds 1-3, round 3 APPROVED) sit **outside** the scan-checked register: they must not be merged into `dispositions.tsv` (`--check` would report each as a stale row) and **`--check` verifies none of them**. Dynamic-module-execution inventory rests on those 15 rows plus this limitation.
- **NEW-1103 (MEDIUM, open).** The default gate can be passed by renaming a registered boundary file to a `test_*.py` name; stale rows for files absent from the scan only warn. Not fixed (the census tool is itself a scanned file).
- **NEW-805 and NEW-1090** (intermittent CCOS test failures), **NEW-1104** (4 `test_service_lifecycle_mechanics` caught-signal parameters fail only when launched under `nohup`; foreground 59 passed; the gate-run chunk 29 failures were this artifact), **NEW-1105** (SUSPECTED: a test appears to write live `ccos/data/capabilities.json`; mtime 09:46:40 inside the gate window; not isolated).
- **Baseline failures are not fixed.** The recorded baseline is 10 nodes; this run had 9 (the 10th, `tests/test_task_executor_telemetry.py::test_orphaned_thread_never_corrupts_concurrent_tasks_stats`, passed this time). That is intermittence, not a fix: G15b-49 stays OPEN. The 9 failing nodes are the 4 in `test_74b_planner_and_coder_n_ctx.py`, 3 in `test_new84_stale_model_path.py`, `test_new91_new163_rollback_preserves_finetune.py::test_rollback_after_swap_restores_base_and_preserves_finetune`, and `test_daemon_shutdown_budget.py::test_fixed_profile_trace_only_canonical_daemon_receives45` (`failed_nodes_now.txt`, `base_ids.txt`).
- **Ruff is not green:** 190 scoped findings against a 179 baseline. This is the prefreeze measurement (`prefreeze_ruff.json`) and was **not** re-run in this pass. **mypy is unavailable on this device** (NEW-984).
- **Stale adjudication edits were NOT re-reviewed.** `stale_register_adjudication.json` (SHA256 `b5134f0b54f1950d03cd77344ee3585d9961e0257b457d11b09e333c87644dbd`): the reviewer approved the pre-correction mapping (`f4143ee832586aa2b70f753dfa44004c5a457337552d8193e20bd59cef645ca0`) and listed corrections as required. The coordinator then edited, on all 10 entries, `adjudicated_by`, `reviewed_by`, `first_seen_rev_decision` and `successor_first_seen_rev`, and rewrote the reason text of the two `setup_dr_key` entries. The `reviewed_by` string on each entry reads as a reviewer attestation but covers only the pre-correction mapping; the reviewer never saw those edits. (A later diff-and-source check confirmed the setup_dr_key citation: `_generate_keypair()` is called at `core/setup_dr_key.py:206` at `770dc66` and at line 133 at `941ec3fb`.)
- **C6 reseal addendum inaccuracies (register row for `ccos/plugins/device/termux_api/extended_api.py::_run::subprocess.run::1`, line 163 of the C6 packet).** The W1 addendum (a) cites `extended.py` aliases at "lines 2-21"; the actual alias lines are 4-22 (line 2 is an import, `notification_channel` is line 22); (b) lists "device.audio_info, call_log, fingerprint, infrared_frequencies, keystore, media_player, ..." as the manifest's names, but those are Python function names; the manifest names are, for example, `device.audio_info`, `device.call_log`, `device.fingerprint`, `hardware.ir_frequencies`, `hardware.nfc`, `media.player`, `media.scan`, `security.keystore`, `ui.toast`, `ui.notification_channel` and `storage.saf_*`. The substance (19 extended capability names, zero overlap with the 41-name manifest, all calling `_run`) was independently checked and is true. The cell text is deliberately NOT corrected, because that would change `d61a5afb...` and every hash citation.
- **`first_seen_rev` provenance.** In the installed register the `first_seen_rev` of existing keys is the merge provenance (for the C6 keys, `941ec3fb`), not the unit packet's `770dc66` column; only the 10 stale-successor keys carry `770dc66`. The register is the authority for that column.
- **The replay-expansion deferral** was relayed by the coordinator from Ish's message of 2026-10-27; there is no Ish-authored ledger text. Ish confirms or corrects it at sign-off.
- **Approval chain for the G15b reconciliation.** `G15B_49_RECONCILIATION_REREVIEW.json` (SHA256 `ab11face1419ecf9177673a1c2c1e4d0d2d3345f36f843a18a95a79e33b258d7`) returned **CHANGES_REQUESTED** (RF-1, RF-2: a second literal `trigger:` tag on G15b-42 and G15b-21; RF-3: a G15b-08 test citation that did not cover `.gitconfig`). It examined the TSV with SHA256 `149f101a4f754da2c5dcfd941977c6d9d5f0cc233102a07241c3d2eaba87ef32` (retained as `G15B_49_RECONCILIATION_FINAL.tsv.pre_rereview`). The current file `5c0f82d4...` has RF-1..3 applied: this pass found exactly one `trigger:` literal in each of the 21 non-closed rows and the G15b-08 cell now cites `test_deny_entries_classify_high_defense_in_depth`. **That is a mechanical check by the assembler, not an independent re-approval of `5c0f82d4`.** The re-review's own `closing_packet_wording` embeds the old hash and the clause "until RF-1, RF-2 and RF-3 are applied", so it is not quoted. Its other limits stand: this does not establish that WP2.1 is closed, that any item is live-verified beyond disposable fixtures, that V-A involved product execution, that the B1 bridge covers HM-01/03/08/11 or final HEAD, or that G15b-20's Q7(c) contradiction is resolved.
- **Reconciliation facts re-stated:** 126 named test nodes cited in the tests column all had a `def` line at `770dc66` (checked by the re-reviewer); 17 file-level citations (2 verified source-path citations). G15b-04 and G15b-32 are HIGH by ambiguity, D-8 not confirmed for those two. G15b-13 changed ACCEPTED_RESIDUAL -> PARTIAL and G15b-34 CLOSED -> PARTIAL (rule 6). No item was upgraded and no severity changed except G15b-12 HIGH -> MEDIUM (NEW-1021, Ish-accepted).
- **Mediator sensitivity checks** and the full per-row mediator proofs from the S6 scope were not part of this pass.

## 3. Evidence SHA256 table (every value below was recomputed in section 9)

| file | SHA256 |
| --- | --- |
| installed register `docs/wp21_census/dispositions.tsv` (= merged candidate) | `5279004783c2c3dc37208f061d76c97fdb1ec558d5eabbcd27dc61f1a8d0de7d` |
| original canonical register at `770dc66` | `f405a6715247c0781abb3232b836d9417fb15d1c46a18b741a7820672a6dcf3f` |
| C1 reviewed packet | `82d69cffc9b2ab99ba584e3e26ab7d2321b7cceaded0f5c55a3cbcfa8ea76ecb` |
| C2 reviewed packet | `869f8fb9e2a1581c973e9d6e40d1b09479835f475ba51f6e3695969ca518eec9` |
| C3 reviewed packet | `6aa4c6a43a39b4a9a4a5708764e6aa793c79212a322b28db37cd3b645ba03706` |
| C4 fresh reviewed packet | `456cadbfe0ca6b67f19edbc46a160a4549e6d4e6538e648ba421683a237f4a21` |
| C5 packet (`C5_FRESH3_dispositions.tsv`) | `7bbfdaf657ce0b823c523890b83e982c483a6db58d3462f780b3c80915e3cfd8` |
| C5 review (round 4) | `954109772f6658fd2379d329cb5e1aaa00e00fc9ade6b1958bb8f3acfb6cc1e9` |
| C6 packet installed (resealed) | `d61a5afb88cec10c6462f25670d228648981b361e1d4cb7abeac7f55395857ff` |
| C6 packet as reviewed (`.pre_reseal`) | `b2aa8b12e8af1a1a9fcc1fe0ea3ea7a1f1b840f7554e1fdd02fac43fb0e84703` |
| C6 review | `8c65742280a76118ece30b12f8802584592e8f0d5e57c586666d16bbc8cbb4e1` |
| C7 reviewed packet | `1b1d15982fdf1c0a8b7955de57da4c2a00f976ead85b39db3ad71f7887826909` |
| merge build summary | `09198d0b71bc1854ea0b8d9e941a1c910174c32fbf9900dcc273a7cc5f5bc350` |
| first-seen provenance | `825fc16b1c062557ed4491ba3ccd351641b2a43f08331edeeccb91138178466a` |
| stale-key review | `f6f704e43fb5af286d8fd169e58580d693f071aa5406fa433a57a5bce605a6a6` |
| stale adjudication (post-review) | `b5134f0b54f1950d03cd77344ee3585d9961e0257b457d11b09e333c87644dbd` |
| supplementary rows (15) | `50fa9ba0cac5cb324daed87bb48a33c7019d9b0dea631a064cee82a9661b3e2a` |
| supplementary review | `ad92819b831292a5128ae9ac16317771c26b333a9061c1eb941251459c3b8cd2` |
| G15b-49 reconciliation FINAL tsv | `5c0f82d4c4ad7146faef1b8b33bc12d04c42e43e004de79cff6a840025e90e29` |
| G15b-49 reconciliation FINAL json | `cf88c29358ad09d5e3a347c239c2e9df1956e81d4c96d3c89b894acc98df2682` |
| G15b-49 reconciliation FINAL md | `97bf7a16b25b709afe2c51b11f3cffd7a0c46af91f05ae738cee9a6cd96b438e` |
| G15b-49 re-review | `ab11face1419ecf9177673a1c2c1e4d0d2d3345f36f843a18a95a79e33b258d7` |
| G15b-49 tsv the re-review examined (`.pre_rereview`) | `149f101a4f754da2c5dcfd941977c6d9d5f0cc233102a07241c3d2eaba87ef32` |
| B1 result audit | `0ede59cfc3d581171b98d360069e5ef959bcaa1c791ce0a816256882997366d5` |
| B1 adapter / data | `4030bdfa4da8ec99c6194c4631a4afc18d36d9d579865cb0bac0250b3569c9b9` / `10ea68c558bb5cf60fe9cbe884164c4badcc60cd6eff61773d6ddf8bd3432e0c` |
| V-A adapter / guard | `a644d8d176a13ad793b446500d9acbde1f921c12384c3e378271f2a85b551f32` / `f68aa877fa92d0fc979c807d3fe7ce0e0d85d9d02075fce2c6bd61ecf0c36995` |
| frozen-source manifest (1,267 files) | `a0a8cd1397add4aeeed60bafd95f2547a36c9caab3310cc47b97331f7729c693` |
| Z-5 deferral schedule | `06eea7a77da76dc7f8f4342b246d729b083058fa10a4ecf93452c765cb57f233` |
| Z-8 tier statement | `2f0e6a644042d720eb8acd3bd3aaf04cfa134b022700f1cb3691ba66150ce338` |
| test gate `summary.txt` | `f6440e9fed3319baf28239e7b4ffff6974242c6fb4779bfb97f0e4e8bbea9f2f` |
| census scan.tsv (runs 1, 2, 3 identical) | `616ee9b058db6a8864e151a2d9e90021542ed49fde351ce485553cc67ec965f2` |

Register composition (from `build_summary.json`): OPERATOR_BOOTSTRAP 223, OPERATOR_SCRIPT_RUNNABLE 149, UNMEDIATED 28, BOOKKEEPING 242, GATED 122, DORMANT 33, FALSE_POSITIVE 88, READ_NOEFFECT 22, NATIVE_AUTHORITY 537, LOOPBACK_IPC 23 (total 1,467). The 28 UNMEDIATED rows each carry a finding, severity and reach (`independent_checks_output.txt`).

## 4. Definition-of-done checklist (spec 4.3 form; "met" means the stated tier only)

| DoD element | state |
| --- | --- |
| Every effectful boundary is mediated, or carries a documented disposition, or is on the accepted-residual list | register complete at 1,467 rows, 0 UNKNOWN (mechanical check passed); content reviewer-approved per unit with the signature and chain caveats in section 1; **uncommitted** |
| Register mechanically re-checkable (`--check --strict`, zero UNKNOWN at the closing HEAD) | passed against the merged candidate on the frozen scan; will need re-running at the actual closing HEAD |
| Default coverage gate blocking; STRICT opt-in; business coverage hard | code-complete + reviewer-approved (reported, two rounds; coordinator transcription in `closing_770dc66/GATE_AND_DOCS_REVIEW_RECORD.md`, no reviewer file; final file byte-identical to the gate-run snapshot, section 1) |
| Accepted-residual list R1-R18 signed (Z-6) | **NOT signed.** R5 and R18 are unratified, section 6 |
| DoD text signed, closing HEAD recorded (Z-7) | **NOT signed**; HEAD placeholder below |
| Z-5 manual deferrals scheduled (R17) | draft schedule only (`Z5_DEFERRAL_SCHEDULE.md`); nothing scheduled or run |
| Z-8 five group-14 slice tiers | statement drafted (`Z8_TIERS.md`); Ish to accept or request runs |
| Replay tier | V-A recorder-only + B1 16-case owned-fixture bridge only; **expansion deferred** (section 2) |
| Ledgers current | this pass: NEW_ISSUES, PROJECT_LOG, blueprint, LIVE_TEST_QUEUE (uncommitted) |
| Tests | 9,303 passed effective / 9 baseline failures / 2 skipped / 19 subtests; CCOS 184 passed / 1 failed (NEW-805); census strict 124 passed |
| Lint / typing | ruff non-green (190 / 179 baseline, prefreeze measurement); mypy unavailable (NEW-984) |

Draft DoD statement (to be signed only by Ish):

> **WP2.1 (Action Gateway): CLOSED WITH ACCEPTED RESIDUALS, 2026-10-__ (Ish to date), closing HEAD `<to be recorded after commit>`.** Every effectful boundary in Codey-OS is either mediated by an authority mechanism (`core/action_gateway.py`; CCOS `CAPABILITY_AUTHORITY`; `restoricon_core` `BUSINESS_MUTATION_AUTHORITY`), or carries a documented bookkeeping / operator-bootstrap / loopback / dormant / read-only disposition in `docs/wp21_census/dispositions.tsv`, or is on the signed accepted-residual list. The register records 28 rows as UNMEDIATED (each with a finding, severity and reach, tracked as OPEN/QUEUE findings, for example NEW-1102, NEW-814, NEW-1095..1099): they are known unmediated boundaries, not mediated ones, and this statement does not claim otherwise. This is not "no destructive call site bypasses the gateway": the shell tool remains an audited ACT opaque-execution surface (F2) that closes named dangerous forms, and only an OS-level boundary (candidate WP, NEW-1069) removes that ceiling. Evidence tiers are listed per item and are not all "live verified"; replay expansion and the Z-5 manual checks are deferred.

## 5. What would be committed (nothing is staged)

Stage exact paths only (never `git add -A`, `commit -a`, stash, reset, checkout, clean, and never the glob `docs/wp21_census/`). Candidate set owned by this closeout, all working-tree today:

- Tracked files modified: `CLAUDE.md` (Ish's rule 8 edit), `CODEY_OS_MASTER_BLUEPRINT.md`, `NEW_ISSUES.md`, `PROJECT_LOG.md`, `LIVE_TEST_QUEUE.md`, `docs/architecture.md`, `docs/commands.md`, `docs/security.md`, `docs/wp21_census/dispositions.tsv`, `docs/wp2_1_census_report_1.md`, `docs/wp2_1_g15z_closure_progress_2026-10-25.md`, `docs/wp2_1_g15z_spec.md`, `tests/test_wp21_census.py`.
- New files: `docs/WP2_1_CLOSING_PACKET_2026-10-27.md`, `docs/HANDOFF_TEMPLATE.md`, `docs/WP2_1_HANDOFF_2026-10-25.md`, `docs/WP2_1_HANDOFF_2026-10-26.md`.
- New directories, staged by these four names only: `docs/wp21_census/review_770dc66/`, `docs/wp21_census/replay_A_770dc66/`, `docs/wp21_census/closing_770dc66/`, and, from `docs/wp21_census/handoff_2026-10-26/`, **only `README.md` and `artifact_manifest.json`, by file name**. `docs/wp21_census/handoff_2026-10-26/checkpoint.tar.gz` (1,666,838 bytes, a binary tarball of scratch checkpoints) is **not staged**: it stays untracked and local, because binary tarballs are excluded from the repo, its content is already represented by the text files plus the hashes in `artifact_manifest.json`, and committing it would put volatile scratch state into history. Unless Ish decides otherwise it must also not be deleted until the coordinator has retained what it needs.
- Never staged: `.claude/` (foreign edits and 77+ memory notes) and the owned CCOS scratch roots `.wp21-closure-ccos-*` in the repo root. The current root `.wp21-closure-ccos-p56u5f68/` contains `config/pulse/cookie` (256 bytes, mode 0600; contents not read). It should be moved out of the repo after retention rather than left untracked in the working tree.

The closeout commit must not change any scanned source: the register keys are tied to `770dc66` source, and editing a scanned file re-keys the register.

## 6. Open questions for Ish, with recommendations

1. **Z-6, G15b-13 / R5 ratification.** Package-spec remainder (pip bare-name / local path / `-r` by precedent; pnpm/yarn conservative only, neither installed) was never decided by Ish as a list (D-1 names only 19, 22, 36). It is PARTIAL with `trigger: Z-6 ratification of R5`. **Recommend ratify**; the row then moves to ACCEPTED_RESIDUAL and the pnpm/yarn tables are re-verified if either is ever installed (rule 12).
2. **G15b-20, Q7(c) contradiction.** `PROJECT_LOG.md` (G15d entry) says Ish answered "Q4/Q5/Q7 accept all (... python -m module allowlist)"; `NEW_ISSUES.md` (NEW-1020/G15b-20 update) says Q7(c) was "not recorded". The reconciliation keeps G15b-20 CLOSED and carries it under R18. **Please state which is true**; recommend recording ratification of the 13-module `python -m` allowlist (side effect: `bench.scorecard`, `timeit`, `cProfile` module forms are HIGH).
3. **R18 carry.** Implemented on the spec default, Ish's answer not recorded: G15d Q1 (lexical rather than realpath for D-3) and Q6 (pnpm/yarn residual), and G15i/G15j Q-A..Q-F. **Recommend** ratifying the spec defaults as one list, or carrying R18 by name in the signed residual list. Already ratified and therefore not R18: G15f Q2, G15g spawn policy, G15h Q-b, D-6/D-7/D-8 (D-8 not confirmed for G15b-04 and G15b-32), the NEW-972/943/944/904/905/913/914/846/753/936 deferrals.
4. **NEW-814, LOW.** Rated LOW/dormant by the coordinator under group-15 scope 2.6 (sole caller of the unguarded `state.py:531` DELETE is `model_registry.prune_adoptions`, called only from tests). **Recommend accept LOW**, OPEN/QUEUE, `trigger: before wiring prune_adoptions`.
5. **NEW-1102, MEDIUM.** Production plugin activation runs `exec_module` with no content integrity check and no `gate_exec`; reach is prod-confirmless (REPL, daemon TaskExecutor, agent, restoricon API route, dashboard). **Recommend keep MEDIUM**, OPEN/QUEUE, trigger next plugin-system work / before accepting third-party plugins; candidate fix is a hash/signature manifest checked before `exec_module`. Escalate to HIGH if a confirm-less write into `ccos/plugins/**` is ever shown to be ACT.
6. **Z-5 manual schedule (R17).** Draft order: T-1..T-3 (attended-terminal `^C` and typeahead checks, one sitting, no model) -> L2-d (real `setup_dr_key.py --force`, needs a key-storage plan) -> L2-a (real cloudflared token, fronts the public API, dev DB copy only) -> L2-b (real bench run, hours, alone on the device) -> T-4 optional (real peers). L2-c is moot while the aigentik/private_agent adapters are `enabled:false`. Entries are now in `LIVE_TEST_QUEUE.md`. **Recommend** closing with these on the residual list rather than blocking closure on them.
7. **Z-6 / Z-7 sign-off.** Sign the R1-R18 list and the DoD text (section 4), or specify changes.
8. **Z-8 group-14 tiers.** Slices 14a (`249b61b`), 14a-ext and 14f and 14g (`96ad7f4`), 14i (`3981457`): code-complete + reviewer-approved + committed, no individual live run. **Recommend accept the reviewer-approved tier** (residuals NEW-975/986/990/991/992/993, NEW-1096 and NEW-1099 are OPEN/QUEUE).
9. **Next work package.** **Recommend WP2.2 (Worlds / Playground isolation)**, with NEW-1069 (OS-level boundary, the F2 ceiling) kept as a separate candidate that is Ish's call, not an automatic roadmap replacement. WP2.2 premise confirmed in the spec: `restoricon_core/database.py` still defaults `DEFAULT_DB_PATH` to `~/.codeyOS/restoricon.db` when `RESTORICON_DB_PATH` is unset.
10. **G15b-34, NEW-1026.** Two sub-claims of the item title are unfixed (audit sink swallows `OSError` by design; optional hash chain). Parked, `trigger: none`. **Recommend** keep parked unless the audit sink is touched again.
11. **Rule 8 revision in `CLAUDE.md`** (fix-when-related, log-with-trigger, frozen-source exception) is already edited in the working tree and is the basis for every trigger tag written this pass. Please confirm it stands and approve it going into the closeout commit.
12. **Commit authorization and review gaps.** The gate test change and the three operator docs were independently reviewed in two rounds (round 2 APPROVED), but only as the coordinator's transcription (`closing_770dc66/GATE_AND_DOCS_REVIEW_RECORD.md`); the reviewer kept no file. Before commit, Ish either accepts that transcription or asks for a retained reviewer file; and Ish decides whether to accept (b) the reconciliation fixes RF-1..3 on the mechanical check rather than a re-approval, and (c) the stale adjudication post-review edits, which were NOT re-reviewed. The final pre-commit review (scratch `FINAL_PRECOMMIT_REVIEW.json`, verdict CHANGES_REQUESTED, whose findings this revision applies) found the register mechanically sound: strict check exit 0, 0 failures, 0 UNKNOWN, 1,467 rows.

## 7. Signatures

Nothing below is signed. Ish signs; no agent signs for Ish.

```
Z-6  Accepted-residual list R1-R18 (with R5 and R18 decisions from section 6):
     [ ] signed as listed   [ ] signed with changes: ______________________
     Ish: ______________________   date: ____________

Z-7  DoD text (section 4) and closure form:
     [ ] WP2.1 CLOSED WITH ACCEPTED RESIDUALS   [ ] NOT closed yet: ____________
     Closing HEAD: <to be recorded after commit>
     Ish: ______________________   date: ____________

Z-8  Group-14 slices 14a, 14a-ext, 14f, 14g, 14i at reviewer-approved tier:
     [ ] accepted   [ ] request live runs for: ____________
     Ish: ______________________   date: ____________

Z-5  Manual deferral schedule (section 6, item 6) and replay expansion deferral:
     [ ] accepted as residual   [ ] required before closure: ____________
     Ish: ______________________   date: ____________

Next WP:  [ ] WP2.2   [ ] other: ____________
     Ish: ______________________   date: ____________
```

## 8. Where the evidence lives (committed vs scratch-only)

- **Committed at `770dc66`:** all production source, the original canonical register (`f405a671...`), the G15b/G15z specs and verification reports up to the freeze.
- **Working tree, uncommitted (this packet's package):** the tracking docs, the installed register, `tests/test_wp21_census.py`, operator docs, `docs/wp21_census/{review_770dc66,replay_A_770dc66,handoff_2026-10-26,closing_770dc66}/`, this packet.
- **Scratch only (volatile, outside the repo; not copied):** the 26.6 MB frozen source archive `frozen_source_770dc66.tar` (and `preflight_7fe60cc.tar`, 26.5 MB) and the 28 MB 1,267-file tree (`frozen_source_770dc66/`, pinned by `frozen_source_manifest.json`, which must stay immutable), the B1 run root `replay_guard_runs/b1-_rr31qb3` and V-A run roots, the 32 `chunk_*.log` and per-chunk `home_*` directories, `census_pre_freeze/`, `reviewer_*_state/`, per-unit work scripts and `.pre_*` histories, the `C*_EVIDENCE_PREP.md` files, `preflight_*` snapshots. The durable copies listed in `closing_770dc66/README.md` are the minimum needed to audit this packet.

## 9. Verification of every hash and count cited here

Recomputed at assembly time by `docs/wp21_census/closing_770dc66/verify_packet.py` (read-only; it extracts every 64-hex string from this packet, the closing-dir README, and the 2026-10-27 additions in PROJECT_LOG, the blueprint and NEW_ISSUES, and matches each against a freshly computed SHA256 of a real file; it then recomputes the counts). Literal output follows. `sha256sum -c SHA256SUMS` in the closing directory: 59 files (every file in the directory except `SHA256SUMS` itself), all OK.

```
packet      06eea7a77da7... OK  docs/wp21_census/closing_770dc66/deferrals/Z5_DEFERRAL_SCHEDULE.md
packet      09198d0b71bc... OK  docs/wp21_census/closing_770dc66/merge/build_summary.json
packet      0ede59cfc3d5... OK  docs/wp21_census/closing_770dc66/b1/B1_SUBSET_RESULT_AUDIT.json
packet      10ea68c558bb... OK  scratch:replay_b1_subset_cases.json
packet      133455401125... OK  docs/commands.md
packet      149f101a4f75... OK  docs/wp21_census/closing_770dc66/g15b49/G15B_49_RECONCILIATION_FINAL.tsv.pre_rereview
packet      1b1d15982fdf... OK  docs/wp21_census/review_770dc66/C7_reviewed_dispositions.tsv
packet      1d6c7bea6990... OK  docs/security.md
packet      280e7687fa3e... OK  docs/wp21_census/closing_770dc66/b1/B1_CITABLE_WORDING.md
packet      2f0e6a644042... OK  docs/wp21_census/closing_770dc66/deferrals/Z8_TIERS.md
packet      4030bdfa4da8... OK  scratch:replay_b1_subset.py
packet      456cadbfe0ca... OK  docs/wp21_census/review_770dc66/C4_FRESH_reviewed_dispositions.tsv
packet      50fa9ba0cac5... OK  docs/wp21_census/closing_770dc66/supplementary/supplementary_dispositions.tsv
packet      5279004783c2... OK  docs/wp21_census/dispositions.tsv
packet      5c0f82d4c4ad... OK  docs/wp21_census/closing_770dc66/g15b49/G15B_49_RECONCILIATION_FINAL.tsv
packet      616ee9b058db... OK  scratch:census_frozen_1/scan.tsv
packet      6aa4c6a43a39... OK  docs/wp21_census/review_770dc66/C3_reviewed_dispositions.tsv
packet      7bbfdaf657ce... OK  docs/wp21_census/closing_770dc66/C5/C5_FRESH3_dispositions.tsv
packet      825fc16b1c06... OK  docs/wp21_census/closing_770dc66/merge/first_seen_provenance.json
packet      82d69cffc9b2... OK  docs/wp21_census/review_770dc66/C1_reviewed_dispositions.tsv
packet      869f8fb9e2a1... OK  docs/wp21_census/review_770dc66/C2_reviewed_dispositions.tsv
packet      8c24d6bb084d... OK  scratch:classification_units/C5_FRESH3_dispositions.tsv.pre_round2_corrections
packet      8c65742280a7... OK  docs/wp21_census/closing_770dc66/C6/C6_FRESH_REVIEW_INDEPENDENT.json
packet      954109772f66... OK  docs/wp21_census/closing_770dc66/C5/C5_FRESH3_REVIEW_INDEPENDENT.json
packet      97bf7a16b25b... OK  docs/wp21_census/closing_770dc66/g15b49/G15B_49_RECONCILIATION_FINAL.md
packet      a0a8cd1397ad... OK  scratch:frozen_source_manifest.json
packet      a644d8d176a1... OK  scratch:replay_va.py
packet      ab11face1419... OK  docs/wp21_census/closing_770dc66/g15b49/G15B_49_RECONCILIATION_REREVIEW.json
packet      ad92819b8312... OK  docs/wp21_census/closing_770dc66/supplementary/SUPPLEMENTARY_REVIEW.json
packet      b2aa8b12e8af... OK  docs/wp21_census/closing_770dc66/C6/C6_FRESH_dispositions.tsv.pre_reseal
packet      b5134f0b54f1... OK  docs/wp21_census/closing_770dc66/merge/stale_register_adjudication.json
packet      cf88c29358ad... OK  docs/wp21_census/closing_770dc66/g15b49/G15B_49_RECONCILIATION_FINAL.json
packet      d61a5afb88ce... OK  docs/wp21_census/closing_770dc66/C6/C6_FRESH_dispositions.tsv
packet      e07fbd0f3711... OK  docs/architecture.md
packet      f405a6715247... OK  git HEAD:docs/wp21_census/dispositions.tsv
packet      f4143ee83258... OK  docs/wp21_census/review_770dc66/stale_register_adjudication.json
packet      f6440e9fed33... OK  docs/wp21_census/closing_770dc66/tests_gate/summary.txt
packet      f68aa877fa92... OK  scratch:replay_guard.py
packet      f6f704e43fb5... OK  docs/wp21_census/closing_770dc66/merge/stale_reconciliation_REVIEW.json
packet      ff95fbcdeaf8... OK  tests/test_wp21_census.py
README      5279004783c2... OK  docs/wp21_census/dispositions.tsv
PROJECT_LOG 5279004783c2... OK  docs/wp21_census/dispositions.tsv
blueprint   5279004783c2... OK  docs/wp21_census/dispositions.tsv
blueprint   5c0f82d4c4ad... OK  docs/wp21_census/closing_770dc66/g15b49/G15B_49_RECONCILIATION_FINAL.tsv
NEW_ISSUES  5c0f82d4c4ad... OK  docs/wp21_census/closing_770dc66/g15b49/G15B_49_RECONCILIATION_FINAL.tsv
FULL-HASH MISMATCHES: 0
register rows 1467 header ['key', 'class', 'mediator', 'evidence', 'reach', 'severity', 'finding', 'decided_by', 'reviewed_by', 'first_seen_rev', 'count']
class {'OPERATOR_BOOTSTRAP': 223, 'OPERATOR_SCRIPT_RUNNABLE': 149, 'UNMEDIATED': 28, 'BOOKKEEPING': 242, 'GATED': 122, 'DORMANT': 33, 'FALSE_POSITIVE': 88, 'READ_NOEFFECT': 22, 'NATIVE_AUTHORITY': 537, 'LOOPBACK_IPC': 23} UNKNOWN 0
reviewed_by populated 961
UNMEDIATED rows 28
G15b cat {'CLOSED_CODE_REVIEW': 28, 'PARTIAL': 12, 'ACCEPTED_RESIDUAL': 3, 'OPEN': 6} sev {'HIGH': 32, 'MEDIUM': 10, 'LOW': 7} non-closed 21
exactly-one trigger literal per non-closed row: True
raw chunks: passed 9299 failed 13 skipped 2 subtests 19 | chunk29 foreground rerun: 264 passed in 67.11s (0:01:07)
effective passed 9303 = raw 9299 - chunk29 raw 260 + foreground rerun 264 ; effective failed 9
effective failing nodes 9 subset of 10 baseline: True | baseline node not failing this run: ['tests/test_task_executor_telemetry.py::test_orphaned_thread_never_corrupts_concurrent_tasks_stats']
failed nodes now 13 lines incl. chunk-29/chunk-6; base_ids 10
build_summary rows 1467 unknown 0 {'OPERATOR_BOOTSTRAP': 223, 'OPERATOR_SCRIPT_RUNNABLE': 149, 'UNMEDIATED': 28, 'BOOKKEEPING': 242, 'GATED': 122, 'DORMANT': 33, 'FALSE_POSITIVE': 88, 'READ_NOEFFECT': 22, 'NATIVE_AUTHORITY': 537, 'LOOPBACK_IPC': 23}
census runs identical: True
HEAD vs origin/main: ['770dc6639e4100ea3215fca07d923769a8290078', '770dc6639e4100ea3215fca07d923769a8290078']
```

Reading the output: "effective passed 9303" is the raw 9,299 with chunk 29's 260 passes replaced by the 264 passes of its foreground rerun (the 4 chunk-29 failures are the NEW-1104 `nohup` artifact). The "1,433 UNKNOWN / 38 failures" figures belong to the original register and are not re-computed here; the installed register shows 0 UNKNOWN. The 8-hex prefixes quoted in ledger prose (for example `7bbfdaf6...`) are prefixes of full hashes in section 3 and were checked by eye against them, not by the script.


## 10. Ish's decision record (2026-10-28)

Ish's instruction (verbatim): "move it out of the repo if thats whats recommended by you. and for your 12 questions do what you recommend and what ever gets us to really completing WP2.1 and being able to move on to the next part of our project".

Recorded by the coordinator as Ish's delegated decision: every section-6 question is resolved **as recommended**, and WP2.1 is **CLOSED WITH ACCEPTED RESIDUALS** (form Z-7). The section-7 signature lines were not filled in by an agent; this section is the sign-off of record. Specifics:

- Q1 R5 ratified (G15b-13 -> ACCEPTED_RESIDUAL; pnpm/yarn tables re-verified if either is ever installed). Q2 13-module `python -m` allowlist ratified; the factual contradiction between PROJECT_LOG and NEW_ISSUES about what Ish answered at Q7(c) remains unresolved in the record, and the ratification is by this delegation, not Ish's recollection. Q3 G15d Q1/Q6 and G15i/G15j Q-A..Q-F ratified at spec defaults. Q4 NEW-814 LOW. Q5 NEW-1102 MEDIUM (escalate to HIGH on a shown confirm-less write into `ccos/plugins/**`). Q6 Z-5 manual schedule and replay-expansion deferral accepted as residual, not blocking. Q7 R1-R18 and DoD text accepted as written. Q8 group-14 slices accepted at reviewer-approved tier. Q9 next WP = WP2.2 (NEW-1069 stays a separate candidate). Q10 NEW-1026 stays parked. Q11 rule 8 stands. Q12 the gate-review transcription and unreviewed edits (RF-1..3, stale adjudication edits, C6 reseal) accepted as known gaps.
- Not changed by closure: live-verified status (none beyond disposable fixtures), the deferred replays, the 9 baseline test failures, ruff 190 vs 179, mypy unavailable (NEW-984).
- Housekeeping: `.wp21-closure-ccos-p56u5f68/` moved out of the repo to scratch (contents unread). `checkpoint.tar.gz` stays local and untracked.
