"""B8.10a: follow-up action wiring (Complete/Cancel/Snooze buttons) and
task_type/trigger_source/rule_name badges on the sales portal's dashboard
Follow-ups panel and the Customer 360 Tasks panel. Pure UI wiring over the
already-existing/already-tested `/api/v1/crm/tasks/{id}/complete` and
`/api/v1/crm/tasks/{id}/update` routes (route-level round-trip coverage for
this round's new UI-triggered call shapes -- cancel via status update,
snooze via due_date update -- lives in test_crm_sales_engine.py). This file
covers the rendered HTML/JS shape only, matching
test_b8_4a_customer_360_and_property_panels.py's established convention.

Actual JS syntax validity (the doubled-brace `${{...}}` convention, the
documented NEW-538 regression source) is covered generically for every
render_* surface by test_web_surfaces_js_syntax.py -- not duplicated here.
"""

from restoricon_core.api.web_surfaces import render_sales_surface


def test_followups_panel_has_type_and_actions_columns():
    html = render_sales_surface()
    start = html.index('<h2 style="margin-top:0;">Follow-ups</h2>')
    end = html.index("</table>", start)
    panel_html = html[start:end]
    assert "<th>Type</th>" in panel_html
    assert "<th>Actions</th>" in panel_html
    # colspan on the loading/empty placeholder rows must match the real
    # column count (6: Title, Type, Due, Priority, Status, Actions) -- a
    # stale colspan doesn't break rendering but is exactly the kind of
    # drift this project's rule 6 asks to catch, not leave standing.
    assert 'colspan="6"' in panel_html


def test_dashboard_followups_renderer_wires_badge_and_actions():
    html = render_sales_surface()
    start = html.index("const renderTask = (t, overdue) =>")
    end = html.index("const fuRows = [")
    render_task_js = html[start:end]
    assert "taskTypeBadge(t)" in render_task_js
    assert "taskActionButtons(t)" in render_task_js


def test_customer_360_tasks_panel_wires_badge_and_actions():
    html = render_sales_surface()
    start = html.index("c360PanelSection('Tasks'")
    # The call's header-row argument ends "...</thead>');" (a single
    # quote, not a double quote) -- a bare `");` search overshoots past
    # this call entirely into unrelated downstream code, which would let
    # this test pass by accident rather than by actually isolating the
    # Tasks panel's own renderer.
    end = html.index("</thead>');", start)
    tasks_panel_js = html[start:end]
    assert "taskTypeBadge(t)" in tasks_panel_js
    assert "taskActionButtons(t)" in tasks_panel_js
    assert "<th>Type</th>" in tasks_panel_js
    assert "<th>Actions</th>" in tasks_panel_js


def test_task_action_functions_hit_real_existing_routes():
    """No new backend route this round -- Complete/Cancel/Snooze must all
    call the pre-existing complete/update endpoints, never a fabricated
    new one."""
    html = render_sales_surface()

    complete_start = html.index("async function completeTaskAction(id)")
    complete_end = html.index("async function cancelTaskAction(id)")
    complete_js = html[complete_start:complete_end]
    assert "/api/v1/crm/tasks/' + id + '/complete" in complete_js

    cancel_start = complete_end
    cancel_end = html.index("async function snoozeTaskAction(id, currentDueDate)")
    cancel_js = html[cancel_start:cancel_end]
    assert "/api/v1/crm/tasks/' + id + '/update" in cancel_js
    assert "status: 'cancelled'" in cancel_js

    snooze_start = cancel_end
    snooze_end = html.index("let dashboardRefreshInFlight")
    snooze_js = html[snooze_start:snooze_end]
    assert "/api/v1/crm/tasks/' + id + '/update" in snooze_js
    assert "due_date: newDueDate" in snooze_js


def test_no_new_task_status_value_invented_for_pause():
    """'Pause' has no backing Task.status value (only pending/in_progress/
    completed/cancelled exist) -- this round must implement the pause-like
    request as the existing Cancel action, never a fabricated 'paused'
    status string anywhere in the rendered surface."""
    html = render_sales_surface()
    assert "'paused'" not in html
    assert '"paused"' not in html


def test_task_type_badge_shows_auto_tag_only_when_trigger_source_set():
    html = render_sales_surface()
    start = html.index("function taskTypeBadge(t)")
    end = html.index("function taskActionButtons(t)")
    badge_js = html[start:end]
    assert "t.trigger_source" in badge_js
    assert "t.rule_name" in badge_js
    assert "Auto" in badge_js


def test_task_action_buttons_only_render_for_actionable_status():
    html = render_sales_surface()
    start = html.index("function taskActionButtons(t)")
    end = html.index("async function completeTaskAction(id)")
    buttons_js = html[start:end]
    assert "t.status !== 'pending' && t.status !== 'in_progress'" in buttons_js
    assert "completeTaskAction(" in buttons_js
    assert "cancelTaskAction(" in buttons_js
    assert "snoozeTaskAction(" in buttons_js
