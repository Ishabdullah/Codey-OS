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


_LEGACY_ESTIMATES_DDL = """
CREATE TABLE estimates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estimate_number TEXT UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL,
    project_id INTEGER,
    assigned_user_id INTEGER,
    line_items_json TEXT NOT NULL DEFAULT '[]',
    subtotal REAL NOT NULL DEFAULT 0.0,
    materials_cost REAL NOT NULL DEFAULT 0.0,
    labor_cost REAL NOT NULL DEFAULT 0.0,
    subcontractor_cost REAL NOT NULL DEFAULT 0.0,
    markup_percent REAL NOT NULL DEFAULT 0.0,
    tax_amount REAL NOT NULL DEFAULT 0.0,
    discount_amount REAL NOT NULL DEFAULT 0.0,
    total_amount REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'sent', 'approved', 'rejected', 'expired')),
    expiration_date TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);
"""


def test_estimates_assigned_user_id_rename_migration_preserves_data(tmp_path):
    """Live 2026-09-29: the real production `estimates` table predates
    B9.1's v2 rebuild and already has `assigned_user_id` -- not a legacy
    synonym for the v2 schema's `assigned_to_user_id`, but `main`'s own
    B8.6a rep-ownership column (`CRMService.create_estimate`/`get_estimate`/
    `list_estimates`), a real, separate, actively-used column, confirmed
    during the 2026-09-29 merge of `main` into `feat/estimator-phase3-schema`
    (see `NEW-710`). An earlier version of `_migrate_estimates_table_v2()`
    treated this as a rename pair (`assigned_user_id` -> `assigned_to_user_id`)
    -- that would have dropped/misrouted this real column and broken
    `CRMService.create_estimate`'s `INSERT` on every write post-rebuild. This
    confirms the corrected behavior: the rebuild succeeds and BOTH columns
    survive, each under its own name, neither dropped nor merged."""
    db_path = tmp_path / "legacy_estimates.db"

    # Build via a fresh DatabaseManager first so users/customers/projects
    # get the real v2 schema, then downgrade only `estimates` to its
    # pre-B9.1 legacy shape (+ the real-world assigned_user_id drift) to
    # exercise the migration on next open.
    db = DatabaseManager(str(db_path))
    conn = db.get_connection()
    now = "2020-01-01T00:00:00Z"
    conn.execute(
        "INSERT INTO users (username, password_hash, full_name, email, role, active, created_at, updated_at) "
        "VALUES ('sales1', 'hash1', 'Sales One', 'sales1@test.com', 'sales', 1, ?, ?);",
        (now, now),
    )
    user_id = conn.execute("SELECT id FROM users WHERE username='sales1';").fetchone()[0]
    conn.execute(
        "INSERT INTO customers (first_name, last_name, created_at) VALUES ('Jane', 'Doe', ?);",
        (now,),
    )
    customer_id = conn.execute("SELECT id FROM customers WHERE first_name='Jane';").fetchone()[0]
    conn.commit()

    conn.execute("DROP TABLE estimates;")
    conn.executescript(_LEGACY_ESTIMATES_DDL)
    conn.execute(
        "INSERT INTO estimates (estimate_number, customer_id, assigned_user_id, created_at, updated_at) "
        "VALUES ('EST-0001', ?, ?, ?, ?);",
        (customer_id, user_id, now, now),
    )
    conn.commit()
    db.close()

    # Reopen -- must not raise, must rebuild to v2 shape, and must carry
    # the pre-existing assigned_user_id value forward under its OWN name
    # (not renamed into assigned_to_user_id, which stays NULL here since
    # nothing set it).
    db2 = DatabaseManager(str(db_path))
    conn2 = db2.get_connection()
    cols = {row["name"] for row in conn2.execute("PRAGMA table_info(estimates);")}
    assert "workflow_status" in cols
    assert "assigned_to_user_id" in cols
    assert "assigned_user_id" in cols

    row = conn2.execute(
        "SELECT estimate_number, customer_id, assigned_user_id, assigned_to_user_id "
        "FROM estimates WHERE estimate_number='EST-0001';"
    ).fetchone()
    assert row["customer_id"] == customer_id
    assert row["assigned_user_id"] == user_id
    assert row["assigned_to_user_id"] is None

    fk_violations = conn2.execute("PRAGMA foreign_key_check;").fetchall()
    assert fk_violations == []
    db2.close()

    # Idempotent second open: no error, no duplicate-column/table issues.
    db3 = DatabaseManager(str(db_path))
    conn3 = db3.get_connection()
    cols3 = {row["name"] for row in conn3.execute("PRAGMA table_info(estimates);")}
    assert "assigned_to_user_id" in cols3
    db3.close()


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


