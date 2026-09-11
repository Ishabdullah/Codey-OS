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
