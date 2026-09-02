"""
Unit and integration tests for User Management, RBAC, and Dynamic Custom Permissions.
"""

import json
import pytest
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_MANAGER,
    ROLE_TECHNICIAN,
    PERM_MANAGE_USERS,
    PERM_READ_ALL_CUSTOMERS,
    PERM_WRITE_CUSTOMERS,
    PERM_READ_FINANCIALS,
    PERMISSIONS_CATALOG,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer
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
    updated = auth.update_user(tech.id, {"full_name": "Dan Updated", "phone": "860-555-1234", "department": "Drying Fleet"}, admin_ctx)
    assert updated is not None
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

    updated = auth.update_user(tech.id, {"role": ROLE_MANAGER}, admin_ctx)
    assert updated.role == ROLE_MANAGER

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