_LEGACY_USERS_ROLE_DDL_PRE_SUBCONTRACTOR = """
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
    role TEXT NOT NULL CHECK(role IN ('admin', 'manager', 'sales', 'sales_manager', 'project_manager', 'technician', 'ai_agent', 'customer')),
    department TEXT,
    customer_id INTEGER,
    custom_permissions_json TEXT NOT NULL DEFAULT '{}',
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    terminated_at TEXT,
    territory_id INTEGER,
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


def test_users_role_migration_widens_check_constraint_for_subcontractor_on_already_migrated_db(tmp_path):
    """Phase 0b, B8.16 (2026-09-27): a DB file that already went through
    the D2 'sales_manager' widening (its role CHECK already contains
    'sales_manager', and it already has territory_id/terminated_at/
    custom_permissions_json) -- i.e. the exact shape of every real,
    already-migrated production DB today -- must STILL get a further
    widened CHECK adding 'subcontractor' on the next open, plus the new
    subcontractor_id column, with existing rows preserved (no data loss).

    Regression guard for a bug caught before it shipped: a naive
    idempotency gate that tests for a bare 'sales_manager' substring
    (this method's original gate) would incorrectly treat this DB as
    already up to date forever. Worse, a bare 'subcontractor' substring
    check would ALSO false-positive here, because the additive ADD COLUMN
    migration list adds a `subcontractor_id` column to `users` in the same
    _migrate_schema() call, and SQLite rewrites sqlite_master.sql to
    include ALTER-added columns -- so `row["sql"]` contains the substring
    'subcontractor' (from the column name) before the CHECK is ever
    widened. The real gate must match the quoted 'subcontractor' role
    literal, not a bare substring.
    """
    db_path = tmp_path / "legacy_users_role_pre_subcontractor.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(_LEGACY_USERS_ROLE_DDL_PRE_SUBCONTRACTOR)
    now = "2020-01-01T00:00:00Z"
    conn.execute(
        "INSERT INTO users (username, password_hash, full_name, email, role, custom_permissions_json, active, created_at, updated_at) "
        "VALUES ('alice', 'hash1', 'Alice A', 'alice@test.com', 'sales_manager', '{}', 1, ?, ?);",
        (now, now),
    )
    conn.commit()
    conn.close()

    db = DatabaseManager(str(db_path))
    conn = db.get_connection()

    # The role CHECK must now accept 'subcontractor' -- this INSERT would
    # raise sqlite3.IntegrityError before the fix.
    conn.execute(
        "INSERT INTO users (username, password_hash, full_name, email, role, custom_permissions_json, active, created_at, updated_at) "
        "VALUES ('sub1', 'hash2', 'Sub One', 'sub1@test.com', 'subcontractor', '{}', 1, ?, ?);",
        (now, now),
    )
    conn.commit()

    cols = {row["name"] for row in conn.execute("PRAGMA table_info(users);")}
    assert "subcontractor_id" in cols
    assert conn.execute("SELECT role FROM users WHERE username='sub1';").fetchone()["role"] == "subcontractor"
    # No data loss: alice's pre-existing row survived the rebuild.
    assert conn.execute("SELECT COUNT(*) FROM users WHERE username='alice';").fetchone()[0] == 1
    db.close()

    # Second open against the now-migrated file must not raise and must
    # not lose rows (idempotency).
    db2 = DatabaseManager(str(db_path))
    conn2 = db2.get_connection()
    assert conn2.execute("SELECT COUNT(*) FROM users;").fetchone()[0] == 2
    db2.close()


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


# ---------------------------------------------------------------------------
# Codey-Estimator Phase B9.x pricing round (2026-09-30): 12 new pricing
# tables, FK attachment on estimate_line_items' 4 pricing-id columns, and
# the estimates.property_id FK fix.
# ---------------------------------------------------------------------------

def test_pricing_tables_created_fresh():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view');")
    }
    for t in (
        "retailers", "retailer_stores", "retailer_products", "price_observations",
        "search_cache", "canonical_materials", "material_matches", "price_book_items",
        "labor_rates", "labor_rate_history", "pricing_jobs",
    ):
        assert t in tables, f"missing table {t}"
    assert conn.execute(
        "SELECT sqlite_compileoption_used('ENABLE_FTS5');"
    ).fetchone()[0] == 1
    assert "product_search_fts" in tables
    fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
    assert fk_violations == []


def test_estimates_property_id_fk_present_on_fresh_db():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='estimates';"
    ).fetchone()["sql"]
    assert "REFERENCES properties(id)" in sql


def test_estimate_line_items_pricing_fks_present_on_fresh_db():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='estimate_line_items';"
    ).fetchone()["sql"]
    for target in ("price_book_items(id)", "retailer_products(id)", "price_observations(id)", "labor_rates(id)"):
        assert f"REFERENCES {target}" in sql
    trigger_count = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND tbl_name='estimate_line_items';"
    ).fetchone()[0]
    assert trigger_count == 3


def test_estimate_line_items_schema_and_v2_sql_column_sets_match():
    """Anti-drift check: _SCHEMA_SQL's `estimate_line_items` column set and
    _ESTIMATE_LINE_ITEMS_V2_SQL's column set (the two duplicated DDL blocks
    database.py's own comments say must be kept in sync) must be identical."""
    from restoricon_core.database import _SCHEMA_SQL, _ESTIMATE_LINE_ITEMS_V2_SQL

    conn_a = sqlite3.connect(":memory:")
    conn_a.executescript(_SCHEMA_SQL)
    schema_cols = {row[1] for row in conn_a.execute("PRAGMA table_info(estimate_line_items);")}
    conn_a.close()

    conn_b = sqlite3.connect(":memory:")
    conn_b.executescript(_ESTIMATE_LINE_ITEMS_V2_SQL)
    v2_cols = {row[1] for row in conn_b.execute("PRAGMA table_info(estimate_line_items);")}
    conn_b.close()

    assert schema_cols == v2_cols


def _strip_fk_clause(create_sql: str, temp_name: str, fk_clause: str) -> str:
    """Helper: rewrite a table's stored CREATE TABLE text under a new
    table name with one trailing FK clause (`,\\n    FOREIGN KEY ...`)
    removed, to synthesize the pre-this-round legacy shape for a
    migration test."""
    renamed = create_sql.replace(
        create_sql.split("(", 1)[0], f"CREATE TABLE {temp_name} ", 1
    )
    stripped = renamed.replace(f",\n    {fk_clause}\n)", "\n)")
    assert fk_clause not in stripped, "FK clause strip failed -- text drifted"
    return stripped


def test_estimates_property_id_fk_migration_on_v2_shaped_legacy_db(tmp_path):
    """The real production DB today: already rebuilt to B9.1's v2 shape
    (has workflow_status) but still missing the property_id FK (this
    round's fix target) -- exercises _migrate_estimates_property_id_fk()."""
    db_path = tmp_path / "v2_no_property_fk.db"
    db = DatabaseManager(str(db_path))
    conn = db.get_connection()
    now = "2026-01-01T00:00:00Z"

    conn.execute(
        "INSERT INTO customers (first_name, last_name, created_at) VALUES ('Jane', 'Doe', ?);",
        (now,),
    )
    customer_id = conn.execute("SELECT id FROM customers;").fetchone()[0]
    conn.commit()

    old_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='estimates';"
    ).fetchone()[0]
    legacy_sql = _strip_fk_clause(
        old_sql, "_legacy_estimates",
        "FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE SET NULL",
    )

    conn.execute("PRAGMA foreign_keys = OFF;")
    with conn:
        conn.execute("BEGIN IMMEDIATE;")
        conn.execute("DROP TABLE IF EXISTS _legacy_estimates;")
        conn.execute(legacy_sql)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(estimates);")]
        col_list = ", ".join(cols)
        conn.execute(
            f"INSERT INTO _legacy_estimates ({col_list}) SELECT {col_list} FROM estimates;"
        )
        conn.execute("DROP TABLE estimates;")
        conn.execute("ALTER TABLE _legacy_estimates RENAME TO estimates;")
        conn.execute(
            f"INSERT INTO estimates (estimate_number, customer_id, created_at, updated_at) "
            f"VALUES ('EST-LEGACY-1', {customer_id}, '{now}', '{now}');"
        )
    conn.execute("PRAGMA foreign_keys = ON;")
    assert "REFERENCES properties(id)" not in conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='estimates';"
    ).fetchone()[0]
    db.close()

    db2 = DatabaseManager(str(db_path))
    conn2 = db2.get_connection()
    new_sql = conn2.execute(
        "SELECT sql FROM sqlite_master WHERE name='estimates';"
    ).fetchone()[0]
    assert "REFERENCES properties(id)" in new_sql
    row = conn2.execute(
        "SELECT customer_id FROM estimates WHERE estimate_number='EST-LEGACY-1';"
    ).fetchone()
    assert row["customer_id"] == customer_id
    fk_violations = conn2.execute("PRAGMA foreign_key_check;").fetchall()
    assert fk_violations == []
    db2.close()

    # Idempotent third open.
    db3 = DatabaseManager(str(db_path))
    conn3 = db3.get_connection()
    assert "REFERENCES properties(id)" in conn3.execute(
        "SELECT sql FROM sqlite_master WHERE name='estimates';"
    ).fetchone()[0]
    db3.close()


