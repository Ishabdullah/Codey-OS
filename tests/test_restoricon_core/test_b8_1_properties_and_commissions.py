"""
Unit tests for B8.1 (D4, sales_rep_portal.md §4, Ish-approved 2026-09-16):
the properties table + CRMService Property CRUD, the commission_ledger_entries
table + CommissionService, the projects.property_id link (both fresh-DB and
legacy-DB-migration paths), and the PERM_READ_TEAM_COMMISSIONS RBAC gate.
"""

import sqlite3

import pytest

from restoricon_core.auth import (
    AuthContext,
    AuthService,
    PERM_READ_TEAM_COMMISSIONS,
    ROLE_ADMIN,
    ROLE_SALES,
)
from restoricon_core.database import DatabaseManager
from restoricon_core.models import CommissionLedgerEntry, Customer, Property
from restoricon_core.services.audit_service import AuditService
from restoricon_core.services.commission_service import CommissionService
from restoricon_core.services.crm_service import CRMService


@pytest.fixture
def setup_services():
    db = DatabaseManager(":memory:")
    auth_service = AuthService(db)
    audit_service = AuditService(db)
    crm_service = CRMService(db, audit_service)
    commission_service = CommissionService(db, audit_service)
    return db, auth_service, audit_service, crm_service, commission_service


def _make_actor(auth_service, username, role, email=None):
    user = auth_service.create_user(
        username=username,
        plain_password="Password123",
        full_name=username.title(),
        email=email or f"{username}@test.com",
        role=role,
    )
    return AuthContext(user_id=user.id, username=username, role=role, actor_type="human")


# ==========================================
# PROPERTIES
# ==========================================


def test_create_and_get_property(setup_services):
    _, auth_service, _, crm_service, _ = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust = crm_service.create_customer(
        Customer(first_name="Jane", last_name="Doe", email="jane@test.com"), admin
    )

    prop = crm_service.create_property(
        Property(
            customer_id=cust.id,
            address="123 Main St",
            property_type="single_family",
            year_built=1995,
            existing_systems={"hvac": "central_air"},
        ),
        admin,
    )
    assert prop.id is not None
    assert prop.address == "123 Main St"

    fetched = crm_service.get_property(prop.id, admin)
    assert fetched is not None
    assert fetched.customer_id == cust.id
    assert fetched.existing_systems == {"hvac": "central_air"}


def test_list_properties_filtered_by_customer(setup_services):
    _, auth_service, _, crm_service, _ = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    cust1 = crm_service.create_customer(
        Customer(first_name="A", last_name="One", email="a@test.com"), admin
    )
    cust2 = crm_service.create_customer(
        Customer(first_name="B", last_name="Two", email="b@test.com"), admin
    )
    crm_service.create_property(Property(customer_id=cust1.id, address="1 First St"), admin)
    crm_service.create_property(Property(customer_id=cust2.id, address="2 Second St"), admin)

    results = crm_service.list_properties(admin, customer_id=cust1.id)
    assert len(results) == 1
    assert results[0].address == "1 First St"


def test_update_property_merges_existing_systems(setup_services):
    _, auth_service, _, crm_service, _ = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    prop = crm_service.create_property(
        Property(address="9 Oak Ave", existing_systems={"hvac": "central_air"}), admin
    )

    updated = crm_service.update_property(
        prop.id,
        {"existing_systems": {"plumbing": "copper"}, "notes": "Updated notes"},
        admin,
    )
    assert updated is not None
    assert updated.existing_systems == {"hvac": "central_air", "plumbing": "copper"}
    assert updated.notes == "Updated notes"


def test_create_property_requires_write_customers_permission(setup_services):
    _, auth_service, _, crm_service, _ = setup_services

    # ROLE_SALES holds PERM_WRITE_CUSTOMERS by default, so use ROLE_CUSTOMER
    # (which has neither PERM_READ_ALL_CUSTOMERS nor PERM_WRITE_CUSTOMERS)
    # to prove the gate is enforced.
    from restoricon_core.auth import ROLE_CUSTOMER

    admin = _make_actor(auth_service, "admin2", ROLE_ADMIN)
    cust = crm_service.create_customer(
        Customer(first_name="Cust", last_name="Owner", email="custowner@test.com"), admin
    )
    cust_user = auth_service.create_user(
        username="custrole",
        plain_password="Password123",
        full_name="Cust Role",
        email="custrole@test.com",
        role=ROLE_CUSTOMER,
        customer_id=cust.id,
    )
    cust_actor = AuthContext(
        user_id=cust_user.id, username="custrole", role=ROLE_CUSTOMER, actor_type="human", customer_id=cust.id
    )

    with pytest.raises(PermissionError):
        crm_service.create_property(Property(address="No Access St"), cust_actor)


