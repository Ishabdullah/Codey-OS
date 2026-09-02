"""
B6.2b-2: canonicalize the CRM service-layer *update* audit sites onto the
``build_audit_details`` envelope (before/after diff + side_effects + snapshot).

Covers all 11 mutation sites in crm_service.py:
update_customer, update_lead, update_opportunity, transition_opportunity_stage,
update_task, complete_task, update_project, sign_contract, record_payment,
update_subcontractor_qualification, update_subcontractor.

Real DatabaseManager / AuditService / CRMService, admin AuthContext, no mocks.
Payloads are read back through AuditService.query_logs(...).details, never the
AuditRecord returned by audit.log().
"""

import json

import pytest

from restoricon_core.auth import AuthService, ROLE_ADMIN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    Contract,
    Customer,
    Invoice,
    Lead,
    Opportunity,
    Project,
    Subcontractor,
    Task,
)
from restoricon_core.services.audit_service import AuditService, _AUDITABLE_PROJECT_FIELDS
from restoricon_core.services.crm_service import CRMService


SIG_BLOB = "SIGNATURE_BLOB_SENTINEL_b6_2b2_zzz"
LICENSE_SECRET = "LIC-SECRET-b6_2b2"
GL_SECRET = "GL-SECRET-b6_2b2"
WC_SECRET = "WC-SECRET-b6_2b2"


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    crm = CRMService(db, audit)
    admin = auth.create_user("admin_u", "AdminPass123!", "Admin U", "admin@r.com", role=ROLE_ADMIN)
    admin_ctx = auth.authenticate_token(auth.create_token(admin))
    cust = crm.create_customer(Customer(first_name="Parent", last_name="Co"), admin_ctx)
    return {
        "db": db, "audit": audit, "crm": crm, "admin": admin_ctx,
        "cust_id": cust.id,
    }


def _details(env, entity_type, entity_id, action):
    rows = env["audit"].query_logs(
        env["admin"], entity_type=entity_type, entity_id=entity_id, action=action, limit=50
    )
    assert rows, f"no audit row for {entity_type}/{entity_id}/{action}"
    return rows[0].details


def _rows(env, entity_type, entity_id, action=None):
    return env["audit"].query_logs(
        env["admin"], entity_type=entity_type, entity_id=entity_id, action=action, limit=50
    )


# ---------------------------------------------------------------------------
# 2.1 per-site: one field change -> exact changed_fields set + real value diff
# ---------------------------------------------------------------------------

def test_update_customer(env):
    crm, actor = env["crm"], env["admin"]
    c = crm.create_customer(Customer(first_name="Casey", last_name="Z", phone="111"), actor)
    crm.update_customer(c.id, {"phone": "222"}, actor)
    d = _details(env, "customer", c.id, "update")
    assert set(d["changed_fields"]) == {"phone"}
    assert d["changed_fields"]["phone"] == {"old": "111", "new": "222"}


def test_update_lead(env):
    crm, actor = env["crm"], env["admin"]
    lead = crm.create_lead(Lead(source="web", status="new", score_factors={}), actor)
    crm.update_lead(lead.id, {"status": "qualified"}, actor)
    d = _details(env, "lead", lead.id, "update")
    assert set(d["changed_fields"]) == {"status", "updated_at"}
    assert d["changed_fields"]["status"] == {"old": "new", "new": "qualified"}


def test_update_opportunity_simple_field(env):
    crm, actor = env["crm"], env["admin"]
    o = crm.create_opportunity(
        Opportunity(title="Opp A", pipeline_stage="new_lead", customer_id=env["cust_id"]), actor
    )
    crm.update_opportunity(o.id, {"title": "Opp B"}, actor)
    d = _details(env, "opportunity", o.id, "update")
    assert set(d["changed_fields"]) == {"title", "updated_at"}
    assert d["changed_fields"]["title"] == {"old": "Opp A", "new": "Opp B"}


def test_update_opportunity_pipeline_stage_delegates_single_log(env):
    """A pipeline_stage change routes to transition_opportunity_stage via an
    early return above update_opportunity's own audit.log -- exactly one row,
    action == stage_transition, never a plain 'update'."""
    crm, actor = env["crm"], env["admin"]
    o = crm.create_opportunity(
        Opportunity(title="Opp D", pipeline_stage="new_lead", customer_id=env["cust_id"]), actor
    )
    crm.update_opportunity(o.id, {"pipeline_stage": "contacted"}, actor)
    all_rows = _rows(env, "opportunity", o.id)
    mutate_rows = [r for r in all_rows if r.action in ("update", "stage_transition")]
    assert len(mutate_rows) == 1
    assert mutate_rows[0].action == "stage_transition"


