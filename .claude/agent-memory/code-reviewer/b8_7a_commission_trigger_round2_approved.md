---
name: b8-7a-commission-trigger-round2-approved
description: B8.7a commission-trigger round 2 — plan-config-outside-try fix verified fixed, APPROVED
metadata:
  type: project
---

2026-09-22, round 2 of [[b8_7a_commission_trigger_plan_outside_try_changes_requested]].
APPROVED. One-line move (`plan = self.commission.get_commission_plan_config(...)`
into the `try:` block, immediately before `record_commission(...)`) confirmed
correct via three independent checks, not just re-reading the diff:

1. My own standalone monkeypatch+DB-state script (separate from the
   implementer's shipped test) — `record_payment` no longer raises,
   invoice status is `paid`, zero commission rows, one
   `commission_recording_failed` audit entry.
2. Manually reverted *just* the fix (moved the line back outside `try:`,
   reproducing the exact round-1 bug shape) and reran the new test in
   isolation — it failed with the identical `RuntimeError` propagating
   out of `record_payment`, proving the test is a real regression guard
   and not vacuously passing. Then restored the fix and reconfirmed green.
3. Read the new 9th test directly (`test_get_commission_plan_config_raising_does_not_fail_the_already_committed_payment`,
   `tests/test_restoricon_core/test_b8_7a_commission_trigger.py:278-312`) —
   exercises this exact scenario, not a weaker proxy.

**Reusable technique confirmed valuable again:** for a one-line
try-block-boundary fix, don't just confirm the line moved — temporarily
re-break it (revert just that line, not the whole diff/file) and rerun
the specific regression test to watch it fail with the *original*
symptom, then restore and rerun green. This is cheap and catches both
"fix doesn't actually work" and "test doesn't actually test the claimed
bug" in one motion. `git stash` on a single file is the wrong tool here
if the whole diff is one feature (stashing reverts the entire feature,
not just the fix) — use `Read` + `Edit` to surgically re-break only the
specific lines, then `Edit` back.

**Full suite this round:** `2252 passed, 1 skipped, 69 warnings in 369.78s`
run from repo root with proxy vars unset — matched the implementer's
claimed figure verbatim. Took ~6 minutes and required backgrounding
(spawns a `multiprocessing.forkserver` subprocess — watch for a
long-running but *actively progressing* `python -m pytest -q` via
`ps aux | grep pytest`, distinct from a genuine hang; CPU% climbing and
child forkserver process present = it's working, not stuck). Confirmed
via `ps aux` while it ran, not just trusted the eventual exit code.
Reconciled against round 1's differing "2137 passed" figure: that was
`tests/` only, this run picked up `ccos/tests/` too (visible via the
`ccos/tests/test_telemetry.py` warnings in the tail output) — a genuine
scope difference, not a discrepancy.

All round-1-approved items (partial unique index
`idx_commission_ledger_source_unique`, FK-violation handling, double-fire
protection, system-actor pattern) re-checked present and unchanged —
this round's diff touched only the try-block boundary in `crm_service.py`.
No scope creep (`git status --short` matched round 1's file set plus the
new test file). The 5 out-of-scope findings from round 1 all still stand
unchanged.
