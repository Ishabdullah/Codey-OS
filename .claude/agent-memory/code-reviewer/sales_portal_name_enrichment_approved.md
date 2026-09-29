---
name: sales-portal-name-enrichment-approved
description: Sales Rep Portal customer/rep name-enrichment fix (routes.py/crm_service.py/web_surfaces.py) — APPROVED first round
metadata:
  type: project
---

Round fixing Ish's "Cust #3"/bare-rep-number raw-id display bug across the
Sales Rep Portal (leads/opportunities tables, lead detail modal, commission
rankings, Communications Center panel, New Lead create form). APPROVED on
first pass, 2026-09-26.

Design that held up under adversarial check:
- New `CRMService._get_customer_display_name(customer_id)` is deliberately
  ungated (no actor param, no [[new568_customer_rep_narrowing_changes_requested|NEW-568]]
  ownership check) — verified it only ever returns a name (first+last or
  company_name fallback), never other customer fields, and every call site
  (`APIRouter._resolve_customer_names`) only ever passes ids pulled from rows
  the caller already fetched through an already-scoped list/get call
  (list_leads(actor), get_lead(actor), list_communication_records(actor)) —
  never a raw request-param id. Same pattern already established for
  `AuthService.get_user_by_id` (pre-existing, no gate) reused for rep names.
- Batch resolution genuinely dedupes via `{c for c in ids if c is not None}`
  set comprehension before querying — confirmed no N+1.
- Response-shape changes are additive: `customer_id`/`assigned_user_id` keys
  verified still present alongside new `customer_name`/`assigned_user_name`
  on every enriched route.
- Scope call verified reasonable: opportunities route deliberately skips
  `customer_name` (no UI column consumes it) despite discovering
  `opportunities.customer_id` is actually NOT NULL (contrary to architect's
  spec assumption) — logged as a finding rather than silently adding an
  unconsumed key or silently fixing scope creep.
- `commission_summary_rows` confirmed to be real dicts (not sqlite3.Row) via
  `get_team_commission_summary`'s own return statement, so `{**row, ...}`
  spread in the ranking response is safe.
- New Lead modal: `<select>` populated from `window.currentSalesCustomers`
  cache; `submitCreateLead()`'s `if (custIdRaw)` guard correctly still
  treats the `<select>`'s empty-string "-- none --" value as falsy, same as
  the old empty `<input type="number">` behaviour — confirmed unchanged.
- Test file `test_sales_portal_name_enrichment.py` asserts actual resolved
  name values (not just key presence); `test_sales_portal_leads_opportunities.py`
  additions assert both the new patterns exist AND the old raw-id patterns
  (`'Cust #'`, `String(l.assigned_user_id)` etc.) are gone — real regression
  coverage, not just "new code exists" tests.
- Reproduced the implementer's proxy-artifact claim exactly: `test_api.py`
  gave 57 failures with ambient `HTTP_PROXY`/`HTTPS_PROXY` set in this
  sandbox, 57 passed with `NO_PROXY="127.0.0.1,localhost"` — matches
  [[sandbox_http_proxy_urllib_405_env_artifact]]. Full `tests/test_restoricon_core/`
  suite: 1253 passed in 422.88s with `NO_PROXY` set.
- `install.sh` correctly untouched — no new dependency introduced.

Nothing blocking found. Only noise: `.claude/agent-memory/code-reviewer/MEMORY.md`
itself showed as modified in the working tree at review time — unrelated to
this task, a repeat of [[working_tree_cross_round_bleed]], not worth blocking
a functional-code review on.
