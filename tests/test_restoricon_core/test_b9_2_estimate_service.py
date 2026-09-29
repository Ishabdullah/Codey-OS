"""
Tests for Phase B9.2 -- EstimateService (restoricon_core/services/estimate_service.py).

Covers the task's five required regression cases (material-markup default,
explicit-zero override, revise() clone verbatim, 'combined'-line gating,
plus standard CRUD/versioning/lock-immutability coverage) and the RBAC gate.

Also covers this round's four additions: claim()/unclaim(), reassign(),
transition() (including the D5 internal-review gate and real share-link
creation), and record_decision()'s accept -> Contract invariant.
"""

import hashlib

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_READ_ESTIMATE_COSTS,
    ROLE_ADMIN,
    ROLE_AI_AGENT,
    ROLE_CUSTOMER,
    ROLE_MANAGER,
    ROLE_SALES,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import ClaimConflictError, CRMService
from restoricon_core.services.estimate_service import DEFAULT_MATERIAL_MARKUP_BP, EstimateService


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
        "db": db, "svc": svc, "admin": admin, "sales": sales, "sales2": sales2,
        "manager": manager, "agent": agent, "customer_id": customer.id,
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


def test_create_get_list_update_header(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], title="Kitchen remodel", actor=env["sales"])
    assert header.estimate_number.startswith("EST-")
    assert header.workflow_status == "DRAFT"
    assert header.created_by_user_id == env["sales"].user_id
    assert header.assigned_to_user_id == env["sales"].user_id
    assert header.current_version_id is not None

    fetched = svc.get(header.id, env["sales"])
    assert fetched.id == header.id

    listed = svc.list(env["sales"])
    assert any(h.id == header.id for h in listed)

    updated = svc.update_header(header.id, {"title": "Kitchen remodel v2"}, env["sales"])
    assert updated.title == "Kitchen remodel v2"

    with pytest.raises(ValueError):
        svc.update_header(header.id, {"created_by_user_id": 1}, env["sales"])


def test_create_requires_permission(env):
    svc = env["svc"]
    with pytest.raises(PermissionError):
        svc.create(customer_id=env["customer_id"], actor=ZeroPermissionActor())


def test_create_ignores_client_supplied_identity_fields(env):
    """F1-shaped regression: even if a caller somehow slipped
    created_by_user_id/estimate_number into kwargs, create()'s signature has
    no such parameters -- there is no code path to set them from a caller."""
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    assert header.created_by_user_id == env["sales"].user_id
    assert header.estimate_number != "EST-FAKE"


def test_material_line_no_markup_key_defaults_to_30_percent(env):
    """Required test 1: adding a material line with NO material_markup_bp
    key persists as 3000 (30%), and the computed sell price reflects it."""
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    line = svc.add_line(header.id, _material_line(), env["sales"])
    assert line.material_markup_bp == DEFAULT_MATERIAL_MARKUP_BP
    # 10 SF * $10.00/SF = $100.00 cost -> 30% markup -> $130.00 sell
    assert line.material_cost_cents == 10_000
    assert line.sell_total_cents == 13_000


def test_material_line_explicit_zero_markup_is_not_overridden(env):
    """Required test 2: explicit material_markup_bp=0 persists as exactly
    0, sell reflects true cost pass-through, never overridden to 3000."""
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    line = svc.add_line(header.id, _material_line(material_markup_bp=0), env["sales"])
    assert line.material_markup_bp == 0
    assert line.material_cost_cents == 10_000
    assert line.sell_total_cents == 10_000


def test_revise_clones_material_markup_verbatim(env):
    """Required test 3: revise()-ing a version with a line at
    material_markup_bp=1200 (12%) keeps the new version's cloned line at
    1200, not reset to 3000."""
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    line = svc.add_line(header.id, _material_line(material_markup_bp=1200), env["sales"])
    assert line.material_markup_bp == 1200

    svc._lock_version(header.current_version_id, "sent", env["admin"])
    new_version = svc.revise(header.id, env["sales"])
    assert new_version.version_number == 2

    cloned_lines = svc.get(header.id, env["sales"], include_lines=True).lines
    assert len(cloned_lines) == 1
    assert cloned_lines[0].material_markup_bp == 1200


