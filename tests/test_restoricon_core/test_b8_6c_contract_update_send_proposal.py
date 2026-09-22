"""
Unit tests for B8.6c: update_contract/send_contract service methods
(mirrors update_estimate/send_estimate's B8.6b shape exactly) plus the
proposal-composition route. Confirms the allow-list enforcement,
customer-isolation gate (reachable only via a custom_permissions
grant -- unreachable by default role permissions, same as B8.6b's
round-2 tests), rep-ownership narrowing, and idempotent-refusal on
re-send.
"""

import json

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_SALES,
    ROLE_TECHNICIAN,
    PERM_WRITE_CONTRACTS,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import BusinessProfile, ComplianceItem, Contract, Customer, Estimate
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService

from .test_services import _make_scoped_actors


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)
    auth_service = AuthService(db)
    admin_user = auth_service.create_user(
        username="contract_admin", plain_password="Password123", full_name="Admin",
        email="contract_admin@test.com", role=ROLE_ADMIN,
    )
    admin = AuthContext(user_id=admin_user.id, username="contract_admin", role=ROLE_ADMIN, actor_type="human")
    return db, audit_service, crm_service, auth_service, admin


def _make_contract(crm, cust_id, actor, number="CTR-1"):
    return crm.create_contract(
        Contract(
            contract_number=number, customer_id=cust_id, title="Original Title",
            # B8.6d-c: "standard" was never a real template_name value (the
            # field was inert before B8.6d-c gave it real meaning) --
            # updated to a legal CONTRACT_TEMPLATE_NAMES value so
            # create_contract's new validation doesn't reject this fixture.
            template_name="general_remodeling", content="Original content",
        ),
        actor,
    )


def test_update_contract_allow_list_enforced(env):
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="A", last_name="One", email="a1@test.com"), admin)
    contract = _make_contract(crm, cust.id, admin)

    with pytest.raises(ValueError):
        crm.update_contract(contract.id, {"status": "signed"}, admin)
    with pytest.raises(ValueError):
        crm.update_contract(contract.id, {"customer_id": 9999}, admin)
    with pytest.raises(ValueError):
        crm.update_contract(contract.id, {"assigned_user_id": 9999}, admin)
    with pytest.raises(ValueError):
        crm.update_contract(contract.id, {"customer_signature_data": "forged"}, admin)

    updated = crm.update_contract(contract.id, {"title": "New Title", "content": "New content"}, admin)
    assert updated.title == "New Title"
    assert updated.content == "New content"

    refetched = crm.get_contract(contract.id, admin)
    assert refetched.title == "New Title"
    assert refetched.content == "New content"


def test_update_contract_excludes_content_from_audit_payload(env):
    """The existing send_contract audit assertion is vacuous for proving
    _AUDITABLE_CONTRACT_FIELDS' exclusion of content actually works --
    send_contract never touches content, so the assertion holds
    regardless of whether fields= filtering works. update_contract is the
    method that actually changes content; this test calls it with a
    content change and asserts content does not leak into the audit
    log's changed_fields, proving the exclusion applies where it matters.

    Note: customer_signature_data is NOT asserted here -- it's rejected
    outright by ALLOWED_CONTRACT_UPDATE_FIELDS (see
    test_update_contract_allow_list_enforced), so it can never actually
    change via update_contract and an absence assertion on it here would
    be just as vacuous as the send_contract one this test replaces. Its
    real change path is the signing flow (crm_service.py's sign_contract
    around line 3767), not update_contract; proving the exclusion there
    is out of this test's scope."""
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="A", last_name="Audit", email="a_audit@test.com"), admin)
    contract = _make_contract(crm, cust.id, admin, number="CTR-AUDIT-1")

    crm.update_contract(contract.id, {"title": "Audited Title", "content": "Sensitive new content"}, admin)

    logs = audit_service.query_logs(admin)
    update_logs = [
        l for l in logs
        if l.entity_type == "contract" and l.entity_id == contract.id and l.action == "update"
    ]
    assert len(update_logs) == 1
    changed_fields = update_logs[0].details.get("changed_fields", {})
    assert "title" in changed_fields
    assert "content" not in changed_fields


