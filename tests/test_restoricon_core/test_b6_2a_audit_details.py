"""
Unit + route tests for B6.2a: the canonical ``build_audit_details`` helper
and the nine user-mutation / session audit sites in ``api/routes.py``.

Covers:
1. Helper envelope semantics (added / removed / equal / dict whole-value /
   empty diff / ``fields=`` filter / allow-list drop / passthrough slots).
2. Per-site route payloads, read back via the raw ``details_json`` column
   and via ``audit.query_logs``.
3. A leak sweep asserting no password hash or plaintext ever reaches the
   serialized audit payload for any of the nine actions.
"""

import json

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthService,
    ROLE_ADMIN,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.services.audit_service import (
    AuditService,
    build_audit_details,
    _AUDITABLE_USER_FIELDS,
)
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------

def test_added_key():
    d = build_audit_details(before={}, after={"role": "manager"})
    assert d["changed_fields"] == {"role": {"old": None, "new": "manager"}}


def test_removed_key():
    d = build_audit_details(before={"phone": "123"}, after={})
    assert d["changed_fields"] == {"phone": {"old": "123", "new": None}}


def test_equal_value_omitted():
    d = build_audit_details(before={"role": "tech"}, after={"role": "tech"})
    assert "changed_fields" not in d


def test_dict_field_whole_value():
    d = build_audit_details(
        before={"custom_permissions": {"a": True}},
        after={"custom_permissions": {"a": True, "b": False}},
    )
    assert d["changed_fields"]["custom_permissions"] == {
        "old": {"a": True},
        "new": {"a": True, "b": False},
    }


def test_empty_diff_omits_changed_fields():
    d = build_audit_details(before={"role": "x"}, after={"role": "x"})
    assert d == {}


def test_both_none_omits_changed_fields():
    d = build_audit_details(before=None, after=None,
                            side_effects={"sessions_revoked": "all_except_actor"})
    assert "changed_fields" not in d
    assert d["side_effects"] == {"sessions_revoked": "all_except_actor"}


def test_fields_filter_limits_domain():
    d = build_audit_details(
        before={"role": "a", "department": "x"},
        after={"role": "b", "department": "y"},
        fields={"role"},
    )
    assert set(d["changed_fields"]) == {"role"}


def test_fields_domain_key_in_neither_omitted():
    d = build_audit_details(before={"role": "a"}, after={"role": "a"},
                            fields=_AUDITABLE_USER_FIELDS)
    assert d == {}


def test_allow_list_drops_password_hash():
    d = build_audit_details(
        before={"password_hash": "OLDHASH", "role": "tech"},
        after={"password_hash": "NEWHASH", "role": "manager"},
        fields=_AUDITABLE_USER_FIELDS,
    )
    assert "password_hash" not in d["changed_fields"]
    assert d["changed_fields"]["role"] == {"old": "tech", "new": "manager"}


def test_side_effects_and_snapshot_passthrough():
    d = build_audit_details(
        side_effects={"tokens_deleted": "all"},
        snapshot={"id": 5, "username": "bob"},
    )
    assert d == {
        "side_effects": {"tokens_deleted": "all"},
        "snapshot": {"id": 5, "username": "bob"},
    }


# ---------------------------------------------------------------------------
# Route-level fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    comm = CommunicationService(db)
    crm = CRMService(db, audit)
    sched = SchedulingService(db, audit)
    auto = AutomationService(db, audit)
    ops = OperationsService(db, audit)
    router = APIRouter(
        auth_service=auth,
        crm_service=crm,
        comm_service=comm,
        audit_service=audit,
        scheduling_service=sched,
        automation_service=auto,
        operations_service=ops,
    )
    admin = auth.create_user("admin_u", "AdminPass123!", "Admin U", "admin@r.com", role=ROLE_ADMIN)
    admin_token = auth.create_token(admin)
    admin_ctx = auth.authenticate_token(admin_token)
    return {
        "db": db, "auth": auth, "audit": audit, "router": router,
        "admin": admin, "admin_token": admin_token, "admin_ctx": admin_ctx,
    }


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _mk_user(env, username="target_u", role=ROLE_TECHNICIAN):
    u = env["auth"].create_user(
        username, "TargetPass123!", "Target U", f"{username}@r.com",
        role=role, actor_context=env["admin_ctx"],
    )
    return u


