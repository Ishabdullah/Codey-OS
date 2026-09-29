"""
Unit tests for B8.6b (NEW-574): server-side estimate/package pricing
computation. Confirms subtotal/materials_cost/labor_cost/
subcontractor_cost/total_amount are always derived from line_items
server-side (never client-trusted), that send_estimate's draft -> sent
transition is audit-logged and rejects invalid re-transitions, and that
PackageOption's price/gross_profit/margin are likewise always computed
server-side from included_items.
"""

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Estimate, PackageOption
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService

from .test_services import _make_scoped_actors


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)
    auth_service = AuthService(db)
    admin_user = auth_service.create_user(
        username="pkg_admin", plain_password="Password123", full_name="Admin",
        email="pkg_admin@test.com", role=ROLE_ADMIN,
    )
    admin = AuthContext(user_id=admin_user.id, username="pkg_admin", role=ROLE_ADMIN, actor_type="human")
    return db, audit_service, crm_service, auth_service, admin


def _line_items():
    return [
        {"description": "Lumber", "category": "materials", "quantity": 10, "unit_cost": 20.0},   # 200
        {"description": "Crew hours", "category": "labor", "quantity": 8, "unit_cost": 50.0},      # 400
        {"description": "Framer sub", "category": "subcontractor", "quantity": 1, "unit_cost": 300.0},  # 300
        {"description": "Dumpster fee", "quantity": 1, "unit_cost": 100.0},  # no category -> subtotal only
    ]


def test_create_estimate_server_computes_pricing_ignores_client_totals(env):
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="P", last_name="One", email="p1@test.com"), admin)

    # Client supplies self-reported totals wildly different from the real
    # line-item math -- these must be overwritten, not persisted verbatim.
    est = crm.create_estimate(
        Estimate(
            estimate_number="EST-PRICE-1",
            customer_id=cust.id,
            line_items=_line_items(),
            subtotal=999999.0,
            materials_cost=999999.0,
            labor_cost=999999.0,
            subcontractor_cost=999999.0,
            markup_percent=10.0,
            tax_amount=50.0,
            discount_amount=25.0,
            total_amount=1.0,
        ),
        admin,
    )

    # subtotal = 200 + 400 + 300 + 100 = 1000
    assert est.subtotal == 1000.0
    assert est.materials_cost == 200.0
    assert est.labor_cost == 400.0
    assert est.subcontractor_cost == 300.0
    # total = subtotal + markup(10%) - discount + tax = 1000 + 100 - 25 + 50 = 1125
    assert est.total_amount == 1125.0

    # Re-fetch to confirm what's actually persisted, not just the returned object.
    refetched = crm.get_estimate(est.id, admin)
    assert refetched.subtotal == 1000.0
    assert refetched.total_amount == 1125.0


def test_update_estimate_recomputes_pricing_and_rejects_direct_cost_field_writes(env):
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="P", last_name="Two", email="p2@test.com"), admin)

    est = crm.create_estimate(
        Estimate(estimate_number="EST-PRICE-2", customer_id=cust.id, line_items=_line_items(), markup_percent=0.0),
        admin,
    )
    assert est.total_amount == 1000.0

    # A direct client attempt to set total_amount/subtotal via update is
    # rejected outright -- those fields aren't in the update allow-list.
    with pytest.raises(ValueError):
        crm.update_estimate(est.id, {"total_amount": 1.0}, admin)
    with pytest.raises(ValueError):
        crm.update_estimate(est.id, {"subtotal": 1.0}, admin)

    # Changing line_items recomputes every derived field server-side.
    new_items = [{"description": "New materials", "category": "materials", "quantity": 5, "unit_cost": 40.0}]  # 200
    updated = crm.update_estimate(est.id, {"line_items": new_items, "markup_percent": 20.0}, admin)
    assert updated.subtotal == 200.0
    assert updated.materials_cost == 200.0
    assert updated.labor_cost == 0.0
    # total = 200 + 20% markup(40) - 0 discount + 0 tax = 240
    assert updated.total_amount == 240.0

    refetched = crm.get_estimate(est.id, admin)
    assert refetched.total_amount == 240.0
    assert refetched.line_items == new_items