def test_update_contract_rejects_none_values(env):
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="A", last_name="Two", email="a2@test.com"), admin)
    contract = _make_contract(crm, cust.id, admin)

    with pytest.raises(ValueError):
        crm.update_contract(contract.id, {"title": None}, admin)


def test_update_contract_respects_rep_ownership_narrowing(env):
    db, audit_service, crm, auth_service, admin = env
    _admin2, actor_rep_a, actor_rep_b, actor_manager, cust = _make_scoped_actors(auth_service, crm, "ctrscope")

    contract = _make_contract(crm, cust.id, actor_rep_a, number="CTR-SCOPE-UPD")

    # rep_b does not own this contract and lacks PERM_READ_TEAM_SALES_DATA.
    assert crm.update_contract(contract.id, {"title": "sneaky"}, actor_rep_b) is None

    # rep_a (owner) can update it.
    updated = crm.update_contract(contract.id, {"title": "legit"}, actor_rep_a)
    assert updated.title == "legit"

    # A full-tier actor can update someone else's contract.
    updated2 = crm.update_contract(contract.id, {"title": "manager edit"}, actor_manager)
    assert updated2.title == "manager edit"


def test_update_contract_customer_isolation_even_with_granted_write_permission(env):
    """A ROLE_CUSTOMER actor is not reachable via default role permissions
    (ROLE_CUSTOMER lacks write:contracts by default), but an admin can
    grant it per-user via custom_permissions_json. Under that grant, the
    customer-isolation gate must still block cross-customer access -- the
    rep-ownership branch alone (guarded by `actor.role != ROLE_CUSTOMER`)
    never runs for this actor. Deliberately tested even though currently
    unreachable via default role permissions, matching B8.6b's round-2
    rationale: a future custom_permissions grant could reach it."""
    db, audit_service, crm, auth_service, admin = env
    cust_a = crm.create_customer(Customer(first_name="A", last_name="Owner", email="ctr_owner_a@test.com"), admin)
    cust_b = crm.create_customer(Customer(first_name="B", last_name="Other", email="ctr_other_b@test.com"), admin)

    contract = _make_contract(crm, cust_a.id, admin, number="CTR-ISO-1")

    other_cust_user = auth_service.create_user(
        username="ctr_cust_other", plain_password="Password123", full_name="Other Customer",
        email="ctr_cust_other@test.com", role=ROLE_CUSTOMER, customer_id=cust_b.id,
    )
    actor_other_customer = AuthContext(
        user_id=other_cust_user.id, username="ctr_cust_other", role=ROLE_CUSTOMER, actor_type="human",
        customer_id=cust_b.id, custom_permissions={PERM_WRITE_CONTRACTS: True},
    )

    with pytest.raises(PermissionError):
        crm.update_contract(contract.id, {"title": "sneaky cross-customer edit"}, actor_other_customer)

    with pytest.raises(PermissionError):
        crm.send_contract(contract.id, actor_other_customer)

    refetched = crm.get_contract(contract.id, admin)
    assert refetched.title != "sneaky cross-customer edit"
    assert refetched.status == "draft"


def test_update_contract_allows_owning_customer_with_granted_write_permission(env):
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="Own", last_name="Er", email="ctr_owner_c@test.com"), admin)
    contract = _make_contract(crm, cust.id, admin, number="CTR-ISO-2")

    own_cust_user = auth_service.create_user(
        username="ctr_cust_own", plain_password="Password123", full_name="Owning Customer",
        email="ctr_cust_own@test.com", role=ROLE_CUSTOMER, customer_id=cust.id,
    )
    actor_own_customer = AuthContext(
        user_id=own_cust_user.id, username="ctr_cust_own", role=ROLE_CUSTOMER, actor_type="human",
        customer_id=cust.id, custom_permissions={PERM_WRITE_CONTRACTS: True},
    )

    updated = crm.update_contract(contract.id, {"title": "own edit"}, actor_own_customer)
    assert updated.title == "own edit"


