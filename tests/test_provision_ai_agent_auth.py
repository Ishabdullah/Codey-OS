"""
Unit tests for tools/provision_ai_agent_auth.py — Restoricon Core
ai_agent auth provisioning used by the do-not-contact write-through pilot
(CODEY_MASTER_PLAN.md §6.4 task 4). Runs against `:memory:` DBs or
pytest tmp_path-backed scratch files; never touches the real persistent
Core DB path.
"""

import pytest

from restoricon_core.auth import ROLE_AI_AGENT, ROLE_PERMISSIONS, AuthService
from restoricon_core.database import DatabaseManager
from tools.provision_ai_agent_auth import (
    CRM_READER_DENY_PERMISSIONS,
    CRM_READER_USERNAME,
    DEFAULT_USERNAME,
    _CRM_READER_MUST_NOT_DENY,
    provision,
)


def test_provision_creates_new_ai_agent_user_and_token():
    token = provision(db_path=":memory:")
    assert isinstance(token, str)
    assert len(token) > 20


def test_provisioned_token_authenticates_as_ai_agent(tmp_path):
    # A real scratch file (not ":memory:") so the token issued by one
    # provision() call and the authentication check below hit the same
    # on-disk DB -- ":memory:" gives each DatabaseManager its own isolated
    # in-memory DB (see DatabaseManager.__init__'s _mem_counter), which
    # would make this test pass for the wrong reason.
    db_path = str(tmp_path / "core.db")
    token = provision(db_path=db_path)

    db = DatabaseManager(db_path)
    try:
        auth = AuthService(db)
        ctx = auth.authenticate_token(token)
        assert ctx is not None
        assert ctx.role == ROLE_AI_AGENT
        assert ctx.actor_type == "agent"
        assert ctx.username == DEFAULT_USERNAME
    finally:
        db.close()


def test_provision_is_idempotent_on_username(tmp_path):
    db_path = str(tmp_path / "core.db")
    token1 = provision(db_path=db_path)
    token2 = provision(db_path=db_path)

    assert token1 != token2  # each call issues its own fresh token

    db = DatabaseManager(db_path)
    try:
        conn = db.get_connection()
        rows = conn.execute("SELECT * FROM users WHERE username = ?;", (DEFAULT_USERNAME,)).fetchall()
        assert len(rows) == 1  # re-run reused the existing user, no duplicate

        auth = AuthService(db)
        ctx1 = auth.authenticate_token(token1)
        ctx2 = auth.authenticate_token(token2)
        assert ctx1 is None  # rerun revoked the earlier token (NEW-227)
        assert ctx2 is not None
        assert ctx2.username == DEFAULT_USERNAME
    finally:
        db.close()


def test_provision_rerun_does_not_accumulate_unrevoked_tokens(tmp_path):
    # NEW-227: a second (and third) run against the same user must leave
    # exactly one unrevoked token behind, not one more each time.
    db_path = str(tmp_path / "core.db")
    provision(db_path=db_path)
    provision(db_path=db_path)
    token3 = provision(db_path=db_path)

    db = DatabaseManager(db_path)
    try:
        conn = db.get_connection()
        user_row = conn.execute(
            "SELECT id FROM users WHERE username = ?;", (DEFAULT_USERNAME,)
        ).fetchone()
        live_tokens = conn.execute(
            "SELECT token FROM api_tokens WHERE user_id = ? AND is_revoked = 0;",
            (user_row["id"],),
        ).fetchall()
        assert len(live_tokens) == 1
        assert live_tokens[0]["token"] == token3

        revoked_count = conn.execute(
            "SELECT COUNT(*) AS n FROM api_tokens WHERE user_id = ? AND is_revoked = 1;",
            (user_row["id"],),
        ).fetchone()["n"]
        assert revoked_count == 2  # the two earlier runs' tokens were revoked
    finally:
        db.close()


def test_provision_rejects_username_collision_with_wrong_role(tmp_path):
    db_path = str(tmp_path / "core.db")
    db = DatabaseManager(db_path)
    try:
        auth = AuthService(db)
        auth.create_user(
            username=DEFAULT_USERNAME,
            plain_password="unused",
            full_name="Some Admin",
            email="admin@example.com",
            role="admin",
        )
    finally:
        db.close()

    with pytest.raises(ValueError):
        provision(db_path=db_path)


# ── CODEY_MASTER_PLAN.md 12.x Part B: codey-ccos-crm-reader deny-list ────

