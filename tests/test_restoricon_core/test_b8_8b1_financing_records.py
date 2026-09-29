"""
Unit tests for B8.8b-1 (sales_rep_portal.md §4/§8): the financing_records
table + FinancingService CRUD/RBAC. DELIBERATELY INERT this round -- no
AR/financial-summary wiring exists yet (that's B8.8b-2). Mirrors
test_b8_5b_assessment_records.py's service-level conventions.
"""

import sqlite3

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_READ_FINANCIALS,
    PERM_WRITE_CUSTOMERS,
    ROLE_ADMIN,
    ROLE_TECHNICIAN,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import Customer, FinancingRecord, Project
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.crm_service import CRMService
from restoricon_core.services.financing_service import FinancingService


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
    financing_service = FinancingService(db, audit_service)
    return db, auth_service, audit_service, crm_service, financing_service


def _make_project(crm_service, admin):
    cust = crm_service.create_customer(
        Customer(first_name="Fin", last_name="Ancing", email="fin_customer@test.com"), admin
    )
    project = crm_service.create_project(
        Project(customer_id=cust.id, title="Financed Restoration"), admin
    )
    return cust, project


# ==========================================
# CREATE / GET round-trip
# ==========================================


def test_create_and_get_financing_record(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    record = financing_service.create_financing_record(
        FinancingRecord(
            project_id=project.id,
            provider="Acme Lending",
            application_status="submitted",
            amount_financed=5000.0,
            customer_contribution=1000.0,
            document_ids=[1, 2],
        ),
        admin,
    )
    assert record.id is not None
    assert record.created_by == admin.user_id
    assert record.created_at is not None
    assert record.updated_at is not None
    assert record.status == "active"

    fetched = financing_service.get_financing_record(record.id, admin)
    assert fetched is not None
    assert fetched.project_id == project.id
    assert fetched.provider == "Acme Lending"
    assert fetched.amount_financed == 5000.0
    assert fetched.customer_contribution == 1000.0
    assert fetched.document_ids == [1, 2]


def test_get_financing_record_not_found(setup_services):
    _, auth_service, _, _, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    assert financing_service.get_financing_record(999999, admin) is None


def test_list_financing_records_for_project(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project1 = _make_project(crm_service, admin)
    cust2 = crm_service.create_customer(
        Customer(first_name="Other", last_name="Cust", email="other_fin@test.com"), admin
    )
    project2 = crm_service.create_project(
        Project(customer_id=cust2.id, title="Other Project"), admin
    )

    r1 = financing_service.create_financing_record(
        FinancingRecord(project_id=project1.id, amount_financed=1000.0), admin
    )
    r2 = financing_service.create_financing_record(
        FinancingRecord(project_id=project1.id, amount_financed=2000.0), admin
    )
    financing_service.create_financing_record(
        FinancingRecord(project_id=project2.id, amount_financed=3000.0), admin
    )

    by_project1 = financing_service.list_financing_records_for_project(project1.id, admin)
    assert {r.id for r in by_project1} == {r1.id, r2.id}


# ==========================================
# UPDATE round-trip
# ==========================================


def test_update_financing_record_round_trip(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    record = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, application_status="submitted", amount_financed=1000.0),
        admin,
    )

    updated = financing_service.update_financing_record(
        record.id,
        {"application_status": "approved", "amount_financed": 1500.0, "provider": "Beta Capital"},
        admin,
    )
    assert updated is not None
    assert updated.application_status == "approved"
    assert updated.amount_financed == 1500.0
    assert updated.provider == "Beta Capital"

    refetched = financing_service.get_financing_record(record.id, admin)
    assert refetched.application_status == "approved"
    assert refetched.amount_financed == 1500.0


def test_update_financing_record_can_link_invoice_id_later(setup_services):
    """The table's nullable invoice_id exists specifically so financing
    can be recorded before the invoice does, then linked later via
    update_financing_record."""
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    record = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, amount_financed=1000.0), admin
    )
    assert record.invoice_id is None

    updated = financing_service.update_financing_record(record.id, {"invoice_id": 77}, admin)
    assert updated.invoice_id == 77

    refetched = financing_service.get_financing_record(record.id, admin)
    assert refetched.invoice_id == 77


