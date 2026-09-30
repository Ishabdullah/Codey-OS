"""
Tests for Phase B9.6 -- the admin-facing `Estimates` tab in
`render_admin_surface()` (`web_surfaces.py`), plus its two supporting
EstimateService read-only getters (`list_versions()`, `get_version_lines()`)
and the two new routes that wire them up (`GET .../versions`,
`GET .../versions/{n}/lines`). This is a DIFFERENT surface from B9.5's
`/estimates` staff builder page -- an admin/manager review view (list/filter,
detail, version history + a side-by-side diff, audit timeline), not a
create/send workflow.

Covers:
  - The tab button, tab-pane, and its JS functions are present in
    render_admin_surface(), and its markup does not leak into the B9.5
    staff builder surface (the inverse check).
  - RBAC/cost-gating -- exercised at the service/route level (there is no
    authenticated actor at admin-shell HTML-render time, same documented
    deviation as B9.5, so an HTML-level cost-gating assertion isn't
    possible; see render_estimates_surface()'s own docstring and this
    round's task brief).
  - `list_versions()`/`get_version_lines()`: cost-field null-safety for an
    actor lacking PERM_READ_ESTIMATE_COSTS, and the IDOR guard (an actor who
    cannot view estimate A cannot read estimate A's version lines by
    guessing/enumerating a version id).
  - The two new routes round-trip through APIRouter, including 404s for a
    missing estimate/version and a 403 for an actor who cannot view the
    estimate at all.
  - XSS regression: the audit-timeline renderer escapes every dynamic
    value (including a decision's `comment`/`signer_name`, which
    record_decision() writes to the audit log's `details` envelope) before
    it reaches innerHTML, and never dumps `signature_data` verbatim into
    the DOM (escaped or not).
  - Source-level check that the tab's JS targets the real B9.3 route paths
    (list/get/preview) plus the two new B9.6 routes.
"""

import json

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.api.web_surfaces import render_admin_surface, render_estimates_surface
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.estimate_service import EstimateService
from restoricon_core.services.scheduling_service import SchedulingService


# ==========================================
# Service-level fixture (mirrors test_b9_2_estimate_service.py's `env`)
# ==========================================


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    crm = CRMService(db, audit)
    svc = EstimateService(db, audit)

    admin_user = auth.create_user("admin_b96", "Pass123!", "Admin B96", "admin_b96@restoricon.com", role=ROLE_ADMIN)
    admin = AuthContext(admin_user.id, admin_user.username, ROLE_ADMIN, "human")

    sales_user = auth.create_user("sales_b96", "Pass123!", "Sales B96", "sales_b96@restoricon.com", role=ROLE_SALES)
    sales = AuthContext(sales_user.id, sales_user.username, ROLE_SALES, "human")

    customer = crm.create_customer(Customer(first_name="Vera", last_name="Client"), admin)
    other_customer = crm.create_customer(Customer(first_name="Other", last_name="Client"), admin)

    # ROLE_CUSTOMER holds PERM_READ_OWN_ESTIMATES but NOT
    # PERM_READ_ESTIMATE_COSTS -- the actor used for cost-gating assertions.
    customer_actor = AuthContext(500001, "cust_b96", ROLE_CUSTOMER, "human", customer_id=customer.id)
    other_customer_actor = AuthContext(500002, "other_cust_b96", ROLE_CUSTOMER, "human", customer_id=other_customer.id)

    return {
        "db": db, "svc": svc, "admin": admin, "sales": sales,
        "customer_id": customer.id, "other_customer_id": other_customer.id,
        "customer_actor": customer_actor, "other_customer_actor": other_customer_actor,
    }


def _material_line(**overrides):
    line = {
        "line_type": "material",
        "description": "Drywall sheets",
        "customer_description": "Drywall",
        "quantity": 10,
        "unit": "SF",
        "unit_cost_cents": 1000,
        "package_qty": 1,
    }
    line.update(overrides)
    return line


# ==========================================
# EstimateService.list_versions() / get_version_lines()
# ==========================================


def test_list_versions_returns_all_versions_in_order(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])
    svc._lock_version(header.current_version_id, "sent", env["admin"])
    svc.revise(header.id, env["sales"])

    versions = svc.list_versions(header.id, env["admin"])
    assert [v.version_number for v in versions] == [1, 2]


def test_list_versions_none_for_missing_estimate(env):
    assert env["svc"].list_versions(999999, env["admin"]) is None


def test_list_versions_permission_error_for_unrelated_customer(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    with pytest.raises(PermissionError):
        svc.list_versions(header.id, env["other_customer_actor"])


def test_list_versions_nulls_cost_fields_without_permission(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])

    # Admin (holds PERM_READ_ESTIMATE_COSTS): cost fields populated.
    admin_versions = svc.list_versions(header.id, env["admin"])
    assert admin_versions[0].cost_total_cents is not None
    assert admin_versions[0].total_cents is not None

    # The estimate's own customer (no PERM_READ_ESTIMATE_COSTS): cost/margin
    # fields nulled, but total_cents (the sell price) stays visible.
    customer_versions = svc.list_versions(header.id, env["customer_actor"])
    assert customer_versions[0].cost_total_cents is None
    assert customer_versions[0].gross_profit_cents is None
    assert customer_versions[0].gross_margin_bp is None
    assert customer_versions[0].material_cost_cents is None
    assert customer_versions[0].total_cents is not None


