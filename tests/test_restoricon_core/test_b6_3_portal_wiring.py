import pytest
from restoricon_core.api.web_surfaces import render_portal_surface

def test_portal_surface_wiring():
    """
    Test that the portal surface JS contains dynamic fetch calls to the live API endpoints
    instead of hardcoded placeholders, satisfying B6.3 exit criteria.
    """
    html = render_portal_surface()
    
    # Assert JS contains fetch calls to real endpoints
    assert "'/api/v1/portal/projects'" in html, "Missing fetch for projects"
    assert "`/api/v1/portal/projects/${projectId}/milestones`" in html, "Missing dynamic fetch for project milestones"
    assert "`/api/v1/portal/invoices?project_id=${projectId}`" in html, "Missing dynamic fetch for invoices"
    assert "`/api/v1/portal/contracts?project_id=${projectId}`" in html, "Missing dynamic fetch for contracts"
    assert "'/api/v1/portal/messages'" in html, "Missing fetch for messages"
    
    # Also assert the contract signature POST is dynamically constructed
    assert "`/api/v1/portal/contracts/${window.currentContractId}/sign`" in html, "Missing dynamic contract signature route"