def test_update_estimate_respects_rep_ownership_narrowing(env):
    db, audit_service, crm, auth_service, admin = env
    _admin2, actor_rep_a, actor_rep_b, actor_manager, cust = _make_scoped_actors(auth_service, crm, "updatescope")

    est = crm.create_estimate(
        Estimate(estimate_number="EST-SCOPE-UPD", customer_id=cust.id, line_items=_line_items()), actor_rep_a
    )

    # rep_b does not own this estimate and lacks PERM_READ_TEAM_SALES_DATA.
    assert crm.update_estimate(est.id, {"notes": "sneaky"}, actor_rep_b) is None

    # rep_a (owner) can update it.
    updated = crm.update_estimate(est.id, {"notes": "legit"}, actor_rep_a)
    assert updated.notes == "legit"

    # A full-tier actor can update someone else's estimate.
    updated2 = crm.update_estimate(est.id, {"notes": "manager edit"}, actor_manager)
    assert updated2.notes == "manager edit"


def test_send_estimate_transitions_draft_to_sent_and_is_audit_logged(env):
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="P", last_name="Three", email="p3@test.com"), admin)

    est = crm.create_estimate(
        Estimate(estimate_number="EST-SEND-1", customer_id=cust.id, line_items=_line_items()), admin
    )
    assert est.status == "draft"

    sent = crm.send_estimate(est.id, admin)
    assert sent.status == "sent"

    refetched = crm.get_estimate(est.id, admin)
    assert refetched.status == "sent"

    logs = audit_service.query_logs(admin)
    transition_logs = [
        l for l in logs
        if l.entity_type == "estimate" and l.entity_id == est.id and l.action == "stage_transition"
    ]
    assert len(transition_logs) == 1
    assert "draft" in transition_logs[0].change_summary
    assert "sent" in transition_logs[0].change_summary


def test_send_estimate_rejects_already_sent(env):
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="P", last_name="Four", email="p4@test.com"), admin)

    est = crm.create_estimate(
        Estimate(estimate_number="EST-SEND-2", customer_id=cust.id, line_items=_line_items()), admin
    )
    crm.send_estimate(est.id, admin)

    with pytest.raises(ValueError):
        crm.send_estimate(est.id, admin)


def test_send_estimate_requires_write_permission(env):
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="P", last_name="Five", email="p5@test.com"), admin)
    est = crm.create_estimate(
        Estimate(estimate_number="EST-SEND-3", customer_id=cust.id, line_items=_line_items()), admin
    )

    tech_user = auth_service.create_user(
        username="tech1", plain_password="Password123", full_name="Tech",
        email="tech1@test.com", role=ROLE_TECHNICIAN,
    )
    actor_tech = AuthContext(user_id=tech_user.id, username="tech1", role=ROLE_TECHNICIAN, actor_type="human")

    with pytest.raises(PermissionError):
        crm.send_estimate(est.id, actor_tech)


def _package_items():
    return [
        {"description": "Basic materials", "quantity": 10, "unit_cost": 20.0, "unit_price": 30.0},  # cost 200, price 300
        {"description": "Basic labor", "quantity": 5, "unit_cost": 50.0, "unit_price": 80.0},        # cost 250, price 400
    ]


def test_create_package_option_server_computes_price_margin_gross_profit(env):
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="P", last_name="Six", email="p6@test.com"), admin)
    est = crm.create_estimate(
        Estimate(estimate_number="EST-PKG-1", customer_id=cust.id, line_items=_line_items()), admin
    )

    # Client-supplied price/gross_profit/margin must be ignored/overwritten.
    pkg = crm.create_package_option(
        PackageOption(
            estimate_id=est.id,
            tier="good",
            price=999999.0,
            gross_profit=999999.0,
            margin=999999.0,
            included_items=_package_items(),
        ),
        admin,
    )

    # cost = 200 + 250 = 450, price = 300 + 400 = 700
    assert pkg.price == 700.0
    assert pkg.gross_profit == 250.0
    assert pkg.margin == pytest.approx(round(250.0 / 700.0 * 100.0, 2))

    refetched_list = crm.list_package_options(admin, estimate_id=est.id)
    assert len(refetched_list) == 1
    assert refetched_list[0].price == 700.0
    assert refetched_list[0].gross_profit == 250.0


