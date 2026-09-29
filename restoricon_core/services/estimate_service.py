"""
Codey-Estimator Integration, Phase B9.2 -- EstimateService.

Domain engine for the estimating workflow: header CRUD, line-item CRUD with
server-authoritative pricing via the vendored `codey_estimator.calc` engine,
versioning (`revise()`), the actor-driven workflow state machine
(`transition()`), claim/unclaim/reassign, decision recording
(accept/decline/changes-requested, with the accept -> Contract invariant),
preview, and the customer-facing allow-list projection (`to_customer_view()`).
Sits alongside `CRMService`/`FinanceService`/`OperationsService` as its own
file, per `codey_estimator_service.md` §1's decision (the estimate domain --
5 tables, a locking workflow, a numbering generator, and a calc-engine
integration point -- is a bigger unit of concern than any existing
`crm_service.py` `# SECTION`).

**Scope actually built** (B9.2 core round plus this round's four additions --
see that round's task brief for the full breakdown):
    create, get, list, update_header
    add_line, update_line, remove_line, reorder_lines
    revise (versioning)
    claim, unclaim (NEW-534-precedent race-safe conditional UPDATE)
    reassign (manager-tier override, bypasses the claim race)
    transition (the public actor-driven workflow state machine, §1.5;
        DRAFT/APPROVED_INTERNAL -> SENT creates a real estimate_share_links
        row and locks the current version; the D5 hard internal-review gate
        is enforced via the pinned `estimates.internal_review_required`
        column, never a live join against users.requires_estimate_approval)
    record_decision (accepted/declined/changes_requested; an 'accepted'
        decision now also creates a real Contract row, in the same
        transaction as the acceptance write and the version lock -- see
        record_decision()'s own docstring for the accept -> contract
        invariant and its disclosed limitation)
    preview, to_customer_view
    lock-immutability enforcement (checked in-transaction before every
    line/header write; the DB triggers are the backstop)

**Deliberately NOT built this round** (each is a real, identified gap --
logged to NEW_ISSUES.md rather than silently built or silently dropped):

  - `convert()` (the ACCEPTED -> CONVERTED Project-creation half, B9.8) --
    gated on a signed Contract per §9 item 4, out of this round's scope.
  - The expiry sweep (B9.2b), API routes (B9.3), the public share-link
    lookup/decision routes (B9.4 -- this round creates real share-link
    rows but nothing yet resolves a raw token back to one), the
    staff/admin UI (B9.5/B9.6), and the quote-portal D8 migration (B9.7).
  - `_lock_version()` remains an internal-use method -- `transition()`'s
    `send` step now uses its shared core (`_lock_version_write()`)
    directly inside its own transaction, the same pattern
    `record_decision()` already established, never through
    `_lock_version()` itself (sqlite3 does not allow a nested `BEGIN`).

**Two real schema gaps found while implementing calc-engine integration**
(logged to NEW_ISSUES.md rather than silently patched with an unreviewed
schema change):
  - No column persists `codey_estimator.dto.TaxMethod` (none / materials_only
    / taxable_lines) per estimate/version -- `DEFAULT_TAX_METHOD` below
    (`TaxMethod.MATERIALS_ONLY`, the dto's own default) is used unconditionally.
  - No column persists `codey_estimator.dto.LaborRateType` (hourly /
    fixed_per_unit / fixed_flat) per line -- `_row_to_line_input()` derives
    it from `labor_unit` (`"HR"` -> HOURLY, else FIXED_PER_UNIT); FIXED_FLAT
    is unrepresentable under the current schema.
  - No column persists an estimate-level `EstimateDiscount` (kind/value) --
    `estimate_discount=None` is passed unconditionally; only per-line
    `discount_cents` (an input column on `estimate_line_items`) is supported
    this round.
"""

from __future__ import annotations

import dataclasses
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional

from codey_estimator.calc.engine import CALC_ENGINE_VERSION, calculate
from codey_estimator.dto import (
    EquipmentInput,
    EstimateInput,
    EstimateResult,
    LaborInput,
    LaborRateType,
    LineInput,
    LineResult,
    LineType,
    MaterialInput,
    SubcontractorInput,
    TaxMethod,
)
from codey_estimator.dto import to_customer_view as _lib_to_customer_view
from codey_estimator.errors import EstimatorError

from ..auth import (
    AuthContext,
    PERM_APPROVE_ESTIMATES,
    PERM_READ_ALL_ESTIMATES,
    PERM_READ_ESTIMATE_COSTS,
    PERM_READ_ESTIMATES,
    PERM_READ_OWN_ESTIMATES,
    PERM_REASSIGN_ESTIMATES,
    PERM_SEND_ESTIMATES,
    PERM_WRITE_ESTIMATES,
    ROLE_ADMIN,
    ROLE_CUSTOMER,
    ROLE_MANAGER,
    ROLE_PROJECT_MANAGER,
    ROLE_SALES,
    ROLE_SALES_MANAGER,
)
from ..database import DatabaseManager
from ..models import (
    EstimateDecision,
    EstimateHeader,
    EstimateLineItem,
    EstimateShareLink,
    EstimateVersion,
    utc_now_iso,
)
from .audit_service import AuditService, build_audit_details
# ClaimConflictError: reused, not redefined -- crm_service.py does not import
# estimate_service.py (confirmed, no cycle), and the NEW-534 claim-workflow
# precedent this module's claim()/unclaim() follow is defined there. A
# future route layer needs exactly one class to map to 409 for every
# claim-shaped entity, not a second, estimate-specific duplicate.
from .crm_service import ClaimConflictError

# Material-markup default (D-task, 2026-09-29): a material line, or a
# 'combined' line's material component, that the caller does not supply an
# explicit `material_markup_bp` for gets this default. 3000bp = 30.00% --
# confirmed against `codey_estimator.money.apply_markup(cost_cents, bp) ==
# cost_cents * (10_000 + bp) / 10_000`, the same basis-points convention
# already used by `equipment_markup_bp`/`sub_markup_bp`/`waste_pct_bp`.
# Hardcoded module constant this round -- the tenant-configurable-default
# feature (NEW-702) is explicitly deferred.
DEFAULT_MATERIAL_MARKUP_BP = 3000

# See the module docstring's "schema gaps" note -- no column exists yet to
# persist a per-estimate tax method, so every calculation this round uses
# the vendored library's own default.
DEFAULT_TAX_METHOD = TaxMethod.MATERIALS_ONLY

# D10 (codey_estimator_service.md §1.7): fixed, versioned consent text baked
# into the service, required on every 'accepted' decision.
CONSENT_TEXT_V1 = (
    "By accepting this estimate, you agree to the scope of work, pricing, "
    "and terms presented in this version of the estimate."
)

# §1.4: roles a reassign() target must hold -- rejecting reassignment to a
# technician/customer/subcontractor/ai_agent account with a ValueError.
_REASSIGNABLE_ROLES = frozenset({ROLE_SALES, ROLE_SALES_MANAGER, ROLE_PROJECT_MANAGER, ROLE_MANAGER, ROLE_ADMIN})

# §4.2: share-link default validity window (D10) unless the estimate's own
# expires_at is sooner.
_SHARE_LINK_DEFAULT_DAYS = 30

# §1.5's allowed-transitions table, actor-driven rows only. Keys are
# (from_status, to_status); the value names the action for audit/error
# messages. Every transition NOT in this table is either genuinely illegal
# or one of §1.5's "not actor-driven" rows (VIEWED / ACCEPTED / DECLINED /
# CHANGES_REQUESTED / EXPIRED / CONVERTED) -- transition() refuses both
# alike, but with a distinguishing error message for the latter so a caller
# doesn't mistake "wrong door" for "no such door".
_ACTOR_DRIVEN_TRANSITIONS: Dict[tuple, str] = {
    ("DRAFT", "INTERNAL_REVIEW"): "submit_for_review",
    ("DRAFT", "SENT"): "send",
    ("INTERNAL_REVIEW", "APPROVED_INTERNAL"): "approve",
    ("INTERNAL_REVIEW", "DRAFT"): "reject_review",
    ("APPROVED_INTERNAL", "SENT"): "send",
    ("DRAFT", "CANCELLED"): "cancel",
    ("INTERNAL_REVIEW", "CANCELLED"): "cancel",
    ("APPROVED_INTERNAL", "CANCELLED"): "cancel",
    ("SENT", "CANCELLED"): "cancel",
    ("VIEWED", "CANCELLED"): "cancel",
}

# The "not actor-driven" carve-out rows §1.5 names explicitly -- listed so
# transition() can tell a caller "that transition exists but isn't reached
# this way" instead of a bare "invalid transition".
_SYSTEM_DRIVEN_TARGET_STATUSES = frozenset({"VIEWED", "ACCEPTED", "DECLINED", "CHANGES_REQUESTED", "EXPIRED", "CONVERTED"})

# Every column on `estimate_line_items` a caller may set directly via
# add_line()/update_line() -- i.e. every INPUT column, excluding the id/FK/
# timestamp columns and the columns codey_estimator.calc writes exclusively
# (packages_needed, material_cost_cents, labor_cost_cents, cost_total_cents,
# sell_total_cents, tax_cents, line_total_cents -- see the DDL comment at
# database.py's estimate_line_items block). Used both as add_line()'s
# defaults table and as the unknown-field guard on both add_line() and
# update_line().
_LINE_INPUT_DEFAULTS: Dict[str, Any] = {
    "sort_order": 0,
    "line_type": None,  # required, no default
    "section": None,
    "category": None,
    "description": None,
    "customer_description": None,
    "visible_to_customer": 1,
    "price_book_item_id": None,
    "retailer_product_id": None,
    "price_observation_id": None,
    "retailer_code_snapshot": None,
    "product_title_snapshot": None,
    "package_qty": None,
    "package_unit": None,
    "unit_cost_cents": None,
    "quantity": None,
    "unit": None,
    "waste_pct_bp": 0,
    "material_markup_bp": 0,
    "labor_type": None,
    "labor_rate_id": None,
    "labor_qty": None,
    "labor_unit": None,
    "labor_cost_rate_cents": None,
    "labor_bill_rate_cents": None,
    "equipment_id": None,
    "equipment_cost_cents": None,
    "equipment_markup_bp": 0,
    "subcontractor_id": None,
    "sub_cost_cents": None,
    "sub_markup_bp": 0,
    "taxable": 1,
    "discount_cents": 0,
    "price_override_cents": None,
    "override_reason": None,
    "internal_note": None,
}
_ALLOWED_LINE_INPUT_FIELDS = frozenset(_LINE_INPUT_DEFAULTS)

