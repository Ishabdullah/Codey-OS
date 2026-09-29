---
name: b9_3_estimate_routes_preview_cost_leak_changes_requested
description: B9.3 EstimateService route wiring (15 routes) — round1 CHANGES REQUESTED, real cost-leak Critical found only via live repro
metadata:
  type: project
---

B9.3 wired the already-reviewed `EstimateService` (B9.1/B9.2) to 15 real HTTP
routes under `/api/v1/estimator/estimates/...`. Diff-read alone looked clean
and thorough (implementer disclosed two deliberate judgment calls, NEW-718
namespace collision avoidance and the `/decisions` manual permission gate,
both independently verified as genuine and correct). NEW-711's
`sqlite3.IntegrityError` → `ValueError` mitigation for a live contract_number
collision was also verified correct: scoped to exactly the one INSERT,
rollback semantics unaffected, and the regression test genuinely pre-creates
the real collision via the real `/api/v1/contracts` route rather than mocking
it.

**The bug the diff-read missed: `preview()` has no ownership narrowing and no
cost-field gating, unlike `get()` on the same service.** `EstimateService.get()`
calls `_can_view_estimate()` (ownership/assignment narrowing) and
`_attach_cost_fields()`/`_gate_line_cost_fields()` (gates cost/margin fields
behind `PERM_READ_ESTIMATE_COSTS`). `preview()` gates only on
`PERM_WRITE_ESTIMATES` and returns the engine's raw `EstimateResult` (via the
new `_json_safe()` serializer) with zero narrowing and zero cost-gating. Any
`PERM_WRITE_ESTIMATES` holder (e.g. ROLE_SALES, which does NOT hold
`PERM_READ_ALL_ESTIMATES`) can preview *any* estimate by id and see its full
`material_cost_cents`/`cost_total_cents`/`gross_profit_cents`/etc. — live
repro: same estimate, same unrelated sales-rep actor, `GET .../{id}` → 403,
`GET .../{id}/preview` → 200 with full cost data. This is the same bug class
this exact service already shipped once (B9.2's line-level cost-field leak,
see [[b9_2_estimate_service_changes_requested]]) — the cost-gating machinery
existed and simply wasn't reused on the new sibling read path.

**How the advisor caught it when diff-reading didn't:** I had already grepped
`dto.py` for `Decimal|class|@dataclass` (narrow, confirmed my
Decimal-serialization hypothesis) but never dumped the FULL field list of
`EstimateResult`/`LineResult` — this is rule-12's exact trap ("don't grep for
the keys you expect, dump the full set first"). The advisor pushed specifically
on the one route (`/preview`) I'd spent the least verification time on, by
name, and named the exact live-test shape needed (existing `sales2_tok`
fixture, ~8 lines). The 14 shipped tests never exercised this because every
`/preview` call in the test file used `mgr_tok`, who legitimately holds
`PERM_READ_ALL_ESTIMATES` — a same-role (ROLE_SALES vs ROLE_SALES), cross-actor
test would have caught it and none existed.

**Reusable technique:** when a service has two sibling read methods
(`get()` vs `preview()`, or similarly-shaped pairs elsewhere), diff their gate
lines side by side, don't assume the narrower-looking one "does the same
narrowing" from a docstring claim ("same as viewing your own draft, per
§1.9" was asserted but not true). Always dump full dataclass field lists for
any DTO returned raw through a new generic serializer like `_json_safe()` —
a generic converter has no per-field gating, so whatever the underlying
dataclass carries goes straight to the client.

See also: [[b9_2_estimate_service_changes_requested]], [[b9_2_round2_branch_divergence_approved]],
[[b9_2_next_slice_transition_toctou_round2_approved]], [[new710_estimates_assigned_user_id_rename_bug]].
