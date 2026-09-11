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
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

DEFAULT_DB_PATH = Path(
    os.getenv("RESTORICON_DB_PATH", os.path.expanduser("~/.codeyOS/restoricon.db"))
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
    custom_permissions_json TEXT NOT NULL DEFAULT '{}',
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
    score_factors_json TEXT NOT NULL DEFAULT '{}',
    property_type TEXT,
    project_scope TEXT,
    urgency_level TEXT,
    insurance_status TEXT,
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
    pipeline_stage TEXT NOT NULL DEFAULT 'new_lead',
    expected_close_date TEXT,
    assigned_user_id INTEGER,
    competitor_info TEXT,
    notes TEXT,
    lost_reason TEXT,
    insurance_carrier TEXT,
    claim_number TEXT,
    adjuster_name TEXT,
    adjuster_phone TEXT,
    adjuster_email TEXT,
    deductible REAL,
    insurance_claim_status TEXT,
    stage_entered_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (assigned_user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Tasks & Follow-up Cadences (Phase B3)
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    task_type TEXT NOT NULL DEFAULT 'follow_up',
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'completed', 'cancelled')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high', 'urgent')),
    due_date TEXT,
    completed_at TEXT,
    customer_id INTEGER,
    opportunity_id INTEGER,
    lead_id INTEGER,
    assigned_user_id INTEGER,
    trigger_source TEXT,
    rule_name TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
    FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE CASCADE,
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE,
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
    stage TEXT NOT NULL DEFAULT 'intake',
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
    stage_entered_at TEXT,
    insurance_claim_number TEXT,
    insurance_carrier TEXT,
    adjuster_name TEXT,
    adjuster_phone TEXT,
    adjuster_email TEXT,
    deductible REAL,
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
    -- appointment_type_id: service-type axis (Emergency / Standard estimate /
    -- Consultation), SEPARATE from the appointment_type modality column above.
    -- Bare INTEGER, no FOREIGN KEY: SQLite's ALTER TABLE ADD COLUMN cannot
    -- attach an FK, so a migrated DB could not enforce one -- keeping fresh and
    -- migrated DBs identical (same precedent as equipment.current_project_id).
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
    updated_at TEXT NOT NULL,
    business_phone TEXT,
    business_email TEXT,
    license_number TEXT
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
--
-- Final scheduling round Phase 3: working_hours_json is the "Business
-- Hours" envelope -- the overall open-for-business window (the outer
-- bound quoted for "what are your hours"), as distinct from the per-type
-- narrower windows in appointment_types.scheduling_hours_json below (an
-- empty scheduling_hours there means "inherit business hours," not
-- "never available"). F3: Core does not enforce either field against
-- appointments.start_time/end_time anywhere -- appointments store UTC
-- ISO timestamps with no timezone column, so a naive "HH:MM" vs.
-- UTC-timestamp comparison here would be silently wrong by hours. Hours
-- enforcement is entirely client-side in calendar.js (device-local Date
-- math); see restoricon_core/models.py's ScheduleConfig/AppointmentType
-- docstrings for the full rationale.
CREATE TABLE IF NOT EXISTS schedule_config (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    working_hours_json TEXT NOT NULL DEFAULT '{}',
    default_duration_minutes INTEGER NOT NULL DEFAULT 30,
    buffer_minutes INTEGER NOT NULL DEFAULT 15,
    booking_window_days INTEGER NOT NULL DEFAULT 365,
    duration_by_relationship_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

-- Appointment service types (final scheduling round, Phase 2). The
-- "service type" axis (Emergency / Standard estimate / Consultation),
-- SEPARATE from appointments.appointment_type (the call/in_person modality
-- the bot auto-detects). Multi-row (AUTOINCREMENT id), unlike the singleton
-- schedule_config above. The three default rows are seeded once, row-count
-- guarded, in _migrate_schema() -- not here -- so re-running DatabaseManager()
-- never re-seeds. scheduling_hours_json mirrors schedule_config's
-- working_hours_json (opaque JSON blob, weekday-keyed when populated).
-- scheduling_hours_json narrows schedule_config.working_hours_json
-- ("Business Hours") per type; empty `{}` means inherit business hours
-- unchanged, not never-bookable. Same F3 no-Core-side-enforcement
-- constraint as schedule_config above applies here.
CREATE TABLE IF NOT EXISTS appointment_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0,
    max_concurrent INTEGER NOT NULL DEFAULT 1 CHECK(max_concurrent >= 1),
    scheduling_hours_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
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

-- Project Milestones Table (Track B Phase B3 Operations Domain Engine)
CREATE TABLE IF NOT EXISTS project_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    stage TEXT NOT NULL,
    target_date TEXT,
    completion_date TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'completed', 'blocked')),
    dependencies_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