# Columns cloned byte-for-byte from an old locked version's line into the
# new version's line by revise() -- includes the already-computed cost/sell
# output columns too (§1.6: "prices don't silently refresh"; a clone must
# match the old version's rendered numbers exactly until a later edit
# triggers recalculation via add_line()/update_line()).
_LINE_ITEM_CLONE_COLUMNS = (
    "sort_order", "line_type", "section", "category", "description",
    "customer_description", "visible_to_customer", "price_book_item_id",
    "retailer_product_id", "price_observation_id", "retailer_code_snapshot",
    "product_title_snapshot", "package_qty", "package_unit", "unit_cost_cents",
    "quantity", "unit", "waste_pct_bp", "material_markup_bp", "labor_type",
    "labor_rate_id", "labor_qty", "labor_unit", "labor_cost_rate_cents",
    "labor_bill_rate_cents", "equipment_id", "equipment_cost_cents",
    "equipment_markup_bp", "subcontractor_id", "sub_cost_cents", "sub_markup_bp",
    "taxable", "discount_cents", "price_override_cents", "override_reason",
    "packages_needed", "material_cost_cents", "labor_cost_cents",
    "cost_total_cents", "sell_total_cents", "tax_cents", "line_total_cents",
    "internal_note",
)

_ALLOWED_HEADER_UPDATE_FIELDS = frozenset(
    {"title", "terms", "customer_notes", "expires_at", "property_id", "opportunity_id", "lead_id"}
)

# D9 line-level cost gate (mirrors _attach_cost_fields()'s header gate,
# PERM_READ_ESTIMATE_COSTS): the true cost/markup/margin columns plus the
# two staff-internal free-text columns. Deliberately excludes exactly three
# fields, none of which are gated: price_override_cents (the overridden
# sell price -- what the customer is actually charged), line_total_cents
# (the final per-line charge including tax), and tax_cents -- so a customer
# without cost visibility still sees a coherent per-line and total charge
# even with the pre-tax sell_total_cents subtotal hidden. See
# _gate_line_cost_fields()'s docstring for the price_override_cents/
# override_reason split.
_LINE_COST_INTERNAL_FIELDS = frozenset(
    {
        "unit_cost_cents", "material_markup_bp", "labor_cost_rate_cents",
        "equipment_cost_cents", "equipment_markup_bp", "sub_cost_cents",
        "sub_markup_bp", "material_cost_cents", "labor_cost_cents",
        "cost_total_cents", "sell_total_cents", "override_reason", "internal_note",
    }
)


def _field(data: Any, key: str) -> Any:
    """Read `key` from either a plain dict (caller input, may be missing the
    key entirely) or a `sqlite3.Row` (a full `SELECT *` row, so the column
    always exists but may be NULL) uniformly."""
    if isinstance(data, sqlite3.Row):
        return data[key]
    return data.get(key)


def _has_material_component(data: Any) -> bool:
    """True if `data` (a caller input dict OR a persisted
    `estimate_line_items` row) carries a material cost component --
    `unit_cost_cents` is set. Used identically in two places: (1)
    add_line()'s `material_markup_bp` default gate, and (2)
    `_row_to_line_input()`'s decision to attach a `MaterialInput` when
    calling `codey_estimator.calc.calculate()`. Using the SAME predicate in
    both places is deliberate (NEW-700 in the task brief): a 'combined'
    line's material portion must never silently ship at the engine's raw 0%
    default just because the gate that decided to attach a `MaterialInput`
    disagreed with the gate that decided to default its markup -- there is
    exactly one definition of "this line has a material component," not two
    that could drift.
    """
    return _field(data, "unit_cost_cents") is not None


def _has_labor_component(data: Any) -> bool:
    return _field(data, "labor_cost_rate_cents") is not None or _field(data, "labor_bill_rate_cents") is not None


def _has_equipment_component(data: Any) -> bool:
    return _field(data, "equipment_cost_cents") is not None


def _has_subcontractor_component(data: Any) -> bool:
    return _field(data, "sub_cost_cents") is not None


