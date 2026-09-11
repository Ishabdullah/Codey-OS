"""
String-level assertions on render_admin_surface()'s rendered HTML for the
Calendar tab: read-only view (Phase 7 Part 2) plus create/edit (Phase 7
Part 3, the final round of the admin-dashboard program).

The actual grid rendering, color assignment, filter behaviour, and modal
create/edit/save/refresh flow have no Python test harness -- these are
coarse presence/wiring checks only, matching this project's established
convention for JS-in-Python-string surfaces (see
test_web_surfaces_admin_wiring.py's module docstring). Behavioural
correctness (including the concurrency-cap 400 round-trip) is exercised
by live-verifier, not here.
"""

import re

from restoricon_core.api.web_surfaces import render_admin_surface


def test_admin_surface_has_calendar_nav_and_tab_pane():
    html = render_admin_surface()
    assert "switchErpTab('calendar')" in html
    assert 'id="tab-calendar"' in html


def test_admin_surface_has_calendar_view_toggle():
    html = render_admin_surface()
    assert 'id="calViewMonthBtn"' in html
    assert 'id="calViewWeekBtn"' in html
    assert "function calSetView" in html


def test_admin_surface_has_calendar_date_nav_controls():
    html = render_admin_surface()
    assert "function calNav" in html
    assert "function calToday" in html


def test_admin_surface_has_calendar_filters():
    html = render_admin_surface()
    assert 'id="calFilterPerson"' in html
    assert 'id="calFilterType"' in html
    assert 'id="calFilterRole"' in html


def test_admin_surface_calendar_fetches_appointments_and_staff_schedules_with_range():
    html = render_admin_surface()
    assert "'/api/v1/appointments?start=' + startStr + '&end=' + endStr" in html
    assert "'/api/v1/staff-schedules?start=' + startStr + '&end=' + endStr" in html


def test_admin_surface_calendar_staff_schedules_fetch_sends_limit():
    # NEW-490: the staff-schedules fetch previously sent no `limit` at
    # all, silently relying on the service's 200-row default with no way
    # to raise it (the route didn't forward one either). Must now send an
    # explicit limit, mirroring the appointments fetch's &limit=500.
    html = render_admin_surface()
    assert "CAL_STAFF_FETCH_LIMIT = 500" in html
    assert "'/api/v1/staff-schedules?start=' + startStr + '&end=' + endStr + '&limit=' + CAL_STAFF_FETCH_LIMIT" in html


def test_admin_surface_calendar_staff_schedules_truncation_warning():
    # Belt-and-braces per code-reviewer: even with the raised limit, a
    # future month could still exceed it -- must detect hitting the cap
    # exactly and surface an explicit warning rather than rendering a
    # month that looks complete but isn't.
    html = render_admin_surface()
    assert "staffTruncated" in html
    assert "schedules.length === CAL_STAFF_FETCH_LIMIT" in html
    assert "Showing the first " in html


def test_admin_surface_calendar_day_view_noted_as_future_not_half_built():
    html = render_admin_surface()
    assert "Day view is a planned future addition" in html
    # No disabled/half-built Day toggle control.
    assert 'id="calViewDayBtn"' not in html


def test_admin_surface_calendar_rendering_functions_use_escapeHtml():
    html = render_admin_surface()
    i = html.find("function renderCalendarMonth")
    j = html.find("function renderCalendarWeek")
    k = html.find("function openCalendarItem")
    end = html.find("function closeCalItemModal")
    assert -1 not in (i, j, k, end)
    month_region = html[i:j]
    week_region = html[j:k]
    detail_region = html[k:end]
    assert "escapeHtml(" in month_region
    assert "escapeHtml(" in week_region
    assert "escapeHtml(" in detail_region


def test_admin_surface_calendar_onclick_handlers_pass_only_ids():
    # NEW-481's exact vulnerable pattern: interpolating a name/string
    # (rather than a numeric id) into an inline onclick handler string.
    # Scope the negative assertion to the calendar region only -- a
    # whole-document check would trip on the pre-existing NEW-481 sites
    # (openPermModal(${u.id}, '${u.username}')) which are out of scope
    # for this round.
    html = render_admin_surface()
    i = html.find("function loadCalendar")
    j = html.find("function loadDocuments")
    assert i != -1 and j != -1
    calendar_region = html[i:j]

    onclick_attrs = re.findall(r'onclick="[^"]*"', calendar_region)
    assert onclick_attrs, "expected calendar region to contain onclick handlers"
    for attr in onclick_attrs:
        assert "'${" not in attr, attr

    assert "onclick=\"openCalendarItem('appointment', ${a.id})\"" in calendar_region
    assert "onclick=\"openCalendarItem('staff', ${s.id})\"" in calendar_region


