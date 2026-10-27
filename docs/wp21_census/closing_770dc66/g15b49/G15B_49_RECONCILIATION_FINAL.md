# G15b 49-item reconciliation, FINAL DRAFT (scratch; not signed; Z-6/Z-7 remain Ish's)

Generated 2026-10-27T14:09:22Z against frozen HEAD `770dc6639e4100ea3215fca07d923769a8290078`. Read-only. No product execution, model, network or repo edit. Companion files: `G15B_49_RECONCILIATION_FINAL.tsv/.json`, `Z5_DEFERRAL_SCHEDULE.md`, `Z8_TIERS.md`. The candidate files are untouched.

## 1. Result

| category | candidate | final |
|---|---:|---:|
| CLOSED_CODE_REVIEW | 29 | 28 |
| ACCEPTED_RESIDUAL | 4 | 3 |
| PARTIAL | 10 | 12 |
| OPEN | 6 | 6 |
| total | 49 | 49 |

Severity unchanged: HIGH 32 / MEDIUM 10 / LOW 7 (G15b-12 HIGH->MEDIUM by rule 6, NEW-1021; nothing else rerated). **Two category changes: G15b-13 ACCEPTED_RESIDUAL -> PARTIAL (section 4) and G15b-34 CLOSED -> PARTIAL (independent review R-1, rule 6: the title names unfixed sub-claims).** Final counts 28 / 3 / 12 / 6. **Of the 32 HIGH rows, two rest on ambiguity ratings whose D-8 confirmation is NOT recorded: G15b-04 and G15b-32** (`severity_note` = "HIGH (amb; D-8 unconfirmed)"; D-8 for 07/31/35/37 is confirmed). Category rule used: ACCEPTED_RESIDUAL only when every remainder is an Ish decision, otherwise PARTIAL; CLOSED only when no unfixed sub-claim of the item title remains. No item was upgraded. Nothing here is "verified": the strongest tier any item holds is `live-verified on a disposable fixture` (G15b-12, G15b-25), `live-STYLE pty` (21, 27, 37, 46) or `V-A replay-recorded` (items in section 3).

### Tier vocabulary used in the per-item columns (CLAUDE.md rule 7; never collapsed)

- **code-complete + reviewer-approved**: the commit(s) in `commits`, no live run unless stated.
- **independently re-probed at b230ce9**: G15z S1, recording fakes, disposable fixtures, NOT live, and it PRE-DATES the S2 fixes (84c7bfd) and 770dc66.
- **live-STYLE**: S1b Python `pty.fork`, disposable env; NOT the attended Termux terminal.
- **live-verified (disposable fixture)**: real process on this phone, fixture not the real service/token.
- **V-A replay-recorded at 770dc66**: independently APPROVED adapted replay (approval basis: REVIEW_VA_RESULT.md final R1 re-review; VA_REPLAY_RESULT.md is the superseded result text), recorder-only (every primitive attempt recorded and refused, nothing executed): 269 case files, 267 matched controls, 301 events, 0 FAIL/0 INCONCLUSIVE; 74 of the 267 original IDs unselected; proves classification/refusal on those argv, not execution semantics.
- **B1 bridge, owned-fixture replay**: citable wording (B1_CITABLE_WORDING.md, from B1_SUBSET_RESULT_AUDIT.json, verdict CHANGES_REQUESTED on wording only; raw execution evidence consistent): "16 mapped historical references re-executed once on fabricated owned fixtures, under reviewed adapter 4030bdfa... and data 10ea68c5..., against frozen 770dc66 (1267-file manifest). 15 selected operations passed their oracles; N17 passed only a read-only partial subcase. Process and network primitives were recorded and refused: 2 events. No real TTY, live state, or real credentials." Tier: owned-fixture replay; not live-verified; not full coverage. MAY NOT be cited as: 16/16 PASS, all of B1/B2, protected-path coverage for HM-01/03/08/11, refused-before-read for FT12, N17 as the no-existence-oracle claim.
- **deferred**: replay expansion (B1 HIGH matrix 31 cases, S1b at final HEAD, remaining B/C1/C2/C3) is OUT of WP2.1 closure by Ish 2026-10-27, to a later WP that has no name or number yet.

### Trigger convention (CLAUDE.md rule 8 as revised 2026-10-27)

Quoted: "**Frozen-source exception:** while a census/freeze is in force (e.g. WP2.1 at `770dc66`), source cannot be changed, so every finding is logged with a trigger tag and no fix is made." Consequence: `trigger_class` is `trigger` or `parked` for every non-closed row; `fix-now` is unavailable while the freeze holds. Each non-closed row carries exactly one tag of the form `trigger: <named WP/event>` or `trigger: none` (= parked); caveats (for example an unsigned WP2.2) are in `trigger_note`/notes, not the tag. "Blueprint pointer line still needed" is a TODO for the coordinator (section 6); this task is scratch-only.

**File format warning:** the `.tsv` is RFC-4180-style (`csv.QUOTE_MINIMAL`, tab-normalised fields, doubled quotes). Parse it with `csv.DictReader(delimiter=chr(9))`, NOT literal tab splitting. The candidate TSV used `QUOTE_NONE`; this one does not.

## 2. Method and limits (stated, not hidden)