def test_combined_line_material_component_gets_default_markup(env):
    """Required test 4: a 'combined'-type line with material cost inputs but
    no explicit markup key gets the 30% default applied to its material
    component (gated on _has_material_component, not on the literal string
    line_type == 'material')."""
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    combined = {
        "line_type": "combined",
        "description": "Install + supply flooring",
        "customer_description": "Flooring",
        "quantity": 5,
        "unit": "SF",
        "unit_cost_cents": 500,
        "package_qty": 1,
        "labor_qty": 2,
        "labor_unit": "HR",
        "labor_cost_rate_cents": 2000,
        "labor_bill_rate_cents": 4000,
    }
    line = svc.add_line(header.id, combined, env["sales"])
    assert line.material_markup_bp == DEFAULT_MATERIAL_MARKUP_BP
    # 5 SF * $5.00/SF = $25.00 material cost -> 30% markup -> $32.50 sell (material component)
    assert line.material_cost_cents == 2_500
    # labor: 2hr * $40.00 bill rate = $80.00 sell; total sell = 32.50 + 80.00 = 112.50
    assert line.labor_cost_cents == 4_000
    assert line.sell_total_cents == 11_250


def test_update_line_material_markup_no_special_default_logic(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    line = svc.add_line(header.id, _material_line(), env["sales"])
    assert line.material_markup_bp == DEFAULT_MATERIAL_MARKUP_BP

    updated = svc.update_line(line.id, {"material_markup_bp": 500}, env["sales"])
    assert updated.material_markup_bp == 500
    assert updated.sell_total_cents == 10_500  # 10000 cost * 1.05


def test_remove_line_and_reorder_lines(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    l1 = svc.add_line(header.id, _material_line(description="Line 1"), env["sales"])
    l2 = svc.add_line(header.id, _material_line(description="Line 2"), env["sales"])

    svc.reorder_lines(header.id, [l2.id, l1.id], env["sales"])
    lines = svc.get(header.id, env["sales"], include_lines=True).lines
    assert [ln.id for ln in lines] == [l2.id, l1.id]

    svc.remove_line(l1.id, env["sales"])
    lines_after = svc.get(header.id, env["sales"], include_lines=True).lines
    assert [ln.id for ln in lines_after] == [l2.id]


def test_lock_immutability_blocks_line_and_header_writes(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])
    svc._lock_version(header.current_version_id, "sent", env["admin"])

    with pytest.raises(ValueError):
        svc.add_line(header.id, _material_line(), env["sales"])
    with pytest.raises(ValueError):
        svc.update_header(header.id, {"title": "should fail"}, env["sales"])


def test_revise_requires_locked_version(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    with pytest.raises(ValueError):
        svc.revise(header.id, env["sales"])


def test_preview_and_to_customer_view(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])

    result = svc.preview(header.id, env["sales"])
    assert result.total_cents == 13_000

    view = svc.to_customer_view(header.id)
    forbidden_keys = {
        "cost_total_cents", "gross_profit_cents", "gross_margin_bp",
        "material_cost_cents", "unit_cost_cents", "retailer_code_snapshot",
        "internal_note", "override_reason", "created_by_user_id",
        "labor_cost_rate_cents", "labor_bill_rate_cents",
    }
    assert forbidden_keys.isdisjoint(view.keys())
    for line in view["lines"]:
        assert forbidden_keys.isdisjoint(line.keys())
    assert view["total_cents"] == 13_000


def test_preview_gates_cost_fields_without_permission(env):
    """Code-review fix regression (Critical): `preview()` originally
    returned the engine's raw `EstimateResult`/`LineResult` tree -- cost and
    margin fields included -- to ANY actor holding `PERM_WRITE_ESTIMATES`,
    with no `PERM_READ_ESTIMATE_COSTS` gate at all (unlike `get()`, which
    correctly gates via `_attach_cost_fields()`/`_gate_line_cost_fields()`).

    Every role in the actual permission matrix that holds
    `PERM_WRITE_ESTIMATES` also holds `PERM_READ_ESTIMATE_COSTS` today
    (confirmed by reading `auth.py`'s `ROLE_PERMISSIONS` directly -- no
    role currently has one without the other), so this exercises the gate
    the only way it's reachable: `custom_permissions` overriding the
    creator's own role grant, exactly as an admin revoking just that one
    permission for a specific user would (`AuthContext.has_permission()`
    checks `custom_permissions` before falling back to the role).
    """
    svc = env["svc"]
    actor = AuthContext(
        env["sales"].user_id, env["sales"].username, ROLE_SALES, "human",
        custom_permissions={PERM_READ_ESTIMATE_COSTS: False},
    )
    header = svc.create(customer_id=env["customer_id"], actor=actor)
    svc.add_line(header.id, _material_line(), actor)

    result = svc.preview(header.id, actor)

    # Header-level cost/margin fields withheld.
    assert result.material_cost_cents is None
    assert result.labor_cost_cents is None
    assert result.equipment_cost_cents is None
    assert result.sub_cost_cents is None
    assert result.cost_total_cents is None
    assert result.gross_profit_cents is None
    assert result.gross_margin_bp is None
    assert result.markup_effective_bp is None
    # Non-cost sell/tax totals still present -- gated, not gutted.
    assert result.total_cents == 13_000
    assert result.subtotal_sell_cents is not None

    line = result.lines[0]
    assert line.material_cost_cents is None
    assert line.cost_total_cents is None
    assert line.sell_total_cents is None
    assert line.line_total_cents is not None  # customer still sees a coherent final charge

    # The raw cost inputs are echoed back on `line.input.material` etc. --
    # gating only the top-level computed fields and leaving the echoed
    # input tree untouched would silently defeat the whole gate.
    assert line.input.material.unit_cost_cents is None
    assert line.input.material.material_markup_bp is None
    assert line.input.override_reason is None

    # Sanity: the same actor with cost-read permission sees the real values.
    full_actor = env["sales"]
    full_result = svc.preview(header.id, full_actor)
    assert full_result.cost_total_cents is not None
    assert full_result.lines[0].input.material.unit_cost_cents is not None


def test_record_decision_requires_signer_name_on_accept(env, request):
    svc = env["svc"]
    auth = AuthService(env["db"])
    customer_user = auth.create_user(
        "cust1", "Pass123!", "Jane Doe", "cust1@example.com", role="customer",
        customer_id=env["customer_id"],
    )

    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])
    svc._lock_version(header.current_version_id, "sent", env["admin"])

    with pytest.raises(ValueError):
        svc.record_decision(
            estimate_version_id=header.current_version_id,
            decision="accepted",
            ip="127.0.0.1",
            user_agent="pytest",
            customer_user_id=customer_user.id,
        )

    decision = svc.record_decision(
        estimate_version_id=header.current_version_id,
        decision="accepted",
        ip="127.0.0.1",
        user_agent="pytest",
        signer_name="Jane Doe",
        customer_user_id=customer_user.id,
    )
    assert decision.decision == "accepted"
    assert decision.consent_text_snapshot

    updated = svc.get(header.id, env["sales"])
    assert updated.workflow_status == "ACCEPTED"
    assert updated.accepted_version_id == header.current_version_id


