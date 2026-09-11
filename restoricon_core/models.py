"""
Canonical data models and serialization for Restoricon Core entities.
"""

from __future__ import annotations

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
    custom_permissions: Dict[str, bool] = field(default_factory=dict)
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


class ProjectStage:
    """Canonical 10-stage lifecycle progression for Restoricon Operations Domain Engine."""
    INTAKE = "intake"
    ASSESSMENT_SCOPING = "assessment_scoping"
    INSURANCE_APPROVAL = "insurance_approval"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    QUALITY_INSPECTION = "quality_inspection"
    FINAL_WALKTHROUGH = "final_walkthrough"
    COMPLETED = "completed"
    BILLED = "billed"
    CLOSED = "closed"

    # Exception stages
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"

    STAGE_ORDER: List[str] = [
        INTAKE,
        ASSESSMENT_SCOPING,
        INSURANCE_APPROVAL,
        SCHEDULED,
        IN_PROGRESS,
        QUALITY_INSPECTION,
        FINAL_WALKTHROUGH,
        COMPLETED,
        BILLED,
        CLOSED,
    ]

    ALL_STAGES: Set[str] = set(STAGE_ORDER) | {ON_HOLD, CANCELLED}

    # Allowed forward and state transitions
    TRANSITIONS: Dict[str, List[str]] = {
        INTAKE: [ASSESSMENT_SCOPING, ON_HOLD, CANCELLED],
        ASSESSMENT_SCOPING: [INSURANCE_APPROVAL, SCHEDULED, ON_HOLD, CANCELLED],  # Non-insurance jobs can bypass INSURANCE_APPROVAL
        INSURANCE_APPROVAL: [SCHEDULED, ASSESSMENT_SCOPING, ON_HOLD, CANCELLED],
        SCHEDULED: [IN_PROGRESS, ON_HOLD, CANCELLED],
        IN_PROGRESS: [QUALITY_INSPECTION, ON_HOLD, CANCELLED],
        QUALITY_INSPECTION: [FINAL_WALKTHROUGH, IN_PROGRESS, ON_HOLD],  # Can return to IN_PROGRESS if punch-list items fail
        FINAL_WALKTHROUGH: [COMPLETED, IN_PROGRESS, ON_HOLD],
        COMPLETED: [BILLED, ON_HOLD],
        BILLED: [CLOSED, ON_HOLD],
        CLOSED: [],
        ON_HOLD: [INTAKE, ASSESSMENT_SCOPING, INSURANCE_APPROVAL, SCHEDULED, IN_PROGRESS, QUALITY_INSPECTION, FINAL_WALKTHROUGH, COMPLETED, BILLED, CANCELLED],
        CANCELLED: [],
    }

    @classmethod
    def normalize(cls, stage: Optional[str]) -> str:
        """Normalize stage string to canonical snake_case."""
        if not stage:
            return cls.INTAKE
        normalized = stage.strip().lower().replace(" ", "_").replace("-", "_")
        aliases = {
            "lead": cls.INTAKE,
            "new": cls.INTAKE,
            "intake": cls.INTAKE,
            "scoping": cls.ASSESSMENT_SCOPING,
            "assessment": cls.ASSESSMENT_SCOPING,
            "assessment_scoping": cls.ASSESSMENT_SCOPING,
            "insurance": cls.INSURANCE_APPROVAL,
            "insurance_approval": cls.INSURANCE_APPROVAL,
            "scheduled": cls.SCHEDULED,
            "approved": cls.SCHEDULED,
            "in_progress": cls.IN_PROGRESS,
            "active": cls.IN_PROGRESS,
            "quality_inspection": cls.QUALITY_INSPECTION,
            "inspection": cls.QUALITY_INSPECTION,
            "final_walkthrough": cls.FINAL_WALKTHROUGH,
            "walkthrough": cls.FINAL_WALKTHROUGH,
            "done": cls.COMPLETED,
            "complete": cls.COMPLETED,
            "completed": cls.COMPLETED,
            "billed": cls.BILLED,
            "invoiced": cls.BILLED,
            "archive": cls.CLOSED,
            "closed": cls.CLOSED,
            "hold": cls.ON_HOLD,
            "on_hold": cls.ON_HOLD,
            "cancel": cls.CANCELLED,
            "cancelled": cls.CANCELLED,
            "canceled": cls.CANCELLED,
        }
        return aliases.get(normalized, normalized)

    @classmethod
    def is_valid(cls, stage: str) -> bool:
        return cls.normalize(stage) in cls.ALL_STAGES

    @classmethod
    def can_transition(cls, current_stage: str, target_stage: str) -> bool:
        curr = cls.normalize(current_stage)
        tgt = cls.normalize(target_stage)
        if curr == tgt:
            return True
        allowed = cls.TRANSITIONS.get(curr, [])
        return tgt in allowed


class MilestoneStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    ALL_STATUSES = {PENDING, IN_PROGRESS, COMPLETED, BLOCKED}


@dataclass
class ProjectMilestone:
    id: Optional[int] = None
    project_id: int = 0
    name: str = ""
    stage: str = ProjectStage.INTAKE
    target_date: Optional[str] = None
    completion_date: Optional[str] = None
    status: str = MilestoneStatus.PENDING
    dependencies: List[int] = field(default_factory=list)  # List of prerequisite milestone IDs
    notes: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WorkOrderStatus:
    DRAFT = "draft"
    DISPATCHED = "dispatched"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    VERIFIED = "verified"
    CANCELLED = "cancelled"

    ALL_STATUSES = {DRAFT, DISPATCHED, ACCEPTED, IN_PROGRESS, COMPLETED, VERIFIED, CANCELLED}

    TRANSITIONS: Dict[str, List[str]] = {
        DRAFT: [DISPATCHED, CANCELLED],
        DISPATCHED: [ACCEPTED, DRAFT, CANCELLED],  # Returning to draft on sub rejection
        ACCEPTED: [IN_PROGRESS, DISPATCHED, CANCELLED],
        IN_PROGRESS: [COMPLETED, CANCELLED],
        COMPLETED: [VERIFIED, IN_PROGRESS],  # Can be rejected back to in_progress during QA
        VERIFIED: [],
        CANCELLED: [],
    }


@dataclass
class WorkOrderLineItem:
    description: str = ""
    quantity: float = 1.0
    unit: str = "ea"  # ea, sqft, lf, hrs, lsum
    unit_cost: float = 0.0
    total_cost: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WorkOrder:
    id: Optional[int] = None
    work_order_number: str = ""  # e.g. "WO-0001"
    title: str = ""
    project_id: int = 0
    trade: str = ""  # e.g. "mitigation", "drywall", "plumbing", "electrical", "flooring", "paint"
    assigned_subcontractor_id: Optional[int] = None
    assigned_crew_lead: Optional[str] = None
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None
    actual_start: Optional[str] = None
    actual_end: Optional[str] = None
    status: str = WorkOrderStatus.DRAFT
    line_items: List[Dict[str, Any]] = field(default_factory=list)
    total_cost: float = 0.0
    instructions: Optional[str] = None
    notes: Optional[str] = None
    dispatched_at: Optional[str] = None
    accepted_at: Optional[str] = None
    completed_at: Optional[str] = None
    verified_at: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EquipmentStatus:
    AVAILABLE = "available"
    DEPLOYED = "deployed"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"

    ALL_STATUSES = {AVAILABLE, DEPLOYED, MAINTENANCE, RETIRED}


