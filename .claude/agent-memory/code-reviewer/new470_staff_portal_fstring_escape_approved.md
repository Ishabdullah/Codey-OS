---
name: new470-staff-portal-fstring-escape-approved
description: NEW-470 web_surfaces.py _render_staff_portal_base doubled-brace f-string fix — APPROVED r1
metadata:
  type: project
---

NEW-470: `_render_staff_portal_base()` in restoricon_core/api/web_surfaces.py served literal
`{_get_common_styles()}` / `{_get_universal_drawer_html("admin")}` text to the 4 staff portals
(pm/sales/tech/subcontractor). Fix: un-double the braces on those 2 lines only.

**Why approved:** CSS `.portal-layout {{ }}` blocks and JS `${{escapeHtml(...)}}` template literals
in the same f-string keep their doubled braces (correct). `rg '\{\{[a-zA-Z_]+\('` shows the only
other doubled-brace call-shapes in the file are `${{escapeHtml(` JS literals. Helpers return plain
triple-quoted strings containing `{`/`}`; f-strings do not re-process interpolated values, and
sibling sites at :482 / :566 / :663 already interpolate these same helpers single-braced.
New test test_staff_portals.py (13 cases) pins: no literal f-string text, `styles[:200] in html`,
`universal-navbar` drawer present, role title interpolated. `pytest tests/test_restoricon_core/`
= 459 passed. Not process-lifecycle / not RBAC.

**How to apply:** if this f-string is edited again, re-run the doubled-brace rg sweep — the file
mixes Python-f-string CSS, JS template literals, and single-brace interpolations in one string.