class EstimateService:
    """Manages estimate headers, versions, line items, and decisions."""

    def __init__(self, db: DatabaseManager, audit: AuditService):
        self.db = db
        self.audit = audit

    # ------------------------------------------------------------------
    # Numbering
    # ------------------------------------------------------------------

    def _next_estimate_number(self, conn: sqlite3.Connection, year: int) -> str:
        """Race-safe, per-year `EST-{year}-{seq:04d}` generator. Caller must
        already hold `conn`'s write transaction (a `BEGIN IMMEDIATE` already
        issued) -- SQLite's write lock, acquired at `BEGIN IMMEDIATE`, is
        what makes the read-then-write below safe under real concurrent
        writers (see `codey_estimator_service.md` §2's full NEW-534-precedent
        reasoning: a bare `SELECT MAX(...)+1` has the identical race shape
        NEW-534's claim-workflow fix closed for leads/opportunities/tasks).
        """
        conn.execute(
            "INSERT INTO estimate_number_sequences (year, next_seq) VALUES (?, 2) "
            "ON CONFLICT(year) DO UPDATE SET next_seq = next_seq + 1;",
            (year,),
        )
        row = conn.execute(
            "SELECT next_seq FROM estimate_number_sequences WHERE year = ?;", (year,)
        ).fetchone()
        seq = row["next_seq"] - 1
        return f"EST-{year}-{seq:04d}"

    # ------------------------------------------------------------------
    # Header CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        customer_id: int,
        actor: AuthContext,
        project_id: Optional[int] = None,
        opportunity_id: Optional[int] = None,
        lead_id: Optional[int] = None,
        property_id: Optional[int] = None,
        title: Optional[str] = None,
        terms: Optional[str] = None,
        customer_notes: Optional[str] = None,
        expires_at: Optional[str] = None,
        assigned_to_user_id: Optional[int] = None,
        tax_rate_bp: int = 0,
    ) -> EstimateHeader:
        """Create a new estimate header plus its version 1 (empty, unlocked
        draft). `created_by_user_id`/`created_by_name`/`estimate_number`/
        `workflow_status` are NEVER parameters -- there is no code path by
        which a request body could set them (the actual fix for the
        `Estimate(**json_body)` client-supplied-`estimate_number` gap
        `codey_estimator_service.md` §0 names).

        **D5 / §9 item 5**: `internal_review_required` is computed HERE,
        once, and pinned onto the row -- `(the creator's current
        users.requires_estimate_approval flag) OR (actor.actor_type ==
        "agent")`. `transition()` reads only this pinned column later,
        never a live join against `users.requires_estimate_approval` --
        the creator's flag or role could change after this estimate exists,
        and the review requirement must reflect what was true at creation
        time, same reasoning as `created_by_name` being a snapshot rather
        than a live join to `users.full_name`.
        """
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to write estimates")
        if not (0 <= tax_rate_bp <= 10_000):
            raise ValueError("tax_rate_bp must be between 0 and 10000")

        conn = self.db.get_connection()
        now = utc_now_iso()
        year = int(now[:4])
        creator_row = conn.execute(
            "SELECT full_name, requires_estimate_approval FROM users WHERE id = ?;", (actor.user_id,)
        ).fetchone()
        created_by_name = creator_row["full_name"] if creator_row is not None else None
        creator_requires_approval = bool(creator_row["requires_estimate_approval"]) if creator_row is not None else False
        internal_review_required = 1 if (creator_requires_approval or actor.actor_type == "agent") else 0
        assignee = assigned_to_user_id if assigned_to_user_id is not None else actor.user_id
        if expires_at is None:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            estimate_number = self._next_estimate_number(conn, year)
            cursor = conn.execute(
                """
                INSERT INTO estimates (
                    estimate_number, customer_id, project_id, created_by_user_id,
                    created_by_name, assigned_to_user_id, opportunity_id, lead_id,
                    property_id, title, source, workflow_status, expires_at,
                    customer_notes, terms, internal_review_required, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'engine', 'DRAFT', ?, ?, ?, ?, ?, ?);
                """,
                (
                    estimate_number, customer_id, project_id, actor.user_id,
                    created_by_name, assignee, opportunity_id, lead_id,
                    property_id, title, expires_at, customer_notes, terms,
                    internal_review_required, now, now,
                ),
            )
            estimate_id = cursor.lastrowid

            version_cursor = conn.execute(
                """
                INSERT INTO estimate_versions (
                    estimate_id, version_number, is_locked, calc_engine_version,
                    tax_rate_bp, terms_snapshot, customer_notes_snapshot,
                    created_by_user_id, created_at
                ) VALUES (?, 1, 0, ?, ?, ?, ?, ?, ?);
                """,
                (estimate_id, CALC_ENGINE_VERSION, tax_rate_bp, terms, customer_notes, actor.user_id, now),
            )
            version_id = version_cursor.lastrowid
            conn.execute("UPDATE estimates SET current_version_id = ? WHERE id = ?;", (version_id, estimate_id))

        row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        header = self._row_to_header(row)
        self.audit.log(
            action="create",
            entity_type="estimate",
            entity_id=estimate_id,
            change_summary=f"Created estimate {estimate_number}",
            actor=actor,
            details=build_audit_details(after=header.to_dict()),
        )
        return header

    def _can_view_estimate(self, row: sqlite3.Row, actor: AuthContext) -> bool:
        if actor.role == ROLE_CUSTOMER:
            return actor.has_permission(PERM_READ_OWN_ESTIMATES) and actor.customer_id == row["customer_id"]
        if actor.has_permission(PERM_READ_ALL_ESTIMATES):
            return True
        if actor.has_permission(PERM_READ_ESTIMATES) or actor.has_permission(PERM_READ_OWN_ESTIMATES):
            # §9 item 1: an unassigned (unclaimed) estimate is visible to
            # any actor in this narrowed-view bucket too, not just "mine or
            # assigned to me" -- mirrors NEW-534's claim-workflow
            # visible-but-claimable pattern for leads/opportunities/tasks.
            # Whether the actor can actually claim() it is claim()'s own,
            # separate PERM_WRITE_ESTIMATES gate.
            return (
                row["created_by_user_id"] == actor.user_id
                or row["assigned_to_user_id"] == actor.user_id
                or row["assigned_to_user_id"] is None
            )
        return False

    def _attach_cost_fields(self, conn: sqlite3.Connection, header: EstimateHeader, current_version_id: Optional[int], actor: AuthContext) -> None:
        if not actor.has_permission(PERM_READ_ESTIMATE_COSTS) or current_version_id is None:
            return
        v = conn.execute(
            "SELECT cost_total_cents, gross_profit_cents, gross_margin_bp FROM estimate_versions WHERE id = ?;",
            (current_version_id,),
        ).fetchone()
        if v is not None:
            header.cost_total_cents = v["cost_total_cents"]
            header.gross_profit_cents = v["gross_profit_cents"]
            header.gross_margin_bp = v["gross_margin_bp"]

    def _gate_line_cost_fields(self, line: EstimateLineItem, actor: AuthContext) -> None:
        """Line-level mirror of `_attach_cost_fields()`'s header gate (D9,
        `PERM_READ_ESTIMATE_COSTS`) -- `_row_to_line()` reads every column
        unconditionally, so this nulls out the cost/margin-revealing and
        staff-internal fields in place when the actor lacks the permission.
        `price_override_cents` (the overridden sell price, i.e. what the
        customer is actually charged) stays visible -- only
        `override_reason` (the staff-facing rationale for the override) is
        gated, alongside the true cost/markup/margin fields."""
        if actor.has_permission(PERM_READ_ESTIMATE_COSTS):
            return
        for f in _LINE_COST_INTERNAL_FIELDS:
            setattr(line, f, None)

    def _gate_preview_result_cost_fields(self, result: EstimateResult, actor: AuthContext) -> EstimateResult:
        """B9.3 code-review fix (Critical): `preview()`'s cost/margin gate.

        `preview()` returns `codey_estimator.dto.EstimateResult` -- a frozen,
        `slots=True` dataclass tree the vendored engine produces directly,
        not an `EstimateHeader`/`EstimateLineItem` -- so `_attach_cost_fields()`/
        `_gate_line_cost_fields()` (which mutate `restoricon_core.models`
        dataclasses in place) cannot be reused unmodified. This is the same
        PERM_READ_ESTIMATE_COSTS principle applied to that different shape,
        via `dataclasses.replace()` since the dto is frozen.

        Header-level cost/margin fields nulled: `material_cost_cents`,
        `labor_cost_cents`, `equipment_cost_cents`, `sub_cost_cents`,
        `cost_total_cents`, `gross_profit_cents`, `gross_margin_bp`,
        `markup_effective_bp` -- mirrors `_attach_cost_fields()`'s
        `cost_total_cents`/`gross_profit_cents`/`gross_margin_bp` gate, plus
        the raw per-component costs `get()` never even exposes at all.

        Per-line, two families are nulled: (1) `LineResult`'s own
        cost/sell-component breakdown (`material_cost_cents`,
        `material_sell_cents`, `labor_cost_cents`, `labor_sell_cents`,
        `equipment_cost_cents`, `equipment_sell_cents`, `sub_cost_cents`,
        `sub_sell_cents`, `cost_total_cents`, `components_sell_cents`,
        `sell_before_discount_cents`, `sell_total_cents`,
        `allocated_discount_cents`, `net_sell_cents`, `taxable_amount_cents`)
        -- the vendored engine has no gated/ungated split of its own, so
        every field finer-grained than the customer-safe aggregate
        (`line_total_cents`, kept visible, same as the persisted-model gate
        keeps it) is treated as cost/margin-revealing; and (2) the nested,
        echoed `LineResult.input` (`LineInput`), which duplicates the raw
        cost-side inputs (`material.unit_cost_cents`,
        `material.material_markup_bp`, `labor.labor_cost_rate_cents`,
        `equipment.equipment_cost_cents`, `equipment.equipment_markup_bp`,
        `subcontractor.sub_cost_cents`, `subcontractor.sub_markup_bp`) plus
        the two staff-internal free-text fields (`override_reason`,
        `internal_note`) -- the exact same fields `_LINE_COST_INTERNAL_FIELDS`
        gates on the persisted model, just reached through the echoed input
        tree instead of a DB row. `price_override_cents` and the sell-side
        `labor_bill_rate_cents` stay visible on `input`, matching
        `_gate_line_cost_fields()`'s deliberate price_override_cents
        exception.

        Every nulled field is typed `int`/`str` (never `Optional[...]`) in
        the vendored `codey_estimator.dto` -- `None` here technically
        disagrees with those type hints, but matches this codebase's own
        established convention (see `models.py`'s `EstimateLineItem` comment
        on why cost fields are `Optional[int]`: an actual `0` is a legitimate
        "at cost" value, so `None` must be the unambiguous "withheld"
        sentinel) rather than inventing a second convention. The vendored
        `codey_estimator.dto` module itself is never modified to accommodate
        this -- gating happens entirely on this side, via `replace()`.
        """
        if actor.has_permission(PERM_READ_ESTIMATE_COSTS):
            return result

        def _gate_line(line: LineResult) -> LineResult:
            li = line.input
            material = (
                dataclasses.replace(li.material, unit_cost_cents=None, material_markup_bp=None)
                if li.material is not None else None
            )
            labor = (
                dataclasses.replace(li.labor, labor_cost_rate_cents=None)
                if li.labor is not None else None
            )
            equipment = (
                dataclasses.replace(li.equipment, equipment_cost_cents=None, equipment_markup_bp=None)
                if li.equipment is not None else None
            )
            subcontractor = (
                dataclasses.replace(li.subcontractor, sub_cost_cents=None, sub_markup_bp=None)
                if li.subcontractor is not None else None
            )
            gated_input = dataclasses.replace(
                li,
                material=material,
                labor=labor,
                equipment=equipment,
                subcontractor=subcontractor,
                override_reason=None,
                internal_note=None,
            )
            return dataclasses.replace(
                line,
                input=gated_input,
                material_cost_cents=None,
                material_sell_cents=None,
                labor_cost_cents=None,
                labor_sell_cents=None,
                equipment_cost_cents=None,
                equipment_sell_cents=None,
                sub_cost_cents=None,
                sub_sell_cents=None,
                cost_total_cents=None,
                components_sell_cents=None,
                sell_before_discount_cents=None,
                sell_total_cents=None,
                allocated_discount_cents=None,
                net_sell_cents=None,
                taxable_amount_cents=None,
            )

        gated_lines = tuple(_gate_line(line) for line in result.lines)
        return dataclasses.replace(
            result,
            lines=gated_lines,
            material_cost_cents=None,
            labor_cost_cents=None,
            equipment_cost_cents=None,
            sub_cost_cents=None,
            cost_total_cents=None,
            gross_profit_cents=None,
            gross_margin_bp=None,
            markup_effective_bp=None,
        )

    def get(self, estimate_id: int, actor: AuthContext, *, include_lines: bool = False) -> Optional[EstimateHeader]:
        """D9 cost gating + §1.2 ownership narrowing ("mine or assigned to
        me", plus the unclaimed/unassigned bucket per §9 item 1 -- see
        `_can_view_estimate()`)."""
        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        if row is None:
            return None
        if not self._can_view_estimate(row, actor):
            raise PermissionError("Actor lacks permission to view this estimate")

        header = self._row_to_header(row)
        self._attach_cost_fields(conn, header, row["current_version_id"], actor)

        if include_lines and row["current_version_id"] is not None:
            line_rows = conn.execute(
                "SELECT * FROM estimate_line_items WHERE estimate_version_id = ? ORDER BY sort_order, id;",
                (row["current_version_id"],),
            ).fetchall()
            lines = [self._row_to_line(r) for r in line_rows]
            for line in lines:
                self._gate_line_cost_fields(line, actor)
            header.lines = lines
        return header

    def list(
        self,
        actor: AuthContext,
        *,
        customer_id: Optional[int] = None,
        project_id: Optional[int] = None,
        assigned_to_user_id: Optional[int] = None,
        created_by_user_id: Optional[int] = None,
        workflow_status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        q: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[EstimateHeader]:
        conn = self.db.get_connection()
        clauses: List[str] = []
        params: List[Any] = []

        if actor.role == ROLE_CUSTOMER:
            if not actor.has_permission(PERM_READ_OWN_ESTIMATES) or actor.customer_id is None:
                raise PermissionError("Actor lacks permission to list estimates")
            clauses.append("customer_id = ?")
            params.append(actor.customer_id)
        elif actor.has_permission(PERM_READ_ALL_ESTIMATES):
            pass
        elif actor.has_permission(PERM_READ_ESTIMATES) or actor.has_permission(PERM_READ_OWN_ESTIMATES):
            # §9 item 1: the unassigned/unclaimed bucket is its own visible
            # row set for this narrowed view, mirroring _can_view_estimate().
            clauses.append("(created_by_user_id = ? OR assigned_to_user_id = ? OR assigned_to_user_id IS NULL)")
            params.extend([actor.user_id, actor.user_id])
        else:
            raise PermissionError("Actor lacks permission to list estimates")

        if customer_id is not None:
            clauses.append("customer_id = ?"); params.append(customer_id)
        if project_id is not None:
            clauses.append("project_id = ?"); params.append(project_id)
        if assigned_to_user_id is not None:
            clauses.append("assigned_to_user_id = ?"); params.append(assigned_to_user_id)
        if created_by_user_id is not None:
            clauses.append("created_by_user_id = ?"); params.append(created_by_user_id)
        if workflow_status is not None:
            clauses.append("workflow_status = ?"); params.append(workflow_status)
        if date_from is not None:
            clauses.append("created_at >= ?"); params.append(date_from)
        if date_to is not None:
            clauses.append("created_at <= ?"); params.append(date_to)
        if q:
            clauses.append("(estimate_number LIKE ? OR title LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like])

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"SELECT * FROM estimates {where} ORDER BY id DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()

        headers = [self._row_to_header(r) for r in rows]
        for header, row in zip(headers, rows):
            self._attach_cost_fields(conn, header, row["current_version_id"], actor)
        return headers

    def update_header(self, estimate_id: int, updates: Dict[str, Any], actor: AuthContext) -> EstimateHeader:
        """Allow-list update of mutable header fields, only while the
        current version is unlocked (§1.3). `created_by_user_id`,
        `created_by_name`, `assigned_to_user_id`, `workflow_status`,
        `estimate_number` are deliberately NOT in the allow-list --
        reassignment/transitions are their own (deferred) methods.
        """
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to write estimates")
        data = dict(updates)
        unknown = set(data) - _ALLOWED_HEADER_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"update_header: unknown/disallowed field(s) {sorted(unknown)}")

        conn = self.db.get_connection()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
            if row is None:
                raise ValueError(f"Estimate {estimate_id} not found")
            if row["current_version_id"] is not None:
                v = conn.execute(
                    "SELECT is_locked FROM estimate_versions WHERE id = ?;", (row["current_version_id"],)
                ).fetchone()
                if v is not None and v["is_locked"]:
                    raise ValueError(
                        "cannot update a header field once the current version is locked; use revise() first"
                    )
            before = self._row_to_header(row)
            if not data:
                return before

            now = utc_now_iso()
            set_clause = ", ".join(f"{k} = :{k}" for k in data)
            params = dict(data)
            params["id"] = estimate_id
            params["updated_at"] = now
            conn.execute(f"UPDATE estimates SET {set_clause}, updated_at = :updated_at WHERE id = :id;", params)

        after_row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        after = self._row_to_header(after_row)
        self.audit.log(
            action="update",
            entity_type="estimate",
            entity_id=estimate_id,
            change_summary=f"Updated estimate {estimate_id} header",
            actor=actor,
            details=build_audit_details(before=before.to_dict(), after=after.to_dict(), fields=data.keys()),
        )
        return after

    # ------------------------------------------------------------------
    # Claim / unclaim / reassign
    # ------------------------------------------------------------------

    def claim(self, estimate_id: int, actor: AuthContext) -> Optional[EstimateHeader]:
        """§9 item 1: atomic self-claim of an unassigned estimate, mirroring
        `CRMService.claim_lead`'s NEW-534 pattern exactly (same race-safe
        conditional `UPDATE ... WHERE assigned_to_user_id IS NULL`, same
        pre-read/disambiguation-query shape, same not-found-vs-conflict
        split). Hardcodes `assigned_to_user_id = actor.user_id` -- never a
        caller-supplied assignee (that's `reassign()`'s job).

        Returns `None` (-> 404 convention) if the estimate genuinely doesn't
        exist. Raises `ClaimConflictError` (-> 409) if it's already claimed
        by someone else or lost a race against a concurrent claim.
        """
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to write estimates")

        conn = self.db.get_connection()
        # Raw, unguarded pre-read (not self.get(), which applies the
        # PERM_READ_ALL_ESTIMATES-narrowing view gate) -- same reasoning as
        # claim_lead's own pre-read: a narrowed actor may attempt a claim on
        # any row id, and whether it succeeds is governed solely by the
        # atomic UPDATE's WHERE clause below, not by a pre-read permission
        # check.
        row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        if row is None:
            return None

        now = utc_now_iso()
        with conn:
            cursor = conn.execute(
                "UPDATE estimates SET assigned_to_user_id = ?, updated_at = ? "
                "WHERE id = ? AND assigned_to_user_id IS NULL;",
                (actor.user_id, now, estimate_id),
            )

        if cursor.rowcount == 0:
            conflict_row = conn.execute(
                "SELECT id, assigned_to_user_id FROM estimates WHERE id = ?;", (estimate_id,)
            ).fetchone()
            if conflict_row is None:
                return None
            raise ClaimConflictError(f"Estimate {estimate_id} already claimed")

        after_row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        header = self._row_to_header(after_row)
        self.audit.log(
            action="claim",
            entity_type="estimate",
            entity_id=estimate_id,
            change_summary=f"Estimate {estimate_id} claimed by user {actor.user_id}",
            actor=actor,
            details=build_audit_details(
                before={"assigned_to_user_id": None}, after={"assigned_to_user_id": actor.user_id}
            ),
        )
        return header

    def unclaim(self, estimate_id: int, actor: AuthContext) -> Optional[EstimateHeader]:
        """Sets `assigned_to_user_id` back to NULL, race-safely. **No
        `unclaim` precedent exists anywhere in this codebase** (confirmed by
        grep -- `claim_lead`/`claim_opportunity`/`claim_task` have no
        `unclaim_*` counterparts) -- the authorization rule below is this
        method's own derived design, not a copied convention:
        - the CURRENT assignee, holding `PERM_WRITE_ESTIMATES` (the same
          permission every other estimate-mutation method in this class
          gates on), may unclaim their own estimate; or
        - any actor holding `PERM_REASSIGN_ESTIMATES` (auth.py's own
          comment defines that permission as "change assigned_to_user_id" --
          unclaiming is a degenerate case of that, target=NULL instead of a
          specific user).

        Returns `None` if the estimate doesn't exist. Raises `ValueError` if
        it's already unassigned (nothing to unclaim). Raises
        `ClaimConflictError` if the assignment changed concurrently between
        the pre-read and the write (the same race-safety shape as `claim()`,
        applied to the reverse direction).
        """
        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        if row is None:
            return None

        current_assignee = row["assigned_to_user_id"]
        if current_assignee is None:
            raise ValueError(f"Estimate {estimate_id} is not currently assigned; nothing to unclaim")

        is_self_unclaim = actor.has_permission(PERM_WRITE_ESTIMATES) and actor.user_id == current_assignee
        is_broad_unclaim = actor.has_permission(PERM_REASSIGN_ESTIMATES)
        if not (is_self_unclaim or is_broad_unclaim):
            raise PermissionError("Actor lacks permission to unclaim this estimate")

        now = utc_now_iso()
        with conn:
            cursor = conn.execute(
                "UPDATE estimates SET assigned_to_user_id = NULL, updated_at = ? "
                "WHERE id = ? AND assigned_to_user_id = ?;",
                (now, estimate_id, current_assignee),
            )

        if cursor.rowcount == 0:
            raise ClaimConflictError(
                f"Estimate {estimate_id}'s assignment changed concurrently; unclaim lost the race"
            )

        after_row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        header = self._row_to_header(after_row)
        self.audit.log(
            action="unclaim",
            entity_type="estimate",
            entity_id=estimate_id,
            change_summary=f"Estimate {estimate_id} unclaimed by user {actor.user_id} (was assigned to {current_assignee})",
            actor=actor,
            details=build_audit_details(
                before={"assigned_to_user_id": current_assignee}, after={"assigned_to_user_id": None}
            ),
        )
        return header

    def reassign(self, estimate_id: int, new_assignee_user_id: int, actor: AuthContext) -> EstimateHeader:
        """§1.4: admin/manager-tier reassignment, bypassing the claim race
        entirely (a deliberate override, not a claim). Requires
        `PERM_REASSIGN_ESTIMATES` (the `PERM_REASSIGN_PROJECT_STAFF`
        precedent). Validates the target is an active user whose role can
        hold estimates -- rejects a technician/customer/subcontractor/
        ai_agent target with a `ValueError`.
        """
        if not actor.has_permission(PERM_REASSIGN_ESTIMATES):
            raise PermissionError("Actor lacks permission to reassign estimates")

        conn = self.db.get_connection()
        user_row = conn.execute(
            "SELECT id, role, active FROM users WHERE id = ?;", (new_assignee_user_id,)
        ).fetchone()
        if user_row is None or not user_row["active"]:
            raise ValueError(f"User {new_assignee_user_id} is not an active user")
        if user_row["role"] not in _REASSIGNABLE_ROLES:
            raise ValueError(
                f"User {new_assignee_user_id} has role '{user_row['role']}', which cannot hold estimates"
            )

        row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        if row is None:
            raise ValueError(f"Estimate {estimate_id} not found")
        old_assignee = row["assigned_to_user_id"]

        now = utc_now_iso()
        with conn:
            conn.execute(
                "UPDATE estimates SET assigned_to_user_id = ?, updated_at = ? WHERE id = ?;",
                (new_assignee_user_id, now, estimate_id),
            )

        after_row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        header = self._row_to_header(after_row)
        self.audit.log(
            action="assign",
            entity_type="estimate",
            entity_id=estimate_id,
            change_summary=f"Estimate {estimate_id} reassigned to user {new_assignee_user_id}",
            actor=actor,
            details=build_audit_details(
                before={"assigned_to_user_id": old_assignee}, after={"assigned_to_user_id": new_assignee_user_id}
            ),
        )
        return header

    # ------------------------------------------------------------------
    # Line-item CRUD, scoped to the unlocked current version
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_bool_fields(data: Dict[str, Any]) -> None:
        for key in ("visible_to_customer", "taxable"):
            if key in data and isinstance(data[key], bool):
                data[key] = int(data[key])

    def _get_unlocked_current_version(self, conn: sqlite3.Connection, estimate_id: int) -> sqlite3.Row:
        est_row = conn.execute(
            "SELECT id, current_version_id FROM estimates WHERE id = ?;", (estimate_id,)
        ).fetchone()
        if est_row is None:
            raise ValueError(f"Estimate {estimate_id} not found")
        version_id = est_row["current_version_id"]
        if version_id is None:
            raise ValueError(f"Estimate {estimate_id} has no current version")
        version_row = conn.execute("SELECT * FROM estimate_versions WHERE id = ?;", (version_id,)).fetchone()
        if version_row is None or version_row["is_locked"]:
            raise ValueError("cannot modify a locked version; call revise() first")
        return version_row

    def add_line(self, estimate_id: int, line: Dict[str, Any], actor: AuthContext) -> EstimateLineItem:
        """Add a line to the estimate's current (unlocked) version, then
        re-run `codey_estimator.calc.calculate()` over every line in the
        version and persist the server-authoritative totals -- the caller
        never supplies a cost/sell column directly (see the "Written by
        codey_estimator.calc ONLY" columns in the DDL).

        **Material-markup default** (the task's explicit requirement): if
        this line has a material cost component (`_has_material_component`
        -- true for a 'material' line, and equally true for a 'combined'
        line that carries material inputs alongside labor/equipment/sub
        inputs on the same row) AND the caller's input dict does NOT
        include the `material_markup_bp` key AT ALL (an explicit
        key-presence check, `"material_markup_bp" not in data`, never a
        truthy-or check -- an explicit `0` is a legitimate "price at cost"
        value and must never be silently overridden), the line defaults to
        `DEFAULT_MATERIAL_MARKUP_BP` (3000bp = 30.00%). Gating on "has a
        material component" rather than on the literal string
        `line_type == 'material'` is deliberate: a 'combined' line's
        material portion must get the same default treatment, not silently
        ship at 0% markup just because its `line_type` string isn't
        `'material'` (NEW-700 in the task brief).
        """
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to write estimates")

        data = dict(line)
        unknown = set(data) - _ALLOWED_LINE_INPUT_FIELDS
        if unknown:
            raise ValueError(f"add_line: unknown field(s) {sorted(unknown)}")
        if not data.get("line_type"):
            raise ValueError("add_line requires 'line_type'")

        if _has_material_component(data) and "material_markup_bp" not in data:
            data["material_markup_bp"] = DEFAULT_MATERIAL_MARKUP_BP

        if data.get("price_override_cents") is not None and not (data.get("override_reason") or "").strip():
            raise ValueError("price_override_cents requires a non-blank override_reason")

        self._normalize_bool_fields(data)
        merged = {**_LINE_INPUT_DEFAULTS, **data}

        conn = self.db.get_connection()
        now = utc_now_iso()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            version_row = self._get_unlocked_current_version(conn, estimate_id)
            version_id = version_row["id"]

            params = dict(merged)
            params["estimate_version_id"] = version_id
            params["created_at"] = now
            params["updated_at"] = now
            cursor = conn.execute(
                """
                INSERT INTO estimate_line_items (
                    estimate_version_id, sort_order, line_type, section, category,
                    description, customer_description, visible_to_customer,
                    price_book_item_id, retailer_product_id, price_observation_id,
                    retailer_code_snapshot, product_title_snapshot, package_qty,
                    package_unit, unit_cost_cents, quantity, unit, waste_pct_bp,
                    material_markup_bp, labor_type, labor_rate_id, labor_qty,
                    labor_unit, labor_cost_rate_cents, labor_bill_rate_cents,
                    equipment_id, equipment_cost_cents, equipment_markup_bp,
                    subcontractor_id, sub_cost_cents, sub_markup_bp, taxable,
                    discount_cents, price_override_cents, override_reason,
                    internal_note, created_at, updated_at
                ) VALUES (
                    :estimate_version_id, :sort_order, :line_type, :section, :category,
                    :description, :customer_description, :visible_to_customer,
                    :price_book_item_id, :retailer_product_id, :price_observation_id,
                    :retailer_code_snapshot, :product_title_snapshot, :package_qty,
                    :package_unit, :unit_cost_cents, :quantity, :unit, :waste_pct_bp,
                    :material_markup_bp, :labor_type, :labor_rate_id, :labor_qty,
                    :labor_unit, :labor_cost_rate_cents, :labor_bill_rate_cents,
                    :equipment_id, :equipment_cost_cents, :equipment_markup_bp,
                    :subcontractor_id, :sub_cost_cents, :sub_markup_bp, :taxable,
                    :discount_cents, :price_override_cents, :override_reason,
                    :internal_note, :created_at, :updated_at
                );
                """,
                params,
            )
            line_id = cursor.lastrowid
            self._recalculate_version(conn, version_id)

        row = conn.execute("SELECT * FROM estimate_line_items WHERE id = ?;", (line_id,)).fetchone()
        result = self._row_to_line(row)
        self.audit.log(
            action="add",
            entity_type="estimate_line",
            entity_id=line_id,
            change_summary=f"Added line {line_id} to estimate {estimate_id}",
            actor=actor,
            details=build_audit_details(after=result.to_dict()),
        )
        return result

    def update_line(self, line_id: int, updates: Dict[str, Any], actor: AuthContext) -> EstimateLineItem:
        """Update an existing line on its version's unlocked current state.
        `material_markup_bp` is just another allow-listed field here -- no
        special-case default logic on update, only on `add_line()` (per the
        task brief: "update_line(): material_markup_bp should already be
        one of the caller-suppliable fields ... wired through the standard
        update path, no special-case default logic on update").
        """
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to write estimates")

        data = dict(updates)
        unknown = set(data) - _ALLOWED_LINE_INPUT_FIELDS
        if unknown:
            raise ValueError(f"update_line: unknown field(s) {sorted(unknown)}")

        conn = self.db.get_connection()
        now = utc_now_iso()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            line_row = conn.execute("SELECT * FROM estimate_line_items WHERE id = ?;", (line_id,)).fetchone()
            if line_row is None:
                raise ValueError(f"Line {line_id} not found")
            version_id = line_row["estimate_version_id"]
            version_row = conn.execute("SELECT is_locked FROM estimate_versions WHERE id = ?;", (version_id,)).fetchone()
            if version_row is None or version_row["is_locked"]:
                raise ValueError("cannot update a line on a locked version; call revise() first")

            before = self._row_to_line(line_row)
            if not data:
                return before

            if "price_override_cents" in data and data["price_override_cents"] is not None:
                reason = data.get("override_reason", line_row["override_reason"])
                if not (reason or "").strip():
                    raise ValueError("price_override_cents requires a non-blank override_reason")

            self._normalize_bool_fields(data)
            set_clause = ", ".join(f"{k} = :{k}" for k in data)
            params = dict(data)
            params["id"] = line_id
            params["updated_at"] = now
            conn.execute(f"UPDATE estimate_line_items SET {set_clause}, updated_at = :updated_at WHERE id = :id;", params)
            self._recalculate_version(conn, version_id)

        after_row = conn.execute("SELECT * FROM estimate_line_items WHERE id = ?;", (line_id,)).fetchone()
        after = self._row_to_line(after_row)
        self.audit.log(
            action="update",
            entity_type="estimate_line",
            entity_id=line_id,
            change_summary=f"Updated line {line_id}",
            actor=actor,
            details=build_audit_details(before=before.to_dict(), after=after.to_dict(), fields=data.keys()),
        )
        return after

    def remove_line(self, line_id: int, actor: AuthContext) -> None:
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to write estimates")

        conn = self.db.get_connection()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            line_row = conn.execute("SELECT * FROM estimate_line_items WHERE id = ?;", (line_id,)).fetchone()
            if line_row is None:
                raise ValueError(f"Line {line_id} not found")
            version_id = line_row["estimate_version_id"]
            version_row = conn.execute("SELECT is_locked FROM estimate_versions WHERE id = ?;", (version_id,)).fetchone()
            if version_row is None or version_row["is_locked"]:
                raise ValueError("cannot remove a line from a locked version; call revise() first")
            before = self._row_to_line(line_row)
            conn.execute("DELETE FROM estimate_line_items WHERE id = ?;", (line_id,))
            self._recalculate_version(conn, version_id)

        self.audit.log(
            action="remove",
            entity_type="estimate_line",
            entity_id=line_id,
            change_summary=f"Removed line {line_id}",
            actor=actor,
            details=build_audit_details(before=before.to_dict()),
        )

    def reorder_lines(self, estimate_id: int, ordered_line_ids: List[int], actor: AuthContext) -> None:
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to write estimates")

        conn = self.db.get_connection()
        now = utc_now_iso()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            version_row = self._get_unlocked_current_version(conn, estimate_id)
            version_id = version_row["id"]
            existing_ids = {
                r["id"] for r in conn.execute(
                    "SELECT id FROM estimate_line_items WHERE estimate_version_id = ?;", (version_id,)
                )
            }
            if set(ordered_line_ids) != existing_ids:
                raise ValueError("reorder_lines: ordered_line_ids must be exactly the current version's line ids")
            for idx, line_id in enumerate(ordered_line_ids):
                conn.execute(
                    "UPDATE estimate_line_items SET sort_order = ?, updated_at = ? WHERE id = ?;",
                    (idx, now, line_id),
                )
            self._recalculate_version(conn, version_id)

        self.audit.log(
            action="reorder",
            entity_type="estimate_line",
            entity_id=estimate_id,
            change_summary=f"Reordered {len(ordered_line_ids)} line(s) on estimate {estimate_id}",
            actor=actor,
            details=build_audit_details(snapshot={"ordered_line_ids": ordered_line_ids}),
        )

    # ------------------------------------------------------------------
    # Calc-engine integration
    # ------------------------------------------------------------------

    def _row_to_line_input(self, row: sqlite3.Row) -> LineInput:
        material = None
        if _has_material_component(row):
            material = MaterialInput(
                quantity=Decimal(str(row["quantity"])) if row["quantity"] is not None else Decimal(0),
                unit=row["unit"] or "EA",
                unit_cost_cents=row["unit_cost_cents"],
                package_qty=Decimal(str(row["package_qty"])) if row["package_qty"] is not None else Decimal(1),
                package_unit=row["package_unit"],
                waste_pct_bp=row["waste_pct_bp"] or 0,
                material_markup_bp=row["material_markup_bp"] or 0,
                price_book_item_id=row["price_book_item_id"],
                retailer_product_id=row["retailer_product_id"],
                price_observation_id=row["price_observation_id"],
                retailer_code_snapshot=row["retailer_code_snapshot"],
                product_title_snapshot=row["product_title_snapshot"],
            )

        labor = None
        if _has_labor_component(row):
            # No `labor_rate_type` column exists (see module docstring's
            # "schema gaps" note) -- derived from labor_unit. FIXED_FLAT is
            # unrepresentable this round.
            unit_code = (row["labor_unit"] or "").strip().upper()
            rate_type = LaborRateType.HOURLY if unit_code == "HR" else LaborRateType.FIXED_PER_UNIT
            labor = LaborInput(
                rate_type=rate_type,
                labor_qty=Decimal(str(row["labor_qty"])) if row["labor_qty"] is not None else Decimal(0),
                labor_unit=row["labor_unit"] or "HR",
                labor_cost_rate_cents=row["labor_cost_rate_cents"] or 0,
                labor_bill_rate_cents=row["labor_bill_rate_cents"] or 0,
                labor_type=row["labor_type"] or "",
                labor_rate_id=row["labor_rate_id"],
            )

        equipment = None
        if _has_equipment_component(row):
            equipment = EquipmentInput(
                equipment_cost_cents=row["equipment_cost_cents"],
                equipment_markup_bp=row["equipment_markup_bp"] or 0,
                equipment_id=row["equipment_id"],
            )

        subcontractor = None
        if _has_subcontractor_component(row):
            subcontractor = SubcontractorInput(
                sub_cost_cents=row["sub_cost_cents"],
                sub_markup_bp=row["sub_markup_bp"] or 0,
                subcontractor_id=row["subcontractor_id"],
            )

        return LineInput(
            line_key=f"line-{row['id']}",
            line_type=LineType(row["line_type"]),
            description=row["description"] or "",
            customer_description=row["customer_description"] or "",
            visible_to_customer=bool(row["visible_to_customer"]),
            sort_order=row["sort_order"] or 0,
            section=row["section"] or "",
            category=row["category"] or "",
            material=material,
            labor=labor,
            equipment=equipment,
            subcontractor=subcontractor,
            taxable=bool(row["taxable"]),
            line_discount_cents=row["discount_cents"] or 0,
            price_override_cents=row["price_override_cents"],
            override_reason=row["override_reason"],
            internal_note=row["internal_note"] or "",
        )

    def _build_estimate_input(self, conn: sqlite3.Connection, version_id: int) -> EstimateInput:
        version_row = conn.execute("SELECT * FROM estimate_versions WHERE id = ?;", (version_id,)).fetchone()
        if version_row is None:
            raise ValueError(f"Estimate version {version_id} not found")
        line_rows = conn.execute(
            "SELECT * FROM estimate_line_items WHERE estimate_version_id = ? ORDER BY sort_order, id;",
            (version_id,),
        ).fetchall()
        lines = tuple(self._row_to_line_input(row) for row in line_rows)
        return EstimateInput(
            lines=lines,
            tax_rate_bp=version_row["tax_rate_bp"] or 0,
            tax_method=DEFAULT_TAX_METHOD,
            estimate_discount=None,  # see module docstring's "schema gaps" note
            terms=version_row["terms_snapshot"] or "",
            customer_notes=version_row["customer_notes_snapshot"] or "",
        )

    def _compute_engine_result(self, conn: sqlite3.Connection, version_id: int):
        estimate_input = self._build_estimate_input(conn, version_id)
        try:
            return calculate(estimate_input)
        except EstimatorError as exc:
            raise ValueError(str(exc)) from exc

    def _recalculate_version(self, conn: sqlite3.Connection, version_id: int) -> None:
        """Re-run `calculate()` over every line in `version_id` and persist
        the server-authoritative per-line and version-aggregate cost/sell
        columns, in the SAME transaction as the caller's write. Must be
        called while already holding `conn`'s write transaction (the caller
        has already issued `BEGIN IMMEDIATE`) -- this method issues no
        `BEGIN` of its own.
        """
        result = self._compute_engine_result(conn, version_id)
        line_rows = conn.execute(
            "SELECT id FROM estimate_line_items WHERE estimate_version_id = ? ORDER BY sort_order, id;",
            (version_id,),
        ).fetchall()
        for row, line_result in zip(line_rows, result.lines):
            conn.execute(
                """
                UPDATE estimate_line_items SET
                    packages_needed = ?, material_cost_cents = ?, labor_cost_cents = ?,
                    cost_total_cents = ?, sell_total_cents = ?, tax_cents = ?, line_total_cents = ?
                WHERE id = ?;
                """,
                (
                    line_result.packages_needed, line_result.material_cost_cents,
                    line_result.labor_cost_cents, line_result.cost_total_cents,
                    line_result.sell_total_cents, line_result.tax_cents,
                    line_result.line_total_cents, row["id"],
                ),
            )
        conn.execute(
            """
            UPDATE estimate_versions SET
                material_cost_cents = ?, labor_cost_cents = ?, equipment_cost_cents = ?, sub_cost_cents = ?,
                cost_total_cents = ?, subtotal_sell_cents = ?, discount_cents = ?, taxable_base_cents = ?,
                tax_cents = ?, total_cents = ?, gross_profit_cents = ?, gross_margin_bp = ?
            WHERE id = ?;
            """,
            (
                result.material_cost_cents, result.labor_cost_cents, result.equipment_cost_cents,
                result.sub_cost_cents, result.cost_total_cents, result.subtotal_sell_cents,
                result.discount_cents, result.taxable_base_cents, result.tax_cents,
                result.total_cents, result.gross_profit_cents, result.gross_margin_bp, version_id,
            ),
        )

    def preview(self, estimate_id: int, actor: AuthContext):
        """Read-only, server-computed totals for the current version --
        never persists anything. Requires `PERM_WRITE_ESTIMATES` (same as
        viewing your own draft, per §1.9), PLUS the same ownership narrowing
        (`_can_view_estimate()`) AND the same `PERM_READ_ESTIMATE_COSTS`
        cost-field gate (`_gate_preview_result_cost_fields()`) that `get()`
        already applies.

        Code-review fix (B9.3, Critical, live-reproduced): this method
        originally gated on `PERM_WRITE_ESTIMATES` alone -- no
        `_can_view_estimate()` call, no cost-field gate at all -- so ANY
        actor holding `PERM_WRITE_ESTIMATES` could preview ANY estimate's
        full cost/margin breakdown regardless of ownership, unlike `get()`
        which correctly applies both. See
        `.claude/agent-memory/code-reviewer/b9_3_estimate_routes_preview_cost_leak_changes_requested.md`.
        """
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to preview estimates")
        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        if row is None:
            raise ValueError(f"Estimate {estimate_id} not found")
        if not self._can_view_estimate(row, actor):
            raise PermissionError("Actor lacks permission to view this estimate")
        version_id = row["current_version_id"]
        if version_id is None:
            raise ValueError(f"Estimate {estimate_id} has no current version")
        result = self._compute_engine_result(conn, version_id)
        return self._gate_preview_result_cost_fields(result, actor)

    def to_customer_view(self, estimate_id: int) -> Dict[str, Any]:
        """Customer-facing projection of an estimate's current version, via
        the vendored `codey_estimator.dto.to_customer_view()` allow-list
        serializer -- never a second, hand-rolled serializer. No `actor`
        parameter: a share-link viewer isn't an authenticated actor at all;
        callers (the future route layer) are responsible for their own
        authorization (RBAC / token resolution) before calling this.
        """
        conn = self.db.get_connection()
        est_row = conn.execute("SELECT current_version_id FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        if est_row is None:
            raise ValueError(f"Estimate {estimate_id} not found")
        version_id = est_row["current_version_id"]
        if version_id is None:
            raise ValueError(f"Estimate {estimate_id} has no current version")
        result = self._compute_engine_result(conn, version_id)
        try:
            view = _lib_to_customer_view(result)
        except EstimatorError as exc:
            raise ValueError(str(exc)) from exc
        return view.to_dict()

    # ------------------------------------------------------------------
    # Versioning
    # ------------------------------------------------------------------

    def _lock_version_write(self, conn: sqlite3.Connection, version_id: int, reason: str) -> None:
        """Core lock write (`is_locked=1`/`locked_at`/`locked_reason`) --
        no transaction management, no audit log. Assumes the caller already
        holds a `BEGIN IMMEDIATE` transaction on `conn`. Shared by
        `_lock_version()` (which wraps this in its own transaction) and
        `record_decision()` (which calls this inside its own existing
        transaction, since sqlite3 does not allow a nested `BEGIN`)."""
        if reason not in ("sent", "accepted", "superseded"):
            raise ValueError(f"invalid lock reason {reason!r}")
        row = conn.execute("SELECT * FROM estimate_versions WHERE id = ?;", (version_id,)).fetchone()
        if row is None:
            raise ValueError(f"Estimate version {version_id} not found")
        if row["is_locked"]:
            raise ValueError(f"Estimate version {version_id} is already locked")
        now = utc_now_iso()
        conn.execute(
            "UPDATE estimate_versions SET is_locked = 1, locked_at = ?, locked_reason = ? WHERE id = ?;",
            (now, reason, version_id),
        )

    def _lock_version(self, version_id: int, reason: str, actor: AuthContext) -> EstimateVersion:
        """Lock a version (`is_locked=1`/`locked_at`/`locked_reason`).
        Internal -- the public callers are `record_decision()` (locks on
        'accepted', in its own transaction via `_lock_version_write()`
        directly rather than through this method -- see its docstring) and
        `transition()`'s `send` step (same direct-`_lock_version_write()`
        pattern, for the same nested-`BEGIN` reason). Exposed so `revise()`'s
        "only callable on a locked version" rule is real and testable rather
        than dead code.
        """
        conn = self.db.get_connection()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            self._lock_version_write(conn, version_id, reason)
        self.audit.log(
            action="lock",
            entity_type="estimate_version",
            entity_id=version_id,
            change_summary=f"Locked version {version_id} ({reason})",
            actor=actor,
            details=build_audit_details(after={"is_locked": 1, "locked_reason": reason}),
        )
        row = conn.execute("SELECT * FROM estimate_versions WHERE id = ?;", (version_id,)).fetchone()
        return self._row_to_version(row)

    def _create_share_link(
        self, conn: sqlite3.Connection, estimate_id: int, version_id: int, customer_id: int,
        estimate_expires_at: Optional[str], actor: AuthContext,
    ) -> tuple:
        """§4.2: create a real `estimate_share_links` row -- a random,
        unguessable token, hashed before storage. Caller must already hold
        `conn`'s write transaction (issues no `BEGIN` of its own, mirroring
        `_lock_version_write()`/`_next_estimate_number()`'s convention for
        methods meant to run inside an existing transition()-owned
        transaction).

        Returns `(EstimateShareLink, raw_token)` -- the raw token is
        returned ONLY to the immediate caller, never persisted, never
        attached to any dataclass field, and never logged. **This round
        (B9.2) creates the row but nothing yet resolves a raw token back to
        one** (B9.4, the public `/api/v1/public/estimate/{token}` route, is
        out of this round's scope) -- the link this creates is therefore not
        yet reachable by any customer. Logged as a real, disclosed gap
        rather than silently left unremarked: `transition()`'s caller gets a
        real row and a real token, with no delivery mechanism for either
        yet.

        `expires_at` (D10): `now + _SHARE_LINK_DEFAULT_DAYS` unless the
        estimate's own `expires_at` is sooner -- an estimate expiring in 10
        days should not hand out a 30-day-valid link. Both timestamps come
        from `utc_now_iso()`'s consistent ISO-8601 (offset-suffixed) format,
        so a plain string comparison/min() is safe.
        """
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        now = utc_now_iso()
        default_expiry = (datetime.now(timezone.utc) + timedelta(days=_SHARE_LINK_DEFAULT_DAYS)).isoformat()
        link_expires_at = min(default_expiry, estimate_expires_at) if estimate_expires_at else default_expiry

        cursor = conn.execute(
            """
            INSERT INTO estimate_share_links (
                estimate_id, estimate_version_id, customer_id, token_hash,
                created_by_user_id, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (estimate_id, version_id, customer_id, token_hash, actor.user_id if actor else None, now, link_expires_at),
        )
        link = EstimateShareLink(
            id=cursor.lastrowid, estimate_id=estimate_id, estimate_version_id=version_id,
            customer_id=customer_id, token_hash=token_hash,
            created_by_user_id=actor.user_id if actor else None, created_at=now, expires_at=link_expires_at,
        )
        return link, raw_token

    def transition(
        self, estimate_id: int, new_status: str, actor: AuthContext, *, comment: Optional[str] = None,
    ) -> EstimateHeader:
        """§1.5: the public actor-driven workflow state machine.
        `_ACTOR_DRIVEN_TRANSITIONS` is the single source of truth for what's
        legal here -- anything not a key in that table is refused, with a
        distinguishing message for the "not actor-driven" rows
        (`_SYSTEM_DRIVEN_TARGET_STATUSES`: VIEWED/ACCEPTED/DECLINED/
        CHANGES_REQUESTED/EXPIRED/CONVERTED, each reached by its own
        internal path -- the public share-link view route, `record_decision()`,
        the expiry sweep, and `convert()` respectively, none of them this
        method).

        `send` (DRAFT|APPROVED_INTERNAL -> SENT) locks the current version
        (`_lock_version_write()`, reason='sent') and creates a real
        `estimate_share_links` row (`_create_share_link()`) in the SAME
        transaction -- both succeed or neither does.

        **TOCTOU / compare-and-swap**: `row`/`old_status` (and, for `send`,
        `current_version_id`/`customer_id`/`expires_at`) are read INSIDE the
        `BEGIN IMMEDIATE` block below, never before it -- matching
        `record_decision()`'s own convention in this same file. A caller
        that reads stale state before this method is invoked will always
        have its transition validated against the truly-current row once
        this method actually acquires the write lock, so a legitimate
        transition committed by someone else in the meantime is never
        silently clobbered by a stale-state-based action lookup. The final
        `UPDATE` additionally carries an `AND workflow_status = ?` guard
        (matching this round's own `claim()`/`unclaim()` conditional-UPDATE
        pattern) and raises on `rowcount == 0` -- defense in depth on top of
        the in-transaction re-read, not a substitute for it.
        """
        if new_status in _SYSTEM_DRIVEN_TARGET_STATUSES:
            raise ValueError(
                f"'{new_status}' is not reached via transition() -- it is system/customer-driven "
                "(see codey_estimator_service.md §1.5's 'not actor-driven' rows)"
            )

        conn = self.db.get_connection()
        now = utc_now_iso()
        share_link = None
        raw_token = None
        version_id = None
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
            if row is None:
                raise ValueError(f"Estimate {estimate_id} not found")
            old_status = row["workflow_status"]

            action = _ACTOR_DRIVEN_TRANSITIONS.get((old_status, new_status))
            if action is None:
                raise ValueError(f"Illegal transition: {old_status} -> {new_status}")

            # Permission + ownership checks, per §1.5's table. Run against
            # the freshly-read row above, not any pre-transaction state.
            if action == "submit_for_review":
                if not actor.has_permission(PERM_WRITE_ESTIMATES):
                    raise PermissionError("Actor lacks permission to write estimates")
                if row["created_by_user_id"] != actor.user_id and row["assigned_to_user_id"] != actor.user_id:
                    raise PermissionError("Only the estimate's creator or assignee may submit it for review")
            elif action == "send":
                if not actor.has_permission(PERM_SEND_ESTIMATES):
                    raise PermissionError("Actor lacks permission to send estimates")
                if old_status == "DRAFT" and row["internal_review_required"]:
                    raise ValueError(
                        "This estimate requires internal review before it can be sent "
                        "(users.requires_estimate_approval was set for its creator, or it was "
                        "created by an agent) -- submit it for review first"
                    )
            elif action in ("approve", "reject_review"):
                if not actor.has_permission(PERM_APPROVE_ESTIMATES):
                    raise PermissionError("Actor lacks permission to approve estimates")
                if action == "reject_review" and not (comment or "").strip():
                    raise ValueError("reject_review requires a non-blank comment")
            elif action == "cancel":
                is_owner_cancel = actor.has_permission(PERM_WRITE_ESTIMATES) and (
                    row["created_by_user_id"] == actor.user_id or row["assigned_to_user_id"] == actor.user_id
                )
                is_manager_cancel = actor.has_permission(PERM_REASSIGN_ESTIMATES)
                if not (is_owner_cancel or is_manager_cancel):
                    raise PermissionError("Actor lacks permission to cancel this estimate")
                if not (comment or "").strip():
                    raise ValueError("cancel requires a non-blank comment")
            else:  # pragma: no cover -- defensive, every action above is covered
                raise ValueError(f"Unhandled transition action {action!r}")

            set_clauses = ["workflow_status = ?", "updated_at = ?"]
            params: List[Any] = [new_status, now]
            if action == "send":
                version_id = row["current_version_id"]
                if version_id is None:
                    raise ValueError(f"Estimate {estimate_id} has no current version to send")
                self._lock_version_write(conn, version_id, "sent")
                share_link, raw_token = self._create_share_link(
                    conn, estimate_id, version_id, row["customer_id"], row["expires_at"], actor,
                )
                set_clauses.append("sent_at = ?")
                params.append(now)
            set_clause_sql = ", ".join(set_clauses)
            params.extend([estimate_id, old_status])
            cursor = conn.execute(
                f"UPDATE estimates SET {set_clause_sql} WHERE id = ? AND workflow_status = ?;", params
            )
            if cursor.rowcount == 0:
                raise ValueError(
                    f"Estimate {estimate_id}'s status changed concurrently; transition lost the race"
                )

        after_row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        header = self._row_to_header(after_row)
        self.audit.log(
            action="transition",
            entity_type="estimate",
            entity_id=estimate_id,
            change_summary=f"{old_status} -> {new_status}",
            actor=actor,
            details=build_audit_details(
                before={"workflow_status": old_status},
                after={"workflow_status": new_status},
                snapshot={"comment": comment} if comment else None,
            ),
        )
        if action == "send" and share_link is not None:
            self.audit.log(
                action="lock",
                entity_type="estimate_version",
                entity_id=version_id,
                change_summary=f"Locked version {version_id} (sent)",
                actor=actor,
                details=build_audit_details(after={"is_locked": 1, "locked_reason": "sent"}),
            )
            self.audit.log(
                action="create",
                entity_type="estimate_share_link",
                entity_id=share_link.id,
                change_summary=f"Created share link for estimate {estimate_id} version {version_id}",
                actor=actor,
                # The raw token is deliberately NOT in this audit payload --
                # only the row id and delivery metadata, matching §4.2's
                # "enough to know a link was sent, never enough to
                # reconstruct it" rule.
                details=build_audit_details(after={"share_link_id": share_link.id, "estimate_version_id": version_id}),
            )
        return header

    def revise(self, estimate_id: int, actor: AuthContext) -> EstimateVersion:
        """Clone the locked current version -- header snapshot fields AND
        every line verbatim (including all cost/sell/snapshot columns;
        prices do NOT silently refresh, per §1.6) -- into a new,
        `version_number + 1`, unlocked version, and set it as current.
        `workflow_status` resets to `DRAFT`.

        Only callable when the current version `is_locked = 1` (else raise
        -- editing an unlocked draft happens directly through the line-item
        methods, no explicit "revise" step needed).

        The old version's `locked_reason` is deliberately NEVER rewritten to
        `'superseded'` here: `trg_estimate_versions_locked_immutable` is
        `BEFORE UPDATE ... WHEN OLD.is_locked = 1` with no column exception,
        so any `UPDATE` against a locked version row -- including a
        `locked_reason`-only one -- aborts. Per
        `codey_estimator_service.md` §1.6's recommended option (b),
        "superseded" is a DERIVED fact (a version with
        `version_number < the estimate's current version's number` and
        `is_locked = 1`), never stored -- callers needing that fact compute
        it by comparing `version_number` against the estimate's
        `current_version_id`'s version_number, not by reading a stored flag.
        """
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to write estimates")

        conn = self.db.get_connection()
        now = utc_now_iso()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            est_row = conn.execute("SELECT * FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
            if est_row is None:
                raise ValueError(f"Estimate {estimate_id} not found")
            old_version_id = est_row["current_version_id"]
            if old_version_id is None:
                raise ValueError(f"Estimate {estimate_id} has no current version")
            old_version = conn.execute("SELECT * FROM estimate_versions WHERE id = ?;", (old_version_id,)).fetchone()
            if old_version is None or not old_version["is_locked"]:
                raise ValueError(
                    "revise() requires the current version to be locked; "
                    "an unlocked draft is edited directly, not revised"
                )

            max_row = conn.execute(
                "SELECT MAX(version_number) AS n FROM estimate_versions WHERE estimate_id = ?;", (estimate_id,)
            ).fetchone()
            new_version_number = (max_row["n"] or 0) + 1

            version_cursor = conn.execute(
                """
                INSERT INTO estimate_versions (
                    estimate_id, version_number, is_locked, locked_at, locked_reason,
                    material_cost_cents, labor_cost_cents, equipment_cost_cents, sub_cost_cents,
                    cost_total_cents, subtotal_sell_cents, discount_cents, taxable_base_cents,
                    tax_cents, total_cents, gross_profit_cents, gross_margin_bp,
                    calc_engine_version, tax_rate_bp, terms_snapshot, customer_notes_snapshot,
                    change_summary, created_by_user_id, created_at
                ) VALUES (
                    ?, ?, 0, NULL, NULL,
                    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                    ?, ?, ?, ?,
                    NULL, ?, ?
                );
                """,
                (
                    estimate_id, new_version_number,
                    CALC_ENGINE_VERSION, old_version["tax_rate_bp"],
                    # Header edits made via update_header() while the OLD
                    # version was current show up here -- copied from the
                    # estimate's CURRENT terms/customer_notes, not re-copied
                    # from the old version's own snapshot (§1.6).
                    est_row["terms"], est_row["customer_notes"],
                    actor.user_id, now,
                ),
            )
            new_version_id = version_cursor.lastrowid

            old_lines = conn.execute(
                "SELECT * FROM estimate_line_items WHERE estimate_version_id = ? ORDER BY sort_order, id;",
                (old_version_id,),
            ).fetchall()
            for old_line in old_lines:
                values = {c: old_line[c] for c in _LINE_ITEM_CLONE_COLUMNS}
                values["estimate_version_id"] = new_version_id
                values["created_at"] = now
                values["updated_at"] = now
                cols = list(values.keys())
                placeholders = ", ".join(f":{c}" for c in cols)
                conn.execute(
                    f"INSERT INTO estimate_line_items ({', '.join(cols)}) VALUES ({placeholders});",
                    values,
                )

            conn.execute(
                "UPDATE estimates SET current_version_id = ?, workflow_status = 'DRAFT', updated_at = ? WHERE id = ?;",
                (new_version_id, now, estimate_id),
            )

        new_version_row = conn.execute("SELECT * FROM estimate_versions WHERE id = ?;", (new_version_id,)).fetchone()
        result = self._row_to_version(new_version_row)
        self.audit.log(
            action="revise",
            entity_type="estimate",
            entity_id=estimate_id,
            change_summary=f"Revised estimate {estimate_id} to version {new_version_number}",
            actor=actor,
            details=build_audit_details(
                snapshot={
                    "old_version_id": old_version_id,
                    "new_version_id": new_version_id,
                    "new_version_number": new_version_number,
                }
            ),
        )
        return result

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    def record_decision(
        self,
        *,
        estimate_version_id: int,
        decision: str,
        ip: str,
        user_agent: str,
        signer_name: Optional[str] = None,
        signature_data: Optional[str] = None,
        comment: Optional[str] = None,
        share_link_id: Optional[int] = None,
        customer_user_id: Optional[int] = None,
    ) -> EstimateDecision:
        """Record an accept/decline/changes-requested decision against an
        estimate's CURRENT version. No `actor: AuthContext` parameter -- a
        share-link viewer isn't an authenticated actor (§1.7); the audit log
        entry is written with `actor=None` (logged as "system"/"agent").

        D10: `signer_name` and a fixed, versioned `consent_text_snapshot`
        (`CONSENT_TEXT_V1`) are REQUIRED on an 'accepted' row.

        An 'accepted' decision locks the version in the SAME transaction as
        the acceptance write, via `_lock_version_write()` (the internal
        core of `_lock_version()`, called directly rather than through
        `_lock_version()` itself because sqlite3 does not allow a nested
        `BEGIN` -- this method already holds its own `BEGIN IMMEDIATE`).
        This closes the gap where `add_line()`/`update_line()`/
        `remove_line()` only checked `is_locked`, not `workflow_status`,
        so an accepted estimate could silently be re-priced after
        acceptance. If the version is already locked (e.g. it was locked
        `'sent'` before the customer decided), locking is a no-op --
        `is_locked=1` is the invariant that matters, not which reason
        string got there first; `locked_reason` is otherwise immutable
        once set (the DB trigger blocks any UPDATE to an already-locked
        row). 'declined'/'changes_requested' decisions do NOT lock --
        only acceptance is final.

        **Accept -> Contract invariant** (§1.7, closes NEW-705): on
        'accepted', a `Contract` row is created in the SAME transaction as
        the acceptance write and the version lock -- one `BEGIN IMMEDIATE`,
        one commit, so an `ACCEPTED` estimate can never exist without a
        linked Contract (and a failure anywhere in this transaction rolls
        back the whole thing, including the decision row and the status
        change -- there is no path to a half-accepted state). The insert is
        done directly here, not via `CRMService.create_contract()`: that
        method requires an `AuthContext` with `PERM_WRITE_CONTRACTS` (this
        method has no actor -- a share-link viewer isn't one) and manages
        its own `with conn:` block (sqlite3 does not allow a nested
        `BEGIN`), so it cannot be called from inside this method's own
        transaction. The INSERT below mirrors `create_contract()`'s column
        list/shape exactly, adapted, not reinvented.

        `contract_number` is derived deterministically from the estimate's
        own (already race-safe, server-generated) `estimate_number` --
        `f"CON-{estimate_number}"` -- rather than adding a second
        `contract_number_sequences` table this round (that generalization
        is explicitly deferred, logged to NEW_ISSUES.md, per
        `codey_estimator_service.md` §2's own note that `contract_number`
        has "the same client-supplied gap" as `estimate_number` had).

        **Double-accept disclosed limitation**: if `estimates.contract_id`
        is already set (a prior acceptance already created one -- e.g. the
        estimate was re-accepted after `revise()` reopened it), this
        method does NOT create a second Contract or raise. **The real,
        narrower trigger** (corrected -- `NEW-705`'s original text named a
        `changes_requested` round as the path here; it isn't required):
        `revise()` (pre-existing, unchanged by this round) is reachable
        directly from `ACCEPTED` with no `changes_requested` decision at
        all -- it only checks the current version's `is_locked = 1`, which
        an `ACCEPTED` estimate's version also satisfies. So the actual
        trigger is `ACCEPTED` -> `revise()` -> re-send -> re-accept (see
        `NEW-705`/`NEW-714` in NEW_ISSUES.md -- the latter logs a
        suggestion, not built this round, that `revise()` should reject
        `workflow_status IN ('ACCEPTED', 'CONVERTED')`). Whichever path
        gets here, this method re-links the existing Contract rather than
        creating a second one, since `CON-{estimate_number}` would
        otherwise collide on `contracts.contract_number`'s UNIQUE
        constraint and roll back a genuine customer acceptance for a
        reason unrelated to the acceptance itself. The resulting gap (the
        linked Contract's amount/content reflects the FIRST accepted
        version, not necessarily the current one) is a real, disclosed
        limitation -- logged to NEW_ISSUES.md, not silently decided.
        """
        if decision not in ("accepted", "declined", "changes_requested"):
            raise ValueError(f"invalid decision {decision!r}")
        if (share_link_id is None) == (customer_user_id is None):
            raise ValueError("record_decision requires exactly one of share_link_id or customer_user_id")

        consent_text_snapshot = None
        if decision == "accepted":
            if not (signer_name or "").strip():
                raise ValueError("decision 'accepted' requires a non-blank signer_name")
            consent_text_snapshot = CONSENT_TEXT_V1

        conn = self.db.get_connection()
        now = utc_now_iso()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            version_row = conn.execute("SELECT * FROM estimate_versions WHERE id = ?;", (estimate_version_id,)).fetchone()
            if version_row is None:
                raise ValueError(f"Estimate version {estimate_version_id} not found")
            estimate_row = conn.execute(
                "SELECT * FROM estimates WHERE current_version_id = ?;", (estimate_version_id,)
            ).fetchone()
            if estimate_row is None:
                raise ValueError(
                    f"Estimate version {estimate_version_id} is not the current version of any estimate; "
                    "cannot record a decision against a superseded version"
                )

            cursor = conn.execute(
                """
                INSERT INTO estimate_decisions (
                    estimate_version_id, share_link_id, customer_user_id, decision,
                    signer_name, signature_data, consent_text_snapshot, comment,
                    ip, user_agent, decided_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    estimate_version_id, share_link_id, customer_user_id, decision,
                    signer_name, signature_data, consent_text_snapshot, comment,
                    ip, user_agent, now,
                ),
            )
            decision_id = cursor.lastrowid

            new_status = {
                "accepted": "ACCEPTED", "declined": "DECLINED", "changes_requested": "CHANGES_REQUESTED",
            }[decision]
            locked_on_accept = False
            new_contract_id = None
            if decision == "accepted":
                conn.execute(
                    "UPDATE estimates SET workflow_status = ?, accepted_version_id = ?, accepted_at = ?, updated_at = ? WHERE id = ?;",
                    (new_status, estimate_version_id, now, now, estimate_row["id"]),
                )
                locked_on_accept = not version_row["is_locked"]
                if locked_on_accept:
                    self._lock_version_write(conn, estimate_version_id, "accepted")

                if estimate_row["contract_id"] is None:
                    contract_number = f"CON-{estimate_row['estimate_number']}"
                    total_cents = version_row["total_cents"] or 0
                    content_lines = [
                        f"Contract generated from accepted estimate {estimate_row['estimate_number']} "
                        f"(version {version_row['version_number']}).",
                        f"Total: ${total_cents / 100:.2f}.",
                    ]
                    if version_row["terms_snapshot"]:
                        content_lines.append(f"Terms: {version_row['terms_snapshot']}")
                    content = "\n".join(content_lines)
                    contract_title = estimate_row["title"] or f"Contract for {estimate_row['estimate_number']}"
                    # NEW-711 (B9.3 route round): this INSERT can collide on
                    # contracts.contract_number's UNIQUE constraint --
                    # routes.py:1637 already lets any PERM_WRITE_CONTRACTS
                    # holder set an arbitrary, client-supplied
                    # contract_number via Contract(**json_body), and
                    # estimate_number ("EST-{year}-{seq:04d}") is trivially
                    # guessable, so a pre-created "CON-{estimate_number}" row
                    # is a real, reachable collision the moment this method
                    # is wired to a route (B9.3). Without this catch, that
                    # collision raises a bare sqlite3.IntegrityError, which
                    # is neither ValueError nor PermissionError, so routes.py's
                    # global handler would turn a LEGITIMATE customer
                    # acceptance into a raw 500 and roll back the whole
                    # transaction (decision row, status change, and version
                    # lock all lost). Narrowly scoped to just this one
                    # INSERT (not the whole `with conn:` block) so a genuine
                    # CHECK/FK failure elsewhere in this transaction still
                    # propagates as itself, not as this message. The
                    # `with conn:` context manager still rolls back
                    # everything on any exception raised out of it --
                    # re-raising as ValueError here only changes the HTTP
                    # status (500 -> 400 via the same global handler), not
                    # the atomicity. The real fix (a race-safe
                    # contract_number_sequences generator, matching
                    # _next_estimate_number()'s shape) remains deferred --
                    # this is a minimal, disclosed mitigation, not that fix.
                    try:
                        contract_cursor = conn.execute(
                            """
                            INSERT INTO contracts (
                                contract_number, customer_id, project_id, estimate_id,
                                title, template_name, content, status, version,
                                assigned_user_id, created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, NULL, ?, 'draft', 1, ?, ?, ?);
                            """,
                            (
                                contract_number, estimate_row["customer_id"], estimate_row["project_id"],
                                estimate_row["id"], contract_title, content,
                                estimate_row["assigned_to_user_id"], now, now,
                            ),
                        )
                    except sqlite3.IntegrityError as exc:
                        raise ValueError(
                            f"Cannot create contract {contract_number!r} for accepted estimate "
                            f"{estimate_row['estimate_number']}: a contract with that number already "
                            "exists (contract_number collision -- NEW-711)"
                        ) from exc
                    new_contract_id = contract_cursor.lastrowid
                    conn.execute(
                        "UPDATE estimates SET contract_id = ? WHERE id = ?;", (new_contract_id, estimate_row["id"])
                    )
            else:
                conn.execute(
                    "UPDATE estimates SET workflow_status = ?, updated_at = ? WHERE id = ?;",
                    (new_status, now, estimate_row["id"]),
                )

        row = conn.execute("SELECT * FROM estimate_decisions WHERE id = ?;", (decision_id,)).fetchone()
        result = self._row_to_decision(row)
        self.audit.log(
            action="decision",
            entity_type="estimate",
            entity_id=estimate_row["id"],
            change_summary=f"Decision recorded: {decision}",
            actor=None,
            details=build_audit_details(after=result.to_dict()),
        )
        if locked_on_accept:
            self.audit.log(
                action="lock",
                entity_type="estimate_version",
                entity_id=estimate_version_id,
                change_summary=f"Locked version {estimate_version_id} (accepted)",
                actor=None,
                details=build_audit_details(after={"is_locked": 1, "locked_reason": "accepted"}),
            )
        if new_contract_id is not None:
            self.audit.log(
                action="create",
                entity_type="contract",
                entity_id=new_contract_id,
                change_summary=f"Contract auto-created from accepted estimate {estimate_row['id']}",
                actor=None,
                details=build_audit_details(snapshot={"estimate_id": estimate_row["id"], "contract_id": new_contract_id}),
            )
        return result

    # ------------------------------------------------------------------
    # Row -> dataclass mirrors
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_header(row: sqlite3.Row) -> EstimateHeader:
        return EstimateHeader(
            id=row["id"], estimate_number=row["estimate_number"], customer_id=row["customer_id"],
            project_id=row["project_id"], created_by_user_id=row["created_by_user_id"],
            created_by_name=row["created_by_name"], assigned_to_user_id=row["assigned_to_user_id"],
            opportunity_id=row["opportunity_id"], lead_id=row["lead_id"], property_id=row["property_id"],
            title=row["title"], current_version_id=row["current_version_id"],
            accepted_version_id=row["accepted_version_id"], accepted_at=row["accepted_at"],
            converted_project_id=row["converted_project_id"], contract_id=row["contract_id"],
            source=row["source"], workflow_status=row["workflow_status"],
            internal_review_required=row["internal_review_required"], expires_at=row["expires_at"],
            customer_notes=row["customer_notes"], terms=row["terms"], sent_at=row["sent_at"],
            last_viewed_at=row["last_viewed_at"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_version(row: sqlite3.Row) -> EstimateVersion:
        return EstimateVersion(
            id=row["id"], estimate_id=row["estimate_id"], version_number=row["version_number"],
            is_locked=row["is_locked"], locked_at=row["locked_at"], locked_reason=row["locked_reason"],
            material_cost_cents=row["material_cost_cents"], labor_cost_cents=row["labor_cost_cents"],
            equipment_cost_cents=row["equipment_cost_cents"], sub_cost_cents=row["sub_cost_cents"],
            cost_total_cents=row["cost_total_cents"], subtotal_sell_cents=row["subtotal_sell_cents"],
            discount_cents=row["discount_cents"], taxable_base_cents=row["taxable_base_cents"],
            tax_cents=row["tax_cents"], total_cents=row["total_cents"],
            gross_profit_cents=row["gross_profit_cents"], gross_margin_bp=row["gross_margin_bp"],
            calc_engine_version=row["calc_engine_version"], tax_rate_bp=row["tax_rate_bp"],
            terms_snapshot=row["terms_snapshot"], customer_notes_snapshot=row["customer_notes_snapshot"],
            change_summary=row["change_summary"], created_by_user_id=row["created_by_user_id"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_line(row: sqlite3.Row) -> EstimateLineItem:
        return EstimateLineItem(
            id=row["id"], estimate_version_id=row["estimate_version_id"], sort_order=row["sort_order"],
            line_type=row["line_type"], section=row["section"], category=row["category"],
            description=row["description"], customer_description=row["customer_description"],
            visible_to_customer=row["visible_to_customer"], price_book_item_id=row["price_book_item_id"],
            retailer_product_id=row["retailer_product_id"], price_observation_id=row["price_observation_id"],
            retailer_code_snapshot=row["retailer_code_snapshot"], product_title_snapshot=row["product_title_snapshot"],
            package_qty=row["package_qty"], package_unit=row["package_unit"], unit_cost_cents=row["unit_cost_cents"],
            quantity=row["quantity"], unit=row["unit"], waste_pct_bp=row["waste_pct_bp"],
            material_markup_bp=row["material_markup_bp"], labor_type=row["labor_type"],
            labor_rate_id=row["labor_rate_id"], labor_qty=row["labor_qty"], labor_unit=row["labor_unit"],
            labor_cost_rate_cents=row["labor_cost_rate_cents"], labor_bill_rate_cents=row["labor_bill_rate_cents"],
            equipment_id=row["equipment_id"], equipment_cost_cents=row["equipment_cost_cents"],
            equipment_markup_bp=row["equipment_markup_bp"], subcontractor_id=row["subcontractor_id"],
            sub_cost_cents=row["sub_cost_cents"], sub_markup_bp=row["sub_markup_bp"], taxable=row["taxable"],
            discount_cents=row["discount_cents"], price_override_cents=row["price_override_cents"],
            override_reason=row["override_reason"], packages_needed=row["packages_needed"],
            material_cost_cents=row["material_cost_cents"], labor_cost_cents=row["labor_cost_cents"],
            cost_total_cents=row["cost_total_cents"], sell_total_cents=row["sell_total_cents"],
            tax_cents=row["tax_cents"], line_total_cents=row["line_total_cents"],
            internal_note=row["internal_note"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_decision(row: sqlite3.Row) -> EstimateDecision:
        return EstimateDecision(
            id=row["id"], estimate_version_id=row["estimate_version_id"], share_link_id=row["share_link_id"],
            customer_user_id=row["customer_user_id"], decision=row["decision"], signer_name=row["signer_name"],
            signature_data=row["signature_data"], consent_text_snapshot=row["consent_text_snapshot"],
            comment=row["comment"], ip=row["ip"], user_agent=row["user_agent"], decided_at=row["decided_at"],
        )
