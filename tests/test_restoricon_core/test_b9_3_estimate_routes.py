"""
Route-level tests for B9.3 -- EstimateService API routes
(restoricon_core/api/routes.py, /api/v1/estimator/estimates/...).

These are plumbing tests confirming the routes correctly call the
already-unit-tested EstimateService methods (B9.2,
test_b9_2_estimate_service.py) and translate their results/exceptions
into the right HTTP status codes -- not a re-test of the service-layer
RBAC/workflow logic itself.

Deliberately namespaced under /api/v1/estimator/estimates/... rather than
/api/v1/estimates/... -- see the route block's own comment in routes.py
and NEW-718 in NEW_ISSUES.md for why (the legacy Estimate/CRMService
estimate routes at /api/v1/estimates/... are still live, not superseded
by this round).
"""

import json

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthService, ROLE_ADMIN, ROLE_CUSTOMER, ROLE_MANAGER, ROLE_PROJECT_MANAGER, ROLE_SALES, ROLE_TECHNICIAN,
)
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

    admin_u = auth.create_user("admin_est", "AdminPass123!", "Admin Est", "admin_est@test.com", ROLE_ADMIN)
    admin_tok = auth.create_token(admin_u)

    mgr_u = auth.create_user("mgr_est", "MgrPass123!", "Manager Est", "mgr_est@test.com", ROLE_MANAGER)
    mgr_tok = auth.create_token(mgr_u)

    sales_u = auth.create_user("sales_est", "SalesPass123!", "Sales Est", "sales_est@test.com", ROLE_SALES)
    sales_tok = auth.create_token(sales_u)

    sales2_u = auth.create_user("sales2_est", "SalesPass123!", "Sales Two Est", "sales2_est@test.com", ROLE_SALES)
    sales2_tok = auth.create_token(sales2_u)

    tech_u = auth.create_user("tech_est", "TechPass123!", "Tech Est", "tech_est@test.com", ROLE_TECHNICIAN)
    tech_tok = auth.create_token(tech_u)

    # PERM_READ_ESTIMATES but NOT PERM_WRITE_ESTIMATES/PERM_SEND_ESTIMATES/
    # PERM_REASSIGN_ESTIMATES (auth.py's ROLE_PROJECT_MANAGER block,
    # confirmed by reading it directly) -- used for the
    # permission-denied-on-a-real-estimate-it-can-view tests below.
    pm_u = auth.create_user("pm_est", "PmPass123!", "PM Est", "pm_est@test.com", ROLE_PROJECT_MANAGER)
    pm_tok = auth.create_token(pm_u)

    admin_ctx = auth.authenticate_token(admin_tok)
    cust = crm.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane_est@test.com"), admin_ctx
    )

    cust_u = auth.create_user(
        "cust_est", "CustPass123!", "Jane Doe", "jane_est@test.com", ROLE_CUSTOMER, customer_id=cust.id
    )
    cust_tok = auth.create_token(cust_u)

    return {
        "router": router,
        "admin_tok": admin_tok,
        "mgr_tok": mgr_tok,
        "sales_tok": sales_tok,
        "sales2_tok": sales2_tok,
        "tech_tok": tech_tok,
        "pm_tok": pm_tok,
        "cust_tok": cust_tok,
        "cust": cust,
    }


def _req(router: APIRouter, method: str, path: str, token: str, body: dict = None):
    headers = {"authorization": f"Bearer {token}"}
    body_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
    status, res_headers, res_json = router.handle_request(method, path, headers, body_bytes)
    # Real production behavior (server.py:131) json.dumps()'s the response
    # dict with NO custom encoder/default -- round-tripping through
    # json.dumps/json.loads here catches anything (e.g. a stray Decimal or
    # dataclass) that would have silently crashed the real HTTP handler,
    # not just whatever handle_request() happens to return in-process.
    if isinstance(res_json, dict):
        res_json = json.loads(json.dumps(res_json))
    return status, res_json


def _create_estimate(router, token, customer_id, **overrides):
    body = {"customer_id": customer_id, "title": "Kitchen remodel"}
    body.update(overrides)
    status, res = _req(router, "POST", "/api/v1/estimator/estimates", token, body)
    assert status == 201, res
    return res["estimate"]


def test_create_get_list_update_header(api_setup):
    router = api_setup["router"]
    sales_tok = api_setup["sales_tok"]
    cust = api_setup["cust"]

    est = _create_estimate(router, sales_tok, cust.id)
    assert est["estimate_number"].startswith("EST-")
    assert est["workflow_status"] == "DRAFT"
    est_id = est["id"]

    status, res = _req(router, "GET", f"/api/v1/estimator/estimates/{est_id}", sales_tok)
    assert status == 200, res
    assert res["estimate"]["id"] == est_id

    status, res = _req(router, "GET", "/api/v1/estimator/estimates/999999", sales_tok)
    assert status == 404, res

    status, res = _req(router, "GET", f"/api/v1/estimator/estimates?customer_id={cust.id}", sales_tok)
    assert status == 200, res
    assert any(e["id"] == est_id for e in res["estimates"])

    status, res = _req(
        router, "PATCH", f"/api/v1/estimator/estimates/{est_id}", sales_tok, {"title": "Kitchen remodel v2"}
    )
    assert status == 200, res
    assert res["estimate"]["title"] == "Kitchen remodel v2"


