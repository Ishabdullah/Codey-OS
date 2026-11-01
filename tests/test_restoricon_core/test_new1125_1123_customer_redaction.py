"""NEW-1125 (Ish decision 2026-10-31) + NEW-1123: for ROLE_CUSTOMER only,
milestone `notes`, the commission-rep `assigned_user_id` on invoices/
estimates/contracts, and the absolute documents `file_path` are hidden.
Staff roles keep all of them (positive controls), another customer is still
denied, and a customer can still download their own document.
In-process APIRouter, no sockets (sandbox-proxy trap).
"""

import json
import os

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthContext, AuthService, ROLE_ADMIN, ROLE_CUSTOMER, ROLE_MANAGER, ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    Contract, Customer, Document, Estimate, Invoice, Project, ProjectMilestone,
)
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

MNOTE = "INTERNAL-MILESTONE-NOTE"
P = "/api/v1"
PAYLOAD = b"%PDF-1.4 customer document bytes"


def _req(router, method, path, token=None):
    headers = {"authorization": f"Bearer {token}"} if token else {}
    status, hdrs, body = router.handle_request(method, path, headers, b"")
    return status, hdrs, body


def _json(router, path, tok):
    s, _, b = _req(router, "GET", path, tok)
    return s, b


@pytest.fixture
def env(tmp_path, monkeypatch):
    store = tmp_path / "docstore"
    store.mkdir()
    monkeypatch.setenv("RESTORICON_DOC_STORE_PATH", str(store))
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    auth = AuthService(db)
    crm = CRMService(db, audit)
    ops = OperationsService(db, audit)
    router = APIRouter(
        auth_service=auth, crm_service=crm, comm_service=CommunicationService(db),
        audit_service=audit, scheduling_service=SchedulingService(db, audit),
        automation_service=AutomationService(db, audit), operations_service=ops,
        finance_service=FinanceService(db, audit), business_ops_service=BusinessOpsService(db, audit),
        analytics_search_service=AnalyticsSearchService(db), estimate_service=EstimateService(db, audit),
    )
    toks, ctxs = {}, {}
    for role in (ROLE_ADMIN, ROLE_MANAGER, ROLE_SALES):
        u = auth.create_user(f"u_{role}", "Passw0rd123!", role, f"{role}@t.com", role)
        toks[role] = auth.create_token(u)
        ctxs[role] = AuthContext(u.id, u.username, role, "human")
    admin = ctxs[ROLE_ADMIN]
    sales = ctxs[ROLE_SALES]

    def mk_customer(name):
        c = crm.create_customer(Customer(first_name=name, last_name="X", email=f"{name}@t.com"), admin)
        u = auth.create_user(f"cu_{name}", "Passw0rd123!", name, f"{name}@t.com", role=ROLE_CUSTOMER, customer_id=c.id)
        return c, auth.create_token(u)

    a, a_tok = mk_customer("A")
    b, b_tok = mk_customer("B")

    proj = crm.create_project(Project(customer_id=a.id, title="Proj A"), admin)
    ms = ops.create_milestone(ProjectMilestone(project_id=proj.id, name="Demo", notes=MNOTE), admin)
    est = crm.create_estimate(Estimate(customer_id=a.id, estimate_number="EST-A"), admin)
    inv = crm.create_invoice(Invoice(customer_id=a.id, amount=10.0), admin)
    contract = crm.create_contract(Contract(customer_id=a.id, project_id=proj.id, title="C-A", content="body"), admin)
    # Rep is the sales user on every record, so the sales role is "assigned"
    # and legitimately sees the id too.
    conn = db.get_connection()
    for table, rid in (("estimates", est.id), ("invoices", inv.id), ("contracts", contract.id)):
        conn.execute(f"UPDATE {table} SET assigned_user_id = ? WHERE id = ?;", (sales.user_id, rid))
    conn.commit()

    doc_file = store / "uploads" / "a.pdf"
    doc_file.parent.mkdir()
    doc_file.write_bytes(PAYLOAD)
    doc = crm.create_document(
        Document(customer_id=a.id, project_id=proj.id, document_type="pdf", title="A doc", file_path=str(doc_file)),
        admin,
    )
    bproj = crm.create_project(Project(customer_id=b.id, title="Proj B"), admin)
    bms = ops.create_milestone(ProjectMilestone(project_id=bproj.id, name="B-ms", notes="B-NOTE"), admin)
    bdoc_file = store / "uploads" / "b.pdf"
    bdoc_file.write_bytes(b"B")
    bdoc = crm.create_document(
        Document(customer_id=b.id, document_type="pdf", title="B doc", file_path=str(bdoc_file)), admin,
    )
    return dict(
        router=router, toks=toks, a_tok=a_tok, b_tok=b_tok, sales_id=sales.user_id, proj=proj, ms=ms,
        est=est, inv=inv, contract=contract, doc=doc, doc_file=str(doc_file), bproj=bproj, bms=bms, bdoc=bdoc,
    )


