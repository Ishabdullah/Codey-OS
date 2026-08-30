"""
Canonical data models and serialization for Restoricon Core entities.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class User:
    id: Optional[int] = None
    username: str = ""
    password_hash: str = ""
    full_name: str = ""
    email: str = ""
    phone: Optional[str] = None
    role: str = "technician"  # admin, manager, sales, project_manager, technician, ai_agent, customer
    department: Optional[str] = None
    customer_id: Optional[int] = None
    active: int = 1
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        data = asdict(self)
        if not include_sensitive:
            data.pop("password_hash", None)
        return data


@dataclass
class Customer:
    id: Optional[int] = None
    external_id: Optional[str] = None  # NEW-212/NEW-232, 2026-08-27: external system's own string ID
    first_name: str = ""
    last_name: str = ""
    company_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    mailing_address: Optional[str] = None
    service_address: Optional[str] = None
    customer_type: str = "residential"  # residential, commercial
    customer_source: Optional[str] = None
    assigned_user_id: Optional[int] = None
    status: str = "lead"  # lead, prospect, active, past, lost
    tags: List[str] = field(default_factory=list)
    notes: Optional[str] = None
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    last_contact_at: Optional[str] = None
    next_followup_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PipelineStage:
    """Canonical 9-stage pipeline progression for Restoricon CRM & Sales Domain Engine."""
    NEW_LEAD = "new_lead"
    CONTACTED = "contacted"
    APPOINTMENT_SET = "appointment_set"
    ESTIMATE_SCHEDULED = "estimate_scheduled"
    ESTIMATE_SENT = "estimate_sent"
    PROPOSAL_SENT = "proposal_sent"
    NEGOTIATION = "negotiation"
    WON = "won"
    LOST = "lost"

    STAGE_ORDER: List[str] = [
        NEW_LEAD,
        CONTACTED,
        APPOINTMENT_SET,
        ESTIMATE_SCHEDULED,
        ESTIMATE_SENT,
        PROPOSAL_SENT,
        NEGOTIATION,
        WON,
        LOST,
    ]

    STAGE_DEFAULT_PROBABILITIES: Dict[str, float] = {
        NEW_LEAD: 0.10,
        CONTACTED: 0.20,
        APPOINTMENT_SET: 0.40,
        ESTIMATE_SCHEDULED: 0.50,
        ESTIMATE_SENT: 0.60,
        PROPOSAL_SENT: 0.70,
        NEGOTIATION: 0.85,
        WON: 1.0,
        LOST: 0.0,
    }

    @classmethod
    def normalize(cls, stage: Optional[str]) -> str:
        """Normalize stage string (e.g. 'New Lead', 'new_lead', 'ESTIMATE SENT') to canonical stage."""
        if not stage:
            return cls.NEW_LEAD
        normalized = stage.strip().lower().replace(" ", "_").replace("-", "_")
        if normalized in cls.STAGE_ORDER:
            return normalized
        aliases = {
            "lead": cls.NEW_LEAD,
            "new": cls.NEW_LEAD,
            "appointment": cls.APPOINTMENT_SET,
            "estimate": cls.ESTIMATE_SCHEDULED,
            "proposal": cls.PROPOSAL_SENT,
            "negotiating": cls.NEGOTIATION,
            "negotiate": cls.NEGOTIATION,
            "closed_won": cls.WON,
            "closed_lost": cls.LOST,
        }
        return aliases.get(normalized, normalized)

    @classmethod
    def is_valid(cls, stage: str) -> bool:
        return cls.normalize(stage) in cls.STAGE_ORDER


STAGE_ORDER = PipelineStage.STAGE_ORDER
STAGE_DEFAULT_PROBABILITIES = PipelineStage.STAGE_DEFAULT_PROBABILITIES


@dataclass
class Lead:
    id: Optional[int] = None
    external_id: Optional[str] = None  # NEW-212/NEW-232, 2026-08-27: external system's own string ID
    customer_id: Optional[int] = None
    source: str = "website"
    status: str = "new"  # new, contacted, qualified, unqualified, converted, lost
    score: int = 0
    score_factors: Dict[str, Any] = field(default_factory=dict)
    property_type: Optional[str] = None
    project_scope: Optional[str] = None
    urgency_level: Optional[str] = None
    insurance_status: Optional[str] = None
    estimated_value: float = 0.0
    assigned_user_id: Optional[int] = None
    first_contact_at: Optional[str] = None
    last_contact_at: Optional[str] = None
    next_followup_at: Optional[str] = None
    notes: Optional[str] = None
    lost_reason: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Opportunity:
    id: Optional[int] = None
    customer_id: int = 0
    project_id: Optional[int] = None
    title: str = ""
    estimated_value: float = 0.0
    probability: float = 0.0
    pipeline_stage: str = PipelineStage.NEW_LEAD  # 9 canonical stages in PipelineStage
    expected_close_date: Optional[str] = None
    assigned_user_id: Optional[int] = None
    competitor_info: Optional[str] = None
    notes: Optional[str] = None
    lost_reason: Optional[str] = None
    insurance_carrier: Optional[str] = None
    claim_number: Optional[str] = None
    adjuster_name: Optional[str] = None
    adjuster_phone: Optional[str] = None
    adjuster_email: Optional[str] = None
    deductible: Optional[float] = None
    insurance_claim_status: Optional[str] = None
    stage_entered_at: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Task:
    """Follow-up task / CRM activity record."""
    id: Optional[int] = None
    external_id: Optional[str] = None
    title: str = ""
    description: Optional[str] = None
    task_type: str = "follow_up"  # follow_up, phone_call, email, inspection, estimate_follow_up, negotiation, production_handoff, lost_review
    status: str = "pending"  # pending, in_progress, completed, cancelled
    priority: str = "medium"  # low, medium, high, urgent
    due_date: Optional[str] = None
    completed_at: Optional[str] = None
    customer_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    lead_id: Optional[int] = None
    assigned_user_id: Optional[int] = None
    trigger_source: Optional[str] = None
    rule_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Project:
    id: Optional[int] = None
    customer_id: int = 0
    title: str = ""
    property_address: str = ""
    project_type: str = "remodel"
    status: str = "planning"  # planning, scheduled, in_progress, on_hold, completed, cancelled
    start_date: Optional[str] = None
    expected_completion: Optional[str] = None
    actual_completion: Optional[str] = None
    project_manager_id: Optional[int] = None
    assigned_employees: List[int] = field(default_factory=list)
    subcontractors: List[str] = field(default_factory=list)
    scope_of_work: Optional[str] = None
    estimated_cost: float = 0.0
    contract_amount: float = 0.0
    actual_cost: float = 0.0
    profit: float = 0.0
    notes: Optional[str] = None
    warranty_info: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Estimate:
    id: Optional[int] = None
    estimate_number: str = ""
    customer_id: int = 0
    project_id: Optional[int] = None
    line_items: List[Dict[str, Any]] = field(default_factory=list)
    subtotal: float = 0.0
    materials_cost: float = 0.0
    labor_cost: float = 0.0
    subcontractor_cost: float = 0.0
    markup_percent: float = 0.0
    tax_amount: float = 0.0
    discount_amount: float = 0.0
    total_amount: float = 0.0
    status: str = "draft"  # draft, sent, approved, rejected, expired
    expiration_date: Optional[str] = None
    version: int = 1
    notes: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Contract:
    id: Optional[int] = None
    contract_number: str = ""
    customer_id: int = 0
    project_id: Optional[int] = None
    estimate_id: Optional[int] = None
    title: str = ""
    template_name: Optional[str] = None
    content: str = ""
    status: str = "draft"  # draft, sent, signed, expired, superseded
    customer_signed_at: Optional[str] = None
    customer_signature_data: Optional[str] = None
    version: int = 1
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Document:
    id: Optional[int] = None
    customer_id: Optional[int] = None
    project_id: Optional[int] = None
    document_type: str = "pdf"  # contract, estimate, proposal, invoice, receipt, insurance, permit, photo, pdf, upload, warranty
    title: str = ""
    file_path: str = ""
    file_size_bytes: int = 0
    mime_type: str = "application/octet-stream"
    tags: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    expiration_date: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Invoice:
    id: Optional[int] = None
    invoice_number: str = ""
    customer_id: int = 0
    project_id: Optional[int] = None
    status: str = "draft"  # draft, sent, partially_paid, paid, overdue, void
    amount: float = 0.0
    deposit_amount: float = 0.0
    balance_due: float = 0.0
    due_date: Optional[str] = None
    payments: List[Dict[str, Any]] = field(default_factory=list)
    notes: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CommunicationRecord:
    """Strictly append-only communication record."""
    id: Optional[int] = None
    timestamp: str = field(default_factory=utc_now_iso)
    channel: str = "email"  # phone, email, sms, voicemail, web_chat, social, internal_note, ai_conversation, appointment
    direction: str = "inbound"  # inbound, outbound, internal
    subject: Optional[str] = None
    content: str = ""
    actor_id: Optional[int] = None
    actor_role: str = "ai_agent"
    actor_type: str = "agent"  # human, agent
    customer_id: Optional[int] = None
    project_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    provider_message_id: Optional[str] = None  # NEW-233: originating channel's own
    # message id (e.g. IMAP Message-ID header), used as an idempotency key so a
    # retried or reprocessed write-through call never creates a duplicate row.

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Subcontractor:
    """Recruitment/qualification pipeline record. Field names mirror
    Aigentik-CLI's subcontractors.json directly; `external_id`/
    `contact_external_id` preserve Aigentik's own string IDs
    (e.g. "sub_0001") for idempotent migration."""
    id: Optional[int] = None
    external_id: Optional[str] = None
    contact_external_id: Optional[str] = None
    company_name: str = ""
    legal_name: Optional[str] = None
    dba: Optional[str] = None
    contact_name: Optional[str] = None
    title: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    primary_trade: Optional[str] = None
    secondary_trades: List[str] = field(default_factory=list)
    service_area: Optional[str] = None
    years_in_business: Optional[int] = None
    crew_size: Optional[int] = None
    residential_experience: Optional[str] = None
    commercial_experience: Optional[str] = None
    typical_project_size: Optional[str] = None
    availability: Optional[str] = None
    emergency_availability: Optional[str] = None
    license_required: Optional[int] = None
    license_type: Optional[str] = None
    license_number: Optional[str] = None
    license_expiration: Optional[str] = None
    license_status: Optional[str] = None
    general_liability: Optional[str] = None
    workers_comp: Optional[str] = None
    coi_received: int = 0
    coi_expiration: Optional[str] = None
    additional_insured_status: Optional[str] = None
    insurance_status: Optional[str] = None
    w9_received: int = 0
    msa_sent: int = 0
    msa_signed: int = 0
    references: List[Dict[str, Any]] = field(default_factory=list)
    portfolio_url: Optional[str] = None
    qualification_status: str = "QUALIFICATION_IN_PROGRESS"
    recruitment_step: Optional[str] = None
    lead_source: Optional[str] = None
    last_contact_at: Optional[str] = None
    next_followup_at: Optional[str] = None
    contact_attempts: int = 0
    dnc_status: int = 0
    notes: Optional[str] = None
    qualification_data: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Appointment:
    """Calendar/scheduling record. Mirrors Aigentik-CLI's calendar.js
    appointment shape, including its negotiate-then-confirm lifecycle
    (status 'negotiating' -> 'confirmed') -- Aigentik never books a slot
    unilaterally, it proposes offered_slots and waits for agreement."""
    id: Optional[int] = None
    external_id: Optional[str] = None
    uid: Optional[str] = None
    ics_sequence: int = 0
    title: str = ""
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    customer_id: Optional[int] = None
    contact_external_id: Optional[str] = None
    attendee_name: Optional[str] = None
    attendee_email: Optional[str] = None
    appointment_type: Optional[str] = None  # 'call', 'in_person', or None
    status: str = "confirmed"  # confirmed, negotiating, cancelled, completed
    rsvp_status: str = "pending"
    offered_slots: List[Dict[str, Any]] = field(default_factory=list)
    requested_datetime: Optional[str] = None
    pending_reschedule: Optional[Dict[str, Any]] = None
    form_sent: int = 0
    created_via: str = "owner"
    notes: Optional[str] = None
    history: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AutomationRule:
    """Inbound email/SMS handling rule. One table/model covers both
    channels (Aigentik-CLI's email-rules.json and sms-rules.json are
    field-identical), distinguished by `channel`."""
    id: Optional[int] = None
    external_id: Optional[str] = None
    channel: str = "email"  # email, sms
    description: Optional[str] = None
    condition_type: str = ""
    condition_value: str = ""
    action: str = ""
    added_by: Optional[str] = None
    match_count: int = 0
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BusinessProfile:
    """Singleton business profile record, mirrors Aigentik-CLI's
    profile.json. There is exactly one row (id fixed to 1)."""
    id: int = 1
    configured: int = 0
    aigentik_name: Optional[str] = None
    agent_name_set: int = 0
    owner_name: Optional[str] = None
    business_name: Optional[str] = None
    business_description: Optional[str] = None
    onboarding_sent: int = 0
    setup_date: Optional[str] = None
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScheduleConfig:
    """Singleton scheduling configuration, mirrors Aigentik-CLI's
    schedule-config.json (NEW-216, 2026-08-27). There is exactly one row
    (id fixed to 1). working_hours maps weekday keys ('mon'..'sun') to
    {'start': 'HH:MM', 'end': 'HH:MM'} dicts; duration_by_relationship is
    an opaque dict (empty in the source data today, key shape unknown)."""
    id: int = 1
    working_hours: Dict[str, Any] = field(default_factory=dict)
    default_duration_minutes: int = 30
    buffer_minutes: int = 15
    booking_window_days: int = 365
    duration_by_relationship: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DoNotContactEntry:
    """Permanent contact-suppression entry. `value` must use the same
    normalization as Aigentik-CLI's do-not-contact.js (email lowercased
    and trimmed; phone reduced to its last 10 digits) -- see
    automation_service.py's normalize_* helpers. A mismatch here means a
    suppressed contact could silently be re-contacted."""
    id: Optional[int] = None
    type: str = "email"  # email, phone
    value: str = ""
    original: Optional[str] = None
    name: Optional[str] = None
    reason: Optional[str] = None
    source: Optional[str] = None
    added_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Contact:
    """Aigentik contact directory entity."""
    id: Optional[int] = None
    external_id: Optional[str] = None
    name: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    address: Optional[str] = None
    relationship: Optional[str] = None
    type: str = "unknown"
    notes: Optional[str] = None
    instructions: Optional[str] = None
    reply_behavior: str = "auto"
    roles: List[str] = field(default_factory=list)
    active_role: Optional[str] = None
    business_name: Optional[str] = None
    trade: Optional[str] = None
    trade_raw: Optional[str] = None
    licensed: Optional[int] = None
    license_number: Optional[str] = None
    gl_insurance: Optional[int] = None
    wc_insurance: Optional[int] = None
    has_tools: Optional[int] = None
    crew_size: Optional[int] = None
    weekly_capacity: Optional[str] = None
    references: List[Dict[str, Any]] = field(default_factory=list)
    source: str = "auto"
    first_seen: Optional[str] = None
    last_contact: Optional[str] = None
    contact_count: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuditRecord:
    """Strictly append-only audit log record."""
    id: Optional[int] = None
    timestamp: str = field(default_factory=utc_now_iso)
    actor_id: Optional[int] = None
    actor_role: str = "system"
    actor_type: str = "agent"  # human, agent
    action: str = "create"  # create, update, delete, status_change, auth_login, auth_logout, sign, pay, export
    entity_type: str = "system"  # customer, lead, opportunity, project, estimate, contract, invoice, document, communication, user
    entity_id: Optional[int] = None
    change_summary: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
