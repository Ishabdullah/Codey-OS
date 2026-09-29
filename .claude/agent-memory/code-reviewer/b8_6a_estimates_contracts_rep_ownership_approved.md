---
name: b8_6a_estimates_contracts_rep_ownership_approved
description: B8.6a estimates/contracts assigned_user_id + rep-ownership RBAC (NEW-548/NEW-573) — APPROVED, clears rule-4 gate
metadata:
  type: project
---

Reviewed 2026-09-17. `restoricon_core/database.py` (schema + migration),
`models.py` (Estimate/Contract.assigned_user_id), `audit_service.py`
(_AUDITABLE_CONTRACT_FIELDS), `crm_service.py` (create/get/list_estimate,
create/get/list_contract, sign_contract), `tests/test_restoricon_core/
test_services.py`.

Verification performed (not just diff read):
- Confirmed the sign_contract ordering fix directly in the diff: the
  customer-isolation/rep-ownership authorization block runs and can
  `raise PermissionError` BEFORE the `if row["status"] == "signed":
  raise ValueError` idempotency guard. An unauthorized actor re-signing an
  already-signed contract gets 403/404-shaped PermissionError, not a
  leaking 400. Matches [[new549_global_search_rep_scoping_approved]]-style
  not-found discipline elsewhere in this service.
- Confirmed `get_estimate`/`get_contract` return `None` (not
  PermissionError) on a narrowed actor's cross-rep access — same
  not-found shape as `get_lead`/`get_opportunity`. Read the actual `if
  estimate.assigned_user_id != actor.user_id: return None` code, not the
  description.
- Traced the assignment-splat fix end to end: `routes.py:1160/1183` builds
  `Estimate(**json_body)`/`Contract(**json_body)` from raw client JSON
  once, passes that same object into `create_estimate`/`create_contract`,
  which then overwrite `.assigned_user_id = actor.user_id` on that
  instance before the INSERT. Order is correct — the client value can
  never survive to the DB write. Same fail-open shape NEW-546 closed.
- Confirmed the disclosed ROLE_PROJECT_MANAGER regression is real by
  reading auth.py's `ROLE_PROJECT_MANAGER` permission set directly
  (lines 436-474): holds `PERM_SIGN_CONTRACTS` (NEW-192 grant) and
  `PERM_READ_ESTIMATES`/`PERM_READ_CONTRACTS`, but NOT
  `PERM_READ_TEAM_SALES_DATA`, `PERM_WRITE_CONTRACTS`, or
  `PERM_WRITE_ESTIMATES`. Net effect: PM can no longer sign/see any
  contract/estimate it doesn't own, and can never own one (no create
  permission) — a silent narrowing of an explicit prior grant. This was
  NOT invented as a workaround; implementer logged it as NEW-575 (already
  committed separately, f480512) and the new
  `test_sign_contract_new192_role_matrix` explicitly asserts+documents the
  gap (`with pytest.raises(PermissionError): ... sig-pm`) rather than
  silently passing around it. Acceptable to ship disclosed/pending a
  product decision — does not block this round.
- `_scoped_assignee_filter` reused unchanged from the existing
  leads/opportunities/tasks mechanism (crm_service.py:827-841); confirmed
  `list_estimates`/`list_contracts` call it with `requested=None` (no
  drill-down param exposed for these two entities) — correct, matches the
  "no unclaimed-pool carve-out" design since these entities always have an
  owner from creation.
- Considered the pre-existing-row (migrated DB, NULL assigned_user_id)
  case raised in the task brief: correctly invisible to narrowed actors
  after this migration (no IS NULL carve-out). Implementer's comment
  acknowledges this is deliberate, not a gap, since normal creation can no
  longer produce a NULL row. Pre-migration data becoming invisible to
  narrowed reps until manually reassigned is a real but minor operational
  wrinkle, not a security bug — worth a one-line ledger note, not a
  blocker.
- New tests are non-vacuous: `test_create_estimate_and_contract_ignore_client_supplied_assigned_user_id`
  actually supplies a different `assigned_user_id` in the constructor and
  asserts the DB round-trip differs; `test_sign_contract_idempotency_guard`
  signs once (asserts success) then re-signs and asserts `ValueError`.
  Both exercise real behavior, not tautologies.
- Full suite reproduced myself: `2160 passed, 1 skipped, 69 warnings in
  346.68s (exit 0)` — matches implementer's claimed number exactly
  (proxy vars unset per [[sandbox_proxy_test_artifact]]).

No new bug pattern beyond what's already in memory — this round is a
clean instance of the established rep-ownership-narrowing pattern, done
carefully (ordering fix, disclosed regression, non-vacuous tests, matched
verbatim test count).
