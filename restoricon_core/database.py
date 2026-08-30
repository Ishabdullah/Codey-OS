"""
Database connection and schema initialization for Restoricon Core.
Provides canonical SQLite storage with WAL mode, strict foreign keys,
and transactional safety.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

DEFAULT_DB_PATH = Path(
    os.getenv("RESTORICON_DB_PATH", os.path.expanduser("~/.codey_restoricon/core.db"))
)

_SCHEMA_SQL = """
-- Users / Employees table (Authentication and RBAC)
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL COLLATE NOCASE,
    phone TEXT,
    role TEXT NOT NULL CHECK(role IN ('admin', 'manager', 'sales', 'project_manager', 'technician', 'ai_agent', 'customer')),
    department TEXT,
    customer_id INTEGER, -- Only populated if role == 'customer'
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL
);

-- Active API sessions / tokens
CREATE TABLE IF NOT EXISTS api_tokens (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    is_revoked INTEGER NOT NULL DEFAULT 0 CHECK(is_revoked IN (0, 1)),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Customers / Accounts. external_id (NEW-212/NEW-232, 2026-08-27, Ish-
-- approved) holds an external system's own string ID (e.g. Aigentik-CLI's
-- contact ID) for idempotent migration/write-through matching, same
-- purpose as subcontractors.external_id. Added without an inline UNIQUE
-- constraint -- SQLite's ALTER TABLE ADD COLUMN rejects UNIQUE columns, so
-- uniqueness is enforced via the separate idx_customers_external_id
-- unique index below instead, kept identical between fresh and migrated
-- DBs (see _migrate_schema()).
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    company_name TEXT,
    phone TEXT,
    email TEXT COLLATE NOCASE,
    mailing_address TEXT,
    service_address TEXT,
    customer_type TEXT NOT NULL DEFAULT 'residential' CHECK(customer_type IN ('residential', 'commercial')),
    customer_source TEXT,
    assigned_user_id INTEGER,
    status TEXT NOT NULL DEFAULT 'lead' CHECK(status IN ('lead', 'prospect', 'active', 'past', 'lost')),
    tags_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    custom_fields_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    last_contact_at TEXT,
    next_followup_at TEXT,
    FOREIGN KEY (assigned_user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Leads. external_id (NEW-212/NEW-232, 2026-08-27) -- see customers'
-- external_id comment above for why it has no inline UNIQUE.
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT,
    customer_id INTEGER,
    source TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new', 'contacted', 'qualified', 'unqualified', 'converted', 'lost')),
    score INTEGER NOT NULL DEFAULT 0,
    estimated_value REAL NOT NULL DEFAULT 0.0,
    assigned_user_id INTEGER,
    first_contact_at TEXT,
    last_contact_at TEXT,
    next_followup_at TEXT,
    notes TEXT,
    lost_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
    FOREIGN KEY (assigned_user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Sales Pipeline / Opportunities
CREATE TABLE IF NOT EXISTS opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    project_id INTEGER,
    title TEXT NOT NULL,
    estimated_value REAL NOT NULL DEFAULT 0.0,
    probability REAL NOT NULL DEFAULT 0.0,
    pipeline_stage TEXT NOT NULL DEFAULT 'New Lead' CHECK(pipeline_stage IN ('New Lead', 'Contacted', 'Appointment Set', 'Estimate', 'Proposal Sent', 'Negotiating', 'Won', 'Lost')),
    expected_close_date TEXT,
    assigned_user_id INTEGER,
    competitor_info TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (assigned_user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Projects / Jobs
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    property_address TEXT NOT NULL,
    project_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'planning' CHECK(status IN ('planning', 'scheduled', 'in_progress', 'on_hold', 'completed', 'cancelled')),
    start_date TEXT,
    expected_completion TEXT,
    actual_completion TEXT,
    project_manager_id INTEGER,
    assigned_employees_json TEXT NOT NULL DEFAULT '[]',
    subcontractors_json TEXT NOT NULL DEFAULT '[]',
    scope_of_work TEXT,
    estimated_cost REAL NOT NULL DEFAULT 0.0,
    contract_amount REAL NOT NULL DEFAULT 0.0,
    actual_cost REAL NOT NULL DEFAULT 0.0,
    profit REAL NOT NULL DEFAULT 0.0,
    notes TEXT,
    warranty_info TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE RESTRICT,
    FOREIGN KEY (project_manager_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Estimates / Quotes
CREATE TABLE IF NOT EXISTS estimates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estimate_number TEXT UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL,
    project_id INTEGER,
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

-- Proposals / Contracts
CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_number TEXT UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL,
    project_id INTEGER,
    estimate_id INTEGER,
    title TEXT NOT NULL,
    template_name TEXT,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'sent', 'signed', 'expired', 'superseded')),
    customer_signed_at TEXT,
    customer_signature_data TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE RESTRICT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (estimate_id) REFERENCES estimates(id) ON DELETE SET NULL
);

-- Documents
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER,
    project_id INTEGER,
    document_type TEXT NOT NULL CHECK(document_type IN ('contract', 'estimate', 'proposal', 'invoice', 'receipt', 'insurance', 'permit', 'photo', 'pdf', 'upload', 'warranty')),
    title TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL DEFAULT 0,
    mime_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    tags_json TEXT NOT NULL DEFAULT '[]',
    permissions_json TEXT NOT NULL DEFAULT '[]',
    expiration_date TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

-- Billing / Invoices / Payments
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL,
    project_id INTEGER,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'sent', 'partially_paid', 'paid', 'overdue', 'void')),
    amount REAL NOT NULL DEFAULT 0.0,
    deposit_amount REAL NOT NULL DEFAULT 0.0,
    balance_due REAL NOT NULL DEFAULT 0.0,
    due_date TEXT,
    payments_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE RESTRICT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