def _legacy_estimate_line_items_sql(create_sql: str) -> str:
    renamed = create_sql.replace("CREATE TABLE estimate_line_items (", "CREATE TABLE _legacy_eli (", 1)
    stripped = renamed.replace(
        ",\n    FOREIGN KEY (price_book_item_id) REFERENCES price_book_items(id) ON DELETE SET NULL,\n"
        "    FOREIGN KEY (retailer_product_id) REFERENCES retailer_products(id) ON DELETE SET NULL,\n"
        "    FOREIGN KEY (price_observation_id) REFERENCES price_observations(id) ON DELETE SET NULL,\n"
        "    FOREIGN KEY (labor_rate_id) REFERENCES labor_rates(id) ON DELETE SET NULL\n)",
        "\n)",
    )
    assert "REFERENCES price_book_items(id)" not in stripped, "FK clause strip failed -- text drifted"
    return stripped


def _downgrade_estimate_line_items_to_legacy(conn) -> None:
    """Rebuild `estimate_line_items` to its pre-this-round shape (no
    pricing FKs) IN PLACE, recreating the 3 locked-immutability triggers
    on the downgraded table -- a real pre-round production DB already has
    those triggers (from B9.1), so a faithful legacy-shape simulation must
    carry them forward too."""
    old_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='estimate_line_items';"
    ).fetchone()[0]
    legacy_sql = _legacy_estimate_line_items_sql(old_sql)
    conn.execute("PRAGMA foreign_keys = OFF;")
    with conn:
        conn.execute("BEGIN IMMEDIATE;")
        conn.execute("DROP TABLE IF EXISTS _legacy_eli;")
        conn.execute(legacy_sql)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(estimate_line_items);")]
        col_list = ", ".join(cols)
        conn.execute(
            f"INSERT INTO _legacy_eli ({col_list}) SELECT {col_list} FROM estimate_line_items;"
        )
        conn.execute("DROP TABLE estimate_line_items;")
        conn.execute("ALTER TABLE _legacy_eli RENAME TO estimate_line_items;")
        for name, event, ref, msg in (
            ("trg_estimate_line_items_locked_update", "UPDATE", "OLD", "cannot modify a line on a locked version"),
            ("trg_estimate_line_items_locked_insert", "INSERT", "NEW", "cannot add a line to a locked version"),
            ("trg_estimate_line_items_locked_delete", "DELETE", "OLD", "cannot remove a line from a locked version"),
        ):
            conn.execute(
                f"CREATE TRIGGER {name} BEFORE {event} ON estimate_line_items "
                f"FOR EACH ROW WHEN (SELECT is_locked FROM estimate_versions WHERE id = {ref}.estimate_version_id) = 1 "
                f"BEGIN SELECT RAISE(ABORT, 'estimate_line_items: {msg}'); END;"
            )
    conn.execute("PRAGMA foreign_keys = ON;")


