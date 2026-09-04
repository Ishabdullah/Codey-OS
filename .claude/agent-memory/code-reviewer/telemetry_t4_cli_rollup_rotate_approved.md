---
name: telemetry-t4-cli-rollup-rotate-approved
description: Telemetry T4 (codey-metrics CLI, rollups.db, rotate.py) review — approved w/ warnings; live-reproduced a real --all short-circuit bug and a --help discoverability break the implementer didn't flag
metadata:
  type: project
---

Reviewed 2026-09-04: `telemetry/cli.py`, `telemetry/rollup.py`, `telemetry/rotate.py`,
`codey-metrics`, `tests/test_telemetry_cli.py`, `tests/test_telemetry_rotation.py`,
`install.sh` (3 sites). **APPROVED with warnings**, closes T4.

**The rotation crash-recovery claim was genuinely verified, not just read.**
`_archive_matches_source()` really does exact `event_id`-set equality (not count).
The two tests that supposedly distinguish "archive==source, don't rebuild" from
"archive!=source same count, do rebuild" actually do: read both bodies, confirmed
`test_rotate_rebuilds_archive_when_source_changed_after_crash` asserts
`source_ids != archive_ids_after_first` as an explicit precondition with matching
n=2 counts on both sides. Live-reproduced the one scenario neither the tests nor
the implementer's notes covered: rotated a synthetic day with a provenance+inference
record, then ran `doctor` against the post-rotation root and confirmed
`orphan_runs_no_run_start` stayed empty — archived provenance is still found via
`iter_records_for_date`'s archive fallback. This was the one check that could have
flipped the verdict; it held.

**Two real bugs found via live reproduction that neither the diff read nor the
implementer's summary surfaced — both from advisor's second pass, not the first:**
1. `main()`'s "prepend 'summary' if argv[0] isn't a known subcommand" rewrite also
   silently rewrites `--help`/`-h` into `summary --help`, so the top-level parser's
   own help (listing all 8 subcommands) is **permanently unreachable** by any argv a
   user would type. Confirmed live: `codey-metrics --help` only ever prints
   `summary`'s tiny help block.
2. `cmd_provenance --all`: `rc = rc or _print_run(...)` — once one run in the loop
   fails (rc becomes 1... actually the bug is subtler, live-reproduce it exactly, don't
   trust reading the line), subsequent runs' `_print_run()` output is silently dropped
   from `--all`'s output. Confirmed live with a 2-run fixture (first empty/invalid,
   second valid) — second run's output never printed.

Neither of these touches the destructive rotation/lock/kill-path (this project's usual
blocking bar per [[gui_c2_remediation_sequence]] / [[daemon_self_pid_check_verified]]
lineage), so both are Warnings not blockers — but both are genuinely reproducible bugs
a first read of the diff would miss. **Lesson: when a CLI's argv-rewrite logic is
"clever" (prepending a default subcommand), always live-test the flag/subcommand you'd
expect a user to reach for FIRST (`--help`) even if it's not in the review checklist** —
it's the cheapest live-repro that catches a real usability regression the diff's own
tests never exercised (no test in the 34 new tests calls `--help` at all).

Also: `deadbeefdeadbeef` and other synthetic-looking runs (`pid: 333`,
`started_ts_wall: 1234567890.0`) live in the real on-device
`~/.codeyOS/metrics/` from an earlier live-verification round, producing
`hard violations: 3` when `doctor` runs against the real store. Confirmed via
`grep -rl deadbeefdeadbeef tests/` (no match) this is NOT from T4's own tests —
this task's tests correctly use `tmp_path`/`--root` isolation throughout. Any future
review that runs `codey-metrics doctor` live against the real device store should
expect this pre-existing pollution and not attribute it to whatever diff is under
review that day.

Full suite: `pytest tests/ -q` → 1359 passed, 1 skipped, 201.98s (pasted verbatim,
ran in background via Bash run_in_background since it exceeds the 120s default).