def _milestone_bodies(env, tok):
    r = env["router"]
    s, b = _json(r, f"{P}/operations/projects/{env['proj'].id}/milestones", tok)
    return s, b


def test_customer_milestone_notes_hidden_portal(env):
    s, b = _json(env["router"], f"{P}/portal/projects/{env['proj'].id}/milestones", env["a_tok"])
    assert s == 200, b
    assert [m["name"] for m in b["milestones"]] == ["Demo"]  # positive: permitted fields still there
    assert b["milestones"][0]["notes"] is None
    assert MNOTE not in json.dumps(b)


@pytest.mark.parametrize("role", [ROLE_ADMIN, ROLE_MANAGER])
def test_staff_still_see_milestone_notes(env, role):
    s, b = _milestone_bodies(env, env["toks"][role])
    assert s == 200, b
    assert b["milestones"][0]["notes"] == MNOTE
    s, b = _json(env["router"], f"{P}/operations/milestones/{env['ms'].id}", env["toks"][role])
    assert s == 200 and b["milestone"]["notes"] == MNOTE


def test_customer_milestone_other_customer_denied(env):
    s, b = _json(env["router"], f"{P}/portal/projects/{env['bproj'].id}/milestones", env["a_tok"])
    assert s == 403, b
    assert "B-NOTE" not in json.dumps(b)


def _contract_bodies(env, tok):
    r = env["router"]
    cid = env["contract"].id
    s1, one = _json(r, f"{P}/contracts/{cid}", tok); assert s1 == 200, one
    s2, lst = _json(r, f"{P}/contracts", tok); assert s2 == 200, lst
    return [one["contract"], [c for c in lst["contracts"] if c["id"] == cid][0]]


def test_customer_commission_rep_hidden_everywhere(env):
    a = env["a_tok"]
    r = env["router"]
    invs, ests, cons = [], [], []
    s, b = _json(r, f"{P}/invoices/{env['inv'].id}", a); assert s == 200, b; invs.append(b["invoice"])
    s, b = _json(r, f"{P}/invoices", a); assert s == 200, b; invs.append([i for i in b["invoices"] if i["id"] == env["inv"].id][0])
    s, b = _json(r, f"{P}/portal/invoices", a); assert s == 200, b; invs.append([i for i in b["invoices"] if i["id"] == env["inv"].id][0])
    s, b = _json(r, f"{P}/estimates/{env['est'].id}", a); assert s == 200, b; ests.append(b["estimate"])
    s, b = _json(r, f"{P}/estimates", a); assert s == 200, b; ests.append([e for e in b["estimates"] if e["id"] == env["est"].id][0])
    cons.extend(_contract_bodies(env, a))
    s, b = _json(r, f"{P}/portal/contracts", a); assert s == 200, b; cons.append([c for c in b["contracts"] if c["id"] == env["contract"].id][0])
    for obj in invs + ests + cons:
        assert obj["assigned_user_id"] is None
    # positive controls: permitted fields survive on the same records
    assert all(i["amount"] == 10.0 for i in invs)
    assert all(e["estimate_number"] == "EST-A" for e in ests)
    assert all(c["title"] == "C-A" and c["content"] == "body" for c in cons)