def test_estimate_line_items_pricing_fk_migration_preserves_triggers_and_data(tmp_path):
    db_path = tmp_path / "legacy_eli.db"
    db = DatabaseManager(str(db_path))
    conn = db.get_connection()
    now = "2026-01-01T00:00:00Z"

    conn.execute("INSERT INTO customers (first_name, last_name, created_at) VALUES ('Jane', 'Doe', ?);", (now,))
    customer_id = conn.execute("SELECT id FROM customers;").fetchone()[0]
    conn.execute(
        "INSERT INTO estimates (estimate_number, customer_id, created_at, updated_at) VALUES ('EST-1', ?, ?, ?);",
        (customer_id, now, now),
    )
    estimate_id = conn.execute("SELECT id FROM estimates;").fetchone()[0]
    conn.execute(
        "INSERT INTO estimate_versions (estimate_id, version_number, calc_engine_version, created_at) "
        "VALUES (?, 1, 1, ?);",
        (estimate_id, now),
    )
    version_id = conn.execute("SELECT id FROM estimate_versions;").fetchone()[0]
    conn.commit()

    _downgrade_estimate_line_items_to_legacy(conn)

    trigger_count_before = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND tbl_name='estimate_line_items';"
    ).fetchone()[0]
    assert trigger_count_before == 3
    assert "REFERENCES price_book_items(id)" not in conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='estimate_line_items';"
    ).fetchone()[0]

    conn.execute(
        "INSERT INTO estimate_line_items (estimate_version_id, line_type, description, created_at, updated_at) "
        "VALUES (?, 'material', 'test line', ?, ?);",
        (version_id, now, now),
    )
    conn.commit()
    line_item_id = conn.execute("SELECT id FROM estimate_line_items;").fetchone()[0]
    db.close()

    db2 = DatabaseManager(str(db_path))
    conn2 = db2.get_connection()
    new_sql = conn2.execute(
        "SELECT sql FROM sqlite_master WHERE name='estimate_line_items';"
    ).fetchone()[0]
    for target in ("price_book_items(id)", "retailer_products(id)", "price_observations(id)", "labor_rates(id)"):
        assert f"REFERENCES {target}" in new_sql
    trigger_count_after = conn2.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND tbl_name='estimate_line_items';"
    ).fetchone()[0]
    assert trigger_count_after == 3
    row = conn2.execute(
        "SELECT description FROM estimate_line_items WHERE id = ?;", (line_item_id,)
    ).fetchone()
    assert row["description"] == "test line"
    fk_violations = conn2.execute("PRAGMA foreign_key_check;").fetchall()
    assert fk_violations == []

    # The locked-immutability trigger must still fire post-rebuild.
    conn2.execute(
        "UPDATE estimate_versions SET is_locked = 1, locked_at = ?, locked_reason = 'sent' WHERE id = ?;",
        (now, version_id),
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn2.execute(
            "UPDATE estimate_line_items SET description = 'changed' WHERE id = ?;", (line_item_id,)
        )
    db2.close()

    db3 = DatabaseManager(str(db_path))
    conn3 = db3.get_connection()
    assert "REFERENCES price_book_items(id)" in conn3.execute(
        "SELECT sql FROM sqlite_master WHERE name='estimate_line_items';"
    ).fetchone()[0]
    db3.close()


def test_estimate_line_items_pricing_fk_migration_dangling_id_preflight_raises(tmp_path):
    """Constructs a case where the pre-flight dangling-id check should
    fire (a non-null labor_rate_id already present before the migration
    runs) and confirms it raises rather than silently proceeding."""
    db_path = tmp_path / "dangling_eli.db"
    db = DatabaseManager(str(db_path))
    conn = db.get_connection()
    now = "2026-01-01T00:00:00Z"

    conn.execute("INSERT INTO customers (first_name, last_name, created_at) VALUES ('Jane', 'Doe', ?);", (now,))
    customer_id = conn.execute("SELECT id FROM customers;").fetchone()[0]
    conn.execute(
        "INSERT INTO estimates (estimate_number, customer_id, created_at, updated_at) VALUES ('EST-1', ?, ?, ?);",
        (customer_id, now, now),
    )
    estimate_id = conn.execute("SELECT id FROM estimates;").fetchone()[0]
    conn.execute(
        "INSERT INTO estimate_versions (estimate_id, version_number, calc_engine_version, created_at) "
        "VALUES (?, 1, 1, ?);",
        (estimate_id, now),
    )
    version_id = conn.execute("SELECT id FROM estimate_versions;").fetchone()[0]
    conn.commit()

    _downgrade_estimate_line_items_to_legacy(conn)
    conn.execute(
        "INSERT INTO estimate_line_items (estimate_version_id, line_type, created_at, updated_at, labor_rate_id) "
        "VALUES (?, 'labor', ?, ?, 999999);",
        (version_id, now, now),
    )
    conn.commit()

    with pytest.raises(RuntimeError, match="dangling|non-null"):
        db._migrate_estimate_line_items_pricing_fks()
    db.close()


# ---------------------------------------------------------------------------
# Code-reviewer round, 2026-09-30: CHANGES-REQUESTED fixes for the critical
# commit-before-raise finding, the narrowed dangling-id check, and the
# `_migrate_estimates_table_v2()` pass-1 ordering hole.
# ---------------------------------------------------------------------------

def test_estimates_property_id_fk_migration_orphaned_id_raises_before_any_commit(tmp_path):
    """The Critical finding's exact repro scenario: a v2-shaped `estimates`
    DB (has workflow_status), `properties` table present, and one
    `estimates` row whose property_id does not resolve to any real
    properties row. The NEW pre-flight check must raise BEFORE the rebuild
    touches anything -- this test proves that by re-opening the raw file
    with a fresh, non-DatabaseManager connection afterwards and confirming
    `estimates`' stored DDL/FK clause is completely UNCHANGED (not just
    that an exception was raised)."""
    db_path = tmp_path / "v2_orphan_property.db"
    db = DatabaseManager(str(db_path))
    conn = db.get_connection()
    now = "2026-01-01T00:00:00Z"

    conn.execute(
        "INSERT INTO customers (first_name, last_name, created_at) VALUES ('Jane', 'Doe', ?);", (now,)
    )
    customer_id = conn.execute("SELECT id FROM customers;").fetchone()[0]
    conn.commit()

    # Downgrade estimates to "v2-shaped but property_id FK-less" (the real
    # production DB's exact shape today), then insert an orphaned row --
    # mirrors test_estimates_property_id_fk_migration_on_v2_shaped_legacy_db
    # above, plus the orphaned id.
    old_sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='estimates';").fetchone()[0]
    legacy_sql = _strip_fk_clause(
        old_sql, "_legacy_estimates",
        "FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE SET NULL",
    )
    conn.execute("PRAGMA foreign_keys = OFF;")
    with conn:
        conn.execute("BEGIN IMMEDIATE;")
        conn.execute("DROP TABLE IF EXISTS _legacy_estimates;")
        conn.execute(legacy_sql)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(estimates);")]
        col_list = ", ".join(cols)
        conn.execute(
            f"INSERT INTO _legacy_estimates ({col_list}) SELECT {col_list} FROM estimates;"
        )
        conn.execute("DROP TABLE estimates;")
        conn.execute("ALTER TABLE _legacy_estimates RENAME TO estimates;")
        conn.execute(
            "INSERT INTO estimates (estimate_number, customer_id, property_id, created_at, updated_at) "
            "VALUES ('EST-ORPHAN-1', ?, 999999, ?, ?);",
            (customer_id, now, now),
        )
    conn.execute("PRAGMA foreign_keys = ON;")
    assert "REFERENCES properties(id)" not in conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='estimates';"
    ).fetchone()[0]
    ddl_before = conn.execute("SELECT sql FROM sqlite_master WHERE name='estimates';").fetchone()[0]
    db.close()

    with pytest.raises(RuntimeError, match="does not resolve to any real properties row"):
        DatabaseManager(str(db_path))

    # Read back with a RAW connection (not DatabaseManager -- reopening via
    # DatabaseManager would re-run the migration and raise again) to prove
    # no partial/committed damage occurred.
    raw = sqlite3.connect(str(db_path))
    raw.row_factory = sqlite3.Row
    ddl_after = raw.execute("SELECT sql FROM sqlite_master WHERE name='estimates';").fetchone()["sql"]
    assert ddl_after == ddl_before
    assert "REFERENCES properties(id)" not in ddl_after
    row = raw.execute(
        "SELECT property_id FROM estimates WHERE estimate_number = 'EST-ORPHAN-1';"
    ).fetchone()
    assert row is not None
    assert row["property_id"] == 999999
    raw.close()


