# Review record: default coverage gate (tests/test_wp21_census.py) and operator docs

Recorded by the coordinator on 2026-10-27 from the independent code-reviewer's reports delivered in-session (the reviewer did not retain a file; this record is the coordinator's transcription, not a reviewer artifact).

Round 1 — CHANGES REQUESTED (code sound; operator docs not yet updated, which S6_GATE_SCOPE.md requires in the same change). Reviewer re-ran tests: tracked register `1 failed, 122 passed, 1 skipped` (38 failures: 10 stale + 28 unregistered, 1,433 UNKNOWN); candidate register default `123 passed, 1 skipped`, STRICT=1 `124 passed`. Mutation checks: gate reverted to warn-only -> 6 failed; gate_restoricon default False -> 2 failed (tests discriminate). Real-commit simulation (test + register only) -> HEAD scan 1,467 keys, gate `123 passed, 1 skipped`. Found NEW-1103 (stale rows for files absent from the scan only warn; rename-to-test_* hole) — logged, not fixed.

Round 2 — APPROVED (docs hunks accurate; no current-tense warn-only/opt-in claim remains; NEW-1103 matches repro; reviewer corrected the deferral rationale: tools/wp21_census.py is a scanned file contributing 16 rows, so a boundary-call change alters the inventory; an edit with no boundary-call change does not). Residual warnings: gate silently skips without .git (CI has .git); local run reads the register from the worktree, not HEAD.

Not retained as a reviewer file. Tier: code-complete + reviewer-approved (reported), tests re-run by reviewer and by live-verifier (final_tests_gate/summary.txt).