# ==========================================
# COMMISSION LEDGER
# ==========================================


def test_record_commission_requires_non_null_rep_user_id(setup_services):
    _, auth_service, _, _, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    with pytest.raises(ValueError):
        commission_service.record_commission(
            CommissionLedgerEntry(
                rep_user_id=None, source_type="assessment", commission_amount=100.0
            ),
            admin,
        )


def test_record_commission_validates_source_type_and_status(setup_services):
    _, auth_service, _, _, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    rep_actor = _make_actor(auth_service, "rep1", ROLE_SALES)

    with pytest.raises(ValueError):
        commission_service.record_commission(
            CommissionLedgerEntry(
                rep_user_id=rep_actor.user_id, source_type="referral", commission_amount=100.0
            ),
            admin,
        )

    with pytest.raises(ValueError):
        commission_service.record_commission(
            CommissionLedgerEntry(
                rep_user_id=rep_actor.user_id,
                source_type="assessment",
                commission_amount=100.0,
                status="bogus",
            ),
            admin,
        )


def test_record_get_reverse_commission_roundtrip(setup_services):
    _, auth_service, _, _, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    rep_actor = _make_actor(auth_service, "rep1", ROLE_SALES)

    entry = commission_service.record_commission(
        CommissionLedgerEntry(
            rep_user_id=rep_actor.user_id,
            source_type="assessment",
            source_id=42,
            basis_amount=1000.0,
            commission_rate_or_flat=0.1,
            commission_amount=100.0,
            status="earned",
        ),
        admin,
    )
    assert entry.id is not None
    assert entry.created_by == admin.user_id

    fetched = commission_service.get_commission(entry.id, admin)
    assert fetched is not None
    assert fetched.commission_amount == 100.0

    reversal = commission_service.reverse_commission(entry.id, admin, notes="correction")
    assert reversal.id != entry.id
    assert reversal.status == "reversed"
    assert reversal.reversed_entry_id == entry.id
    assert reversal.commission_amount == -100.0

    # Original row must be unchanged (append-only -- never UPDATE/DELETE).
    original_after = commission_service.get_commission(entry.id, admin)
    assert original_after.status == "earned"
    assert original_after.commission_amount == 100.0


def test_reverse_commission_missing_entry_raises(setup_services):
    _, auth_service, _, _, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)

    with pytest.raises(ValueError):
        commission_service.reverse_commission(999999, admin)


def test_reverse_commission_rejects_double_reversal(setup_services):
    """code-reviewer round 2 (B8.1), reproducing the bug live: reversing
    the same commission entry twice must not be allowed -- it would
    otherwise produce two -100 reversal rows against one +100 original,
    netting to -100 instead of 0."""
    _, auth_service, _, _, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    rep_actor = _make_actor(auth_service, "rep1", ROLE_SALES)

    entry = commission_service.record_commission(
        CommissionLedgerEntry(
            rep_user_id=rep_actor.user_id,
            source_type="assessment",
            commission_amount=100.0,
            status="earned",
        ),
        admin,
    )

    first_reversal = commission_service.reverse_commission(entry.id, admin)
    assert first_reversal.commission_amount == -100.0

    with pytest.raises(ValueError):
        commission_service.reverse_commission(entry.id, admin)

    # Only one reversal row exists -- the ledger nets out correctly.
    all_rows = commission_service.list_commissions(admin, rep_user_id=rep_actor.user_id)
    total = sum(e.commission_amount for e in all_rows)
    assert total == 0.0
    reversal_rows = [e for e in all_rows if e.reversed_entry_id == entry.id]
    assert len(reversal_rows) == 1