- Sources: `docs/wp2_1_g15b_consolidated.md` (sha256 `5e0173bb...`, identical at HEAD and in the working tree; matches the candidate's `consolidated_sha256`), sections 3, 9, 10-10g; `NEW_ISSUES.md`, `PROJECT_LOG.md`, `docs/wp2_1_g15z_spec.md` and the handoff; verify-A/B/C/C2/C3 and S1b TSVs; `docs/wp21_census/replay_A_770dc66/` (V-A rows read from `va-results.json` + `replay_va_cases.json`); scratch B1 result and `B_REPLAY_COVERAGE_LEDGER`; `final_tests/chunk_*.log`; `LIVE_TEST_QUEUE.md`; `docs/wp2_1_group14_scope.md`.
- **Provisional-text caveat:** the working-tree `NEW_ISSUES.md`, `PROJECT_LOG.md`, blueprint and `docs/wp2_1_g15z_spec.md` carry UNCOMMITTED, unreviewed edits (and `tests/test_wp21_census.py`, `CLAUDE.md`, `docs/wp2_1_census_report_1.md` are also modified; `git status --short` snapshot saved as `g15b_final_work/git_status_snapshot.txt`, 109 lines). Item statuses here rest on the CONSOLIDATED doc (unchanged at HEAD) and on NEW_ISSUES updates that exist in the `770dc66` blob; the uncommitted additions I read are NEW-1095..1099 and 2026-10-25/26 continuation notes, none of which changes a G15b category. I read all of the uncommitted PROJECT_LOG additions (42 lines, continuation notes only) and all NEW_ISSUES additions visible at the end of the task (NEW-1095..1103 plus update notes). The tree is being edited by a concurrent session (the added NEW_ISSUES block grew from 86 lines to NEW-1103 while I worked, and the census gate test changed), so everything uncommitted is PROVISIONAL: NEW-1099/1100 (dormant optimizer/recombiner defects), NEW-1102 (plugin exec_module, MEDIUM, relevant to the G15b-25 residual) and NEW-1103 (census gate) are cited only as provisional pointers. Working-tree sha256 values are in the JSON `meta`.
- Source and tests were read from `git archive 770dc66` (scratch `g15b_final_work/head/`) and `git grep ... 770dc66`, not the working tree. Test names were located by literal-form proximity; each cited node name was machine-checked to exist at HEAD. **Where no test was located the row says so** (G15b-02 crontab/at/killall, 03 gcloud/aws/rclone family, 04 am/cmd/pm/settings/svc/input, 23, 39-42, 44, 49-failing test only).
- Per-item S1 counts are NOT published: a regex over the TSV `maps_to_finding` column misattributes rows that cite lists/ranges (for example `G15b-04..08, 21, 22`, which put a G15b-21 stop-script FAIL on G15b-04). FAIL rows were mapped by hand (section 5). V-A counts use the case file's own mapping text and are references, not unique cases (a reference can map to two items).
- The frozen suite is 9,294 passed / 10 recorded baseline failures / 2 skipped (handoff section 5). None of the closed items is claimed on the strength of that total; it only shows the cited tests are not among the 10 failures except G15b-49's own.

## 3. Per-item ledger (49 rows; full text in the TSV/JSON)

| id | sev | candidate | FINAL | evidence_tier (rule 7, single) | commits | tracking NEW | trigger_class / trigger |
|---|---|---|---|---|---|---|---|
| G15b-01 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c] | e167e0c | 933,1006 | - |
| G15b-02 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c] | e167e0c | 1006 | - |
| G15b-03 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c; 890d4b9 (npm part)] | e167e0c; 890d4b9 (npm part) | 1006,932,1036 | - |
| G15b-04 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c] | e167e0c | 1006 | - |
| G15b-05 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c] | e167e0c | 904,1006 | - |
| G15b-06 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9] | 890d4b9 | 1022 | - |
| G15b-07 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c; 890d4b9; c842d97] | e167e0c; 890d4b9; c842d97 | 1022,1006,1051 | - |
| G15b-08 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9 (G01/G02/G05); c842d97 (G11-G13, nested/case .git)] | 890d4b9 (G01/G02/G05); c842d97 (G11-G13, nested/case .git) | 1022 | - |
| G15b-09 | HIGH | PARTIAL | **PARTIAL** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9; c842d97] | 890d4b9; c842d97 | 1019,1037 | trigger: trigger: NEW-1069 OS-boundary candidate WP (NEW-1069 is an UNSCHEDULED candidate WP (D-10 log), so this is effectively parked; only the OS-boundary WP removes the condition.) |
| G15b-10 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9; 84c7bfd] | 890d4b9; 84c7bfd | 1020,1079,1044 | - |
| G15b-11 | HIGH | PARTIAL | **PARTIAL** | reviewer-approved [committed e9f593f (bench child); f4353cf (cloudflared child, plugin audit); no live run; replay deferred] | e9f593f (bench child); f4353cf (cloudflared child, plugin audit) | 1020,1053,1054 | trigger: trigger: D-2(c) env-scrub work |
| G15b-12 | MEDIUM | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | live-verified [DISPOSABLE fixture only; real token / real spawn deferred] | f4353cf | 1021 | - |
| G15b-13 | HIGH | ACCEPTED_RESIDUAL | **PARTIAL (CHANGED)** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c; 890d4b9] | e167e0c; 890d4b9 | 1023,1036,1044 | trigger: trigger: Z-6 ratification of R5 |
| G15b-14 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9 (G15d Unit B)] | 890d4b9 (G15d Unit B) | 1023,1036 | - |
| G15b-15 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9] | 890d4b9 | 1023,1036 | - |
| G15b-16 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9] | 890d4b9 | 1023,1040 | - |
| G15b-17 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c] | e167e0c | 1007 | - |
| G15b-18 | LOW | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c] | e167e0c | 1007 | - |
| G15b-19 | HIGH | ACCEPTED_RESIDUAL | **ACCEPTED_RESIDUAL** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only; accepted-residual attempts recorded/refused, not execution success; accepted by Ish D-1] | none (decision); ceiling statement on the register | 904,1028 | trigger: trigger: NEW-1069 OS-boundary candidate WP (NEW-1069 is an unscheduled candidate WP: effectively parked.) |
| G15b-20 | MEDIUM | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9] | 890d4b9 | 1028 | - |
| G15b-21 | HIGH | PARTIAL | **PARTIAL** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; also live-STYLE S1b pty at b230ce9 (pre-S2, not the attended terminal); over reviewer-approved, committed e167e0c; c842d97; 781542a] | e167e0c; c842d97; 781542a | 1028,1070,1071 | trigger: trigger: L2-d first real setup_dr_key.py run (NEW-1070 siblings (migrate/backfill --apply, api.server --host 0.0.0.0) are parked.) |
| G15b-22 | HIGH | ACCEPTED_RESIDUAL | **ACCEPTED_RESIDUAL** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only; accepted-residual attempts recorded/refused, not execution success; accepted by Ish D-1] | c842d97 (narrowing); none for the residual | 1028 | trigger: trigger: NEW-1069 OS-boundary candidate WP (NEW-1069 is an unscheduled candidate WP: effectively parked.) |
| G15b-23 | LOW | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | reviewer-approved [committed 890d4b9; no live run; replay deferred] | 890d4b9 | 1019 | - |
| G15b-24 | LOW | PARTIAL | **PARTIAL** | reviewer-approved [committed 890d4b9; no live run; replay deferred] | 890d4b9 | 1023,1044 | parked: trigger: none (re-verify if ruby/perl are installed (rule 12).) |
| G15b-25 | HIGH | PARTIAL | **PARTIAL** | live-verified [DISPOSABLE fixture only; real token / real spawn deferred] | e9f593f; f4353cf; c842d97; 84c7bfd; 770dc66 | 1024,1052,1053,1054,1081 | trigger: trigger: adapter repair / re-enable of private_agent or aigentik (L2-c) |
| G15b-26 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | reviewer-approved [committed c842d97; no live run; replay deferred] | c842d97 | 1024 | - |
| G15b-27 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; also live-STYLE S1b pty at b230ce9 (pre-S2, not the attended terminal); over reviewer-approved, committed c842d97; 781542a] | c842d97; 781542a | 1024,1049 | - |
| G15b-28 | HIGH | PARTIAL | **PARTIAL** | reviewer-approved [committed c842d97; no live run; replay deferred] | c842d97 | 1024,1016,1051 | parked: trigger: none |
| G15b-29 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | reviewer-approved [committed c842d97; 623e4c7; 84c7bfd; no live run; replay deferred] | c842d97; 623e4c7; 84c7bfd | 1025,1067,1082 | - |
| G15b-30 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | reviewer-approved [committed 623e4c7; 84c7bfd; no live run; replay deferred] | 623e4c7; 84c7bfd | 1008,1025,1046,1067,1082 | - |
| G15b-31 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | reviewer-approved [committed e9f593f; no live run; replay deferred] | e9f593f | 1025,1045 | - |
| G15b-32 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | reviewer-approved [committed e9f593f; no live run; replay deferred] | e9f593f | 1025,1047 | - |
| G15b-33 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | reviewer-approved [committed c842d97; B1 owned-fixture replay on fabricated fixtures, audit CHANGES_REQUESTED on wording only, not live, not full coverage, no HM-* protected-path coverage; S1 re-probe PRE-S2] | c842d97 | 1026,1088 | - |
| G15b-34 | HIGH | CLOSED_CODE_REVIEW | **PARTIAL (CHANGED)** | reviewer-approved [committed c842d97; B1 owned-fixture replay on fabricated fixtures, audit CHANGES_REQUESTED on wording only, not live, not full coverage, no HM-* protected-path coverage; S1 re-probe PRE-S2] | c842d97 | 1026 | parked: trigger: none (parked; two unfixed sub-claims, NEW-1026 append needed.) |
| G15b-35 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | reviewer-approved [committed c842d97; no live run; replay deferred] | c842d97 | 1026,894,1051,1087 | - |
| G15b-36 | HIGH | ACCEPTED_RESIDUAL | **ACCEPTED_RESIDUAL** | deferred [decision only; no code] | none (decision) | 975,986 | trigger: trigger: NEW-1069 OS-boundary candidate WP (NEW-1069 is an unscheduled candidate WP: effectively parked.) |
| G15b-37 | HIGH | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | reviewer-approved [committed 781542a/84c7bfd; live-STYLE S1b pty at b230ce9 PRE-dates S2-D flush; B1 owned-fixture replay, not live, not full coverage] | 781542a; 84c7bfd | 1027,1074,1075,1078 | - |
| G15b-38 | MEDIUM | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | reviewer-approved [committed c842d97; B1 owned-fixture replay on fabricated fixtures, audit CHANGES_REQUESTED on wording only, not live, not full coverage, no HM-* protected-path coverage; S1 re-probe PRE-S2] | c842d97 | 1031,1048 | - |
| G15b-39 | MEDIUM | OPEN | **OPEN** | deferred [no fix; queued; still reproduces at b230ce9 or by source read] | none | 1032 | parked: trigger: none (parked) |
| G15b-40 | MEDIUM | OPEN | **OPEN** | deferred [no fix; queued; still reproduces at b230ce9 or by source read] | none (c842d97 side effect) | 1032,846,1088 | parked: trigger: none (parked; content trust is R14.) |
| G15b-41 | LOW | OPEN | **OPEN** | deferred [no fix; queued; still reproduces at b230ce9 or by source read] | none | 1031 | parked: trigger: none (parked) |
| G15b-42 | LOW | OPEN | **OPEN** | deferred [no fix; queued; still reproduces at 770dc66 (V-A import effect / frozen suite)] | none | 855,1011 | parked: trigger: none (WP2.2 recommended but unsigned; NEW-1011 has no blueprint pointer.) |
| G15b-43 | MEDIUM | PARTIAL | **PARTIAL** | reviewer-approved [committed e9f593f; 84c7bfd; no live run; replay deferred] | e9f593f; 84c7bfd | 1034,1086,1091,1093 | trigger: trigger: before wiring a production caller of the CCOS executors (NEW-1086 gets its own trigger on the next capability_registry change.) |
| G15b-44 | MEDIUM | OPEN | **OPEN** | deferred [no fix; queued; still reproduces at b230ce9 or by source read] | none | 1029 | trigger: trigger: next change to daemon IPC auth (rule-4 reviewer required for any fix.) |
| G15b-45 | LOW | PARTIAL | **PARTIAL** | reviewer-approved [committed 890d4b9; no live run; replay deferred] | 890d4b9 | 1029,1089 | trigger: trigger: before wiring is_interactive_environment() into a production caller (also NEW-1089 headless peer skip-vs-park follow-up.) |
| G15b-46 | MEDIUM | PARTIAL | **PARTIAL** | reviewer-approved [committed 890d4b9/84c7bfd; live-STYLE S1b typeahead case FAILED, fixed, not re-run live] | 890d4b9; 84c7bfd | 1030,1041,1083,1084,1089 | trigger: trigger: Z-5 attended-terminal check T-2 |
| G15b-47 | MEDIUM | PARTIAL | **PARTIAL** | reviewer-approved [committed 781542a; no live run; replay deferred] | 781542a | 1029,1076,1077 | parked: trigger: none (parked pending Z-6 signature of the residual list.) |
| G15b-48 | MEDIUM | CLOSED_CODE_REVIEW | **CLOSED_CODE_REVIEW** | reviewer-approved [committed f4353cf; 84c7bfd; no live run; replay deferred] | f4353cf; 84c7bfd | 1033,1055,1056,1057,1058,1060,1066,1080 | - |
| G15b-49 | LOW | OPEN | **OPEN** | deferred [no fix; queued; still reproduces at 770dc66 (V-A import effect / frozen suite)] | none | 1035,1043,1064,1065 | parked: trigger: none (parked) |

### 3.1 Evidence tiers, per item

**G15b-01 `bash/sh -c` flag/spacing variants (NEW-933)** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c]
- review: code-complete + reviewer-approved (G15c: rounds 1-2 CHANGES REQUESTED, round 3 APPROVED)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 11 refs, 11 product refusals incl. bash/sh -c cluster variants)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_shell_wrapper_boundaries.py::test_opaque_shell_dispatch_is_high; test_shell_g15c_allowlist.py::test_bundled_inline_code_forms_are_high (located by literal -xc/-lc/-ec proximity; no test named for the 'extra spacing' variant was located)
- residual: -
- note: NEW-933 body still reads 'not fixed' at HEAD; the closing evidence is in NEW-1007's G15b/G15c update and consolidated 10.

**G15b-02 named dangerous binaries at ACT (kill family, su, gh verbs, crontab, at)** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c]
- review: code-complete + reviewer-approved
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 17 refs, 17 product refusals)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_shell_g15c_allowlist.py::test_non_allowlisted_and_escape_forms_are_high (literal pkill adjacent); ::test_remote_fetch_and_run_forms_are_high (su, gh, pkill adjacent). NO dedicated test located for crontab, at, killall; coverage there is the default-deny mechanism only
- residual: -

**G15b-03 credentialed egress/publish binaries (gcloud, gsutil, bq, aws, rclone, cloudflared, socat, openssl, ssh-copy-id, mail*, npm/cargo publish, DNS/ICMP, xdg-open)** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c; 890d4b9 (npm part)]
- review: code-complete + reviewer-approved (npm half REOPENED by rule-6 correction NEW-1036 at e167e0c, re-closed by G15d Unit B)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 15 refs, 15 product refusals)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_shell_g15c_allowlist.py::test_publishing_and_remote_initializer_forms_are_high; test_shell_g15d_unit_b.py npm exact allowlist tests. NO dedicated test located for gcloud/gsutil/bq/aws/rclone/socat/openssl forms (default-deny mechanism)
- residual: -
- note: 'other forms not re-probed' after the npm reopening (consolidated 10).

