---
name: b8_12a_sales_project_ownership_narrowing_approved
description: B8.12a ROLE_SALES project/operations RBAC narrowing (removes PERM_READ_ALL_PROJECTS/PERM_READ_OPERATIONS over-grant, adds PERM_READ_OWN_SOLD_PROJECTS) -- APPROVED round1, zero blocking findings
metadata:
  type: project
---

2026-09-24. Files: `restoricon_core/auth.py`, `restoricon_core/services/crm_service.py`,
`restoricon_core/services/operations_service.py`, `tests/test_restoricon_core/test_b8_12a_sales_project_ownership_narrowing.py`
(21 tests). Removes a real, live company-wide over-grant (NEW-628) from
`ROLE_SALES` rather than adding access -- reviewed with removal-side regression
risk weighted equally with narrowing-side security correctness, per CLAUDE.md
rule 4.

**Verified independently (not just re-reading the diff or trusting the
implementer's own 21 tests):**
- Wrote a standalone script exercising `list_projects(customer_id=X)` AND
  precedence (subquery correctly AND-ed, not OR'd, with the `customer_id`
  filter -- two customers each with a rep-owned project, filtered result
  correctly scoped to one), the NULL-`assigned_user_id` fail-closed case via
  raw SQL UPDATE, and `ROLE_SALES_MANAGER`'s equipment-visibility loss
  (NEW-630) -- all matched the implementer's claims.
- Dumped `ROLE_PERMISSIONS[ROLE_SALES]` and the `ROLE_SALES_MANAGER`-only
  diff directly (`sorted(ROLE_PERMISSIONS[...])`) rather than inferring from
  grep -- confirmed only `ROLE_SALES_MANAGER` derives from `ROLE_SALES`'s set
  (`ROLE_PERMISSIONS[ROLE_SALES_MANAGER] = ROLE_PERMISSIONS[ROLE_SALES] |
  {...}` is the only such derivation in the file), and confirmed `ROLE_SALES`
  does NOT hold `PERM_READ_ASSIGNED_PROJECTS`/`PERM_READ_OWN_PROJECTS` today.
- Traced every internal caller of the six narrowed methods
  (`get_project`/`list_projects`/`get_milestone`/`list_milestones`/
  `get_work_order`/`list_work_orders`) via grep across `restoricon_core/` --
  all either sit behind write-permission gates `ROLE_SALES` already lacks, or
  are routes.py handlers protected by the file's single global
  `except PermissionError: return 403` wrapper (line ~3348) -- no bare
  internal caller can turn a narrowed denial into an uncaught 500.
- Mapped every remaining `PERM_READ_OPERATIONS`-only gate in
  `operations_service.py` (grep for the constant) to confirm the *only*
  other ones left are equipment/deployment methods (disclosed, intended) and
  `get_active_work_orders_for_subcontractor` (admin subcontractor-delete
  precheck, not sales-portal-reachable) and
  `match_subcontractors_for_trade` (has an OR with `PERM_READ_SUBCONTRACTORS`,
  which `ROLE_SALES` still holds) -- no undisclosed sales-portal regression.
- Full suite: 2419 passed, 1 skipped, matching the claimed 2398->2419 (+21)
  verbatim.

**One Warning found that the implementer didn't disclose** (advisor caught
it, not the first read-through): `crm_service._actor_lacks_sold_project_ownership`'s
bypass check only exempts `PERM_READ_ALL_PROJECTS`/`PERM_READ_TEAM_SALES_DATA`,
NOT `PERM_READ_ASSIGNED_PROJECTS`/`PERM_READ_OWN_PROJECTS` -- both independent
entitlements in `get_project`'s own outer gate. A hypothetical actor holding
`PERM_READ_OWN_SOLD_PROJECTS` *and* one of those (e.g. via a future
`custom_permissions_json` grant) would be narrowed *below* what the weaker
permission alone grants -- contradicts the helper's own docstring claim that
a custom grant "is narrowed identically." Not live-reachable today (confirmed
via the permission dump above), so didn't block approval, but flagged for the
ledger. The `operations_service.py` helper (`_actor_reaches_only_via_sold_projects`)
does NOT have this asymmetry -- it exempts both flat ops gates symmetrically.

**Lesson for next RBAC-narrowing round:** when a permission is *removed* from
a role (not just added), the advisor's push to trace every internal caller of
the newly-gated methods is the right instinct even when a global
`except PermissionError` wrapper exists -- don't assume it exists, confirm it
by reading the actual except-clause count and placement. This matches
[[new568_customer_rep_narrowing_changes_requested]]'s pattern (that round's
real bug was exactly an untraced internal caller) but this round came back
clean because the codebase's routes.py has a single global 403 handler this
round's methods all flow through.

Verdict: **APPROVED round1**, zero blocking findings. NEW-630 correctly
characterized as a Warning needing Ish's product decision (visibility loss,
not a security hole) -- ledger entry's fix direction is correct (compensate
on `ROLE_SALES_MANAGER`'s own derived block, never re-grant to `ROLE_SALES`).
Noted for coordinator: `.claude/agent-memory/code-reviewer/MEMORY.md` carried
a pre-existing ~150-line unstaged condensation diff from an earlier round,
unrelated to B8.12a -- out of scope for this review's staging.