def test_migrate_estimates_table_v2_ordering_hole_closed_when_properties_missing(tmp_path):
    """A genuinely legacy DB missing BOTH workflow_status (pre-v2) AND
    properties (pre-B8.1), with a NULL property_id (no dangling data) --
    proves _migrate_estimates_table_v2()'s pass-1 rebuild no longer embeds
    a FK against a not-yet-existing `properties` table, and that
    `_migrate_estimates_property_id_fk()` correctly attaches the FK in
    pass 2 once `properties` exists, ending in a fully v2-shaped,
    FK-attached, violation-free `estimates` table."""
    db_path = tmp_path / "pre_v2_pre_properties.db"
    db = DatabaseManager(str(db_path))
    conn = db.get_connection()
    now = "2026-01-01T00:00:00Z"

    conn.execute(
        "INSERT INTO customers (first_name, last_name, created_at) VALUES ('Jane', 'Doe', ?);", (now,)
    )
    customer_id = conn.execute("SELECT id FROM customers;").fetchone()[0]
    conn.commit()

    # Strip the property_id FK (same helper as the v2-shaped test above),
    # insert a NULL-property_id row, then strip workflow_status/
    # internal_review_required too (down to a genuinely pre-v2 shape), and
    # drop `properties` entirely (simulating a pre-B8.1 DB file).
    old_sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='estimates';").fetchone()[0]
    legacy_sql = _strip_fk_clause(
        old_sql, "_legacy_estimates",
        "FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE SET NULL",
    )
    conn.execute("PRAGMA foreign_keys = OFF;")
    with conn:
        conn.execute("BEGIN IMMEDIATE;")
        conn.execute("DROP TABLE IF EXISTS _legacy_estimates;")
        conn.execute(legacy_sql)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(estimates);")]
        col_list = ", ".join(cols)
        conn.execute(
            f"INSERT INTO _legacy_estimates ({col_list}) SELECT {col_list} FROM estimates;"
        )
        conn.execute("DROP TABLE estimates;")
        conn.execute("ALTER TABLE _legacy_estimates RENAME TO estimates;")
        conn.execute(
            "INSERT INTO estimates (estimate_number, customer_id, created_at, updated_at) "
            "VALUES ('EST-CLEAN-1', ?, ?, ?);",
            (customer_id, now, now),
        )
        # Strip workflow_status + internal_review_required to reach a
        # genuinely pre-v2 shape.
        cur_sql = conn.execute("SELECT sql FROM sqlite_master WHERE name='estimates';").fetchone()[0]
        pre_v2_sql = cur_sql.replace(cur_sql.split("(", 1)[0], "CREATE TABLE _pre_v2_estimates ", 1)
        import re as _re
        pre_v2_sql = _re.sub(
            r"\s*workflow_status TEXT NOT NULL DEFAULT 'DRAFT' CHECK\(workflow_status IN \([^)]*\)\),\n",
            "\n", pre_v2_sql,
        )
        pre_v2_sql = _re.sub(
            r"\s*internal_review_required INTEGER NOT NULL DEFAULT 0 "
            r"CHECK\(internal_review_required IN \(0, 1\)\),\n",
            "\n", pre_v2_sql,
        )
        assert "workflow_status" not in pre_v2_sql, "strip failed -- text drifted"
        conn.execute("DROP TABLE IF EXISTS _pre_v2_estimates;")
        conn.execute(pre_v2_sql)
        cols2 = [
            r["name"] for r in conn.execute("PRAGMA table_info(estimates);")
            if r["name"] not in ("workflow_status", "internal_review_required")
        ]
        col_list2 = ", ".join(cols2)
        conn.execute(
            f"INSERT INTO _pre_v2_estimates ({col_list2}) SELECT {col_list2} FROM estimates;"
        )
        conn.execute("DROP TABLE estimates;")
        conn.execute("ALTER TABLE _pre_v2_estimates RENAME TO estimates;")
        conn.execute("DROP TABLE IF EXISTS properties;")
    conn.execute("PRAGMA foreign_keys = ON;")
    ddl = conn.execute("SELECT sql FROM sqlite_master WHERE name='estimates';").fetchone()[0]
    assert "workflow_status" not in ddl
    assert conn.execute("SELECT name FROM sqlite_master WHERE name='properties';").fetchone() is None
    db.close()

    # Must NOT raise -- this is exactly what used to commit a broken
    # rebuild (FK against a not-yet-existing `properties` table) before the
    # fix.
    db2 = DatabaseManager(str(db_path))
    conn2 = db2.get_connection()
    new_sql = conn2.execute("SELECT sql FROM sqlite_master WHERE name='estimates';").fetchone()[0]
    assert "workflow_status" in new_sql
    assert "REFERENCES properties(id)" in new_sql
    row = conn2.execute(
        "SELECT property_id FROM estimates WHERE estimate_number = 'EST-CLEAN-1';"
    ).fetchone()
    assert row is not None
    assert row["property_id"] is None
    fk_violations = conn2.execute("PRAGMA foreign_key_check;").fetchall()
    assert fk_violations == []
    db2.close()