def test_transition_opportunity_stage_diff_and_cadence_side_effect(env):
    crm, actor = env["crm"], env["admin"]
    o = crm.create_opportunity(
        Opportunity(title="Opp T", pipeline_stage="new_lead", customer_id=env["cust_id"]), actor
    )
    crm.transition_opportunity_stage(o.id, "contacted", actor)
    d = _details(env, "opportunity", o.id, "stage_transition")
    assert set(d["changed_fields"]) == {
        "pipeline_stage", "probability", "stage_entered_at", "updated_at"
    }
    assert d["changed_fields"]["pipeline_stage"] == {"old": "new_lead", "new": "contacted"}
    assert d["changed_fields"]["probability"]["old"] == 0.10
    assert d["changed_fields"]["probability"]["new"] == 0.20

    se = d["side_effects"]["cadence_task_created"]
    assert se["rule_name"] == "cadence_contacted"
    task_id = se["id"]
    # the cadence task carries its OWN create audit row (cross-ref, not double-log)
    task_creates = _rows(env, "task", task_id, "create")
    assert len(task_creates) == 1


def test_transition_opportunity_stage_notes_side_effect(env):
    crm, actor = env["crm"], env["admin"]
    o = crm.create_opportunity(
        Opportunity(title="Opp N", pipeline_stage="new_lead", customer_id=env["cust_id"]), actor
    )
    crm.transition_opportunity_stage(o.id, "contacted", actor, notes="call back Monday")
    d = _details(env, "opportunity", o.id, "stage_transition")
    assert d["side_effects"]["notes_appended"] == "call back Monday"


def test_update_task(env):
    crm, actor = env["crm"], env["admin"]
    t = crm.create_task(Task(title="T1", priority="medium"), actor)
    crm.update_task(t.id, {"priority": "high"}, actor)
    d = _details(env, "task", t.id, "update")
    assert set(d["changed_fields"]) == {"priority", "updated_at"}
    assert d["changed_fields"]["priority"] == {"old": "medium", "new": "high"}


def test_complete_task_no_notes(env):
    crm, actor = env["crm"], env["admin"]
    t = crm.create_task(Task(title="T2"), actor)
    crm.complete_task(t.id, actor)
    d = _details(env, "task", t.id, "complete")
    assert set(d["changed_fields"]) == {"status", "completed_at", "updated_at"}
    assert d["changed_fields"]["status"] == {"old": "pending", "new": "completed"}
    assert "side_effects" not in d


def test_complete_task_with_notes(env):
    crm, actor = env["crm"], env["admin"]
    t = crm.create_task(Task(title="T3"), actor)
    crm.complete_task(t.id, actor, notes="done on site")
    d = _details(env, "task", t.id, "complete")
    assert d["side_effects"]["notes_appended"] == "done on site"
    assert set(d["changed_fields"]) >= {"status", "completed_at", "updated_at"}


def test_update_project(env):
    crm, actor = env["crm"], env["admin"]
    p = crm.create_project(Project(title="P1", customer_id=env["cust_id"]), actor)
    crm.update_project(p.id, {"title": "P2"}, actor)
    d = _details(env, "project", p.id, "update")
    assert set(d["changed_fields"]) == {"title", "updated_at"}
    assert d["changed_fields"]["title"] == {"old": "P1", "new": "P2"}


def test_update_project_noop_writes_no_audit(env):
    crm, actor = env["crm"], env["admin"]
    p = crm.create_project(Project(title="P-noop", customer_id=env["cust_id"]), actor)
    crm.update_project(p.id, {"title": "P-noop", "project_type": p.project_type}, actor)
    assert _rows(env, "project", p.id, "update") == []


def test_sign_contract(env):
    crm, actor = env["crm"], env["admin"]
    k = crm.create_contract(
        Contract(contract_number="C-1", title="Ct", customer_id=env["cust_id"]), actor
    )
    crm.sign_contract(k.id, SIG_BLOB, actor)
    d = _details(env, "contract", k.id, "sign")
    assert set(d["changed_fields"]) == {"status", "customer_signed_at", "updated_at"}
    assert d["changed_fields"]["status"] == {"old": "draft", "new": "signed"}
    assert d["side_effects"] == {"signature_captured": True}
    assert SIG_BLOB not in json.dumps(d)


def test_record_payment_partial_then_full(env):
    crm, actor = env["crm"], env["admin"]
    inv = crm.create_invoice(
        Invoice(invoice_number="I-1", amount=1000.0, customer_id=env["cust_id"]), actor
    )
    crm.record_payment(inv.id, 400.0, "check", " REF-1", actor)
    d1 = _details(env, "invoice", inv.id, "pay")
    assert d1["side_effects"]["payment_recorded"]["new_balance"] == 600.0
    assert d1["changed_fields"]["balance_due"]["new"] == 600.0
    assert d1["changed_fields"]["balance_due"]["old"] != 600.0

    crm.record_payment(inv.id, 600.0, "check", "REF-2", actor)
    d2 = _details(env, "invoice", inv.id, "pay")
    assert d2["changed_fields"]["status"] == {"old": "partially_paid", "new": "paid"}
    assert d2["changed_fields"]["balance_due"]["new"] == 0.0


