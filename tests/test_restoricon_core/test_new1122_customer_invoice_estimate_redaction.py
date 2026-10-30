"""NEW-1122: customers must not see invoice `notes` / payment
`recorded_by_user_id`, nor internal legacy-estimate line-item cost keys
(`cost`, `unit_cost`, `category`); the global-search `notes LIKE` oracle on
those objects is closed too. Staff keep full visibility (negative controls).
In-process APIRouter, no sockets (sandbox-proxy trap).
"""

import json

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthContext, AuthService, ROLE_ADMIN, ROLE_CUSTOMER, ROLE_MANAGER, ROLE_SALES, ROLE_TECHNICIAN, PERM_WRITE_FINANCIALS,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Estimate, Invoice
from restoricon_core.services.analytics_search_service import AnalyticsSearchService
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.business_ops_service import BusinessOpsService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.estimate_service import EstimateService
from restoricon_core.services.finance_service import FinanceService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService

NOTE = "INTERNAL-NOTE-INV-A"
ENOTE = "INTERNAL-NOTE-EST-A"
P = "/api/v1"


def _req(router, method, path, token=None):
    headers = {"authorization": f"Bearer {token}"} if token else {}
    status, _, body = router.handle_request(method, path, headers, b"")
    return status, body


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    auth = AuthService(db)
    crm = CRMService(db, audit)
    router = APIRouter(
        auth_service=auth, crm_service=crm, comm_service=CommunicationService(db),
        audit_service=audit, scheduling_service=SchedulingService(db, audit),
        automation_service=AutomationService(db, audit), operations_service=OperationsService(db, audit),
        finance_service=FinanceService(db, audit), business_ops_service=BusinessOpsService(db, audit),
        analytics_search_service=AnalyticsSearchService(db), estimate_service=EstimateService(db, audit),
    )
    toks = {}
    ctxs = {}
    for role in (ROLE_ADMIN, ROLE_MANAGER, ROLE_SALES, ROLE_TECHNICIAN):
        u = auth.create_user(f"u_{role}", "Passw0rd123!", role, f"{role}@t.com", role)
        toks[role] = auth.create_token(u)
        ctxs[role] = AuthContext(u.id, u.username, role, "human")
    admin = ctxs[ROLE_ADMIN]

    def mk_customer(name):
        c = crm.create_customer(Customer(first_name=name, last_name="X", email=f"{name}@t.com"), admin)
        u = auth.create_user(f"cu_{name}", "Passw0rd123!", name, f"{name}@t.com", role=ROLE_CUSTOMER, customer_id=c.id)
        return c, auth.create_token(u)

    a, a_tok = mk_customer("A")
    b, b_tok = mk_customer("B")

    items = [{"description": "demo", "cost": 1234.0, "unit_cost": 99.0, "category": "labor",
              "quantity": 2, "unit_price": 150.0, "unit": "ea"}]
    est = crm.create_estimate(Estimate(customer_id=a.id, estimate_number="EST-A", line_items=items, notes=ENOTE), admin)
    inv = crm.create_invoice(
        Invoice(customer_id=a.id, notes=NOTE, line_items=[{"description": "Labor", "quantity": 4, "unit_cost": 55.0}]),
        admin,
    )
    crm.record_payment(inv.id, 20.0, "check", "REF1", admin)
    binv = crm.create_invoice(Invoice(customer_id=b.id, notes="B-NOTE", amount=5.0), admin)
    best = crm.create_estimate(Estimate(customer_id=b.id, estimate_number="EST-B", line_items=items), admin)
    return dict(router=router, auth=auth, db=db, ctxs=ctxs, toks=toks, a_tok=a_tok, a=a, est=est, inv=inv, binv=binv, best=best, admin=admin)


def _all_invoice_bodies(env, tok):
    r = env["router"]
    out = []
    s, b = _req(r, "GET", f"{P}/invoices/{env['inv'].id}", tok); assert s == 200, b
    out.append(b["invoice"])
    s, b = _req(r, "GET", f"{P}/invoices", tok); assert s == 200, b
    out.append([i for i in b["invoices"] if i["id"] == env["inv"].id][0])
    return out, b


def _est_bodies(env, tok):
    r = env["router"]
    s, b1 = _req(r, "GET", f"{P}/estimates/{env['est'].id}", tok); assert s == 200, b1
    s, b2 = _req(r, "GET", f"{P}/estimates", tok); assert s == 200, b2
    lst = [e for e in b2["estimates"] if e["id"] == env["est"].id][0]
    return [b1["estimate"], lst], [b1, b2]


def test_customer_invoice_notes_and_recorded_by_hidden(env):
    r = env["router"]
    invs, _ = _all_invoice_bodies(env, env["a_tok"])
    s, portal = _req(r, "GET", f"{P}/portal/invoices", env["a_tok"]); assert s == 200, portal
    invs.append([i for i in portal["invoices"] if i["id"] == env["inv"].id][0])
    assert len(invs) == 3
    for inv in invs:
        assert inv["notes"] is None
        assert NOTE not in json.dumps(inv)
        assert inv["payments"] and all("recorded_by_user_id" not in p for p in inv["payments"])
        assert inv["payments"][0]["amount"] == 20.0
        # no over-stripping: billed price data stays
        assert inv["amount"] == 220.0 and inv["balance_due"] == 200.0
        assert inv["line_items"][0]["unit_cost"] == 55.0 and inv["line_items"][0]["total_cost"] == 220.0