def _insert_minimal_pricing_targets(conn, now: str) -> dict:
    """Insert one minimal valid row into each of the 4 pricing FK target
    tables, returning their ids, for tests that need REAL resolvable ids
    (not just orphaned ones) to prove the narrowed check doesn't block
    legitimate data."""
    conn.execute(
        "INSERT INTO retailers (code, display_name, created_at, updated_at) "
        "VALUES ('home_depot', 'Home Depot', ?, ?);", (now, now),
    )
    conn.execute(
        "INSERT INTO retailer_products (retailer_code, retailer_sku, title, first_seen_at, created_at, updated_at) "
        "VALUES ('home_depot', 'SKU-1', 'Test Product', 0, ?, ?);", (now, now),
    )
    retailer_product_id = conn.execute("SELECT id FROM retailer_products;").fetchone()[0]
    conn.execute(
        "INSERT INTO price_observations (retailer_product_id, price_cents, observed_at, source) "
        "VALUES (?, 1000, 0, 'manual');", (retailer_product_id,),
    )
    price_observation_id = conn.execute("SELECT id FROM price_observations;").fetchone()[0]
    conn.execute(
        "INSERT INTO canonical_materials (category, display_name, attributes_json, created_at, updated_at) "
        "VALUES ('material', 'Test Material', '[]', ?, ?);", (now, now),
    )
    canonical_material_id = conn.execute("SELECT id FROM canonical_materials;").fetchone()[0]
    conn.execute(
        "INSERT INTO price_book_items (canonical_material_id, description, unit, unit_cost_cents, created_at, updated_at) "
        "VALUES (?, 'Test Item', 'ea', 500, ?, ?);", (canonical_material_id, now, now),
    )
    price_book_item_id = conn.execute("SELECT id FROM price_book_items;").fetchone()[0]
    conn.execute(
        "INSERT INTO labor_rates (labor_type, rate_type, cost_rate_cents, bill_rate_cents, effective_date, created_at, updated_at) "
        "VALUES ('general', 'hourly', 3000, 6000, ?, ?, ?);", (now, now, now),
    )
    labor_rate_id = conn.execute("SELECT id FROM labor_rates;").fetchone()[0]
    return {
        "price_book_item_id": price_book_item_id,
        "retailer_product_id": retailer_product_id,
        "price_observation_id": price_observation_id,
        "labor_rate_id": labor_rate_id,
    }