def test_admin_surface_calendar_color_palette_is_deterministic_no_new_column():
    html = render_admin_surface()
    assert "function calColorForType" in html
    # NEW-488: no schema change, no new `color` column -- purely a
    # client-side hash into a fixed palette.
    assert "CAL_TYPE_COLORS" in html


def test_admin_surface_calendar_item_label_shows_time_title_and_type():
    # Task requires each appointment cell show title/attendee_name, time,
    # and its resolved appointment-type name if set -- calApptLabel()
    # assembles all three; both month and week rendering call it.
    html = render_admin_surface()
    assert "function calApptLabel" in html
    assert "calApptLabel(a)" in html
    assert html.count("calApptLabel(a)") >= 2  # month view + week view


def test_admin_surface_calendar_month_cell_caps_items_with_more_link():
    # Unconditional rendering inside a fixed-height, overflow:hidden cell
    # would silently clip extra items -- must collapse into a "+N more"
    # affordance instead (task: "or just a colored dot + count if many").
    html = render_admin_surface()
    assert "CAL_MONTH_CELL_ITEM_CAP" in html
    assert "function openCalendarDay" in html
    assert "more</div>" in html


def test_admin_surface_calendar_month_nav_does_not_use_bare_setMonth():
    # setMonth(m + delta) on a Date carrying a day-of-month greater than
    # the target month's length overflows into the following month
    # (e.g. Aug 31 -> Oct 1, skipping September). calNav() must rebuild
    # from day 1 of the target month instead.
    html = render_admin_surface()
    i = html.find("function calNav")
    j = html.find("function calToday")
    assert i != -1 and j != -1
    region = html[i:j]
    assert "new Date(d.getFullYear(), d.getMonth() + delta, 1)" in region
    assert "d.setMonth(d.getMonth() + delta)" not in region


def test_admin_surface_calendar_detail_modal_present():
    html = render_admin_surface()
    assert 'id="calItemModal"' in html
    assert 'id="calItemModalBody"' in html
    assert "function closeCalItemModal" in html


# ---- Phase 7 Part 3: create/edit ----

def test_admin_surface_calendar_has_new_item_actions():
    html = render_admin_surface()
    assert 'onclick="openNewApptModal()"' in html
    assert 'onclick="openNewSchedModal()"' in html
    assert "function openNewApptModal" in html
    assert "function openNewSchedModal" in html


def test_admin_surface_calendar_has_edit_and_form_functions():
    html = render_admin_surface()
    for fn in (
        "function openEditApptModal",
        "function closeApptFormModal",
        "function submitApptForm",
        "function openEditSchedModal",
        "function closeSchedFormModal",
        "function submitSchedForm",
    ):
        assert fn in html, fn


def test_admin_surface_calendar_appointment_create_and_update_routes():
    html = render_admin_surface()
    # Create: plain collection POST.
    assert "const url = id ? '/api/v1/appointments/' + id + '/update' : '/api/v1/appointments';" in html
    # The create-vs-update branch always POSTs (both routes.py verbs are POST).
    i = html.find("async function submitApptForm")
    j = html.find("async function cancelAppointmentFromCalendar")
    assert i != -1 and j != -1
    region = html[i:j]
    assert "method: 'POST'" in region


def test_admin_surface_calendar_appointment_cancel_uses_status_route_not_delete():
    # No hard delete for appointments -- a cancelled status transition
    # instead (POST .../status), per task scope.
    html = render_admin_surface()
    assert "function cancelAppointmentFromCalendar" in html
    i = html.find("async function cancelAppointmentFromCalendar")
    j = html.find("function openNewSchedModal")
    assert i != -1 and j != -1
    region = html[i:j]
    assert "'/api/v1/appointments/' + id + '/status'" in region
    assert "status: 'cancelled'" in region
    assert "DELETE" not in region


def test_admin_surface_calendar_staff_schedule_create_and_update_routes():
    html = render_admin_surface()
    i = html.find("async function submitSchedForm")
    j = html.find("async function removeScheduleFromCalendar")
    assert i != -1 and j != -1
    region = html[i:j]
    assert "const url = id ? '/api/v1/staff-schedules/' + id : '/api/v1/staff-schedules';" in region
    assert "const method = id ? 'PATCH' : 'POST';" in region


def test_admin_surface_calendar_staff_schedule_remove_uses_delete_route():
    # DELETE /api/v1/staff-schedules/{id} already exists and is simple
    # (confirmed against routes.py) -- wired here per task scope.
    html = render_admin_surface()
    i = html.find("async function removeScheduleFromCalendar")
    j = html.find("async function loadDocuments")
    assert i != -1 and j != -1 and j > i
    region = html[i:j]
    assert "method: 'DELETE'" in region
    assert "'/api/v1/staff-schedules/' + id" in region