def test_reverse_commission_race_is_closed_at_db_level(setup_services):
    """code-reviewer round 2 (B8.1): the double-reversal guard must be
    race-safe, not just a pre-check -- proven here by bypassing
    reverse_commission's own pre-check SELECT and inserting a second
    reversal row directly (simulating a second concurrent caller that won
    the race between the first caller's pre-check and its INSERT). The
    schema-level partial unique index must reject it with an
    IntegrityError, exactly as reverse_commission's except-clause expects
    to catch."""
    import sqlite3

    _, auth_service, _, _, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    rep_actor = _make_actor(auth_service, "rep1", ROLE_SALES)

    entry = commission_service.record_commission(
        CommissionLedgerEntry(
            rep_user_id=rep_actor.user_id,
            source_type="assessment",
            commission_amount=100.0,
            status="earned",
        ),
        admin,
    )
    commission_service.reverse_commission(entry.id, admin)

    conn = commission_service.db.get_connection()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO commission_ledger_entries (
                rep_user_id, source_type, commission_amount, status,
                reversed_entry_id, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (rep_actor.user_id, "assessment", -100.0, "reversed", entry.id, admin.user_id, "2026-09-17T00:00:00Z"),
        )


def test_reverse_commission_does_not_swallow_unrelated_integrity_errors(setup_services, monkeypatch):
    """code-reviewer round 2 (B8.1): the except sqlite3.IntegrityError
    clause in reverse_commission must be narrowly scoped to the
    reversed_entry_id unique-constraint violation only -- an unrelated
    IntegrityError (e.g. a future FK/CHECK violation on the same INSERT)
    must propagate as-is, not get silently reported to the caller as
    'already reversed'."""
    _, auth_service, _, _, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    rep_actor = _make_actor(auth_service, "rep1", ROLE_SALES)

    entry = commission_service.record_commission(
        CommissionLedgerEntry(
            rep_user_id=rep_actor.user_id,
            source_type="assessment",
            commission_amount=100.0,
            status="earned",
        ),
        admin,
    )

    # sqlite3.Connection is an immutable C type -- neither the instance's
    # nor the class's `execute` attribute can be monkeypatched directly.
    # Wrap the real connection in a thin proxy instead: only `execute` is
    # overridden (to raise an unrelated IntegrityError on the reversal
    # INSERT specifically), every other attribute (including `__enter__`/
    # `__exit__`, since reverse_commission uses `with conn:`) delegates
    # straight through to the real connection.
    real_conn = commission_service.db.get_connection()

    class _FaultInjectingConn:
        def execute(self, sql, params=()):
            if "INSERT INTO commission_ledger_entries" in sql:
                raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")
            return real_conn.execute(sql, params)

        def __enter__(self):
            return real_conn.__enter__()

        def __exit__(self, *args):
            return real_conn.__exit__(*args)

        def __getattr__(self, name):
            return getattr(real_conn, name)

    monkeypatch.setattr(commission_service.db, "get_connection", lambda: _FaultInjectingConn())

    with pytest.raises(sqlite3.IntegrityError):
        commission_service.reverse_commission(entry.id, admin)


def test_list_commissions_excludes_reversed_original_when_status_filtered(setup_services):
    """code-reviewer round 2 (B8.1): status='earned' must not return an
    original row that has since been reversed -- otherwise a
    payout-style query silently double-counts it."""
    _, auth_service, _, _, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    rep_actor = _make_actor(auth_service, "rep1", ROLE_SALES)

    entry = commission_service.record_commission(
        CommissionLedgerEntry(
            rep_user_id=rep_actor.user_id,
            source_type="assessment",
            commission_amount=100.0,
            status="earned",
        ),
        admin,
    )
    still_earned = commission_service.record_commission(
        CommissionLedgerEntry(
            rep_user_id=rep_actor.user_id,
            source_type="bonus",
            commission_amount=25.0,
            status="earned",
        ),
        admin,
    )

    earned_before = commission_service.list_commissions(admin, rep_user_id=rep_actor.user_id, status="earned")
    assert {e.id for e in earned_before} == {entry.id, still_earned.id}

    commission_service.reverse_commission(entry.id, admin)

    earned_after = commission_service.list_commissions(admin, rep_user_id=rep_actor.user_id, status="earned")
    assert entry.id not in {e.id for e in earned_after}
    assert still_earned.id in {e.id for e in earned_after}

    # Full audit history (include_reversed=True) still shows the original
    # earned row plus its reversal row.
    full_history = commission_service.list_commissions(
        admin, rep_user_id=rep_actor.user_id, status="earned", include_reversed=True
    )
    assert entry.id in {e.id for e in full_history}

    # Unfiltered (no status arg) always shows everything, reversed or not.
    unfiltered = commission_service.list_commissions(admin, rep_user_id=rep_actor.user_id)
    assert entry.id in {e.id for e in unfiltered}


