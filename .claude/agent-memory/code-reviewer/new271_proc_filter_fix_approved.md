---
name: new271-proc-filter-fix-approved
description: NEW-271 svc_entrypoint_proc_filter() fix (proc_filter hardcoded "node" at 3 Aigentik call sites) — APPROVED, negative-controlled directly
metadata:
  type: project
---

Round 1 review 2026-09-09 of `lib/service_manager.sh` +
`tests/test_service_manager_config.py`, scoped diff only (parallel
working tree had other uncommitted files not reviewed).

## Verdict: APPROVED

- `svc_entrypoint_proc_filter()` maps `.py`→python3, `.sh`→bash, `.js`→node,
  `""`→"", `*`→literal script (dead fallback, mirrors
  `svc_entrypoint_command`'s existing pattern). `svc_detect_entrypoint_script`
  only ever returns from a fixed whitelist (main.py/app.py/server.py/run.sh/
  index.js/start.sh) — all 3 extensions covered, fallback arm unreachable
  today, same as the pre-existing sibling function. Not a gap.
- Real `~/Codey-Aigentik` still resolves to `index.js` (verified directly:
  `package.json` main/start both `index.js`, `index.js` present, comes before
  `start.sh` in the detection order) → `proc_filter` still literally `"node"`
  for the real service. Zero behavior change for the actual current Aigentik.
- **NEW-268 flock interaction verified by reading the actual `(...)` subshell
  boundaries, not trusting the claim**: `proc_filter` (like `entry_script`/
  `entrypoint`) is assigned at line 294-297, *before* the `(` at line 334 that
  opens NEW-268's locked subshell; it's only read (line 360) inside. A bash
  subshell can read but not write back to parent-scope variables, so if this
  had been computed inside the lock instead, it would be silently invisible
  outside — it is not. Fix is correctly ordered.
- `stop_aigentik`/`status_aigentik` mirror the same ordering (compute before
  any locking/scanning use), consistent across all 3 call sites.
- **Negative-controlled myself** (not just trusting the implementer's claim):
  reverted all 4 `svc_find_orphans_by_cwd "$a_dir" "$proc_filter" ...` call
  sites back to literal `"node"`, reran the new end-to-end test
  (`test_status_aigentik_detects_python_entrypoint_orphan`) — it failed
  exactly as predicted (`UNTRACKED orphan` absent, only "stopped" printed).
  Restored the real fix, test passes again. This is real regression coverage,
  not a tautological unit test on the helper alone (the earlier two tests in
  the same diff also pass but only exercise the helper / `svc_find_orphans_by_cwd`
  directly — the 3rd test is the one that actually proves the call-site fix).
- Full suite: `python -m pytest tests/ -q` → 1542 passed, 3 failed (unrelated:
  `test_new118_shutdown_short_circuit`, `test_new256_handle_health_task_timeout`,
  `test_new88_embed_watchdog_logs` — daemon watchdog/health-check tests, zero
  overlap with `service_manager.sh`/Aigentik). All 3 passed cleanly when rerun
  in isolation (`6 passed in 0.63s`) — consistent with flaky-under-full-suite-
  load, not a regression from this diff. Note: the implementer's own claimed
  flaky set was `test_context_budget.py` (fully mocked/synthetic per its own
  docstring, no thermal gating logic actually present in that file at all —
  the "thermal-throttle-gated" framing doesn't hold up on inspection, though
  it didn't fail in my run either). **Lesson for future reviews: don't accept
  a specific mechanism ("thermal-throttle-gated") for a flaky-test claim
  without grepping the named file for that mechanism — this project's full
  suite does have real cross-run flakiness under load, but the *why* offered
  isn't always accurate. Downgrade "thermal-throttle-gated" to just "flaky
  under load, unrelated to this diff" absent evidence.**

## Gotcha for future service_manager.sh reviews
`svc_find_orphans_by_cwd`'s `$2` uses `${2:-node}` — an *empty string* arg
(not just an unset one) also falls back to `"node"` under bash's `:-`
operator. This is currently safe because all 3 real call sites guard on
`entry_script` being non-empty before ever calling the scan (empty
`entry_script` short-circuits to a report-only path), so `proc_filter` is
never empty when the scan actually runs. If a future change loosens that
guard, re-check this fallback — it would silently degrade back to the
NEW-271 bug for exactly the entrypoints that need the fix most.
