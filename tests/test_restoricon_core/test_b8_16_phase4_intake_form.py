"""
Unit/integration tests for B8.16 Phase 4 (the technician/subcontractor-
facing work-order-intake form UI + its POST route, Ish-driven; see
CODEY_MASTER_PLAN.md's B8.16 entry for full phase history). Covers:

  - Role gating of the form's markup itself: present (server-side, not
    client-side) for the technician and subcontractor staff portals,
    absent from the PM and sales portals -- verified against the actual
    rendered HTML bytes, matching test_web_surfaces_admin_wiring.py's
    established style.
  - The client-side line-item row builder routes every dynamic value
    (row description) through escapeHtml() before interpolating it into
    row HTML, and never inlines a line-item object into an onclick/
    oninput attribute -- same discipline NEW-661/664 established
    elsewhere in this file, checked at the source level since this form
    renders no server-side dynamic value (Python-side _pesc escaping has
    nothing to protect here).
  - POST /api/v1/operations/work-order-intake: a real round trip over
    live HTTP through RestoriconAPIServer, confirming it reaches
    CRMService.submit_work_order_intake and produces a
    customer+project+work_order+invoice; RBAC on the route (technician/
    subcontractor succeed, an actor without PERM_WRITE_OPERATIONS is
    rejected with 403); missing-required-field validation (400).
"""

import json
import socket

import pytest
import urllib.request
import urllib.error

from restoricon_core.api.server import RestoriconAPIServer
from restoricon_core.api.web_surfaces import (
    render_pm_surface,
    render_sales_surface,
    render_subcontractor_surface,
    render_tech_surface,
)
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_SUBCONTRACTOR,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer


# ==========================================
# Role-gated markup (static HTML, no server needed)
# ==========================================


def test_intake_form_present_on_technician_portal():
    html = render_tech_surface()
    assert 'id="woiModal"' in html
    assert "openWorkOrderIntakeModal()" in html


def test_intake_form_present_on_subcontractor_portal():
    html = render_subcontractor_surface()
    assert 'id="woiModal"' in html
    assert "openWorkOrderIntakeModal()" in html


def test_intake_form_absent_from_pm_portal():
    html = render_pm_surface()
    assert 'id="woiModal"' not in html
    assert "openWorkOrderIntakeModal" not in html


def test_intake_form_absent_from_sales_portal():
    html = render_sales_surface()
    assert 'id="woiModal"' not in html
    assert "openWorkOrderIntakeModal" not in html


def test_intake_form_line_item_rows_escape_description():
    # The only client-side-rendered dynamic value in this form (a
    # line-item row's description) must be routed through escapeHtml()
    # before being placed in the row's HTML -- matches
    # test_admin_surface_appointment_type_name_is_escaped's established
    # source-level convention for this file's non-f-string-rendered
    # client-side content.
    html = render_tech_surface()
    assert "escapeHtml(item.description)" in html


def test_intake_form_line_items_use_index_lookup_not_inline_object():
    # Regression guard for the exact NEW-661/664 bug class: a line item
    # must never be inlined as a stringified/JSON object into an
    # onclick/oninput attribute -- only a numeric index into the held
    # woiLineItems array.
    html = render_tech_surface()
    assert "JSON.stringify(item)" not in html
    assert "woiUpdateLineItem(${i}" in html
    assert "woiRemoveLineItem(${i})" in html


def test_intake_form_line_item_edit_does_not_trigger_full_rerender():
    # Regression guard for the reviewer-caught focus-loss bug: a full
    # woiRenderLineItems() re-render replaces every row's DOM node via
    # tbody.innerHTML, which destroys whichever <input> currently has
    # focus/caret position. woiUpdateLineItem() fires on every keystroke
    # (its oninput handler), so it must NOT call the full re-render --
    # only the derived-values-only update helper. Reserve the full
    # re-render for woiAddLineItem/woiRemoveLineItem, which genuinely
    # need it since row indices go stale.
    html = render_tech_surface()

    def code_only(src: str) -> str:
        # Strips '//'-prefixed comment lines before asserting, so this
        # test tracks actual code, not comment wording -- anchoring
        # slice boundaries or assertions on prose is fragile (a prior
        # draft of this test anchored on a comment string that itself
        # happened to contain "woiRenderLineItems()", producing a false
        # failure).
        return "\n".join(
            line for line in src.splitlines() if not line.strip().startswith("//")
        )

    start = html.index("function woiUpdateLineItem(index, field, value)")
    end = html.index("function woiUpdateDerivedTotals(index)", start)
    update_fn_body = code_only(html[start:end])
    assert "woiRenderLineItems()" not in update_fn_body
    assert "woiUpdateDerivedTotals(index)" in update_fn_body

    add_start = html.index("function woiAddLineItem()")
    add_end = html.index("function woiRemoveLineItem(index)", add_start)
    assert "woiRenderLineItems()" in code_only(html[add_start:add_end])

    remove_start = add_end
    remove_end = html.index("function woiUpdateLineItem(index, field, value)", remove_start)
    assert "woiRenderLineItems()" in code_only(html[remove_start:remove_end])