class EquipmentCategory:
    DEHUMIDIFIER = "dehumidifier"
    AIR_MOVER = "air_mover"
    MOISTURE_METER = "moisture_meter"
    AIR_SCRUBBER = "air_scrubber"
    GENERATOR = "generator"
    HEATER = "heater"
    EXTRACTOR = "extractor"
    OTHER = "other"

    ALL_CATEGORIES = {
        DEHUMIDIFIER,
        AIR_MOVER,
        MOISTURE_METER,
        AIR_SCRUBBER,
        GENERATOR,
        HEATER,
        EXTRACTOR,
        OTHER,
    }


@dataclass
class Equipment:
    id: Optional[int] = None
    asset_tag: str = ""  # Unique identifier barcode/asset tag (e.g. "EQ-DH-001")
    name: str = ""
    category: str = EquipmentCategory.DEHUMIDIFIER
    model_number: Optional[str] = None
    serial_number: Optional[str] = None
    status: str = EquipmentStatus.AVAILABLE
    daily_rate: float = 0.0
    current_project_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EquipmentDeployment:
    id: Optional[int] = None
    equipment_id: int = 0
    project_id: int = 0
    work_order_id: Optional[int] = None
    deployed_at: str = field(default_factory=utc_now_iso)
    return_due_at: Optional[str] = None
    returned_at: Optional[str] = None
    deployed_by_user_id: Optional[int] = None
    received_by_user_id: Optional[int] = None
    condition_out: str = "good"  # new, good, fair, worn, damaged
    condition_in: Optional[str] = None
    initial_reading: Optional[str] = None  # e.g. "Moisture: 42% WME, RH: 75%"
    final_reading: Optional[str] = None  # e.g. "Moisture: 11% WME, RH: 38%"
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
    stage: str = ProjectStage.INTAKE  # 10 canonical stages in ProjectStage
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
    stage_entered_at: Optional[str] = None
    insurance_claim_number: Optional[str] = None
    insurance_carrier: Optional[str] = None
    adjuster_name: Optional[str] = None
    adjuster_phone: Optional[str] = None
    adjuster_email: Optional[str] = None
    deductible: Optional[float] = None
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
    appointment_type: Optional[str] = None  # 'call', 'in_person', or None (modality)
    appointment_type_id: Optional[int] = None  # FK-less ref to appointment_types (service type)
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
    """Singleton business profile record. There is exactly one row (id
    fixed to 1). The identity/onboarding fields mirror Aigentik-CLI's
    profile.json, PLUS Core-only public-contact fields (business_phone,
    business_email, license_number) surfaced for the admin dashboard and
    not present in Aigentik."""
    id: int = 1
    configured: int = 0
    aigentik_name: Optional[str] = None
    agent_name_set: int = 0
    owner_name: Optional[str] = None
    business_name: Optional[str] = None
    business_description: Optional[str] = None
    business_phone: Optional[str] = None
    business_email: Optional[str] = None
    license_number: Optional[str] = None
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
class AppointmentType:
    """A bookable service type (Emergency / Standard estimate / Consultation),
    final scheduling round Phase 2. This is a SEPARATE axis from
    Appointment.appointment_type (the 'call'/'in_person' modality the bot
    auto-detects). Multi-row, unlike the ScheduleConfig singleton. The
    dataclass field is `scheduling_hours` (a dict); the DB column is
    `scheduling_hours_json` -- mirrors ScheduleConfig.working_hours <->
    working_hours_json."""
    id: Optional[int] = None
    name: str = ""
    active: int = 1
    sort_order: int = 0
    max_concurrent: int = 1
    scheduling_hours: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
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


