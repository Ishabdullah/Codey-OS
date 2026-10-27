# WP2.1 closing evidence, frozen source 770dc66 (assembled 2026-10-27)

Durable copies of the evidence cited by `docs/WP2_1_CLOSING_PACKET_2026-10-27.md`.
Status: working-tree only, **uncommitted**, and nothing here records closure. This
directory is a sibling of `review_770dc66/` on purpose: adding files there would
have invalidated its existing 351-hash manifest. `SHA256SUMS` in this directory
pins every file here (`sha256sum -c SHA256SUMS` from this directory).

Files are byte-for-byte copies of the scratch originals in
`/data/data/com.termux/files/usr/tmp/wp21_closure_next/` (volatile, outside the
repo), except the three `census_frozen_*__SHA256SUMS_generated_by_this_pass.txt`
files, which this pass generated (runs 1 and 2 had no checksum file) and
`SHA256SUMS`/this README. Raw trailing tabs and spaces in TSV/log files are
intentional evidence; do not trim them.

| directory | contents |
| --- | --- |
| `C5/` | third fresh C5 packet (`C5_FRESH3_dispositions.tsv`), report, review round 4 (`C5_FRESH3_REVIEW_INDEPENDENT.json`), disagreement files for the final state and rounds 1-3, corrections changelog |
| `C6/` | installed fresh C6 packet (`d61a5afb...`), the as-reviewed packet (`C6_FRESH_dispositions.tsv.pre_reseal`, `b2aa8b12...`), report, review, disagreements (non-blind), reseal changelog |
| `merge/` | merge `build_summary.json`, first-seen provenance, aggregate expansion, `stale_key_movements_PENDING_REVIEW.json`, the stale-key review and the post-review adjudication, the strict `--check` output and independent-checks output, the merge plan, the merged candidate's own `SHA256SUMS.txt` |
| `supplementary/` | the 15 NEW-1101 `exec_module` rows (outside the scan-checked register), README, 3-round review, builder and verifier scripts. `.pre_*` clutter excluded |
| `b1/` | independent B1 result audit (CHANGES_REQUESTED on wording only), citable wording, author result |
| `g15b49/` | final 49-item reconciliation (`.tsv`/`.json`/`.md`), the predecessor TSV the re-review examined (`.pre_rereview`, `149f101a...`), first review and the re-review (CHANGES_REQUESTED) |
| `deferrals/` | Z-5 manual deferral schedule (draft) and Z-8 group-14 tier statement (draft) |
| `tests_gate/` | `summary.txt` (raw), `rerun_summary.txt`, `failed_nodes_now.txt`, `base_ids.txt`, the foreground chunk-29 rerun log, `ccos_exit.json`, `census_strict.log`, `ccos_guarded.log` |
| `verify_packet.py` | the read-only script that recomputes every 64-hex hash and count cited by the closing packet (reads scratch paths, so it only runs while the scratch directory exists); its output is pasted in packet section 9 |
| `GATE_AND_DOCS_REVIEW_RECORD.md` | the coordinator's transcription (NOT a reviewer file; the reviewer kept none) of the two in-session review rounds of the default-gate test change and the operator docs: round 1 CHANGES REQUESTED, round 2 APPROVED |
| `census_frozen/` | `summary.json` of runs 1 and 3, run 3's own `SHA256SUMS.txt`, and generated sums for runs 1, 2 and 3 (all identical) |

## Not copied, and where it remains

- The installed register itself: it is `docs/wp21_census/dispositions.tsv` (SHA256 `5279004783c2c3dc37208f061d76c97fdb1ec558d5eabbcd27dc61f1a8d0de7d`), identical to scratch `merged_candidate/dispositions_candidate.tsv`. The seven unit packets are the files under `C5/`, `C6/` and `docs/wp21_census/review_770dc66/` (C1-C4, C7).
- Scratch only, volatile: `frozen_source_770dc66/` (28 MB, 1,267 files, immutable, pinned by `frozen_source_manifest.json`) and `frozen_source_770dc66.tar` (26.6 MB); `preflight_7fe60cc.tar` (26.5 MB); `replay_guard_runs/` (V-A and B1 run roots); the 32 `chunk_*.log` and `home_*` test sandboxes; `census_pre_freeze/`; `census_frozen_1..3/` inventories (the six TSV files are byte-identical across the three runs, their hashes are in `census_frozen/`); reviewer/author state directories; `.pre_*` history files; the `C*_EVIDENCE_PREP.md` files; the `.wp21-closure-ccos-*` owned CCOS scratch roots in the repo root (untracked).
- The V-A and earlier classification evidence is already in `docs/wp21_census/replay_A_770dc66/` and `docs/wp21_census/review_770dc66/` (their own manifests).
- No model, key, token, credential, live database or generated state file is included.
