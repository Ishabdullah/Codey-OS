"""
NEW-481 remaining scope: the raw text-node interpolation half (the
inline-handler half was fixed separately under NEW-496,
tests/test_restoricon_core/test_admin_inline_handler_quoting.py).

Four sinks in render_admin_surface() interpolate user-editable strings
directly into innerHTML text-node/option-text positions with no
escaping: loadUsersList() (username/full_name/email/role),
loadCrmList()'s customer block (first_name/last_name/email/phone) and
project block (title/project_type/stage), and
populateCustomerDropdown() (first_name/last_name inside an <option>).
The fix wraps each in escapeHtml(...), matching this file's existing
`function escapeHtml(unsafe)` helper (entity-encodes & < > " ').

This is a TEXT-NODE injection context, not an attribute/onclick context
(NEW-496's concern) -- the escaping requirement differs: a template
literal placed directly into innerHTML as text only needs entity
encoding of `& < >` (plus `" '` here, harmlessly) to prevent the HTML
parser from ever creating a new element out of the value; there is no
JS-string-inside-an-attribute double-decode hazard here.

Two kinds of check below:
  1. Presence/wiring assertions against the real rendered HTML -- proves
     the deployed source actually calls escapeHtml(...) at each site
     (catches a future regression that strips the call).
  2. A node round-trip mechanism proof -- reconstructs each sink's real
     template literal verbatim (matching the source line for line) and
     evaluates it with the surface's own real escapeHtml against hostile
     payloads, using a small hand-rolled tag/text splitter (no jsdom
     dependency exists in this repo) to prove (a) the hostile input's
     text content survives verbatim as text, and (b) no new element
     (img/script/svg/etc.) gets created by it.
"""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from restoricon_core.api import web_surfaces

NODE = shutil.which("node")

HOSTILE_PAYLOADS = [
    "<img src=x onerror=alert(1)>",
    "</td><td>injected",
    "<script>alert(1)</script>",
    'a & b < c > d "e" \'f\'',
    "O'Brien",  # non-hostile regression check: legitimate data still round-trips
]

OPTION_PAYLOADS = HOSTILE_PAYLOADS + ["</option><script>alert(1)</script>"]


def _admin_escape_html_source() -> str:
    html = web_surfaces.render_admin_surface()
    m = re.search(r"function escapeHtml\(unsafe\) \{.*?\n\s*\}\n", html, re.DOTALL)
    assert m, "render_admin_surface() no longer defines escapeHtml(unsafe)"
    return m.group(0)


# Small tag/text splitter -- sufficient for these sinks' known-simple,
# single-level structure. Finds every `<tag ...>` / `</tag>` boundary and
# the text between them.
_SPLITTER = r"""
function splitTags(html) {
    const parts = [];
    const re = /<[^>]*>/g;
    let last = 0, m;
    while ((m = re.exec(html))) {
        if (m.index > last) parts.push({type: 'text', value: html.slice(last, m.index)});
        parts.push({type: 'tag', value: m[0]});
        last = re.lastIndex;
    }
    if (last < html.length) parts.push({type: 'text', value: html.slice(last)});
    return parts;
}
function decodeEntities(s) {
    return s
        .replace(/&quot;/g, '"').replace(/&#039;/g, "'")
        .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}
function tagNamesOf(parts, allowed) {
    const names = parts.filter(p => p.type === 'tag' && !p.value.startsWith('</'))
        .map(p => (p.value.match(/^<([a-zA-Z0-9]+)/) || [])[1].toLowerCase());
    return names.filter(n => !allowed.has(n));
}
"""


def _run_node(script: str, timeout: int = 30):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(script)
        path = f.name
    try:
        return subprocess.run([NODE, path], capture_output=True, text=True, timeout=timeout)
    finally:
        Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 1. Wiring/presence assertions against the real rendered HTML.
# ---------------------------------------------------------------------------

