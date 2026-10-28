# WP2.2 closing note — Worlds / Playground isolation (2026-10-28)

**Status: CLOSED WITH ACCEPTED RESIDUALS** on Ish's instruction ("keep going until WP2.2 is closed", after the attended checks below and "yes and approved", 2026-10-28). Not a claim of OS-level isolation: the guard is a seatbelt, NEW-1069 is the boundary.

## Delivered (commits)
| Slice | What | Commit | Tier |
|---|---|---|---|
| S0 | tests redirect `RESTORICON_DB_PATH`; live-untouched guard | d21da20 | code-complete (test-only) |
| S1 | `restoricon_core/world.py` live-path classifier | 61fe532 | reviewer-approved (2 rounds) |
| S2 | `--world production` flag + launcher plumbing | 40308cb | reviewer-approved; dev half + production half live-verified (Ish) |
| S3a | strict classifier, `guard_db_open`, launcher authorizes only on positive match | b2a5989 | reviewer-approved (2 rounds) |
| S3b | no default DB path; `DatabaseManager`/server/3 CLIs refuse live without `--world production` | 7e47ab2 | reviewer-approved; refusal + production start live-verified (Ish) |
| S4 | `tools/world.py` create/list/env/destroy under `~/.codeyOS-worlds/`, empty worlds only | 3321f71 | reviewer-approved (3 rounds + final confirm); attended check passed (Ish) |
| S5 | cross-surface closure test (47 tests) + `docs/worlds.md` | 41b097f | code-complete; no separate review (tests+docs) |
| census | 23 `tools/world.py` rows registered, 23/23 reviewed | this commit | reviewer-approved |

## Live-verified (Ish-attended, 2026-10-28, verbatim in PROJECT_LOG)
- Dev API on `~/s2check`: no `--world production` in argv.
- Non-production start on the live path: `refusing to start ... without production authorization`, exit 2, sqlite tripwire silent; env path and no-config variants exit 2; live db/-wal/-shm stat identical.
- Managed production start: argv `--db .../.codeyOS/restoricon.db --world production`, log `[restoricon world] PRODUCTION open of live store: ...`, clean stop.
- World tool: create/list/env, world DB opens, live refused (`LiveStoreRefused`), destroy dry-run exit 2, bad name exit 2, destroy exit 0, live files IDENTICAL.

## Final suite (HEAD 41b097f, 29 isolated chunks, CCOS tests excluded as untouched)
9,616 passed. 10 failures: 9 = the recorded baseline (4 `test_74b`, 3 `test_new84`, 1 `test_new91`, 1 `test_daemon_shutdown_budget`/NEW-1109) + 1 census gate (23 unregistered `tools/world.py` rows) fixed in this commit: `WP21_CENSUS_STRICT=1 tests/test_wp21_census.py` 124 passed after. No other new failures. The chunks were not re-run in full after the register fix (only the census file).

## Accepted residuals (all logged with triggers)
NEW-1069 (OS-level boundary, separate candidate); NEW-1106 (Oct 24 live-store touch, Suspected, likely the 11:49 server start, unproven); NEW-1107 (committed repo `config.json` names live path); NEW-1108 (`tests/test_restoricon_core` single-process memory abort; split batches pass); NEW-1109 (shutdown-budget test); NEW-1111 (stale DEAD pid record race); NEW-1112 (S3b: fd-reuse, double-classification window, 0-byte file, hardlink detection untestable here); NEW-1113 (world tool limits: same-uid manifest forgery pinned as a known-gap test, final-rmdir window, special files block destroy). NEW-855/NEW-1011 mitigated in worlds only (lazy-init refactor parked). NEW-907 fixed in code.

## Not done / not claimed
Hardlink detection untested (no `os.link`); cross-mount refusal tested via a faked `st_dev`; `--fixture` and live-snapshot seeding intentionally not built (Ish: empty worlds only); `install.sh` unchanged (worlds root created on demand); CCOS tests not re-run; `CLAUDE.md` rule 0(b) pointer to `docs/worlds.md` added at Ish's approval.

## Next
Candidates: NEW-1069 (OS-level boundary), WP2.3 (registry/validator cleanup). Ish decides.
