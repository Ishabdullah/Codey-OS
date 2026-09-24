"""
Unit tests for B8.10b: CommunicationRecord.lead_id, the NEW-618 RBAC
narrowing fix in CommunicationService.query_communications(), and the new
GET /api/v1/sales/communications-center Communications Center feed route.

Covers:
- lead_id round-trips through record_communication/query_communications.
- a rep without PERM_READ_TEAM_SALES_DATA only sees communications tied to
  their own assigned (or unclaimed) customers/leads via the new feed route,
  never another rep's.
- a PERM_READ_TEAM_SALES_DATA holder sees everything via the same route.
- the existing customer_id-scoped call path (Customer 360's own panel,
  GET /api/v1/communications?customer_id=X) is unaffected -- still returns
  the same rows it did before this round for an actor who can access that
  customer.
- route-level 401/403 guards.
"""

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_READ_TEAM_SALES_DATA,
    ROLE_ADMIN,
    ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Lead
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.scheduling_service import SchedulingService


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    comm = CommunicationService(db)
    crm = CRMService(db, audit)
    sched = SchedulingService(db, audit)
    auto = AutomationService(db, audit)
    router = APIRouter(auth, crm, comm, audit, sched, auto)

    admin_user = auth.create_user("admin_user", "Pass123!", "Admin User", "admin@test.com", ROLE_ADMIN)
    admin_actor = AuthContext(admin_user.id, "admin_user", ROLE_ADMIN, "human")

    rep_a_user = auth.create_user("rep_a", "Pass123!", "Rep A", "repa@test.com", ROLE_SALES)
    rep_b_user = auth.create_user("rep_b", "Pass123!", "Rep B", "repb@test.com", ROLE_SALES)
    mgr_user = auth.create_user(
        "sales_mgr", "Pass123!", "Sales Mgr", "mgr@test.com", ROLE_SALES,
        custom_permissions={PERM_READ_TEAM_SALES_DATA: True},
    )

    tokens = {
        "admin": auth.create_token(admin_user),
        "rep_a": auth.create_token(rep_a_user),
        "rep_b": auth.create_token(rep_b_user),
        "mgr": auth.create_token(mgr_user),
    }
    actors = {
        "admin": admin_actor,
        "rep_a": AuthContext(rep_a_user.id, "rep_a", ROLE_SALES, "human", token=tokens["rep_a"]),
        "rep_b": AuthContext(rep_b_user.id, "rep_b", ROLE_SALES, "human", token=tokens["rep_b"]),
    }

    # Customer A is assigned to rep A; Customer B to rep B; Customer U is
    # unclaimed (assigned_user_id=None). Same for leads.
    cust_a = crm.create_customer(
        Customer(first_name="Cust", last_name="A", email="a@test.com", assigned_user_id=rep_a_user.id),
        admin_actor,
    )
    cust_b = crm.create_customer(
        Customer(first_name="Cust", last_name="B", email="b@test.com", assigned_user_id=rep_b_user.id),
        admin_actor,
    )
    cust_u = crm.create_customer(
        Customer(first_name="Cust", last_name="Unclaimed", email="u@test.com"),
        admin_actor,
    )
    lead_a = crm.create_lead(Lead(source="web", assigned_user_id=rep_a_user.id), admin_actor)
    lead_b = crm.create_lead(Lead(source="web", assigned_user_id=rep_b_user.id), admin_actor)

    # One communication tied to each: rep A's customer, rep B's customer,
    # unclaimed customer, rep A's lead, rep B's lead.
    comm_cust_a = comm.record_communication(
        channel="email", direction="outbound", content="Hi A", actor=admin_actor, customer_id=cust_a.id,
    )
    comm_cust_b = comm.record_communication(
        channel="email", direction="outbound", content="Hi B", actor=admin_actor, customer_id=cust_b.id,
    )
    comm_cust_u = comm.record_communication(
        channel="email", direction="outbound", content="Hi U", actor=admin_actor, customer_id=cust_u.id,
    )
    comm_lead_a = comm.record_communication(
        channel="email", direction="outbound", content="Lead A follow-up", actor=admin_actor, lead_id=lead_a.id,
    )
    comm_lead_b = comm.record_communication(
        channel="email", direction="outbound", content="Lead B follow-up", actor=admin_actor, lead_id=lead_b.id,
    )
    # Unknown-provenance row: neither customer_id nor lead_id set (e.g. the
    # from_email-resolution-failed POST path). Must NOT be visible to a
    # narrowed actor -- there is no customer/lead record to check
    # assigned_user_id against, so it cannot be proven "unclaimed" the way
    # a real customer/lead row with a NULL assigned_user_id can.
    comm_unlinked = comm.record_communication(
        channel="email", direction="inbound", content="Unresolved inbound email", actor=admin_actor,
    )

    return {
        "db": db, "auth": auth, "crm": crm, "comm": comm, "router": router,
        "tokens": tokens, "actors": actors,
        "cust_a": cust_a, "cust_b": cust_b, "cust_u": cust_u,
        "lead_a": lead_a, "lead_b": lead_b,
        "ids": {
            "comm_cust_a": comm_cust_a.id, "comm_cust_b": comm_cust_b.id, "comm_cust_u": comm_cust_u.id,
            "comm_lead_a": comm_lead_a.id, "comm_lead_b": comm_lead_b.id,
            "comm_unlinked": comm_unlinked.id,
        },
    }