def test_send_contract_transitions_draft_to_sent_and_is_audit_logged(env):
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="A", last_name="Three", email="a3@test.com"), admin)
    contract = _make_contract(crm, cust.id, admin, number="CTR-SEND-1")
    assert contract.status == "draft"

    sent = crm.send_contract(contract.id, admin)
    assert sent.status == "sent"

    refetched = crm.get_contract(contract.id, admin)
    assert refetched.status == "sent"

    logs = audit_service.query_logs(admin)
    transition_logs = [
        l for l in logs
        if l.entity_type == "contract" and l.entity_id == contract.id and l.action == "stage_transition"
    ]
    assert len(transition_logs) == 1
    assert "draft" in transition_logs[0].change_summary
    assert "sent" in transition_logs[0].change_summary
    # NEW-314's diff domain excludes content/customer_signature_data -- the
    # audit call must pass fields=_AUDITABLE_CONTRACT_FIELDS (not the
    # unfiltered estimate shape) or content would leak into the payload.
    assert "content" not in transition_logs[0].details.get("changed_fields", {})
    assert "customer_signature_data" not in transition_logs[0].details.get("changed_fields", {})


def test_send_contract_rejects_already_sent(env):
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="A", last_name="Four", email="a4@test.com"), admin)
    contract = _make_contract(crm, cust.id, admin, number="CTR-SEND-2")
    crm.send_contract(contract.id, admin)

    with pytest.raises(ValueError):
        crm.send_contract(contract.id, admin)


def test_send_contract_requires_write_permission(env):
    db, audit_service, crm, auth_service, admin = env
    cust = crm.create_customer(Customer(first_name="A", last_name="Five", email="a5@test.com"), admin)
    contract = _make_contract(crm, cust.id, admin, number="CTR-SEND-3")

    tech_user = auth_service.create_user(
        username="ctr_tech1", plain_password="Password123", full_name="Tech",
        email="ctr_tech1@test.com", role=ROLE_TECHNICIAN,
    )
    actor_tech = AuthContext(user_id=tech_user.id, username="ctr_tech1", role=ROLE_TECHNICIAN, actor_type="human")

    with pytest.raises(PermissionError):
        crm.send_contract(contract.id, actor_tech)


def test_send_contract_respects_rep_ownership_narrowing(env):
    db, audit_service, crm, auth_service, admin = env
    _admin2, actor_rep_a, actor_rep_b, actor_manager, cust = _make_scoped_actors(auth_service, crm, "ctrsendscope")
    contract = _make_contract(crm, cust.id, actor_rep_a, number="CTR-SEND-SCOPE")

    assert crm.send_contract(contract.id, actor_rep_b) is None

    sent = crm.send_contract(contract.id, actor_rep_a)
    assert sent.status == "sent"


# ---------------------------------------------------------------------------
# Route-level: POST /api/v1/contracts/<id>/update, /send,
# GET /api/v1/estimates/<id>/proposal
# ---------------------------------------------------------------------------

@pytest.fixture
def route_env():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    comm_service = CommunicationService(db)
    crm_service = CRMService(db, audit_service)
    sched_service = SchedulingService(db, audit_service)
    auto_service = AutomationService(db, audit_service)
    ops_service = OperationsService(db, audit_service)
    router = APIRouter(
        auth_service=auth_service,
        crm_service=crm_service,
        comm_service=comm_service,
        audit_service=audit_service,
        scheduling_service=sched_service,
        automation_service=auto_service,
        operations_service=ops_service,
    )

    admin_user = auth_service.create_user("route_admin", "Pass123!", "Admin", "route_admin@r.com", role=ROLE_ADMIN)
    admin_token = auth_service.create_token(admin_user)
    actor_admin = AuthContext(admin_user.id, "route_admin", ROLE_ADMIN, "human", token=admin_token)

    sales_user = auth_service.create_user("route_sales", "Pass123!", "Sales", "route_sales@r.com", role=ROLE_SALES)
    sales_token = auth_service.create_token(sales_user)
    actor_sales = AuthContext(sales_user.id, "route_sales", ROLE_SALES, "human", token=sales_token)

    cust = crm_service.create_customer(
        Customer(first_name="Route", last_name="Test", email="route_cust@r.com", service_address="1 Test Ln"),
        actor_admin,
    )
    return {
        "router": router, "crm": crm_service, "cust": cust,
        "actor_admin": actor_admin, "actor_sales": actor_sales,
    }