def test_customer_estimate_line_items_allow_list(env):
    objs, raws = _est_bodies(env, env["a_tok"])
    for e in objs:
        assert e["line_items"] == [{"description": "demo", "quantity": 2, "unit": "ea", "unit_price": 150.0}]
        assert e["notes"] is None and e["total_amount"] is not None and "subtotal" in e
    text = json.dumps(raws)
    for needle in ("1234", "unit_cost", '"cost"', "category"):
        assert needle not in text
    s, b = _req(env["router"], "GET", f"{P}/estimates?project_id=999999", env["a_tok"])
    assert s == 200 and b["estimates"] == []


def test_customer_search_cannot_probe_internal_notes(env):
    r = env["router"]
    for q in (NOTE, ENOTE, "INTERNAL-NOTE"):
        s, b = _req(r, "GET", f"{P}/search?q={q}", env["a_tok"]); assert s == 200, b
        assert not b["results"].get("invoices") and not b["results"].get("estimates")
    s, b = _req(r, "GET", f"{P}/search?q={env['inv'].invoice_number}", env["a_tok"])
    assert [i["id"] for i in b["results"]["invoices"]] == [env["inv"].id]


@pytest.mark.parametrize("role", [ROLE_ADMIN, ROLE_MANAGER])
def test_staff_still_see_everything(env, role):
    tok = env["toks"][role]
    invs, _ = _all_invoice_bodies(env, tok)
    for inv in invs:
        assert inv["notes"] == NOTE
        assert "recorded_by_user_id" in inv["payments"][0]
    objs, _ = _est_bodies(env, tok)
    for e in objs:
        li = e["line_items"][0]
        assert li["cost"] == 1234.0 and li["unit_cost"] == 99.0 and li["category"] == "labor"
        assert e["notes"] == ENOTE
    s, b = _req(env["router"], "GET", f"{P}/search?q=INTERNAL-NOTE", tok)
    assert b["results"]["invoices"] and b["results"]["estimates"]


def test_sales_assigned_still_sees_estimate_cost_keys(env):
    sales = env["ctxs"][ROLE_SALES]
    conn = env["db"].get_connection()
    conn.execute("UPDATE estimates SET assigned_user_id = ? WHERE id = ?;", (sales.user_id, env["est"].id))
    conn.commit()
    s, b = _req(env["router"], "GET", f"{P}/estimates/{env['est'].id}", env["toks"][ROLE_SALES])
    assert s == 200, b
    assert b["estimate"]["line_items"][0]["cost"] == 1234.0


def test_technician_estimates_route_forbidden(env):
    s, _ = _req(env["router"], "GET", f"{P}/estimates", env["toks"][ROLE_TECHNICIAN])
    assert s == 403


def test_technician_row_to_estimate_branch_strips_line_items(env):
    row = env["db"].get_connection().execute("SELECT * FROM estimates WHERE id = ?;", (env["est"].id,)).fetchone()
    e = CRMService._row_to_estimate(row, ROLE_TECHNICIAN)
    assert e.line_items == [{"description": "demo", "quantity": 2, "unit": "ea", "unit_price": 150.0}]
    assert e.notes is None


def test_portal_estimates_omits_legacy_crm_estimate_entirely(env):
    """By design (routes.py /portal/estimates): an estimate with no
    current_version_id (legacy CRM-created) is skipped, and listed rows go
    through to_customer_view(), never the legacy line_items. So the legacy
    estimate (with cost keys / notes) must not appear at all. This asserts
    the empty list explicitly; it makes no line-item stripping claim.
    """
    row = env["db"].get_connection().execute(
        "SELECT current_version_id FROM estimates WHERE id = ?;", (env["est"].id,)
    ).fetchone()
    assert row["current_version_id"] is None  # precondition: really a legacy estimate
    s, b = _req(env["router"], "GET", f"{P}/portal/estimates", env["a_tok"])
    assert s == 200, b
    assert b == {"estimates": []}


def _post(router, path, tok, body):
    headers = {"authorization": f"Bearer {tok}"}
    s, _, b = router.handle_request("POST", path, headers, json.dumps(body).encode())
    return s, b


def _paying_customer(env, cust, name):
    auth = env["auth"]
    u = auth.create_user(
        f"pay_{name}", "Passw0rd123!", name, f"pay_{name}@t.com", role=ROLE_CUSTOMER,
        customer_id=cust.id, custom_permissions={PERM_WRITE_FINANCIALS: True},
    )
    return auth.create_token(u)


def test_custom_perm_customer_pay_own_invoice_response_redacted(env):
    tok = _paying_customer(env, env["a"], "A")
    s, b = _post(env["router"], f"{P}/invoices/{env['inv'].id}/pay", tok, {"amount": 5.0})
    assert s == 200, b
    inv = b["invoice"]
    assert inv["notes"] is None and NOTE not in json.dumps(inv)
    assert len(inv["payments"]) == 2 and all("recorded_by_user_id" not in p for p in inv["payments"])
    assert inv["balance_due"] == 195.0


def test_custom_perm_customer_cannot_pay_other_customers_invoice(env):
    tok = _paying_customer(env, env["a"], "A")
    conn = env["db"].get_connection()
    before = conn.execute("SELECT payments_json, balance_due, status FROM invoices WHERE id = ?;", (env["binv"].id,)).fetchone()
    before = tuple(before)
    s, b = _post(env["router"], f"{P}/invoices/{env['binv'].id}/pay", tok, {"amount": 1.0})
    assert s == 403, b
    assert "B-NOTE" not in json.dumps(b)
    after = tuple(conn.execute("SELECT payments_json, balance_due, status FROM invoices WHERE id = ?;", (env["binv"].id,)).fetchone())
    assert after == before


def test_cross_customer_still_403(env):
    r, tok = env["router"], env["a_tok"]
    assert _req(r, "GET", f"{P}/invoices/{env['binv'].id}", tok)[0] == 403
    assert _req(r, "GET", f"{P}/estimates/{env['best'].id}", tok)[0] == 403