def test_estimate_line_items_pricing_fk_migration_allows_valid_resolvable_ids(tmp_path):
    """Narrowed-check regression test: a legacy `estimate_line_items` row
    with REAL, resolvable ids in all 4 pricing columns (not just NULLs)
    must migrate successfully -- the original blunt "any non-null" check
    would have wrongly aborted this, even though nothing is actually
    dangling."""
    db_path = tmp_path / "legacy_eli_valid_ids.db"
    db = DatabaseManager(str(db_path))
    conn = db.get_connection()
    now = "2026-01-01T00:00:00Z"

    conn.execute("INSERT INTO customers (first_name, last_name, created_at) VALUES ('Jane', 'Doe', ?);", (now,))
    customer_id = conn.execute("SELECT id FROM customers;").fetchone()[0]
    conn.execute(
        "INSERT INTO estimates (estimate_number, customer_id, created_at, updated_at) VALUES ('EST-1', ?, ?, ?);",
        (customer_id, now, now),
    )
    estimate_id = conn.execute("SELECT id FROM estimates;").fetchone()[0]
    conn.execute(
        "INSERT INTO estimate_versions (estimate_id, version_number, calc_engine_version, created_at) "
        "VALUES (?, 1, 1, ?);",
        (estimate_id, now),
    )
    version_id = conn.execute("SELECT id FROM estimate_versions;").fetchone()[0]
    ids = _insert_minimal_pricing_targets(conn, now)
    conn.commit()

    _downgrade_estimate_line_items_to_legacy(conn)
    conn.execute(
        "INSERT INTO estimate_line_items ("
        "estimate_version_id, line_type, created_at, updated_at, "
        "price_book_item_id, retailer_product_id, price_observation_id, labor_rate_id"
        ") VALUES (?, 'material', ?, ?, ?, ?, ?, ?);",
        (
            version_id, now, now,
            ids["price_book_item_id"], ids["retailer_product_id"],
            ids["price_observation_id"], ids["labor_rate_id"],
        ),
    )
    conn.commit()
    line_item_id = conn.execute("SELECT id FROM estimate_line_items;").fetchone()[0]

    # Must NOT raise.
    db._migrate_estimate_line_items_pricing_fks()

    new_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='estimate_line_items';"
    ).fetchone()[0]
    assert "REFERENCES price_book_items(id)" in new_sql
    row = conn.execute(
        "SELECT price_book_item_id, labor_rate_id FROM estimate_line_items WHERE id = ?;", (line_item_id,)
    ).fetchone()
    assert row["price_book_item_id"] == ids["price_book_item_id"]
    assert row["labor_rate_id"] == ids["labor_rate_id"]
    fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
    assert fk_violations == []
    db.close()


