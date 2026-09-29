"""B8.3 Part A (CRMService.convert_lead_to_opportunity, NEW-556/NEW-557) and
Part D (CRMService.get_stage_duration_analytics) unit tests.

Part A covers: existing-customer conversion, missing-customer conversion via
customer_fields, audit logging on both writes, double-conversion rejection,
and the NEW-557 create_opportunity customer_id guard.

Part D covers: a full audit chain, a broken chain (changed_fields.
pipeline_stage.new is None on a stage_transition row, NEW-559), an
opportunity with no audit history at all falling back to stage_entered_at/
created_at, and the coverage counts (opportunities_with_full_chain /
opportunities_using_fallback / opportunities_chain_broken).
"""

import json
import time

import pytest

from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN, ROLE_SALES, ROLE_TECHNICIAN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Lead, Opportunity, PipelineStage
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    crm = CRMService(db, audit)

    # audit_log.actor_id has a real FK to users(id) -- an AuthContext with a
    # user_id that doesn't correspond to a real row would fail every write
    # this test suite exercises with an IntegrityError, not a permission
    # error, so real users are created here exactly like
    # test_crm_sales_engine.py's fixture does.
    sales_user = auth.create_user("b83_sales", "Pass123!", "Sales User", "b83sales@test.com", ROLE_SALES)
    admin_user = auth.create_user("b83_admin", "Pass123!", "Admin User", "b83admin@test.com", ROLE_ADMIN)
    no_perm_user = auth.create_user("b83_tech", "Pass123!", "Tech User", "b83tech@test.com", ROLE_TECHNICIAN)

    actor = AuthContext(sales_user.id, "b83_sales", ROLE_SALES, "human")
    admin_actor = AuthContext(admin_user.id, "b83_admin", ROLE_ADMIN, "human")
    no_perm_actor = AuthContext(no_perm_user.id, "b83_tech", ROLE_TECHNICIAN, "human")
    return {
        "db": db,
        "auth": auth,
        "audit": audit,
        "crm": crm,
        "actor": actor,
        "admin_actor": admin_actor,
        "no_perm_actor": no_perm_actor,
    }


# ==========================================
# Part A: convert_lead_to_opportunity
# ==========================================

def test_convert_lead_with_existing_customer(env):
    crm, actor = env["crm"], env["actor"]
    cust = crm.create_customer(Customer(first_name="Jane", last_name="Doe"), actor)
    lead = crm.create_lead(
        Lead(customer_id=cust.id, source="website", estimated_value=5000.0, notes="Roof leak"),
        actor,
    )

    opp = crm.convert_lead_to_opportunity(lead.id, actor)

    assert opp.customer_id == cust.id
    assert opp.estimated_value == 5000.0
    assert opp.notes == "Roof leak"
    assert opp.pipeline_stage == PipelineStage.NEW_LEAD

    refetched_lead = crm.get_lead(lead.id, actor)
    assert refetched_lead.status == "converted"


def test_convert_lead_with_no_customer_requires_customer_fields(env):
    crm, actor = env["crm"], env["actor"]
    lead = crm.create_lead(Lead(customer_id=None, source="referral", estimated_value=1000.0), actor)

    with pytest.raises(ValueError):
        crm.convert_lead_to_opportunity(lead.id, actor)


def test_convert_lead_with_no_customer_creates_one(env):
    crm, actor = env["crm"], env["actor"]
    lead = crm.create_lead(Lead(customer_id=None, source="referral", estimated_value=2500.0), actor)

    opp = crm.convert_lead_to_opportunity(
        lead.id,
        actor,
        customer_fields={"first_name": "New", "last_name": "Customer", "phone": "8605551234"},
    )

    assert opp.customer_id is not None
    created_cust = crm.get_customer(opp.customer_id, actor)
    assert created_cust.first_name == "New"
    assert created_cust.last_name == "Customer"
    assert created_cust.phone == "8605551234"


def test_convert_lead_writes_customer_id_back_onto_lead(env):
    """code-reviewer CHANGES REQUESTED, item 1: convert_lead_to_opportunity
    must write the newly-created Customer's id back onto the Lead, not just
    mark it converted. Re-fetch the Lead itself (not just the Opportunity/
    Customer) -- the original bug only shows up on the Lead's own row."""
    crm, actor = env["crm"], env["actor"]
    lead = crm.create_lead(Lead(customer_id=None, source="referral", estimated_value=2500.0), actor)

    opp = crm.convert_lead_to_opportunity(
        lead.id,
        actor,
        customer_fields={"first_name": "Link", "last_name": "Back"},
    )

    refetched_lead = crm.get_lead(lead.id, actor)
    assert refetched_lead.customer_id == opp.customer_id
    assert refetched_lead.status == "converted"


