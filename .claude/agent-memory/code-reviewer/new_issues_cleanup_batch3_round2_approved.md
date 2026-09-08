---
name: new_issues_cleanup_batch3_round2_approved
description: NEW_ISSUES.md ledger closeout batch 3 round2 (crm_service.py update_customer/create_project) — both round1 findings fixed, APPROVED
metadata:
  type: project
---

Follow-up to [[new_issues_cleanup_batch3_role_vs_permission_leak]]. Both
round1 findings verified fixed:

1. **Critical (notes-redaction leak)**: fix adds an inline
   `if updated_cust is not None and actor.role == ROLE_CUSTOMER:
   updated_cust.notes = None` in `update_customer` right after the raw
   post-write row read, BEFORE `build_audit_details(after=...)` is built —
   so the audit trail also gets the redacted value, not just the HTTP
   response (a stricter outcome than what was asked, not a new leak).
   Confirmed the inline check is a byte-exact match for `get_customer()`'s
   only-`notes`-is-redacted-for-ROLE_CUSTOMER behavior (crm_service.py:168)
   — no other Customer field is redacted there, so nothing else was missed.
   Negative-control-verified for real: temporarily disabled the redaction
   line (`if False and ...`), reran
   `test_update_role_customer_with_write_grant_redacts_notes`, watched it
   fail with the actual leaked notes string in the AssertionError, restored
   the file from a scratchpad backup. The regression test constructs a real
   `ROLE_CUSTOMER` `AuthContext` with `custom_permissions={PERM_WRITE_CUSTOMERS:
   True}` — the exact vulnerable shape, not a synthetic stand-in.

2. **Warning (create_project missing type guard)**: `if not all(isinstance(x,
   int) for x in project.assigned_employees): raise ValueError(...)` added
   immediately before the existence-check SQL block, matching
   `update_project`'s NEW-308 ordering and error-message convention exactly.

Full suite live-run by the reviewer (not just trusted from implementer
report): `1500 passed, 1 skipped in 270.13s` — verbatim match to the
claimed count.

`git diff --stat -- NEW_ISSUES.md` still empty — ledger not yet updated,
as expected; that's the coordinator's post-approval step, not something to
re-flag as blocking (per this round's explicit task framing).

No new issues found this round. The automation_service.py/
scheduling_service.py NEW-218 kwargs and the qualification_data/
secondary_trades/email-empty-string crm_service.py subcontractor fixes
present in the same working-tree diff are pre-existing batch-3 scope
(NEW-238/239/218), already covered and verified clean in round1 — not new
scope creep.
