"""
Unit/integration tests for B9.5 -- the staff-facing `/estimates` estimator
builder UI (`render_estimates_surface()` in `web_surfaces.py`, wired to the
real B9.3/B9.4 `/api/v1/estimator/estimates/...` routes). Covers:

  - The route serves the surface's HTML (GET /estimates and /estimates/).
  - RBAC-gating deviation, stated explicitly (see render_estimates_surface()'s
    own docstring and this round's handoff): this codebase's web-surface GET
    routes (/sales, /pm, /tech, /subcontractor, and now /estimates) are all
    served BEFORE `actor` is authenticated in `APIRouter.handle_request`, so
    there is no server-side per-role gate possible on the shell HTML itself
    -- unlike B8.16's `_render_work_order_intake_section()`, whose role_key
    gate is a hardcoded per-route constant, not an authenticated identity.
    What IS testable and tested here: the surface's markup is genuinely
    distinct from (not accidentally leaked into) the other staff portals'
    rendered bytes, and every mutating API call the page's JS makes is
    gated server-side by EstimateService's own RBAC (already covered by
    test_b9_2_estimate_service.py / test_b9_3_estimate_routes.py -- not
    re-tested here).
  - XSS regression: every dynamic value this surface's client-side JS
    renders (customer search results, line-item rows) is routed through
    escapeHtml() before reaching innerHTML, and no onclick/oninput inlines
    a stringified object -- same NEW-661/664 discipline
    test_b8_16_phase4_intake_form.py already established, checked at the
    source level (this surface renders no server-side dynamic value
    either, same as the B8.16 form).
  - Focus-preservation regression: editing a line's description does NOT
    trigger a full estRenderLineItems() re-render; add/remove do.
  - A source-level check that the JS targets the real B9.3/B9.4 route
    paths, plus a full live round-trip through APIRouter (create customer
    -> create estimate -> add line -> preview -> send) confirming those
    same paths actually work end-to-end.
"""

import json

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.api.web_surfaces import (
    render_estimates_surface,
    render_pm_surface,
    render_sales_surface,
    render_subcontractor_surface,
    render_tech_surface,
)
from restoricon_core.auth import AuthService, ROLE_ADMIN, ROLE_SALES
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer
from restoricon_core.services.analytics_search_service import AnalyticsSearchService
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.business_ops_service import BusinessOpsService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.estimate_service import EstimateService
from restoricon_core.services.finance_service import FinanceService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService


# ==========================================
# Route wiring (static HTML, no server needed for the wiring itself)
# ==========================================


@pytest.fixture
def api_setup():
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    auth = AuthService(db)
    crm = CRMService(db, audit)
    comm = CommunicationService(db)
    sched = SchedulingService(db, audit)
    auto = AutomationService(db, audit)
    ops = OperationsService(db, audit)
    fin = FinanceService(db, audit)
    bops = BusinessOpsService(db, audit)
    search = AnalyticsSearchService(db)
    estimates = EstimateService(db, audit)

    router = APIRouter(
        auth_service=auth,
        crm_service=crm,
        comm_service=comm,
        audit_service=audit,
        scheduling_service=sched,
        automation_service=auto,
        operations_service=ops,
        finance_service=fin,
        business_ops_service=bops,
        analytics_search_service=search,
        estimate_service=estimates,
    )

    admin_u = auth.create_user("admin_estui", "AdminPass123!", "Admin Est UI", "admin_estui@test.com", ROLE_ADMIN)
    admin_tok = auth.create_token(admin_u)
    sales_u = auth.create_user("sales_estui", "SalesPass123!", "Sales Est UI", "sales_estui@test.com", ROLE_SALES)
    sales_tok = auth.create_token(sales_u)

    return {"router": router, "auth": auth, "admin_tok": admin_tok, "sales_tok": sales_tok}


