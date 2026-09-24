"""
Unit tests for B8.12b (sales_rep_portal.md §B8.12, request §23/§24): the
production_handoff_checklists table + CRMService's checklist CRUD and the
guarded completion action, plus record_payment's new payment_type
deposit-tagging mechanism.

Confirmed decisions (Ish, 2026-09-24, folded into this round's spec):
1. Deposit-received tagging is an explicit payment_type='deposit' field,
   NOT a sum-of-payments inference.
2. The completion guard blocks checklist completion ONLY, never project
   creation or production tracking.
3. All 7 checklist items are always present; each is individually
   'done'/'na'/'pending' -- complete once every item is done-or-na.
"""

import json
import socket
import urllib.error
import urllib.request

import pytest

from restoricon_core.api.server import RestoriconAPIServer
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_PROJECT_MANAGER,
    ROLE_SALES,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    Contract,
    Customer,
    Invoice,
    PRODUCTION_HANDOFF_CHECKLIST_ITEMS,
    Project,
)
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService


def _make_actor(auth_service, username, role, email=None):
    user = auth_service.create_user(
        username=username,
        plain_password="Password123",
        full_name=username.title(),
        email=email or f"{username}@test.com",
        role=role,
    )
    return AuthContext(user_id=user.id, username=username, role=role, actor_type="human")


@pytest.fixture
def setup_services():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)
    return db, auth_service, audit_service, crm_service


def _make_project(crm_service, admin, rep=None):
    cust = crm_service.create_customer(
        Customer(first_name="Hand", last_name="Off", email="handoff_customer@test.com"), admin
    )
    project = crm_service.create_project(
        Project(customer_id=cust.id, title="Handoff Restoration"), admin
    )
    return cust, project


def _make_signed_contract(crm_service, admin, customer, project, assigned_user_id=None):
    contract = crm_service.create_contract(
        Contract(
            contract_number=f"C-{project.id}",
            customer_id=customer.id,
            project_id=project.id,
            title="GC Contract",
            template_name="general_remodeling",
            content="Terms...",
        ),
        admin,
    )
    signed = crm_service.sign_contract(contract.id, "signature-data", admin)
    return signed


def _make_invoice(crm_service, admin, customer, project, deposit_amount=1000.0, amount=10000.0):
    invoice = crm_service.create_invoice(
        Invoice(
            customer_id=customer.id,
            project_id=project.id,
            amount=amount,
            deposit_amount=deposit_amount,
        ),
        admin,
    )
    return invoice


def _mark_all_items(crm_service, admin, project_id, status="done"):
    for item in PRODUCTION_HANDOFF_CHECKLIST_ITEMS:
        crm_service.update_handoff_checklist_item(project_id, item, status, admin)


# ==========================================
# Checklist CRUD round-trip
# ==========================================