# ==========================================
# Route round trip + RBAC (live HTTP)
# ==========================================


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_request(url: str, method: str = "GET", data: dict = None, headers: dict = None):
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    body_bytes = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            return resp.status, json.loads(resp_body) if resp_body else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        return e.code, json.loads(err_body) if err_body else {}


@pytest.fixture
def intake_server():
    port = find_free_port()
    server = RestoriconAPIServer(db_path=":memory:", host="127.0.0.1", port=port)
    server.start(background=True)
    base_url = f"http://127.0.0.1:{port}"

    # Admin created FIRST so it lands users.id == 1, matching
    # intake_system_actor's hardcoded user_id=1 (same NEW-602 FK-fragility
    # as commission_system_actor/pdf_system_actor).
    server.auth_service.create_user(
        username="admin",
        plain_password="AdminSecretPassword123",
        full_name="Admin Boss",
        email="admin@restoricon.com",
        role=ROLE_ADMIN,
    )
    sales_user = server.auth_service.create_user(
        username="sales1",
        plain_password="SalesSecretPassword123",
        full_name="Sales Rep",
        email="sales1@restoricon.com",
        role="sales",
    )
    server.auth_service.create_user(
        username="tech1",
        plain_password="TechSecretPassword123",
        full_name="Tech Nician",
        email="tech1@restoricon.com",
        role=ROLE_TECHNICIAN,
    )
    server.auth_service.create_user(
        username="sub1",
        plain_password="SubSecretPassword123",
        full_name="Sub Contractor",
        email="sub1@restoricon.com",
        role=ROLE_SUBCONTRACTOR,
    )
    admin_ctx = AuthContext(user_id=1, username="admin", role=ROLE_ADMIN, actor_type="human")
    seed_customer = server.crm_service.create_customer(
        Customer(first_name="Seed", last_name="Customer", email="seed.customer@test.com"),
        admin_ctx,
    )
    server.auth_service.create_user(
        username="cust1",
        plain_password="CustSecretPassword123",
        full_name="A Customer",
        email="cust1@restoricon.com",
        role=ROLE_CUSTOMER,
        customer_id=seed_customer.id,
    )

    yield server, base_url, sales_user
    server.stop()


def _login(base_url, username, password):
    status, body = make_request(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": username, "password": password},
    )
    assert status == 200, body
    return {"Authorization": f"Bearer {body['token']}"}


def _intake_payload(sales_user_id, **overrides):
    payload = {
        "salesperson_user_id": sales_user_id,
        "property_address": "123 Test St, Hartford, CT",
        "customer_data": {
            "first_name": "Joy",
            "last_name": "Clark",
            "phone": "(555) 123-4567",
            "email": "joy.clark@test.com",
        },
        "work_order_data": {
            "trade": "plumbing",
            "appliance_type": "Water Heater",
            "issue_description": "Leaking from base",
            "leaking": "Yes",
            "service_call_fee": 75.0,
            "at_home": "Yes",
        },
        "line_items": [
            {"description": "Labor Charge", "quantity": 2.0, "unit_cost": 55.0},
            {"description": "Replacement part", "quantity": 1.0, "unit_cost": 120.0},
        ],
        "reported_technician_name": "Alex Fieldman",
    }
    payload.update(overrides)
    return payload


