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

-- Customers / Accounts
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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

-- Leads
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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

-- Communication History (DAY-ONE-OR-NEVER, STRICTLY APPEND-ONLY)
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
    FOREIGN KEY (actor_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE SET NULL
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

-- Indexing for performance
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
        """Execute the DDL schema to set up all tables and indexes."""
        conn = self.get_connection()
        with conn:
            conn.executescript(_SCHEMA_SQL)

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
