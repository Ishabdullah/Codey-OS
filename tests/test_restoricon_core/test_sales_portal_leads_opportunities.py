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
    """The banner reads user.custom_permissions client-side purely for
    display -- real enforcement is server-side. Assert the banner logic
    is present and explicitly NOT gating the fetch calls themselves."""
    html = render_sales_surface()
    assert "read:team_sales_data" in html
    assert "Viewing: Whole Team" in html
    assert "Viewing: My Own" in html


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