@pytest.mark.parametrize("role", [ROLE_ADMIN, ROLE_MANAGER, ROLE_SALES])
def test_staff_still_see_commission_rep(env, role):
    tok = env["toks"][role]
    r = env["router"]
    sid = env["sales_id"]
    s, b = _json(r, f"{P}/invoices/{env['inv'].id}", tok); assert s == 200, b
    assert b["invoice"]["assigned_user_id"] == sid
    s, b = _json(r, f"{P}/estimates/{env['est'].id}", tok); assert s == 200, b
    assert b["estimate"]["assigned_user_id"] == sid
    for c in _contract_bodies(env, tok):
        assert c["assigned_user_id"] == sid


def test_customer_commission_rep_hidden_on_sign_response(env):
    r = env["router"]
    headers = {"authorization": f"Bearer {env['a_tok']}"}
    # contract must be 'sent' before a customer can sign
    conn_status = env["router"].crm.db.get_connection()
    conn_status.execute("UPDATE contracts SET status = 'sent' WHERE id = ?;", (env["contract"].id,))
    conn_status.commit()
    s, _, b = r.handle_request(
        "POST", f"{P}/portal/contracts/{env['contract'].id}/sign", headers,
        json.dumps({"signature_data": "sig"}).encode(),
    )
    assert s == 200, b
    assert b["contract"]["assigned_user_id"] is None
    assert b["contract"]["status"] == "signed"
    # the DB row is untouched (redaction is output-only)
    row = conn_status.execute("SELECT assigned_user_id FROM contracts WHERE id = ?;", (env["contract"].id,)).fetchone()
    assert row["assigned_user_id"] == env["sales_id"]


def test_other_customer_still_denied_commission_records(env):
    r, b_tok = env["router"], env["b_tok"]
    assert _req(r, "GET", f"{P}/invoices/{env['inv'].id}", b_tok)[0] == 403
    assert _req(r, "GET", f"{P}/estimates/{env['est'].id}", b_tok)[0] == 403
    assert _req(r, "GET", f"{P}/contracts/{env['contract'].id}", b_tok)[0] == 403
    s, lst = _json(r, f"{P}/contracts", b_tok)
    assert s == 200 and all(c["id"] != env["contract"].id for c in lst["contracts"])


def _doc_bodies(env, tok, portal=False):
    r = env["router"]
    did = env["doc"].id
    out = []
    s, b = _json(r, f"{P}/documents/{did}", tok); assert s == 200, b; out.append(b["document"])
    s, b = _json(r, f"{P}/documents", tok); assert s == 200, b; out.append([d for d in b["documents"] if d["id"] == did][0])
    if portal:
        s, b = _json(r, f"{P}/portal/documents", tok); assert s == 200, b
        out.append([d for d in b["documents"] if d["id"] == did][0])
    return out


def test_customer_documents_hide_file_path(env):
    bodies = _doc_bodies(env, env["a_tok"], portal=True)
    assert len(bodies) == 3
    for d in bodies:
        assert "file_path" not in d
        assert env["doc_file"] not in json.dumps(d)
        assert d["title"] == "A doc" and d["id"] == env["doc"].id and d["mime_type"]  # permitted fields remain


@pytest.mark.parametrize("role", [ROLE_ADMIN, ROLE_MANAGER])
def test_staff_documents_keep_file_path(env, role):
    for d in _doc_bodies(env, env["toks"][role]):
        assert d["file_path"] == env["doc_file"]


def test_customer_can_still_download_own_document(env):
    s, hdrs, body = _req(env["router"], "GET", f"{P}/documents/{env['doc'].id}/download", env["a_tok"])
    assert s == 200, body
    assert b"".join(body) == PAYLOAD
    assert "a.pdf" in hdrs["Content-Disposition"]


def test_other_customer_document_denied_and_no_download(env):
    r, a = env["router"], env["a_tok"]
    s, _, body = _req(r, "GET", f"{P}/documents/{env['bdoc'].id}", a)
    assert s == 403 and "b.pdf" not in json.dumps(body)
    s, _, body = _req(r, "GET", f"{P}/documents/{env['bdoc'].id}/download", a)
    assert s == 403
    s, _, body = _req(r, "GET", f"{P}/documents/{env['doc'].id}/download", env["b_tok"])
    assert s == 403


# ---- create paths, audit feed, milestone status audit (reviewer round 2) ----

