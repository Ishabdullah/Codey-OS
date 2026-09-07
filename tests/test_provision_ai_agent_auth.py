"""
Unit tests for tools/provision_ai_agent_auth.py — Restoricon Core
ai_agent auth provisioning used by the do-not-contact write-through pilot
(CODEY_MASTER_PLAN.md §6.4 task 4). Runs against `:memory:` DBs or
pytest tmp_path-backed scratch files; never touches the real persistent
Core DB path.
"""

import pytest

from restoricon_core.auth import ROLE_AI_AGENT, AuthService
from restoricon_core.database import DatabaseManager
from tools.provision_ai_agent_auth import DEFAULT_USERNAME, provision


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
