---
name: new650-credit-balance-route-approved
description: First caller wired for CRMService.get_customer_credit_balance; RBAC-delegated route reviewed and approved
metadata:
  type: project
---

NEW-650: `GET /api/v1/customers/{id}/credit-balance` — first route/caller for
`CRMService.get_customer_credit_balance` (service added `a8365a7`, zero callers
until this task). APPROVED 2026-09-26 after full live verification (not just
diff read).

**What was verified, not just trusted:**
- Read `handle_request` end-to-end (`restoricon_core/api/routes.py` lines
  383-3479): confirmed the new route sits inside the single big `try` block
  that ends at the generic `404 Endpoint not found` fallthrough (line 3473),
  with `except PermissionError` -> 403 and `except ValueError` -> 400 below it
  (3475-3478). This project's routes genuinely never do their own permission
  checks — RBAC-delegation-to-service-method is the established pattern, e.g.
  `/api/v1/sales/analytics-rollup`'s own comment at line ~3440 says the same
  thing.
- Traced the malformed-path guard's three shapes by hand (string-slice
  arithmetic, not just running the test): non-integer id -> clean 400 via
  `_parse_int_path_segment`'s `ValueError`; omitted id -> slice is empty
  string (guard's truthy check catches it, note the omitted-id case here
  overlaps the prefix's trailing slash with the suffix's leading slash, worth
  rechecking by hand each time rather than assuming) -> falls through to
  generic 404; extra segment -> slice contains "/" -> guard fails -> generic
  404. All three match test assertions exactly.
- Confirmed guard shape (`path[len(PREFIX):-len(SUFFIX)]` truthy +
  `"/" not in ...` before `_parse_int_path_segment`) is the actual established
  NEW-525/526 fix convention by reading `NEW_ISSUES.md`'s NEW-525 entry
  directly, not trusting the implementer's citation.
- Read `get_customer_credit_balance` itself (`restoricon_core/services/`
  around line 4900): RBAC gate + `ROLE_CUSTOMER` same-customer narrowing
  exactly as claimed; `COALESCE(SUM(...), 0.0)` really does return 0.0 for a
  nonexistent customer_id with no existence check — implementer correctly
  scoped this out as "already-reviewed service contract," not scope creep.
- Reran (not trusted) all three test files with proxy vars unset: test_api.py
  57 passed, test_b8_15_overpayment_credit.py + test_b8_15_round6 11 passed —
  matches implementer's claim exactly.

**Reusable technique:** when a route match uses a prefix/suffix slice guard,
walk the string-index arithmetic by hand for the omitted-id case specifically
— the prefix's trailing slash and the suffix's leading slash can overlap on
the same character, making the "remainder" slice empty in a non-obvious way
(start index > end index -> Python gives `""`, not an error). Don't just trust
that the guard "looks like" the established pattern; recompute the indices.

See also [[b8_15_overpayment_credit_approved]] for the underlying service
method's own review.
