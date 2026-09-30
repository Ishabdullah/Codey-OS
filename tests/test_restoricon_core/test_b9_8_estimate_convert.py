"""
Tests for Phase B9.8 -- `EstimateService.convert()` (the ACCEPTED ->
CONVERTED Project-creation half of the estimate->job workflow).

Reuses the `env` fixture shape from `test_b9_2_estimate_service.py`
(~lines 35-63), extended with `_accept_with_signed_contract()`, a helper
that drives a fresh estimate through `add_line()` -> `record_decision()`
(accepted) -> a direct contract-status UPDATE to `'signed'` (mirroring
`test_accepted_decision_creates_contract_in_same_transaction`'s own setup
pattern for getting to ACCEPTED-with-a-linked-Contract).
"""

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_READ_ALL_ESTIMATES,
    PERM_WRITE_ESTIMATES,
    ROLE_ADMIN,
    ROLE_AI_AGENT,
    ROLE_MANAGER,
    ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Opportunity, Project, Property
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import ClaimConflictError, CRMService
from restoricon_core.services.estimate_service import EstimateService


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    crm = CRMService(db, audit)
    svc = EstimateService(db, audit)

    admin_user = auth.create_user("admin1", "Pass123!", "Admin One", "admin1@restoricon.com", role=ROLE_ADMIN)
    admin = AuthContext(admin_user.id, admin_user.username, ROLE_ADMIN, "human")

    sales_user = auth.create_user("sales1", "Pass123!", "Sales One", "sales1@restoricon.com", role=ROLE_SALES)
    sales = AuthContext(sales_user.id, sales_user.username, ROLE_SALES, "human")

    sales2_user = auth.create_user("sales2", "Pass123!", "Sales Two", "sales2@restoricon.com", role=ROLE_SALES)
    sales2 = AuthContext(sales2_user.id, sales2_user.username, ROLE_SALES, "human")

    manager_user = auth.create_user("mgr1", "Pass123!", "Manager One", "mgr1@restoricon.com", role=ROLE_MANAGER)
    manager = AuthContext(manager_user.id, manager_user.username, ROLE_MANAGER, "human")

    agent_user = auth.create_user("agent1", "Pass123!", "Agent One", "agent1@restoricon.com", role=ROLE_AI_AGENT)
    agent = AuthContext(agent_user.id, agent_user.username, ROLE_AI_AGENT, "agent")

    customer = crm.create_customer(Customer(first_name="Jane", last_name="Doe"), admin)

    return {
        "db": db, "svc": svc, "crm": crm, "auth": auth, "admin": admin, "sales": sales,
        "sales2": sales2, "manager": manager, "agent": agent, "customer_id": customer.id,
    }


class ZeroPermissionActor:
    user_id = 999999
    username = "zero_perm"
    role = "nobody"
    actor_type = "agent"
    customer_id = None
    token = None

    def has_permission(self, permission: str) -> bool:
        return False


def _material_line(**overrides):
    line = {
        "line_type": "material",
        "description": "Drywall sheets",
        "customer_description": "Drywall",
        "quantity": 10,
        "unit": "SF",
        "unit_cost_cents": 1000,
        "package_qty": 1,
    }
    line.update(overrides)
    return line


def _set_contract_status(env, contract_id, status):
    conn = env["db"].get_connection()
    with conn:
        conn.execute("UPDATE contracts SET status = ? WHERE id = ?;", (status, contract_id))


def _accept_with_signed_contract(
    env, *, actor=None, opportunity_id=None, property_id=None, contract_status="signed",
):
    """Create an estimate, add one priced line, accept it (creating a real
    linked Contract per record_decision()'s accept->Contract invariant),
    then set that Contract's status directly (mirrors
    test_accepted_decision_creates_contract_in_same_transaction's own setup
    -- record_decision()'s own Contract INSERT always lands as 'draft';
    nothing in this round drives a contract to 'signed' through a service
    method, so the test fixture sets it directly, same as
    test_accepted_decision_contract_creation_failure_rolls_back_whole_transaction
    manipulates `contracts` directly via raw SQL).
    """
    svc = env["svc"]
    actor = actor or env["sales"]
    header = svc.create(
        customer_id=env["customer_id"], actor=actor,
        opportunity_id=opportunity_id, property_id=property_id,
    )
    svc.add_line(header.id, _material_line(), actor)

    customer_user = env["auth"].create_user(
        f"cust_{header.id}", "Pass123!", "Accept Customer", f"cust_{header.id}@example.com",
        role="customer", customer_id=env["customer_id"],
    )
    svc.record_decision(
        estimate_version_id=header.current_version_id,
        decision="accepted",
        ip="127.0.0.1",
        user_agent="pytest",
        signer_name="Accept Customer",
        customer_user_id=customer_user.id,
    )
    accepted = svc.get(header.id, actor)
    if contract_status is not None:
        _set_contract_status(env, accepted.contract_id, contract_status)
    return accepted


