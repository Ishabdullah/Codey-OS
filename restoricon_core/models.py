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
    role: str = "technician"  # admin, manager, sales, sales_manager, project_manager, technician, ai_agent, customer
    department: Optional[str] = None
    customer_id: Optional[int] = None
    custom_permissions: Dict[str, bool] = field(default_factory=dict)
    active: int = 1
    terminated_at: Optional[str] = None  # B8.7c: set/cleared by AuthService.set_user_active, see database.py's ALTER comment
    territory_id: Optional[int] = None  # B8.9a: at most one territory per rep, see database.py's ALTER comment
    subcontractor_id: Optional[int] = None  # Phase 0b, B8.16: populated for a ROLE_SUBCONTRACTOR user's own account
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
    customer_number: Optional[int] = None  # B8.6d-c: server-generated, sequential, see create_customer
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
    territory_id: Optional[int] = None  # B8.9a: FK-less, see database.py's territories table comment
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
    territory_id: Optional[int] = None  # B8.9a: FK-less, see database.py's territories table comment
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
    # B8.16 Phase 3: a non-terminal status distinct from CANCELLED (see
    # OperationsService.split_work_order's docstring for why CANCELLED was
    # explicitly rejected as this phase's original design -- the job is
    # still proceeding, just divided across child work orders). A SPLIT
    # parent's own line_items/total_cost are zeroed at write time (the work
    # moved to its children), so it is intentionally treated like a
    # terminal status by every "active work order" query in
    # operations_service.py (the QUALITY_INSPECTION transition guard and
    # the subcontractor active-work-orders query) even though the project
    # as a whole is still live. Settable ONLY via
    # OperationsService.split_work_order -- update_work_order_execution_
    # status explicitly rejects it (see that method).
    SPLIT = "split"

    ALL_STATUSES = {DRAFT, DISPATCHED, ACCEPTED, IN_PROGRESS, COMPLETED, VERIFIED, CANCELLED, SPLIT}

    TRANSITIONS: Dict[str, List[str]] = {
        DRAFT: [DISPATCHED, CANCELLED, SPLIT],
        DISPATCHED: [ACCEPTED, DRAFT, CANCELLED],  # Returning to draft on sub rejection
        ACCEPTED: [IN_PROGRESS, DISPATCHED, CANCELLED],
        IN_PROGRESS: [COMPLETED, CANCELLED],
        COMPLETED: [VERIFIED, IN_PROGRESS],  # Can be rejected back to in_progress during QA
        VERIFIED: [],
        CANCELLED: [],
        SPLIT: [],
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
    # B8.16 Phase 3: FK-less ref to the parent WorkOrder this row was split
    # from (same "loosely-linked, additive ALTER TABLE ADD COLUMN" pattern
    # as Invoice.assigned_user_id/Contract.assigned_user_id above), NOT a
    # real FOREIGN KEY -- only populated on a child created by
    # OperationsService.split_work_order. Immutable by construction: never
    # written by update_work_order's UPDATE (same treatment as project_id).
    parent_work_order_id: Optional[int] = None
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
    coverage_amount: Optional[float] = None
    supplement_amount: Optional[float] = None
    property_id: Optional[int] = None
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
    assigned_user_id: Optional[int] = None  # FK-less ref to users (who's assigned)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# --- Codey-Estimator Phase B9.2: EstimateService dataclasses ---------------
# New, additional dataclasses for the B9.1-rebuilt `estimates` table's new
# columns plus the four brand-new tables (`estimate_versions`,
# `estimate_line_items`, `estimate_decisions`). The existing `Estimate`
# dataclass above is left untouched -- it is still what the legacy
# `line_items_json`/REAL-money columns serialize to for any pre-B9.1 caller;
# nothing here replaces it. Field names/types match `codey_estimator_schema.md`
# §1/§2 and the real `database.py` DDL, confirmed by reading both (rule 12).
# `EstimateShareLink` (added B9.2, this round): the raw token itself is
# NEVER a field on this dataclass -- only `token_hash` (the persisted
# column) -- matching `estimate_share_links`' own "token_hash-only" DDL
# comment in database.py. `EstimateService._create_share_link()` returns
# the raw token separately, out-of-band, never attached to this object or
# serialized via to_dict().


@dataclass
class EstimateHeader:
    """The `estimates` table's B9.1 header columns only (identity/workflow
    metadata) -- not the legacy REAL-money/`line_items_json` columns, which
    stay on `Estimate` above."""
    id: Optional[int] = None
    estimate_number: str = ""
    customer_id: int = 0
    project_id: Optional[int] = None
    created_by_user_id: Optional[int] = None
    created_by_name: Optional[str] = None
    assigned_to_user_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    lead_id: Optional[int] = None
    property_id: Optional[int] = None
    title: Optional[str] = None
    current_version_id: Optional[int] = None
    accepted_version_id: Optional[int] = None
    accepted_at: Optional[str] = None
    converted_project_id: Optional[int] = None
    contract_id: Optional[int] = None
    source: str = "engine"
    workflow_status: str = "DRAFT"
    # B9.2 (D5 / codey_estimator_service.md §9 item 5): pinned once at
    # create() time -- see EstimateService.create()'s docstring. Never
    # recomputed from users.requires_estimate_approval on read.
    internal_review_required: int = 0
    expires_at: Optional[str] = None
    customer_notes: Optional[str] = None
    terms: Optional[str] = None
    sent_at: Optional[str] = None
    last_viewed_at: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    # Not DB columns -- populated in-memory by EstimateService.get()/list()
    # only when the actor holds PERM_READ_ESTIMATE_COSTS (cost fields) or
    # passed include_lines=True (lines), per D9's cost-gating design
    # (codey_estimator_service.md §1.2). Always present on the dataclass
    # (default None / empty list) so to_dict() has a stable key set; a
    # caller without the permission simply sees None there.
    cost_total_cents: Optional[int] = None
    gross_profit_cents: Optional[int] = None
    gross_margin_bp: Optional[int] = None
    # B9.6 addition: the current version's customer-facing sell total, in
    # cents -- NOT gated by PERM_READ_ESTIMATE_COSTS (it's the price the
    # customer is actually charged, same "stays visible" treatment
    # EstimateLineItem.price_override_cents/line_total_cents already get
    # at the line level, and EstimateVersion.total_cents gets at the
    # version level) -- see EstimateService._attach_cost_fields().
    total_cents: Optional[int] = None
    lines: List["EstimateLineItem"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EstimateVersion:
    id: Optional[int] = None
    estimate_id: int = 0
    version_number: int = 1
    is_locked: int = 0
    locked_at: Optional[str] = None
    locked_reason: Optional[str] = None
    material_cost_cents: int = 0
    labor_cost_cents: int = 0
    equipment_cost_cents: int = 0
    sub_cost_cents: int = 0
    cost_total_cents: int = 0
    subtotal_sell_cents: int = 0
    discount_cents: int = 0
    taxable_base_cents: int = 0
    tax_cents: int = 0
    total_cents: int = 0
    gross_profit_cents: int = 0
    gross_margin_bp: int = 0
    calc_engine_version: int = 1
    tax_rate_bp: int = 0
    terms_snapshot: Optional[str] = None
    customer_notes_snapshot: Optional[str] = None
    change_summary: Optional[str] = None
    created_by_user_id: Optional[int] = None
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EstimateLineItem:
    id: Optional[int] = None
    estimate_version_id: int = 0
    sort_order: int = 0
    line_type: str = "material"
    section: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    customer_description: Optional[str] = None
    visible_to_customer: int = 1
    price_book_item_id: Optional[int] = None
    retailer_product_id: Optional[int] = None
    price_observation_id: Optional[int] = None
    retailer_code_snapshot: Optional[str] = None
    product_title_snapshot: Optional[str] = None
    package_qty: Optional[float] = None
    package_unit: Optional[str] = None
    unit_cost_cents: Optional[int] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    waste_pct_bp: int = 0
    # material_markup_bp/equipment_markup_bp/sub_markup_bp/material_cost_cents/
    # labor_cost_cents/cost_total_cents/sell_total_cents are `Optional[int]`
    # (rather than `int` with a `0` default) specifically so
    # EstimateService._row_to_line()'s PERM_READ_ESTIMATE_COSTS gate (D9,
    # mirroring _attach_cost_fields()'s header-level gate) can null them out
    # to mean "withheld" unambiguously -- an actual `0` is a legitimate
    # "at cost" value and must never be confused with "not permitted to see
    # this field".
    material_markup_bp: Optional[int] = None
    labor_type: Optional[str] = None
    labor_rate_id: Optional[int] = None
    labor_qty: Optional[float] = None
    labor_unit: Optional[str] = None
    labor_cost_rate_cents: Optional[int] = None
    labor_bill_rate_cents: Optional[int] = None
    equipment_id: Optional[int] = None
    equipment_cost_cents: Optional[int] = None
    equipment_markup_bp: Optional[int] = None
    subcontractor_id: Optional[int] = None
    sub_cost_cents: Optional[int] = None
    sub_markup_bp: Optional[int] = None
    taxable: int = 1
    discount_cents: int = 0
    price_override_cents: Optional[int] = None
    override_reason: Optional[str] = None
    # Written by codey_estimator.calc ONLY -- never by the API/UI layer.
    packages_needed: Optional[int] = None
    material_cost_cents: Optional[int] = None
    labor_cost_cents: Optional[int] = None
    cost_total_cents: Optional[int] = None
    sell_total_cents: Optional[int] = None
    tax_cents: int = 0
    line_total_cents: int = 0
    internal_note: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EstimateDecision:
    id: Optional[int] = None
    estimate_version_id: int = 0
    share_link_id: Optional[int] = None
    customer_user_id: Optional[int] = None
    decision: str = "accepted"
    signer_name: Optional[str] = None
    signature_data: Optional[str] = None
    consent_text_snapshot: Optional[str] = None
    comment: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    decided_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EstimateShareLink:
    """Mirrors `estimate_share_links` (database.py). `token_hash` is the
    persisted SHA-256 of the raw capability token -- the raw token itself
    is never a field here (see this section's header comment above)."""
    id: Optional[int] = None
    estimate_id: int = 0
    estimate_version_id: int = 0
    customer_id: int = 0
    token_hash: str = ""
    created_by_user_id: Optional[int] = None
    created_at: str = field(default_factory=utc_now_iso)
    expires_at: str = ""
    revoked_at: Optional[str] = None
    revoked_by_user_id: Optional[int] = None
    first_viewed_at: Optional[str] = None
    last_viewed_at: Optional[str] = None
    view_count: int = 0
    delivery_channel: Optional[str] = None
    delivered_to: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PackageOption:
    """Good/Better/Best tiered pricing option scoped to an Estimate
    (B8.6b, sales_rep_portal.md §B8.6). Deliberately distinct from and
    never mixed with home-care.html's real published subscription tiers
    (Basic/Plus/Complete/Estate) -- settled by the B8 scoping pass,
    not a naming decision made here. price/gross_profit/margin are
    always server-computed from included_items by
    CRMService.create_package_option -- never trusted from a client,
    same discipline as Estimate's computed cost fields."""
    id: Optional[int] = None
    estimate_id: Optional[int] = None
    tier: str = "good"  # good, better, best
    price: float = 0.0
    gross_profit: Optional[float] = None
    margin: Optional[float] = None
    included_items: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# B8.6d-c: the small, fixed set of legal Contract.template_name values.
# 'general_remodeling' is the original free-form contract path; the other
# four are the real published HomeCare subscription tiers (confirmed
# against home-care.html during B8.6 scoping) -- Basic/Plus/Complete/
# Estate, NOT PackageOption's unrelated good/better/best estimate-pricing
# tiers. template_name stays a plain TEXT column (no CHECK constraint --
# same "can't be widened later without a full table rebuild" reasoning as
# contract_signers.party_role) -- this tuple is the single Python-level
# source of truth create_contract/update_contract validate against and the
# sales portal's template picker renders from.
CONTRACT_TEMPLATE_NAMES = (
    "general_remodeling",
    "homecare_basic",
    "homecare_plus",
    "homecare_complete",
    "homecare_estate",
)

# B8.7b: maps each of CONTRACT_TEMPLATE_NAMES' four 'homecare_*' values to
# the CommissionPlanConfig attribute holding that tier's monthly fee --
# single source of truth so CRMService.sign_contract's enrollment trigger
# doesn't hand-roll a second if/elif tier-to-field mapping.
HOMECARE_TIER_FEE_FIELDS = {
    "homecare_basic": "homecare_basic_monthly_fee",
    "homecare_plus": "homecare_plus_monthly_fee",
    "homecare_complete": "homecare_complete_monthly_fee",
    "homecare_estate": "homecare_estate_monthly_fee",
}


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
    assigned_user_id: Optional[int] = None  # FK-less ref to users (who's assigned)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ContractSigner:
    """One required signer on a Contract (B8.6d-b, multi-party signing).
    Additive on top of Contract.customer_signed_at/customer_signature_data
    -- a contract with no ContractSigner rows uses that original
    single-signer pair unchanged; a contract opted into multi-party
    signing (CRMService.add_contract_signers) tracks each party's
    signature here instead, and Contract.status only reaches 'signed'
    once every row's signed_at is non-null."""
    id: Optional[int] = None
    contract_id: Optional[int] = None
    party_role: str = ""  # e.g. 'customer', 'rep', 'project_manager', 'admin'
    signer_name: Optional[str] = None
    anchor_label: Optional[str] = None  # matches a pdf_service.SignatureAnchor.label
    signature_data: Optional[str] = None  # nullable until signed
    signed_at: Optional[str] = None  # nullable until signed
    created_at: str = field(default_factory=utc_now_iso)

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
    # B8.7a: which rep earns a commission on this invoice (FK-less ref to
    # users, same pattern as Contract.assigned_user_id/Estimate.assigned_
    # user_id). Invoice has no reliable link to a Contract/Opportunity to
    # trace a rep through (verified directly -- no contract_id/opportunity_id
    # column exists here), so this is populated at create_invoice() time
    # from the linked Customer's own assigned_user_id (falls back to None,
    # same "unclaimed" semantics as Customer.assigned_user_id, if the
    # customer itself has no owning rep -- see NEW-600 for the known gap
    # where an admin-converted lead's Customer can land unclaimed).
    assigned_user_id: Optional[int] = None
    # B8.7a: classifies what this invoice is for, distinct from any other
    # invoice -- 'assessment' is the only value B8.7a's trigger logic acts
    # on. No CHECK constraint (same reasoning as ContractSigner.party_role
    # -- a real DB's CHECK constraint can't be widened later without a full
    # table rebuild); validated in Python instead, mirroring
    # CommissionService._VALID_SOURCE_TYPES.
    invoice_type: str = "other"  # assessment, subscription, project, other
    # Phase 0-slim: itemized line items, mirroring WorkOrder.line_items'
    # shape ({"description", "quantity", "unit_cost", "total_cost"}).
    # When non-empty, create_invoice() computes `amount` server-side from
    # these rather than trusting a client-supplied amount.
    line_items: List[Dict[str, Any]] = field(default_factory=list)
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
    lead_id: Optional[int] = None  # B8.10b: pre-conversion correspondence -- a
    # lead's own communications (before it becomes a customer) link here
    # instead of customer_id, per Ish's 2026-09-23 decision that lead
    # correspondence must show up in the communications feed too.
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
    # Links this subcontractor to a real users row so staff_schedules
    # (user_id NOT NULL) can represent their schedule unchanged (Ish's
    # Phase 7 decision resolving NEW-486). Nullable -- most subcontractors
    # have no linked account.
    user_id: Optional[int] = None
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
    assigned_user_id: Optional[int] = None  # FK-less ref to users (who's assigned)
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
    an opaque dict (empty in the source data today, key shape unknown).

    Final scheduling round Phase 3: working_hours is the "Business Hours"
    envelope -- the overall open-for-business window an agent quotes for
    "what are your hours," and the outer bound that AppointmentType.
    scheduling_hours narrows per service type (see that class's docstring).
    Core does NOT enforce this window against Appointment.start_time/
    end_time anywhere (F3) -- appointments store UTC ISO timestamps with no
    timezone field, so a naive "10:00" vs. UTC-timestamp comparison here
    would be silently wrong by hours. Hours enforcement is entirely
    client-side in calendar.js (device-local Date math)."""
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
    working_hours_json.

    Final scheduling round Phase 3: scheduling_hours is a per-type
    narrowing of ScheduleConfig.working_hours ("Business Hours", the
    overall open-for-business envelope) -- e.g. a Consultation type
    bookable only 10:00-16:00 within a business that's open 08:00-18:00.
    An empty `{}` means "inherit business hours, no narrower window" --
    explicitly NOT "never available." As with working_hours, Core does not
    compare scheduling_hours against Appointment.start_time/end_time
    anywhere (F3); enforcement is entirely client-side in calendar.js."""
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
    user_id: int
    title: str
    start_time: str
    end_time: str
    status: str
    notes: Optional[str]
    id: Optional[int] = None
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


@dataclass
class Property:
    id: Optional[int] = None
    external_id: Optional[str] = None
    customer_id: Optional[int] = None
    address: str = ""
    parcel_number: Optional[str] = None
    property_type: Optional[str] = None
    year_built: Optional[int] = None
    square_footage: Optional[int] = None
    stories: Optional[int] = None
    roof_type: Optional[str] = None
    exterior_type: Optional[str] = None
    existing_systems: Dict[str, Any] = field(default_factory=dict)
    insurance_carrier: Optional[str] = None
    notes: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CommissionLedgerEntry:
    """Strictly append-only commission ledger entry (B8.1, D4,
    sales_rep_portal.md §4, Ish-approved 2026-09-16). Corrections and
    chargebacks are new rows referencing the original via
    reversed_entry_id -- never an UPDATE or DELETE of an existing row.
    See CommissionService.reverse_commission."""
    id: Optional[int] = None
    rep_user_id: Optional[int] = None
    source_type: str = "assessment"  # assessment, subscription_upsell, portfolio_override, bonus, adjustment, chargeback
    source_id: Optional[int] = None
    basis_amount: Optional[float] = None
    commission_rate_or_flat: Optional[float] = None
    commission_amount: float = 0.0
    status: str = "pending"  # pending, earned, paid, reversed
    earned_at: Optional[str] = None
    paid_at: Optional[str] = None
    reversed_entry_id: Optional[int] = None
    created_by: Optional[int] = None
    notes: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CommissionPlanConfig:
    """Singleton commission-plan configuration (B8.7a, D4,
    sales_rep_portal.md §4, Ish-approved 2026-09-16). There is exactly one
    row (id fixed to 1), same pattern as BusinessProfile/ScheduleConfig --
    lives in the DB (not Python constants) so a future dashboard round can
    edit these numbers without a schema change, per the standing "everything
    configurable must be dashboard-editable" rule (Ish, 2026-09-10).

    Values seeded from D4's real numbers, read directly from
    `Sales_Rep_Contract.docx` (not guessed): Phase 1 is a $100 flat
    commission per $299 Initial Property Assessment sold/booked/paid.
    The four HomeCare monthly tier fees (Basic/Plus/Complete/Estate) are
    seeded here for Phase 2's future bonus calculation (bonus = first
    month's fee minus the $100 already paid in Phase 1) -- not used by
    B8.7a's own trigger logic, which only reads assessment_flat_commission,
    but seeded now so the whole plan lives in one config row rather than
    being added piecemeal across B8.7a/b. Estate's real contract value is
    "$999+/mo" (variable/negotiated at the top end); the seeded value is
    the floor, not a hard ceiling -- no range mechanism is invented here,
    that's B8.7b/d's concern if it's ever needed.

    homecare_basic_monthly_fee repriced 179.0 -> 119.0 (Ish, 2026-09-22,
    mid-B8.7b) -- confirmed against the live home-care.html pricing
    table, which already reflects $119. database.py's _migrate_schema()
    carries a one-time corrective UPDATE for any DB whose singleton row
    was already seeded with the old 179.0 default before this change.

    portfolio_override_rate/portfolio_override_window_months (B8.7c, D6,
    Phase 3): the 5% residual on gross collected revenue from major GC
    projects, for 12 months from a customer's initial HomeCare enrollment.
    Snapshotted at each ledger write (CRMService.record_payment reads the
    live config value at write time, same as every other field here) so a
    later rate edit never retroactively changes historical ledger rows."""
    id: int = 1
    assessment_price: float = 299.0
    assessment_flat_commission: float = 100.0
    homecare_basic_monthly_fee: float = 119.0
    homecare_plus_monthly_fee: float = 399.0
    homecare_complete_monthly_fee: float = 599.0
    homecare_estate_monthly_fee: float = 999.0
    portfolio_override_rate: float = 0.05
    portfolio_override_window_months: int = 12
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HomecareSubscription:
    """One HomeCare enrollment (B8.7b, D4, sales_rep_portal.md §4,
    Ish-approved 2026-09-16). Created by CRMService.sign_contract as a
    best-effort side effect when a contract whose template_name is one of
    CONTRACT_TEMPLATE_NAMES' four 'homecare_*' values reaches
    status='signed'.

    monthly_fee is a SNAPSHOT of commission_plan_config's corresponding
    tier field at enrollment time -- deliberately not re-read live later,
    so a future dashboard edit to the plan config doesn't retroactively
    change historical Phase 2 bonus math.

    property_id is nullable: Contract has no direct property column (only
    project_id), and a contract's own project's property_id is itself
    nullable (B8.1) -- this is a best-effort resolution, not a guarantee.

    status is 'active'/'cancelled', no CHECK constraint at either layer
    -- same enum-like-text-column pattern as Invoice.invoice_type/
    ContractSigner.party_role (see database.py's homecare_subscriptions
    comment for why)."""
    id: Optional[int] = None
    customer_id: int = 0
    property_id: Optional[int] = None
    contract_id: int = 0
    tier: str = "homecare_basic"
    monthly_fee: float = 0.0
    originating_rep_user_id: Optional[int] = None
    status: str = "active"
    enrolled_at: str = field(default_factory=utc_now_iso)
    cancelled_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AssessmentRecord:
    """Property/appointment assessment record (B8.5b, sales_rep_portal.md
    §5/§6/§7, resolves NEW-567's deferred decision: property ->
    assessment_record -> documents via evidence_document_ids is the real
    mechanism for pre-project property photos, not a Document.property_id
    schema change). checklist mirrors Property.existing_systems' pattern
    (opaque dict, structure not yet settled). evidence_document_ids is a
    KNOWN, ACCEPTED LIMITATION: an unenforced list of Document.id values,
    no FK/cascade/validation -- a deleted Document leaves a dangling id."""
    id: Optional[int] = None
    appointment_id: Optional[int] = None
    property_id: Optional[int] = None
    checklist: Dict[str, Any] = field(default_factory=dict)
    evidence_document_ids: List[int] = field(default_factory=list)
    customer_statements: Optional[str] = None
    created_by: Optional[int] = None
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Territory:
    """Territory management lookup (B8.9a, sales_rep_portal.md §5 B8.9,
    corrected scope 2026-09-23). Explicit, human-set only -- no ZIP/
    geocoding inference, see database.py's territories table comment for
    why. `code` is a short rep-facing label (e.g. "NORTH"), NOT a ZIP
    code."""
    id: Optional[int] = None
    name: str = ""
    code: Optional[str] = None
    notes: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FinancingRecord:
    """Third-party financing application/status tracking for a project
    (B8.8b-1, sales_rep_portal.md §4/§8). Deliberately inert this round --
    reads into nothing else. B8.8b-2 will wire ``amount_financed`` into
    ``FinanceService.get_ar_aging``/``get_financial_summary``/
    ``get_project_pnl`` as an AR offset for records whose
    ``application_status IN ('approved', 'funded') AND status == 'active'``
    -- BOTH conditions together, never application_status alone: a
    voided record can still carry application_status='approved' (voiding
    never clears it), so status='active' is load-bearing for the offset,
    not incidental. That eligibility concept belongs entirely to
    B8.8b-2, not here.

    invoice_id is nullable: financing is often initiated before the
    invoice exists.

    customer_contribution is the customer's OWN out-of-pocket share of
    the financed project (already reflected in invoices.balance_due if
    paid via the normal record_payment path) -- it must NEVER be summed
    into the AR offset B8.8b-2 computes. amount_financed is the only
    field B8.8b-2 will ever read from; a future implementer should not
    double-count by also reading customer_contribution.

    application_status ('submitted'/'approved'/'funded'/'denied'/
    'cancelled') and status ('active'/'voided', an administrative flag
    that gates whether a row counts at all -- NOT independent of
    application_status for AR-offset purposes, see above) carry no CHECK
    constraint at the DB layer, same enum-like-text-column pattern as
    ContractSigner.party_role/Invoice.invoice_type -- FinancingService
    enforces both at the service layer instead."""
    id: Optional[int] = None
    project_id: int = 0
    invoice_id: Optional[int] = None
    provider: Optional[str] = None
    application_status: str = "submitted"
    amount_financed: float = 0.0
    customer_contribution: float = 0.0
    document_ids: List[int] = field(default_factory=list)
    status: str = "active"
    created_by: Optional[int] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# B8.12b, sales_rep_portal.md §B8.12 (`production handoff checklist`): the
# fixed set of 7 required items, confirmed against the source doc's own
# text ("scope, materials, customer selections, permits, insurance info,
# financing, deposit status") -- NOT invented here. Always all 7 present on
# every checklist row; each is individually 'done'/'na'/'pending', never a
# partial/some-required scheme beyond that (Ish, 2026-09-24). A plain
# Python tuple validated at the service layer, same "can't be widened
# later without a full table rebuild" reasoning as CONTRACT_TEMPLATE_NAMES
# -- not a DB CHECK constraint.
PRODUCTION_HANDOFF_CHECKLIST_ITEMS = (
    "scope",
    "materials",
    "customer_selections",
    "permits",
    "insurance",
    "financing",
    "deposit",
)

PRODUCTION_HANDOFF_ITEM_STATUSES = ("pending", "done", "na")


@dataclass
class ProductionHandoffChecklist:
    """Sales-to-production handoff gate (B8.12b). Keyed on `project_id`,
    NOT `contract_id` as sales_rep_portal.md's B8.12 text literally says --
    deliberate reconciliation, not an arbitrary choice: Invoice (the other
    half of the completion guard, for deposit status) has no contract_id
    column at all (verified directly, see Invoice.assigned_user_id's own
    B8.7a comment), only project_id, while Contract does carry project_id.
    Keying this table on contract_id would make the deposit half of the
    guard unreachable. The completion guard resolves "is there a signed
    contract for this project" via a direct `contracts.status = 'signed'`
    existence check (mirroring crm_service.py's
    `_resolve_gc_contract_for_portfolio_override` gate-1b query shape) --
    it does not store or pin to one specific contract row, since a project
    can have more than one contract (e.g. a HomeCare enrollment alongside
    a general_remodeling contract) and the guard only needs "a signed one
    exists", not "which one".

    One checklist per project (UNIQUE(project_id) at the DB layer,
    financing_records.invoice_id's own precedent for this shape of
    guard). FK-less by design on project_id/completed_by/created_by,
    matching financing_records' project_id/invoice_id/created_by
    precedent -- a checklist row must survive a linked row's deletion
    without cascading.

    `completed_at`/`completed_by` are both nullable and only ever set
    together, atomically, by `CRMService.complete_handoff_checklist` once
    every guard condition passes (contract signed + qualifying deposit
    payment recorded + every one of the 7 items done-or-na)."""
    id: Optional[int] = None
    project_id: int = 0
    items: Dict[str, str] = field(
        default_factory=lambda: {k: "pending" for k in PRODUCTION_HANDOFF_CHECKLIST_ITEMS}
    )
    completed_at: Optional[str] = None
    completed_by: Optional[int] = None
    created_by: Optional[int] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