def _get_center(router, token, **params):
    path = "/api/v1/sales/communications-center"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        path += f"?{qs}"
    return router.handle_request("GET", path, {"Authorization": f"Bearer {token}"}, b"")


def _get_by_customer(router, token, customer_id):
    return router.handle_request(
        "GET", f"/api/v1/communications?customer_id={customer_id}",
        {"Authorization": f"Bearer {token}"}, b"",
    )


# ---------------------------------------------------------------------
# lead_id round-trip
# ---------------------------------------------------------------------

def test_lead_id_round_trips_through_create_and_read(env):
    comm = env["comm"]
    admin_actor = env["actors"]["admin"]
    rec = comm.record_communication(
        channel="phone", direction="outbound", content="Called about their claim",
        actor=admin_actor, lead_id=env["lead_a"].id,
    )
    assert rec.lead_id == env["lead_a"].id
    assert rec.customer_id is None

    fetched = comm.query_communications(admin_actor, lead_id=env["lead_a"].id)
    assert any(c.id == rec.id and c.lead_id == env["lead_a"].id for c in fetched)


def test_lead_id_round_trips_through_post_route(env):
    router = env["router"]
    status, _, data = router.handle_request(
        "POST", "/api/v1/communications",
        {"Authorization": f"Bearer {env['tokens']['admin']}", "Content-Type": "application/json"},
        b'{"channel": "email", "direction": "outbound", "content": "hi", "lead_id": %d}'
        % env["lead_a"].id,
    )
    assert status == 201
    assert data["communication"]["lead_id"] == env["lead_a"].id


# ---------------------------------------------------------------------
# NEW-618 RBAC narrowing via the new Communications Center feed route
# ---------------------------------------------------------------------

def test_rep_without_team_permission_sees_only_own_and_unclaimed(env):
    status, _, data = _get_center(env["router"], env["tokens"]["rep_a"])
    assert status == 200
    assert data["scope"] == "rep"
    ids = {c["id"] for c in data["communications"]}

    # Rep A's own customer + unclaimed customer + rep A's own lead: visible.
    assert env["ids"]["comm_cust_a"] in ids
    assert env["ids"]["comm_cust_u"] in ids
    assert env["ids"]["comm_lead_a"] in ids

    # Rep B's customer and lead: never visible to rep A.
    assert env["ids"]["comm_cust_b"] not in ids
    assert env["ids"]["comm_lead_b"] not in ids

    # Unknown-provenance row (no customer_id, no lead_id): never visible to
    # a narrowed actor -- not treated as "unclaimed".
    assert env["ids"]["comm_unlinked"] not in ids