def test_convert_lead_unknown_customer_field_rejected(env):
    crm, actor = env["crm"], env["actor"]
    lead = crm.create_lead(Lead(customer_id=None, source="referral"), actor)

    with pytest.raises(ValueError):
        crm.convert_lead_to_opportunity(
            lead.id, actor, customer_fields={"first_name": "X", "assigned_user_id": 99}
        )


def test_convert_lead_audit_logs_both_writes(env):
    crm, audit, actor = env["crm"], env["audit"], env["actor"]
    lead = crm.create_lead(Lead(customer_id=None, source="referral", estimated_value=1000.0), actor)

    opp = crm.convert_lead_to_opportunity(
        lead.id, actor, customer_fields={"first_name": "Audit", "last_name": "Trail"}
    )

    conn = env["db"].get_connection()
    rows = conn.execute(
        "SELECT action, entity_type, entity_id FROM audit_log ORDER BY id ASC;"
    ).fetchall()
    actions = [(r["entity_type"], r["action"]) for r in rows]
    assert ("customer", "create") in actions
    assert ("opportunity", "create") in actions
    assert ("lead", "update") in actions


def test_convert_lead_twice_rejected(env):
    crm, actor = env["crm"], env["actor"]
    cust = crm.create_customer(Customer(first_name="A", last_name="B"), actor)
    lead = crm.create_lead(Lead(customer_id=cust.id, source="website"), actor)

    crm.convert_lead_to_opportunity(lead.id, actor)
    with pytest.raises(ValueError):
        crm.convert_lead_to_opportunity(lead.id, actor)


def test_convert_lead_inherits_assigned_user_id(env):
    crm, actor = env["crm"], env["actor"]
    cust = crm.create_customer(Customer(first_name="A", last_name="B"), actor)
    lead = crm.create_lead(Lead(customer_id=cust.id, source="website", assigned_user_id=actor.user_id), actor)

    opp = crm.convert_lead_to_opportunity(lead.id, actor)
    assert opp.assigned_user_id == actor.user_id


def test_create_opportunity_rejects_invalid_customer_id(env):
    """NEW-557."""
    crm, actor = env["crm"], env["actor"]
    with pytest.raises(ValueError):
        crm.create_opportunity(Opportunity(customer_id=0, title="No customer"), actor)
    with pytest.raises(ValueError):
        crm.create_opportunity(Opportunity(customer_id=-1, title="Negative customer"), actor)


# ==========================================
# Part D: get_stage_duration_analytics
# ==========================================

def _transition(crm, actor, opp_id, stage, lost_reason=None):
    return crm.transition_opportunity_stage(opp_id, stage, actor, lost_reason=lost_reason)


def test_stage_analytics_full_chain(env):
    crm, actor = env["crm"], env["actor"]
    cust = crm.create_customer(Customer(first_name="Full", last_name="Chain"), actor)
    opp = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Full chain deal", assigned_user_id=actor.user_id), actor
    )
    _transition(crm, actor, opp.id, PipelineStage.CONTACTED)
    _transition(crm, actor, opp.id, PipelineStage.APPOINTMENT_SET)

    result = crm.get_stage_duration_analytics(actor)

    assert result["opportunities_with_full_chain"] >= 1
    assert result["opportunities_chain_broken"] == 0
    assert isinstance(result["avg_hours_per_stage"], dict)
    stuck_ids = [s["opportunity_id"] for s in result["currently_stuck"]]
    assert opp.id in stuck_ids