def test_create_handoff_checklist_all_items_pending(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    checklist = crm_service.create_handoff_checklist(project.id, admin)
    assert checklist.id is not None
    assert checklist.project_id == project.id
    assert set(checklist.items.keys()) == set(PRODUCTION_HANDOFF_CHECKLIST_ITEMS)
    assert all(v == "pending" for v in checklist.items.values())
    assert checklist.completed_at is None
    assert checklist.completed_by is None
    assert checklist.created_by == admin.user_id


def test_create_handoff_checklist_duplicate_rejected(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    crm_service.create_handoff_checklist(project.id, admin)
    with pytest.raises(ValueError, match="already has a handoff checklist"):
        crm_service.create_handoff_checklist(project.id, admin)


def test_create_handoff_checklist_project_not_found(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    with pytest.raises(ValueError, match="not found"):
        crm_service.create_handoff_checklist(999999, admin)


def test_update_handoff_checklist_item_round_trip(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)
    crm_service.create_handoff_checklist(project.id, admin)

    updated = crm_service.update_handoff_checklist_item(project.id, "permits", "na", admin)
    assert updated.items["permits"] == "na"
    assert all(v == "pending" for k, v in updated.items.items() if k != "permits")

    updated2 = crm_service.update_handoff_checklist_item(project.id, "permits", "done", admin)
    assert updated2.items["permits"] == "done"


def test_update_handoff_checklist_item_invalid_item(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)
    crm_service.create_handoff_checklist(project.id, admin)

    with pytest.raises(ValueError, match="Invalid checklist item"):
        crm_service.update_handoff_checklist_item(project.id, "not_a_real_item", "done", admin)


def test_update_handoff_checklist_item_invalid_status(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)
    crm_service.create_handoff_checklist(project.id, admin)

    with pytest.raises(ValueError, match="Invalid item status"):
        crm_service.update_handoff_checklist_item(project.id, "permits", "not_a_status", admin)


def test_get_handoff_checklist_returns_none_when_missing(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)
    # No checklist created -- confirms a project can be created/tracked
    # in production with no checklist at all.
    assert crm_service.get_handoff_checklist(project.id, admin) is None


def test_get_handoff_checklist_includes_guard_status(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust, project = _make_project(crm_service, admin)
    crm_service.create_handoff_checklist(project.id, admin)

    result = crm_service.get_handoff_checklist(project.id, admin)
    assert result["project_id"] == project.id
    assert result["guard"]["contract_signed"] is False
    assert result["guard"]["deposit_received"] is False
    assert result["guard"]["items_complete"] is False
    assert len(result["guard"]["blocking_reasons"]) == 3


# ==========================================
# Project creation / production tracking is never gated (guard is
# completion-only)
# ==========================================


def test_project_creation_never_blocked_by_missing_or_incomplete_checklist(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    # No checklist at all
    cust, project = _make_project(crm_service, admin)
    assert project.id is not None
    fetched = crm_service.get_project(project.id, admin)
    assert fetched is not None
    assert fetched.status == "planning"

    # Incomplete checklist also does not block reading/using the project.
    crm_service.create_handoff_checklist(project.id, admin)
    crm_service.update_handoff_checklist_item(project.id, "scope", "done", admin)
    still_fetched = crm_service.get_project(project.id, admin)
    assert still_fetched is not None


# ==========================================
# complete_handoff_checklist guard
# ==========================================


def test_complete_handoff_checklist_blocks_unsigned_contract(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust, project = _make_project(crm_service, admin)
    crm_service.create_handoff_checklist(project.id, admin)
    _mark_all_items(crm_service, admin, project.id, "done")

    invoice = _make_invoice(crm_service, admin, cust, project, deposit_amount=500.0)
    crm_service.record_payment(invoice.id, 500.0, "check", "ref-1", admin, payment_type="deposit")

    with pytest.raises(ValueError, match="contract is not signed"):
        crm_service.complete_handoff_checklist(project.id, admin)


def test_complete_handoff_checklist_blocks_missing_deposit_payment(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust, project = _make_project(crm_service, admin)
    crm_service.create_handoff_checklist(project.id, admin)
    _mark_all_items(crm_service, admin, project.id, "done")
    _make_signed_contract(crm_service, admin, cust, project)
    _make_invoice(crm_service, admin, cust, project, deposit_amount=500.0)
    # No payment recorded at all.

    with pytest.raises(ValueError, match="no qualifying deposit payment"):
        crm_service.complete_handoff_checklist(project.id, admin)


def test_complete_handoff_checklist_blocks_deposit_payment_under_threshold(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust, project = _make_project(crm_service, admin)
    crm_service.create_handoff_checklist(project.id, admin)
    _mark_all_items(crm_service, admin, project.id, "done")
    _make_signed_contract(crm_service, admin, cust, project)
    invoice = _make_invoice(crm_service, admin, cust, project, deposit_amount=1000.0)
    crm_service.record_payment(invoice.id, 250.0, "check", "ref-2", admin, payment_type="deposit")

    with pytest.raises(ValueError, match="no qualifying deposit payment"):
        crm_service.complete_handoff_checklist(project.id, admin)


def test_complete_handoff_checklist_ignores_untagged_or_legacy_payment(setup_services):
    """A payment recorded with the default payment_type='installment' (or
    a legacy payment dict predating this round with no payment_type key
    at all) must never satisfy the deposit guard."""
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust, project = _make_project(crm_service, admin)
    crm_service.create_handoff_checklist(project.id, admin)
    _mark_all_items(crm_service, admin, project.id, "done")
    _make_signed_contract(crm_service, admin, cust, project)
    invoice = _make_invoice(crm_service, admin, cust, project, deposit_amount=500.0)
    # Default payment_type (installment) -- amount matches but is not tagged.
    crm_service.record_payment(invoice.id, 500.0, "check", "ref-3", admin)

    with pytest.raises(ValueError, match="no qualifying deposit payment"):
        crm_service.complete_handoff_checklist(project.id, admin)

    # Simulate a legacy payment dict with no payment_type key at all.
    conn = crm_service.db.get_connection()
    row = conn.execute("SELECT payments_json FROM invoices WHERE id = ?;", (invoice.id,)).fetchone()
    import json as _json
    payments = _json.loads(row["payments_json"])
    del payments[0]["payment_type"]
    with conn:
        conn.execute(
            "UPDATE invoices SET payments_json = ? WHERE id = ?;",
            (_json.dumps(payments), invoice.id),
        )
    with pytest.raises(ValueError, match="no qualifying deposit payment"):
        crm_service.complete_handoff_checklist(project.id, admin)


def test_complete_handoff_checklist_blocks_pending_items(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust, project = _make_project(crm_service, admin)
    crm_service.create_handoff_checklist(project.id, admin)
    _make_signed_contract(crm_service, admin, cust, project)
    invoice = _make_invoice(crm_service, admin, cust, project, deposit_amount=500.0)
    crm_service.record_payment(invoice.id, 500.0, "check", "ref-4", admin, payment_type="deposit")
    # Mark only some items -- leave the rest pending.
    crm_service.update_handoff_checklist_item(project.id, "scope", "done", admin)

    with pytest.raises(ValueError, match="checklist item.s. still pending"):
        crm_service.complete_handoff_checklist(project.id, admin)


def test_complete_handoff_checklist_succeeds_when_all_conditions_met(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust, project = _make_project(crm_service, admin)
    crm_service.create_handoff_checklist(project.id, admin)
    # Mix of done/na is allowed -- not all "done".
    for i, item in enumerate(PRODUCTION_HANDOFF_CHECKLIST_ITEMS):
        crm_service.update_handoff_checklist_item(
            project.id, item, "na" if i % 2 == 0 else "done", admin
        )
    _make_signed_contract(crm_service, admin, cust, project)
    invoice = _make_invoice(crm_service, admin, cust, project, deposit_amount=500.0)
    crm_service.record_payment(invoice.id, 500.0, "check", "ref-5", admin, payment_type="deposit")

    # Before completing, exercise the REAL guard evaluation (not the
    # post-completion hardcoded shape below) to confirm each condition is
    # independently recognized as satisfied.
    pre_result = crm_service.get_handoff_checklist(project.id, admin)
    assert pre_result["completed_at"] is None
    assert pre_result["guard"]["contract_signed"] is True
    assert pre_result["guard"]["deposit_received"] is True
    assert pre_result["guard"]["items_complete"] is True
    assert pre_result["guard"]["blocking_reasons"] == []

    completed = crm_service.complete_handoff_checklist(project.id, admin)
    assert completed.completed_at is not None
    assert completed.completed_by == admin.user_id

    # get_handoff_checklist's post-completion response is the deliberately
    # hardcoded "fully satisfied" shape (see get_handoff_checklist's
    # docstring) -- this asserts that shape, not a re-derivation of the
    # guard (the pre-completion assertions above already cover that).
    result = crm_service.get_handoff_checklist(project.id, admin)
    assert result["completed_at"] is not None
    assert result["guard"]["blocking_reasons"] == []


def test_complete_handoff_checklist_deposit_amount_over_threshold_ok(setup_services):
    """A payment tagged 'deposit' with amount strictly greater than
    deposit_amount still satisfies the >= comparison."""
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust, project = _make_project(crm_service, admin)
    crm_service.create_handoff_checklist(project.id, admin)
    _mark_all_items(crm_service, admin, project.id, "done")
    _make_signed_contract(crm_service, admin, cust, project)
    invoice = _make_invoice(crm_service, admin, cust, project, deposit_amount=500.0)
    crm_service.record_payment(invoice.id, 750.0, "check", "ref-6", admin, payment_type="deposit")

    completed = crm_service.complete_handoff_checklist(project.id, admin)
    assert completed.completed_at is not None


def test_complete_handoff_checklist_already_completed_rejected(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust, project = _make_project(crm_service, admin)
    crm_service.create_handoff_checklist(project.id, admin)
    _mark_all_items(crm_service, admin, project.id, "done")
    _make_signed_contract(crm_service, admin, cust, project)
    invoice = _make_invoice(crm_service, admin, cust, project, deposit_amount=500.0)
    crm_service.record_payment(invoice.id, 500.0, "check", "ref-7", admin, payment_type="deposit")
    crm_service.complete_handoff_checklist(project.id, admin)

    with pytest.raises(ValueError, match="already completed"):
        crm_service.complete_handoff_checklist(project.id, admin)


def test_update_handoff_checklist_item_rejected_after_completion(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust, project = _make_project(crm_service, admin)
    crm_service.create_handoff_checklist(project.id, admin)
    _mark_all_items(crm_service, admin, project.id, "done")
    _make_signed_contract(crm_service, admin, cust, project)
    invoice = _make_invoice(crm_service, admin, cust, project, deposit_amount=500.0)
    crm_service.record_payment(invoice.id, 500.0, "check", "ref-8", admin, payment_type="deposit")
    crm_service.complete_handoff_checklist(project.id, admin)

    with pytest.raises(ValueError, match="already completed"):
        crm_service.update_handoff_checklist_item(project.id, "scope", "pending", admin)


# ==========================================
# RBAC
# ==========================================


def test_sales_rep_cannot_write_checklist(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    rep = _make_actor(auth_service, "rep", ROLE_SALES)
    cust, project = _make_project(crm_service, admin)

    with pytest.raises(PermissionError):
        crm_service.create_handoff_checklist(project.id, rep)

    crm_service.create_handoff_checklist(project.id, admin)
    with pytest.raises(PermissionError):
        crm_service.update_handoff_checklist_item(project.id, "scope", "done", rep)
    with pytest.raises(PermissionError):
        crm_service.complete_handoff_checklist(project.id, rep)


def test_technician_cannot_write_checklist(setup_services):
    """PERM_WRITE_PROJECTS is admin/manager/PM tier -- ROLE_TECHNICIAN
    holds PERM_WRITE_OPERATIONS, a different permission, and must not be
    able to write the checklist just by holding that."""
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    tech = _make_actor(auth_service, "tech", ROLE_TECHNICIAN)
    cust, project = _make_project(crm_service, admin)

    with pytest.raises(PermissionError):
        crm_service.create_handoff_checklist(project.id, tech)


def test_project_manager_can_write_checklist(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    pm = _make_actor(auth_service, "pm", ROLE_PROJECT_MANAGER)
    cust, project = _make_project(crm_service, admin)

    checklist = crm_service.create_handoff_checklist(project.id, pm)
    assert checklist.id is not None
    updated = crm_service.update_handoff_checklist_item(project.id, "scope", "done", pm)
    assert updated.items["scope"] == "done"


def test_sold_rep_can_read_own_checklist_but_not_others(setup_services):
    """Reuses B8.12a's PERM_READ_OWN_SOLD_PROJECTS narrowing entirely via
    get_project -- a rep who sold the project (owns the Contract) can
    read its checklist; a rep who did not sell it cannot."""
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    owning_rep = _make_actor(auth_service, "owning_rep", ROLE_SALES)
    other_rep = _make_actor(auth_service, "other_rep", ROLE_SALES)
    cust, project = _make_project(crm_service, admin)
    crm_service.create_handoff_checklist(project.id, admin)

    # Directly assign the contract to owning_rep to establish "sold" ownership.
    contract = crm_service.create_contract(
        Contract(
            contract_number=f"C-{project.id}",
            customer_id=cust.id,
            project_id=project.id,
            title="GC Contract",
        ),
        admin,
    )
    conn = crm_service.db.get_connection()
    with conn:
        conn.execute(
            "UPDATE contracts SET assigned_user_id = ? WHERE id = ?;",
            (owning_rep.user_id, contract.id),
        )

    result = crm_service.get_handoff_checklist(project.id, owning_rep)
    assert result is not None
    assert result["project_id"] == project.id

    with pytest.raises(PermissionError):
        crm_service.get_handoff_checklist(project.id, other_rep)


# ==========================================
# record_payment payment_type
# ==========================================


def test_record_payment_defaults_to_installment_type(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust, project = _make_project(crm_service, admin)
    invoice = _make_invoice(crm_service, admin, cust, project, deposit_amount=100.0)

    updated = crm_service.record_payment(invoice.id, 200.0, "check", "ref-9", admin)
    assert updated.payments[-1]["payment_type"] == "installment"


def test_record_payment_accepts_deposit_type(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust, project = _make_project(crm_service, admin)
    invoice = _make_invoice(crm_service, admin, cust, project, deposit_amount=100.0)

    updated = crm_service.record_payment(
        invoice.id, 100.0, "check", "ref-10", admin, payment_type="deposit"
    )
    assert updated.payments[-1]["payment_type"] == "deposit"


def test_record_payment_rejects_invalid_payment_type(setup_services):
    _, auth_service, _, crm_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    cust, project = _make_project(crm_service, admin)
    invoice = _make_invoice(crm_service, admin, cust, project, deposit_amount=100.0)

    with pytest.raises(ValueError, match="Invalid payment_type"):
        crm_service.record_payment(
            invoice.id, 100.0, "check", "ref-11", admin, payment_type="not_a_type"
        )


# ==========================================
# Route-level (real HTTP dispatch), not service-level. NEW-259's own class
# of bug (a code-complete, reviewer-approved mechanism that was a
# permanent no-op in production) was caught only by exercising the actual
# route layer, not by re-reading the diff -- these prove json_body
# construction, path matching, and response shape for all three write
# routes, two of which (create/complete) deliberately send NO request
# body, unlike the item route.
# ==========================================


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _http(url, method="GET", data=None, headers=None):
    req_headers = dict(headers or {})
    body_bytes = None
    if data is not None:
        body_bytes = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        return e.code, json.loads(body) if body else {}


@pytest.fixture
def live_api_server():
    port = _find_free_port()
    server = RestoriconAPIServer(db_path=":memory:", host="127.0.0.1", port=port)
    server.start(background=True)
    base_url = f"http://127.0.0.1:{port}"
    admin_user = server.auth_service.create_user(
        username="admin",
        plain_password="AdminSecretPassword123",
        full_name="Admin Boss",
        email="admin_handoff@restoricon.com",
        role=ROLE_ADMIN,
    )
    yield server, base_url, admin_user
    server.stop()


def test_handoff_checklist_route_full_round_trip(live_api_server):
    """Exercises all three write routes (create/item/complete) plus the
    GET route over a real HTTP dispatch -- createHandoffChecklist and
    completeHandoffChecklist send no request body at all (only the item
    route does), so this proves handle_request's json_body defaulting
    handles that correctly, not just that the service methods work when
    called directly in Python."""
    server, base_url, admin_user = live_api_server

    status, body = _http(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "admin", "password": "AdminSecretPassword123"},
    )
    assert status == 200
    token = body["token"]
    headers = {"Authorization": f"Bearer {token}"}

    status, body = _http(
        f"{base_url}/api/v1/customers",
        method="POST",
        data={"first_name": "Route", "last_name": "Test", "email": "route_handoff@test.com"},
        headers=headers,
    )
    assert status == 201, body
    customer_id = body["customer"]["id"]

    status, body = _http(
        f"{base_url}/api/v1/projects",
        method="POST",
        data={"customer_id": customer_id, "title": "Route Handoff Project"},
        headers=headers,
    )
    assert status == 201, body
    project_id = body["project"]["id"]

    # GET before any checklist exists -- 404, not a 500.
    status, body = _http(f"{base_url}/api/v1/projects/{project_id}/handoff-checklist", headers=headers)
    assert status == 404, body

    # POST create -- deliberately no request body.
    status, body = _http(
        f"{base_url}/api/v1/projects/{project_id}/handoff-checklist", method="POST", headers=headers
    )
    assert status == 201, body
    assert body["handoff_checklist"]["project_id"] == project_id
    assert set(body["handoff_checklist"]["items"].keys()) == set(PRODUCTION_HANDOFF_CHECKLIST_ITEMS)

    # POST item update -- sends a real body.
    status, body = _http(
        f"{base_url}/api/v1/projects/{project_id}/handoff-checklist/item",
        method="POST",
        data={"item": "scope", "status": "done"},
        headers=headers,
    )
    assert status == 200, body
    assert body["handoff_checklist"]["items"]["scope"] == "done"

    # GET reflects the update and includes the live guard status (a plain
    # dict merge, not a .to_dict() call -- confirms that shape survives
    # real JSON serialization).
    status, body = _http(f"{base_url}/api/v1/projects/{project_id}/handoff-checklist", headers=headers)
    assert status == 200, body
    assert body["handoff_checklist"]["items"]["scope"] == "done"
    assert body["handoff_checklist"]["guard"]["items_complete"] is False
    assert "contract is not signed" in body["handoff_checklist"]["guard"]["blocking_reasons"]

    # POST complete without the guard satisfied -- 400 with a clear reason,
    # not a 500 and not a silent success.
    status, body = _http(
        f"{base_url}/api/v1/projects/{project_id}/handoff-checklist/complete", method="POST", headers=headers
    )
    assert status == 400, body
    assert "contract is not signed" in body["error"]

    # A malformed project_id path segment returns a clean 400, not a 500.
    status, body = _http(f"{base_url}/api/v1/projects/not-a-number/handoff-checklist", headers=headers)
    assert status == 400, body

    # A rep-tier role (no PERM_WRITE_PROJECTS) gets a clean 403 on create,
    # over real HTTP, mirroring the service-level RBAC tests above.
    server.auth_service.create_user(
        username="rep_route",
        plain_password="Password123",
        full_name="Rep Route",
        email="rep_route@test.com",
        role=ROLE_SALES,
    )
    status, body = _http(
        f"{base_url}/api/v1/auth/login",
        method="POST",
        data={"username": "rep_route", "password": "Password123"},
    )
    assert status == 200
    rep_headers = {"Authorization": f"Bearer {body['token']}"}
    status, body = _http(
        f"{base_url}/api/v1/projects/{project_id}/handoff-checklist/complete",
        method="POST",
        headers=rep_headers,
    )
    assert status == 403, body