def _hdr(ctx):
    return {"Authorization": f"Bearer {ctx.token}"}


def test_route_update_contract_200(route_env):
    crm = route_env["crm"]
    contract = crm.create_contract(
        Contract(contract_number="CTR-RT-1", customer_id=route_env["cust"].id, title="T1", content="C1"),
        route_env["actor_admin"],
    )
    status, _, data = route_env["router"].handle_request(
        "POST", f"/api/v1/contracts/{contract.id}/update", _hdr(route_env["actor_admin"]),
        json.dumps({"title": "T1 revised"}).encode(),
    )
    assert status == 200
    assert data["contract"]["title"] == "T1 revised"


def test_route_update_contract_unknown_field_400(route_env):
    crm = route_env["crm"]
    contract = crm.create_contract(
        Contract(contract_number="CTR-RT-2", customer_id=route_env["cust"].id, title="T2", content="C2"),
        route_env["actor_admin"],
    )
    status, _, data = route_env["router"].handle_request(
        "POST", f"/api/v1/contracts/{contract.id}/update", _hdr(route_env["actor_admin"]),
        json.dumps({"status": "signed"}).encode(),
    )
    assert status == 400


def test_route_send_contract_200_then_idempotent_refusal_400(route_env):
    """Confirms the global except ValueError -> 400 handler in
    handle_request catches send_contract's idempotent-refusal, matching
    send_estimate's route behavior."""
    crm = route_env["crm"]
    contract = crm.create_contract(
        Contract(contract_number="CTR-RT-3", customer_id=route_env["cust"].id, title="T3", content="C3"),
        route_env["actor_admin"],
    )
    status, _, data = route_env["router"].handle_request(
        "POST", f"/api/v1/contracts/{contract.id}/send", _hdr(route_env["actor_admin"]), b"",
    )
    assert status == 200
    assert data["contract"]["status"] == "sent"

    status2, _, _ = route_env["router"].handle_request(
        "POST", f"/api/v1/contracts/{contract.id}/send", _hdr(route_env["actor_admin"]), b"",
    )
    assert status2 == 400


def test_route_estimate_proposal_html_admin(route_env):
    crm = route_env["crm"]
    # Matches the real create_estimate/_compute_line_item_costs data shape
    # -- only unit_cost, no unit_price (NEW-576 territory: no real UI
    # authors a per-line unit_price today).
    est = crm.create_estimate(
        Estimate(
            estimate_number="EST-RT-1", customer_id=route_env["cust"].id,
            line_items=[{"description": "Roof repair", "quantity": 1, "unit_cost": 300.0}],
        ),
        route_env["actor_admin"],
    )
    status, headers, body = route_env["router"].handle_request(
        "GET", f"/api/v1/estimates/{est.id}/proposal", _hdr(route_env["actor_admin"]), b"",
    )
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert "Roof repair" in body
    assert "Route Test" in body  # customer name
    # Admin has read:business_profile/read:compliance -- default business
    # name fallback still applies since no BusinessProfile row was created
    # in this test DB.
    assert "Restoricon, LLC" in body


def test_render_estimate_proposal_never_leaks_unit_cost_as_price(route_env):
    """Critical fix verification: an estimate built the way the real
    system builds it (create_estimate -> _compute_line_item_costs, which
    only ever sets unit_cost, never unit_price) must never render its
    internal unit_cost figure in the customer-facing Price column. qty=3
    so the per-unit cost (123.45) can't legitimately appear anywhere in
    the rendered subtotal/total aggregates either."""
    crm = route_env["crm"]
    est = crm.create_estimate(
        Estimate(
            estimate_number="EST-RT-NOPRICE", customer_id=route_env["cust"].id,
            line_items=[{"description": "Water extraction", "quantity": 3, "unit_cost": 123.45}],
        ),
        route_env["actor_admin"],
    )
    status, _, body = route_env["router"].handle_request(
        "GET", f"/api/v1/estimates/{est.id}/proposal", _hdr(route_env["actor_admin"]), b"",
    )
    assert status == 200
    assert "Water extraction" in body
    assert "123.45" not in body
    assert '<td class="num">&mdash;</td>' in body


