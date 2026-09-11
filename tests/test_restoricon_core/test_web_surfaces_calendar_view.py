"""
String-level assertions on render_admin_surface()'s rendered HTML for the
new read-only Calendar tab (Phase 7 Part 2 of 3).

The actual grid rendering, color assignment, and filter behaviour have no
Python test harness -- these are coarse presence/wiring checks only,
matching this project's established convention for JS-in-Python-string
surfaces (see test_web_surfaces_admin_wiring.py's module docstring).
Behavioural correctness is exercised by live-verifier, not here.
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