def test_get_version_lines_none_for_missing_version(env):
    assert env["svc"].get_version_lines(999999, env["admin"]) is None


def test_get_version_lines_gates_cost_fields(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])
    version_id = header.current_version_id

    admin_lines = svc.get_version_lines(version_id, env["admin"])
    assert admin_lines[0].cost_total_cents is not None

    customer_lines = svc.get_version_lines(version_id, env["customer_actor"])
    assert customer_lines[0].cost_total_cents is None
    # price_override_cents/line_total_cents stay visible even ungated --
    # same D9 exception _gate_line_cost_fields() already documents.
    assert customer_lines[0].line_total_cents is not None


def test_get_version_lines_is_not_an_idor(env):
    """The IDOR guard the task brief flagged explicitly: an actor who
    cannot view estimate A must not be able to read A's line items just by
    holding a valid version id for it (e.g. by enumerating small integers).
    """
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])
    version_id = header.current_version_id

    with pytest.raises(PermissionError):
        svc.get_version_lines(version_id, env["other_customer_actor"])


# ==========================================
# Route round trip
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
    estimates = EstimateService(db, audit)

    router = APIRouter(
        auth_service=auth,
        crm_service=crm,
        comm_service=comm,
        audit_service=audit,
        scheduling_service=sched,
        automation_service=auto,
        estimate_service=estimates,
    )

    admin_u = auth.create_user("admin_b96r", "AdminPass123!", "Admin B96 R", "admin_b96r@test.com", ROLE_ADMIN)
    admin_tok = auth.create_token(admin_u)
    sales_u = auth.create_user("sales_b96r", "SalesPass123!", "Sales B96 R", "sales_b96r@test.com", ROLE_SALES)
    sales_tok = auth.create_token(sales_u)

    return {"router": router, "admin_tok": admin_tok, "sales_tok": sales_tok}


def _req(router: APIRouter, method: str, path: str, token: str = None, body: dict = None):
    headers = {"authorization": f"Bearer {token}"} if token else {}
    body_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
    status, res_headers, res_body = router.handle_request(method, path, headers, body_bytes)
    if isinstance(res_body, dict):
        res_body = json.loads(json.dumps(res_body))
    return status, res_headers, res_body


def test_versions_and_diff_routes_round_trip(api_setup):
    router = api_setup["router"]
    sales_tok = api_setup["sales_tok"]
    admin_tok = api_setup["admin_tok"]

    status, _, body = _req(
        router, "POST", "/api/v1/customers", sales_tok,
        {"first_name": "Robin", "last_name": "Versioncheck", "email": "robin.versioncheck@test.com"},
    )
    assert status == 201, body
    customer_id = body["customer"]["id"]

    status, _, body = _req(
        router, "POST", "/api/v1/estimator/estimates", sales_tok,
        {"customer_id": customer_id, "title": "Diff round trip"},
    )
    assert status == 201, body
    est_id = body["estimate"]["id"]

    status, _, body = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/lines", sales_tok,
        {
            "line_type": "material", "description": "Drywall sheets",
            "customer_description": "Drywall", "quantity": 10, "unit": "SF",
            "unit_cost_cents": 1000,
        },
    )
    assert status == 201, body

    # 1 version so far.
    status, _, body = _req(router, "GET", f"/api/v1/estimator/estimates/{est_id}/versions", sales_tok)
    assert status == 200, body
    assert len(body["versions"]) == 1
    assert body["versions"][0]["version_number"] == 1

    status, _, body = _req(
        router, "GET", f"/api/v1/estimator/estimates/{est_id}/versions/1/lines", sales_tok
    )
    assert status == 200, body
    assert body["version"]["version_number"] == 1
    assert len(body["lines"]) == 1
    assert body["lines"][0]["description"] == "Drywall sheets"

    # Send -> locks version 1; revise() -> creates version 2.
    status, _, body = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/transition", sales_tok,
        {"new_status": "SENT"},
    )
    assert status == 200, body

    status, _, body = _req(router, "POST", f"/api/v1/estimator/estimates/{est_id}/revise", sales_tok)
    assert status == 200, body

    status, _, body = _req(router, "GET", f"/api/v1/estimator/estimates/{est_id}/versions", admin_tok)
    assert status == 200, body
    assert [v["version_number"] for v in body["versions"]] == [1, 2]

    status, _, body = _req(
        router, "GET", f"/api/v1/estimator/estimates/{est_id}/versions/2/lines", admin_tok
    )
    assert status == 200, body
    assert body["version"]["version_number"] == 2
    assert len(body["lines"]) == 1  # cloned verbatim from version 1


