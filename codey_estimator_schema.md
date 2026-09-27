# Codey-Estimator Integration — Schema & Migration (Phase B9.1)

**Status: scoped 2026-09-27, code-complete, code-reviewer approved, NOT
live-verified.** Live verification requires the actual device
(`~/.codeyOS/restoricon.db` on the S24 Ultra) — see the "Live verification"
section at the end for exactly what still needs to run there before this is
"done" per rule 7.

This is a spoke, not a second hub — `CODEY_MASTER_PLAN.md` remains the single
authoritative plan (§0). Registered there as **Phase B9** (§6.13, Appendix A)
with a one-line pointer back to this file. Reconciles the standalone
[`Codey-Estimator`](https://github.com/Ishabdullah/Codey-Estimator) library's
own `docs/ARCHITECTURE_PLAN.md` §14–24 design against the real current schema
and RBAC in this repo — where they conflict, the real `database.py`/
`models.py`/`auth.py` win, not the companion plan.

**Scope of this round: schema + migration + RBAC constants only.** The
service layer, API routes, and UI are B9.2+, not yet scoped.

## 0. Why this is low-risk despite touching a live production table

`Codey-Estimator/docs/DECISIONS.md` records that a read-only query against
the live `~/.codeyOS/restoricon.db` (run by Ish, 2026-09-27) found the
`estimates` table **completely empty** — zero rows, so zero line items, zero
linked documents/contracts, zero audit rows to migrate or preserve. FTS5 is
available (SQLite 3.53.4). This means the `estimates` table rebuild below
carries none of the data-loss risk a populated-table rebuild would, and no
backfill logic (creator-from-audit-log, legacy-status mapping,
`line_items_json` parsing) is needed — stated explicitly rather than silently
dropped from the companion plan's §21.

## 1. `estimates` table: full rebuild, not left additive

**Decision: rebuild it now**, reusing `_migrate_users_role_constraint`'s exact
9-step procedure (`database.py:1209-1401`) — never rename `users`/`estimates`
itself; build the new shape under a disposable temp name, copy, drop the
original, rename the temp table in. The empty-table finding makes this
low-risk, and it fixes a real bug (`customer_id ON DELETE CASCADE` on a
financial-document header table — deleting a customer would silently destroy
their estimate history) while it costs nothing to fix now. Deferring it would
just carry the same rebuild risk forward to a day when the table has real
rows.

Because this is a real rebuild (`CREATE TABLE`, not `ALTER TABLE ADD COLUMN`),
new columns get **real `FOREIGN KEY` constraints** where the target table
already exists — better than the bare-int-no-FK pattern, which is only forced
on `ALTER TABLE ADD COLUMN` migrations. One exception: `property_id` stays
bare-int-no-FK, because its target table (`properties`, designed in
`sales_rep_portal.md` B8.1 but **not yet built** — only its permission half
shipped) doesn't exist yet.

### `_SCHEMA_SQL`'s `estimates` block (replaces the current block at
`database.py:204-227`; fresh-DB-safe via `IF NOT EXISTS`, so a new install
gets this shape natively):