-- Work Orders Table (Track B Phase B3 Operations Domain Engine)
CREATE TABLE IF NOT EXISTS work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_number TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    project_id INTEGER NOT NULL,
    trade TEXT NOT NULL,
    assigned_subcontractor_id INTEGER,
    assigned_crew_lead TEXT,
    scheduled_start TEXT,
    scheduled_end TEXT,
    actual_start TEXT,
    actual_end TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'dispatched', 'accepted', 'in_progress', 'completed', 'verified', 'cancelled')),
    line_items_json TEXT NOT NULL DEFAULT '[]',
    total_cost REAL NOT NULL DEFAULT 0.0,
    instructions TEXT,
    notes TEXT,
    dispatched_at TEXT,
    accepted_at TEXT,
    completed_at TEXT,
    verified_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE RESTRICT,
    FOREIGN KEY (assigned_subcontractor_id) REFERENCES subcontractors(id) ON DELETE SET NULL
);

-- Equipment Inventory Table (Track B Phase B3 Operations Domain Engine)
CREATE TABLE IF NOT EXISTS equipment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_tag TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('dehumidifier', 'air_mover', 'moisture_meter', 'air_scrubber', 'generator', 'heater', 'extractor', 'other')),
    model_number TEXT,
    serial_number TEXT,
    status TEXT NOT NULL DEFAULT 'available' CHECK(status IN ('available', 'deployed', 'maintenance', 'retired')),
    daily_rate REAL NOT NULL DEFAULT 0.0,
    current_project_id INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (current_project_id) REFERENCES projects(id) ON DELETE SET NULL
);

-- Equipment Deployments Table (Track B Phase B3 Operations Domain Engine)
CREATE TABLE IF NOT EXISTS equipment_deployments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    work_order_id INTEGER,
    deployed_at TEXT NOT NULL,
    return_due_at TEXT,
    returned_at TEXT,
    deployed_by_user_id INTEGER,
    received_by_user_id INTEGER,
    condition_out TEXT NOT NULL DEFAULT 'good',
    condition_in TEXT,
    initial_reading TEXT,
    final_reading TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (equipment_id) REFERENCES equipment(id) ON DELETE RESTRICT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (work_order_id) REFERENCES work_orders(id) ON DELETE SET NULL,
    FOREIGN KEY (deployed_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (received_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Financial Transactions Table (Track B Phase B5a Finance Domain Engine)
CREATE TABLE IF NOT EXISTS financial_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_number TEXT UNIQUE NOT NULL,
    transaction_type TEXT NOT NULL CHECK(transaction_type IN ('payment_received', 'vendor_expense', 'payroll', 'material_cost', 'equipment_rental', 'refund', 'other')),
    amount REAL NOT NULL,
    category TEXT,
    payment_method TEXT,
    reference_number TEXT,
    customer_id INTEGER,
    project_id INTEGER,
    invoice_id INTEGER,
    vendor_id INTEGER,
    recorded_by_id INTEGER,
    transaction_date TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE SET NULL,
    FOREIGN KEY (vendor_id) REFERENCES vendors(id) ON DELETE SET NULL,
    FOREIGN KEY (recorded_by_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Marketing Campaigns Table (Track B Phase B5a Marketing Domain Engine)
CREATE TABLE IF NOT EXISTS marketing_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    channel TEXT NOT NULL CHECK(channel IN ('google_ads', 'meta_ads', 'local_seo', 'direct_mail', 'email_blast', 'referral', 'billboard', 'other')),
    status TEXT NOT NULL DEFAULT 'planning' CHECK(status IN ('planning', 'active', 'paused', 'completed')),
    budget REAL NOT NULL DEFAULT 0.0,
    actual_spend REAL NOT NULL DEFAULT 0.0,
    leads_generated INTEGER NOT NULL DEFAULT 0,
    revenue_attributed REAL NOT NULL DEFAULT 0.0,
    start_date TEXT,
    end_date TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Review Requests Table (Track B Phase B5a Marketing Domain Engine)
CREATE TABLE IF NOT EXISTS review_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    project_id INTEGER,
    platform TEXT NOT NULL CHECK(platform IN ('google', 'yelp', 'facebook', 'direct', 'other')),
    rating INTEGER CHECK(rating BETWEEN 1 AND 5 OR rating IS NULL),
    feedback TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'sent', 'opened', 'completed', 'declined')),
    sent_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

-- Compliance Items Table (Track B Phase B5a Compliance Domain Engine)
CREATE TABLE IF NOT EXISTS compliance_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT NOT NULL CHECK(category IN ('business_license', 'contractor_license', 'general_liability', 'workers_comp', 'epa_lead_cert', 'iicrc_cert', 'osha_inspection', 'vehicle_insurance', 'other')),
    entity_type TEXT NOT NULL CHECK(entity_type IN ('company', 'subcontractor', 'employee', 'vehicle')),
    entity_id INTEGER,
    license_number TEXT,
    issuer TEXT,
    issue_date TEXT,
    expiration_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'expiring_soon', 'expired', 'renewed')),
    document_id INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL
);

