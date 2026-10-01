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


def test_admin_surface_redirects_dedicated_portal_roles_away_from_admin():
    """NEW-625: an authenticated actor whose role has its own dedicated
    staff/customer portal (B6.8) must not be able to sail through to the
    full 11-domain admin ERP shell just by holding a valid token. The JS
    *behavior* of this redirect (does the browser actually navigate) has
    no Python harness here -- only the presence of the correct role->path
    map is pinned; live-verifier is needed to confirm the redirect fires."""
    html = render_admin_surface()
    for role, portal_path in (
        ("project_manager", "/pm"),
        ("sales", "/sales"),
        ("sales_manager", "/sales"),
        ("technician", "/tech"),
        ("customer", "/portal"),
        ("subcontractor", "/subcontractor"),
    ):
        assert f"'{role}': '{portal_path}'" in html, role


def test_admin_surface_does_not_redirect_roles_without_a_dedicated_portal():
    """Negative list: ROLE_MANAGER and ROLE_AI_AGENT have no dedicated
    portal of their own, so they must continue to land on /admin --
    getting this wrong risks silently locking one of them out.
    'sales_manager' is NOT in this negative list -- as of NEW-642
    (resolved 2026-09-25), it DOES have a dedicated portal (/sales, see
    _render_sales_portal()'s docstring and the pre-existing login-redirect
    at web_surfaces.py:713-714) and IS now a key in rolePortals, covered
    instead by test_admin_surface_redirects_dedicated_portal_roles_away_from_admin
    above.
    'subcontractor' is likewise NOT in this negative list as of Phase 0b/
    B8.16 (2026-09-27, NEW-641 resolved) -- ROLE_SUBCONTRACTOR is now a
    real member of auth.py's ALL_ROLES and IS now a key in rolePortals,
    covered instead by test_admin_surface_redirects_dedicated_portal_roles_away_from_admin
    above."""
    html = render_admin_surface()
    i = html.find("const rolePortals = {")
    assert i != -1
    j = html.find("};", i)
    assert j != -1
    role_portal_map_js = html[i:j]
    for role in ("manager", "ai_agent", "admin"):
        assert f"'{role}':" not in role_portal_map_js, role


def test_admin_surface_documents_panel_renders_names_not_raw_ids():
    """NEW-661: the admin Documents panel's loadDocuments() used to render
    bare 'Cust: <id>' / 'Proj: <id>' text. GET /api/v1/documents now
    additively returns customer_name/project_name (routes.py), and the
    client renders those, falling back to 'Customer #id'/'Project #id'
    (matching this project's established fallback convention) only when a
    name failed to resolve -- customer_id/project_id keys/behaviour are
    otherwise unchanged."""
    html = render_admin_surface()
    start = html.index("async function loadDocuments()")
    end = html.index("async function searchAuditLog()")
    documents_js = html[start:end]
    assert "'Cust: ' + d.customer_id" not in documents_js
    assert "'Proj: ' + d.project_id" not in documents_js
    assert "d.customer_name || ('Customer #' + d.customer_id)" in documents_js
    assert "d.project_name || ('Project #' + d.project_id)" in documents_js
    assert "escapeHtml(d.customer_name" in documents_js
    assert "escapeHtml(d.project_name" in documents_js


# ---------------------------------------------------------------------------
# B9.y: customer-login creation via the existing Add User modal + an
# admin-triggered password reset action. Frontend-only round -- the backend
# primitives (role='customer' + customer_id on POST /api/v1/users,
# POST /api/v1/users/{id}/password) already exist and are unchanged here.
# ---------------------------------------------------------------------------


def test_admin_surface_new_role_dropdown_has_customer_option():
    html = render_admin_surface()
    i = html.find('id="newRole"')
    j = html.find("</select>", i)
    assert i != -1 and j != -1
    region = html[i:j]
    assert '<option value="customer">Customer</option>' in region
    # 7 options total: 6 pre-existing standard roles + the new 'customer'.
    assert region.count("<option value=") == 7


