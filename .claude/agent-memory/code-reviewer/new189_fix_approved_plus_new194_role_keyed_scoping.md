---
name: new189_fix_approved_plus_new194_role_keyed_scoping
description: NEW-189 (crm_service.py get_project/list_projects missing permission gate) fix confirmed APPROVED; found a distinct, narrower follow-on gap (needs NEW-194) in the same methods' role-keyed scoping logic
metadata:
  type: project
---

Confirmatory rule-4 re-review of Track B / Phase B1's `NEW-189` fix
(`restoricon_core/services/crm_service.py`'s `get_project()`/
`list_projects()`). Verdict: **fix APPROVED** — independently reproduced
the fake zero-permission actor test against a real `CRMService`/
`DatabaseManager(":memory:")` instance (not mocked), both methods now
raise `PermissionError`; confirmed the gate runs before any DB read;
confirmed `has_permission()` uses `ROLE_PERMISSIONS.get(role, set())`
(fails closed, no `KeyError` for out-of-matrix roles, so the ledger's
"covers a bug producing an actor outside ROLE_PERMISSIONS" claim is
accurate); confirmed no regression across all 7 legitimate roles
(spot-checked customer isolation and technician-assignment narrowing
live, both still correct beneath the new gate); ran both test suites
myself, `11 passed` and `482 passed, 1 skipped` matched claims exactly.

**New finding surfaced, not yet in NEW_ISSUES.md as of this review — flag
if it's still missing on a future pass, should be `NEW-194`:** the fix
adds a *permission-based* top gate, but the narrowing beneath it
(customer isolation, technician-assignment check, and the
customer-field-redaction branch) is still keyed on `actor.role ==
ROLE_CUSTOMER` / `== ROLE_TECHNICIAN` identity, not on which permission
let the actor through the gate. Built an actor with `role = "nobody"`
whose `has_permission()` returns `True` only for `"read:own_projects"` —
it passes the base gate but is skipped by every `role ==` narrowing
branch, so it saw another customer's full project (financials, notes,
subcontractors — more than a real `ROLE_CUSTOMER` actor sees for their
*own* project) and `list_projects` returned every row unfiltered. Not
live-exploitable today (only `ROLE_CUSTOMER` holds `read:own_projects`,
only `ROLE_TECHNICIAN` holds `read:assigned_projects` in the shipped
matrix) — same "one matrix edit away" shape `NEW-189` itself used to
justify non-Critical status. Does not reopen `NEW-189` (that was "no
gate at all"; this is a narrower gap one level down in the scoping
logic) but needs its own ledger entry per rule 8.

**Technique reinforced:** when checking a fix for "gate added," always
re-run the same fake-actor technique **one level down** — check whether
the code *beneath* the new gate still branches on role identity rather
than on the permission that authorized entry. A top-level permission
check does not retroactively make identity-keyed branches beneath it
permission-safe.

**Process note:** advisor caught that I announced "check ledger accuracy
against diff" (item 6) but then skipped straight to an unrelated test
without actually doing it — call advisor before declaring a verdict on
multi-item confirmatory tasks like this one, even when early items look
clean, since it's an effective check on whether every named checklist
item actually got executed.