-- Communication History (DAY-ONE-OR-NEVER, STRICTLY APPEND-ONLY).
-- provider_message_id (NEW-233, 2026-08-27, Ish-approved -- "reliable
-- log" requirement) holds the originating channel's own message
-- identifier (e.g. the IMAP/RFC 5322 Message-ID header for email and
-- Google-Voice-via-email, both of which are captured today by
-- email-provider.js's parseMessage()) so a write-through call can be
-- retried after a failure (Core unreachable, timeout) or fired again by
-- a reprocessed source message (email-provider.js's documented
-- \Seen-flag race, see NEW-233) without creating a duplicate row. It is
-- nullable because internal_note/ai_conversation/phone/voicemail rows
-- have no natural external message id -- see idx_comms_provider_message_id
-- below (a partial unique index, not an inline UNIQUE column) for why.
CREATE TABLE IF NOT EXISTS communication_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    channel TEXT NOT NULL CHECK(channel IN ('phone', 'email', 'sms', 'voicemail', 'web_chat', 'social', 'internal_note', 'ai_conversation', 'appointment')),
    direction TEXT NOT NULL CHECK(direction IN ('inbound', 'outbound', 'internal')),
    subject TEXT,
    content TEXT NOT NULL,
    actor_id INTEGER,
    actor_role TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK(actor_type IN ('human', 'agent')),
    customer_id INTEGER,
    project_id INTEGER,
    opportunity_id INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    provider_message_id TEXT,
    FOREIGN KEY (actor_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE SET NULL
);

-- Subcontractors (recruitment/qualification pipeline — B2/NEW-209 schema
-- expansion, per Ish's 2026-08-27 decision to build all five of
-- Aigentik-CLI's real data shapes now rather than defer four of them).
-- external_id/contact_external_id hold Aigentik's own string IDs
-- (e.g. "sub_0001", "contact_0197") so a future migration script can be
-- re-run idempotently against this table without creating duplicates.
CREATE TABLE IF NOT EXISTS subcontractors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE,
    contact_external_id TEXT,
    company_name TEXT NOT NULL,
    legal_name TEXT,
    dba TEXT,
    contact_name TEXT,
    title TEXT,
    phone TEXT,
    email TEXT COLLATE NOCASE,
    website TEXT,
    primary_trade TEXT,
    secondary_trades_json TEXT NOT NULL DEFAULT '[]',
    service_area TEXT,
    years_in_business INTEGER,
    crew_size INTEGER,
    residential_experience TEXT,
    commercial_experience TEXT,
    typical_project_size TEXT,
    availability TEXT,
    emergency_availability TEXT,
    license_required INTEGER CHECK(license_required IN (0, 1) OR license_required IS NULL),
    license_type TEXT,
    license_number TEXT,
    license_expiration TEXT,
    license_status TEXT,
    general_liability TEXT,
    workers_comp TEXT,
    coi_received INTEGER NOT NULL DEFAULT 0 CHECK(coi_received IN (0, 1)),
    coi_expiration TEXT,
    additional_insured_status TEXT,
    insurance_status TEXT,
    w9_received INTEGER NOT NULL DEFAULT 0 CHECK(w9_received IN (0, 1)),
    msa_sent INTEGER NOT NULL DEFAULT 0 CHECK(msa_sent IN (0, 1)),
    msa_signed INTEGER NOT NULL DEFAULT 0 CHECK(msa_signed IN (0, 1)),
    references_json TEXT NOT NULL DEFAULT '[]',
    portfolio_url TEXT,
    qualification_status TEXT NOT NULL DEFAULT 'QUALIFICATION_IN_PROGRESS',
    recruitment_step TEXT,
    lead_source TEXT,
    last_contact_at TEXT,
    next_followup_at TEXT,
    contact_attempts INTEGER NOT NULL DEFAULT 0,
    dnc_status INTEGER NOT NULL DEFAULT 0 CHECK(dnc_status IN (0, 1)),
    notes TEXT,
    qualification_data_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Appointments / Calendar (B2/NEW-209 schema expansion). Field names and
-- the negotiate-then-confirm lifecycle (status: negotiating -> confirmed)
-- mirror Aigentik-CLI's calendar.js directly, since Aigentik deliberately
-- never books unilaterally when a requested slot isn't free -- it proposes
-- offered_slots and waits for the other party. customer_id is nullable
-- and only populated when a match to a known Core customer exists.
CREATE TABLE IF NOT EXISTS appointments (
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
    updated_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL
);

-- Automation Rules (B2/NEW-209 schema expansion). Covers both
-- email-rules.json and sms-rules.json in one table (identical field
-- shapes in the source data) distinguished by `channel`. `match_count`
-- is a simple hit counter Aigentik-CLI increments on every rule match --
-- deliberately NOT run through the audit log (see automation_service.py)
-- since that would flood audit_log with a high-frequency, non-business
-- event on every inbound message.
CREATE TABLE IF NOT EXISTS automation_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE,
    channel TEXT NOT NULL CHECK(channel IN ('email', 'sms')),
    description TEXT,
    condition_type TEXT NOT NULL,
    condition_value TEXT NOT NULL,
    action TEXT NOT NULL,
    added_by TEXT,
    match_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Business Profile (B2/NEW-209 schema expansion). Deliberately a
-- singleton table (id fixed to 1 via CHECK) -- Restoricon has exactly one
-- business profile, so this models profile.json's single-object shape
-- rather than allowing multiple rows.
CREATE TABLE IF NOT EXISTS business_profile (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    configured INTEGER NOT NULL DEFAULT 0 CHECK(configured IN (0, 1)),
    aigentik_name TEXT,
    agent_name_set INTEGER NOT NULL DEFAULT 0 CHECK(agent_name_set IN (0, 1)),
    owner_name TEXT,
    business_name TEXT,
    business_description TEXT,
    onboarding_sent INTEGER NOT NULL DEFAULT 0 CHECK(onboarding_sent IN (0, 1)),
    setup_date TEXT,
    updated_at TEXT NOT NULL
);

-- Scheduling configuration (NEW-216, 2026-08-27, Ish-approved "create best
-- place for it"). Deliberately a dedicated singleton table (id fixed to 1
-- via CHECK), same pattern as business_profile, rather than folding these
-- columns into business_profile: business_profile is identity/onboarding
-- data, this is operational scheduling config owned by the same domain as
-- appointments (calendar.js's counterpart, schedule-config.json). Field
-- names (working_hours, not "business hours") are kept as source-system
-- names for migration fidelity, matching how the appointments table
-- mirrored calendar.js's own field names. duration_by_relationship is
-- stored as an opaque JSON blob rather than given its own columns because
-- the live source file has it as `{}` (empty) -- its key shape is
-- currently unknown, so no structure is invented for it here.
CREATE TABLE IF NOT EXISTS schedule_config (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    working_hours_json TEXT NOT NULL DEFAULT '{}',
    default_duration_minutes INTEGER NOT NULL DEFAULT 30,
    buffer_minutes INTEGER NOT NULL DEFAULT 15,
    booking_window_days INTEGER NOT NULL DEFAULT 365,
    duration_by_relationship_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

-- Do-Not-Contact list (B2/NEW-209 schema expansion, DAY-ONE-OR-NEVER
-- permanent-suppression semantics). UNIQUE(type, value) matches
-- do-not-contact.js's own idempotent add-refreshes-existing behavior.
-- SAFETY-RELEVANT: `value` must be stored using the exact same
-- normalization do-not-contact.js uses (email lowercased+trimmed; phone
-- reduced to its last 10 digits) or a suppressed contact could be
-- silently re-contacted because the stored value no longer matches an
-- inbound identifier -- see automation_service.py's normalize_* helpers,
-- which must stay byte-for-byte equivalent to the JS versions.
CREATE TABLE IF NOT EXISTS do_not_contact (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK(type IN ('email', 'phone')),
    value TEXT NOT NULL,
    original TEXT,
    name TEXT,
    reason TEXT,
    source TEXT,
    added_at TEXT NOT NULL,
    UNIQUE(type, value)
);

-- Activity / Audit Log (DAY-ONE-OR-NEVER, STRICTLY APPEND-ONLY)
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    actor_id INTEGER,
    actor_role TEXT NOT NULL,
    actor_type TEXT NOT NULL CHECK(actor_type IN ('human', 'agent')),
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id INTEGER,
    change_summary TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (actor_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Contacts (Aigentik contact memory system)
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT,
    name TEXT,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    phones_json TEXT NOT NULL DEFAULT '[]',
    emails_json TEXT NOT NULL DEFAULT '[]',
    address TEXT,
    relationship TEXT,
    type TEXT NOT NULL DEFAULT 'unknown',
    notes TEXT,
    instructions TEXT,
    reply_behavior TEXT NOT NULL DEFAULT 'auto',
    roles_json TEXT NOT NULL DEFAULT '[]',
    active_role TEXT,
    business_name TEXT,
    trade TEXT,
    trade_raw TEXT,
    licensed INTEGER CHECK(licensed IN (0, 1) OR licensed IS NULL),
    license_number TEXT,
    gl_insurance INTEGER CHECK(gl_insurance IN (0, 1) OR gl_insurance IS NULL),
    wc_insurance INTEGER CHECK(wc_insurance IN (0, 1) OR wc_insurance IS NULL),
    has_tools INTEGER CHECK(has_tools IN (0, 1) OR has_tools IS NULL),
    crew_size INTEGER,
    weekly_capacity TEXT,
    references_json TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT 'auto',
    first_seen TEXT,
    last_contact TEXT,
    contact_count INTEGER NOT NULL DEFAULT 0,
    history_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Indexing for performance
-- NOTE: the unique indexes for customers.external_id / leads.external_id /
-- contacts.external_id / communication_history.provider_message_id are
-- NOT here -- they're created in _migrate_schema() instead, after the ALTER
-- TABLE that adds the column on a pre-existing DB file. Creating them here
-- would run before that ALTER on a legacy DB (executescript runs top-to-bottom
-- in one pass) and fail with "no such column".
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_api_tokens_token ON api_tokens(token);
CREATE INDEX IF NOT EXISTS idx_customers_status ON customers(status);
CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);
CREATE INDEX IF NOT EXISTS idx_leads_customer_id ON leads(customer_id);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_opportunities_customer_id ON opportunities(customer_id);
CREATE INDEX IF NOT EXISTS idx_opportunities_stage ON opportunities(pipeline_stage);
CREATE INDEX IF NOT EXISTS idx_projects_customer_id ON projects(customer_id);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_estimates_customer_id ON estimates(customer_id);
CREATE INDEX IF NOT EXISTS idx_estimates_number ON estimates(estimate_number);
CREATE INDEX IF NOT EXISTS idx_contracts_customer_id ON contracts(customer_id);
CREATE INDEX IF NOT EXISTS idx_invoices_customer_id ON invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_documents_customer_id ON documents(customer_id);
CREATE INDEX IF NOT EXISTS idx_comms_customer_id ON communication_history(customer_id);
CREATE INDEX IF NOT EXISTS idx_comms_project_id ON communication_history(project_id);
CREATE INDEX IF NOT EXISTS idx_comms_timestamp ON communication_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_subcontractors_external_id ON subcontractors(external_id);
CREATE INDEX IF NOT EXISTS idx_subcontractors_qualification_status ON subcontractors(qualification_status);
CREATE INDEX IF NOT EXISTS idx_appointments_customer_id ON appointments(customer_id);
CREATE INDEX IF NOT EXISTS idx_appointments_start_time ON appointments(start_time);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);
CREATE INDEX IF NOT EXISTS idx_automation_rules_channel ON automation_rules(channel);
CREATE INDEX IF NOT EXISTS idx_dnc_type_value ON do_not_contact(type, value);
CREATE INDEX IF NOT EXISTS idx_contacts_type ON contacts(type);
CREATE INDEX IF NOT EXISTS idx_contacts_active_role ON contacts(active_role);
"""

_local = threading.local()
_mem_counter = 0
_mem_lock = threading.Lock()


class DatabaseManager:
    """Manages SQLite database connections, schema setup, and transactions."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        global _mem_counter
        if str(db_path) == ":memory:":
            with _mem_lock:
                _mem_counter += 1
                self.db_path = f"file:restoricon_mem_{_mem_counter}?mode=memory&cache=shared"
                self.is_memory = True
        else:
            self.db_path = str(db_path)
            self.is_memory = False
            self._ensure_db_dir()

        self.init_schema()

    def _ensure_db_dir(self) -> None:
        """Create parent directory if it does not exist."""
        if not self.is_memory:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """Return a thread-local SQLite connection with WAL mode and foreign keys."""
        conn = getattr(_local, f"conn_{self.db_path}", None)
        if conn is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False,
                uri=self.is_memory,
            )
            conn.row_factory = sqlite3.Row
            # Enable foreign keys and WAL mode (if file-based)
            conn.execute("PRAGMA foreign_keys = ON;")
            if not self.is_memory:
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")
            setattr(_local, f"conn_{self.db_path}", conn)
        return conn

    def init_schema(self) -> None:
        """Execute the DDL schema to set up all tables and indexes, then
        run any additive column migrations (see _migrate_schema) needed to
        bring a pre-existing DB file up to the current column set. Fresh
        DBs already have every column via CREATE TABLE, so the migration
        step is a no-op for them; it only does real work against a DB file
        created before a given column existed."""
        conn = self.get_connection()
        with conn:
            conn.executescript(_SCHEMA_SQL)
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        """Additive, idempotent column migrations for existing DB files.

        This project has no schema-versioning mechanism (no PRAGMA
        user_version tracking, no migration table) -- _SCHEMA_SQL's
        `CREATE TABLE IF NOT EXISTS` only ever helps a brand-new DB file;
        it does nothing for a column added to a table that already exists
        on disk. Each entry here must check PRAGMA table_info() before
        attempting `ALTER TABLE ... ADD COLUMN`, since re-running ADD
        COLUMN on a column that already exists raises
        "duplicate column name" and would break every subsequent
        DatabaseManager() call against that file.
        """
        conn = self.get_connection()
        migrations = (
            ("customers", "external_id", "ALTER TABLE customers ADD COLUMN external_id TEXT;"),
            ("leads", "external_id", "ALTER TABLE leads ADD COLUMN external_id TEXT;"),
            (
                "communication_history",
                "provider_message_id",
                "ALTER TABLE communication_history ADD COLUMN provider_message_id TEXT;",
            ),
        )
        with conn:
            for table, column, ddl in migrations:
                existing_columns = {
                    row["name"] for row in conn.execute(f"PRAGMA table_info({table});")
                }
                if column not in existing_columns:
                    conn.execute(ddl)
            # Unique indexes must run after the ALTERs above (see the note
            # in _SCHEMA_SQL's index block for why they can't live there).
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_external_id ON customers(external_id);"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_external_id ON leads(external_id);"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_external_id ON contacts(external_id);"
            )
            # Partial index (WHERE provider_message_id IS NOT NULL): rows
            # with no natural external message id (internal_note,
            # ai_conversation, phone, voicemail) never collide with each
            # other under a bare UNIQUE column, only real, non-null
            # provider ids are deduplicated. record_communication() is
            # responsible for normalizing '' / whitespace-only ids to
            # NULL before insert -- this index alone does not catch an
            # empty-string id, since '' IS NOT NULL is true in SQLite.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_comms_provider_message_id "
                "ON communication_history(provider_message_id) "
                "WHERE provider_message_id IS NOT NULL;"
            )

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager for explicit atomic transactions."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            conn.execute("BEGIN TRANSACTION;")
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def close(self) -> None:
        """Close connection for current thread if open."""
        conn = getattr(_local, f"conn_{self.db_path}", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            setattr(_local, f"conn_{self.db_path}", None)