-- Employees Table (Track B Phase B5a HR Domain Engine)
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    role_title TEXT NOT NULL,
    department TEXT NOT NULL CHECK(department IN ('management', 'sales', 'operations', 'field_technician', 'admin', 'other')),
    phone TEXT,
    email TEXT,
    hourly_rate REAL NOT NULL DEFAULT 0.0,
    hire_date TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'on_leave', 'terminated')),
    emergency_contact TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Timesheets Table (Track B Phase B5a HR Domain Engine)
CREATE TABLE IF NOT EXISTS timesheets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    project_id INTEGER,
    work_order_id INTEGER,
    work_date TEXT NOT NULL,
    hours_worked REAL NOT NULL,
    work_type TEXT NOT NULL DEFAULT 'regular' CHECK(work_type IN ('regular', 'overtime', 'travel', 'admin', 'other')),
    hourly_rate REAL NOT NULL DEFAULT 0.0,
    total_cost REAL NOT NULL DEFAULT 0.0,
    notes TEXT,
    approved_by_id INTEGER,
    status TEXT NOT NULL DEFAULT 'submitted' CHECK(status IN ('submitted', 'approved', 'rejected')),
    created_at TEXT NOT NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (work_order_id) REFERENCES work_orders(id) ON DELETE SET NULL,
    FOREIGN KEY (approved_by_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Vendors Table (Track B Phase B5a Procurement Domain Engine)
CREATE TABLE IF NOT EXISTS vendors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    contact_name TEXT,
    phone TEXT,
    email TEXT,
    address TEXT,
    category TEXT NOT NULL CHECK(category IN ('building_materials', 'equipment_rental', 'safety_supplies', 'specialty_contractor', 'office', 'other')),
    payment_terms TEXT NOT NULL DEFAULT 'net_30' CHECK(payment_terms IN ('due_on_receipt', 'net_15', 'net_30', 'net_60', 'cod')),
    rating REAL,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Purchase Orders Table (Track B Phase B5a Procurement Domain Engine)
CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    po_number TEXT UNIQUE NOT NULL,
    vendor_id INTEGER NOT NULL,
    project_id INTEGER,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'submitted', 'partially_received', 'received', 'invoiced', 'cancelled')),
    items_json TEXT NOT NULL DEFAULT '[]',
    subtotal REAL NOT NULL DEFAULT 0.0,
    tax_amount REAL NOT NULL DEFAULT 0.0,
    total_amount REAL NOT NULL DEFAULT 0.0,
    ordered_date TEXT,
    expected_date TEXT,
    received_date TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (vendor_id) REFERENCES vendors(id) ON DELETE RESTRICT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL
);

