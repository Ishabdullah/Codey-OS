"""
B6.2b-1: mechanical create/delete audit-detail canonicalization.

Verifies the 25 enumerated pure create/delete service-layer audit sites
(spec headline says "26"; the spec body enumerates 25 -- 22 creates + 3
deletes -- and the enumeration is authoritative) now emit the canonical
``build_audit_details`` envelope:

* creates  -> top-level ``changed_fields`` with ``{"old": None, "new": v}``
* deletes  -> top-level ``snapshot``
* ``record_transaction`` -> ``side_effects`` only when a project actual_cost
  delta was applied
* the four NEW-314 allow-list creates (contract / invoice / subcontractor /
  employee) drop their excluded sensitive fields from ``changed_fields``

Plus a secret-leak sweep over every audit row written by all 25 ops.

Note: ``license_number`` is deliberately NOT sweep-forbidden -- it is a
legitimate payload field for ``create_compliance_item`` and the
``delete_contact`` snapshot. It is still allow-list-excluded from the
Subcontractor diff domain.

Real DatabaseManager / AuditService / services, admin AuthContext. No mocks.
"""

import pytest

from restoricon_core.auth import AuthService, ROLE_ADMIN
from restoricon_core.database import DatabaseManager
from restoricon_core.models import (
    Appointment,
    AutomationRule,
    ComplianceItem,
    Contact,
    Contract,
    Customer,
    Document,
    Employee,
    Equipment,
    Estimate,
    FinancialTransaction,
    Invoice,
    Lead,
    MarketingCampaign,
    Opportunity,
    Project,
    ProjectMilestone,
    PurchaseOrder,
    Subcontractor,
    Task,
    Vendor,
    WorkOrder,
)
from restoricon_core.services.audit_service import (
    AuditService,
    build_audit_details,
    _AUDITABLE_EMPLOYEE_FIELDS,
)
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.business_ops_service import BusinessOpsService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.finance_service import FinanceService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService


SIG_SENTINEL = "SIGNATURE_BLOB_SENTINEL_zzz"
PAY_SENTINEL = "PAYMENT_SENTINEL_zzz"


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    crm = CRMService(db, audit)
    ops = OperationsService(db, audit)
    biz = BusinessOpsService(db, audit)
    auto = AutomationService(db, audit)
    sched = SchedulingService(db, audit)
    fin = FinanceService(db, audit)
    admin = auth.create_user("admin_u", "AdminPass123!", "Admin U", "admin@r.com", role=ROLE_ADMIN)
    admin_token = auth.create_token(admin)
    admin_ctx = auth.authenticate_token(admin_token)

    # Real parent rows for FK-constrained child creates.
    parent_customer = crm.create_customer(Customer(first_name="Parent", last_name="Co"), admin_ctx)
    parent_project = crm.create_project(
        Project(title="Parent Project", customer_id=parent_customer.id), admin_ctx
    )
    parent_vendor = biz.create_vendor(Vendor(company_name="Parent Vendor Inc"), admin_ctx)
    return {
        "db": db, "audit": audit, "crm": crm, "ops": ops, "biz": biz,
        "auto": auto, "sched": sched, "fin": fin, "admin_ctx": admin_ctx,
        "cust_id": parent_customer.id, "proj_id": parent_project.id,
        "vend_id": parent_vendor.id,
    }


# ---------------------------------------------------------------------------
# Per-site builders: each performs the minimal create/delete and returns
# (entity_id, identifying_field, identifying_value). entity_id may be None
# (remove_from_do_not_contact logs entity_id=None).
# ---------------------------------------------------------------------------

def _b_customer(e):
    o = e["crm"].create_customer(Customer(first_name="Casey", last_name="Zoolander"), e["admin_ctx"])
    return o.id, "first_name", "Casey"

def _b_lead(e):
    o = e["crm"].create_lead(Lead(source="web_form_zzz"), e["admin_ctx"])
    return o.id, "source", "web_form_zzz"

def _b_opportunity(e):
    o = e["crm"].create_opportunity(Opportunity(title="Opp Zzz", pipeline_stage="qualification", customer_id=e["cust_id"]), e["admin_ctx"])
    return o.id, "title", "Opp Zzz"

def _b_task(e):
    o = e["crm"].create_task(Task(title="Task Zzz"), e["admin_ctx"])
    return o.id, "title", "Task Zzz"

def _b_project(e):
    o = e["crm"].create_project(Project(title="Project Zzz", customer_id=e["cust_id"]), e["admin_ctx"])
    return o.id, "title", "Project Zzz"

def _b_estimate(e):
    o = e["crm"].create_estimate(Estimate(estimate_number="EST-ZZZ", total_amount=100.0, customer_id=e["cust_id"]), e["admin_ctx"])
    return o.id, "estimate_number", "EST-ZZZ"

