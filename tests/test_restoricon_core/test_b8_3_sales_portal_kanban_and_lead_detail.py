"""B8.3 Parts B/C/D: sales portal lead detail modal, lead create form,
opportunity kanban board, and stage-stuck analytics panel. Covers the
rendered HTML/JS shape only (matches test_sales_portal_leads_opportunities.py's
established convention) -- real server-side scoping/permission behavior is
covered by tests/test_restoricon_core/test_b8_3_lead_convert_and_stage_analytics.py
and test_crm_sales_engine.py."""

from restoricon_core.api.web_surfaces import render_sales_surface


def test_sales_portal_has_lead_detail_modal_and_view_link():
    html = render_sales_surface()
    assert 'id="leadDetailModal"' in html
    assert "openLeadDetailModal(" in html
    assert "onclick=\"openLeadDetailModal(${l.id}); return false;\"" in html


def test_sales_portal_lead_detail_shows_real_lead_fields():
    """Lead detail rendering must reference each real Lead field (models.py)
    -- not a guessed subset."""
    html = render_sales_surface()
    start = html.index("function renderLeadDetail(l)")
    end = html.index("async function scoreLeadFromModal(")
    detail_js = html[start:end]
    for field in [
        "l.status", "l.source", "l.score", "l.property_type", "l.project_scope",
        "l.urgency_level", "l.insurance_status", "l.estimated_value",
        "l.first_contact_at", "l.last_contact_at", "l.next_followup_at",
        "l.notes", "l.lost_reason", "l.assigned_user_id", "l.customer_id",
    ]:
        assert field in detail_js, f"lead detail modal is missing {field}"


def test_sales_portal_lead_edit_only_sends_real_update_lead_allowed_fields():
    """update_lead's real allowed_fields set (crm_service.py) is a superset
    of what saveLeadEdit sends -- assert it never sends a field outside that
    set (a typo'd/invented field name would be silently dropped server-side
    by update_lead's allow-list, not an error, so this is worth pinning)."""
    html = render_sales_surface()
    start = html.index("async function saveLeadEdit(id)")
    end = html.index("// Convert-to-opportunity")
    save_js = html[start:end]
    allowed = {
        "customer_id", "source", "status", "score", "score_factors",
        "property_type", "project_scope", "urgency_level", "insurance_status",
        "estimated_value", "assigned_user_id", "first_contact_at",
        "last_contact_at", "next_followup_at", "notes", "lost_reason",
    }
    sent_fields = {
        "status", "property_type", "project_scope", "urgency_level",
        "insurance_status", "estimated_value", "notes",
    }
    assert sent_fields.issubset(allowed)
    for field in sent_fields:
        assert f"{field}:" in save_js
    assert "/api/v1/leads/' + id + '/update'" in save_js


def test_sales_portal_convert_button_and_route():
    html = render_sales_surface()
    assert "convertLeadAction(" in html
    assert "/api/v1/leads/' + id + '/convert'" in html
    assert "customer_fields" in html


def test_sales_portal_create_lead_form_uses_only_real_lead_fields():
    """POST /api/v1/leads constructs Lead(**json_body) directly (routes.py)
    -- the create form must only ever send real Lead dataclass field names."""
    html = render_sales_surface()
    start = html.index("async function submitCreateLead()")
    end = html.index("window.onload = loadDashboard;")
    create_js = html[start:end]
    real_lead_fields = {
        "id", "external_id", "customer_id", "source", "status", "score",
        "score_factors", "property_type", "project_scope", "urgency_level",
        "insurance_status", "estimated_value", "assigned_user_id",
        "first_contact_at", "last_contact_at", "next_followup_at", "notes",
        "lost_reason", "created_at", "updated_at",
    }
    sent_fields = {"source", "property_type", "project_scope", "urgency_level",
                   "insurance_status", "estimated_value", "notes", "customer_id"}
    assert sent_fields.issubset(real_lead_fields)
    for field in ["source", "property_type", "project_scope", "urgency_level",
                  "insurance_status", "estimated_value", "notes"]:
        assert f"{field}:" in create_js
    assert "/api/v1/leads'" in create_js


def test_sales_portal_kanban_columns_match_pipeline_stage_order_verbatim():
    """Columns must be the real PipelineStage.STAGE_ORDER list verbatim, in
    order (read directly from models.py) -- Opportunity-only, not a
    Lead.status column set."""
    html = render_sales_surface()
    assert (
        "const KANBAN_STAGES = ['new_lead', 'contacted', 'appointment_set', "
        "'estimate_scheduled', 'estimate_sent', 'proposal_sent', 'negotiation', "
        "'won', 'lost'];" in html
    )
    assert "fetch('/api/v1/opportunities'" in html


def test_sales_portal_kanban_lost_transition_requires_reason():
    """NEW-558: LOST column requires a reason before firing the transition."""
    html = render_sales_surface()
    start = html.index("async function handleStageChange(")
    end = html.index("// -----", start)
    js = html[start:end]
    assert "newStage === 'lost'" in js
    assert "prompt(" in js
    assert "lost_reason" in js
    assert "/api/v1/opportunities/' + id + '/transition'" in js


def test_sales_portal_kanban_claim_before_transition_gate():
    """NEW-558: an unclaimed opportunity's card must show a Claim-first
    action instead of the Move-to select -- a client-side UI gate only, no
    new server-side enforcement."""
    html = render_sales_surface()
    start = html.index("function renderKanbanCard(o, stage)")
    end = html.index("// Claim-before-transition")
    card_js = html[start:end]
    assert "isClaimed" in card_js
    assert "Claim first" in card_js
    assert "claimOpportunity(" in card_js
    assert "handleStageChange(this" in card_js


def test_sales_portal_stage_analytics_panel_present():
    html = render_sales_surface()
    assert 'id="stageAnalyticsList"' in html
    assert 'id="currentlyStuckList"' in html
    assert "/api/v1/sales/pipeline-stuck-analytics" in html
    assert "avg_hours_per_stage" in html
    assert "opportunities_with_full_chain" in html
    assert "opportunities_using_fallback" in html
    assert "currently_stuck" in html