def test_create_package_option_rejects_invalid_tier(env):
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="P", last_name="Seven", email="p7@test.com"), admin)
    est = crm.create_estimate(
        Estimate(estimate_number="EST-PKG-2", customer_id=cust.id, line_items=_line_items()), admin
    )

    with pytest.raises(ValueError):
        crm.create_package_option(
            PackageOption(estimate_id=est.id, tier="premium", included_items=_package_items()), admin
        )


def test_list_package_options_filtered_by_estimate_id(env):
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="P", last_name="Eight", email="p8@test.com"), admin)
    est_a = crm.create_estimate(
        Estimate(estimate_number="EST-PKG-A", customer_id=cust.id, line_items=_line_items()), admin
    )
    est_b = crm.create_estimate(
        Estimate(estimate_number="EST-PKG-B", customer_id=cust.id, line_items=_line_items()), admin
    )

    crm.create_package_option(
        PackageOption(estimate_id=est_a.id, tier="good", included_items=_package_items()), admin
    )
    crm.create_package_option(
        PackageOption(estimate_id=est_a.id, tier="better", included_items=_package_items()), admin
    )
    crm.create_package_option(
        PackageOption(estimate_id=est_b.id, tier="best", included_items=_package_items()), admin
    )

    a_list = crm.list_package_options(admin, estimate_id=est_a.id)
    assert {p.tier for p in a_list} == {"good", "better"}

    b_list = crm.list_package_options(admin, estimate_id=est_b.id)
    assert {p.tier for p in b_list} == {"best"}


def test_create_package_option_requires_estimate_id(env):
    db, audit_service, crm, auth_service, admin = env
    with pytest.raises(ValueError):
        crm.create_package_option(
            PackageOption(estimate_id=None, tier="good", included_items=_package_items()), admin
        )


def test_customer_sees_package_price_but_not_margin_or_gross_profit(env):
    """A customer viewing their own estimate's package options must see
    the customer-facing `price`, never internal `gross_profit`/`margin`/
    per-item cost data -- mirrors _row_to_estimate's cost-field redaction
    for ROLE_CUSTOMER/ROLE_TECHNICIAN."""
    db, audit_service, crm, auth_service, admin = env
    from restoricon_core.auth import ROLE_CUSTOMER

    cust = crm.create_customer(Customer(first_name="P", last_name="Nine", email="p9@test.com"), admin)
    est = crm.create_estimate(
        Estimate(estimate_number="EST-PKG-CUST", customer_id=cust.id, line_items=_line_items()), admin
    )
    crm.create_package_option(
        PackageOption(estimate_id=est.id, tier="good", included_items=_package_items()), admin
    )

    cust_user = auth_service.create_user(
        username="cust9", plain_password="Password123", full_name="Cust Nine",
        email="cust9_user@test.com", role=ROLE_CUSTOMER, customer_id=cust.id,
    )
    actor_cust = AuthContext(
        user_id=cust_user.id, username="cust9", role=ROLE_CUSTOMER, actor_type="human", customer_id=cust.id
    )

    result = crm.list_package_options(actor_cust, estimate_id=est.id)
    assert len(result) == 1
    assert result[0].price == 700.0
    assert result[0].gross_profit is None
    assert result[0].margin is None
    assert result[0].included_items == []


