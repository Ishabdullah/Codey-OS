"""
String-level assertions on render_admin_surface()'s rendered HTML for the
admin-dashboard chrome/form wiring (NEW-450, NEW-449, NEW-466).

These pin the presence of the stable element IDs and JS hooks the
live admin surface depends on. The JS *behaviour* itself
(patchBusinessChrome null-handling, the agent_name_set co-write) has no
Python harness -- it is only exercised by live-verifier.
"""

from restoricon_core.api.web_surfaces import render_admin_surface


def test_admin_surface_has_business_chrome_ids():
    html = render_admin_surface()
    for stable_id in (
        'id="navPhoneText"',
        'id="navPhoneLink"',
        'id="drawerPhoneLink"',
        'id="drawerLicense"',
        'id="drawerEmailLink"',
        'id="adminBarLicense"',
    ):
        assert stable_id in html, stable_id


def test_admin_surface_wires_patch_business_chrome():
    html = render_admin_surface()
    # def + 3 call sites (200 branch, 404 branch, saveBusinessProfile success)
    assert html.count("patchBusinessChrome") == 4


def test_admin_surface_has_company_profile_identity_inputs():
    html = render_admin_surface()
    assert 'id="profOwner"' in html
    assert 'id="profAgentName"' in html


def test_admin_surface_has_schedule_booking_window_input():
    html = render_admin_surface()
    assert 'id="schedBookingWindow" min="1"' in html


def test_admin_surface_has_business_hours_grid_ids():
    html = render_admin_surface()
    for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
        assert f'id="bizHours_{day}_closed"' in html, day
        assert f'id="bizHours_{day}_start"' in html, day
        assert f'id="bizHours_{day}_end"' in html, day


def test_admin_surface_has_appointment_types_section():
    html = render_admin_surface()
    assert 'id="apptTypesTableBody"' in html
    for fn in ("loadAppointmentTypes", "saveAppointmentType", "addAppointmentType"):
        assert fn in html, fn


def test_admin_surface_appointment_type_name_is_escaped():
    html = render_admin_surface()
    # renderAppointmentTypes() must route t.name through escapeHtml before
    # interpolating it into the row HTML (XSS guard, matches
    # loadEquipment/loadSubcontractors' existing convention).
    assert "escapeHtml(t.name)" in html


def test_admin_surface_removed_dead_sched_concurrent_input():
    # schedConcurrent + its "(not yet configurable)" label (f21ad63,
    # NEW-452) are superseded by the per-type Max Concurrent inputs in
    # the Appointment Types section.
    html = render_admin_surface()
    assert "schedConcurrent" not in html
    assert "(not yet configurable)" not in html


def test_admin_surface_schedule_numeric_inputs_still_present():
    html = render_admin_surface()
    assert 'id="schedDuration"' in html
    assert 'id="schedBuffer"' in html
    assert 'id="schedBookingWindow"' in html


def test_admin_surface_wires_business_hours_into_schedule_config_save_load():
    html = render_admin_surface()
    assert "serializeBusinessHours()" in html
    assert "populateBusinessHours(" in html
    # saveScheduleConfig() must set working_hours on the object before the
    # POST (full-row-replace trap called out in the phase brief).
    assert "window.currentScheduleConfig.working_hours = serializeBusinessHours();" in html


# ---------------------------------------------------------------------------
# Delete-buttons round (Ish 2026-09-11)
# ---------------------------------------------------------------------------


def test_admin_surface_has_user_delete_button_and_precheck():
    html = render_admin_surface()
    # username goes through JSON.stringify + escapeHtml (NEW-481/NEW-496
    # fix, cloud review 2026-09-15) -- never a bare '${u.username}' inside
    # a handler's JS string. Relies on users.username being NOT NULL:
    # JSON.stringify(undefined) would render an empty argument.
    assert "deleteUser(${u.id}, ${escapeHtml(JSON.stringify(u.username))})" in html
    assert "async function deleteUser(userId, username)" in html
    assert "/active-references" in html
    assert "confirm(" in html


