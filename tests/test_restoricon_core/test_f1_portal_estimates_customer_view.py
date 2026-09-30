"""
Tests for F1 (`codey_estimator_service.md` §3, `CODEY_MASTER_PLAN.md`
"F1 fix" note): `GET /api/v1/portal/estimates` must serialize every
returned estimate through `EstimateService.to_customer_view()` -- the
same `CustomerEstimateView` allow-list the public share-link route
(B9.4) uses -- never the raw legacy `Estimate.to_dict()`.

Fixture style matches test_b9_4_public_share_link.py's `api_setup`: a
full in-process `APIRouter`, no live HTTP, no proxy/socket-bind
exposure (this repo's known sandbox-proxy trap).
"""

import json

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import AuthContext, AuthService, ROLE_CUSTOMER, ROLE_MANAGER
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


def _req(router, method, path, token=None, body=None):
    headers = {"authorization": f"Bearer {token}"} if token else {}
    body_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
    return router.handle_request(method, path, headers, body_bytes)


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
    estimates = EstimateService(db, audit)  # no notification_service: no live HTTP in route tests

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

    mgr_u = auth.create_user("mgr_f1", "MgrPass123!", "Manager F1", "mgr_f1@test.com", ROLE_MANAGER)
    mgr_tok = auth.create_token(mgr_u)
    mgr_ctx = AuthContext(mgr_u.id, mgr_u.username, ROLE_MANAGER, "human")

    cust = crm.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane_f1@test.com"), mgr_ctx
    )
    cust_user = auth.create_user(
        "jane_f1", "JanePass123!", "Jane Doe", "jane_f1@test.com", role=ROLE_CUSTOMER, customer_id=cust.id,
    )
    cust_tok = auth.create_token(cust_user)

    other_cust = crm.create_customer(
        Customer(first_name="Bob", last_name="Other", email="bob_f1@test.com"), mgr_ctx
    )
    other_user = auth.create_user(
        "bob_f1", "BobPass123!", "Bob Other", "bob_f1@test.com", role=ROLE_CUSTOMER, customer_id=other_cust.id,
    )
    other_tok = auth.create_token(other_user)

    return {
        "router": router, "estimates": estimates, "crm": crm, "db": db,
        "mgr_tok": mgr_tok, "mgr_ctx": mgr_ctx,
        "cust": cust, "cust_tok": cust_tok,
        "other_cust": other_cust, "other_tok": other_tok,
    }


def _create_and_send(router, mgr_tok, cust_id):
    status, _, res = _req(
        router, "POST", "/api/v1/estimator/estimates", mgr_tok,
        {"customer_id": cust_id, "title": "Kitchen remodel"},
    )
    assert status == 201, res
    est_id = res["estimate"]["id"]
    status, _, res = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/lines", mgr_tok,
        {
            "line_type": "material", "description": "Drywall", "customer_description": "Drywall sheets",
            "quantity": 10, "unit": "SF", "unit_cost_cents": 1000, "package_qty": 1,
        },
    )
    assert status == 201, res
    status, _, res = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/transition", mgr_tok, {"new_status": "SENT"}
    )
    assert status == 200, res
    return est_id


