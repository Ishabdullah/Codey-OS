"""Sales Rep Portal name-enrichment fix: Ish reported leads/opportunities
tables and forms showed raw customer/rep ids ("Cust #3", a bare rep
number) instead of names, in both display tables and the New Lead create
form. This covers the server-side response-shape change (new
`customer_name`/`assigned_user_name` keys on GET /api/v1/leads,
GET /api/v1/leads/{id}, GET /api/v1/opportunities -- attached alongside
the existing customer_id/assigned_user_id keys, which stay for other
consumers) plus CRMService._get_customer_display_name, the new ungated
helper backing it.

/api/v1/sales/dashboard's team_commission_rankings rep_user_name key is
covered separately in test_b8_2a_sales_dashboard.py, alongside its
existing rankings coverage.
"""

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import AuthContext, AuthService, ROLE_ADMIN, ROLE_SALES
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, Lead, Opportunity
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.scheduling_service import SchedulingService


@pytest.fixture
def env():
    db = DatabaseManager(":memory:")
    auth = AuthService(db)
    audit = AuditService(db)
    comm = CommunicationService(db)
    crm = CRMService(db, audit)
    sched = SchedulingService(db, audit)
    auto = AutomationService(db, audit)
    router = APIRouter(auth, crm, comm, audit, sched, auto)

    admin_user = auth.create_user("admin_user", "Pass123!", "Admin User", "admin@test.com", ROLE_ADMIN)
    admin_actor = AuthContext(admin_user.id, "admin_user", ROLE_ADMIN, "human")
    rep_user = auth.create_user("rep_user", "Pass123!", "Sales Rep", "rep@test.com", ROLE_SALES)
    rep_token = auth.create_token(rep_user)

    cust = crm.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin_actor
    )
    biz_cust = crm.create_customer(
        Customer(first_name="", last_name="", company_name="Acme Roofing", email="acme@test.com"),
        admin_actor,
    )

    lead = crm.create_lead(
        Lead(customer_id=cust.id, status="new", assigned_user_id=rep_user.id), admin_actor
    )
    unlinked_lead = crm.create_lead(Lead(status="new"), admin_actor)
    opp = crm.create_opportunity(
        Opportunity(customer_id=cust.id, title="Roof Job", assigned_user_id=rep_user.id),
        admin_actor,
    )

    return {
        "router": router,
        "admin_token": auth.create_token(admin_user),
        "rep_token": rep_token,
        "rep_user": rep_user,
        "cust": cust,
        "biz_cust": biz_cust,
        "lead": lead,
        "unlinked_lead": unlinked_lead,
        "opp": opp,
        "crm": crm,
    }


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_list_leads_includes_customer_and_assigned_user_names(env):
    status, _, data = env["router"].handle_request(
        "GET", "/api/v1/leads", _headers(env["admin_token"]), b""
    )
    assert status == 200
    by_id = {l["id"]: l for l in data["leads"]}
    linked = by_id[env["lead"].id]
    assert linked["customer_id"] == env["cust"].id, "existing customer_id key must not be removed"
    assert linked["assigned_user_id"] == env["rep_user"].id, "existing assigned_user_id key must not be removed"
    assert linked["customer_name"] == "Jane Doe"
    assert linked["assigned_user_name"] == "Sales Rep"

    unlinked = by_id[env["unlinked_lead"].id]
    assert unlinked["customer_id"] is None
    assert unlinked["customer_name"] is None
    assert unlinked["assigned_user_id"] is None
    assert unlinked["assigned_user_name"] is None


def test_get_single_lead_includes_names(env):
    status, _, data = env["router"].handle_request(
        "GET", f"/api/v1/leads/{env['lead'].id}", _headers(env["admin_token"]), b""
    )
    assert status == 200
    lead = data["lead"]
    assert lead["customer_id"] == env["cust"].id
    assert lead["customer_name"] == "Jane Doe"
    assert lead["assigned_user_id"] == env["rep_user"].id
    assert lead["assigned_user_name"] == "Sales Rep"


def test_list_opportunities_includes_assigned_user_name(env):
    """Per spec, only assigned_user_name is enriched here -- the
    opportunities table in the sales portal has no customer column to
    consume a customer_name key, so none is added (an unconsumed response
    key beyond what was asked for). NOTE: opportunities.customer_id is
    actually a real, NOT NULL column (database.py) -- contrary to the
    architect's spec assumption, verified directly here rather than taken
    on faith -- so customer_id itself is still present and unchanged."""
    status, _, data = env["router"].handle_request(
        "GET", "/api/v1/opportunities", _headers(env["admin_token"]), b""
    )
    assert status == 200
    by_id = {o["id"]: o for o in data["opportunities"]}
    opp = by_id[env["opp"].id]
    assert opp["customer_id"] == env["cust"].id, "existing customer_id key must not be removed"
    assert "customer_name" not in opp
    assert opp["assigned_user_id"] == env["rep_user"].id
    assert opp["assigned_user_name"] == "Sales Rep"


def test_get_customer_display_name_business_customer_falls_back_to_company_name(env):
    """CRMService._get_customer_display_name: a business customer with
    blank first/last name resolves to company_name, not a blank string."""
    assert env["crm"]._get_customer_display_name(env["biz_cust"].id) == "Acme Roofing"


def test_get_customer_display_name_nonexistent_id_returns_none(env):
    assert env["crm"]._get_customer_display_name(999999) is None


def test_communications_center_includes_customer_name(env):
    """Communications Center panel showed the same raw 'Cust #id' symptom
    Ish reported -- a separate endpoint from /api/v1/leads, so it needs
    its own server-side enrichment rather than inheriting the leads
    route's (per the architect's own note to check this, rather than
    assume)."""
    env["router"].comm.record_communication(
        channel="email", direction="outbound", content="hi",
        actor=AuthContext(env["rep_user"].id, "rep_user", ROLE_SALES, "human"),
        customer_id=env["cust"].id,
    )
    status, _, data = env["router"].handle_request(
        "GET", "/api/v1/sales/communications-center", _headers(env["rep_token"]), b""
    )
    assert status == 200
    comms = data["communications"]
    assert len(comms) == 1
    assert comms[0]["customer_id"] == env["cust"].id, "existing customer_id key must not be removed"
    assert comms[0]["customer_name"] == "Jane Doe"


def test_get_customer_display_name_is_ungated_unlike_get_customer(env):
    """A rep who does NOT own this customer (assigned_user_id mismatch)
    would get None back from get_customer's NEW-568 narrowing -- but
    _get_customer_display_name has no actor param at all and must still
    resolve the name, since this is the whole point of the fix (a lead's
    assigned_user_id can diverge from its linked customer's)."""
    assert env["crm"]._get_customer_display_name(env["cust"].id) == "Jane Doe"