# ------------------------------------------------------------------
# Happy path / idempotency
# ------------------------------------------------------------------

def test_convert_happy_path_creates_project(env):
    svc = env["svc"]
    accepted = _accept_with_signed_contract(env)

    result = svc.convert(accepted.id, env["sales"])
    assert set(result.keys()) == {"contract_id", "project_id"}
    assert result["contract_id"] == accepted.contract_id
    assert isinstance(result["project_id"], int)

    updated = svc.get(accepted.id, env["sales"])
    assert updated.converted_project_id == result["project_id"]
    assert updated.workflow_status == "CONVERTED"

    count = env["db"].get_connection().execute("SELECT COUNT(*) AS n FROM projects;").fetchone()["n"]
    assert count == 1


def test_convert_idempotent_second_call_returns_identical_pair_no_duplicate_project(env):
    svc = env["svc"]
    accepted = _accept_with_signed_contract(env)

    first = svc.convert(accepted.id, env["sales"])
    second = svc.convert(accepted.id, env["sales"])
    assert first == second

    count = env["db"].get_connection().execute("SELECT COUNT(*) AS n FROM projects;").fetchone()["n"]
    assert count == 1


def test_convert_idempotent_short_circuit_writes_no_audit_entry(env):
    """The idempotent second call returns before reaching either audit.log()
    call -- confirmed here explicitly, since it's easy to assume (wrongly)
    that 'convert succeeded' always implies a fresh audit row."""
    svc = env["svc"]
    accepted = _accept_with_signed_contract(env)
    svc.convert(accepted.id, env["sales"])

    conn = env["db"].get_connection()
    before = conn.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE action = 'convert' AND entity_id = ?;", (accepted.id,)
    ).fetchone()["n"]
    svc.convert(accepted.id, env["sales"])
    after = conn.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE action = 'convert' AND entity_id = ?;", (accepted.id,)
    ).fetchone()["n"]
    assert before == 1
    assert after == 1


# ------------------------------------------------------------------
# Signed-contract gate
# ------------------------------------------------------------------

@pytest.mark.parametrize("status", ["draft", "sent", "expired", "superseded"])
def test_convert_refuses_unsigned_contract(env, status):
    svc = env["svc"]
    accepted = _accept_with_signed_contract(env, contract_status=status)
    with pytest.raises(ValueError, match="not signed"):
        svc.convert(accepted.id, env["sales"])


def test_convert_succeeds_with_signed_contract(env):
    svc = env["svc"]
    accepted = _accept_with_signed_contract(env, contract_status="signed")
    result = svc.convert(accepted.id, env["sales"])
    assert result["project_id"] is not None


def test_convert_refuses_when_no_contract_linked_yet(env):
    """Belt-and-suspenders: an ACCEPTED estimate with no contract_id at all
    (should not normally occur, given the accept -> Contract invariant, but
    convert() must still refuse cleanly rather than crash)."""
    svc = env["svc"]
    accepted = _accept_with_signed_contract(env)
    conn = env["db"].get_connection()
    with conn:
        conn.execute("UPDATE estimates SET contract_id = NULL WHERE id = ?;", (accepted.id,))
    with pytest.raises(ValueError, match="no linked contract"):
        svc.convert(accepted.id, env["sales"])


# ------------------------------------------------------------------
# Non-ACCEPTED refusal
# ------------------------------------------------------------------

_ALL_WORKFLOW_STATUSES = [
    "DRAFT", "INTERNAL_REVIEW", "APPROVED_INTERNAL", "SENT", "VIEWED",
    "DECLINED", "CHANGES_REQUESTED", "EXPIRED", "CANCELLED",
]


