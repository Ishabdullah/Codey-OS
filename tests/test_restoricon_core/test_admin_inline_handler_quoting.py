"""
Cloud-review round (2026-09-15) regression guards for the admin surface.

F1 -- inline-handler string args (NEW-481 class): `onclick="fn(${x.id},
'${x.name}')"` breaks on an apostrophe (SyntaxError, button dead) and is
an inline-handler XSS for a crafted value, because the HTML parser decodes
entities before the JS parser ever sees the string. The fix is
`${escapeHtml(JSON.stringify(value))}`: JSON gives a double-quoted JS
string literal with every quote/backslash/newline escaped, and escapeHtml
makes it survive the attribute context. These tests (a) sweep every
rendered surface for the broken pattern and (b) prove the mechanism end
to end with node against the surface's own escapeHtml.

F5 -- the Staff Schedules tab must send an explicit limit (the service
default is the 200 OLDEST rows) and flag a full-to-the-cap response.

F6 -- saveSubcontractorUserId must branch on res.ok.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from restoricon_core.api import web_surfaces

NODE = shutil.which("node")

SURFACE_FNS = sorted(n for n in dir(web_surfaces) if n.startswith("render_") and n.endswith("_surface"))

# on*="...'${expr}'..." -- a template-literal interpolation wrapped in
# single quotes inside an inline handler attribute.
QUOTED_INTERP_IN_HANDLER = re.compile(r"""on\w+="[^"]*'\$\{[^}]*\}'""")

# The only two remaining matches interpolate server-side constants, not
# user-editable data: permission ids come from auth.py's fixed catalog
# (`p.id`), and day keys come from the BIZ_HOURS_DAYS literal. Anything
# else matching is a new instance of the bug.
ALLOWED_CONSTANT_INTERPOLATIONS = {
    """onchange="userPermissionsState['${p.id}'""",
    """onchange="toggleApptHoursRow(${t.id}, '${day}'""",
}


@pytest.mark.parametrize("name", SURFACE_FNS)
def test_no_user_data_single_quoted_into_inline_handlers(name):
    html = getattr(web_surfaces, name)()
    hits = set(QUOTED_INTERP_IN_HANDLER.findall(html))
    unexpected = hits - ALLOWED_CONSTANT_INTERPOLATIONS
    assert not unexpected, (
        f"{name}(): user data interpolated inside a single-quoted string in an "
        f"inline handler (NEW-481 pattern) -- use "
        f"${{escapeHtml(JSON.stringify(value))}} instead:\n" + "\n".join(sorted(unexpected))
    )


def test_admin_delete_and_perm_buttons_use_json_stringify_escape():
    html = web_surfaces.render_admin_surface()
    assert "deleteUser(${u.id}, ${escapeHtml(JSON.stringify(u.username))})" in html
    assert "openPermModal(${u.id}, ${escapeHtml(JSON.stringify(u.username))})" in html
    assert "deleteAppointmentType(${t.id}, ${escapeHtml(JSON.stringify(t.name))})" in html
    # NEW-507: the Subcontractors tab's delete button follows the same
    # JSON.stringify + escapeHtml quoting convention.
    assert "deleteSubcontractor(${sc.id}, ${escapeHtml(JSON.stringify(sc.company_name))})" in html


def _admin_escape_html_source() -> str:
    html = web_surfaces.render_admin_surface()
    m = re.search(r"function escapeHtml\(unsafe\) \{.*?\n\s*\}\n", html, re.DOTALL)
    assert m, "render_admin_surface() no longer defines escapeHtml(unsafe)"
    return m.group(0)


