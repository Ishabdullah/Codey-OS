"""
Tests for customer upsert, update, search, RBAC enforcement, and HTTP routes
(Phase B2 Task 4: Customer Write-Through Cutover and Core API Groundwork).
"""

import pytest
from restoricon_core.api.server import RestoriconAPIServer
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService
from .test_api import find_free_port, make_request


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def services():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)

    admin_user = auth_service.create_user(
        username="admin",
        plain_password="Password123",
        full_name="Admin Boss",
        email="admin@test.com",
        role=ROLE_ADMIN,
    )
    actor = AuthContext(
        user_id=admin_user.id,
        username="admin",
        role=ROLE_ADMIN,
        actor_type="human",
    )
    return crm_service, actor, auth_service, audit_service


def _make_customer(**kwargs) -> Customer:
    """Minimal valid Customer for upsert tests."""
    defaults = dict(
        external_id="CUST-TEST-001",
        first_name="Jane",
        last_name="Doe",
        phone="860-555-1234",
        email="jane.doe@example.com",
        service_address="123 Main St, Hartford, CT 06103",
        customer_type="residential",
        status="lead",
        tags=["new_lead"],
        custom_fields={"city": "Hartford", "project_type": "kitchen_remodeling"},
    )
    defaults.update(kwargs)
    return Customer(**defaults)


class _ZeroPermActor:
    role = "nobody"

    def has_permission(self, _perm: str) -> bool:
        return False

    def can_access_customer(self, _cid: int) -> bool:
        return False


# ---------------------------------------------------------------------------
# upsert_customer tests
# ---------------------------------------------------------------------------

class TestUpsertCustomer:
    def test_insert_path_creates_new_row(self, services):
        crm, actor, _, _ = services
        cust = _make_customer()
        created = crm.upsert_customer(cust, actor)
        assert created.id is not None
        assert created.external_id == "CUST-TEST-001"
        assert created.first_name == "Jane"
        assert created.last_name == "Doe"
        assert created.email == "jane.doe@example.com"

    def test_insert_sets_timestamps(self, services):
        crm, actor, _, _ = services
        cust = _make_customer()
        created = crm.upsert_customer(cust, actor)
        assert created.created_at is not None

    def test_update_path_modifies_existing_row(self, services):
        crm, actor, _, _ = services
        original = crm.upsert_customer(_make_customer(), actor)
        original_id = original.id

        updated = crm.upsert_customer(
            _make_customer(first_name="Janet", company_name="Acme Remodeling"),
            actor,
        )
        assert updated.id == original_id
        assert updated.first_name == "Janet"
        assert updated.company_name == "Acme Remodeling"
        assert updated.external_id == "CUST-TEST-001"

    def test_no_duplicate_rows_after_multiple_upserts(self, services):
        crm, actor, _, _ = services
        crm.upsert_customer(_make_customer(), actor)
        crm.upsert_customer(_make_customer(first_name="Janet"), actor)
        crm.upsert_customer(_make_customer(phone="860-555-9999"), actor)

        customers = crm.list_customers(actor)
        matching = [c for c in customers if c.external_id == "CUST-TEST-001"]
        assert len(matching) == 1

    def test_raises_on_blank_external_id(self, services):
        crm, actor, _, _ = services
        with pytest.raises(ValueError, match="external_id"):
            crm.upsert_customer(_make_customer(external_id=""), actor)

    def test_raises_on_none_external_id(self, services):
        crm, actor, _, _ = services
        with pytest.raises(ValueError, match="external_id"):
            crm.upsert_customer(_make_customer(external_id=None), actor)

    def test_permission_enforced(self, services):
        crm, _, _, _ = services
        with pytest.raises(PermissionError):
            crm.upsert_customer(_make_customer(), _ZeroPermActor())


# ---------------------------------------------------------------------------
# update_customer tests
# ---------------------------------------------------------------------------