def test_create_requires_customer_id(api_setup):
    router = api_setup["router"]
    sales_tok = api_setup["sales_tok"]
    status, res = _req(router, "POST", "/api/v1/estimator/estimates", sales_tok, {"title": "No customer"})
    assert status == 400, res


def test_create_denied_for_customer_role(api_setup):
    router = api_setup["router"]
    cust_tok = api_setup["cust_tok"]
    cust = api_setup["cust"]
    status, res = _req(
        router, "POST", "/api/v1/estimator/estimates", cust_tok, {"customer_id": cust.id}
    )
    assert status == 403, res


def test_get_denied_when_actor_lacks_read_permission(api_setup):
    """Confirms a genuinely unrelated actor's PermissionError from
    EstimateService.get()'s ownership-narrowing surfaces as a 403, not a
    404 or a 500 -- ROLE_CUSTOMER lacks PERM_READ_ESTIMATES/
    PERM_READ_OWN_ESTIMATES scoped to a DIFFERENT customer_id here."""
    router = api_setup["router"]
    sales_tok = api_setup["sales_tok"]
    admin_tok = api_setup["admin_tok"]
    cust = api_setup["cust"]
    est = _create_estimate(router, sales_tok, cust.id)

    auth = router.auth
    admin_ctx = auth.authenticate_token(admin_tok)
    other_cust = router.crm.create_customer(
        Customer(first_name="Other", last_name="Cust", email="other_cust_row@test.com"), admin_ctx
    )
    other_cust_u = auth.create_user(
        "other_cust_est", "Pass123!", "Other Cust", "other_est@test.com", ROLE_CUSTOMER, customer_id=other_cust.id
    )
    other_tok = auth.create_token(other_cust_u)
    status, res = _req(router, "GET", f"/api/v1/estimator/estimates/{est['id']}", other_tok)
    assert status == 403, res


def test_line_add_update_delete_reorder(api_setup):
    router = api_setup["router"]
    sales_tok = api_setup["sales_tok"]
    cust = api_setup["cust"]
    est = _create_estimate(router, sales_tok, cust.id)
    est_id = est["id"]

    status, res = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/lines", sales_tok,
        {
            "line_type": "material", "description": "Drywall", "customer_description": "Drywall",
            "quantity": 10, "unit": "SF", "unit_cost_cents": 1000, "package_qty": 1,
        },
    )
    assert status == 201, res
    line = res["line"]
    line_id = line["id"]
    assert line["material_markup_bp"] == 3000  # DEFAULT_MATERIAL_MARKUP_BP, no key supplied

    status, res = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/lines", sales_tok,
        {
            "line_type": "material", "description": "Studs", "customer_description": "Studs",
            "quantity": 20, "unit": "EA", "unit_cost_cents": 500, "package_qty": 1,
        },
    )
    assert status == 201, res
    line2_id = res["line"]["id"]

    status, res = _req(
        router, "PATCH", f"/api/v1/estimator/estimates/{est_id}/lines/{line_id}", sales_tok,
        {"quantity": 15},
    )
    assert status == 200, res
    assert res["line"]["quantity"] == 15

    status, res = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/lines/reorder", sales_tok,
        {"ordered_line_ids": [line2_id, line_id]},
    )
    assert status == 200, res

    status, res = _req(
        router, "DELETE", f"/api/v1/estimator/estimates/{est_id}/lines/{line2_id}", sales_tok,
    )
    assert status == 200, res
    assert res == {"deleted": True}


def test_preview_and_revise(api_setup):
    router = api_setup["router"]
    mgr_tok = api_setup["mgr_tok"]
    cust = api_setup["cust"]
    est = _create_estimate(router, mgr_tok, cust.id)
    est_id = est["id"]

    _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/lines", mgr_tok,
        {
            "line_type": "material", "description": "Drywall", "customer_description": "Drywall",
            "quantity": 10, "unit": "SF", "unit_cost_cents": 1000, "package_qty": 1,
        },
    )

    status, res = _req(router, "GET", f"/api/v1/estimator/estimates/{est_id}/preview", mgr_tok)
    assert status == 200, res
    assert res["preview"]["total_cents"] > 0
    assert res["preview"]["lines"][0]["qty_with_waste"] == "10"  # Decimal -> str, round-tripped through real json.dumps

    status, res = _req(router, "POST", f"/api/v1/estimator/estimates/{est_id}/transition", mgr_tok, {"new_status": "SENT"})
    assert status == 200, res
    assert res["estimate"]["workflow_status"] == "SENT"

    status, res = _req(router, "POST", f"/api/v1/estimator/estimates/{est_id}/revise", mgr_tok)
    assert status == 200, res
    assert res["version"]["version_number"] == 2