def test_sales_rep_without_team_read_cannot_read_another_reps_commission(setup_services):
    """Exit-criteria permission test: a sales-role actor without
    PERM_READ_TEAM_COMMISSIONS cannot read another rep's ledger rows, but
    can read their own."""
    _, auth_service, _, _, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    rep1 = _make_actor(auth_service, "rep1", ROLE_SALES)
    rep2 = _make_actor(auth_service, "rep2", ROLE_SALES)

    assert not rep1.has_permission(PERM_READ_TEAM_COMMISSIONS)
    assert not rep2.has_permission(PERM_READ_TEAM_COMMISSIONS)

    entry_for_rep1 = commission_service.record_commission(
        CommissionLedgerEntry(
            rep_user_id=rep1.user_id, source_type="bonus", commission_amount=50.0
        ),
        admin,
    )

    # rep2 (plain ROLE_SALES, no PERM_READ_TEAM_COMMISSIONS) cannot see rep1's entry.
    assert commission_service.get_commission(entry_for_rep1.id, rep2) is None

    # rep1 CAN see their own entry.
    own = commission_service.get_commission(entry_for_rep1.id, rep1)
    assert own is not None
    assert own.id == entry_for_rep1.id

    # list_commissions is narrowed the same way: rep2's team-wide filter
    # request is ignored and forced to their own user_id, so rep1's entry
    # never appears in rep2's list.
    rep2_list = commission_service.list_commissions(rep2, rep_user_id=rep1.user_id)
    assert all(e.rep_user_id == rep2.user_id for e in rep2_list)
    assert entry_for_rep1.id not in {e.id for e in rep2_list}

    # An actor holding PERM_READ_TEAM_COMMISSIONS (admin here) sees it fine.
    assert commission_service.get_commission(entry_for_rep1.id, admin) is not None


def test_sales_rep_without_team_read_cannot_record_or_reverse_commissions(setup_services):
    _, auth_service, _, _, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    rep1 = _make_actor(auth_service, "rep1", ROLE_SALES)

    with pytest.raises(PermissionError):
        commission_service.record_commission(
            CommissionLedgerEntry(
                rep_user_id=rep1.user_id, source_type="bonus", commission_amount=25.0
            ),
            rep1,
        )

    entry = commission_service.record_commission(
        CommissionLedgerEntry(
            rep_user_id=rep1.user_id, source_type="bonus", commission_amount=25.0
        ),
        admin,
    )
    with pytest.raises(PermissionError):
        commission_service.reverse_commission(entry.id, rep1)


def test_read_only_actor_cannot_record_or_reverse_commissions(setup_services):
    """code-reviewer round 2 (B8.1): record_commission/reverse_commission
    must be gated on PERM_WRITE_TEAM_COMMISSIONS specifically, not
    PERM_READ_TEAM_COMMISSIONS -- proven by an actor who holds read but
    not write via a custom_permissions_json-style override."""
    from restoricon_core.auth import PERM_READ_TEAM_COMMISSIONS, PERM_WRITE_TEAM_COMMISSIONS

    _, auth_service, _, _, commission_service = setup_services
    admin = _make_actor(auth_service, "admin", ROLE_ADMIN)
    rep1 = _make_actor(auth_service, "rep1", ROLE_SALES)

    read_only_actor = AuthContext(
        user_id=rep1.user_id,
        username="rep1",
        role=ROLE_SALES,
        actor_type="human",
        custom_permissions={PERM_READ_TEAM_COMMISSIONS: True, PERM_WRITE_TEAM_COMMISSIONS: False},
    )
    assert read_only_actor.has_permission(PERM_READ_TEAM_COMMISSIONS)
    assert not read_only_actor.has_permission(PERM_WRITE_TEAM_COMMISSIONS)

    with pytest.raises(PermissionError):
        commission_service.record_commission(
            CommissionLedgerEntry(
                rep_user_id=rep1.user_id, source_type="bonus", commission_amount=25.0
            ),
            read_only_actor,
        )

    entry = commission_service.record_commission(
        CommissionLedgerEntry(
            rep_user_id=rep1.user_id, source_type="bonus", commission_amount=25.0
        ),
        admin,
    )
    with pytest.raises(PermissionError):
        commission_service.reverse_commission(entry.id, read_only_actor)

    # But the read-only actor CAN still read.
    assert commission_service.get_commission(entry.id, read_only_actor) is not None


