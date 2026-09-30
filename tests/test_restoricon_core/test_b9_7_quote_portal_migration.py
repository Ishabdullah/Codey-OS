"""
B9.7 -- quote portal migration (D8, `codey_estimator_service.md` S:7).

`Codey-Estimator/docs/DECISIONS.md` line 17 (D8): "Remove the public $/sq ft
ranges. Replace with a 'request an estimate' flow; no price expectations
set before a real estimator looks at the job." This is a pure front-end
content change to `render_quote_surface()` -- no schema/API change, no new
route: the existing `POST /api/v1/public/leads` lead-capture form is
untouched, only the self-service $/sq-ft calculator UI/JS is removed and
replaced with a "Request a Free Estimate" CTA that scrolls to and focuses
the same lead-intake form.

String-level presence/absence assertions only, matching this project's
established convention for JS-in-Python-string surfaces (see
test_web_surfaces_admin_wiring.py's module docstring) -- there is no Python
test harness for actual DOM/JS execution here.
"""

import re

from restoricon_core.api.web_surfaces import render_quote_surface


def test_calculator_is_genuinely_removed():
    """No $/sq-ft computation path is reachable from this surface anymore:
    the calculator's markup ids, its result-rendering CSS classes, and its
    JS calculation function must all be gone, not just visually hidden."""
    html = render_quote_surface()

    # Markup: calculator input fields and result display no longer exist.
    for calc_id in (
        "calcArea",
        "calcHeight",
        "calcCategory",
        "calcCostRange",
        "calcMovers",
        "calcDehums",
        "calcContainment",
    ):
        assert calc_id not in html, f"calculator element {calc_id!r} still present"

    # CSS: the calculator's result-box styling is gone (nothing left to
    # style once the calculator markup is removed).
    for css_class in ("calc-result-box", "calc-result-num", "calc-meta-grid", "calc-meta-item"):
        assert css_class not in html, f"leftover calculator CSS class {css_class!r}"

    # JS: the calculation function is gone. (Not asserting "multiplier"
    # is absent page-wide -- that would be a whole-page substring ban that
    # could false-fail on unrelated future content in the shared
    # _get_common_styles()/_get_common_script() helpers; the calc-id and
    # dollar-range checks above already cover the real requirement.)
    assert "runDryingCalculation" not in html

    # No hardcoded computed-looking dollar range remains anywhere in the
    # page (the old default render showed "$2,400 - $4,800").
    assert not re.search(r"\$[\d,]+\s*-\s*\$[\d,]+", html), (
        "a computed-looking dollar price range is still present in the "
        "rendered quote surface"
    )


def test_request_estimate_cta_renders():
    """The replacement CTA is present, wired to the existing lead form
    (no new endpoint/form), and contains no unescaped dynamic content
    (it's static server-authored copy, not user-supplied)."""
    html = render_quote_surface()

    assert "Request a Free Estimate" in html
    assert 'id="ctaRequestEstimateBtn"' in html
    assert "focusLeadIntakeForm" in html

    # The CTA button calls a plain, no-argument JS function -- not an
    # inlined object/onclick payload (this file's established discipline:
    # no inlining objects into onclick attributes).
    assert 'onclick="focusLeadIntakeForm()"' in html

    # The CTA function itself targets the *same* existing lead-intake
    # form/fields, not a duplicate form or a new submission path.
    assert "getElementById('publicQuoteForm')" in html
    assert "getElementById('leadName')" in html


def test_lead_capture_form_and_endpoint_unchanged():
    """D8 only removes the calculator; the lead-capture form and its
    backend endpoint are explicitly out of scope and must still work
    exactly as before."""
    html = render_quote_surface()

    assert 'id="publicQuoteForm"' in html
    assert "/api/v1/public/leads" in html
    assert 'id="leadName"' in html
    assert 'id="leadPhone"' in html
    assert 'id="leadEmail"' in html
    assert 'id="leadAddress"' in html

    # Booking flow (separate from the calculator) is also untouched.
    assert "/api/v1/public/booking" in html
    assert 'id="bookingForm"' in html