def test_rep_b_never_sees_rep_a_data_either(env):
    """Symmetric check -- confirms the narrowing isn't accidentally a
    one-directional artifact of fixture ordering."""
    status, _, data = _get_center(env["router"], env["tokens"]["rep_b"])
    assert status == 200
    ids = {c["id"] for c in data["communications"]}
    assert env["ids"]["comm_cust_b"] in ids
    assert env["ids"]["comm_cust_u"] in ids
    assert env["ids"]["comm_lead_b"] in ids
    assert env["ids"]["comm_cust_a"] not in ids
    assert env["ids"]["comm_lead_a"] not in ids
    assert env["ids"]["comm_unlinked"] not in ids


def test_team_permission_holder_sees_everything(env):
    status, _, data = _get_center(env["router"], env["tokens"]["mgr"])
    assert status == 200
    assert data["scope"] == "team"
    ids = {c["id"] for c in data["communications"]}
    for key in env["ids"].values():
        assert key in ids


def test_admin_sees_everything(env):
    status, _, data = _get_center(env["router"], env["tokens"]["admin"])
    assert status == 200
    assert data["scope"] == "team"
    ids = {c["id"] for c in data["communications"]}
    for key in env["ids"].values():
        assert key in ids


def test_route_requires_valid_token(env):
    status, _, _ = env["router"].handle_request(
        "GET", "/api/v1/sales/communications-center", {"Authorization": "Bearer not-a-real-token"}, b"",
    )
    assert status == 401


# ---------------------------------------------------------------------
# Regression: existing customer_id-scoped Customer 360 call path unaffected
# ---------------------------------------------------------------------

def test_customer_scoped_call_unaffected_for_own_customer(env):
    """The exact call shape Customer 360's panel uses
    (GET /api/v1/communications?customer_id=X) for a customer the actor is
    actually assigned to must still return that customer's communications,
    same as before this round's narrowing was added."""
    status, _, data = _get_by_customer(env["router"], env["tokens"]["rep_a"], env["cust_a"].id)
    assert status == 200
    ids = {c["id"] for c in data["communications"]}
    assert env["ids"]["comm_cust_a"] in ids


def test_customer_scoped_call_unaffected_for_unclaimed_customer(env):
    status, _, data = _get_by_customer(env["router"], env["tokens"]["rep_a"], env["cust_u"].id)
    assert status == 200
    ids = {c["id"] for c in data["communications"]}
    assert env["ids"]["comm_cust_u"] in ids


def test_customer_scoped_call_narrowed_for_unowned_customer(env):
    """New, correct behavior: rep A explicitly requesting rep B's customer's
    communications via the generic customer_id-filtered route now gets
    nothing back, closing the NEW-618 gap for this call shape too (not just
    the new unscoped feed)."""
    status, _, data = _get_by_customer(env["router"], env["tokens"]["rep_a"], env["cust_b"].id)
    assert status == 200
    ids = {c["id"] for c in data["communications"]}
    assert env["ids"]["comm_cust_b"] not in ids


def test_admin_customer_scoped_call_still_sees_everything(env):
    status, _, data = _get_by_customer(env["router"], env["tokens"]["admin"], env["cust_b"].id)
    assert status == 200
    ids = {c["id"] for c in data["communications"]}
    assert env["ids"]["comm_cust_b"] in ids