def _last_details(env, entity_id):
    rows = env["audit"].query_logs(env["admin_ctx"], entity_type="user", entity_id=entity_id)
    return rows[0].details


def _raw_details_json(env, entity_id=None):
    conn = env["db"].get_connection()
    if entity_id is None:
        rows = conn.execute("SELECT details_json FROM audit_log").fetchall()
    else:
        rows = conn.execute(
            "SELECT details_json FROM audit_log WHERE entity_id = ?", (entity_id,)
        ).fetchall()
    return [r["details_json"] for r in rows]


# ---------------------------------------------------------------------------
# Per-site route tests
# ---------------------------------------------------------------------------

def test_role_change_via_put_records_diff_and_revokes_all(env):
    u = _mk_user(env)
    status, _, _ = env["router"].handle_request(
        "PUT", f"/api/v1/users/{u.id}", _hdr(env["admin_token"]),
        json.dumps({"role": "manager"}).encode(),
    )
    assert status == 200
    details = _last_details(env, u.id)
    assert details["changed_fields"]["role"] == {"old": "technician", "new": "manager"}
    assert details["side_effects"]["sessions_revoked"] == "all"


def test_non_role_field_change_revokes_none(env):
    u = _mk_user(env)
    status, _, _ = env["router"].handle_request(
        "PUT", f"/api/v1/users/{u.id}", _hdr(env["admin_token"]),
        json.dumps({"department": "Remediation"}).encode(),
    )
    assert status == 200
    details = _last_details(env, u.id)
    assert details["changed_fields"]["department"] == {"old": None, "new": "Remediation"}
    assert details["side_effects"]["sessions_revoked"] == "none"


def test_suspend_revokes_all(env):
    u = _mk_user(env)
    status, _, _ = env["router"].handle_request(
        "POST", f"/api/v1/users/{u.id}/suspend", _hdr(env["admin_token"]), b"",
    )
    assert status == 200
    details = _last_details(env, u.id)
    assert details["side_effects"]["sessions_revoked"] == "all"
    assert details["changed_fields"]["active"] == {"old": 1, "new": 0}


def test_activate_revokes_none(env):
    u = _mk_user(env)
    env["router"].handle_request(
        "POST", f"/api/v1/users/{u.id}/suspend", _hdr(env["admin_token"]), b"",
    )
    status, _, _ = env["router"].handle_request(
        "POST", f"/api/v1/users/{u.id}/activate", _hdr(env["admin_token"]), b"",
    )
    assert status == 200
    details = _last_details(env, u.id)
    assert details["side_effects"]["sessions_revoked"] == "none"
    assert details["changed_fields"]["active"] == {"old": 0, "new": 1}


def test_self_password_change_revokes_all_except_actor_no_values(env):
    # admin changes own password
    status, _, _ = env["router"].handle_request(
        "POST", f"/api/v1/users/{env['admin'].id}/password", _hdr(env["admin_token"]),
        json.dumps({"old_password": "AdminPass123!", "new_password": "NewAdminPass456!"}).encode(),
    )
    assert status == 200
    details = _last_details(env, env["admin"].id)
    assert details == {"side_effects": {"sessions_revoked": "all_except_actor"}}
    raw = _raw_details_json(env, env["admin"].id)[0]
    assert "NewAdminPass456!" not in raw
    assert "password_hash" not in raw


def test_admin_resets_other_user_password_revokes_all(env):
    # admin resets a DIFFERENT user's password: the actor's own token belongs
    # to a different user_id, so it is not spared -- every target session goes.
    u = _mk_user(env)
    status, _, _ = env["router"].handle_request(
        "POST", f"/api/v1/users/{u.id}/password", _hdr(env["admin_token"]),
        json.dumps({"new_password": "ResetByAdmin789!"}).encode(),
    )
    assert status == 200
    details = _last_details(env, u.id)
    assert details == {"side_effects": {"sessions_revoked": "all"}}
    raw = _raw_details_json(env, u.id)[0]
    assert "ResetByAdmin789!" not in raw
    assert "password_hash" not in raw


def test_permissions_update_stores_cleaned_bool_dict(env):
    u = _mk_user(env)
    status, _, _ = env["router"].handle_request(
        "PUT", f"/api/v1/users/{u.id}/permissions", _hdr(env["admin_token"]),
        json.dumps({"custom_permissions": {"read_financials": 1}}).encode(),
    )
    assert status == 200
    details = _last_details(env, u.id)
    assert details["changed_fields"]["custom_permissions"]["new"] == {"read_financials": True}
    assert details["side_effects"]["sessions_revoked"] == "none"


