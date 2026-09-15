from restoricon_core.api.web_surfaces import render_admin_surface

def test_b6_4_admin_wiring_tabs_has_fetches():
    html = render_admin_surface()
    
    # Check KPI board endpoints
    assert "'/api/v1/reports/summary'" in html
    assert "loadKPIs()" in html
    
    # Check Operations and Subcontractors endpoints
    assert "'/api/v1/operations/equipment'" in html
    assert "loadEquipment()" in html
    
    # NEW-489: the correct list route is /api/v1/subcontractors, not the
    # nonexistent /api/v1/operations/subcontractors.
    assert "/api/v1/operations/subcontractors" not in html
    assert "/api/v1/subcontractors?limit=" in html
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


def test_new507_subcontractors_delete_wiring():
    """NEW-507: the Subcontractors tab has an Actions column with a real
    delete flow, not just the read-only columns from the NEW-489 fix.
    <th>Actions</th> alone would be a vacuous assertion (Users and
    Appointment Types already have one) -- scope it to the Subcontractors
    tab specifically and pin the colspan bump too."""
    html = render_admin_surface()
    tab = html[html.index("<!-- Tab 7: Subcontractors -->"):html.index("<!-- Tab 8: Communications -->")]
    assert "<th>Actions</th>" in tab
    assert 'colspan="5"' not in tab
    assert "deleteSubcontractor(${sc.id}, ${escapeHtml(JSON.stringify(sc.company_name))})" in html
    assert "/api/v1/subcontractors/${id}/active-references" in html
    assert "/api/v1/subcontractors/${id}/delete" in html


def test_new508_onboard_trade_partner_wiring():
    """NEW-508: the '+ Onboard Trade Partner' button opens a real create
    modal instead of the old alert() stub."""
    html = render_admin_surface()
    assert "alert('Trade partner onboarding active.')" not in html
    assert "openAddSubcontractorModal()" in html
    assert 'id="addSubcontractorModalOverlay"' in html
    assert "submitNewSubcontractor(event)" in html
    assert 'id="newSubCompanyName"' in html
    assert 'id="newSubPrimaryTrade"' in html


def test_new509_load_subcontractors_and_load_documents_401_handling():
    """NEW-509: loadSubcontractors() must log out on a 401, matching
    loadStaffSchedules()'s existing pattern; loadDocuments() must call
    the real logoutUser() (not the nonexistent logout())."""
    html = render_admin_surface()

    start = html.index("async function loadSubcontractors()")
    region = html[start:html.index("// Delete-buttons follow-on round", start)]
    assert "if (res.status === 401) { logoutUser(); return; }" in region

    start = html.index("async function loadDocuments()")
    region = html[start:html.index("async function searchAuditLog", start)]
    assert "if (res.status === 401) { logoutUser(); return; }" in region
    assert "logout(); return;" not in region