from restoricon_core.auth import (  # noqa: E402
    PERM_READ_AUDIT_LOG, PERM_READ_OPERATIONS, PERM_WRITE_CONTRACTS, PERM_WRITE_ESTIMATES,
    PERM_WRITE_FINANCIALS, PERM_WRITE_OPERATIONS,
)

_GRANTS = {
    p: True for p in (
        PERM_READ_AUDIT_LOG, PERM_READ_OPERATIONS, PERM_WRITE_CONTRACTS, PERM_WRITE_ESTIMATES,
        PERM_WRITE_FINANCIALS, PERM_WRITE_OPERATIONS,
    )
}


def _call(router, method, path, tok, body=None):
    headers = {"authorization": f"Bearer {tok}"}
    s, _, b = router.handle_request(method, path, headers, json.dumps(body or {}).encode())
    return s, b


@pytest.fixture
def granted(env):
    """Customer A holding custom write/audit grants (customer role only)."""
    router = env["router"]
    auth = router.auth
    db = router.crm.db
    cust_id = db.get_connection().execute("SELECT id FROM customers WHERE email = 'A@t.com';").fetchone()["id"]
    u = auth.create_user(
        "cu_A_grant", "Passw0rd123!", "A", "agrant@t.com", role=ROLE_CUSTOMER,
        customer_id=cust_id, custom_permissions=_GRANTS,
    )
    env["g_tok"] = auth.create_token(u)
    env["cust_id"] = cust_id
    return env


def test_create_responses_hide_commission_rep_for_customer(granted):
    env = granted
    r, tok, cid = env["router"], env["g_tok"], env["cust_id"]
    for path, key, body in (
        (f"{P}/invoices", "invoice", {"customer_id": cid, "amount": 7.0}),
        (f"{P}/estimates", "estimate", {"customer_id": cid, "estimate_number": "EST-NEW"}),
        (f"{P}/contracts", "contract", {"customer_id": cid, "contract_number": "CN-NEW", "title": "C-NEW", "content": "x"}),
    ):
        s, b = _call(r, "POST", path, tok, body)
        assert s == 201, (path, b)
        obj = b[key]
        assert obj["assigned_user_id"] is None, path
    # positive control: staff create response still shows the rep (the actor)
    s, b = _call(r, "POST", f"{P}/invoices", env["toks"][ROLE_ADMIN], {"customer_id": cid, "amount": 8.0})
    assert s == 201, b
    # invoice rep defaults from customer; for contract/estimate it is the actor
    s, b = _call(r, "POST", f"{P}/contracts", env["toks"][ROLE_ADMIN], {"customer_id": cid, "contract_number": "CN-2", "title": "C2", "content": "x"})
    assert s == 201 and b["contract"]["assigned_user_id"] is not None
    s, b = _call(r, "POST", f"{P}/estimates", env["toks"][ROLE_ADMIN], {"customer_id": cid, "estimate_number": "EST-S"})
    assert s == 201 and b["estimate"]["assigned_user_id"] is not None
    # the stored rows keep the rep (output-only redaction)
    conn = r.crm.db.get_connection()
    row = conn.execute("SELECT assigned_user_id FROM contracts WHERE title = 'C-NEW';").fetchone()
    assert row["assigned_user_id"] is not None


def test_audit_feed_hides_internal_fields_for_customer_only(granted):
    env = granted
    r = env["router"]
    # generate audit rows carrying notes / rep id / file_path
    s, b = _call(r, "GET", f"{P}/audit-log?limit=1000", env["g_tok"])
    assert s == 200, b
    text = json.dumps(b)
    assert b["audit_logs"]  # non-vacuous
    for needle in (MNOTE, env["doc_file"], "assigned_user_id", "file_path", '"notes"'):
        assert needle not in text, needle
    s, a = _call(r, "GET", f"{P}/audit-log?limit=1000", env["toks"][ROLE_ADMIN])
    atext = json.dumps(a)
    assert MNOTE in atext and env["doc_file"] in atext and "assigned_user_id" in atext