```sql
-- Estimates / Quotes. REBUILT (Codey-Estimator Phase B9.1) to widen
-- customer_id's delete action from CASCADE to RESTRICT (an estimate is a
-- financial document; deleting a customer must never silently delete their
-- estimate history) and to add the header columns Codey-Estimator's own
-- workflow needs. Legacy `status`/`version` columns are kept, UNTOUCHED,
-- for backward-compat reads only -- new code drives off `workflow_status`
-- and `estimate_versions.version_number` instead. This block must stay
-- byte-for-byte identical to _ESTIMATES_TABLE_V2_SQL below (its rebuilt-
-- table copy, used by _migrate_estimates_table_v2() to rebuild a legacy
-- DB's `estimates` table -- the 'workflow_status' column-presence check
-- there is also this file's idempotency gate) -- keep the two in sync any
-- time this table changes.
CREATE TABLE IF NOT EXISTS estimates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estimate_number TEXT UNIQUE NOT NULL,
    customer_id INTEGER NOT NULL,
    project_id INTEGER,
    -- Codey-Estimator Phase B9.1 additions:
    created_by_user_id INTEGER,   -- immutable once set; service-layer only, never from request body
    created_by_name TEXT,         -- snapshot of users.full_name at creation; survives role changes/departures
    assigned_to_user_id INTEGER,  -- defaults to creator; reassignment needs PERM_REASSIGN_ESTIMATES
    opportunity_id INTEGER,
    lead_id INTEGER,
    -- property_id: bare INTEGER, NO FOREIGN KEY. Not the ALTER-TABLE-can't-
    -- attach-an-FK reason used elsewhere in this file -- this IS a fresh
    -- CREATE TABLE, so a real FK would normally be used. The real reason:
    -- B8.1's `properties` table (sales_rep_portal.md) is DESIGNED but NOT
    -- YET BUILT (only its permission half shipped) -- there is no target
    -- table to reference yet. Attach a real FK in the migration that
    -- creates `properties`.
    property_id INTEGER,
    title TEXT,
    current_version_id INTEGER,   -- FK below; NULL until the first version is created
    accepted_version_id INTEGER,
    accepted_at TEXT,
    converted_project_id INTEGER,
    contract_id INTEGER,
    source TEXT NOT NULL DEFAULT 'engine' CHECK(source IN ('engine', 'legacy', 'api')),
    workflow_status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(workflow_status IN (
        'DRAFT', 'INTERNAL_REVIEW', 'APPROVED_INTERNAL', 'SENT', 'VIEWED',
        'ACCEPTED', 'DECLINED', 'CHANGES_REQUESTED', 'EXPIRED', 'CANCELLED', 'CONVERTED'
    )),
    expires_at TEXT,
    customer_notes TEXT,
    terms TEXT,
    sent_at TEXT,
    last_viewed_at TEXT,
    -- Legacy columns, UNCHANGED from the original table:
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
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE RESTRICT,  -- widened from CASCADE
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (assigned_to_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (opportunity_id) REFERENCES opportunities(id) ON DELETE SET NULL,
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE SET NULL,
    FOREIGN KEY (current_version_id) REFERENCES estimate_versions(id) ON DELETE SET NULL,
    FOREIGN KEY (accepted_version_id) REFERENCES estimate_versions(id) ON DELETE SET NULL,
    FOREIGN KEY (converted_project_id) REFERENCES projects(id) ON DELETE SET NULL,
    FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_estimates_customer_id ON estimates(customer_id);      -- pre-existing
CREATE INDEX IF NOT EXISTS idx_estimates_number ON estimates(estimate_number);       -- pre-existing
CREATE INDEX IF NOT EXISTS idx_estimates_created_by_user_id ON estimates(created_by_user_id);
CREATE INDEX IF NOT EXISTS idx_estimates_assigned_to_user_id ON estimates(assigned_to_user_id);
CREATE INDEX IF NOT EXISTS idx_estimates_workflow_status ON estimates(workflow_status, updated_at);
CREATE INDEX IF NOT EXISTS idx_estimates_project_id ON estimates(project_id);
CREATE INDEX IF NOT EXISTS idx_estimates_opportunity_id ON estimates(opportunity_id);
```

A standalone `_ESTIMATES_TABLE_V2_SQL` module constant (placed near
`_USERS_TABLE_WIDENED_ROLE_SQL`, ~`database.py:989`) holds byte-for-byte the
same DDL but with `CREATE TABLE estimates (` (no `IF NOT EXISTS`) — used only
by `.replace("CREATE TABLE estimates (", "CREATE TABLE _estimates_new_v2 (", 1)`,
mirroring the existing pattern's fail-loud guard if that `.replace()` no-ops.

### `_migrate_estimates_table_v2()` — new method, called where
`_migrate_users_role_constraint()` is called today (`database.py:1207`, own
transaction scope):