def test_preview_denied_for_unrelated_actor_same_role(api_setup):
    """Code-review fix regression (Critical, live-reproduced): `preview()`
    originally gated ONLY on `PERM_WRITE_ESTIMATES`, with no
    `_can_view_estimate()` ownership narrowing and no
    `PERM_READ_ESTIMATE_COSTS` cost-field gate at all -- unlike `get()`,
    which correctly applies both. Exact mirror of the reviewer's live repro:
    create an estimate as one ROLE_SALES actor (sales_tok, assigned to
    themselves per create()'s default assignee), then hit BOTH
    `GET .../{id}` and `GET .../{id}/preview` as a DIFFERENT, unrelated
    ROLE_SALES actor (sales2_tok -- holds PERM_WRITE_ESTIMATES but not
    PERM_READ_ALL_ESTIMATES, and is neither the creator nor the assignee of
    this specific estimate) -- both must now deny with 403, not just `get()`.

    Before this fix, `get()` returned 403 here while `preview()` returned
    200 with the full cost/margin breakdown -- same estimate, same actor,
    same request pair. The 14 pre-existing tests in this file never
    exercised this because every `/preview` call used `mgr_tok`, who
    legitimately holds `PERM_READ_ALL_ESTIMATES`.
    """
    router = api_setup["router"]
    sales_tok = api_setup["sales_tok"]
    sales2_tok = api_setup["sales2_tok"]
    cust = api_setup["cust"]
    est = _create_estimate(router, sales_tok, cust.id)
    est_id = est["id"]
    assert est["assigned_to_user_id"] is not None  # confirms this is NOT the unclaimed/unassigned bucket

    _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/lines", sales_tok,
        {
            "line_type": "material", "description": "Drywall", "customer_description": "Drywall",
            "quantity": 10, "unit": "SF", "unit_cost_cents": 1000, "package_qty": 1,
        },
    )

    status, res = _req(router, "GET", f"/api/v1/estimator/estimates/{est_id}", sales2_tok)
    assert status == 403, res

    status, res = _req(router, "GET", f"/api/v1/estimator/estimates/{est_id}/preview", sales2_tok)
    assert status == 403, res
    assert "material_cost_cents" not in json.dumps(res)
    assert "gross_profit_cents" not in json.dumps(res)


def test_claim_unclaim_reassign(api_setup):
    router = api_setup["router"]
    sales_tok = api_setup["sales_tok"]
    sales2_tok = api_setup["sales2_tok"]
    mgr_tok = api_setup["mgr_tok"]
    cust = api_setup["cust"]
    est = _create_estimate(router, sales_tok, cust.id)
    est_id = est["id"]

    status, res = _req(router, "POST", f"/api/v1/estimator/estimates/{est_id}/unclaim", sales_tok)
    assert status == 200, res
    assert res["estimate"]["assigned_to_user_id"] is None

    status, res = _req(router, "POST", f"/api/v1/estimator/estimates/{est_id}/claim", sales2_tok)
    assert status == 200, res
    assert res["estimate"]["assigned_to_user_id"] is not None

    status, res = _req(router, "POST", f"/api/v1/estimator/estimates/{est_id}/claim", sales_tok)
    assert status == 409, res

    auth = router.auth
    mgr_ctx = auth.authenticate_token(mgr_tok)
    status, res = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/reassign", mgr_tok,
        {"assigned_to_user_id": mgr_ctx.user_id},
    )
    assert status == 200, res
    assert res["estimate"]["assigned_to_user_id"] == mgr_ctx.user_id


def test_transition_illegal_transition_maps_to_400(api_setup):
    router = api_setup["router"]
    mgr_tok = api_setup["mgr_tok"]
    cust = api_setup["cust"]
    est = _create_estimate(router, mgr_tok, cust.id)
    est_id = est["id"]

    # ACCEPTED is a system-driven target, not actor-driven -- transition()
    # raises ValueError, which must surface as 400 through the route, not
    # a raw 500.
    status, res = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/transition", mgr_tok, {"new_status": "ACCEPTED"}
    )
    assert status == 400, res


