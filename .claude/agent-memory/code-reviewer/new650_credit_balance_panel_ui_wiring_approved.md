---
name: new650-credit-balance-panel-ui-wiring-approved
description: NEW-650 UI half — credit-balance panel wired into Customer 360 (sales portal) — APPROVED, but mid-review self-inflicted git checkout wiped the diff under review
metadata:
  type: project
---

2026-09-26. `restoricon_core/api/web_surfaces.py` (`_render_sales_portal`)
gained a `creditBalance` fan-out entry + `renderCreditBalancePanel()` +
call site inside `renderCustomer360`; two new string-level tests in
`tests/test_restoricon_core/test_b8_4a_customer_360_and_property_panels.py`.
APPROVED after full verification:

- `CRMService.get_customer_credit_balance` uses the same permission
  constants as `list_invoices` (`PERM_READ_FINANCIALS`/`PERM_READ_OWN_
  FINANCIALS`) — confirmed by reading both methods directly.
- BUT the ROLE_CUSTOMER narrowing is NOT identical: `list_invoices`
  silently narrows `customer_id = actor.customer_id`; `get_customer_
  credit_balance` *raises* `PermissionError` (403) for a mismatched
  `customer_id`. The implementer's code comment and test docstring both
  say "gated identically" / "same ROLE_CUSTOMER gating" — that's an
  overclaim for this one case. Ruled non-blocking (Warning only) because
  `/sales` is served to any authenticated role regardless of route guard
  (routes.py serves the HTML unconditionally at `/sales`), and normal
  ROLE_CUSTOMER traffic goes through `render_portal_surface()` instead —
  confirmed via grep that `web_surfaces.py` has zero `ROLE_CUSTOMER`
  references at all, i.e. no role branch exists in this file to race.
  Still logged as a documentation-accuracy issue matching the recurring
  "grep docstring claims against adjacent code, don't assume agreement"
  pattern from [[b8_7b_homecare_subscriptions_clawback_approved]].
- `balance > 0` empty-state boundary checked against the only writer of
  `customer_credits` (crm_service.py ~L5479): insert is gated
  `credit_delta > 0.001`, so a negative balance is currently
  unreachable — no DB-level CHECK exists though, so this is a soft
  guarantee tied to there being exactly one write path today, not a
  schema-enforced invariant. Confirmed via a repo-wide grep for
  `customer_credits` INSERTs (only one hit, non-pycache).
- Currency convention (`'$' + escapeHtml(x.toLocaleString())`) and the
  403/"No access." panel convention are both byte-matched against two
  other panels in the same file (`c360PanelSection`, Invoices/Estimates).
- The cited test `test_customer_360_panel_renders_no_access_on_403_
  not_a_hard_failure` exists and its docstring genuinely states the
  "no client-side role guard" rationale the implementer cited.
- `customer360Modal`/`renderCustomer360` confirmed present only inside
  `_render_sales_portal()` — `render_admin_surface`/`render_tech_surface`
  are separate top-level functions with zero hits for either string.
- Extracted the new function's rendered JS via the same `html.index(...)`
  boundaries the tests use and ran `node --check` on it — genuine syntax
  validation, not just Python f-string brace-escaping (which the 7
  passing tests already prove). Converts "string-level only, no DOM
  harness" from an unverified caveat into a checked claim.
- Reproduced the differential-test technique from [[b8_5b_assessment_photo_round2_approved]]: sed-deleted the call site, re-ran the 2 new
  tests, confirmed the wiring test actually fails (not vacuous).
- Full suite genuinely re-run after the mistake below: 1243 passed in
  288.83s, proxy vars unset per [[sandbox_http_proxy_urllib_405_env_artifact]].

**Self-inflicted incident, log the lesson harder**: mid-review, ran
`git checkout -- restoricon_core/api/web_surfaces.py` to revert my own
sed test-edit and it wiped the entire uncommitted diff under review
(the memory file [[git_checkout_path_wipes_uncommitted_diff]] already
warned about exactly this and I did it anyway). Recovered only because
the full diff text had been captured verbatim earlier in the same
transcript — reconstructed via three `Edit` calls and confirmed
byte-identical with `git diff`. Had the diff not been in scrollback,
this would have destroyed the implementer's uncommitted work.
**Never `git checkout -- <path>` on a file with a live uncommitted diff
under review, even to undo your own scratch edit — `cp` the file to the
scratchpad first, or apply the sed edit to a scratchpad copy instead of
the real file.**