**G15b-04 device actions outside `termux-*` (am, cmd, pm, settings, svc, input)** [HIGH HIGH (amb; D-8 unconfirmed), CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c]
- review: code-complete + reviewer-approved (rated HIGH by ambiguity; D-8 for 04 is NOT confirmed: the 2026-10-25 closure-decision text at 770dc66 reads 'remaining D-8 HIGH ratings (07/31/35;37 already approved)' and does not name 04; consolidated 516-517 list 04 and say '04 is CLOSED regardless'). Mechanism: default-deny classifier (no dedicated test for am/cmd/pm/settings/svc/input)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 8 refs, 8 product refusals)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: NO dedicated test located for am/cmd/pm/settings/svc/input literal forms (literal search found none); the V-A replay (8 refusals) is the only form-specific evidence, covered only by the default-deny mechanism in code
- residual: -
- note: Weak on dedicated unit tests; V-A replay-recorded is the strongest evidence.

**G15b-05 unknown wrappers/dispatchers and inline-code interpreters (proot, setpriv, prlimit, socat, less, su, `python3 -c`, `node -e`, `make --eval`, tar checkpoint-action)** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c]
- review: code-complete + reviewer-approved
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 23 refs, 23 product refusals)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_shell_wrapper_boundaries.py::test_inline_interpreter_dispatch_is_high, ::test_privilege_wrappers_require_confirmation; test_shell_g15c_allowlist.py::test_bundled_inline_code_forms_are_high
- residual: NEW-904 open-ended wrapper-tail ceiling (script-file/-m ceiling, see G15b-19); NEW-904/905/913/914 deferrals RATIFIED by Ish 2026-10-24 second block
- note: Closed for the enumerated forms; the open-ended tail is the accepted ceiling of G15b-19.

**G15b-06 ALLOWED text tools as dispatchers/writers (sed `e`/`w`/`-i`, awk `system()`/redirect, sort `-o`/`--compress-program`, uniq/tree outputs, find `-fprint`)** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9]
- review: code-complete + reviewer-approved (G15d Unit A; reviewer C1 found sed --sandbox ordering, fixed; 3072-form differential vs real sed 4.10: 0 bypass)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 39 refs (mapping text includes '07 (+06)' rows), 39 product refusals)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_shell_g15d_unit_a.py::test_sed_sandbox_before_expression_is_act, ::test_sed_expression_before_sandbox_is_high, ::test_sed_refusals, ::test_walker_fails_closed
- residual: -
- note: Candidate OPEN-at-G15c column in the TSV is stale; closed by G15d Unit A.

**G15b-07 silent writes to protected targets via ALLOWED tools (sed -i, ln -sf, sort -o; cp/mv/rm only prompt)** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c; 890d4b9; c842d97]
- review: code-complete + reviewer-approved (HIGH by ambiguity; D-8 HIGH rating CONFIRMED by Ish 2026-10-25 (NEW_ISSUES 'Update 2026-10-25 (closure decisions)' at 770dc66: 'remaining D-8 HIGH ratings (07/31/35;37 already approved)'; PROJECT_LOG 2026-10-25: 'D-8 remaining HIGH ratings'))
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A + verify-B1)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 61 refs, 61 product refusals)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_shell_g15e_protected_scan.py::test_ln_plants_are_caught_on_link_name_and_target, ::test_shell_refuses_protected_mutation_confirm_less, ::test_alias_and_case_and_tilde_forms, ::test_operand_forms_found_without_positional_parsing
- residual: NEW-1051: hard links (os.link unavailable here), /dev/fd/N, opaque execution F2, rm -rf of a dir containing a nested .git
- note: Closed for argv-visible forms only (spec 3.2 wording).

**G15b-08 git-metadata scan gaps (script-embedded writes, sibling-repo hooks, `~/.gitconfig`, `~/.config/git/config`)** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9 (G01/G02/G05); c842d97 (G11-G13, nested/case .git)]
- review: code-complete + reviewer-approved
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 9 refs, 9 product refusals)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_filesystem_git_metadata.py::test_write_denied_under_git_metadata, ::test_append_denied_under_git_metadata (workspace .git/config and hooks only); ~/.gitconfig and ~/.config/git/config: test_filesystem_protected_paths.py::test_deny_tier_refused_with_rule_and_no_side_effect (row .gitconfig, home-git), test_file_tools_protected_classification.py::test_deny_entries_classify_high_defense_in_depth; test_shell_g15e_protected_scan.py::test_mutators_hit_every_rule_class (home-git)
- residual: NEW-1051 (8): Unicode-ignorable .git aliasing, .gitmodules/.gitattributes not matched

**G15b-09 basename-only classification: symlink/copy/spoofed argv[0] two-step** [HIGH, PARTIAL]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9; c842d97]
- review: code-complete + reviewer-approved (NARROWED, NOT CLOSED, consolidated 10/10b)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A + verify-B1)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 9 refs, 9 product refusals; V-A also exercises the D-3 argv[0] and PATH-shadow rows)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: test_shell_g15d_unit_a.py::test_d3_slash_argv0_outside_system_dirs_is_high, ::test_d3_two_step_symlink_attack_is_refused_at_second_step, ::test_d3_system_dir_and_bare_names_keep_their_class
- residual: system bin dirs and PATH dirs are agent-uid-writable; classification stays basename-keyed; pip install / npm -g / pkg write with no operand; /system/bin unlistable; repo root stays on PATH (decided friction, NEW-1050)

**G15b-10 secret reads as READ (cat ssh key/.netrc/.git-credentials, printenv, env, grep -r token, /proc/N/cmdline), also in daemon** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9; 84c7bfd]
- review: code-complete + reviewer-approved (closed for classifier/daemon scope under D-2 option (b); S2-A casefold fix NEW-1079 at 84c7bfd)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live): 2 FAIL (NV33, EV03 case-variant SSH path) PRE-fix (10f)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 18 refs, 18 product refusals; NV33/EV03 now product-refused with 0 events; 8 S2 casefold cases S2CF01-08 all refused; NV30 invalid and NV32 superseded explicitly UNRUN)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_shell_s2a_credential_casefold.py::test_casefolded_credential_operands_are_refused, ::test_ancestor_rule_casefolds, ::test_symlink_resolved_form_casefolds, ::test_existing_basename_secret_names_casefold; test_shell_g15d_unit_a.py::test_credential_paths_refused_through_shell, ::test_credential_paths_refused_through_daemon
- residual: D-2 option (c) environment scrubbing for children is NOT done (deferred; tracked under G15b-11); basename-pattern secrets (.env, *.pem) caught by direct operand only (NEW-1044)
- note: Scope is explicitly the classifier/daemon READ scan; the ambient-env half lives in G15b-11.

**G15b-11 ambient environment inherited by every child (shell, plugin Popen, bench agent)** [HIGH, PARTIAL]
- evidence_tier: reviewer-approved [committed e9f593f (bench child); f4353cf (cloudflared child, plugin audit); no live run; replay deferred]
- review: code-complete + reviewer-approved for narrowed pieces (bench child 10a; cloudflared child 10c); shell and plugin children still inherit all
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-C1: ACCEPTED-RESIDUAL)
- live: no live run
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: test_bench_integrity_grader.py::test_grader_env_allowlist, ::test_bench_child_env_pure; test_g15h_cloudflared_env_delivery.py::test_provider_builds_env_copy
- residual: shell and plugin children inherit-all env; D-2 option (c) deferred; other services keep operator-exported token names (G15h Q-b = no, RATIFIED by Ish 2026-10-24 second block)

**G15b-12 cloudflared tunnel token in argv (readable via `cat /proc/<pid>/cmdline`, daemon-allowlisted)** [MEDIUM, CLOSED_CODE_REVIEW]
- evidence_tier: live-verified [DISPOSABLE fixture only; real token / real spawn deferred]
- review: code-complete + reviewer-approved
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-C1)
- live: live-verified on a DISPOSABLE chain only (stub cloudflared: before 3 cmdline hits, after 0; real cloudflared 2026.10.1 with a malformed fabricated token, no network contact). Real token NOT run by any agent.
- replay @770dc66: V-A has 1 ref (mapping text 'G15b-10/12') product-refused; the tunnel start itself is not replayable; replay expansion deferred (Ish 2026-10-27)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_g15h_cloudflared_env_delivery.py::test_profile_argv_has_no_token, ::test_provider_ignores_argv_entirely, ::test_provider_builds_env_copy, ::test_selector_table_is_exactly_cloudflared; test_service_public_lifecycle.py
- residual: real-token tunnel start is an Ish-attended manual step (L2-a); fix removes a side channel, not a boundary (same-uid can decrypt via age.key)
- note: Severity corrected HIGH -> MEDIUM by rule 6 (NEW-1021 update, G15h Unit A); the only explicit severity change in the 49.

**G15b-13 package-spec fetch forms (npm/pnpm/yarn add\|install\|link of git/URL spec, requirements-file index/URL lines; pip bare-name, local path, `-r` by precedent)** [HIGH, PARTIAL]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c; 890d4b9]
- review: code-complete + reviewer-approved for the URL/VCS-spec half (G15d Unit B)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 3 refs refused, 3 accepted-residual attempts recorded/refused by harness, 1 positive attempt control)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: test_shell_g15d_unit_b.py::test_pip_high_rows, ::test_pip_act_rows, ::test_pip_operand_shape_regexes, ::test_pnpm_yarn_act_rows
- residual: bare-name / local-path / -r pip forms and pnpm/yarn (not installed, conservative only) remain ACT/conservative; NO Ish decision recorded for this remainder
- note: CATEGORY CHANGED vs candidate (ACCEPTED_RESIDUAL -> PARTIAL). D-1 (consolidated line 526) names only 19, 22, 36. Spec R5: 'not yet formally decided by Ish as a list'. PROJECT_LOG G15d entry (HEAD line 163): 'Implemented on the spec\'s stated default, Ish\'s answer NOT recorded: Q1 ... and Q6 (pnpm/yarn residual accepted; recorded as spec default only)'. Z-6 ratification of R5 would move it to ACCEPTED_RESIDUAL; re-verify pnpm/yarn tables if either is installed (rule 12).

**G15b-14 reviewer W1: `pip install -qf x foo` short cluster hides `-f`/`-i`** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9 (G15d Unit B)]
- review: code-complete + reviewer-approved
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 5 refs, 5 product refusals)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_shell_g15d_unit_b.py::test_python_dash_m_pip_args_any_spelling (this is the node that carries the literal -qf form), ::test_pip_high_rows, ::test_pip_subcommand_set_and_dangerous_options_absent
- residual: -

**G15b-15 reviewer W2: `npm test --node-options=--import=data:...`, `--userconfig=x`, `npm c edit\|fix` alias** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9]
- review: code-complete + reviewer-approved
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 2 refs, 2 product refusals)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_shell_g15d_unit_b.py::test_npm_every_abbreviation_and_alias_is_checked_against_real_cmd_list, ::test_npm_i_x_is_act_the_x_token_is_an_operand_not_the_exec_alias
- residual: -

