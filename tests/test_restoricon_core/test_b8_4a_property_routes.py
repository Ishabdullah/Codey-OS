"""
Route-level tests for B8.4a's new Property API routes
(restoricon_core/api/routes.py): GET /api/v1/properties,
GET /api/v1/properties/<id>, POST /api/v1/properties,
POST /api/v1/properties/<id>/update.

These are plumbing tests confirming the routes correctly call the
already-unit-tested CRMService.{create,get,list,update}_property methods
(B8.1, test_b8_1_properties_and_commissions.py) and translate their
results/exceptions into the right HTTP status codes -- not a re-test of
the service-layer permission logic itself.
"""

import json

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import AuthService, ROLE_ADMIN, ROLE_CUSTOMER
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer
from restoricon_core.services.analytics_search_service import AnalyticsSearchService
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.business_ops_service import BusinessOpsService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
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
    )

    admin_u = auth.create_user("admin_prop", "AdminPass123!", "Admin Prop", "admin_prop@test.com", ROLE_ADMIN)
    admin_tok = auth.create_token(admin_u)
    admin_ctx = auth.authenticate_token(admin_tok)

    cust = crm.create_customer(
        Customer(first_name="Pat", last_name="Prop", email="pat_prop@test.com"), admin_ctx
    )

    cust_u = auth.create_user(
        "cust_prop", "CustPass123!", "Pat Prop", "pat_prop@test.com", ROLE_CUSTOMER, customer_id=cust.id
    )
    cust_tok = auth.create_token(cust_u)

    return {
        "router": router,
        "admin_tok": admin_tok,
        "cust_tok": cust_tok,
        "cust": cust,
    }


def _req(router: APIRouter, method: str, path: str, token: str, body: dict = None):
    headers = {"authorization": f"Bearer {token}"}
    body_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
    status, res_headers, res_json = router.handle_request(method, path, headers, body_bytes)
    return status, res_json


def test_create_list_get_update_property(api_setup):
    router = api_setup["router"]
    admin_tok = api_setup["admin_tok"]
    cust = api_setup["cust"]

    # Create
    status, res = _req(
        router,
        "POST",
        "/api/v1/properties",
        admin_tok,
        {
            "customer_id": cust.id,
            "address": "456 Oak Ave",
            "property_type": "single_family",
            "year_built": 2001,
            "existing_systems": {"hvac": "heat_pump"},
        },
    )
    assert status == 201, res
    prop = res["property"]
    assert prop["id"] is not None
    assert prop["address"] == "456 Oak Ave"
    assert prop["existing_systems"] == {"hvac": "heat_pump"}
    prop_id = prop["id"]

    # List filtered by customer_id
    status, res = _req(router, "GET", f"/api/v1/properties?customer_id={cust.id}", admin_tok)
    assert status == 200, res
    assert len(res["properties"]) == 1
    assert res["properties"][0]["id"] == prop_id

    # Get by id
    status, res = _req(router, "GET", f"/api/v1/properties/{prop_id}", admin_tok)
    assert status == 200, res
    assert res["property"]["address"] == "456 Oak Ave"

    # Get non-existent id -> 404
    status, res = _req(router, "GET", "/api/v1/properties/999999", admin_tok)
    assert status == 404, res

    # Update
    status, res = _req(
        router,
        "POST",
        f"/api/v1/properties/{prop_id}/update",
        admin_tok,
        {"roof_type": "metal"},
    )
    assert status == 200, res
    assert res["property"]["roof_type"] == "metal"

    # Update non-existent id -> 404
    status, res = _req(
        router, "POST", "/api/v1/properties/999999/update", admin_tok, {"roof_type": "metal"}
    )
    assert status == 404, res


def test_property_routes_permission_denied_for_customer_role(api_setup):
    router = api_setup["router"]
    cust_tok = api_setup["cust_tok"]
    cust = api_setup["cust"]

    # ROLE_CUSTOMER lacks PERM_WRITE_CUSTOMERS/PERM_READ_ALL_CUSTOMERS (same
    # gate B8.1's service tests already cover) -- confirming the route
    # correctly surfaces the service's PermissionError as a 403.
    status, res = _req(
        router,
        "POST",
        "/api/v1/properties",
        cust_tok,
        {"customer_id": cust.id, "address": "789 Elm St"},
    )
    assert status == 403, res

    status, res = _req(router, "GET", "/api/v1/properties", cust_tok)
    assert status == 403, res