def test_admin_surface_calendar_400_errors_surfaced_inline_not_swallowed():
    # Both the appointment and staff-schedule submit handlers must read
    # data.error from the response body and display it inline -- no
    # alert(), no generic message, no silent no-op -- and must not close
    # the modal or reset the form fields on failure (the else branch has
    # no closeApptFormModal()/closeSchedFormModal() call and no .value =
    # '' resets).
    html = render_admin_surface()
    i = html.find("async function submitApptForm")
    j = html.find("async function cancelAppointmentFromCalendar")
    appt_region = html[i:j]
    assert "data.error" in appt_region
    assert "errBox.innerText = data.error" in appt_region
    assert "errBox.style.display = 'block';" in appt_region
    # Structural (not merely positional) check: closeApptFormModal() must
    # appear exactly once, immediately inside the `if (res.ok) {` success
    # branch, never in the else/failure branch.
    assert appt_region.count("closeApptFormModal();") == 1
    assert "if (res.ok) {\n                    closeApptFormModal();" in appt_region

    sched_start = html.find("async function submitSchedForm")
    sched_end = html.find("async function removeScheduleFromCalendar")
    sched_region = html[sched_start:sched_end]
    assert "data.error" in sched_region
    assert "errBox.innerText = data.error" in sched_region
    assert sched_region.count("closeSchedFormModal();") == 1
    assert "if (res.ok) {\n                    closeSchedFormModal();" in sched_region


def test_admin_surface_calendar_success_path_refreshes_via_loadCalendar():
    html = render_admin_surface()
    i = html.find("async function submitApptForm")
    j = html.find("async function submitSchedForm")
    region = html[i:j]
    assert region.count("loadCalendar();") >= 1
    sched_start = html.find("async function submitSchedForm")
    sched_end = html.find("async function removeScheduleFromCalendar")
    sched_region = html[sched_start:sched_end]
    assert sched_region.count("loadCalendar();") >= 1


def test_admin_surface_calendar_edit_does_not_clobber_status():
    # NEW: submitApptForm/submitSchedForm must only send `status` on
    # create (empty id) -- both update_appointment() and
    # update_staff_schedule() are partial SET-clause writers, so sending
    # a hardcoded/stale status on every edit would silently overwrite the
    # entity's real status. Also: an appointment edit must never carry
    # status through the generic /update route at all (that bypasses
    # update_appointment_status()'s history-log entry and distinct
    # 'status_change' audit action) -- the Status field is disabled
    # whenever editing.
    html = render_admin_surface()
    i = html.find("async function submitApptForm")
    j = html.find("async function cancelAppointmentFromCalendar")
    appt_region = html[i:j]
    assert "if (!id) {" in appt_region
    assert "payload.status = document.getElementById('calApptStatus').value;" in appt_region

    i2 = html.find("function openEditApptModal")
    j2 = html.find("function closeApptFormModal")
    edit_region = html[i2:j2]
    assert "document.getElementById('calApptStatus').disabled = true;" in edit_region

    sched_start = html.find("async function submitSchedForm")
    sched_end = html.find("async function removeScheduleFromCalendar")
    sched_region = html[sched_start:sched_end]
    assert "if (!id) {" in sched_region
    assert "payload.status = 'scheduled';" in sched_region


def test_admin_surface_calendar_item_detail_gains_edit_actions():
    html = render_admin_surface()
    i = html.find("function openCalendarItem")
    j = html.find("function closeCalItemModal")
    region = html[i:j]
    assert "onclick=\"openEditApptModal(${a.id})\"" in region
    assert "onclick=\"openEditSchedModal(${s.id})\"" in region
    assert "onclick=\"cancelAppointmentFromCalendar(${a.id})\"" in region
    assert "onclick=\"removeScheduleFromCalendar(${s.id})\"" in region


def test_admin_surface_calendar_create_edit_onclicks_pass_only_ids():
    # Same NEW-481-shaped check as Part 2's onclick test, extended to
    # cover the new region past loadDocuments (the new form functions
    # live between openCalendarItem/closeCalItemModal and loadDocuments).
    html = render_admin_surface()
    i = html.find("function loadCalendar")
    j = html.find("function loadDocuments")
    assert i != -1 and j != -1
    region = html[i:j]
    onclick_attrs = re.findall(r'onclick="[^"]*"', region)
    for attr in onclick_attrs:
        assert "'${" not in attr, attr
