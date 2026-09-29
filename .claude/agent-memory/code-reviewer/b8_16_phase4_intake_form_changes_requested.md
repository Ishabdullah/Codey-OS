---
name: b8_16_phase4_intake_form_changes_requested
description: B8.16 Phase 4 (work-order-intake form UI + salesperson-roster RBAC endpoint) — CHANGES REQUESTED round 1, two real bugs the source-level test suite couldn't catch
metadata:
  type: project
---

Reviewed 2026-09-29 (not committed at review time): new `PERM_READ_SALESPERSON_ROSTER`
permission + `SALES_ATTRIBUTION_ROLES` role-set + `AuthService.list_salesperson_roster`
(`restoricon_core/auth.py`), new `POST /api/v1/operations/work-order-intake` +
`GET /api/v1/operations/salesperson-roster` routes, new `_render_work_order_intake_section`
form UI (`restoricon_core/api/web_surfaces.py`), 18 new tests. XSS discipline, RBAC gating,
role-set scoping, and the `PERM_READ_TEAM_SALES_DATA`-as-bypass claim all verified genuine
(revert-tested both escapeHtml calls, both regression tests fail as expected). **Verdict:
CHANGES REQUESTED** — two bugs the diff-read + test suite alone missed, both surfaced by the
advisor call before finalizing:

1. **`tbody.innerHTML = ...` full re-render on every `oninput` keystroke destroys focus/caret.**
   `woiUpdateLineItem` unconditionally calls `woiRenderLineItems()`, which reassigns
   `tbody.innerHTML`, detaching and recreating the currently-focused `<input>` node on every
   character typed. No DOM harness needed — deterministic from reading the code (an `innerHTML`
   reassignment always destroys focused descendants). None of the 18 tests catch it: all are
   source-level string assertions with no interaction/rendering model, so a functional
   UX-breaking bug in the form's *primary* interaction shipped invisible to the test suite.
   **New bug-class to watch for**: any `on<event>` handler on a text/number input that triggers
   a full parent `innerHTML =` re-render of the row/table it lives in — always destroys focus,
   always needs to be a from-scratch code read, source-level tests will never catch it.

2. **A "same discipline as elsewhere" 401 handler called a function (`logoutUser()`) that isn't
   defined in the template it was copied into.** `_render_work_order_intake_section`'s fetch
   handler called `logoutUser()` on 401, but that function only exists in `_get_common_script()`
   (a different helper this template never includes) — `_render_staff_portal_base`'s own actual
   401 convention is `window.location.href = '/admin/login'`. The resulting `ReferenceError` was
   caught by the surrounding `try/catch` and silently converted into a generic "failed to load"
   message — masking session expiry as a network/server error. **Lesson**: when new client-side
   code calls a same-surface helper function "matching an existing pattern," grep for that
   function's actual definition **within the specific template being extended**, not just
   anywhere in the file — helper functions can be scoped to a different render function's own
   script block and simply not present in the one being edited.

Also worth noting: the implementer's own `NEW-682` disclosure (unvalidated `salesperson_user_id`
in `submit_work_order_intake`) undersold its own severity as "data-integrity/correctness," but
tracing one hop further (`record_payment` → `rep_user_id = row["assigned_user_id"]` →
`CommissionService.record_commission`, zero role check anywhere in that chain) shows it's a real
self-dealing money-diversion path (a technician can attribute a sale to themselves and collect
a real commission). The deferral was still reasonable (Phase 2's orchestrator, out of this
round's scope) but the ledger wording needed the correction — rule 6 applies to severity
undersells found during review, not just outright-wrong claims.

See also [phase0b_role_subcontractor_round3_documents_fix_approved](phase0b_role_subcontractor_round3_documents_fix_approved.md)
and [new661_documents_names_and_new_lead_typeahead_xss_changes_requested](new661_documents_names_and_new_lead_typeahead_xss_changes_requested.md)
for the established XSS-regression-test revert-and-rerun technique this round reused successfully.