class TestUpdateCustomer:
    def test_update_allowed_fields(self, services):
        crm, actor, _, audit = services
        created = crm.create_customer(_make_customer(), actor)

        updated = crm.update_customer(
            created.id,
            {
                "first_name": "Janet",
                "last_name": "Smith",
                "phone": "860-555-9999",
                "status": "prospect",
            },
            actor,
        )
        assert updated is not None
        assert updated.first_name == "Janet"
        assert updated.last_name == "Smith"
        assert updated.phone == "860-555-9999"
        assert updated.status == "prospect"

    def test_update_unknown_field_rejected(self, services):
        crm, actor, _, _ = services
        created = crm.create_customer(_make_customer(), actor)
        with pytest.raises(ValueError, match="Unknown field"):
            crm.update_customer(created.id, {"non_existent_field": "val"}, actor)

    def test_update_none_value_guard(self, services):
        crm, actor, _, _ = services
        created = crm.create_customer(_make_customer(), actor)
        with pytest.raises(ValueError, match="cannot be set to None"):
            crm.update_customer(created.id, {"phone": None}, actor)

    def test_update_custom_fields_shallow_merge(self, services):
        crm, actor, _, _ = services
        created = crm.create_customer(
            _make_customer(custom_fields={"city": "Hartford", "budget": "$20k"}),
            actor,
        )

        updated = crm.update_customer(
            created.id,
            {"custom_fields": {"urgency": "High", "budget": "$25k"}},
            actor,
        )
        assert updated.custom_fields == {
            "city": "Hartford",
            "budget": "$25k",
            "urgency": "High",
        }

    def test_update_tags_replace(self, services):
        crm, actor, _, _ = services
        created = crm.create_customer(
            _make_customer(tags=["tag1", "tag2"]),
            actor,
        )

        updated = crm.update_customer(
            created.id,
            {"tags": ["tag3"]},
            actor,
        )
        assert updated.tags == ["tag3"]

    def test_update_nonexistent_returns_none(self, services):
        crm, actor, _, _ = services
        assert crm.update_customer(999999, {"first_name": "Nobody"}, actor) is None

    def test_update_permission_enforced(self, services):
        crm, actor, _, _ = services
        created = crm.create_customer(_make_customer(), actor)
        with pytest.raises(PermissionError):
            crm.update_customer(created.id, {"first_name": "Test"}, _ZeroPermActor())


# ---------------------------------------------------------------------------
# find_customer tests
# ---------------------------------------------------------------------------

class TestFindCustomer:
    @pytest.fixture(autouse=True)
    def seed_customers(self, services):
        crm, actor, _, _ = services
        crm.create_customer(
            Customer(
                external_id="CUST-001",
                first_name="Alice",
                last_name="Johnson",
                company_name="Johnson Properties",
                phone="860-111-2222",
                email="alice@example.com",
                service_address="100 Farmington Ave, Hartford, CT 06105",
                status="lead",
            ),
            actor,
        )
        crm.create_customer(
            Customer(
                external_id="CUST-002",
                first_name="Bob",
                last_name="Smith",
                company_name=None,
                phone="203-999-8888",
                email="bob.smith@testct.org",
                service_address="45 Elm St, New Haven, CT 06510",
                status="prospect",
            ),
            actor,
        )

    def test_find_by_external_id(self, services):
        crm, actor, _, _ = services
        found = crm.find_customer("cust-001", actor)
        assert found is not None
        assert found.first_name == "Alice"

    def test_find_by_phone(self, services):
        crm, actor, _, _ = services
        found = crm.find_customer("8601112222", actor)
        assert found is not None
        assert found.external_id == "CUST-001"

    def test_find_by_email(self, services):
        crm, actor, _, _ = services
        found = crm.find_customer("BOB.SMITH@TESTCT.ORG", actor)
        assert found is not None
        assert found.external_id == "CUST-002"

    def test_find_by_name(self, services):
        crm, actor, _, _ = services
        found = crm.find_customer("Alice Johnson", actor)
        assert found is not None
        assert found.external_id == "CUST-001"

    def test_find_by_company_name(self, services):
        crm, actor, _, _ = services
        found = crm.find_customer("Johnson Properties", actor)
        assert found is not None
        assert found.external_id == "CUST-001"

    def test_find_by_address(self, services):
        crm, actor, _, _ = services
        found = crm.find_customer("Farmington Ave", actor)
        assert found is not None
        assert found.external_id == "CUST-001"

    def test_find_empty_or_whitespace_returns_none(self, services):
        crm, actor, _, _ = services
        assert crm.find_customer("", actor) is None
        assert crm.find_customer("   ", actor) is None

    def test_find_no_match_returns_none(self, services):
        crm, actor, _, _ = services
        assert crm.find_customer("NonExistentCustomerName", actor) is None

    def test_find_permission_enforced(self, services):
        crm, _, _, _ = services
        with pytest.raises(PermissionError):
            crm.find_customer("Alice", _ZeroPermActor())