def test_audit_feed_hides_invoice_notes_for_customer(granted):
    env = granted
    r = env["router"]
    r.crm.create_invoice(
        Invoice(customer_id=env["cust_id"], amount=3.0, notes="INV-NOTE-SECRET"),
        AuthContext(1, "x", ROLE_ADMIN, "human"),
    )
    s, b = _call(r, "GET", f"{P}/audit-log?entity_type=invoice", env["g_tok"])
    assert s == 200 and b["audit_logs"]
    assert "INV-NOTE-SECRET" not in json.dumps(b)
    s, a = _call(r, "GET", f"{P}/audit-log?entity_type=invoice", env["toks"][ROLE_ADMIN])
    assert "INV-NOTE-SECRET" in json.dumps(a)


def test_customer_milestone_status_change_audit_keeps_notes(granted):
    env = granted
    r = env["router"]
    s, b = _call(r, "POST", f"{P}/operations/milestones/{env['ms'].id}/status", env["g_tok"],
                 {"status": "in_progress", "notes": "NEW-MS-NOTE"})
    assert s == 200, b
    assert b["milestone"]["notes"] is None  # returned object redacted
    conn = r.crm.db.get_connection()
    row = conn.execute(
        "SELECT details_json FROM audit_log WHERE entity_type = 'milestone' AND action = 'status_change' "
        "AND entity_id = ?;", (env["ms"].id,)
    ).fetchone()
    assert "NEW-MS-NOTE" in row["details_json"]
    nrow = conn.execute("SELECT notes FROM project_milestones WHERE id = ?;", (env["ms"].id,)).fetchone()
    assert nrow["notes"] == "NEW-MS-NOTE"
    # status change without notes must not wipe stored notes
    s, b = _call(r, "POST", f"{P}/operations/milestones/{env['ms'].id}/status", env["g_tok"], {"status": "completed"})
    assert s == 200, b
    nrow = conn.execute("SELECT notes FROM project_milestones WHERE id = ?;", (env["ms"].id,)).fetchone()
    assert nrow["notes"] == "NEW-MS-NOTE"


def test_invoice_create_response_customer_null_staff_shows_rep(granted):
    """Kills the create_invoice mutant: customer response hides the rep, the
    staff response (rep defaulted from the customer's assignee) shows it."""
    env = granted
    r, cid = env["router"], env["cust_id"]
    conn = r.crm.db.get_connection()
    conn.execute("UPDATE customers SET assigned_user_id = ? WHERE id = ?;", (env["sales_id"], cid))
    conn.commit()
    s, b = _call(r, "POST", f"{P}/invoices", env["g_tok"], {"customer_id": cid, "amount": 4.0})
    assert s == 201, b
    assert b["invoice"]["assigned_user_id"] is None
    s, b = _call(r, "POST", f"{P}/invoices", env["toks"][ROLE_ADMIN], {"customer_id": cid, "amount": 5.0})
    assert s == 201, b
    assert b["invoice"]["assigned_user_id"] == env["sales_id"]


def test_milestone_status_audit_changed_fields_has_notes_diff(granted):
    """Kills the _before-from-redacted-get_milestone mutant: the stored audit
    diff must carry old=<real prior notes>, not None."""
    env = granted
    r = env["router"]
    s, b = _call(r, "POST", f"{P}/operations/milestones/{env['ms'].id}/status", env["g_tok"],
                 {"status": "in_progress", "notes": "NEW-MS-NOTE"})
    assert s == 200, b
    row = r.crm.db.get_connection().execute(
        "SELECT details_json FROM audit_log WHERE entity_type = 'milestone' AND action = 'status_change' "
        "AND entity_id = ?;", (env["ms"].id,)
    ).fetchone()
    details = json.loads(row["details_json"])
    assert details["changed_fields"]["notes"] == {"old": MNOTE, "new": "NEW-MS-NOTE"}