@pytest.mark.skipif(NODE is None, reason="node not installed in this environment")
@pytest.mark.parametrize("value", [
    "O'Brien",
    "Bob's Estimate",
    "foo'); alert(1); //",
    'a"b\\c<d>&e',
    "multi\nline",
    "</script><script>alert(1)</script>",
])
def test_json_stringify_plus_escapeHtml_round_trips_through_attribute(value):
    """Builds the attribute exactly as the row template does, decodes
    entities the way the HTML parser would, then executes the resulting
    handler body -- the callee must receive the original string verbatim
    and nothing else must run (the alert() in the payloads is never
    defined, so any breakout would throw ReferenceError)."""
    script = _admin_escape_html_source() + r"""
const value = JSON.parse(process.argv[2]);
const attr = `${escapeHtml(JSON.stringify(value))}`;
// HTML attribute entity decoding, &amp; last (as a real decoder does).
const decoded = attr
    .replace(/&quot;/g, '"').replace(/&#039;/g, "'")
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
let received;
const deleteUser = (id, name) => { received = name; };
new Function('deleteUser', `deleteUser(7, ${decoded})`)(deleteUser);
if (received !== value) {
    console.error('mismatch: ' + JSON.stringify(received) + ' !== ' + JSON.stringify(value));
    process.exit(3);
}
"""
    import json
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(script)
        path = f.name
    try:
        result = subprocess.run([NODE, path, json.dumps(value)], capture_output=True, text=True, timeout=30)
    finally:
        Path(path).unlink(missing_ok=True)
    assert result.returncode == 0, f"rc={result.returncode}\n{result.stderr}"


def test_staff_schedules_tab_sends_explicit_limit_and_truncation_notice():
    html = web_surfaces.render_admin_surface()
    start = html.index("async function loadStaffSchedules()")
    region = html[start:html.index("async function submitStaffSchedule", start)]
    assert "const STAFF_TAB_FETCH_LIMIT = 500;" in region
    assert "fetch('/api/v1/staff-schedules?limit=' + STAFF_TAB_FETCH_LIMIT" in region
    assert "data.schedules.length === STAFF_TAB_FETCH_LIMIT" in region
    assert "some may be hidden" in region
    # The bare, unscoped fetch that returned the 200 oldest rows is gone.
    assert "fetch('/api/v1/staff-schedules', {" not in region


def test_subcontractors_tab_sends_explicit_limit_and_truncation_notice():
    """NEW-489: loadSubcontractors() must hit the real /api/v1/subcontractors
    route (not the nonexistent /api/v1/operations/subcontractors) with an
    explicit, bounded limit, and flag a full-to-the-cap response -- same
    truncation-banner pattern as NEW-499's staff-schedules fix."""
    html = web_surfaces.render_admin_surface()
    start = html.index("async function loadSubcontractors()")
    region = html[start:html.index("// Linked-user save", start)]
    assert "const SUBCONTRACTORS_TAB_FETCH_LIMIT = 500;" in region
    assert "fetch('/api/v1/subcontractors?limit=' + SUBCONTRACTORS_TAB_FETCH_LIMIT" in region
    assert "data.subcontractors.length === SUBCONTRACTORS_TAB_FETCH_LIMIT" in region
    assert "some may be hidden" in region
    # The broken, nonexistent route is gone.
    assert "/api/v1/operations/subcontractors" not in region
    # Real model fields, not the nonexistent specialty/status/rating.
    assert "sc.company_name" in region
    assert "sc.primary_trade" in region
    assert "sc.qualification_status" in region
    assert "sc.license_status" in region
    assert "sc.specialty" not in region
    assert "sc.status" not in region
    assert "sc.rating" not in region


def test_save_subcontractor_user_id_checks_res_ok_and_reloads():
    html = web_surfaces.render_admin_surface()
    start = html.index("async function saveSubcontractorUserId(")
    region = html[start:html.index("async function loadFinance", start)]
    assert "const res = await fetch(`/api/v1/subcontractors/${subId}/update`" in region
    assert "if (res.ok) {" in region
    assert region.count("loadSubcontractors();") == 2  # success and failure paths both refresh
    assert "Failed to save linked user" in region
