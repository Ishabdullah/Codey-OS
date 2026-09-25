---
name: b8_13a_subcontractor_audit_layering_opportunity_559_approved
description: B8.13a — delete_subcontractor audit-layering move, NEW-595/580/559 fixes — APPROVED round1, one Warning (test-count claim off by one)
metadata:
  type: project
---

Reviewed 2026-09-25, scoped diff (routes.py, crm_service.py, and 3 test
files only — a parallel B8.13b mobile-CSS round was concurrently editing
web_surfaces.py/test_sales_portal_dashboard_panels.py in the same tree,
correctly excluded from this review per explicit caller instruction).

All 4 claims verified true, independently:
- delete_subcontractor audit call moved from routes.py into
  CRMService.delete_subcontractor() itself (matches delete_contact's
  byte-for-byte structure: DELETE inside `with conn:`, early-return on
  rowcount==0 still inside the block — a `return` inside `with` still
  runs `__exit__`/commits — audit.log() call unambiguously after/outside
  the block). Independently live-repro'd via a standalone script (not
  the implementer's own test): both the HTTP-route path and a direct
  service-layer call each produced exactly one audit_log row, not zero,
  not two. Only one call site of delete_subcontractor() exists repo-wide
  (the route) — no other caller silently started emitting audit entries.
- NEW-595 (per-signer side_effects attribution): `signed_party_details`
  only ever gets set inside the `else:` (multi-party, signer_rows
  non-empty) branch; the legacy single-signer path (`if not
  signer_rows:`) never touches it, so side_effects there stays exactly
  `{"signature_captured": True}`. Structurally guaranteed, not just
  tested.
- NEW-580 (sign_contract anti-vacuity test): read directly, confirms
  `"status" in changed_fields` genuinely asserted alongside the
  exclusion checks.
- NEW-559 (`_after = opp` instead of `self.get_opportunity(opp_id,
  actor)`): verified `get_opportunity` is a plain row_to_dataclass
  conversion (`_row_to_opportunity`) with zero enrichment — its ONLY
  extra behavior is a permission-gated visibility check that can return
  None. `opp` is mutated in-place with every field the UPDATE statement
  writes (pipeline_stage, probability, lost_reason, stage_entered_at,
  notes, updated_at) before `_after = opp`, so it's a genuine match for
  what a fresh read would return. Also checked `Opportunity.to_dict()`
  = `dataclasses.asdict(self)` — Opportunity has zero nested
  dataclass/list/dict fields (all flat scalars), so `_before =
  opp.to_dict()` at the top of the function is a genuinely clean snapshot,
  immune to the later in-place mutation of `opp`. No test in this diff
  exercises this specific claim directly (no new
  transition_opportunity_stage audit test) — noted as a gap, not a
  blocker, since the equivalence was verified by code reading + the
  existing (unmodified) transition_opportunity_stage test suite passing.

One Warning (non-blocking): implementer claimed 2454→2458 (+4) for "own
scope," but the scoped diff's 3 test files contain exactly 3 new test
functions (one each), not 4 — verified via `git show HEAD:<file> | grep
-c '^def test'` vs working-copy count, all three files +1. The 4th
passing-suite-count difference likely comes from the concurrently-edited
B8.13b round already present in the same working tree (task brief
flagged this as expected), not a phantom 4th test in this round's own
files. Full suite run today: 2458 passed, 1 skipped (381.86s) — matches
literally, no regressions attributable to this round.

Lesson: **always independently live-repro count-based claims ("exactly
one audit entry") with a standalone script, not by re-running the
implementer's own test file** — a test can only prove what it was
written to check, and a double-log bug that both the old and new test
share a blind spot on would still show a clean pytest run. Matches
[[b8_5b_assessment_photo_round2_approved]]'s lesson but this is the
first round where the reviewer used a from-scratch scratchpad script
(not the modified test file at all) for the differential repro, calling
both the route path and the raw service method in one process against
two separate `:memory:` DBs — cheap and unambiguous.
