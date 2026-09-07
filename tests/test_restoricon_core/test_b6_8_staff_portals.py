from restoricon_core.api.web_surfaces import (
    render_pm_surface,
    render_sales_surface,
    render_tech_surface,
    render_subcontractor_surface,
    render_login_surface
)

def test_staff_portals_render_and_fetch():
    """Verify that the staff portals render properly and contain the required fetch logic."""
    portals = [
        render_pm_surface(),
        render_sales_surface(),
        render_tech_surface(),
        render_subcontractor_surface()
    ]
    
    for html in portals:
        assert "fetch('/api/v1/projects'" in html, "Portal is missing projects fetch"
        assert "fetch('/api/v1/staff-schedules" in html, "Portal is missing staff-schedules fetch"
        assert "window.onload = loadDashboard;" in html, "Dashboard load hook missing"

def test_smart_login_routing_patch():
    """Verify that render_login_surface contains the smart B6.8 JS redirect logic."""
    html = render_login_surface("admin")
    assert "data.user.role" in html, "Smart redirect missing role check"
    assert "target = '/pm';" in html, "Smart redirect missing /pm route"
    assert "target = '/subcontractor';" in html, "Smart redirect missing /subcontractor route"