def _b_contract(e):
    o = e["crm"].create_contract(
        Contract(
            contract_number="CON-ZZZ", title="Contract Zzz", customer_id=e["cust_id"],
            customer_signature_data=SIG_SENTINEL, content="secret contract body",
        ),
        e["admin_ctx"],
    )
    return o.id, "contract_number", "CON-ZZZ"

def _b_invoice(e):
    o = e["crm"].create_invoice(
        Invoice(invoice_number="INV-ZZZ", amount=250.0, customer_id=e["cust_id"], payments=[{"note": PAY_SENTINEL}]),
        e["admin_ctx"],
    )
    return o.id, "invoice_number", "INV-ZZZ"

def _b_document(e):
    o = e["crm"].create_document(Document(title="Doc Zzz", document_type="pdf"), e["admin_ctx"])
    return o.id, "title", "Doc Zzz"

def _b_subcontractor(e):
    o = e["crm"].create_subcontractor(
        Subcontractor(
            company_name="Sub Zzz LLC", license_number="LIC-SECRET-999",
            general_liability="GL-SECRET", workers_comp="WC-SECRET",
        ),
        e["admin_ctx"],
    )
    return o.id, "company_name", "Sub Zzz LLC"

def _b_contact(e):
    o = e["crm"].create_contact(Contact(name="Contact Zzz", external_id="ext_zzz_1"), e["admin_ctx"])
    return o.id, "name", "Contact Zzz"

def _b_milestone(e):
    o = e["ops"].create_milestone(ProjectMilestone(name="Milestone Zzz", project_id=e["proj_id"]), e["admin_ctx"])
    return o.id, "name", "Milestone Zzz"

def _b_work_order(e):
    o = e["ops"].create_work_order(
        WorkOrder(work_order_number="WO-ZZZ", title="WO Zzz", trade="plumbing", project_id=e["proj_id"]), e["admin_ctx"]
    )
    return o.id, "title", "WO Zzz"

def _b_equipment(e):
    o = e["ops"].create_equipment(Equipment(asset_tag="AT-ZZZ", name="Equip Zzz"), e["admin_ctx"])
    return o.id, "name", "Equip Zzz"

def _b_campaign(e):
    o = e["biz"].create_campaign(MarketingCampaign(name="Campaign Zzz", channel="email_blast"), e["admin_ctx"])
    return o.id, "name", "Campaign Zzz"

def _b_compliance_item(e):
    o = e["biz"].create_compliance_item(
        ComplianceItem(title="Compliance Zzz", expiration_date="2030-01-01", license_number="CL-12345"),
        e["admin_ctx"],
    )
    return o.id, "title", "Compliance Zzz"

def _b_employee(e):
    o = e["biz"].create_employee(
        Employee(
            first_name="Emp", last_name="Zzz", role_title="Estimator",
            hourly_rate=99.0, emergency_contact="Mom 555-0000",
        ),
        e["admin_ctx"],
    )
    return o.id, "first_name", "Emp"

def _b_vendor(e):
    o = e["biz"].create_vendor(Vendor(company_name="Vendor Zzz Inc"), e["admin_ctx"])
    return o.id, "company_name", "Vendor Zzz Inc"

def _b_purchase_order(e):
    o = e["biz"].create_purchase_order(
        PurchaseOrder(po_number="PO-ZZZ", total_amount=500.0, ordered_date="2026-01-01", vendor_id=e["vend_id"]), e["admin_ctx"]
    )
    return o.id, "po_number", "PO-ZZZ"

def _b_rule(e):
    o = e["auto"].create_rule(
        AutomationRule(channel="email", description="Rule Zzz", condition_type="from_contains",
                       condition_value="zzz@x.com", action="flag"),
        e["admin_ctx"],
    )
    return o.id, "description", "Rule Zzz"

def _b_appointment(e):
    o = e["sched"].create_appointment(Appointment(title="Appt Zzz", status="negotiating"), e["admin_ctx"])
    return o.id, "title", "Appt Zzz"

def _b_txn_with_cost(e):
    o = e["fin"].record_transaction(
        FinancialTransaction(
            transaction_number="TXN-COST-ZZZ", transaction_type="vendor_expense",
            amount=123.45, project_id=e["proj_id"],
        ),
        e["admin_ctx"],
    )
    return o.id, "transaction_number", "TXN-COST-ZZZ"

def _b_txn_no_cost(e):
    o = e["fin"].record_transaction(
        FinancialTransaction(
            transaction_number="TXN-NOCOST-ZZZ", transaction_type="payment_received",
            amount=67.89,
        ),
        e["admin_ctx"],
    )
    return o.id, "transaction_number", "TXN-NOCOST-ZZZ"

def _b_delete_contact(e):
    o = e["crm"].create_contact(Contact(name="DelContact Zzz", external_id="ext_del_1"), e["admin_ctx"])
    assert e["crm"].delete_contact(o.id, e["admin_ctx"]) is True
    return o.id, None, None

def _b_delete_rule(e):
    o = e["auto"].create_rule(
        AutomationRule(channel="sms", description="DelRule Zzz", condition_type="from_contains",
                       condition_value="del@x.com", action="flag"),
        e["admin_ctx"],
    )
    assert e["auto"].delete_rule(o.id, e["admin_ctx"]) is True
    return o.id, None, None

