---
name: b8_8b2_financing_ar_offset_approved
description: B8.8b-2 financing AR offset wiring into get_ar_aging/get_financial_summary/get_project_pnl — APPROVED round1, one Warning
metadata:
  type: project
---

2026-09-23, `restoricon_core/services/finance_service.py` +
`tests/test_restoricon_core/test_b8_8b2_financing_ar_offset.py` (18 new
tests). Rule-4 money-computation round wiring live financing offsets
(from B8.8b-1's inert table, see [[b8_8b1_financing_records_inert_approved]])
into AR aging / financial summary / project P&L. APPROVED round 1.

**What was independently verified (not just read):**
- The `get_project_pnl` misattribution guard (per-invoice clamp before
  sum, not sum-then-clamp) — live-reproduced the exact scenario from the
  task brief (invoice A paid off in cash but with a stale `'approved'`
  financing row still linked to it, invoice B with a real balance and no
  financing, same project): confirmed invoice A's stale offset does NOT
  spill onto invoice B. `linked_offset = sum(min(offset_by_invoice.get(r["id"], 0.0), float(r["balance_due"])) for r in proj_inv_rows)` — clamp is
  per-row, character-verified against the diff.
- Reconciliation identity (`total_ar_gross - total_financed_offset ==
  total_ar`) holds under over-financing with realistic 2-decimal-cent
  inputs.
- Live re-evaluation (voiding a record makes its offset vanish on the
  very next `get_ar_aging` read, no caching) — reproduced independently,
  not just trusting the round's own test.
- Both NEW-614 shapes (voided-but-still-`'approved'` excluded via
  `status='active' AND application_status IN (...)` together; NULL-
  `invoice_id` rows excluded from the invoice-scoped helper, included
  only in the project-scoped unlinked helper).
- RBAC: `PERM_READ_FINANCE` unchanged, same permission constant, all 3
  methods, unmoved gate lines.
- `AnalyticsSearchService`'s AR total is a genuinely separate raw-SQL
  query (`SUM(balance_due) FROM invoices WHERE balance_due > 0`), never
  calls `get_ar_aging` — confirms the NEW-613 "deliberately not wired"
  deferral claim is true, not just asserted.
- No consumer in this repo currently reads the netted `total_ar`/
  `total_outstanding`/`ar_buckets` keys and does further money math on
  them as if they were gross (no dashboard JS exists yet for this data;
  `routes.py` only passes the dicts through unmodified). Re-check this
  the moment a finance dashboard panel is built against these endpoints
  — that's exactly the shape of bug this project has been bitten by
  before (B8.2b "verify every JS field name against real service
  shapes").
- SQLite `MAX_VARIABLE_NUMBER=32766` confirmed via `PRAGMA
  compile_options` on this build. `get_ar_aging`'s invoice query is
  actually filtered (`status IN ('sent','partially_paid','overdue') AND
  balance_due > 0`), not literally "unfiltered/company-wide" as the
  implementer's own comment claims — but this only makes the
  32,766-simultaneous-open-invoices threshold even less reachable, so
  the "impractical at Restoricon's scale" conclusion still holds; just
  correct the mischaracterization if it matters later.
- Full suite: 2309 → 2327 passed (+18 exactly), 1 skipped, matched the
  implementer's claim verbatim. `git diff -- tests/test_finance_service.py`
  empty (pre-existing suite genuinely untouched). No `install.sh`/
  `requirements.txt` changes (none needed).

**One Warning (not blocking, logged for awareness, not yet in
NEW_ISSUES.md as of this write — flag for coordinator to log):** the
"identity holds exactly" claim is NOT strictly true for sub-cent
`amount_financed` inputs — `_validate_non_negative_amount` only checks
non-negativity, never rounds to 2 decimals, so a caller passing e.g.
`amount_financed=166.665` across a few invoices can produce a real
1-cent mismatch between `total_ar_gross - total_financed_offset` and
`total_ar` (three independently-accumulated-then-rounded running sums,
not one). Reproduced live: 3×(bal=333.33, financed=166.665) gives
gross=999.99, offset=500.0, total_ar=500.0, but
`round(999.99-500.0,2)=499.99 != 500.0`. Not reachable with normal
2-decimal-cent currency values (verified separately — realistic cent
inputs reconcile exactly), and this validation gap pre-dates B8.8b-2
(inherited from B8.8b-1's `_validate_non_negative_amount`), so it's not
a regression this round introduced — just an overclaim in the round's
own documentation/comments that should be softened, and a good target
for a `_validate_non_negative_amount` cent-rounding guard if anyone
ever revisits `FinancingService`.

Reusable technique: when a round claims an arithmetic "identity holds
exactly," don't just trust the round's own round-dollar test fixtures —
retest with a sub-cent input specifically designed to expose
independent-rounding drift between separately-accumulated sums.
