---
name: b6-2b2-audit-details-crm-update-sites
description: B6.2b-2 — 11 crm_service.py real-update audit sites migrated to build_audit_details before/after. APPROVED w/ 1 Warning (update_project audit-gap on custom-perm write-without-read).
metadata:
  type: project
---

B6.2b-2 (2026-09-02): 11 `crm_service.py` update sites → `build_audit_details`
before/after. +`_AUDITABLE_PROJECT_FIELDS` frozenset (NEW-314, excludes nothing,
drift guard — verified exact match vs `Project.to_dict()` keys via live compare).

**APPROVED.** new file 21/21; `tests/test_restoricon_core/` 309 passed, zero
regressions (incl. `test_b6_1_update_project.py` noop-bump-no-audit still green).

Verified sound:
- `_before` capture strictly above first mutation at every getter site
  (update_lead/opportunity/task/complete_task/transition). `to_dict()` returns a
  fresh dict so the snapshot is frozen against later setattr on the live object.
- update_lead/update_opportunity/update_task/transition all call `get_*()` at the
  TOP of the method, so the post-mutation `_after = get_*()` can NEVER newly
  raise. update_project is the sole exception (deliberate raw `SELECT *`, no
  up-front getter) — see Warning.
- update_customer `_before[k]=row[k]`: every non-json member of
  `ALLOWED_CUSTOMER_UPDATE_FIELDS` is a real `customers` column; keys validated
  against the allow-list before the loop; the `_before` loop runs before the
  UPDATE anyway. No KeyError past point of no return.
- `_cadence_tasks=[]` initialized before the `try` — no NameError on except path.
- generate_cadence_tasks returns `List[Task]`; `t.rule_name`/`t.title`/`t.id` all
  real. cadence task's own `create` audit row is separate & expected, not a
  double-log. update_opportunity→transition delegation logs exactly one row
  (action="stage_transition"); update_opportunity returns early, no second log.
- sign_contract/record_payment hand-built `_signed`/`_updated` literals mirror the
  UPDATE's SET clause field-for-field (status, *_signed_at/balance_due,
  updated_at from `now`, everything else copied from `row`).
  `_AUDITABLE_{CONTRACT,INVOICE}_FIELDS` exclude the sensitive blobs
  (customer_signature_data / payments) so they never reach changed_fields.
- update_project redaction symmetry: only built-in roles with PERM_WRITE_PROJECTS
  are ADMIN/MANAGER/PROJECT_MANAGER — none are ROLE_CUSTOMER, so
  `_row_to_project(row, actor.role)` (is_customer only) does not redact; `_after`
  via get_project also unredacted. Symmetric.
- change_summary format byte-identical; `_meaningful = sorted(set(_changed) -
  {"updated_at"})` preserves the noop-bump-no-audit contract; `updated_at` still
  present in `details["changed_fields"]` (only the gate/summary drop it).
- Tests: exact set-equality on changed_fields, phantom-diff regressions (stage
  normalization, customer domain scoping, json-col parse), None-guard monkeypatches
  the actual re-read, secret-leak sweep reads persisted column.

**WARNING (not blocking; NEW_ISSUES entry required, rule 8) — update_project
NEW-312 ordering:** `_after = self.get_project(project_id, actor)` now runs
BEFORE `audit.log` (was only in the final `return`). `get_project` RAISES for a
technician not in assigned_employees / a customer / a write-without-read actor.
For such an actor holding PERM_WRITE_PROJECTS, the UPDATE commits, then
get_project raises → **no audit row is written for a persisted mutation**
(pre-diff code wrote the row first, then raised). NOT reachable via any built-in
role (all PERM_WRITE_PROJECTS holders also have PERM_READ_ALL_PROJECTS); only via
a custom_permissions misconfig. Recommended fix if pursued: build the audit
`_after` from a raw `SELECT *` + `_row_to_project(row, actor.role)` (mirrors how
`_before` is built), keep `get_project` solely for the return value, and log
before that call. transition_opportunity_stage has the same theoretical shape but
calls get_opportunity up front so its post-mutation getter can't newly raise.
