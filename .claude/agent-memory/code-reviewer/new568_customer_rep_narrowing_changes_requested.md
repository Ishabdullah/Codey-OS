---
name: new568_customer_rep_narrowing_changes_requested
description: NEW-568 customer rep-ownership narrowing + admin reassign — CHANGES REQUESTED round 1 (undisclosed regression + understated ledger entry), core logic itself verified sound
metadata:
  type: project
---

Reviewed 2026-09-22. `restoricon_core/services/crm_service.py` `get_customer`/
`list_customers` rep-ownership narrowing + `update_customer`'s
`assigned_user_id` write-gate. The core mechanism (narrowing clause,
write-gate ordering, None-guard scoping, audit before/after values,
parameterization) was all verified correct by direct read and full-suite
reproduction (`2204 passed, 1 skipped, exit 0` — matched implementer's
claim verbatim). Assignment/reassignment/unassignment round-trip test
(`test_admin_can_assign_and_reassign_customer_with_audit_and_visibility_flip`)
is real and non-vacuous.

Two things the implementer's own out-of-scope logging (`NEW-584/585/586`)
missed, caught only by tracing *callers* of the narrowed method rather than
re-reading the diff (advisor flagged this as the gating step — diff-reading
alone would have approved):

1. **Undisclosed regression, not just an out-of-scope gap**: `get_estimate`
   (B8.6a) narrows on `estimate.assigned_user_id`; the new `get_customer`
   narrows on `customer.assigned_user_id` — two *independent* fields. The
   shipped `GET /api/v1/estimates/<id>/proposal` route
   (`routes.py:1217`, B8.6c) calls `get_estimate` then `get_customer` with
   the same actor. Before this diff, the second call had no narrowing, so
   it always succeeded once the first passed. After this diff, a rep who
   legitimately owns the estimate but whose customer has been reassigned
   to a *different* rep (newly and directly reachable via this same
   round's Part 2 admin-reassign feature) now gets a 404 on their own
   estimate's proposal. Zero test coverage (the existing B8.6c test's
   fixture customer is unassigned/NULL, which happens to bypass the new
   narrowing, masking the regression). This is new-this-diff, not a
   pre-existing sharp edge — unlike NEW-584/585/586, it didn't exist in
   any form before this change and needed its own ledger entry, which
   didn't exist.

2. **NEW-586 materially understates severity.** Its text says a narrowed
   actor can still mutate another rep's customer's ordinary fields via
   `update_customer` if they already know/guess the id. What it omits:
   `routes.py:811` returns `updated_cust.to_dict()` — the **full customer
   record** — in the 200 response body for *every* successful write, not
   just the changed field. A plain `ROLE_SALES` actor (holds
   `PERM_WRITE_CUSTOMERS`, lacks `PERM_READ_TEAM_SALES_DATA`) can send a
   trivial no-op-ish write like `{"notes": "x"}` against a sequential,
   guessable customer id and get back the entire record — a complete
   bypass of the read-narrowing this same round built, not a "low
   severity, needs to guess the id" write-only gap. Severity
   characterization needs correcting (rule 6), not just left as filed.

Verdict: CHANGES REQUESTED — not because the shipped code's narrowing/
reassign-gate logic is wrong (it isn't), but because rule 8 (log
everything found, don't silently drop) wasn't fully honored: one real,
live regression in an already-shipped feature has zero ledger entry, and
one existing entry (NEW-586) is inaccurate on severity. Both are
ledger-only asks, not necessarily code fixes this round — but they must
exist accurately before commit.

New pattern worth carrying: **when a fix narrows a service-layer read
method that other service methods call internally (not just external API
routes), trace those internal callers specifically for a case where two
*different* narrowing fields (e.g. `estimate.assigned_user_id` vs
`customer.assigned_user_id`) can diverge for the same legitimately-scoped
actor.** Diff-reading and even full-suite runs miss this class because
existing fixtures tend to use NULL/unclaimed sentinel values that happen
to bypass new narrowing clauses, producing a false-clean pass. Also:
**when a write route's response echoes the full post-write object
(`.to_dict()` of the whole row), a narrowing added only to the read path
is fully bypassable via that write route** — check the route handler's
response body, not just the service method's permission gate, before
treating a write-side gap as "low severity."
