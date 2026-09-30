---
name: f1-portal-estimates-customer-view-approved
description: F1 fix (portal estimates list routed through to_customer_view()) — APPROVED round 1, with a false NEW-720 cross-reference caught
metadata:
  type: project
---

F1 (`GET /api/v1/portal/estimates` leaking raw `Estimate.to_dict()` instead
of the `to_customer_view()` allow-list) — APPROVED 2026-09-30. Fix maps each
`crm.list_estimates()`-sourced id through `self.estimates.to_customer_view(e.id)`
instead of `.to_dict()`, confirmed as the exact same method B9.4's public
share-link route already used (traced both call sites, not just grepped the
function name).

**Two-pass mutation technique for recursive leak tests**: a first mutation
injected a leaked field at the *top level* — it only proved the shallow
`leaked_field in view` explicit-list check fires, not the `_walk()`-based
recursive walk the test also has. Advisor caught this. Had to redo the
mutation *one level nested* (`v["lines"][0]["burden_cost_cents"] = 7`) with a
key name not already in the shallow list, to prove the recursive walk
specifically is the one that fires. Always mutate at the deepest plausible
nesting level with a novel key name, not the top level, when validating a
"walks the full tree" leak-check claim — see [[b9_3_estimate_routes_preview_cost_leak_changes_requested]]
for the original Critical this pattern guards against (nested `LineResult.input`
cost echo a top-level-only gate missed).

**False cross-reference caught, not just a vacuous one.** The implementer's
disclosed gap ("`to_customer_view()`'s dict has no `id`/`status`, so a portal
list is indistinguishable blobs") was itself accurate and independently
verified (dumped `CustomerEstimateView.to_dict()`'s real key set from
`codey_estimator/dto.py`). But the implementer claimed "NEW-720 already
covers this" — reading NEW-720's actual text showed it's a *different* bug
entirely (a CANCELLED estimate's share-link view route not being gated).
Same for a second citation to NEW-718 (actually about route-namespace
collision, not about legacy rows lacking `current_version_id`). **A
ticket-number citation is a claim like any other — read the cited entry's
actual body before accepting "already covered by NEW-###," even when the
underlying technical claim next to it checks out.** Don't let a plausible-
sounding NEW-### citation substitute for reading NEW_ISSUES.md at that line
number.

**Deciding "disclosed gap vs. live regression"**: the decisive check was a
full-repo grep (`.py`/`.js`/`.html`, not just `.js`/`.html`) for the route
path string (`portal/estimates`) to confirm zero UI consumers exist yet —
that's what makes a real, confirmed functional gap non-blocking rather than
a live regression. If a consumer had been found reading `.id`/`.status` off
the list, the verdict would have had to flip.
