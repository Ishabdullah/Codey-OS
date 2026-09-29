"""
Unit tests for B8.7b (D4, sales_rep_portal.md §4, Ish-approved
2026-09-16; repriced 2026-09-22 mid-round): the new
`homecare_subscriptions` table, CRMService.sign_contract's automatic
HomeCare enrollment trigger (fires exactly once a contract whose
template_name is one of the four 'homecare_*' values reaches
status='signed'), the Phase 2 subscription-upsell bonus
(commission_ledger_entries, source_type='subscription_upsell'), and the
lazy-evaluated 90-day clawback on cancel_homecare_subscription.

Note on the clawback's real ledger shape (deliberately verified, not
assumed): the reversal row CommissionService.reverse_commission writes
mirrors the ORIGINAL entry's own source_type (see its docstring) --
CommissionService has no separate 'chargeback' write path. A within-90-day
cancellation therefore produces a source_type='subscription_upsell',
status='reversed' row with reversed_entry_id pointing at the original
Phase 2 bonus entry, NOT a source_type='chargeback' row. Tests below
assert that real shape.
"""

from __future__ import annotations

import base64
import io
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Contract, Customer, Project
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.commission_service import CommissionService
from restoricon_core.services.crm_service import CRMService


def _png_data_url() -> str:
    img = Image.new("RGBA", (20, 10), (10, 20, 30, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    encoded = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(tmp_path / "docstore"))
    db = DatabaseManager(":memory:")
    audit_service = AuditService(db)
    commission_service = CommissionService(db, audit_service)
    crm = CRMService(db, audit_service, commission_service=commission_service)
    auth_service = AuthService(db)

    admin_user = auth_service.create_user(
        username="hc_admin", plain_password="Password123", full_name="Admin",
        email="hc_admin@test.com", role=ROLE_ADMIN,
    )
    admin = AuthContext(user_id=admin_user.id, username="hc_admin", role=ROLE_ADMIN, actor_type="human")

    rep_user = auth_service.create_user(
        username="hc_rep", plain_password="Password123", full_name="Rep",
        email="hc_rep@test.com", role=ROLE_SALES,
    )
    rep = AuthContext(user_id=rep_user.id, username="hc_rep", role=ROLE_SALES, actor_type="human")

    cust = crm.create_customer(
        Customer(first_name="Home", last_name="Owner", email="home_owner@test.com", assigned_user_id=rep.user_id),
        admin,
    )
    customer_user = auth_service.create_user(
        username="hc_cust", plain_password="Password123", full_name="Home Owner",
        email="hc_cust_login@test.com", role=ROLE_CUSTOMER, customer_id=cust.id,
    )
    actor_customer = AuthContext(
        user_id=customer_user.id, username="hc_cust", role=ROLE_CUSTOMER,
        actor_type="human", customer_id=cust.id,
    )

    return {
        "db": db, "crm": crm, "audit": audit_service, "auth": auth_service,
        "commission": commission_service, "admin": admin, "rep": rep,
        "cust": cust, "actor_customer": actor_customer,
    }


def _make_contract(env, number, template_name, actor=None, project_id=None):
    return env["crm"].create_contract(
        Contract(
            contract_number=number,
            customer_id=env["cust"].id,
            project_id=project_id,
            title="HomeCare Agreement",
            template_name=template_name,
            content="Terms...",
        ),
        actor or env["rep"],
    )


# ---------------------------------------------------------------------------
# Core enrollment + Phase 2 bonus
# ---------------------------------------------------------------------------

def test_signing_homecare_contract_creates_subscription_and_phase2_bonus(env):
    plan = env["commission"].get_commission_plan_config(env["admin"])
    contract = _make_contract(env, "CTR-HC-1", "homecare_basic")

    signed = env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])
    assert signed.status == "signed"

    conn = env["db"].get_connection()
    subs = conn.execute("SELECT * FROM homecare_subscriptions WHERE contract_id = ?;", (contract.id,)).fetchall()
    assert len(subs) == 1
    sub = subs[0]
    assert sub["customer_id"] == env["cust"].id
    assert sub["tier"] == "homecare_basic"
    assert sub["monthly_fee"] == plan.homecare_basic_monthly_fee
    assert sub["originating_rep_user_id"] == env["rep"].user_id
    assert sub["status"] == "active"
    assert sub["cancelled_at"] is None

    entries = env["commission"].list_commissions(env["admin"], rep_user_id=env["rep"].user_id)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.source_type == "subscription_upsell"
    assert entry.source_id == sub["id"]
    assert entry.rep_user_id == env["rep"].user_id
    # Bonus reads the LIVE config value, not a hardcoded 179/119, so this
    # assertion can't mask a wiring bug in either direction of the
    # mid-round reprice.
    assert entry.commission_amount == plan.homecare_basic_monthly_fee - plan.assessment_flat_commission
    assert entry.status == "earned"


