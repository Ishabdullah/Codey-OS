"""
Phase B4 Test Suite — Staff/Admin Surface, Customer Portal SPAs & Device Limb API Integration.
"""

import json
import pytest
from typing import Dict, Any

from restoricon_core.auth import (
    AuthService,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    Customer,
    Project,
    Contract,
    FinancialTransaction,
    Appointment,
)
from restoricon_core.services.analytics_search_service import AnalyticsSearchService
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.business_ops_service import BusinessOpsService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.finance_service import FinanceService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService
from restoricon_core.api.routes import APIRouter


@pytest.fixture
def b4_env(tmp_path):
    db_path = str(tmp_path / "test_b4.db")
    db = DatabaseManager(db_path)
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

    # Setup Admin user
    admin_u = auth.create_user("admin_user", "AdminSecret123!", "Admin Manager", "admin@restoricon.com", ROLE_ADMIN)
    admin_token = auth.create_token(admin_u)

    # Setup Customer 1
    admin_ctx = auth.authenticate_token(admin_token)
    cust1 = crm.create_customer(Customer(first_name="Bob", last_name="Customer", email="bob@customer.com", phone="+15551234567"), admin_ctx)
    cust1_u = auth.create_user("bob_cust", "BobPassword123!", "Bob Customer", "bob@customer.com", ROLE_CUSTOMER, customer_id=cust1.id)
    cust1_token = auth.create_token(cust1_u)

    # Setup Customer 2 (for boundary testing)
    cust2 = crm.create_customer(Customer(first_name="Alice", last_name="Other", email="alice@other.com", phone="+15559876543"), admin_ctx)
    cust2_u = auth.create_user("alice_cust", "AlicePassword123!", "Alice Other", "alice@other.com", ROLE_CUSTOMER, customer_id=cust2.id)
    cust2_token = auth.create_token(cust2_u)

    # Create project & contract for Customer 1
    proj1 = crm.create_project(Project(title="Water Remediation 101", customer_id=cust1.id, contract_amount=15000.0, estimated_cost=8000.0), admin_ctx)
    contr1 = crm.create_contract(Contract(project_id=proj1.id, customer_id=cust1.id, title="Water Mitigation Scope", contract_number="CNT-101", status="draft"), admin_ctx)

    # Create finance transaction
    fin.record_transaction(FinancialTransaction(amount=5000.0, transaction_type="payment_received", category="deposit", customer_id=cust1.id, project_id=proj1.id), admin_ctx)

    return {
        "db": db,
        "router": router,
        "admin_token": admin_token,
        "cust1_token": cust1_token,
        "cust2_token": cust2_token,
        "cust1": cust1,
        "cust2": cust2,
        "proj1": proj1,
        "contr1": contr1,
    }


def test_web_surfaces_html_rendering(b4_env):
    router = b4_env["router"]

    # Test Admin Dashboard Surface
    status, headers, body = router.handle_request("GET", "/admin", {}, b"")
    assert status == 200
    assert "text/html" in headers.get("Content-Type", "")
    assert "Restoricon ERP" in body
    assert "Active Restoration Job Sites" in body

    # Test Admin Login Surface
    status, headers, body = router.handle_request("GET", "/admin/login", {}, b"")
    assert status == 200
    assert "text/html" in headers.get("Content-Type", "")
    assert "Staff & Admin Portal" in body

    # Test Customer Portal Surface
    status, headers, body = router.handle_request("GET", "/portal", {}, b"")
    assert status == 200
    assert "text/html" in headers.get("Content-Type", "")
    assert "Your Restoration Portal" in body

    # Test Customer Portal Login Surface
    status, headers, body = router.handle_request("GET", "/portal/login", {}, b"")
    assert status == 200
    assert "text/html" in headers.get("Content-Type", "")
    assert "Customer Portal" in body


def test_customer_portal_isolation_and_masking(b4_env):
    router = b4_env["router"]
    cust1_token = b4_env["cust1_token"]
    cust2_token = b4_env["cust2_token"]
    proj1 = b4_env["proj1"]
    contr1 = b4_env["contr1"]

    # Customer 1 lists projects -> sees proj1 with masked estimated_cost
    headers1 = {"authorization": f"Bearer {cust1_token}"}
    status, _, data = router.handle_request("GET", "/api/v1/portal/projects", headers1, b"")
    assert status == 200
    projects = data.get("projects", [])
    assert len(projects) == 1
    assert projects[0]["id"] == proj1.id
    assert projects[0]["contract_amount"] == 15000.0
    # Internal cost must be masked (0.0 or None)
    assert projects[0].get("estimated_cost") in (0.0, None)

    # Customer 2 lists projects -> sees 0 projects (Customer Isolation)
    headers2 = {"authorization": f"Bearer {cust2_token}"}
    status2, _, data2 = router.handle_request("GET", "/api/v1/portal/projects", headers2, b"")
    assert status2 == 200
    assert len(data2.get("projects", [])) == 0

    # Customer 1 views contracts -> sees contr1
    status, _, data = router.handle_request("GET", "/api/v1/portal/contracts", headers1, b"")
    assert status == 200
    contracts = data.get("contracts", [])
    assert len(contracts) == 1
    assert contracts[0]["id"] == contr1.id

    # Customer 1 signs contract
    sign_payload = json.dumps({"signature_data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."}).encode("utf-8")
    status, _, sign_res = router.handle_request("POST", f"/api/v1/portal/contracts/{contr1.id}/sign", headers1, sign_payload)
    assert status == 200
    assert sign_res.get("contract", {}).get("status") == "signed"

    # Customer 2 attempts to sign Customer 1's contract -> Permission Denied
    status, _, err_res = router.handle_request("POST", f"/api/v1/portal/contracts/{contr1.id}/sign", headers2, sign_payload)
    assert status in (403, 404)


def test_device_limb_executive_report_and_summary(b4_env):
    router = b4_env["router"]
    admin_token = b4_env["admin_token"]
    headers = {"authorization": f"Bearer {admin_token}"}

    # Test Executive Report endpoint used by RestoriconApiClient
    status, _, report = router.handle_request("GET", "/api/v1/reports/executive", headers, b"")
    assert status == 200
    assert "sales" in report
    assert "operations" in report
    assert "financial" in report
    assert report["operations"]["total_projects"] >= 1
    assert report["financial"]["total_revenue"] == 5000.0

    # Test Financial Summary endpoint used by RestoriconApiClient
    status, _, fin_summary = router.handle_request("GET", "/api/v1/finance/summary", headers, b"")
    assert status == 200
    assert fin_summary["total_revenue"] == 5000.0
    assert "net_profit" in fin_summary