def test_create_records_snapshot_no_changed_fields(env):
    status, _, data = env["router"].handle_request(
        "POST", "/api/v1/users", _hdr(env["admin_token"]),
        json.dumps({
            "username": "fresh_u", "password": "FreshPass123!",
            "full_name": "Fresh U", "email": "fresh@r.com", "role": "technician",
        }).encode(),
    )
    assert status == 201
    uid = data["user"]["id"]
    details = _last_details(env, uid)
    assert "changed_fields" not in details
    assert details["snapshot"]["username"] == "fresh_u"
    assert "password_hash" not in json.dumps(details)


def test_delete_records_snapshot_and_tokens_deleted(env):
    u = _mk_user(env)
    status, _, _ = env["router"].handle_request(
        "DELETE", f"/api/v1/users/{u.id}", _hdr(env["admin_token"]), b"",
    )
    assert status == 200
    details = _last_details(env, u.id)
    assert "changed_fields" not in details
    assert details["snapshot"]["username"] == u.username
    assert details["side_effects"] == {"tokens_deleted": "all"}


def test_login_logout_side_effects_only(env):
    # login
    status, _, data = env["router"].handle_request(
        "POST", "/api/v1/auth/login", {},
        json.dumps({"username": "admin_u", "password": "AdminPass123!"}).encode(),
    )
    assert status == 200
    token = data["token"]
    login_rows = env["audit"].query_logs(env["admin_ctx"], entity_type="user",
                                         entity_id=env["admin"].id, action="auth_login")
    assert login_rows[0].details == {"side_effects": {"session_created": True}}
    assert "changed_fields" not in login_rows[0].details

    # logout
    status, _, _ = env["router"].handle_request(
        "POST", "/api/v1/auth/logout", _hdr(token), b"",
    )
    assert status == 200
    logout_rows = env["audit"].query_logs(env["admin_ctx"], entity_type="user",
                                          entity_id=env["admin"].id, action="auth_logout")
    assert logout_rows[0].details == {"side_effects": {"sessions_revoked": "current_only"}}


# ---------------------------------------------------------------------------
# Highest-value: nothing sensitive ever reaches the serialized payload
# ---------------------------------------------------------------------------

def test_no_secret_leaks_across_all_nine_actions(env):
    PLAINTEXT = "SuperSecretPlain999!"
    r = env["router"]
    tok = env["admin_token"]

    # 1. create (with the sensitive plaintext)
    _, _, data = r.handle_request(
        "POST", "/api/v1/users", _hdr(tok),
        json.dumps({
            "username": "leak_u", "password": PLAINTEXT, "full_name": "Leak U",
            "email": "leak@r.com", "role": "technician",
        }).encode(),
    )
    uid = data["user"]["id"]
    utok = env["auth"].create_token(env["auth"].get_user_by_id(uid))

    # 2. update (role)
    r.handle_request("PUT", f"/api/v1/users/{uid}", _hdr(tok),
                     json.dumps({"role": "manager"}).encode())
    # 3. permissions
    r.handle_request("PUT", f"/api/v1/users/{uid}/permissions", _hdr(tok),
                     json.dumps({"custom_permissions": {"read_financials": 1}}).encode())
    # 4. suspend
    r.handle_request("POST", f"/api/v1/users/{uid}/suspend", _hdr(tok), b"")
    # 5. activate
    r.handle_request("POST", f"/api/v1/users/{uid}/activate", _hdr(tok), b"")
    # 6. admin-set password (plaintext again)
    r.handle_request("POST", f"/api/v1/users/{uid}/password", _hdr(tok),
                     json.dumps({"new_password": PLAINTEXT + "x"}).encode())
    # 7. login as target
    _, _, ldata = r.handle_request("POST", "/api/v1/auth/login", {},
                                   json.dumps({"username": "leak_u",
                                               "password": PLAINTEXT + "x"}).encode())
    # 8. logout
    r.handle_request("POST", "/api/v1/auth/logout", _hdr(ldata["token"]), b"")
    # 9. delete
    r.handle_request("DELETE", f"/api/v1/users/{uid}", _hdr(tok), b"")

    for raw in _raw_details_json(env):
        assert raw is not None
        assert "password_hash" not in raw
        assert PLAINTEXT not in raw
