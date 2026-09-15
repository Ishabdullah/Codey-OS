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


def test_new509_remaining_eleven_loaders_401_handling():
    """NEW-509 (finishing round): the 11 admin-dashboard load*() functions
    deliberately deferred by the first NEW-509 fix (loadSubcontractors/
    loadDocuments only) must now also log out on a 401, matching
    loadStaffSchedules()'s established pattern. Some of these functions
    make more than one fetch() call internally, so those regions are
    checked for a matching count, not just presence, to catch a fix
    applied to only one of several fetches.

    loadDashboard() (a different, staff-portal surface --
    _render_staff_portal_base, not render_admin_surface -- that has no
    logoutUser() in scope at all) was excluded from the 11: see NEW-509's
    ledger entry for the follow-up finding logged about it instead of
    silently folding it into this round's verbatim pattern.
    """
    html = render_admin_surface()
    check = "if (res.status === 401) { logoutUser(); return; }"

    def region(start_marker, end_marker):
        start = html.index(start_marker)
        return html[start:html.index(end_marker, start)]

    # Single-fetch functions.
    r = region("async function loadKPIs()", "async function loadEquipment()")
    assert check in r

    r = region("async function loadEquipment()", "async function loadSubcontractors()")
    assert check in r

    r = region("async function loadComms()", "async function loadBizOps()")
    assert check in r

    r = region("async function loadUsersList()", "async function loadDeletedUserHistory()")
    assert check in r

    r = region("async function loadDeletedUserHistory()", "async function openPermModal(")
    assert check in r

    r = region("async function loadAuditLogs()", "function patchBusinessChrome(")
    assert check in r

    r = region("async function loadAppointmentTypes()", "function renderAppointmentTypes()")
    assert check in r

    # Multi-fetch functions: assert both/all fetches got the check, not
    # just the first one.
    r = region("async function loadFinance()", "async function loadComms()")
    assert r.count("if (res.status === 401) { logoutUser(); return; }") == 1
    assert r.count("if (inv_res.status === 401) { logoutUser(); return; }") == 1

    r = region("async function loadBizOps()", "window.addEventListener('DOMContentLoaded'")
    assert r.count("if (res1.status === 401) { logoutUser(); return; }") == 1
    assert r.count("if (res2.status === 401) { logoutUser(); return; }") == 1

    r = region("async function loadCrmList()", "function populateCustomerDropdown()")
    assert r.count(check) == 2


def test_new513_load_audit_logs_reads_real_response_shape_and_escapes():
    """NEW-513: loadAuditLogs() previously read data.entries/e.created_at/
    e.details (none of which the real /api/v1/audit-log response has --
    it returns {"audit_logs": [...]} with timestamp/change_summary
    fields, per AuditRecord.to_dict()) and interpolated every field
    unescaped -- a stored-text-node-XSS-class gap in the same family as
    the already-fixed NEW-481/NEW-496."""
    html = render_admin_surface()
    start = html.index("async function loadAuditLogs()")
    end = html.index("function patchBusinessChrome(", start)
    r = html[start:end]

    # Reads the real response shape, not the nonexistent one.
    assert "data.audit_logs" in r
    assert "data.entries" not in r
    assert "e.created_at" not in r
    assert "e.details" not in r
    assert "e.timestamp" in r
    assert "e.change_summary" in r

    # Empty-state branch present (an empty [] is truthy in JS -- without
    # this branch the feed silently stays blank forever).
    assert "No results." in r

    # Every interpolated field is escaped.
    assert "escapeHtml(e.timestamp)" in r
    assert "escapeHtml(e.action)" in r
    assert "escapeHtml(e.change_summary)" in r
    assert "escapeHtml(e.actor_id) || 'System'" in r

    # 401 handling preserved.
    assert "if (res.status === 401) { logoutUser(); return; }" in r
