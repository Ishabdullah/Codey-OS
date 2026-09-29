---
name: b8_6b_estimate_pricing_package_options_round2_approved
description: B8.6b round 2 — customer-isolation gate + return-redaction fixes on update_estimate/send_estimate verified, APPROVED 2026-09-22
metadata:
  type: project
---

Round 2 of [[b8_6b_estimate_pricing_package_options_changes_requested]].
Both round-1 findings genuinely fixed:

1. Customer-isolation gate (`actor.role == ROLE_CUSTOMER and (not
   actor.customer_id or actor.customer_id != row["customer_id"])`) added
   to both `update_estimate`/`send_estimate`, placed correctly before the
   rep-ownership narrowing branch, matching `get_estimate`'s exact
   condition.
2. Both methods now re-select the row post-write
   (`updated_row = conn.execute("SELECT * FROM estimates WHERE id = ?;"
   ...)`) and return `self._row_to_estimate(updated_row, actor.role)` —
   genuinely re-masked. `update_estimate`'s empty-updates early-return
   goes through `get_estimate` (which has its own full gate+redaction),
   so both paths now produce identical masked shape — verified via a
   test that checks the SAME actor through both the empty-update path
   and the normal-update path (`test_update_estimate_response_redacts_
   cost_fields_for_customer_and_technician`).

Also verified: both `_compute_line_item_costs` and
`create_package_option`'s item loop wrap `float(item.get(...))` in
`try/except (TypeError, ValueError)` raising a clean `ValueError` —
explicit-null-quantity tests exist and are non-vacuous
(`test_compute_line_item_costs_rejects_explicit_null_quantity`,
`test_create_package_option_rejects_explicit_null_quantity`).

Full suite re-run myself (proxy vars unset): verbatim `2178 passed, 1
skipped, 69 warnings in 254.89s (0:04:14)` — matched implementer's claim
exactly, first time in this project's B8.x history the two independent
full-suite numbers (coordinator's + reviewer's) were both captured and
matched verbatim rather than trusted on say-so.

**Pattern confirmed working**: when round 1 finds "sibling method copied
gate A but not gate B," round 2's fix should be checked not just for gate
B's presence but its exact placement relative to gate A and to the
existing early-return paths — a gate added in the wrong order, or a
redaction fix that only covers the "normal" path and misses an
early-return path, is the next place this bug class hides. Here the
early-return was specifically tested against, which is the right level
of rigor.

No new findings this round; diff scope was unchanged from round 1 except
for the described fixes (verified via full `git diff` of all 4 tracked
files, not just the two touched methods).
