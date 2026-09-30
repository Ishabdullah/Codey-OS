---
name: b9_5_estimates_ui_surface_approved
description: B9.5 staff estimator builder UI (/estimates) — APPROVED round 1; quantity-field falsy-zero JS pattern investigated and empirically ruled a non-bug
metadata:
  type: project
---

B9.5 (`render_estimates_surface()` in `restoricon_core/api/web_surfaces.py` +
`/estimates` route in `restoricon_core/api/routes.py` + new test file,
2026-09-30) — APPROVED on round 1, no changes requested.

**What held up on direct verification** (not just the docstring's claim):
- XSS discipline: every dynamic value in the customer-search-results list
  and line-items table goes through `escapeHtml()`; no `onclick`/`oninput`
  ever inlines `JSON.stringify(obj)` — confirmed by reading
  `estSearchCustomers`/`estSelectCustomer`/`estRenderLineItems`/
  `estUpdateLineItem` directly (index-based lookup only).
- Focus-preservation: `estUpdateLineItem()` (oninput, fires every keystroke)
  mutates the array only, never calls `estRenderLineItems()`;
  `estRenderLineItems()` only fires from load/add/remove.
- The self-disclosed fix (generic Qty/Unit-Cost inputs → read-only,
  per-line-type-resolved display, only `description` inline-editable) is
  genuinely in the code, and the read-only resolution order
  (`unit_cost_cents` → `labor_cost_rate_cents` → `equipment_cost_cents` →
  `sub_cost_cents`) matches `codey_estimator/calc/engine.py`'s actual
  `_validate_line` per-line-type field requirements (read directly, lines
  85-116).
- `maybeSet`'s exact condition (`val !== null && val !== undefined && val
  !== ''`) is correct, and every money/percent field routes through
  `estDollarsToCentsOrNull`/`estPercentToBpOrNull` before reaching it.
- Cost-field null-safety in `estRefreshPreview()`: checks
  `gross_profit_cents !== null && !== undefined`, hides the margin row
  entirely rather than computing a partial value — matches B9.3's
  `_gate_preview_result_cost_fields()`.
- Share-link token is set via `textContent`, never `innerHTML`.
- NEW-722 (no staff web-surface GET route is RBAC-gated at render time,
  pre-existing across /sales/pm/tech/subcontractor, not introduced here):
  all three claims verified directly against `routes.py:handle_request` —
  the web-surface GET dispatch block (~line 500-540) genuinely runs before
  `actor = self.auth.authenticate_token(token)` (line ~689/702). Severity
  characterization (low, no server-rendered dynamic value, all real
  data-bearing calls gated at the service layer) holds up.
- Full suite: 1453 passed, matching the implementer's claim exactly,
  verbatim (`python -m pytest tests/test_restoricon_core/ -q` with proxy
  env vars unset, 257s).

**A hypothesis I raised and then ruled out empirically** (worth recording
so it isn't re-flagged as a false positive next time): the raw
`parseFloat(x) || null` pattern used for `quantity`/`labor_qty` (as
opposed to `estDollarsToCentsOrNull`/`estPercentToBpOrNull` used for money/
percent fields) conflates a user typing "0" with leaving the field blank —
both produce `null` and get omitted from the request body by `maybeSet`.
This looked like it would contradict the code's own stated discipline
("explicit 0 must never be silently overridden"). Traced it end-to-end
with a live repro (`EstimateService.add_line()` with `unit_cost_cents=500`
and `quantity` key omitted entirely) and found `_row_to_line_input()`
(estimate_service.py:1180) already defaults a missing `quantity`/
`labor_qty` to `Decimal(0)` when the column is `None` — i.e. the server's
own "omitted" default is the same value the omitted key would have
produced anyway, so there's no divergence in outcome. Only
`material_markup_bp` has a non-zero omission-default (30%), which is
exactly the field the code's `estPercentToBpOrNull` treats correctly
(explicit "0" input round-trips as `0`, not `null`). So: no bug, but the
lesson is generalizable — before flagging a "falsy zero vs. omitted key"
pattern as a money bug, check what the *server's actual default-when-
absent* is for that specific field; they can coincide.
