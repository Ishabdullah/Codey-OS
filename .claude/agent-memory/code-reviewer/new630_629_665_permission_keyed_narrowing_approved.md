---
name: new630-629-665-permission-keyed-narrowing-approved
description: NEW-630 reversal + NEW-629 doc comments + NEW-665 document-access permission-keyed narrowing fix — all APPROVED
metadata:
  type: project
---

2026-09-27, three unrelated fixes reviewed together (uncommitted, concurrent
with another session's `ROLE_SUBCONTRACTOR` work in the same tree):

- **NEW-630 reversal**: `PERM_READ_OPERATIONS` removed from
  `ROLE_PERMISSIONS[ROLE_SALES_MANAGER]` (Ish reversed his own 2026-09-25
  grant, `dd244d5`). Diff isolated to the one permission-set line + comment;
  confirmed via `git show dd244d5 --stat` that the original grant touched
  only `auth.py`/`operations_service.py`/`web_surfaces.py` (NEW-642's
  redirect map, unrelated)/tests — no sales-portal UI panel was ever built
  on top of the grant, so the reversal leaves nothing dangling. Verified
  `deploy_equipment`/`return_equipment` gate only on
  `PERM_WRITE_OPERATIONS`/`PERM_MANAGE_PROJECTS` by reading the actual gate
  code (not trusting the comment) — genuinely unaffected either way.

- **NEW-665 (the real bug)**: `_parse_custom_permissions` in `auth.py` does
  `{str(k): bool(v) for k, v in raw.items()}` with NO filtering of falsy
  values, and `_validate_custom_permissions` only rejects *unknown keys*,
  never rejects a `False` value for a permission the role grants `True` by
  default. This means **`custom_permissions_json` can genuinely suppress a
  role-default permission** — not just add ones the role lacks. That's what
  makes "non-customer role custom-granted `PERM_READ_OWN_DOCUMENTS` alone
  (with `PERM_READ_DOCUMENTS` explicitly forced `False`)" a real, JSON-path
  vector, not a strawman construction. This generalizes: any future
  permission-keyed narrowing review should check whether the narrowed
  permission has a role-default of `True` that a custom grant could turn
  off, using this same mechanism.

  The actual vulnerable code path: `list_documents` only appends
  `AND customer_id = ?` `if customer_id is not None` — so naively setting
  `customer_id = actor.customer_id` when narrowing (and `actor.customer_id`
  is `None`, the normal case for a non-customer role) would silently DROP
  the WHERE clause and return every document, the opposite of narrowing.
  Fix added an explicit `if not actor.customer_id: return []` guard before
  the query. Confirmed this crux by reading the query-builder directly, not
  trusting the implementer's description.

- **NEW-629**: comment-only, verified both `get_project` and `list_projects`
  actually have `PERM_READ_OWN_PROJECTS`/`PERM_READ_ASSIGNED_PROJECTS` only
  in the outer `or`-gate (checked both methods' gates individually — the
  diff hunk for `list_projects` didn't itself contain the gate lines, they
  were a few lines above the hunk start; don't assume a "same as above"
  comment is accurate for the second method without reading its own gate).

Disclosed but not actioned (correctly, per advisor): `PERM_READ_DOCUMENTS`
is dashboard-grantable via `PERMISSIONS_CATALOG`, so an admin could now
custom-grant it to a `ROLE_CUSTOMER` actor, un-narrowing them where the old
role-keyed check would have still narrowed. This is the permissive
direction, requires deliberate admin intent, and matches the codebase's
established permission-keyed convention elsewhere — Warning only, and the
"fix" would be reintroducing role-keying, which is the wrong direction.
Not logged to `NEW_ISSUES.md` per the other session's untouched work
warning — see [[working_tree_cross_round_bleed]].

Full suite: 2 failed (both explicitly reference `subcontractor`/
`ROLE_SUBCONTRACTOR`, confirmed unrelated to this diff), 1271 passed, no
errors. Implementer had claimed 2 failures + 1 error
(`test_api.py::test_api_new627_...`) — that third item did not reproduce
(targeted re-run: 4 passed). Favorable discrepancy, not a regression, but
another instance of the NEW-512 lesson: claimed test-count deltas don't
always match reality, always reproduce them yourself.