def _req(router: APIRouter, method: str, path: str, token: str = None, body: dict = None):
    headers = {"authorization": f"Bearer {token}"} if token else {}
    body_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
    status, res_headers, res_body = router.handle_request(method, path, headers, body_bytes)
    if isinstance(res_body, dict):
        res_body = json.loads(json.dumps(res_body))
    return status, res_headers, res_body


def test_estimates_route_serves_surface_html(api_setup):
    router = api_setup["router"]
    status, headers, body = _req(router, "GET", "/estimates")
    assert status == 200, body
    assert headers["Content-Type"].startswith("text/html")
    assert 'id="estAddLineModal"' in body
    assert "Estimate Builder" in body


def test_estimates_route_trailing_slash_also_serves_surface(api_setup):
    router = api_setup["router"]
    status, headers, body = _req(router, "GET", "/estimates/")
    assert status == 200, body
    assert 'id="estAddLineModal"' in body


def test_estimates_surface_markup_absent_from_other_staff_portals():
    # Confirms this surface's own markup didn't leak into a shared base
    # template it doesn't belong to -- the inverse of B8.16's own
    # absent-from-other-portals test, applied to the one thing that's
    # actually checkable given this surface is its own dedicated function
    # (not a role_key-gated section of _render_staff_portal_base).
    for html in (render_pm_surface(), render_sales_surface(), render_tech_surface(), render_subcontractor_surface()):
        assert 'id="estAddLineModal"' not in html
        assert "estCreateEstimate()" not in html


def test_estimates_surface_does_not_include_unrelated_woi_markup():
    html = render_estimates_surface()
    assert 'id="woiModal"' not in html
    assert "openWorkOrderIntakeModal" not in html


# ==========================================
# XSS / injection discipline (source-level, matching
# test_b8_16_phase4_intake_form.py's established convention)
# ==========================================


def test_customer_search_results_escape_dynamic_values():
    html = render_estimates_surface()
    start = html.index("async function estSearchCustomers()")
    end = html.index("function estSelectCustomer(customerId)", start)
    fn_body = html[start:end]
    assert "escapeHtml((c.first_name" in fn_body
    assert "escapeHtml(c.phone" in fn_body
    assert "escapeHtml(c.customer_number)" in fn_body
    # No stringified-object inlining into the onclick attribute --
    # index-based lookup into the held search-results array only.
    assert "JSON.stringify(c)" not in fn_body
    assert "estSelectCustomer(${c.id})" in fn_body


def test_line_items_render_escapes_dynamic_values_and_uses_index_lookup():
    html = render_estimates_surface()
    start = html.index("function estRenderLineItems()")
    end = html.index("function estUpdateLineItem(index, value)", start)
    fn_body = html[start:end]
    assert "escapeHtml(item.description)" in fn_body
    assert "escapeHtml(item.line_type)" in fn_body
    assert "JSON.stringify(item)" not in fn_body
    assert "estUpdateLineItem(${i}" in fn_body
    assert "estRemoveLineItem(${i})" in fn_body


def test_add_line_form_never_computes_authoritative_totals_client_side():
    # The only totals ever displayed come from estRefreshPreview()'s server
    # response -- confirm the add-line submit path does not itself compute
    # or render a sell/total figure.
    html = render_estimates_surface()
    start = html.index("async function estSubmitAddLine(e)")
    end = html.index("function estRenderLineItems()", start)
    fn_body = html[start:end]
    assert "sell_total" not in fn_body
    assert "estGrandTotal" not in fn_body


# ==========================================
# Focus-preservation regression (mirrors
# test_intake_form_line_item_edit_does_not_trigger_full_rerender)
# ==========================================