def test_intake_route_round_trip_technician(intake_server):
    server, base_url, sales_user = intake_server
    headers = _login(base_url, "tech1", "TechSecretPassword123")

    status, body = make_request(
        f"{base_url}/api/v1/operations/work-order-intake",
        method="POST",
        data=_intake_payload(sales_user.id),
        headers=headers,
    )
    assert status == 201, body
    assert body["status"] == "created"
    assert body["customer_created"] is True
    assert body["project_created"] is True
    assert isinstance(body["work_order_id"], int)
    assert isinstance(body["invoice_id"], int)

    # Confirm the pipeline really produced a work order with the server-
    # recomputed total (2*55 + 1*120 = 230.00), not a client-trusted total,
    # and that the invoice reflects the same line items server-side.
    wo = server.operations_service.get_work_order(
        body["work_order_id"],
        AuthContext(user_id=1, username="system", role=ROLE_ADMIN, actor_type="agent"),
    )
    assert wo.total_cost == 230.0


def test_intake_route_round_trip_subcontractor(intake_server):
    server, base_url, sales_user = intake_server
    headers = _login(base_url, "sub1", "SubSecretPassword123")

    status, body = make_request(
        f"{base_url}/api/v1/operations/work-order-intake",
        method="POST",
        data=_intake_payload(sales_user.id, customer_data={
            "first_name": "Sam",
            "last_name": "Rivera",
            "phone": "(555) 987-6543",
            "email": "sam.rivera@test.com",
        }),
        headers=headers,
    )
    assert status == 201, body
    assert isinstance(body["work_order_id"], int)


def test_intake_route_rejects_actor_without_write_operations(intake_server):
    server, base_url, sales_user = intake_server
    headers = _login(base_url, "cust1", "CustSecretPassword123")

    status, body = make_request(
        f"{base_url}/api/v1/operations/work-order-intake",
        method="POST",
        data=_intake_payload(sales_user.id),
        headers=headers,
    )
    assert status == 403, body


def test_intake_route_missing_salesperson_user_id_is_400(intake_server):
    server, base_url, sales_user = intake_server
    headers = _login(base_url, "tech1", "TechSecretPassword123")

    payload = _intake_payload(sales_user.id)
    del payload["salesperson_user_id"]

    status, body = make_request(
        f"{base_url}/api/v1/operations/work-order-intake",
        method="POST",
        data=payload,
        headers=headers,
    )
    assert status == 400, body


def test_intake_route_missing_property_address_is_400(intake_server):
    server, base_url, sales_user = intake_server
    headers = _login(base_url, "tech1", "TechSecretPassword123")

    payload = _intake_payload(sales_user.id, property_address="")

    status, body = make_request(
        f"{base_url}/api/v1/operations/work-order-intake",
        method="POST",
        data=payload,
        headers=headers,
    )
    assert status == 400, body


# ==========================================
# NEW-680: salesperson roster endpoint (narrow id+name-only RBAC surface)
# ==========================================


def test_salesperson_roster_scoped_to_sales_attribution_roles(intake_server):
    # Real security-relevant assertion, not just "the call succeeds": the
    # fixture creates admin (id 1, ROLE_ADMIN), sales1 (id 2, "sales"),
    # tech1 (id 3, ROLE_TECHNICIAN), sub1 (id 4, ROLE_SUBCONTRACTOR), cust1
    # (id 5, ROLE_CUSTOMER). Only admin/sales1 are in SALES_ATTRIBUTION_ROLES
    # -- confirm the roster is exactly those two, not every active user in
    # the system.
    server, base_url, sales_user = intake_server
    headers = _login(base_url, "tech1", "TechSecretPassword123")

    status, body = make_request(
        f"{base_url}/api/v1/operations/salesperson-roster",
        headers=headers,
    )
    assert status == 200, body
    roster_ids = {entry["id"] for entry in body["salespeople"]}
    assert roster_ids == {1, sales_user.id}


def test_salesperson_roster_returns_only_id_and_name(intake_server):
    # A stronger assertion than "email not in entry": the exact key set
    # per entry, so the response can never silently widen later.
    server, base_url, sales_user = intake_server
    headers = _login(base_url, "sub1", "SubSecretPassword123")

    status, body = make_request(
        f"{base_url}/api/v1/operations/salesperson-roster",
        headers=headers,
    )
    assert status == 200, body
    assert len(body["salespeople"]) >= 1
    for entry in body["salespeople"]:
        assert set(entry.keys()) == {"id", "name"}