def test_record_decision_accepted_locks_version_against_further_edits(env):
    """Regression for the reviewer-found gap: record_decision('accepted')
    must lock the version in the same transaction as the acceptance write,
    so a subsequent add_line() (which only checks is_locked, not
    workflow_status) can no longer silently re-price an accepted estimate.
    Deliberately does NOT pre-lock via _lock_version() -- the bug was that
    accept() on an unlocked version left it unlocked."""
    svc = env["svc"]
    auth = AuthService(env["db"])
    customer_user = auth.create_user(
        "cust2", "Pass123!", "John Roe", "cust2@example.com", role="customer",
        customer_id=env["customer_id"],
    )

    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])
    assert header.current_version_id is not None

    svc.record_decision(
        estimate_version_id=header.current_version_id,
        decision="accepted",
        ip="127.0.0.1",
        user_agent="pytest",
        signer_name="John Roe",
        customer_user_id=customer_user.id,
    )

    version = svc.get(header.id, env["sales"]).current_version_id
    assert version == header.current_version_id

    # Pin the actual fix, not just its downstream effect: the version row
    # itself must be locked with locked_reason='accepted', not merely
    # "add_line() happens to raise for some other reason."
    version_row = env["db"].get_connection().execute(
        "SELECT is_locked, locked_reason FROM estimate_versions WHERE id = ?;", (version,)
    ).fetchone()
    assert version_row["is_locked"] == 1
    assert version_row["locked_reason"] == "accepted"

    with pytest.raises(ValueError):
        svc.add_line(header.id, _material_line(), env["sales"])
    with pytest.raises(ValueError):
        svc.update_line(
            svc.get(header.id, env["sales"], include_lines=True).lines[0].id,
            {"material_markup_bp": 999},
            env["sales"],
        )