def test_admin_surface_edit_role_dropdown_unchanged_no_customer_option():
    """Regression guard (B9.y spec, explicit out-of-scope item): #editRole
    must stay at its pre-existing 6 options with no 'customer' option --
    this modal doesn't collect a customer_id, so adding 'customer' here
    would let a save 400 via _validate_user_role_invariants. Someone may be
    tempted to "fix" the #newRole/#editRole asymmetry; don't -- it's
    deliberate (see the comment at web_surfaces.py's editUserModalOverlay)."""
    html = render_admin_surface()
    i = html.find('id="editRole"')
    j = html.find("</select>", i)
    assert i != -1 and j != -1
    region = html[i:j]
    assert '<option value="customer">Customer</option>' not in region
    assert region.count("<option value=") == 6


def test_admin_surface_new_user_customer_picker_dom_ids_start_hidden():
    html = render_admin_surface()
    for stable_id in (
        'id="newUserCustomerPickerBlock"',
        'id="newUserCustomerSearch"',
        'id="newUserCustomerResults"',
        'id="newUserSelectedCustomerLabel"',
        'id="newUserClearCustomerBtn"',
        'id="newCustomerId"',
    ):
        assert stable_id in html, stable_id
    i = html.find('id="newUserCustomerPickerBlock"')
    j = html.find(">", i)
    assert 'style="display:none;"' in html[i:j]


def test_admin_surface_submit_new_user_includes_customer_id_conditionally():
    html = render_admin_surface()
    assert "async function submitNewUser(e)" in html
    i = html.find("async function submitNewUser(e)")
    j = html.find("\n        }\n", i)
    fn_body = html[i:j]
    assert "customer_id: customerIdRaw ? parseInt(customerIdRaw, 10) : null" in fn_body
    # Client-side guard: role === 'customer' with no selected customer_id
    # must block submit instead of letting the server 400.
    assert "role === 'customer' && !customerIdRaw" in fn_body


def test_admin_surface_has_reset_password_button_per_row_with_numeric_id_only():
    """The new Reset Password button deliberately does NOT follow the
    pre-existing Perms/Delete buttons' inline-onclick-JSON pattern
    (escapeHtml(JSON.stringify(u.username)) passed into onclick) -- that
    shape is a documented stored-XSS vector elsewhere in this file. Only
    the numeric id crosses the onclick boundary; the username is resolved
    inside openResetPasswordModal() from a held array."""
    html = render_admin_surface()
    assert 'onclick="openResetPasswordModal(${u.id})"' in html
    assert "openResetPasswordModal(${u.id}, ${escapeHtml(JSON.stringify(u.username))})" not in html


def test_admin_surface_has_reset_password_modal_dom_ids():
    html = render_admin_surface()
    for stable_id in (
        'id="resetPasswordModalOverlay"',
        'id="resetPasswordUsername"',
        'id="resetPasswordNewValue"',
        'id="submitResetPasswordBtn"',
    ):
        assert stable_id in html, stable_id
    i = html.find('id="resetPasswordNewValue"')
    j = html.find(">", i)
    assert 'minlength="6"' in html[i:j]