def test_bonus_amount_matches_each_real_tier(env):
    """D4's four real tiers, bonus = monthly_fee - assessment_flat_commission,
    read live from commission_plan_config (not hardcoded)."""
    plan = env["commission"].get_commission_plan_config(env["admin"])
    tiers = {
        "homecare_basic": plan.homecare_basic_monthly_fee,
        "homecare_plus": plan.homecare_plus_monthly_fee,
        "homecare_complete": plan.homecare_complete_monthly_fee,
        "homecare_estate": plan.homecare_estate_monthly_fee,
    }
    for i, (tier, fee) in enumerate(tiers.items()):
        contract = _make_contract(env, f"CTR-HC-TIER-{i}", tier)
        env["crm"].sign_contract(contract.id, f"sig-{i}", env["actor_customer"])

        conn = env["db"].get_connection()
        sub = conn.execute(
            "SELECT id FROM homecare_subscriptions WHERE contract_id = ?;", (contract.id,)
        ).fetchone()
        entries = [
            e for e in env["commission"].list_commissions(env["admin"], rep_user_id=env["rep"].user_id)
            if e.source_type == "subscription_upsell" and e.source_id == sub["id"]
        ]
        assert len(entries) == 1
        assert entries[0].commission_amount == fee - plan.assessment_flat_commission


def test_general_remodeling_contract_signing_creates_no_subscription(env):
    contract = _make_contract(env, "CTR-GR-1", "general_remodeling")
    signed = env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])
    assert signed.status == "signed"

    conn = env["db"].get_connection()
    subs = conn.execute("SELECT * FROM homecare_subscriptions;").fetchall()
    assert subs == []
    entries = env["commission"].list_commissions(env["admin"])
    assert entries == []


def test_contract_with_no_template_name_creates_no_subscription(env):
    contract = env["crm"].create_contract(
        Contract(contract_number="CTR-NONE-1", customer_id=env["cust"].id, title="Legacy", content="..."),
        env["rep"],
    )
    signed = env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])
    assert signed.status == "signed"

    conn = env["db"].get_connection()
    subs = conn.execute("SELECT * FROM homecare_subscriptions;").fetchall()
    assert subs == []


# ---------------------------------------------------------------------------
# No-rep case -- mirrors B8.7a exactly
# ---------------------------------------------------------------------------