def test_update_subcontractor_qualification_snapshot(env):
    crm, actor = env["crm"], env["admin"]
    s = crm.create_subcontractor(Subcontractor(company_name="Sub Q"), actor)
    crm.update_subcontractor_qualification(s.id, "qualified", actor, recruitment_step="msa_sent")
    d = _details(env, "subcontractor", s.id, "status_change")
    assert set(d) == {"snapshot"}
    assert set(d["snapshot"]) == {"qualification_status", "recruitment_step"}
    assert d["snapshot"] == {"qualification_status": "qualified", "recruitment_step": "msa_sent"}


def test_update_subcontractor(env):
    crm, actor = env["crm"], env["admin"]
    s = crm.create_subcontractor(Subcontractor(company_name="Sub U", phone="111"), actor)
    crm.update_subcontractor(s.id, {"phone": "222"}, actor)
    d = _details(env, "subcontractor", s.id, "update")
    assert set(d["changed_fields"]) == {"phone", "updated_at", "last_contact_at"}
    assert d["changed_fields"]["phone"] == {"old": "111", "new": "222"}


# ---------------------------------------------------------------------------
# 2.2 phantom-diff regressions
# ---------------------------------------------------------------------------

def test_update_project_noncanonical_stage_not_a_phantom_diff(env):
    crm, actor = env["crm"], env["admin"]
    p = crm.create_project(Project(title="P-stage", customer_id=env["cust_id"]), actor)
    conn = env["db"].get_connection()
    with conn:
        conn.execute("UPDATE projects SET stage = 'Intake' WHERE id = ?;", (p.id,))
    crm.update_project(p.id, {"title": "P-stage-2"}, actor)
    d = _details(env, "project", p.id, "update")
    assert "stage" not in d["changed_fields"]
    assert set(d["changed_fields"]) == {"title", "updated_at"}


def test_update_customer_single_field_only(env):
    crm, actor = env["crm"], env["admin"]
    c = crm.create_customer(Customer(first_name="Ann", last_name="B", phone="111"), actor)
    crm.update_customer(c.id, {"phone": "999"}, actor)
    d = _details(env, "customer", c.id, "update")
    assert set(d["changed_fields"]) == {"phone"}


def test_update_subcontractor_json_col_parsed_not_stringified(env):
    crm, actor = env["crm"], env["admin"]
    s = crm.create_subcontractor(Subcontractor(company_name="Sub J", secondary_trades=[]), actor)
    crm.update_subcontractor(s.id, {"secondary_trades": ["roofing", "siding"]}, actor)
    d = _details(env, "subcontractor", s.id, "update")
    st = d["changed_fields"]["secondary_trades"]
    assert st["old"] == []
    assert st["new"] == ["roofing", "siding"]


# ---------------------------------------------------------------------------
# 2.3 after-image None-guard
# ---------------------------------------------------------------------------

def test_update_subcontractor_after_image_none_guard(env, monkeypatch):
    crm, actor = env["crm"], env["admin"]
    s = crm.create_subcontractor(Subcontractor(company_name="Sub G", phone="111"), actor)
    monkeypatch.setattr(crm, "get_subcontractor", lambda *a, **k: None)
    # must not raise even though the post-write re-read yields None
    crm.update_subcontractor(s.id, {"phone": "222"}, actor)
    assert _rows(env, "subcontractor", s.id, "update")


# ---------------------------------------------------------------------------
# 2.4 secret-leak sweep over every audit row this module wrote
# ---------------------------------------------------------------------------

def test_no_secret_leaks(env):
    crm, actor = env["crm"], env["admin"]

    k = crm.create_contract(
        Contract(contract_number="C-S", title="Ct", customer_id=env["cust_id"]), actor
    )
    crm.sign_contract(k.id, SIG_BLOB, actor)

    s = crm.create_subcontractor(
        Subcontractor(
            company_name="Sub S", license_number=LICENSE_SECRET,
            general_liability=GL_SECRET, workers_comp=WC_SECRET,
        ),
        actor,
    )
    crm.update_subcontractor(s.id, {"license_number": LICENSE_SECRET + "-x"}, actor)

    conn = env["db"].get_connection()
    raws = [r["details_json"] for r in conn.execute("SELECT details_json FROM audit_log").fetchall()]
    assert raws
    for raw in raws:
        assert SIG_BLOB not in raw
        assert LICENSE_SECRET not in raw
        assert GL_SECRET not in raw
        assert WC_SECRET not in raw
        assert "customer_signature_data" not in raw


# ---------------------------------------------------------------------------
# 2.5 drift guard
# ---------------------------------------------------------------------------

def test_auditable_project_fields_matches_dataclass():
    from dataclasses import fields as dc_fields
    from restoricon_core.models import Project

    assert _AUDITABLE_PROJECT_FIELDS == frozenset(f.name for f in dc_fields(Project))