def _extract_fn_body_by_braces(html: str, fn_start_marker: str) -> str:
    """Returns the body of a `function name(...) { ... }` block (the text
    strictly between its outer braces), located via brace-matching rather
    than a fixed-offset end marker -- needed here because the statements
    we care about are nested one level deep (inside an `if`), so a plain
    substring search can't distinguish "appears in the function" from
    "appears at the function's top level"."""
    start = html.find(fn_start_marker)
    assert start != -1, fn_start_marker
    open_brace = html.find("{", start)
    assert open_brace != -1
    depth = 0
    i = open_brace
    while True:
        ch = html[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return html[open_brace + 1 : i]
        i += 1


def _depth_at_each_index(body: str):
    """Returns a list the same length as `body` where entry i is the brace
    depth (relative to the body itself, i.e. the function's own `{ }` are
    not counted) BEFORE character i is consumed. Used to check whether a
    given substring match starts at depth 0 (top level of the function)
    rather than nested inside an `if`/`for`/etc block.

    (An earlier version of this helper split the body into "statements" on
    top-level `;` instead -- that's wrong: a whole `if (...) { ... }` block
    has no trailing `;`, so it got treated as a single statement whose raw
    text still contained a nested substring, silently defeating the check.
    Verified by hand: that version stayed green even when the fix under
    test was reverted to the buggy guarded form. Per-index depth tracking
    doesn't have this blind spot.)"""
    depths = []
    depth = 0
    for ch in body:
        depths.append(depth)
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
    return depths


def _has_top_level_occurrence(body: str, needle: str) -> bool:
    depths = _depth_at_each_index(body)
    start = 0
    while True:
        idx = body.find(needle, start)
        if idx == -1:
            return False
        if depths[idx] == 0:
            return True
        start = idx + 1


def test_clear_new_user_customer_clears_email_unconditionally():
    """NEW-fix (B9.y review round): clearNewUserCustomer() must clear
    #newEmail as a TOP-LEVEL statement of its own body, not nested inside
    an `if (fullName.readOnly)` guard. The pre-fix code already contained
    the literal string "document.getElementById('newEmail').value = '';"
    -- it was just one brace deeper, inside a guard that's already false
    by the time toggleNewUserCustomerFields()'s role-switch-away branch
    calls this function (it sets fullName.readOnly = false on the
    preceding line). A plain substring-presence assertion is green on
    both the buggy and fixed code and proves nothing; this test instead
    asserts the statement sits at depth 0 in the function body, which is
    only true post-fix. (Verified by hand: temporarily re-wrapping the
    statement in `if (fullName.readOnly) { ... }` turns this test red.)
    """
    html = render_admin_surface()
    body = _extract_fn_body_by_braces(html, "function clearNewUserCustomer()")
    assert _has_top_level_occurrence(
        body, "getElementById('newEmail').value = ''"
    ), body


def test_toggle_new_user_customer_fields_else_branch_still_clears_customer_state():
    """Regression guard for the other half of the fix: the role-switch-away
    (else) branch of toggleNewUserCustomerFields() must still call
    clearNewUserCustomer() -- a future edit could drop the call site
    entirely now that the email-clear no longer depends on statement
    ordering within this function. (Statement ORDER relative to
    `fullName.readOnly = false` is deliberately not asserted here post-fix
    -- once clearNewUserCustomer()'s own guard is gone, ordering is no
    longer load-bearing, and pinning it would lock in an arbitrary
    sequence a harmless future edit could "break".)
    """
    html = render_admin_surface()
    body = _extract_fn_body_by_braces(html, "function toggleNewUserCustomerFields()")
    else_idx = body.find("} else {")
    assert else_idx != -1
    else_branch = body[else_idx:]
    assert "clearNewUserCustomer();" in else_branch


def test_reset_new_user_customer_fields_clears_new_email():
    """NEW-fix (B9.y review round): resetNewUserCustomerFields() -- called
    from both openAddUserModal() and closeAddUserModal() -- must also
    clear #newEmail, otherwise a stale email from a previous (unrelated)
    user-creation attempt survives a modal close/reopen cycle. Asserted
    at depth 0 of the function body for the same reason as above (there's
    no guard here to dodge, but keep the extraction consistent)."""
    html = render_admin_surface()
    body = _extract_fn_body_by_braces(html, "function resetNewUserCustomerFields()")
    assert _has_top_level_occurrence(
        body, "getElementById('newEmail').value = ''"
    ), body


def test_admin_surface_reset_password_never_echoes_the_new_password():
    """No alert()/confirm() near submitResetPassword may contain the
    password variable -- a reset is not a reveal."""
    html = render_admin_surface()
    assert "async function submitResetPassword()" in html
    i = html.find("async function submitResetPassword()")
    j = html.find("\n        }\n", i)
    fn_body = html[i:j]
    assert "alert(" not in fn_body
    # Body sent to the server carries only new_password, never old_password.
    assert "new_password: newValue" in fn_body
    assert "old_password" not in fn_body
