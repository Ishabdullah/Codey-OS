"""
Unit + route-level tests for B8.5b (sales_rep_portal.md §5/§6/§7):
the assessment_records table, AssessmentService, and the
GET/POST /api/v1/assessment-records routes.

Mirrors test_b8_1_properties_and_commissions.py / test_b8_4a_property_routes.py's
conventions for this codebase.
"""

import json

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_READ_ALL_CUSTOMERS,
    PERM_WRITE_CUSTOMERS,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import AssessmentRecord, Customer, Property
from restoricon_core.services.analytics_search_service import AnalyticsSearchService
from restoricon_core.services.assessment_service import AssessmentService
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.business_ops_service import BusinessOpsService
from restoricon_core.services.commission_service import CommissionService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.finance_service import FinanceService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService


def _make_actor(auth_service, username, role, email=None, customer_id=None):
    user = auth_service.create_user(
        username=username,
        plain_password="Password123",
        full_name=username.title(),
        email=email or f"{username}@test.com",
        role=role,
        customer_id=customer_id,
    )
    return AuthContext(user_id=user.id, username=username, role=role, actor_type="human")


# ==========================================
# SERVICE-LEVEL (AssessmentService)
# ==========================================


@pytest.fixture
def setup_services():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)
    sched_service = SchedulingService(db, audit_service)
    assessment_service = AssessmentService(db, audit_service)
    return db, auth_service, audit_service, crm_service, sched_service, assessment_service


def test_create_and_get_assessment_record(setup_services):
    _, auth_service, _, crm_service, sched_service, assessment_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane_assess@test.com"), admin
    )
    prop = crm_service.create_property(
        Property(customer_id=cust.id, address="1 Assess St"), admin
    )

    record = assessment_service.create_assessment_record(
        AssessmentRecord(
            property_id=prop.id,
            checklist={"roof_condition": "damaged", "water_intrusion": True},
            evidence_document_ids=[1, 2],
            customer_statements="Customer reports leak started after last storm.",
        ),
        admin,
    )
    assert record.id is not None
    assert record.created_by == admin.user_id
    assert record.created_at is not None

    fetched = assessment_service.get_assessment_record(record.id, admin)
    assert fetched is not None
    assert fetched.property_id == prop.id
    assert fetched.checklist == {"roof_condition": "damaged", "water_intrusion": True}
    assert fetched.evidence_document_ids == [1, 2]
    assert fetched.customer_statements == "Customer reports leak started after last storm."


def test_get_assessment_record_not_found(setup_services):
    _, auth_service, _, _, _, assessment_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    assert assessment_service.get_assessment_record(999999, admin) is None


def test_list_assessment_records_filtered_by_property_and_appointment(setup_services):
    _, auth_service, _, crm_service, sched_service, assessment_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust = crm_service.create_customer(
        Customer(first_name="A", last_name="One", email="a_assess@test.com"), admin
    )
    prop1 = crm_service.create_property(Property(customer_id=cust.id, address="1 First St"), admin)
    prop2 = crm_service.create_property(Property(customer_id=cust.id, address="2 Second St"), admin)

    from restoricon_core.models import Appointment

    appt = sched_service.create_appointment(
        Appointment(title="Initial assessment", customer_id=cust.id, status="negotiating"),
        admin,
    )

    r1 = assessment_service.create_assessment_record(
        AssessmentRecord(property_id=prop1.id, checklist={"a": 1}), admin
    )
    r2 = assessment_service.create_assessment_record(
        AssessmentRecord(property_id=prop2.id, checklist={"b": 2}), admin
    )
    r3 = assessment_service.create_assessment_record(
        AssessmentRecord(appointment_id=appt.id, property_id=prop1.id, checklist={"c": 3}), admin
    )

    by_prop1 = assessment_service.list_assessment_records(admin, property_id=prop1.id)
    assert {r.id for r in by_prop1} == {r1.id, r3.id}

    by_prop2 = assessment_service.list_assessment_records(admin, property_id=prop2.id)
    assert {r.id for r in by_prop2} == {r2.id}

    by_appt = assessment_service.list_assessment_records(admin, appointment_id=appt.id)
    assert {r.id for r in by_appt} == {r3.id}

    all_records = assessment_service.list_assessment_records(admin)
    assert {r.id for r in all_records} == {r1.id, r2.id, r3.id}


def test_create_assessment_record_permission_denied(setup_services):
    _, auth_service, _, crm_service, _, assessment_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust = crm_service.create_customer(
        Customer(first_name="P", last_name="Cust", email="p_cust_assess@test.com"), admin
    )
    cust_actor = _make_actor(
        auth_service, "custuser_assess", ROLE_CUSTOMER, email="cu_assess@test.com", customer_id=cust.id
    )

    with pytest.raises(PermissionError):
        assessment_service.create_assessment_record(
            AssessmentRecord(property_id=None, checklist={}), cust_actor
        )