def test_contract_with_no_assigned_rep_creates_subscription_but_skips_commission(env):
    unclaimed_cust = env["crm"].create_customer(
        Customer(first_name="Unclaimed", last_name="Owner", email="unclaimed_hc@test.com"), env["admin"],
    )
    unclaimed_cust_user = env["auth"].create_user(
        username="hc_unclaimed", plain_password="Password123", full_name="Unclaimed",
        email="hc_unclaimed_login@test.com", role=ROLE_CUSTOMER, customer_id=unclaimed_cust.id,
    )
    actor_unclaimed = AuthContext(
        user_id=unclaimed_cust_user.id, username="hc_unclaimed", role=ROLE_CUSTOMER,
        actor_type="human", customer_id=unclaimed_cust.id,
    )
    # Created by admin, not a rep -- create_contract force-sets
    # assigned_user_id to the CREATING actor, so an admin-created contract
    # has assigned_user_id == admin.user_id, not None. Use a
    # ROLE_SALES-authored-but-then-cleared shape instead: directly clear
    # assigned_user_id at the DB level to simulate a genuinely rep-less
    # contract (e.g. one whose owning rep account was later deleted --
    # assigned_user_id is FK-less by design).
    contract = env["crm"].create_contract(
        Contract(contract_number="CTR-HC-NOREP-1", customer_id=unclaimed_cust.id, title="HC", content="...", template_name="homecare_basic"),
        env["admin"],
    )
    conn = env["db"].get_connection()
    with conn:
        conn.execute("UPDATE contracts SET assigned_user_id = NULL WHERE id = ?;", (contract.id,))

    signed = env["crm"].sign_contract(contract.id, _png_data_url(), actor_unclaimed)
    assert signed.status == "signed"

    subs = conn.execute("SELECT * FROM homecare_subscriptions WHERE contract_id = ?;", (contract.id,)).fetchall()
    assert len(subs) == 1
    assert subs[0]["originating_rep_user_id"] is None
    assert subs[0]["status"] == "active"

    entries = env["commission"].list_commissions(env["admin"])
    assert entries == []

    logs = env["audit"].query_logs(
        env["admin"], entity_type="homecare_subscription", entity_id=subs[0]["id"],
        action="commission_skipped_no_rep",
    )
    assert len(logs) == 1


# ---------------------------------------------------------------------------
# Idempotency / no new double-fire path
# ---------------------------------------------------------------------------

def test_signing_already_signed_contract_raises_before_reaching_enrollment(env):
    """sign_contract's own pre-existing idempotency guard (status ==
    'signed' -> ValueError) fires before the enrollment trigger, for the
    single-signer path -- confirms the normal path can't double-enroll."""
    contract = _make_contract(env, "CTR-HC-IDEMP-1", "homecare_basic")
    env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])

    with pytest.raises(ValueError):
        env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])

    conn = env["db"].get_connection()
    subs = conn.execute("SELECT * FROM homecare_subscriptions WHERE contract_id = ?;", (contract.id,)).fetchall()
    assert len(subs) == 1


def test_double_fire_past_any_guard_is_caught_by_the_contract_id_unique_index(env):
    """Second layer of defense: even if the enrollment trigger somehow
    ran twice for the same contract (bypassing sign_contract's own
    idempotency guard), the UNIQUE(contract_id) index on
    homecare_subscriptions rejects the second INSERT as an
    IntegrityError -- which sign_contract must catch and turn into a
    no-op audit entry, not a crash and not a false failure on the
    (already-committed) sign. Exercises this directly by pre-seeding a
    homecare_subscriptions row for this contract before the real sign
    call runs its enrollment trigger."""
    contract = _make_contract(env, "CTR-HC-DUPE-1", "homecare_basic")

    conn = env["db"].get_connection()
    with conn:
        conn.execute(
            "INSERT INTO homecare_subscriptions "
            "(customer_id, property_id, contract_id, tier, monthly_fee, "
            "originating_rep_user_id, status, enrolled_at, cancelled_at) "
            "VALUES (?, NULL, ?, 'homecare_basic', 119.0, ?, 'active', datetime('now'), NULL);",
            (env["cust"].id, contract.id, env["rep"].user_id),
        )

    signed = env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])
    assert signed.status == "signed"

    subs = conn.execute("SELECT * FROM homecare_subscriptions WHERE contract_id = ?;", (contract.id,)).fetchall()
    assert len(subs) == 1  # only the pre-seeded row

    logs = env["audit"].query_logs(
        env["admin"], entity_type="contract", entity_id=contract.id,
        action="homecare_enrollment_duplicate_skipped",
    )
    assert len(logs) == 1


