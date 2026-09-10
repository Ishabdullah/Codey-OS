"""
Unit + integration tests for the business_profile public-contact fields
(business_phone, business_email, license_number) added for the admin
dashboard. Covers the additive migration on a legacy DB file, the
service round-trip, the HTTP route round-trip, and the full-row-replace
contract of upsert_business_profile.
"""

import socket
import sqlite3

import pytest

from restoricon_core.api.server import RestoriconAPIServer
from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import BusinessProfile
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService

from tests.test_restoricon_core.test_api import make_request


# The business_profile DDL as it stood before the public-contact columns
# were added (10 columns, ending at updated_at) -- used to exercise the
# ALTER TABLE branch of _migrate_schema(), which an in-memory DB can
# never hit because CREATE TABLE always includes the new columns.
_LEGACY_BUSINESS_PROFILE_DDL = """
CREATE TABLE business_profile (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    configured INTEGER NOT NULL DEFAULT 0 CHECK(configured IN (0, 1)),
    aigentik_name TEXT,
    agent_name_set INTEGER NOT NULL DEFAULT 0 CHECK(agent_name_set IN (0, 1)),
    owner_name TEXT,
    business_name TEXT,
    business_description TEXT,
    onboarding_sent INTEGER NOT NULL DEFAULT 0 CHECK(onboarding_sent IN (0, 1)),
    setup_date TEXT,
    updated_at TEXT NOT NULL
);
"""


@pytest.fixture
def ops(tmp_path):
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    automation = AutomationService(db, audit)
    auth = AuthService(db)
    user = auth.create_user(
        username="admin", plain_password="Password123", full_name="Admin",
        email="admin@test.com", role=ROLE_ADMIN,
    )
    actor = AuthContext(user_id=user.id, username="admin", role=ROLE_ADMIN, actor_type="human")
    return automation, actor


def test_business_profile_contact_migration_adds_columns_to_legacy_db(tmp_path):
    db_path = tmp_path / "legacy_bp.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_LEGACY_BUSINESS_PROFILE_DDL)
    conn.execute(
        "INSERT INTO business_profile "
        "(id, configured, aigentik_name, agent_name_set, owner_name, business_name, updated_at) "
        "VALUES (1, 1, 'Codey', 1, 'Ish', 'Restoricon, LLC', '2020-01-01T00:00:00Z');"
    )
    conn.commit()
    conn.close()

    db = DatabaseManager(str(db_path))
    db.init_schema()
    conn = db.get_connection()
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(business_profile);")}
    assert {"business_phone", "business_email", "license_number"} <= cols

    row = conn.execute(
        "SELECT business_name, aigentik_name, owner_name, configured, "
        "business_phone, business_email, license_number FROM business_profile WHERE id = 1;"
    ).fetchone()
    assert row["business_name"] == "Restoricon, LLC"
    assert row["aigentik_name"] == "Codey"
    assert row["owner_name"] == "Ish"
    assert row["configured"] == 1
    assert row["business_phone"] is None
    assert row["business_email"] is None
    assert row["license_number"] is None

    auth = AuthService(db)
    user = auth.create_user(
        username="admin", plain_password="Password123", full_name="Admin",
        email="admin@test.com", role=ROLE_ADMIN,
    )
    actor = AuthContext(user_id=user.id, username="admin", role=ROLE_ADMIN, actor_type="human")
    automation = AutomationService(db, AuditService(db))
    automation.get_business_profile(actor)  # must not raise
    db.close()

    # Second open against the now-migrated file must not raise
    # "duplicate column name".
    db2 = DatabaseManager(str(db_path))
    db2.init_schema()
    cols2 = {row["name"] for row in db2.get_connection().execute("PRAGMA table_info(business_profile);")}
    assert {"business_phone", "business_email", "license_number"} <= cols2
    db2.close()


def test_business_profile_contact_fields_round_trip(ops):
    automation, actor = ops
    automation.upsert_business_profile(
        BusinessProfile(
            business_name="Restoricon, LLC",
            business_phone="PHONE-SENTINEL",
            business_email="EMAIL-SENTINEL",
            license_number="LIC-SENTINEL",
        ),
        actor,
    )
    fetched = automation.get_business_profile(actor)
    assert fetched.business_phone == "PHONE-SENTINEL"
    assert fetched.business_email == "EMAIL-SENTINEL"
    assert fetched.license_number == "LIC-SENTINEL"


def test_business_profile_identity_fields_round_trip(ops):
    automation, actor = ops
    automation.upsert_business_profile(
        BusinessProfile(
            business_name="Restoricon, LLC",
            owner_name="OWNER-SENTINEL",
            aigentik_name="AGENT-SENTINEL",
            agent_name_set=1,
        ),
        actor,
    )
    fetched = automation.get_business_profile(actor)
    assert fetched.owner_name == "OWNER-SENTINEL"
    assert fetched.aigentik_name == "AGENT-SENTINEL"
    assert fetched.agent_name_set == 1