# ---------------------------------------------------------------------
# Disclosed behavior change: PERM_READ_COMMUNICATIONS-without-
# PERM_READ_TEAM_SALES_DATA actors (e.g. ROLE_PROJECT_MANAGER) are now
# narrowed on query_communications() too, including an explicit
# customer_id they don't own. This is a NARROWING, not a widening -- the
# fix applies uniformly at this one service-layer choke point regardless
# of which route/panel a caller reaches it from, so nothing is more
# exposed than before this diff. CORRECTED (code-reviewer, 2026-09-24):
# render_admin_surface's Customer 360 panel is NOT "admin/manager-only"
# -- routes.py serves /admin with no server-side role check, so it's
# architecturally reachable by any authenticated actor, including
# PM-tier. See communication_service.py's own corrected comment and
# NEW-625 for the underlying /admin route-gating gap this surfaced.
# ---------------------------------------------------------------------

def test_pm_tier_actor_is_also_narrowed_on_explicit_customer_id(env):
    from restoricon_core.auth import PERM_READ_COMMUNICATIONS, ROLE_PROJECT_MANAGER

    pm_user = env["auth"].create_user(
        "pm_user", "Pass123!", "PM User", "pm@test.com", ROLE_PROJECT_MANAGER,
    )
    pm_actor = AuthContext(pm_user.id, "pm_user", ROLE_PROJECT_MANAGER, "human")
    assert pm_actor.has_permission(PERM_READ_COMMUNICATIONS)
    assert not pm_actor.has_permission(PERM_READ_TEAM_SALES_DATA)

    # Not assigned to cust_a -> narrowed out, even with an explicit
    # customer_id filter.
    results = env["comm"].query_communications(pm_actor, customer_id=env["cust_a"].id)
    assert env["ids"]["comm_cust_a"] not in {c.id for c in results}

    # Unclaimed customer's communications remain visible.
    results_u = env["comm"].query_communications(pm_actor, customer_id=env["cust_u"].id)
    assert env["ids"]["comm_cust_u"] in {c.id for c in results_u}


# ---------------------------------------------------------------------
# Migration path: a pre-existing DB file whose communication_history table
# predates lead_id must get the column (and its index) added via
# _migrate_schema()'s ALTER, not just via CREATE TABLE IF NOT EXISTS
# (which only helps brand-new DB files) -- B8.9a shipped a real bug in
# this exact mechanism (a drift-guard rebuild), so this is exercised
# directly rather than assumed from the ordering analysis alone.
# ---------------------------------------------------------------------

def test_lead_id_column_and_index_added_via_migration_on_legacy_db(tmp_path):
    import sqlite3

    from restoricon_core.database import DatabaseManager

    db_path = str(tmp_path / "legacy.sqlite3")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE communication_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            channel TEXT NOT NULL,
            direction TEXT NOT NULL,
            subject TEXT,
            content TEXT NOT NULL,
            actor_id INTEGER,
            actor_role TEXT NOT NULL,
            actor_type TEXT NOT NULL,
            customer_id INTEGER,
            project_id INTEGER,
            opportunity_id INTEGER,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            provider_message_id TEXT
        );
        """
    )
    conn.commit()
    conn.close()

    db = DatabaseManager(db_path)
    conn = db.get_connection()
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(communication_history);")}
    assert "lead_id" in columns

    indexes = {row["name"] for row in conn.execute("PRAGMA index_list(communication_history);")}
    assert "idx_comms_lead_id" in indexes

    # Full round-trip against the migrated table.
    auth = AuthService(db)
    audit = AuditService(db)
    crm = CRMService(db, audit)
    comm = CommunicationService(db)
    admin_user = auth.create_user("admin_user", "Pass123!", "Admin", "admin2@test.com", ROLE_ADMIN)
    admin_actor = AuthContext(admin_user.id, "admin_user", ROLE_ADMIN, "human")
    lead = crm.create_lead(Lead(source="web"), admin_actor)
    rec = comm.record_communication(
        channel="email", direction="outbound", content="hi", actor=admin_actor, lead_id=lead.id,
    )
    assert rec.lead_id == lead.id
    fetched = comm.query_communications(admin_actor, lead_id=lead.id)
    assert any(c.id == rec.id for c in fetched)
