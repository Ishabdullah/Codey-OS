---
name: new628-technician-operations-rbac-narrowing-approved
description: NEW-628 ROLE_TECHNICIAN row-level narrowing of 9 operations_service.py read methods, plus deploy_equipment self-race fix — APPROVED round1
metadata:
  type: project
---

2026-09-25, `restoricon_core/services/operations_service.py` +
`tests/test_restoricon_core/test_operations_domain_engine.py` +
new `tests/test_restoricon_core/test_new628_technician_operations_ownership_narrowing.py`
(23 tests). APPROVED round1, no Critical.

**Discriminator for "does a post-write re-read need to bypass RBAC"**: check
whether the write mutates the exact column the narrowing check keys on. In
this diff, `deploy_equipment` sets `current_project_id = project_id` in the
same write whose audit trail needs a post-read of that equipment — and
`get_equipment`'s new technician narrowing keys on `current_project_id`. That
combination is a real self-race (own-write RBAC re-check denies the actor's
own just-completed write), matching this project's known self-referential-race
bug class (see [[working_tree_cross_round_bleed]] sibling entries on
PID-file races). Fix was a raw SELECT bypass reusing the already-RBAC-cleared
`equipment_id`, not re-deriving it from input — safe. Other post-write
re-reads in the same file (`update_work_order_execution_status`,
`dispatch_work_order`, `accept_work_order` all re-read via
`self.get_work_order(...)` after their UPDATE) do NOT have this race, because
none of those writes change `work_orders.project_id` — the field the
narrowing keys on. Systematically check "does this write touch the narrowed
column" before accepting or rejecting a bypass claim.

**Branch-ordering check for a new `elif ROLE_X` narrowing behind an existing
`elif self._actor_reaches_only_via_sold_projects(...)` gate**: read the
gating helper's actual condition (here: requires `not
actor.has_permission(PERM_READ_OPERATIONS)`) against the new role's *built-in*
permission set in `auth.py` (ROLE_TECHNICIAN always holds
`PERM_READ_OPERATIONS`). If the built-in grant makes the prior `elif`
permanently unreachable for that role, the new branch is safe purely by
elimination — don't just trust "elif order looks right," trace both
conditions' truth values for the specific role.

**Internal-caller sweep, done systematically not ad hoc**: python3 regex scan
(not grep — still shimmed/broken in this shell) for every `self.<narrowed_method>(`
call site across the whole package, not just the 2-3 obvious ones. Caught
that all such calls live inside the one file already reviewed, and
distinguished `CRMService.get_project` (a same-named but different method on
a different class) from the actually-narrowed `OperationsService.get_project`
— don't let a same-name grep hit register as a caller of the changed method
without checking which class it's actually bound to.

Disclosed-but-out-of-scope gaps independently confirmed real by reading the
methods directly: `return_equipment` has zero ownership narrowing at all
(flat permission gate only); `deploy_equipment` never validates its target
`project_id` against the technician's assignment (equipment ownership is
checked, target project is not). Read-path is narrowed this round; write-path
stays org-wide for ROLE_TECHNICIAN — say this explicitly in the ledger entry,
don't let "NEW-628 closed" read as "operations RBAC fixed."

Test-count claim mismatch again (see [[admin_dashboard_partB_kpi_consolidation_approved]]
precedent): implementer claimed 1058/1058 after excluding 4 files; my own
full run of `tests/test_restoricon_core/` with `HTTP_PROXY` unset (per
[[sandbox_http_proxy_urllib_405_env_artifact]]) needed zero exclusions and
passed 1157 + 23 deselected = 1180. Didn't block on the mismatch since my own
number is strictly stronger evidence (a full clean run beats a smaller
exclusion-laden claim), but always reproduce the claimed number yourself
rather than repeating it in the ledger.