**G15b-16 reviewer W3: `node --inspect=0.0.0.0:9229 x.js` classified ACT** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9]
- review: code-complete + reviewer-approved (NEW-1040 node inspect re-review APPROVED)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 1 ref, 1 product refusal)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_shell_g15d_unit_b.py::test_node_inspect_non_loopback_forms_are_high, ::test_node_inspect_loopback_forms_stay_act, ::test_node_inspect_subcommand_is_high
- residual: -

**G15b-17 daemon `_DANGEROUS_FLAGS` substring test defeated by bundled `-Bc/-Ic/-Ec/-Wc`** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c]
- review: code-complete + reviewer-approved (G15c round 3; found marginal HIGH)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 6 refs, 6 product refusals)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_shell_g15c_allowlist.py::test_bundled_inline_code_forms_are_high, ::test_daemon_refuses_bundled_inline_forms_without_spawn, ::test_script_and_module_forms_stay_act
- residual: -
- note: NEW-1007 'Status' still reads Open; closure is in its Update 2026-10-23 note.

**G15b-18 daemon prefix boundary (NEW-1007)** [LOW, CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed e167e0c]
- review: code-complete + reviewer-approved
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 12 refs, 12 product refusals)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_shell_g15c_allowlist.py::test_daemon_prefix_word_boundary, ::test_daemon_blocks_prefix_lookalikes_before_any_spawn, ::test_daemon_still_allows_whole_word_prefix; source core/task_executor.py:563 uses _daemon_prefix_matches (read at 770dc66)
- residual: -

**G15b-19 script-file and `-m` opaque execution at ACT (bash script, python3 file, `pytest -p/-c`, make, compiler/go/cargo project configs)** [HIGH, ACCEPTED_RESIDUAL]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only; accepted-residual attempts recorded/refused, not execution success; accepted by Ish D-1]
- review: no code change; ACCEPTED RESIDUAL, DECIDED by Ish 2026-10-24 (D-1) under the section 1 ceiling statement
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A; the accepted-residual rows still execute as the ceiling statement says, 10f)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 1 ref refused, 5 accepted-residual attempts and 1 positive attempt control recorded/refused by harness; 'accepted' attempts are NOT execution success)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: control: script-file ceiling documented (V-A control row)
- residual: same-uid script children can still read environ, age.key, the .age file (NEW-1066 R1/R2); NEW-904 deferral ratified 2026-10-24

**G15b-20 `python3 -m http.server` / `-m code` ACT (network listener)** [MEDIUM, CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; over reviewer-approved, committed 890d4b9]
- review: code-complete + reviewer-approved (python -m 13-module allowlist, G15d Unit B)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 3 refs, 3 product refusals)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_shell_g15d_unit_b.py::test_python_m_other_modules_are_high, ::test_python_m_allowlisted_modules_stay_act, ::test_python_m_allowlist_is_pinned_exactly
- residual: ledger conflict on ratification: PROJECT_LOG G15d entry (HEAD line 163) says Ish answered 'Q4/Q5/Q7 accept all (... python -m module allowlist)', while NEW-1020/G15b-20 update says 'Ish's answer to Q7(c) not recorded'; side effect: bench.scorecard, timeit, cProfile module forms now HIGH
- note: Closed at code+review; whether Q7(c) is ratified is contradictory in the ledger. Carried under R18 until the coordinator reconciles.

**G15b-21 committed operator entry points runnable at ACT (`python3 -m tools.provision_ai_agent_auth`, `core/setup_dr_key.py --force`, `bash setup_repo.sh`, migrate/backfill `--apply`, `api.server --host 0.0.0.0`, service-stop by path, LoRA adopt NEW-977)** [HIGH, PARTIAL]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; also live-STYLE S1b pty at b230ce9 (pre-S2, not the attended terminal); over reviewer-approved, committed e167e0c; c842d97; 781542a]
- review: code-complete + reviewer-approved for the two NAMED entry points (G15i)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A/C/C3): C3 KILL-08 + DSHELL stop forms FAIL = service stop-script forms, now a DECIDED accepted residual (Ish 2026-10-24, third block)
- live: live-STYLE only: S1b real pty.fork on disposable DB/config with shim age-keygen, 4a/4b PASS (not the attended Termux terminal; real age-keygen never run)
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 4 refs refused + 1 accepted-residual attempt)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: test_g15i_operator_script_guards.py::test_provision_declined_changes_nothing, ::test_provision_no_tty_enxio_fails_closed_no_db_no_token, ::test_provision_stale_typeahead_does_not_approve, ::test_provision_approved_mints_and_audits_without_secrets; test_tty_confirm.py
- residual: siblings NOT covered: migrate/backfill --apply, restoricon_core.api.server --host 0.0.0.0 (NEW-1070 QUEUE); service stop-script forms and tools/encrypt_cloudflare_token.py = accepted residual (3rd decision block); DR key escrow creation PENDING ISH; script that creates its own pty can answer y (NEW-1071)
- note: The candidate's PARTIAL stands.

**G15b-22 self-launch of a more-privileged agent child (`python3 main.py --yolo --allow-self-mod`, `codeyOS --yolo --allow-self-mod`)** [HIGH, ACCEPTED_RESIDUAL]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only; accepted-residual attempts recorded/refused, not execution success; accepted by Ish D-1]
- review: NARROWED by G15e then ACCEPTED RESIDUAL, DECIDED Ish 2026-10-24 (D-1)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A/C/C3)
- live: no live run
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 4 refs, 4 product refusals)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: n/a for the residual (literal runner-operand forms HIGH via protected scan)
- residual: internal exec, PATH-resolved launcher and -c forms unchanged

**G15b-23 audit-label inaccuracies (`./ls` labelled READ, READ-class writers)** [LOW, CLOSED_CODE_REVIEW]
- evidence_tier: reviewer-approved [committed 890d4b9; no live run; replay deferred]
- review: code-complete + reviewer-approved (consequence of D-3 and the option tables; NO separate code)
- re-probe: none: no S1 or V-A row maps to G15b-23
- live: no live run
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: closed at code+review tier, replay deferred (tier recorded)
- tests: test_shell_g15d_unit_a.py::test_d3_slash_argv0_outside_system_dirs_is_high, ::test_unrelated_tools_keep_their_class (indirect; no label-specific test located)
- residual: -
- note: WEAKEST closed item: closed by inference. The audit label ('./ls' labelled READ) derives from classify_shell_command, which now returns HIGH_IMPACT for './ls push origin main' (reviewer scratch import at 770dc66); no test asserts the audit-row label itself, and no S1/V-A row maps to it.

**G15b-24 G15c fidelity residuals (pip3.11 false positive, accepted `pnpm run node` false positives, ruby/perl allowlists unverified)** [LOW, PARTIAL]
- evidence_tier: reviewer-approved [committed 890d4b9; no live run; replay deferred]
- review: code-complete + reviewer-approved for W5 (pip3.11) only
- re-probe: none located (no S1/V-A row)
- live: no live run
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: test_shell_g15d_unit_b.py::test_pip_basename_regex_admits_versioned_pip_only_after_table_check
- residual: ruby/perl allowlists conservative and UNVERIFIED against real help (not installed, rule 12); accepted false positives (pnpm run node, yarn run config, npm x, node -r, ruby -C, perl -x, make -C)

**G15b-25 plugin `manifest.json` ACT-writable: code execution at next load, same-name shadowing, `entry_point` `..`, no spawn audit row** [HIGH, PARTIAL]
- evidence_tier: live-verified [DISPOSABLE fixture only; real token / real spawn deferred]
- review: code-complete + reviewer-approved (G15g-A round 2; G15g-B with warnings, W-a open; 770dc66 enabled-policy slice reviewed). D-6 (manifest.json HIGH, fork-3 reversal) approved by Ish 2026-10-25 ('D-6/D-7 protections'); G15g spawn policy ACT + audit RATIFIED 2026-10-24 second block; thermal-only dashboard activation and retained-disabled canonical adapters approved 2026-10-25
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-C1 PASS on containment / spawn audit / duplicate names with controls per 10f; zero-width name FAIL fixed S2-B NEW-1081)
- live: live-verified on DISPOSABLE fixture plugins only (real PluginManager + real Popen); real aigentik/private_agent NOT exercised; the two canonical adapters are enabled:false at 770dc66
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: test_plugin_manifest_authority.py::test_duplicate_names_refused_for_all, ::test_symlinked_plugin_dir_category_dir_manifest_refused; test_plugin_spawn_audit.py; test_plugin_manifest_enabled.py; test_s2_ccos_authority.py::test_zero_width_duplicate_refused_both
- residual: R1: start_command/env/working_dir arbitrary (attribution, not a block); child env inherit-all; W-a positional secrets in argv reach the audit row; real-spawn live check deferred; NEW-1102 (plugin exec_module has no content integrity check, MEDIUM, OPEN/QUEUE) is PROVISIONAL: absent from the 770dc66 NEW_ISSUES blob, present only in the later uncommitted ledger text
- note: Register's three asks done at code-complete (10c) but 10f/spec 3.2 keep it Partial on R1; kept.

**G15b-26 `config.json` (repo/state) ACT-writable: tunnel token, `api_host` 0.0.0.0, `aigentik.dir` launcher, GCS bucket** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: reviewer-approved [committed c842d97; no live run; replay deferred]
- review: code-complete + reviewer-approved
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-B1/C1)
- live: no live run
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: closed at code+review tier, replay deferred (tier recorded)
- tests: test_protected_paths.py::test_root_config_json_is_high_with_state_config_present_and_absent, ::test_config_active_alone_denies_when_no_f3_row_matches, ::test_codey_config_path_nondefault_file_is_denied_not_just_via_default_resolution
- residual: repo-root config.json is HIGH (not DENY; Q1(b) not taken); sibling dev repos deliberately unprotected (NEW-1051 (9))

