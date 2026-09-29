"""
Unit/route tests for B8.6d-c: the guided customer->template->fill->sign UI's
backend pieces (NEW-579).

Covers:
  - customer_number generation (create_customer): sequential, collision-free
    under the single-statement INSERT...SELECT approach, across several
    rapid creates.
  - The customer_number backfill (DatabaseManager._backfill_customer_numbers):
    idempotent, ordered by (created_at, id), leaves already-numbered rows
    alone.
  - The new POST /api/v1/contracts/<id>/signers route, including the
    NEW-597 duplicate-party_role guard and the NEW-593 actor/party_role
    identity-validation check.
  - Contract.template_name round-trips through create_contract/
    update_contract against the fixed CONTRACT_TEMPLATE_NAMES set.
"""

from __future__ import annotations

import json

import pytest

from restoricon_core.api.routes import APIRouter
from restoricon_core.auth import (
    AuthContext,
    AuthService,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_PROJECT_MANAGER,
    ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import CONTRACT_TEMPLATE_NAMES, Contract, Customer
from restoricon_core.services.analytics_search_service import AnalyticsSearchService
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.automation_service import AutomationService
from restoricon_core.services.business_ops_service import BusinessOpsService
from restoricon_core.services.communication_service import CommunicationService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.finance_service import FinanceService
from restoricon_core.services.operations_service import OperationsService
from restoricon_core.services.scheduling_service import SchedulingService


# ---------------------------------------------------------------------------
# Service-layer fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def crm_env():
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    crm = CRMService(db, audit)
    auth = AuthService(db)

    admin_u = auth.create_user(
        "gflow_admin", "Password123", "Admin", "gflow_admin@test.com", ROLE_ADMIN
    )
    actor_admin = AuthContext(user_id=admin_u.id, username="gflow_admin", role=ROLE_ADMIN, actor_type="human")

    cust = crm.create_customer(
        Customer(first_name="Guided", last_name="Flow", email="gflow_cust@test.com"), actor_admin
    )
    cust_u = auth.create_user(
        "gflow_cust", "Password123", "Guided Flow", "gflow_cust_login@test.com",
        ROLE_CUSTOMER, customer_id=cust.id,
    )
    actor_customer = AuthContext(
        user_id=cust_u.id, username="gflow_cust", role=ROLE_CUSTOMER, actor_type="human", customer_id=cust.id,
    )

    sales_u = auth.create_user(
        "gflow_sales", "Password123", "Sales Rep", "gflow_sales@test.com", ROLE_SALES
    )
    actor_sales = AuthContext(user_id=sales_u.id, username="gflow_sales", role=ROLE_SALES, actor_type="human")

    pm_u = auth.create_user(
        "gflow_pm", "Password123", "PM", "gflow_pm@test.com", ROLE_PROJECT_MANAGER
    )
    actor_pm = AuthContext(user_id=pm_u.id, username="gflow_pm", role=ROLE_PROJECT_MANAGER, actor_type="human")

    return {
        "db": db, "crm": crm, "auth": auth,
        "admin": actor_admin, "cust": cust, "actor_customer": actor_customer,
        "actor_sales": actor_sales, "actor_pm": actor_pm,
    }


def _make_contract(env, number, template_name=None, assigned_actor=None):
    actor = assigned_actor or env["admin"]
    return env["crm"].create_contract(
        Contract(
            contract_number=number,
            customer_id=env["cust"].id,
            title="Guided Flow Contract",
            content="Terms...",
            template_name=template_name,
        ),
        actor,
    )


# ---------------------------------------------------------------------------
# customer_number generation
# ---------------------------------------------------------------------------

def test_create_customer_assigns_sequential_customer_numbers(crm_env):
    crm = crm_env["crm"]
    admin = crm_env["admin"]
    created = [
        crm.create_customer(Customer(first_name=f"C{i}", last_name="Num"), admin)
        for i in range(6)
    ]
    numbers = [c.customer_number for c in created]
    assert all(n is not None for n in numbers)
    assert numbers == sorted(numbers)
    assert len(set(numbers)) == len(numbers)
    # crm_env's own fixture customer was created first, so numbering
    # continues from it rather than restarting at 1.
    assert numbers[0] == crm_env["cust"].customer_number + 1


def test_create_customer_customer_number_round_trips_via_get(crm_env):
    crm = crm_env["crm"]
    admin = crm_env["admin"]
    created = crm.create_customer(Customer(first_name="Round", last_name="Trip"), admin)
    fetched = crm.get_customer(created.id, admin)
    assert fetched.customer_number == created.customer_number


# ---------------------------------------------------------------------------
# customer_number backfill
# ---------------------------------------------------------------------------

def test_backfill_customer_numbers_orders_by_created_at_then_id():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    # Two rows sharing a created_at (tiebreaker must be id) and one later.
    conn.execute(
        "INSERT INTO customers (id, first_name, last_name, created_at) "
        "VALUES (2, 'B', 'B', '2020-01-01T00:00:00Z');"
    )
    conn.execute(
        "INSERT INTO customers (id, first_name, last_name, created_at) "
        "VALUES (1, 'A', 'A', '2020-01-01T00:00:00Z');"
    )
    conn.execute(
        "INSERT INTO customers (id, first_name, last_name, created_at) "
        "VALUES (3, 'C', 'C', '2020-01-02T00:00:00Z');"
    )
    db._backfill_customer_numbers(conn)
    conn.commit()
    rows = {
        r["id"]: r["customer_number"]
        for r in conn.execute("SELECT id, customer_number FROM customers;")
    }
    # id=1 and id=2 tie on created_at -> id tiebreaker means id=1 gets the
    # lower number.
    assert rows[1] < rows[2] < rows[3]
    assert sorted(rows.values()) == [1, 2, 3]


def test_backfill_customer_numbers_is_idempotent_and_skips_numbered_rows():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO customers (id, first_name, last_name, created_at, customer_number) "
        "VALUES (1, 'A', 'A', '2020-01-01T00:00:00Z', 99);"
    )
    conn.execute(
        "INSERT INTO customers (id, first_name, last_name, created_at) "
        "VALUES (2, 'B', 'B', '2020-01-02T00:00:00Z');"
    )
    db._backfill_customer_numbers(conn)
    conn.commit()
    rows = {
        r["id"]: r["customer_number"]
        for r in conn.execute("SELECT id, customer_number FROM customers;")
    }
    assert rows[1] == 99  # untouched
    assert rows[2] == 100  # continues from existing MAX, not from 1

    # Re-running is a no-op.
    db._backfill_customer_numbers(conn)
    conn.commit()
    rows_again = {
        r["id"]: r["customer_number"]
        for r in conn.execute("SELECT id, customer_number FROM customers;")
    }
    assert rows_again == rows


