"""
Unit and integration tests for User Management, RBAC, and Dynamic Custom Permissions.
"""

import json
import pytest
from restoricon_core.auth import (
    AuthService,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_MANAGER,
    ROLE_TECHNICIAN,
    PERM_READ_ALL_CUSTOMERS,
    PERM_READ_FINANCIALS,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, StaffSchedule
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.scheduling_service import SchedulingService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.finance_service import FinanceService
from restoricon_core.services.business_ops_service import BusinessOpsService
from restoricon_core.services.analytics_search_service import AnalyticsSearchService
from restoricon_core.api.routes import APIRouter


@pytest.fixture
def user_mgmt_env(tmp_path):
    db_path = str(tmp_path / "test_user_mgmt.db")
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

    # Admin User
    admin = auth.create_user("admin_chief", "AdminMaster123!", "Chief Administrator", "chief@restoricon.com", ROLE_ADMIN)
    admin_token = auth.create_token(admin)
    admin_ctx = auth.authenticate_token(admin_token)

    # Standard Technician
    tech = auth.create_user("tech_dan", "TechSecret123!", "Dan Technician", "dan@restoricon.com", ROLE_TECHNICIAN, actor_context=admin_ctx)
    tech_token = auth.create_token(tech)

    return {
        "db": db,
        "auth": auth,
        "crm": crm,
        "sched": sched,
        "router": router,
        "admin": admin,
        "admin_token": admin_token,
        "admin_ctx": admin_ctx,
        "tech": tech,
        "tech_token": tech_token,
    }


def test_user_creation_and_listing(user_mgmt_env):
    auth = user_mgmt_env["auth"]
    admin_ctx = user_mgmt_env["admin_ctx"]

    # Create manager
    mgr = auth.create_user("mgr_sarah", "MgrSecret123!", "Sarah Manager", "sarah@restoricon.com", ROLE_MANAGER, department="Remediation", actor_context=admin_ctx)
    assert mgr.id is not None
    assert mgr.username == "mgr_sarah"
    assert mgr.role == ROLE_MANAGER
    assert mgr.department == "Remediation"
    assert mgr.active == 1

    # List all users
    users = auth.list_users(admin_ctx)
    assert len(users) >= 3  # admin, tech, manager

    # List users filtered by role
    techs = auth.list_users(admin_ctx, role=ROLE_TECHNICIAN)
    assert len(techs) == 1
    assert techs[0].username == "tech_dan"


def test_user_updates_and_profile_modification(user_mgmt_env):
    auth = user_mgmt_env["auth"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    tech = user_mgmt_env["tech"]

    # Update full name, phone, department
    updated, role_changed = auth.update_user(tech.id, {"full_name": "Dan Updated", "phone": "860-555-1234", "department": "Drying Fleet"}, admin_ctx)
    assert updated is not None
    assert role_changed is False
    assert updated.full_name == "Dan Updated"
    assert updated.phone == "860-555-1234"
    assert updated.department == "Drying Fleet"


def test_role_change_revokes_existing_tokens(user_mgmt_env):
    """api_tokens.role is a login-time snapshot, so a role change must
    revoke outstanding tokens or the user keeps their old role."""
    auth = user_mgmt_env["auth"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    tech = user_mgmt_env["tech"]
    tech_token = user_mgmt_env["tech_token"]

    ctx_before = auth.authenticate_token(tech_token)
    assert ctx_before is not None
    assert ctx_before.role == ROLE_TECHNICIAN

    updated, role_changed = auth.update_user(tech.id, {"role": ROLE_MANAGER}, admin_ctx)
    assert updated.role == ROLE_MANAGER
    assert role_changed is True

    # The stale-role token must no longer authenticate
    assert auth.authenticate_token(tech_token) is None

    # A fresh login picks up the new role
    relogged = auth.authenticate_user("tech_dan", "TechSecret123!")
    new_ctx = auth.authenticate_token(auth.create_token(relogged))
    assert new_ctx.role == ROLE_MANAGER


def test_role_change_revokes_actors_own_token(user_mgmt_env):
    """Self-demotion must not leave the actor's own stale-role token alive."""
    auth = user_mgmt_env["auth"]
    admin = user_mgmt_env["admin"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    admin_token = user_mgmt_env["admin_token"]

    auth.update_user(admin.id, {"role": ROLE_MANAGER}, admin_ctx)
    assert auth.authenticate_token(admin_token) is None


def test_non_role_update_does_not_revoke_tokens(user_mgmt_env):
    """Profile edits must not force a re-login."""
    auth = user_mgmt_env["auth"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    tech = user_mgmt_env["tech"]
    tech_token = user_mgmt_env["tech_token"]

    auth.update_user(tech.id, {"full_name": "Dan Renamed", "phone": "860-555-9999"}, admin_ctx)
    ctx = auth.authenticate_token(tech_token)
    assert ctx is not None
    assert ctx.role == ROLE_TECHNICIAN

    # A no-op role write (same role) is also not a role change
    auth.update_user(tech.id, {"role": ROLE_TECHNICIAN}, admin_ctx)
    assert auth.authenticate_token(tech_token) is not None


def test_user_suspension_activation_and_token_revocation(user_mgmt_env):
    auth = user_mgmt_env["auth"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    tech = user_mgmt_env["tech"]
    tech_token = user_mgmt_env["tech_token"]

    # Verify tech token works
    ctx_before = auth.authenticate_token(tech_token)
    assert ctx_before is not None

    # Suspend tech user
    suspended = auth.set_user_active(tech.id, 0, admin_ctx)
    assert suspended.active == 0

    # Tech token must now fail authentication
    ctx_after = auth.authenticate_token(tech_token)
    assert ctx_after is None

    # Tech login must fail
    login_attempt = auth.authenticate_user("tech_dan", "TechSecret123!")
    assert login_attempt is None

    # Re-activate tech user
    activated = auth.set_user_active(tech.id, 1, admin_ctx)
    assert activated.active == 1

    # Login succeeds now
    relogin_user = auth.authenticate_user("tech_dan", "TechSecret123!")
    assert relogin_user is not None


def test_password_change_self_and_admin_reset(user_mgmt_env):
    auth = user_mgmt_env["auth"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    tech = user_mgmt_env["tech"]
    tech_token = user_mgmt_env["tech_token"]
    tech_ctx = auth.authenticate_token(tech_token)

    # 1. Tech changes own password providing valid current password
    ok = auth.change_password(tech.id, "NewTechPassword456!", tech_ctx, old_password="TechSecret123!")
    assert ok is True

    # Old password no longer works
    assert auth.authenticate_user("tech_dan", "TechSecret123!") is None
    # New password works
    assert auth.authenticate_user("tech_dan", "NewTechPassword456!") is not None

    # 2. Self-change with wrong current password must fail
    with pytest.raises(ValueError, match="Current password verification failed"):
        auth.change_password(tech.id, "AnotherPass789!", tech_ctx, old_password="WrongPassword")

    # 3. Admin resets password without needing old_password
    ok_admin = auth.change_password(tech.id, "AdminForcedPass999!", admin_ctx)
    assert ok_admin is True
    assert auth.authenticate_user("tech_dan", "AdminForcedPass999!") is not None


def test_user_deletion_and_self_deletion_prevention(user_mgmt_env):
    auth = user_mgmt_env["auth"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    admin = user_mgmt_env["admin"]
    tech = user_mgmt_env["tech"]

    # Admin cannot delete self
    with pytest.raises(ValueError, match="Cannot delete currently authenticated user"):
        auth.delete_user(admin.id, admin_ctx)

    # Admin deletes tech user
    deleted = auth.delete_user(tech.id, admin_ctx)
    assert deleted is True
    assert auth.get_user_by_id(tech.id) is None


def test_dynamic_permissions_grant_and_revoke(user_mgmt_env):
    auth = user_mgmt_env["auth"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    tech = user_mgmt_env["tech"]

    # By default, ROLE_TECHNICIAN lacks PERM_READ_ALL_CUSTOMERS and PERM_READ_FINANCIALS
    tech_token = auth.create_token(tech)
    ctx = auth.authenticate_token(tech_token)
    assert ctx.has_permission(PERM_READ_ALL_CUSTOMERS) is False
    assert ctx.has_permission(PERM_READ_FINANCIALS) is False

    # Grant PERM_READ_ALL_CUSTOMERS dynamically via custom_permissions
    updated_user = auth.set_user_permissions(tech.id, {PERM_READ_ALL_CUSTOMERS: True}, admin_ctx)
    assert updated_user.custom_permissions[PERM_READ_ALL_CUSTOMERS] is True

    # Re-authenticate token (or check new token) -> has_permission is now TRUE
    new_token = auth.create_token(updated_user)
    ctx_updated = auth.authenticate_token(new_token)
    assert ctx_updated.has_permission(PERM_READ_ALL_CUSTOMERS) is True
    assert ctx_updated.has_permission(PERM_READ_FINANCIALS) is False

    # Revoke custom permission explicitly ({PERM_READ_ALL_CUSTOMERS: False})
    auth.set_user_permissions(tech.id, {PERM_READ_ALL_CUSTOMERS: False}, admin_ctx)
    user_revoked = auth.get_user_by_id(tech.id)
    token_revoked = auth.create_token(user_revoked)
    ctx_revoked = auth.authenticate_token(token_revoked)
    assert ctx_revoked.has_permission(PERM_READ_ALL_CUSTOMERS) is False

    # Test effective permissions list calculation
    effective = auth.get_effective_permissions(user_revoked)
    assert PERM_READ_ALL_CUSTOMERS not in effective


def test_user_management_api_routes(user_mgmt_env):
    router = user_mgmt_env["router"]
    admin_token = user_mgmt_env["admin_token"]
    tech_token = user_mgmt_env["tech_token"]
    admin_headers = {"authorization": f"Bearer {admin_token}"}
    tech_headers = {"authorization": f"Bearer {tech_token}"}

    # 1. GET /api/v1/permissions/catalog
    status, _, cat_data = router.handle_request("GET", "/api/v1/permissions/catalog", admin_headers, b"")
    assert status == 200
    assert "catalog" in cat_data
    assert "crm" in cat_data["catalog"]
    assert "operations" in cat_data["catalog"]

    # 2. GET /api/v1/users (Admin succeeds, Tech fails with 403)
    status, _, users_data = router.handle_request("GET", "/api/v1/users", admin_headers, b"")
    assert status == 200
    assert "users" in users_data
    assert users_data["total"] >= 2

    status_tech, _, _ = router.handle_request("GET", "/api/v1/users", tech_headers, b"")
    assert status_tech == 403

    # 3. POST /api/v1/users (Create user via API)
    new_user_body = json.dumps({
        "username": "sales_jess",
        "password": "JessPassword123!",
        "full_name": "Jessica Sales",
        "email": "jessica@restoricon.com",
        "role": "sales",
        "department": "Commercial Intake"
    }).encode("utf-8")
    status, _, create_res = router.handle_request("POST", "/api/v1/users", admin_headers, new_user_body)
    assert status == 201
    created_id = create_res["user"]["id"]
    assert create_res["user"]["username"] == "sales_jess"

    # 4. GET /api/v1/users/{id}
    status, _, user_detail = router.handle_request("GET", f"/api/v1/users/{created_id}", admin_headers, b"")
    assert status == 200
    assert user_detail["user"]["full_name"] == "Jessica Sales"

    # 5. PUT /api/v1/users/{id}
    update_body = json.dumps({"department": "Senior Commercial Scoping"}).encode("utf-8")
    status, _, update_res = router.handle_request("PUT", f"/api/v1/users/{created_id}", admin_headers, update_body)
    assert status == 200
    assert update_res["user"]["department"] == "Senior Commercial Scoping"

    # 6. PUT /api/v1/users/{id}/permissions (Dynamic permissions via API)
    perm_payload = json.dumps({"custom_permissions": {"read:financials": True}}).encode("utf-8")
    status, _, perm_res = router.handle_request("PUT", f"/api/v1/users/{created_id}/permissions", admin_headers, perm_payload)
    assert status == 200
    assert perm_res["custom_permissions"]["read:financials"] is True

    # 7. GET /api/v1/users/{id}/permissions
    status, _, get_perm_res = router.handle_request("GET", f"/api/v1/users/{created_id}/permissions", admin_headers, b"")
    assert status == 200
    assert get_perm_res["custom_permissions"]["read:financials"] is True
    assert "read:financials" in get_perm_res["effective_permissions"]

    # 8. POST /api/v1/users/{id}/suspend
    status, _, susp_res = router.handle_request("POST", f"/api/v1/users/{created_id}/suspend", admin_headers, b"")
    assert status == 200
    assert susp_res["user"]["active"] == 0

    # 9. POST /api/v1/users/{id}/activate
    status, _, act_res = router.handle_request("POST", f"/api/v1/users/{created_id}/activate", admin_headers, b"")
    assert status == 200
    assert act_res["user"]["active"] == 1

    # 10. POST /api/v1/users/{id}/password
    pw_payload = json.dumps({"new_password": "BrandNewSecret999!"}).encode("utf-8")
    status, _, pw_res = router.handle_request("POST", f"/api/v1/users/{created_id}/password", admin_headers, pw_payload)
    assert status == 200
    assert pw_res["success"] is True

    # 11. DELETE /api/v1/users/{id}
    status, _, del_res = router.handle_request("DELETE", f"/api/v1/users/{created_id}", admin_headers, b"")
    assert status == 200
    assert del_res["deleted"] is True


# ---------------------------------------------------------------------------
# U.35 / U.36 — update_user auth defects
#   NEW-264: update_user must not be a second, token-unaware suspension path
#   NEW-266: customer-role users must carry a customer_id (cross-field invariant)
# ---------------------------------------------------------------------------


def test_update_user_active_change_rejected_and_not_persisted(user_mgmt_env):
    """U.35 resurrection regression (load-bearing): a real `active` change via
    update_user raises AND the guard runs before any SQL, so nothing persists."""
    auth = user_mgmt_env["auth"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    tech = user_mgmt_env["tech"]

    with pytest.raises(ValueError) as exc:
        auth.update_user(tech.id, {"full_name": "X", "active": 0}, admin_ctx)
    assert "suspend" in str(exc.value) or "set_user_active" in str(exc.value)

    after = auth.get_user_by_id(tech.id)
    assert after.full_name == "Dan Technician"  # unchanged — guard ran pre-SQL
    assert after.active == 1


def test_update_user_active_noop_echoback_passes(user_mgmt_env):
    """U.35: echoing the current active value back is tolerated as a no-op."""
    auth = user_mgmt_env["auth"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    tech = user_mgmt_env["tech"]

    updated, _ = auth.update_user(tech.id, {"department": "Y", "active": 1}, admin_ctx)
    assert updated.department == "Y"
    assert updated.active == 1

    # JSON-string form of the same current value also passes as a no-op
    updated2, _ = auth.update_user(tech.id, {"active": "1"}, admin_ctx)
    assert updated2.active == 1


def test_route_put_user_active_returns_400(user_mgmt_env):
    """U.35: PUT /api/v1/users/{id} with {"active": 0} -> 400, not 500/200."""
    router = user_mgmt_env["router"]
    admin_token = user_mgmt_env["admin_token"]
    tech = user_mgmt_env["tech"]
    admin_headers = {"authorization": f"Bearer {admin_token}"}

    body = json.dumps({"active": 0}).encode("utf-8")
    status, _, res = router.handle_request("PUT", f"/api/v1/users/{tech.id}", admin_headers, body)
    assert status == 400
    assert "suspend" in res["error"] or "set_user_active" in res["error"]


def test_update_user_role_customer_without_customer_id_rejected(user_mgmt_env):
    """U.36: moving a user to the customer role with no customer_id is rejected."""
    auth = user_mgmt_env["auth"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    tech = user_mgmt_env["tech"]

    with pytest.raises(ValueError) as exc:
        auth.update_user(tech.id, {"role": "customer"}, admin_ctx)
    assert str(exc.value) == "Customer user role requires an associated customer_id"


def test_update_user_role_customer_with_customer_id_accepted(user_mgmt_env):
    """U.36: role+customer_id together is accepted; role change still revokes tokens."""
    auth = user_mgmt_env["auth"]
    crm = user_mgmt_env["crm"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    tech = user_mgmt_env["tech"]
    tech_token = user_mgmt_env["tech_token"]

    cust = crm.create_customer(
        Customer(first_name="Cara", last_name="Client", email="cara@client.com"),
        admin_ctx,
    )

    assert auth.authenticate_token(tech_token) is not None
    updated, role_changed = auth.update_user(
        tech.id, {"role": "customer", "customer_id": cust.id}, admin_ctx
    )
    assert updated.role == ROLE_CUSTOMER
    assert role_changed is True
    assert updated.customer_id == cust.id
    # role change -> outstanding tokens revoked
    assert auth.authenticate_token(tech_token) is None


def test_update_user_move_away_from_customer_role(user_mgmt_env):
    """U.36: leaving the customer role succeeds; a stale customer_id may remain."""
    auth = user_mgmt_env["auth"]
    crm = user_mgmt_env["crm"]
    admin_ctx = user_mgmt_env["admin_ctx"]

    cust = crm.create_customer(
        Customer(first_name="Cody", last_name="Customer", email="cody@client.com"),
        admin_ctx,
    )
    cust_user = auth.create_user(
        "cody_c", "CodyPass123!", "Cody Customer", "cody@client.com",
        ROLE_CUSTOMER, customer_id=cust.id, actor_context=admin_ctx,
    )

    updated, role_changed = auth.update_user(cust_user.id, {"role": ROLE_TECHNICIAN}, admin_ctx)
    assert updated.role == ROLE_TECHNICIAN
    assert role_changed is True


def test_create_user_customer_role_without_customer_id_still_raises(user_mgmt_env):
    """U.36 helper-refactor regression guard: create_user behaviour unchanged."""
    auth = user_mgmt_env["auth"]
    admin_ctx = user_mgmt_env["admin_ctx"]

    with pytest.raises(ValueError) as exc:
        auth.create_user(
            "bad_cust", "BadPass123!", "Bad Customer", "bad@client.com",
            ROLE_CUSTOMER, customer_id=None, actor_context=admin_ctx,
        )
    assert str(exc.value) == "Customer user role requires an associated customer_id"


def test_update_user_duplicate_email_maps_to_400(user_mgmt_env):
    """U.35 (in scope): sqlite3.IntegrityError -> ValueError at the boundary,
    and 400 (not 500) at the route."""
    auth = user_mgmt_env["auth"]
    router = user_mgmt_env["router"]
    admin = user_mgmt_env["admin"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    admin_token = user_mgmt_env["admin_token"]
    tech = user_mgmt_env["tech"]

    with pytest.raises(ValueError):
        auth.update_user(tech.id, {"email": admin.email}, admin_ctx)

    admin_headers = {"authorization": f"Bearer {admin_token}"}
    body = json.dumps({"email": admin.email}).encode("utf-8")
    status, _, res = router.handle_request("PUT", f"/api/v1/users/{tech.id}", admin_headers, body)
    assert status == 400


def test_update_user_unlink_customer_id_while_stored_role_is_customer(user_mgmt_env):
    """U.36: `effective_role` fallback to the STORED role is load-bearing —
    clearing customer_id on a customer-role user (role not in the patch) is
    rejected, and the row is left untouched."""
    auth = user_mgmt_env["auth"]
    crm = user_mgmt_env["crm"]
    admin_ctx = user_mgmt_env["admin_ctx"]

    cust = crm.create_customer(
        Customer(first_name="Cleo", last_name="Client", email="cleo@client.com"),
        admin_ctx,
    )
    cust_user = auth.create_user(
        "cleo_c", "CleoPass123!", "Cleo Client", "cleo@client.com",
        ROLE_CUSTOMER, customer_id=cust.id, actor_context=admin_ctx,
    )

    with pytest.raises(ValueError) as exc:
        auth.update_user(cust_user.id, {"customer_id": None}, admin_ctx)
    assert str(exc.value) == "Customer user role requires an associated customer_id"

    after = auth.get_user_by_id(cust_user.id)
    assert after.customer_id == cust.id
    assert after.role == ROLE_CUSTOMER


def test_update_user_nonexistent_id_returns_none_false_not_tuple_error(user_mgmt_env):
    """Regression guard: update_user's return type is Tuple[Optional[User], bool]
    everywhere (NEW-310), so the missing-row branch must return (None, False)
    rather than a bare None -- a bare None broke the one production call site's
    `updated, role_changed = self.auth.update_user(...)` unpack with a
    TypeError, 500-ing instead of 404-ing a PUT/POST to a nonexistent user."""
    auth = user_mgmt_env["auth"]
    router = user_mgmt_env["router"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    admin_token = user_mgmt_env["admin_token"]

    nonexistent_id = 999999

    updated, role_changed = auth.update_user(nonexistent_id, {"full_name": "Ghost"}, admin_ctx)
    assert updated is None
    assert role_changed is False

    admin_headers = {"authorization": f"Bearer {admin_token}"}
    body = json.dumps({"full_name": "Ghost"}).encode("utf-8")
    status, _, res = router.handle_request(
        "PUT", f"/api/v1/users/{nonexistent_id}", admin_headers, body
    )
    assert status == 404

    status, _, res = router.handle_request(
        "POST", f"/api/v1/users/{nonexistent_id}", admin_headers, body
    )
    assert status == 404


# ---------------------------------------------------------------------------
# Delete-buttons round (Ish 2026-09-11): active-reference precheck + delete
# ---------------------------------------------------------------------------


def test_get_active_staff_schedules_for_user_empty_and_populated(user_mgmt_env):
    sched = user_mgmt_env["sched"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    tech = user_mgmt_env["tech"]

    assert sched.get_active_staff_schedules_for_user(tech.id, admin_ctx) == []

    created = sched.create_staff_schedule(
        StaffSchedule(
            user_id=tech.id, title="Job site visit",
            start_time="2027-01-05T09:00:00", end_time="2027-01-05T11:00:00",
            status="scheduled", notes=None,
        ),
        admin_ctx,
    )

    active = sched.get_active_staff_schedules_for_user(tech.id, admin_ctx)
    assert len(active) == 1
    assert active[0]["id"] == created.id
    assert active[0]["title"] == "Job site visit"
    assert active[0]["status"] == "scheduled"

    # A completed (terminal) schedule is not "active".
    sched.update_staff_schedule(created.id, {"status": "completed"}, admin_ctx)
    assert sched.get_active_staff_schedules_for_user(tech.id, admin_ctx) == []


def test_route_delete_user_blocked_when_active_staff_schedule(user_mgmt_env):
    """A 'scheduled' staff_schedules row blocks the DELETE (400, itemized)."""
    router = user_mgmt_env["router"]
    sched = user_mgmt_env["sched"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    admin_token = user_mgmt_env["admin_token"]
    tech = user_mgmt_env["tech"]
    admin_headers = {"authorization": f"Bearer {admin_token}"}

    created = sched.create_staff_schedule(
        StaffSchedule(
            user_id=tech.id, title="Job site visit",
            start_time="2027-01-05T09:00:00", end_time="2027-01-05T11:00:00",
            status="scheduled", notes=None,
        ),
        admin_ctx,
    )

    status, _, res = router.handle_request("DELETE", f"/api/v1/users/{tech.id}", admin_headers, b"")
    assert status == 400
    assert str(created.id) in res["error"]
    assert "Job site visit" in res["error"]

    # User must still exist -- the delete was actually blocked, not a no-op success.
    auth = user_mgmt_env["auth"]
    assert auth.get_user_by_id(tech.id) is not None


def test_route_get_active_references_for_user(user_mgmt_env):
    router = user_mgmt_env["router"]
    sched = user_mgmt_env["sched"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    admin_token = user_mgmt_env["admin_token"]
    tech = user_mgmt_env["tech"]
    admin_headers = {"authorization": f"Bearer {admin_token}"}

    status, _, res = router.handle_request(
        "GET", f"/api/v1/users/{tech.id}/active-references", admin_headers, b""
    )
    assert status == 200
    assert res["active_references"] == []

    sched.create_staff_schedule(
        StaffSchedule(
            user_id=tech.id, title="Emergency callout",
            start_time="2027-02-01T09:00:00", end_time="2027-02-01T11:00:00",
            status="scheduled", notes=None,
        ),
        admin_ctx,
    )

    status, _, res = router.handle_request(
        "GET", f"/api/v1/users/{tech.id}/active-references", admin_headers, b""
    )
    assert status == 200
    assert len(res["active_references"]) == 1
    assert res["active_references"][0]["title"] == "Emergency callout"


def test_route_delete_user_succeeds_with_only_terminal_staff_schedule(user_mgmt_env):
    router = user_mgmt_env["router"]
    sched = user_mgmt_env["sched"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    admin_token = user_mgmt_env["admin_token"]
    tech = user_mgmt_env["tech"]
    admin_headers = {"authorization": f"Bearer {admin_token}"}

    sched.create_staff_schedule(
        StaffSchedule(
            user_id=tech.id, title="Old completed job",
            start_time="2020-01-01T09:00:00", end_time="2020-01-01T11:00:00",
            status="completed", notes=None,
        ),
        admin_ctx,
    )

    status, _, res = router.handle_request("DELETE", f"/api/v1/users/{tech.id}", admin_headers, b"")
    assert status == 200
    assert res["deleted"] is True


def test_delete_user_terminal_staff_schedule_is_archived_not_lost(user_mgmt_env):
    """Archive-then-delete (Ish 2026-09-11 policy decision, NEW-493 fix):
    staff_schedules.user_id still carries FOREIGN KEY ... ON DELETE CASCADE,
    so the live staff_schedules row for a deleted user is still gone -- but
    its content now survives in staff_schedules_archive, copied there in
    the same transaction immediately before DELETE FROM users. This
    replaces the old pinning test for the pre-fix data-loss behavior."""
    auth = user_mgmt_env["auth"]
    sched = user_mgmt_env["sched"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    tech = user_mgmt_env["tech"]

    terminal = sched.create_staff_schedule(
        StaffSchedule(
            user_id=tech.id, title="Old completed job",
            start_time="2020-01-01T09:00:00", end_time="2020-01-01T11:00:00",
            status="completed", notes="wrapped up fine",
        ),
        admin_ctx,
    )

    deleted = auth.delete_user(tech.id, admin_ctx)
    assert deleted is True

    conn = user_mgmt_env["db"].get_connection()
    row = conn.execute(
        "SELECT * FROM staff_schedules WHERE id = ?;", (terminal.id,)
    ).fetchone()
    assert row is None  # cascade-deleted, still expected

    archived = conn.execute(
        "SELECT * FROM staff_schedules_archive WHERE original_schedule_id = ?;",
        (terminal.id,),
    ).fetchone()
    assert archived is not None
    assert archived["original_user_id"] == tech.id
    assert archived["original_username"] == tech.username
    assert archived["title"] == "Old completed job"
    assert archived["start_time"] == "2020-01-01T09:00:00"
    assert archived["end_time"] == "2020-01-01T11:00:00"
    assert archived["status"] == "completed"
    assert archived["notes"] == "wrapped up fine"
    assert archived["archived_reason"] == "user_deleted"
    assert archived["archived_at"]  # non-empty timestamp


def test_delete_user_multiple_terminal_staff_schedules_all_archived(user_mgmt_env):
    """Both 'completed' and 'cancelled' terminal rows get archived -- not
    just the first one found."""
    auth = user_mgmt_env["auth"]
    sched = user_mgmt_env["sched"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    tech = user_mgmt_env["tech"]

    completed = sched.create_staff_schedule(
        StaffSchedule(
            user_id=tech.id, title="Finished job",
            start_time="2020-01-01T09:00:00", end_time="2020-01-01T11:00:00",
            status="completed", notes=None,
        ),
        admin_ctx,
    )
    cancelled = sched.create_staff_schedule(
        StaffSchedule(
            user_id=tech.id, title="Called off job",
            start_time="2020-02-01T09:00:00", end_time="2020-02-01T11:00:00",
            status="cancelled", notes=None,
        ),
        admin_ctx,
    )

    deleted = auth.delete_user(tech.id, admin_ctx)
    assert deleted is True

    conn = user_mgmt_env["db"].get_connection()
    archived_ids = {
        row["original_schedule_id"]
        for row in conn.execute(
            "SELECT original_schedule_id FROM staff_schedules_archive WHERE original_user_id = ?;",
            (tech.id,),
        ).fetchall()
    }
    assert archived_ids == {completed.id, cancelled.id}


def test_delete_user_archive_insert_failure_rolls_back_whole_delete(user_mgmt_env, monkeypatch):
    """Transaction atomicity: if an archive INSERT fails PARTWAY through --
    i.e. after at least one row has already been successfully inserted --
    the whole delete_user() call must roll back, including undoing that
    already-succeeded insert. Two terminal rows are created and the
    wrapper fails only the SECOND INSERT INTO staff_schedules_archive, so
    there is something real to roll back (failing on the first insert,
    with only one row total, cannot distinguish "rolled back" from
    "never inserted" -- this must fail after a real partial write).
    Simulated by wrapping the real connection so the second archive
    INSERT raises while every other statement (including the first
    archive INSERT) passes through unchanged -- this keeps the real
    connection object (and its transaction state) doing the actual work,
    so rollback behavior is real sqlite3 behavior, not mocked."""
    import sqlite3

    auth = user_mgmt_env["auth"]
    sched = user_mgmt_env["sched"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    tech = user_mgmt_env["tech"]

    first = sched.create_staff_schedule(
        StaffSchedule(
            user_id=tech.id, title="Old completed job",
            start_time="2020-01-01T09:00:00", end_time="2020-01-01T11:00:00",
            status="completed", notes=None,
        ),
        admin_ctx,
    )
    second = sched.create_staff_schedule(
        StaffSchedule(
            user_id=tech.id, title="Another completed job",
            start_time="2020-02-01T09:00:00", end_time="2020-02-01T11:00:00",
            status="completed", notes=None,
        ),
        admin_ctx,
    )

    real_conn = user_mgmt_env["db"].get_connection()

    class _FailingSecondArchiveInsertConn:
        def __init__(self, real):
            self._real = real
            self._archive_insert_count = 0

        def execute(self, sql, params=()):
            if "INSERT INTO staff_schedules_archive" in sql:
                self._archive_insert_count += 1
                if self._archive_insert_count == 2:
                    raise sqlite3.OperationalError("simulated archive insert failure")
            return self._real.execute(sql, params)

        def __enter__(self):
            self._real.__enter__()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return self._real.__exit__(exc_type, exc_val, exc_tb)

    wrapper = _FailingSecondArchiveInsertConn(real_conn)
    monkeypatch.setattr(user_mgmt_env["db"], "get_connection", lambda: wrapper)

    with pytest.raises(sqlite3.OperationalError):
        auth.delete_user(tech.id, admin_ctx)

    # Confirm the wrapper actually reached and failed on the second insert
    # (i.e. this test exercises a real partial write, not a first-insert no-op).
    assert wrapper._archive_insert_count == 2

    # Undo the monkeypatch to inspect real state with the real connection.
    monkeypatch.undo()

    assert auth.get_user_by_id(tech.id) is not None  # NOT deleted

    conn = user_mgmt_env["db"].get_connection()
    for sched_id in (first.id, second.id):
        row = conn.execute(
            "SELECT * FROM staff_schedules WHERE id = ?;", (sched_id,)
        ).fetchone()
        assert row is not None  # live schedule rows still present, cascade never ran

        archived = conn.execute(
            "SELECT * FROM staff_schedules_archive WHERE original_schedule_id = ?;",
            (sched_id,),
        ).fetchone()
        assert archived is None  # neither row survived the rollback, including the first (already-inserted) one


def test_delete_user_blocked_by_active_schedule_archives_nothing(user_mgmt_env):
    """Regression guard: if the active-reference precheck blocks the
    delete (a 'scheduled' row exists), nothing is archived and nothing is
    deleted -- no partial archive on a blocked delete."""
    router = user_mgmt_env["router"]
    auth = user_mgmt_env["auth"]
    sched = user_mgmt_env["sched"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    admin_token = user_mgmt_env["admin_token"]
    tech = user_mgmt_env["tech"]
    admin_headers = {"authorization": f"Bearer {admin_token}"}

    sched.create_staff_schedule(
        StaffSchedule(
            user_id=tech.id, title="Upcoming job",
            start_time="2027-01-05T09:00:00", end_time="2027-01-05T11:00:00",
            status="scheduled", notes=None,
        ),
        admin_ctx,
    )

    status, _, res = router.handle_request("DELETE", f"/api/v1/users/{tech.id}", admin_headers, b"")
    assert status == 400

    # User still exists -- delete was actually blocked.
    assert auth.get_user_by_id(tech.id) is not None

    conn = user_mgmt_env["db"].get_connection()
    archived = conn.execute(
        "SELECT * FROM staff_schedules_archive WHERE original_user_id = ?;", (tech.id,)
    ).fetchall()
    assert archived == []


def test_route_get_staff_schedules_archive_rbac_and_filter(user_mgmt_env):
    """New read-only archive route: RBAC-gated (same tier as staff-schedules
    reads) and filterable by original_username."""
    router = user_mgmt_env["router"]
    auth = user_mgmt_env["auth"]
    sched = user_mgmt_env["sched"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    admin_token = user_mgmt_env["admin_token"]
    tech_token = user_mgmt_env["tech_token"]
    tech = user_mgmt_env["tech"]
    admin_headers = {"authorization": f"Bearer {admin_token}"}
    tech_headers = {"authorization": f"Bearer {tech_token}"}

    # RBAC: a technician (role has no PERM_READ_STAFF_SCHEDULES) is
    # forbidden, checked BEFORE tech is deleted below (delete_user also
    # revokes tech's own tokens).
    status, _, _ = router.handle_request(
        "GET", "/api/v1/staff-schedules-archive", tech_headers, b""
    )
    assert status == 403

    sched.create_staff_schedule(
        StaffSchedule(
            user_id=tech.id, title="Old completed job",
            start_time="2020-01-01T09:00:00", end_time="2020-01-01T11:00:00",
            status="completed", notes=None,
        ),
        admin_ctx,
    )
    tech_username = tech.username
    auth.delete_user(tech.id, admin_ctx)

    # An admin (has PERM_READ_STAFF_SCHEDULES) can read the archived row.
    status, _, res = router.handle_request(
        "GET", "/api/v1/staff-schedules-archive", admin_headers, b""
    )
    assert status == 200
    assert len(res["archived_schedules"]) == 1
    assert res["archived_schedules"][0]["original_username"] == tech_username

    # ...filtered by original_username finds the same row.
    status, _, res = router.handle_request(
        "GET", f"/api/v1/staff-schedules-archive?original_username={tech_username}", admin_headers, b""
    )
    assert status == 200
    assert len(res["archived_schedules"]) == 1
    assert res["archived_schedules"][0]["title"] == "Old completed job"

    # A nonexistent username filter finds nothing.
    status, _, res = router.handle_request(
        "GET", "/api/v1/staff-schedules-archive?original_username=nobody_here", admin_headers, b""
    )
    assert status == 200
    assert res["archived_schedules"] == []


def test_route_delete_user_active_references_rbac_403(user_mgmt_env):
    """A non-privileged actor gets 403 on both the reference-check and the delete."""
    router = user_mgmt_env["router"]
    tech_token = user_mgmt_env["tech_token"]
    admin = user_mgmt_env["admin"]
    tech_headers = {"authorization": f"Bearer {tech_token}"}

    status, _, _ = router.handle_request(
        "GET", f"/api/v1/users/{admin.id}/active-references", tech_headers, b""
    )
    assert status == 403

    status, _, _ = router.handle_request(
        "DELETE", f"/api/v1/users/{admin.id}", tech_headers, b""
    )
    assert status == 403


def test_route_delete_user_rbac_403_even_with_active_reference_present(user_mgmt_env):
    """Regression guard: the active-reference re-check in the DELETE branch
    is deliberately unguarded/unRBAC'd (it must not additionally require
    PERM_READ_STAFF_SCHEDULES on top of PERM_MANAGE_USERS), so the explicit
    PERM_MANAGE_USERS gate must run BEFORE it, not after. A non-privileged
    actor attempting to delete a DIFFERENT user who genuinely has an active
    staff schedule must still get a bare 403 -- not a 400 whose body leaks
    that schedule's title/date to someone with no delete permission at all.
    (Without the explicit pre-gate, execution reaches the reference query
    and 400s with the itemized schedule before ever calling delete_user,
    which is where the only permission check used to live.)"""
    router = user_mgmt_env["router"]
    auth = user_mgmt_env["auth"]
    sched = user_mgmt_env["sched"]
    admin_ctx = user_mgmt_env["admin_ctx"]
    admin_token = user_mgmt_env["admin_token"]
    tech = user_mgmt_env["tech"]
    tech_token = user_mgmt_env["tech_token"]
    admin_headers = {"authorization": f"Bearer {admin_token}"}
    tech_headers = {"authorization": f"Bearer {tech_token}"}

    # A second, no-permissions user attempting to delete `tech`.
    bystander = auth.create_user(
        "bystander_bo", "BystanderPass123!", "Bo Bystander", "bo@restoricon.com",
        ROLE_TECHNICIAN, actor_context=admin_ctx,
    )
    bystander_token = auth.create_token(bystander)
    bystander_headers = {"authorization": f"Bearer {bystander_token}"}

    sched.create_staff_schedule(
        StaffSchedule(
            user_id=tech.id, title="Sensitive job site visit",
            start_time="2027-03-01T09:00:00", end_time="2027-03-01T11:00:00",
            status="scheduled", notes=None,
        ),
        admin_ctx,
    )

    status, _, res = router.handle_request("DELETE", f"/api/v1/users/{tech.id}", bystander_headers, b"")
    assert status == 403
    assert "Sensitive job site visit" not in str(res)

    # Sanity: the admin (who DOES hold PERM_MANAGE_USERS) is still blocked
    # with the itemized 400, confirming the reference check itself still
    # runs for a privileged actor.
    status, _, res = router.handle_request("DELETE", f"/api/v1/users/{tech.id}", admin_headers, b"")
    assert status == 400
    assert "Sensitive job site visit" in res["error"]