- **Idempotency gate:** `PRAGMA table_info(estimates)` — if `workflow_status`
  is already present (or the table doesn't exist yet), no-op.
- **Same 9 steps as `_migrate_users_role_constraint`**: `PRAGMA foreign_keys
  = OFF` (outside any transaction) → `BEGIN IMMEDIATE` → `DROP TABLE IF
  EXISTS _estimates_new_v2` (defense in depth) → `CREATE TABLE
  _estimates_new_v2` (from `_ESTIMATES_TABLE_V2_SQL`) → `INSERT INTO
  _estimates_new_v2 (<old col list>) SELECT <old col list> FROM estimates`
  (new columns take their `DEFAULT`s) → `DROP TABLE estimates` → `ALTER TABLE
  _estimates_new_v2 RENAME TO estimates` → recreate all indexes above →
  restore the preserved `sqlite_sequence` high-water mark for `estimates`
  (`DELETE` + plain `INSERT`, not `INSERT OR REPLACE`) → `PRAGMA foreign_keys
  = ON` (outside transaction) → `PRAGMA foreign_key_check` (raise loudly on
  any violation).
- SQLite does not verify a `FOREIGN KEY REFERENCES` target's existence at
  `CREATE TABLE` time, only at DML time under enforcement — so this rebuild
  is safe even before `estimate_versions` exists on the same `init_schema()`
  pass. No special ordering relative to the new tables' creation is required.
- **No backfill logic needed** (empty-table finding, §0).

### `users` table: one small additive column

`ALTER TABLE users ADD COLUMN requires_estimate_approval INTEGER NOT NULL
DEFAULT 0 CHECK(requires_estimate_approval IN (0, 1));` — added to the
existing `_migrate_schema()` migrations tuple (and to `_SCHEMA_SQL`'s `users`
CREATE TABLE / `_USERS_TABLE_WIDENED_ROLE_SQL` for fresh DBs). This is the
"optional per-user 'requires approval' flag" from `Codey-Estimator`'s D5 —
it's about the *creator*, not any one estimate, so it lives on `users`.

**Verified empirically by the implementer, not assumed** (rule 12): whether a
plain `CHECK` constraint works on a brand-new `ALTER TABLE ADD COLUMN`
against this project's real SQLite (3.53.4) — no existing `ADD COLUMN`
migration in `_migrate_schema()` uses one. If it fails, fall back to a bare
`INTEGER NOT NULL DEFAULT 0` with the 0/1 constraint enforced at the service
layer only (same precedent as `appointment_type_id`).

## 2. New tables

### `estimate_versions` (immutable priced snapshots, integer cents)

```sql
-- Estimate Versions (Codey-Estimator Phase B9.1, NEW). The estimates header
-- (rebuilt above) is mutable identity/workflow metadata; a version is the
-- priced content, and once locked it is never edited again -- revising
-- creates version_number+1 instead. Money columns are INTEGER cents -- the
-- first cents-based table in this codebase; every legacy REAL money column
-- elsewhere stays untouched. calc_engine_version pins
-- codey_estimator.calc.CALC_ENGINE_VERSION (currently 1) so an old estimate
-- can always be re-derived exactly even after the engine's formulas change.
CREATE TABLE IF NOT EXISTS estimate_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estimate_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL,
    is_locked INTEGER NOT NULL DEFAULT 0 CHECK(is_locked IN (0, 1)),
    locked_at TEXT,
    locked_reason TEXT CHECK(locked_reason IN ('sent', 'accepted', 'superseded') OR locked_reason IS NULL),
    material_cost_cents INTEGER NOT NULL DEFAULT 0,
    labor_cost_cents INTEGER NOT NULL DEFAULT 0,
    equipment_cost_cents INTEGER NOT NULL DEFAULT 0,
    sub_cost_cents INTEGER NOT NULL DEFAULT 0,
    cost_total_cents INTEGER NOT NULL DEFAULT 0,
    subtotal_sell_cents INTEGER NOT NULL DEFAULT 0,
    discount_cents INTEGER NOT NULL DEFAULT 0,
    taxable_base_cents INTEGER NOT NULL DEFAULT 0,
    tax_cents INTEGER NOT NULL DEFAULT 0,
    total_cents INTEGER NOT NULL DEFAULT 0,
    gross_profit_cents INTEGER NOT NULL DEFAULT 0,
    gross_margin_bp INTEGER NOT NULL DEFAULT 0,
    calc_engine_version INTEGER NOT NULL,
    tax_rate_bp INTEGER NOT NULL DEFAULT 0,
    terms_snapshot TEXT,
    customer_notes_snapshot TEXT,
    change_summary TEXT,
    created_by_user_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (estimate_id) REFERENCES estimates(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE(estimate_id, version_number)
);
CREATE INDEX IF NOT EXISTS idx_estimate_versions_estimate_id ON estimate_versions(estimate_id);

-- Immutability defense-in-depth -- the service layer must also refuse
-- writes to a locked version; this trigger is the DB-level backstop,
-- matching the append-only trigger convention already used elsewhere in
-- this file.
CREATE TRIGGER IF NOT EXISTS trg_estimate_versions_locked_immutable
BEFORE UPDATE ON estimate_versions
FOR EACH ROW WHEN OLD.is_locked = 1
BEGIN
    SELECT RAISE(ABORT, 'estimate_versions: cannot modify a locked version');
END;
```

### `estimate_line_items` (one table, typed columns)

```sql
-- Estimate Line Items (Codey-Estimator Phase B9.1, NEW). line_type drives
-- which component group applies (mirrors codey_estimator.calc.LineType).
-- Snapshot columns (retailer_code_snapshot, product_title_snapshot,
-- unit_cost_cents, and every pricing-table id below being nullable) mean a
-- line renders identically forever even if the underlying price book item,
-- retailer product, or labor rate later changes or is deactivated.
-- price_book_item_id / retailer_product_id / price_observation_id /
-- labor_rate_id are bare INTEGER, NO FOREIGN KEY -- their target tables are
-- deliberately deferred to a later phase (see §3 below); a future migration
-- attaches real FKs once those tables exist. equipment_id / subcontractor_id
-- DO get real FKs -- those tables already exist in this schema.
CREATE TABLE IF NOT EXISTS estimate_line_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estimate_version_id INTEGER NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    line_type TEXT NOT NULL CHECK(line_type IN ('material', 'labor', 'equipment', 'subcontractor', 'combined', 'allowance', 'fee')),
    section TEXT,
    category TEXT,
    description TEXT,
    customer_description TEXT,
    visible_to_customer INTEGER NOT NULL DEFAULT 1 CHECK(visible_to_customer IN (0, 1)),
    price_book_item_id INTEGER,
    retailer_product_id INTEGER,
    price_observation_id INTEGER,
    retailer_code_snapshot TEXT,
    product_title_snapshot TEXT,
    package_qty REAL,
    package_unit TEXT,
    unit_cost_cents INTEGER,
    quantity REAL,
    unit TEXT,
    waste_pct_bp INTEGER NOT NULL DEFAULT 0,
    material_markup_bp INTEGER NOT NULL DEFAULT 0,
    labor_type TEXT,
    labor_rate_id INTEGER,
    labor_qty REAL,
    labor_unit TEXT,
    labor_cost_rate_cents INTEGER,
    labor_bill_rate_cents INTEGER,
    equipment_id INTEGER,
    equipment_cost_cents INTEGER,
    equipment_markup_bp INTEGER NOT NULL DEFAULT 0,
    subcontractor_id INTEGER,
    sub_cost_cents INTEGER,
    sub_markup_bp INTEGER NOT NULL DEFAULT 0,
    taxable INTEGER NOT NULL DEFAULT 1 CHECK(taxable IN (0, 1)),
    discount_cents INTEGER NOT NULL DEFAULT 0,
    price_override_cents INTEGER,
    override_reason TEXT,
    -- Written by codey_estimator.calc ONLY -- never by the API/UI layer
    -- directly (totals are server-computed, never client-supplied).
    packages_needed INTEGER,
    material_cost_cents INTEGER NOT NULL DEFAULT 0,
    labor_cost_cents INTEGER NOT NULL DEFAULT 0,
    cost_total_cents INTEGER NOT NULL DEFAULT 0,
    sell_total_cents INTEGER NOT NULL DEFAULT 0,
    tax_cents INTEGER NOT NULL DEFAULT 0,
    line_total_cents INTEGER NOT NULL DEFAULT 0,
    internal_note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (estimate_version_id) REFERENCES estimate_versions(id) ON DELETE CASCADE,
    FOREIGN KEY (equipment_id) REFERENCES equipment(id) ON DELETE SET NULL,
    FOREIGN KEY (subcontractor_id) REFERENCES subcontractors(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_estimate_line_items_version_id ON estimate_line_items(estimate_version_id, sort_order);

CREATE TRIGGER IF NOT EXISTS trg_estimate_line_items_locked_update
BEFORE UPDATE ON estimate_line_items
FOR EACH ROW WHEN (SELECT is_locked FROM estimate_versions WHERE id = OLD.estimate_version_id) = 1
BEGIN
    SELECT RAISE(ABORT, 'estimate_line_items: cannot modify a line on a locked version');
END;
CREATE TRIGGER IF NOT EXISTS trg_estimate_line_items_locked_insert
BEFORE INSERT ON estimate_line_items
FOR EACH ROW WHEN (SELECT is_locked FROM estimate_versions WHERE id = NEW.estimate_version_id) = 1
BEGIN
    SELECT RAISE(ABORT, 'estimate_line_items: cannot add a line to a locked version');
END;
CREATE TRIGGER IF NOT EXISTS trg_estimate_line_items_locked_delete
BEFORE DELETE ON estimate_line_items
FOR EACH ROW WHEN (SELECT is_locked FROM estimate_versions WHERE id = OLD.estimate_version_id) = 1
BEGIN
    SELECT RAISE(ABORT, 'estimate_line_items: cannot remove a line from a locked version');
END;
```

### `estimate_share_links` (capability token, only the hash stored)

```sql
-- Estimate Share Links (Codey-Estimator Phase B9.1, NEW). A capability
-- token scoped to exactly one estimate_version_id; it never grants an API
-- session. Only the SHA-256 of the raw token is ever stored (token_hash) --
-- the raw token exists only in the email/URL sent to the customer and is
-- never written here.
CREATE TABLE IF NOT EXISTS estimate_share_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estimate_id INTEGER NOT NULL,
    estimate_version_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    token_hash TEXT NOT NULL,
    created_by_user_id INTEGER,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    revoked_by_user_id INTEGER,
    first_viewed_at TEXT,
    last_viewed_at TEXT,
    view_count INTEGER NOT NULL DEFAULT 0,
    delivery_channel TEXT,
    delivered_to TEXT,
    FOREIGN KEY (estimate_id) REFERENCES estimates(id) ON DELETE CASCADE,
    FOREIGN KEY (estimate_version_id) REFERENCES estimate_versions(id) ON DELETE CASCADE,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL,
    FOREIGN KEY (revoked_by_user_id) REFERENCES users(id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_estimate_share_links_token_hash ON estimate_share_links(token_hash);
CREATE INDEX IF NOT EXISTS idx_estimate_share_links_estimate_id ON estimate_share_links(estimate_id);
```

Default expiry (30 days) is a service-layer default, not a DB default —
`expires_at` is always written explicitly by the service.

### `estimate_decisions` (append-only)

```sql
-- Estimate Decisions (Codey-Estimator Phase B9.1, NEW, append-only). One row
-- per accept/decline/changes-requested action, whether via a share link
-- (share_link_id set, customer_user_id NULL) or the logged-in /portal
-- (customer_user_id set, share_link_id NULL). signer_name +
-- consent_text_snapshot are always required on an 'accepted' row
-- (service-layer enforced); signature_data is optional, reusing the
-- existing contract signature pad.
CREATE TABLE IF NOT EXISTS estimate_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estimate_version_id INTEGER NOT NULL,
    share_link_id INTEGER,
    customer_user_id INTEGER,
    decision TEXT NOT NULL CHECK(decision IN ('accepted', 'declined', 'changes_requested')),
    signer_name TEXT,
    signature_data TEXT,
    consent_text_snapshot TEXT,
    comment TEXT,
    ip TEXT,
    user_agent TEXT,
    decided_at TEXT NOT NULL,
    FOREIGN KEY (estimate_version_id) REFERENCES estimate_versions(id) ON DELETE CASCADE,
    FOREIGN KEY (share_link_id) REFERENCES estimate_share_links(id) ON DELETE SET NULL,
    FOREIGN KEY (customer_user_id) REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_estimate_decisions_version_id ON estimate_decisions(estimate_version_id);
```

### `documents`: additive, existing table

```sql
ALTER TABLE documents ADD COLUMN estimate_id INTEGER;               -- bare, no FK: ALTER TABLE ADD COLUMN can't attach one
ALTER TABLE documents ADD COLUMN customer_visible INTEGER NOT NULL DEFAULT 0 CHECK(customer_visible IN (0, 1));  -- verify CHECK-on-ADD-COLUMN empirically first, same as users.requires_estimate_approval
```

`document_type`'s existing CHECK already includes `'estimate'` — no change
needed there.

## 3. Pricing tables: deferred to a later phase (not built this round)

`retailers`, `retailer_stores`, `retailer_products`, `price_observations`,
`canonical_materials`, `material_matches`, `product_search_fts`,
`search_cache`, `pricing_jobs`, `price_book_items`, `labor_rates`, and
`labor_rate_history` all stay out of this round:

1. They depend on `codey_estimator.ports.py`'s exact repository-Protocol
   shapes (already built — `retailer_code`/`store_code` as strings, not Core
   integer ids, per the library's own Phase 4b decisions), a genuinely
   separate integration surface from the estimate/version/line-item schema.
2. `estimate_line_items` above is deliberately schema-compatible with them
   arriving later (bare-int-no-FK on the four pricing-table ids) — nothing
   in this round blocks that follow-on phase or needs revisiting.
3. Rule 1 (one thing at a time) — this round is already a real rebuild plus
   four new tables; folding in FTS5, a token-bucket/circuit-breaker-backed
   refresh table, and the scraper's own accepted-risk posture would make
   this round unreviewable as one unit.

This becomes its own phase, directly after this one, once `ports.py`'s
repository implementations are ready to bind against real tables.

## 4. New permission constants (`auth.py`)

```python
PERM_READ_ALL_ESTIMATES = "read:all_estimates"        # unrestricted read of every estimate, no ownership narrowing
PERM_READ_ESTIMATE_COSTS = "read:estimate_costs"      # gates cost/margin/GP fields in the served DTO
PERM_REASSIGN_ESTIMATES = "reassign:estimates"        # change assigned_to_user_id (PERM_REASSIGN_PROJECT_STAFF precedent)
PERM_SEND_ESTIMATES = "send:estimates"                # DRAFT/APPROVED_INTERNAL -> SENT transition (ai_agent NEVER gets this)
PERM_APPROVE_ESTIMATES = "approve:estimates"          # INTERNAL_REVIEW -> APPROVED_INTERNAL transition
PERM_MANAGE_PRICE_BOOK = "manage:price_book"          # declared now, unused until the pricing-tables phase
```

**Default role grants** (additive to the existing `ROLE_PERMISSIONS` sets,
`auth.py:218-497`):

| Role | + grants | Why |
|---|---|---|
| `ROLE_ADMIN` | all six | unrestricted, matches every existing pattern |
| `ROLE_MANAGER` | all six | same |
| `ROLE_SALES` | `PERM_READ_ESTIMATE_COSTS`, `PERM_SEND_ESTIMATES` | sales sees cost/margin on every estimate; can send. **Not** `PERM_READ_ALL_ESTIMATES` (stays scoped to own/assigned/unclaimed once a future service-layer phase adds real narrowing), **not** `PERM_REASSIGN_ESTIMATES`/`PERM_APPROVE_ESTIMATES`/`PERM_MANAGE_PRICE_BOOK` (editing rates/markups is admin/manager only) |
| `ROLE_SALES_MANAGER` (derived line, `auth.py:509`) | update to `ROLE_PERMISSIONS[ROLE_SALES] \| {PERM_READ_TEAM_SALES_DATA, PERM_READ_ALL_ESTIMATES, PERM_REASSIGN_ESTIMATES, PERM_APPROVE_ESTIMATES}` | team-wide visibility + reassignment + internal-review approval, same "derived so it can't drift" reasoning already documented at that line |
| `ROLE_PROJECT_MANAGER` | `PERM_READ_ESTIMATE_COSTS` | **Ish's decision, 2026-09-27: keep current behavior** — today's `_row_to_estimate` already lets PMs see cost (its `is_customer` gate only excludes `ROLE_CUSTOMER`/`ROLE_TECHNICIAN`); this formalizes that under the new permission system rather than narrowing it |
| `ROLE_TECHNICIAN` | none | unchanged |
| `ROLE_AI_AGENT` | `PERM_WRITE_ESTIMATES` (fixes a real pre-existing gap — see NEW-544), `PERM_READ_ALL_ESTIMATES`, `PERM_READ_ESTIMATE_COSTS` | preserves today's de facto behavior and satisfies the library's D11 ("read/search/draft-create permissions"). **Never** `PERM_SEND_ESTIMATES` (hard requirement — an autonomous agent must never email a customer a price without a human clicking send), **never** `PERM_APPROVE_ESTIMATES`/`PERM_REASSIGN_ESTIMATES`/`PERM_MANAGE_PRICE_BOOK` |
| `ROLE_CUSTOMER` | none | unaffected; keeps `PERM_READ_OWN_ESTIMATES` only |

`PERMISSIONS_CATALOG`'s existing `"estimates"` domain block
(`auth.py:557-559`) gets six new entries, same `{"id", "name", "description"}`
shape as the three already there.

See `NEW_ISSUES.md` [NEW-544] for the pre-existing `ROLE_AI_AGENT` gap this
round also fixes.

## 5. Where the migration goes, and the "done" bar

- **New tables + triggers**: appended to `_SCHEMA_SQL`, after the existing
  `estimates`/`contracts` blocks — fresh-DB-safe via `IF NOT EXISTS`, no
  migration logic needed for them.
- **`estimates` rebuild**: `_SCHEMA_SQL`'s `estimates` literal replaced with
  the v2 shape (§1); new `_migrate_estimates_table_v2()` called from
  `_migrate_schema()` at the same spot `_migrate_users_role_constraint()` is
  called today.
- **`users.requires_estimate_approval`, `documents.estimate_id`/
  `customer_visible`**: added to the existing additive migrations tuple.
- **Rehearsal**: still warranted per rule 4 — rehearse on a **copy** of the
  live `~/.codeyOS/restoricon.db`, confirm `PRAGMA foreign_key_check` is
  clean before and after, confirm `users`/`api_tokens`/`staff_schedules`/
  `contracts`/`documents` row counts are byte-for-byte unchanged except for
  the new/altered columns. Lower-stakes than a populated-`estimates`-table
  rehearsal, but not skipped — an empty-table rebuild never actually run
  against a copy of the real file is still an unrehearsed rebuild.

**What "done" means for this round, stated so it can't be conflated later:**
- **code-complete**: the DDL lands in `database.py`, `_migrate_estimates_table_v2()`
  is written and unit-tested against a synthetic SQLite DB built through the
  real `DatabaseManager`/`_SCHEMA_SQL` (both a fresh-DB path and a
  pre-existing-legacy-shape path), the new `auth.py` permission constants and
  `ROLE_PERMISSIONS` grants land, `PERMISSIONS_CATALOG` is updated.
- **code-reviewer-approved**: mandatory before commit (rule 4). The reviewer
  independently verifies the CHECK-on-ADD-COLUMN behavior against the real
  installed SQLite, not on faith.
- **NOT live-verified this round, and must not be represented as such**: no
  session working on this had access to the real phone/device. Live
  verification — running this migration against a copy of the actual
  `~/.codeyOS/restoricon.db`, confirming `PRAGMA foreign_key_check` clean,
  confirming row-count/content parity outside the intended change — is
  explicitly out of scope here and must happen in a session with device
  access before this is merged to `main` and deployed.

## 6. Deferred/inert this round

- `estimate_number`'s `EST-{YYYY}-{NNNN}` server-generated numbering sequence
  (the increment logic) is deferred to the service-layer phase (B9.2+) —
  it's inert schema without that logic. `estimate_number` stays a plain
  `UNIQUE NOT NULL TEXT` column regardless.
- The `CustomerEstimateView` allow-list serializer is already built in the
  `Codey-Estimator` library (`codey_estimator.dto.CustomerEstimateView`,
  `to_customer_view`) — the next phase reuses it, does not reinvent it,
  per the library/Core boundary decision.

## Live verification checklist (for a session with device access)

1. Back up first, per the B7 backup discipline already in place.
2. Copy `~/.codeyOS/restoricon.db` to a scratch path.
3. Point `RESTORICON_DB_PATH` at the copy and run the Core's normal startup
   (which runs `_migrate_schema()`).
4. `PRAGMA foreign_key_check` — must be clean.
5. Confirm `users`, `api_tokens`, `staff_schedules`, `contracts`, `documents`
   row counts are unchanged (except the new/altered columns on `documents`).
6. Confirm `estimates` still has 0 rows, `estimate_number` uniqueness intact,
   the new `workflow_status` column defaults to `DRAFT`.
7. Confirm the `users.requires_estimate_approval` `ADD COLUMN` with `CHECK`
   actually succeeded against the real SQLite build (§1's flagged risk) —
   if it failed, the implementer's documented fallback (bare int, no CHECK)
   needs to be applied instead, on the real device, before this merges.
8. Only after all of the above pass clean does this get merged to `main`.