# ---------------------------------------------------------------------------
# add_contract_signers: NEW-597 duplicate-party_role guard
# ---------------------------------------------------------------------------

def test_add_contract_signers_skips_duplicate_party_role_within_one_call(crm_env):
    crm = crm_env["crm"]
    contract = _make_contract(crm_env, "CTR-GFLOW-DUP-1")
    created = crm.add_contract_signers(
        contract.id,
        [{"party_role": "customer"}, {"party_role": "customer"}],
        crm_env["admin"],
    )
    assert len(created) == 1
    rows = crm.db.get_connection().execute(
        "SELECT COUNT(*) AS c FROM contract_signers WHERE contract_id = ? AND party_role = 'customer';",
        (contract.id,),
    ).fetchone()["c"]
    assert rows == 1


def test_add_contract_signers_skips_duplicate_party_role_across_calls(crm_env):
    crm = crm_env["crm"]
    contract = _make_contract(crm_env, "CTR-GFLOW-DUP-2")
    first = crm.add_contract_signers(contract.id, [{"party_role": "customer"}], crm_env["admin"])
    second = crm.add_contract_signers(contract.id, [{"party_role": "customer"}], crm_env["admin"])
    assert len(first) == 1
    assert len(second) == 0  # silently skipped, not an error
    rows = crm.db.get_connection().execute(
        "SELECT COUNT(*) AS c FROM contract_signers WHERE contract_id = ? AND party_role = 'customer';",
        (contract.id,),
    ).fetchone()["c"]
    assert rows == 1


# ---------------------------------------------------------------------------
# sign_contract: NEW-593 actor/party_role identity validation
# ---------------------------------------------------------------------------

def test_sign_contract_rejects_mismatched_party_role(crm_env):
    crm = crm_env["crm"]
    contract = _make_contract(crm_env, "CTR-GFLOW-593-1")
    crm.add_contract_signers(
        contract.id,
        [{"party_role": "customer"}, {"party_role": "project_manager"}],
        crm_env["admin"],
    )
    # actor_sales's derived party_role is 'rep', not 'customer' -- claiming
    # to sign as 'customer' must be rejected.
    with pytest.raises(PermissionError):
        crm.sign_contract(
            contract.id, "sig-data", crm_env["actor_sales"], party_role="customer"
        )


def test_sign_contract_accepts_matching_party_role(crm_env):
    crm = crm_env["crm"]
    contract = _make_contract(crm_env, "CTR-GFLOW-593-2")
    crm.add_contract_signers(
        contract.id,
        [{"party_role": "customer"}, {"party_role": "project_manager"}],
        crm_env["admin"],
    )
    signed = crm.sign_contract(
        contract.id, "sig-data", crm_env["actor_customer"], party_role="customer"
    )
    assert signed.status != "signed"  # PM hasn't signed yet


# ---------------------------------------------------------------------------
# template_name
# ---------------------------------------------------------------------------

def test_create_contract_accepts_legal_template_name(crm_env):
    contract = _make_contract(crm_env, "CTR-GFLOW-TPL-1", template_name="homecare_plus")
    assert contract.template_name == "homecare_plus"
    fetched = crm_env["crm"].get_contract(contract.id, crm_env["admin"])
    assert fetched.template_name == "homecare_plus"


def test_create_contract_rejects_illegal_template_name(crm_env):
    with pytest.raises(ValueError):
        _make_contract(crm_env, "CTR-GFLOW-TPL-2", template_name="good")  # PackageOption tier, not legal here


