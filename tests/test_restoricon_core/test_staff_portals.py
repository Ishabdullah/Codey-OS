"""NEW-470: the 4 staff portals must serve valid HTML, not literal f-string text."""
import pytest

from restoricon_core.api.web_surfaces import (
    render_pm_surface,
    render_sales_surface,
    render_tech_surface,
    render_subcontractor_surface,
    _get_common_styles,
    _get_universal_drawer_html,
)

PORTALS = [
    ("Project Manager", render_pm_surface),
    ("Sales & Estimating", render_sales_surface),
    ("Field Technician", render_tech_surface),
    ("Subcontractor", render_subcontractor_surface),
]


@pytest.mark.parametrize("role_title,render", PORTALS)
def test_no_literal_fstring_text(role_title, render):
    html = render()
    assert "{_get_common_styles()}" not in html
    assert "{_get_universal_drawer_html" not in html


@pytest.mark.parametrize("role_title,render", PORTALS)
def test_style_block_has_real_css(role_title, render):
    html = render()
    styles = _get_common_styles()
    # a stable substring of the rendered common styles must appear inline
    assert ":root" in styles
    assert ":root" in html
    assert styles[:200] in html


@pytest.mark.parametrize("role_title,render", PORTALS)
def test_nav_drawer_present(role_title, render):
    html = render()
    drawer = _get_universal_drawer_html("admin")
    assert 'class="universal-navbar"' in drawer
    assert 'class="universal-navbar"' in html


def test_role_title_interpolated():
    assert "Project Manager Dashboard" in render_pm_surface()
    assert "Sales & Estimating Dashboard" in render_sales_surface()
    assert "Field Technician Dashboard" in render_tech_surface()
    assert "Subcontractor Dashboard" in render_subcontractor_surface()
