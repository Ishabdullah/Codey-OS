"""
Unit tests for AuthService, token management, password hashing, and RBAC matrix.
"""

import pytest
from restoricon_core.auth import (
    AuthService,
    AuthContext,
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SALES,
    ROLE_PROJECT_MANAGER,
    ROLE_TECHNICIAN,
    ROLE_AI_AGENT,
    ROLE_CUSTOMER,
    PERM_READ_ALL_CUSTOMERS,
    PERM_READ_OWN_CUSTOMER,
    PERM_MANAGE_USERS,
    PERM_READ_AUDIT_LOG,
    PERM_WRITE_FINANCIALS,
)
from restoricon_core.database import DatabaseManager


@pytest.fixture
def auth_service():
    db = DatabaseManager(":memory:")
    return AuthService(db)


def test_password_hashing_and_verification(auth_service):
    raw_pass = "SuperSecret123!"
    hashed = auth_service.hash_password(raw_pass)
    
    assert hashed.startswith("pbkdf2_sha256$")
    assert auth_service.verify_password(raw_pass, hashed) is True
    assert auth_service.verify_password("WrongPassword", hashed) is False
    assert auth_service.verify_password(raw_pass, "corrupted_hash") is False


def test_user_creation_and_authentication(auth_service):
    user = auth_service.create_user(
        username="admin_user",
        plain_password="AdminPassword123",
        full_name="Admin Boss",
        email="admin@restoricon.com",
        role=ROLE_ADMIN,
    )
    assert user.id is not None
    assert user.role == ROLE_ADMIN

    # Test login success
    authed = auth_service.authenticate_user("admin_user", "AdminPassword123")
    assert authed is not None
    assert authed.id == user.id

    # Test email login
    authed_email = auth_service.authenticate_user("admin@restoricon.com", "AdminPassword123")
    assert authed_email is not None
    assert authed_email.id == user.id

    # Test invalid password
    assert auth_service.authenticate_user("admin_user", "BadPass") is None


def test_token_creation_and_authentication(auth_service):
    user = auth_service.create_user(
        username="tech_john",
        plain_password="Password123",
        full_name="John Tech",
        email="john@restoricon.com",
        role=ROLE_TECHNICIAN,
    )

    token = auth_service.create_token(user)
    assert isinstance(token, str) and len(token) > 20

    # Authenticate token
    ctx = auth_service.authenticate_token(token)
    assert ctx is not None
    assert ctx.user_id == user.id
    assert ctx.role == ROLE_TECHNICIAN
    assert ctx.actor_type == "human"

    # Revoke token
    revoked = auth_service.revoke_token(token)
    assert revoked is True
    assert auth_service.authenticate_token(token) is None


def test_rbac_permissions():
    admin_ctx = AuthContext(user_id=1, username="admin", role=ROLE_ADMIN, actor_type="human")
    assert admin_ctx.has_permission(PERM_MANAGE_USERS) is True
    assert admin_ctx.has_permission(PERM_READ_AUDIT_LOG) is True
    assert admin_ctx.has_permission(PERM_WRITE_FINANCIALS) is True
    assert admin_ctx.can_access_customer(99) is True

    tech_ctx = AuthContext(user_id=2, username="tech", role=ROLE_TECHNICIAN, actor_type="human")
    assert tech_ctx.has_permission(PERM_MANAGE_USERS) is False
    assert tech_ctx.has_permission(PERM_READ_AUDIT_LOG) is False
    assert tech_ctx.has_permission(PERM_WRITE_FINANCIALS) is False

    customer_ctx = AuthContext(user_id=3, username="cust", role=ROLE_CUSTOMER, actor_type="human", customer_id=42)
    assert customer_ctx.has_permission(PERM_READ_OWN_CUSTOMER) is True
    assert customer_ctx.has_permission(PERM_READ_ALL_CUSTOMERS) is False
    assert customer_ctx.can_access_customer(42) is True
    assert customer_ctx.can_access_customer(43) is False

def test_role_change_audit(auth_service):
    from restoricon_core.services.audit_service import AuditService
    # Inject AuditService since AuthService does not have it injected by default (FINDING)
    audit = AuditService(auth_service.db)
    auth_service.audit = audit
    
    admin_user = auth_service.create_user("admin_user2", "AdminPassword123", "Admin Boss", "admin2@restoricon.com", ROLE_ADMIN)
    admin_ctx = AuthContext(user_id=admin_user.id, username=admin_user.username, role=ROLE_ADMIN, actor_type="human")
    
    user = auth_service.create_user("roletech", "Pass123!", "Role Tech", "rt@ex.com", "technician", actor_context=admin_ctx)
    
    auth_service.update_user(user.id, {"role": "manager"}, admin_ctx)
    
    logs = audit.query_logs(admin_ctx, entity_type="user", entity_id=user.id, action="update")
    assert len(logs) == 1
    assert logs[0].action == "update"
    assert "role" in logs[0].details["changed_fields"]
    assert logs[0].details["changed_fields"]["role"] == {"old": "technician", "new": "manager"}