@dataclass
class FinancialTransaction:
    """Finance domain transaction ledger record."""
    id: Optional[int] = None
    transaction_number: str = ""
    transaction_type: str = "payment_received"  # payment_received, vendor_expense, payroll, material_cost, equipment_rental, refund, other
    amount: float = 0.0
    category: Optional[str] = None
    payment_method: Optional[str] = None
    reference_number: Optional[str] = None
    customer_id: Optional[int] = None
    project_id: Optional[int] = None
    invoice_id: Optional[int] = None
    vendor_id: Optional[int] = None
    recorded_by_id: Optional[int] = None
    transaction_date: str = field(default_factory=utc_now_iso)
    notes: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MarketingCampaign:
    """Marketing domain campaign record."""
    id: Optional[int] = None
    name: str = ""
    channel: str = "google_ads"  # google_ads, meta_ads, local_seo, direct_mail, email_blast, referral, billboard, other
    status: str = "planning"  # planning, active, paused, completed
    budget: float = 0.0
    actual_spend: float = 0.0
    leads_generated: int = 0
    revenue_attributed: float = 0.0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewRequest:
    """Customer satisfaction and online review tracking."""
    id: Optional[int] = None
    customer_id: int = 0
    project_id: Optional[int] = None
    platform: str = "google"  # google, yelp, facebook, direct, other
    rating: Optional[int] = None  # 1-5
    feedback: Optional[str] = None
    status: str = "pending"  # pending, sent, opened, completed, declined
    sent_at: Optional[str] = None
    completed_at: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ComplianceItem:
    """Compliance domain certification, license, and insurance tracking."""
    id: Optional[int] = None
    title: str = ""
    category: str = "general_liability"  # business_license, contractor_license, general_liability, workers_comp, epa_lead_cert, iicrc_cert, osha_inspection, vehicle_insurance, other
    entity_type: str = "company"  # company, subcontractor, employee, vehicle
    entity_id: Optional[int] = None
    license_number: Optional[str] = None
    issuer: Optional[str] = None
    issue_date: Optional[str] = None
    expiration_date: str = ""
    status: str = "active"  # active, expiring_soon, expired, renewed
    document_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Employee:
    """HR domain employee record."""
    id: Optional[int] = None
    user_id: Optional[int] = None
    first_name: str = ""
    last_name: str = ""
    role_title: str = ""
    department: str = "operations"  # management, sales, operations, field_technician, admin, other
    phone: Optional[str] = None
    email: Optional[str] = None
    hourly_rate: float = 0.0
    hire_date: Optional[str] = None
    status: str = "active"  # active, on_leave, terminated
    emergency_contact: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Timesheet:
    """HR domain labor hours tracking and job costing record."""
    id: Optional[int] = None
    employee_id: int = 0
    project_id: Optional[int] = None
    work_order_id: Optional[int] = None
    work_date: str = ""
    hours_worked: float = 0.0
    work_type: str = "regular"  # regular, overtime, travel, admin, other
    hourly_rate: float = 0.0
    total_cost: float = 0.0
    notes: Optional[str] = None
    approved_by_id: Optional[int] = None
    status: str = "submitted"  # submitted, approved, rejected
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Vendor:
    """Procurement domain vendor and supplier record."""
    id: Optional[int] = None
    company_name: str = ""
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    category: str = "building_materials"  # building_materials, equipment_rental, safety_supplies, specialty_contractor, office, other
    payment_terms: str = "net_30"  # due_on_receipt, net_15, net_30, net_60, cod
    rating: Optional[float] = None
    notes: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PurchaseOrder:
    """Procurement domain purchase order record."""
    id: Optional[int] = None
    po_number: str = ""
    vendor_id: int = 0
    project_id: Optional[int] = None
    status: str = "draft"  # draft, submitted, partially_received, received, invoiced, cancelled
    items: List[Dict[str, Any]] = field(default_factory=list)
    subtotal: float = 0.0
    tax_amount: float = 0.0
    total_amount: float = 0.0
    ordered_date: Optional[str] = None
    expected_date: Optional[str] = None
    received_date: Optional[str] = None
    notes: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StaffSchedule:
    id: Optional[int]
    user_id: int
    title: str
    start_time: str
    end_time: str
    status: str
    notes: Optional[str]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "status": self.status,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_row(cls, row) -> 'StaffSchedule':
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            status=row["status"],
            notes=row["notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"]
        )

