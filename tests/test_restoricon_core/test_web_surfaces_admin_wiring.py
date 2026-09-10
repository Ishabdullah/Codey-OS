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