@pytest.mark.parametrize("status", _ALL_WORKFLOW_STATUSES)
def test_convert_refuses_every_non_accepted_non_converted_status(env, status):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])
    conn = env["db"].get_connection()
    with conn:
        conn.execute("UPDATE estimates SET workflow_status = ? WHERE id = ?;", (status, header.id))
    with pytest.raises(ValueError, match="requires ACCEPTED"):
        svc.convert(header.id, env["sales"])


def test_convert_converted_with_project_id_set_is_idempotent_success(env):
    svc = env["svc"]
    accepted = _accept_with_signed_contract(env)
    first = svc.convert(accepted.id, env["sales"])
    # Now workflow_status == CONVERTED, converted_project_id set -- calling
    # again must be the idempotent-success path, not a negative case.
    second = svc.convert(accepted.id, env["sales"])
    assert second == first


def test_convert_converted_with_null_project_id_is_an_inconsistent_state_that_raises(env):
    """CONVERTED with converted_project_id NULL should never normally occur
    (only convert()'s own CAS-guarded UPDATE ever sets workflow_status to
    CONVERTED, and it always pairs that with a non-NULL converted_project_id
    in the same UPDATE). If the DB is ever forced into this state anyway
    (simulated here via raw SQL), convert() must not silently "succeed" with
    a None project_id -- given the method's actual ordering (the
    converted_project_id-is-not-None idempotency check runs BEFORE the
    workflow_status check), this falls through to the
    workflow_status != 'ACCEPTED' ValueError, which is the defined,
    documented behavior here: raise, never a silent no-op success."""
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])
    conn = env["db"].get_connection()
    with conn:
        conn.execute("UPDATE estimates SET workflow_status = 'CONVERTED' WHERE id = ?;", (header.id,))
    with pytest.raises(ValueError, match="requires ACCEPTED"):
        svc.convert(header.id, env["sales"])


# ------------------------------------------------------------------
# Project-linking priority order
# ------------------------------------------------------------------

def test_convert_links_directly_when_estimate_project_id_already_set_no_opportunity_lookup(env):
    """estimate.project_id is set -> that IS the Project; no new Project
    created, and no Opportunity lookup performed at all -- proven by
    pointing opportunity_id at a real opportunity whose OWN project_id
    differs, and confirming the returned project_id is the estimate's own,
    not the opportunity's (an FK-enforced nonexistent opportunity_id is not
    constructible here -- `estimates.opportunity_id` has a real FK)."""
    svc = env["svc"]
    crm = env["crm"]

    existing_project_id = crm.create_project(
        Project(
            customer_id=env["customer_id"], title="Direct-linked project",
            property_address="123 Main St", project_type="remodel",
        ),
        env["admin"],
    ).id
    other_project_id = crm.create_project(
        Project(
            customer_id=env["customer_id"], title="Opportunity's own (different) project",
            property_address="456 Oak St", project_type="remodel",
        ),
        env["admin"],
    ).id
    assert existing_project_id != other_project_id

    opp = crm.create_opportunity(
        Opportunity(
            customer_id=env["customer_id"], title="Some opportunity", project_id=other_project_id,
        ),
        env["admin"],
    )

    header = svc.create(
        customer_id=env["customer_id"], actor=env["sales"],
        project_id=existing_project_id, opportunity_id=opp.id,
    )
    svc.add_line(header.id, _material_line(), env["sales"])
    customer_user = env["auth"].create_user(
        "cust_direct", "Pass123!", "Direct Customer", "cust_direct@example.com",
        role="customer", customer_id=env["customer_id"],
    )
    svc.record_decision(
        estimate_version_id=header.current_version_id, decision="accepted",
        ip="127.0.0.1", user_agent="pytest", signer_name="Direct Customer",
        customer_user_id=customer_user.id,
    )
    accepted = svc.get(header.id, env["sales"])
    _set_contract_status(env, accepted.contract_id, "signed")

    result = svc.convert(accepted.id, env["sales"])
    assert result["project_id"] == existing_project_id

    count = env["db"].get_connection().execute("SELECT COUNT(*) AS n FROM projects;").fetchone()["n"]
    assert count == 2  # the two pre-existing ones; no third was created

    # Opportunity's own project_id is untouched (no write-back attempted
    # when convert() never even creates a new Project).
    opp_row = env["db"].get_connection().execute(
        "SELECT project_id FROM opportunities WHERE id = ?;", (opp.id,)
    ).fetchone()
    assert opp_row["project_id"] == other_project_id