**G15b-27 launchers, `main.py`, `lib/*.sh`, `install.sh`, `setup*.sh`, `tools/setup_skills.sh` ACT-writable (F3)** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: replay-recorded [V-A @770dc66, approved per REVIEW_VA_RESULT.md final review recorder-only, 74/267 original IDs unselected, no execution semantics; also live-STYLE S1b pty at b230ce9 (pre-S2, not the attended terminal); over reviewer-approved, committed c842d97; 781542a]
- review: code-complete + reviewer-approved (confirm-less modes at c842d97; REPL new-file/append prompt added by G15j 781542a)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-A/B1/C/C3)
- live: live-STYLE: S1b checks 1-3 (G15j new-file/append at install.sh/lib/x.sh on a Python pty.fork) PASS; not the attended terminal
- replay @770dc66: V-A replay-recorded at frozen 770dc66 (approved: REVIEW_VA_RESULT.md FINAL R1 RE-REVIEW; VA_REPLAY_RESULT.md is the superseded result text) (recorder-only harness; attempts recorded/refused, nothing executed; 3 refs refused)
- replay status: partially replay-recorded (V-A @770dc66); B/C remainder deferred (Ish 2026-10-27)
- tests: test_protected_paths.py::test_f3_launcher_set_includes_codey_metrics_and_all_listed, ::test_f3_launcher_stays_high_when_exec_bit_would_make_path_shadow; test_protected_paths_repo_drift.py; test_file_tools_protected_classification.py
- residual: NEW-1051 reviewer warnings (HIGH tier unlocked by --allow-self-mod by design)

