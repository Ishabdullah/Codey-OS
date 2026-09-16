from restoricon_core.api.web_surfaces import (
    render_pm_surface,
    render_sales_surface,
    render_tech_surface,
    render_subcontractor_surface,
    render_login_surface
)

def test_staff_portals_render_and_fetch():
    """Verify that the staff portals render properly and contain the required fetch logic.

    render_sales_surface() is deliberately excluded here (NEW-533): it no
    longer serves the shared fetch('/api/v1/projects') "Assignments" panel
    -- that was the cross-rep leak this round fixed. It has its own
    dedicated coverage below and in test_sales_portal_leads_opportunities.py.
    """
    portals = [
        render_pm_surface(),
        render_tech_surface(),
        render_subcontractor_surface()
    ]

    for html in portals:
        assert "fetch('/api/v1/projects'" in html, "Portal is missing projects fetch"
        assert "fetch('/api/v1/staff-schedules" in html, "Portal is missing staff-schedules fetch"
        assert "window.onload = loadDashboard;" in html, "Dashboard load hook missing"

def test_staff_portal_dashboard_handles_401():
    """NEW-512: loadDashboard()'s staff-schedules and projects fetches must redirect
    to /admin/login on a 401, using this surface's own idiom (no logoutUser(), which
    is not in scope here since _get_common_script() is never injected).

    render_sales_surface() is excluded here for the same reason as above --
    see test_sales_portal_leads_opportunities.py for its 401 coverage.
    """
    portals = [
        render_pm_surface(),
        render_tech_surface(),
        render_subcontractor_surface()
    ]

    for html in portals:
        # Isolate loadDashboard() so region-scoped assertions can't match the
        # /auth/me guard or the Sign Out button by accident.
        start = html.index("async function loadDashboard()")
        end = html.index("window.onload = loadDashboard;")
        dashboard_js = html[start:end]

        schedules_region_start = dashboard_js.index("fetch('/api/v1/staff-schedules")
        schedules_region_end = dashboard_js.index("await res.json();", schedules_region_start)
        schedules_region = dashboard_js[schedules_region_start:schedules_region_end]
        assert "res.status === 401" in schedules_region, "staff-schedules fetch missing 401 check"
        assert "window.location.href = '/admin/login';" in schedules_region

        projects_region_start = dashboard_js.index("fetch('/api/v1/projects'")
        projects_region_end = dashboard_js.index("await res.json();", projects_region_start)
        projects_region = dashboard_js[projects_region_start:projects_region_end]
        assert "res.status === 401" in projects_region, "projects fetch missing 401 check"
        assert "window.location.href = '/admin/login';" in projects_region

        # logoutUser() must never appear inside loadDashboard() -- it is not in
        # scope for this surface (_get_common_script() is never injected here).
        assert "logoutUser(" not in dashboard_js


def test_smart_login_routing_patch():
    """Verify that render_login_surface contains the smart B6.8 JS redirect logic."""
    html = render_login_surface("admin")
    assert "data.user.role" in html, "Smart redirect missing role check"
    assert "target = '/pm';" in html, "Smart redirect missing /pm route"
    assert "target = '/subcontractor';" in html, "Smart redirect missing /subcontractor route"


def test_smart_login_routing_has_sales_manager():
    """D2, sales_rep_portal.md §4: a sales_manager login must route to
    the same /sales portal as a plain sales login."""
    html = render_login_surface("admin")
    assert "r === 'sales_manager'" in html
    i = html.index("r === 'sales_manager'")
    j = html.index(";", i) + 1
    assert "target = '/sales';" in html[i:j]
