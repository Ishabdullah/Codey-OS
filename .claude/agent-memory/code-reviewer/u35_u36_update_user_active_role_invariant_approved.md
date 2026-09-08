---
name: u35-u36-update-user-active-role-invariant-approved
description: U.35/U.36 auth.py update_user — remove active path (token resurrection) + shared role/customer_id invariant helper. Round 1 APPROVED.
metadata:
  type: project
---

U.35 (NEW-264) + U.36 (NEW-266), `restoricon_core/auth.py::update_user`. Round 1 **APPROVED** 2026-09-02.

**What the fix does:** drops `"active"` from `update_user.allowed_fields` (closes token-resurrection: update_user(active=0) never revoked tokens, update_user(active=1) revived them — set_user_active is now the only suspend path and it revokes on active==0). Adds a guard that rejects any real `active` change with a pointer to set_user_active; a no-op echo of the current value passes. New module-level `_validate_user_role_invariants(role, customer_id)` shared by create_user and update_user, evaluated against post-update effective state. `with conn:` write block wrapped in `try/except sqlite3.IntegrityError -> ValueError` so dup-email etc. maps to 400 not 500.

**Verified:**
- Only `UPDATE users SET active` site left is `set_user_active` (grep). No other resurrection path. create_user sets active=1, set_user_permissions/change_password/delete_user don't touch active.
- `users.active` is sqlite INTEGER -> `User.active` is int 0/1, so `requested_active != user.active` comparison is int-vs-int, sound.
- routes.py single try: PermissionError->403, ValueError->400, Exception->500, no shadowing `except Exception` before. update_user reached at routes.py:328 passing raw json_body.
- `with conn:` = stdlib commit-on-success / rollback-on-exception; role-revoke UPDATE is inside same block (atomic); IntegrityError caught outside `with` so rollback precedes re-raise.
- Guards sit before `if not set_clauses: return user`, so `update_user(uid,{"active":0})` and `{"role":"customer"}` both raise rather than hitting the early return.
- NEW-264's "active:banana -> 500" cosmetic defect also fixed (int() ValueError -> 400).
- Tests: `tests/test_user_management.py tests/test_restoricon_core/test_auth.py` 22 passed; `tests/test_restoricon_core` 211 passed. 8 new tests, negative controls reasoned through (test1: without fix full_name+active persist, no raise; test8: without wrapper IntegrityError !subclass of ValueError -> pytest.raises fails + route 500).

**Non-blocking warnings surfaced to coordinator:**
1. Accepted edge (per NEW-266 spec): moving TO role=customer in a call that omits customer_id while a stale non-null customer_id sits on the row -> passes, silently re-links to that customer. Preconditions are narrow (privileged actor + pre-existing stale id) and NEW-266 already says "evaluate post-update state"; suggested a one-line addendum to NEW-266, not a blocker.
2. `int(1.9)->1` silent truncation in the active guard — cosmetic, nobody sends 1.9.
3. NEW-267 (audit record for role-change token revoke) still open — coordinator's call whether to bundle.
4. PROJECT_LOG §4 / CODEY_MASTER_PLAN Appendix A still show U.35/U.36 as open `[ ]` — coordinator step 5.