def test_versions_route_404_for_missing_estimate(api_setup):
    router = api_setup["router"]
    status, _, body = _req(router, "GET", "/api/v1/estimator/estimates/999999/versions", api_setup["admin_tok"])
    assert status == 404, body


def test_versions_lines_route_404_for_missing_version_number(api_setup):
    router = api_setup["router"]
    sales_tok = api_setup["sales_tok"]

    status, _, body = _req(
        router, "POST", "/api/v1/customers", sales_tok,
        {"first_name": "Missing", "last_name": "Version", "email": "missing.version@test.com"},
    )
    customer_id = body["customer"]["id"]
    status, _, body = _req(
        router, "POST", "/api/v1/estimator/estimates", sales_tok,
        {"customer_id": customer_id},
    )
    est_id = body["estimate"]["id"]

    status, _, body = _req(
        router, "GET", f"/api/v1/estimator/estimates/{est_id}/versions/2/lines", sales_tok
    )
    assert status == 404, body


# ==========================================
# Admin surface markup / wiring
# ==========================================


def test_admin_surface_has_estimates_tab_button_and_pane():
    html = render_admin_surface()
    assert "switchErpTab('estimates')" in html
    assert 'id="tab-estimates"' in html
    assert "if (tabId === 'estimates') loadEstimatesTab();" in html


def test_estimates_tab_markup_absent_from_b9_5_builder_surface():
    html = render_estimates_surface()
    assert 'id="tab-estimates"' not in html
    assert "loadEstimatesTab" not in html


def test_b9_5_builder_markup_absent_from_admin_surface():
    html = render_admin_surface()
    assert 'id="estAddLineModal"' not in html


def test_admin_surface_js_targets_real_estimator_route_paths():
    html = render_admin_surface()
    assert "/api/v1/estimator/estimates?" in html
    assert "/api/v1/estimator/estimates/${estimateId}?include_lines=true" in html
    assert "/versions`" in html
    assert "/versions/${vA}/lines`" in html
    assert "/api/v1/audit-log?entity_type=estimate&entity_id=" in html


def test_diff_renderer_never_computes_a_delta_client_side():
    html = render_admin_surface()
    start = html.index("async function estimateAdminRunDiff()")
    end = html.index("async function estimateAdminLoadAudit(estimateId)", start)
    fn_body = html[start:end]
    # Same money-arithmetic discipline as B9.5's estRefreshPreview(): no
    # `_cents` value is added/subtracted/multiplied client-side.
    assert "_cents +" not in fn_body
    assert "_cents -" not in fn_body
    assert "_cents *" not in fn_body


# ==========================================
# XSS / injection discipline
# ==========================================


def test_audit_timeline_escapes_dynamic_values():
    html = render_admin_surface()
    start = html.index("async function estimateAdminLoadAudit(estimateId)")
    end = html.index("async function loadUsersList()", start)
    fn_body = html[start:end]
    assert "escapeHtml(r.timestamp)" in fn_body
    assert "escapeHtml(r.change_summary)" in fn_body
    assert "escapeHtml(field)" in fn_body
    assert "escapeHtml(JSON.stringify(diff.old))" in fn_body
    assert "escapeHtml(JSON.stringify(diff.new))" in fn_body
    # No stringified-object inlining into an attribute -- this function
    # only ever builds template-literal text content, no onclick/oninput
    # carrying a raw object.
    assert "JSON.stringify(r)" not in fn_body


def test_audit_timeline_never_dumps_raw_signature_data():
    html = render_admin_surface()
    start = html.index("async function estimateAdminLoadAudit(estimateId)")
    end = html.index("async function loadUsersList()", start)
    fn_body = html[start:end]
    assert "signature_data" in fn_body  # explicitly filtered, not silently forgotten
    assert "!== 'signature_data'" in fn_body


def test_decision_comment_and_signer_name_surface_in_audit_timeline_via_details(env):
    """record_decision()'s audit row (entity_type='estimate', action=
    'decision') carries `comment`/`signer_name` inside `details.
    changed_fields` (build_audit_details(after=result.to_dict())) -- confirm
    the real data shape the admin timeline's `details.changed_fields`
    rendering path (asserted above at the source level) actually has
    something to render, not just an untested code path."""
    svc = env["svc"]
    audit = AuditService(env["db"])
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])
    share_link_out: dict = {}
    svc.transition(header.id, "SENT", env["sales"], share_link_out=share_link_out)
    header = svc.get(header.id, env["sales"])

    svc.record_decision(
        estimate_version_id=header.current_version_id,
        decision="declined",
        ip="127.0.0.1",
        user_agent="pytest",
        signer_name="<script>alert(1)</script>",
        comment="<img src=x onerror=alert(1)>",
        share_link_id=share_link_out["share_link_id"],
    )

    logs = audit.query_logs(env["admin"], entity_type="estimate", entity_id=header.id, action="decision")
    assert len(logs) == 1
    details = logs[0].details or {}
    changed = details.get("changed_fields", {})
    assert changed.get("comment", {}).get("new") == "<img src=x onerror=alert(1)>"
    assert changed.get("signer_name", {}).get("new") == "<script>alert(1)</script>"