def test_update_contract_template_name_round_trips(crm_env):
    crm = crm_env["crm"]
    contract = _make_contract(crm_env, "CTR-GFLOW-TPL-3")
    updated = crm.update_contract(contract.id, {"template_name": "homecare_estate"}, crm_env["admin"])
    assert updated.template_name == "homecare_estate"
    with pytest.raises(ValueError):
        crm.update_contract(contract.id, {"template_name": "not_a_real_template"}, crm_env["admin"])


def test_contract_template_names_covers_general_and_homecare_tiers():
    assert "general_remodeling" in CONTRACT_TEMPLATE_NAMES
    for tier in ("basic", "plus", "complete", "estate"):
        assert f"homecare_{tier}" in CONTRACT_TEMPLATE_NAMES


# ---------------------------------------------------------------------------
# Route-level: POST /api/v1/contracts/<id>/signers
# ---------------------------------------------------------------------------

@pytest.fixture
def api_setup():
    db = DatabaseManager(":memory:")
    audit = AuditService(db)
    auth = AuthService(db)
    crm = CRMService(db, audit)
    comm = CommunicationService(db)
    sched = SchedulingService(db, audit)
    auto = AutomationService(db, audit)
    ops = OperationsService(db, audit)
    fin = FinanceService(db, audit)
    bops = BusinessOpsService(db, audit)
    search = AnalyticsSearchService(db)

    router = APIRouter(
        auth_service=auth,
        crm_service=crm,
        comm_service=comm,
        audit_service=audit,
        scheduling_service=sched,
        automation_service=auto,
        operations_service=ops,
        finance_service=fin,
        business_ops_service=bops,
        analytics_search_service=search,
    )

    admin_u = auth.create_user("gflow_r_admin", "AdminPass123!", "Admin", "gflow_r_admin@test.com", ROLE_ADMIN)
    admin_tok = auth.create_token(admin_u)
    admin_ctx = auth.authenticate_token(admin_tok)

    cust = crm.create_customer(
        Customer(first_name="Route", last_name="Flow", email="gflow_r_cust@test.com"), admin_ctx
    )
    cust_u = auth.create_user(
        "gflow_r_cust", "CustPass123!", "Route Flow", "gflow_r_cust_login@test.com",
        ROLE_CUSTOMER, customer_id=cust.id,
    )
    cust_tok = auth.create_token(cust_u)

    contract = crm.create_contract(
        Contract(contract_number="CTR-GFLOW-ROUTE-1", customer_id=cust.id, title="Route Contract", content="..."),
        admin_ctx,
    )

    return {
        "router": router, "admin_tok": admin_tok, "cust_tok": cust_tok,
        "cust": cust, "contract": contract,
    }


def _req(router: APIRouter, method: str, path: str, token: str, body: dict = None):
    headers = {"authorization": f"Bearer {token}"}
    body_bytes = json.dumps(body).encode("utf-8") if body is not None else b""
    status, res_headers, res_json = router.handle_request(method, path, headers, body_bytes)
    return status, res_json


def test_signers_route_creates_and_guards_duplicates(api_setup):
    router = api_setup["router"]
    admin_tok = api_setup["admin_tok"]
    contract_id = api_setup["contract"].id

    status, body = _req(
        router, "POST", f"/api/v1/contracts/{contract_id}/signers", admin_tok,
        {"signers": [{"party_role": "customer"}, {"party_role": "project_manager"}]},
    )
    assert status == 201
    assert {s["party_role"] for s in body["signers"]} == {"customer", "project_manager"}

    # Duplicate call: silently skipped, empty signers list back, still 201.
    status, body = _req(
        router, "POST", f"/api/v1/contracts/{contract_id}/signers", admin_tok,
        {"signers": [{"party_role": "customer"}]},
    )
    assert status == 201
    assert body["signers"] == []


def test_signers_route_requires_non_empty_list(api_setup):
    router = api_setup["router"]
    admin_tok = api_setup["admin_tok"]
    contract_id = api_setup["contract"].id
    status, body = _req(router, "POST", f"/api/v1/contracts/{contract_id}/signers", admin_tok, {"signers": []})
    assert status == 400


def test_sign_route_passes_through_party_role_and_rejects_mismatch(api_setup):
    router = api_setup["router"]
    admin_tok = api_setup["admin_tok"]
    cust_tok = api_setup["cust_tok"]
    contract_id = api_setup["contract"].id

    _req(
        router, "POST", f"/api/v1/contracts/{contract_id}/signers", admin_tok,
        {"signers": [{"party_role": "customer"}, {"party_role": "project_manager"}]},
    )

    # Customer signing as themselves: fine.
    status, body = _req(
        router, "POST", f"/api/v1/contracts/{contract_id}/sign", cust_tok,
        {"signature_data": "sig", "party_role": "customer"},
    )
    assert status == 200

    # Customer claiming to sign as project_manager: rejected (NEW-593).
    status, body = _req(
        router, "POST", f"/api/v1/contracts/{contract_id}/sign", cust_tok,
        {"signature_data": "sig2", "party_role": "project_manager"},
    )
    assert status == 403