def test_convert_links_via_opportunity_project_id_when_already_non_null(env):
    svc = env["svc"]
    crm = env["crm"]

    existing_project = crm.create_project(
        Project(customer_id=env["customer_id"], title="Pre-existing", property_address="1 Elm St", project_type="remodel"),
        env["admin"],
    )
    opp = crm.create_opportunity(
        Opportunity(customer_id=env["customer_id"], title="Opp with project", project_id=existing_project.id),
        env["admin"],
    )

    header = svc.create(customer_id=env["customer_id"], actor=env["sales"], opportunity_id=opp.id)
    svc.add_line(header.id, _material_line(), env["sales"])
    customer_user = env["auth"].create_user(
        "cust_opp1", "Pass123!", "Opp Customer", "cust_opp1@example.com",
        role="customer", customer_id=env["customer_id"],
    )
    svc.record_decision(
        estimate_version_id=header.current_version_id, decision="accepted",
        ip="127.0.0.1", user_agent="pytest", signer_name="Opp Customer",
        customer_user_id=customer_user.id,
    )
    accepted = svc.get(header.id, env["sales"])
    _set_contract_status(env, accepted.contract_id, "signed")

    result = svc.convert(accepted.id, env["sales"])
    assert result["project_id"] == existing_project.id

    count = env["db"].get_connection().execute("SELECT COUNT(*) AS n FROM projects;").fetchone()["n"]
    assert count == 1  # no new Project created

    # write-back's `WHERE project_id IS NULL` guard is a no-op here, since
    # the opportunity's project_id was already non-NULL.
    opp_row = env["db"].get_connection().execute(
        "SELECT project_id FROM opportunities WHERE id = ?;", (opp.id,)
    ).fetchone()
    assert opp_row["project_id"] == existing_project.id


def test_convert_creates_new_project_using_accepted_version_not_current_version(env):
    """Both estimate.project_id and opportunity.project_id are NULL, but
    opportunity_id IS set -> a new Project is created, priced off the
    ACCEPTED version's totals, not the current version's (which, after a
    post-accept revise(), can differ). Also confirms the opportunity
    write-back fires."""
    svc = env["svc"]
    crm = env["crm"]

    opp = crm.create_opportunity(
        Opportunity(customer_id=env["customer_id"], title="Fresh opportunity"), env["admin"],
    )

    header = svc.create(customer_id=env["customer_id"], actor=env["sales"], opportunity_id=opp.id)
    svc.add_line(header.id, _material_line(unit_cost_cents=1000, quantity=10), env["sales"])
    customer_user = env["auth"].create_user(
        "cust_opp2", "Pass123!", "Opp Customer Two", "cust_opp2@example.com",
        role="customer", customer_id=env["customer_id"],
    )
    svc.record_decision(
        estimate_version_id=header.current_version_id, decision="accepted",
        ip="127.0.0.1", user_agent="pytest", signer_name="Opp Customer Two",
        customer_user_id=customer_user.id,
    )
    accepted = svc.get(header.id, env["sales"])
    _set_contract_status(env, accepted.contract_id, "signed")

    accepted_version_row = env["db"].get_connection().execute(
        "SELECT * FROM estimate_versions WHERE id = ?;", (accepted.accepted_version_id,)
    ).fetchone()
    accepted_total_cents = accepted_version_row["total_cents"]
    accepted_cost_total_cents = accepted_version_row["cost_total_cents"]
    assert accepted_total_cents != accepted_cost_total_cents  # distinct values, not a transposition-proof gap

    # Post-accept revise(): a real, unaccepted DRAFT with zero totals until
    # re-priced -- proves current_version_id now diverges from
    # accepted_version_id, and must NOT be what convert() prices off.
    svc.revise(header.id, env["sales"])
    conn = env["db"].get_connection()
    # Force workflow_status back to ACCEPTED with the mismatched
    # current/accepted version pair intact (revise() itself always resets to
    # DRAFT -- there is no organic service-method path back to ACCEPTED
    # without record_decision() re-syncing accepted_version_id to the new
    # current version, so this state is constructed directly, same
    # technique as this file's other raw-SQL state-construction tests).
    with conn:
        conn.execute("UPDATE estimates SET workflow_status = 'ACCEPTED' WHERE id = ?;", (header.id,))
    reaccepted = svc.get(header.id, env["sales"])
    assert reaccepted.accepted_version_id != reaccepted.current_version_id

    result = svc.convert(header.id, env["sales"])
    project_row = conn.execute("SELECT * FROM projects WHERE id = ?;", (result["project_id"],)).fetchone()
    assert project_row["contract_amount"] == accepted_total_cents / 100.0
    assert project_row["estimated_cost"] == accepted_cost_total_cents / 100.0

    opp_row = conn.execute("SELECT project_id FROM opportunities WHERE id = ?;", (opp.id,)).fetchone()
    assert opp_row["project_id"] == result["project_id"]