def test_update_financing_record_not_found(setup_services):
    _, auth_service, _, _, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    assert financing_service.update_financing_record(999999, {"provider": "X"}, admin) is None


def test_update_financing_record_unknown_field_rejected(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)
    record = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id), admin
    )
    with pytest.raises(ValueError):
        financing_service.update_financing_record(record.id, {"project_id": 999}, admin)


# ==========================================
# Python-level validation
# ==========================================


def test_create_financing_record_rejects_invalid_application_status(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)
    with pytest.raises(ValueError):
        financing_service.create_financing_record(
            FinancingRecord(project_id=project.id, application_status="bogus"), admin
        )


def test_create_financing_record_rejects_invalid_status(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)
    with pytest.raises(ValueError):
        financing_service.create_financing_record(
            FinancingRecord(project_id=project.id, status="bogus"), admin
        )


def test_update_financing_record_rejects_invalid_application_status(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)
    record = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id), admin
    )
    with pytest.raises(ValueError):
        financing_service.update_financing_record(record.id, {"application_status": "bogus"}, admin)


# ==========================================
# Partial unique index: double-financing-provider guard
# ==========================================


def test_double_approved_financing_on_same_invoice_rejected(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=42, application_status="approved"),
        admin,
    )
    with pytest.raises(ValueError):
        financing_service.create_financing_record(
            FinancingRecord(project_id=project.id, invoice_id=42, application_status="funded"),
            admin,
        )


def test_second_submitted_financing_on_same_invoice_allowed(setup_services):
    """Non-eligible statuses (submitted/denied/cancelled) may coexist on
    the same invoice -- the guard only blocks two simultaneously
    approved/funded records."""
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    r1 = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=43, application_status="submitted"),
        admin,
    )
    r2 = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=43, application_status="denied"),
        admin,
    )
    r3 = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=43, application_status="cancelled"),
        admin,
    )
    assert r1.id != r2.id != r3.id


def test_approved_financing_on_different_invoices_allowed(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    r1 = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=44, application_status="approved"),
        admin,
    )
    r2 = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=45, application_status="funded"),
        admin,
    )
    assert r1.id != r2.id


def test_update_into_second_approved_on_same_invoice_rejected(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=46, application_status="approved"),
        admin,
    )
    r2 = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=46, application_status="submitted"),
        admin,
    )
    with pytest.raises(ValueError):
        financing_service.update_financing_record(r2.id, {"application_status": "funded"}, admin)


def test_voided_approved_financing_does_not_block_a_new_one(setup_services):
    """The guard's WHERE clause is scoped to status='active' -- voiding
    the first record frees the invoice for a new approved/funded one."""
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    r1 = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=47, application_status="approved"),
        admin,
    )
    financing_service.update_financing_record(r1.id, {"status": "voided"}, admin)

    r2 = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, invoice_id=47, application_status="funded"),
        admin,
    )
    assert r2.id != r1.id


# ==========================================
# RBAC
# ==========================================


def test_create_financing_record_permission_denied(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)
    tech = _make_actor(auth_service, "tech", ROLE_TECHNICIAN)

    assert not tech.has_permission(PERM_WRITE_CUSTOMERS)
    with pytest.raises(PermissionError):
        financing_service.create_financing_record(
            FinancingRecord(project_id=project.id), tech
        )


def test_update_financing_record_permission_denied(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)
    record = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id), admin
    )
    tech = _make_actor(auth_service, "tech2", ROLE_TECHNICIAN)

    with pytest.raises(PermissionError):
        financing_service.update_financing_record(record.id, {"provider": "X"}, tech)


