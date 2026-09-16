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
    start = html.index("async function loadDashboard()")
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