def test_send_requires_permission(api_setup):
    """ROLE_PROJECT_MANAGER holds PERM_READ_ESTIMATES (can view this
    unassigned-visible estimate, per _can_view_estimate()'s own bucket) but
    NOT PERM_SEND_ESTIMATES -- transition()'s PermissionError must surface
    as 403 through the route, not a 404/500."""
    router = api_setup["router"]
    sales_tok = api_setup["sales_tok"]
    pm_tok = api_setup["pm_tok"]
    cust = api_setup["cust"]
    est = _create_estimate(router, sales_tok, cust.id)
    est_id = est["id"]

    status, res = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/transition", pm_tok, {"new_status": "SENT"}
    )
    assert status == 403, res


def test_reassign_requires_permission(api_setup):
    """ROLE_PROJECT_MANAGER lacks PERM_REASSIGN_ESTIMATES."""
    router = api_setup["router"]
    sales_tok = api_setup["sales_tok"]
    pm_tok = api_setup["pm_tok"]
    cust = api_setup["cust"]
    est = _create_estimate(router, sales_tok, cust.id)
    est_id = est["id"]

    status, res = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/reassign", pm_tok,
        {"assigned_to_user_id": 1},
    )
    assert status == 403, res


def test_decisions_route_requires_write_estimates_permission(api_setup):
    """record_decision() itself performs NO permission check (it's
    actor-less by design, serving the future public share-link viewer) --
    this route's OWN explicit PERM_WRITE_ESTIMATES gate is the only thing
    stopping an unrelated authenticated actor (here: ROLE_TECHNICIAN, which
    does not hold PERM_WRITE_ESTIMATES) from recording an arbitrary
    decision. Regression test for the gate the route adds on top of the
    service layer -- NOT a duplicate of a check the service already makes,
    since no such check exists there."""
    router = api_setup["router"]
    sales_tok = api_setup["sales_tok"]
    tech_tok = api_setup["tech_tok"]
    cust = api_setup["cust"]
    est = _create_estimate(router, sales_tok, cust.id)
    est_id = est["id"]

    status, res = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/decisions", tech_tok,
        {"decision": "accepted", "signer_name": "Jane Doe", "customer_user_id": 1},
    )
    assert status == 403, res


def test_decisions_route_records_accept_and_creates_contract(api_setup):
    router = api_setup["router"]
    mgr_tok = api_setup["mgr_tok"]
    cust = api_setup["cust"]
    est = _create_estimate(router, mgr_tok, cust.id)
    est_id = est["id"]
    auth = router.auth
    mgr_ctx = auth.authenticate_token(mgr_tok)

    status, res = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/decisions", mgr_tok,
        {"decision": "accepted", "signer_name": "Jane Doe", "customer_user_id": mgr_ctx.user_id},
    )
    assert status == 201, res
    assert res["decision"]["decision"] == "accepted"

    status, res = _req(router, "GET", f"/api/v1/estimator/estimates/{est_id}", mgr_tok)
    assert status == 200, res
    assert res["estimate"]["workflow_status"] == "ACCEPTED"
    assert res["estimate"]["contract_id"] is not None


def test_decisions_route_missing_current_version_or_not_found(api_setup):
    router = api_setup["router"]
    mgr_tok = api_setup["mgr_tok"]
    status, res = _req(
        router, "POST", "/api/v1/estimator/estimates/999999/decisions", mgr_tok,
        {"decision": "accepted", "signer_name": "X", "customer_user_id": 1},
    )
    assert status == 404, res


def test_decisions_route_contract_number_collision_maps_to_400_not_500(api_setup):
    """NEW-711 regression, route level: a pre-existing contracts row with
    the deterministic CON-{estimate_number} contract_number (reachable
    today via the legacy /api/v1/contracts POST route's
    Contract(**json_body), which lets any PERM_WRITE_CONTRACTS holder set
    an arbitrary contract_number) must not turn a legitimate accept
    decision into a raw 500 -- and the whole transaction (decision row,
    workflow_status, version lock) must still roll back atomically."""
    router = api_setup["router"]
    mgr_tok = api_setup["mgr_tok"]
    cust = api_setup["cust"]
    est = _create_estimate(router, mgr_tok, cust.id)
    est_id = est["id"]
    auth = router.auth
    mgr_ctx = auth.authenticate_token(mgr_tok)

    contract_number = f"CON-{est['estimate_number']}"
    status, res = _req(
        router, "POST", "/api/v1/contracts", mgr_tok,
        {
            "contract_number": contract_number, "customer_id": cust.id,
            "title": "Pre-existing collider", "content": "x", "status": "draft",
        },
    )
    assert status == 201, res

    status, res = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/decisions", mgr_tok,
        {"decision": "accepted", "signer_name": "Jane Doe", "customer_user_id": mgr_ctx.user_id},
    )
    assert status == 400, res

    status, res = _req(router, "GET", f"/api/v1/estimator/estimates/{est_id}", mgr_tok)
    assert status == 200, res
    assert res["estimate"]["workflow_status"] == "DRAFT"  # rolled back, not ACCEPTED
    assert res["estimate"]["contract_id"] is None
