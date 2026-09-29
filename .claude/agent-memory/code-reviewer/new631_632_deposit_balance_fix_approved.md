---
name: new631-632-deposit-balance-fix-approved
description: NEW-631 (Critical deposit-balance double-count) + NEW-632 (handoff deposit guard) fix, round 1 — APPROVED with 2 new Warning findings
metadata:
  type: project
---

2026-09-25, `restoricon_core/services/crm_service.py` — APPROVED round 1, zero blocking findings. Design B (Ish 2026-09-25): `deposit_amount` becomes a pure target figure, `balance_due` always computed from real payments only via new shared `_recalculate_invoice_balance` helper. `create_invoice` deliberately calls it with `payments=[]` (never `invoice.payments` — a `test_b6_2b1_audit_details.py` fixture builds an `Invoice(payments=[{"note": ...}])` with no `"amount"` key, which would `KeyError` against the hard-key `p["amount"]` used by the helper). `record_payment` calls it with the real list, appended-to before the call (confirmed by reading control flow directly, not assumed).

Exact NEW-631 repro live-reproduced independently (standalone script, not the shipped test): `create_invoice(amount=10000, deposit_amount=5000)` → `balance_due=10000`; `record_payment(5000, payment_type='deposit')` → `balance_due=5000, status='partially_paid'`.

Epsilon (0.001) for the summed deposit-tagged-payment guard tested independently at 3 different scales (0.3, 3000, 15000) in both directions — forgives genuine float drift (`0.1+0.1+0.1` vs `0.3`), never a genuine one-cent shortfall. Confirmed correctly scoped.

**Found something the implementer's own summary never mentioned**: `Invoice.invoice_type` defaults to `"other"`, not `"project"` (models.py dataclass default). NEW-632's guard filters to `invoice_type == 'project'` only. The one production caller (`POST /api/v1/invoices` → `Invoice(**json_body)` in `api/routes.py`) has zero validation/default forcing `invoice_type='project'`. Test suite's `_make_invoice` helper defaults to `invoice_type="project"` explicitly, which is exactly why this never surfaced in the shipped tests — same fixture-masks-reality shape as [[b8_3_lead_convert_stage_analytics_round2_approved]] and [[b8_5b_assessment_photo_round2_approved]]. My own first live-repro attempt hit this trap (forgot to pass `invoice_type='project'`, got a false "correctly blocked" result for the wrong reason) before re-running with it explicit. Zero blast radius today (no frontend creates invoices yet, grepped for JS hitting `/api/v1/invoices`, found none) but a real footgun for the next integration/UI built against this endpoint. Recommended as a new NEW-### (Warning).

**Why:** confirms the standing pattern — a test helper's sensible-looking default can silently hide a production gap in the same round that narrows a guard's eligibility filter. Any time a round adds a `WHERE column = 'X'` filter to a guard, check what the *dataclass default* for that column actually is and whether the only production writer enforces or even sets it.

**How to apply:** whenever reviewing a round that narrows eligibility via a new column filter (invoice_type, status, category, etc.), don't just check the filter logic in isolation — trace back to (a) the field's dataclass/schema default, and (b) whether the real production write path sets it explicitly or relies on that default. A passing test suite with a fixture default that happens to match the filter is not evidence the production path does too.

Full suite: 2454 passed, 1 skipped, 406.47s — matched claimed 2446→2454 (+8) exactly. Full-suite `pytest -q` run took ~6m46s in this sandbox; a `timeout 300` wrapper killed it prematurely (exit 143, not a real failure) — use a `ps`-poll wait loop or a longer timeout instead of trusting a short `timeout N` wrapper on the full suite here.