def test_multi_party_contract_enrolls_only_after_last_signer_not_first(env):
    """A multi-party HomeCare contract must not enroll on the FIRST
    signature -- only once _signed.status == 'signed' (i.e. every
    required signer has completed)."""
    from restoricon_core.auth import ROLE_PROJECT_MANAGER

    pm_user = env["auth"].create_user(
        username="hc_pm", plain_password="Password123", full_name="PM",
        email="hc_pm@test.com", role=ROLE_PROJECT_MANAGER,
    )
    actor_pm = AuthContext(user_id=pm_user.id, username="hc_pm", role=ROLE_PROJECT_MANAGER, actor_type="human")

    contract = _make_contract(env, "CTR-HC-MP-1", "homecare_plus")
    env["crm"].add_contract_signers(
        contract.id,
        [
            {"party_role": "customer", "signer_name": "Home Owner"},
            {"party_role": "project_manager", "signer_name": "PM"},
        ],
        env["admin"],
    )

    after_first = env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"], party_role="customer")
    assert after_first.status != "signed"

    conn = env["db"].get_connection()
    subs_after_first = conn.execute(
        "SELECT * FROM homecare_subscriptions WHERE contract_id = ?;", (contract.id,)
    ).fetchall()
    assert subs_after_first == []  # not enrolled yet -- only one of two signers done

    after_second = env["crm"].sign_contract(contract.id, "portal_countersignature", actor_pm, party_role="project_manager")
    assert after_second.status == "signed"

    subs_after_second = conn.execute(
        "SELECT * FROM homecare_subscriptions WHERE contract_id = ?;", (contract.id,)
    ).fetchall()
    assert len(subs_after_second) == 1


# ---------------------------------------------------------------------------
# property_id resolution
# ---------------------------------------------------------------------------

def test_subscription_resolves_property_id_from_contracts_project(env):
    project = env["crm"].create_project(
        Project(customer_id=env["cust"].id, title="HC Project", property_address="123 Main St", project_type="homecare"),
        env["admin"],
    )
    project_id = project.id
    conn = env["db"].get_connection()

    with conn:
        cursor = conn.execute(
            "INSERT INTO properties (customer_id, address, created_at) VALUES (?, '123 Main St', datetime('now'));",
            (env["cust"].id,),
        )
        property_id = cursor.lastrowid
        conn.execute("UPDATE projects SET property_id = ? WHERE id = ?;", (property_id, project_id))

    contract = _make_contract(env, "CTR-HC-PROP-1", "homecare_basic", project_id=project_id)
    env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])

    sub = conn.execute("SELECT * FROM homecare_subscriptions WHERE contract_id = ?;", (contract.id,)).fetchone()
    assert sub["property_id"] == property_id


def test_subscription_property_id_is_none_when_contract_has_no_project(env):
    contract = _make_contract(env, "CTR-HC-NOPROJ-1", "homecare_basic")
    env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])

    conn = env["db"].get_connection()
    sub = conn.execute("SELECT * FROM homecare_subscriptions WHERE contract_id = ?;", (contract.id,)).fetchone()
    assert sub["property_id"] is None


# ---------------------------------------------------------------------------
# Plan-config read inside try/except from the start (B8.7a round-1 bug,
# must not be repeated)
# ---------------------------------------------------------------------------

def test_get_commission_plan_config_raising_does_not_fail_the_already_committed_sign(env, monkeypatch):
    contract = _make_contract(env, "CTR-HC-PLANFAIL-1", "homecare_basic")

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated get_commission_plan_config failure")

    monkeypatch.setattr(CommissionService, "get_commission_plan_config", _raise)

    signed = env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])
    assert signed.status == "signed"  # the sign itself must succeed regardless

    conn = env["db"].get_connection()
    subs = conn.execute("SELECT * FROM homecare_subscriptions WHERE contract_id = ?;", (contract.id,)).fetchall()
    assert subs == []  # no subscription either -- can't snapshot a fee it couldn't read

    logs = env["audit"].query_logs(
        env["admin"], entity_type="contract", entity_id=contract.id, action="homecare_enrollment_failed",
    )
    assert len(logs) == 1
    assert "simulated get_commission_plan_config failure" in logs[0].change_summary


# ---------------------------------------------------------------------------
# 90-day clawback
# ---------------------------------------------------------------------------