def test_list_assessment_records_permission_denied(setup_services):
    _, auth_service, _, crm_service, _, assessment_service = setup_services
    admin = _make_actor(auth_service, "admin2", ROLE_ADMIN, email="admin2_assess@test.com")
    cust = crm_service.create_customer(
        Customer(first_name="R", last_name="Cust", email="r_cust_assess@test.com"), admin
    )
    cust_actor = _make_actor(
        auth_service, "custuser_assess2", ROLE_CUSTOMER, email="cu_assess2@test.com", customer_id=cust.id
    )
    with pytest.raises(PermissionError):
        assessment_service.list_assessment_records(cust_actor)


def test_create_assessment_record_writes_audit_log(setup_services):
    db, auth_service, audit_service, crm_service, _, assessment_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust = crm_service.create_customer(
        Customer(first_name="Q", last_name="Cust", email="q_cust_assess@test.com"), admin
    )
    prop = crm_service.create_property(Property(customer_id=cust.id, address="9 Audit Ln"), admin)

    record = assessment_service.create_assessment_record(
        AssessmentRecord(property_id=prop.id, checklist={"x": 1}), admin
    )

    conn = db.get_connection()
    row = conn.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'assessment_record' AND entity_id = ?;",
        (record.id,),
    ).fetchone()
    assert row is not None
    assert row["action"] == "create"


# ==========================================
# ROUTE-LEVEL (GET/POST /api/v1/assessment-records)
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
    commissions = CommissionService(db, audit)
    assessments = AssessmentService(db, audit)

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
        commission_service=commissions,
        assessment_service=assessments,
    )

    admin_u = auth.create_user("admin_assess", "AdminPass123!", "Admin Assess", "admin_assess@test.com", ROLE_ADMIN)
    admin_tok = auth.create_token(admin_u)
    admin_ctx = auth.authenticate_token(admin_tok)

    sales_u = auth.create_user("sales_assess", "SalesPass123!", "Sales Assess", "sales_assess@test.com", ROLE_SALES)
    sales_tok = auth.create_token(sales_u)

    cust = crm.create_customer(
        Customer(first_name="Pat", last_name="Assess", email="pat_assess@test.com"), admin_ctx
    )
    prop = crm.create_property(Property(customer_id=cust.id, address="123 Route St"), admin_ctx)

    cust_u = auth.create_user(
        "cust_assess", "CustPass123!", "Pat Assess", "pat_assess2@test.com", ROLE_CUSTOMER, customer_id=cust.id
    )
    cust_tok = auth.create_token(cust_u)

    return {
        "router": router,
        "admin_tok": admin_tok,
        "sales_tok": sales_tok,
        "cust_tok": cust_tok,
        "cust": cust,
        "prop": prop,
    }


def _req(router: APIRouter, method: str, path: str, token: str, body: dict = None):
    headers = {"authorization": f"Bearer {token}"}
    body_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
    status, res_headers, res_json = router.handle_request(method, path, headers, body_bytes)
    return status, res_json


def test_create_list_get_assessment_record_routes(api_setup):
    router = api_setup["router"]
    sales_tok = api_setup["sales_tok"]
    prop = api_setup["prop"]

    status, res = _req(
        router,
        "POST",
        "/api/v1/assessment-records",
        sales_tok,
        {
            "property_id": prop.id,
            "checklist": {"roof": "ok"},
            "evidence_document_ids": [1],
            "customer_statements": "Nothing unusual reported.",
        },
    )
    assert status == 201, res
    rec = res["assessment_record"]
    assert rec["id"] is not None
    assert rec["property_id"] == prop.id
    record_id = rec["id"]

    status, res = _req(
        router, "GET", f"/api/v1/assessment-records?property_id={prop.id}", sales_tok
    )
    assert status == 200, res
    assert len(res["assessment_records"]) == 1
    assert res["assessment_records"][0]["id"] == record_id

    status, res = _req(router, "GET", f"/api/v1/assessment-records/{record_id}", sales_tok)
    assert status == 200, res
    assert res["assessment_record"]["property_id"] == prop.id

    status, res = _req(router, "GET", "/api/v1/assessment-records/999999", sales_tok)
    assert status == 404, res


def test_assessment_record_routes_permission_denied_for_customer_role(api_setup):
    router = api_setup["router"]
    cust_tok = api_setup["cust_tok"]
    prop = api_setup["prop"]

    status, res = _req(
        router,
        "POST",
        "/api/v1/assessment-records",
        cust_tok,
        {"property_id": prop.id, "checklist": {}},
    )
    assert status == 403, res

    status, res = _req(router, "GET", "/api/v1/assessment-records", cust_tok)
    assert status == 403, res