@pytest.mark.parametrize(
    "dangling_column", ["price_book_item_id", "retailer_product_id", "price_observation_id", "labor_rate_id"]
)
def test_estimate_line_items_pricing_fk_migration_per_column_dangling_id_raises(tmp_path, dangling_column):
    """Narrowed-check regression test, one per column: an orphaned id in
    ONLY that one column (the other 3 NULL) must still raise -- confirms
    the narrowed LEFT JOIN/NOT EXISTS check covers each of the 4 columns
    individually, not just a blunt combined check."""
    db_path = tmp_path / f"legacy_eli_dangling_{dangling_column}.db"
    db = DatabaseManager(str(db_path))
    conn = db.get_connection()
    now = "2026-01-01T00:00:00Z"

    conn.execute("INSERT INTO customers (first_name, last_name, created_at) VALUES ('Jane', 'Doe', ?);", (now,))
    customer_id = conn.execute("SELECT id FROM customers;").fetchone()[0]
    conn.execute(
        "INSERT INTO estimates (estimate_number, customer_id, created_at, updated_at) VALUES ('EST-1', ?, ?, ?);",
        (customer_id, now, now),
    )
    estimate_id = conn.execute("SELECT id FROM estimates;").fetchone()[0]
    conn.execute(
        "INSERT INTO estimate_versions (estimate_id, version_number, calc_engine_version, created_at) "
        "VALUES (?, 1, 1, ?);",
        (estimate_id, now),
    )
    version_id = conn.execute("SELECT id FROM estimate_versions;").fetchone()[0]
    conn.commit()

    _downgrade_estimate_line_items_to_legacy(conn)
    conn.execute(
        f"INSERT INTO estimate_line_items (estimate_version_id, line_type, created_at, updated_at, {dangling_column}) "
        f"VALUES (?, 'material', ?, ?, 999999);",
        (version_id, now, now),
    )
    conn.commit()

    with pytest.raises(RuntimeError, match=dangling_column):
        db._migrate_estimate_line_items_pricing_fks()
    db.close()