def _walk(obj):
    """Yield every scalar leaf value and every key in a nested JSON-shaped
    structure -- used so a leak check covers nested trees, not just the
    top level (B9.3's real Critical was a raw-cost echo buried in a
    nested `LineResult.input` tree that a naive top-level-only gate
    missed entirely -- see codey_estimator_service.md/PROJECT_LOG.md)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield ("key", k)
            yield from _walk(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk(item)
    else:
        yield ("value", obj)


def test_portal_estimates_returns_customer_view_shape_no_cost_fields(api_setup):
    router = api_setup["router"]
    _create_and_send(router, api_setup["mgr_tok"], api_setup["cust"].id)

    status, _, res = _req(router, "GET", "/api/v1/portal/estimates", api_setup["cust_tok"])
    assert status == 200, res
    assert len(res["estimates"]) == 1
    view = res["estimates"][0]

    # Cost/margin fields must never reach the customer, even indirectly.
    for leaked_field in (
        "cost_total_cents", "gross_profit_cents", "gross_margin_bp",
        "material_cost_cents", "labor_cost_cents", "equipment_cost_cents",
        "sub_cost_cents", "materials_cost", "labor_cost", "subcontractor_cost",
        "markup_percent",
    ):
        assert leaked_field not in view, f"{leaked_field} leaked in {view!r}"

    # Sell-side/customer-relevant fields must still be present.
    assert "total_cents" in view
    assert view["total_cents"] is not None

    # Recursive check over the whole serialized tree, not just the top
    # level or one level of `lines` -- this line's real material cost
    # (10 * 1000 = 10000 cents) must not appear anywhere as a value, and
    # no cost/margin/markup-shaped key must appear anywhere, at any depth.
    leaked_cost_value = 10 * 1000
    cost_key_fragments = ("cost", "margin", "markup", "profit")
    for kind, item in _walk(view):
        if kind == "value":
            assert item != leaked_cost_value, f"raw cost value leaked at some depth in {view!r}"
        else:
            lowered = str(item).lower()
            assert not any(frag in lowered for frag in cost_key_fragments), (
                f"cost-shaped key {item!r} leaked at some depth in {view!r}"
            )


def test_portal_estimates_line_items_visible_without_line_costs(api_setup):
    router = api_setup["router"]
    _create_and_send(router, api_setup["mgr_tok"], api_setup["cust"].id)

    status, _, res = _req(router, "GET", "/api/v1/portal/estimates", api_setup["cust_tok"])
    assert status == 200, res
    view = res["estimates"][0]
    assert "lines" in view
    assert len(view["lines"]) == 1
    line = view["lines"][0]
    # customer_description ("Drywall sheets") is what the customer sees --
    # never the internal description ("Drywall").
    assert line.get("description") == "Drywall sheets"
    assert line.get("unit") == "SF"
    assert "price_cents" in line
    for leaked_field in (
        "unit_cost_cents", "line_cost_cents", "override_reason", "material_cost_cents",
    ):
        assert leaked_field not in line, f"{leaked_field} leaked in line {line!r}"


def test_portal_estimates_ownership_enforced_across_customers(api_setup):
    router = api_setup["router"]
    _create_and_send(router, api_setup["mgr_tok"], api_setup["cust"].id)

    status, _, res = _req(router, "GET", "/api/v1/portal/estimates", api_setup["other_tok"])
    assert status == 200, res
    assert res["estimates"] == []


def test_portal_estimates_omits_legacy_estimate_with_no_current_version(api_setup):
    """A legacy-CRM-created estimate (NEW-718, still open) has no
    current_version_id and therefore nothing computed to project through
    to_customer_view() -- it must be omitted, not 500 the whole request."""
    from restoricon_core.models import Estimate

    router = api_setup["router"]
    crm = api_setup["crm"]
    mgr_ctx = api_setup["mgr_ctx"]
    crm.create_estimate(Estimate(customer_id=api_setup["cust"].id, estimate_number="EST-LEGACY-1"), mgr_ctx)

    _create_and_send(router, api_setup["mgr_tok"], api_setup["cust"].id)

    status, _, res = _req(router, "GET", "/api/v1/portal/estimates", api_setup["cust_tok"])
    assert status == 200, res
    assert len(res["estimates"]) == 1


def test_portal_estimates_project_id_filter_still_applied(api_setup):
    router = api_setup["router"]
    est_id = _create_and_send(router, api_setup["mgr_tok"], api_setup["cust"].id)

    status, _, res = _req(
        router, "GET", "/api/v1/portal/estimates?project_id=999999", api_setup["cust_tok"]
    )
    assert status == 200, res
    assert res["estimates"] == []


def test_portal_estimates_calls_the_same_serializer_as_public_share_link(api_setup):
    """codey_estimator_service.md:983: `/api/v1/portal/estimates` "must be
    proven, by test, to call the **same** `to_customer_view()`" the public
    share-link route (B9.4) uses -- not a second, independently-written
    serializer that could silently drift from it."""
    router = api_setup["router"]

    status, _, send_res = _req(
        router, "POST", "/api/v1/estimator/estimates", api_setup["mgr_tok"],
        {"customer_id": api_setup["cust"].id, "title": "Kitchen remodel"},
    )
    assert status == 201, send_res
    est_id = send_res["estimate"]["id"]
    _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/lines", api_setup["mgr_tok"],
        {
            "line_type": "material", "description": "Drywall", "customer_description": "Drywall sheets",
            "quantity": 10, "unit": "SF", "unit_cost_cents": 1000, "package_qty": 1,
        },
    )
    status, _, transition_res = _req(
        router, "POST", f"/api/v1/estimator/estimates/{est_id}/transition", api_setup["mgr_tok"],
        {"new_status": "SENT"},
    )
    assert status == 200, transition_res
    raw_token = transition_res["share_link"]["raw_token"]

    status, _, share_res = _req(router, "GET", f"/api/v1/public/estimate/{raw_token}")
    assert status == 200, share_res

    status, _, portal_res = _req(router, "GET", "/api/v1/portal/estimates", api_setup["cust_tok"])
    assert status == 200, portal_res
    assert len(portal_res["estimates"]) == 1

    assert portal_res["estimates"][0] == share_res