def test_audit_feed_customer_hides_assignee_summary_and_costs(granted):
    env = granted
    r = env["router"]
    admin = AuthContext(1, "x", ROLE_ADMIN, "human")
    items = [{"description": "d", "category": "materials", "quantity": 2, "unit_cost": 50.0},
             {"description": "l", "category": "labor", "quantity": 1, "unit_cost": 30.0}]
    est = r.crm.create_estimate(
        Estimate(customer_id=env["cust_id"], estimate_number="EST-COST", line_items=items), admin
    )
    # shape produced by estimate_service.unclaim/reassign audit entries
    from restoricon_core.services.audit_service import build_audit_details
    r.crm.audit.log(
        action="reassign", entity_type="estimate", entity_id=est.id,
        change_summary="Estimate reassigned to staff@restoricon.test (user 77)", actor=admin,
        details=build_audit_details(before={"assigned_to_user_id": 77}, after={"assigned_to_user_id": None}),
    )
    s, b = _call(r, "GET", f"{P}/audit-log?entity_type=estimate&limit=1000", env["g_tok"])
    assert s == 200 and b["audit_logs"], b
    text = json.dumps(b)
    for needle in ("assigned_to_user_id", "assigned_user_id", "materials_cost", "labor_cost",
                   "unit_cost", "staff@restoricon.test", "change_summary"):
        assert needle not in text, needle
    assert all("action" in e and "entity_type" in e for e in b["audit_logs"])  # envelope survives
    s, a = _call(r, "GET", f"{P}/audit-log?entity_type=estimate&limit=1000", env["toks"][ROLE_ADMIN])
    atext = json.dumps(a)
    for needle in ("assigned_to_user_id", "materials_cost", "labor_cost", "staff@restoricon.test", "change_summary"):
        assert needle in atext, needle


_B9_INTERNAL_KEYS = (
    "unit_cost_cents", "material_cost_cents", "labor_cost_rate_cents", "labor_bill_rate_cents",
    "equipment_cost_cents", "sub_cost_cents", "cost_total_cents", "sell_total_cents",
    "material_markup_bp", "sub_markup_bp", "equipment_markup_bp", "gross_margin_bp",
    "internal_note", "gross_profit_cents",
)


def _all_keys(value, out=None):
    out = set() if out is None else out
    if isinstance(value, dict):
        for k, v in value.items():
            out.add(k)
            _all_keys(v, out)
    elif isinstance(value, list):
        for v in value:
            _all_keys(v, out)
    return out


def test_audit_feed_b9_estimator_line_audits_hidden_for_customer(granted):
    """Real EstimateService.add_line/update_line/remove_line audit entries:
    no cost/markup/margin/internal key reaches a customer; admin sees them."""
    env = granted
    r = env["router"]
    svc = r.estimates
    admin = AuthContext(1, "x", ROLE_ADMIN, "human")
    header = svc.create(customer_id=env["cust_id"], actor=admin)
    line = svc.add_line(header.id, {
        "line_type": "material", "description": "Drywall", "customer_description": "Drywall",
        "quantity": 10, "unit": "SF", "unit_cost_cents": 1000, "package_qty": 1,
        "internal_note": "SECRET-LINE-NOTE",
    }, admin)
    svc.update_line(line.id, {"quantity": 12}, admin)
    svc.remove_line(line.id, admin)
    s, a = _call(r, "GET", f"{P}/audit-log?limit=1000", env["toks"][ROLE_ADMIN])
    admin_keys = _all_keys(a)
    seen = [k for k in _B9_INTERNAL_KEYS if k in admin_keys]
    assert len(seen) >= 5, seen  # non-vacuous: real line audits carry these keys
    s, b = _call(r, "GET", f"{P}/audit-log?limit=1000", env["g_tok"])
    assert s == 200 and b["audit_logs"]
    ckeys = _all_keys(b)
    for k in _B9_INTERNAL_KEYS:
        assert k not in ckeys, k
    assert "SECRET-LINE-NOTE" not in json.dumps(b)
    # envelope fields (incl. the entry's own `category`-free structure) survive
    assert all({"action", "entity_type", "entity_id"} <= set(e) for e in b["audit_logs"])


def test_audit_key_filter_keeps_visible_and_entry_fields():
    from restoricon_core.api.routes import _customer_audit_key_hidden as hidden
    for k in ("category", "total_cents", "line_total_cents", "price_override_cents", "tax_cents",
              "quantity", "description", "customer_description", "action", "entity_type", "details",
              "changed_fields", "status", "amount", "balance_due", "title"):
        assert not hidden(k), k
    for k in ("sell_total_cents", "gross_margin_bp", "internal_note", "labor_bill_rate_cents", "notes",
              "change_summary", "file_path", "assigned_to_user_id", "markup_percent", "override_reason"):
        assert hidden(k), k
