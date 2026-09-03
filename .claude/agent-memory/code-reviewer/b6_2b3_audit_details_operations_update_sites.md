---
name: b6-2b3-audit-details-operations-update-sites
description: B6.2b-3 — 8 operations_service.py real-update audit sites onto build_audit_details before/after. APPROVED (358 green). Rule-8 notes on dispatch compliance-branch refactor.
metadata:
  type: project
---

B6.2b-3 (2026-09-03): 8 `operations_service.py` update sites → `build_audit_details`.
+4 `_AUDITABLE_{WORK_ORDER,MILESTONE,EQUIPMENT,DEPLOYMENT}_FIELDS` frozensets
(NEW-314, all "exclude nothing" == full to_dict(); drift tests assert equality).

**APPROVED.** `tests/test_restoricon_core/` 358 passed (+49 in
test_b6_2b3_audit_details.py), zero regressions.

Verified sound:
- `_before` strictly above first in-memory mutation / DB write at every site.
  #1 transition_project_stage: `_before` sits after the gate checks but before
  `_ensure_default_milestones` and before the COMPLETED branch's
  `project.actual_completion = ...` in-memory set. #4 dispatch: before the
  `wo.assigned_subcontractor_id = ...` block. #2/#5/#6/#7: first stmt after the
  top getter guard.
- `after` = post-commit re-read through the SAME builder as `before` at all
  sites. #2/#4/#5/#6/#7 use `get_*()`; #1 uses `_row_to_project(row, actor.role)`
  for both halves; #8 uses raw SELECT + `_row_to_equipment_deployment` for both.
  Never the input param / in-memory-mutated model. `_row_to_{milestone,
  equipment,work_order,equipment_deployment}` take no actor → no redaction →
  symmetric. #1 both halves pass `actor.role` identically.
- NEW-312 recurrence avoided: every `get_*` used for `_after` is also called at
  method top BEFORE any write, so the post-commit re-read can never newly raise
  (perm check already passed; row just written). #1's return-path `get_project`
  is post-audit. All `_after` derefs guarded `if _after else None`.
- NEW-313 COALESCE after-image trap closed: `instructions`/`notes` diffs are now
  taken against a genuine post-commit re-read, not the COALESCE input param, so
  an omitted (None) field produces no phantom `changed_fields` entry (6 tests:
  transition/milestone/dispatch/accept/exec/return "omitted absent"; plus
  dispatch `instructions=""` still recorded).
- `side_effects` rule-4 clean: only bool flags (`default_milestones_ensured`,
  `compliance_overridden`) / non-column params (`transition_reason` — `reason`
  is not a projects column) / cross-entity nested diffs (`deployment_created`,
  `deployment_returned` — deployment rows under an `equipment` entity_type).
  Milestone auto-creates are logged as their own `action="create"` rows, NOT
  echoed into #1's side_effects (test_se_transition_default_milestones_flag_not_dicts).
  Same-entity column effect (`actual_completion`) lands only in `changed_fields`.
- `action=` / `change_summary=` byte-identical to pre-diff (no +/- on those lines).
- #8 return_equipment: `updated_row` re-read hoisted above `audit.log`. No
  behavior change; the 2-key snapshot `{status: next_status, current_project_id:
  None}` matches the method's `current_project_id = NULL` UPDATE exactly.
- 4 new allow-lists: no credential/PII column reachable (WorkOrder/Milestone/
  Equipment/Deployment carry none; Equipment.serial_number is asset tracking,
  not PII). #3 update_work_order unfiltered `snapshot=work_order.to_dict()` is
  C-none + deferred to B6.2b-4 per architect classification.
- Tests read `query_logs(...).details` / `details_json`, not the `audit.log()`
  return; assert set-equality on changed_fields, key absence for NEW-313, drift
  frozenset == to_dict keys, and a parametrized out-of-domain key sweep over the
  persisted `audit_log` table. None-guards monkeypatch the real getter.

**Non-blocking / rule-8 notes handed to coordinator:**
1. `dispatch_work_order` compliance-check refactor: the COI and license branches
   were `if <cond> and not override_compliance:` (short-circuited under override);
   now `if <cond>:` always evaluated, with an inner `if not override_compliance:
   raise` + `_compliance_overridden = True`. Raise behavior is provably identical
   in every path (verified: `(sub_row["license_status"] or "").strip().lower()`
   is None-safe). Only new observable is the `compliance_overridden` side-effect
   flag. Covered by test_se_dispatch_{compliance_overridden,license_bypass_sets_flag,
   override_but_nothing_bypassed_no_key}. Worth a NEW_ISSUES line as a logic
   touch in a compliance gate, not a defect.
2. `deploy_equipment`: new `if not dep_row: raise ValueError` after a just-
   committed INSERT — previously would `TypeError` on `_row_to_equipment_
   deployment(None)`. Improvement; dead-safe branch.
3. `return_equipment`: `updated_row` deref (`_row_to_equipment_deployment(
   updated_row)`) is unguarded — but it was unguarded pre-diff too (the re-read
   just moved up). Identical risk, no regression. Implementer flagged this as
   "new"; it is not. Could add `if not updated_row: raise` for consistency with
   #4/#7's guards — cosmetic, does not block.