def test_convert_writeback_prevents_duplicate_project_for_second_estimate_same_opportunity(env):
    """The concrete regression test for the gap Ish decided to close: two
    estimates under the SAME opportunity, neither with estimate.project_id
    set -- converting the first creates Project A and writes back
    opportunities.project_id; converting the second must link to Project A
    via the write-back, not create Project B."""
    svc = env["svc"]
    crm = env["crm"]

    opp = crm.create_opportunity(
        Opportunity(customer_id=env["customer_id"], title="Shared opportunity"), env["admin"],
    )

    first = _accept_with_signed_contract(env, opportunity_id=opp.id)
    first_result = svc.convert(first.id, env["sales"])

    second = _accept_with_signed_contract(env, opportunity_id=opp.id)
    second_result = svc.convert(second.id, env["sales"])

    assert second_result["project_id"] == first_result["project_id"]
    count = env["db"].get_connection().execute("SELECT COUNT(*) AS n FROM projects;").fetchone()["n"]
    assert count == 1


# ------------------------------------------------------------------
# Permission / ownership / role gates
# ------------------------------------------------------------------

def test_convert_non_owner_sales_without_read_all_is_denied(env):
    """Pins the ownership-narrowing branch specifically, not just "lacks
    some permission" -- env["sales2"] DOES hold PERM_WRITE_ESTIMATES (so it
    clears convert()'s first gate) and does NOT hold PERM_READ_ALL_ESTIMATES
    (so it cannot bypass ownership), asserted explicitly so this test can
    only pass via the ownership check actually working, not via
    ROLE_SALES lacking write permission entirely."""
    assert env["sales2"].has_permission(PERM_WRITE_ESTIMATES)
    assert not env["sales2"].has_permission(PERM_READ_ALL_ESTIMATES)
    svc = env["svc"]
    accepted = _accept_with_signed_contract(env)  # created+assigned to env["sales"]
    with pytest.raises(PermissionError):
        svc.convert(accepted.id, env["sales2"])


def test_convert_non_owner_with_read_all_estimates_succeeds(env):
    svc = env["svc"]
    accepted = _accept_with_signed_contract(env)
    # env["manager"] holds PERM_READ_ALL_ESTIMATES (and PERM_WRITE_ESTIMATES)
    # via ROLE_MANAGER's default grants.
    assert env["manager"].has_permission(PERM_READ_ALL_ESTIMATES)
    result = svc.convert(accepted.id, env["manager"])
    assert result["project_id"] is not None


def test_convert_actor_lacking_write_estimates_entirely_is_denied(env):
    svc = env["svc"]
    accepted = _accept_with_signed_contract(env)
    with pytest.raises(PermissionError):
        svc.convert(accepted.id, ZeroPermissionActor())


def test_convert_denies_ai_agent_even_though_it_holds_the_permissions(env):
    """ROLE_AI_AGENT must be refused before any other check runs, even
    though it actually holds both PERM_WRITE_ESTIMATES and
    PERM_READ_ALL_ESTIMATES by default (confirmed here, not assumed) --
    otherwise this test would pass via the ordinary permission gate instead
    of proving the role-specific denial."""
    assert env["agent"].has_permission(PERM_WRITE_ESTIMATES)
    assert env["agent"].has_permission(PERM_READ_ALL_ESTIMATES)
    svc = env["svc"]
    accepted = _accept_with_signed_contract(env)
    with pytest.raises(PermissionError, match="ai_agent"):
        svc.convert(accepted.id, env["agent"])


