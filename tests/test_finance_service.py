"""
Unit and integration tests for Finance & Bookkeeping Domain Engine (Track B Phase B5a).
"""

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
    Customer,
    FinancialTransaction,
    Invoice,
    Project,
    User,
)
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.finance_service import FinanceService


@pytest.fixture
def test_setup():
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    auth = AuthService(db)
    crm = CRMService(db, audit)
    finance = FinanceService(db, audit)

    # Setup admin user & context
    admin_user = auth.create_user("admin_fin", "AdminPass123!", "Admin User", "admin_fin@test.com", ROLE_ADMIN)
    admin_ctx = AuthContext(user_id=admin_user.id, username=admin_user.username, role=ROLE_ADMIN, actor_type="human")

    # Setup technician user & context (no finance perms)
    tech_user = auth.create_user("tech_fin", "TechPass123!", "Tech User", "tech_fin@test.com", ROLE_TECHNICIAN)
    tech_ctx = AuthContext(user_id=tech_user.id, username=tech_user.username, role=ROLE_TECHNICIAN, actor_type="human")

    # Setup customer user & context
    cust = crm.create_customer(Customer(first_name="Jane", last_name="FinTest", email="jane@fintest.com"), admin_ctx)
    cust_user = auth.create_user("cust_fin", "CustPass123!", "Jane FinTest", "jane@fintest.com", ROLE_CUSTOMER, customer_id=cust.id)
    cust_ctx = AuthContext(user_id=cust_user.id, username=cust_user.username, role=ROLE_CUSTOMER, customer_id=cust.id, actor_type="human")

    # Setup sample project
    proj = crm.create_project(
        Project(
            customer_id=cust.id,
            title="Kitchen Water Restoration",
            contract_amount=15000.0,
            estimated_cost=8000.0,
        ),
        admin_ctx,
    )

    return {
        "db": db,
        "audit": audit,
        "auth": auth,
        "crm": crm,
        "finance": finance,
        "admin_ctx": admin_ctx,
        "tech_ctx": tech_ctx,
        "cust_ctx": cust_ctx,
        "cust": cust,
        "proj": proj,
    }


def test_record_financial_transaction(test_setup):
    f = test_setup["finance"]
    admin_ctx = test_setup["admin_ctx"]
    proj = test_setup["proj"]

    # Record material cost transaction
    txn = f.record_transaction(
        FinancialTransaction(
            transaction_type="material_cost",
            amount=1250.50,
            category="Drywall & Framing",
            project_id=proj.id,
            notes="Supplies from Home Depot",
        ),
        admin_ctx,
    )

    assert txn.id is not None
    assert txn.transaction_number.startswith("TXN-")
    assert txn.amount == 1250.50

    # Verify project actual_cost was incremented
    updated_proj = test_setup["crm"].get_project(proj.id, admin_ctx)
    assert updated_proj.actual_cost == 1250.50


def test_transaction_permission_enforcement(test_setup):
    f = test_setup["finance"]
    tech_ctx = test_setup["tech_ctx"]

    with pytest.raises(PermissionError):
        f.record_transaction(
            FinancialTransaction(transaction_type="payroll", amount=500.0),
            tech_ctx,
        )


def test_project_pnl_calculation(test_setup):
    f = test_setup["finance"]
    admin_ctx = test_setup["admin_ctx"]
    proj = test_setup["proj"]
    crm = test_setup["crm"]

    # 1. Record customer payment received ($15,000)
    f.record_transaction(
        FinancialTransaction(
            transaction_type="payment_received",
            amount=15000.0,
            project_id=proj.id,
        ),
        admin_ctx,
    )

    # 2. Record materials ($2,000)
    f.record_transaction(
        FinancialTransaction(
            transaction_type="material_cost",
            amount=2000.0,
            project_id=proj.id,
        ),
        admin_ctx,
    )

    # 3. Record subcontractor expense ($3,000)
    f.record_transaction(
        FinancialTransaction(
            transaction_type="vendor_expense",
            amount=3000.0,
            project_id=proj.id,
        ),
        admin_ctx,
    )

    # 4. Record equipment rental ($1,000)
    f.record_transaction(
        FinancialTransaction(
            transaction_type="equipment_rental",
            amount=1000.0,
            project_id=proj.id,
        ),
        admin_ctx,
    )

    # Compute P&L
    pnl = f.get_project_pnl(proj.id, admin_ctx)
    assert pnl["contract_amount"] == 15000.0
    assert pnl["total_collected"] == 15000.0
    assert pnl["total_expenses"] == 6000.0
    assert pnl["gross_profit"] == 9000.0
    assert pnl["gross_margin_percent"] == 60.0
    assert pnl["expenses_breakdown"]["materials"] == 2000.0
    assert pnl["expenses_breakdown"]["subcontractors"] == 3000.0
    assert pnl["expenses_breakdown"]["equipment"] == 1000.0


def test_ar_aging_buckets(test_setup):
    f = test_setup["finance"]
    admin_ctx = test_setup["admin_ctx"]
    crm = test_setup["crm"]
    cust = test_setup["cust"]
    proj = test_setup["proj"]

    # Create current invoice
    crm.create_invoice(
        Invoice(
            customer_id=cust.id,
            project_id=proj.id,
            amount=5000.0,
            balance_due=5000.0,
            due_date="2099-01-01T00:00:00Z",
            status="sent",
        ),
        admin_ctx,
    )

    # Create overdue invoice (45 days overdue)
    crm.create_invoice(
        Invoice(
            customer_id=cust.id,
            project_id=proj.id,
            amount=2500.0,
            balance_due=2500.0,
            due_date="2020-01-01T00:00:00Z",
            status="overdue",
        ),
        admin_ctx,
    )

    aging = f.get_ar_aging(admin_ctx)
    assert aging["total_ar"] == 7500.0
    assert aging["buckets"]["current"] == 5000.0
    assert aging["buckets"]["over_90_days"] == 2500.0


def test_financial_summary(test_setup):
    f = test_setup["finance"]
    admin_ctx = test_setup["admin_ctx"]

    f.record_transaction(
        FinancialTransaction(transaction_type="payment_received", amount=20000.0),
        admin_ctx,
    )
    f.record_transaction(
        FinancialTransaction(transaction_type="payroll", amount=6000.0),
        admin_ctx,
    )

    summary = f.get_financial_summary(admin_ctx)
    assert summary["total_revenue"] == 20000.0
    assert summary["total_expenses"] == 6000.0
    assert summary["net_profit"] == 14000.0
    assert summary["net_margin_percent"] == 70.0