def test_get_financing_record_permission_denied(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)
    record = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id), admin
    )
    tech = _make_actor(auth_service, "tech3", ROLE_TECHNICIAN)

    assert not tech.has_permission(PERM_READ_FINANCIALS)
    with pytest.raises(PermissionError):
        financing_service.get_financing_record(record.id, tech)


def test_list_financing_records_permission_denied(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)
    tech = _make_actor(auth_service, "tech4", ROLE_TECHNICIAN)

    with pytest.raises(PermissionError):
        financing_service.list_financing_records_for_project(project.id, tech)


# ==========================================
# Audit logging
# ==========================================


def test_create_financing_record_writes_audit_log(setup_services):
    db, auth_service, audit_service, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    record = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, amount_financed=2500.0), admin
    )

    conn = db.get_connection()
    row = conn.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'financing_record' AND entity_id = ?;",
        (record.id,),
    ).fetchone()
    assert row is not None
    assert row["action"] == "create"


def test_update_financing_record_writes_audit_log_with_field_diff(setup_services):
    db, auth_service, audit_service, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    record = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, amount_financed=1000.0), admin
    )
    financing_service.update_financing_record(record.id, {"amount_financed": 1200.0}, admin)

    conn = db.get_connection()
    row = conn.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'financing_record' AND entity_id = ? AND action = 'update';",
        (record.id,),
    ).fetchone()
    assert row is not None
    import json as _json
    details = _json.loads(row["details_json"])
    assert "changed_fields" in details
    assert details["changed_fields"]["amount_financed"]["old"] == 1000.0
    assert details["changed_fields"]["amount_financed"]["new"] == 1200.0


def test_create_financing_record_rejects_negative_amount_financed(setup_services):
    """code-reviewer finding (B8.8b-1 round 1): a negative amount_financed
    would silently INCREASE reported AR once B8.8b-2 wires the offset.
    Guarded at create time, mirroring FinanceService.record_transaction's
    sibling amount validation."""
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    with pytest.raises(ValueError):
        financing_service.create_financing_record(
            FinancingRecord(project_id=project.id, amount_financed=-500.0), admin
        )


def test_create_financing_record_rejects_negative_customer_contribution(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    with pytest.raises(ValueError):
        financing_service.create_financing_record(
            FinancingRecord(project_id=project.id, customer_contribution=-1.0), admin
        )


def test_update_financing_record_rejects_negative_amount_financed(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    record = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, amount_financed=1000.0), admin
    )
    with pytest.raises(ValueError):
        financing_service.update_financing_record(record.id, {"amount_financed": -1.0}, admin)


def test_create_financing_record_rounds_sub_cent_amount_financed(setup_services):
    """code-reviewer finding (B8.8b-2 review): a sub-cent amount_financed
    (e.g. 166.665) could make B8.8b-2's AR reconciliation identity off by
    a cent across several invoices. Rounded to 2 decimal places at the
    write side, same convention every other money field in this codebase
    uses -- closes the gap at the source rather than every downstream AR
    read needing to defend against it."""
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    record = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, amount_financed=166.665, customer_contribution=33.335),
        admin,
    )
    # Exact rounded value depends on float representation/banker's
    # rounding; what matters is idempotency -- the stored value is
    # already cent-precision, not that it lands on a specific cent.
    assert round(record.amount_financed, 2) == record.amount_financed
    assert round(record.customer_contribution, 2) == record.customer_contribution

    fetched = financing_service.get_financing_record(record.id, admin)
    assert round(fetched.amount_financed, 2) == fetched.amount_financed
    assert round(fetched.customer_contribution, 2) == fetched.customer_contribution


def test_update_financing_record_rounds_sub_cent_amount_financed(setup_services):
    _, auth_service, _, crm_service, financing_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    _, project = _make_project(crm_service, admin)

    record = financing_service.create_financing_record(
        FinancingRecord(project_id=project.id, amount_financed=100.0), admin
    )
    updated = financing_service.update_financing_record(record.id, {"amount_financed": 250.001}, admin)
    assert round(updated.amount_financed, 2) == updated.amount_financed
    assert updated.amount_financed == 250.0