def test_to_dict_emits_new_keys():
    d = BusinessProfile().to_dict()
    assert "business_phone" in d
    assert "business_email" in d
    assert "license_number" in d


@pytest.fixture
def api_server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = RestoriconAPIServer(db_path=":memory:", host="127.0.0.1", port=port)
    server.start(background=True)
    base_url = f"http://127.0.0.1:{port}"
    server.auth_service.create_user(
        username="admin", plain_password="AdminSecretPassword123",
        full_name="Admin Boss", email="admin@restoricon.com", role=ROLE_ADMIN,
    )
    yield base_url
    server.stop()


def _admin_headers(base_url):
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    return {"Authorization": f"Bearer {body['token']}"}


def test_business_profile_route_round_trip(api_server):
    base_url = api_server
    headers = _admin_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/business-profile",
        method="POST",
        headers=headers,
        data={
            "business_name": "Restoricon, LLC",
            "business_phone": "PHONE-SENTINEL",
            "business_email": "EMAIL-SENTINEL",
            "license_number": "LIC-SENTINEL",
        },
    )
    assert status == 200

    status, body = make_request(f"{base_url}/api/v1/business-profile", headers=headers)
    assert status == 200
    profile = body["business_profile"]
    assert profile["business_phone"] == "PHONE-SENTINEL"
    assert profile["business_email"] == "EMAIL-SENTINEL"
    assert profile["license_number"] == "LIC-SENTINEL"


def test_business_profile_route_identity_round_trip(api_server):
    base_url = api_server
    headers = _admin_headers(base_url)

    status, body = make_request(
        f"{base_url}/api/v1/business-profile",
        method="POST",
        headers=headers,
        data={
            "business_name": "Restoricon, LLC",
            "owner_name": "OWNER-SENTINEL",
            "aigentik_name": "AGENT-SENTINEL",
            "agent_name_set": 1,
        },
    )
    assert status == 200

    status, body = make_request(f"{base_url}/api/v1/business-profile", headers=headers)
    assert status == 200
    profile = body["business_profile"]
    assert profile["owner_name"] == "OWNER-SENTINEL"
    assert profile["aigentik_name"] == "AGENT-SENTINEL"
    assert profile["agent_name_set"] == 1


def test_business_profile_upsert_is_full_row_replace(ops):
    automation, actor = ops
    automation.upsert_business_profile(
        BusinessProfile(
            business_name="Restoricon, LLC",
            business_phone="PHONE-SENTINEL",
            business_email="EMAIL-SENTINEL",
            license_number="LIC-SENTINEL",
            owner_name="Ish",
            aigentik_name="Codey",
            agent_name_set=1,
        ),
        actor,
    )
    # A partial body (only business_name) must reset every unmentioned
    # column to its BusinessProfile dataclass default.
    automation.upsert_business_profile(BusinessProfile(business_name="Just The Name"), actor)
    fetched = automation.get_business_profile(actor)
    defaults = BusinessProfile()
    assert fetched.business_name == "Just The Name"
    assert fetched.business_phone == defaults.business_phone
    assert fetched.business_email == defaults.business_email
    assert fetched.license_number == defaults.license_number
    assert fetched.owner_name == defaults.owner_name
    assert fetched.aigentik_name == defaults.aigentik_name
    assert fetched.agent_name_set == defaults.agent_name_set


def test_schedule_config_route_booking_window_round_trip(api_server):
    base_url = api_server
    headers = _admin_headers(base_url)

    status, _ = make_request(
        f"{base_url}/api/v1/schedule-config",
        method="POST",
        headers=headers,
        data={"booking_window_days": 90},
    )
    assert status == 200

    status, body = make_request(f"{base_url}/api/v1/schedule-config", headers=headers)
    assert status == 200
    assert body["schedule_config"]["booking_window_days"] == 90


def test_schedule_config_route_is_full_row_replace(api_server):
    """Pins NEW-466: schedule-config POST is a full-row replace. A body
    that omits working_hours after it was set blanks it back to {}."""
    base_url = api_server
    headers = _admin_headers(base_url)

    status, _ = make_request(
        f"{base_url}/api/v1/schedule-config",
        method="POST",
        headers=headers,
        data={"working_hours": {"mon": {"start": "09:00", "end": "17:00"}}},
    )
    assert status == 200

    status, body = make_request(f"{base_url}/api/v1/schedule-config", headers=headers)
    assert body["schedule_config"]["working_hours"] == {"mon": {"start": "09:00", "end": "17:00"}}

    # Omit working_hours -> ScheduleConfig dataclass default {} -> row blanked.
    status, _ = make_request(
        f"{base_url}/api/v1/schedule-config",
        method="POST",
        headers=headers,
        data={"booking_window_days": 90},
    )
    assert status == 200

    status, body = make_request(f"{base_url}/api/v1/schedule-config", headers=headers)
    assert body["schedule_config"]["working_hours"] == {}
