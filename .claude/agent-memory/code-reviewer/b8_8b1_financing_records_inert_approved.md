---
name: b8_8b1_financing_records_inert_approved
description: B8.8b-1 financing_records table + FinancingService (deliberately inert, no AR wiring) — APPROVED round1
metadata:
  type: project
---

2026-09-23. New `financing_records` table + `FinancingService` (CRUD +
RBAC only, no AR/P&L wiring — that's the separate, higher-scrutiny
B8.8b-2). APPROVED round 1, zero blocking findings.

Verified independently, not just from the implementer's self-report:
- Inertness: read `get_ar_aging`/`get_financial_summary`/`get_project_pnl`
  in `finance_service.py` in full myself — zero references to
  `financing`/`FinancingRecord`/`financing_service` anywhere in the repo
  outside the four claimed files (grepped repo-wide).
- RBAC: read `auth.ROLE_PERMISSIONS` directly. Exactly 4 roles hold
  `PERM_WRITE_CUSTOMERS` (ADMIN/MANAGER/SALES/AI_AGENT) and all 4 also
  hold `PERM_READ_FINANCIALS` — the "empty-updates-dict falls through to
  a differently-gated read" claim holds. `ROLE_SALES_MANAGER` derives via
  `ROLE_PERMISSIONS[ROLE_SALES] | {...}` union so it inherits both too.
  `PERM_READ_FINANCIALS` ("read:financials") and `PERM_READ_FINANCE`
  ("read:finance") are genuinely two different constants in this
  project — don't confuse them when checking a new service's gate.
- Live-reproduced the disclosed NULL-invoice_id double-count gap myself
  (two `funded`/`approved` records, same project, both `invoice_id=None`
  — both inserts succeed, no IntegrityError) — confirms the partial
  unique index (`WHERE ... invoice_id IS NOT NULL`) is genuinely inert
  for that case, same documented shape as `idx_commission_ledger_source_
  unique`'s own NULL hole from B8.7a.
- Traced `build_audit_details` to confirm it diffs `.to_dict()` output
  (dataclass field names via `asdict()`), so the audit frozenset
  correctly uses `document_ids` not the DB column `document_ids_json`.
- Checked the `invoice_id`-updatable fix in BOTH the allow-list AND the
  actual `UPDATE ... SET` SQL string (this is exactly the shape of the
  `reserve_slot()` port= bug NEW-259 caught — allow-list-only fixes that
  don't reach the real SQL are a recurring near-miss in this project).
- Full suite: `2306 passed, 1 skipped` verbatim, matches claimed
  2285→2306 (+21) exactly, no hang.

Recommended (not yet logged by me — coordinator's call): open a new
NEW-### covering BOTH unguarded double-count shapes: (a) NULL-invoice_id
rows (disclosed) and (b) a voided-approved record coexisting with an
active-approved/funded record on the SAME invoice_id (NOT disclosed
anywhere in the round's comments, but directly proven live by the
round's own `test_voided_approved_financing_does_not_block_a_new_one`
— invoice 47 ends the test holding a voided 'approved' row AND an
active 'funded' row simultaneously). Both non-blocking for THIS round
(nothing reads the offset yet), both structural prerequisites B8.8b-2
must filter for.

Advisor caught what my own pass missed: all three docstrings
(database.py, models.py, financing_service.py) state the eligibility
rule as "application_status is 'approved' or 'funded'" and OMIT
`status='active'` — models.py goes further and calls `status`
"independent of application_status," actively steering a future
implementer away from filtering on it. Followed literally in B8.8b-2,
this reintroduces the exact invoice-scoped double-count the partial
unique index exists to prevent. Grep pattern: `grep -n "approved.*funded\|independent of" database.py models.py financing_service.py`.
Cheap 3-comment fix, non-blocking for this round since it's text-only
and nothing computes the offset yet, but should be fixed before commit
since it's the load-bearing spec for the very next round.

Also flagged: `create_financing_record` validates both enum fields but
never validates `amount_financed >= 0`, unlike its sibling
`FinanceService.record_transaction` (`if txn.amount <= 0: raise
ValueError`). A negative `amount_financed` would silently *increase* AR
once B8.8b-2 wires the offset. Worth a Warning, non-blocking today.

See also [b8_7a_commission_trigger_round2_approved](b8_7a_commission_trigger_round2_approved.md)
for the `idx_commission_ledger_source_unique` precedent this round
mirrors, and [new565_575_rbac_sign_contract_approved](new565_575_rbac_sign_contract_approved.md)
for the `PERM_READ_FINANCIALS` grant-on-`ROLE_SALES` precedent.