# ==========================================
# SCHEMA: projects.property_id (fresh DB + legacy-DB migration path)
# ==========================================


def test_fresh_db_has_properties_table_and_projects_property_id():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()

    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")}
    assert "properties" in tables
    assert "commission_ledger_entries" in tables

    project_cols = {row["name"] for row in conn.execute("PRAGMA table_info(projects);")}
    assert "property_id" in project_cols

    indexes = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index';")}
    assert "idx_properties_customer_id" in indexes
    assert "idx_projects_property_id" in indexes
    assert "idx_commission_ledger_rep_user_id" in indexes
    assert "idx_commission_ledger_status" in indexes
    assert "idx_commission_ledger_source" in indexes


# Pre-round DDL for `projects` (the shape before B8.1 added property_id),
# used to exercise the ALTER TABLE ADD COLUMN branch in _migrate_schema()
# -- an in-memory DB always gets the column via CREATE TABLE, so it can
# never actually test the ALTER TABLE path (see test_database.py's own
# _LEGACY_CUSTOMERS_LEADS_DDL for the same precedent).
_LEGACY_PROJECTS_DDL = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    company_name TEXT,
    phone TEXT,
    email TEXT COLLATE NOCASE,
    mailing_address TEXT,
    service_address TEXT,
    customer_type TEXT NOT NULL DEFAULT 'residential',
    customer_source TEXT,
    assigned_user_id INTEGER,
    status TEXT NOT NULL DEFAULT 'lead',
    tags_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    custom_fields_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    last_contact_at TEXT,
    next_followup_at TEXT
);
CREATE TABLE projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    property_address TEXT NOT NULL,
    project_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planning',
    stage TEXT NOT NULL DEFAULT 'intake',
    project_manager_id INTEGER,
    assigned_employees_json TEXT NOT NULL DEFAULT '[]',
    subcontractors_json TEXT NOT NULL DEFAULT '[]',
    estimated_cost REAL NOT NULL DEFAULT 0.0,
    contract_amount REAL NOT NULL DEFAULT 0.0,
    actual_cost REAL NOT NULL DEFAULT 0.0,
    profit REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def test_legacy_db_gets_property_id_column_and_index_added(tmp_path):
    """B8.1: a DB file created before property_id existed must get the
    column (and its index) added on the next open, with existing rows
    preserved, and must not error on a second open."""
    db_path = tmp_path / "legacy_projects.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_LEGACY_PROJECTS_DDL)
    conn.execute(
        "INSERT INTO customers (first_name, last_name, created_at) VALUES ('Jane', 'Doe', '2020-01-01');"
    )
    conn.execute(
        "INSERT INTO projects (customer_id, title, property_address, project_type, created_at, updated_at) "
        "VALUES (1, 'Old Project', '1 Legacy Rd', 'remodel', '2020-01-01', '2020-01-01');"
    )
    conn.commit()
    conn.close()

    db = DatabaseManager(str(db_path))
    conn2 = db.get_connection()

    project_cols = {row["name"] for row in conn2.execute("PRAGMA table_info(projects);")}
    assert "property_id" in project_cols

    row = conn2.execute("SELECT * FROM projects WHERE title = 'Old Project';").fetchone()
    assert row is not None
    assert row["property_id"] is None  # ALTER-added column defaults to NULL for existing rows

    indexes = {row["name"] for row in conn2.execute("SELECT name FROM sqlite_master WHERE type='index';")}
    assert "idx_projects_property_id" in indexes

    # Re-opening must not raise "duplicate column name".
    db2 = DatabaseManager(str(db_path))
    project_cols2 = {row["name"] for row in db2.get_connection().execute("PRAGMA table_info(projects);")}
    assert "property_id" in project_cols2