def test_cancel_within_90_days_reverses_the_phase2_bonus(env):
    contract = _make_contract(env, "CTR-HC-CLAW-1", "homecare_basic")
    env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])

    conn = env["db"].get_connection()
    sub_row = conn.execute("SELECT * FROM homecare_subscriptions WHERE contract_id = ?;", (contract.id,)).fetchone()
    original = [
        e for e in env["commission"].list_commissions(env["admin"], rep_user_id=env["rep"].user_id)
        if e.source_type == "subscription_upsell"
    ][0]

    cancelled = env["crm"].cancel_homecare_subscription(sub_row["id"], env["rep"])
    assert cancelled.status == "cancelled"
    assert cancelled.cancelled_at is not None

    entries = env["commission"].list_commissions(env["admin"], rep_user_id=env["rep"].user_id, include_reversed=True)
    reversals = [e for e in entries if e.reversed_entry_id == original.id]
    assert len(reversals) == 1
    reversal = reversals[0]
    # The real reverse_commission() shape -- mirrors the original entry's
    # own source_type, NOT a distinct 'chargeback' source_type (see
    # module docstring).
    assert reversal.source_type == "subscription_upsell"
    assert reversal.status == "reversed"
    assert reversal.commission_amount == -original.commission_amount


def test_cancel_after_90_days_does_not_reverse(env):
    contract = _make_contract(env, "CTR-HC-CLAW-2", "homecare_basic")
    env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])

    conn = env["db"].get_connection()
    sub_row = conn.execute("SELECT * FROM homecare_subscriptions WHERE contract_id = ?;", (contract.id,)).fetchone()

    # Backdate enrolled_at to 91 days ago.
    old_enrolled_at = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
    with conn:
        conn.execute(
            "UPDATE homecare_subscriptions SET enrolled_at = ? WHERE id = ?;",
            (old_enrolled_at, sub_row["id"]),
        )

    original = [
        e for e in env["commission"].list_commissions(env["admin"], rep_user_id=env["rep"].user_id)
        if e.source_type == "subscription_upsell"
    ][0]

    cancelled = env["crm"].cancel_homecare_subscription(sub_row["id"], env["rep"])
    assert cancelled.status == "cancelled"

    entries = env["commission"].list_commissions(env["admin"], rep_user_id=env["rep"].user_id, include_reversed=True)
    reversals = [e for e in entries if e.reversed_entry_id == original.id]
    assert reversals == []


def test_cancel_with_no_original_bonus_row_does_not_crash(env):
    """A rep-less enrollment has no Phase 2 bonus row to reverse -- cancel
    within 90 days must still succeed cleanly, no crash, nothing to claw
    back."""
    contract = env["crm"].create_contract(
        Contract(contract_number="CTR-HC-CLAW-NOREP-1", customer_id=env["cust"].id, title="HC", content="...", template_name="homecare_basic"),
        env["admin"],
    )
    conn = env["db"].get_connection()
    with conn:
        conn.execute("UPDATE contracts SET assigned_user_id = NULL WHERE id = ?;", (contract.id,))

    env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])
    sub_row = conn.execute("SELECT * FROM homecare_subscriptions WHERE contract_id = ?;", (contract.id,)).fetchone()

    cancelled = env["crm"].cancel_homecare_subscription(sub_row["id"], env["admin"])
    assert cancelled.status == "cancelled"


def test_cancel_already_cancelled_subscription_raises(env):
    contract = _make_contract(env, "CTR-HC-CLAW-3", "homecare_basic")
    env["crm"].sign_contract(contract.id, _png_data_url(), env["actor_customer"])
    conn = env["db"].get_connection()
    sub_row = conn.execute("SELECT * FROM homecare_subscriptions WHERE contract_id = ?;", (contract.id,)).fetchone()

    env["crm"].cancel_homecare_subscription(sub_row["id"], env["rep"])
    with pytest.raises(ValueError):
        env["crm"].cancel_homecare_subscription(sub_row["id"], env["rep"])