def test_line_item_edit_does_not_trigger_full_rerender():
    html = render_estimates_surface()

    def code_only(src: str) -> str:
        return "\n".join(line for line in src.splitlines() if not line.strip().startswith("//"))

    update_start = html.index("function estUpdateLineItem(index, value)")
    update_end = html.index("async function estCommitLineEdit(index)", update_start)
    update_body = code_only(html[update_start:update_end])
    assert "estRenderLineItems()" not in update_body

    commit_start = update_end
    commit_end = html.index("async function estRemoveLineItem(index)", commit_start)
    commit_body = code_only(html[commit_start:commit_end])
    assert "estRenderLineItems()" not in commit_body

    remove_start = commit_end
    remove_end = html.index("async function estRefreshPreview()", remove_start)
    assert "estRenderLineItems()" in code_only(html[remove_start:remove_end])

    # estSubmitAddLine (a genuine structural change -- a new row/index) DOES
    # call the full re-render, unlike the edit paths asserted above.
    add_start = html.index("async function estSubmitAddLine(e)")
    add_end = html.index("function estRenderLineItems()", add_start)
    add_body = code_only(html[add_start:add_end])
    assert "estLineItems.push(data.line)" in add_body
    assert "estRenderLineItems();" in add_body


# ==========================================
# Route-path correctness (source-level string presence + a real round trip)
# ==========================================


def test_surface_js_targets_real_estimator_route_paths():
    html = render_estimates_surface()
    assert "/api/v1/estimator/estimates'" in html  # create (POST)
    assert "/lines'" in html
    assert "/preview'" in html
    assert "/transition'" in html
    assert "/api/v1/customers?search=" in html
    assert "/api/v1/customers'" in html  # create-new-customer POST


def test_full_round_trip_customer_estimate_line_preview_send(api_setup):
    router = api_setup["router"]
    admin_tok = api_setup["admin_tok"]
    sales_tok = api_setup["sales_tok"]

    # 1. Customer picker -> create a new customer, same route the surface's
    #    estSubmitNewCustomer() calls.
    status, _, body = _req(
        router, "POST", "/api/v1/customers", sales_tok,
        {"first_name": "Robin", "last_name": "Estimate", "email": "robin.estimate@test.com"},
    )
    assert status == 201, body
    customer_id = body["customer"]["id"]

    # 2. New estimate -> POST /api/v1/estimator/estimates.
    status, _, body = _req(
        router, "POST", "/api/v1/estimator/estimates", sales_tok,
        {"customer_id": customer_id, "title": "UI round trip"},
    )
    assert status == 201, body
    est_id = body["estimate"]["id"]
    assert body["estimate"]["workflow_status"] == "DRAFT"

    # 3. Add-line sheet -> POST .../lines (material line, same shape
    #    estSubmitAddLine() builds when material_markup_bp is left blank).
    status, _, body = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/lines", sales_tok,
        {
            "line_type": "material", "description": "Drywall sheets",
            "customer_description": "Drywall", "quantity": 10, "unit": "SF",
            "unit_cost_cents": 1000,
        },
    )
    assert status == 201, body
    assert body["line"]["material_markup_bp"] == 3000  # default applied server-side

    # 4. Server-computed preview -> GET .../preview.
    status, _, body = _req(router, "GET", f"/api/v1/estimator/estimates/{est_id}/preview", sales_tok)
    assert status == 200, body
    preview = body["preview"]
    assert preview["total_cents"] > 0
    # sales holds PERM_READ_ESTIMATE_COSTS -- cost fields are populated, not null.
    assert preview["cost_total_cents"] is not None

    # 5. Send -> POST .../transition {new_status: "SENT"}.
    status, _, body = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/transition", sales_tok,
        {"new_status": "SENT"},
    )
    assert status == 200, body
    assert body["estimate"]["workflow_status"] == "SENT"
    # sales holds PERM_SEND_ESTIMATES -- the send succeeds directly from
    # DRAFT (internal_review_required is 0 by default for this actor), and
    # the share_link_out is populated -- the raw token the surface's
    # estSendEstimate() must surface to the user per B9.4/NEW-712.
    assert "share_link" in body
    assert body["share_link"]["raw_token"]