def test_render_estimate_proposal_none_and_blank_unit_price_render_placeholder():
    """An explicit `unit_price: None` (not just a missing key) must also
    fall through to the placeholder, not float(None or 0) -> $0.00. A
    non-numeric unit_price (e.g. a blank string, storable today per
    NEW-576 -- _compute_line_item_costs only validates quantity/
    unit_cost, not unit_price) must degrade to the placeholder too,
    rather than raising ValueError out of float('') and 500ing this
    customer-facing page."""
    from restoricon_core.api.web_surfaces import render_estimate_proposal
    from restoricon_core.models import Customer, Estimate

    est = Estimate(
        id=1, estimate_number="EST-NONE-1", customer_id=1,
        line_items=[
            {"description": "Debris removal", "quantity": 2, "unit_cost": 50.0, "unit_price": None},
            {"description": "Blank price", "quantity": 1, "unit_cost": 10.0, "unit_price": ""},
        ],
        subtotal=0, discount_amount=0, tax_amount=0, total_amount=0,
    )
    cust = Customer(id=1, first_name="Test", last_name="Customer")
    body = render_estimate_proposal(est, cust)
    assert "Debris removal" in body
    assert "Blank price" in body
    assert "50.0" not in body
    assert body.count('<td class="num">&mdash;</td>') == 2


def test_render_estimate_proposal_renders_real_unit_price_when_present():
    """Guard against over-correcting into a permanently dead price column
    -- when an item genuinely carries a unit_price, it still renders."""
    from restoricon_core.api.web_surfaces import render_estimate_proposal
    from restoricon_core.models import Customer, Estimate

    est = Estimate(
        id=1, estimate_number="EST-PRICE-1", customer_id=1,
        line_items=[{"description": "Package item", "quantity": 1, "unit_price": 500.0}],
        subtotal=500, discount_amount=0, tax_amount=0, total_amount=500,
    )
    cust = Customer(id=1, first_name="Test", last_name="Customer")
    body = render_estimate_proposal(est, cust)
    assert "Package item" in body
    assert '<td class="num">$500.00</td>' in body


def test_route_estimate_proposal_html_sales_rep_degrades_gracefully(route_env):
    """A ROLE_SALES actor lacks read:business_profile/read:compliance
    (NEW-578) -- the proposal route must still return
    200 for the estimate's own rep, just without the compliance section,
    not a 403/500.

    A real BusinessProfile row and a company-scoped ComplianceItem are
    created first, via the admin actor, so this test can differentiate
    "PermissionError caught, degraded gracefully" from "no
    BusinessProfile/ComplianceItem rows exist at all" -- without real
    data present, "Licensed & Insured" not in body would be true
    regardless of whether the route's permission gate does anything.
    """
    router = route_env["router"]
    crm = route_env["crm"]
    actor_admin = route_env["actor_admin"]

    router.automation.upsert_business_profile(
        BusinessProfile(business_name="Degrade Test Co", license_number="LIC-999"),
        actor_admin,
    )
    router.business_ops.create_compliance_item(
        ComplianceItem(
            title="General Liability Policy", category="general_liability",
            entity_type="company", expiration_date="2099-01-01T00:00:00Z",
        ),
        actor_admin,
    )

    est = crm.create_estimate(
        Estimate(
            estimate_number="EST-RT-2", customer_id=route_env["cust"].id,
            line_items=[{"description": "Water mitigation", "quantity": 1, "unit_price": 200.0, "unit_cost": 100.0}],
        ),
        route_env["actor_sales"],
    )

    # Admin has read:business_profile/read:compliance -- the proposal
    # shows the real business/compliance content.
    status_admin, _, body_admin = router.handle_request(
        "GET", f"/api/v1/estimates/{est.id}/proposal", _hdr(actor_admin), b"",
    )
    assert status_admin == 200
    assert "Water mitigation" in body_admin
    assert "Degrade Test Co" in body_admin
    assert "Licensed &amp; Insured" in body_admin
    assert "General Liability Policy" in body_admin

    # ROLE_SALES lacks the read perms -- route degrades gracefully (200,
    # no compliance section) instead of raising/500ing.
    status_sales, headers, body = router.handle_request(
        "GET", f"/api/v1/estimates/{est.id}/proposal", _hdr(route_env["actor_sales"]), b"",
    )
    assert status_sales == 200
    assert "Water mitigation" in body
    assert "Degrade Test Co" not in body
    assert "Licensed &amp; Insured" not in body
    assert "General Liability Policy" not in body


