"""
Unit and integration tests for Business Operations Domain Engine (Track B Phase B5a).
Covers Marketing, Compliance, HR & Timesheets, and Procurement.
"""

from datetime import datetime, timezone, timedelta
import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    ComplianceItem,
    Customer,
    Employee,
    MarketingCampaign,
    PurchaseOrder,
    ReviewRequest,
    Timesheet,
    User,
    Vendor,
)
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.business_ops_service import BusinessOpsService
from restoricon_core.services.crm_service import CRMService


@pytest.fixture
def ops_setup():
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    auth = AuthService(db)
    crm = CRMService(db, audit)
    ops = BusinessOpsService(db, audit)

    admin_user = auth.create_user("admin_ops", "AdminPass123!", "Admin Ops", "admin_ops@test.com", ROLE_ADMIN)
    admin_ctx = AuthContext(user_id=admin_user.id, username=admin_user.username, role=ROLE_ADMIN, actor_type="human")

    tech_user = auth.create_user("tech_ops", "TechPass123!", "Tech Ops", "tech_ops@test.com", ROLE_TECHNICIAN)
    tech_ctx = AuthContext(user_id=tech_user.id, username=tech_user.username, role=ROLE_TECHNICIAN, actor_type="human")

    cust = crm.create_customer(Customer(first_name="Bob", last_name="OpsTest", email="bob@opstest.com"), admin_ctx)
    cust_user = auth.create_user("cust_ops", "CustPass123!", "Bob OpsTest", "bob@opstest.com", ROLE_CUSTOMER, customer_id=cust.id)
    cust_ctx = AuthContext(user_id=cust_user.id, username=cust_user.username, role=ROLE_CUSTOMER, customer_id=cust.id, actor_type="human")

    return {
        "db": db,
        "audit": audit,
        "auth": auth,
        "crm": crm,
        "ops": ops,
        "admin_ctx": admin_ctx,
        "tech_ctx": tech_ctx,
        "cust_ctx": cust_ctx,
        "cust": cust,
    }


def test_marketing_campaign_lifecycle(ops_setup):
    ops = ops_setup["ops"]
    admin_ctx = ops_setup["admin_ctx"]

    # Create campaign
    camp = ops.create_campaign(
        MarketingCampaign(
            name="Spring Water Damage Awareness",
            channel="google_ads",
            budget=3000.0,
            actual_spend=1200.0,
            leads_generated=15,
            revenue_attributed=18000.0,
            status="active",
        ),
        admin_ctx,
    )
    assert camp.id is not None
    assert camp.name == "Spring Water Damage Awareness"

    # List campaigns
    camps = ops.list_campaigns(admin_ctx)
    assert len(camps) == 1
    assert camps[0].channel == "google_ads"


def test_review_request_and_submission(ops_setup):
    ops = ops_setup["ops"]
    admin_ctx = ops_setup["admin_ctx"]
    cust = ops_setup["cust"]

    # Dispatch review request
    req = ops.create_review_request(
        ReviewRequest(
            customer_id=cust.id,
            platform="google",
        ),
        admin_ctx,
    )
    assert req.id is not None
    assert req.status == "sent"

    # Submit review
    completed_review = ops.submit_review(
        request_id=req.id,
        rating=5,
        feedback="Outstanding 24/7 emergency water extraction service!",
    )
    assert completed_review.status == "completed"
    assert completed_review.rating == 5
    assert "water extraction" in completed_review.feedback


def test_compliance_expiration_scanner(ops_setup):
    ops = ops_setup["ops"]
    admin_ctx = ops_setup["admin_ctx"]

    # 1. Active item (expiring next year)
    ops.create_compliance_item(
        ComplianceItem(
            title="IICRC Master Water Restorer",
            category="iicrc_cert",
            expiration_date="2099-01-01T00:00:00Z",
        ),
        admin_ctx,
    )

    # 2. Expiring soon item (expiring in 10 days)
    soon_date = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    ops.create_compliance_item(
        ComplianceItem(
            title="General Liability Insurance",
            category="general_liability",
            expiration_date=soon_date,
        ),
        admin_ctx,
    )

    # 3. Already expired item
    past_date = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    ops.create_compliance_item(
        ComplianceItem(
            title="EPA Lead-Safe Certification",
            category="epa_lead_cert",
            expiration_date=past_date,
        ),
        admin_ctx,
    )

    scan_res = ops.scan_compliance_expirations(admin_ctx, threshold_days=30)
    assert scan_res["total_scanned"] == 3
    assert scan_res["expiring_soon_count"] == 1
    assert scan_res["expired_count"] == 1
    assert scan_res["active_count"] == 1


def test_hr_employee_and_timesheet(ops_setup):
    ops = ops_setup["ops"]
    admin_ctx = ops_setup["admin_ctx"]
    tech_ctx = ops_setup["tech_ctx"]

    # Create employee
    emp = ops.create_employee(
        Employee(
            first_name="Marcus",
            last_name="Technician",
            role_title="Lead Restoration Tech",
            department="operations",
            hourly_rate=35.0,
        ),
        admin_ctx,
    )
    assert emp.id is not None

    # Submit timesheet (8 hours regular @ $35/hr = $280)
    ts = ops.submit_timesheet(
        Timesheet(
            employee_id=emp.id,
            hours_worked=8.0,
            work_type="regular",
        ),
        tech_ctx,
    )
    assert ts.id is not None
    assert ts.total_cost == 280.0
    assert ts.status == "submitted"

    # Approve timesheet
    approved = ops.approve_timesheet(ts.id, admin_ctx)
    assert approved.status == "approved"
    assert approved.approved_by_id == admin_ctx.user_id


def test_procurement_vendor_and_po(ops_setup):
    ops = ops_setup["ops"]
    admin_ctx = ops_setup["admin_ctx"]

    # Create vendor
    vendor = ops.create_vendor(
        Vendor(
            company_name="Jon-Don Restoration Supply",
            category="building_materials",
            payment_terms="net_30",
        ),
        admin_ctx,
    )
    assert vendor.id is not None

    # Create purchase order
    po = ops.create_purchase_order(
        PurchaseOrder(
            vendor_id=vendor.id,
            items=[
                {"item": "Antimicrobial Disinfectant 5Gal", "quantity": 4, "unit_cost": 85.0},
                {"item": "HEPA Filters", "quantity": 10, "unit_cost": 25.0},
            ],
            tax_amount=47.20,
        ),
        admin_ctx,
    )
    assert po.id is not None
    assert po.subtotal == 590.0
    assert po.total_amount == 637.20
    assert po.status == "draft"

    # Receive PO
    received_po = ops.receive_purchase_order(po.id, admin_ctx)
    assert received_po.status == "received"
    assert received_po.received_date is not None