# ---------------------------------------------------------------------------
# HTTP Route Integration tests
# ---------------------------------------------------------------------------

class TestCustomerHTTPRoutes:
    @pytest.fixture
    def server_env(self):
        port = find_free_port()
        server = RestoriconAPIServer(db_path=":memory:", host="127.0.0.1", port=port)
        server.start(background=True)
        base_url = f"http://127.0.0.1:{port}"

        admin_user = server.auth_service.create_user(
            username="admin_test",
            plain_password="AdminPassword123",
            full_name="Admin Test",
            email="admin@testapi.com",
            role=ROLE_ADMIN,
        )
        admin_token = server.auth_service.create_token(admin_user)

        yield server, base_url, admin_token
        server.stop()

    def test_route_upsert_customer(self, server_env):
        _, base_url, admin_token = server_env
        headers = {"Authorization": f"Bearer {admin_token}"}

        payload = {
            "external_id": "CUST-API-001",
            "first_name": "Sarah",
            "last_name": "Connor",
            "phone": "860-555-0199",
            "email": "sarah@cyberdyne.com",
            "custom_fields": {"threat_level": "none"},
        }
        status, body = make_request(
            f"{base_url}/api/v1/customers/upsert",
            method="POST",
            data=payload,
            headers=headers,
        )
        assert status == 200
        assert "customer" in body
        assert body["customer"]["external_id"] == "CUST-API-001"
        assert body["customer"]["first_name"] == "Sarah"
        cust_id = body["customer"]["id"]

        # Second upsert (update path)
        update_payload = {
            "external_id": "CUST-API-001",
            "first_name": "Sarah",
            "last_name": "Connor",
            "phone": "860-555-9999",
        }
        status2, body2 = make_request(
            f"{base_url}/api/v1/customers/upsert",
            method="POST",
            data=update_payload,
            headers=headers,
        )
        assert status2 == 200
        assert body2["customer"]["id"] == cust_id
        assert body2["customer"]["phone"] == "860-555-9999"

    def test_route_update_customer(self, server_env):
        _, base_url, admin_token = server_env
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Create customer first
        create_payload = {
            "external_id": "CUST-API-002",
            "first_name": "John",
            "last_name": "Connor",
            "email": "john@resistance.org",
        }
        status, body = make_request(
            f"{base_url}/api/v1/customers/upsert",
            method="POST",
            data=create_payload,
            headers=headers,
        )
        cust_id = body["customer"]["id"]

        # Update via /api/v1/customers/{id}/update
        update_payload = {"first_name": "Johnny", "status": "active"}
        status_up, body_up = make_request(
            f"{base_url}/api/v1/customers/{cust_id}/update",
            method="POST",
            data=update_payload,
            headers=headers,
        )
        assert status_up == 200
        assert body_up["customer"]["first_name"] == "Johnny"
        assert body_up["customer"]["status"] == "active"

    def test_route_search_customer(self, server_env):
        _, base_url, admin_token = server_env
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Seed customer
        make_request(
            f"{base_url}/api/v1/customers/upsert",
            method="POST",
            data={
                "external_id": "CUST-SEARCH-1",
                "first_name": "Kyle",
                "last_name": "Reese",
                "phone": "203-555-4321",
                "email": "kyle@resistance.org",
            },
            headers=headers,
        )

        # Search by phone
        status, body = make_request(
            f"{base_url}/api/v1/customers/search?q=2035554321",
            method="GET",
            headers=headers,
        )
        assert status == 200
        assert body["customer"]["external_id"] == "CUST-SEARCH-1"

        # Search no match
        status_404, _ = make_request(
            f"{base_url}/api/v1/customers/search?q=nonexistent",
            method="GET",
            headers=headers,
        )
        assert status_404 == 404

        # Search empty q returns 400
        status_400, _ = make_request(
            f"{base_url}/api/v1/customers/search?q=",
            method="GET",
            headers=headers,
        )
        assert status_400 == 400
