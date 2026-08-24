---
name: m1f-resource-gate-constants-closed
description: M1-F (NEW-156) resource_gate.py constant re-derivation, 2026-08-24 — values, the NEW-179 invariant catch, and status
metadata:
  type: project
---

M1-F (`NEW-156`) closed 2026-08-24: re-derived `MAX_CONCURRENT_MODEL_BUDGET_BYTES`
(8.90GiB → 7.00GiB) and `MAX_SWAP_ASSIST_BYTES` (10.00GiB → 6.50GiB) in
`core/resource_gate.py` for the single-model Qwen3.5-4B architecture (§1.4/M1-D).
Files touched: `core/resource_gate.py`, `tests/test_resource_gate.py`,
`tests/test_loader_resource_gate.py` (stale-prose fix only), plus the three
tracking docs (`CODEY_MASTER_PLAN.md`, `PROJECT_LOG.md`, `NEW_ISSUES.md`).

**Why the value isn't a straight "raw sum + margin" calc:** `MAX_CONCURRENT_MODEL_BUDGET_BYTES`
has two independent floors — the concurrent raw sum (~5.18GiB here) AND
`compute_device_ceiling_bytes()` (~6.49GiB on this device). A first-pass value
derived from the raw sum alone (5.25GiB) sat BELOW the device ceiling, which
inverts rule 12 (hard_reject should be the absolute per-model bound) — a single
model near the device ceiling got wrongly refused via `budget_ceiling_exceeded`.
This was previously undocumented as a requirement and had no test pinning it
(logged as `NEW-179`, fixed same round with `test_max_concurrent_budget_at_least_device_ceiling`).
**How to apply:** any future re-derivation of this constant must check BOTH
floors (`max(raw_sum + margin, compute_device_ceiling_bytes())`), not just the
raw sum — the existing single-model test suite (`test_hard_ceiling_boundary_flips_hard_reject`
et al.) is what will catch a regression here; run the full suite before trusting
a new value, not just the new constant's own pinned-value test.

`NEW-180` spun off: embed model's real resident RSS has never been measured
(every derivation since 7.4a sub-task C1 uses the same file-size-only floor,
352,542,080 bytes) — not currently load-bearing at the new margins, but still
open.

**Status honestly recorded:** code-complete + self-reviewed only. No
code-reviewer subagent was available in this session's tool set (only Read/
Bash/Edit/Write/advisor) — the mandatory rule-4 review pass for this
model-load-admission-gating change is still outstanding and should be the
next step before this is considered fully done. Not live-verified either
(M1-F is arithmetic re-derivation from M1-E's already-live numbers, not a
fresh live pass of its own — consistent with M1-F's own scoping).

See also [[project_work_queue_pointer]] for where M1-F sits in the phase order.
