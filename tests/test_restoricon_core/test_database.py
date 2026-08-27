"""
Unit tests for database initialization, schema integrity, and foreign key constraints.
"""

import sqlite3
import pytest
from restoricon_core.database import DatabaseManager


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
        "do_not_contact",
    }
    
    assert expected_tables.issubset(tables)


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