def test_update_estimate_customer_isolation_even_with_granted_write_permission(env):
    """A ROLE_CUSTOMER actor is not reachable via default role permissions
    (ROLE_CUSTOMER lacks write:estimates by default), but an admin can
    grant it per-user via custom_permissions_json (the same NEW-533
    mechanism). Under that grant, the customer-isolation gate must still
    block cross-customer access -- the rep-ownership branch alone
    (guarded by `actor.role != ROLE_CUSTOMER`) never runs for this actor."""
    from restoricon_core.auth import ROLE_CUSTOMER, PERM_WRITE_ESTIMATES

    db, audit_service, crm, auth_service, admin = env
    cust_a = crm.create_customer(Customer(first_name="A", last_name="Owner", email="owner_a@test.com"), admin)
    cust_b = crm.create_customer(Customer(first_name="B", last_name="Other", email="other_b@test.com"), admin)

    est = crm.create_estimate(
        Estimate(estimate_number="EST-ISO-1", customer_id=cust_a.id, line_items=_line_items()), admin
    )

    other_cust_user = auth_service.create_user(
        username="cust_other", plain_password="Password123", full_name="Other Customer",
        email="cust_other@test.com", role=ROLE_CUSTOMER, customer_id=cust_b.id,
    )
    actor_other_customer = AuthContext(
        user_id=other_cust_user.id, username="cust_other", role=ROLE_CUSTOMER, actor_type="human",
        customer_id=cust_b.id, custom_permissions={PERM_WRITE_ESTIMATES: True},
    )

    with pytest.raises(PermissionError):
        crm.update_estimate(est.id, {"notes": "sneaky cross-customer edit"}, actor_other_customer)

    with pytest.raises(PermissionError):
        crm.send_estimate(est.id, actor_other_customer)

    # Confirm nothing was actually changed.
    refetched = crm.get_estimate(est.id, admin)
    assert refetched.notes != "sneaky cross-customer edit"
    assert refetched.status == "draft"


def test_update_estimate_allows_owning_customer_with_granted_write_permission(env):
    """The isolation gate must not block the *owning* customer -- only
    cross-customer access."""
    from restoricon_core.auth import ROLE_CUSTOMER, PERM_WRITE_ESTIMATES

    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="Own", last_name="Er", email="owner_c@test.com"), admin)

    est = crm.create_estimate(
        Estimate(estimate_number="EST-ISO-2", customer_id=cust.id, line_items=_line_items()), admin
    )

    own_cust_user = auth_service.create_user(
        username="cust_own", plain_password="Password123", full_name="Owning Customer",
        email="cust_own@test.com", role=ROLE_CUSTOMER, customer_id=cust.id,
    )
    actor_own_customer = AuthContext(
        user_id=own_cust_user.id, username="cust_own", role=ROLE_CUSTOMER, actor_type="human",
        customer_id=cust.id, custom_permissions={PERM_WRITE_ESTIMATES: True},
    )

    updated = crm.update_estimate(est.id, {"notes": "own edit"}, actor_own_customer)
    # Redacted response: cost fields are masked for ROLE_CUSTOMER.
    assert updated.materials_cost == 0.0
    assert updated.labor_cost == 0.0
    assert updated.subcontractor_cost == 0.0
    assert updated.markup_percent == 0.0
    assert updated.notes is None


def test_update_estimate_response_redacts_cost_fields_for_customer_and_technician(env):
    """update_estimate's returned object must be genuinely redacted for
    ROLE_CUSTOMER/ROLE_TECHNICIAN, matching get_estimate's shape --
    both the empty-updates early-return path and the normal path."""
    from restoricon_core.auth import ROLE_CUSTOMER, ROLE_TECHNICIAN, PERM_WRITE_ESTIMATES, PERM_READ_ESTIMATES

    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="Red", last_name="Act", email="redact@test.com"), admin)

    tech_user = auth_service.create_user(
        username="tech_redact", plain_password="Password123", full_name="Tech Redact",
        email="tech_redact@test.com", role=ROLE_TECHNICIAN,
    )
    actor_tech = AuthContext(
        user_id=tech_user.id, username="tech_redact", role=ROLE_TECHNICIAN, actor_type="human",
        custom_permissions={PERM_WRITE_ESTIMATES: True, PERM_READ_ESTIMATES: True},
    )

    # Created by actor_tech itself so the rep-ownership narrowing check
    # (assigned_user_id == actor.user_id) doesn't independently block this
    # redaction test.
    est = crm.create_estimate(
        Estimate(estimate_number="EST-REDACT-1", customer_id=cust.id, line_items=_line_items()), actor_tech
    )

    # Empty-updates early-return path.
    empty = crm.update_estimate(est.id, {}, actor_tech)
    assert empty.materials_cost == 0.0
    assert empty.labor_cost == 0.0
    assert empty.subcontractor_cost == 0.0
    assert empty.notes is None

    # Normal (non-empty) update path must match the same masked shape.
    updated = crm.update_estimate(est.id, {"notes": "tech note"}, actor_tech)
    assert updated.materials_cost == 0.0
    assert updated.labor_cost == 0.0
    assert updated.subcontractor_cost == 0.0
    assert updated.markup_percent == 0.0
    assert updated.notes is None

    # But the underlying persisted row is unredacted (verified via admin).
    refetched = crm.get_estimate(est.id, admin)
    assert refetched.materials_cost == 200.0
    assert refetched.notes == "tech note"