# ---------------------------------------------------------------------------
# Mid-round reprice: the one-time corrective UPDATE in _migrate_schema()
# for a DB that already seeded commission_plan_config with B8.7a's
# original 179.0 default before this round's 119.0 correction. Must be
# file-backed (tmp_path), not :memory: -- a fresh :memory: DB is always
# seeded directly at the new 119.0 default and can never exercise the
# "reopen an existing DB that already has the old value" path this
# corrective UPDATE exists for.
# ---------------------------------------------------------------------------

def test_reprice_migration_corrects_existing_179_row_on_reopen(tmp_path):
    db_path = str(tmp_path / "reprice.db")

    db1 = DatabaseManager(db_path)
    conn1 = db1.get_connection()
    with conn1:
        conn1.execute(
            "UPDATE commission_plan_config SET homecare_basic_monthly_fee = 179.0 WHERE id = 1;"
        )
    row = conn1.execute("SELECT homecare_basic_monthly_fee FROM commission_plan_config WHERE id = 1;").fetchone()
    assert row["homecare_basic_monthly_fee"] == 179.0  # simulated pre-reprice state, confirmed set

    # Reopening the SAME DB file re-runs _migrate_schema() -- the
    # corrective UPDATE must fire and fix the stale value.
    db2 = DatabaseManager(db_path)
    conn2 = db2.get_connection()
    row2 = conn2.execute("SELECT * FROM commission_plan_config WHERE id = 1;").fetchone()
    assert row2["homecare_basic_monthly_fee"] == 119.0
    # The other five fields must be untouched by the narrowly-scoped
    # corrective UPDATE.
    assert row2["assessment_price"] == 299.0
    assert row2["assessment_flat_commission"] == 100.0
    assert row2["homecare_plus_monthly_fee"] == 399.0
    assert row2["homecare_complete_monthly_fee"] == 599.0
    assert row2["homecare_estate_monthly_fee"] == 999.0


def test_reprice_migration_is_idempotent_on_repeated_reopen(tmp_path):
    db_path = str(tmp_path / "reprice_idempotent.db")

    db1 = DatabaseManager(db_path)
    conn1 = db1.get_connection()
    with conn1:
        conn1.execute(
            "UPDATE commission_plan_config SET homecare_basic_monthly_fee = 179.0 WHERE id = 1;"
        )

    DatabaseManager(db_path)  # first reopen: corrects 179.0 -> 119.0
    db3 = DatabaseManager(db_path)  # second reopen: must be a no-op, not re-touch the row
    row = db3.get_connection().execute(
        "SELECT homecare_basic_monthly_fee FROM commission_plan_config WHERE id = 1;"
    ).fetchone()
    assert row["homecare_basic_monthly_fee"] == 119.0


def test_reprice_migration_does_not_clobber_a_deliberately_customized_value(tmp_path):
    """The corrective UPDATE is scoped to WHERE homecare_basic_monthly_fee
    = 179.0 specifically so it never overwrites a value an operator has
    already deliberately changed to something other than the old
    default (e.g. via a future dashboard round)."""
    db_path = str(tmp_path / "reprice_custom.db")

    db1 = DatabaseManager(db_path)
    conn1 = db1.get_connection()
    with conn1:
        conn1.execute(
            "UPDATE commission_plan_config SET homecare_basic_monthly_fee = 150.0 WHERE id = 1;"
        )

    db2 = DatabaseManager(db_path)
    row = db2.get_connection().execute(
        "SELECT homecare_basic_monthly_fee FROM commission_plan_config WHERE id = 1;"
    ).fetchone()
    assert row["homecare_basic_monthly_fee"] == 150.0  # untouched, not reset to 119.0


def test_fresh_db_seeds_directly_at_119(tmp_path):
    """A brand-new DB (never seeded at the old 179.0 default) is seeded
    directly with the corrected 119.0 -- the corrective UPDATE is a no-op
    for it, not a second write."""
    db_path = str(tmp_path / "fresh.db")
    db = DatabaseManager(db_path)
    row = db.get_connection().execute(
        "SELECT homecare_basic_monthly_fee FROM commission_plan_config WHERE id = 1;"
    ).fetchone()
    assert row["homecare_basic_monthly_fee"] == 119.0