def test_stage_analytics_broken_chain(env):
    """NEW-559: a stage_transition row whose changed_fields.pipeline_stage.new
    is None must exclude that row from duration math and land the
    opportunity in the chain-broken/fallback bucket, not crash."""
    crm, audit, actor = env["crm"], env["audit"], env["actor"]
    cust = crm.create_customer(Customer(first_name="Broken", last_name="Chain"), actor)
    opp = crm.create_opportunity(Opportunity(customer_id=cust.id, title="Broken chain deal"), actor)

    # Simulate a corrupted stage_transition audit row directly (the actual
    # NEW-559 production bug this guards is not itself being fixed here).
    conn = env["db"].get_connection()
    with conn:
        conn.execute(
            "INSERT INTO audit_log (timestamp, actor_id, actor_role, actor_type, action, "
            "entity_type, entity_id, change_summary, details_json) VALUES "
            "(?, ?, ?, ?, 'stage_transition', 'opportunity', ?, 'corrupted row', ?);",
            (
                "2026-01-01T00:00:00+00:00",
                actor.user_id,
                actor.role,
                actor.actor_type,
                opp.id,
                json.dumps({"changed_fields": {"pipeline_stage": {"old": "new_lead", "new": None}}}),
            ),
        )

    result = crm.get_stage_duration_analytics(actor)
    assert result["opportunities_chain_broken"] >= 1
    assert result["opportunities_using_fallback"] >= 1


def test_stage_analytics_malformed_timestamp_in_primary_chain_degrades_gracefully(env):
    """code-reviewer CHANGES REQUESTED, item 3: a malformed timestamp on a
    create/stage_transition row in the primary chain-walking loop must not
    raise out of the endpoint -- it should be treated the same as any other
    broken chain (chain_broken bucket), same as the existing
    stage_entered_at/created_at fallback path already tolerates."""
    crm, actor = env["crm"], env["actor"]
    cust = crm.create_customer(Customer(first_name="Bad", last_name="Timestamp"), actor)
    opp = crm.create_opportunity(Opportunity(customer_id=cust.id, title="Malformed ts deal"), actor)
    _transition(crm, actor, opp.id, PipelineStage.CONTACTED)

    conn = env["db"].get_connection()
    with conn:
        conn.execute(
            "UPDATE audit_log SET timestamp = 'not-a-real-timestamp' "
            "WHERE entity_type = 'opportunity' AND entity_id = ? AND action = 'stage_transition';",
            (opp.id,),
        )

    result = crm.get_stage_duration_analytics(actor)  # must not raise
    assert result["opportunities_chain_broken"] >= 1


def test_stage_analytics_malformed_create_row_timestamp_counts_as_chain_broken(env):
    """code-reviewer CHANGES REQUESTED, item 3 (create-row site specifically):
    a malformed timestamp on the CREATE audit row is corrupt data, not
    absent data -- it must land in opportunities_chain_broken, not be lumped
    into opportunities_using_fallback's no-audit-history bucket."""
    crm, actor = env["crm"], env["actor"]
    cust = crm.create_customer(Customer(first_name="Bad", last_name="CreateTimestamp"), actor)
    opp = crm.create_opportunity(Opportunity(customer_id=cust.id, title="Malformed create ts deal"), actor)

    conn = env["db"].get_connection()
    with conn:
        conn.execute(
            "UPDATE audit_log SET timestamp = 'not-a-real-timestamp' "
            "WHERE entity_type = 'opportunity' AND entity_id = ? AND action = 'create';",
            (opp.id,),
        )

    result = crm.get_stage_duration_analytics(actor)  # must not raise
    assert result["opportunities_chain_broken"] >= 1


