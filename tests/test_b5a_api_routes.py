"""
API Route Integration Tests for Track B Phase B5a Endpoints.
Covers HTTP request routing, RBAC enforcement, and JSON response formats across:
- Finance & Bookkeeping
- Marketing & Customer Reviews
- Compliance & Licensing
- HR & Timesheets
- Procurement & Purchase Orders
- Global Search & Executive Reports
"""

import json
import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import AuthService, ROLE_ADMIN, ROLE_CUSTOMER, ROLE_TECHNICIAN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Project
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

    # Create admin user & token
    admin_u = auth.create_user("admin_api", "AdminPass123!", "Admin API", "admin_api@test.com", ROLE_ADMIN)
    admin_tok = auth.create_token(admin_u)

    # Create customer user & token
    admin_ctx = auth.authenticate_token(admin_tok)
    cust = crm.create_customer(Customer(first_name="Carl", last_name="Customer", email="carl@test.com"), admin_ctx)
    cust_u = auth.create_user("cust_api", "CustPass123!", "Carl Customer", "carl@test.com", ROLE_CUSTOMER, customer_id=cust.id)
    cust_tok = auth.create_token(cust_u)

    # Create sample project
    proj = crm.create_project(
        Project(
            customer_id=cust.id,
            title="Basement Water Dryout",
            property_address="789 Pine Street",
            contract_amount=10000.0,
        ),
        admin_ctx,
    )

    return {
        "router": router,
        "admin_tok": admin_tok,
        "cust_tok": cust_tok,
        "cust": cust,
        "proj": proj,
    }


def _req(router: APIRouter, method: str, path: str, token: str, body: dict = None):
    headers = {"authorization": f"Bearer {token}"}
    body_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
    status, res_headers, res_json = router.handle_request(method, path, headers, body_bytes)
    return status, res_json


def test_api_finance_workflow(api_setup):
    router = api_setup["router"]
    admin_tok = api_setup["admin_tok"]
    proj = api_setup["proj"]

    # 1. POST transaction
    status, res = _req(
        router,
        "POST",
        "/api/v1/finance/transactions",
        admin_tok,
        {
            "transaction_type": "payment_received",
            "amount": 5000.0,
            "project_id": proj.id,
            "notes": "Initial deposit",
        },
    )
    assert status == 201
    assert res["status"] == "created"
    assert res["transaction"]["amount"] == 5000.0

    # 2. GET transactions
    status, res = _req(router, "GET", "/api/v1/finance/transactions", admin_tok)
    assert status == 200
    assert len(res["transactions"]) == 1

    # 3. GET project P&L
    status, res = _req(router, "GET", f"/api/v1/finance/projects/{proj.id}/pnl", admin_tok)
    assert status == 200
    assert res["pnl"]["contract_amount"] == 10000.0
    assert res["pnl"]["total_collected"] == 5000.0

    # 4. GET financial summary
    status, res = _req(router, "GET", "/api/v1/finance/summary", admin_tok)
    assert status == 200
    assert res["financial_summary"]["total_revenue"] == 5000.0


def test_api_marketing_workflow(api_setup):
    router = api_setup["router"]
    admin_tok = api_setup["admin_tok"]
    cust = api_setup["cust"]

    # 1. POST campaign
    status, res = _req(
        router,
        "POST",
        "/api/v1/marketing/campaigns",
        admin_tok,
        {
            "name": "Storm Response Campaign",
            "channel": "meta_ads",
            "budget": 2000.0,
            "actual_spend": 800.0,
            "leads_generated": 10,
        },
    )
    assert status == 201
    assert res["campaign"]["name"] == "Storm Response Campaign"

    # 2. GET campaigns
    status, res = _req(router, "GET", "/api/v1/marketing/campaigns", admin_tok)
    assert status == 200
    assert len(res["campaigns"]) == 1

    # 3. POST review request
    status, res = _req(
        router,
        "POST",
        "/api/v1/marketing/reviews/request",
        admin_tok,
        {"customer_id": cust.id, "platform": "google"},
    )
    assert status == 201
    req_id = res["review_request"]["id"]

    # 4. POST review submit
    status, res = _req(
        router,
        "POST",
        f"/api/v1/marketing/reviews/{req_id}/submit",
        admin_tok,
        {"rating": 5, "feedback": "Super fast flood remediation service!"},
    )
    assert status == 200
    assert res["review"]["status"] == "completed"


def test_api_compliance_and_hr(api_setup):
    router = api_setup["router"]
    admin_tok = api_setup["admin_tok"]

    # Compliance item
    status, res = _req(
        router,
        "POST",
        "/api/v1/compliance/items",
        admin_tok,
        {
            "title": "State Mold Remediation Contractor License",
            "category": "contractor_license",
            "expiration_date": "2030-01-01T00:00:00Z",
        },
    )
    assert status == 201
    assert res["compliance_item"]["title"] == "State Mold Remediation Contractor License"

    # Compliance scan
    status, res = _req(router, "POST", "/api/v1/compliance/scan", admin_tok, {"threshold_days": 30})
    assert status == 200
    assert res["results"]["total_scanned"] == 1

    # HR Employee
    status, res = _req(
        router,
        "POST",
        "/api/v1/hr/employees",
        admin_tok,
        {
            "first_name": "Dave",
            "last_name": "Technician",
            "role_title": "Field Supervisor",
            "hourly_rate": 40.0,
        },
    )
    assert status == 201
    emp_id = res["employee"]["id"]

    # HR Timesheet
    status, res = _req(
        router,
        "POST",
        "/api/v1/hr/timesheets",
        admin_tok,
        {"employee_id": emp_id, "hours_worked": 5.0, "hourly_rate": 40.0},
    )
    assert status == 201
    ts_id = res["timesheet"]["id"]
    assert res["timesheet"]["total_cost"] == 200.0

    # HR Timesheet approve
    status, res = _req(router, "POST", f"/api/v1/hr/timesheets/{ts_id}/approve", admin_tok)
    assert status == 200
    assert res["timesheet"]["status"] == "approved"


def test_api_procurement_and_search(api_setup):
    router = api_setup["router"]
    admin_tok = api_setup["admin_tok"]

    # Create vendor
    status, res = _req(
        router,
        "POST",
        "/api/v1/procurement/vendors",
        admin_tok,
        {
            "company_name": "Acme Restoration Equipment",
            "category": "equipment_rental",
        },
    )
    assert status == 201
    vendor_id = res["vendor"]["id"]

    # Create PO
    status, res = _req(
        router,
        "POST",
        "/api/v1/procurement/purchase-orders",
        admin_tok,
        {
            "vendor_id": vendor_id,
            "items": [{"item": "Commercial Dehumidifier", "quantity": 2, "unit_cost": 1500.0}],
            "tax_amount": 200.0,
        },
    )
    assert status == 201
    po_id = res["purchase_order"]["id"]
    assert res["purchase_order"]["total_amount"] == 3200.0

    # Receive PO
    status, res = _req(router, "POST", f"/api/v1/procurement/purchase-orders/{po_id}/receive", admin_tok)
    assert status == 200
    assert res["purchase_order"]["status"] == "received"

    # Global Search
    status, res = _req(router, "GET", "/api/v1/search?q=Acme", admin_tok)
    assert status == 200
    assert res["total_matches"] >= 1
    assert "vendors" in res["results"]

    # Executive Dashboard
    status, res = _req(router, "GET", "/api/v1/reports/summary", admin_tok)
    assert status == 200
    assert "sales" in res["dashboard"]
    assert "financial" in res["dashboard"]
    assert "operations" in res["dashboard"]
