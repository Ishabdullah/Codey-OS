"""
Unit tests for B8.9a (sales_rep_portal.md §5 B8.9, corrected scope
2026-09-23 -- territory management only, NOT referral compensation, see
NEW-545's resolution): the territories table + TerritoryService CRUD,
territory_id on users/leads/customers via the three corrected allow-
lists, and territory_id filtering on list_leads/list_customers.

Mirrors test_b8_8b1_financing_records.py's service-level conventions.
"""

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_READ_TERRITORIES,
    PERM_WRITE_TERRITORIES,
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SALES,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Lead, Territory
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.territory_service import TerritoryService


def _make_actor(auth_service, username, role, email=None):
    user = auth_service.create_user(
        username=username,
        plain_password="Password123",
        full_name=username.title(),
        email=email or f"{username}@test.com",
        role=role,
    )
    return AuthContext(user_id=user.id, username=username, role=role, actor_type="human")


@pytest.fixture
def setup_services():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)
    territory_service = TerritoryService(db, audit_service)
    return db, auth_service, audit_service, crm_service, territory_service


# ==========================================
# Territory CRUD round-trip
# ==========================================


def test_create_list_get_update_territory(setup_services):
    _, auth_service, _, _, territory_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    created = territory_service.create_territory(
        Territory(name="North Metro", code="NORTH", notes="Serves the north side"), admin
    )
    assert created.id is not None
    assert created.name == "North Metro"
    assert created.code == "NORTH"
    assert created.created_at is not None

    fetched = territory_service.get_territory(created.id, admin)
    assert fetched is not None
    assert fetched.name == "North Metro"

    territories = territory_service.list_territories(admin)
    assert any(t.id == created.id for t in territories)

    updated = territory_service.update_territory(created.id, {"name": "North Metro Zone", "code": "N1"}, admin)
    assert updated.name == "North Metro Zone"
    assert updated.code == "N1"
    assert updated.notes == "Serves the north side"  # untouched field preserved

    refetched = territory_service.get_territory(created.id, admin)
    assert refetched.name == "North Metro Zone"
    assert refetched.code == "N1"


def test_get_territory_not_found(setup_services):
    _, auth_service, _, _, territory_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    assert territory_service.get_territory(999999, admin) is None


def test_update_territory_not_found(setup_services):
    _, auth_service, _, _, territory_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    assert territory_service.update_territory(999999, {"name": "X"}, admin) is None


def test_create_territory_requires_name(setup_services):
    _, auth_service, _, _, territory_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    with pytest.raises(ValueError):
        territory_service.create_territory(Territory(name=""), admin)


def test_update_territory_unknown_field_rejected(setup_services):
    _, auth_service, _, _, territory_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    created = territory_service.create_territory(Territory(name="East"), admin)
    with pytest.raises(ValueError):
        territory_service.update_territory(created.id, {"bogus_field": "x"}, admin)


# ==========================================
# RBAC on territory CRUD
# ==========================================


def test_territory_write_gated_on_perm_write_territories(setup_services):
    _, auth_service, _, _, territory_service = setup_services
    tech = _make_actor(auth_service, "tech", ROLE_TECHNICIAN)
    assert not AuthContext(user_id=tech.user_id, username="tech", role=ROLE_TECHNICIAN, actor_type="human").has_permission(
        PERM_WRITE_TERRITORIES
    )
    with pytest.raises(PermissionError):
        territory_service.create_territory(Territory(name="Blocked"), tech)


def test_territory_read_gated_on_perm_read_territories(setup_services):
    _, auth_service, _, _, territory_service = setup_services
    tech = _make_actor(auth_service, "tech", ROLE_TECHNICIAN)
    with pytest.raises(PermissionError):
        territory_service.list_territories(tech)


def test_manager_can_write_territories(setup_services):
    _, auth_service, _, _, territory_service = setup_services
    manager = _make_actor(auth_service, "mgr", ROLE_MANAGER)
    created = territory_service.create_territory(Territory(name="South"), manager)
    assert created.id is not None


# ==========================================
# territory_id settable via update_user / update_lead / update_customer
# ==========================================


def test_territory_id_settable_via_update_user(setup_services):
    _, auth_service, _, _, territory_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    territory = territory_service.create_territory(Territory(name="West"), admin)
    rep = auth_service.create_user(
        username="rep1", plain_password="Password123", full_name="Rep One",
        email="rep1@test.com", role=ROLE_SALES,
    )
    assert rep.territory_id is None

    updated, _ = auth_service.update_user(rep.id, {"territory_id": territory.id}, admin)
    assert updated.territory_id == territory.id

    # Clearing back to None is accepted (no None-guard on this path).
    cleared, _ = auth_service.update_user(rep.id, {"territory_id": None}, admin)
    assert cleared.territory_id is None


def test_territory_id_settable_via_update_lead(setup_services):
    _, auth_service, _, crm_service, territory_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    territory = territory_service.create_territory(Territory(name="East Side"), admin)

    lead = crm_service.create_lead(Lead(source="website"), admin)
    assert lead.territory_id is None

    updated = crm_service.update_lead(lead.id, {"territory_id": territory.id}, admin)
    assert updated.territory_id == territory.id


def test_territory_id_settable_via_update_customer(setup_services):
    _, auth_service, _, crm_service, territory_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    territory = territory_service.create_territory(Territory(name="Downtown"), admin)

    cust = crm_service.create_customer(
        Customer(first_name="Terri", last_name="Tory", email="terri_tory@test.com"), admin
    )
    assert cust.territory_id is None

    updated = crm_service.update_customer(cust.id, {"territory_id": territory.id}, admin)
    assert updated.territory_id == territory.id

    # Clearing back to None is accepted (mirrors assigned_user_id's exception).
    cleared = crm_service.update_customer(cust.id, {"territory_id": None}, admin)
    assert cleared.territory_id is None


# ==========================================
# list_leads / list_customers territory_id filtering
# ==========================================


def test_list_leads_filters_by_territory_id(setup_services):
    _, auth_service, _, crm_service, territory_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    north = territory_service.create_territory(Territory(name="North"), admin)
    south = territory_service.create_territory(Territory(name="South"), admin)

    lead_north = crm_service.create_lead(Lead(source="website"), admin)
    crm_service.update_lead(lead_north.id, {"territory_id": north.id}, admin)
    lead_south = crm_service.create_lead(Lead(source="website"), admin)
    crm_service.update_lead(lead_south.id, {"territory_id": south.id}, admin)
    crm_service.create_lead(Lead(source="website"), admin)  # no territory

    north_leads = crm_service.list_leads(admin, territory_id=north.id)
    assert {l.id for l in north_leads} == {lead_north.id}

    south_leads = crm_service.list_leads(admin, territory_id=south.id)
    assert {l.id for l in south_leads} == {lead_south.id}


def test_list_customers_filters_by_territory_id(setup_services):
    _, auth_service, _, crm_service, territory_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    north = territory_service.create_territory(Territory(name="North"), admin)

    cust_north = crm_service.create_customer(
        Customer(first_name="A", last_name="North", email="a_north@test.com"), admin
    )
    crm_service.update_customer(cust_north.id, {"territory_id": north.id}, admin)
    crm_service.create_customer(
        Customer(first_name="B", last_name="Unset", email="b_unset@test.com"), admin
    )

    filtered = crm_service.list_customers(admin, territory_id=north.id)
    assert {c.id for c in filtered} == {cust_north.id}