**G15b-28 non-root authority/agent-adjacent files ACT-writable (`ccos/core/**`, `restoricon_core/authority.py`; `telemetry/store.py`, `pipeline/run.py`, `codey_estimator/__init__.py` ambiguity-only)** [HIGH, PARTIAL]
- evidence_tier: reviewer-approved [committed c842d97; no live run; replay deferred]
- review: code-complete + reviewer-approved for the D-7 set (ccos/core/**, restoricon_core/authority*.py direct-child .py); D-6/D-7 CONFIRMED by Ish 2026-10-25 (NEW-1016 update: 'Ish formally confirmed D-7 existing HIGH protection for ccos/core and restoricon_core/authority*.py, plus Z-1 default-blocking coverage ... business-boundary rows still covered')
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-B1/C/C3; the queued files still write: ACCEPTED-RESIDUAL as registered, NEW-1051 S0-S2 note)
- live: no live run
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: test_core_file_classification_ext.py (ccos/core and authority rows moved to HIGH); test_protected_paths.py
- residual: telemetry/store.py, pipeline/run.py, codey_estimator/__init__.py (ambiguity-only) were queued by the D-7 recommendation ('the other three queue'), NOT added; HIGH but not core files so no checkpoint under --allow-self-mod
- note: D-7 and Z-1 are decided (so the trigger is not 'NEW-1016 decision'), the queued remainder is decided-as-queued. Still PARTIAL because three ambiguity-only files are neither classified HIGH nor accepted by a residual signature (R12 unsigned).

**G15b-29 bench non-`.py` evaluator files ACT-writable (`bench/suite.lock`, `scorecard_manual.json`, `scorecard_history.jsonl`, `bench/tasks/**` fixtures)** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: reviewer-approved [committed c842d97; 623e4c7; 84c7bfd; no live run; replay deferred]
- review: code-complete + reviewer-approved (classification half c842d97; hash half 623e4c7 round 2; NEW-1082 symlink-dir lock fix 84c7bfd)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-B1/C/C2; function level; bench never run)
- live: none: the bench has never been run with lock v2 / hardened grader / scrubbed env
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: closed at code+review tier, replay deferred (tier recorded)
- tests: test_bench_integrity_classification.py (5); test_bench_integrity_lock.py::test_evaluator_hash_algorithm_pinned, ::test_lock_coverage_every_bench_py_is_covered_or_explicitly_excluded, ::test_editing_each_covered_file_breaks_lock; test_s2_bench_symlink_lock.py
- residual: non-.py bench files (scorecard_manual.json, suite.lock, history, README) intentionally outside the hash (NEW-1067)
- note: Self-attestation (G15f Q2, no /dev/tty gate on write_lock) was RATIFIED as an accepted residual by Ish 2026-10-24 second block; the remainder of the NEW-1067 list is covered by R11, not yet signed as a list.

**G15b-30 bench lock hashes `bench/tasks/**` only; `write_lock()` self-attesting; verify/gate/compare/stats unhashed (NEW-1008 confirmed)** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: reviewer-approved [committed 623e4c7; 84c7bfd; no live run; replay deferred]
- review: code-complete + reviewer-approved (G15f-B round 1 with warnings, round 2 APPROVED; closed EXCEPT self-attestation)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-B/C2; VC2-N01 FAIL symlinked directory bench/linkdir -> NEW-1082, fixed 84c7bfd)
- live: none: bench never run with lock v2
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: closed at code+review tier, replay deferred (tier recorded)
- tests: test_bench_integrity_lock.py::test_evaluator_hash_framing_is_unambiguous, ::test_nonutf8_lock_fails_closed_and_runner_raises_runtimeerror, ::test_suite_hash_collision_is_a_pinned_accepted_residual; test_s2_bench_symlink_lock.py
- residual: NEW-1067: self-attesting write_lock (G15f Q2 RATIFIED as accepted residual 2026-10-24 second block), same-uid windows, symlink-following snapshot copy, unchecked-hash .pyc, all-absent evaluator_hash accepted by compare(), suite_hash NUL framing; every existing baseline must be re-run (legacy rows lack evaluator_hash)
- note: CLOSED; self-attestation ratified, rest of NEW-1067 under R11 (list unsigned). NEW-1008 body still reads Suspected/Open (closing evidence in its updates; NEW_ISSUES 22624 still says 'Q2 unanswered', superseded by consolidated line 528).

**G15b-31 graded-workspace `conftest.py`/`pytest.ini` honored: unsolved task grades pass (BN-05)** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: reviewer-approved [committed e9f593f; no live run; replay deferred]
- review: code-complete + reviewer-approved (G15f-A)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-C2: every planted case graded False; sensitivity control: same payloads graded True on e9f593f^ 4/4, NEW-1045 update)
- live: none: grader never run on the device
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: closed at code+review tier, replay deferred (tier recorded)
- tests: test_bench_integrity_grader.py::test_ambient_pytest_addopts_does_not_leak, ::test_exit0_without_evidence_is_false, ::test_shadow_pytest_module_forging_junit_needs_dash_I
- residual: in-process junit forgery with the correct count remains (accepted, NEW-1045)
- note: HIGH by ambiguity; D-8 HIGH rating CONFIRMED by Ish 2026-10-25 (NEW_ISSUES 'Update 2026-10-25 (closure decisions)' at 770dc66: 'remaining D-8 HIGH ratings (07/31/35;37 already approved)'; PROJECT_LOG 2026-10-25: 'D-8 remaining HIGH ratings').

**G15b-32 bench agent inherits `dict(os.environ)` (re-enables `ALLOW_SELF_MOD`) and operator stdin** [HIGH HIGH (amb; D-8 unconfirmed), CLOSED_CODE_REVIEW]
- evidence_tier: reviewer-approved [committed e9f593f; no live run; replay deferred]
- review: code-complete + reviewer-approved (G15f-A). Rated HIGH by ambiguity; D-8 for 32 is NOT confirmed: it is in the consolidated D-8 list (line 516-517, '32 is cheap') but not in the 2026-10-25 enumeration (07/31/35;37)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-C2; function level)
- live: none: allowlist sufficiency for a real on-device bench run UNVERIFIED (LD_PRELOAD dropped)
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: closed at code+review tier, replay deferred (tier recorded)
- tests: test_bench_integrity_grader.py::test_grader_env_allowlist, ::test_bench_child_env_pure, ::test_extra_args_exact_allowlist, ::test_extra_env_authority_rejected_at_construction
- residual: env allowlist might starve the on-device backend: unknown until L2-b
- note: Closed at code+review; sufficiency deferred to the Ish-attended bench run.

**G15b-33 file tools with cwd = `$HOME`/repo write persistence (`.bashrc`, boot script, `authorized_keys`, `.gitconfig`), Codey config/keys (`.codeyOS/config.json`, `age.key`), launchers; HM-06/07/12 MEDIUM rows** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: reviewer-approved [committed c842d97; B1 owned-fixture replay on fabricated fixtures, audit CHANGES_REQUESTED on wording only, not live, not full coverage, no HM-* protected-path coverage; S1 re-probe PRE-S2]
- review: code-complete + reviewer-approved (given repo/$HOME in the workspace; reviewer Critical C1 fixed in Unit A)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-B1: 187 rows 0 FAIL; V-B2 restore step run)
- live: none
- replay @770dc66: none citable for HM-* protected-path coverage (B1 HM-01/03/08 hit the HIGH no-confirmation gate first); B1 bridge owned-fixture replay (16 references re-executed once on fabricated owned fixtures against frozen 770dc66; independent result audit B1_SUBSET_RESULT_AUDIT.json = CHANGES_REQUESTED on WORDING only, raw execution evidence consistent, no escape); not live-verified; not full coverage; replay expansion deferred (Ish 2026-10-27)
- replay status: closed at code+review tier, replay deferred (tier recorded)
- tests: test_filesystem_protected_paths.py::test_deny_tier_refused_with_rule_and_no_side_effect, ::test_deny_tier_unchanged_bytes_for_existing_target, ::test_allow_self_modification_never_unlocks_deny_tier; test_protected_paths.py::test_deny_beats_high
- residual: NEW-1088 (MEDIUM, verifier-labelled accepted residual, unsigned): checkpoint restore of a planted core/agent.py is verbatim after operator confirm; session/queue files carry no integrity check; hard links not exercisable

**G15b-34 audit-ledger truncation/tamper (`write_file` over `action_gateway_audit.jsonl`; shell `sed -i`/`ln -sf /dev/null`; sink swallows OSError)** [HIGH, PARTIAL]
- evidence_tier: reviewer-approved [committed c842d97; B1 owned-fixture replay on fabricated fixtures, audit CHANGES_REQUESTED on wording only, not live, not full coverage, no HM-* protected-path coverage; S1 re-probe PRE-S2]
- review: code-complete + reviewer-approved (for the NAMED forms)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-B1/C/C3: 3 ACCEPTED-RESIDUAL in C3)
- live: none
- replay @770dc66: none citable: B1 HM-11 hit the HIGH no-confirmation gate first and may not be cited as protected-path coverage; replay expansion deferred (Ish 2026-10-27)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: test_filesystem_protected_paths.py::test_audit_ledger_guarded_and_gateway_can_still_append, ::test_audit_default_path_guarded_when_env_override_unset; test_protected_paths.py::test_audit_sink_env_set_and_unset_and_default_always_guarded; test_file_tools_protected_classification.py::test_audit_ledger_classifies_high. These cover write_file/patch/append only; shell sed -i / ln -sf against the ledger are NOT among them (test_shell_g15e_protected_scan.py:283 ln -sf is an allow-case); no test covers the sink OSError behaviour
- residual: UNFIXED sub-claims named in the item title: the audit sink swallowing OSError by design (NEW-1026 body: 'the sink swallows OSError by design') and the optional hash chain ('Optional hash-chain is queue'); fixed forms only: write_file/patch/append over the ledger and argv-visible shell forms
- note: CATEGORY CHANGED vs the first draft (CLOSED -> PARTIAL) on independent review R-1 and CLAUDE.md rule 6: a row whose title names unfixed sub-claims must not be CLOSED. Consolidated 10b/spec 3.2 closed it 'for the named forms'; that wording is now the fixed-forms scope of this PARTIAL. Parked (no fix planned); NEW-1026 needs an append stating the two sub-claims.

**G15b-35 nested `.git` and case-variant `.GIT` unprotected by file tools** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: reviewer-approved [committed c842d97; no live run; replay deferred]
- review: code-complete + reviewer-approved (HIGH by ambiguity; D-8 HIGH rating CONFIRMED by Ish 2026-10-25 (NEW_ISSUES 'Update 2026-10-25 (closure decisions)' at 770dc66: 'remaining D-8 HIGH ratings (07/31/35;37 already approved)'; PROJECT_LOG 2026-10-25: 'D-8 remaining HIGH ratings'))
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-B1; see NEW-1051 S0-S2 note)
- live: none
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: closed at code+review tier, replay deferred (tier recorded)
- tests: test_filesystem_git_metadata.py::test_write_denied_under_git_metadata, ::test_nested_repository_git_is_blocked (declared flip); case-variant .GIT: test_filesystem_protected_paths.py::test_deny_tier_refused_with_rule_and_no_side_effect (parametrized row 'proj/.GIT/config', rule git-component, line 71)
- residual: MEASURED residual, undecided: a '.git' + zero-width-character name classifies ACT and lands as a distinct directory on this byte-exact ext4 (NEW-1087; the verifier label ACCEPTED-RESIDUAL is not an Ish decision); Unicode normalization of the protected set open (NEW-1087)

**G15b-36 `--allow-self-mod --yolo` lets HIGH writes through unprompted (AS-01); checkpoint omits bench/ccos/lib (AS-02 LOW)** [HIGH, ACCEPTED_RESIDUAL]
- evidence_tier: deferred [decision only; no code]
- review: no code; ACCEPTED RESIDUAL, DECIDED Ish 2026-10-24 (D-1) for AS-01 (--allow-self-mod --yolo writes HIGH unprompted)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-B1/C/C3 ACCEPTED-RESIDUAL)
- live: no live run
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: test_g15j_file_tools_confirm.py::test_allow_self_mod_still_prompts (pins the non-yolo behavior)
- residual: AS-02 (LOW: checkpoint omits bench/ccos/lib) not separately decided; still true (NEW-1051 reviewer warning (b))
- note: AS-02 (LOW, checkpoint omits bench/ccos/lib) is NOT an Ish decision: D-1 covers AS-01 only. Hedge kept: the item stays ACCEPTED_RESIDUAL on the strength of AS-01 and consolidated lines 379-382 ('on purpose' per group 14); if Ish wants AS-02 recorded it needs its own residual line.

**G15b-37 HIGH_IMPACT file writes with no prompt in REPL and non-tty non-`--yolo` runs (new core `.py`, `append_file` to core/config files)** [HIGH, CLOSED_CODE_REVIEW]
- evidence_tier: reviewer-approved [committed 781542a/84c7bfd; live-STYLE S1b pty at b230ce9 PRE-dates S2-D flush; B1 owned-fixture replay, not live, not full coverage]
- review: code-complete + reviewer-approved (G15j; HIGH by ambiguity; D-8 for 37 DECIDED keep HIGH via the G15j GO of 2026-10-24)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-B1 IA rows PASS per 10f; verify-C3: REPL.pipey_real_confirm FAIL = legacy overwrite/patch prompts accepted piped y, fixed S2-D NEW-1074 at 84c7bfd)
- live: live-STYLE only: S1b checks 1-3 real pty.fork PASS (59/62 rows overall; the 3 FAILs are peer typeahead, /git commit typeahead, ^C timing); NOT the attended terminal and PRE-DATES the S2-D flush
- replay @770dc66: B1 bridge owned-fixture replay (16 references re-executed once on fabricated owned fixtures against frozen 770dc66; independent result audit B1_SUBSET_RESULT_AUDIT.json = CHANGES_REQUESTED on WORDING only, raw execution evidence consistent, no escape); not live-verified; not full coverage (IA-01b, IA-02b PASS_OWNED_FIXTURE)
- replay status: closed at code+review tier, replay deferred (tier recorded)
- tests: test_g15j_file_tools_confirm.py::test_non_tty_fails_closed_without_reading, ::test_isatty_raising_fails_closed, ::test_deny_and_out_of_workspace_refused_without_prompt, ::test_live_no_tty_refuses; test_g15j_gateway_confirm.py; test_s2_confirm_fail_closed.py::test_non_tty_never_reaches_console_input
- residual: NEW-1078 residuals R1-R9; G15i/G15j Q-A..Q-F unratified defaults (R18); NEW-1075 _sync_to_codeymd callback-free; live-STYLE S1b FAILs on the 2026-10-24 run: 5.escalate.typeahead_y (peer typeahead, NEW-1084, tracked under G15b-46), 6.commit.typeahead (/git commit stale Enter, NEW-1084), 7.ctrlc_delay_note (^C does not wake input(), NEW-996); the typeahead fixes (S2-D) were not re-run on the attended terminal
- note: Closed at code+review; the attended-terminal re-run is in the Z-5 schedule.

**G15b-38 `patch_file` reads any readable file outside the workspace (FT11/FT12 **UNSUPPORTED**: no retained output)** [MEDIUM, CLOSED_CODE_REVIEW]
- evidence_tier: reviewer-approved [committed c842d97; B1 owned-fixture replay on fabricated fixtures, audit CHANGES_REQUESTED on wording only, not live, not full coverage, no HM-* protected-path coverage; S1 re-probe PRE-S2]
- review: code-complete + reviewer-approved (rule-6 corrected from UNSUPPORTED to CONFIRMED then FIXED)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-B1/B2/C1; FT11/FT12 re-run with retained output, refused before read, nothing echoed)
- live: none
- replay @770dc66: B1 bridge owned-fixture replay (16 references re-executed once on fabricated owned fixtures against frozen 770dc66; independent result audit B1_SUBSET_RESULT_AUDIT.json = CHANGES_REQUESTED on WORDING only, raw execution evidence consistent, no escape); not live-verified; not full coverage (FT12-ssh, FT12-age PASS_OWNED_FIXTURE; may NOT be cited as 'refused before read'; N17 is a read-only partial subcase and does not cover the no-existence-oracle claim)
- replay status: closed at code+review tier, replay deferred (tier recorded)
- tests: test_g15e_unit_c.py::test_patch_nonmatching_old_str_does_not_echo_file_outside_workspace, ::test_patch_nonmatching_old_str_does_not_echo_credential_inside_workspace, ::test_patch_missing_and_outside_give_same_refusal_class
- residual: -

**G15b-39 `.codeyignore` not applied to read tools (IG-02)** [MEDIUM, OPEN]
- evidence_tier: deferred [no fix; queued; still reproduces at b230ce9 or by source read]
- review: not addressed (boundary clarified only, 10b)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-B1/C: still reproduces, label ACCEPTED-RESIDUAL-UNCHANGED = verifier label, NOT an Ish decision)
- live: no live run
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: none
- residual: .codeyignore not applied to read tools; .env/*.pem/*.key reads through file tools intentionally allowed

**G15b-40 model-writable steering state (CODEY.md, notes with forged section headers and no size cap, KB/skills)** [MEDIUM, OPEN]
- evidence_tier: deferred [no fix; queued; still reproduces at b230ce9 or by source read]
- review: not addressed (partly reduced: ~/.codey_sessions and the state dir are DENY write targets)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-B1: CM-01/NT-01/NT-02 reproduce, KB-01 INCONCLUSIVE; verifier labels, not Ish decisions)
- live: no live run
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: none
- residual: CODEY.md/notes/KB/skills steering state still model-writable; content-trust (NEW-846) deferral RATIFIED by Ish 2026-10-24 second block (R14)
- note: Stays OPEN despite the ratification: Ish's 2026-10-24 second block ratified only the NEW-846 content-trust DEFERRAL (R14). The write-ability of CODEY.md / notes / KB / skills (NEW-1032) was never ratified or fixed, so the item itself remains an unfixed, undecided queue finding.

**G15b-41 symlink/case alias bypasses `WRITE_PROTECTED` overwrite prompt (FT16, CS-02)** [LOW, OPEN]
- evidence_tier: deferred [no fix; queued; still reproduces at b230ce9 or by source read]
- review: not addressed
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-B1: FT16 reproduces; CS-02 INCONCLUSIVE, no case-insensitive FS)
- live: no live run
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: none
- residual: symlink/case alias bypasses WRITE_PROTECTED overwrite prompt (FT16, CS-02)

**G15b-42 import-time state creation (IM-01/02; IM-03 INCONCLUSIVE)** [LOW, OPEN]
- evidence_tier: deferred [no fix; queued; still reproduces at 770dc66 (V-A import effect / frozen suite)]
- review: not addressed in production code (NEW-855 only fixed test isolation)
- re-probe: none: no S1 row for G15b-42
- live: no live run
- replay @770dc66: V-A R1 correction at frozen 770dc66 is fresh incidental evidence the defect still reproduces: 'checkpoint536->_extend_state_schema523->get_state_store->StateStore41 creates fresh nonce SQLite schema/WAL' (VA_REPLAY_RESULT.md); core/checkpoint.py:536 at HEAD
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: none for the production behavior (test_new855_codey_state_dir_isolation.py covers test isolation only)
- residual: import-time state creation (IM-01/02); IM-03 INCONCLUSIVE
- note: Parked. WP2.2 (Worlds/Playground + live-data isolation) is only RECOMMENDED next in handoff section 7 and is unsigned; NEW-1011 has no pointer in the blueprint. If Ish signs WP2.2, retag it to WP2.2 and add the blueprint pointer line.

**G15b-43 CCOS authority keyed by capability name; `coding.run_agent` kwargs downgrade; limits are metadata; manifest URLs unvalidated** [MEDIUM, PARTIAL]
- evidence_tier: reviewer-approved [committed e9f593f; 84c7bfd; no live run; replay deferred]
- review: code-complete + reviewer-approved (S2-B M25b/M26 + NEW-1093 positional bypass at 84c7bfd; 'name-hijack narrowed' e9f593f)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-C1: 2 FAIL M25b, M26 PRE-fix, fixed 84c7bfd; verify-C3 3 PASS 1 ACCEPTED-RESIDUAL)
- live: no live run
- replay @770dc66: none; post-S2 re-probe replay expansion deferred (Ish 2026-10-27)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: test_s2_ccos_authority.py::test_relaxing_kwargs_refused_and_audited, ::test_callable_positional_refused, ::test_smuggled_trusted_flag_does_not_bypass, ::test_run_agent_capability_via_public_path_refused, ::test_benign_positional_data_refused_and_audited, ::test_zero_width_duplicate_refused_both
- residual: C:M24 (resource limits are metadata) and C:N03 (manifest URLs unvalidated) remain; runtime handlers untouched; PL-04 capabilities.json NEW-1086; latent (no production caller outside ccos/)

**G15b-44 daemon IPC `peer_uid` check is dead code; `codeyOS --bg` launders a prompt into an unattended daemon task** [MEDIUM, OPEN]
- evidence_tier: deferred [no fix; queued; still reproduces at b230ce9 or by source read]
- review: not addressed
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-C3: D-01 peer_uid None on this asyncio unix server, D-02 socket 0o777->chmod; labelled ACCEPTED-RESIDUAL by the verifier, NOT an Ish decision)
- live: no live run
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: none (core/daemon.py:739-741 at 770dc66 still performs the dead `peer_uid is not None` check)
- residual: peer_uid check dead code; codeyOS --bg launders a prompt into an unattended daemon task (same-uid only)

**G15b-45 dead confirmation signals (`CODEY_DAEMON_MODE`, `CODEY_NON_INTERACTIVE` never set); `peer_cli` fail-open on stdin exception** [LOW, PARTIAL]
- evidence_tier: reviewer-approved [committed 890d4b9; no live run; replay deferred]
- review: code-complete + reviewer-approved for the interactivity part (DORMANT; is_interactive_environment fails closed, no production caller)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-C3: D-09 no writer of CODEY_DAEMON_MODE / CODEY_NON_INTERACTIVE anywhere)
- live: no live run
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: test_peer_cli_confirm_default_no.py::test_is_interactive_environment_fails_closed; test_escalation_review_queue.py::test_is_interactive_environment
- residual: dead confirmation signals (no writers); NEW-1089 headless peer skip vs park follow-up

**G15b-46 peer escalation approval default-Yes; committed `.qwen/settings.json` allows `pkill`/`rm`/`curl` for the qwen peer** [MEDIUM, PARTIAL]
- evidence_tier: reviewer-approved [committed 890d4b9/84c7bfd; live-STYLE S1b typeahead case FAILED, fixed, not re-run live]
- review: code-complete + reviewer-approved (Enter=No at 890d4b9; .qwen/settings.json trimmed 20->7 with NO separate reviewer pass; S2-D flush at 84c7bfd)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-C3: 5 PASS)
- live: live-STYLE S1b check 5 on a Python pty: Enter/n skip, y once, piped y skipped PASS; TYPEAHEAD case FAILED, fixed S2-D round 4 and NOT re-run live (NEW-1084)
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: test_peer_cli_confirm_default_no.py::test_enter_and_no_decline, ::test_escalate_with_enter_never_dispatches, ::test_confirm_non_tty_piped_y_cannot_approve; test_qwen_settings_allowlist.py::test_destructive_and_egress_entries_are_not_allowed
- residual: typeahead flush not re-verified live; rule-6 correction NEW-1083 (earlier 'parks off-tty' claim was false)

**G15b-47 `--tdd` confirm-less without `--yolo`; `--fix` re-runs model-rewritten code unattended** [MEDIUM, PARTIAL]
- evidence_tier: reviewer-approved [committed 781542a; no live run; replay deferred]
- review: code-complete + reviewer-approved for the --tdd half (D-9, 781542a); --fix half DECIDED accepted residual (Ish 2026-10-24, NEW-1077, list unsigned)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-C3: TDD-01/02 PASS; FIX-01 FAIL = decided residual)
- live: no live run
- replay @770dc66: none; replay expansion deferred (Ish 2026-10-27)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: test_tdd_confirmations.py::test_tdd_default_keeps_confirmations, ::test_tdd_explicit_no_yolo_keeps_confirmations, ::test_main_tdd_alone_passes_yolo_false_and_leaves_config
- residual: --fix unattended re-run of model-rewritten code; --tdd without a tty wastes 5 iterations (NEW-1076)
- note: Stays PARTIAL because NEW-1076 (--tdd without a tty wastes 5 iterations, no early refusal) is open and the --fix half is a residual whose list is unsigned; not relitigated.

**G15b-48 export/session redaction misses credential shapes (cloudflared `--token`, `AGE-SECRET-KEY-`, `.netrc` passwords)** [MEDIUM, CLOSED_CODE_REVIEW]
- evidence_tier: reviewer-approved [committed f4353cf; 84c7bfd; no live run; replay deferred]
- review: code-complete + reviewer-approved (G15h-B two rounds; NEW-1080 mid-line env gap fixed 84c7bfd)
- re-probe: independently re-probed at b230ce9 (recording fakes; PRE-S2; not live) (verify-C1: 15 original + 6 added + 14 further shapes through six sinks PASS per 10f; verify-C3: GW-10b FAIL PRE-fix)
- live: no live run
- replay @770dc66: none; post-S2 re-probe replay expansion deferred (Ish 2026-10-27)
- replay status: closed at code+review tier, replay deferred (tier recorded)
- tests: test_g15h_masking_redaction.py::test_mask_secrets_masks_every_shape, ::test_redact_secrets_all_shapes_and_legacy, ::test_file_log_masks_all_shapes_console_untouched, ::test_age_canary_matches_real_shape
- residual: sinks NOT covered: trajectory DB, checkpoints, telemetry, recovery history, episodic_log, memory tiers, console; positional secrets (NEW-1060/1066)
- note: Rule-6 correction retained: sessions.redact_secrets masked 2 of 15 shapes.

**G15b-49 order-dependent test failure and working-tree pollution (non-hunter, found during G15c verification)** [LOW, OPEN]
- evidence_tier: deferred [no fix; queued; still reproduces at 770dc66 (V-A import effect / frozen suite)]
- review: not addressed
- re-probe: none: no S1 row for G15b-49
- live: no live run
- replay @770dc66: frozen 770dc66 recursive run still FAILS it: chunk_31.log `FAILED tests/test_task_executor_telemetry.py::test_orphaned_thread_never_corrupts_concurrent_tasks_stats` (listed in the 10 recorded baseline failures)
- replay status: n/a (not closed); replay expansion deferred (Ish 2026-10-27)
- tests: tests/test_task_executor_telemetry.py::test_orphaned_thread_never_corrupts_concurrent_tasks_stats (the failing test itself)
- residual: state-dependent test failure + working-tree pollution; trigger not isolated

## 4. Changes versus the candidate, with verbatim evidence

### G15b-13: ACCEPTED_RESIDUAL_PREVIOUS_DECISION -> PARTIAL (the only category change)

Candidate basis was "previous decision". No Ish decision on the remainder exists in the sources read:

1. `docs/wp2_1_g15b_consolidated.md` line 526 (Ish decisions 2026-10-24), D-1 names exactly three items: "**D-1 = YES:** G15b-19 (script-file and `-m` opaque execution), G15b-22 (self-launch) and G15b-36 (`--allow-self-mod`) are ACCEPTED RESIDUALS on the register".
2. `docs/wp2_1_g15z_spec.md` line 355 (R5): "package-spec rest: pip bare-name / local path / `-r` by precedent, pnpm/yarn conservative only (not installed) | G15b-13 rest, NEW-1044 | G15d, **not yet formally decided by Ish as a list**".
3. `NEW_ISSUES.md` NEW-1023 Status (HEAD blob): "G15b-13 PARTIALLY CLOSED (**FIX-NOW for git/URL specs; bare names/local paths/`-r` AR**)"; the consolidated section 10 row: "`G15b-13 | PARTIALLY CLOSED | URL/VCS part closed by Unit B; rest accepted residual | pnpm/yarn conservative only (not installed)`" and the PROJECT_LOG G15d ledger-effect line "G15b-13 URL/VCS part closed (rest accepted residual)" are coordinator/architect recommendations ("AR" = ACCEPT-AS-RESIDUAL in the consolidated rec column), not a recorded Ish answer.
4. `PROJECT_LOG.md` G15d entry (HEAD blob, line 163): "Recorded as decided by Ish (2026-10-23): F1, F2, D-F5, F3, D-2(b), D-3, D-4; and, answered by Ish in-session ...: Q2 yes, Q3 yes, Q4/Q5/Q7 'accept all' ... **Implemented on the spec's stated default, Ish's answer NOT recorded:** Q1 (D-3 lexical rather than realpath) and Q6 (pnpm/yarn residual accepted; recorded as spec default only)." Spec 3.4 repeats "Ish's answers not recorded".
5. I read the decision blocks whole: consolidated lines 524 (2026-10-23 "yes to all"), 526 (first 2026-10-24 block, D-1/D-10/D-7 partial), 528 (second block: G15j GO, D-9, D-5, Z-3, Z-2, RATIFIED G15f Q2 / G15g spawn policy / G15h Q-b, accepted-residual deferrals NEW-972, 943/944, 904/905/913/914, 846, 753/936, PENDING list) and 708 (third block: REPL non-tty fail-closed, `--fix` residual, M26/M25b fix, KILL-08 residual); then the 2026-10-25 closure-decision updates (D-6/D-7/D-8/Z-1). A grep over consolidated, closure-progress, takeover, handoffs, PROJECT_LOG, NEW_ISSUES, blueprint and the G15d spec at the `770dc66` blobs for `R5`, `package-spec`, `G15d Q`, `Q7(c)`, `pnpm/yarn`, `bare name` found no Ish decision on G15b-13's remainder. The quoted spec lines were checked against `git diff -- docs/wp2_1_g15z_spec.md`: the only working-tree changes are "Superseded 2026-10-27" gate-wording notes (lines 102-120, 321, 390), so lines 284, 355 and 449 are identical at HEAD.

Result: the URL/VCS-spec half is closed at code+review (`890d4b9`); the remainder is an unratified residual (R5/R18). Counts at this point 29 / 3 / 11 / 6 (28 / 3 / 12 / 6 after G15b-34, section 4b). If Ish ratifies R5 at Z-6 it can move back to ACCEPTED_RESIDUAL.

### 4b. G15b-34: CLOSED -> PARTIAL (independent review R-1)

Evidence: title names the audit sink swallowing OSError; NEW-1026 (770dc66): the sink swallows OSError by design, optional hash-chain is queue; my first version recorded both as not fixed with no trigger. Counts: CLOSED 28 / ACCEPTED_RESIDUAL 3 / PARTIAL 12 / OPEN 6.

### 4c. Other review corrections applied

R-2 G15b-04/32 D-8 citation; R-6 B1 wording on 33/34/37/38; warnings: 23 label-by-inference; 35 NEW-1087 undecided residual; 37 S1b FAILs named; 25 NEW-1102 provisional + D-6; 40 split explained; 42 re-tagged trigger: none; 36 AS-02 hedge; 47 NEW-1076; test citations completed for 08, 14, 34, 35; NEW-1069 triggers noted as effectively parked; V-A cited via the final review. See the TSV notes/tests/severity_note columns.

### Not changed, but each checked (check -> finding)

- **G15b-44, 39, 40, 41 (verifier "ACCEPTED-RESIDUAL"/"-UNCHANGED" labels)** -> Those labels are verify-agent verdict vocabulary, not Ish decisions. NEW-1029 update: "D-01 ... and D-02 ... remain ACCEPTED-RESIDUAL as queued". `core/daemon.py:739-741` at 770dc66 still has `peer_uid = writer.get_extra_info("peer_uid")` / `if peer_uid is not None and ...`. Kept OPEN, trigger per row.
- **G15b-30 and 29 (self-attestation)** -> Consolidated 10d says G15f Q2 was "implemented on the spec default", but the SECOND 2026-10-24 decision block (line 528) later records "**RATIFIED spec defaults:** G15f Q2 (no `/dev/tty` gate on `write_lock`; the self-attestation is an accepted residual)". So the self-attestation is a ratified residual; the rest of the NEW-1067 list is covered by R11 (list unsigned). NEW_ISSUES line 22624 ("Ish's G15f Q2 unanswered") is stale. Category CLOSED kept. 29 additionally: non-.py bench files outside the hash by design.
- **G15b-04, 07, 31, 32, 35, 37 (D-8)** -> D-8 is DECIDED: NEW_ISSUES 770dc66 "Update 2026-10-25 (closure decisions)": "remaining D-8 HIGH ratings (07/31/35;37 already approved)"; PROJECT_LOG 2026-10-25: "D-6/D-7 protections; D-8 remaining HIGH ratings". D-8 is no longer an R18 reason for those four. CAVEAT (review R-2): the enumeration does NOT name 04 or 32 (both are in the consolidated D-8 list, lines 516-517: "04 is CLOSED regardless", "32 is cheap"), so those two stay HIGH (amb; D-8 unconfirmed).
- **G15b-23** -> No S1 or V-A row maps to it; consolidated 10: "CLOSED (consequence of D-3 and the tables) | no separate code". Closed at code+review by inference only: the weakest closed item; the audit label derives from classify_shell_command, no test asserts the label. Kept CLOSED, flagged.
- **G15b-32** -> Closed at code+review; "allowlist sufficiency for a real bench run unverified (`LD_PRELOAD` dropped; deferred live check)" (10a). Sufficiency stays unverified until Z-5 L2-b.
- **G15b-47** -> 10f: "kept Partial because Z-6 has not signed the residual list". Left PARTIAL, not relitigated.
- **G15b-42** -> Fresh 770dc66 evidence it still reproduces: VA_REPLAY_RESULT.md R1 correction: "Actual checkpoint536->_extend_state_schema523->get_state_store->StateStore41 creates fresh nonce SQLite schema/WAL." Kept OPEN.
- **G15b-49** -> Frozen 770dc66 run: `chunk_31.log: FAILED tests/test_task_executor_telemetry.py::test_orphaned_thread_never_corrupts_concurrent_tasks_stats`, one of the 10 recorded baseline failures (`failed_nodes.txt`). Kept OPEN.
- **G15b-12** -> Severity MEDIUM is the rule-6 correction in NEW-1021 ("accepted by Ish"). Closed at disposable-chain live tier; the real token is not run (Z-5 L2-a).
- **G15b-34** -> CHANGED to PARTIAL on independent review R-1 (rule 6). The title names sink swallows OSError and NEW-1026 says the sink swallows OSError by design and Optional hash-chain is queue; neither is fixed and no cited test covers the sink behaviour or shell sed -i / ln -sf against the ledger. Fixed forms: write_file/patch/append and argv-visible shell forms. trigger: none (parked); NEW-1026 needs an append.
- **G15b-33** -> Closed for the file-tool/shell-argv routes given the workspace precondition; NEW-1088 (checkpoint content / session / queue integrity, MEDIUM/LOW) is a residual, "ACCEPTED-RESIDUAL by the verifier's label (for signature in Z-6)". Kept CLOSED with the residual named.
- **G15b-25** -> 10c says the register's three asks are done at code-complete, 10f/spec 3.2 keep Partial on R1 (arbitrary start_command/env). Kept PARTIAL. Spawn policy ACT+audit was RATIFIED (line 528); lazy activation and the dead-manifest fate were decided 2026-10-25 and implemented in 770dc66 (strict `enabled` policy, two canonical adapters `enabled:false`, thermal-only dashboard), which reduces but does not remove the residual. Provisional pointer: NEW-1102 (uncommitted).
- **G15b-28** -> D-6/D-7 CONFIRMED 2026-10-25 (NEW-1016 update; Z-1 default-blocking coverage with business rows still covered). The three ambiguity-only files were queued by the D-7 recommendation, so the trigger is `trigger: none`, not "NEW-1016 decision". Still PARTIAL: three files neither classified nor covered by a signed residual.
- **G15b-36** -> AS-02 (LOW, checkpoint omits bench/ccos/lib) is not separately decided; D-1 covers AS-01 explicitly. Kept ACCEPTED_RESIDUAL with a note.
- **R18 scope after the corrections** -> Still unratified (R18): G15d Q1 and Q6 (PROJECT_LOG line 163), G15i/G15j Q-A..Q-F (line 528 "Implemented on the spec default, Ish's answer NOT recorded"), and the G15b-20 Q7(c) point, where the ledger contradicts itself (PROJECT_LOG: "Q4/Q5/Q7 accept all"; NEW_ISSUES: "Q7(c) not recorded"). RATIFIED and therefore NOT R18: G15f Q2, G15g spawn policy, G15h Q-b, D-6/D-7/D-8, NEW-972/943/944/904/905/913/914/846/753/936 deferrals. G15b-37 keeps R18 (Q-A..Q-F); G15b-11, 25, 29, 30 do not.
- **Stale ledger wording** -> NEW-933, NEW-1007 and NEW-1008 headers still read "not fixed"/"Open"/"Suspected"; closure evidence is only in their later Update notes. Candidate TSV column `original_post_G15c_status` is the post-G15c snapshot (for example G15b-06 "OPEN") and must not be read as current. The blueprint §3 status text should be refreshed at S7.

## 5. S1/S1b FAIL rows mapped by hand (all later handled; none left unmapped)

| row | item | what happened | disposition |
|---|---|---|---|
| verify-A NV33, EV03 | G15b-10 | case-variant `$HOME/.SSH/ID_RSA` classified READ | fixed S2-A NEW-1079 (84c7bfd); V-A at 770dc66 now product-refuses both with 0 events |
| verify-C M25b | G15b-43 | out-of-tree plugin claimed `system.info`, dispatched as READ | fixed S2-B (84c7bfd) |
| verify-C M26 | G15b-43 | `call_capability` kwargs downgraded confirmations | fixed S2-B; positional hole NEW-1093 fixed 84c7bfd after a Critical review finding |
| verify-C M07.*capabilities_json, NEW.norm.zero_width | NEW-1086 / G15b-25,43 adjacent | PL-04 capabilities.json unprompted write; zero-width plugin name | NEW-1086 OPEN/QUEUE (not a G15b item); zero-width fixed S2-B NEW-1081 |
| verify-C2 VC2-N01 | G15b-29/30 | symlinked dir bench/linkdir importable but outside the evaluator hash | fixed NEW-1082 (84c7bfd); lock regenerated; baselines must be re-run |
| verify-C3 GW-10b | G15b-48 | mid-line `env NAME=secret` leaked into audit row | fixed S2-A NEW-1080 |
| verify-C3 KILL-08, DSHELL.service stop | G15b-21 | stop-script / process_identity stop forms run as ACT | DECIDED accepted residual (Ish 2026-10-24, third block); NEW-1070 |
| verify-C3 FIX-01 | G15b-47 | `--fix` re-runs model-rewritten code unattended | DECIDED accepted residual NEW-1077 |
| verify-C3 REPL.pipey_real_confirm | G15b-37 | legacy Overwrite/Apply-patch prompts accepted piped y | fixed S2-D NEW-1074; not re-verified at the attended terminal |
| S1b 5.escalate.typeahead_y | G15b-46 | stale `y\n` approved peer dispatch | fixed S2-D round 4 NEW-1084; NOT re-run live (Z-5) |
| S1b 6.commit.typeahead | NEW-1084 (/git commit) | stale Enter accepted commit suggestion | fixed S2-D; NOT re-run live (Z-5) |
| S1b 7.ctrlc_delay_note | NEW-996 | ^C on a pty does not wake input() until next key | readline startup helper committed 770dc66 (test_cli_readline_startup.py, disposable pty); attended-terminal re-check in Z-5 |

## 6. Items to carry into the closing packet (for the coordinator)

- **B1 result audit is now done** (`B1_SUBSET_RESULT_AUDIT.json`, CHANGES_REQUESTED on wording only). Cite B1 only with the wording above; the audit W1..W4 wording fixes and removal of the stray frozen_source_770dc66/tools/__pycache__/wp21_census.cpython-314.pyc (not in the manifest) are for the coordinator to apply.
- **Residual list R1-R18 still unsigned (Z-6).** Rows referencing R-numbers: see `residual_refs`. The candidate's R5 (G15b-13) is the only residual whose category depended on an unrecorded decision.
- **Blueprint pointer lines** (CLAUDE.md rule 8 trigger convention) are still needed in the WP entries for: WP2.2 (G15b-42 state isolation), NEW-1069 OS-boundary candidate (9, 19, 22, 36, 25 ceiling), NEW-1016 (28), and the unnamed replay-expansion WP. TODO for whoever edits the blueprint; this task is scratch-only.
- Tracking-doc corrections implied (not made): refresh stale "Open" headers on NEW-933/1007/1008; append the G15b-34 unfixed sub-claims to NEW-1026; append the G15b-13 category correction to NEW-1023/NEW-1044. Per rule 8, no new NEW-ID is needed for any of these (each restates an existing mechanism).
- No out-of-scope source defect was found, so no new NEW_ISSUES entry is proposed.
