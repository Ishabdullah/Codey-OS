---
name: b8_1_properties_commissions_changes_requested
description: B8.1 properties+commission_ledger_entries schema round — CHANGES REQUESTED, live-repro'd a real double-reversal ledger corruption and a separate single-reversal status-filter overstatement bug
metadata:
  type: project
---

Reviewed 2026-09-17: new `properties` + `commission_ledger_entries` tables,
`Property`/`CommissionLedgerEntry` models, `PERM_READ_TEAM_COMMISSIONS`,
Property CRUD in `crm_service.py`, new `commission_service.py`. Schema/RBAC
mechanics (allow-list before f-string, append-only grep, legacy-migration
test using a real sqlite3 file/DatabaseManager, RBAC role grants) were all
clean on direct verification. The blocking issues were both financial-
correctness bugs in `CommissionService.reverse_commission`/`list_commissions`,
caught only by writing a live repro script against an in-memory DB — not
visible from reading the diff alone:

1. **Double-reversal produces a non-zero net.** Nothing blocks calling
   `reverse_commission(entry_id)` twice; each call inserts a full negation
   of the *original* amount, so two reversals net to `-amount` instead of
   `0`. The docstring's own claim ("summing commission_amount ... nets out
   correctly") is false under this input — verified via direct SQL dump of
   the three resulting rows.
2. **Even a single correct reversal breaks status-filtered reads**, because
   the original row's `status` can never change (append-only) — a
   `status='earned'` filter (the exact use case `idx_commission_ledger_status`
   exists for) returns the un-reversed original with no offset visible.
   This is the happy path, not an edge case, and is worse than finding 1.
3. Any double-reversal guard must sit **inside** the same `with conn:` block
   as the insert — a bare pre-check SELECT outside the transaction repeats
   the exact TOCTOU shape this project already hit in NEW-135/136 and
   NEW-534.

Pattern for future reviews: **when a service claims a ledger/sum invariant
in its docstring ("X nets out", "sums correctly"), don't take the claim on
the diff — write the smallest live repro that stresses the stated invariant
(single op, then the op twice) before approving.** A green test suite here
did not catch either bug because no test exercised double-reversal or a
status-filtered read after a reversal.

Separately: implementer's claimed "1958 passed, 1 skipped" didn't match
either of my own runs (59 false failures under ambient HTTP_PROXY — see
[[sandbox_http_proxy_urllib_405_env_artifact]] — vs 1957 passed/1 skipped/1
unrelated socket-bind error with proxies unset). One-test discrepancy isn't
itself alarming, but reinforces: always rerun the suite yourself, never
cite the implementer's count as verified.