def test_load_users_list_wraps_fields_in_escape_html():
    html = web_surfaces.render_admin_surface()
    start = html.index("async function loadUsersList()")
    region = html[start:html.index("async function loadDeletedUserHistory", start)]
    assert "<strong>${escapeHtml(u.username)}</strong>" in region
    assert "<td>${escapeHtml(u.full_name)}</td>" in region
    assert "<td>${escapeHtml(u.email)}</td>" in region
    assert '<span class="card-badge badge-slate">${escapeHtml(u.role)}</span>' in region
    # Unescaped literals must be gone.
    assert "${u.username}" not in region
    assert "${u.full_name}" not in region
    assert "${u.email}" not in region
    assert "${u.role}" not in region


def test_load_crm_list_wraps_customer_and_project_fields_in_escape_html():
    html = web_surfaces.render_admin_surface()
    start = html.index("async function loadCrmList()")
    region = html[start:html.index("function populateCustomerDropdown()", start)]
    assert "${escapeHtml(c.first_name || '')} ${escapeHtml(c.last_name || '')}" in region
    assert "${escapeHtml(c.email || '')} | ${escapeHtml(c.phone || '')}" in region
    assert "${escapeHtml(p.title || 'Untitled')}" in region
    assert "${escapeHtml(p.stage)}</span> - ${escapeHtml(p.project_type)}" in region
    # Unescaped literals must be gone.
    assert "${c.first_name || ''} ${c.last_name || ''}" not in region
    assert "${c.email || ''} | ${c.phone || ''}" not in region
    assert "${p.title || 'Untitled'}</div>" not in region
    assert "${p.stage}</span> - ${p.project_type}" not in region


def test_populate_customer_dropdown_wraps_fields_in_escape_html():
    html = web_surfaces.render_admin_surface()
    start = html.index("function populateCustomerDropdown()")
    region = html[start:html.index("function filterCrm()", start)]
    assert "<option value=\"${c.id}\">${escapeHtml(c.first_name)} ${escapeHtml(c.last_name)}</option>" in region
    assert "${c.first_name} ${c.last_name}</option>" not in region


# ---------------------------------------------------------------------------
# 2. Mechanism round-trip proof, real escapeHtml, real template shape.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(NODE is None, reason="node not installed in this environment")
@pytest.mark.parametrize("payload", HOSTILE_PAYLOADS)
def test_users_row_textnode_survives_as_text_only(payload):
    """Reconstructs the 4 <td> cells verbatim (matching loadUsersList()'s
    real template) and proves the hostile username survives as inert
    text with no new element created."""
    script = _admin_escape_html_source() + _SPLITTER + f"""
const u = {{ username: {json.dumps(payload)}, full_name: "Regular Name", email: "a@b.com", role: "admin" }};
const html = `<td>#${{1}}</td><td><strong>${{escapeHtml(u.username)}}</strong></td><td>${{escapeHtml(u.full_name)}}</td><td>${{escapeHtml(u.email)}}</td><td><span class="card-badge badge-slate">${{escapeHtml(u.role)}}</span></td>`;
const parts = splitTags(html);
const bad = tagNamesOf(parts, new Set(['td', 'strong', 'span']));
if (bad.length) {{ console.error('unexpected element created: ' + bad.join(',')); process.exit(2); }}
const texts = parts.filter(p => p.type === 'text').map(p => decodeEntities(p.value));
if (texts[1] !== u.username) {{
    console.error('mismatch: ' + JSON.stringify(texts[1]) + ' !== ' + JSON.stringify(u.username));
    process.exit(3);
}}
"""
    result = _run_node(script)
    assert result.returncode == 0, f"rc={result.returncode}\n{result.stderr}"


