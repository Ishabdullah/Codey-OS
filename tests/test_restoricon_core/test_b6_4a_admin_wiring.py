from restoricon_core.api.web_surfaces import render_admin_surface

def test_admin_surface_contains_fetch_calls():
    html = render_admin_surface()
    
    # Assert fetch calls to /api/v1/business-profile exist (both GET and POST usually represented in the JS)
    assert "'/api/v1/business-profile'" in html or '"/api/v1/business-profile"' in html
    
    # Assert fetch calls to /api/v1/schedule-config exist
    assert "'/api/v1/schedule-config'" in html or '"/api/v1/schedule-config"' in html
