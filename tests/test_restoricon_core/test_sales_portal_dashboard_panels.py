"""B8.2b: render_sales_surface() wires the new GET /api/v1/sales/dashboard
route (B8.2a, commit a5206a5) into the sales portal -- Appointments,
Follow-ups, Pipeline Summary, Commissions, and a manager-only Team
snapshot, plus the NEW-552 viewer-scope banner fix. This file covers the
portal's rendered HTML/JS shape only; server-side scoping is covered by
tests/test_restoricon_core/test_crm_sales_engine.py and the B8.2a route
tests.

Also covers B8.13b (mobile-first pass, sales-portal half): the
.table-scroll-wrapper container every rendered <table> in the sales
portal must be wrapped in."""

from restoricon_core.api.web_surfaces import _get_common_styles, render_sales_surface


def test_sales_portal_fetches_command_center_dashboard():
    html = render_sales_surface()
    assert "fetch('/api/v1/sales/dashboard?days=7'" in html
    # The three pre-existing panels' data sources must be untouched --
    # this task must not swap them for dashboard sub-fields (a status='new'-
    # only leads subset and a zero-row pipeline aggregate would silently
    # drop rows / delete the claim-button affordance, per this task's spec).
    assert "fetch('/api/v1/leads'" in html
    assert "fetch('/api/v1/opportunities'" in html
    assert "fetch('/api/v1/staff-schedules?user_id=' + user.id" in html


def test_sales_portal_dashboard_fetch_handles_401_and_403():
    html = render_sales_surface()
    start = html.index("Load Command Center Dashboard")
    end = html.index("new panels keep their \"Loading...\" placeholders, no further UI action needed")
    block = html[start:end]
    assert "res.status === 401" in block
    assert "res.status === 403" in block
    assert "Cannot load dashboard: no associated user identity" in block
    # 403 must not redirect -- it's a valid token that just doesn't resolve
    # to a scopable user identity, distinct from the 401 auth-failure case.
    status_403_region = block[block.index("res.status === 403"):block.index("} else if (res.ok)")]
    assert "window.location.href" not in status_403_region


def test_sales_portal_new_panels_present():
    html = render_sales_surface()
    for panel_id in (
        "dashApptTodayList",
        "dashApptUpcomingList",
        "newLeadsBadge",
        "followupsList",
        "pipelineSummaryList",
        "pipelineTotals",
        "commissionsHeading",
        "commissionsList",
        "teamSummaryCard",
        "teamSummaryStrip",
    ):
        assert f'id="{panel_id}"' in html, f"missing panel element #{panel_id}"


def test_sales_portal_pipeline_uses_stage_order_and_per_stage_fields():
    html = render_sales_surface()
    assert "pl.stage_order" in html
    assert "stages[st]" in html
    # Per-stage dicts only carry count/total_value/weighted_value -- there
    # is no per-stage win_rate (CRMService.get_pipeline_summary). win_rate
    # only exists at the pipeline-summary level.
    assert "s.count" in html
    assert "s.total_value" in html
    assert "s.weighted_value" in html
    assert "pl.win_rate" in html


def test_sales_portal_commissions_scope_label_is_independent():
    html = render_sales_surface()
    assert "data.commissions_scope" in html
    assert "commissionsHeading.textContent" in html
    assert "'Commissions (' + (data.commissions_scope === 'team' ? 'Team' : 'Mine') + ')'" in html


def test_sales_portal_team_block_gated_on_key_presence():
    html = render_sales_surface()
    assert "'team' in data" in html
    # Must not gate on scope truthiness instead of key presence.
    assert "data.scope === 'team' && data.team" not in html


def test_sales_portal_tables_wrapped_for_mobile_horizontal_scroll():
    """B8.13b: every <table> the sales portal renders (both the static
    markup and the ones the dashboard/Customer 360 JS builds via
    innerHTML) must be immediately preceded by the shared
    .table-scroll-wrapper container so it scrolls sideways instead of
    overflowing a phone-width viewport. Decided against card-stacking
    (Ish) -- existing table markup is kept exactly as-is."""
    styles = _get_common_styles()
    assert ".table-scroll-wrapper" in styles
    assert "overflow-x: auto" in styles

    html = render_sales_surface()
    table_count = html.count("<table")
    wrapped_count = html.count('<div class="table-scroll-wrapper"><table')
    assert table_count > 0
    assert wrapped_count == table_count, (
        f"expected every <table> ({table_count}) to be immediately preceded "
        f"by <div class=\"table-scroll-wrapper\">, only {wrapped_count} were"
    )

    # Spot-check a sample of distinct panels across the surface, not just
    # the aggregate count -- covers a static dashboard table, a JS-built
    # Customer 360 panel table, and the on-demand assessment-history table.
    for anchor in (
        'id="myScheduleList"',
        'id="commissionRankingsList"',
        "<thead><tr><th>Address</th><th>Type</th><th>Year Built</th>",
        "<thead><tr><th>Created</th><th>Checklist</th><th>Evidence</th>",
    ):
        idx = html.index(anchor)
        preceding = html[max(0, idx - 200):idx]
        assert '<div class="table-scroll-wrapper">' in preceding, (
            f"no table-scroll-wrapper found ahead of panel anchored by {anchor!r}"
        )