def test_send_estimate_response_redacts_cost_fields_for_customer(env):
    from restoricon_core.auth import ROLE_CUSTOMER, PERM_WRITE_ESTIMATES

    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="Send", last_name="Redact", email="sendredact@test.com"), admin)
    est = crm.create_estimate(
        Estimate(estimate_number="EST-REDACT-2", customer_id=cust.id, line_items=_line_items()), admin
    )

    cust_user = auth_service.create_user(
        username="cust_send", plain_password="Password123", full_name="Cust Send",
        email="cust_send@test.com", role=ROLE_CUSTOMER, customer_id=cust.id,
    )
    actor_cust = AuthContext(
        user_id=cust_user.id, username="cust_send", role=ROLE_CUSTOMER, actor_type="human",
        customer_id=cust.id, custom_permissions={PERM_WRITE_ESTIMATES: True},
    )

    sent = crm.send_estimate(est.id, actor_cust)
    assert sent.status == "sent"
    assert sent.materials_cost == 0.0
    assert sent.labor_cost == 0.0
    assert sent.subcontractor_cost == 0.0
    assert sent.markup_percent == 0.0


def test_compute_line_item_costs_rejects_explicit_null_quantity(env):
    """A client-supplied `"quantity": null` must raise a clean ValueError
    (-> 400 at the API layer), not an uncaught TypeError from float(None)."""
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="Null", last_name="Qty", email="nullqty@test.com"), admin)

    bad_items = [{"description": "Bad", "category": "materials", "quantity": None, "unit_cost": 20.0}]
    with pytest.raises(ValueError):
        crm.create_estimate(
            Estimate(estimate_number="EST-NULLQTY-1", customer_id=cust.id, line_items=bad_items), admin
        )


def test_create_package_option_rejects_explicit_null_quantity(env):
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="Null", last_name="Pkg", email="nullpkg@test.com"), admin)
    est = crm.create_estimate(
        Estimate(estimate_number="EST-NULLQTY-2", customer_id=cust.id, line_items=_line_items()), admin
    )

    bad_items = [{"description": "Bad", "quantity": None, "unit_cost": 20.0, "unit_price": 30.0}]
    with pytest.raises(ValueError):
        crm.create_package_option(
            PackageOption(estimate_id=est.id, tier="good", included_items=bad_items), admin
        )


def test_list_package_options_narrowed_by_rep_ownership_when_unfiltered(env):
    db, audit_service, crm, auth_service, admin = env
    _admin2, actor_rep_a, actor_rep_b, actor_manager, cust = _make_scoped_actors(auth_service, crm, "pkgscope")

    est_a = crm.create_estimate(
        Estimate(estimate_number="EST-PKGSCOPE-A", customer_id=cust.id, line_items=_line_items()), actor_rep_a
    )
    est_b = crm.create_estimate(
        Estimate(estimate_number="EST-PKGSCOPE-B", customer_id=cust.id, line_items=_line_items()), actor_rep_b
    )
    crm.create_package_option(
        PackageOption(estimate_id=est_a.id, tier="good", included_items=_package_items()), actor_rep_a
    )
    crm.create_package_option(
        PackageOption(estimate_id=est_b.id, tier="good", included_items=_package_items()), actor_rep_b
    )

    rep_a_unfiltered = crm.list_package_options(actor_rep_a)
    assert {p.estimate_id for p in rep_a_unfiltered} == {est_a.id}

    manager_unfiltered = crm.list_package_options(actor_manager)
    assert {p.estimate_id for p in manager_unfiltered} == {est_a.id, est_b.id}