def test_route_estimate_proposal_escapes_injected_customer_name(route_env):
    crm = route_env["crm"]
    evil_cust = crm.create_customer(
        Customer(first_name="<script>alert(1)</script>", last_name="X", email="evil@r.com"),
        route_env["actor_admin"],
    )
    est = crm.create_estimate(
        Estimate(estimate_number="EST-RT-3", customer_id=evil_cust.id, line_items=[]),
        route_env["actor_admin"],
    )
    status, _, body = route_env["router"].handle_request(
        "GET", f"/api/v1/estimates/{est.id}/proposal", _hdr(route_env["actor_admin"]), b"",
    )
    assert status == 200
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_route_estimate_proposal_survives_customer_reassignment_to_other_rep(route_env):
    """NEW-587 regression test. Rep A owns the estimate (assigned_user_id
    via create_estimate). Admin then reassigns the *customer* record
    (NEW-568's own admin assign/reassign feature) to a different rep, B.
    Before the NEW-587 fix, the proposal route's second call --
    get_customer(estimate.customer_id, actor) -- independently re-applied
    NEW-568's rep-ownership narrowing and 404'd for rep A even though
    get_estimate had already authorized them via the estimate's own
    (unchanged) assigned_user_id. The fix must let rep A's proposal call
    keep succeeding here."""
    router = route_env["router"]
    crm = route_env["crm"]
    actor_admin = route_env["actor_admin"]
    actor_sales = route_env["actor_sales"]  # "rep A"

    auth_service = router.auth
    rep_b_user = auth_service.create_user(
        "route_sales_b", "Pass123!", "Sales B", "route_sales_b@r.com", role=ROLE_SALES,
    )
    rep_b_token = auth_service.create_token(rep_b_user)
    actor_sales_b = AuthContext(rep_b_user.id, "route_sales_b", ROLE_SALES, "human", token=rep_b_token)

    est = crm.create_estimate(
        Estimate(
            estimate_number="EST-RT-4", customer_id=route_env["cust"].id,
            line_items=[{"description": "Smoke damage repair", "quantity": 1, "unit_cost": 500.0}],
        ),
        actor_sales,  # rep A's own estimate -- assigned_user_id = rep A
    )

    # Admin reassigns the CUSTOMER (not the estimate) to rep B.
    crm.update_customer(route_env["cust"].id, {"assigned_user_id": rep_b_user.id}, actor_admin)

    # Rep A still owns the estimate and must still be able to view its
    # proposal -- not a 404, per NEW-587.
    status, headers, body = router.handle_request(
        "GET", f"/api/v1/estimates/{est.id}/proposal", _hdr(actor_sales), b"",
    )
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert "Smoke damage repair" in body
    assert "Route Test" in body  # customer's name still renders

    # A rep who never owned the estimate at all (rep B, despite now owning
    # the customer) must still be correctly rejected -- the fix must only
    # skip narrowing on the customer lookup, not widen the estimate-level
    # gate itself.
    status_b, _, _ = router.handle_request(
        "GET", f"/api/v1/estimates/{est.id}/proposal", _hdr(actor_sales_b), b"",
    )
    assert status_b == 404