# ------------------------------------------------------------------
# Concurrent-conversion race (CAS guard)
# ------------------------------------------------------------------

def test_convert_cas_guard_raises_and_rolls_back_when_converted_project_id_changes_mid_transaction(env):
    """**No true two-writer race is exercised here** -- named and documented
    accordingly so this isn't mistaken for one. A monkeypatched
    `conn.execute()` injects a mutation to `converted_project_id` right
    before convert()'s own final guarded `UPDATE` runs, but because every
    write here shares the SAME connection/transaction as convert()'s own
    `BEGIN IMMEDIATE` (there is no real second writer available in a
    `:memory:`-DB unit test -- unlike
    test_transition_stale_pre_read_no_longer_clobbers_state_changed_before_lock's
    technique in test_b9_2_estimate_service.py, which injects a fully
    separate, COMMITTING transaction at the `BEGIN IMMEDIATE` boundary
    itself, before the outer transaction even starts), the injected
    "competing" UPDATE here is really a same-transaction mid-function
    mutation, not a concurrent writer's committed change.

    What this DOES prove, and is worth keeping: the CAS guard's WHERE
    clause (`converted_project_id IS NULL`) catches a value that changed out
    from under it since the idempotency check ran, raising
    ClaimConflictError instead of silently overwriting -- and because the
    whole `with conn:` block rolls back on that exception, the injected
    mutation itself is also undone, so the estimate ends up back at its
    pre-call ACCEPTED state (not left half-converted). The final assertions
    below are that rollback's effect, not a genuine concurrent write's."""
    svc = env["svc"]
    accepted = _accept_with_signed_contract(env)
    racing_project = env["crm"].create_project(
        Project(customer_id=env["customer_id"], title="Raced-in project", property_address="1 Race St", project_type="remodel"),
        env["admin"],
    )

    real_conn = env["db"].get_connection()
    real_get_connection = env["db"].get_connection

    class _RacingConnProxy:
        def __getattr__(self, name):
            return getattr(real_conn, name)

        def __enter__(self):
            return real_conn.__enter__()

        def __exit__(self, *exc_info):
            return real_conn.__exit__(*exc_info)

        def execute(self, sql, *args, **kwargs):
            if sql.strip().upper().startswith("UPDATE ESTIMATES SET CONVERTED_PROJECT_ID"):
                # A competing conversion "wins" first, landing between this
                # call's own read and its own write.
                real_conn.execute(
                    "UPDATE estimates SET converted_project_id = ?, workflow_status = 'CONVERTED' "
                    "WHERE id = ?;",
                    (racing_project.id, accepted.id),
                )
            return real_conn.execute(sql, *args, **kwargs)

    proxy = _RacingConnProxy()
    env["db"].get_connection = lambda: proxy
    try:
        with pytest.raises(ClaimConflictError):
            svc.convert(accepted.id, env["sales"])
    finally:
        env["db"].get_connection = real_get_connection

    # The CAS guard's own UPDATE affected 0 rows (WHERE converted_project_id
    # IS NULL no longer matched) -- that's what raised ClaimConflictError,
    # which then rolled back the WHOLE transaction, including convert()'s
    # own (never-committed) Project INSERT and the injected mutation alike.
    count = real_conn.execute("SELECT COUNT(*) AS n FROM projects;").fetchone()["n"]
    assert count == 1  # only the pre-existing racing_project; nothing from convert() landed
    row = real_conn.execute(
        "SELECT converted_project_id, workflow_status FROM estimates WHERE id = ?;", (accepted.id,)
    ).fetchone()
    assert row["converted_project_id"] is None
    assert row["workflow_status"] == "ACCEPTED"


# ------------------------------------------------------------------
# Audit
# ------------------------------------------------------------------