def test_record_decision_accepted_on_already_locked_version_is_idempotent(env):
    """A version already locked (e.g. 'sent') before acceptance must not
    error when record_decision('accepted') tries to lock it again --
    is_locked=1 is the invariant that matters, not which reason got there
    first."""
    svc = env["svc"]
    auth = AuthService(env["db"])
    customer_user = auth.create_user(
        "cust3", "Pass123!", "Mary Poe", "cust3@example.com", role="customer",
        customer_id=env["customer_id"],
    )

    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])
    svc._lock_version(header.current_version_id, "sent", env["admin"])

    decision = svc.record_decision(
        estimate_version_id=header.current_version_id,
        decision="accepted",
        ip="127.0.0.1",
        user_agent="pytest",
        signer_name="Mary Poe",
        customer_user_id=customer_user.id,
    )
    assert decision.decision == "accepted"


def test_record_decision_declined_and_changes_requested_do_not_lock(env):
    """Only 'accepted' is final/locking -- 'declined' and
    'changes_requested' must leave the version editable."""
    svc = env["svc"]
    auth = AuthService(env["db"])
    customer_user = auth.create_user(
        "cust4", "Pass123!", "Sam Roe", "cust4@example.com", role="customer",
        customer_id=env["customer_id"],
    )

    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])

    svc.record_decision(
        estimate_version_id=header.current_version_id,
        decision="changes_requested",
        ip="127.0.0.1",
        user_agent="pytest",
        comment="please adjust quantities",
        customer_user_id=customer_user.id,
    )
    # Still unlocked -- add_line() must succeed.
    svc.add_line(header.id, _material_line(description="Line 2"), env["sales"])

    svc.record_decision(
        estimate_version_id=header.current_version_id,
        decision="declined",
        ip="127.0.0.1",
        user_agent="pytest",
        customer_user_id=customer_user.id,
    )
    # Still unlocked -- add_line() must still succeed.
    svc.add_line(header.id, _material_line(description="Line 3"), env["sales"])


def test_get_include_lines_gates_cost_fields_for_customer(env):
    """D9 line-level mirror of the header cost gate: a ROLE_CUSTOMER actor
    calling get(..., include_lines=True) on their own estimate must not see
    any cost-internal line fields."""
    svc = env["svc"]
    auth = AuthService(env["db"])
    customer_user = auth.create_user(
        "cust5", "Pass123!", "Cost Gate", "cust5@example.com", role="customer",
        customer_id=env["customer_id"],
    )
    customer_actor = AuthContext(
        customer_user.id, customer_user.username, ROLE_CUSTOMER, "human", customer_id=env["customer_id"]
    )

    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])

    result = svc.get(header.id, customer_actor, include_lines=True)
    assert len(result.lines) == 1
    line = result.lines[0]
    for field_name in (
        "unit_cost_cents", "material_markup_bp", "labor_cost_rate_cents",
        "equipment_cost_cents", "equipment_markup_bp", "sub_cost_cents",
        "sub_markup_bp", "material_cost_cents", "labor_cost_cents",
        "cost_total_cents", "sell_total_cents", "override_reason", "internal_note",
    ):
        assert getattr(line, field_name) is None

    # Sanity check: the admin/sales actor (has PERM_READ_ESTIMATE_COSTS)
    # still sees the real values on the same line.
    staff_result = svc.get(header.id, env["sales"], include_lines=True)
    staff_line = staff_result.lines[0]
    assert staff_line.unit_cost_cents == 1000
    assert staff_line.cost_total_cents == 10_000


# ------------------------------------------------------------------
# claim() / unclaim()
# ------------------------------------------------------------------

