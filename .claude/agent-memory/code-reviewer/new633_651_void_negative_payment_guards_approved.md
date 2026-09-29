---
name: new633-651-void-negative-payment-guards-approved
description: B8.15 round 6 — record_payment negative-amount + voided-invoice guards (NEW-651/NEW-633) — APPROVED after live verification
metadata:
  type: project
---

2026-09-26, uncommitted at review time (crm_service.py + new test file,
round 6 of the B8.15 findings-backlog sweep, following
[[b8_15_overpayment_credit_approved]]).

**Verified, not just read:**
- NEW-651 negative-amount guard (`if payment_amount < 0: raise
  ValueError`) sits right after the existing `payment_type` validation
  and strictly before `conn = self.db.get_connection()` / the invoice
  SELECT — no DB read or write has happened yet. `payment_amount == 0`
  intentionally still allowed; traced to a pre-existing idempotency
  comment (line ~5434-5436, predates this round) that explicitly
  documents "$0 reconciliation note" as a legitimate use case — the
  implementer's claim wasn't just self-referential, it points at real
  prior documentation.
- NEW-633 void guard (`if row["status"] == "void": raise ValueError`)
  sits right after the invoice-not-found check and strictly before
  `_before = self._row_to_invoice(row).to_dict()` — the row SELECT
  itself is read-only, so no side effect precedes the guard either.
- Rule-6 correction confirmed directly: `operations_service.py` has zero
  void-related lines (grepped `'void'`/`"void"`, no hits at all).
  `finance_service.py` has exactly two active filter lines (`354`,
  `463`, both `WHERE project_id = ? AND status != 'void';`) plus
  comments — matches the implementer's "two lines" claim exactly. The
  original NEW-633 finding's operations_service.py claim was wrong;
  implementer's correction is accurate.
- Router mapping confirmed: `restoricon_core/api/routes.py`'s `/pay`
  handling (~line 1434-1446) lives inside the same `try:` block (starts
  at `handle_request`, line 383) that terminates in a top-level
  `except ValueError as ve: return 400, ...` at line 3458 — both new
  guards surface as clean 400s, not 500s.
- "record_payment is the only invoice-status writer" claim confirmed
  within its actual scope: grepped `SET status` across every
  `restoricon_core/services/*.py` file — the only `UPDATE invoices ...
  SET status` hit is inside `crm_service.py` itself (record_payment's
  own write, line ~5461). Every other `SET status` hit belongs to a
  different table (compliance_items, timesheets, tasks, estimates,
  contracts, homecare_subscriptions, appointments). Separately grepped
  `UPDATE invoices` (filename-only, in case a multi-line UPDATE has
  `status` non-adjacent to `SET`) — only `crm_service.py` matches.
  State this as "no other `UPDATE invoices` site exists in
  `restoricon_core/services/`", not "no path anywhere" — the grep is
  services/*.py-scoped, not a full-repo claim. Also confirmed this
  scope gap is not a guard bug either way: the void guard reads
  `row["status"]` fresh on every call, so an unknown void-setter
  outside this scope would just make the guard correctly fire, and an
  unknown un-void-setter would make it correctly not fire.
- Enumerated every `record_payment(` caller repo-wide (including
  Codey-Aigentik): the only non-test call site is `routes.py`'s `/pay`
  handler (line 1446). No internal service-to-service, batch, refund,
  or reconciliation caller exists that could be broken by the new
  unconditional `raise`s.
- Guard ordering vs. authorization: `actor.has_permission(
  PERM_WRITE_FINANCIALS)` (line 5370) runs before both new guards
  (5385, and the void check after the row fetch) — the void guard does
  not disclose invoice status to an unauthorized caller; authorization
  is checked first, consistent with the pre-existing `payment_type`
  validation already being downstream of it.
- Read all 4 new tests directly, not just trusted the pass count. Test 3
  (`test_negative_payment_does_not_claw_back_an_existing_credit_row`) is
  the load-bearing one: creates a genuine $500 credit via a real
  overpayment, then attempts a -$200 payment on the same invoice,
  asserts `ValueError` AND that `customer_credits` still has exactly one
  $500 row (not clawed back, not doubled) AND `payments_json` still
  shows only the original TXN-1 payment. This is a real proof of the
  filed consequence, not a placeholder assertion.
- Test 4 ($0.00 still succeeds, status becomes `partially_paid`) is
  ordinary `_recalculate_invoice_balance` behavior unrelated to NEW-651,
  correctly scoped as a regression guard rather than a new bug.
- Rewritten "KNOWN, ACCEPTED LIMITATIONS" comment checked against actual
  code: double-fire (same timestamp/amount twice) is genuinely still
  unguarded (no dedup logic added anywhere in the diff) — comment
  doesn't overclaim. Negative-amount claim in the comment matches the
  new guard. Accurate on both counts.
- Ran the new test file directly (4/4 passed) and the full `tests/`
  suite myself after unsetting `HTTP_PROXY`/`HTTPS_PROXY` per
  [[sandbox_http_proxy_urllib_405_env_artifact]]: **2436 passed, 1
  skipped in 378.30s** — matches the implementer's claimed number
  exactly, not just "close enough."
- `git status --short` on `restoricon_core/` and `tests/` shows exactly
  the two files claimed (crm_service.py modified, new test file
  untracked) — no stray uncommitted changes bleeding in from another
  round.

**Verdict: APPROVED.** Stage `restoricon_core/services/crm_service.py`,
`tests/test_restoricon_core/test_b8_15_round6_void_negative_guards.py`.