def test_stage_analytics_broken_chain_retracts_partial_stage_hours(env):
    """code-reviewer's "also" note: an opportunity whose chain breaks
    partway through must not have the hours it accumulated before the break
    leak into avg_hours_per_stage -- the whole opportunity's contribution
    should be retracted, not partially retained.

    Timestamps are pinned explicitly (not left at wall-clock `now`) so the
    corrupted row is guaranteed to sort AFTER the one valid transition in
    the ORDER BY entity_id, timestamp ASC audit query -- otherwise the
    chain could break on its very first row, and pending_stage_hours would
    never have anything to retract, making this test pass identically
    whether or not the retraction fix is present."""
    crm, audit, actor = env["crm"], env["audit"], env["actor"]
    cust = crm.create_customer(Customer(first_name="Partial", last_name="Retract"), actor)
    opp = crm.create_opportunity(Opportunity(customer_id=cust.id, title="Partial retract deal"), actor)
    _transition(crm, actor, opp.id, PipelineStage.CONTACTED)

    conn = env["db"].get_connection()
    with conn:
        conn.execute(
            "UPDATE audit_log SET timestamp = '2026-01-01T00:00:00+00:00' "
            "WHERE entity_type = 'opportunity' AND entity_id = ? AND action = 'create';",
            (opp.id,),
        )
        conn.execute(
            "UPDATE audit_log SET timestamp = '2026-01-01T02:00:00+00:00' "
            "WHERE entity_type = 'opportunity' AND entity_id = ? AND action = 'stage_transition';",
            (opp.id,),
        )
        # Corrupted second stage_transition row, timestamped AFTER the real
        # one above, so the walk computes and appends a NEW_LEAD -> 2.0hr
        # pending entry before hitting this break.
        conn.execute(
            "INSERT INTO audit_log (timestamp, actor_id, actor_role, actor_type, action, "
            "entity_type, entity_id, change_summary, details_json) VALUES "
            "(?, ?, ?, ?, 'stage_transition', 'opportunity', ?, 'corrupted row', ?);",
            (
                "2026-01-01T03:00:00+00:00",
                actor.user_id,
                actor.role,
                actor.actor_type,
                opp.id,
                json.dumps({"changed_fields": {"pipeline_stage": {"old": "contacted", "new": None}}}),
            ),
        )

    result = crm.get_stage_duration_analytics(actor)
    assert result["opportunities_chain_broken"] >= 1
    # This test's env fixture gives each test a fresh in-memory DB, and this
    # is the only opportunity created here -- so if the NEW_LEAD -> CONTACTED
    # hours entry computed before the break had leaked into
    # avg_hours_per_stage instead of being retracted, PipelineStage.NEW_LEAD
    # would be the only possible source of it.
    assert PipelineStage.NEW_LEAD not in result["avg_hours_per_stage"]


def test_stage_analytics_no_audit_history_falls_back(env):
    """Migrated (migrate_aigentik.py-imported) opportunities have no audit
    history at all -- must fall back to stage_entered_at/created_at for a
    currently-stuck figure, not be silently dropped."""
    crm, actor = env["crm"], env["actor"]
    cust = crm.create_customer(Customer(first_name="No", last_name="History"), actor)
    opp = crm.create_opportunity(Opportunity(customer_id=cust.id, title="Imported deal"), actor)

    # Wipe this opportunity's audit rows entirely to simulate a migrated
    # record with no audit trail.
    conn = env["db"].get_connection()
    with conn:
        conn.execute(
            "DELETE FROM audit_log WHERE entity_type = 'opportunity' AND entity_id = ?;", (opp.id,)
        )

    result = crm.get_stage_duration_analytics(actor)
    assert result["opportunities_using_fallback"] >= 1
    stuck_ids = [s["opportunity_id"] for s in result["currently_stuck"]]
    assert opp.id in stuck_ids


def test_stage_analytics_coverage_counts_sum_correctly(env):
    crm, actor = env["crm"], env["actor"]
    cust = crm.create_customer(Customer(first_name="Cov", last_name="Erage"), actor)
    full_opp = crm.create_opportunity(Opportunity(customer_id=cust.id, title="Full"), actor)
    _transition(crm, actor, full_opp.id, PipelineStage.CONTACTED)

    no_hist_opp = crm.create_opportunity(Opportunity(customer_id=cust.id, title="No history"), actor)
    conn = env["db"].get_connection()
    with conn:
        conn.execute(
            "DELETE FROM audit_log WHERE entity_type = 'opportunity' AND entity_id = ?;",
            (no_hist_opp.id,),
        )

    result = crm.get_stage_duration_analytics(actor)
    assert result["opportunities_with_full_chain"] >= 1
    assert result["opportunities_using_fallback"] >= 1


def test_stage_analytics_permission_denied_without_read_permission(env):
    crm = env["crm"]
    with pytest.raises(PermissionError):
        crm.get_stage_duration_analytics(env["no_perm_actor"])


def test_stage_analytics_lost_reason_required_on_lost_transition(env):
    """Sanity check that the existing transition_opportunity_stage guard
    (which the kanban UI's client-side lost-reason prompt depends on) is
    still in force -- not a new behavior, just confirming the contract
    Part C's UI gate relies on."""
    crm, actor = env["crm"], env["actor"]
    cust = crm.create_customer(Customer(first_name="Lost", last_name="Deal"), actor)
    opp = crm.create_opportunity(Opportunity(customer_id=cust.id, title="Will be lost"), actor)
    with pytest.raises(ValueError):
        crm.transition_opportunity_stage(opp.id, PipelineStage.LOST, actor, lost_reason=None)