def _b_remove_dnc(e):
    e["auto"].add_to_do_not_contact("dnczzz@example.com", e["admin_ctx"], reason="test")
    assert e["auto"].remove_from_do_not_contact("dnczzz@example.com", e["admin_ctx"]) is True
    return None, None, None


CREATE_SITES = [
    ("customer", _b_customer),
    ("lead", _b_lead),
    ("opportunity", _b_opportunity),
    ("task", _b_task),
    ("project", _b_project),
    ("estimate", _b_estimate),
    ("contract", _b_contract),
    ("invoice", _b_invoice),
    ("document", _b_document),
    ("subcontractor", _b_subcontractor),
    ("contact", _b_contact),
    ("milestone", _b_milestone),
    ("work_order", _b_work_order),
    ("equipment", _b_equipment),
    ("marketing_campaign", _b_campaign),
    ("compliance_item", _b_compliance_item),
    ("employee", _b_employee),
    ("vendor", _b_vendor),
    ("purchase_order", _b_purchase_order),
    ("automation_rule", _b_rule),
    ("appointment", _b_appointment),
    ("financial_transaction", _b_txn_with_cost),
    ("financial_transaction", _b_txn_no_cost),
]

DELETE_SITES = [
    ("contact", "delete", _b_delete_contact),
    ("automation_rule", "delete", _b_delete_rule),
    ("do_not_contact", "delete", _b_remove_dnc),
]

ALL_SITES = (
    [(t, "create", fn) for t, fn in CREATE_SITES] + list(DELETE_SITES)
)


def _query(env, entity_type, entity_id, action):
    rows = env["audit"].query_logs(
        env["admin_ctx"], entity_type=entity_type, action=action, limit=200
    )
    if entity_id is not None:
        rows = [r for r in rows if r.entity_id == entity_id]
    return rows


# ---------------------------------------------------------------------------
# 7a. one parametrized test over all 25 sites
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "entity_type,action,builder",
    ALL_SITES,
    ids=[f"{t}-{a}-{fn.__name__}" for t, a, fn in ALL_SITES],
)
def test_site_emits_canonical_envelope(env, entity_type, action, builder):
    entity_id, id_field, id_value = builder(env)
    rows = _query(env, entity_type, entity_id, action)
    assert rows, f"no audit row for {entity_type}/{action}"
    details = rows[0].details

    if action == "create":
        assert "changed_fields" in details
        assert details["changed_fields"][id_field] == {"old": None, "new": id_value}

        if builder is _b_txn_with_cost:
            assert details["side_effects"]["project_actual_cost_delta"] == {
                "project_id": env["proj_id"], "amount": 123.45
            }
        elif builder is _b_txn_no_cost:
            assert "side_effects" not in details

        if builder is _b_contract:
            assert "customer_signature_data" not in details["changed_fields"]
            assert "content" not in details["changed_fields"]
            assert "contract_number" in details["changed_fields"]
        elif builder is _b_invoice:
            assert "payments" not in details["changed_fields"]
            assert "invoice_number" in details["changed_fields"]
        elif builder is _b_subcontractor:
            assert "license_number" not in details["changed_fields"]
            assert "general_liability" not in details["changed_fields"]
            assert "company_name" in details["changed_fields"]
        elif builder is _b_employee:
            assert "hourly_rate" not in details["changed_fields"]
            assert "emergency_contact" not in details["changed_fields"]
            assert "first_name" in details["changed_fields"]
    else:
        assert "snapshot" in details
        assert "changed_fields" not in details


# ---------------------------------------------------------------------------
# 7b. secret-leak sweep across every audit row from all 25 ops
# ---------------------------------------------------------------------------

def test_no_secret_leaks_across_all_sites(env):
    for _t, _a, builder in ALL_SITES:
        builder(env)

    conn = env["db"].get_connection()
    raws = [r["details_json"] for r in conn.execute("SELECT details_json FROM audit_log").fetchall()]
    assert raws
    for raw in raws:
        assert raw is not None
        assert SIG_SENTINEL not in raw
        assert PAY_SENTINEL not in raw
        assert "hourly_rate" not in raw
        assert "emergency_contact" not in raw
        low = raw.lower()
        assert "password" not in low
        assert "secret" not in low
        assert "token" not in low


# ---------------------------------------------------------------------------
# 7c. helper unit test: fields= filters changed_fields for the before=None case
# ---------------------------------------------------------------------------

def test_helper_fields_filter_before_none():
    d = {"first_name": "A", "hourly_rate": 99.0, "emergency_contact": "x", "role_title": "R"}
    out = build_audit_details(after=d, fields=_AUDITABLE_EMPLOYEE_FIELDS)
    assert set(out["changed_fields"]) == {"first_name", "role_title"}
    assert out["changed_fields"]["first_name"] == {"old": None, "new": "A"}
