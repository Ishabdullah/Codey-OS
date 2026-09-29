"""
Codey-Estimator Integration, Phase B9.2 -- EstimateService.

Domain engine for the estimating workflow: header CRUD, line-item CRUD with
server-authoritative pricing via the vendored `codey_estimator.calc` engine,
versioning (`revise()`), decision recording (accept/decline/changes-
requested), preview, and the customer-facing allow-list projection
(`to_customer_view()`). Sits alongside `CRMService`/`FinanceService`/
`OperationsService` as its own file, per `codey_estimator_service.md` §1's
decision (the estimate domain -- 5 tables, a locking workflow, a numbering
generator, and a calc-engine integration point -- is a bigger unit of
concern than any existing `crm_service.py` `# SECTION`).

**Scope actually built this round** (per the B9.2 task brief, narrower than
`codey_estimator_service.md`'s full §1.x method table -- see that document
for the full future design):
    create, get, list, update_header
    add_line, update_line, remove_line, reorder_lines
    revise (versioning)
    record_decision (accepted/declined/changes_requested)
    preview, to_customer_view
    lock-immutability enforcement (checked in-transaction before every
    line/header write; the DB triggers are the backstop)

**Deliberately NOT built this round** (each is a real, identified gap --
logged to NEW_ISSUES.md rather than silently built or silently dropped):

  - `transition()` (the public actor-driven workflow-state-machine method),
    `reassign()`, `claim()`/`unclaim()`, `convert()`. The discriminating
    reason: `codey_estimator_service.md` §1.5's `DRAFT -> SENT` and
    `APPROVED_INTERNAL -> SENT` transitions both create an
    `estimate_share_links` row as a side effect, and share-link creation is
    explicitly on this round's do-not-build list (it needs its own
    capability-token auth-boundary review, B9.4). A `transition()` that
    structurally cannot reach SENT is worse than no `transition()` --
    deferred whole, not half-built.
  - The expiry sweep (B9.2b), API routes (B9.3), the public share-link
    routes (B9.4), the staff/admin UI (B9.5/B9.6), the quote-portal D8
    migration (B9.7), and `convert()`'s Project-creation half (B9.8) -- all
    per the task brief's explicit do-not-build list.
  - Real ownership-narrowing's "unassigned/unclaimed" visible bucket
    (`codey_estimator_service.md` §9 item 1) -- `list()`/`get()` below
    implement the baseline "mine or assigned to me" / "everything"
    narrowing only, not the claim-workflow's unclaimed-is-visible carve-out
    (that needs `claim()`/`unclaim()`, deferred above).
  - `_lock_version()` is implemented as an internal-use method (no public
    route calls it this round) purely so `revise()`'s own "only callable on
    a locked version" rule is real and testable, rather than dead code.
    `record_decision(decision="accepted")` now locks the version too (via
    `_lock_version_write()`, `_lock_version()`'s shared core, called
    directly inside `record_decision()`'s own transaction rather than
    through `_lock_version()` itself, since sqlite3 does not allow a nested
    `BEGIN`) -- this closes the gap where an accepted estimate could still
    be silently re-priced by `add_line()`/`update_line()`/`remove_line()`.
    The deferred `transition()` send step is still the only caller that
    would use `_lock_version()` directly (for the `'sent'` reason).

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

import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional

from codey_estimator.calc.engine import CALC_ENGINE_VERSION, calculate
from codey_estimator.dto import (
    EquipmentInput,
    EstimateInput,
    LaborInput,
    LaborRateType,
    LineInput,
    LineType,
    MaterialInput,
    SubcontractorInput,
    TaxMethod,
)
from codey_estimator.dto import to_customer_view as _lib_to_customer_view
from codey_estimator.errors import EstimatorError

from ..auth import (
    AuthContext,
    PERM_READ_ALL_ESTIMATES,
    PERM_READ_ESTIMATE_COSTS,
    PERM_READ_ESTIMATES,
    PERM_READ_OWN_ESTIMATES,
    PERM_WRITE_ESTIMATES,
    ROLE_CUSTOMER,
)
from ..database import DatabaseManager
from ..models import (
    EstimateDecision,
    EstimateHeader,
    EstimateLineItem,
    EstimateVersion,
    utc_now_iso,
)
from .audit_service import AuditService, build_audit_details

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
        """
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to write estimates")
        if not (0 <= tax_rate_bp <= 10_000):
            raise ValueError("tax_rate_bp must be between 0 and 10000")

        conn = self.db.get_connection()
        now = utc_now_iso()
        year = int(now[:4])
        creator_row = conn.execute(
            "SELECT full_name FROM users WHERE id = ?;", (actor.user_id,)
        ).fetchone()
        created_by_name = creator_row["full_name"] if creator_row is not None else None
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
                    customer_notes, terms, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'engine', 'DRAFT', ?, ?, ?, ?, ?);
                """,
                (
                    estimate_number, customer_id, project_id, actor.user_id,
                    created_by_name, assignee, opportunity_id, lead_id,
                    property_id, title, expires_at, customer_notes, terms, now, now,
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
            return row["created_by_user_id"] == actor.user_id or row["assigned_to_user_id"] == actor.user_id
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

    def get(self, estimate_id: int, actor: AuthContext, *, include_lines: bool = False) -> Optional[EstimateHeader]:
        """D9 cost gating + §1.2 ownership narrowing (baseline "mine or
        assigned to me" -- the unclaimed-bucket carve-out is deferred, see
        module docstring)."""
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
            clauses.append("(created_by_user_id = ? OR assigned_to_user_id = ?)")
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
        viewing your own draft, per §1.9)."""
        if not actor.has_permission(PERM_WRITE_ESTIMATES):
            raise PermissionError("Actor lacks permission to preview estimates")
        conn = self.db.get_connection()
        est_row = conn.execute("SELECT current_version_id FROM estimates WHERE id = ?;", (estimate_id,)).fetchone()
        if est_row is None:
            raise ValueError(f"Estimate {estimate_id} not found")
        version_id = est_row["current_version_id"]
        if version_id is None:
            raise ValueError(f"Estimate {estimate_id} has no current version")
        return self._compute_engine_result(conn, version_id)

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
        Internal -- the public callers this round are `record_decision()`
        (locks on 'accepted', in its own transaction via
        `_lock_version_write()` directly rather than through this method --
        see its docstring) and the deferred `transition()` send step.
        Exposed so `revise()`'s "only callable on a locked version" rule is
        real and testable rather than dead code.
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

        NOTE on the accepted-estimate-must-have-a-contract rule
        (`codey_estimator_service.md` §1.7/§1.9): this round defers
        `convert()`/`_create_contract_from_estimate()` entirely (see module
        docstring) -- an 'accepted' decision here sets `workflow_status`,
        `accepted_version_id`, and `accepted_at` on the estimate, but does
        NOT create a Contract. This gap is logged to NEW_ISSUES.md rather
        than silently built (out of this round's scope) or silently left
        unremarked.
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
            if decision == "accepted":
                conn.execute(
                    "UPDATE estimates SET workflow_status = ?, accepted_version_id = ?, accepted_at = ?, updated_at = ? WHERE id = ?;",
                    (new_status, estimate_version_id, now, now, estimate_row["id"]),
                )
                locked_on_accept = not version_row["is_locked"]
                if locked_on_accept:
                    self._lock_version_write(conn, estimate_version_id, "accepted")
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
            source=row["source"], workflow_status=row["workflow_status"], expires_at=row["expires_at"],
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
