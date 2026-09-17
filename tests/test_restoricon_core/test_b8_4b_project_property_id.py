"""
Unit tests for B8.4b (NEW-566): wiring ``projects.property_id`` (a real DB
column added by B8.1's schema migration, but never read/written by the
Project dataclass or CRMService) into the model/service layer.

Covers:
1. ``Project.property_id`` round-trips through create_project -> _row_to_project.
2. ``update_project`` can set/change ``property_id`` via the allow-list.
3. ``GET /api/v1/projects?property_id=<id>`` returns only matching projects.
"""

import json

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Project, Property
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
    return {"db": db, "auth": auth_service, "crm": crm_service, "router": router}


@pytest.fixture
def admin(env):
    u = env["auth"].create_user("admin_u", "Pass123!", "Admin", "admin@r.com", role=ROLE_ADMIN)
    t = env["auth"].create_token(u)
    return AuthContext(u.id, u.username, ROLE_ADMIN, "human", token=t)


@pytest.fixture
def customer(env, admin):
    return env["crm"].create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@example.com"), admin
    )


@pytest.fixture
def properties(env, admin, customer):
    prop_a = env["crm"].create_property(
        Property(customer_id=customer.id, address="1 Main St"), admin
    )
    prop_b = env["crm"].create_property(
        Property(customer_id=customer.id, address="2 Oak Ave"), admin
    )
    return prop_a, prop_b


def test_create_project_persists_and_reads_back_property_id(env, admin, customer, properties):
    prop_a, _ = properties
    created = env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Kitchen Remodel",
            property_address=prop_a.address,
            project_type="remodel",
            property_id=prop_a.id,
        ),
        admin,
    )
    assert created.property_id == prop_a.id

    fetched = env["crm"].get_project(created.id, admin)
    assert fetched.property_id == prop_a.id


def test_create_project_without_property_id_defaults_to_none(env, admin, customer):
    created = env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Roof Repair",
            property_address="3 Elm St",
            project_type="roofing",
        ),
        admin,
    )
    assert created.property_id is None
    fetched = env["crm"].get_project(created.id, admin)
    assert fetched.property_id is None


def test_create_project_bad_property_id_raises_value_error(env, admin, customer):
    """NEW-303-class check: a nonexistent property_id must raise a clean
    ValueError (-> 400 at the route) rather than reach the INSERT and leak
    an uncaught sqlite3.IntegrityError as a 500 -- the fresh-DB schema has
    a real FOREIGN KEY (property_id) REFERENCES properties(id)."""
    with pytest.raises(ValueError):
        env["crm"].create_project(
            Project(
                customer_id=customer.id,
                title="Bad FK Project",
                property_address="1 Main St",
                project_type="remodel",
                property_id=999999,
            ),
            admin,
        )


def test_route_create_project_bad_property_id_400_not_500(env, admin, customer):
    router = env["router"]
    status, _, body = router.handle_request(
        "POST",
        "/api/v1/projects",
        {"Authorization": f"Bearer {admin.token}"},
        json.dumps({
            "customer_id": customer.id,
            "title": "Bad FK Project",
            "property_address": "1 Main St",
            "project_type": "remodel",
            "property_id": 999999,
        }).encode(),
    )
    assert status == 400, body


def test_update_project_can_set_property_id_via_allow_list(env, admin, customer, properties):
    prop_a, prop_b = properties
    created = env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Water Damage Restoration",
            property_address=prop_a.address,
            project_type="water_damage",
            property_id=prop_a.id,
        ),
        admin,
    )
    updated = env["crm"].update_project(created.id, {"property_id": prop_b.id}, admin)
    assert updated.property_id == prop_b.id

    refetched = env["crm"].get_project(created.id, admin)
    assert refetched.property_id == prop_b.id


def test_update_project_rejects_non_int_property_id(env, admin, customer, properties):
    prop_a, _ = properties
    created = env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Water Damage Restoration",
            property_address=prop_a.address,
            project_type="water_damage",
        ),
        admin,
    )
    with pytest.raises(ValueError):
        env["crm"].update_project(created.id, {"property_id": "not-an-int"}, admin)


def test_list_projects_filters_by_property_id(env, admin, customer, properties):
    prop_a, prop_b = properties
    proj_a = env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Project A",
            property_address=prop_a.address,
            project_type="remodel",
            property_id=prop_a.id,
        ),
        admin,
    )
    env["crm"].create_project(
        Project(
            customer_id=customer.id,
            title="Project B",
            property_address=prop_b.address,
            project_type="remodel",
            property_id=prop_b.id,
        ),
        admin,
    )

    results = env["crm"].list_projects(admin, property_id=prop_a.id)
    assert len(results) == 1
    assert results[0].id == proj_a.id
    assert results[0].property_id == prop_a.id


def test_get_projects_route_filters_by_property_id_query_param(env, admin, customer, properties):
    prop_a, prop_b = properties
    router = env["router"]
    token = admin.token

    status, _, body = router.handle_request(
        "POST",
        "/api/v1/projects",
        {"Authorization": f"Bearer {token}"},
        json.dumps({
            "customer_id": customer.id,
            "title": "Project A",
            "property_address": prop_a.address,
            "project_type": "remodel",
            "property_id": prop_a.id,
        }).encode(),
    )
    assert status == 201, body

    status, _, body = router.handle_request(
        "POST",
        "/api/v1/projects",
        {"Authorization": f"Bearer {token}"},
        json.dumps({
            "customer_id": customer.id,
            "title": "Project B",
            "property_address": prop_b.address,
            "project_type": "remodel",
            "property_id": prop_b.id,
        }).encode(),
    )
    assert status == 201, body

    status, _, body = router.handle_request(
        "GET",
        f"/api/v1/projects?property_id={prop_a.id}",
        {"Authorization": f"Bearer {token}"},
        b"",
    )
    assert status == 200, body
    projects = body["projects"]
    assert len(projects) == 1
    assert projects[0]["title"] == "Project A"
    assert projects[0]["property_id"] == prop_a.id
