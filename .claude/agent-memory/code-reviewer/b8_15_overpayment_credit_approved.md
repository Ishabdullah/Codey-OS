---
name: b8-15-overpayment-credit-approved
description: B8.15 customer_credits overpayment-tracking feature (crm_service.record_payment) — APPROVED after live verification
metadata:
  type: project
---

2026-09-25, uncommitted at review time (database.py + crm_service.py +
new test file). Ish decision: "overpayments should be logged as credit"
— manual-only, no auto-apply, kept out of AR reporting.

**Verified, not just read:**
- New `customer_credits` table is a plain `CREATE TABLE IF NOT EXISTS`
  inside `_SCHEMA_SQL`; `init_schema()` runs `executescript(_SCHEMA_SQL)`
  on every `DatabaseManager()` construction — genuinely self-migrating,
  no `_migrate_schema()` entry needed (new table, not an ALTER). Read
  `init_schema()`/`_migrate_schema()` directly to confirm rather than
  trusting the implementer's claim.
- Credit INSERT is inside the SAME `with conn:` block as the invoice
  balance UPDATE in `record_payment` — confirmed by reading the actual
  code, not the diff summary.
- Delta-against-already-recorded idempotency guard (`credit_delta =
  overage - already_credited`) hand-verified against a concrete 3-payment
  example (1000 invoice, +1500, +200 → credits of 500 then 200, balance
  700) — matches the 7 new tests, all of which pass.
- `get_customer_credit_balance`'s `ROLE_CUSTOMER` narrowing matches
  `get_invoice`'s established pattern line-for-line.
- AR-reporting separation: grepped `finance_service.py` and
  `analytics_search_service.py` for `customer_credits` myself — zero
  matches, confirmed.
- `created_by_user_id` has no FK (unlike this codebase's usual
  `created_by` convention) — **initially looked suspicious** since
  `commission_ledger_entries.created_by` DOES have a FK. Traced the
  actual call site: commission recording happens in a *separate*
  transaction *after* the payment's `with conn:` already committed, with
  an explicit `except sqlite3.IntegrityError` that distinguishes a real
  FK violation from the expected double-fire and never re-raises.
  `customer_credits`' INSERT, by contrast, is unified inside the SAME
  transaction as the invoice UPDATE with no catch — a FK failure there
  would roll back the whole payment. The omission is deliberate and
  consistent once you see this distinction, not a contradiction of the
  commission-table precedent. **Lesson: when a diff claims "unlike
  established convention X", trace X's actual call site before either
  accepting or flagging the deviation — the answer usually hinges on a
  detail (same-transaction vs separate-transaction, caught vs uncaught)
  that isn't visible from the field/table name alone.**
- Ran the new test file directly (7 passed), the full repo root suite
  (`2546 passed, 1 skipped`), and `pytest tests/` scoped exactly as the
  implementer likely ran it (`2432 passed, 1 skipped`, matching their
  claim exactly) — after unsetting HTTP_PROXY/HTTPS_PROXY per
  [[sandbox_http_proxy_urllib_405_env_artifact]]. Root-level run
  (2546) includes `ccos/tests/` which `tests/`-scoped does not; both are
  0-failure. Reproduced the exact claimed number, not just "close enough."

**Pre-existing, out-of-scope, correctly NOT touched:** the
`payments_json` read-modify-write race between two truly concurrent
`record_payment` calls (same connection, no `BEGIN IMMEDIATE`) is
already documented elsewhere in the file (the B8.7c commission block's
"KNOWN, ACCEPTED LIMITATIONS" comment) and is covered by
[[project_new311_txn_boundary_decision]] — the credit feature just
inherits this pre-existing gap rather than introducing a new one.

**Two Confirmed findings logged to NEW_ISSUES.md in this round** (per
rule 8 — not deferred, per [[feedback_fix_related_findings_immediately]]):
1. `get_customer_credit_balance` has zero callers outside its own
   definition and test file (verified by grep across
   `restoricon_core/` and `tests/`) — no route, no dashboard panel. The
   credit ledger is write-only from an operator's perspective, which
   conflicts with the DDL comment's own stated goal ("a recorded,
   queryable, customer-linked liability") and Ish's standing dashboard-
   single-control-surface directive. Not a blocker — no application/UI
   was ever in scope this round — but it's a real gap, not a maybe.
2. `record_payment` still doesn't validate `payment_amount >= 0`
   (pre-existing, documented elsewhere in the same file). A negative
   payment_amount silently skips any credit insert but does NOT claw
   back a previously-issued credit — `already_credited`'s high-water
   mark stays stuck until a future overpayment exceeds it again. Checked
   whether an invoice-amount-amendment path could trigger the same
   thing (advisor's hypothesis) — grepped for `update_invoice`/`UPDATE
   invoices` and confirmed no such mechanism exists yet; `invoices.amount`
   is immutable after creation in the current codebase, so negative
   payment_amount is the only currently-reachable trigger.

**Verdict: APPROVED.** Stage `restoricon_core/database.py`,
`restoricon_core/services/crm_service.py`,
`tests/test_restoricon_core/test_b8_15_overpayment_credit.py`.
