"""
Unit tests for database initialization, schema integrity, and foreign key constraints.
"""

import sqlite3
import pytest
from restoricon_core.database import DatabaseManager


# Pre-round DDL for customers/leads (the shape both tables had before
# NEW-212/NEW-232 added external_id), used to exercise the additive
# migration path in _migrate_schema() -- an in-memory DB always gets the
# column via CREATE TABLE, so it can never actually test the ALTER TABLE
# branch. Kept intentionally minimal (customers/leads only, not every
# column) since only these two tables are under migration this round.
_LEGACY_CUSTOMERS_LEADS_DDL = """
CREATE TABLE customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
CREATE TABLE leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    score INTEGER NOT NULL DEFAULT 0,
    estimated_value REAL NOT NULL DEFAULT 0.0,
    assigned_user_id INTEGER,
    first_contact_at TEXT,
    last_contact_at TEXT,
    next_followup_at TEXT,
    notes TEXT,
    lost_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def test_database_initialization_in_memory():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    
    # Check tables exist
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row["name"] for row in cursor.fetchall()}
    
    expected_tables = {
        "users",
        "api_tokens",
        "customers",
        "leads",
        "opportunities",
        "projects",
        "estimates",
        "contracts",
        "documents",
        "invoices",
        "communication_history",
        "audit_log",
        "subcontractors",
        "appointments",
        "automation_rules",
        "business_profile",
        "schedule_config",
        "do_not_contact",
    }
    
    assert expected_tables.issubset(tables)


def test_external_id_migration_adds_column_to_legacy_db(tmp_path):
    """NEW-212/NEW-232: a DB file created before external_id existed must
    get the column (and its unique index) added on the next open, with
    existing rows preserved, and must not error on a second open (which
    would happen if the ALTER weren't gated on PRAGMA table_info)."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_LEGACY_CUSTOMERS_LEADS_DDL)
    conn.execute(
        "INSERT INTO customers (first_name, last_name, created_at) VALUES ('Jane', 'Doe', '2020-01-01');"
    )
    conn.commit()
    conn.close()

    db = DatabaseManager(str(db_path))
    conn = db.get_connection()
    customer_cols = {row["name"] for row in conn.execute("PRAGMA table_info(customers);")}
    lead_cols = {row["name"] for row in conn.execute("PRAGMA table_info(leads);")}
    assert "external_id" in customer_cols
    assert "external_id" in lead_cols

    row = conn.execute("SELECT first_name, last_name, external_id FROM customers;").fetchone()
    assert row["first_name"] == "Jane"
    assert row["external_id"] is None

    indexes = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index';")}
    assert "idx_customers_external_id" in indexes
    assert "idx_leads_external_id" in indexes
    db.close()

    # Second open against the now-migrated file must not raise
    # "duplicate column name".
    db2 = DatabaseManager(str(db_path))
    conn2 = db2.get_connection()
    customer_cols2 = {row["name"] for row in conn2.execute("PRAGMA table_info(customers);")}
    assert "external_id" in customer_cols2
    db2.close()


def test_customers_external_id_unique_index_enforced():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    now = "2026-08-27T00:00:00Z"
    conn.execute(
        "INSERT INTO customers (external_id, first_name, last_name, created_at) VALUES (?, ?, ?, ?);",
        ("dup_ext_id", "A", "One", now),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO customers (external_id, first_name, last_name, created_at) VALUES (?, ?, ?, ?);",
            ("dup_ext_id", "B", "Two", now),
        )
    # NULL external_id must remain unconstrained (multiple NULLs allowed).
    conn.execute(
        "INSERT INTO customers (external_id, first_name, last_name, created_at) VALUES (NULL, ?, ?, ?);",
        ("C", "Three", now),
    )
    conn.execute(
        "INSERT INTO customers (external_id, first_name, last_name, created_at) VALUES (NULL, ?, ?, ?);",
        ("D", "Four", now),
    )
    conn.commit()


def test_foreign_key_enforcement():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    
    # Attempt inserting a project with non-existent customer_id should raise IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                """
                INSERT INTO projects (
                    customer_id, title, property_address, project_type, status,
                    created_at, updated_at
                ) VALUES (9999, 'Test Project', '123 Main St', 'remodel', 'planning',
                          '2026-08-26T00:00:00Z', '2026-08-26T00:00:00Z');
                """
            )
