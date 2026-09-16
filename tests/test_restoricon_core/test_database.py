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


def test_init_schema_false_does_not_create_tables(tmp_path):
    """U.39 / NEW-456: DatabaseManager(path, init_schema=False) must attach
    without running any DDL, so migrate_aigentik's dry run cannot mutate
    schema on the target DB. The default (init_schema=True) must still
    create the schema."""
    db_path = tmp_path / "noschema.db"

    DatabaseManager(str(db_path), init_schema=False)

    # No DDL ran: either the file was never created, or it holds no tables.
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            ).fetchall()
        finally:
            conn.close()
        assert rows == []

    # Default construction against the same path does create the schema.
    db = DatabaseManager(str(db_path))
    tables = {
        row["name"]
        for row in db.get_connection().execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        )
    }
    assert "users" in tables and "customers" in tables


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


_LEGACY_APPOINTMENTS_DDL = """
CREATE TABLE appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE,
    uid TEXT,
    ics_sequence INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    customer_id INTEGER,
    contact_external_id TEXT,
    attendee_name TEXT,
    attendee_email TEXT COLLATE NOCASE,
    appointment_type TEXT CHECK(appointment_type IN ('call', 'in_person') OR appointment_type IS NULL),
    appointment_type_id INTEGER,
    status TEXT NOT NULL DEFAULT 'confirmed' CHECK(status IN ('confirmed', 'negotiating', 'cancelled', 'completed')),
    rsvp_status TEXT NOT NULL DEFAULT 'pending',
    offered_slots_json TEXT NOT NULL DEFAULT '[]',
    requested_datetime TEXT,
    pending_reschedule_json TEXT,
    form_sent INTEGER NOT NULL DEFAULT 0 CHECK(form_sent IN (0, 1)),
    created_via TEXT NOT NULL DEFAULT 'owner',
    notes TEXT,
    history_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def test_appointments_assigned_user_id_migration_adds_column_to_legacy_db(tmp_path):
    """NEW-487: a DB file created before assigned_user_id existed (but
    already had appointment_type_id, matching the real rollout order) must
    get the column added on the next open, with existing rows preserved,
    and must not error on a second open (duplicate column name)."""
    db_path = tmp_path / "legacy_appointments.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_LEGACY_APPOINTMENTS_DDL)
    conn.execute(
        "INSERT INTO appointments (title, created_at, updated_at) VALUES ('Inspection', '2020-01-01', '2020-01-01');"
    )
    conn.commit()
    conn.close()

    db = DatabaseManager(str(db_path))
    conn = db.get_connection()
    appt_cols = {row["name"] for row in conn.execute("PRAGMA table_info(appointments);")}
    assert "assigned_user_id" in appt_cols

    row = conn.execute("SELECT title, assigned_user_id FROM appointments;").fetchone()
    assert row["title"] == "Inspection"
    assert row["assigned_user_id"] is None
    db.close()

    # Second open against the now-migrated file must not raise
    # "duplicate column name".
    db2 = DatabaseManager(str(db_path))
    conn2 = db2.get_connection()
    appt_cols2 = {row["name"] for row in conn2.execute("PRAGMA table_info(appointments);")}
    assert "assigned_user_id" in appt_cols2
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


_LEGACY_USERS_ROLE_DDL = """
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
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL COLLATE NOCASE,
    phone TEXT,
    role TEXT NOT NULL CHECK(role IN ('admin', 'manager', 'sales', 'project_manager', 'technician', 'ai_agent', 'customer')),
    department TEXT,
    customer_id INTEGER,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE api_tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    is_revoked INTEGER NOT NULL DEFAULT 0 CHECK(is_revoked IN (0, 1)),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE staff_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled' CHECK(status IN ('scheduled', 'cancelled', 'completed')),
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
"""


def test_users_role_migration_widens_check_constraint_on_legacy_db(tmp_path):
    """D2 (sales_rep_portal.md §4): a DB file created before the
    'sales_manager' role existed (original 7-value CHECK) must get the
    widened CHECK on next open, via the SQLite table-rebuild procedure --
    preserving all users/api_tokens/staff_schedules rows and FK integrity,
    including the two ON DELETE CASCADE FKs (api_tokens, staff_schedules)
    that make a naive drop-and-recreate of `users` dangerous."""
    db_path = tmp_path / "legacy_users_role.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(_LEGACY_USERS_ROLE_DDL)
    now = "2020-01-01T00:00:00Z"
    conn.execute(
        "INSERT INTO users (username, password_hash, full_name, email, role, active, created_at, updated_at) "
        "VALUES ('alice', 'hash1', 'Alice A', 'alice@test.com', 'sales', 1, ?, ?);",
        (now, now),
    )
    conn.execute(
        "INSERT INTO users (username, password_hash, full_name, email, role, active, created_at, updated_at) "
        "VALUES ('bob', 'hash2', 'Bob B', 'bob@test.com', 'admin', 1, ?, ?);",
        (now, now),
    )
    conn.commit()
    # Set up the sqlite_sequence regression case: insert a user at the
    # current max id, then delete it, so the next real insert must NOT
    # reuse that id.
    conn.execute(
        "INSERT INTO users (username, password_hash, full_name, email, role, active, created_at, updated_at) "
        "VALUES ('temp_user', 'hash3', 'Temp User', 'temp@test.com', 'technician', 1, ?, ?);",
        (now, now),
    )
    temp_id = conn.execute("SELECT id FROM users WHERE username='temp_user';").fetchone()[0]
    conn.execute(
        "INSERT INTO api_tokens (token, user_id, role, created_at, expires_at, is_revoked) VALUES (?, ?, ?, ?, ?, 0);",
        ("tok-alice", 1, "sales", now, "2099-01-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO staff_schedules (user_id, title, start_time, end_time, status, created_at, updated_at) "
        "VALUES (1, 'Shift', ?, ?, 'scheduled', ?, ?);",
        (now, now, now, now),
    )
    conn.commit()
    conn.execute("DELETE FROM users WHERE id = ?;", (temp_id,))
    conn.commit()
    conn.close()

    db = DatabaseManager(str(db_path))
    conn = db.get_connection()

    # 'sales_manager' now insertable.
    conn.execute(
        "INSERT INTO users (username, password_hash, full_name, email, phone, role, department, "
        "customer_id, custom_permissions_json, active, created_at, updated_at) "
        "VALUES ('carol', 'hash4', 'Carol C', 'carol@test.com', NULL, 'sales_manager', NULL, "
        "NULL, '{}', 1, ?, ?);",
        (now, now),
    )
    conn.commit()
    new_row = conn.execute("SELECT id, role FROM users WHERE username='carol';").fetchone()
    assert new_row["role"] == "sales_manager"
    # Regression check: the new id must be MAX(id)+1 from BEFORE the
    # deleted temp_user, not a reused id (sqlite_sequence preservation).
    assert new_row["id"] > temp_id

    # A garbage role value still raises IntegrityError.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, email, role, active, created_at, updated_at) "
            "VALUES ('bogus', 'hash5', 'Bogus User', 'bogus@test.com', 'not_a_real_role', 1, ?, ?);",
            (now, now),
        )

    # Pre-existing rows preserved.
    user_count = conn.execute("SELECT COUNT(*) FROM users WHERE username IN ('alice','bob');").fetchone()[0]
    assert user_count == 2
    token_count = conn.execute("SELECT COUNT(*) FROM api_tokens;").fetchone()[0]
    assert token_count == 1
    schedule_count = conn.execute("SELECT COUNT(*) FROM staff_schedules;").fetchone()[0]
    assert schedule_count == 1

    # No FK violations left behind by the rebuild.
    fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
    assert fk_violations == []

    # Expected indexes exist.
    indexes = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index';")}
    assert "idx_users_username" in indexes
    assert "idx_users_role" in indexes

    # Regression guard: the CASCADE relationship from api_tokens/
    # staff_schedules to users must still actually fire after the
    # rebuild, not just look intact in the schema text. An earlier
    # version of this migration passed PRAGMA foreign_key_check clean but
    # had silently left api_tokens/staff_schedules referencing a
    # dead renamed-away table name, so a real DELETE no longer cascaded
    # at all -- this call is what would catch that class of bug.
    conn.execute(
        "INSERT INTO api_tokens (token, user_id, role, created_at, expires_at, is_revoked) VALUES (?, ?, ?, ?, ?, 0);",
        ("tok-carol", new_row["id"], "sales_manager", now, "2099-01-01T00:00:00Z"),
    )
    conn.execute(
        "INSERT INTO staff_schedules (user_id, title, start_time, end_time, status, created_at, updated_at) "
        "VALUES (?, 'Carol Shift', ?, ?, 'scheduled', ?, ?);",
        (new_row["id"], now, now, now, now),
    )
    conn.commit()
    conn.execute("DELETE FROM users WHERE id = ?;", (new_row["id"],))
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM api_tokens WHERE token='tok-carol';").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM staff_schedules WHERE title='Carol Shift';").fetchone()[0] == 0

    db.close()

    # Second open against the now-migrated file is idempotent: no error,
    # CHECK still correct, no duplicate-table/column errors.
    db2 = DatabaseManager(str(db_path))
    conn2 = db2.get_connection()
    conn2.execute(
        "INSERT INTO users (username, password_hash, full_name, email, role, active, created_at, updated_at) "
        "VALUES ('dave', 'hash6', 'Dave D', 'dave@test.com', 'sales_manager', 1, ?, ?);",
        (now, now),
    )
    conn2.commit()
    assert conn2.execute("SELECT COUNT(*) FROM users WHERE username='dave';").fetchone()[0] == 1
    db2.close()


def test_users_role_migration_recovers_from_stale_leftover_temp_table(tmp_path):
    """Crash-recovery guard: if a prior run of the rebuild crashed after
    creating the throwaway `_users_new_role_migration` temp table but
    before completing (a scenario that predated this migration's `BEGIN
    IMMEDIATE` fix, which makes the whole rebuild atomic), a leftover
    stale copy of that temp table must not permanently brick the DB file
    on the next open -- the pre-flight `DROP TABLE IF EXISTS` must clear
    it and the rebuild must proceed normally."""
    db_path = tmp_path / "legacy_users_role_stale_temp.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(_LEGACY_USERS_ROLE_DDL)
    now = "2020-01-01T00:00:00Z"
    conn.execute(
        "INSERT INTO users (username, password_hash, full_name, email, role, active, created_at, updated_at) "
        "VALUES ('alice', 'hash1', 'Alice A', 'alice@test.com', 'sales', 1, ?, ?);",
        (now, now),
    )
    conn.commit()
    # Simulate a stale leftover from a prior crashed rebuild attempt.
    conn.execute("CREATE TABLE _users_new_role_migration (id INTEGER PRIMARY KEY, junk TEXT);")
    conn.commit()
    conn.close()

    db = DatabaseManager(str(db_path))
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO users (username, password_hash, full_name, email, role, custom_permissions_json, active, created_at, updated_at) "
        "VALUES ('carol', 'hash4', 'Carol C', 'carol@test.com', 'sales_manager', '{}', 1, ?, ?);",
        (now, now),
    )
    conn.commit()
    assert conn.execute("SELECT role FROM users WHERE username='carol';").fetchone()["role"] == "sales_manager"
    assert conn.execute("SELECT COUNT(*) FROM users WHERE username='alice';").fetchone()[0] == 1
    # The stale junk table must be gone, not merely tolerated.
    leftover = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='_users_new_role_migration';"
    ).fetchone()
    assert leftover is None
    db.close()


def test_users_schema_and_widened_role_sql_column_sets_match():
    """Anti-drift check: _SCHEMA_SQL's `users` column set and
    _USERS_TABLE_WIDENED_ROLE_SQL's column set (the two duplicated `users`
    DDL blocks database.py's own comments say must be kept in sync) must
    be identical."""
    from restoricon_core.database import _SCHEMA_SQL, _USERS_TABLE_WIDENED_ROLE_SQL

    conn_a = sqlite3.connect(":memory:")
    conn_a.executescript(_SCHEMA_SQL)
    schema_cols = {row[1] for row in conn_a.execute("PRAGMA table_info(users);")}
    conn_a.close()

    conn_b = sqlite3.connect(":memory:")
    conn_b.executescript(_USERS_TABLE_WIDENED_ROLE_SQL)
    widened_cols = {row[1] for row in conn_b.execute("PRAGMA table_info(users);")}
    conn_b.close()

    assert schema_cols == widened_cols


def test_migrate_users_role_constraint_raises_if_widened_sql_opener_text_drifts(tmp_path, monkeypatch):
    """Guard test for the load-bearing `.replace()` inside
    _migrate_users_role_constraint(): if _USERS_TABLE_WIDENED_ROLE_SQL's
    'CREATE TABLE users (' opener text ever drifts (reformatting,
    whitespace change), the replace would silently no-op and the method
    would attempt to CREATE a second literal `users` table instead of the
    intended temp table -- this must raise loudly instead."""
    import restoricon_core.database as database_module

    db_path = tmp_path / "legacy_users_role_drift.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(_LEGACY_USERS_ROLE_DDL)
    now = "2020-01-01T00:00:00Z"
    conn.execute(
        "INSERT INTO users (username, password_hash, full_name, email, role, active, created_at, updated_at) "
        "VALUES ('alice', 'hash1', 'Alice A', 'alice@test.com', 'sales', 1, ?, ?);",
        (now, now),
    )
    conn.commit()
    conn.close()

    # Simulate the constant's opener text having drifted from what the
    # method's .replace() call expects.
    monkeypatch.setattr(
        database_module,
        "_USERS_TABLE_WIDENED_ROLE_SQL",
        database_module._USERS_TABLE_WIDENED_ROLE_SQL.replace(
            "CREATE TABLE users (", "CREATE TABLE  users (", 1  # double space
        ),
    )

    with pytest.raises(RuntimeError, match="could not rewrite"):
        DatabaseManager(str(db_path))


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