-- Staff Schedules (B6.7)
CREATE TABLE IF NOT EXISTS staff_schedules (
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
CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(score);
CREATE INDEX IF NOT EXISTS idx_opportunities_customer_id ON opportunities(customer_id);
CREATE INDEX IF NOT EXISTS idx_opportunities_stage ON opportunities(pipeline_stage);
CREATE INDEX IF NOT EXISTS idx_projects_customer_id ON projects(customer_id);
CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_projects_stage ON projects(stage);
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
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_subcontractors_external_id ON subcontractors(external_id);
CREATE INDEX IF NOT EXISTS idx_subcontractors_qualification_status ON subcontractors(qualification_status);
CREATE INDEX IF NOT EXISTS idx_appointments_customer_id ON appointments(customer_id);
CREATE INDEX IF NOT EXISTS idx_appointments_start_time ON appointments(start_time);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);
CREATE INDEX IF NOT EXISTS idx_automation_rules_channel ON automation_rules(channel);
CREATE INDEX IF NOT EXISTS idx_dnc_type_value ON do_not_contact(type, value);
CREATE INDEX IF NOT EXISTS idx_contacts_type ON contacts(type);
CREATE INDEX IF NOT EXISTS idx_contacts_active_role ON contacts(active_role);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_customer_id ON tasks(customer_id);
CREATE INDEX IF NOT EXISTS idx_tasks_opportunity_id ON tasks(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_tasks_lead_id ON tasks(lead_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned_user_id ON tasks(assigned_user_id);
CREATE INDEX IF NOT EXISTS idx_milestones_project_id ON project_milestones(project_id);
CREATE INDEX IF NOT EXISTS idx_milestones_status ON project_milestones(status);
CREATE INDEX IF NOT EXISTS idx_milestones_stage ON project_milestones(stage);
CREATE INDEX IF NOT EXISTS idx_work_orders_project_id ON work_orders(project_id);
CREATE INDEX IF NOT EXISTS idx_work_orders_subcontractor_id ON work_orders(assigned_subcontractor_id);
CREATE INDEX IF NOT EXISTS idx_work_orders_status ON work_orders(status);
CREATE INDEX IF NOT EXISTS idx_work_orders_trade ON work_orders(trade);
CREATE INDEX IF NOT EXISTS idx_equipment_asset_tag ON equipment(asset_tag);
CREATE INDEX IF NOT EXISTS idx_equipment_category ON equipment(category);
CREATE INDEX IF NOT EXISTS idx_equipment_status ON equipment(status);
CREATE INDEX IF NOT EXISTS idx_equipment_current_project ON equipment(current_project_id);
CREATE INDEX IF NOT EXISTS idx_deployments_equipment_id ON equipment_deployments(equipment_id);
CREATE INDEX IF NOT EXISTS idx_deployments_project_id ON equipment_deployments(project_id);
CREATE INDEX IF NOT EXISTS idx_deployments_work_order_id ON equipment_deployments(work_order_id);
CREATE INDEX IF NOT EXISTS idx_fin_txn_project_id ON financial_transactions(project_id);
CREATE INDEX IF NOT EXISTS idx_fin_txn_customer_id ON financial_transactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_fin_txn_type ON financial_transactions(transaction_type);
CREATE INDEX IF NOT EXISTS idx_fin_txn_date ON financial_transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_mkt_camp_status ON marketing_campaigns(status);
CREATE INDEX IF NOT EXISTS idx_mkt_camp_channel ON marketing_campaigns(channel);
CREATE INDEX IF NOT EXISTS idx_rev_req_customer_id ON review_requests(customer_id);
CREATE INDEX IF NOT EXISTS idx_rev_req_status ON review_requests(status);
CREATE INDEX IF NOT EXISTS idx_comp_items_exp_date ON compliance_items(expiration_date);
CREATE INDEX IF NOT EXISTS idx_comp_items_status ON compliance_items(status);
CREATE INDEX IF NOT EXISTS idx_comp_items_entity ON compliance_items(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_employees_status ON employees(status);
CREATE INDEX IF NOT EXISTS idx_employees_user_id ON employees(user_id);
CREATE INDEX IF NOT EXISTS idx_timesheets_employee_id ON timesheets(employee_id);
CREATE INDEX IF NOT EXISTS idx_timesheets_project_id ON timesheets(project_id);
CREATE INDEX IF NOT EXISTS idx_timesheets_work_date ON timesheets(work_date);
CREATE INDEX IF NOT EXISTS idx_timesheets_status ON timesheets(status);
CREATE INDEX IF NOT EXISTS idx_vendors_category ON vendors(category);
CREATE INDEX IF NOT EXISTS idx_po_vendor_id ON purchase_orders(vendor_id);
CREATE INDEX IF NOT EXISTS idx_po_project_id ON purchase_orders(project_id);
CREATE INDEX IF NOT EXISTS idx_po_status ON purchase_orders(status);
CREATE INDEX IF NOT EXISTS idx_staff_schedules_user_id ON staff_schedules(user_id);
"""

_local = threading.local()
_mem_counter = 0
_mem_lock = threading.Lock()


class DatabaseManager:
    """Manages SQLite database connections, schema setup, and transactions.

    The ``init_schema`` constructor flag (default ``True``) exists so that
    ``migrate_aigentik``'s dry run can open the target DB without mutating
    its schema — a bare (non-``--apply``) dry run must not ``CREATE`` or
    ``ALTER`` tables on the production DB. Every normal caller
    (``api/server.py``, ``provision_ai_agent_auth.py``, the test suite)
    leaves it at ``True`` and sees zero behavior change.
    """

    def __init__(
        self, db_path: Path | str = DEFAULT_DB_PATH, init_schema: bool = True
    ):
        """Open (or create) the DB at ``db_path``. When ``init_schema`` is
        ``True`` (default) the DDL schema and additive column migrations
        run on construction; pass ``init_schema=False`` to attach without
        touching schema (used by ``migrate_aigentik``'s dry run so it does
        not mutate schema on the target DB)."""
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

        if init_schema:
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
        self._migrate_schema()
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
            ("leads", "score_factors_json", "ALTER TABLE leads ADD COLUMN score_factors_json TEXT NOT NULL DEFAULT '{}';"),
            ("leads", "property_type", "ALTER TABLE leads ADD COLUMN property_type TEXT;"),
            ("leads", "project_scope", "ALTER TABLE leads ADD COLUMN project_scope TEXT;"),
            ("leads", "urgency_level", "ALTER TABLE leads ADD COLUMN urgency_level TEXT;"),
            ("leads", "insurance_status", "ALTER TABLE leads ADD COLUMN insurance_status TEXT;"),
            ("opportunities", "lost_reason", "ALTER TABLE opportunities ADD COLUMN lost_reason TEXT;"),
            ("opportunities", "insurance_carrier", "ALTER TABLE opportunities ADD COLUMN insurance_carrier TEXT;"),
            ("opportunities", "claim_number", "ALTER TABLE opportunities ADD COLUMN claim_number TEXT;"),
            ("opportunities", "adjuster_name", "ALTER TABLE opportunities ADD COLUMN adjuster_name TEXT;"),
            ("opportunities", "adjuster_phone", "ALTER TABLE opportunities ADD COLUMN adjuster_phone TEXT;"),
            ("opportunities", "adjuster_email", "ALTER TABLE opportunities ADD COLUMN adjuster_email TEXT;"),
            ("opportunities", "deductible", "ALTER TABLE opportunities ADD COLUMN deductible REAL;"),
            ("opportunities", "insurance_claim_status", "ALTER TABLE opportunities ADD COLUMN insurance_claim_status TEXT;"),
            ("opportunities", "stage_entered_at", "ALTER TABLE opportunities ADD COLUMN stage_entered_at TEXT;"),
            (
                "communication_history",
                "provider_message_id",
                "ALTER TABLE communication_history ADD COLUMN provider_message_id TEXT;",
            ),
            ("projects", "stage", "ALTER TABLE projects ADD COLUMN stage TEXT NOT NULL DEFAULT 'intake';"),
            ("projects", "stage_entered_at", "ALTER TABLE projects ADD COLUMN stage_entered_at TEXT;"),
            ("projects", "insurance_claim_number", "ALTER TABLE projects ADD COLUMN insurance_claim_number TEXT;"),
            ("projects", "insurance_carrier", "ALTER TABLE projects ADD COLUMN insurance_carrier TEXT;"),
            ("projects", "adjuster_name", "ALTER TABLE projects ADD COLUMN adjuster_name TEXT;"),
            ("projects", "adjuster_phone", "ALTER TABLE projects ADD COLUMN adjuster_phone TEXT;"),
            ("projects", "adjuster_email", "ALTER TABLE projects ADD COLUMN adjuster_email TEXT;"),
            ("projects", "deductible", "ALTER TABLE projects ADD COLUMN deductible REAL;"),
            ("equipment", "current_project_id", "ALTER TABLE equipment ADD COLUMN current_project_id INTEGER;"),
            ("users", "custom_permissions_json", "ALTER TABLE users ADD COLUMN custom_permissions_json TEXT NOT NULL DEFAULT '{}';"),
            ("business_profile", "business_phone", "ALTER TABLE business_profile ADD COLUMN business_phone TEXT;"),
            ("business_profile", "business_email", "ALTER TABLE business_profile ADD COLUMN business_email TEXT;"),
            ("business_profile", "license_number", "ALTER TABLE business_profile ADD COLUMN license_number TEXT;"),
            ("appointments", "appointment_type_id", "ALTER TABLE appointments ADD COLUMN appointment_type_id INTEGER;"),
        )
        with conn:
            for table, column, ddl in migrations:
                existing_columns = {
                    row["name"] for row in conn.execute(f"PRAGMA table_info({table});")
                }
                if existing_columns and column not in existing_columns:
                    conn.execute(ddl)
            # Seed the three default appointment_types rows exactly once.
            # Row-count guarded (COUNT(*) == 0) so re-running DatabaseManager()
            # -- and _migrate_schema runs on every construction -- is a no-op
            # once the rows exist. Guarded on table existence too:
            # init_schema() calls _migrate_schema() TWICE -- once before
            # executescript(_SCHEMA_SQL) and once after (see init_schema
            # above). On a legacy DB file's first open, the table doesn't
            # exist yet for the pre-executescript call (table-existence
            # check no-ops it); executescript's CREATE TABLE IF NOT EXISTS
            # then creates the table, and the post-executescript call is
            # the one that actually seeds it -- both calls happen within
            # the same DatabaseManager() construction, so seeding is
            # already done by the time __init__ returns.
            if conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='appointment_types';"
            ).fetchone():
                if conn.execute("SELECT COUNT(*) FROM appointment_types;").fetchone()[0] == 0:
                    _now = datetime.now(timezone.utc).isoformat()
                    for _i, _nm in enumerate(("Emergency", "Standard estimate", "Consultation")):
                        conn.execute(
                            "INSERT INTO appointment_types "
                            "(name, active, sort_order, max_concurrent, scheduling_hours_json, created_at, updated_at) "
                            "VALUES (?, 1, ?, 1, '{}', ?, ?);",
                            (_nm, _i, _now, _now),
                        )
            # Unique indexes must run after the ALTERs above (see the note
            # in _SCHEMA_SQL's index block for why they can't live there).
            if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='customers';").fetchone():
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_external_id ON customers(external_id);"
                )
            if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='leads';").fetchone():
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_external_id ON leads(external_id);"
                )
            if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='contacts';").fetchone():
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_external_id ON contacts(external_id);"
                )
            if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks';").fetchone():
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_external_id ON tasks(external_id);"
                )
            # Partial index (WHERE provider_message_id IS NOT NULL): rows
            # with no natural external message id (internal_note,
            # ai_conversation, phone, voicemail) never collide with each
            # other under a bare UNIQUE column, only real, non-null
            # provider ids are deduplicated. record_communication() is
            # responsible for normalizing '' / whitespace-only ids to
            # NULL before insert -- this index alone does not catch an
            # empty-string id, since '' IS NOT NULL is true in SQLite.
            if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='communication_history';").fetchone():
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
