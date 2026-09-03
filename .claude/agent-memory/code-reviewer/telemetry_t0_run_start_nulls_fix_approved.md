---
name: telemetry-t0-run-start-nulls-fix-approved
description: T0 telemetry honest-null fix (record_run_start git/ram/swap/uptime fields) — round2 approved after live negative+positive control verification
metadata:
  type: project
---

Telemetry layer T0 (docs/telemetry_layer_design.md) round1 blocker: `record_run_start()`
silently omitted git_commit_sha/git_dirty/git_dirty_file_count/git_branch/ram_total_bytes/
swap_total_bytes instead of honest-nulling them when their collectors fail — invisible to
schema validation since an absent field passes null-checking.

Fix: `telemetry/provenance.py::build_run_start_nulls(body)` derives a `nulls` dict from
`body.get(field) is None` (git fields -> `git_command_unavailable`, ram/swap ->
`state_store_unreadable`), plus unconditional `device_uptime_sec` ->
`proc_uptime_permission_denied` via `always_keep_null={"device_uptime_sec"}` in `_emit()`,
mirroring `record_device_sample`'s existing pattern exactly.

Verified round2 (not just re-read): grepped `telemetry/schema/v1.json`'s `null_reason_codes`
directly for the 3 reason strings (all present); live-scripted both directions myself
(mock.patch `_run_git`/`get_ram_swap_bytes` to force failure, and unmodified real-git success
case) and confirmed via a mocked `store.record` capture that the null fields survive
`_emit()`'s pruning and land in the actual emitted record body — not just the intermediate
`nulls` dict. Full suite: 1307 passed / 2 pre-existing failures (embed_server slot tests,
unrelated) / 1 skipped — matches claimed baseline exactly, zero new regressions.

**Why:** this closes the honest-null-vs-silent-omission gap that made round1 a blocker —
absent fields pass schema null-checking cleanly, so the only way to catch this bug class is
to force each collector to fail and inspect the actual record body, not just read the code.

**How to apply:** for any future "honest null" claim in this telemetry layer (T1+), don't
trust that a `nulls` dict was built — verify it actually reaches the stored record past
`_emit()`'s pruning logic, via a captured `store.record` call, same technique used here.
Reusable pattern: `mock.patch.object(store, "record", side_effect=capture)` +
`mock.patch.object(provenance, "_run_git"/"get_ram_swap_bytes", ...)` to force each collector
failure mode independently and inspect `record["body"]` + `record["nulls"]` together.
