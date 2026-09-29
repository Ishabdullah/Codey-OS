---
name: b8_6b_estimate_pricing_package_options_changes_requested
description: B8.6b server-side estimate pricing + PackageOption table (NEW-574) — CHANGES REQUESTED 2026-09-17, missing customer-isolation gate + unredacted return leak on update_estimate/send_estimate
metadata:
  type: project
---

Reviewed 2026-09-17 (uncommitted, rule-4 gate). `crm_service.py`
(`_compute_line_item_costs`/`_compute_estimate_total`/
`_apply_estimate_pricing`, `update_estimate`, `send_estimate`,
`create_package_option`/`list_package_options`), `models.py`
(`PackageOption`), `database.py` (`package_options` table), `routes.py`,
new test file.

Pricing formula, override-vs-reject create/update distinction, rep-
ownership narrowing on raw-row reads, idempotent send_estimate, package
redaction (the implementer's two self-caught bugs — money-visibility
leak and orphan `estimate_id=None` — both genuinely fixed), SQL
parameterization, and the full suite (2172 passed, 1 skipped, matched
claim) all verified correct.

**Real bug pattern found**: `get_estimate` has TWO authorization gates —
a `ROLE_CUSTOMER`-vs-`row["customer_id"]` isolation raise, AND a
`PERM_READ_TEAM_SALES_DATA`-gated rep-ownership narrowing (`if
actor.role != ROLE_CUSTOMER and not actor.has_permission(...)`). New
sibling methods `update_estimate`/`send_estimate` only copied the SECOND
gate — a `ROLE_CUSTOMER` actor falls through `actor.role != ROLE_CUSTOMER`
with zero scoping. Unreachable via default role permissions today
(`ROLE_CUSTOMER` lacks `PERM_WRITE_ESTIMATES`), BUT
`AuthContext.has_permission` checks `custom_permissions` before role
defaults, and `_validate_custom_permissions` only checks catalog
membership, not role-compatibility — so an admin CAN grant
`write:estimates` to a customer-role user via `custom_permissions_json`
(this project's own `_scoped_assignee_filter` comment explicitly states
permission grants are "keyed on permission, never actor.role" as
deliberate design, and NEW-533 sales_manager custom-grant precedent shows
this mechanism is live, not theoretical). Under that grant a customer
could update/send ANY customer's estimate.

**Compounding leak**: `update_estimate`/`send_estimate` return
`self._row_to_estimate(row)` with NO `actor_role` arg — unlike
`list_package_options`' two call sites (which correctly pass
`actor.role`, the implementer's own self-caught-bug fix pattern applied
inconsistently). Response body leaks unmasked
`materials_cost`/`labor_cost`/`subcontractor_cost`/`markup_percent`/
`notes` under the same reachability gap. Also: `update_estimate`'s
`if not updates: return self.get_estimate(...)` early-return is masked
while the normal path isn't — two response shapes from one method.

**Pattern for future reviews**: when a diff adds a sibling method to an
existing one (`update_X`/`send_X` next to established `get_X`), diff the
FULL set of authorization checks side by side, not just the ownership-
narrowing one that's usually the focus — a customer-isolation check that
looks orthogonal/redundant at a glance is often NOT copied by the new
method even when the rep-ownership check is. Also: whenever a method
does a raw/unmasked row read for write purposes (`_row_to_estimate(row)`
with no role, matching `update_project`'s established precedent for
reading), separately verify what gets RETURNED to the caller — the raw
read is often correct and necessary, but the return value needs to be
re-masked before serialization; these are two different bugs (read-side
is fine here, return-side leaks).

Also useful: reachability of a "theoretical" RBAC gap should be checked
against `_validate_custom_permissions`/`custom_permissions_json` before
downgrading it to a Suggestion — this project's permission model is
explicitly role-independent by design (see [[b8_6a_estimates_contracts_rep_ownership_approved]]
for the sibling PM-regression precedent of taking permission-keyed design
seriously), so "no default role reaches this" is not the same as "this
can't happen."
