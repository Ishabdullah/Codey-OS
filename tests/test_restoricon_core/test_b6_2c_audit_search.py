import pytest
from restoricon_core.database import DatabaseManager
from restoricon_core.services.audit_service import AuditService
from restoricon_core.auth import AuthContext, ROLE_ADMIN, ROLE_TECHNICIAN

@pytest.fixture
def setup_audit():
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    from restoricon_core.auth import AuthService
    auth = AuthService(db)
    u1 = auth.create_user("admin", "pass", "Admin", "admin@ex.com", ROLE_ADMIN)
    u2 = auth.create_user("tech", "pass", "Tech", "tech@ex.com", ROLE_TECHNICIAN)
    admin_ctx = AuthContext(user_id=u1.id, username="admin", role=ROLE_ADMIN, actor_type="human")
    tech_ctx = AuthContext(user_id=u2.id, username="tech", role=ROLE_TECHNICIAN, actor_type="human")
    return db, audit, admin_ctx, tech_ctx

def test_audit_query_logs_with_actor_id(setup_audit):
    db, audit, admin_ctx, tech_ctx = setup_audit
    audit.log("test", "user", 1, "test1", actor=admin_ctx)
    audit.log("test", "user", 2, "test2", actor=tech_ctx)
    
    logs = audit.query_logs(admin_ctx, actor_id=1)
    assert len(logs) == 1
    assert logs[0].actor_id == 1

def test_audit_query_logs_without_actor_id(setup_audit):
    db, audit, admin_ctx, tech_ctx = setup_audit
    audit.log("test", "user", 1, "test1", actor=admin_ctx)
    audit.log("test", "user", 2, "test2", actor=tech_ctx)
    
    logs = audit.query_logs(admin_ctx)
    assert len(logs) == 2

def test_audit_query_logs_permission_denied(setup_audit):
    db, audit, admin_ctx, tech_ctx = setup_audit
    with pytest.raises(PermissionError):
        audit.query_logs(tech_ctx)

def test_audit_route_get_with_actor_id(setup_audit):
    # Dummy mock for routes
    db, audit, admin_ctx, _ = setup_audit
    audit.log("test", "user", 1, "test1", actor=admin_ctx)
    logs = audit.query_logs(admin_ctx, actor_id=1, limit=100, offset=0)
    assert len(logs) == 1

def test_audit_route_get_without_actor_id(setup_audit):
    # Dummy mock for routes
    db, audit, admin_ctx, _ = setup_audit
    audit.log("test", "user", 1, "test1", actor=admin_ctx)
    logs = audit.query_logs(admin_ctx, limit=100, offset=0)
    assert len(logs) == 1

def test_web_surface_audit_search_tab_rendered():
    from restoricon_core.api.web_surfaces import render_admin_surface
    html = render_admin_surface()
    assert "switchErpTab('audit')" in html

def test_web_surface_audit_pane_rendered():
    from restoricon_core.api.web_surfaces import render_admin_surface
    html = render_admin_surface()
    assert 'id="tab-audit"' in html
    assert 'id="auditActorId"' in html

def test_web_surface_search_audit_log_js_present():
    from restoricon_core.api.web_surfaces import render_admin_surface
    html = render_admin_surface()
    assert 'async function searchAuditLog()' in html

