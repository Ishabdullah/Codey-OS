"""
Tests for Phase B9.2 -- EstimateService (restoricon_core/services/estimate_service.py).

Covers the task's five required regression cases (material-markup default,
explicit-zero override, revise() clone verbatim, 'combined'-line gating,
plus standard CRUD/versioning/lock-immutability coverage) and the RBAC gate.
"""

import pytest

from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN, ROLE_CUSTOMER, ROLE_SALES
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService
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

    customer = crm.create_customer(Customer(first_name="Jane", last_name="Doe"), admin)

    return {"db": db, "svc": svc, "admin": admin, "sales": sales, "customer_id": customer.id}


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
