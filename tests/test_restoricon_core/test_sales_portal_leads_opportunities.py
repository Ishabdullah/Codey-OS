"""NEW-533: render_sales_surface() must serve dedicated leads/opportunities
panels backed by /api/v1/leads and /api/v1/opportunities, not the shared
fetch('/api/v1/projects') "Assignments" panel every other staff portal
uses -- that shared panel was the cross-rep visibility leak this round
closed. Real narrowing is server-side (CRMService._scoped_assignee_filter,
see tests/test_restoricon_core/test_crm_sales_engine.py); this file only
covers the portal's rendered HTML/JS shape."""

from restoricon_core.api.web_surfaces import render_sales_surface


def test_sales_portal_serves_leads_and_opportunities_fetches():
    html = render_sales_surface()
    assert "fetch('/api/v1/leads'" in html, "Sales portal is missing leads fetch"
    assert "fetch('/api/v1/opportunities'" in html, "Sales portal is missing opportunities fetch"
    assert "fetch('/api/v1/projects'" not in html, "Sales portal must not use the shared projects fetch (NEW-533 leak)"
    assert "window.onload = loadDashboard;" in html, "Dashboard load hook missing"


def test_sales_portal_leads_and_opportunities_handle_401():
    html = render_sales_surface()
    start = html.index("async function loadDashboard(redirectOnIndeterminate = true)")
    end = html.index("window.onload = loadDashboard;")
    dashboard_js = html[start:end]

    leads_region_start = dashboard_js.index("fetch('/api/v1/leads'")
    leads_region_end = dashboard_js.index("await res.json();", leads_region_start)
    leads_region = dashboard_js[leads_region_start:leads_region_end]
    assert "res.status === 401" in leads_region, "leads fetch missing 401 check"
    assert "window.location.href = '/admin/login';" in leads_region

    opps_region_start = dashboard_js.index("fetch('/api/v1/opportunities'")
    opps_region_end = dashboard_js.index("await res.json();", opps_region_start)
    opps_region = dashboard_js[opps_region_start:opps_region_end]
    assert "res.status === 401" in opps_region, "opportunities fetch missing 401 check"
    assert "window.location.href = '/admin/login';" in opps_region

    assert "logoutUser(" not in dashboard_js


def test_sales_portal_viewer_scope_banner_is_display_only():
    """NEW-552: the banner used to read user.custom_permissions client-side,
    which missed any actor with team access via the real ROLE_SALES_MANAGER
    role rather than a custom_permissions override. It now derives from
    data.scope === 'team' off the /api/v1/sales/dashboard response (the
    authoritative signal, no OR-fallback to the old check) and fails closed
    to 'My Own' until that response confirms 'team'. Assert the banner logic
    is present and explicitly NOT gating the fetch calls themselves."""
    html = render_sales_surface()
    assert "read:team_sales_data" not in html, (
        "NEW-552: old custom_permissions-based banner check must be fully "
        "removed, not left as a fallback alongside the new one"
    )
    assert "data.scope === 'team'" in html
    assert "Viewing: Whole Team" in html
    assert "Viewing: My Own" in html
    assert "scopeBanner.textContent = 'Viewing: My Own';" in html, (
        "banner must default (fail closed) to 'My Own' before any dashboard "
        "response is confirmed"
    )


def test_sales_portal_has_claim_buttons_and_fetch_calls():
    """NEW-534: unclaimed leads/opportunities render a Claim button in
    place of the old plain 'Unclaimed' text, wired to POST the new claim
    routes."""
    html = render_sales_surface()
    assert "claimLead(" in html
    assert "claimOpportunity(" in html
    # Anchor on the actual button markup, not just the function definition
    # existing -- the spec requires an "Unclaimed" row to still render a
    # clickable Claim button, not just the JS function being present.
    assert 'onclick="claimLead(\' + l.id + \')">Claim</button>' in html
    assert 'onclick="claimOpportunity(\' + o.id + \')">Claim</button>' in html
    assert "Unclaimed" in html, "Unclaimed label must still render alongside the Claim button"
    assert "/api/v1/leads/' + id + '/claim'" in html
    assert "/api/v1/opportunities/' + id + '/claim'" in html

    claim_lead_js = html[html.index("async function claimLead("):html.index("async function claimOpportunity(")]
    assert "method: 'POST'" in claim_lead_js
    assert "'Authorization': 'Bearer ' + token" in claim_lead_js
    assert "loadDashboard();" in claim_lead_js

    claim_opp_js = html[html.index("async function claimOpportunity("):html.index("window.onload = loadDashboard;")]
    assert "method: 'POST'" in claim_opp_js
    assert "'Authorization': 'Bearer ' + token" in claim_opp_js
    assert "loadDashboard();" in claim_opp_js


