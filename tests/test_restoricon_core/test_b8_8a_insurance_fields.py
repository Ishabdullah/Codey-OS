"""
Unit tests for B8.8a: two new additive nullable Project columns
(``coverage_amount``, ``supplement_amount``) wired into the same
insurance/claim/adjuster field group already carried by ``Project``
(``insurance_claim_number``, ``insurance_carrier``, ``adjuster_name``,
``adjuster_phone``, ``adjuster_email``, ``deductible``).

Covers:
1. All 6 existing + 2 new insurance fields round-trip through
   create_project -> _row_to_project with distinct values each (catches an
   INSERT column/value ordering swap that same-valued fields would not).
2. update_project can set/change coverage_amount/supplement_amount via the
   allow-list, and the ordinary numeric type-check guard (NEW-308's class)
   rejects a non-numeric value for either.
3. The audit diff (build_audit_details via update_project) includes both
   new fields in changed_fields with correct old/new, not silently dropped
   from _AUDITABLE_PROJECT_FIELDS.
4. RBAC on the new fields is identical to every other project field --
   PERM_WRITE_PROJECTS gate, PermissionError for an actor lacking it (same
   shape as test_b6_1_update_project.py's technician fixture).

insurance_claim_status is deliberately out of scope for Project -- it lives
on Opportunity only (models.py, crm_service.py:1487's vocabulary-separation
docstring); there is no Project column for it, so no test asserts it here.
"""

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import AuthContext, AuthService, PERM_WRITE_PROJECTS, ROLE_ADMIN, ROLE_TECHNICIAN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Project
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    comm_service = CommunicationService(db)
    crm_service = CRMService(db, audit_service)
    sched_service = SchedulingService(db, audit_service)
    auto_service = AutomationService(db, audit_service)
    ops_service = OperationsService(db, audit_service)
    router = APIRouter(
        auth_service=auth_service,
        crm_service=crm_service,
        comm_service=comm_service,
        audit_service=audit_service,
        scheduling_service=sched_service,
        automation_service=auto_service,
        operations_service=ops_service,
    )
    return {
        "db": db,
        "auth": auth_service,
        "audit": audit_service,
        "crm": crm_service,
        "router": router,
    }


@pytest.fixture
def admin(env):
    u = env["auth"].create_user("admin_u", "Pass123!", "Admin", "admin@r.com", role=ROLE_ADMIN)
    t = env["auth"].create_token(u)
    return AuthContext(u.id, u.username, ROLE_ADMIN, "human", token=t)


@pytest.fixture
def technician(env):
    u = env["auth"].create_user("tech_u", "Pass123!", "Tech", "tech@r.com", role=ROLE_TECHNICIAN)
    t = env["auth"].create_token(u)
    return AuthContext(u.id, u.username, ROLE_TECHNICIAN, "human", token=t)


@pytest.fixture
def customer(env, admin):
    return env["crm"].create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@example.com"), admin
    )


def test_create_project_round_trips_all_insurance_fields_with_distinct_values(env, admin, customer):
    created = env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Fire Damage Restoration",
            property_address="12 Cedar Ln",
            project_type="fire_damage",
            insurance_claim_number="CLM-1001",
            insurance_carrier="State Farm",
            adjuster_name="Pat Adjuster",
            adjuster_phone="555-0100",
            adjuster_email="pat@carrier.com",
            deductible=1000.0,
            coverage_amount=85000.0,
            supplement_amount=4200.5,
        ),
        admin,
    )
    assert created.insurance_claim_number == "CLM-1001"
    assert created.insurance_carrier == "State Farm"
    assert created.adjuster_name == "Pat Adjuster"
    assert created.adjuster_phone == "555-0100"
    assert created.adjuster_email == "pat@carrier.com"
    assert created.deductible == 1000.0
    assert created.coverage_amount == 85000.0
    assert created.supplement_amount == 4200.5

    fetched = env["crm"].get_project(created.id, admin)
    assert fetched.insurance_claim_number == "CLM-1001"
    assert fetched.insurance_carrier == "State Farm"
    assert fetched.adjuster_name == "Pat Adjuster"
    assert fetched.adjuster_phone == "555-0100"
    assert fetched.adjuster_email == "pat@carrier.com"
    assert fetched.deductible == 1000.0
    assert fetched.coverage_amount == 85000.0
    assert fetched.supplement_amount == 4200.5


def test_create_project_without_new_fields_defaults_to_none(env, admin, customer):
    created = env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Roof Repair",
            property_address="3 Elm St",
            project_type="roofing",
        ),
        admin,
    )
    assert created.coverage_amount is None
    assert created.supplement_amount is None
    fetched = env["crm"].get_project(created.id, admin)
    assert fetched.coverage_amount is None
    assert fetched.supplement_amount is None


def test_update_project_can_set_new_fields_via_allow_list(env, admin, customer):
    created = env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Water Damage Restoration",
            property_address="1 Main St",
            project_type="water_damage",
        ),
        admin,
    )
    updated = env["crm"].update_project(
        created.id,
        {"coverage_amount": 60000.25, "supplement_amount": 1500.75},
        admin,
    )
    assert updated.coverage_amount == 60000.25
    assert updated.supplement_amount == 1500.75

    refetched = env["crm"].get_project(created.id, admin)
    assert refetched.coverage_amount == 60000.25
    assert refetched.supplement_amount == 1500.75


@pytest.mark.parametrize("field", ["coverage_amount", "supplement_amount"])
def test_update_project_rejects_non_numeric_new_field(env, admin, customer, field):
    created = env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Water Damage Restoration",
            property_address="1 Main St",
            project_type="water_damage",
        ),
        admin,
    )
    with pytest.raises(ValueError):
        env["crm"].update_project(created.id, {field: "not-a-number"}, admin)


def test_update_project_new_fields_audit_diff_includes_both(env, admin, customer):
    created = env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Mold Remediation",
            property_address="9 Birch Rd",
            project_type="mold",
            coverage_amount=10000.0,
            supplement_amount=500.0,
        ),
        admin,
    )
    env["crm"].update_project(
        created.id,
        {"coverage_amount": 12000.0, "supplement_amount": 900.0},
        admin,
    )
    rows = env["audit"].query_logs(admin, entity_type="project", entity_id=created.id, action="update")
    assert len(rows) == 1
    changed = rows[0].details["changed_fields"]
    assert changed["coverage_amount"] == {"old": 10000.0, "new": 12000.0}
    assert changed["supplement_amount"] == {"old": 500.0, "new": 900.0}


def test_update_project_new_fields_denied_without_write_permission(env, technician, customer, admin):
    created = env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Storm Damage",
            property_address="4 Pine Ct",
            project_type="storm",
        ),
        admin,
    )
    assert not technician.has_permission(PERM_WRITE_PROJECTS)
    with pytest.raises(PermissionError):
        env["crm"].update_project(created.id, {"coverage_amount": 5000.0}, technician)


def test_route_update_project_new_fields_200(env, admin, customer):
    router = env["router"]
    created = env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Wind Damage",
            property_address="7 Maple Dr",
            project_type="wind",
        ),
        admin,
    )
    import json

    status, _, body = router.handle_request(
        "POST",
        f"/api/v1/projects/{created.id}/update",
        {"Authorization": f"Bearer {admin.token}"},
        json.dumps({"coverage_amount": 30000.0, "supplement_amount": 2000.0}).encode(),
    )
    assert status == 200, body
    assert body["project"]["coverage_amount"] == 30000.0
    assert body["project"]["supplement_amount"] == 2000.0