@pytest.mark.skipif(NODE is None, reason="node not installed in this environment")
@pytest.mark.parametrize("payload", HOSTILE_PAYLOADS)
def test_crm_customer_block_textnode_survives_as_text_only(payload):
    script = _admin_escape_html_source() + _SPLITTER + f"""
const c = {{ first_name: {json.dumps(payload)}, last_name: "Doe", email: "a@b.com", phone: "555-1234" }};
const html = `<div style="x">${{escapeHtml(c.first_name || '')}} ${{escapeHtml(c.last_name || '')}}</div><div style="y">${{escapeHtml(c.email || '')}} | ${{escapeHtml(c.phone || '')}}</div>`;
const parts = splitTags(html);
const bad = tagNamesOf(parts, new Set(['div']));
if (bad.length) {{ console.error('unexpected element created: ' + bad.join(',')); process.exit(2); }}
const texts = parts.filter(p => p.type === 'text').map(p => decodeEntities(p.value));
const expectedName = {json.dumps(payload)} + ' ' + c.last_name;
if (texts[0] !== expectedName) {{
    console.error('mismatch: ' + JSON.stringify(texts[0]) + ' !== ' + JSON.stringify(expectedName));
    process.exit(3);
}}
"""
    result = _run_node(script)
    assert result.returncode == 0, f"rc={result.returncode}\n{result.stderr}"


@pytest.mark.skipif(NODE is None, reason="node not installed in this environment")
@pytest.mark.parametrize("payload", HOSTILE_PAYLOADS)
def test_crm_project_block_textnode_survives_as_text_only(payload):
    script = _admin_escape_html_source() + _SPLITTER + f"""
const p = {{ title: {json.dumps(payload)}, stage: "intake", project_type: {json.dumps(payload)} }};
const html = `<div style="x">${{escapeHtml(p.title || 'Untitled')}}</div><div style="y"><span class="badge">${{escapeHtml(p.stage)}}</span> - ${{escapeHtml(p.project_type)}}</div>`;
const parts = splitTags(html);
const bad = tagNamesOf(parts, new Set(['div', 'span']));
if (bad.length) {{ console.error('unexpected element created: ' + bad.join(',')); process.exit(2); }}
const texts = parts.filter(p => p.type === 'text').map(p => decodeEntities(p.value));
if (texts[0] !== p.title) {{
    console.error('title mismatch: ' + JSON.stringify(texts[0]) + ' !== ' + JSON.stringify(p.title));
    process.exit(3);
}}
if (texts[1] !== p.stage) {{
    console.error('stage mismatch: ' + JSON.stringify(texts[1]) + ' !== ' + JSON.stringify(p.stage));
    process.exit(4);
}}
const expectedTail = ' - ' + p.project_type;
if (texts[2] !== expectedTail) {{
    console.error('type mismatch: ' + JSON.stringify(texts[2]) + ' !== ' + JSON.stringify(expectedTail));
    process.exit(5);
}}
"""
    result = _run_node(script)
    assert result.returncode == 0, f"rc={result.returncode}\n{result.stderr}"


@pytest.mark.skipif(NODE is None, reason="node not installed in this environment")
@pytest.mark.parametrize("payload", OPTION_PAYLOADS)
def test_customer_dropdown_option_textcontent_survives_verbatim(payload):
    """Per the task's explicit instruction: do NOT rely on element-absence
    checks for the <option> sink -- the HTML in-select insertion mode
    silently drops most element start tags inside <option> regardless of
    whether escaping happened, so an element-absence assertion would give
    false confidence. Instead assert the decoded text content equals the
    raw hostile input string verbatim, proving it was escaped and then
    decodes back to plain text rather than parsing as markup."""
    script = _admin_escape_html_source() + _SPLITTER + f"""
const c = {{ id: 7, first_name: {json.dumps(payload)}, last_name: "Doe" }};
const html = `<option value="${{c.id}}">${{escapeHtml(c.first_name)}} ${{escapeHtml(c.last_name)}}</option>`;
const parts = splitTags(html);
const texts = parts.filter(p => p.type === 'text').map(p => decodeEntities(p.value));
const expected = {json.dumps(payload)} + ' ' + c.last_name;
if (texts[0] !== expected) {{
    console.error('mismatch: ' + JSON.stringify(texts[0]) + ' !== ' + JSON.stringify(expected));
    process.exit(3);
}}
"""
    result = _run_node(script)
    assert result.returncode == 0, f"rc={result.returncode}\n{result.stderr}"