def test_convert_audit_entries_only_on_writing_paths(env):
    svc = env["svc"]
    conn = env["db"].get_connection()

    def _count(action, entity_type, entity_id):
        return conn.execute(
            "SELECT COUNT(*) AS n FROM audit_log WHERE action = ? AND entity_type = ? AND entity_id = ?;",
            (action, entity_type, entity_id),
        ).fetchone()["n"]

    # New-Project path: both a convert/estimate AND a create/project entry.
    new_project_case = _accept_with_signed_contract(env)
    result = svc.convert(new_project_case.id, env["sales"])
    assert _count("convert", "estimate", new_project_case.id) == 1
    assert _count("create", "project", result["project_id"]) == 1

    # Link-to-existing (estimate.project_id already set) path: convert/
    # estimate entry present, but NO create/project entry (no Project was
    # created on this path).
    existing_project = env["crm"].create_project(
        Project(
            customer_id=env["customer_id"], title="Pre-existing for audit test",
            property_address="9 Pine St", project_type="remodel",
        ),
        env["admin"],
    )
    link_case = svc.create(customer_id=env["customer_id"], actor=env["sales"], project_id=existing_project.id)
    svc.add_line(link_case.id, _material_line(), env["sales"])
    customer_user = env["auth"].create_user(
        "cust_audit", "Pass123!", "Audit Customer", "cust_audit@example.com",
        role="customer", customer_id=env["customer_id"],
    )
    svc.record_decision(
        estimate_version_id=link_case.current_version_id, decision="accepted",
        ip="127.0.0.1", user_agent="pytest", signer_name="Audit Customer",
        customer_user_id=customer_user.id,
    )
    accepted_link_case = svc.get(link_case.id, env["sales"])
    _set_contract_status(env, accepted_link_case.contract_id, "signed")

    # existing_project already has its OWN "create"/"project" audit entry
    # from crm.create_project() itself -- count it before convert() runs so
    # the assertion below is about what convert() itself adds, not conflated
    # with that pre-existing entry.
    create_project_count_before = _count("create", "project", existing_project.id)

    link_result = svc.convert(accepted_link_case.id, env["sales"])
    assert link_result["project_id"] == existing_project.id
    assert _count("convert", "estimate", accepted_link_case.id) == 1
    # No NEW "create"/"project" entry was added by convert() on this
    # link-to-existing path.
    assert _count("create", "project", existing_project.id) == create_project_count_before


# ------------------------------------------------------------------
# Property-address fallback
# ------------------------------------------------------------------

def test_convert_new_project_uses_property_address_when_property_id_set(env):
    svc = env["svc"]
    crm = env["crm"]

    prop = crm.create_property(
        Property(customer_id=env["customer_id"], address="777 Property Rd"), env["admin"],
    )
    accepted = _accept_with_signed_contract(env, property_id=prop.id)
    result = svc.convert(accepted.id, env["sales"])
    project_row = env["db"].get_connection().execute(
        "SELECT property_address FROM projects WHERE id = ?;", (result["project_id"],)
    ).fetchone()
    assert project_row["property_address"] == "777 Property Rd"


def test_convert_new_project_falls_back_to_customer_service_address(env):
    svc = env["svc"]
    conn = env["db"].get_connection()
    with conn:
        conn.execute(
            "UPDATE customers SET service_address = ?, mailing_address = ? WHERE id = ?;",
            ("555 Service Ave", "555 Mailing Ave", env["customer_id"]),
        )
    accepted = _accept_with_signed_contract(env)  # no property_id
    result = svc.convert(accepted.id, env["sales"])
    project_row = conn.execute(
        "SELECT property_address FROM projects WHERE id = ?;", (result["project_id"],)
    ).fetchone()
    assert project_row["property_address"] == "555 Service Ave"


def test_convert_new_project_property_address_falls_back_to_empty_string_without_raising(env):
    svc = env["svc"]
    conn = env["db"].get_connection()
    with conn:
        conn.execute(
            "UPDATE customers SET service_address = NULL, mailing_address = NULL WHERE id = ?;",
            (env["customer_id"],),
        )
    accepted = _accept_with_signed_contract(env)  # no property_id
    result = svc.convert(accepted.id, env["sales"])
    project_row = conn.execute(
        "SELECT property_address FROM projects WHERE id = ?;", (result["project_id"],)
    ).fetchone()
    assert project_row["property_address"] == ""
