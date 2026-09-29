---
name: new661-documents-names-and-new-lead-typeahead-xss-changes-requested
description: NEW-661 documents customer_name/project_name enrichment APPROVED; New Lead type-ahead's onclick=JSON.stringify(c) pattern is a real, live-reproduced attribute-breakout XSS via customer first_name/last_name — CHANGES REQUESTED
metadata:
  type: project
---

Third round extending [[sales_portal_name_enrichment_approved]] /
[[staff_portal_projects_name_enrichment_approved]]. Two independent fixes;
split verdict.

**Fix 1 (NEW-661, `_get_project_display_name` + `_resolve_project_names` +
documents route + admin panel): APPROVED.** Same shape as the already-approved
`_get_customer_display_name`/`_resolve_customer_names` — ungated, name-only
(`title` only), every `project_id` passed to it comes from `d.project_id` on
rows `crm.list_documents(actor, ...)` already returned (that method's own
gate: `PERM_READ_DOCUMENTS`/`PERM_READ_OWN_DOCUMENTS` permission check, plus a
`ROLE_CUSTOMER`-only `customer_id` override — **note this is a permission
gate, not ownership narrowing**, for non-customer roles the `PERM_READ_OWN_DOCUMENTS`
holder gets zero id-based restriction; that asymmetry is pre-existing,
unrelated to this diff, logged here as a rule-8 Suspected finding worth a
future NEW-### but not blocking). Fallback strings `'Customer #' + id` /
`'Project #' + id` match convention exactly. `window.currentSalesCustomers`
grep-confirmed zero remaining reads anywhere in `web_surfaces.py` (only
hits left are the test file's own negative assertions). Additive-only
confirmed (customer_id/project_id keys untouched).

**Fix 2 (New Lead type-ahead): CHANGES REQUESTED — blocking XSS, not the
claimed "pre-existing cosmetic bug".** The implementer flagged
`onclick='selectNewLeadCustomer(${JSON.stringify(c)})'` as "breaks for an
apostrophe in a customer name" and framed it as a replicated pre-existing
issue from the guided-contract-flow's `guidedSelectCustomer` (same pattern,
web_surfaces.py:7894). Live-reproduced it goes further than a broken button:

```
node -e "const c={id:1,first_name:\"O' onmouseover='alert(document.cookie)\",last_name:'X',customer_number:5,phone:'555'};console.log(\`<button onclick='selectNewLeadCustomer(\${JSON.stringify(c)})'>Select</button>\`)"
# => <button onclick='selectNewLeadCustomer({"id":1,"first_name":"O' onmouseover='alert(document.cookie)","last_name":"X",...})'>Select</button>
```

The apostrophe in `first_name` terminates the single-quoted `onclick`
attribute early; everything after it — including an attacker-supplied
`onmouseover='...'` — becomes a **new, live HTML attribute on the button**.
Any user who can create/edit a customer record (any sales rep) fully
controls `first_name`/`last_name`, and this fires for anyone who later
searches for that customer's name in the New Lead modal (or the guided
flow, same bug). This is a genuine stored/DOM injection vector, not a
fail-safe cosmetic break — per the task's explicit instruction, replicating
a real security bug into a second location is blocking even though the
first instance already shipped.

`customer_number` interpolated unescaped in the same block
(`(#${{c.customer_number}})`) is *not* a second sink — confirmed
`customer_number` is `INTEGER` in the schema (`database.py:1716`,
`ALTER TABLE customers ADD COLUMN customer_number INTEGER`), so it can't
carry a quote character.

**Required fix, both call sites (this round, not deferred — standing rule
[[feedback_fix_related_findings_immediately]] makes the guided flow's
identical bug at web_surfaces.py:7894 an in-scope related finding, not a
separate future ticket):** stop inlining `JSON.stringify(c)` into a
single-quoted HTML attribute. Hold the fetched `matches` array in a
module-scope variable (or re-fetch by id) and emit
`onclick="selectNewLeadCustomer(${{c.id}})"` (numeric, double-quoted,
untouched by any string field), looking the full record up by id inside
the handler.

**Secondary Warning (non-blocking) also in the highest-scrutiny area of
this diff (item 4, state reset):** `openCreateLeadModal()` resets the
search input, results div, hidden id, label, and Change-button visibility
correctly, but never calls `clearTimeout(newLeadSearchDebounce)`. A
pending 250ms debounce timer from a search typed just before closing a
prior modal session can fire after the reset and repopulate
`newLeadCustomerResults` with stale rows in a freshly-opened modal. Does
NOT cause the wrong-customer-attached bug the task was specifically
worried about (the hidden `newLeadCustomerId` only changes on an explicit
`selectNewLeadCustomer()` click, never from a stale render), so Warning
not Critical — but flag explicitly since it's in the exact function the
task said to scrutinize hardest.

Test evidence gathered directly (not trusted from implementer's summary):
- 49/49 targeted tests passed (test_b8_6d_a_contract_pdf.py +
  test_sales_portal_leads_opportunities.py + test_web_surfaces_admin_wiring.py).
- Full `tests/test_restoricon_core/` with proxy vars fully unset: 1260
  passed, 0 failed (437.23s) — this is the authoritative full-suite number,
  more reliable than the `NO_PROXY`-only run since it removes the ambient
  var entirely.
- Reproduced [[sandbox_http_proxy_urllib_405_env_artifact]] exactly on the
  4 named files: 65 failed with ambient proxy, 127 passed with
  `NO_PROXY="127.0.0.1,localhost"` — matches implementer's claimed numbers
  verbatim.
- `git diff | grep -n 'PERM_\|ROLE_'` across all three source files: zero
  matches (exit 1) — literal confirmation no RBAC/permission constant was
  touched.
- `submitCreateLead()` reads `document.getElementById('newLeadCustomerId').value`
  generically — no `<select>`-specific access, works unchanged with the new
  hidden input.

New pattern for this project's memory: **`onclick='fn(${JSON.stringify(obj)})'`
is a recurring unescaped-attribute-breakout pattern** — any object field
containing user-editable free text (names, notes, addresses) that reaches
this pattern is a live XSS candidate, not just a "special characters break
the button" cosmetic issue. Grep for `JSON.stringify(` inside `onclick=`
attributes project-wide next time one of these name-enrichment/type-ahead
rounds comes up — this is the second such construct found
(`guidedSelectCustomer` originally, now `selectNewLeadCustomer` copying it).