def test_admin_surface_has_appointment_type_delete_button_and_precheck():
    html = render_admin_surface()
    # Same JSON.stringify + escapeHtml treatment as deleteUser above
    # (appointment_types.name is NOT NULL).
    assert "deleteAppointmentType(${t.id}, ${escapeHtml(JSON.stringify(t.name))})" in html
    assert "async function deleteAppointmentType(id, name)" in html
    assert "/api/v1/appointment-types/' + id + '/active-references'" in html
    assert "/api/v1/appointment-types/' + id + '/delete'" in html


# ---------------------------------------------------------------------------
# Archive-then-delete fix-forward (Ish 2026-09-11 policy decision, NEW-493)
# ---------------------------------------------------------------------------


def test_admin_surface_has_deleted_user_history_panel():
    html = render_admin_surface()
    assert 'id="deletedUserHistoryTableBody"' in html
    assert 'id="deletedUserHistoryFilter"' in html
    assert "async function loadDeletedUserHistory()" in html
    assert "'/api/v1/staff-schedules-archive'" in html


def test_admin_surface_wires_deleted_user_history_into_users_tab_switch():
    html = render_admin_surface()
    # Loaded whenever the Users tab is switched to, same as loadUsersList().
    assert "if (tabId === 'users') { loadUsersList(); loadDeletedUserHistory(); }" in html


# ---------------------------------------------------------------------------
# Admin Dashboard round, Part B (Ish 2026-09-11): Business Profile and
# Booking & Schedule Config consolidated into the Executive Overview tab,
# below the (also-consolidated) Calendar section.
# ---------------------------------------------------------------------------


def test_admin_surface_profile_and_schedule_nav_buttons_removed():
    html = render_admin_surface()
    assert "switchErpTab('profile')" not in html
    assert "switchErpTab('schedule')" not in html
    assert 'id="tab-profile"' not in html
    assert 'id="tab-schedule"' not in html


def test_admin_surface_profile_and_schedule_content_now_inside_executive_overview():
    html = render_admin_surface()
    i = html.find('id="tab-kpis"')
    j = html.find('id="tab-users"')
    assert i != -1 and j != -1
    region = html[i:j]
    for marker in (
        'id="profName"',
        'id="schedBookingWindow" min="1"',
        'id="bizHours_mon_closed"',
        'id="apptTypesTableBody"',
    ):
        assert marker in region, marker


def test_admin_surface_executive_overview_section_order_kpi_calendar_schedule_profile():
    # Order matters per task: KPI content, then Calendar, then Booking
    # Config, then Business Profile -- all still inside tab-kpis.
    html = render_admin_surface()
    i = html.find('id="tab-kpis"')
    j = html.find('id="tab-users"')
    region = html[i:j]
    kpi_pos = region.find('id="kpiPipelineBoard"')
    cal_pos = region.find('id="calGrid"')
    sched_pos = region.find('id="bizHoursTableBody"')
    profile_pos = region.find('id="profName"')
    assert -1 not in (kpi_pos, cal_pos, sched_pos, profile_pos)
    assert kpi_pos < cal_pos < sched_pos < profile_pos


def test_admin_surface_load_calendar_moved_to_unconditional_initial_load():
    # Only loadCalendar() was previously gated behind switchErpTab's
    # 'calendar' branch (Business Profile and Schedule Config already
    # loaded unconditionally); that branch must now be gone, and
    # loadCalendar() must instead fire in the initial validateSession(...)
    # load block.
    html = render_admin_surface()
    assert "if (tabId === 'calendar') loadCalendar();" not in html
    i = html.find("validateSession('/admin/login')")
    j = html.find("</script>", i)
    init_region = html[i:j]
    assert "await loadCalendar();" in init_region


def test_admin_surface_key_functions_still_reachable_after_consolidation():
    html = render_admin_surface()
    for fn in (
        "saveBusinessProfile",
        "saveScheduleConfig",
        "deleteAppointmentType",
        "openNewApptModal",
        "openEditApptModal",
        "submitApptForm",
    ):
        assert fn in html, fn


def test_admin_surface_new_user_dropdown_has_sales_manager_option():
    """D2, sales_rep_portal.md §4: the #newRole user-create dropdown must
    offer 'sales_manager' immediately after 'sales'."""
    html = render_admin_surface()
    i = html.find('id="newRole"')
    j = html.find("</select>", i)
    assert i != -1 and j != -1
    region = html[i:j]
    assert '<option value="sales_manager">Sales Manager</option>' in region
    assert region.index('<option value="sales">Sales</option>') < region.index(
        '<option value="sales_manager">Sales Manager</option>'
    )