def test_salesperson_roster_excludes_inactive_user(intake_server):
    server, base_url, sales_user = intake_server
    admin_ctx = AuthContext(user_id=1, username="admin", role=ROLE_ADMIN, actor_type="human")
    inactive_sales = server.auth_service.create_user(
        username="sales2",
        plain_password="SalesSecretPassword456",
        full_name="Departed Rep",
        email="sales2@restoricon.com",
        role="sales",
    )
    server.auth_service.set_user_active(inactive_sales.id, 0, admin_ctx)

    headers = _login(base_url, "tech1", "TechSecretPassword123")
    status, body = make_request(
        f"{base_url}/api/v1/operations/salesperson-roster",
        headers=headers,
    )
    assert status == 200, body
    roster_ids = {entry["id"] for entry in body["salespeople"]}
    assert inactive_sales.id not in roster_ids


def test_salesperson_roster_rejects_actor_without_permission(intake_server):
    server, base_url, sales_user = intake_server
    headers = _login(base_url, "cust1", "CustSecretPassword123")

    status, body = make_request(
        f"{base_url}/api/v1/operations/salesperson-roster",
        headers=headers,
    )
    assert status == 403, body


def test_salesperson_roster_service_layer_rejects_missing_permission():
    # Direct AuthService-level check (not just the HTTP route), mirroring
    # this project's established pytest.raises(PermissionError) convention
    # (see test_appointment_types.py).
    db = DatabaseManager(db_path=":memory:")
    auth_service = AuthService(db)
    customer_ctx = AuthContext(user_id=99, username="cust", role=ROLE_CUSTOMER, actor_type="human")
    with pytest.raises(PermissionError):
        auth_service.list_salesperson_roster(customer_ctx)


def test_salesperson_roster_name_containing_script_tag_is_escaped_in_select_js():
    # NEW-661/664-class regression: a salesperson's full_name is
    # attacker-influenceable (anyone with account-creation/edit access can
    # set it -- AuthService.create_user only .strip()s it, no HTML
    # sanitization). The roster endpoint itself correctly returns the raw
    # name JSON-encoded (JSON-encoding a '<script>' string is not an XSS
    # leak -- it is never HTML-parsed as JSON). The actual guard is
    # source-level, same pattern as
    # test_admin_surface_documents_panel_renders_names_not_raw_ids:
    # confirm the client-side <select> population routes every returned
    # name through escapeHtml() before building option HTML, so a name
    # like `<script>alert(1)</script>` or `Bob"><img onerror=alert(1)>`
    # can never break out of the generated markup. This asserts the JS
    # source routes the value through escapeHtml(), not that any specific
    # payload is neutralized at runtime (no browser/DOM in this test).
    html = render_tech_surface()
    start = html.index("async function woiLoadSalespersonRoster()")
    end = html.index("</script>", start)
    roster_js = html[start:end]
    assert "escapeHtml(s.name)" in roster_js
    assert "${s.name}" not in roster_js


def test_intake_form_salesperson_field_is_select_not_numeric_input():
    html = render_tech_surface()
    assert 'id="woiSalespersonId"' in html
    assert '<select id="woiSalespersonId" required>' in html
    assert '<input type="number" id="woiSalespersonId"' not in html


def test_woi_load_salesperson_roster_401_matches_page_convention_not_logout_user():
    # Regression guard for the reviewer-caught bug: _render_staff_portal_base
    # (the function this form lives in) never defines or calls logoutUser()
    # -- that function only exists in _get_common_script(), which this page
    # does not include. Calling it would throw a ReferenceError, silently
    # swallowed by the surrounding try/catch into the generic "Failed to
    # load, contact admin" placeholder, so an expired session's 401 would
    # never actually redirect the user to log back in. This page's own
    # convention (used elsewhere in the same <script> block, e.g.
    # loadDashboard's 401 handling) is window.location.href =
    # '/admin/login'; confirm woiLoadSalespersonRoster() matches it.
    html = render_tech_surface()
    assert "logoutUser" not in html

    start = html.index("async function woiLoadSalespersonRoster()")
    end = html.index("function closeWorkOrderIntakeModal()", start)
    roster_fn_body = html[start:end]
    assert "if (res.status === 401) { window.location.href = '/admin/login'; return; }" in roster_fn_body