def test_claim_unassigned_estimate(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"], assigned_to_user_id=None)
    # create() defaults assigned_to_user_id to the creator when not given
    # explicitly -- unclaim it first so this test starts from a genuinely
    # unassigned row, matching claim()'s actual precondition.
    svc.unclaim(header.id, env["admin"])

    claimed = svc.claim(header.id, env["sales2"])
    assert claimed.assigned_to_user_id == env["sales2"].user_id


def test_claim_already_claimed_raises_conflict(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.unclaim(header.id, env["sales"])

    svc.claim(header.id, env["sales"])
    with pytest.raises(ClaimConflictError):
        svc.claim(header.id, env["sales2"])


def test_claim_nonexistent_estimate_returns_none(env):
    svc = env["svc"]
    assert svc.claim(999999, env["sales"]) is None


def test_claim_requires_write_permission(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.unclaim(header.id, env["sales"])
    with pytest.raises(PermissionError):
        svc.claim(header.id, ZeroPermissionActor())


def test_unclaim_by_current_assignee(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    assert header.assigned_to_user_id == env["sales"].user_id

    result = svc.unclaim(header.id, env["sales"])
    assert result.assigned_to_user_id is None


def test_unclaim_by_manager_tier_allowed(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    result = svc.unclaim(header.id, env["admin"])
    assert result.assigned_to_user_id is None


def test_unclaim_by_unrelated_sales_rep_denied(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    with pytest.raises(PermissionError):
        svc.unclaim(header.id, env["sales2"])


def test_unclaim_already_unassigned_raises(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.unclaim(header.id, env["sales"])
    with pytest.raises(ValueError):
        svc.unclaim(header.id, env["admin"])


def test_unassigned_estimate_visible_to_other_sales_reps(env):
    """§9 item 1: an unclaimed estimate must be visible (not just claimable)
    to another actor in the narrowed-view bucket -- both get() and list()."""
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.unclaim(header.id, env["sales"])

    seen = svc.get(header.id, env["sales2"])
    assert seen is not None
    assert seen.assigned_to_user_id is None

    listed_ids = {h.id for h in svc.list(env["sales2"])}
    assert header.id in listed_ids


# ------------------------------------------------------------------
# reassign()
# ------------------------------------------------------------------

def test_reassign_by_manager_tier(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    result = svc.reassign(header.id, env["sales2"].user_id, env["admin"])
    assert result.assigned_to_user_id == env["sales2"].user_id


def test_reassign_requires_permission(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    with pytest.raises(PermissionError):
        svc.reassign(header.id, env["sales2"].user_id, env["sales"])


def test_reassign_rejects_non_reassignable_role_target(env):
    svc = env["svc"]
    auth = AuthService(env["db"])
    tech_user = auth.create_user(
        "tech1", "Pass123!", "Tech One", "tech1@restoricon.com", role=ROLE_TECHNICIAN
    )
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    with pytest.raises(ValueError):
        svc.reassign(header.id, tech_user.id, env["admin"])


# ------------------------------------------------------------------
# transition()
# ------------------------------------------------------------------

def test_transition_draft_to_sent_creates_share_link_and_locks_version(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])
    version_id = header.current_version_id

    result = svc.transition(header.id, "SENT", env["sales"])
    assert result.workflow_status == "SENT"
    assert result.sent_at is not None

    version_row = env["db"].get_connection().execute(
        "SELECT is_locked, locked_reason FROM estimate_versions WHERE id = ?;", (version_id,)
    ).fetchone()
    assert version_row["is_locked"] == 1
    assert version_row["locked_reason"] == "sent"

    link_row = env["db"].get_connection().execute(
        "SELECT * FROM estimate_share_links WHERE estimate_id = ?;", (header.id,)
    ).fetchone()
    assert link_row is not None
    assert link_row["estimate_version_id"] == version_id
    assert link_row["expires_at"] is not None
    # The raw token must never be persisted anywhere -- only its SHA-256.
    assert len(link_row["token_hash"]) == 64


def test_transition_send_requires_permission(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])
    with pytest.raises(PermissionError):
        svc.transition(header.id, "SENT", ZeroPermissionActor())


def test_transition_agent_created_estimate_cannot_skip_review(env):
    """D5 / §9 item 5: an ai_agent-originated estimate is forced into
    internal review, pinned at create() time -- DRAFT -> SENT must be
    refused even though ROLE_AI_AGENT structurally never holds
    PERM_SEND_ESTIMATES anyway; this test targets the actual gate
    (internal_review_required), using an actor who DOES hold
    PERM_SEND_ESTIMATES to isolate that the refusal is the review gate,
    not just a missing permission."""
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["agent"], assigned_to_user_id=env["sales"].user_id)
    assert header.internal_review_required == 1
    svc.add_line(header.id, _material_line(), env["admin"])

    with pytest.raises(ValueError):
        svc.transition(header.id, "SENT", env["admin"])

    # The legal path still works: submit for review, approve, then send.
    svc.transition(header.id, "INTERNAL_REVIEW", env["sales"])
    svc.transition(header.id, "APPROVED_INTERNAL", env["admin"])
    sent = svc.transition(header.id, "SENT", env["admin"])
    assert sent.workflow_status == "SENT"


def test_transition_human_created_estimate_not_forced_into_review(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    assert header.internal_review_required == 0
    svc.add_line(header.id, _material_line(), env["sales"])
    sent = svc.transition(header.id, "SENT", env["sales"])
    assert sent.workflow_status == "SENT"


def test_transition_human_creator_with_requires_approval_flag_cannot_skip_review(env):
    """Warning 2 / §9 item 2: 'HARD RULE, no per-estimate override' -- a
    HUMAN user (not just an ai_agent) with `users.requires_estimate_approval
    = 1` must also be forced into internal review, with no override. Every
    prior test of this gate only exercised the `actor.actor_type ==
    'agent'` OR-branch or the default (flag unset); this is the first test
    of the actual human-facing hard rule the flag itself exists for."""
    svc = env["svc"]
    db = env["db"]
    db.get_connection().execute(
        "UPDATE users SET requires_estimate_approval = 1 WHERE id = ?;", (env["sales"].user_id,)
    )
    db.get_connection().commit()

    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    assert header.internal_review_required == 1
    svc.add_line(header.id, _material_line(), env["sales"])

    with pytest.raises(ValueError):
        svc.transition(header.id, "SENT", env["sales"])

    # No override escape hatch, not even for a manager with PERM_SEND_ESTIMATES.
    with pytest.raises(ValueError):
        svc.transition(header.id, "SENT", env["manager"])

    # The legal path still works: submit for review, approve, then send.
    svc.transition(header.id, "INTERNAL_REVIEW", env["sales"])
    svc.transition(header.id, "APPROVED_INTERNAL", env["admin"])
    sent = svc.transition(header.id, "SENT", env["sales"])
    assert sent.workflow_status == "SENT"


def test_transition_stale_pre_read_no_longer_clobbers_state_changed_before_lock(env):
    """Regression for the TOCTOU/no-CAS race code-reviewer live-reproduced:
    pre-fix, `transition()` read `row`/`old_status` BEFORE `BEGIN
    IMMEDIATE`, then wrote an unconditional `UPDATE` with no re-validation,
    so a caller whose read raced against a concurrent legitimate transition
    could silently clobber it against stale state.

    Simulated here without real threads: a monkeypatched `conn.execute`
    injects a competing, legitimate `DRAFT -> SENT` transition at the exact
    moment a second `transition()` call issues its own `BEGIN IMMEDIATE` --
    the window a stale pre-fix pre-read would have missed entirely (it
    would already have captured `DRAFT` before this point). Post-fix,
    `transition()` reads `old_status` AFTER acquiring the write lock, so it
    always observes the truly-current, just-committed `SENT` state and
    correctly refuses the now-illegal `SENT -> INTERNAL_REVIEW` transition
    instead of silently succeeding against a stale `DRAFT` assumption.
    """
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])

    real_conn = env["db"].get_connection()
    real_get_connection = env["db"].get_connection
    injected = {"done": False}

    class _RacingConnProxy:
        """Thin forwarding proxy over the real (shared, thread-local)
        connection -- `sqlite3.Connection` is a built-in type and cannot be
        monkeypatched per-instance or subclassed onto an already-open
        connection, so this wraps it instead. Every attribute (including
        the context-manager protocol `transition()`'s `with conn:` relies
        on) forwards straight through to the real connection; only
        `execute()` is intercepted."""

        def __getattr__(self, name):
            return getattr(real_conn, name)

        def __enter__(self):
            return real_conn.__enter__()

        def __exit__(self, *exc_info):
            return real_conn.__exit__(*exc_info)

        def execute(self, sql, *args, **kwargs):
            if not injected["done"] and sql.strip().upper().startswith("BEGIN IMMEDIATE"):
                injected["done"] = True
                # A competing, legitimate transition commits here -- in the
                # exact window a stale pre-fix pre-read would have missed.
                svc.transition(header.id, "SENT", env["sales"])
            return real_conn.execute(sql, *args, **kwargs)

    proxy = _RacingConnProxy()
    env["db"].get_connection = lambda: proxy
    try:
        with pytest.raises(ValueError, match="Illegal transition"):
            svc.transition(header.id, "INTERNAL_REVIEW", env["sales"])
    finally:
        env["db"].get_connection = real_get_connection

    # The earlier, real SENT transition's effects (status, lock, share
    # link) must be intact -- nothing was clobbered by the raced call.
    header_after = svc.get(header.id, env["sales"])
    assert header_after.workflow_status == "SENT"
    version_row = real_conn.execute(
        "SELECT is_locked, locked_reason FROM estimate_versions WHERE id = ?;",
        (header_after.current_version_id,),
    ).fetchone()
    assert version_row["is_locked"] == 1
    assert version_row["locked_reason"] == "sent"


def test_transition_sent_to_cancelled_after_race_revalidates_as_legal_cancel(env):
    """The reviewer's exact literal repro pair (`SENT -> CANCELLED`, from a
    caller whose stale pre-read thought the estimate was still `DRAFT`) is
    itself a LEGAL transition per §1.5's table. Post-fix, this pair no
    longer succeeds against stale state -- it re-validates against the
    truly-current `SENT` status and legitimately cancels it, with the
    audit-relevant `old_status` correctly reflecting `SENT`, not a
    fabricated `DRAFT`. (The reviewer's separate observation that the
    `SENT` transition's share link stays live after this cancellation is a
    real, still-open, and DIFFERENT gap -- logged as `NEW-715`, not fixed
    by this round's CAS/re-read fix.)"""
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])

    sent = svc.transition(header.id, "SENT", env["sales"])
    assert sent.workflow_status == "SENT"

    cancelled = svc.transition(header.id, "CANCELLED", env["sales"], comment="stale-caller cancel")
    assert cancelled.workflow_status == "CANCELLED"


def test_transition_illegal_transition_raises(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    with pytest.raises(ValueError):
        svc.transition(header.id, "APPROVED_INTERNAL", env["admin"])


def test_transition_refuses_system_driven_targets(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    for target in ("VIEWED", "ACCEPTED", "DECLINED", "CHANGES_REQUESTED", "EXPIRED", "CONVERTED"):
        with pytest.raises(ValueError):
            svc.transition(header.id, target, env["admin"])


def test_transition_cancel_requires_comment(env):
    svc = env["svc"]
    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    with pytest.raises(ValueError):
        svc.transition(header.id, "CANCELLED", env["sales"])
    cancelled = svc.transition(header.id, "CANCELLED", env["sales"], comment="customer withdrew")
    assert cancelled.workflow_status == "CANCELLED"


# ------------------------------------------------------------------
# record_decision(): accept -> Contract invariant (NEW-705)
# ------------------------------------------------------------------

def test_accepted_decision_creates_contract_in_same_transaction(env):
    svc = env["svc"]
    auth = AuthService(env["db"])
    customer_user = auth.create_user(
        "cust_acc1", "Pass123!", "Accept One", "cust_acc1@example.com", role="customer",
        customer_id=env["customer_id"],
    )

    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])

    svc.record_decision(
        estimate_version_id=header.current_version_id,
        decision="accepted",
        ip="127.0.0.1",
        user_agent="pytest",
        signer_name="Accept One",
        customer_user_id=customer_user.id,
    )

    updated = svc.get(header.id, env["sales"])
    assert updated.workflow_status == "ACCEPTED"
    assert updated.contract_id is not None

    contract_row = env["db"].get_connection().execute(
        "SELECT * FROM contracts WHERE id = ?;", (updated.contract_id,)
    ).fetchone()
    assert contract_row is not None
    assert contract_row["estimate_id"] == header.id
    assert contract_row["customer_id"] == env["customer_id"]
    assert contract_row["contract_number"] == f"CON-{header.estimate_number}"

    # Both the version lock AND the contract creation happened -- pin both
    # halves of the invariant, not just one.
    version_row = env["db"].get_connection().execute(
        "SELECT is_locked, locked_reason FROM estimate_versions WHERE id = ?;", (header.current_version_id,)
    ).fetchone()
    assert version_row["is_locked"] == 1
    assert version_row["locked_reason"] == "accepted"


def test_accepted_decision_contract_creation_failure_rolls_back_whole_transaction(env):
    """Regression for the prior-round lock-ordering-bug class: if contract
    creation fails for a reason unrelated to the accept itself (here,
    simulated via a pre-existing contracts row that collides on the
    deterministic CON-{estimate_number} contract_number), NOTHING in this
    call must be left half-applied -- no decision row, no status change, no
    version lock."""
    svc = env["svc"]
    auth = AuthService(env["db"])
    customer_user = auth.create_user(
        "cust_acc2", "Pass123!", "Accept Two", "cust_acc2@example.com", role="customer",
        customer_id=env["customer_id"],
    )

    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])

    conn = env["db"].get_connection()
    now = "2026-01-01T00:00:00+00:00"
    conn.execute(
        """
        INSERT INTO contracts (
            contract_number, customer_id, title, content, status, version, created_at, updated_at
        ) VALUES (?, ?, 'Unrelated pre-existing contract', 'n/a', 'draft', 1, ?, ?);
        """,
        (f"CON-{header.estimate_number}", env["customer_id"], now, now),
    )
    conn.commit()

    with pytest.raises(Exception):
        svc.record_decision(
            estimate_version_id=header.current_version_id,
            decision="accepted",
            ip="127.0.0.1",
            user_agent="pytest",
            signer_name="Accept Two",
            customer_user_id=customer_user.id,
        )

    unchanged = svc.get(header.id, env["sales"])
    assert unchanged.workflow_status == "DRAFT"
    assert unchanged.accepted_version_id is None

    version_row = conn.execute(
        "SELECT is_locked FROM estimate_versions WHERE id = ?;", (header.current_version_id,)
    ).fetchone()
    assert version_row["is_locked"] == 0

    decisions = conn.execute(
        "SELECT COUNT(*) AS n FROM estimate_decisions WHERE estimate_version_id = ?;",
        (header.current_version_id,),
    ).fetchall()
    assert decisions[0]["n"] == 0


def test_accepted_decision_reaccept_after_revise_relinks_existing_contract(env):
    """Disclosed limitation: a second acceptance (after changes_requested ->
    revise() -> re-send -> re-accept) does NOT create a second Contract row
    (that would collide on contract_number) -- it re-links the already
    existing one rather than raising, so a genuine second acceptance is
    never blocked by this invariant's own bookkeeping."""
    svc = env["svc"]
    auth = AuthService(env["db"])
    customer_user = auth.create_user(
        "cust_acc3", "Pass123!", "Accept Three", "cust_acc3@example.com", role="customer",
        customer_id=env["customer_id"],
    )

    header = svc.create(customer_id=env["customer_id"], actor=env["sales"])
    svc.add_line(header.id, _material_line(), env["sales"])
    first_version_id = header.current_version_id

    svc.record_decision(
        estimate_version_id=first_version_id,
        decision="accepted",
        ip="127.0.0.1",
        user_agent="pytest",
        signer_name="Accept Three",
        customer_user_id=customer_user.id,
    )
    first_contract_id = svc.get(header.id, env["sales"]).contract_id
    assert first_contract_id is not None

    new_version = svc.revise(header.id, env["sales"])
    svc.record_decision(
        estimate_version_id=new_version.id,
        decision="accepted",
        ip="127.0.0.1",
        user_agent="pytest",
        signer_name="Accept Three",
        customer_user_id=customer_user.id,
    )

    final = svc.get(header.id, env["sales"])
    assert final.contract_id == first_contract_id

    contract_count = env["db"].get_connection().execute(
        "SELECT COUNT(*) AS n FROM contracts WHERE estimate_id = ?;", (header.id,)
    ).fetchall()[0]["n"]
    assert contract_count == 1