def test_crm_reader_deny_list_covers_every_ai_agent_permission_or_is_explicitly_allowed():
    """Drift guard: CRM_READER_DENY_PERMISSIONS is derived by verb-prefix
    (write:/manage:) plus three named exceptions (score:leads,
    dispatch:work_orders, log:communication) rather than a literal copy of
    ROLE_PERMISSIONS[ROLE_AI_AGENT] -- see
    _compute_crm_reader_deny_permissions()'s docstring. That derivation
    fails silently if ROLE_AI_AGENT ever gains a new write-capable
    permission under a verb prefix this script doesn't recognize (e.g. a
    future "approve:contracts" or "send:email"). This test makes that
    failure loud: every permission ROLE_AI_AGENT holds today must be
    either in the computed deny-list, or in the five explicitly-allowed
    read permissions this round's spec named as must-not-deny. A newly
    added permission that's neither fails this test instead of silently
    shipping a hole in the next rerun of this script.
    """
    # Frozen 2026-10-01: every OTHER read permission ROLE_AI_AGENT held at
    # the time this round scoped the deny-list -- outside CRM/sales scope
    # (HR, compliance, finance, operations, etc.) and not flagged as
    # sensitive by 12.x Part B's spec, so left granted/untouched rather
    # than evaluated. Deliberately a literal, frozen set, NOT a prefix
    # rule -- a brand-new permission added to ROLE_AI_AGENT later (read or
    # otherwise) must be classified by a human into either this set or
    # CRM_READER_DENY_PERMISSIONS, not silently pass because it happens
    # to start with "read:".
    _OUT_OF_SCOPE_READS_LEFT_GRANTED = frozenset({
        "read:staff_schedules", "read:compliance", "read:all_estimates", "read:contracts",
        "read:appointments", "read:do_not_contact", "read:schedule_config", "read:marketing",
        "read:finance", "read:subcontractors", "read:appointment_types", "read:business_profile",
        "read:estimates", "read:documents", "read:territories", "read:communications",
        "read:all_projects", "read:contacts", "read:hr", "read:procurement", "read:operations",
        "read:automation_rules",
    })
    explicitly_allowed_reads = _CRM_READER_MUST_NOT_DENY | _OUT_OF_SCOPE_READS_LEFT_GRANTED
    all_ai_agent_perms = ROLE_PERMISSIONS[ROLE_AI_AGENT]
    unaccounted_for = all_ai_agent_perms - set(CRM_READER_DENY_PERMISSIONS) - explicitly_allowed_reads
    assert not unaccounted_for, (
        f"ROLE_AI_AGENT permission(s) {unaccounted_for} are neither denied nor "
        f"explicitly allowed for {CRM_READER_USERNAME} -- classify them in "
        f"tools/provision_ai_agent_auth.py's _compute_crm_reader_deny_permissions() "
        f"or _CRM_READER_MUST_NOT_DENY before shipping."
    )


def test_crm_reader_deny_list_never_denies_a_must_not_deny_permission():
    assert not (set(CRM_READER_DENY_PERMISSIONS) & _CRM_READER_MUST_NOT_DENY)


def test_provision_crm_reader_applies_deny_list_on_creation(tmp_path):
    db_path = str(tmp_path / "core.db")
    provision(
        username=CRM_READER_USERNAME,
        email="codey-ccos-crm-reader@local.invalid",
        db_path=db_path,
        custom_permissions=CRM_READER_DENY_PERMISSIONS,
    )

    db = DatabaseManager(db_path)
    try:
        conn = db.get_connection()
        row = conn.execute(
            "SELECT custom_permissions_json FROM users WHERE username = ?;", (CRM_READER_USERNAME,)
        ).fetchone()
        import json as _json

        stored = _json.loads(row["custom_permissions_json"])
        assert stored == CRM_READER_DENY_PERMISSIONS
    finally:
        db.close()


def test_provision_crm_reader_reapplies_deny_list_on_rerun(tmp_path):
    """A rerun for an already-existing codey-ccos-crm-reader user must
    reapply the deny-list, not just skip it (reuse path) -- otherwise a
    manually-edited custom_permissions_json could drift away from the
    deny-list and a later rerun would never repair it."""
    db_path = str(tmp_path / "core.db")
    provision(username=CRM_READER_USERNAME, db_path=db_path, custom_permissions=CRM_READER_DENY_PERMISSIONS)

    # Simulate drift: directly clear custom_permissions_json as if some
    # other process had reset it.
    db = DatabaseManager(db_path)
    try:
        conn = db.get_connection()
        with conn:
            conn.execute(
                "UPDATE users SET custom_permissions_json = '{}' WHERE username = ?;", (CRM_READER_USERNAME,)
            )
    finally:
        db.close()

    provision(username=CRM_READER_USERNAME, db_path=db_path, custom_permissions=CRM_READER_DENY_PERMISSIONS)

    db = DatabaseManager(db_path)
    try:
        conn = db.get_connection()
        row = conn.execute(
            "SELECT custom_permissions_json FROM users WHERE username = ?;", (CRM_READER_USERNAME,)
        ).fetchone()
        import json as _json

        assert _json.loads(row["custom_permissions_json"]) == CRM_READER_DENY_PERMISSIONS
    finally:
        db.close()


def test_provision_rejects_invalid_custom_permissions_key(tmp_path):
    db_path = str(tmp_path / "core.db")
    with pytest.raises(ValueError):
        provision(
            username="codey-ccos-crm-reader-bad-perm-test",
            email="codey-ccos-crm-reader-bad-perm-test@local.invalid",
            db_path=db_path,
            custom_permissions={"not:a:real:permission": False},
        )