# ---------------------------------------------------------------------------
# NEW-538 (corrected scope): Edit User modal -- role + profile-field edit
# for an *existing* user. The Perms modal, Suspend/Activate button, Delete
# flow, and Add-User modal are all pre-existing and untouched.
# ---------------------------------------------------------------------------


def test_admin_surface_has_edit_user_button_per_row():
    html = render_admin_surface()
    assert "openEditUserModal(${u.id})" in html


def test_admin_surface_has_edit_user_modal_dom_ids():
    html = render_admin_surface()
    for stable_id in (
        'id="editUserModalOverlay"',
        'id="editRole"',
        'id="editFullName"',
        'id="editEmail"',
        'id="editPhone"',
        'id="editDept"',
    ):
        assert stable_id in html, stable_id


def test_admin_surface_edit_user_modal_fetches_user_by_id_loader_style():
    html = render_admin_surface()
    assert "async function openEditUserModal(userId)" in html
    i = html.find("async function openEditUserModal(userId)")
    j = html.find("\n        }\n", i)
    fn_body = html[i:j]
    assert "fetch(`/api/v1/users/${userId}`" in fn_body
    # Loader idiom (matches loadUsersList/loadAuditLogs), NOT the mutator
    # idiom -- this is the initial GET, not the save.
    assert "if (res.status === 401) { logoutUser(); return; }" in fn_body


def test_admin_surface_save_edit_user_uses_put_not_patch_and_omits_active():
    html = render_admin_surface()
    assert "async function saveEditUser()" in html
    i = html.find("async function saveEditUser()")
    j = html.find("\n        async function", i + 1)
    if j == -1:
        j = len(html)
    fn_body = html[i:j]
    assert "method: 'PUT'" in fn_body
    assert "method: 'PATCH'" not in fn_body
    assert "active:" not in fn_body
    # Mutator idiom (matches saveUserPermissions/submitNewUser): no explicit
    # 401 check, alert() on a non-ok response.
    assert "if (res.status === 401)" not in fn_body


def test_admin_surface_edit_user_role_dropdown_has_6_standard_options_only():
    html = render_admin_surface()
    i = html.find('id="editRole"')
    j = html.find("</select>", i)
    assert i != -1 and j != -1
    region = html[i:j]
    for role in ("technician", "project_manager", "sales", "sales_manager", "manager", "admin"):
        assert f'<option value="{role}">' in region, role
    assert '<option value="customer">' not in region
    assert '<option value="ai_agent">' not in region


def test_admin_surface_save_edit_user_confirms_on_role_change():
    html = render_admin_surface()
    i = html.find("async function saveEditUser()")
    j = html.find("\n        async function", i + 1)
    if j == -1:
        j = len(html)
    fn_body = html[i:j]
    assert "newRole !== currentEditUserOriginalRole" in fn_body
    assert "confirm(" in fn_body


def test_admin_surface_edit_user_modal_element_ids_are_self_consistent():
    """Every getElementById('edit...') the modal's JS reads/writes must have
    a matching id="..." somewhere in the rendered output -- catches an id
    typo string assertions on isolated substrings would miss."""
    import re

    html = render_admin_surface()
    i = html.find("async function openEditUserModal(userId)")
    j = html.find("async function saveEditUser()")
    region = html[i:j]
    referenced_ids = set(re.findall(r"getElementById\('(edit[A-Za-z]+)'\)", region))
    assert referenced_ids, "expected at least one editXxx getElementById call"
    for elem_id in referenced_ids:
        assert f'id="{elem_id}"' in html, elem_id


def test_admin_surface_edit_user_modal_adds_back_nonstandard_current_role():
    """Trap 4's last sentence: if the user being edited already holds a role
    outside the 6 standard options (ai_agent / customer), the dropdown must
    still surface it as selectable, not silently omit it."""
    html = render_admin_surface()
    i = html.find("async function openEditUserModal(userId)")
    j = html.find("async function closeEditUserModal()", i)
    fn_body = html[i:j]
    assert "standardRoles.includes(u.role)" in fn_body
    assert "data-dynamic-role" in fn_body
    assert "roleSelect.appendChild(opt)" in fn_body