def test_sales_portal_leads_and_opportunities_render_names_not_raw_ids():
    """Ish reported the portal showed raw customer/rep ids ("Cust #3", a
    bare rep number) instead of names. Leads/opportunities tables, the
    lead detail modal, and the commission rankings table must all prefer
    the new customer_name/assigned_user_name/rep_user_name fields, with a
    'Customer #id'/'User #id' fallback (matching the calUserName
    convention) only when a name failed to resolve."""
    html = render_sales_surface()
    assert "l.customer_name || ('Customer #' + l.customer_id)" in html
    assert "l.assigned_user_name || ('User #' + l.assigned_user_id)" in html
    assert "o.assigned_user_name || ('User #' + o.assigned_user_id)" in html
    assert "r.rep_user_name || ('User #' + r.rep_user_id)" in html
    # Lead detail modal
    assert "l.customer_name || ('Customer #' + l.customer_id)) : 'None linked'" in html
    assert "Assigned: ${escapeHtml(l.assigned_user_name || ('User #' + l.assigned_user_id))}" in html
    # No stray raw-id-only rendering left over from before the fix. Bare
    # "'Cust #'" (not just "'Cust #' + l.customer_id") also catches the
    # Communications Center panel's own copy of the same symptom, which
    # used a different variable name (c.customer_id, not l.customer_id).
    assert "'Cust #'" not in html
    assert "String(l.assigned_user_id)" not in html
    assert "String(o.assigned_user_id)" not in html
    assert "String(r.rep_user_id)" not in html


def test_communications_center_panel_shows_customer_name_not_raw_id():
    """Ish's reported symptom ("Cust #3") also appeared in the
    Communications Center panel's linkedTo computation, a separate
    /api/v1/sales/communications-center fetch from the leads table above --
    covered by its own test since it's a distinct code path/endpoint."""
    html = render_sales_surface()
    assert "c.customer_name || ('Customer #' + c.customer_id)" in html
    assert "c.lead_id ? 'Lead #' + c.lead_id : '—'" in html, (
        "lead_id half must be left alone per spec -- leads have no "
        "independent name field"
    )


def test_new_lead_modal_customer_field_is_a_live_type_ahead_search():
    """NEW-663 superseded: the New Lead create form's customer field went
    through two shapes -- a bare `<input type="number">` (raw id), then a
    `<select>` populated from a static window.currentSalesCustomers cache
    (stale-preload gap = NEW-663), and is now live per-keystroke type-ahead
    search matching the guided-contract-flow's own established pattern
    (guidedSearchCustomers/guidedSelectCustomer). A hidden input keeps the
    same `newLeadCustomerId` id so submitCreateLead()'s existing
    `if (custIdRaw)` guard needs no changes."""
    html = render_sales_surface()
    assert '<input type="number" id="newLeadCustomerId">' not in html
    assert '<select id="newLeadCustomerId">' not in html
    assert "function populateNewLeadCustomerSelect()" not in html
    assert "window.currentSalesCustomers" not in html
    assert '<input type="hidden" id="newLeadCustomerId" value="">' in html
    assert 'id="newLeadCustomerSearch"' in html
    assert 'oninput="searchNewLeadCustomers()"' in html
    assert 'id="newLeadCustomerResults"' in html
    assert "async function searchNewLeadCustomers()" in html
    assert "function selectNewLeadCustomer(customerId)" in html
    assert "document.getElementById('newLeadCustomerId').value = customer.id;" in html
    assert "if (custIdRaw)" in html, "empty-value read-side guard must be untouched"


def test_new_lead_and_guided_flow_customer_select_no_json_stringify_onclick():
    """NEW-XXX (this round): JSON.stringify(c) inlined into a single-quoted
    onclick attribute is a stored-XSS breakout vector -- a customer name
    containing a single quote (e.g. malicious ' onmouseover=... content set
    via the ordinary customer create/edit form, no special privilege gate)
    breaks out of the attribute. Both the New Lead modal's
    selectNewLeadCustomer and the guided-contract-flow's guidedSelectCustomer
    must pass a bare numeric id through a double-quoted onclick and look the
    customer object up from a held search-results array instead."""
    html = render_sales_surface()
    assert "onclick='selectNewLeadCustomer(${JSON.stringify" not in html
    assert "onclick='guidedSelectCustomer(${JSON.stringify" not in html
    assert 'onclick="selectNewLeadCustomer(${c.id})"' in html
    assert 'onclick="guidedSelectCustomer(${c.id})"' in html
    assert "let newLeadSearchResults = [];" in html
    assert "let gflowSearchResults = [];" in html
    assert "function guidedSelectCustomer(customerId)" in html
    assert "function guidedSelectCustomerObj(customer)" in html
    assert "guidedSelectCustomerObj(data.customer);" in html


def test_sales_portal_auto_refreshes_via_interval():
    """D3 (sales_rep_portal.md §4a item 3): Ish chose the cheap 10-15s
    periodic-refresh fix over the full SSE push layer
    (docs/realtime_push_design.md, designed but not implemented). A
    401-confirmed auth failure still redirects unconditionally; a network
    blip or ambiguous non-401 response on an unattended interval tick must
    not silently eject an actively-working rep to the login screen."""
    html = render_sales_surface()
    assert "setInterval(() => loadDashboard(false), 12000);" in html, \
        "Sales portal must poll loadDashboard every 12s (D3 fix, 10-15s range)"
    assert "async function loadDashboard(redirectOnIndeterminate = true)" in html
    assert "if (redirectOnIndeterminate) { window.location.href = '/admin/login'; }" in html
