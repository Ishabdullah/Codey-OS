"""
Unit tests for B8.2a: GET /api/v1/sales/dashboard (Sales Rep Portal
Command Center), sales_rep_portal.md §5, project-architect scoping pass
2026-09-17.

Covers:
- rep-tier scoping: rep A's dashboard never contains rep B's leads,
  tasks, appointments, or commission entries.
- the "team" key is *absent* (not `{}`) for an actor lacking
  PERM_READ_TEAM_SALES_DATA, and present with company-wide totals for one
  who holds it via either grant mechanism (real role, or custom_permissions
  per the NEW-533 precedent).
- the `days` query param actually changes the appointments/follow-ups
  window.
- the actor.user_id is None guard.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_READ_TEAM_COMMISSIONS,
    PERM_READ_TEAM_SALES_DATA,
    PERM_WRITE_TEAM_COMMISSIONS,
    ROLE_ADMIN,
    ROLE_SALES,
    ROLE_SALES_MANAGER,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    Appointment,
    CommissionLedgerEntry,
    Customer,
    Lead,
    Opportunity,
    Task,
)
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.commission_service import CommissionService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.scheduling_service import SchedulingService


def _iso_date(offset_days: int = 0) -> str:
    return (datetime.now(timezone.utc).date() + timedelta(days=offset_days)).isoformat()


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    comm = CommunicationService(db)
    crm = CRMService(db, audit)
    sched = SchedulingService(db, audit)
    auto = AutomationService(db, audit)
    commissions = CommissionService(db, audit)
    router = APIRouter(auth, crm, comm, audit, sched, auto, commission_service=commissions)

    admin_user = auth.create_user("admin_user", "Pass123!", "Admin User", "admin@test.com", ROLE_ADMIN)
    admin_actor = AuthContext(admin_user.id, "admin_user", ROLE_ADMIN, "human")

    rep_a_user = auth.create_user("rep_a", "Pass123!", "Rep A", "repa@test.com", ROLE_SALES)
    rep_b_user = auth.create_user("rep_b", "Pass123!", "Rep B", "repb@test.com", ROLE_SALES)
    mgr_user = auth.create_user("sales_mgr", "Pass123!", "Sales Mgr", "mgr@test.com", ROLE_SALES_MANAGER)
    granted_rep_user = auth.create_user(
        "granted_rep", "Pass123!", "Granted Rep", "granted@test.com", ROLE_SALES,
        custom_permissions={PERM_READ_TEAM_SALES_DATA: True},
    )
    # NEW-533-style split grant: PERM_READ_TEAM_COMMISSIONS WITHOUT
    # PERM_READ_TEAM_SALES_DATA -- e.g. payroll reconciliation access
    # without full sales-pipeline visibility. Every built-in role pairs
    # these two permissions together, so only a custom_permissions grant
    # can produce this split.
    commissions_only_rep_user = auth.create_user(
        "commissions_only_rep", "Pass123!", "Commissions Only Rep", "commonly@test.com", ROLE_SALES,
        custom_permissions={PERM_READ_TEAM_COMMISSIONS: True},
    )

    tokens = {
        "admin": auth.create_token(admin_user),
        "rep_a": auth.create_token(rep_a_user),
        "rep_b": auth.create_token(rep_b_user),
        "mgr": auth.create_token(mgr_user),
        "granted_rep": auth.create_token(granted_rep_user),
        "commissions_only_rep": auth.create_token(commissions_only_rep_user),
    }

    cust = crm.create_customer(Customer(first_name="Test", last_name="Cust", email="cust@test.com"), admin_actor)

    # Rep A's data
    lead_a = crm.create_lead(Lead(customer_id=cust.id, status="new", assigned_user_id=rep_a_user.id), admin_actor)
    opp_a = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Opp A", estimated_value=1000.0, assigned_user_id=rep_a_user.id),
        admin_actor,
    )
    task_a = crm.create_task(
        Task(title="Task A", status="pending", assigned_user_id=rep_a_user.id, due_date=_iso_date(0)),
        admin_actor,
    )
    appt_a = sched.create_appointment(
        Appointment(
            title="Appt A", start_time=f"{_iso_date(0)}T10:00:00Z", end_time=f"{_iso_date(0)}T11:00:00Z",
            assigned_user_id=rep_a_user.id, status="confirmed",
        ),
        admin_actor,
    )
    assert admin_actor.has_permission(PERM_WRITE_TEAM_COMMISSIONS)  # sanity: admin holds it by default
    comm_a = commissions.record_commission(
        CommissionLedgerEntry(rep_user_id=rep_a_user.id, source_type="assessment", commission_amount=100.0, status="earned"),
        admin_actor,
    )

    # Rep B's data (must never leak into rep A's dashboard)
    lead_b = crm.create_lead(Lead(customer_id=cust.id, status="new", assigned_user_id=rep_b_user.id), admin_actor)
    opp_b = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Opp B", estimated_value=5000.0, assigned_user_id=rep_b_user.id),
        admin_actor,
    )
    task_b = crm.create_task(
        Task(title="Task B", status="pending", assigned_user_id=rep_b_user.id, due_date=_iso_date(0)),
        admin_actor,
    )
    appt_b = sched.create_appointment(
        Appointment(
            title="Appt B", start_time=f"{_iso_date(0)}T10:00:00Z", end_time=f"{_iso_date(0)}T11:00:00Z",
            assigned_user_id=rep_b_user.id, status="confirmed",
        ),
        admin_actor,
    )
    comm_b = commissions.record_commission(
        CommissionLedgerEntry(rep_user_id=rep_b_user.id, source_type="assessment", commission_amount=200.0, status="earned"),
        admin_actor,
    )

    return {
        "router": router,
        "tokens": tokens,
        "rep_a_user": rep_a_user,
        "rep_b_user": rep_b_user,
        "ids": {
            "lead_a": lead_a.id, "lead_b": lead_b.id,
            "task_a": task_a.id, "task_b": task_b.id,
            "appt_a": appt_a.id, "appt_b": appt_b.id,
            "comm_a": comm_a.id, "comm_b": comm_b.id,
        },
    }


def _get(router, token, days=None):
    path = "/api/v1/sales/dashboard"
    if days is not None:
        path += f"?days={days}"
    return router.handle_request("GET", path, {"Authorization": f"Bearer {token}"}, b"")


def test_rep_tier_scoping_excludes_other_reps_data(env):
    status, _, data = _get(env["router"], env["tokens"]["rep_a"])
    assert status == 200
    ids = env["ids"]

    lead_ids = {l["id"] for l in data["leads"]["new"]}
    assert ids["lead_a"] in lead_ids
    assert ids["lead_b"] not in lead_ids

    task_ids = {
        t["id"] for section in ("overdue", "due_today", "upcoming") for t in data["followups"][section]
    }
    assert ids["task_a"] in task_ids
    assert ids["task_b"] not in task_ids

    appt_ids = {a["id"] for section in ("today", "upcoming") for a in data["appointments"][section]}
    assert ids["appt_a"] in appt_ids
    assert ids["appt_b"] not in appt_ids

    commission_ids = {
        c["id"] for status_bucket in data["commissions"].values() for c in status_bucket
    }
    assert ids["comm_a"] in commission_ids
    assert ids["comm_b"] not in commission_ids

    # get_pipeline_summary self-scopes via list_opportunities(actor); confirm
    # that scoping actually excludes rep B's $5000 opportunity from rep A's
    # pipeline totals (only rep A's $1000 opp_a should count).
    assert data["pipeline"]["total_deals"] == 1
    assert data["pipeline"]["active_pipeline_value"] == 1000.0


def test_team_key_absent_for_plain_rep(env):
    status, _, data = _get(env["router"], env["tokens"]["rep_a"])
    assert status == 200
    assert data["scope"] == "rep"
    assert "team" not in data


def test_team_key_present_for_sales_manager_role(env):
    status, _, data = _get(env["router"], env["tokens"]["mgr"])
    assert status == 200
    assert data["scope"] == "team"
    assert "team" in data
    # Company-wide totals: get_executive_dashboard is intentionally
    # unscoped (NEW-550, out of scope for this route) -- assert it
    # actually reflects BOTH reps' leads (2 total), not just one rep's,
    # confirming this is the real company-wide dashboard and not an
    # accidentally-narrowed copy.
    assert data["team"]["sales"]["total_leads"] == 2


def test_team_key_present_for_custom_permission_grant(env):
    """NEW-533 precedent: a plain ROLE_SALES actor individually granted
    PERM_READ_TEAM_SALES_DATA via custom_permissions gets the same
    team-tier visibility as a real ROLE_SALES_MANAGER."""
    status, _, data = _get(env["router"], env["tokens"]["granted_rep"])
    assert status == 200
    assert data["scope"] == "team"
    assert "team" in data


def test_manager_sees_both_reps_leads_via_team_scope(env):
    status, _, data = _get(env["router"], env["tokens"]["mgr"])
    assert status == 200
    ids = env["ids"]
    lead_ids = {l["id"] for l in data["leads"]["new"]}
    assert ids["lead_a"] in lead_ids
    assert ids["lead_b"] in lead_ids


def test_commissions_scope_independent_of_sales_data_scope(env):
    """An actor holding PERM_READ_TEAM_COMMISSIONS but NOT
    PERM_READ_TEAM_SALES_DATA must be narrowed everywhere else ("scope":
    "rep") while still seeing every rep's commission entries, and the
    response must say so explicitly via "commissions_scope" rather than
    letting the top-level "scope": "rep" imply commissions are rep-scoped
    too."""
    status, _, data = _get(env["router"], env["tokens"]["commissions_only_rep"])
    assert status == 200
    ids = env["ids"]

    # Sales-data narrowing is untouched: still "rep", leads/tasks/
    # appointments/pipeline still exclude rep A/B's data (this actor has
    # none of its own, so both should be empty/excluded).
    assert data["scope"] == "rep"
    assert "team" not in data
    lead_ids = {l["id"] for l in data["leads"]["new"]}
    assert ids["lead_a"] not in lead_ids
    assert ids["lead_b"] not in lead_ids

    # Commissions are independently team-scoped: both rep A's and rep B's
    # commission entries are visible despite "scope" being "rep".
    assert data["commissions_scope"] == "team"
    commission_ids = {
        c["id"] for status_bucket in data["commissions"].values() for c in status_bucket
    }
    assert ids["comm_a"] in commission_ids
    assert ids["comm_b"] in commission_ids


def test_commissions_scope_own_for_plain_rep(env):
    status, _, data = _get(env["router"], env["tokens"]["rep_a"])
    assert status == 200
    assert data["commissions_scope"] == "own"


def test_commission_summary_own_row_for_plain_rep_no_rankings(env):
    """B8.7d: a plain rep's dashboard carries their own this-month
    commission_summary row (backing the "This Month" panel) but no
    team_commission_rankings key at all -- that key is gated on
    PERM_READ_TEAM_COMMISSIONS, same independent-axis rule
    commissions_scope already established."""
    status, _, data = _get(env["router"], env["tokens"]["rep_a"])
    assert status == 200
    assert "team_commission_rankings" not in data
    summary = data["commission_summary"]
    assert summary["rep_user_id"] == env["rep_a_user"].id
    assert summary["total_earned"] == 100.0
    assert summary["entry_count"] == 1


def test_commission_summary_rankings_present_for_team_commissions_holder(env):
    """The commissions_only_rep actor (PERM_READ_TEAM_COMMISSIONS without
    PERM_READ_TEAM_SALES_DATA) gets team_commission_rankings covering
    both reps -- same independent-permission-axis point
    test_commissions_scope_independent_of_sales_data_scope already makes
    for the row-level "commissions" key."""
    status, _, data = _get(env["router"], env["tokens"]["commissions_only_rep"])
    assert status == 200
    assert "team" not in data  # PERM_READ_TEAM_SALES_DATA-gated, absent
    rankings = data["team_commission_rankings"]
    ranked_ids = {row["rep_user_id"] for row in rankings}
    assert ranked_ids == {env["rep_a_user"].id, env["rep_b_user"].id}
    by_rep = {row["rep_user_id"]: row for row in rankings}
    assert by_rep[env["rep_a_user"].id]["total_earned"] == 100.0
    assert by_rep[env["rep_b_user"].id]["total_earned"] == 200.0
    # Sales portal name-resolution fix: rep_user_name must resolve to the
    # rep's real full_name, not just the raw rep_user_id -- Sales Rep
    # Portal previously showed a bare rep number here.
    assert by_rep[env["rep_a_user"].id]["rep_user_name"] == "Rep A"
    assert by_rep[env["rep_b_user"].id]["rep_user_name"] == "Rep B"
    # This actor's own user_id doesn't match either rep, so their own
    # commission_summary row is the empty-defaults shape, not one of the
    # two reps' rows.
    assert data["commission_summary"]["total_earned"] == 0.0
    assert data["commission_summary"]["entry_count"] == 0


def test_days_param_changes_window(env):
    router = env["router"]
    token = env["tokens"]["rep_a"]

    # Create a far-future appointment for rep A, outside the default 7-day window.
    admin_token = env["tokens"]["admin"]

    far_date = _iso_date(20)
    s, _, appt_resp = router.handle_request(
        "POST",
        "/api/v1/appointments",
        {"Authorization": f"Bearer {admin_token}"},
        json.dumps({
            "title": "Far Appt",
            "start_time": f"{far_date}T10:00:00Z",
            "end_time": f"{far_date}T11:00:00Z",
            "assigned_user_id": env["rep_a_user"].id,
            "status": "confirmed",
        }).encode("utf-8"),
    )
    assert s == 201
    far_appt_id = appt_resp["appointment"]["id"]

    status, _, short_window = _get(router, token, days=7)
    assert status == 200
    short_ids = {a["id"] for section in ("today", "upcoming") for a in short_window["appointments"][section]}
    assert far_appt_id not in short_ids

    status, _, long_window = _get(router, token, days=25)
    assert status == 200
    long_ids = {a["id"] for section in ("today", "upcoming") for a in long_window["appointments"][section]}
    assert far_appt_id in long_ids


def test_actor_user_id_none_guard(env):
    router = env["router"]
    auth = router.auth
    no_id_actor = AuthContext(user_id=None, username="ghost", role=ROLE_SALES, actor_type="agent")
    token = "no-user-id-token"
    # authenticate_token resolves a real token from the DB; simulate the
    # guard directly against the router's dispatcher instead by monkeypatching
    # authenticate_token for this one call.
    original = auth.authenticate_token
    auth.authenticate_token = lambda t: no_id_actor
    try:
        status, _, data = router.handle_request(
            "GET", "/api/v1/sales/dashboard", {"Authorization": f"Bearer {token}"}, b""
        )
    finally:
        auth.authenticate_token = original

    assert status == 403
    assert "error" in data
