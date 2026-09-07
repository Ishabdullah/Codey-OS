from restoricon_core.api.web_surfaces import render_admin_surface

def test_b6_4_admin_wiring_tabs_has_fetches():
    html = render_admin_surface()
    
    # Check KPI board endpoints
    assert "'/api/v1/reports/summary'" in html
    assert "loadKPIs()" in html
    
    # Check Operations and Subcontractors endpoints
    assert "'/api/v1/operations/equipment'" in html
    assert "loadEquipment()" in html
    
    assert "'/api/v1/operations/subcontractors'" in html
    assert "loadSubcontractors()" in html
    
    # Check Finance endpoints
    assert "'/api/v1/finance/summary'" in html
    assert "loadFinance()" in html
    
    # Check Comms endpoints
    assert "'/api/v1/communications'" in html
    assert "loadComms()" in html
    
    # Check BizOps endpoints
    assert "'/api/v1/marketing/campaigns'" in html
    assert "'/api/v1/compliance/items'" in html
    assert "loadBizOps()" in html
    
    # Make sure switchErpTab calls them
    assert "if (tabId === 'kpis') loadKPIs();" in html
    assert "if (tabId === 'operations') loadEquipment();" in html
    assert "if (tabId === 'subcontractors') loadSubcontractors();" in html
    assert "if (tabId === 'finance') loadFinance();" in html
    assert "if (tabId === 'comms') loadComms();" in html
    assert "if (tabId === 'bizops') loadBizOps();" in html
