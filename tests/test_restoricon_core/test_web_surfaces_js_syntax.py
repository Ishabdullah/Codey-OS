"""
Regression guard: every rendered surface's <script> content must be
syntactically valid JavaScript.

2026-09-11 incident: a Python triple-quoted (non-raw) string embedding JS
wrote `.join('\n')` intending the two-character JS escape `\n`, but Python's
own string-literal parser consumed it first, producing a literal newline
character inside a single-quoted JS string in the *output* HTML -- invalid
JS syntax. A single syntax error anywhere in a <script> block prevents the
WHOLE script from executing, so this broke every button and every data load
on the live admin page, not just the feature that introduced the bug.

Every prior check this incident slipped through (code-reviewer, the test
suite, live-verifier) checked that expected TEXT was present in the
rendered HTML and that the underlying API calls worked -- none of them ran
the assembled JavaScript through an actual parser. This test closes that
gap: it extracts every <script>...</script> block from every render_*
surface and syntax-checks it with `node --check`, the same tool used to
diagnose and confirm the fix for the incident above.

Skips cleanly (does not fail) if `node` is not installed in the test
environment, rather than false-failing CI on an environment gap.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from restoricon_core.api.web_surfaces import (
    render_admin_surface,
    render_login_surface,
    render_pm_surface,
    render_portal_surface,
    render_quote_surface,
    render_sales_surface,
    render_subcontractor_surface,
    render_tech_surface,
)

NODE = shutil.which("node")

SURFACES = {
    "render_admin_surface": lambda: render_admin_surface(),
    "render_login_surface": lambda: render_login_surface(),
    "render_quote_surface": lambda: render_quote_surface(),
    "render_portal_surface": lambda: render_portal_surface(),
    "render_pm_surface": lambda: render_pm_surface(),
    "render_sales_surface": lambda: render_sales_surface(),
    "render_tech_surface": lambda: render_tech_surface(),
    "render_subcontractor_surface": lambda: render_subcontractor_surface(),
}


def _extract_script_blocks(html: str):
    return re.findall(r"<script>(.*?)</script>", html, re.DOTALL)


@pytest.mark.skipif(NODE is None, reason="node not installed in this environment")
@pytest.mark.parametrize("name", sorted(SURFACES))
def test_rendered_surface_script_is_valid_js(name):
    html = SURFACES[name]()
    blocks = _extract_script_blocks(html)
    assert blocks, f"{name}() produced no <script>...</script> block to check"

    for i, js in enumerate(blocks):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, encoding="utf-8"
        ) as f:
            f.write(js)
            path = f.name
        try:
            result = subprocess.run(
                [NODE, "--check", path],
                capture_output=True,
                text=True,
                timeout=30,
            )
        finally:
            Path(path).unlink(missing_ok=True)

        assert result.returncode == 0, (
            f"{name}()'s <script> block #{i} is not valid JavaScript "
            f"(node --check failed):\n{result.stderr}"
        )


def test_admin_surface_join_backslash_n_regression():
    """Pins the exact incident: .join(...) calls that build a newline-
    separated string for an alert()/message must use the JS escape \\n
    (which requires \\\\n in the Python source, since this string is not
    a raw string), not a literal newline that Python's own parser
    would otherwise have swallowed into the output."""
    html = render_admin_surface()
    assert ").join('\\n')" in html, (
        "expected the properly-escaped JS \\n inside the rendered HTML; "
        "if this fails, the join(...) call likely contains a real newline "
        "character again -- see this file's module docstring"
    )
    # A real embedded newline between the join() parens would mean the
    # single-quote string spans two lines in the raw HTML text.
    assert ").join('\n" not in html
